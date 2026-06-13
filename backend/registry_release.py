from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Iterable

from registry_governance import APPROVED_LICENSE_STATUSES, GovernedRegistryEntry, QuarantineReason

RELEASE_STATUSES = {
    "candidate",
    "approved_for_activation",
    "active",
    "deprecated",
    "rolled_back",
}

FRAMEWORK_RELEASE_COMPONENTS = {
    "3S": ("SDKI:diagnosis", "SLKI:outcome", "SIKI:intervention"),
    "3N": ("NANDA:diagnosis", "NOC:outcome", "NIC:intervention"),
}


@dataclass(frozen=True)
class ReleaseValidationIssue:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class ReleaseValidationResult:
    accepted: bool
    issues: tuple[ReleaseValidationIssue, ...]


@dataclass(frozen=True)
class RegistryReleaseManifest:
    release_id: str
    registry_version: str
    framework: str
    component_type: str
    created_at: str
    created_by_role: str
    approval_record_ids: tuple[str, ...]
    source_manifest_hash: str
    entry_hashes: tuple[str, ...]
    entry_count: int
    release_status: str
    previous_release_id: str | None = None

    def with_status(self, status: str, previous_release_id: str | None = None) -> "RegistryReleaseManifest":
        return replace(
            self,
            release_status=status,
            previous_release_id=previous_release_id if previous_release_id is not None else self.previous_release_id,
        )


def make_release_manifest(
    release_id: str,
    registry_version: str,
    framework: str,
    component_type: str,
    entries: Iterable[GovernedRegistryEntry],
    release_status: str = "candidate",
    created_at: str = "2026-06-06T00:00:00Z",
    created_by_role: str = "registry_governance_test",
    previous_release_id: str | None = None,
) -> RegistryReleaseManifest:
    entry_tuple = tuple(entries)
    entry_hashes = tuple(entry.content_hash or "" for entry in entry_tuple)
    approval_record_ids = tuple(sorted({entry.approval_record_id or "" for entry in entry_tuple if entry.approval_record_id}))
    return RegistryReleaseManifest(
        release_id=release_id,
        registry_version=registry_version,
        framework=framework,
        component_type=component_type,
        created_at=created_at,
        created_by_role=created_by_role,
        approval_record_ids=approval_record_ids,
        source_manifest_hash=_source_manifest_hash(entry_hashes),
        entry_hashes=entry_hashes,
        entry_count=len(entry_tuple),
        release_status=release_status,
        previous_release_id=previous_release_id,
    )


def validate_release_candidate(
    manifest: RegistryReleaseManifest,
    entries: Iterable[GovernedRegistryEntry],
) -> ReleaseValidationResult:
    entry_tuple = tuple(entries)
    issues: list[ReleaseValidationIssue] = []

    if manifest.release_status not in RELEASE_STATUSES:
        issues.append(_issue("INVALID_RELEASE_STATUS", "critical", "Release status is not recognized."))
    if manifest.release_status in {"active", "rolled_back", "deprecated"}:
        issues.append(_issue("RELEASE_NOT_CANDIDATE", "critical", "Only candidate or approved-for-activation releases can be validated for activation."))
    if not manifest.release_id or not manifest.registry_version:
        issues.append(_issue("MISSING_RELEASE_METADATA", "critical", "Release id and registry version are mandatory."))
    if not manifest.created_by_role:
        issues.append(_issue("MISSING_CREATED_BY_ROLE", "high", "Release creator role is mandatory."))
    if not manifest.approval_record_ids:
        issues.append(_issue("MISSING_APPROVAL_RECORD", "critical", "Release is missing approval record ids."))
    if manifest.entry_count != len(entry_tuple):
        issues.append(_issue("ENTRY_COUNT_MISMATCH", "critical", "Release entry count does not match supplied entries."))
    supplied_hashes = tuple(entry.content_hash or "" for entry in entry_tuple)
    if tuple(manifest.entry_hashes) != supplied_hashes:
        issues.append(_issue("ENTRY_HASH_MISMATCH", "critical", "Release entry hashes do not match supplied entries."))
    if manifest.source_manifest_hash != _source_manifest_hash(manifest.entry_hashes):
        issues.append(_issue("SOURCE_MANIFEST_HASH_MISMATCH", "critical", "Release source manifest hash is invalid."))

    for entry in entry_tuple:
        if entry.quarantine_reasons:
            issues.append(_issue("QUARANTINED_ENTRY", "critical", "Release contains quarantined entry."))
            break
    for entry in entry_tuple:
        if not entry.release_eligible:
            issues.append(_issue("ENTRY_NOT_RELEASE_ELIGIBLE", "critical", "Release contains an entry that is not release eligible."))
            break
    for entry in entry_tuple:
        if not entry.approval_record_id or entry.approval_record_id not in manifest.approval_record_ids:
            issues.append(_issue("MISSING_ENTRY_APPROVAL_RECORD", "critical", "Entry approval record is missing from release manifest."))
            break
    for entry in entry_tuple:
        if (entry.source_license_status or "").strip().lower() not in APPROVED_LICENSE_STATUSES:
            issues.append(_issue(QuarantineReason.LICENSE_STATUS_UNKNOWN, "critical", "Entry source license status is unknown or not approved."))
            break

    deduped = _dedupe_issues(issues)
    return ReleaseValidationResult(accepted=not deduped, issues=tuple(deduped))


class RegistryReleaseStore:
    def __init__(self) -> None:
        self._active: dict[tuple[str, str], RegistryReleaseManifest] = {}
        self._history: dict[str, RegistryReleaseManifest] = {}

    def activate_release(
        self,
        manifest: RegistryReleaseManifest,
        entries: Iterable[GovernedRegistryEntry],
    ) -> RegistryReleaseManifest:
        if manifest.release_status != "approved_for_activation":
            raise ValueError("Activation requires an approved_for_activation release artifact.")
        if manifest.release_status in {"deprecated", "rolled_back"}:
            raise ValueError("Deprecated or rolled-back releases cannot be reactivated.")
        validation = validate_release_candidate(manifest, entries)
        if not validation.accepted:
            codes = ", ".join(issue.code for issue in validation.issues)
            raise ValueError("Release activation rejected: " + codes)
        key = (manifest.framework, manifest.component_type)
        previous = self._active.get(key)
        active = manifest.with_status("active", previous.release_id if previous else manifest.previous_release_id)
        self._active[key] = active
        self._history[active.release_id] = active
        if previous:
            self._history[previous.release_id] = previous
        return active

    def active_release(self, framework: str, component_type: str) -> RegistryReleaseManifest | None:
        return self._active.get((framework, component_type))

    def rollback(self, framework: str, component_type: str) -> RegistryReleaseManifest:
        key = (framework, component_type)
        current = self._active.get(key)
        if current is None or not current.previous_release_id:
            raise ValueError("No previous active release is available for rollback.")
        previous = self._history.get(current.previous_release_id)
        if previous is None:
            raise ValueError("Previous release pointer cannot be resolved.")
        self._history[current.release_id] = current.with_status("rolled_back")
        restored = previous.with_status("active", previous.previous_release_id)
        self._active[key] = restored
        self._history[restored.release_id] = restored
        return restored

    def activate_framework_release_set(
        self,
        standard: str,
        manifests: Iterable[RegistryReleaseManifest],
        entries_by_release: dict[str, Iterable[GovernedRegistryEntry]],
    ) -> tuple[RegistryReleaseManifest, ...]:
        validation = validate_framework_release_set(standard, manifests, entries_by_release)
        if not validation.accepted:
            codes = ", ".join(issue.code for issue in validation.issues)
            raise ValueError("Framework release activation rejected: " + codes)
        activated: list[RegistryReleaseManifest] = []
        for manifest in manifests:
            activated.append(self.activate_release(manifest, entries_by_release.get(manifest.release_id, ())))
        return tuple(activated)


def validate_framework_release_set(
    standard: str,
    manifests: Iterable[RegistryReleaseManifest],
    entries_by_release: dict[str, Iterable[GovernedRegistryEntry]],
) -> ReleaseValidationResult:
    required = FRAMEWORK_RELEASE_COMPONENTS.get((standard or "").upper())
    manifest_tuple = tuple(manifests)
    issues: list[ReleaseValidationIssue] = []
    if not required:
        issues.append(_issue("UNSUPPORTED_FRAMEWORK", "critical", "Framework release set is unsupported."))
        return ReleaseValidationResult(False, tuple(issues))

    present = {f"{manifest.framework}:{manifest.component_type}" for manifest in manifest_tuple}
    missing = [component for component in required if component not in present]
    if missing:
        issues.append(_issue("INCOMPLETE_FRAMEWORK_RELEASE", "critical", "Framework release set is missing components: " + ", ".join(missing) + "."))

    release_ids = [manifest.release_id for manifest in manifest_tuple]
    if len(release_ids) != len(set(release_ids)):
        issues.append(_issue("DUPLICATE_RELEASE_ID", "critical", "Framework release set contains duplicate release ids."))

    all_entry_hashes: list[str] = []
    for manifest in manifest_tuple:
        entries = tuple(entries_by_release.get(manifest.release_id, ()))
        validation = validate_release_candidate(manifest, entries)
        issues.extend(validation.issues)
        all_entry_hashes.extend(hash_value for hash_value in manifest.entry_hashes if hash_value)

    if len(all_entry_hashes) != len(set(all_entry_hashes)):
        issues.append(_issue("DUPLICATE_RELEASE_ENTRY", "critical", "Framework release set contains duplicate entry hashes across component manifests."))

    deduped = _dedupe_issues(issues)
    return ReleaseValidationResult(accepted=not deduped, issues=tuple(deduped))


def _source_manifest_hash(entry_hashes: Iterable[str]) -> str:
    material = json.dumps(tuple(entry_hashes), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _issue(code: str, severity: str, message: str) -> ReleaseValidationIssue:
    return ReleaseValidationIssue(code, severity, message)


def _dedupe_issues(issues: list[ReleaseValidationIssue]) -> list[ReleaseValidationIssue]:
    seen: set[str] = set()
    result: list[ReleaseValidationIssue] = []
    for issue in issues:
        if issue.code in seen:
            continue
        seen.add(issue.code)
        result.append(issue)
    return result
