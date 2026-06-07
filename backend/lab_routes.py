from __future__ import annotations

import secrets
import threading
import time
from typing import Callable, Optional

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from lab_config import lab_disabled_payload, lab_status_payload, synthetic_lab_enabled
from lab_trace_store import LabTraceStore
from security_controls import AuthPrincipal, constant_time_equal, issue_secret_token, token_digest


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


def create_lab_router(
    get_config: Callable[[], object],
    auth_context: Callable[[Request, Optional[str], str], tuple[AuthPrincipal | None, str, JSONResponse | None]],
    security_response: Callable[[str], JSONResponse],
    security_pepper: str,
) -> APIRouter:
    router = APIRouter(prefix="/lab", tags=["synthetic-lab"])

    def guard() -> JSONResponse | None:
        if synthetic_lab_enabled(get_config()):
            return None
        return JSONResponse(lab_disabled_payload(), status_code=503)

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
        trace = LAB_TRACE_STORE.get(run_id)
        if trace is None:
            return JSONResponse(
                {"status": "error", "error_code": "lab_trace_not_found", "message": "Synthetic lab trace not found."},
                status_code=404,
            )
        return {"status": "sukses", "trace": trace}

    return router
