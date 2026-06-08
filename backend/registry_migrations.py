"""Phase 8 P8-A — Registry schema migrations.

Reviewed DDL for the governed clinical registry store. Uses PostgreSQL
with parameterized SQL for runtime mutations; migration DDL is static
reviewed SQL applied through the registry store.

Schema tables:
- schema_migrations     — migration version tracking
- registry_sources      — approved reference data sources
- registry_entries      — governed registry entries (metadata only)
- entry_provenance      — provenance chain for each entry
- review_queue          — clinical review queue (P8-B placeholder)
- approval_artifacts    — non-repudiable approval records (P8-B placeholder)
- release_manifests     — governed release manifests
- release_manifest_entries — entries within each release manifest
- active_releases       — current active release pointers
- release_history       — historical release activations and rollbacks

Design decisions:
- Content hashes use SHA-256 stored as text for portability.
- No registry body text is stored in schema metadata columns.
- Lifecycle states use CHECK constraints, not enums (simpler migration).
- All tables have explicit primary keys and foreign keys.
- Timestamps default to CURRENT_TIMESTAMP (UTC).
- No activation logic is implemented; tables exist for future phases.
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Migration registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Migration:
    """A single schema migration."""
    version: str
    description: str
    sql: str


# V001: Bootstrap schema_migrations table
MIGRATION_V001_BOOTSTRAP = Migration(
    version='V001',
    description='Create schema_migrations table',
    sql="""\
CREATE TABLE IF NOT EXISTS schema_migrations (
    version       VARCHAR(32) PRIMARY KEY,
    description   VARCHAR(256) NOT NULL DEFAULT '',
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""",
)

# V002: Core registry tables
MIGRATION_V002_CORE_TABLES = Migration(
    version='V002',
    description='Create core registry tables: sources, entries, provenance',
    sql="""\
-- Approved reference data sources
CREATE TABLE IF NOT EXISTS registry_sources (
    source_id       VARCHAR(64) PRIMARY KEY,
    framework       VARCHAR(16) NOT NULL,
    source_title    VARCHAR(256) NOT NULL,
    source_version  VARCHAR(64) NOT NULL DEFAULT '',
    source_hash     VARCHAR(128) NOT NULL DEFAULT '',
    license_status  VARCHAR(32) NOT NULL DEFAULT 'unknown'
        CHECK (license_status IN ('unknown', 'pending_review', 'approved', 'rejected', 'expired')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Governed registry entries (metadata only — no clinical body text)
CREATE TABLE IF NOT EXISTS registry_entries (
    entry_id        VARCHAR(64) PRIMARY KEY,
    source_id       VARCHAR(64) NOT NULL REFERENCES registry_sources(source_id),
    framework       VARCHAR(16) NOT NULL,
    registry_family VARCHAR(16) NOT NULL
        CHECK (registry_family IN ('SDKI', 'SLKI', 'SIKI', 'NANDA', 'NOC', 'NIC')),
    entry_code      VARCHAR(32) NOT NULL,
    entry_name      VARCHAR(256) NOT NULL DEFAULT '',
    content_hash    VARCHAR(128) NOT NULL,
    lifecycle_state VARCHAR(32) NOT NULL DEFAULT 'quarantined'
        CHECK (lifecycle_state IN ('quarantined', 'pending_review', 'approved', 'rejected', 'deprecated')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (framework, registry_family, entry_code, content_hash)
);

-- Provenance chain for each entry
CREATE TABLE IF NOT EXISTS entry_provenance (
    provenance_id   SERIAL PRIMARY KEY,
    entry_id        VARCHAR(64) NOT NULL REFERENCES registry_entries(entry_id),
    extraction_method VARCHAR(32) NOT NULL DEFAULT 'unknown'
        CHECK (extraction_method IN ('unknown', 'manual', 'ocr', 'llm_assisted', 'api_import', 'hybrid')),
    extraction_tool VARCHAR(128) NOT NULL DEFAULT '',
    extraction_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewer        VARCHAR(128) NOT NULL DEFAULT '',
    review_date     TIMESTAMPTZ,
    notes           VARCHAR(512) NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""",
)

# V003: Review and approval tables (P8-B placeholder schema)
MIGRATION_V003_REVIEW_APPROVAL = Migration(
    version='V003',
    description='Create review queue and approval artifact tables (P8-B placeholder)',
    sql="""\
-- Clinical review queue
CREATE TABLE IF NOT EXISTS review_queue (
    review_id       VARCHAR(64) PRIMARY KEY,
    entry_id        VARCHAR(64) NOT NULL REFERENCES registry_entries(entry_id),
    reviewer_id     VARCHAR(128) NOT NULL DEFAULT '',
    review_status   VARCHAR(32) NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'in_review', 'approved', 'rejected', 'deferred')),
    review_scope    VARCHAR(128) NOT NULL DEFAULT '',
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at     TIMESTAMPTZ,
    notes           VARCHAR(512) NOT NULL DEFAULT ''
);

-- Non-repudiable approval artifacts
CREATE TABLE IF NOT EXISTS approval_artifacts (
    approval_id     VARCHAR(64) PRIMARY KEY,
    review_id       VARCHAR(64) NOT NULL REFERENCES review_queue(review_id),
    entry_id        VARCHAR(64) NOT NULL REFERENCES registry_entries(entry_id),
    approver_id     VARCHAR(128) NOT NULL,
    approval_decision VARCHAR(32) NOT NULL
        CHECK (approval_decision IN ('approved', 'rejected', 'conditional')),
    content_hash_at_approval VARCHAR(128) NOT NULL,
    approved_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rationale       VARCHAR(512) NOT NULL DEFAULT ''
);
""",
)

# V004: Release management tables
MIGRATION_V004_RELEASE_TABLES = Migration(
    version='V004',
    description='Create release manifest, active release, and history tables',
    sql="""\
-- Governed release manifests
CREATE TABLE IF NOT EXISTS release_manifests (
    manifest_id     VARCHAR(64) PRIMARY KEY,
    framework       VARCHAR(16) NOT NULL,
    release_version VARCHAR(64) NOT NULL,
    manifest_hash   VARCHAR(128) NOT NULL DEFAULT '',
    status          VARCHAR(32) NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'validated', 'active', 'deprecated', 'rolled_back')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activated_at    TIMESTAMPTZ,
    deprecated_at   TIMESTAMPTZ,
    UNIQUE (framework, release_version)
);

-- Entries within each release manifest
CREATE TABLE IF NOT EXISTS release_manifest_entries (
    id              SERIAL PRIMARY KEY,
    manifest_id     VARCHAR(64) NOT NULL REFERENCES release_manifests(manifest_id),
    entry_id        VARCHAR(64) NOT NULL REFERENCES registry_entries(entry_id),
    registry_family VARCHAR(16) NOT NULL
        CHECK (registry_family IN ('SDKI', 'SLKI', 'SIKI', 'NANDA', 'NOC', 'NIC')),
    content_hash    VARCHAR(128) NOT NULL,
    UNIQUE (manifest_id, entry_id)
);

-- Current active release pointers
CREATE TABLE IF NOT EXISTS active_releases (
    framework       VARCHAR(16) PRIMARY KEY,
    manifest_id     VARCHAR(64) NOT NULL REFERENCES release_manifests(manifest_id),
    activated_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Historical release activations and rollbacks
CREATE TABLE IF NOT EXISTS release_history (
    id              SERIAL PRIMARY KEY,
    framework       VARCHAR(16) NOT NULL,
    manifest_id     VARCHAR(64) NOT NULL REFERENCES release_manifests(manifest_id),
    action          VARCHAR(32) NOT NULL
        CHECK (action IN ('activated', 'rolled_back', 'deprecated')),
    performed_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    performed_by    VARCHAR(128) NOT NULL DEFAULT 'system',
    notes           VARCHAR(512) NOT NULL DEFAULT ''
);
""",
)

# ---------------------------------------------------------------------------
# Ordered migration list
# ---------------------------------------------------------------------------

ALL_MIGRATIONS: tuple[Migration, ...] = (
    MIGRATION_V001_BOOTSTRAP,
    MIGRATION_V002_CORE_TABLES,
    MIGRATION_V003_REVIEW_APPROVAL,
    MIGRATION_V004_RELEASE_TABLES,
)


def run_migrations(store) -> list[str]:
    """Run all pending migrations. Returns list of applied versions.

    The store must support:
    - execute_migration(version, description, sql) -> bool
    - schema_version() -> str | None
    """
    import psycopg

    # Ensure schema_migrations table exists first
    conn = store._get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_V001_BOOTSTRAP.sql)
            cur.execute(
                "INSERT INTO schema_migrations (version, description) "
                "VALUES (%s, %s) ON CONFLICT (version) DO NOTHING",
                (MIGRATION_V001_BOOTSTRAP.version, MIGRATION_V001_BOOTSTRAP.description),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    # Check which migrations are already applied
    applied: set[str] = set()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM schema_migrations")
            applied = {row[0] for row in cur.fetchall()}
    except Exception:
        pass

    # Apply pending migrations in order
    newly_applied: list[str] = []
    for migration in ALL_MIGRATIONS:
        if migration.version in applied:
            continue
        store.execute_migration(
            migration.version,
            migration.description,
            migration.sql,
        )
        newly_applied.append(migration.version)

    return newly_applied
