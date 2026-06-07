from __future__ import annotations

import json
import re
import secrets
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from typing import Any, Callable


SAFE_TRACE_FIELDS = {
    "run_id",
    "mode",
    "fixture_case_id",
    "route",
    "feature_label",
    "agent_stages",
    "stage_status",
    "stage_latency_ms",
    "stage_reason_codes",
    "latency_ms",
    "provider_type",
    "retrieved_document_ids",
    "retrieval_scores",
    "retrieval_source",
    "corpus_version",
    "weak_context",
    "registry_source",
    "registry_authoritative",
    "clinical_use_allowed",
    "clinical_status",
    "accepted_recommendations",
    "nurse_review_required",
    "prototype_candidate_ids",
    "missing_data",
    "validation_issue_codes",
    "audit_event_ids",
    "sanitization_status",
}

FORBIDDEN_TRACE_FIELDS = {
    "raw_prompt",
    "raw prompt",
    "prompt",
    "raw_model_output",
    "raw model output",
    "model_output",
    "raw_output",
    "raw output",
    "uploaded_text",
    "uploaded text",
    "patient_narrative",
    "api_key",
    "session_token",
    "otp",
    "director_seed",
    "bootstrap_secret",
    "provider_key",
    "filesystem_path",
    "stack_trace",
    "chain_of_thought",
    "chain-of-thought",
}

FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"chain[-_ ]of[-_ ]thought", re.I),
    re.compile(r"raw\s+(?:prompt|model output|output)", re.I),
    re.compile(r"uploaded\s+text", re.I),
    re.compile(r"api[_ -]?key", re.I),
    re.compile(r"session[_ -]?token", re.I),
    re.compile(r"director\s+seed", re.I),
    re.compile(r"bootstrap\s+secret", re.I),
    re.compile(r"provider\s+key", re.I),
    re.compile(r"secret[-_ ]canary", re.I),
    re.compile(r"phi[-_ ]canary", re.I),
    re.compile(r"\b(?:nik|mrn|rekam\s+medis)\b", re.I),
    re.compile(r"[A-Za-z]:\\"),
    re.compile(r"/(?:etc|users|home|var|tmp)/", re.I),
)


class LabTraceValidationError(ValueError):
    pass


class LabTraceStore:
    def __init__(
        self,
        *,
        ttl_sec: int = 600,
        max_runs: int = 128,
        max_stages: int = 16,
        max_document_ids: int = 32,
        max_metadata_bytes: int = 8192,
        now_func: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_sec = max(1, int(ttl_sec))
        self.max_runs = max(1, int(max_runs))
        self.max_stages = max(0, int(max_stages))
        self.max_document_ids = max(0, int(max_document_ids))
        self.max_metadata_bytes = max(128, int(max_metadata_bytes))
        self._now = now_func
        self._lock = threading.Lock()
        self._records: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def count(self) -> int:
        with self._lock:
            self._cleanup_locked()
            return len(self._records)

    def create(self, payload: dict[str, Any], *, owner_id: str = "", lab_session_id: str = "") -> dict[str, Any]:
        record = self._validate(payload)
        record["run_id"] = secrets.token_urlsafe(24)
        expires_at = self._now() + self.ttl_sec
        with self._lock:
            self._cleanup_locked()
            while len(self._records) >= self.max_runs:
                self._records.popitem(last=False)
            self._records[record["run_id"]] = {
                "expires_at": expires_at,
                "owner_id": owner_id or "",
                "lab_session_id": lab_session_id or "",
                "payload": deepcopy(record),
            }
        return deepcopy(record)

    def get(self, run_id: str, *, owner_id: str = "", lab_session_id: str = "") -> dict[str, Any] | None:
        with self._lock:
            self._cleanup_locked()
            rec = self._records.get(run_id or "")
            if not rec:
                return None
            if rec.get("owner_id", "") != (owner_id or "") or rec.get("lab_session_id", "") != (lab_session_id or ""):
                return None
            return deepcopy(rec["payload"])

    def _cleanup_locked(self) -> None:
        now = self._now()
        for run_id, rec in list(self._records.items()):
            if now >= rec.get("expires_at", 0):
                self._records.pop(run_id, None)

    def _validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise LabTraceValidationError("Trace payload must be an object.")
        unknown = set(payload) - SAFE_TRACE_FIELDS
        forbidden = {key for key in payload if _normal_key(key) in {_normal_key(item) for item in FORBIDDEN_TRACE_FIELDS}}
        if unknown or forbidden:
            raise LabTraceValidationError("Trace payload contains unsupported fields.")
        record = deepcopy(payload)
        record.pop("run_id", None)
        self._validate_bounds(record)
        self._validate_values(record)
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        if len(encoded) > self.max_metadata_bytes:
            raise LabTraceValidationError("Trace payload exceeds metadata bounds.")
        return record

    def _validate_bounds(self, record: dict[str, Any]) -> None:
        stages = record.get("agent_stages", [])
        if stages is not None and (not isinstance(stages, list) or len(stages) > self.max_stages):
            raise LabTraceValidationError("Trace stage list exceeds bounds.")
        stage_status = record.get("stage_status", [])
        if stage_status is not None and not isinstance(stage_status, str) and (not isinstance(stage_status, list) or len(stage_status) > self.max_stages):
            raise LabTraceValidationError("Trace stage status list exceeds bounds.")
        stage_latency = record.get("stage_latency_ms", [])
        if stage_latency is not None and (not isinstance(stage_latency, list) or len(stage_latency) > self.max_stages):
            raise LabTraceValidationError("Trace stage latency list exceeds bounds.")
        stage_reason_codes = record.get("stage_reason_codes", [])
        if stage_reason_codes is not None and (not isinstance(stage_reason_codes, list) or len(stage_reason_codes) > self.max_stages):
            raise LabTraceValidationError("Trace stage reason list exceeds bounds.")
        doc_ids = record.get("retrieved_document_ids", [])
        if doc_ids is not None and (not isinstance(doc_ids, list) or len(doc_ids) > self.max_document_ids):
            raise LabTraceValidationError("Trace document list exceeds bounds.")
        candidate_ids = record.get("prototype_candidate_ids", [])
        if candidate_ids is not None and (not isinstance(candidate_ids, list) or len(candidate_ids) > self.max_document_ids):
            raise LabTraceValidationError("Trace candidate list exceeds bounds.")

    def _validate_values(self, value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if _normal_key(str(key)) not in {_normal_key(field) for field in SAFE_TRACE_FIELDS}:
                    raise LabTraceValidationError("Trace nested metadata is not allowed.")
                self._validate_values(item)
            return
        if isinstance(value, list):
            for item in value:
                self._validate_values(item)
            return
        if isinstance(value, str):
            for pattern in FORBIDDEN_VALUE_PATTERNS:
                if pattern.search(value):
                    raise LabTraceValidationError("Trace payload contains forbidden content.")


def _normal_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())
