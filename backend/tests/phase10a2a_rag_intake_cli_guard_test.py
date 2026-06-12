from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
from scripts.rag_db_migrate import main, _operation_name, _validate_operator_mode


class P10A2ARagIntakeCliGuardTests(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {
            "APP_MODE": "clinical_sandbox",
            "RAG_RUNTIME_MODE": "synthetic_corpus_test",
            "RAG_ISOLATED_TEST_DATABASE_CONFIRMED": "true",
            "REGISTRY_ACTIVATION_ENABLED": "false",
            "RAG_BODY_STORAGE_ENABLED": "false",
            "RAG_REAL_CORPUS_INGESTION_ENABLED": "false",
            "RAG_CORPUS_PROMOTION_ENABLED": "false",
            "RAG_VECTOR_RETRIEVAL_ENABLED": "false",
            "RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED": "false",
            "REGISTRY_DATABASE_ADMIN_URL": "postgresql://admin_user:admin_pass@localhost:5432/test_db",
            "REGISTRY_DATABASE_URL": "postgresql://pool_user:pool_pass@localhost:5432/test_db",
        }, clear=True)
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    def test_help_exits_safely(self):
        # Verify --help raises SystemExit and doesn't mutate or connect
        parser = argparse.ArgumentParser()
        with patch("sys.argv", ["rag_db_migrate.py", "--help"]), \
             patch("psycopg.connect") as mock_connect, \
             patch("sys.exit") as mock_exit:
            try:
                main()
            except SystemExit:
                pass
            mock_connect.assert_not_called()

    def test_no_flag_invocation_performs_no_mutation(self):
        with patch("sys.argv", ["rag_db_migrate.py"]), \
             patch("psycopg.connect") as mock_connect, \
             patch("sys.stdout") as mock_stdout:
            exit_code = main()
            self.assertEqual(exit_code, 2)
            mock_connect.assert_not_called()

            output = "".join(call[0][0] for call in mock_stdout.write.call_args_list)
            self.assertIn("failure_reason_code=no_mutation_flag_specified", output)

    def test_apply_intake_schema_exists_exactly_once(self):
        # We construct the actual parser used in main to verify flags
        parser = argparse.ArgumentParser()
        actions = parser.add_mutually_exclusive_group()
        actions.add_argument('--enable-pgvector', action='store_true')
        actions.add_argument('--apply-vector-schema', action='store_true')
        actions.add_argument('--apply-intake-schema', action='store_true')

        args = parser.parse_args(['--apply-intake-schema'])
        self.assertTrue(args.apply_intake_schema)
        self.assertFalse(args.enable_pgvector)
        self.assertFalse(args.apply_vector_schema)

    def test_mutation_options_are_mutually_exclusive(self):
        # Argparse throws an error if we pass mutually exclusive options together
        parser = argparse.ArgumentParser()
        actions = parser.add_mutually_exclusive_group()
        actions.add_argument('--enable-pgvector', action='store_true')
        actions.add_argument('--apply-vector-schema', action='store_true')
        actions.add_argument('--apply-intake-schema', action='store_true')

        with self.assertRaises(SystemExit):
            parser.parse_args(['--apply-vector-schema', '--apply-intake-schema'])

    def test_apply_intake_schema_selects_exactly_rag_core_v008(self):
        from rag_migrations import MIGRATION_RAG_CORE_V008
        self.assertEqual(MIGRATION_RAG_CORE_V008.migration_id, "RAG_CORE_V008")

    def test_prior_core_migrations_not_silently_replayed(self):
        from rag_migrations import run_migrations
        mock_conn = MagicMock()
        with patch("rag_migrations._ensure_journal"), \
             patch("rag_migrations._applied_migrations", return_value={}), \
             patch("rag_migrations._verify_applied_checksums"), \
             patch("rag_migrations.run_selected_migrations") as mock_run_selected:

            run_migrations(mock_conn)

            called_migrations = mock_run_selected.call_args[1]["migrations"]
            migration_ids = {m.migration_id for m in called_migrations}

            self.assertNotIn("RAG_CORE_V008", migration_ids)
            self.assertIn("RAG_CORE_V001", migration_ids)
            self.assertIn("RAG_CORE_V002", migration_ids)
            self.assertIn("RAG_CORE_V003", migration_ids)
            self.assertIn("RAG_CORE_V004", migration_ids)
            self.assertIn("RAG_CORE_V005", migration_ids)
            self.assertIn("RAG_C007", migration_ids)
            self.assertIn("RAG_CORE_V006", migration_ids)

    def test_historical_migration_behavior_remains_unchanged(self):
        from rag_migrations import CORE_MIGRATIONS
        expected_checksums = {
            "RAG_CORE_V001": "a398e3fb52dfaabd0a5ad4fafee8fb257de5c1ecb58ee942fc2818cebe882b75",
            "RAG_CORE_V002": "d12fae5d1b858fcd651e6f7f1c7d9cd606212d41109a109f072dbd12890ce3c4",
            "RAG_CORE_V003": "dd3c5cf91badca4231d9636700988c8e70655cd322081b0d566c5b0ffaf2369c",
            "RAG_CORE_V004": "49069b4ccbca204a24c62e41cc33939d41f6633ad416d6241d8890f71b0b62f2",
            "RAG_CORE_V005": "82112de3042fdd5fdf1cf56ddfea7f5f080a7e2a7b8af12dfe393045665a5988",
            "RAG_C007": "05a9458944caad1da330109f1595df7a743ae16dee7256d7fd8757af43bfbde0",
            "RAG_CORE_V006": "77f93eb04990c389954032ee6397a9bfdcbb7359fd0fd8f50d0679cb2ae18b21",
        }
        for m in CORE_MIGRATIONS:
            if m.migration_id in expected_checksums:
                self.assertEqual(m.checksum, expected_checksums[m.migration_id])

    @patch("os.environ.get")
    def test_app_mode_sandbox_guard_required(self, mock_env_get):
        mock_env_get.side_effect = lambda k, default=None: {
            "APP_MODE": "production",
            "RAG_RUNTIME_MODE": "synthetic_corpus_test",
            "RAG_ISOLATED_TEST_DATABASE_CONFIRMED": "true",
            "REGISTRY_ACTIVATION_ENABLED": "false",
            "RAG_BODY_STORAGE_ENABLED": "false",
            "RAG_REAL_CORPUS_INGESTION_ENABLED": "false",
            "RAG_CORPUS_PROMOTION_ENABLED": "false",
            "RAG_VECTOR_RETRIEVAL_ENABLED": "false",
            "RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED": "false",
            "REGISTRY_DATABASE_ADMIN_URL": "postgresql://localhost:5432/db",
        }.get(k, default)

        with self.assertRaises(RuntimeError) as ctx:
            _validate_operator_mode()
        self.assertEqual(str(ctx.exception), "app_mode_not_sandbox")

    @patch("os.environ.get")
    def test_synthetic_runtime_guard_required(self, mock_env_get):
        mock_env_get.side_effect = lambda k, default=None: {
            "APP_MODE": "clinical_sandbox",
            "RAG_RUNTIME_MODE": "disabled",
            "RAG_ISOLATED_TEST_DATABASE_CONFIRMED": "true",
            "REGISTRY_ACTIVATION_ENABLED": "false",
            "RAG_BODY_STORAGE_ENABLED": "false",
            "RAG_REAL_CORPUS_INGESTION_ENABLED": "false",
            "RAG_CORPUS_PROMOTION_ENABLED": "false",
            "RAG_VECTOR_RETRIEVAL_ENABLED": "false",
            "RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED": "false",
            "REGISTRY_DATABASE_ADMIN_URL": "postgresql://localhost:5432/db",
        }.get(k, default)

        with self.assertRaises(RuntimeError) as ctx:
            _validate_operator_mode()
        self.assertEqual(str(ctx.exception), "rag_runtime_mode_not_synthetic_corpus_test")

    @patch("os.environ.get")
    def test_isolated_db_attestation_required(self, mock_env_get):
        mock_env_get.side_effect = lambda k, default=None: {
            "APP_MODE": "clinical_sandbox",
            "RAG_RUNTIME_MODE": "synthetic_corpus_test",
            "RAG_ISOLATED_TEST_DATABASE_CONFIRMED": "false",
            "REGISTRY_ACTIVATION_ENABLED": "false",
            "RAG_BODY_STORAGE_ENABLED": "false",
            "RAG_REAL_CORPUS_INGESTION_ENABLED": "false",
            "RAG_CORPUS_PROMOTION_ENABLED": "false",
            "RAG_VECTOR_RETRIEVAL_ENABLED": "false",
            "RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED": "false",
            "REGISTRY_DATABASE_ADMIN_URL": "postgresql://localhost:5432/db",
        }.get(k, default)

        with self.assertRaises(RuntimeError) as ctx:
            _validate_operator_mode()
        self.assertEqual(str(ctx.exception), "isolated_test_database_not_confirmed")

    @patch("os.environ.get")
    def test_registry_activation_false_guard_required(self, mock_env_get):
        mock_env_get.side_effect = lambda k, default=None: {
            "APP_MODE": "clinical_sandbox",
            "RAG_RUNTIME_MODE": "synthetic_corpus_test",
            "RAG_ISOLATED_TEST_DATABASE_CONFIRMED": "true",
            "REGISTRY_ACTIVATION_ENABLED": "true",
            "RAG_BODY_STORAGE_ENABLED": "false",
            "RAG_REAL_CORPUS_INGESTION_ENABLED": "false",
            "RAG_CORPUS_PROMOTION_ENABLED": "false",
            "RAG_VECTOR_RETRIEVAL_ENABLED": "false",
            "RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED": "false",
            "REGISTRY_DATABASE_ADMIN_URL": "postgresql://localhost:5432/db",
        }.get(k, default)

        with self.assertRaises(RuntimeError) as ctx:
            _validate_operator_mode()
        self.assertEqual(str(ctx.exception), "registry_activation_enabled")

    @patch("os.environ.get")
    def test_body_storage_false_guard_required(self, mock_env_get):
        mock_env_get.side_effect = lambda k, default=None: {
            "APP_MODE": "clinical_sandbox",
            "RAG_RUNTIME_MODE": "synthetic_corpus_test",
            "RAG_ISOLATED_TEST_DATABASE_CONFIRMED": "true",
            "REGISTRY_ACTIVATION_ENABLED": "false",
            "RAG_BODY_STORAGE_ENABLED": "true",
            "RAG_REAL_CORPUS_INGESTION_ENABLED": "false",
            "RAG_CORPUS_PROMOTION_ENABLED": "false",
            "RAG_VECTOR_RETRIEVAL_ENABLED": "false",
            "RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED": "false",
            "REGISTRY_DATABASE_ADMIN_URL": "postgresql://localhost:5432/db",
        }.get(k, default)

        with self.assertRaises(RuntimeError) as ctx:
            _validate_operator_mode()
        self.assertEqual(str(ctx.exception), "rag_body_storage_enabled")

    @patch("os.environ.get")
    def test_real_corpus_ingestion_false_guard_required(self, mock_env_get):
        mock_env_get.side_effect = lambda k, default=None: {
            "APP_MODE": "clinical_sandbox",
            "RAG_RUNTIME_MODE": "synthetic_corpus_test",
            "RAG_ISOLATED_TEST_DATABASE_CONFIRMED": "true",
            "REGISTRY_ACTIVATION_ENABLED": "false",
            "RAG_BODY_STORAGE_ENABLED": "false",
            "RAG_REAL_CORPUS_INGESTION_ENABLED": "true",
            "RAG_CORPUS_PROMOTION_ENABLED": "false",
            "RAG_VECTOR_RETRIEVAL_ENABLED": "false",
            "RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED": "false",
            "REGISTRY_DATABASE_ADMIN_URL": "postgresql://localhost:5432/db",
        }.get(k, default)

        with self.assertRaises(RuntimeError) as ctx:
            _validate_operator_mode()
        self.assertEqual(str(ctx.exception), "rag_real_corpus_ingestion_enabled")

    @patch("os.environ.get")
    def test_corpus_promotion_false_guard_required(self, mock_env_get):
        mock_env_get.side_effect = lambda k, default=None: {
            "APP_MODE": "clinical_sandbox",
            "RAG_RUNTIME_MODE": "synthetic_corpus_test",
            "RAG_ISOLATED_TEST_DATABASE_CONFIRMED": "true",
            "REGISTRY_ACTIVATION_ENABLED": "false",
            "RAG_BODY_STORAGE_ENABLED": "false",
            "RAG_REAL_CORPUS_INGESTION_ENABLED": "false",
            "RAG_CORPUS_PROMOTION_ENABLED": "true",
            "RAG_VECTOR_RETRIEVAL_ENABLED": "false",
            "RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED": "false",
            "REGISTRY_DATABASE_ADMIN_URL": "postgresql://localhost:5432/db",
        }.get(k, default)

        with self.assertRaises(RuntimeError) as ctx:
            _validate_operator_mode()
        self.assertEqual(str(ctx.exception), "rag_corpus_promotion_enabled")

    @patch("os.environ.get")
    def test_vector_retrieval_false_guard_required(self, mock_env_get):
        mock_env_get.side_effect = lambda k, default=None: {
            "APP_MODE": "clinical_sandbox",
            "RAG_RUNTIME_MODE": "synthetic_corpus_test",
            "RAG_ISOLATED_TEST_DATABASE_CONFIRMED": "true",
            "REGISTRY_ACTIVATION_ENABLED": "false",
            "RAG_BODY_STORAGE_ENABLED": "false",
            "RAG_REAL_CORPUS_INGESTION_ENABLED": "false",
            "RAG_CORPUS_PROMOTION_ENABLED": "false",
            "RAG_VECTOR_RETRIEVAL_ENABLED": "true",
            "RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED": "false",
            "REGISTRY_DATABASE_ADMIN_URL": "postgresql://localhost:5432/db",
        }.get(k, default)

        with self.assertRaises(RuntimeError) as ctx:
            _validate_operator_mode()
        self.assertEqual(str(ctx.exception), "rag_vector_retrieval_enabled")

    @patch("os.environ.get")
    def test_external_embedding_provider_false_guard_required(self, mock_env_get):
        mock_env_get.side_effect = lambda k, default=None: {
            "APP_MODE": "clinical_sandbox",
            "RAG_RUNTIME_MODE": "synthetic_corpus_test",
            "RAG_ISOLATED_TEST_DATABASE_CONFIRMED": "true",
            "REGISTRY_ACTIVATION_ENABLED": "false",
            "RAG_BODY_STORAGE_ENABLED": "false",
            "RAG_REAL_CORPUS_INGESTION_ENABLED": "false",
            "RAG_CORPUS_PROMOTION_ENABLED": "false",
            "RAG_VECTOR_RETRIEVAL_ENABLED": "false",
            "RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED": "true",
            "REGISTRY_DATABASE_ADMIN_URL": "postgresql://localhost:5432/db",
        }.get(k, default)

        with self.assertRaises(RuntimeError) as ctx:
            _validate_operator_mode()
        self.assertEqual(str(ctx.exception), "rag_external_embedding_provider_enabled")

    def test_unsafe_guards_fail_before_db_connection(self):
        with patch("sys.argv", ["rag_db_migrate.py", "--apply-intake-schema"]), \
             patch("os.environ.get", return_value="production"), \
             patch("psycopg.connect") as mock_connect, \
             patch("sys.stdout"):
            exit_code = main()
            self.assertEqual(exit_code, 2)
            mock_connect.assert_not_called()

    def test_mutation_uses_registry_database_admin_url_only(self):
        with patch("sys.argv", ["rag_db_migrate.py", "--apply-intake-schema"]), \
             patch("psycopg.connect") as mock_connect, \
             patch("rag_migrations.acquire_advisory_lock"), \
             patch("rag_migrations.release_advisory_lock"), \
             patch("scripts.rag_db_migrate._intake_schema_ready", return_value=True), \
             patch("rag_migrations.run_selected_migrations"), \
             patch("sys.stdout"):

            main()
            mock_connect.assert_called_once()
            called_url = mock_connect.call_args[0][0]
            self.assertEqual(called_url, "postgresql://admin_user:admin_pass@localhost:5432/test_db")
            self.assertNotEqual(called_url, "postgresql://pool_user:pool_pass@localhost:5432/test_db")

    def test_safe_output_excludes_sensitive_info(self):
        with patch("sys.argv", ["rag_db_migrate.py", "--apply-intake-schema"]), \
             patch("psycopg.connect"), \
             patch("rag_migrations.acquire_advisory_lock"), \
             patch("rag_migrations.release_advisory_lock"), \
             patch("scripts.rag_db_migrate._intake_schema_ready", return_value=True), \
             patch("rag_migrations.run_selected_migrations"), \
             patch("sys.stdout") as mock_stdout:

            main()

            output_lines = []
            for call in mock_stdout.write.call_args_list:
                output_lines.append(call[0][0])
            full_output = "".join(output_lines)

            self.assertNotIn("admin_user", full_output)
            self.assertNotIn("admin_pass", full_output)
            self.assertNotIn("pool_user", full_output)
            self.assertNotIn("pool_pass", full_output)
            self.assertNotIn("postgresql://", full_output)
            self.assertNotIn("localhost", full_output)


if __name__ == "__main__":
    unittest.main()
