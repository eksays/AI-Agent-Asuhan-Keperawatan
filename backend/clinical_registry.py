from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


REGISTRY_STATES = {
    "draft",
    "ocr_extracted",
    "llm_assisted",
    "extraction_unverified",
    "under_clinical_review",
    "approved",
    "deprecated",
    "quarantined",
}

CODE_PATTERNS = {
    "SDKI": re.compile(r"^D\.\d{4}$"),
    "SLKI": re.compile(r"^L\.\d{4,5}$"),
    "SIKI": re.compile(r"^I\.\d{4,5}$"),
    "NANDA": re.compile(r"^00\d{3}$"),
    "NOC": re.compile(r"^\d{4}$"),
    "NIC": re.compile(r"^\d{4}$"),
}

PROVENANCE_FIELDS = (
    "source_title",
    "source_version",
    "reviewer",
    "review_date",
    "content_hash",
)


@dataclass(frozen=True)
class RegistryIssue:
    code: str
    severity: str
    message: str
    framework: str | None = None


@dataclass(frozen=True)
class RegistryEntry:
    framework: str
    code: str
    name: str
    source_title: str | None = None
    source_version: str | None = None
    source_page: str | int | None = None
    source_section: str | None = None
    extraction_method: str | None = None
    reviewer: str | None = None
    review_date: str | None = None
    approval_status: str = "draft"
    content_hash: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str]:
        return self.framework.upper(), self.code.strip()

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "RegistryEntry":
        status = str(raw.get("approval_status") or raw.get("status") or "draft").strip().lower()
        return cls(
            framework=str(raw.get("framework") or "").strip().upper(),
            code=str(raw.get("code") or raw.get("kode") or "").strip(),
            name=str(raw.get("name") or raw.get("nama") or "").strip(),
            source_title=_optional_text(raw.get("source_title")),
            source_version=_optional_text(raw.get("source_version") or raw.get("version")),
            source_page=raw.get("source_page"),
            source_section=_optional_text(raw.get("source_section")),
            extraction_method=_optional_text(raw.get("extraction_method")),
            reviewer=_optional_text(raw.get("reviewer")),
            review_date=_optional_text(raw.get("review_date")),
            approval_status=status,
            content_hash=_optional_text(raw.get("content_hash")),
            raw=dict(raw),
        )


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def normalize_registry_framework(framework: str) -> str:
    f = (framework or "").strip().upper()
    aliases = {
        "NANDA-I": "NANDA",
        "NANDAI": "NANDA",
    }
    return aliases.get(f, f)


def valid_code_format(framework: str, code: str) -> bool:
    pattern = CODE_PATTERNS.get(normalize_registry_framework(framework))
    return bool(pattern and pattern.match((code or "").strip()))


class ClinicalRegistry:
    def __init__(
        self,
        approved: dict[tuple[str, str], RegistryEntry] | None = None,
        quarantined: list[RegistryEntry] | None = None,
        issues: list[RegistryIssue] | None = None,
        unavailable_reason: str | None = None,
    ) -> None:
        self._approved = approved or {}
        self.quarantined = quarantined or []
        self.issues = issues or []
        self.unavailable_reason = unavailable_reason

    @classmethod
    def unavailable(cls, reason: str = "No approved clinical registry release is configured.") -> "ClinicalRegistry":
        return cls(unavailable_reason=reason)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "ClinicalRegistry":
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        entries = raw.get("entries", raw) if isinstance(raw, dict) else raw
        if not isinstance(entries, list):
            return cls(unavailable_reason="Registry JSON did not contain a list of entries.")
        return cls.from_entries(entries)

    @classmethod
    def from_entries(cls, raw_entries: Iterable[dict[str, Any]]) -> "ClinicalRegistry":
        entries = [RegistryEntry.from_mapping(raw) for raw in raw_entries]
        issues: list[RegistryIssue] = []
        quarantined: list[RegistryEntry] = []
        approved: dict[tuple[str, str], RegistryEntry] = {}
        counts: dict[tuple[str, str], int] = {}
        names: dict[tuple[str, str], set[str]] = {}

        for entry in entries:
            counts[entry.key] = counts.get(entry.key, 0) + 1
            names.setdefault(entry.key, set()).add(entry.name.casefold())

        duplicate_keys = {key for key, count in counts.items() if count > 1}
        for entry in entries:
            entry_issues = _entry_issues(entry)
            if entry.key in duplicate_keys:
                entry_issues.append(RegistryIssue(
                    code="duplicate_code",
                    severity="critical",
                    framework=entry.framework,
                    message=f"Duplicate registry code is not authoritative: {entry.framework} {entry.code}.",
                ))
                if len(names.get(entry.key, set())) > 1:
                    entry_issues.append(RegistryIssue(
                        code="duplicate_code_name_mismatch",
                        severity="critical",
                        framework=entry.framework,
                        message="Duplicate registry code has conflicting names.",
                    ))
            if entry_issues or entry.approval_status != "approved":
                quarantined.append(entry)
                issues.extend(entry_issues)
                if entry.approval_status != "approved" and not entry_issues:
                    issues.append(RegistryIssue(
                        code="not_approved",
                        severity="high",
                        framework=entry.framework,
                        message=f"Entry {entry.framework} {entry.code} is not approved and is excluded.",
                    ))
                continue
            approved[entry.key] = entry
        return cls(approved=approved, quarantined=quarantined, issues=issues)

    def lookup(self, framework: str, code: str) -> RegistryEntry | None:
        return self._approved.get((normalize_registry_framework(framework), (code or "").strip()))

    def approved_available(self, framework: str) -> bool:
        f = normalize_registry_framework(framework)
        return any(key[0] == f for key in self._approved)

    def version_for(self, framework: str) -> str | None:
        f = normalize_registry_framework(framework)
        versions = sorted({entry.source_version for key, entry in self._approved.items() if key[0] == f and entry.source_version})
        return versions[0] if len(versions) == 1 else (", ".join(versions) if versions else None)

    @property
    def approved_count(self) -> int:
        return len(self._approved)

    @property
    def is_unavailable(self) -> bool:
        return bool(self.unavailable_reason) and not self._approved


def _entry_issues(entry: RegistryEntry) -> list[RegistryIssue]:
    issues: list[RegistryIssue] = []
    if not entry.framework:
        issues.append(RegistryIssue("missing_framework", "critical", "Registry entry is missing framework."))
    elif entry.framework not in CODE_PATTERNS:
        issues.append(RegistryIssue("unsupported_framework", "critical", f"Unsupported registry framework: {entry.framework}.", entry.framework))
    if not entry.code:
        issues.append(RegistryIssue("missing_code", "critical", "Registry entry is missing code.", entry.framework or None))
    elif entry.framework and not valid_code_format(entry.framework, entry.code):
        issues.append(RegistryIssue("malformed_code", "critical", f"Malformed code for {entry.framework}: {entry.code}.", entry.framework))
    if not entry.name:
        issues.append(RegistryIssue("missing_name", "critical", "Registry entry is missing name.", entry.framework or None))
    if entry.approval_status not in REGISTRY_STATES:
        issues.append(RegistryIssue("invalid_status", "high", f"Invalid registry approval status: {entry.approval_status}.", entry.framework or None))
    if entry.approval_status == "approved":
        missing = [field_name for field_name in PROVENANCE_FIELDS if not getattr(entry, field_name)]
        if missing:
            issues.append(RegistryIssue(
                "missing_provenance",
                "critical",
                "Approved registry entry is missing provenance: " + ", ".join(missing) + ".",
                entry.framework or None,
            ))
    return issues
