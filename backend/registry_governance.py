from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from clinical_registry import normalize_registry_framework, valid_code_format

LIFECYCLE_STATES = {
    "draft",
    "ocr_extracted",
    "llm_assisted",
    "extraction_unverified",
    "under_clinical_review",
    "approved",
    "deprecated",
    "quarantined",
}

NON_AUTHORITATIVE_STATES = LIFECYCLE_STATES - {"approved"}

COMPONENT_BY_FRAMEWORK = {
    "SDKI": "diagnosis",
    "SLKI": "outcome",
    "SIKI": "intervention",
    "NANDA": "diagnosis",
    "NOC": "outcome",
    "NIC": "intervention",
}

APPROVED_LICENSE_STATUSES = {
    "approved",
    "cleared",
    "licensed",
    "license_reviewed",
}

MANDATORY_PROVENANCE_FIELDS = (
    "source_title",
    "source_version",
    "source_page",
    "source_section",
    "source_identifier",
    "source_license_status",
    "extraction_method",
    "extraction_tool",
    "extraction_timestamp",
    "reviewer_role",
    "reviewer_identifier",
    "review_date",
    "approval_status",
    "approval_record_id",
    "content_hash",
    "registry_version",
    "release_id",
    "lifecycle_state",
)

MAX_REGISTRY_FILE_BYTES = 512 * 1024
MAX_IMPORT_ENTRY_COUNT = 500
MAX_JSON_DEPTH = 16
MAX_STRING_LENGTH = 4096
MAX_QUARANTINE_REASON_CODES = 64


class RegistryImportError(ValueError):
    """Safe metadata-only import error. Never include registry body text."""


class QuarantineReason:
    MALFORMED_CODE = "MALFORMED_CODE"
    DUPLICATE_CODE = "DUPLICATE_CODE"
    MISSING_NAME = "MISSING_NAME"
    MISSING_FRAMEWORK = "MISSING_FRAMEWORK"
    WRONG_COMPONENT_TYPE = "WRONG_COMPONENT_TYPE"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    LICENSE_STATUS_UNKNOWN = "LICENSE_STATUS_UNKNOWN"
    OCR_REVIEW_REQUIRED = "OCR_REVIEW_REQUIRED"
    LLM_ASSISTED_REVIEW_REQUIRED = "LLM_ASSISTED_REVIEW_REQUIRED"
    EXTRACTION_UNVERIFIED = "EXTRACTION_UNVERIFIED"
    CODE_NAME_CONFLICT = "CODE_NAME_CONFLICT"
    CONTENT_HASH_MISMATCH = "CONTENT_HASH_MISMATCH"
    DEPRECATED_ENTRY = "DEPRECATED_ENTRY"
    MANUAL_QUARANTINE = "MANUAL_QUARANTINE"
    UNDER_CLINICAL_REVIEW = "UNDER_CLINICAL_REVIEW"
    NOT_APPROVED_LIFECYCLE = "NOT_APPROVED_LIFECYCLE"
    APPROVAL_STATUS_NOT_APPROVED = "APPROVAL_STATUS_NOT_APPROVED"
    FIELD_TOO_LONG = "FIELD_TOO_LONG"


@dataclass(frozen=True)
class QuarantineIssue:
    reason_code: str
    severity: str
    message: str
    framework: str | None = None
    code: str | None = None


@dataclass(frozen=True)
class GovernedRegistryEntry:
    framework: str
    component_type: str
    code: str
    name: str
    source_title: str | None = None
    source_version: str | None = None
    source_page: str | None = None
    source_section: str | None = None
    source_identifier: str | None = None
    source_license_status: str | None = None
    extraction_method: str | None = None
    extraction_tool: str | None = None
    extraction_timestamp: str | None = None
    reviewer_role: str | None = None
    reviewer_identifier: str | None = None
    review_date: str | None = None
    approval_status: str = "draft"
    approval_record_id: str | None = None
    content_hash: str | None = None
    registry_version: str | None = None
    release_id: str | None = None
    lifecycle_state: str = "draft"
    manual_quarantine: bool = False
    expected_name: str | None = None
    source_path: str | None = None
    quarantine_reasons: tuple[str, ...] = field(default_factory=tuple)
    issues: tuple[QuarantineIssue, ...] = field(default_factory=tuple)

    @property
    def key(self) -> tuple[str, str]:
        return normalize_registry_framework(self.framework), self.code.strip()

    @property
    def release_eligible(self) -> bool:
        return (
            self.lifecycle_state == "approved"
            and self.approval_status == "approved"
            and not self.quarantine_reasons
        )

    @property
    def authoritative(self) -> bool:
        # Phase 3 import never makes an entry authoritative. Authority requires an
        # explicit active release handled by registry_release.py.
        return False

    @classmethod
    def from_mapping(cls, raw: dict[str, Any], source_path: str | None = None) -> "GovernedRegistryEntry":
        framework = normalize_registry_framework(_text(raw.get("framework")))
        component_type = _normalize_component_type(raw.get("component_type") or raw.get("tipe"))
        lifecycle_state = _normalize_lifecycle_state(raw.get("lifecycle_state") or raw.get("state") or raw.get("status"))
        approval_status = _text(raw.get("approval_status") or raw.get("approval") or raw.get("status") or lifecycle_state).lower() or "draft"
        return cls(
            framework=framework,
            component_type=component_type,
            code=_text(raw.get("code") or raw.get("kode")),
            name=_text(raw.get("name") or raw.get("nama")),
            source_title=_optional(raw.get("source_title")),
            source_version=_optional(raw.get("source_version") or raw.get("version")),
            source_page=_optional(raw.get("source_page")),
            source_section=_optional(raw.get("source_section")),
            source_identifier=_optional(raw.get("source_identifier")),
            source_license_status=_optional(raw.get("source_license_status")),
            extraction_method=_optional(raw.get("extraction_method")),
            extraction_tool=_optional(raw.get("extraction_tool")),
            extraction_timestamp=_optional(raw.get("extraction_timestamp")),
            reviewer_role=_optional(raw.get("reviewer_role")),
            reviewer_identifier=_optional(raw.get("reviewer_identifier") or raw.get("reviewer")),
            review_date=_optional(raw.get("review_date")),
            approval_status=approval_status,
            approval_record_id=_optional(raw.get("approval_record_id")),
            content_hash=_optional(raw.get("content_hash")),
            registry_version=_optional(raw.get("registry_version")),
            release_id=_optional(raw.get("release_id")),
            lifecycle_state=lifecycle_state,
            manual_quarantine=bool(raw.get("manual_quarantine")),
            expected_name=_optional(raw.get("expected_name")),
            source_path=source_path,
        )

    def with_validation(self, issues: Iterable[QuarantineIssue]) -> "GovernedRegistryEntry":
        issue_tuple = tuple(issues)
        reasons = tuple(sorted({issue.reason_code for issue in issue_tuple}))
        return GovernedRegistryEntry(
            framework=self.framework,
            component_type=self.component_type,
            code=self.code,
            name=self.name,
            source_title=self.source_title,
            source_version=self.source_version,
            source_page=self.source_page,
            source_section=self.source_section,
            source_identifier=self.source_identifier,
            source_license_status=self.source_license_status,
            extraction_method=self.extraction_method,
            extraction_tool=self.extraction_tool,
            extraction_timestamp=self.extraction_timestamp,
            reviewer_role=self.reviewer_role,
            reviewer_identifier=self.reviewer_identifier,
            review_date=self.review_date,
            approval_status=self.approval_status,
            approval_record_id=self.approval_record_id,
            content_hash=self.content_hash,
            registry_version=self.registry_version,
            release_id=self.release_id,
            lifecycle_state=self.lifecycle_state,
            manual_quarantine=self.manual_quarantine,
            expected_name=self.expected_name,
            source_path=self.source_path,
            quarantine_reasons=reasons,
            issues=issue_tuple,
        )


@dataclass(frozen=True)
class RegistryImportReport:
    source_path: str
    dataset_name: str
    source_framework: str | None
    entries: tuple[GovernedRegistryEntry, ...]
    dry_run: bool = True

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def quarantined_count(self) -> int:
        return sum(1 for entry in self.entries if entry.quarantine_reasons)

    @property
    def release_eligible_count(self) -> int:
        return sum(1 for entry in self.entries if entry.release_eligible)

    @property
    def authoritative_count(self) -> int:
        return 0

    @property
    def reason_counts(self) -> Counter[str]:
        counts: Counter[str] = Counter()
        for entry in self.entries:
            counts.update(entry.quarantine_reasons)
        return counts

    def to_safe_dict(self) -> dict[str, Any]:
        reason_counts = dict(sorted(self.reason_counts.items()))
        if len(reason_counts) > MAX_QUARANTINE_REASON_CODES:
            raise RegistryImportError("Quarantine report exceeded maximum reason-code count.")
        return {
            "dataset_name": self.dataset_name,
            "source_path": self.source_path,
            "source_framework": self.source_framework,
            "dry_run": self.dry_run,
            "entry_count": self.entry_count,
            "quarantined_count": self.quarantined_count,
            "release_eligible_count": self.release_eligible_count,
            "authoritative_count": self.authoritative_count,
            "quarantine_reason_counts": reason_counts,
        }


def compute_entry_content_hash(entry: GovernedRegistryEntry | dict[str, Any]) -> str:
    if isinstance(entry, dict):
        entry = GovernedRegistryEntry.from_mapping(entry)
    material = {
        "framework": normalize_registry_framework(entry.framework),
        "component_type": entry.component_type,
        "code": entry.code.strip(),
        "name": entry.name.strip(),
        "source_identifier": entry.source_identifier or "",
        "source_page": entry.source_page or "",
        "source_section": entry.source_section or "",
        "source_title": entry.source_title or "",
        "source_version": entry.source_version or "",
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_registry_entries(
    raw_entries: Iterable[dict[str, Any]],
    source_path: str | None = None,
    source_framework: str | None = None,
) -> tuple[GovernedRegistryEntry, ...]:
    entries = [GovernedRegistryEntry.from_mapping(raw, source_path=source_path) for raw in raw_entries]
    key_counts: Counter[tuple[str, str]] = Counter(entry.key for entry in entries)
    name_sets: dict[tuple[str, str], set[str]] = {}
    for entry in entries:
        name_sets.setdefault(entry.key, set()).add(entry.name.casefold().strip())
    validated: list[GovernedRegistryEntry] = []
    expected_source_framework = normalize_registry_framework(source_framework or "")
    for entry in entries:
        issues = _entry_issues(entry, key_counts, name_sets, expected_source_framework)
        validated.append(entry.with_validation(issues))
    return tuple(validated)


def dry_run_import(
    source_path: str | Path,
    dataset_name: str | None = None,
    source_framework: str | None = None,
    import_root: str | Path | None = None,
) -> RegistryImportReport:
    path = resolve_import_source(source_path, import_root=import_root, source_framework=source_framework)
    payload = _load_json(path)
    raw_entries = _extract_raw_entries(payload)
    report_name = dataset_name or path.name
    framework = normalize_registry_framework(source_framework or _framework_from_name(path.name)) or None
    entries = validate_registry_entries(raw_entries, source_path=str(path), source_framework=framework)
    return RegistryImportReport(
        source_path=str(path),
        dataset_name=report_name,
        source_framework=framework,
        entries=entries,
        dry_run=True,
    )


def dry_run_import_batch(
    source_paths: Iterable[str | Path],
    dataset_name: str = "registry-import-batch",
    source_framework: str | None = None,
    import_root: str | Path | None = None,
) -> RegistryImportReport:
    raw_entries: list[dict[str, Any]] = []
    resolved_paths: list[str] = []
    framework = normalize_registry_framework(source_framework or "") or None
    for source_path in source_paths:
        path = resolve_import_source(source_path, import_root=import_root, source_framework=source_framework)
        payload = _load_json(path)
        raw_entries.extend(_extract_raw_entries(payload))
        resolved_paths.append(str(path))
    entries = validate_registry_entries(raw_entries, source_path=";".join(resolved_paths), source_framework=framework)
    return RegistryImportReport(
        source_path=";".join(resolved_paths),
        dataset_name=dataset_name,
        source_framework=framework,
        entries=entries,
        dry_run=True,
    )


def resolve_import_source(
    source_path: str | Path,
    import_root: str | Path | None = None,
    source_framework: str | None = None,
) -> Path:
    root = Path(import_root) if import_root is not None else Path.cwd()
    root = root.resolve()
    requested = Path(source_path)
    resolved = requested.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RegistryImportError("Import source is outside the approved import root.") from exc

    if resolved.is_dir():
        framework = normalize_registry_framework(source_framework or "")
        if not framework:
            raise RegistryImportError("Directory import requires an explicit source framework.")
        primary = (resolved / f"{framework}.json").resolve()
        try:
            primary.relative_to(root)
        except ValueError as exc:
            raise RegistryImportError("Resolved directory import target is outside the approved import root.") from exc
        if not primary.exists():
            raise RegistryImportError("Primary registry JSON file is missing from import directory.")
        return _validate_source_file(primary)

    return _validate_source_file(resolved)


def manifest_only(report: RegistryImportReport) -> dict[str, Any]:
    manifest = report.to_safe_dict()
    manifest["entry_hashes"] = [entry.content_hash for entry in report.entries if entry.content_hash]
    return manifest


def _entry_issues(
    entry: GovernedRegistryEntry,
    key_counts: Counter[tuple[str, str]],
    name_sets: dict[tuple[str, str], set[str]],
    source_framework: str | None = None,
) -> list[QuarantineIssue]:
    issues: list[QuarantineIssue] = []
    framework = normalize_registry_framework(entry.framework)
    format_framework = framework or normalize_registry_framework(source_framework or "")
    expected_component = COMPONENT_BY_FRAMEWORK.get(framework or format_framework)

    if not framework:
        issues.append(_issue(QuarantineReason.MISSING_FRAMEWORK, "critical", "Registry entry is missing framework.", entry))
    if not entry.code or (format_framework and not valid_code_format(format_framework, entry.code)):
        issues.append(_issue(QuarantineReason.MALFORMED_CODE, "critical", "Registry code is malformed for its framework.", entry))
    if not entry.name:
        issues.append(_issue(QuarantineReason.MISSING_NAME, "critical", "Registry entry is missing name.", entry))
    if _has_oversized_string(entry):
        issues.append(_issue(QuarantineReason.FIELD_TOO_LONG, "high", "Registry entry contains an oversized field.", entry))
    if not entry.component_type or (expected_component and entry.component_type != expected_component):
        issues.append(_issue(QuarantineReason.WRONG_COMPONENT_TYPE, "critical", "Registry component type does not match framework family.", entry))
    if key_counts[entry.key] > 1:
        issues.append(_issue(QuarantineReason.DUPLICATE_CODE, "critical", "Registry code is duplicated in the import batch.", entry))
    if key_counts[entry.key] > 1 and len(name_sets.get(entry.key, set())) > 1:
        issues.append(_issue(QuarantineReason.CODE_NAME_CONFLICT, "critical", "Duplicated registry code has conflicting names.", entry))
    if entry.expected_name and entry.name.casefold().strip() != entry.expected_name.casefold().strip():
        issues.append(_issue(QuarantineReason.CODE_NAME_CONFLICT, "critical", "Registry code/name pair conflicts with expected name metadata.", entry))

    missing_provenance = [field_name for field_name in MANDATORY_PROVENANCE_FIELDS if not getattr(entry, field_name)]
    if missing_provenance:
        issues.append(_issue(QuarantineReason.MISSING_PROVENANCE, "critical", "Mandatory provenance is incomplete.", entry))
    if (entry.source_license_status or "").strip().lower() not in APPROVED_LICENSE_STATUSES:
        issues.append(_issue(QuarantineReason.LICENSE_STATUS_UNKNOWN, "critical", "Source license status is unknown or not approved.", entry))

    extraction_method = (entry.extraction_method or "").casefold()
    if entry.lifecycle_state == "ocr_extracted" or "ocr" in extraction_method:
        issues.append(_issue(QuarantineReason.OCR_REVIEW_REQUIRED, "high", "OCR-derived registry content requires review before release.", entry))
    if entry.lifecycle_state == "llm_assisted" or "llm" in extraction_method:
        issues.append(_issue(QuarantineReason.LLM_ASSISTED_REVIEW_REQUIRED, "high", "LLM-assisted registry content requires review before release.", entry))
    if entry.lifecycle_state == "extraction_unverified":
        issues.append(_issue(QuarantineReason.EXTRACTION_UNVERIFIED, "high", "Extraction quality is not verified.", entry))
    if entry.lifecycle_state == "under_clinical_review":
        issues.append(_issue(QuarantineReason.UNDER_CLINICAL_REVIEW, "high", "Entry is still under clinical review.", entry))
    if entry.lifecycle_state == "deprecated":
        issues.append(_issue(QuarantineReason.DEPRECATED_ENTRY, "high", "Deprecated entry is not authoritative for new requests.", entry))
    if entry.lifecycle_state == "quarantined" or entry.manual_quarantine:
        issues.append(_issue(QuarantineReason.MANUAL_QUARANTINE, "critical", "Entry is manually quarantined.", entry))
    if entry.lifecycle_state != "approved":
        issues.append(_issue(QuarantineReason.NOT_APPROVED_LIFECYCLE, "high", "Entry lifecycle state is not approved.", entry))
    if entry.approval_status != "approved":
        issues.append(_issue(QuarantineReason.APPROVAL_STATUS_NOT_APPROVED, "high", "Entry approval status is not approved.", entry))
    if entry.content_hash and entry.content_hash.lower() != compute_entry_content_hash(entry).lower():
        issues.append(_issue(QuarantineReason.CONTENT_HASH_MISMATCH, "critical", "Registry content hash does not match canonical entry metadata.", entry))

    return _dedupe_issues(issues)


def _dedupe_issues(issues: list[QuarantineIssue]) -> list[QuarantineIssue]:
    seen: set[str] = set()
    result: list[QuarantineIssue] = []
    for issue in issues:
        if issue.reason_code in seen:
            continue
        seen.add(issue.reason_code)
        result.append(issue)
    return result


def _issue(reason_code: str, severity: str, message: str, entry: GovernedRegistryEntry) -> QuarantineIssue:
    return QuarantineIssue(reason_code, severity, message, framework=entry.framework or None, code=entry.code or None)


def _validate_source_file(path: Path) -> Path:
    if not path.exists():
        raise RegistryImportError("Registry import source file is missing.")
    if not path.is_file():
        raise RegistryImportError("Registry import source must be a file or approved directory.")
    if path.suffix.lower() != ".json":
        raise RegistryImportError("Unsupported registry import extension.")
    if path.stat().st_size > MAX_REGISTRY_FILE_BYTES:
        raise RegistryImportError("Registry import source exceeds maximum file size.")
    return path


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        try:
            payload = json.load(fh)
        except json.JSONDecodeError as exc:
            raise RegistryImportError("Registry import source is not valid JSON.") from exc
    if _json_depth(payload) > MAX_JSON_DEPTH:
        raise RegistryImportError("Registry import source exceeds maximum JSON nesting depth.")
    entries = _extract_raw_entries(payload)
    if len(entries) > MAX_IMPORT_ENTRY_COUNT:
        raise RegistryImportError("Registry import source exceeds maximum entry count.")
    return payload


def _extract_raw_entries(payload: Any) -> list[dict[str, Any]]:
    entries = payload.get("entries", payload) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _json_depth(value: Any, current: int = 0) -> int:
    if isinstance(value, dict):
        return max([current + 1, *(_json_depth(item, current + 1) for item in value.values())]) if value else current + 1
    if isinstance(value, list):
        return max([current + 1, *(_json_depth(item, current + 1) for item in value)]) if value else current + 1
    return current


def _has_oversized_string(entry: GovernedRegistryEntry) -> bool:
    values = (
        entry.framework,
        entry.component_type,
        entry.code,
        entry.name,
        entry.source_title,
        entry.source_version,
        entry.source_page,
        entry.source_section,
        entry.source_identifier,
        entry.source_license_status,
        entry.extraction_method,
        entry.extraction_tool,
        entry.extraction_timestamp,
        entry.reviewer_role,
        entry.reviewer_identifier,
        entry.review_date,
        entry.approval_status,
        entry.approval_record_id,
        entry.content_hash,
        entry.registry_version,
        entry.release_id,
        entry.lifecycle_state,
        entry.expected_name,
    )
    return any(len(str(value)) > MAX_STRING_LENGTH for value in values if value is not None)


def _normalize_component_type(value: Any) -> str:
    text = _text(value).lower()
    aliases = {
        "diagnosa": "diagnosis",
        "diagnosis": "diagnosis",
        "luaran": "outcome",
        "outcome": "outcome",
        "intervensi": "intervention",
        "intervention": "intervention",
    }
    return aliases.get(text, text)


def _normalize_lifecycle_state(value: Any) -> str:
    text = _text(value).lower()
    return text if text in LIFECYCLE_STATES else "draft"


def _framework_from_name(name: str) -> str:
    upper = name.upper()
    for framework in COMPONENT_BY_FRAMEWORK:
        if framework in upper:
            return framework
    return ""


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _optional(value: Any) -> str | None:
    text = _text(value)
    return text or None
