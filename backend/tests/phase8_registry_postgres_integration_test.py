"""Phase 8 P8-A — Optional PostgreSQL/Neon integration smoke tests.

These tests require a real PostgreSQL connection. They skip safely
when REGISTRY_DATABASE_URL and REGISTRY_DATABASE_ADMIN_URL are not set.

Safety:
- Uses synthetic-only data (SYN-* identifiers).
- Cleans up synthetic rows after each test.
- Never prints connection URLs or passwords.
- Never imports real registry data.
- Never activates registry grounding.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load only registry URLs from backend/.env without polluting the full process environment.
# This prevents side effects on other test modules when running under full discover.
try:
    from dotenv import dotenv_values as _dotenv_values
    _env_candidate = ROOT / '.env'
    if _env_candidate.exists():
        _env_vals = _dotenv_values(str(_env_candidate))
        for _key in ('REGISTRY_DATABASE_URL', 'REGISTRY_DATABASE_ADMIN_URL'):
            if _key not in os.environ and _key in _env_vals and _env_vals[_key]:
                os.environ[_key] = _env_vals[_key]
except ImportError:
    pass

# Skip entire module if no database URL is configured
_DB_URL = os.environ.get('REGISTRY_DATABASE_ADMIN_URL', '') or os.environ.get('REGISTRY_DATABASE_URL', '')
_SKIP_REASON = 'REGISTRY_DATABASE_URL or REGISTRY_DATABASE_ADMIN_URL not set; skipping remote integration tests.'


@unittest.skipUnless(_DB_URL, _SKIP_REASON)
class P8APostgresIntegrationTests(unittest.TestCase):
    """Remote PostgreSQL/Neon integration smoke tests with synthetic data only."""

    @classmethod
    def setUpClass(cls):
        from registry_store import load_registry_store_config, PostgresRegistryStore
        cls._config = load_registry_store_config(
            backend='postgres',
            database_url=_DB_URL,
            runtime_mode='synthetic_governance_test',
            activation_enabled=False,
        )
        cls._store = PostgresRegistryStore(cls._config)

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_synthetic()
        if hasattr(cls, '_store'):
            cls._store.close()

    @classmethod
    def _cleanup_synthetic(cls):
        """Remove all synthetic test data."""
        try:
            conn = cls._store._get_conn()
            with conn.cursor() as cur:
                # Clean up in reverse dependency order
                cur.execute("DELETE FROM release_history WHERE manifest_id LIKE 'SYN-%'")
                cur.execute("DELETE FROM active_releases WHERE manifest_id LIKE 'SYN-%'")
                cur.execute("DELETE FROM release_manifest_entries WHERE manifest_id LIKE 'SYN-%'")
                cur.execute("DELETE FROM release_manifests WHERE manifest_id LIKE 'SYN-%'")
                cur.execute("DELETE FROM approval_artifacts WHERE approval_id LIKE 'SYN-%'")
                cur.execute("DELETE FROM review_queue WHERE review_id LIKE 'SYN-%'")
                cur.execute("DELETE FROM entry_provenance WHERE entry_id LIKE 'SYN-%'")
                cur.execute("DELETE FROM registry_entries WHERE entry_id LIKE 'SYN-%'")
                cur.execute("DELETE FROM registry_sources WHERE source_id LIKE 'SYN-%'")
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

    def setUp(self):
        self._cleanup_synthetic()

    def tearDown(self):
        self._cleanup_synthetic()

    def test_connection_healthy(self):
        self.assertTrue(self._store.is_healthy())

    def test_migration_bootstrap(self):
        from registry_migrations import run_migrations
        applied = run_migrations(self._store)
        # May be empty if already applied
        self.assertIsInstance(applied, list)

    def test_schema_version_exists(self):
        from registry_migrations import run_migrations
        run_migrations(self._store)
        version = self._store.schema_version()
        self.assertIsNotNone(version)

    def test_migration_idempotency(self):
        from registry_migrations import run_migrations
        first = run_migrations(self._store)
        second = run_migrations(self._store)
        self.assertEqual(second, [], 'Second migration run should apply nothing.')

    def test_synthetic_source_insert(self):
        from registry_migrations import run_migrations
        run_migrations(self._store)
        conn = self._store._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO registry_sources (source_id, framework, source_title) "
                "VALUES (%s, %s, %s)",
                ('SYN-SOURCE-001', '3S', 'Synthetic Test Source'),
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT source_id FROM registry_sources WHERE source_id = %s", ('SYN-SOURCE-001',))
            row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'SYN-SOURCE-001')

    def test_synthetic_entry_insert(self):
        from registry_migrations import run_migrations
        run_migrations(self._store)
        conn = self._store._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO registry_sources (source_id, framework, source_title) "
                "VALUES (%s, %s, %s)",
                ('SYN-SOURCE-001', '3S', 'Synthetic Test Source'),
            )
            cur.execute(
                "INSERT INTO registry_entries (entry_id, source_id, framework, registry_family, entry_code, entry_name, content_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                ('SYN-D-001', 'SYN-SOURCE-001', '3S', 'SDKI', 'SYN.0001', 'Synthetic Diagnosis One', 'sha256:syn001'),
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT entry_id, lifecycle_state FROM registry_entries WHERE entry_id = %s", ('SYN-D-001',))
            row = cur.fetchone()
        self.assertEqual(row[0], 'SYN-D-001')
        self.assertEqual(row[1], 'quarantined')  # Default lifecycle state

    def test_foreign_key_enforcement(self):
        from registry_migrations import run_migrations
        import psycopg
        run_migrations(self._store)
        conn = self._store._get_conn()
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO registry_entries (entry_id, source_id, framework, registry_family, entry_code, content_hash) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    ('SYN-D-ORPHAN', 'SYN-NONEXISTENT-SOURCE', '3S', 'SDKI', 'SYN.9999', 'sha256:orphan'),
                )
        conn.rollback()

    def test_unique_constraint_enforcement(self):
        from registry_migrations import run_migrations
        import psycopg
        run_migrations(self._store)
        conn = self._store._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO registry_sources (source_id, framework, source_title) "
                "VALUES (%s, %s, %s)",
                ('SYN-SOURCE-001', '3S', 'Synthetic Test Source'),
            )
            cur.execute(
                "INSERT INTO registry_entries (entry_id, source_id, framework, registry_family, entry_code, entry_name, content_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                ('SYN-D-001', 'SYN-SOURCE-001', '3S', 'SDKI', 'SYN.0001', 'Synthetic Diagnosis One', 'sha256:syn001'),
            )
        conn.commit()
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO registry_entries (entry_id, source_id, framework, registry_family, entry_code, entry_name, content_hash) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    ('SYN-D-001-dup', 'SYN-SOURCE-001', '3S', 'SDKI', 'SYN.0001', 'Duplicate', 'sha256:syn001'),
                )
        conn.rollback()

    def test_transaction_rollback_on_failure(self):
        from registry_migrations import run_migrations
        run_migrations(self._store)
        conn = self._store._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO registry_sources (source_id, framework, source_title) "
                    "VALUES (%s, %s, %s)",
                    ('SYN-SOURCE-ROLLBACK', '3S', 'Will Rollback'),
                )
                # Force error
                cur.execute("SELECT invalid_column FROM nonexistent_table")
        except Exception:
            conn.rollback()
        # Verify the source was not persisted
        with conn.cursor() as cur:
            cur.execute("SELECT source_id FROM registry_sources WHERE source_id = %s", ('SYN-SOURCE-ROLLBACK',))
            row = cur.fetchone()
        self.assertIsNone(row)

    def test_no_real_registry_data(self):
        """Verify no real SDKI data exists in the database."""
        from registry_migrations import run_migrations
        run_migrations(self._store)
        conn = self._store._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM registry_entries "
                "WHERE entry_id NOT LIKE 'SYN-%'"
            )
            count = cur.fetchone()[0]
        self.assertEqual(count, 0, 'No real registry data should exist in the test database.')

    def test_synthetic_provenance_insert(self):
        from registry_migrations import run_migrations
        run_migrations(self._store)
        conn = self._store._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO registry_sources (source_id, framework, source_title) "
                "VALUES (%s, %s, %s)",
                ('SYN-SOURCE-001', '3S', 'Synthetic Test Source'),
            )
            cur.execute(
                "INSERT INTO registry_entries (entry_id, source_id, framework, registry_family, entry_code, content_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                ('SYN-D-001', 'SYN-SOURCE-001', '3S', 'SDKI', 'SYN.0001', 'sha256:syn001'),
            )
            cur.execute(
                "INSERT INTO entry_provenance (entry_id, extraction_method, extraction_tool, reviewer, notes) "
                "VALUES (%s, %s, %s, %s, %s)",
                ('SYN-D-001', 'manual', 'synthetic_test', 'closure_reviewer', 'P8-A closure test'),
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT entry_id, extraction_method FROM entry_provenance WHERE entry_id = %s", ('SYN-D-001',))
            row = cur.fetchone()
        self.assertEqual(row[0], 'SYN-D-001')
        self.assertEqual(row[1], 'manual')

    def test_synthetic_review_queue_insert(self):
        from registry_migrations import run_migrations
        run_migrations(self._store)
        conn = self._store._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO registry_sources (source_id, framework, source_title) "
                "VALUES (%s, %s, %s)",
                ('SYN-SOURCE-001', '3S', 'Synthetic Test Source'),
            )
            cur.execute(
                "INSERT INTO registry_entries (entry_id, source_id, framework, registry_family, entry_code, content_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                ('SYN-D-001', 'SYN-SOURCE-001', '3S', 'SDKI', 'SYN.0001', 'sha256:syn001'),
            )
            cur.execute(
                "INSERT INTO review_queue (review_id, entry_id, reviewer_id, review_status) "
                "VALUES (%s, %s, %s, %s)",
                ('SYN-RQ-001', 'SYN-D-001', 'synthetic_reviewer', 'pending'),
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT review_id, review_status FROM review_queue WHERE review_id = %s", ('SYN-RQ-001',))
            row = cur.fetchone()
        self.assertEqual(row[0], 'SYN-RQ-001')
        self.assertEqual(row[1], 'pending')

    def test_synthetic_approval_artifact_insert(self):
        from registry_migrations import run_migrations
        run_migrations(self._store)
        conn = self._store._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO registry_sources (source_id, framework, source_title) "
                "VALUES (%s, %s, %s)",
                ('SYN-SOURCE-001', '3S', 'Synthetic Test Source'),
            )
            cur.execute(
                "INSERT INTO registry_entries (entry_id, source_id, framework, registry_family, entry_code, content_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                ('SYN-D-001', 'SYN-SOURCE-001', '3S', 'SDKI', 'SYN.0001', 'sha256:syn001'),
            )
            cur.execute(
                "INSERT INTO review_queue (review_id, entry_id, reviewer_id, review_status) "
                "VALUES (%s, %s, %s, %s)",
                ('SYN-RQ-001', 'SYN-D-001', 'synthetic_reviewer', 'approved'),
            )
            cur.execute(
                "INSERT INTO approval_artifacts (approval_id, review_id, entry_id, approver_id, approval_decision, content_hash_at_approval) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                ('SYN-AA-001', 'SYN-RQ-001', 'SYN-D-001', 'synthetic_approver', 'approved', 'sha256:syn001'),
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT approval_id, approval_decision FROM approval_artifacts WHERE approval_id = %s", ('SYN-AA-001',))
            row = cur.fetchone()
        self.assertEqual(row[0], 'SYN-AA-001')
        self.assertEqual(row[1], 'approved')

    def test_synthetic_release_manifest_insert(self):
        from registry_migrations import run_migrations
        run_migrations(self._store)
        conn = self._store._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO release_manifests (manifest_id, framework, release_version, manifest_hash, status) "
                "VALUES (%s, %s, %s, %s, %s)",
                ('SYN-RM-001', '3S', 'SYN-v0.0.1', 'sha256:manifest001', 'candidate'),
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT manifest_id, status FROM release_manifests WHERE manifest_id = %s", ('SYN-RM-001',))
            row = cur.fetchone()
        self.assertEqual(row[0], 'SYN-RM-001')
        self.assertEqual(row[1], 'candidate')

    def test_synthetic_manifest_entry_insert(self):
        from registry_migrations import run_migrations
        run_migrations(self._store)
        conn = self._store._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO registry_sources (source_id, framework, source_title) "
                "VALUES (%s, %s, %s)",
                ('SYN-SOURCE-001', '3S', 'Synthetic Test Source'),
            )
            cur.execute(
                "INSERT INTO registry_entries (entry_id, source_id, framework, registry_family, entry_code, content_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                ('SYN-D-001', 'SYN-SOURCE-001', '3S', 'SDKI', 'SYN.0001', 'sha256:syn001'),
            )
            cur.execute(
                "INSERT INTO release_manifests (manifest_id, framework, release_version) "
                "VALUES (%s, %s, %s)",
                ('SYN-RM-001', '3S', 'SYN-v0.0.1'),
            )
            cur.execute(
                "INSERT INTO release_manifest_entries (manifest_id, entry_id, registry_family, content_hash) "
                "VALUES (%s, %s, %s, %s)",
                ('SYN-RM-001', 'SYN-D-001', 'SDKI', 'sha256:syn001'),
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT manifest_id, entry_id FROM release_manifest_entries WHERE manifest_id = %s", ('SYN-RM-001',))
            row = cur.fetchone()
        self.assertEqual(row[0], 'SYN-RM-001')
        self.assertEqual(row[1], 'SYN-D-001')

    def test_active_releases_table_exists(self):
        from registry_migrations import run_migrations
        run_migrations(self._store)
        conn = self._store._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = 'active_releases'"
            )
            count = cur.fetchone()[0]
        self.assertEqual(count, 1)

    def test_release_history_table_exists(self):
        from registry_migrations import run_migrations
        run_migrations(self._store)
        conn = self._store._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = 'release_history'"
            )
            count = cur.fetchone()[0]
        self.assertEqual(count, 1)

    def test_activation_remains_false(self):
        self.assertFalse(self._config.activation_enabled)

    def test_cleanup_removes_all_synthetic(self):
        from registry_migrations import run_migrations
        run_migrations(self._store)
        conn = self._store._get_conn()
        # Insert synthetic data
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO registry_sources (source_id, framework, source_title) "
                "VALUES (%s, %s, %s)",
                ('SYN-SOURCE-CLEANUP', '3S', 'Cleanup Test'),
            )
        conn.commit()
        # Run cleanup
        self._cleanup_synthetic()
        # Verify gone
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM registry_sources WHERE source_id LIKE 'SYN-%'")
            count = cur.fetchone()[0]
        self.assertEqual(count, 0, 'Cleanup should remove all SYN-* rows.')

    def test_no_data_terstruktur_loading(self):
        """Verify registry_store and registry_migrations never reference data_terstruktur."""
        import registry_store
        import registry_migrations
        for mod in (registry_store, registry_migrations):
            source = open(mod.__file__, 'r', encoding='utf-8').read()
            self.assertNotIn('data_terstruktur', source)


if __name__ == '__main__':
    unittest.main()
