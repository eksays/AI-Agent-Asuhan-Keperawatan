from __future__ import annotations

import sys
import os
import unittest
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _enabled(raw: str) -> bool:
    return (raw or '').strip().lower() in {'1', 'true', 'yes', 'on'}


# Skip check configuration
_SHOULD_SKIP = not (
    _enabled(os.environ.get("P10A2_POSTGRES_INTEGRATION_TEST", "false"))
    and os.environ.get("APP_MODE", "").strip().lower() == "clinical_sandbox"
    and os.environ.get("RAG_RUNTIME_MODE", "").strip().lower() == "synthetic_corpus_test"
    and _enabled(os.environ.get("RAG_ISOLATED_TEST_DATABASE_CONFIRMED", "false"))
    and not _enabled(os.environ.get("REGISTRY_ACTIVATION_ENABLED", "false"))
    and not _enabled(os.environ.get("RAG_BODY_STORAGE_ENABLED", "false"))
    and not _enabled(os.environ.get("RAG_REAL_CORPUS_INGESTION_ENABLED", "false"))
    and not _enabled(os.environ.get("RAG_CORPUS_PROMOTION_ENABLED", "false"))
    and not _enabled(os.environ.get("RAG_VECTOR_RETRIEVAL_ENABLED", "false"))
    and not _enabled(os.environ.get("RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED", "false"))
)


@unittest.skipIf(_SHOULD_SKIP, "Skipping isolated PostgreSQL integration tests for P10-A2A review pass.")
class P10A2RagIntakePostgresIntegrationTests(unittest.TestCase):

    def setUp(self):
        # Database connection config from env (REGISTRY_DATABASE_ADMIN_URL)
        self.admin_url = os.environ.get("REGISTRY_DATABASE_ADMIN_URL", "").strip()
        if not self.admin_url:
            self.skipTest("REGISTRY_DATABASE_ADMIN_URL is missing.")

        import psycopg
        self.conn = psycopg.connect(self.admin_url, autocommit=False)

    def tearDown(self):
        if hasattr(self, "conn") and self.conn:
            self.conn.close()

    def test_postgres_integration_workflow(self):
        import psycopg

        # 1. Read pre-state
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'rag_schema_migrations'")
            has_journal = bool(cur.fetchone()[0])

        # 2. Invoke the explicit --apply-intake-schema path only via subprocess
        script_path = str(ROOT / "scripts" / "rag_db_migrate.py")
        res = subprocess.run(
            [sys.executable, script_path, "--apply-intake-schema"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.return_value if hasattr(res, "return_value") else res.returncode, 0, f"Migration script failed: {res.stderr}")

        # 3. Verify journal contains RAG_CORE_V008 with expected checksum
        with self.conn.cursor() as cur:
            cur.execute("SELECT migration_checksum FROM rag_schema_migrations WHERE migration_id = 'RAG_CORE_V008'")
            row = cur.fetchone()
            self.assertIsNotNone(row, "RAG_CORE_V008 migration was not applied.")
            checksum = row[0]

            from rag_migrations import MIGRATION_RAG_CORE_V008
            self.assertEqual(checksum, MIGRATION_RAG_CORE_V008.checksum)

        # 4. Verify exactly three intake companion tables exist
        expected_tables = {
            "rag_intake_submissions",
            "rag_intake_decision_events",
            "rag_intake_quarantine_records"
        }
        with self.conn.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_name IN ('rag_intake_submissions', 'rag_intake_decision_events', 'rag_intake_quarantine_records')")
            actual_tables = {row[0] for row in cur.fetchall()}
            self.assertEqual(actual_tables, expected_tables)

        # 5. Verify the actual database-column allowlist exactly
        expected_columns = {
            "rag_intake_submissions": {
                "source_id", "source_type", "source_title", "source_owner_ref", "source_version",
                "source_version_date", "license_status", "license_evidence_ref", "provenance_status",
                "provenance_evidence_ref", "content_hash", "content_language", "content_domain",
                "synthetic_only", "contains_patient_data", "contains_phi", "deidentification_disposition",
                "clinical_review_status", "qa_status", "retrieval_eligibility", "clinical_use_allowed",
                "retention_policy", "created_by_actor_ref", "cleanup_after", "created_at"
            },
            "rag_intake_decision_events": {
                "event_id", "source_id", "event_type", "reason_code", "created_by_actor_ref",
                "quarantine_reason", "created_at"
            },
            "rag_intake_quarantine_records": {
                "source_id", "quarantine_reason", "cleanup_after", "cleanup_disposition", "created_at"
            }
        }

        # 6. Verify forbidden columns are absent by verifying actual matches expected exactly
        for table, expected in expected_columns.items():
            with self.conn.cursor() as cur:
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,))
                actual = {row[0] for row in cur.fetchall()}
                self.assertEqual(actual, expected, f"Column mismatch in table {table}")

        # 7-13. Insert and verify synthetic metadata rows only using prefix SYN-P10A2-
        try:
            # Let's perform queries and check constraints
            # Insert standard SYN-P10A2- row
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rag_intake_submissions (
                        source_id, source_type, source_title, source_owner_ref, source_version,
                        source_version_date, license_status, license_evidence_ref, provenance_status,
                        provenance_evidence_ref, content_hash, content_language, content_domain,
                        synthetic_only, contains_patient_data, contains_phi, deidentification_disposition,
                        clinical_review_status, qa_status, retrieval_eligibility, clinical_use_allowed,
                        retention_policy, created_by_actor_ref, cleanup_after
                    ) VALUES (
                        'SYN-P10A2-SUB1', 'synthetic_fixture', 'Test Title', 'actor-1', '1.0',
                        '2026-06-12', 'approved', 'ref-1', 'approved',
                        'provenance-ref-1', 'a'*64, 'id', 'nursing',
                        TRUE, FALSE, FALSE, 'none',
                        'approved', 'passed', TRUE, FALSE,
                        'retain-30d', 'actor-ref-1', %s
                    )
                """, (datetime.now(timezone.utc) + timedelta(days=30),))

                # Check insert of event
                cur.execute("""
                    INSERT INTO rag_intake_decision_events (
                        event_id, source_id, event_type, reason_code, created_by_actor_ref, quarantine_reason
                    ) VALUES (
                        'SYN-P10A2-EV1', 'SYN-P10A2-SUB1', 'accept', 'policy_passed', 'actor-ref-1', ''
                    )
                """)

                # 9. Verify database constraints reject:
                # - synthetic_only=false
                with self.assertRaises(psycopg.Error):
                    cur.execute("UPDATE rag_intake_submissions SET synthetic_only = FALSE WHERE source_id = 'SYN-P10A2-SUB1'")
                self.conn.rollback()

                # - contains_patient_data=true
                with self.assertRaises(psycopg.Error):
                    cur.execute("UPDATE rag_intake_submissions SET contains_patient_data = TRUE WHERE source_id = 'SYN-P10A2-SUB1'")
                self.conn.rollback()

                # - contains_phi=true
                with self.assertRaises(psycopg.Error):
                    cur.execute("UPDATE rag_intake_submissions SET contains_phi = TRUE WHERE source_id = 'SYN-P10A2-SUB1'")
                self.conn.rollback()

                # - clinical_use_allowed=true
                with self.assertRaises(psycopg.Error):
                    cur.execute("UPDATE rag_intake_submissions SET clinical_use_allowed = TRUE WHERE source_id = 'SYN-P10A2-SUB1'")
                self.conn.rollback()

        finally:
            # 12. Delete all SYN-P10A2-* rows inside finally
            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM rag_intake_decision_events WHERE source_id LIKE 'SYN-P10A2-%'")
                cur.execute("DELETE FROM rag_intake_quarantine_records WHERE source_id LIKE 'SYN-P10A2-%'")
                cur.execute("DELETE FROM rag_intake_submissions WHERE source_id LIKE 'SYN-P10A2-%'")
            self.conn.commit()

        # 13. Verify synthetic intake rows remaining=0
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM rag_intake_submissions WHERE source_id LIKE 'SYN-P10A2-%'")
            self.assertEqual(cur.fetchone()[0], 0)

            cur.execute("SELECT COUNT(*) FROM rag_intake_decision_events WHERE source_id LIKE 'SYN-P10A2-%'")
            self.assertEqual(cur.fetchone()[0], 0)

            cur.execute("SELECT COUNT(*) FROM rag_intake_quarantine_records WHERE source_id LIKE 'SYN-P10A2-%'")
            self.assertEqual(cur.fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
