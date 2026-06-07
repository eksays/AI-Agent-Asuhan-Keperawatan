from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Header, Request
from fastapi.responses import JSONResponse

from lab_config import lab_disabled_payload, lab_status_payload, sprint_b_feature_enabled, synthetic_lab_enabled
from lab_core import FEATURE_LABELS, base_lab_response, lab_error, trace_payload
from lab_ebp import ebp_payload, load_offline_ebp_fixture
from lab_feedback import LabFeedbackError, LabFeedbackStore
from lab_fixture_loader import LabFixtureError, SyntheticFixtureLoader
from lab_mermaid import load_safe_mermaid_fixture
from lab_mocks import run_ocr_mock, run_photo_mock
from lab_orchestration import run_deterministic_orchestration
from lab_rag import rag_payload, retrieve_synthetic_context
from lab_registry import load_synthetic_registry, reject_non_manifest_code
from lab_trace_store import LabTraceStore
from lab_uploads import run_synthetic_upload_fixture
from security_controls import AuthPrincipal, constant_time_equal, issue_secret_token, token_digest
from upload_security import config_from_app


class LabSessionStore:
    def __init__(self, *, ttl_sec: int = 600, max_active: int = 256, now_func: Callable[[], float] = time.monotonic) -> None:
        self.ttl_sec = max(60, int(ttl_sec))
        self.max_active = max(1, int(max_active))
        self._now = now_func
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, object]] = {}

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def count(self) -> int:
        with self._lock:
            self._cleanup_locked()
            return len(self._records)

    def issue(self, principal: AuthPrincipal, pepper: str) -> tuple[str, str]:
        session_id = "lab_" + secrets.token_urlsafe(24)
        session_token = issue_secret_token()
        now = self._now()
        with self._lock:
            self._cleanup_locked()
            while len(self._records) >= self.max_active:
                oldest = min(self._records, key=lambda sid: float(self._records[sid].get("last_access", 0)))
                self._records.pop(oldest, None)
            self._records[session_id] = {
                "owner": principal.principal_id,
                "token_digest": token_digest(session_token, pepper),
                "created_at": now,
                "last_access": now,
                "expires_at": now + self.ttl_sec,
            }
        return session_id, session_token

    def validate(self, session_id: str, principal: AuthPrincipal, session_token: str, pepper: str) -> str:
        now = self._now()
        with self._lock:
            self._cleanup_locked()
            rec = self._records.get(session_id or "")
            if not rec:
                return "session_not_found"
            if now >= float(rec.get("expires_at", 0)):
                self._records.pop(session_id, None)
                return "session_expired"
            if rec.get("owner") != principal.principal_id:
                return "session_owner_mismatch"
            if not session_token or not constant_time_equal(str(rec.get("token_digest", "")), token_digest(session_token, pepper)):
                return "session_token_invalid"
            rec["last_access"] = now
            return "ok"

    def _cleanup_locked(self) -> None:
        now = self._now()
        for session_id, rec in list(self._records.items()):
            if now >= float(rec.get("expires_at", 0)):
                self._records.pop(session_id, None)


LAB_SESSION_STORE = LabSessionStore()
LAB_TRACE_STORE = LabTraceStore()
LAB_FEEDBACK_STORE = LabFeedbackStore()

FEATURE_FLAG_BY_ROUTE = {
    "run": "synthetic_multi_agent",
    "rag": "synthetic_rag",
    "registry": "synthetic_registry",
    "ebp": "synthetic_ebp",
    "upload": "synthetic_uploads",
    "pathway": "synthetic_mermaid",
    "ocr": "synthetic_ocr_mock",
    "photo": "synthetic_photo_mock",
    "feedback": "synthetic_feedback_memory",
}


def create_lab_router(
    get_config: Callable[[], object],
    auth_context: Callable[[Request, Optional[str], str], tuple[AuthPrincipal | None, str, JSONResponse | None]],
    security_response: Callable[[str], JSONResponse],
    security_pepper: str,
    audit_callback: Callable[..., bool] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/lab", tags=["synthetic-lab"])

    def guard() -> JSONResponse | None:
        if synthetic_lab_enabled(get_config()):
            return None
        return JSONResponse(lab_disabled_payload(), status_code=503)

    def _payload(payload: dict[str, Any] | None) -> dict[str, Any]:
        return payload if isinstance(payload, dict) else {}

    def _loader(cfg: object) -> SyntheticFixtureLoader:
        return SyntheticFixtureLoader(str(getattr(cfg, "synthetic_lab_fixture_root", "")))

    def _feature_disabled(feature: str) -> JSONResponse | None:
        cfg = get_config()
        field = FEATURE_FLAG_BY_ROUTE[feature]
        if sprint_b_feature_enabled(cfg, field):
            return None
        return JSONResponse(
            lab_error("lab_feature_disabled", f"Synthetic lab feature is disabled: {feature}."),
            status_code=503,
        )

    def _protected(
        request: Request,
        authorization: Optional[str],
        lab_session_id: Optional[str],
        lab_session_token: Optional[str],
        feature: str | None = None,
    ) -> tuple[object | None, AuthPrincipal | None, JSONResponse | None]:
        disabled = guard()
        if disabled:
            return None, None, disabled
        if feature is not None:
            feature_disabled = _feature_disabled(feature)
            if feature_disabled:
                return None, None, feature_disabled
        principal, _key, error = auth_context(request, authorization, "LAB")
        if error:
            return None, None, error
        assert principal is not None
        status = LAB_SESSION_STORE.validate(lab_session_id or "", principal, lab_session_token or "", security_pepper)
        if status != "ok":
            return None, None, security_response(status)
        return get_config(), principal, None

    def _emit(event_type: str, principal: AuthPrincipal, route: str, run_id: str, fixture_id: str, feature_label: str, status_code: int = 200) -> bool:
        if audit_callback is None:
            return False
        return bool(audit_callback(
            event_type,
            actor_type="api_principal",
            actor_id=principal.credential_fingerprint,
            route_class="LAB",
            action=route,
            outcome="synthetic_lab_safe_metadata_only",
            status_code=status_code,
            security_tags=("lab", "privacy"),
            metadata={"run_id": run_id, "fixture_id": fixture_id, "feature_label": feature_label, "route": route},
        ))

    def _trace_and_audit(payload: dict[str, Any], event_type: str, principal: AuthPrincipal, route: str, fixture_id: str, feature_label: str, lab_session_id: str) -> dict[str, Any]:
        trace = LAB_TRACE_STORE.create({**payload, "audit_event_ids": [event_type]}, owner_id=principal.principal_id, lab_session_id=lab_session_id)
        _emit(event_type, principal, route, trace["run_id"], fixture_id, feature_label)
        return trace

    def _safe_error(exc: Exception, status_code: int = 400) -> JSONResponse:
        if isinstance(exc, LabFixtureError):
            code = "lab_fixture_rejected"
        elif isinstance(exc, LabFeedbackError):
            code = "lab_feedback_rejected"
        else:
            code = "lab_safe_failure"
        return JSONResponse(lab_error(code, "Synthetic lab request was rejected safely."), status_code=status_code)

    @router.get("/status")
    def lab_status():
        disabled = guard()
        if disabled:
            return disabled
        return lab_status_payload(get_config())

    @router.post("/session")
    def lab_session(request: Request, authorization: Optional[str] = Header(None)):
        disabled = guard()
        if disabled:
            return disabled
        principal, _key, error = auth_context(request, authorization, "LAB")
        if error:
            return error
        assert principal is not None
        session_id, session_token = LAB_SESSION_STORE.issue(principal, security_pepper)
        return {
            "status": "sukses",
            "lab_session_id": session_id,
            "lab_session_token": session_token,
            "lab_session_ttl_sec": LAB_SESSION_STORE.ttl_sec,
            "lab_namespace": "/lab",
        }

    @router.get("/trace/{run_id}")
    def lab_trace(
        request: Request,
        run_id: str,
        authorization: Optional[str] = Header(None),
        lab_session_id: Optional[str] = Header(None, alias="X-Lab-Session-Id"),
        lab_session_token: Optional[str] = Header(None, alias="X-Lab-Session-Token"),
    ):
        disabled = guard()
        if disabled:
            return disabled
        principal, _key, error = auth_context(request, authorization, "LAB")
        if error:
            return error
        assert principal is not None
        status = LAB_SESSION_STORE.validate(lab_session_id or "", principal, lab_session_token or "", security_pepper)
        if status != "ok":
            return security_response(status)
        trace = LAB_TRACE_STORE.get(run_id, owner_id=principal.principal_id, lab_session_id=lab_session_id or "")
        if trace is None:
            return JSONResponse(
                {"status": "error", "error_code": "lab_trace_not_found", "message": "Synthetic lab trace not found."},
                status_code=404,
            )
        return {"status": "sukses", "trace": trace}

    @router.post("/run")
    def lab_run(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
        authorization: Optional[str] = Header(None),
        lab_session_id: Optional[str] = Header(None, alias="X-Lab-Session-Id"),
        lab_session_token: Optional[str] = Header(None, alias="X-Lab-Session-Token"),
    ):
        cfg, principal, error = _protected(request, authorization, lab_session_id, lab_session_token, "run")
        if error:
            return error
        disabled = _feature_disabled("run")
        if disabled:
            return disabled
        assert cfg is not None and principal is not None
        body = _payload(payload)
        loader = _loader(cfg)
        try:
            case_fixture_id = str(body.get("fixture_id") or "SYN-CASE-RESP-001")
            case = loader.load_fixture_by_id(case_fixture_id, prefix="cases/")
            query = str(body.get("query") or case.get("query") or "")
            rag_result = retrieve_synthetic_context(loader, fixture_id=str(body.get("rag_fixture_id") or "SYN-RAG-RESP-001"), query=query) if sprint_b_feature_enabled(cfg, "synthetic_rag") else None
            registry_result = load_synthetic_registry(loader, fixture_id=str(body.get("registry_fixture_id") or "SYN-REG-001")) if sprint_b_feature_enabled(cfg, "synthetic_registry") else None
            result = run_deterministic_orchestration(
                case_fixture=case,
                rag_result=rag_result,
                registry_result=registry_result,
                force_stage_failure=str(body.get("force_stage_failure") or ""),
                force_timeout=bool(body.get("force_timeout") is True),
            )
            trace = _trace_and_audit(trace_payload(
                fixture_case_id=case_fixture_id,
                route="/lab/run",
                feature_label=result.feature_label,
                agent_stages=[stage.name for stage in result.stages],
                stage_status=[stage.status for stage in result.stages],
                stage_latency_ms=[stage.latency_ms for stage in result.stages],
                stage_reason_codes=[stage.reason_code for stage in result.stages],
                retrieved_document_ids=rag_result.retrieved_document_ids if rag_result else [],
                retrieval_scores=rag_result.retrieval_scores if rag_result else [],
                retrieval_source=rag_result.retrieval_source if rag_result else "none",
                corpus_version=rag_result.corpus_version if rag_result else "",
                weak_context=bool(rag_result.weak_context) if rag_result else True,
                registry_source=registry_result.registry_source if registry_result else "none",
                prototype_candidate_ids=registry_result.candidate_ids if registry_result else [],
                missing_data=result.missing_data,
                validation_issue_codes=result.validation_issue_codes,
                latency_ms=sum(stage.latency_ms for stage in result.stages),
            ), "lab_feature_run", principal, "/lab/run", case_fixture_id, result.feature_label, lab_session_id or "")
            return base_lab_response(
                feature_label=result.feature_label,
                run_id=trace["run_id"],
                clinical_status=result.clinical_status,
                missing_data=result.missing_data,
                validation_issue_codes=result.validation_issue_codes,
                prototype_candidates=result.prototype_candidates,
                extra={"critic_applied": result.critic_applied, "trace": trace},
            )
        except Exception as exc:
            return _safe_error(exc)

    @router.post("/rag")
    def lab_rag(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
        authorization: Optional[str] = Header(None),
        lab_session_id: Optional[str] = Header(None, alias="X-Lab-Session-Id"),
        lab_session_token: Optional[str] = Header(None, alias="X-Lab-Session-Token"),
    ):
        cfg, principal, error = _protected(request, authorization, lab_session_id, lab_session_token, "rag")
        if error:
            return error
        disabled = _feature_disabled("rag")
        if disabled:
            return disabled
        assert cfg is not None and principal is not None
        body = _payload(payload)
        try:
            fixture_id = str(body.get("fixture_id") or "SYN-RAG-RESP-001")
            result = retrieve_synthetic_context(_loader(cfg), fixture_id=fixture_id, query=str(body.get("query") or ""))
            trace = _trace_and_audit(trace_payload(
                fixture_case_id=fixture_id,
                route="/lab/rag",
                feature_label=FEATURE_LABELS["rag"],
                agent_stages=["retrieval"],
                stage_status=["weak_context" if result.weak_context else "complete"],
                stage_latency_ms=[1],
                stage_reason_codes=["synthetic_fixture_lexical"],
                retrieved_document_ids=result.retrieved_document_ids,
                retrieval_scores=result.retrieval_scores,
                retrieval_source=result.retrieval_source,
                corpus_version=result.corpus_version,
                weak_context=result.weak_context,
                validation_issue_codes=["weak_context"] if result.weak_context else ["synthetic_only_not_clinical"],
            ), "lab_rag_retrieval", principal, "/lab/rag", fixture_id, FEATURE_LABELS["rag"], lab_session_id or "")
            return base_lab_response(feature_label=FEATURE_LABELS["rag"], run_id=trace["run_id"], validation_issue_codes=trace["validation_issue_codes"], extra={**rag_payload(result), "trace": trace})
        except Exception as exc:
            return _safe_error(exc)

    @router.post("/registry")
    def lab_registry(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
        authorization: Optional[str] = Header(None),
        lab_session_id: Optional[str] = Header(None, alias="X-Lab-Session-Id"),
        lab_session_token: Optional[str] = Header(None, alias="X-Lab-Session-Token"),
    ):
        cfg, principal, error = _protected(request, authorization, lab_session_id, lab_session_token, "registry")
        if error:
            return error
        disabled = _feature_disabled("registry")
        if disabled:
            return disabled
        assert cfg is not None and principal is not None
        body = _payload(payload)
        try:
            fixture_id = str(body.get("fixture_id") or "SYN-REG-001")
            result = load_synthetic_registry(_loader(cfg), fixture_id=fixture_id)
            code = str(body.get("code") or "")
            if code and reject_non_manifest_code(_loader(cfg), registry_fixture_id=fixture_id, code=code):
                return JSONResponse(lab_error("lab_registry_code_rejected", "Synthetic registry code is not manifest-approved."), status_code=400)
            trace = _trace_and_audit(trace_payload(
                fixture_case_id=fixture_id,
                route="/lab/registry",
                feature_label=FEATURE_LABELS["registry"],
                agent_stages=["registry_fixture_load"],
                stage_status=["complete"],
                stage_latency_ms=[1],
                stage_reason_codes=["non_authoritative_fixture"],
                registry_source=result.registry_source,
                prototype_candidate_ids=result.candidate_ids,
                validation_issue_codes=["synthetic_registry_not_authoritative"],
            ), "lab_registry_fixture_run", principal, "/lab/registry", fixture_id, FEATURE_LABELS["registry"], lab_session_id or "")
            return base_lab_response(feature_label=FEATURE_LABELS["registry"], run_id=trace["run_id"], prototype_candidates=result.prototype_candidates, validation_issue_codes=trace["validation_issue_codes"], extra={"trace": trace})
        except Exception as exc:
            return _safe_error(exc)

    @router.post("/ebp")
    def lab_ebp(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
        authorization: Optional[str] = Header(None),
        lab_session_id: Optional[str] = Header(None, alias="X-Lab-Session-Id"),
        lab_session_token: Optional[str] = Header(None, alias="X-Lab-Session-Token"),
    ):
        cfg, principal, error = _protected(request, authorization, lab_session_id, lab_session_token, "ebp")
        if error:
            return error
        disabled = _feature_disabled("ebp")
        if disabled:
            return disabled
        assert cfg is not None and principal is not None
        body = _payload(payload)
        try:
            fixture_id = str(body.get("fixture_id") or "SYN-EBP-RESP-001")
            result = load_offline_ebp_fixture(_loader(cfg), fixture_id=fixture_id)
            trace = _trace_and_audit(trace_payload(
                fixture_case_id=fixture_id,
                route="/lab/ebp",
                feature_label=FEATURE_LABELS["ebp"],
                agent_stages=["offline_ebp_fixture"],
                stage_status=["complete"],
                stage_latency_ms=[1],
                stage_reason_codes=["offline_fixture_not_current_evidence"],
                retrieved_document_ids=result.reference_ids,
                retrieval_scores=[1.0 for _ in result.reference_ids],
                retrieval_source="offline_synthetic_ebp_fixture",
                validation_issue_codes=["offline_fixture_not_medical_evidence"],
            ), "lab_ebp_fixture_run", principal, "/lab/ebp", fixture_id, FEATURE_LABELS["ebp"], lab_session_id or "")
            return base_lab_response(feature_label=FEATURE_LABELS["ebp"], run_id=trace["run_id"], validation_issue_codes=trace["validation_issue_codes"], extra={**ebp_payload(result), "trace": trace})
        except Exception as exc:
            return _safe_error(exc)

    @router.post("/upload")
    def lab_upload(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
        authorization: Optional[str] = Header(None),
        lab_session_id: Optional[str] = Header(None, alias="X-Lab-Session-Id"),
        lab_session_token: Optional[str] = Header(None, alias="X-Lab-Session-Token"),
    ):
        cfg, principal, error = _protected(request, authorization, lab_session_id, lab_session_token, "upload")
        if error:
            return error
        disabled = _feature_disabled("upload")
        if disabled:
            return disabled
        assert cfg is not None and principal is not None
        body = _payload(payload)
        try:
            fixture_id = str(body.get("fixture_id") or "SYN-UPLOAD-TXT-001")
            result = run_synthetic_upload_fixture(_loader(cfg), fixture_id=fixture_id, parser_config=config_from_app(cfg))
            parser = result.parser_result
            trace = _trace_and_audit(trace_payload(
                fixture_case_id=fixture_id,
                route="/lab/upload",
                feature_label=FEATURE_LABELS["upload"],
                agent_stages=["fixture_select", "upload_parser"],
                stage_status=["complete", parser.status],
                stage_latency_ms=[1, 1],
                stage_reason_codes=["manifest_fixture", "parser_status_" + parser.status],
                validation_issue_codes=["upload_" + parser.status],
            ), "lab_upload_fixture_run", principal, "/lab/upload", fixture_id, FEATURE_LABELS["upload"], lab_session_id or "")
            return base_lab_response(feature_label=FEATURE_LABELS["upload"], run_id=trace["run_id"], validation_issue_codes=trace["validation_issue_codes"], extra={"upload_status": parser.status, "detected_type": parser.detected_type, "parser_invoked": parser.parser_invoked, "extracted_text_chars": len(parser.text), "trace": trace})
        except Exception as exc:
            return _safe_error(exc)

    @router.post("/pathway")
    def lab_pathway(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
        authorization: Optional[str] = Header(None),
        lab_session_id: Optional[str] = Header(None, alias="X-Lab-Session-Id"),
        lab_session_token: Optional[str] = Header(None, alias="X-Lab-Session-Token"),
    ):
        cfg, principal, error = _protected(request, authorization, lab_session_id, lab_session_token, "pathway")
        if error:
            return error
        disabled = _feature_disabled("pathway")
        if disabled:
            return disabled
        assert cfg is not None and principal is not None
        body = _payload(payload)
        try:
            fixture_id = str(body.get("fixture_id") or "SYN-MMD-SAFE-001")
            result = load_safe_mermaid_fixture(_loader(cfg), fixture_id=fixture_id)
            trace = _trace_and_audit(trace_payload(
                fixture_case_id=fixture_id,
                route="/lab/pathway",
                feature_label=FEATURE_LABELS["pathway"],
                agent_stages=["fixture_mermaid", "sanitizer_boundary"],
                stage_status=["complete", "frontend_sanitizer_required"],
                stage_latency_ms=[1, 1],
                stage_reason_codes=["safe_fixture", "strict_svg_sanitizer_boundary"],
                validation_issue_codes=["synthetic_mermaid_not_clinical"],
            ), "lab_mermaid_fixture_run", principal, "/lab/pathway", fixture_id, FEATURE_LABELS["pathway"], lab_session_id or "")
            return base_lab_response(feature_label=FEATURE_LABELS["pathway"], run_id=trace["run_id"], validation_issue_codes=trace["validation_issue_codes"], extra={"mermaid": result.mermaid_code, "sanitizer_boundary": result.sanitizer_boundary, "trace": trace})
        except Exception as exc:
            return _safe_error(exc)

    @router.post("/ocr")
    def lab_ocr(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
        authorization: Optional[str] = Header(None),
        lab_session_id: Optional[str] = Header(None, alias="X-Lab-Session-Id"),
        lab_session_token: Optional[str] = Header(None, alias="X-Lab-Session-Token"),
    ):
        cfg, principal, error = _protected(request, authorization, lab_session_id, lab_session_token, "ocr")
        if error:
            return error
        disabled = _feature_disabled("ocr")
        if disabled:
            return disabled
        assert cfg is not None and principal is not None
        fixture_id = str(_payload(payload).get("fixture_id") or "SYN-OCR-001")
        try:
            result = run_ocr_mock(_loader(cfg), fixture_id=fixture_id)
            trace = _trace_and_audit(trace_payload(fixture_case_id=fixture_id, route="/lab/ocr", feature_label=FEATURE_LABELS["ocr"], agent_stages=["ocr_mock"], stage_status=["complete"], stage_latency_ms=[1], stage_reason_codes=["deterministic_mock"], validation_issue_codes=["ocr_mock_unverified"]), "lab_mock_ocr_run", principal, "/lab/ocr", fixture_id, FEATURE_LABELS["ocr"], lab_session_id or "")
            return base_lab_response(feature_label=result.label, run_id=trace["run_id"], validation_issue_codes=trace["validation_issue_codes"], extra={"mock_label": result.label, "extracted_fields": result.extracted_fields, "trace": trace})
        except Exception as exc:
            return _safe_error(exc)

    @router.post("/photo")
    def lab_photo(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
        authorization: Optional[str] = Header(None),
        lab_session_id: Optional[str] = Header(None, alias="X-Lab-Session-Id"),
        lab_session_token: Optional[str] = Header(None, alias="X-Lab-Session-Token"),
    ):
        cfg, principal, error = _protected(request, authorization, lab_session_id, lab_session_token, "photo")
        if error:
            return error
        disabled = _feature_disabled("photo")
        if disabled:
            return disabled
        assert cfg is not None and principal is not None
        fixture_id = str(_payload(payload).get("fixture_id") or "SYN-PHOTO-001")
        try:
            result = run_photo_mock(_loader(cfg), fixture_id=fixture_id)
            trace = _trace_and_audit(trace_payload(fixture_case_id=fixture_id, route="/lab/photo", feature_label=FEATURE_LABELS["photo"], agent_stages=["photo_mock"], stage_status=["complete"], stage_latency_ms=[1], stage_reason_codes=["deterministic_mock"], validation_issue_codes=["photo_mock_not_clinical"]), "lab_mock_photo_run", principal, "/lab/photo", fixture_id, FEATURE_LABELS["photo"], lab_session_id or "")
            return base_lab_response(feature_label=result.label, run_id=trace["run_id"], validation_issue_codes=trace["validation_issue_codes"], extra={"mock_label": result.label, "extracted_fields": result.extracted_fields, "trace": trace})
        except Exception as exc:
            return _safe_error(exc)

    @router.post("/feedback")
    def lab_feedback(
        request: Request,
        payload: dict[str, Any] | None = Body(default=None),
        authorization: Optional[str] = Header(None),
        lab_session_id: Optional[str] = Header(None, alias="X-Lab-Session-Id"),
        lab_session_token: Optional[str] = Header(None, alias="X-Lab-Session-Token"),
    ):
        cfg, principal, error = _protected(request, authorization, lab_session_id, lab_session_token, "feedback")
        if error:
            return error
        disabled = _feature_disabled("feedback")
        if disabled:
            return disabled
        assert principal is not None
        body = _payload(payload)
        try:
            feedback_id = str(body.get("feedback_id") or "SYN-FB-001")
            result = LAB_FEEDBACK_STORE.record(lab_session_id or "", feedback_id=feedback_id, rating=str(body.get("rating") or "neutral"), note=str(body.get("note") or ""))
            trace = _trace_and_audit(trace_payload(fixture_case_id=feedback_id, route="/lab/feedback", feature_label=FEATURE_LABELS["feedback"], agent_stages=["feedback_record"], stage_status=["complete"], stage_latency_ms=[1], stage_reason_codes=["lab_namespace_only"], validation_issue_codes=["not_authoritative_learning"]), "lab_feedback_recorded", principal, "/lab/feedback", feedback_id, FEATURE_LABELS["feedback"], lab_session_id or "")
            return base_lab_response(feature_label=FEATURE_LABELS["feedback"], run_id=trace["run_id"], validation_issue_codes=trace["validation_issue_codes"], extra={"feedback_count": result["feedback_count"], "trace": trace})
        except Exception as exc:
            return _safe_error(exc)

    return router
