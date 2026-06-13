from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class P10A1RagMigrationStaticTests(unittest.TestCase):
    def test_prior_migrations_checksums_and_sql_bytes_are_unmutated(self):
        from rag_migrations import CORE_MIGRATIONS

        # Verify that all migrations up to CORE_V006 are unaltered
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
                self.assertEqual(m.checksum, expected_checksums[m.migration_id], f"Checksum mismatch for migration {m.migration_id}")

    def test_new_migration_is_appended_correctly(self):
        from rag_migrations import CORE_MIGRATIONS

        last_migration = CORE_MIGRATIONS[-1]
        self.assertEqual(last_migration.migration_id, "RAG_CORE_V008")
        self.assertEqual(last_migration.migration_name, "create governed corpus intake companion metadata tables")

    def test_migration_sql_safety_rules(self):
        from rag_migrations import MIGRATION_RAG_CORE_V008

        sql = MIGRATION_RAG_CORE_V008.sql.lower()

        # Verify required tables are declared
        self.assertIn("rag_intake_submissions", sql)
        self.assertIn("rag_intake_decision_events", sql)
        self.assertIn("rag_intake_quarantine_records", sql)

        # Verify absolutely no body/excerpt/etc storage columns exist
        forbidden_columns = (
            "body", "excerpt", "prompt", "query", "raw_query", "url", "path",
            "credential", "credentials", "patient_identifier"
        )
        for term in forbidden_columns:
            # Check if it occurs as a column definition (e.g. " term " or " term_")
            self.assertNotIn(f" {term} ", sql)
            self.assertNotIn(f"\n    {term} ", sql)
            self.assertNotIn(f"\t{term} ", sql)

        # Verify constraints are present
        self.assertIn("synthetic_only = true", sql)
        self.assertIn("contains_patient_data = false", sql)
        self.assertIn("contains_phi = false", sql)
        self.assertIn("clinical_use_allowed = false", sql)

        # Verify no ANN index/HNSW/IVFFlat/Qdrant or extensions are mentioned
        self.assertNotIn("hnsw", sql)
        self.assertNotIn("ivfflat", sql)
        self.assertNotIn("qdrant", sql)
        self.assertNotIn("create extension", sql)


if __name__ == "__main__":
    unittest.main()
