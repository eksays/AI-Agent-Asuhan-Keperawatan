from __future__ import annotations

from pathlib import Path
from typing import Any

LAB_NAMESPACE = "/lab"
LAB_FEATURE_ACTIVATION_STATUS = "foundation_only"
LAB_DISABLED_ERROR_CODE = "synthetic_lab_disabled"
LAB_DISABLED_MESSAGE = "Synthetic integration lab is unavailable."
APPROVED_SYNTHETIC_FIXTURE_PARENT = Path(__file__).resolve().parent / "tests" / "fixtures"


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


def lab_disabled_payload() -> dict[str, str]:
    return {
        "status": "error",
        "error_code": LAB_DISABLED_ERROR_CODE,
        "message": LAB_DISABLED_MESSAGE,
    }


def lab_status_payload(cfg: Any) -> dict[str, object]:
    enabled = synthetic_lab_enabled(cfg)
    return {
        "mode": getattr(cfg, "app_mode", "clinical_sandbox"),
        "synthetic_lab_enabled": enabled,
        "synthetic_data_only": bool(getattr(cfg, "synthetic_data_only", False)),
        "feature_activation_status": LAB_FEATURE_ACTIVATION_STATUS if enabled else "disabled",
        "external_provider_enabled": False,
        "authoritative_registry_enabled": False,
        "clinical_use_allowed": False,
    }
