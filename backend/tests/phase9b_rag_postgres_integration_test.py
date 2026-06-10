"""Optional Phase 9 P9-B synthetic PostgreSQL integration tests.

Skipped unless explicit synthetic RAG integration environment variables are set.
Uses generated synthetic fixtures only and cleans all SYN-P9B rows after each run.
"""
from __future__ import annotations

import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import dotenv_values as _dotenv_values

    _env_candidate = ROOT / '.env'
    if _env_candidate.exists():
        _env_vals = _dotenv_values(str(_env_candidate))
        for _key in (
            'REGISTRY_DATABASE_ADMIN_URL', 'REGISTRY_ACTIVATION_ENABLED', 'RAG_RUNTIME_MODE',
            'RAG_STORE_ENABLED', 'RAG_INGESTION_ENABLED', 'RAG_LEXICAL_RETRIEVAL_ENABLED',
            'RAG_INDEX_ACTIVATION_ENABLED', 'RAG_VECTOR_RETRIEVAL_ENABLED',
            'RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED',
        ):
            if _key not in os.environ and _env_vals.get(_key):
                os.environ[_key] = str(_env_vals[_key])
except ImportError:
    pass


def _enabled(name: str) -> bool:
    return os.environ.get(name, '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, '') or default)
    except ValueError:
        return default


_OPT_IN = os.environ.get('RAG_POSTGRES_INTEGRATION_TEST') == '1'
_ADMIN_URL = os.environ.get('REGISTRY_DATABASE_ADMIN_URL', '')
_RUNTIME_MODE = os.environ.get('RAG_RUNTIME_MODE', 'disabled')
_REGISTRY_ACTIVE = _enabled('REGISTRY_ACTIVATION_ENABLED')
_REQUIRED_FLAGS = _enabled('RAG_STORE_ENABLED') and _enabled('RAG_INGESTION_ENABLED') and _enabled('RAG_LEXICAL_RETRIEVAL_ENABLED') and _enabled('RAG_INDEX_ACTIVATION_ENABLED')
_FORBIDDEN_FLAGS = _enabled('RAG_VECTOR_RETRIEVAL_ENABLED') or _enabled('RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED')
_SKIP = 'P9-B PostgreSQL integration requires explicit synthetic RAG opt-in, admin URL, and registry/vector/provider disabled.'


@unittest.skipUnless(_OPT_IN and _ADMIN_URL and _RUNTIME_MODE == 'synthetic_corpus_test' and _REQUIRED_FLAGS and not _REGISTRY_ACTIVE and not _FORBIDDEN_FLAGS, _SKIP)
class P9BRagPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg

        cls.psycopg = psycopg
        cls.conn = psycopg.connect(_ADMIN_URL, connect_timeout=15, autocommit=False)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        from rag_repository import ACTIVE_POINTER_NAME

        self.prefix = 'SYN-P9B-' + uuid.uuid4().hex[:12]
        self.previous_pointer = None
        with self.conn.cursor() as cur:
            cur.execute('SELECT to_regclass(%s)', ('rag_active_index_release',))
            if cur.fetchone()[0]:
                cur.execute('SELECT release_id FROM rag_active_index_release WHERE pointer_name = %s', (ACTIVE_POINTER_NAME,))
                row = cur.fetchone()
                self.previous_pointer = row[0] if row else None
        self._cleanup_prefix()

    def tearDown(self):
        from rag_repository import ACTIVE_POINTER_NAME, RagRepository

        repo = RagRepository(self.conn)
        repo.cleanup_prefix(self.prefix)
        with self.conn.cursor() as cur:
            if self.previous_pointer:
                cur.execute(
                    "INSERT INTO rag_active_index_release (pointer_name, release_id, activated_at) "
                    "VALUES (%s, %s, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (pointer_name) DO UPDATE SET release_id = EXCLUDED.release_id, activated_at = CURRENT_TIMESTAMP",
                    (ACTIVE_POINTER_NAME, self.previous_pointer),
                )
            else:
                cur.execute('DELETE FROM rag_active_index_release WHERE pointer_name = %s', (ACTIVE_POINTER_NAME,))
        self.conn.commit()
        counts = repo.safe_counts(self.prefix)
        self.assertEqual(counts.synthetic_rows, 0)
        self.assertEqual(counts.temporary_staging_rows, 0)
        self.assertEqual(counts.active_synthetic_pointers, 0)
        self.assertEqual(counts.real_corpus_rows, 0)
        self.assertFalse(_REGISTRY_ACTIVE)

    def _cleanup_prefix(self):
        from rag_repository import RagRepository

        repo = RagRepository(self.conn)
        repo.cleanup_prefix(self.prefix)
        self.conn.commit()

    def _table_exists(self, table_name: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute('SELECT to_regclass(%s)', (table_name,))
            row = cur.fetchone()
        return bool(row and row[0])

    def _active_pointer(self):
        from rag_repository import ACTIVE_POINTER_NAME

        with self.conn.cursor() as cur:
            cur.execute('SELECT release_id FROM rag_active_index_release WHERE pointer_name = %s', (ACTIVE_POINTER_NAME,))
            row = cur.fetchone()
        return row[0] if row else None

    def _restore_previous_pointer_now(self) -> None:
        from rag_repository import ACTIVE_POINTER_NAME

        with self.conn.cursor() as cur:
            if self.previous_pointer:
                cur.execute(
                    "INSERT INTO rag_active_index_release (pointer_name, release_id, activated_at) "
                    "VALUES (%s, %s, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (pointer_name) DO UPDATE SET release_id = EXCLUDED.release_id, activated_at = CURRENT_TIMESTAMP",
                    (ACTIVE_POINTER_NAME, self.previous_pointer),
                )
            else:
                cur.execute('DELETE FROM rag_active_index_release WHERE pointer_name = %s', (ACTIVE_POINTER_NAME,))

    def _insert_release_manifest(self, release_id: str, *, synthetic_only: bool) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_index_release_manifests "
                "(release_id, release_version, release_hash, release_status, approved_at, synthetic_only, authority, "
                "clinical_use_allowed, retrieval_backend, chunking_profile) "
                "VALUES (%s, %s, %s, 'active', CURRENT_TIMESTAMP, %s, false, false, 'lexical', 'synthetic-lexical-v1')",
                (release_id, release_id + '-version', 'a' * 64, synthetic_only),
            )

    def test_pointer_activation_with_empty_previous_and_success_cleanup(self):
        from rag_repository import ACTIVE_POINTER_NAME, RagRepository, ensure_core_schema

        ensure_core_schema(self.conn)
        repo = RagRepository(self.conn)
        release_id = f'{self.prefix}-REL-EMPTY'
        with self.conn.cursor() as cur:
            cur.execute('DELETE FROM rag_active_index_release WHERE pointer_name = %s', (ACTIVE_POINTER_NAME,))
        self._insert_release_manifest(release_id, synthetic_only=True)
        repo.activate_release(release_id=release_id)
        self.conn.commit()
        self.assertEqual(self._active_pointer(), release_id)

        repo.cleanup_prefix(self.prefix)
        self._restore_previous_pointer_now()
        self.conn.commit()
        self.assertEqual(self._active_pointer(), self.previous_pointer)

    def test_pointer_activation_refuses_existing_non_synthetic_pointer(self):
        from rag_repository import ACTIVE_POINTER_NAME, RagRepository, ensure_core_schema

        ensure_core_schema(self.conn)
        repo = RagRepository(self.conn)
        non_synthetic_release = f'{self.prefix}-REL-NON-SYN'
        synthetic_release = f'{self.prefix}-REL-SYN'
        self._insert_release_manifest(non_synthetic_release, synthetic_only=False)
        self._insert_release_manifest(synthetic_release, synthetic_only=True)
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_active_index_release (pointer_name, release_id, activated_at) "
                "VALUES (%s, %s, CURRENT_TIMESTAMP) "
                "ON CONFLICT (pointer_name) DO UPDATE SET release_id = EXCLUDED.release_id, activated_at = CURRENT_TIMESTAMP",
                (ACTIVE_POINTER_NAME, non_synthetic_release),
            )
        self.conn.commit()

        with self.assertRaises(RuntimeError):
            repo.activate_release(release_id=synthetic_release)
        self.assertEqual(self._active_pointer(), non_synthetic_release)

    def test_pointer_restored_after_exception_cleanup(self):
        from rag_repository import RagRepository, ensure_core_schema

        ensure_core_schema(self.conn)
        repo = RagRepository(self.conn)
        release_id = f'{self.prefix}-REL-EXCEPTION'
        self._insert_release_manifest(release_id, synthetic_only=True)
        repo.activate_release(release_id=release_id)
        self.conn.commit()
        self.assertEqual(self._active_pointer(), release_id)

        try:
            raise RuntimeError('synthetic_failure_after_pointer_update')
        except RuntimeError:
            repo.cleanup_prefix(self.prefix)
            self._restore_previous_pointer_now()
            self.conn.commit()
        self.assertEqual(self._active_pointer(), self.previous_pointer)

    def test_partial_ingestion_failure_cleanup_leaves_zero_rows(self):
        from rag_fixture_loader import default_fixture_root
        from rag_ingestion_service import RagIngestionError, SyntheticIngestionConfig, ingest_synthetic_fixtures
        from rag_repository import RagRepository

        repo = RagRepository(self.conn)
        with self.assertRaises(RagIngestionError):
            ingest_synthetic_fixtures(
                self.conn,
                SyntheticIngestionConfig(
                    fixture_root=default_fixture_root(),
                    max_document_chars=12000,
                    max_staging_chunks=1,
                    chunk_target_words=40,
                    chunk_overlap_words=0,
                    staging_ttl_seconds=60,
                ),
                prefix=self.prefix,
            )
        repo.cleanup_prefix(self.prefix)
        self.conn.commit()
        counts = repo.safe_counts(self.prefix)
        self.assertEqual(counts.synthetic_rows, 0)
        self.assertEqual(counts.temporary_staging_rows, 0)
        self.assertEqual(counts.active_synthetic_pointers, 0)

    def test_synthetic_ingestion_release_retrieval_citation_abstention_and_telemetry(self):
        from rag_fixture_loader import default_fixture_root
        from rag_ingestion_service import SyntheticIngestionConfig, ingest_synthetic_fixtures
        from rag_lexical_retrieval import LexicalRetrievalConfig, retrieve_lexical
        from rag_migrations import pgvector_installed
        from rag_repository import ACTIVE_POINTER_NAME

        result = ingest_synthetic_fixtures(
            self.conn,
            SyntheticIngestionConfig(
                fixture_root=default_fixture_root(),
                max_document_chars=_int_env('RAG_MAX_DOCUMENT_CHARS', 12000),
                max_staging_chunks=_int_env('RAG_MAX_STAGING_CHUNKS', 200),
                chunk_target_words=_int_env('RAG_CHUNK_TARGET_WORDS', 90),
                chunk_overlap_words=_int_env('RAG_CHUNK_OVERLAP_WORDS', 12),
                staging_ttl_seconds=_int_env('RAG_STAGING_TTL_SECONDS', 3600),
            ),
            prefix=self.prefix,
        )
        self.assertEqual(result.ingestion_status, 'succeeded')
        self.assertGreaterEqual(result.document_count, 3)
        self.assertGreater(result.chunk_count, 0)
        with self.conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM rag_ingestion_staging_chunks WHERE staging_chunk_id LIKE %s AND searchable = true', (self.prefix + '%',))
            self.assertEqual(int(cur.fetchone()[0]), 0)
            cur.execute(
                "SELECT COUNT(*) FROM rag_index_release_manifest_chunks mc "
                "JOIN rag_chunks c ON c.chunk_id = mc.chunk_id "
                "WHERE mc.release_id = %s AND c.synthetic_only = true AND c.authority = false "
                "AND c.clinical_use_allowed = false AND c.lifecycle_state = 'approved' AND c.retrieval_eligible = true",
                (result.release_id,),
            )
            self.assertGreater(int(cur.fetchone()[0]), 0)
            cur.execute('SELECT release_id FROM rag_active_index_release WHERE pointer_name = %s', (ACTIVE_POINTER_NAME,))
            self.assertEqual(cur.fetchone()[0], result.release_id)
            cur.execute(
                "SELECT COUNT(*) FROM rag_index_release_history h "
                "JOIN rag_index_release_manifests rm ON rm.release_id = h.release_id "
                "WHERE h.release_id = %s AND rm.synthetic_only = true AND rm.authority = false "
                "AND rm.clinical_use_allowed = false",
                (result.release_id,),
            )
            self.assertGreaterEqual(int(cur.fetchone()[0]), 1)

        retrieval = retrieve_lexical(
            self.conn,
            'breathing comfort',
            LexicalRetrievalConfig(max_results=5, max_excerpt_chars=240, min_lexical_rank=0.0, event_prefix=self.prefix),
        )
        self.assertTrue(retrieval.retrieved)
        self.assertGreater(len(retrieval.citations), 0)
        first = retrieval.citations[0]
        self.assertTrue(first.synthetic_only)
        self.assertFalse(first.authority)
        self.assertFalse(first.clinical_use_allowed)

        markup = retrieve_lexical(
            self.conn,
            'script',
            LexicalRetrievalConfig(max_results=5, max_excerpt_chars=240, min_lexical_rank=0.0, event_prefix=self.prefix),
        )
        self.assertTrue(markup.retrieved)
        self.assertNotIn('<script>', markup.citations[0].excerpt_plain_text.lower())

        abstained = retrieve_lexical(self.conn, '', LexicalRetrievalConfig(event_prefix=self.prefix))
        self.assertFalse(abstained.retrieved)
        self.assertEqual(abstained.abstention.reason_code, 'query_empty')

        with self.conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM rag_retrieval_events WHERE event_id LIKE %s', (self.prefix + '%',))
            self.assertGreaterEqual(int(cur.fetchone()[0]), 3)
            cur.execute('SELECT selected_chunk_count, selected_chunk_ids, safe_metadata FROM rag_retrieval_events WHERE event_id = %s', (retrieval.telemetry_event_id,))
            selected_count, selected_ids, metadata = cur.fetchone()
            self.assertGreaterEqual(int(selected_count), 1)
            self.assertNotIn('raw', str(metadata).lower())
            self.assertNotIn('query', str(metadata).lower())
            self.assertNotIn('prompt', str(metadata).lower())
            self.assertLessEqual(len(selected_ids), 4096)

        installed, version_present = pgvector_installed(self.conn)
        self.assertFalse(installed)
        self.assertFalse(version_present)
        self.assertFalse(self._table_exists('rag_chunk_embeddings'))

    def test_retrieval_failure_records_safe_abstention_and_cleanup(self):
        from rag_fixture_loader import default_fixture_root
        from rag_ingestion_service import SyntheticIngestionConfig, ingest_synthetic_fixtures
        from rag_lexical_retrieval import LexicalRetrievalConfig, retrieve_lexical
        from rag_repository import RagRepository

        result = ingest_synthetic_fixtures(
            self.conn,
            SyntheticIngestionConfig(fixture_root=default_fixture_root()),
            prefix=self.prefix,
        )
        self.assertEqual(self._active_pointer(), result.release_id)
        with mock.patch('rag_lexical_retrieval.RagRepository.fetch_active_lexical', side_effect=RuntimeError('unsafe raw failure')):
            retrieval = retrieve_lexical(
                self.conn,
                'breathing comfort',
                LexicalRetrievalConfig(max_results=5, min_lexical_rank=0.0, event_prefix=self.prefix),
            )
        self.assertFalse(retrieval.retrieved)
        self.assertEqual(retrieval.abstention.reason_code, 'internal_safe_failure')

        repo = RagRepository(self.conn)
        repo.cleanup_prefix(self.prefix)
        self.conn.commit()
        counts = repo.safe_counts(self.prefix)
        self.assertEqual(counts.synthetic_rows, 0)
        self.assertEqual(counts.temporary_staging_rows, 0)
        self.assertEqual(counts.active_synthetic_pointers, 0)


if __name__ == '__main__':
    unittest.main()
