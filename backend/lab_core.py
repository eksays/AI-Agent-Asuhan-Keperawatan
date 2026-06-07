from __future__ import annotations

from typing import Any

LAB_MODE = "synthetic_integration_lab"
PROTOTYPE_STATUS = "synthetic_prototype_abstention"
NOT_FOR_PATIENT_CARE = "not_for_patient_care"
TRACE_SANITIZATION_STATUS = "safe_metadata_only"

FEATURE_LABELS = {
    "run": "multi-stage agent orchestration prototype",
    "rag": "synthetic lexical RAG prototype",
    "registry": "lab-only synthetic registry fixture",
    "ebp": "offline synthetic EBP fixture",
    "upload": "real local upload parser with synthetic fixture",
    "pathway": "Mermaid sanitizer fixture route",
    "ocr": "DETERMINISTIC OCR MOCK - EXTRACTION UNVERIFIED",
    "photo": "DETERMINISTIC PHOTO MOCK - NOT CLINICAL IMAGE ANALYSIS",
    "feedback": "isolated synthetic feedback memory",
}

LABEL_CLASSES = {
    "auth": "REAL LOCAL PATH",
    "session": "REAL LOCAL PATH",
    "audit": "REAL LOCAL PATH",
    "upload": "REAL LOCAL PATH",
    "validator": "REAL LOCAL PATH",
    "abstention": "REAL LOCAL PATH",
    "orchestration": "SYNTHETIC PROTOTYPE",
    "rag": "SYNTHETIC PROTOTYPE",
    "registry": "SYNTHETIC PROTOTYPE",
    "ebp": "SYNTHETIC PROTOTYPE",
    "mermaid": "SYNTHETIC PROTOTYPE",
    "ocr": "DETERMINISTIC MOCK",
    "photo": "DETERMINISTIC MOCK",
    "external_provider": "FORBIDDEN IN LAB",
}

def base_lab_response(
    *,
    feature_label: str,
    run_id: str = "",
    clinical_status: str = PROTOTYPE_STATUS,
    missing_data: list[str] | None = None,
    validation_issue_codes: list[str] | None = None,
    prototype_candidates: list[dict[str, Any]] | None = None,
    trace_url: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "sukses",
        "mode": LAB_MODE,
        "feature_label": feature_label,
        "run_id": run_id,
        "clinical_status": clinical_status,
        "accepted_recommendations": False,
        "nurse_review_required": True,
        "registry_authoritative": False,
        "clinical_use_allowed": False,
        "missing_data": missing_data or [],
        "validation_issue_codes": validation_issue_codes or [],
        "prototype_candidates": prototype_candidates or [],
        "trace_url": trace_url or (f"/lab/trace/{run_id}" if run_id else ""),
    }
    payload.update(extra or {})
    return payload

def lab_error(error_code: str, message: str, *, status: str = "error") -> dict[str, str]:
    return {"status": status, "error_code": error_code, "message": message}

def trace_payload(
    *,
    fixture_case_id: str,
    route: str,
    feature_label: str,
    agent_stages: list[str] | None = None,
    stage_status: list[str] | str | None = None,
    stage_latency_ms: list[int] | None = None,
    stage_reason_codes: list[str] | None = None,
    provider_type: str = "deterministic_mock",
    retrieved_document_ids: list[str] | None = None,
    retrieval_scores: list[float] | None = None,
    retrieval_source: str = "none",
    corpus_version: str = "",
    weak_context: bool = False,
    registry_source: str = "none",
    prototype_candidate_ids: list[str] | None = None,
    missing_data: list[str] | None = None,
    validation_issue_codes: list[str] | None = None,
    audit_event_ids: list[str] | None = None,
    clinical_status: str = PROTOTYPE_STATUS,
    latency_ms: int = 0,
) -> dict[str, Any]:
    return {
        "mode": LAB_MODE,
        "fixture_case_id": fixture_case_id,
        "route": route,
        "feature_label": feature_label,
        "agent_stages": agent_stages or [],
        "stage_status": stage_status or [],
        "stage_latency_ms": stage_latency_ms or [],
        "stage_reason_codes": stage_reason_codes or [],
        "latency_ms": int(latency_ms),
        "provider_type": provider_type,
        "retrieved_document_ids": retrieved_document_ids or [],
        "retrieval_scores": retrieval_scores or [],
        "retrieval_source": retrieval_source,
        "corpus_version": corpus_version,
        "weak_context": bool(weak_context),
        "registry_source": registry_source,
        "registry_authoritative": False,
        "clinical_use_allowed": False,
        "clinical_status": clinical_status,
        "accepted_recommendations": False,
        "nurse_review_required": True,
        "prototype_candidate_ids": prototype_candidate_ids or [],
        "missing_data": missing_data or [],
        "validation_issue_codes": validation_issue_codes or [],
        "audit_event_ids": audit_event_ids or [],
        "sanitization_status": TRACE_SANITIZATION_STATUS,
    }
