from __future__ import annotations

import inspect
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class P9ARagConfigTests(unittest.TestCase):
    def test_rag_defaults_are_disabled(self):
        from config import build_capabilities, load_config

        cfg = load_config({'APP_MODE': 'clinical_sandbox'})
        self.assertEqual(cfg.rag_runtime_mode, 'disabled')
        self.assertFalse(cfg.rag_store_enabled)
        self.assertFalse(cfg.rag_ingestion_enabled)
        self.assertFalse(cfg.rag_lexical_retrieval_enabled)
        self.assertFalse(cfg.rag_vector_retrieval_enabled)
        self.assertFalse(cfg.rag_index_activation_enabled)
        self.assertFalse(cfg.rag_external_embedding_provider_enabled)
        self.assertFalse(cfg.rag_db_mutation_allowed)
        caps = build_capabilities(cfg)['capabilities']
        self.assertFalse(caps['rag_lexical_retrieval']['enabled'])
        self.assertFalse(caps['rag_vector_retrieval']['enabled'])
        self.assertFalse(caps['rag_external_embedding_provider']['enabled'])
        self.assertFalse(caps['rag_index_activation']['enabled'])

    def test_rag_flags_do_not_enable_registry_or_external_provider(self):
        from config import load_config

        cfg = load_config({
            'APP_MODE': 'clinical_sandbox',
            'RAG_RUNTIME_MODE': 'synthetic_corpus_test',
            'RAG_STORE_ENABLED': 'true',
            'RAG_INGESTION_ENABLED': 'true',
            'RAG_LEXICAL_RETRIEVAL_ENABLED': 'true',
            'REGISTRY_ACTIVATION_ENABLED': 'false',
        })
        self.assertFalse(cfg.registry_activation_enabled)
        self.assertFalse(cfg.external_llm_enabled)
        self.assertFalse(cfg.ebp_external_search_enabled)
        self.assertFalse(cfg.rag_vector_retrieval_enabled)
        self.assertFalse(cfg.rag_external_embedding_provider_enabled)
        self.assertTrue(cfg.rag_db_mutation_allowed)

    def test_synthetic_corpus_mode_is_sandbox_only(self):
        from config import load_config

        with self.assertRaises(RuntimeError):
            load_config({
                'APP_MODE': 'controlled_pilot',
                'RAG_RUNTIME_MODE': 'synthetic_corpus_test',
            })

    def test_experimental_rag_flags_rejected_outside_sandbox(self):
        from config import load_config

        with self.assertRaises(RuntimeError):
            load_config({
                'APP_MODE': 'controlled_pilot',
                'RAG_STORE_ENABLED': 'true',
            })

    def test_vector_and_activation_flags_rejected_in_p9a(self):
        from config import load_config

        for flag in ('RAG_VECTOR_RETRIEVAL_ENABLED', 'RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED', 'RAG_INDEX_ACTIVATION_ENABLED'):
            env = {
                'APP_MODE': 'clinical_sandbox',
                'RAG_RUNTIME_MODE': 'synthetic_corpus_test',
                flag: 'true',
            }
            with self.subTest(flag=flag), self.assertRaises(RuntimeError):
                load_config(env)

    def test_rag_mutation_rejected_when_registry_activation_true(self):
        from config import load_config

        with self.assertRaises(RuntimeError):
            load_config({
                'APP_MODE': 'clinical_sandbox',
                'RAG_RUNTIME_MODE': 'synthetic_corpus_test',
                'REGISTRY_ACTIVATION_ENABLED': 'true',
            })


class P9ARagMigrationDefinitionTests(unittest.TestCase):
    def _core_sql(self) -> str:
        from rag_migrations import CORE_MIGRATIONS

        return '\n'.join(m.sql for m in CORE_MIGRATIONS).lower()

    def _all_sql(self) -> str:
        from rag_migrations import CORE_MIGRATIONS, PGVECTOR_MIGRATIONS

        return '\n'.join(m.sql for m in (*CORE_MIGRATIONS, *PGVECTOR_MIGRATIONS)).lower()

    def test_rag_migrations_are_separate_from_registry_migrations(self):
        import rag_migrations

        self.assertTrue(Path(rag_migrations.__file__).name, 'rag_migrations.py')
        registry_source = (ROOT / 'registry_migrations.py').read_text(encoding='utf-8')
        self.assertNotIn('rag_schema_migrations', registry_source)
        self.assertNotIn('rag_sources', registry_source)

    def test_journal_contains_checksum_columns(self):
        from rag_migrations import MIGRATION_RAG_CORE_V001

        sql = MIGRATION_RAG_CORE_V001.sql.lower()
        for column in ('migration_id', 'migration_name', 'migration_checksum', 'applied_at'):
            self.assertIn(column, sql)

    def test_checksum_mismatch_fails_closed(self):
        from rag_migrations import CORE_MIGRATIONS, RagMigrationError, _verify_applied_checksums

        with self.assertRaises(RagMigrationError):
            _verify_applied_checksums({CORE_MIGRATIONS[0].migration_id: '0' * 64}, CORE_MIGRATIONS)

    def test_migration_ids_are_unique_and_ordered(self):
        from rag_migrations import CORE_MIGRATIONS, PGVECTOR_MIGRATIONS

        ids = [m.migration_id for m in (*CORE_MIGRATIONS, *PGVECTOR_MIGRATIONS)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[:2], ['RAG_CORE_V001', 'RAG_CORE_V002'])

    def test_core_lexical_schema_does_not_require_pgvector(self):
        sql = self._core_sql()
        self.assertIn('rag_chunks', sql)
        self.assertIn('tsvector', sql)
        self.assertIn('using gin', sql)
        self.assertNotIn('create extension', sql)
        self.assertNotIn('rag_chunk_embeddings', sql)
        self.assertNotIn(' vector', sql)

    def test_optional_pgvector_schema_is_separate(self):
        from rag_migrations import PGVECTOR_MIGRATIONS

        sql = '\n'.join(m.sql for m in PGVECTOR_MIGRATIONS).lower()
        self.assertIn('create extension if not exists vector', sql)
        self.assertIn('rag_chunk_embeddings', sql)
        self.assertIn('embedding_model_id', sql)
        self.assertIn('embedding_dimension', sql)
        self.assertIn('embedding_hash', sql)

    def test_no_ann_indexes_are_defined(self):
        sql = self._all_sql()
        self.assertNotIn('hnsw', sql)
        self.assertNotIn('ivfflat', sql)
        self.assertNotIn('using hnsw', sql)
        self.assertNotIn('using ivfflat', sql)

    def test_required_tables_are_declared(self):
        sql = self._all_sql()
        for table in (
            'rag_sources', 'rag_source_versions', 'rag_ingestion_runs',
            'rag_ingestion_staging_documents', 'rag_ingestion_staging_chunks',
            'rag_documents', 'rag_chunks', 'rag_chunk_embeddings',
            'rag_index_release_manifests', 'rag_index_release_manifest_chunks',
            'rag_active_index_release', 'rag_index_release_history',
            'rag_retrieval_events',
        ):
            self.assertIn(table, sql)

    def test_staging_is_non_searchable_and_cannot_enter_manifests(self):
        sql = self._core_sql()
        self.assertIn('check (searchable = false)', sql)
        manifest_start = sql.index('create table if not exists rag_index_release_manifest_chunks')
        manifest_sql = sql[manifest_start:]
        self.assertIn('references rag_chunks', manifest_sql)
        self.assertNotIn('references rag_ingestion_staging_chunks', manifest_sql)

    def test_active_pointer_is_separate_and_empty_by_design(self):
        sql = self._core_sql()
        self.assertIn('create table if not exists rag_active_index_release', sql)
        self.assertIn('references rag_index_release_manifests', sql)
        self.assertNotIn('insert into rag_active_index_release', sql)

    def test_retrieval_telemetry_has_no_forbidden_columns(self):
        sql = self._core_sql()
        start = sql.index('create table if not exists rag_retrieval_events')
        telemetry_sql = sql[start:]
        forbidden = (
            'raw_query', 'raw_prompt', 'query_hash', 'query_fingerprint', 'query_hmac',
            'patient', 'phi', 'corpus_body', 'path', 'url', 'credential', 'exception',
            'stack_trace', 'database_url', 'hostname', 'password', 'secret',
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, telemetry_sql)
        self.assertIn('selected_chunk_count', telemetry_sql)
        self.assertIn('selected_chunk_count <= 20', telemetry_sql)
        self.assertIn('char_length(selected_chunk_ids) <= 4096', telemetry_sql)

    def test_synthetic_phi_canaries_absent_from_schema(self):
        sql = self._all_sql()
        for canary in ('budi santoso', '3273010101010001', '081234567890', 'mrn', 'rekam medis'):
            self.assertNotIn(canary, sql)


class P9ARagScriptSafetyTests(unittest.TestCase):
    def test_probe_script_is_read_only(self):
        import scripts.rag_db_probe as probe

        source = inspect.getsource(probe).lower()
        self.assertNotIn('run_migrations', source)
        self.assertNotIn('create extension', source)
        self.assertNotIn('insert into', source)
        self.assertNotIn('delete from', source)

    def test_migrate_script_requires_explicit_pgvector_flag(self):
        import scripts.rag_db_migrate as migrate

        source = inspect.getsource(migrate).lower()
        self.assertIn('--enable-pgvector', source)
        self.assertIn('args.enable_pgvector', source)
        self.assertIn('rag_runtime_mode_not_synthetic_corpus_test', source)
        self.assertIn('registry_activation_enabled', source)

    def test_advisory_lock_is_bounded(self):
        from rag_migrations import acquire_advisory_lock

        source = inspect.getsource(acquire_advisory_lock).lower()
        self.assertIn('pg_try_advisory_lock', source)
        self.assertIn('deadline', source)
        self.assertIn('timeout_sec', source)

    def test_api_startup_does_not_auto_migrate_or_install_extensions(self):
        api_source = (ROOT / 'api.py').read_text(encoding='utf-8').lower()
        self.assertNotIn('rag_db_migrate', api_source)
        self.assertNotIn('run_migrations(conn', api_source)
        self.assertNotIn('create extension if not exists vector', api_source)


if __name__ == '__main__':
    unittest.main()
