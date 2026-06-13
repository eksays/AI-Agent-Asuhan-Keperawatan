"""Phase 8 P8-BE — Durable registry workflow service.

Bridges registry_governance.py validation with the PostgreSQL schema tables.
Implements: review queue, approval artifacts, extraction verification,
entry lifecycle management, and safe governance status queries.

All methods require an explicit connection. All use parameterized SQL.
No registry body text is stored or returned. No credentials are logged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from registry_governance import APPROVED_LICENSE_STATUSES

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENTRY_LIFECYCLE_STATES = frozenset({
    'quarantined', 'draft', 'pending_review', 'review_rejected',
    'review_verified', 'approved', 'deprecated',
})

RELEASE_LIFECYCLE_STATES = frozenset({
    'draft', 'validated', 'approved', 'active',
    'superseded', 'rolled_back', 'rejected',
})

EXTRACTION_REVIEW_STATUSES = frozenset({
    'unverified', 'verified_by_human', 'rejected',
})

REVIEW_STATUSES = frozenset({
    'pending', 'in_review', 'approved', 'rejected', 'deferred',
})

APPROVAL_DECISIONS = frozenset({
    'approved', 'rejected', 'conditional',
})

# Safe identifier pattern: alphanumeric, hyphens, underscores, dots, colons
_SAFE_ID_RE = re.compile(r'^[A-Za-z0-9_.\-:]{1,128}$')
_SHA256_RE = re.compile(r'^[a-f0-9]{64}$')


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class RegistryWorkflowError(ValueError):
    """Safe workflow error. Never include credentials or body text."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GovernanceStatus:
    """Safe governance status for an entry (no body text)."""
    entry_id: str
    framework: str
    registry_family: str
    entry_code: str
    lifecycle_state: str
    has_provenance: bool
    has_review: bool
    review_status: str | None
    has_approval: bool
    approval_decision: str | None
    extraction_method: str | None
    extraction_verified: bool
    source_license_status: str | None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _require_safe_id(value: str, field_name: str) -> str:
    """Validate an identifier is safe for storage and logging."""
    value = (value or '').strip()
    if not value:
        raise RegistryWorkflowError(f'{field_name} is required.')
    if not _SAFE_ID_RE.match(value):
        raise RegistryWorkflowError(f'{field_name} contains unsafe characters.')
    return value


def _require_enum(value: str, allowed: frozenset, field_name: str) -> str:
    value = (value or '').strip().lower()
    if value not in allowed:
        raise RegistryWorkflowError(f'{field_name} must be one of: {", ".join(sorted(allowed))}.')
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Source metadata
# ---------------------------------------------------------------------------

def create_source_metadata(
    conn,
    source_id: str,
    framework: str,
    title: str,
    version: str,
    source_hash: str,
    license_status: str,
) -> dict[str, Any]:
    """Insert a registry source record. Returns safe metadata dict."""
    source_id = _require_safe_id(source_id, 'source_id')
    framework = _require_safe_id(framework, 'framework')
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO registry_sources "
            "(source_id, framework, source_title, source_version, source_hash, license_status) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (source_id) DO NOTHING",
            (source_id, framework, title[:256], version[:64], source_hash[:128], license_status[:32]),
        )
    conn.commit()
    return {'source_id': source_id, 'framework': framework, 'license_status': license_status}


# ---------------------------------------------------------------------------
# Entry registration
# ---------------------------------------------------------------------------

def register_entry(
    conn,
    entry_id: str,
    source_id: str,
    framework: str,
    registry_family: str,
    entry_code: str,
    entry_name: str,
    content_hash: str,
    lifecycle_state: str = 'quarantined',
) -> dict[str, Any]:
    """Insert a governed registry entry. Returns safe metadata dict."""
    entry_id = _require_safe_id(entry_id, 'entry_id')
    source_id = _require_safe_id(source_id, 'source_id')
    lifecycle_state = _require_enum(lifecycle_state, ENTRY_LIFECYCLE_STATES, 'lifecycle_state')
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO registry_entries "
            "(entry_id, source_id, framework, registry_family, entry_code, entry_name, "
            "content_hash, lifecycle_state) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (entry_id) DO NOTHING",
            (entry_id, source_id, framework[:16], registry_family[:16],
             entry_code[:32], entry_name[:256], content_hash[:128], lifecycle_state),
        )
    conn.commit()
    return {'entry_id': entry_id, 'lifecycle_state': lifecycle_state}


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def record_provenance(
    conn,
    entry_id: str,
    extraction_method: str,
    extraction_tool: str = '',
    reviewer: str = '',
    notes: str = '',
) -> dict[str, Any]:
    """Insert provenance for an entry."""
    entry_id = _require_safe_id(entry_id, 'entry_id')
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entry_provenance "
            "(entry_id, extraction_method, extraction_tool, reviewer, notes) "
            "VALUES (%s, %s, %s, %s, %s)",
            (entry_id, extraction_method[:32], extraction_tool[:128],
             reviewer[:128], notes[:512]),
        )
    conn.commit()
    return {'entry_id': entry_id, 'extraction_method': extraction_method}


# ---------------------------------------------------------------------------
# Extraction verification
# ---------------------------------------------------------------------------

def record_extraction_verification(
    conn,
    verification_id: str,
    entry_id: str,
    status: str,
    verified_by: str = '',
    reason_code: str = '',
    notes: str = '',
) -> dict[str, Any]:
    """Record human extraction verification for OCR/LLM-derived entries."""
    verification_id = _require_safe_id(verification_id, 'verification_id')
    entry_id = _require_safe_id(entry_id, 'entry_id')
    status = _require_enum(status, EXTRACTION_REVIEW_STATUSES, 'extraction_review_status')
    verified_at = _utc_now() if status != 'unverified' else None
    if status == 'verified_by_human' and not verified_by.strip():
        raise RegistryWorkflowError('verified_by is required for verified_by_human status.')
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO extraction_verifications "
            "(verification_id, entry_id, extraction_review_status, verified_by, "
            "verified_at, reason_code, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (verification_id) DO UPDATE SET "
            "extraction_review_status = EXCLUDED.extraction_review_status, "
            "verified_by = EXCLUDED.verified_by, "
            "verified_at = EXCLUDED.verified_at, "
            "reason_code = EXCLUDED.reason_code, "
            "notes = EXCLUDED.notes",
            (verification_id, entry_id, status, verified_by[:128],
             verified_at, reason_code[:64], notes[:512]),
        )
    conn.commit()
    return {'verification_id': verification_id, 'entry_id': entry_id, 'status': status}


def get_extraction_verification(conn, entry_id: str) -> dict[str, Any] | None:
    """Get latest extraction verification for an entry."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT verification_id, extraction_review_status, verified_by, verified_at "
            "FROM extraction_verifications WHERE entry_id = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (entry_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        'verification_id': row[0],
        'status': row[1],
        'verified_by': row[2],
        'verified_at': str(row[3]) if row[3] else None,
    }


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

def enqueue_review(
    conn,
    review_id: str,
    entry_id: str,
    reviewer_id: str = '',
    scope: str = '',
) -> dict[str, Any]:
    """Insert a review queue item."""
    review_id = _require_safe_id(review_id, 'review_id')
    entry_id = _require_safe_id(entry_id, 'entry_id')
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO review_queue "
            "(review_id, entry_id, reviewer_id, review_status, review_scope) "
            "VALUES (%s, %s, %s, 'pending', %s) "
            "ON CONFLICT (review_id) DO NOTHING",
            (review_id, entry_id, reviewer_id[:128], scope[:128]),
        )
    conn.commit()
    return {'review_id': review_id, 'entry_id': entry_id, 'status': 'pending'}


def record_review_decision(
    conn,
    review_id: str,
    status: str,
    reviewer_id: str,
    notes: str = '',
) -> dict[str, Any]:
    """Update review queue with decision."""
    review_id = _require_safe_id(review_id, 'review_id')
    status = _require_enum(status, REVIEW_STATUSES, 'review_status')
    if not reviewer_id.strip():
        raise RegistryWorkflowError('reviewer_id is required for review decision.')
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE review_queue SET review_status = %s, reviewer_id = %s, "
            "reviewed_at = %s, notes = %s WHERE review_id = %s",
            (status, reviewer_id[:128], _utc_now(), notes[:512], review_id),
        )
    conn.commit()
    return {'review_id': review_id, 'status': status}


def get_review_queue(conn, status_filter: str | None = None) -> list[dict[str, Any]]:
    """Get review queue items. Returns safe metadata only."""
    if status_filter:
        status_filter = _require_enum(status_filter, REVIEW_STATUSES, 'status_filter')
    with conn.cursor() as cur:
        if status_filter:
            cur.execute(
                "SELECT review_id, entry_id, reviewer_id, review_status, submitted_at "
                "FROM review_queue WHERE review_status = %s ORDER BY submitted_at",
                (status_filter,),
            )
        else:
            cur.execute(
                "SELECT review_id, entry_id, reviewer_id, review_status, submitted_at "
                "FROM review_queue ORDER BY submitted_at",
            )
        rows = cur.fetchall()
    return [
        {'review_id': r[0], 'entry_id': r[1], 'reviewer_id': r[2],
         'status': r[3], 'submitted_at': str(r[4])}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Entry approval artifacts
# ---------------------------------------------------------------------------

def create_approval_artifact(
    conn,
    approval_id: str,
    review_id: str,
    entry_id: str,
    approver_id: str,
    decision: str,
    content_hash_at_approval: str,
    rationale: str = '',
) -> dict[str, Any]:
    """Create an entry-level approval artifact with full governance guards."""
    approval_id = _require_safe_id(approval_id, 'approval_id')
    review_id = _require_safe_id(review_id, 'review_id')
    entry_id = _require_safe_id(entry_id, 'entry_id')
    decision = _require_enum(decision, APPROVAL_DECISIONS, 'decision')

    # Guard: explicit approver required
    if not approver_id.strip():
        raise RegistryWorkflowError('approver_id is required for approval artifact.')

    # Guard: check entry exists and is not in a blocked lifecycle state
    with conn.cursor() as cur:
        cur.execute(
            "SELECT lifecycle_state FROM registry_entries WHERE entry_id = %s",
            (entry_id,),
        )
        entry_row = cur.fetchone()
    if not entry_row:
        raise RegistryWorkflowError('Entry does not exist.')
    lifecycle = entry_row[0]
    if lifecycle in ('quarantined', 'deprecated'):
        raise RegistryWorkflowError(
            f'Cannot create approval for entry in lifecycle state: {lifecycle}.'
        )

    # Guard: provenance must exist
    with conn.cursor() as cur:
        cur.execute(
            "SELECT extraction_method FROM entry_provenance WHERE entry_id = %s LIMIT 1",
            (entry_id,),
        )
        prov_row = cur.fetchone()
    if not prov_row:
        raise RegistryWorkflowError('Cannot create approval without provenance.')
    extraction_method = (prov_row[0] or '').lower()

    # Guard: OCR/LLM requires human extraction verification
    if extraction_method in ('ocr', 'llm_assisted'):
        ev = get_extraction_verification(conn, entry_id)
        if not ev or ev['status'] != 'verified_by_human':
            raise RegistryWorkflowError(
                f'OCR/LLM-derived entry requires human extraction verification '
                f'before approval (current: {ev["status"] if ev else "none"}).'
            )

    # Guard: source license must be approved
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.license_status FROM registry_entries e "
            "JOIN registry_sources s ON e.source_id = s.source_id "
            "WHERE e.entry_id = %s",
            (entry_id,),
        )
        src_row = cur.fetchone()
    if not src_row or (src_row[0] or '').strip().lower() not in APPROVED_LICENSE_STATUSES:
        raise RegistryWorkflowError('Source license status is not approved.')

    # Insert approval artifact
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO approval_artifacts "
            "(approval_id, review_id, entry_id, approver_id, approval_decision, "
            "content_hash_at_approval, rationale) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (approval_id, review_id, entry_id, approver_id[:128], decision,
             content_hash_at_approval[:128], rationale[:512]),
        )
    conn.commit()
    return {'approval_id': approval_id, 'entry_id': entry_id, 'decision': decision}


# ---------------------------------------------------------------------------
# Lifecycle management
# ---------------------------------------------------------------------------

def update_entry_lifecycle(
    conn,
    entry_id: str,
    new_state: str,
) -> dict[str, Any]:
    """Update an entry's lifecycle state."""
    entry_id = _require_safe_id(entry_id, 'entry_id')
    new_state = _require_enum(new_state, ENTRY_LIFECYCLE_STATES, 'lifecycle_state')
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE registry_entries SET lifecycle_state = %s, updated_at = %s "
            "WHERE entry_id = %s",
            (new_state, _utc_now(), entry_id),
        )
    conn.commit()
    return {'entry_id': entry_id, 'lifecycle_state': new_state}


# ---------------------------------------------------------------------------
# Governance status
# ---------------------------------------------------------------------------

def get_entry_governance_status(conn, entry_id: str) -> GovernanceStatus | None:
    """Get full governance status for an entry. Returns safe metadata only."""
    with conn.cursor() as cur:
        # Entry
        cur.execute(
            "SELECT framework, registry_family, entry_code, lifecycle_state "
            "FROM registry_entries WHERE entry_id = %s",
            (entry_id,),
        )
        entry_row = cur.fetchone()
        if not entry_row:
            return None

        # Provenance
        cur.execute(
            "SELECT extraction_method FROM entry_provenance "
            "WHERE entry_id = %s ORDER BY created_at DESC LIMIT 1",
            (entry_id,),
        )
        prov_row = cur.fetchone()

        # Review
        cur.execute(
            "SELECT review_status FROM review_queue "
            "WHERE entry_id = %s ORDER BY submitted_at DESC LIMIT 1",
            (entry_id,),
        )
        review_row = cur.fetchone()

        # Approval
        cur.execute(
            "SELECT approval_decision FROM approval_artifacts "
            "WHERE entry_id = %s ORDER BY approved_at DESC LIMIT 1",
            (entry_id,),
        )
        approval_row = cur.fetchone()

        # Extraction verification
        ev = get_extraction_verification(conn, entry_id)

        # Source license
        cur.execute(
            "SELECT s.license_status FROM registry_entries e "
            "JOIN registry_sources s ON e.source_id = s.source_id "
            "WHERE e.entry_id = %s",
            (entry_id,),
        )
        license_row = cur.fetchone()

    return GovernanceStatus(
        entry_id=entry_id,
        framework=entry_row[0],
        registry_family=entry_row[1],
        entry_code=entry_row[2],
        lifecycle_state=entry_row[3],
        has_provenance=prov_row is not None,
        has_review=review_row is not None,
        review_status=review_row[0] if review_row else None,
        has_approval=approval_row is not None,
        approval_decision=approval_row[0] if approval_row else None,
        extraction_method=prov_row[0] if prov_row else None,
        extraction_verified=bool(ev and ev['status'] == 'verified_by_human'),
        source_license_status=license_row[0] if license_row else None,
    )
