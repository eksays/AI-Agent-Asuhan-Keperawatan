"""Phase 8 P8-A — Durable PostgreSQL registry-store foundation.

This module provides a protocol-based registry store abstraction and a
PostgreSQL implementation using Psycopg 3. It does NOT activate registry
grounding, import real registry bodies, or change normal care-plan behavior.

Design decisions:
- Standard PostgreSQL interfaces only; no Neon-specific SDKs.
- Parameterized SQL for all runtime mutations.
- Explicit transactions with rollback on failure.
- Bounded cold-start retry with exponential backoff.
- Safe redacted connection diagnostics (never log credentials).
- Registry activation is always disabled in P8-A.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Safe connection-string redaction
# ---------------------------------------------------------------------------

_CREDENTIAL_RE = re.compile(
    r'(://[^:]+:)[^@]+(@)',
    re.IGNORECASE,
)


def redact_connection_string(url: str) -> str:
    """Replace password in a PostgreSQL URL with [REDACTED]."""
    if not url:
        return ''
    return _CREDENTIAL_RE.sub(r'\1[REDACTED]\2', url)


def redact_hostname(url: str) -> str:
    """Replace hostname in a PostgreSQL URL with [HOST]."""
    if not url:
        return ''
    redacted = redact_connection_string(url)
    return re.sub(r'@[^/]+', '@[HOST]', redacted)


# ---------------------------------------------------------------------------
# Registry store configuration
# ---------------------------------------------------------------------------

VALID_BACKENDS = {'disabled', 'postgres'}
VALID_RUNTIME_MODES = {'synthetic_governance_test', 'controlled_pilot', 'production'}


@dataclass(frozen=True)
class RegistryStoreConfig:
    """Validated registry store configuration."""
    backend: str = 'disabled'
    database_url: str = ''
    admin_url: str = ''
    runtime_mode: str = 'synthetic_governance_test'
    activation_enabled: bool = False
    connect_timeout_sec: int = 15
    max_retries: int = 3
    retry_backoff_ms: int = 750

    @property
    def is_enabled(self) -> bool:
        return self.backend == 'postgres' and bool(self.database_url)

    @property
    def safe_diagnostic(self) -> dict[str, Any]:
        """Return safe diagnostic info without credentials."""
        return {
            'backend': self.backend,
            'has_database_url': bool(self.database_url),
            'has_admin_url': bool(self.admin_url),
            'runtime_mode': self.runtime_mode,
            'activation_enabled': self.activation_enabled,
            'connect_timeout_sec': self.connect_timeout_sec,
            'max_retries': self.max_retries,
        }


class RegistryStoreConfigError(ValueError):
    """Safe configuration error. Never include credentials."""


def load_registry_store_config(
    backend: str = 'disabled',
    database_url: str = '',
    admin_url: str = '',
    runtime_mode: str = 'synthetic_governance_test',
    activation_enabled: bool = False,
    connect_timeout_sec: int = 15,
    max_retries: int = 3,
    retry_backoff_ms: int = 750,
) -> RegistryStoreConfig:
    """Validate and return a RegistryStoreConfig."""
    backend = (backend or 'disabled').strip().lower()
    if backend not in VALID_BACKENDS:
        raise RegistryStoreConfigError(
            f'Unsupported REGISTRY_STORE_BACKEND: {backend!r}. '
            f'Valid values: {", ".join(sorted(VALID_BACKENDS))}.'
        )
    if backend == 'postgres' and not database_url:
        raise RegistryStoreConfigError(
            'REGISTRY_DATABASE_URL is required when REGISTRY_STORE_BACKEND=postgres.'
        )
    runtime_mode = (runtime_mode or 'synthetic_governance_test').strip().lower()
    if runtime_mode not in VALID_RUNTIME_MODES:
        raise RegistryStoreConfigError(
            f'Unsupported REGISTRY_RUNTIME_MODE: {runtime_mode!r}.'
        )
    connect_timeout_sec = max(1, min(connect_timeout_sec, 60))
    max_retries = max(0, min(max_retries, 10))
    retry_backoff_ms = max(100, min(retry_backoff_ms, 10_000))

    return RegistryStoreConfig(
        backend=backend,
        database_url=database_url,
        admin_url=admin_url,
        runtime_mode=runtime_mode,
        activation_enabled=bool(activation_enabled),
        connect_timeout_sec=connect_timeout_sec,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
    )


# ---------------------------------------------------------------------------
# Registry store protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class RegistryStore(Protocol):
    """Protocol for durable registry stores."""

    def is_healthy(self) -> bool:
        """Return True if the store is reachable and schema is initialized."""
        ...

    def schema_version(self) -> str | None:
        """Return the current schema version, or None if not initialized."""
        ...

    def close(self) -> None:
        """Release resources."""
        ...


# ---------------------------------------------------------------------------
# PostgreSQL implementation
# ---------------------------------------------------------------------------

class PostgresRegistryStore:
    """Psycopg 3 PostgreSQL registry store with bounded retry and safe logging."""

    def __init__(self, config: RegistryStoreConfig) -> None:
        if config.backend != 'postgres':
            raise RegistryStoreConfigError('PostgresRegistryStore requires backend=postgres.')
        self._config = config
        self._conn = None

    def _connect(self):
        """Establish a connection with bounded retry and backoff."""
        import psycopg
        last_error: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                conn = psycopg.connect(
                    self._config.database_url,
                    connect_timeout=self._config.connect_timeout_sec,
                    autocommit=False,
                )
                return conn
            except psycopg.OperationalError as exc:
                last_error = exc
                if attempt < self._config.max_retries:
                    backoff_sec = (self._config.retry_backoff_ms / 1000) * (2 ** attempt)
                    time.sleep(min(backoff_sec, 30.0))
        raise RegistryStoreConfigError(
            f'Failed to connect after {self._config.max_retries + 1} attempts. '
            f'Backend: postgres. URL provided: yes. '
            f'Last error type: {type(last_error).__name__}.'
        )

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = self._connect()
        return self._conn

    def is_healthy(self) -> bool:
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone() == (1,)
        except Exception:
            return False

    def schema_version(self) -> str | None:
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT version FROM schema_migrations "
                    "ORDER BY applied_at DESC LIMIT 1"
                )
                row = cur.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    def execute_migration(self, version: str, description: str, sql: str) -> bool:
        """Execute a migration DDL within a transaction."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations (version, description) "
                    "VALUES (%s, %s) ON CONFLICT (version) DO NOTHING",
                    (version, description),
                )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None

    @property
    def safe_diagnostic(self) -> dict[str, Any]:
        return {
            **self._config.safe_diagnostic,
            'connected': self._conn is not None and not getattr(self._conn, 'closed', True),
        }


# ---------------------------------------------------------------------------
# Disabled store (default)
# ---------------------------------------------------------------------------

class DisabledRegistryStore:
    """No-op store for when registry storage is disabled."""

    def is_healthy(self) -> bool:
        return False

    def schema_version(self) -> str | None:
        return None

    def close(self) -> None:
        pass

    @property
    def safe_diagnostic(self) -> dict[str, Any]:
        return {'backend': 'disabled', 'activation_enabled': False}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_registry_store(config: RegistryStoreConfig) -> PostgresRegistryStore | DisabledRegistryStore:
    """Create the appropriate registry store from configuration."""
    if config.backend == 'disabled' or not config.is_enabled:
        return DisabledRegistryStore()
    return PostgresRegistryStore(config)
