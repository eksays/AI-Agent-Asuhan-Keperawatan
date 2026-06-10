"""Optional Phase 9 P9-A PostgreSQL integration tests.

These tests are skipped unless RAG_POSTGRES_INTEGRATION_TEST=1 and
RAG_RUNTIME_MODE=synthetic_corpus_test are explicitly set. They use synthetic
rows only and clean up mandatory P9 prefixes after each run.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import dotenv_values as _dotenv_values

    _env_candidate = ROOT / '.env'
    if _env_candidate.exists():
        _env_vals = _dotenv_values(str(_env_candidate))
        for _key in (
            'REGISTRY_DATABASE_ADMIN_URL', 'REGISTRY_DATABASE_URL',
            'REGISTRY_ACTIVATION_ENABLED', 'RAG_RUNTIME_MODE',
        ):
            if _key not in os.environ and _env_vals.get(_key):
                os.environ[_key] = str(_env_vals[_key])
except ImportError:
    pass

_OPT_IN = os.environ.get('RAG_POSTGRES_INTEGRATION_TEST') == '1'
_ADMIN_URL = os.environ.get('REGISTRY_DATABASE_ADMIN_URL', '')
_RUNTIME_MODE = os.environ.get('RAG_RUNTIME_MODE', 'disabled')
_REGISTRY_ACTIVE = os.environ.get('REGISTRY_ACTIVATION_ENABLED', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}
_SKIP = (
    'RAG PostgreSQL integration requires RAG_POSTGRES_INTEGRATION_TEST=1, '
    'RAG_RUNTIME_MODE=synthetic_corpus_test, admin URL, and registry activation false.'
)


@unittest.skipUnless(_OPT_IN and _ADMIN_URL and _RUNTIME_MODE == 'synthetic_corpus_test' and not _REGISTRY_ACTIVE, _SKIP)
class P9ARagPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg

        cls.psycopg = psycopg
        cls.conn = psycopg.connect(_ADMIN_URL, connect_timeout=15, autocommit=False)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.conn.close()
        except Exception:
            pass

    def setUp(self):
        self.prefix = 'SYN-P9-' + uuid.uuid4().hex[:12]
        self._cleanup_prefix(self.prefix)

    def tearDown(self):
        self._cleanup_prefix(self.prefix)
        counts = self._safe_counts(self.prefix)
        self.assertEqual(counts['synthetic_rows'], 0)
        self.assertEqual(counts['temporary_staging_rows'], 0)
        self.assertEqual(counts['active_synthetic_pointers'], 0)
        self.assertEqual(counts['real_corpus_rows'], 0)
        self.assertFalse(_REGISTRY_ACTIVE)

    def _table_exists(self, table_name: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute('SELECT to_regclass(%s)', (table_name,))
            row = cur.fetchone()
        return bool(row and row[0])

    def _cleanup_prefix(self, prefix: str) -> None:
        try:
            from psycopg import sql

            with self.conn.cursor() as cur:
                cleanup_sql = (
                    ('rag_chunk_embeddings', 'embedding_id'),
                    ('rag_index_release_manifest_chunks', 'release_id'),
                    ('rag_active_index_release', 'release_id'),
                    ('rag_index_release_history', 'release_id'),
                    ('rag_index_release_manifests', 'release_id'),
                    ('rag_retrieval_events', 'event_id'),
                    ('rag_chunks', 'chunk_id'),
                    ('rag_documents', 'document_id'),
                    ('rag_ingestion_staging_chunks', 'staging_chunk_id'),
                    ('rag_ingestion_staging_documents', 'staging_document_id'),
                    ('rag_ingestion_runs', 'ingestion_run_id'),
                    ('rag_source_versions', 'source_version_id'),
                    ('rag_sources', 'source_id'),
                )
                for table, column in cleanup_sql:
                    cur.execute('SELECT to_regclass(%s)', (table,))
                    if cur.fetchone()[0]:
                        cur.execute(
                            sql.SQL('DELETE FROM {} WHERE {} LIKE %s').format(
                                sql.Identifier(table), sql.Identifier(column),
                            ),
                            (prefix + '%',),
                        )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _safe_counts(self, prefix: str) -> dict[str, int]:
        from psycopg import sql

        counts = {
            'synthetic_rows': 0,
            'temporary_staging_rows': 0,
            'active_synthetic_pointers': 0,
            'real_corpus_rows': 0,
        }
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
                if self._table_exists(table):
                    cur.execute(
                        sql.SQL('SELECT COUNT(*) FROM {} WHERE {} LIKE %s').format(
                            sql.Identifier(table), sql.Identifier(column),
                        ),
                        (prefix + '%',),
                    )
                    counts['synthetic_rows'] += int(cur.fetchone()[0])
            for table, column in (
                ('rag_ingestion_staging_documents', 'staging_document_id'),
                ('rag_ingestion_staging_chunks', 'staging_chunk_id'),
            ):
                if self._table_exists(table):
                    cur.execute(
                        sql.SQL('SELECT COUNT(*) FROM {} WHERE {} LIKE %s').format(
                            sql.Identifier(table), sql.Identifier(column),
                        ),
                        (prefix + '%',),
                    )
                    counts['temporary_staging_rows'] += int(cur.fetchone()[0])
            if self._table_exists('rag_active_index_release'):
                cur.execute('SELECT COUNT(*) FROM rag_active_index_release WHERE release_id LIKE %s', (prefix + '%',))
                counts['active_synthetic_pointers'] = int(cur.fetchone()[0])
            if self._table_exists('rag_documents'):
                cur.execute("SELECT COUNT(*) FROM rag_documents WHERE document_id NOT LIKE 'SYN-P9-%'")
                counts['real_corpus_rows'] = int(cur.fetchone()[0])
        return counts

    def _run_migration_cli(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env['APP_MODE'] = 'clinical_sandbox'
        env['RAG_RUNTIME_MODE'] = 'synthetic_corpus_test'
        env['REGISTRY_ACTIVATION_ENABLED'] = 'false'
        return subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'rag_db_migrate.py'), *args],
            cwd=str(ROOT.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def test_core_migration_and_synthetic_lexical_smoke(self):
        result = self._run_migration_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        second = self._run_migration_cli()
        self.assertEqual(second.returncode, 0, second.stderr)
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM rag_schema_migrations "
                "WHERE migration_id LIKE 'RAG_CORE_%' AND char_length(migration_checksum) = 64"
            )
            self.assertGreaterEqual(int(cur.fetchone()[0]), 6)

        source_id = self.prefix + '-SRC'
        version_id = self.prefix + '-VER'
        run_id = self.prefix + '-RUN'
        staging_doc_id = self.prefix + '-ST-DOC'
        staging_chunk_id = self.prefix + '-ST-CHUNK'
        document_id = self.prefix + '-DOC'
        chunk_id = self.prefix + '-CHUNK'
        release_id = self.prefix + '-REL'
        h = 'a' * 64
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_sources (source_id, source_title, source_hash, license_status, governance_status) "
                "VALUES (%s, %s, %s, 'approved', 'approved')",
                (source_id, 'Synthetic P9 Source', h),
            )
            cur.execute(
                "INSERT INTO rag_source_versions (source_version_id, source_id, version_label, version_hash, approval_status, license_status) "
                "VALUES (%s, %s, 'v1', %s, 'approved', 'approved')",
                (version_id, source_id, h),
            )
            cur.execute(
                "INSERT INTO rag_ingestion_runs (ingestion_run_id, source_version_id, run_status, dry_run) "
                "VALUES (%s, %s, 'succeeded', false)",
                (run_id, version_id),
            )
            cur.execute(
                "INSERT INTO rag_ingestion_staging_documents "
                "(staging_document_id, ingestion_run_id, source_version_id, document_hash, expires_at, cleanup_after) "
                "VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP + INTERVAL '1 hour', CURRENT_TIMESTAMP + INTERVAL '2 hours')",
                (staging_doc_id, run_id, version_id, h),
            )
            cur.execute(
                "INSERT INTO rag_ingestion_staging_chunks "
                "(staging_chunk_id, staging_document_id, chunk_hash, chunk_ordinal, chunk_text, expires_at, cleanup_after) "
                "VALUES (%s, %s, %s, 0, %s, CURRENT_TIMESTAMP + INTERVAL '1 hour', CURRENT_TIMESTAMP + INTERVAL '2 hours')",
                (staging_chunk_id, staging_doc_id, h, 'synthetic lexical fixture only'),
            )
            cur.execute(
                "INSERT INTO rag_documents (document_id, source_version_id, document_hash, lifecycle_state, approval_status) "
                "VALUES (%s, %s, %s, 'approved', 'approved')",
                (document_id, version_id, h),
            )
            cur.execute(
                "INSERT INTO rag_chunks (chunk_id, document_id, chunk_hash, chunk_ordinal, chunk_text, lifecycle_state, retrieval_eligible) "
                "VALUES (%s, %s, %s, 0, %s, 'approved', true)",
                (chunk_id, document_id, h, 'synthetic lexical fixture only'),
            )
            cur.execute(
                "SELECT chunk_id FROM rag_chunks WHERE search_vector @@ to_tsquery('simple', 'synthetic') AND chunk_id = %s",
                (chunk_id,),
            )
            self.assertEqual(cur.fetchone()[0], chunk_id)
            cur.execute(
                "INSERT INTO rag_index_release_manifests (release_id, release_version, release_hash) VALUES (%s, %s, %s)",
                (release_id, self.prefix + '-v1', h),
            )
            cur.execute(
                "INSERT INTO rag_index_release_manifest_chunks (release_id, chunk_id, chunk_hash, chunk_rank) VALUES (%s, %s, %s, 0)",
                (release_id, chunk_id, h),
            )
        self.conn.commit()

    def test_optional_vector_migration_is_not_applied_in_closure_review(self):
        from rag_migrations import pgvector_available, pgvector_installed

        result = self._run_migration_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        available = pgvector_available(self.conn)
        installed, version_present = pgvector_installed(self.conn)
        self.assertIsInstance(available, bool)
        self.assertFalse(installed)
        self.assertFalse(version_present)
        self.assertFalse(self._table_exists('rag_chunk_embeddings'))
        self.assertNotIn('--enable-pgvector', result.args)


if __name__ == '__main__':
    unittest.main()
