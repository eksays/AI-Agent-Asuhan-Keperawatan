"""Phase 9 P9-A - Governed RAG corpus foundation migrations.

This module is intentionally separate from registry_migrations.py. P9-A creates
default-off corpus foundation tables only; it does not ingest real corpus bodies,
activate retrieval, install extensions at API startup, or integrate embeddings.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass


RAG_ADVISORY_LOCK_ID = 907_090_001


class RagMigrationError(RuntimeError):
    """Safe migration error. Never include credentials or raw database details."""


@dataclass(frozen=True)
class RagMigration:
    migration_id: str
    migration_name: str
    sql: str
    requires_pgvector: bool = False

    @property
    def checksum(self) -> str:
        normalized = "\n".join(line.rstrip() for line in self.sql.strip().splitlines())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


MIGRATION_RAG_CORE_V001 = RagMigration(
    migration_id="RAG_CORE_V001",
    migration_name="create rag schema migration journal",
    sql="""\
CREATE TABLE IF NOT EXISTS rag_schema_migrations (
    migration_id       VARCHAR(64) PRIMARY KEY,
    migration_name     VARCHAR(256) NOT NULL,
    migration_checksum CHAR(64) NOT NULL,
    applied_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""",
)


MIGRATION_RAG_CORE_V002 = RagMigration(
    migration_id="RAG_CORE_V002",
    migration_name="create governed rag corpus core tables",
    sql="""\
CREATE TABLE IF NOT EXISTS rag_sources (
    source_id         VARCHAR(96) PRIMARY KEY,
    source_type       VARCHAR(32) NOT NULL DEFAULT 'synthetic_fixture'
        CHECK (source_type IN ('synthetic_fixture', 'reference_corpus', 'open_access_reference')),
    source_title      VARCHAR(256) NOT NULL DEFAULT '',
    source_owner      VARCHAR(128) NOT NULL DEFAULT '',
    source_hash       CHAR(64) NOT NULL DEFAULT repeat('0', 64),
    license_status    VARCHAR(32) NOT NULL DEFAULT 'unknown'
        CHECK (license_status IN ('unknown', 'pending_review', 'approved', 'rejected', 'expired')),
    governance_status VARCHAR(32) NOT NULL DEFAULT 'proposed'
        CHECK (governance_status IN ('proposed', 'license_review', 'approved', 'rejected', 'deprecated', 'quarantined')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rag_source_versions (
    source_version_id VARCHAR(96) PRIMARY KEY,
    source_id         VARCHAR(96) NOT NULL REFERENCES rag_sources(source_id),
    version_label     VARCHAR(128) NOT NULL DEFAULT '',
    version_hash      CHAR(64) NOT NULL,
    approval_status   VARCHAR(32) NOT NULL DEFAULT 'draft'
        CHECK (approval_status IN ('draft', 'verified', 'approved', 'rejected', 'superseded', 'quarantined')),
    license_status    VARCHAR(32) NOT NULL DEFAULT 'unknown'
        CHECK (license_status IN ('unknown', 'pending_review', 'approved', 'rejected', 'expired')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at       TIMESTAMPTZ,
    UNIQUE (source_id, version_label, version_hash)
);

CREATE TABLE IF NOT EXISTS rag_ingestion_runs (
    ingestion_run_id VARCHAR(96) PRIMARY KEY,
    source_version_id VARCHAR(96) REFERENCES rag_source_versions(source_version_id),
    runtime_mode     VARCHAR(32) NOT NULL DEFAULT 'synthetic_corpus_test'
        CHECK (runtime_mode IN ('synthetic_corpus_test')),
    corpus_kind      VARCHAR(32) NOT NULL DEFAULT 'synthetic_only'
        CHECK (corpus_kind IN ('synthetic_only')),
    dry_run          BOOLEAN NOT NULL DEFAULT TRUE,
    run_status       VARCHAR(32) NOT NULL DEFAULT 'pending'
        CHECK (run_status IN ('pending', 'running', 'succeeded', 'failed', 'rejected')),
    operator_id      VARCHAR(128) NOT NULL DEFAULT '',
    documents_seen   INTEGER NOT NULL DEFAULT 0 CHECK (documents_seen >= 0),
    chunks_seen      INTEGER NOT NULL DEFAULT 0 CHECK (chunks_seen >= 0),
    safe_error_code  VARCHAR(64) NOT NULL DEFAULT '',
    started_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at     TIMESTAMPTZ
);
""",
)


MIGRATION_RAG_CORE_V003 = RagMigration(
    migration_id="RAG_CORE_V003",
    migration_name="create rag staging tables with ttl cleanup metadata",
    sql="""\
CREATE TABLE IF NOT EXISTS rag_ingestion_staging_documents (
    staging_document_id VARCHAR(96) PRIMARY KEY,
    ingestion_run_id    VARCHAR(96) NOT NULL REFERENCES rag_ingestion_runs(ingestion_run_id),
    source_version_id   VARCHAR(96) NOT NULL REFERENCES rag_source_versions(source_version_id),
    document_hash       CHAR(64) NOT NULL,
    document_title      VARCHAR(256) NOT NULL DEFAULT '',
    lifecycle_state     VARCHAR(32) NOT NULL DEFAULT 'staged'
        CHECK (lifecycle_state IN ('staged', 'quarantined', 'rejected', 'expired', 'promoted')),
    searchable          BOOLEAN NOT NULL DEFAULT FALSE CHECK (searchable = FALSE),
    expires_at          TIMESTAMPTZ NOT NULL,
    cleanup_after       TIMESTAMPTZ NOT NULL,
    cleanup_status      VARCHAR(32) NOT NULL DEFAULT 'pending'
        CHECK (cleanup_status IN ('pending', 'cleaned', 'expired', 'failed')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (ingestion_run_id, document_hash)
);

CREATE TABLE IF NOT EXISTS rag_ingestion_staging_chunks (
    staging_chunk_id    VARCHAR(96) PRIMARY KEY,
    staging_document_id VARCHAR(96) NOT NULL REFERENCES rag_ingestion_staging_documents(staging_document_id) ON DELETE CASCADE,
    chunk_hash          CHAR(64) NOT NULL,
    chunk_ordinal       INTEGER NOT NULL CHECK (chunk_ordinal >= 0),
    section_label       VARCHAR(160) NOT NULL DEFAULT '',
    token_count         INTEGER NOT NULL DEFAULT 0 CHECK (token_count >= 0),
    chunk_text          TEXT NOT NULL DEFAULT '',
    searchable          BOOLEAN NOT NULL DEFAULT FALSE CHECK (searchable = FALSE),
    expires_at          TIMESTAMPTZ NOT NULL,
    cleanup_after       TIMESTAMPTZ NOT NULL,
    cleanup_status      VARCHAR(32) NOT NULL DEFAULT 'pending'
        CHECK (cleanup_status IN ('pending', 'cleaned', 'expired', 'failed')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (staging_document_id, chunk_hash)
);

CREATE INDEX IF NOT EXISTS idx_rag_staging_documents_cleanup
    ON rag_ingestion_staging_documents (cleanup_status, cleanup_after);
CREATE INDEX IF NOT EXISTS idx_rag_staging_chunks_cleanup
    ON rag_ingestion_staging_chunks (cleanup_status, cleanup_after);
""",
)


MIGRATION_RAG_CORE_V004 = RagMigration(
    migration_id="RAG_CORE_V004",
    migration_name="create retrieval eligible documents and lexical chunks",
    sql="""\
CREATE TABLE IF NOT EXISTS rag_documents (
    document_id       VARCHAR(96) PRIMARY KEY,
    source_version_id VARCHAR(96) NOT NULL REFERENCES rag_source_versions(source_version_id),
    document_hash     CHAR(64) NOT NULL,
    document_title    VARCHAR(256) NOT NULL DEFAULT '',
    language          VARCHAR(16) NOT NULL DEFAULT 'id',
    document_type     VARCHAR(32) NOT NULL DEFAULT 'synthetic_fixture'
        CHECK (document_type IN ('synthetic_fixture', 'reference_document')),
    lifecycle_state   VARCHAR(32) NOT NULL DEFAULT 'quarantined'
        CHECK (lifecycle_state IN ('approved', 'deprecated', 'quarantined')),
    approval_status   VARCHAR(32) NOT NULL DEFAULT 'draft'
        CHECK (approval_status IN ('draft', 'approved', 'rejected', 'superseded')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_version_id, document_hash)
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id           VARCHAR(96) PRIMARY KEY,
    document_id        VARCHAR(96) NOT NULL REFERENCES rag_documents(document_id),
    chunk_hash         CHAR(64) NOT NULL,
    chunk_ordinal      INTEGER NOT NULL CHECK (chunk_ordinal >= 0),
    chunk_text         TEXT NOT NULL,
    search_vector      TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', coalesce(chunk_text, ''))) STORED,
    page_label         VARCHAR(64) NOT NULL DEFAULT '',
    section_label      VARCHAR(160) NOT NULL DEFAULT '',
    metadata           JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    lifecycle_state    VARCHAR(32) NOT NULL DEFAULT 'quarantined'
        CHECK (lifecycle_state IN ('approved', 'deprecated', 'quarantined')),
    retrieval_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (document_id, chunk_hash)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_document_id ON rag_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_fts ON rag_chunks USING GIN (search_vector)
    WHERE retrieval_eligible = TRUE AND lifecycle_state = 'approved';
""",
)


MIGRATION_RAG_CORE_V005 = RagMigration(
    migration_id="RAG_CORE_V005",
    migration_name="create rag index release metadata tables",
    sql="""\
CREATE TABLE IF NOT EXISTS rag_index_release_manifests (
    release_id      VARCHAR(96) PRIMARY KEY,
    release_version VARCHAR(128) NOT NULL,
    release_hash    CHAR(64) NOT NULL,
    release_status  VARCHAR(32) NOT NULL DEFAULT 'candidate'
        CHECK (release_status IN ('candidate', 'validated', 'approved', 'active', 'superseded', 'deprecated', 'rolled_back')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at     TIMESTAMPTZ,
    UNIQUE (release_version)
);

CREATE TABLE IF NOT EXISTS rag_index_release_manifest_chunks (
    release_id  VARCHAR(96) NOT NULL REFERENCES rag_index_release_manifests(release_id),
    chunk_id    VARCHAR(96) NOT NULL REFERENCES rag_chunks(chunk_id),
    chunk_hash  CHAR(64) NOT NULL,
    chunk_rank  INTEGER NOT NULL DEFAULT 0 CHECK (chunk_rank >= 0),
    PRIMARY KEY (release_id, chunk_id),
    UNIQUE (release_id, chunk_rank)
);

CREATE TABLE IF NOT EXISTS rag_active_index_release (
    pointer_name VARCHAR(64) PRIMARY KEY,
    release_id   VARCHAR(96) NOT NULL REFERENCES rag_index_release_manifests(release_id),
    activated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rag_index_release_history (
    history_id   SERIAL PRIMARY KEY,
    release_id   VARCHAR(96) REFERENCES rag_index_release_manifests(release_id),
    action       VARCHAR(32) NOT NULL CHECK (action IN ('activated', 'rolled_back', 'deprecated')),
    performed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    performed_by VARCHAR(128) NOT NULL DEFAULT '',
    safe_notes   VARCHAR(256) NOT NULL DEFAULT ''
);
""",
)


MIGRATION_RAG_CORE_V006 = RagMigration(
    migration_id="RAG_CORE_V006",
    migration_name="create bounded metadata only rag retrieval telemetry",
    sql="""\
CREATE TABLE IF NOT EXISTS rag_retrieval_events (
    event_id             VARCHAR(96) PRIMARY KEY,
    release_id           VARCHAR(96) REFERENCES rag_index_release_manifests(release_id),
    event_type           VARCHAR(32) NOT NULL CHECK (event_type IN ('retrieved', 'abstained', 'error')),
    retrieval_backend    VARCHAR(32) NOT NULL CHECK (retrieval_backend IN ('none', 'lexical', 'vector', 'hybrid')),
    filter_policy        VARCHAR(64) NOT NULL DEFAULT '',
    result_count         INTEGER NOT NULL DEFAULT 0 CHECK (result_count >= 0 AND result_count <= 50),
    selected_chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (selected_chunk_count >= 0 AND selected_chunk_count <= 20),
    selected_chunk_ids   VARCHAR(4096) NOT NULL DEFAULT '' CHECK (char_length(selected_chunk_ids) <= 4096),
    abstention_reason    VARCHAR(96) NOT NULL DEFAULT '',
    safe_metadata        JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(safe_metadata) = 'object'),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""",
)


MIGRATION_RAG_VECTOR_V001 = RagMigration(
    migration_id="RAG_VECTOR_V001",
    migration_name="install pgvector extension explicitly",
    requires_pgvector=True,
    sql="""\
CREATE EXTENSION IF NOT EXISTS vector;
""",
)


MIGRATION_RAG_VECTOR_V002 = RagMigration(
    migration_id="RAG_VECTOR_V002",
    migration_name="create optional rag chunk embedding table",
    requires_pgvector=True,
    sql="""\
CREATE TABLE IF NOT EXISTS rag_chunk_embeddings (
    embedding_id        VARCHAR(96) PRIMARY KEY,
    chunk_id            VARCHAR(96) NOT NULL REFERENCES rag_chunks(chunk_id) ON DELETE CASCADE,
    embedding_model_id  VARCHAR(128) NOT NULL,
    embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension > 0 AND embedding_dimension <= 4096),
    embedding_hash      CHAR(64) NOT NULL,
    embedding           vector,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (chunk_id, embedding_model_id, embedding_hash)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunk_embeddings_chunk_id
    ON rag_chunk_embeddings(chunk_id);
""",
)


CORE_MIGRATIONS: tuple[RagMigration, ...] = (
    MIGRATION_RAG_CORE_V001,
    MIGRATION_RAG_CORE_V002,
    MIGRATION_RAG_CORE_V003,
    MIGRATION_RAG_CORE_V004,
    MIGRATION_RAG_CORE_V005,
    MIGRATION_RAG_CORE_V006,
)

PGVECTOR_MIGRATIONS: tuple[RagMigration, ...] = (
    MIGRATION_RAG_VECTOR_V001,
    MIGRATION_RAG_VECTOR_V002,
)


def acquire_advisory_lock(conn, timeout_sec: float = 5.0, poll_interval_sec: float = 0.25) -> bool:
    """Acquire a bounded PostgreSQL advisory lock for explicit migrations."""
    deadline = time.monotonic() + max(0.0, timeout_sec)
    while True:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (RAG_ADVISORY_LOCK_ID,))
            row = cur.fetchone()
            if row and row[0]:
                return True
        if time.monotonic() >= deadline:
            raise RagMigrationError("RAG migration lock is already held.")
        time.sleep(max(0.05, poll_interval_sec))


def release_advisory_lock(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s)", (RAG_ADVISORY_LOCK_ID,))


def pgvector_available(conn) -> bool:
    """Read-only extension availability probe."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')"
        )
        row = cur.fetchone()
    return bool(row and row[0])


def pgvector_installed(conn) -> tuple[bool, bool]:
    """Return safe booleans: installed and version-present."""
    with conn.cursor() as cur:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        row = cur.fetchone()
    return bool(row), bool(row and row[0])


def _ensure_journal(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(MIGRATION_RAG_CORE_V001.sql)
    conn.commit()


def _applied_migrations(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT migration_id, migration_checksum FROM rag_schema_migrations")
        return {row[0]: row[1] for row in cur.fetchall()}


def _verify_applied_checksums(applied: dict[str, str], migrations: tuple[RagMigration, ...]) -> None:
    known = {migration.migration_id: migration for migration in (*CORE_MIGRATIONS, *PGVECTOR_MIGRATIONS)}
    for migration_id, checksum in applied.items():
        migration = known.get(migration_id)
        if migration and checksum != migration.checksum:
            raise RagMigrationError("Applied RAG migration checksum mismatch.")
    for migration in migrations:
        checksum = applied.get(migration.migration_id)
        if checksum and checksum != migration.checksum:
            raise RagMigrationError("Applied RAG migration checksum mismatch.")


def run_migrations(conn, *, include_pgvector: bool = False) -> list[str]:
    """Run pending RAG migrations. Caller owns explicit CLI/operator gating."""
    _ensure_journal(conn)
    migrations = CORE_MIGRATIONS + (PGVECTOR_MIGRATIONS if include_pgvector else ())
    applied = _applied_migrations(conn)
    _verify_applied_checksums(applied, migrations)

    newly_applied: list[str] = []
    for migration in migrations:
        if migration.migration_id in applied:
            continue
        try:
            with conn.cursor() as cur:
                cur.execute(migration.sql)
                cur.execute(
                    "INSERT INTO rag_schema_migrations "
                    "(migration_id, migration_name, migration_checksum) VALUES (%s, %s, %s)",
                    (migration.migration_id, migration.migration_name, migration.checksum),
                )
            conn.commit()
            newly_applied.append(migration.migration_id)
        except Exception as exc:
            conn.rollback()
            raise RagMigrationError("RAG migration failed safely.") from exc
    return newly_applied
