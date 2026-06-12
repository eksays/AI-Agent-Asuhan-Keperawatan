from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.rag_db_probe import main


@patch("scripts.rag_db_probe._load_env", lambda: None)
class P10A2ARagDbProbeTests(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {
            "APP_MODE": "clinical_sandbox",
            "RAG_RUNTIME_MODE": "disabled",
            "RAG_ISOLATED_TEST_DATABASE_CONFIRMED": "false",
            "REGISTRY_ACTIVATION_ENABLED": "false",
            "RAG_BODY_STORAGE_ENABLED": "false",
            "RAG_REAL_CORPUS_INGESTION_ENABLED": "false",
            "RAG_CORPUS_PROMOTION_ENABLED": "false",
            "REGISTRY_DATABASE_URL": "postgresql://pool_user:pool_pass@localhost:5432/test_db",
            "REGISTRY_DATABASE_ADMIN_URL": "",
        }, clear=True)
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    @patch("psycopg.connect")
    @patch("sys.stdout")
    def test_rag_runtime_mode_disabled(self, mock_stdout, mock_connect):
        os.environ["RAG_RUNTIME_MODE"] = "disabled"
        main()

        output = "".join(call[0][0] for call in mock_stdout.write.call_args_list)
        self.assertIn("rag_runtime_mode=disabled", output)

    @patch("psycopg.connect")
    @patch("sys.stdout")
    def test_rag_runtime_mode_synthetic_corpus_test(self, mock_stdout, mock_connect):
        os.environ["RAG_RUNTIME_MODE"] = "synthetic_corpus_test"
        main()

        output = "".join(call[0][0] for call in mock_stdout.write.call_args_list)
        self.assertIn("rag_runtime_mode=synthetic_corpus_test", output)

    @patch("psycopg.connect")
    @patch("sys.stdout")
    def test_unknown_runtime_mode_reports_unknown(self, mock_stdout, mock_connect):
        os.environ["RAG_RUNTIME_MODE"] = "some_invalid_mode"
        main()

        output = "".join(call[0][0] for call in mock_stdout.write.call_args_list)
        self.assertIn("rag_runtime_mode=unknown", output)

    @patch("psycopg.connect")
    @patch("sys.stdout")
    def test_table_readiness_booleans_exposed_as_false_when_missing(self, mock_stdout, mock_connect):
        # Mock connection and check tables missing
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        # mock _relation_exists to return False
        with patch("scripts.rag_db_probe._relation_exists", return_value=False):
            main()

        output = "".join(call[0][0] for call in mock_stdout.write.call_args_list)
        self.assertIn("rag_intake_schema_ready=false", output)
        self.assertIn("rag_intake_submissions_table_ready=false", output)
        self.assertIn("rag_intake_decision_events_table_ready=false", output)
        self.assertIn("rag_intake_quarantine_records_table_ready=false", output)

    @patch("psycopg.connect")
    @patch("sys.stdout")
    def test_flags_exposed_as_booleans(self, mock_stdout, mock_connect):
        main()

        output = "".join(call[0][0] for call in mock_stdout.write.call_args_list)
        self.assertIn("body_storage_enabled=false", output)
        self.assertIn("real_corpus_ingestion_enabled=false", output)
        self.assertIn("corpus_promotion_enabled=false", output)
        self.assertIn("isolated_test_database_operator_attestation=false", output)

    @patch("psycopg.connect")
    @patch("sys.stdout")
    def test_probe_executes_no_mutations_and_acquires_no_locks(self, mock_stdout, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value

        main()

        # Ensure it only executes select statements (to_regclass or pg_indexes)
        for call in mock_cur.execute.call_args_list:
            sql = call[0][0].lower()
            self.assertTrue(sql.startswith("select"))
            self.assertNotIn("insert", sql)
            self.assertNotIn("delete", sql)
            self.assertNotIn("update", sql)
            self.assertNotIn("create", sql)
            self.assertNotIn("alter", sql)
            self.assertNotIn("advisory", sql)  # No advisory lock

    @patch("psycopg.connect")
    @patch("sys.stdout")
    def test_probe_safe_output_excludes_credentials_and_errors(self, mock_stdout, mock_connect):
        mock_connect.side_effect = Exception("Failed connection raw error")
        main()

        output = "".join(call[0][0] for call in mock_stdout.write.call_args_list)

        # Check that no sensitive database details or connection strings are printed
        self.assertNotIn("pool_user", output)
        self.assertNotIn("pool_pass", output)
        self.assertNotIn("postgresql://", output)
        self.assertNotIn("localhost", output)
        self.assertNotIn("Failed connection raw error", output)
        self.assertIn("probe_error=true", output)


if __name__ == "__main__":
    unittest.main()
