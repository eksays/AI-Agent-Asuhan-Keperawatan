"""Optional Phase 9 P9-C synthetic pgvector PostgreSQL integration tests."""
from __future__ import annotations

import hashlib
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
            'RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED', 'RAG_ISOLATED_TEST_DATABASE_CONFIRMED',
        ):
            if _key not in os.environ and _env_vals.get(_key):
                os.environ[_key] = str(_env_vals[_key])
except ImportError:
    pass


def _enabled(name: str) -> bool:
    return os.environ.get(name, '').strip().lower() in {'1', 'true', 'yes', 'on'}


_OPT_IN = os.environ.get('RAG_POSTGRES_INTEGRATION_TEST') == '1'
_ADMIN_URL = os.environ.get('REGISTRY_DATABASE_ADMIN_URL', '')
_RUNTIME_MODE = os.environ.get('RAG_RUNTIME_MODE', 'disabled')
_REGISTRY_ACTIVE = _enabled('REGISTRY_ACTIVATION_ENABLED')
_REQUIRED_FLAGS = (
    _enabled('RAG_STORE_ENABLED')
    and _enabled('RAG_INGESTION_ENABLED')
    and _enabled('RAG_LEXICAL_RETRIEVAL_ENABLED')
    and _enabled('RAG_INDEX_ACTIVATION_ENABLED')
    and _enabled('RAG_ISOLATED_TEST_DATABASE_CONFIRMED')
)
_FORBIDDEN_FLAGS = _enabled('RAG_VECTOR_RETRIEVAL_ENABLED') or _enabled('RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED')
_SKIP = 'P9-C PostgreSQL integration requires explicit isolated synthetic RAG opt-in and disabled registry/vector/provider activation.'


@unittest.skipUnless(_OPT_IN and _ADMIN_URL and _RUNTIME_MODE == 'synthetic_corpus_test' and _REQUIRED_FLAGS and not _REGISTRY_ACTIVE and not _FORBIDDEN_FLAGS, _SKIP)
class P9CVectorPostgresIntegrationTests(unittest.TestCase):
    synthetic_vectors_inserted = 0
    exact_cosine_queries_executed = 0
    lexical_queries_executed = 0
    benchmark_runs = 0
    red_team_rejections = 0
    external_provider_calls = 0

    @classmethod
    def setUpClass(cls):
        import psycopg
        from rag_migrations import pgvector_installed

        cls.psycopg = psycopg
        cls.conn = psycopg.connect(_ADMIN_URL, connect_timeout=15, autocommit=False)
        installed, version_present = pgvector_installed(cls.conn)
        if not installed or not version_present:
            raise AssertionError('pgvector_not_ready')
        with cls.conn.cursor() as cur:
            cur.execute('SELECT to_regclass(%s) IS NOT NULL', ('rag_chunk_embeddings',))
            if not bool(cur.fetchone()[0]):
                raise AssertionError('vector_schema_not_ready')

    @classmethod
    def tearDownClass(cls):
        print(f'synthetic_vectors_inserted={cls.synthetic_vectors_inserted}')
        print(f'exact_cosine_queries_executed={cls.exact_cosine_queries_executed}')
        print(f'lexical_queries_executed={cls.lexical_queries_executed}')
        print(f'benchmark_runs={cls.benchmark_runs}')
        print(f'red_team_rejections={cls.red_team_rejections}')
        print(f'external_provider_calls={cls.external_provider_calls}')
        cls.conn.close()

    def setUp(self):
        from rag_repository import ACTIVE_POINTER_NAME

        self.prefix = 'SYN-P9C-' + uuid.uuid4().hex[:12]
        self.previous_pointer = None
        with self.conn.cursor() as cur:
            cur.execute('SELECT release_id FROM rag_active_index_release WHERE pointer_name = %s', (ACTIVE_POINTER_NAME,))
            row = cur.fetchone()
            self.previous_pointer = row[0] if row else None
        if self.previous_pointer and not self._release_is_safe_synthetic(self.previous_pointer):
            raise AssertionError('active_pointer_not_safe_to_restore')
        self._cleanup_prefix()

    def tearDown(self):
        from rag_repository import ACTIVE_POINTER_NAME, RagRepository

        self.conn.rollback()
        repo = RagRepository(self.conn)
        repo.cleanup_prefix(self.prefix)
        with self.conn.cursor() as cur:
            if self.previous_pointer:
                if not self._release_is_safe_synthetic(self.previous_pointer):
                    raise AssertionError('previous_pointer_no_longer_safe')
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

    def _release_is_safe_synthetic(self, release_id: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT synthetic_only, authority, clinical_use_allowed, retrieval_backend "
                "FROM rag_index_release_manifests WHERE release_id = %s",
                (release_id,),
            )
            row = cur.fetchone()
        return row == (True, False, False, 'lexical')

    def _vector_literal(self, text: str) -> str:
        from rag_synthetic_vectors import generate_synthetic_vector

        vector = generate_synthetic_vector(text)
        return '[' + ','.join(str(value) for value in vector) + ']'

    def _embedding_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def _ingest_and_embed(self):
        from rag_fixture_loader import default_fixture_root
        from rag_ingestion_service import SyntheticIngestionConfig, ingest_synthetic_fixtures

        result = ingest_synthetic_fixtures(
            self.conn,
            SyntheticIngestionConfig(fixture_root=default_fixture_root(), chunk_target_words=60, chunk_overlap_words=0),
            prefix=self.prefix,
        )
        inserted = self._insert_embeddings_for_prefix()
        self.conn.commit()
        self.__class__.synthetic_vectors_inserted += inserted
        return result

    def _insert_embeddings_for_prefix(self) -> int:
        from rag_synthetic_vectors import SYNTHETIC_DIMENSION, SYNTHETIC_MODEL_ID

        with self.conn.cursor() as cur:
            cur.execute(
                'SELECT chunk_id, chunk_text FROM rag_chunks WHERE chunk_id LIKE %s ORDER BY chunk_ordinal',
                (self.prefix + '%',),
            )
            rows = cur.fetchall()
            for idx, (chunk_id, chunk_text) in enumerate(rows):
                vector_literal = self._vector_literal(chunk_text)
                cur.execute(
                    "INSERT INTO rag_chunk_embeddings "
                    "(embedding_id, chunk_id, embedding_model_id, embedding_dimension, embedding_hash, embedding, synthetic_only) "
                    "VALUES (%s, %s, %s, %s, %s, %s::vector, true)",
                    (
                        f'{self.prefix}-EMB-{idx:04d}',
                        chunk_id,
                        SYNTHETIC_MODEL_ID,
                        SYNTHETIC_DIMENSION,
                        self._embedding_hash(chunk_id + chunk_text),
                        vector_literal,
                    ),
                )
        return len(rows)

    def _first_chunk(self):
        with self.conn.cursor() as cur:
            cur.execute(
                'SELECT chunk_id, chunk_text FROM rag_chunks WHERE chunk_id LIKE %s ORDER BY chunk_ordinal LIMIT 1',
                (self.prefix + '%',),
            )
            return cur.fetchone()

    def _assert_insert_rejected(self, statement: str, params: tuple) -> None:
        with self.assertRaises(Exception):
            with self.conn.cursor() as cur:
                cur.execute(statement, params)
            self.conn.commit()
        self.conn.rollback()
        self.__class__.red_team_rejections += 1

    def _insert_extra_chunk(self, *, suffix: str, synthetic_only: bool, lifecycle_state: str, retrieval_eligible: bool, model_id: str) -> str:
        from rag_synthetic_vectors import SYNTHETIC_DIMENSION

        source_version_id = f'{self.prefix}-VER'
        doc_id = f'{self.prefix}-DOC-{suffix}'[:96]
        chunk_id = f'{self.prefix}-CHK-{suffix}'[:96]
        text = f'synthetic vector red team chunk {suffix}'
        chunk_rank = 900 + (int(hashlib.sha256(suffix.encode('utf-8')).hexdigest()[:4], 16) % 1000)
        vector_literal = self._vector_literal(text)
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_documents "
                "(document_id, source_version_id, document_hash, document_title, lifecycle_state, approval_status, "
                "synthetic_only, authority, clinical_use_allowed, source_title_safe) "
                "VALUES (%s, %s, %s, %s, 'approved', 'approved', %s, false, false, %s)",
                (doc_id, source_version_id, self._embedding_hash(doc_id), suffix, synthetic_only, suffix),
            )
            cur.execute(
                "INSERT INTO rag_chunks "
                "(chunk_id, document_id, source_version_id, chunk_hash, chunk_ordinal, chunk_text, lifecycle_state, "
                "retrieval_eligible, synthetic_only, authority, clinical_use_allowed, section_path, language_code, fts_config_code) "
                "VALUES (%s, %s, %s, %s, 900, %s, %s, %s, %s, false, false, %s, 'id', 'simple')",
                (
                    chunk_id,
                    doc_id,
                    source_version_id,
                    self._embedding_hash(chunk_id),
                    text,
                    lifecycle_state,
                    retrieval_eligible,
                    synthetic_only,
                    suffix,
                ),
            )
            cur.execute(
                'INSERT INTO rag_index_release_manifest_chunks (release_id, chunk_id, chunk_hash, chunk_rank) VALUES (%s, %s, %s, %s)',
                (f'{self.prefix}-REL', chunk_id, self._embedding_hash(chunk_id), chunk_rank),
            )
            cur.execute(
                "INSERT INTO rag_chunk_embeddings "
                "(embedding_id, chunk_id, embedding_model_id, embedding_dimension, embedding_hash, embedding, synthetic_only) "
                "VALUES (%s, %s, %s, %s, %s, %s::vector, true)",
                (
                    f'{self.prefix}-EMB-{suffix}',
                    chunk_id,
                    model_id,
                    SYNTHETIC_DIMENSION,
                    self._embedding_hash('embedding-' + suffix),
                    vector_literal,
                ),
            )
        self.conn.commit()
        return chunk_id

    def test_vector_retrieval_benchmark_citation_and_metadata_cleanup(self):
        from rag_benchmark import BenchmarkQuery, run_lexical_benchmark, run_vector_benchmark
        from rag_lexical_retrieval import LexicalRetrievalConfig, retrieve_lexical
        from rag_vector_retrieval import VectorRetrievalConfig, retrieve_exact_cosine_vector

        result = self._ingest_and_embed()
        chunk_id, _chunk_text = self._first_chunk()

        lexical = retrieve_lexical(
            self.conn,
            'breathing comfort',
            LexicalRetrievalConfig(max_results=5, min_lexical_rank=0.0, event_prefix=self.prefix),
        )
        self.__class__.lexical_queries_executed += 1
        self.assertTrue(lexical.retrieved)
        self.assertFalse(lexical.citations[0].authority)
        self.assertFalse(lexical.citations[0].clinical_use_allowed)

        vector = retrieve_exact_cosine_vector(
            self.conn,
            'breathing comfort',
            VectorRetrievalConfig(max_results=5, min_vector_score=0.0, event_prefix=self.prefix),
        )
        self.__class__.exact_cosine_queries_executed += 1
        self.assertTrue(vector.retrieved)
        self.assertGreater(len(vector.citations), 0)
        self.assertTrue(vector.citations[0].synthetic_only)
        self.assertFalse(vector.citations[0].authority)
        self.assertFalse(vector.citations[0].clinical_use_allowed)

        queries = (BenchmarkQuery('SYN-P9C-Q1', 'breathing comfort', (chunk_id,)),)
        lexical_metrics = run_lexical_benchmark(self.conn, queries, top_k=5)
        vector_metrics = run_vector_benchmark(self.conn, queries, top_k=5)
        self.__class__.benchmark_runs += 2
        self.assertEqual(lexical_metrics.query_count, 1)
        self.assertEqual(vector_metrics.query_count, 1)
        self.assertGreaterEqual(lexical_metrics.latency_ms_min, 0)
        self.assertGreaterEqual(vector_metrics.latency_ms_min, 0)

        with self.conn.cursor() as cur:
            cur.execute(
                'SELECT retrieval_backend, selected_chunk_ids, safe_metadata FROM rag_retrieval_events WHERE release_id = %s',
                (result.release_id,),
            )
            events = cur.fetchall()
        self.assertGreaterEqual(len(events), 4)
        for backend, selected_ids, metadata in events:
            self.assertIn(backend, {'lexical', 'vector'})
            self.assertLessEqual(len(selected_ids), 4096)
            serialized = str(metadata).lower()
            self.assertNotIn('raw', serialized)
            self.assertNotIn('query', serialized)
            self.assertNotIn('prompt', serialized)
            self.assertNotIn('corpus_body', serialized)

    def test_vector_red_team_db_constraints_and_service_filters(self):
        from rag_repository import RagRepository
        from rag_synthetic_vectors import SYNTHETIC_DIMENSION, SYNTHETIC_MODEL_ID, generate_synthetic_vector
        from rag_vector_retrieval import VectorRetrievalConfig, retrieve_exact_cosine_vector

        self._ingest_and_embed()
        chunk_id, chunk_text = self._first_chunk()
        valid_vector = self._vector_literal(chunk_text)

        duplicate_sql = (
            "INSERT INTO rag_chunk_embeddings "
            "(embedding_id, chunk_id, embedding_model_id, embedding_dimension, embedding_hash, embedding, synthetic_only) "
            "VALUES (%s, %s, %s, %s, %s, %s::vector, true)"
        )
        self._assert_insert_rejected(duplicate_sql, (f'{self.prefix}-EMB-DUP', chunk_id, SYNTHETIC_MODEL_ID, SYNTHETIC_DIMENSION, self._embedding_hash(chunk_id + chunk_text), valid_vector))
        self._assert_insert_rejected(duplicate_sql, (f'{self.prefix}-EMB-WRONG-DIM', chunk_id, SYNTHETIC_MODEL_ID, 7, 'b' * 64, valid_vector))
        self._assert_insert_rejected(duplicate_sql, (f'{self.prefix}-EMB-OVERSIZED', chunk_id, SYNTHETIC_MODEL_ID, 4097, 'c' * 64, valid_vector))
        self._assert_insert_rejected(duplicate_sql, (f'{self.prefix}-EMB-NAN', chunk_id, SYNTHETIC_MODEL_ID, SYNTHETIC_DIMENSION, 'd' * 64, '[NaN,0,0,0,0,0,0,0]'))
        self._assert_insert_rejected(duplicate_sql, (f'{self.prefix}-EMB-INF', chunk_id, SYNTHETIC_MODEL_ID, SYNTHETIC_DIMENSION, 'e' * 64, '[Infinity,0,0,0,0,0,0,0]'))
        self._assert_insert_rejected(duplicate_sql, (f'{self.prefix}-EMB-STAGING', f'{self.prefix}-ST-CHUNK-0000-synthetic-respiratory-observ', SYNTHETIC_MODEL_ID, SYNTHETIC_DIMENSION, 'f' * 64, valid_vector))

        blocked_ids = {
            self._insert_extra_chunk(suffix='NON-SYN', synthetic_only=False, lifecycle_state='approved', retrieval_eligible=True, model_id=SYNTHETIC_MODEL_ID),
            self._insert_extra_chunk(suffix='NON-APPROVED', synthetic_only=True, lifecycle_state='quarantined', retrieval_eligible=True, model_id=SYNTHETIC_MODEL_ID),
            self._insert_extra_chunk(suffix='NON-ELIGIBLE', synthetic_only=True, lifecycle_state='approved', retrieval_eligible=False, model_id=SYNTHETIC_MODEL_ID),
            self._insert_extra_chunk(suffix='UNSUPPORTED-MODEL', synthetic_only=True, lifecycle_state='approved', retrieval_eligible=True, model_id='unsupported-synthetic-model'),
        }
        repo = RagRepository(self.conn)
        query_vector = generate_synthetic_vector('synthetic vector red team chunk NON-SYN')
        _release_id, rows = repo.fetch_active_vector(query_vector=query_vector, max_results=20)
        returned_ids = {str(row['chunk_id']) for row in rows}
        self.assertTrue(blocked_ids.isdisjoint(returned_ids))

        with self.conn.cursor() as cur:
            cur.execute('DELETE FROM rag_active_index_release WHERE pointer_name = %s', ('synthetic_p9b',))
        self.conn.commit()
        missing = retrieve_exact_cosine_vector(self.conn, 'breathing comfort', VectorRetrievalConfig(event_prefix=self.prefix))
        self.__class__.exact_cosine_queries_executed += 1
        self.assertFalse(missing.retrieved)
        self.assertEqual(missing.abstention.reason_code, 'no_active_synthetic_release')

        with self.conn.cursor() as cur:
            stale_release = f'{self.prefix}-REL-STALE'
            cur.execute(
                "INSERT INTO rag_index_release_manifests "
                "(release_id, release_version, release_hash, release_status, synthetic_only, authority, clinical_use_allowed, retrieval_backend) "
                "VALUES (%s, %s, %s, 'active', true, false, false, 'lexical')",
                (stale_release, stale_release + '-v1', 'a' * 64),
            )
            cur.execute(
                "INSERT INTO rag_active_index_release (pointer_name, release_id, activated_at) "
                "VALUES (%s, %s, CURRENT_TIMESTAMP) "
                "ON CONFLICT (pointer_name) DO UPDATE SET release_id = EXCLUDED.release_id, activated_at = CURRENT_TIMESTAMP",
                ('synthetic_p9b', stale_release),
            )
        self.conn.commit()
        stale = retrieve_exact_cosine_vector(self.conn, 'breathing comfort', VectorRetrievalConfig(event_prefix=self.prefix))
        self.__class__.exact_cosine_queries_executed += 1
        self.assertFalse(stale.retrieved)
        self.assertIn(stale.abstention.reason_code, {'below_minimum_rank', 'insufficient_result_count'})

    def test_cleanup_after_retrieval_and_benchmark_exception_paths(self):
        from rag_benchmark import BenchmarkQuery, run_vector_benchmark
        from rag_repository import RagRepository
        from rag_vector_retrieval import VectorRetrievalConfig, retrieve_exact_cosine_vector

        self._ingest_and_embed()
        with mock.patch('rag_repository.RagRepository.fetch_active_vector', side_effect=RuntimeError('raw failure must not leak')):
            retrieval = retrieve_exact_cosine_vector(
                self.conn,
                'breathing comfort',
                VectorRetrievalConfig(event_prefix=self.prefix),
            )
        self.__class__.exact_cosine_queries_executed += 1
        self.assertFalse(retrieval.retrieved)
        self.assertEqual(retrieval.abstention.reason_code, 'internal_safe_failure')

        try:
            with mock.patch('rag_benchmark.retrieve_exact_cosine_vector', side_effect=RuntimeError('synthetic benchmark failure')):
                with self.assertRaises(RuntimeError):
                    run_vector_benchmark(self.conn, (BenchmarkQuery('SYN-P9C-QX', 'breathing comfort', ('SYN-P9C-CHUNK',)),), top_k=5)
        finally:
            repo = RagRepository(self.conn)
            repo.cleanup_prefix(self.prefix)
            self.conn.commit()
        self.__class__.benchmark_runs += 1
        counts = repo.safe_counts(self.prefix)
        self.assertEqual(counts.synthetic_rows, 0)
        self.assertEqual(counts.temporary_staging_rows, 0)
        self.assertEqual(counts.active_synthetic_pointers, 0)


if __name__ == '__main__':
    unittest.main()
