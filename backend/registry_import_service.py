"""Phase 8 P8-BE — Governed explicit-source import service.

Bridges registry_governance.py dry-run validation with the PostgreSQL store.
Implements: single explicit source import, dry-run default, apply mode with
quarantined-only storage, source hash recording, and safe metadata reporting.

Rules enforced:
- Single explicit regular file only (no glob, no recursive, no folder auto-import)
- Backup files rejected by default (requires --allow-backup)
- Dry-run is default (no DB mutation)
- Apply stores quarantined/draft entries only (never approves, never activates)
- Symlink escape and directory traversal rejected
- Report contains metadata only (no body text, no absolute paths leaked)
- No network calls, no provider calls, no LLM calls
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from registry_governance import (
    MAX_IMPORT_ENTRY_COUNT,
    MAX_REGISTRY_FILE_BYTES,
    RegistryImportError,
    compute_entry_content_hash,
    dry_run_import,
    validate_registry_entries,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = frozenset({'.json'})
MAX_DECODED_CHARS = 5_000_000
_SAFE_LABEL_RE = re.compile(r'^[A-Za-z0-9_.\-]{1,128}$')
_BACKUP_PATTERN = re.compile(r'\.bak', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ImportResult:
    """Safe import result (no body text, no absolute paths)."""
    source_label: str
    source_hash: str
    framework: str | None
    dry_run: bool
    entry_count: int
    quarantined_count: int
    draft_count: int
    malformed_count: int
    duplicate_count: int
    missing_name_count: int
    missing_framework_count: int
    missing_provenance_count: int
    license_unknown_count: int
    ocr_review_required_count: int
    llm_assisted_review_required_count: int
    extraction_unverified_count: int
    code_name_conflict_count: int
    content_hash_mismatch_count: int
    release_eligible_count: int
    stored_source_id: str | None = None

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            'source_label': self.source_label,
            'source_hash': self.source_hash,
            'framework': self.framework,
            'dry_run': self.dry_run,
            'entry_count': self.entry_count,
            'quarantined_count': self.quarantined_count,
            'draft_count': self.draft_count,
            'malformed_count': self.malformed_count,
            'duplicate_count': self.duplicate_count,
            'missing_name_count': self.missing_name_count,
            'missing_framework_count': self.missing_framework_count,
            'missing_provenance_count': self.missing_provenance_count,
            'license_unknown_count': self.license_unknown_count,
            'ocr_review_required_count': self.ocr_review_required_count,
            'llm_assisted_review_required_count': self.llm_assisted_review_required_count,
            'extraction_unverified_count': self.extraction_unverified_count,
            'code_name_conflict_count': self.code_name_conflict_count,
            'content_hash_mismatch_count': self.content_hash_mismatch_count,
            'release_eligible_count': self.release_eligible_count,
            'stored_source_id': self.stored_source_id,
        }


# ---------------------------------------------------------------------------
# Source validation
# ---------------------------------------------------------------------------

def compute_source_hash(path: Path) -> str:
    """SHA-256 hash of file contents for provenance."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def validate_source_file(
    source_path: str | Path,
    import_root: str | Path,
    allow_backup: bool = False,
) -> Path:
    """Validate and resolve a source file with full containment checks."""
    root = Path(import_root).resolve()
    requested = Path(source_path)

    # Reject absolute paths from outside
    if requested.is_absolute():
        resolved = requested.resolve()
    else:
        resolved = (root / requested).resolve()

    # Containment: must be within import root
    try:
        resolved.relative_to(root)
    except ValueError:
        raise RegistryImportError('Import source is outside the approved import root.')

    # Reject symlink escape
    if resolved != Path(os.path.realpath(resolved)):
        real = Path(os.path.realpath(resolved)).resolve()
        try:
            real.relative_to(root)
        except ValueError:
            raise RegistryImportError('Import source symlink escapes the approved import root.')

    # Must be a regular file (not directory)
    if not resolved.is_file():
        raise RegistryImportError('Import source must be a single regular file.')

    # Extension check
    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise RegistryImportError(f'Unsupported import file extension: {resolved.suffix}.')

    # Backup check
    if _BACKUP_PATTERN.search(resolved.name) and not allow_backup:
        raise RegistryImportError(
            'Backup files are rejected by default. Use --allow-backup to override.'
        )

    # Size check
    if resolved.stat().st_size > MAX_REGISTRY_FILE_BYTES:
        raise RegistryImportError('Import source exceeds maximum file size.')

    return resolved


# ---------------------------------------------------------------------------
# Dry-run import (no DB mutation)
# ---------------------------------------------------------------------------

def dry_run_import_to_db(
    source_path: str | Path,
    framework: str | None = None,
    import_root: str | Path | None = None,
    allow_backup: bool = False,
) -> ImportResult:
    """Perform a dry-run import validation. No database mutation."""
    root = Path(import_root) if import_root else Path.cwd()
    resolved = validate_source_file(source_path, root, allow_backup=allow_backup)
    source_hash = compute_source_hash(resolved)
    safe_label = resolved.name  # basename only — no absolute path

    report = dry_run_import(
        resolved, dataset_name=safe_label, source_framework=framework, import_root=root,
    )
    reason_counts = dict(report.reason_counts)

    return ImportResult(
        source_label=safe_label,
        source_hash=source_hash,
        framework=report.source_framework,
        dry_run=True,
        entry_count=report.entry_count,
        quarantined_count=report.quarantined_count,
        draft_count=report.entry_count - report.quarantined_count,
        malformed_count=reason_counts.get('MALFORMED_CODE', 0),
        duplicate_count=reason_counts.get('DUPLICATE_CODE', 0),
        missing_name_count=reason_counts.get('MISSING_NAME', 0),
        missing_framework_count=reason_counts.get('MISSING_FRAMEWORK', 0),
        missing_provenance_count=reason_counts.get('MISSING_PROVENANCE', 0),
        license_unknown_count=reason_counts.get('LICENSE_STATUS_UNKNOWN', 0),
        ocr_review_required_count=reason_counts.get('OCR_REVIEW_REQUIRED', 0),
        llm_assisted_review_required_count=reason_counts.get('LLM_ASSISTED_REVIEW_REQUIRED', 0),
        extraction_unverified_count=reason_counts.get('EXTRACTION_UNVERIFIED', 0),
        code_name_conflict_count=reason_counts.get('CODE_NAME_CONFLICT', 0),
        content_hash_mismatch_count=reason_counts.get('CONTENT_HASH_MISMATCH', 0),
        release_eligible_count=report.release_eligible_count,
    )


# ---------------------------------------------------------------------------
# Apply import (stores quarantined/draft only)
# ---------------------------------------------------------------------------

def apply_import(
    conn,
    source_path: str | Path,
    framework: str,
    import_root: str | Path,
    operator_id: str,
    source_id: str,
    allow_backup: bool = False,
) -> ImportResult:
    """Apply import: stores entries as quarantined/draft. Never approves or activates."""
    from registry_workflow import create_source_metadata, register_entry, record_provenance

    root = Path(import_root).resolve()
    resolved = validate_source_file(source_path, root, allow_backup=allow_backup)
    source_hash = compute_source_hash(resolved)
    safe_label = resolved.name

    report = dry_run_import(
        resolved, dataset_name=safe_label, source_framework=framework, import_root=root,
    )

    # Store source metadata
    create_source_metadata(
        conn, source_id=source_id, framework=framework,
        title=safe_label, version='', source_hash=source_hash,
        license_status='unknown',
    )

    # Store entries as quarantined (if issues) or draft (if clean but not approved)
    stored_count = 0
    for i, entry in enumerate(report.entries):
        entry_id = f'{source_id}-E-{i:04d}'
        lifecycle = 'quarantined' if entry.quarantine_reasons else 'draft'
        content_hash = entry.content_hash or compute_entry_content_hash(entry)
        register_entry(
            conn, entry_id=entry_id, source_id=source_id,
            framework=entry.framework, registry_family=entry.framework,
            entry_code=entry.code, entry_name=entry.name,
            content_hash=content_hash, lifecycle_state=lifecycle,
        )
        record_provenance(
            conn, entry_id=entry_id,
            extraction_method=entry.extraction_method or 'unknown',
            extraction_tool=entry.extraction_tool or '',
            reviewer=operator_id,
        )
        stored_count += 1

    reason_counts = dict(report.reason_counts)
    return ImportResult(
        source_label=safe_label,
        source_hash=source_hash,
        framework=report.source_framework,
        dry_run=False,
        entry_count=report.entry_count,
        quarantined_count=report.quarantined_count,
        draft_count=report.entry_count - report.quarantined_count,
        malformed_count=reason_counts.get('MALFORMED_CODE', 0),
        duplicate_count=reason_counts.get('DUPLICATE_CODE', 0),
        missing_name_count=reason_counts.get('MISSING_NAME', 0),
        missing_framework_count=reason_counts.get('MISSING_FRAMEWORK', 0),
        missing_provenance_count=reason_counts.get('MISSING_PROVENANCE', 0),
        license_unknown_count=reason_counts.get('LICENSE_STATUS_UNKNOWN', 0),
        ocr_review_required_count=reason_counts.get('OCR_REVIEW_REQUIRED', 0),
        llm_assisted_review_required_count=reason_counts.get('LLM_ASSISTED_REVIEW_REQUIRED', 0),
        extraction_unverified_count=reason_counts.get('EXTRACTION_UNVERIFIED', 0),
        code_name_conflict_count=reason_counts.get('CODE_NAME_CONFLICT', 0),
        content_hash_mismatch_count=reason_counts.get('CONTENT_HASH_MISMATCH', 0),
        release_eligible_count=report.release_eligible_count,
        stored_source_id=source_id,
    )
