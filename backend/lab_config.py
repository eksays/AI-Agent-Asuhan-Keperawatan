from __future__ import annotations

from pathlib import Path
from typing import Any

LAB_NAMESPACE = "/lab"
LAB_FEATURE_ACTIVATION_STATUS = "foundation_only"
LAB_CORE_FEATURE_ACTIVATION_STATUS = "offline_core_features"
LAB_DISABLED_ERROR_CODE = "synthetic_lab_disabled"
LAB_DISABLED_MESSAGE = "Synthetic integration lab is unavailable."
APPROVED_SYNTHETIC_FIXTURE_PARENT = Path(__file__).resolve().parent / "tests" / "fixtures"

SPRINT_B_FLAG_FIELDS = (
    "synthetic_multi_agent",
    "synthetic_rag",
    "synthetic_registry",
    "synthetic_ebp",
    "synthetic_mermaid",
    "synthetic_uploads",
    "synthetic_ocr_mock",
    "synthetic_photo_mock",
    "synthetic_feedback_memory",
)

LAB_FEATURE_CAPABILITY_FIELDS = {
    "synthetic_multi_agent": "synthetic_multi_agent_enabled",
    "synthetic_rag": "synthetic_rag_enabled",
    "synthetic_registry": "synthetic_registry_enabled",
    "synthetic_ebp": "synthetic_ebp_enabled",
    "synthetic_mermaid": "synthetic_mermaid_enabled",
    "synthetic_uploads": "synthetic_uploads_enabled",
    "synthetic_ocr_mock": "synthetic_ocr_mock_enabled",
    "synthetic_photo_mock": "synthetic_photo_mock_enabled",
    "synthetic_feedback_memory": "synthetic_feedback_memory_enabled",
}


def ensure_approved_fixture_root(path: str | Path) -> str:
    root = Path(path).resolve(strict=False)
    approved_parent = APPROVED_SYNTHETIC_FIXTURE_PARENT.resolve(strict=False)
    forbidden_parts = {
        "audit_exports",
        "audit-exports",
        "audit_segments",
        "audit-segments",
        "data_terstruktur",
        "hospital_documents",
        "hospital-documents",
        "patient_records",
        "patient-records",
        "runtime",
        "runtime_ledgers",
        "runtime-ledgers",
        "runtime_logs",
        "runtime-logs",
        "upload",
        "uploads",
    }
    if {part.lower() for part in root.parts} & forbidden_parts:
        raise RuntimeError("Synthetic lab fixture root uses a forbidden location.")
    try:
        root.relative_to(approved_parent)
    except ValueError as exc:
        raise RuntimeError("Synthetic lab fixture root must remain under the approved synthetic fixture parent.") from exc
    return str(root)


def synthetic_lab_enabled(cfg: Any) -> bool:
    return bool(
        getattr(cfg, "app_mode", "") == "clinical_sandbox"
        and getattr(cfg, "synthetic_lab_mode", False) is True
        and getattr(cfg, "synthetic_data_only", False) is True
    )

def sprint_b_feature_enabled(cfg: Any, field: str) -> bool:
    return synthetic_lab_enabled(cfg) and bool(getattr(cfg, field, False))

def any_sprint_b_feature_enabled(cfg: Any) -> bool:
    return any(sprint_b_feature_enabled(cfg, field) for field in SPRINT_B_FLAG_FIELDS)

def lab_feature_activation_status(cfg: Any) -> str:
    if not synthetic_lab_enabled(cfg):
        return "disabled"
    return LAB_CORE_FEATURE_ACTIVATION_STATUS if any_sprint_b_feature_enabled(cfg) else LAB_FEATURE_ACTIVATION_STATUS

def lab_feature_capabilities(cfg: Any) -> dict[str, bool]:
    return {
        public_name: sprint_b_feature_enabled(cfg, field_name)
        for field_name, public_name in LAB_FEATURE_CAPABILITY_FIELDS.items()
    }


def lab_disabled_payload() -> dict[str, str]:
    return {
        "status": "error",
        "error_code": LAB_DISABLED_ERROR_CODE,
        "message": LAB_DISABLED_MESSAGE,
    }


def lab_status_payload(cfg: Any) -> dict[str, object]:
    enabled = synthetic_lab_enabled(cfg)
    payload: dict[str, object] = {
        "mode": getattr(cfg, "app_mode", "clinical_sandbox"),
        "synthetic_lab_enabled": enabled,
        "synthetic_data_only": bool(getattr(cfg, "synthetic_data_only", False)),
        "feature_activation_status": lab_feature_activation_status(cfg),
        "external_provider_enabled": False,
        "authoritative_registry_enabled": False,
        "clinical_use_allowed": False,
    }
    payload.update(lab_feature_capabilities(cfg))
    return payload
