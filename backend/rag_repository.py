from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from psycopg import sql
from psycopg.types.json import Jsonb

from rag_migrations import run_migrations


ACTIVE_POINTER_NAME = 'synthetic_p9b'


@dataclass(frozen=True)
class SyntheticCounts:
    synthetic_rows: int
    temporary_staging_rows: int
    active_synthetic_pointers: int
    real_corpus_rows: int


def ensure_core_schema(conn) -> list[str]:
    return run_migrations(conn, include_pgvector=False)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class RagRepository:
    def __init__(self, conn):
        self.conn = conn

    def table_exists(self, table_name: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute('SELECT to_regclass(%s)', (table_name,))
            row = cur.fetchone()
        return bool(row and row[0])

    def create_source_version(self, *, source_id: str, source_version_id: str, title: str, version_hash: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_sources "
                "(source_id, source_type, source_title, source_owner, source_hash, license_status, governance_status) "
                "VALUES (%s, 'synthetic_fixture', %s, 'synthetic', %s, 'approved', 'approved')",
                (source_id, title[:256], version_hash),
            )
            cur.execute(
                "INSERT INTO rag_source_versions "
                "(source_version_id, source_id, version_label, version_hash, approval_status, license_status, approved_at) "
                "VALUES (%s, %s, 'synthetic-lexical-v1', %s, 'approved', 'approved', CURRENT_TIMESTAMP)",
                (source_version_id, source_id, version_hash),
            )

    def create_ingestion_run(self, *, run_id: str, source_version_id: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_ingestion_runs "
                "(ingestion_run_id, source_version_id, dry_run, run_status, operator_id) "
                "VALUES (%s, %s, false, 'running', 'synthetic-p9b-cli')",
                (run_id, source_version_id),
            )

    def finish_ingestion_run(self, *, run_id: str, document_count: int, chunk_count: int, status: str = 'succeeded') -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE rag_ingestion_runs SET run_status = %s, documents_seen = %s, chunks_seen = %s, "
                "completed_at = CURRENT_TIMESTAMP WHERE ingestion_run_id = %s",
                (status, document_count, chunk_count, run_id),
            )

    def insert_staging_document(
        self,
        *,
        staging_document_id: str,
        run_id: str,
        source_version_id: str,
        document_hash: str,
        title: str,
        ttl_seconds: int,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_ingestion_staging_documents "
                "(staging_document_id, ingestion_run_id, source_version_id, document_hash, document_title, expires_at, cleanup_after) "
                "VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'), "
                "CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'))",
                (staging_document_id, run_id, source_version_id, document_hash, title[:256], ttl_seconds, ttl_seconds * 2),
            )

    def insert_staging_chunk(self, *, staging_chunk_id: str, staging_document_id: str, chunk) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_ingestion_staging_chunks "
                "(staging_chunk_id, staging_document_id, chunk_hash, chunk_ordinal, section_label, token_count, "
                "chunk_text, section_path, word_count, chunking_profile, expires_at, cleanup_after) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "CURRENT_TIMESTAMP + INTERVAL '1 hour', CURRENT_TIMESTAMP + INTERVAL '2 hours')",
                (
                    staging_chunk_id,
                    staging_document_id,
                    chunk.chunk_hash,
                    chunk.chunk_ordinal,
                    chunk.section_path[:160],
                    chunk.word_count,
                    chunk.chunk_text,
                    chunk.section_path,
                    chunk.word_count,
                    chunk.chunking_profile,
                ),
            )

    def promote_document(self, *, document_id: str, source_version_id: str, document_hash: str, title: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_documents "
                "(document_id, source_version_id, document_hash, document_title, language, document_type, "
                "lifecycle_state, approval_status, synthetic_only, authority, clinical_use_allowed, source_title_safe) "
                "VALUES (%s, %s, %s, %s, 'id', 'synthetic_fixture', 'approved', 'approved', true, false, false, %s)",
                (document_id, source_version_id, document_hash, title[:256], title[:256]),
            )

    def promote_chunk(self, *, chunk) -> None:
        metadata = {
            'section_path': chunk.section_path,
            'chunking_profile': chunk.chunking_profile,
            'synthetic_only': True,
            'authority': False,
            'clinical_use_allowed': False,
        }
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_chunks "
                "(chunk_id, document_id, source_version_id, chunk_hash, chunk_ordinal, chunk_text, page_label, "
                "section_label, metadata, lifecycle_state, retrieval_eligible, section_path, word_count, "
                "language_code, fts_config_code, synthetic_only, authority, clinical_use_allowed, chunking_profile) "
                "VALUES (%s, %s, %s, %s, %s, %s, '', %s, %s, 'approved', true, %s, %s, %s, %s, true, false, false, %s)",
                (
                    chunk.chunk_id,
                    chunk.document_id,
                    chunk.source_version_id,
                    chunk.chunk_hash,
                    chunk.chunk_ordinal,
                    chunk.chunk_text,
                    chunk.section_path[:160],
                    Jsonb(metadata),
                    chunk.section_path,
                    chunk.word_count,
                    chunk.language_code,
                    chunk.fts_config_code,
                    chunk.chunking_profile,
                ),
            )

    def create_release(self, *, release_id: str, release_version: str, release_hash: str, chunks: Iterable) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_index_release_manifests "
                "(release_id, release_version, release_hash, release_status, approved_at, synthetic_only, authority, "
                "clinical_use_allowed, retrieval_backend, chunking_profile) "
                "VALUES (%s, %s, %s, 'active', CURRENT_TIMESTAMP, true, false, false, 'lexical', 'synthetic-lexical-v1')",
                (release_id, release_version[:128], release_hash),
            )
            for rank, chunk in enumerate(chunks):
                cur.execute(
                    "INSERT INTO rag_index_release_manifest_chunks (release_id, chunk_id, chunk_hash, chunk_rank) "
                    "VALUES (%s, %s, %s, %s)",
                    (release_id, chunk.chunk_id, chunk.chunk_hash, rank),
                )

    def activate_release(self, *, release_id: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT synthetic_only, authority, clinical_use_allowed, retrieval_backend "
                "FROM rag_index_release_manifests WHERE release_id = %s",
                (release_id,),
            )
            target = cur.fetchone()
            if not target or target != (True, False, False, 'lexical'):
                raise RuntimeError('unsafe_synthetic_release_pointer')
            cur.execute(
                "SELECT ar.release_id, rm.synthetic_only, rm.authority, rm.clinical_use_allowed, rm.retrieval_backend "
                "FROM rag_active_index_release ar "
                "LEFT JOIN rag_index_release_manifests rm ON rm.release_id = ar.release_id "
                "WHERE ar.pointer_name = %s FOR UPDATE OF ar",
                (ACTIVE_POINTER_NAME,),
            )
            existing = cur.fetchone()
            if existing and existing[1:] != (True, False, False, 'lexical'):
                raise RuntimeError('active_pointer_not_synthetic')
            cur.execute(
                "INSERT INTO rag_active_index_release (pointer_name, release_id, activated_at) "
                "VALUES (%s, %s, CURRENT_TIMESTAMP) "
                "ON CONFLICT (pointer_name) DO UPDATE SET release_id = EXCLUDED.release_id, activated_at = CURRENT_TIMESTAMP",
                (ACTIVE_POINTER_NAME, release_id),
            )
            cur.execute(
                "INSERT INTO rag_index_release_history (release_id, action, performed_by, safe_notes) "
                "VALUES (%s, 'activated', 'synthetic-p9b-cli', 'synthetic lexical activation')",
                (release_id,),
            )

    def fetch_active_lexical(self, *, safe_query: str, max_results: int) -> tuple[str | None, list[dict[str, object]]]:
        limit = max(1, min(int(max_results), 20))
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT ar.release_id FROM rag_active_index_release ar "
                "JOIN rag_index_release_manifests rm ON rm.release_id = ar.release_id "
                "WHERE ar.pointer_name = %s AND rm.synthetic_only = true AND rm.authority = false "
                "AND rm.clinical_use_allowed = false AND rm.retrieval_backend = 'lexical'",
                (ACTIVE_POINTER_NAME,),
            )
            row = cur.fetchone()
            if not row:
                return None, []
            release_id = row[0]
            cur.execute(
                "SELECT c.chunk_id, c.document_id, c.source_version_id, d.source_title_safe, c.section_path, "
                "c.chunk_ordinal, c.chunk_hash, c.chunk_text, c.synthetic_only, c.authority, c.clinical_use_allowed, "
                "ts_rank_cd(c.search_vector, websearch_to_tsquery('simple', %s)) AS retrieval_score "
                "FROM rag_index_release_manifest_chunks mc "
                "JOIN rag_chunks c ON c.chunk_id = mc.chunk_id "
                "JOIN rag_documents d ON d.document_id = c.document_id "
                "WHERE mc.release_id = %s "
                "AND c.lifecycle_state = 'approved' AND c.retrieval_eligible = true "
                "AND c.synthetic_only = true AND c.authority = false AND c.clinical_use_allowed = false "
                "AND d.synthetic_only = true AND d.authority = false AND d.clinical_use_allowed = false "
                "AND c.search_vector @@ websearch_to_tsquery('simple', %s) "
                "ORDER BY retrieval_score DESC, mc.chunk_rank ASC LIMIT %s",
                (safe_query, release_id, safe_query, limit),
            )
            columns = [desc.name for desc in cur.description]
            rows = [dict(zip(columns, result)) for result in cur.fetchall()]
        return release_id, rows

    def insert_retrieval_event(
        self,
        *,
        event_id: str,
        release_id: str | None,
        event_type: str,
        result_count: int,
        selected_chunk_ids: list[str],
        abstention_reason: str,
        safe_metadata: dict[str, object],
    ) -> None:
        bounded_ids = [str(value)[:96] for value in selected_chunk_ids[:20]]
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_retrieval_events "
                "(event_id, release_id, event_type, retrieval_backend, filter_policy, result_count, "
                "selected_chunk_count, selected_chunk_ids, abstention_reason, safe_metadata) "
                "VALUES (%s, %s, %s, 'lexical', 'synthetic_only_v1', %s, %s, %s, %s, %s)",
                (
                    event_id,
                    release_id,
                    event_type,
                    max(0, min(int(result_count), 50)),
                    len(bounded_ids),
                    ','.join(bounded_ids)[:4096],
                    abstention_reason[:96],
                    Jsonb(safe_metadata),
                ),
            )

    def cleanup_prefix(self, prefix: str) -> None:
        cleanup_sql = (
            ('rag_chunk_embeddings', 'embedding_id'),
            ('rag_index_release_manifest_chunks', 'release_id'),
            ('rag_active_index_release', 'release_id'),
            ('rag_index_release_history', 'release_id'),
            ('rag_retrieval_events', 'event_id'),
            ('rag_retrieval_events', 'release_id'),
            ('rag_index_release_manifests', 'release_id'),
            ('rag_chunks', 'chunk_id'),
            ('rag_documents', 'document_id'),
            ('rag_ingestion_staging_chunks', 'staging_chunk_id'),
            ('rag_ingestion_staging_documents', 'staging_document_id'),
            ('rag_ingestion_runs', 'ingestion_run_id'),
            ('rag_source_versions', 'source_version_id'),
            ('rag_sources', 'source_id'),
        )
        with self.conn.cursor() as cur:
            for table, column in cleanup_sql:
                cur.execute('SELECT to_regclass(%s)', (table,))
                if cur.fetchone()[0]:
                    cur.execute(
                        sql.SQL('DELETE FROM {} WHERE {} LIKE %s').format(
                            sql.Identifier(table), sql.Identifier(column),
                        ),
                        (prefix + '%',),
                    )

    def safe_counts(self, prefix: str) -> SyntheticCounts:
        counts = {'synthetic_rows': 0, 'temporary_staging_rows': 0, 'active_synthetic_pointers': 0, 'real_corpus_rows': 0}
        with self.conn.cursor() as cur:
            for table, column in (
                ('rag_sources', 'source_id'),
                ('rag_source_versions', 'source_version_id'),
                ('rag_ingestion_runs', 'ingestion_run_id'),
                ('rag_documents', 'document_id'),
                ('rag_chunks', 'chunk_id'),
                ('rag_index_release_manifests', 'release_id'),
                ('rag_retrieval_events', 'event_id'),
            ):
                if self.table_exists(table):
                    cur.execute(sql.SQL('SELECT COUNT(*) FROM {} WHERE {} LIKE %s').format(sql.Identifier(table), sql.Identifier(column)), (prefix + '%',))
                    counts['synthetic_rows'] += int(cur.fetchone()[0])
            for table, column in (('rag_ingestion_staging_documents', 'staging_document_id'), ('rag_ingestion_staging_chunks', 'staging_chunk_id')):
                if self.table_exists(table):
                    cur.execute(sql.SQL('SELECT COUNT(*) FROM {} WHERE {} LIKE %s').format(sql.Identifier(table), sql.Identifier(column)), (prefix + '%',))
                    counts['temporary_staging_rows'] += int(cur.fetchone()[0])
            if self.table_exists('rag_active_index_release'):
                cur.execute('SELECT COUNT(*) FROM rag_active_index_release WHERE release_id LIKE %s', (prefix + '%',))
                counts['active_synthetic_pointers'] = int(cur.fetchone()[0])
            if self.table_exists('rag_documents'):
                cur.execute("SELECT COUNT(*) FROM rag_documents WHERE synthetic_only = false AND document_id NOT LIKE 'SYN-P9%'")
                counts['real_corpus_rows'] = int(cur.fetchone()[0])
        return SyntheticCounts(**counts)
