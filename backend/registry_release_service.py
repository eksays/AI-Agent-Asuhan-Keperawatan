"""Phase 8 P8-BE — Durable release, activation, and rollback service.

Bridges registry_release.py validation logic with the PostgreSQL store.
Implements: release candidate creation, deterministic manifest hashing,
release-level approval, atomic activation/rollback with SELECT FOR UPDATE
serialization, and complete-family policy.

Design:
- All pointer mutations use SELECT ... FOR UPDATE for serialization.
- First-activation initializes a stable pointer row via INSERT ... ON CONFLICT.
- Activation and rollback require explicit activation_enabled=True.
- Synthetic integration tests may use a test-local override only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from registry_workflow import (
    ENTRY_LIFECYCLE_STATES,
    RELEASE_LIFECYCLE_STATES,
    RegistryWorkflowError,
    _require_safe_id,
    _require_enum,
    _utc_now,
)

# ---------------------------------------------------------------------------
# Complete-family policy
# ---------------------------------------------------------------------------

FRAMEWORK_FAMILIES = {
    '3S': frozenset({'SDKI', 'SLKI', 'SIKI'}),
    '3N': frozenset({'NANDA', 'NOC', 'NIC'}),
}


# ---------------------------------------------------------------------------
# Deterministic manifest hash
# ---------------------------------------------------------------------------

def compute_manifest_hash(entries: list[dict[str, str]]) -> str:
    """Compute deterministic manifest hash from canonical sorted entry fields.

    Each entry dict must have: registry_family, code, entry_id, content_hash.
    Sorted by (registry_family, code, entry_id) for deterministic ordering.
    """
    canonical = sorted(
        entries,
        key=lambda e: (e.get('registry_family', ''), e.get('code', ''), e.get('entry_id', '')),
    )
    material = json.dumps(
        canonical, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
    ).encode('utf-8')
    return hashlib.sha256(material).hexdigest()


# ---------------------------------------------------------------------------
# Release candidate creation
# ---------------------------------------------------------------------------

def create_release_candidate(
    conn,
    manifest_id: str,
    framework: str,
    release_version: str,
    entry_ids: list[str],
) -> dict[str, Any]:
    """Create a release candidate from approved entries.

    Validates: all entries are approved, hashes match, provenance complete.
    Stores manifest and manifest entries. Returns safe metadata.
    """
    manifest_id = _require_safe_id(manifest_id, 'manifest_id')

    # Fetch entry data
    entry_data = []
    with conn.cursor() as cur:
        for eid in entry_ids:
            eid = _require_safe_id(eid, 'entry_id')
            cur.execute(
                "SELECT entry_id, framework, registry_family, entry_code, "
                "content_hash, lifecycle_state "
                "FROM registry_entries WHERE entry_id = %s",
                (eid,),
            )
            row = cur.fetchone()
            if not row:
                raise RegistryWorkflowError(f'Entry not found: {eid}')
            if row[5] != 'approved':
                raise RegistryWorkflowError(
                    f'Entry {eid} lifecycle is {row[5]}, not approved.'
                )
            # Check approval artifact exists
            cur.execute(
                "SELECT approval_id FROM approval_artifacts "
                "WHERE entry_id = %s AND approval_decision = 'approved' LIMIT 1",
                (eid,),
            )
            if not cur.fetchone():
                raise RegistryWorkflowError(
                    f'Entry {eid} has no entry-level approval artifact.'
                )
            entry_data.append({
                'entry_id': row[0],
                'framework': row[1],
                'registry_family': row[2],
                'code': row[3],
                'content_hash': row[4],
            })

    # Compute deterministic manifest hash
    manifest_hash = compute_manifest_hash(entry_data)

    # Insert manifest
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO release_manifests "
            "(manifest_id, framework, release_version, manifest_hash, status) "
            "VALUES (%s, %s, %s, %s, 'candidate')",
            (manifest_id, framework[:16], release_version[:64], manifest_hash),
        )
        # Insert manifest entries
        for ed in entry_data:
            cur.execute(
                "INSERT INTO release_manifest_entries "
                "(manifest_id, entry_id, registry_family, content_hash) "
                "VALUES (%s, %s, %s, %s)",
                (manifest_id, ed['entry_id'], ed['registry_family'], ed['content_hash']),
            )
    conn.commit()
    return {
        'manifest_id': manifest_id,
        'framework': framework,
        'manifest_hash': manifest_hash,
        'entry_count': len(entry_data),
        'status': 'candidate',
    }


# ---------------------------------------------------------------------------
# Release validation
# ---------------------------------------------------------------------------

def validate_release(conn, manifest_id: str) -> dict[str, Any]:
    """Validate a release candidate. Returns validation result."""
    manifest_id = _require_safe_id(manifest_id, 'manifest_id')
    issues = []

    with conn.cursor() as cur:
        # Get manifest
        cur.execute(
            "SELECT manifest_id, framework, release_version, manifest_hash, status "
            "FROM release_manifests WHERE manifest_id = %s",
            (manifest_id,),
        )
        manifest_row = cur.fetchone()
        if not manifest_row:
            return {'valid': False, 'issues': ['manifest_not_found']}

        if manifest_row[4] not in ('candidate', 'validated'):
            issues.append(f'invalid_status:{manifest_row[4]}')

        # Get manifest entries
        cur.execute(
            "SELECT entry_id, registry_family, content_hash "
            "FROM release_manifest_entries WHERE manifest_id = %s",
            (manifest_id,),
        )
        me_rows = cur.fetchall()

        # Verify each entry
        families_present = set()
        for me in me_rows:
            entry_id, family, expected_hash = me
            families_present.add(family)
            cur.execute(
                "SELECT content_hash, lifecycle_state FROM registry_entries "
                "WHERE entry_id = %s",
                (entry_id,),
            )
            er = cur.fetchone()
            if not er:
                issues.append(f'entry_missing:{entry_id}')
                continue
            if er[0] != expected_hash:
                issues.append(f'hash_mismatch:{entry_id}')
            if er[1] != 'approved':
                issues.append(f'not_approved:{entry_id}')

            # Check approval artifact
            cur.execute(
                "SELECT 1 FROM approval_artifacts "
                "WHERE entry_id = %s AND approval_decision = 'approved' LIMIT 1",
                (entry_id,),
            )
            if not cur.fetchone():
                issues.append(f'missing_approval:{entry_id}')

        # Verify manifest hash
        entry_data = [
            {'entry_id': r[0], 'registry_family': r[1], 'content_hash': r[2],
             'code': '', 'framework': ''}
            for r in me_rows
        ]
        # Need full entry data for hash
        entry_data_full = []
        for me in me_rows:
            cur.execute(
                "SELECT entry_code, framework FROM registry_entries WHERE entry_id = %s",
                (me[0],),
            )
            er = cur.fetchone()
            entry_data_full.append({
                'entry_id': me[0], 'registry_family': me[1],
                'content_hash': me[2], 'code': er[0] if er else '',
                'framework': er[1] if er else '',
            })
        recomputed = compute_manifest_hash(entry_data_full)
        if recomputed != manifest_row[3]:
            issues.append('manifest_hash_mismatch')

    return {
        'valid': not issues,
        'manifest_id': manifest_id,
        'framework': manifest_row[1],
        'entry_count': len(me_rows),
        'families_present': sorted(families_present),
        'issues': issues,
    }


# ---------------------------------------------------------------------------
# Release validation update
# ---------------------------------------------------------------------------

def mark_release_validated(conn, manifest_id: str) -> dict[str, Any]:
    """Mark a validated release candidate."""
    validation = validate_release(conn, manifest_id)
    if not validation['valid']:
        raise RegistryWorkflowError(
            f'Release validation failed: {", ".join(validation["issues"])}'
        )
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE release_manifests SET status = 'validated' WHERE manifest_id = %s",
            (manifest_id,),
        )
    conn.commit()
    return {'manifest_id': manifest_id, 'status': 'validated'}


# ---------------------------------------------------------------------------
# Release-level approval artifact
# ---------------------------------------------------------------------------

def create_release_approval(
    conn,
    approval_id: str,
    manifest_id: str,
    approver_id: str,
    decision: str,
    rationale: str = '',
) -> dict[str, Any]:
    """Create a release-level approval artifact (separate from entry-level)."""
    approval_id = _require_safe_id(approval_id, 'approval_id')
    manifest_id = _require_safe_id(manifest_id, 'manifest_id')
    if not approver_id.strip():
        raise RegistryWorkflowError('approver_id is required for release approval.')
    decision = _require_enum(decision, frozenset({'approved', 'rejected', 'conditional'}), 'decision')

    # Check manifest exists and is validated
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, manifest_hash FROM release_manifests WHERE manifest_id = %s",
            (manifest_id,),
        )
        row = cur.fetchone()
    if not row:
        raise RegistryWorkflowError('Release manifest not found.')
    if row[0] != 'validated':
        raise RegistryWorkflowError(
            f'Release must be validated before approval (current: {row[0]}).'
        )

    # Insert release approval artifact
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO release_approval_artifacts "
            "(approval_id, manifest_id, approver_id, approval_decision, "
            "manifest_hash_at_approval, rationale) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (approval_id, manifest_id, approver_id[:128], decision,
             row[1], rationale[:512]),
        )
    # Update manifest status if approved
    if decision == 'approved':
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE release_manifests SET status = 'approved' "
                "WHERE manifest_id = %s",
                (manifest_id,),
            )
    conn.commit()
    return {'approval_id': approval_id, 'manifest_id': manifest_id, 'decision': decision}


# ---------------------------------------------------------------------------
# Complete-family check
# ---------------------------------------------------------------------------

def check_family_completeness(
    conn,
    framework_standard: str,
    manifest_id: str,
) -> dict[str, Any]:
    """Check if a release manifest has all required families for a standard."""
    required = FRAMEWORK_FAMILIES.get(framework_standard.upper())
    if not required:
        return {'complete': False, 'reason': 'unsupported_standard'}

    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT registry_family FROM release_manifest_entries "
            "WHERE manifest_id = %s",
            (manifest_id,),
        )
        present = {r[0] for r in cur.fetchall()}

    missing = required - present
    return {
        'complete': not missing,
        'required': sorted(required),
        'present': sorted(present),
        'missing': sorted(missing),
        'status': 'registry_ready' if not missing else 'registry_incomplete',
    }


# ---------------------------------------------------------------------------
# Atomic activation
# ---------------------------------------------------------------------------

def activate_release(
    conn,
    framework: str,
    manifest_id: str,
    *,
    activation_enabled: bool,
    performed_by: str = 'system',
) -> dict[str, Any]:
    """Atomically activate a release with SELECT FOR UPDATE serialization.

    Requires activation_enabled=True. Blocked otherwise.
    """
    if not activation_enabled:
        raise RegistryWorkflowError(
            'Activation rejected: REGISTRY_ACTIVATION_ENABLED=false.'
        )
    manifest_id = _require_safe_id(manifest_id, 'manifest_id')
    framework = framework.strip()

    with conn.cursor() as cur:
        # Verify manifest is approved
        cur.execute(
            "SELECT status, manifest_hash FROM release_manifests "
            "WHERE manifest_id = %s",
            (manifest_id,),
        )
        mrow = cur.fetchone()
        if not mrow:
            raise RegistryWorkflowError('Release manifest not found.')
        if mrow[0] != 'approved':
            raise RegistryWorkflowError(
                f'Release must be approved before activation (current: {mrow[0]}).'
            )

        # Verify release-level approval artifact exists
        cur.execute(
            "SELECT 1 FROM release_approval_artifacts "
            "WHERE manifest_id = %s AND approval_decision = 'approved' LIMIT 1",
            (manifest_id,),
        )
        if not cur.fetchone():
            raise RegistryWorkflowError(
                'Release-level approval artifact is required for activation.'
            )

        # Initialize stable pointer row if absent
        cur.execute(
            "INSERT INTO active_releases (framework, manifest_id) "
            "VALUES (%s, %s) ON CONFLICT (framework) DO NOTHING",
            (framework, manifest_id),
        )

        # Lock pointer row for serialization
        cur.execute(
            "SELECT manifest_id FROM active_releases "
            "WHERE framework = %s FOR UPDATE",
            (framework,),
        )
        pointer_row = cur.fetchone()
        previous_manifest_id = pointer_row[0] if pointer_row else None

        # Record history
        cur.execute(
            "INSERT INTO release_history "
            "(framework, manifest_id, action, performed_by, notes) "
            "VALUES (%s, %s, 'activated', %s, %s)",
            (framework, manifest_id, performed_by[:128],
             f'previous:{previous_manifest_id or "none"}'),
        )

        # Update active pointer
        cur.execute(
            "UPDATE active_releases SET manifest_id = %s, activated_at = %s "
            "WHERE framework = %s",
            (manifest_id, _utc_now(), framework),
        )

        # Update manifest status
        cur.execute(
            "UPDATE release_manifests SET status = 'active', activated_at = %s "
            "WHERE manifest_id = %s",
            (_utc_now(), manifest_id),
        )

        # Mark previous as superseded
        if previous_manifest_id and previous_manifest_id != manifest_id:
            cur.execute(
                "UPDATE release_manifests SET status = 'superseded' "
                "WHERE manifest_id = %s AND status = 'active'",
                (previous_manifest_id,),
            )

    conn.commit()
    return {
        'manifest_id': manifest_id,
        'framework': framework,
        'status': 'active',
        'previous_manifest_id': previous_manifest_id,
    }


# ---------------------------------------------------------------------------
# Atomic rollback
# ---------------------------------------------------------------------------

def rollback_release(
    conn,
    framework: str,
    target_manifest_id: str,
    *,
    activation_enabled: bool,
    performed_by: str = 'system',
) -> dict[str, Any]:
    """Atomically rollback to a previously approved release.

    Requires activation_enabled=True. Target must be an approved historical release.
    """
    if not activation_enabled:
        raise RegistryWorkflowError(
            'Rollback rejected: REGISTRY_ACTIVATION_ENABLED=false.'
        )
    target_manifest_id = _require_safe_id(target_manifest_id, 'target_manifest_id')
    framework = framework.strip()

    with conn.cursor() as cur:
        # Verify target exists and was previously active or approved
        cur.execute(
            "SELECT status FROM release_manifests WHERE manifest_id = %s",
            (target_manifest_id,),
        )
        trow = cur.fetchone()
        if not trow:
            raise RegistryWorkflowError('Rollback target manifest not found.')
        if trow[0] not in ('approved', 'superseded', 'active'):
            raise RegistryWorkflowError(
                f'Rollback target must be an approved or previously active release '
                f'(current: {trow[0]}).'
            )

        # Verify release-level approval exists for target
        cur.execute(
            "SELECT 1 FROM release_approval_artifacts "
            "WHERE manifest_id = %s AND approval_decision = 'approved' LIMIT 1",
            (target_manifest_id,),
        )
        if not cur.fetchone():
            raise RegistryWorkflowError(
                'Rollback target requires a release-level approval artifact.'
            )

        # Initialize stable pointer row if absent (same pattern as activate)
        cur.execute(
            "INSERT INTO active_releases (framework, manifest_id) "
            "VALUES (%s, %s) ON CONFLICT (framework) DO NOTHING",
            (framework, target_manifest_id),
        )

        # Lock pointer row for serialization
        cur.execute(
            "SELECT manifest_id FROM active_releases "
            "WHERE framework = %s FOR UPDATE",
            (framework,),
        )
        pointer_row = cur.fetchone()
        current_manifest_id = pointer_row[0] if pointer_row else None

        # Record rollback history
        cur.execute(
            "INSERT INTO release_history "
            "(framework, manifest_id, action, performed_by, notes) "
            "VALUES (%s, %s, 'rolled_back', %s, %s)",
            (framework, target_manifest_id, performed_by[:128],
             f'rolled_back_from:{current_manifest_id or "none"}'),
        )

        # Mark current as rolled_back
        if current_manifest_id and current_manifest_id != target_manifest_id:
            cur.execute(
                "UPDATE release_manifests SET status = 'rolled_back' "
                "WHERE manifest_id = %s AND status = 'active'",
                (current_manifest_id,),
            )

        # Restore target as active
        cur.execute(
            "UPDATE release_manifests SET status = 'active', activated_at = %s "
            "WHERE manifest_id = %s",
            (_utc_now(), target_manifest_id),
        )

        # Update pointer
        cur.execute(
            "UPDATE active_releases SET manifest_id = %s, activated_at = %s "
            "WHERE framework = %s",
            (target_manifest_id, _utc_now(), framework),
        )

    conn.commit()
    return {
        'manifest_id': target_manifest_id,
        'framework': framework,
        'status': 'active',
        'rolled_back_from': current_manifest_id,
    }


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_active_release(conn, framework: str) -> dict[str, Any] | None:
    """Get the active release for a framework."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ar.manifest_id, ar.activated_at, rm.release_version, "
            "rm.manifest_hash, rm.status "
            "FROM active_releases ar "
            "JOIN release_manifests rm ON ar.manifest_id = rm.manifest_id "
            "WHERE ar.framework = %s",
            (framework.strip(),),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        'manifest_id': row[0],
        'activated_at': str(row[1]),
        'release_version': row[2],
        'manifest_hash': row[3],
        'status': row[4],
    }


def get_release_history(conn, framework: str) -> list[dict[str, Any]]:
    """Get release history for a framework."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT manifest_id, action, performed_at, performed_by, notes "
            "FROM release_history WHERE framework = %s "
            "ORDER BY performed_at DESC",
            (framework.strip(),),
        )
        rows = cur.fetchall()
    return [
        {
            'manifest_id': r[0], 'action': r[1],
            'performed_at': str(r[2]), 'performed_by': r[3],
            'notes': r[4],
        }
        for r in rows
    ]
