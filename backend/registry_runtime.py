"""Phase 8 P8-BE — Registry runtime startup loader and safe metadata.

Implements:
- Bounded startup probe (max 3 attempts, 15s timeout, 2s backoff)
- Fail-closed registry loading (never auto-migrate, auto-import, or auto-approve)
- Safe server metadata exposure (no body text, no credentials)
- Complete-family awareness for 3S/3N frameworks

Design:
- Startup probe is separate from admin migration retry policy
- No Uvicorn hang — documented total upper bound ~51s
- Normal product behavior remains registry_unavailable
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from registry_store import (
    RegistryStoreConfig,
    redact_hostname,
)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

class RegistryRuntimeStatus(str, Enum):
    UNAVAILABLE = 'registry_unavailable'
    INCOMPLETE = 'registry_incomplete'
    READY = 'registry_ready'


SUPPORTED_SCHEMA_VERSIONS = frozenset({'V004', 'V005', 'V006', 'V007'})


# ---------------------------------------------------------------------------
# Runtime info
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegistryRuntimeInfo:
    """Safe runtime info for registry status. No credentials, no body text."""
    status: RegistryRuntimeStatus
    release_id: str | None = None
    framework: str | None = None
    family_completeness: dict[str, bool] | None = None
    schema_version: str | None = None
    failure_reason_code: str | None = None
    last_verified_at: str | None = None
    store_backend: str = 'disabled'
    store_health: bool = False
    activation_enabled: bool = False


# ---------------------------------------------------------------------------
# Safe metadata (for API endpoint)
# ---------------------------------------------------------------------------

def safe_registry_metadata(info: RegistryRuntimeInfo) -> dict[str, Any]:
    """Return safe structured metadata. Never body text, never credentials."""
    result: dict[str, Any] = {
        'registry_store_backend': info.store_backend,
        'registry_store_health': info.store_health,
        'registry_activation_enabled': info.activation_enabled,
        'registry_runtime_status': info.status.value,
        'registry_schema_version': info.schema_version,
        'registry_last_verified_at': info.last_verified_at,
    }
    if info.release_id:
        result['registry_active_release_id'] = info.release_id
    if info.framework:
        result['registry_framework'] = info.framework
    if info.family_completeness:
        result['registry_family_completeness'] = info.family_completeness
    if info.failure_reason_code:
        result['registry_failure_reason_code'] = info.failure_reason_code
    return result


# ---------------------------------------------------------------------------
# Bounded startup probe
# ---------------------------------------------------------------------------

# Startup probe policy (distinct from admin migration retry):
# - max_attempts: 3 (ceiling: 5)
# - connect_timeout: 15s (ceiling: 30s)
# - backoff: 2s (ceiling: 5s), exponential factor 2^attempt, capped at 10s
# - documented total upper bound: ~51s (3×15s timeouts + 2s + 4s backoffs)
STARTUP_MAX_ATTEMPTS = 3
STARTUP_CONNECT_TIMEOUT_SEC = 15
STARTUP_BACKOFF_SEC = 2


def probe_registry_store(
    config: RegistryStoreConfig,
    *,
    max_attempts: int = STARTUP_MAX_ATTEMPTS,
    connect_timeout_sec: int = STARTUP_CONNECT_TIMEOUT_SEC,
    backoff_sec: float = STARTUP_BACKOFF_SEC,
) -> RegistryRuntimeInfo:
    """Bounded startup probe. Fail-closed on any issue.

    Does NOT auto-migrate, auto-import, auto-approve, or auto-activate.
    Does NOT load backend/data_terstruktur/*.
    Does NOT log credentials or raw exceptions.
    """
    now = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    # Clamp bounds
    max_attempts = max(1, min(max_attempts, 5))
    connect_timeout_sec = max(1, min(connect_timeout_sec, 30))
    backoff_sec = max(0.5, min(backoff_sec, 5.0))

    # Store disabled
    if config.backend == 'disabled' or not config.is_enabled:
        return RegistryRuntimeInfo(
            status=RegistryRuntimeStatus.UNAVAILABLE,
            failure_reason_code='store_disabled',
            last_verified_at=now,
            store_backend=config.backend,
            activation_enabled=config.activation_enabled,
        )

    # Activation disabled
    if not config.activation_enabled:
        # Still probe health for diagnostics
        health = _probe_health(config, max_attempts, connect_timeout_sec, backoff_sec)
        return RegistryRuntimeInfo(
            status=RegistryRuntimeStatus.UNAVAILABLE,
            failure_reason_code='activation_disabled',
            last_verified_at=now,
            store_backend=config.backend,
            store_health=health.get('healthy', False),
            schema_version=health.get('schema_version'),
            activation_enabled=False,
        )

    # Full probe: activation enabled
    health = _probe_health(config, max_attempts, connect_timeout_sec, backoff_sec)
    if not health.get('healthy'):
        return RegistryRuntimeInfo(
            status=RegistryRuntimeStatus.UNAVAILABLE,
            failure_reason_code=health.get('reason', 'connection_failed'),
            last_verified_at=now,
            store_backend=config.backend,
            activation_enabled=True,
        )

    schema = health.get('schema_version')
    if schema not in SUPPORTED_SCHEMA_VERSIONS:
        return RegistryRuntimeInfo(
            status=RegistryRuntimeStatus.UNAVAILABLE,
            failure_reason_code='unsupported_schema',
            last_verified_at=now,
            store_backend=config.backend,
            store_health=True,
            schema_version=schema,
            activation_enabled=True,
        )

    # Check active release
    active = _load_active_release(config)
    if not active:
        return RegistryRuntimeInfo(
            status=RegistryRuntimeStatus.UNAVAILABLE,
            failure_reason_code='no_active_release',
            last_verified_at=now,
            store_backend=config.backend,
            store_health=True,
            schema_version=schema,
            activation_enabled=True,
        )

    if active.get('validation_error'):
        return RegistryRuntimeInfo(
            status=RegistryRuntimeStatus.UNAVAILABLE,
            failure_reason_code=active['validation_error'],
            last_verified_at=now,
            store_backend=config.backend,
            store_health=True,
            schema_version=schema,
            activation_enabled=True,
        )

    if not active.get('family_complete'):
        return RegistryRuntimeInfo(
            status=RegistryRuntimeStatus.INCOMPLETE,
            release_id=active.get('manifest_id'),
            framework=active.get('framework'),
            family_completeness=active.get('family_completeness'),
            last_verified_at=now,
            store_backend=config.backend,
            store_health=True,
            schema_version=schema,
            activation_enabled=True,
        )

    return RegistryRuntimeInfo(
        status=RegistryRuntimeStatus.READY,
        release_id=active.get('manifest_id'),
        framework=active.get('framework'),
        family_completeness=active.get('family_completeness'),
        last_verified_at=now,
        store_backend=config.backend,
        store_health=True,
        schema_version=schema,
        activation_enabled=True,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _probe_health(
    config: RegistryStoreConfig,
    max_attempts: int,
    connect_timeout_sec: int,
    backoff_sec: float,
) -> dict[str, Any]:
    """Bounded health probe with retry. No credentials in output."""
    import psycopg

    for attempt in range(max_attempts):
        try:
            conn = psycopg.connect(
                config.database_url,
                connect_timeout=connect_timeout_sec,
                autocommit=True,
            )
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    if cur.fetchone() != (1,):
                        return {'healthy': False, 'reason': 'health_check_failed'}
                    # Get schema version
                    try:
                        cur.execute(
                            "SELECT version FROM schema_migrations "
                            "ORDER BY applied_at DESC LIMIT 1"
                        )
                        row = cur.fetchone()
                        schema = row[0] if row else None
                    except Exception:
                        schema = None
                return {'healthy': True, 'schema_version': schema}
            finally:
                conn.close()
        except psycopg.OperationalError:
            if attempt < max_attempts - 1:
                time.sleep(min(backoff_sec * (2 ** attempt), 10.0))
        except Exception:
            return {'healthy': False, 'reason': 'unexpected_error'}
    return {'healthy': False, 'reason': 'connection_failed'}


def _load_active_release(config: RegistryStoreConfig) -> dict[str, Any] | None:
    """Load and validate the active release. No credentials in output."""
    import psycopg

    try:
        conn = psycopg.connect(
            config.database_url,
            connect_timeout=STARTUP_CONNECT_TIMEOUT_SEC,
            autocommit=True,
        )
    except Exception:
        return None

    try:
        with conn.cursor() as cur:
            # Find any active release (check all frameworks)
            cur.execute(
                "SELECT framework, manifest_id, activated_at "
                "FROM active_releases LIMIT 1"
            )
            ar_row = cur.fetchone()
            if not ar_row:
                return None

            framework = ar_row[0]
            manifest_id = ar_row[1]

            # Get manifest
            cur.execute(
                "SELECT status, manifest_hash, release_version "
                "FROM release_manifests WHERE manifest_id = %s",
                (manifest_id,),
            )
            mr = cur.fetchone()
            if not mr:
                return {'validation_error': 'missing_release'}
            if mr[0] != 'active':
                return {'validation_error': 'release_not_active'}

            # Check release-level approval
            cur.execute(
                "SELECT 1 FROM release_approval_artifacts "
                "WHERE manifest_id = %s AND approval_decision = 'approved' LIMIT 1",
                (manifest_id,),
            )
            if not cur.fetchone():
                return {'validation_error': 'missing_release_approval'}

            # Verify entry hashes
            cur.execute(
                "SELECT me.entry_id, me.content_hash, e.content_hash, e.lifecycle_state "
                "FROM release_manifest_entries me "
                "JOIN registry_entries e ON me.entry_id = e.entry_id "
                "WHERE me.manifest_id = %s",
                (manifest_id,),
            )
            entries = cur.fetchall()
            for e in entries:
                if e[1] != e[2]:
                    return {'validation_error': 'entry_hash_mismatch'}
                if e[3] != 'approved':
                    return {'validation_error': 'entry_not_approved'}

            # Check family completeness
            cur.execute(
                "SELECT DISTINCT registry_family FROM release_manifest_entries "
                "WHERE manifest_id = %s",
                (manifest_id,),
            )
            families = {r[0] for r in cur.fetchall()}

            # Determine which standard
            from registry_release_service import FRAMEWORK_FAMILIES
            family_status = {}
            family_complete = False
            for std, required in FRAMEWORK_FAMILIES.items():
                if families & required:
                    completeness = {f: f in families for f in required}
                    family_status[std] = completeness
                    if families >= required:
                        family_complete = True

        return {
            'manifest_id': manifest_id,
            'framework': framework,
            'family_complete': family_complete,
            'family_completeness': family_status,
        }
    except Exception:
        return {'validation_error': 'unexpected_error'}
    finally:
        conn.close()
