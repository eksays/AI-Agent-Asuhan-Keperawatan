import unittest
from unittest.mock import patch, MagicMock

from backend.registry_migrations import run_migrations

class TestP8FMigrationSafety(unittest.TestCase):
    def test_idempotency_if_already_applied(self):
        # All migrations applied
        store = MagicMock()
        conn = MagicMock()
        store._get_conn.return_value = conn
        cur = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur

        # Return all versions as applied
        cur.fetchall.return_value = [("V001",), ("V002",), ("V003",), ("V004",), ("V005",), ("V006",), ("V007",)]

        applied = run_migrations(store)
        self.assertEqual(applied, [])
        # execute should only be called for V001 bootstrap and the SELECT
        # plus the bootstrap INSERT DO NOTHING

    def test_applies_unapplied_migrations_in_order(self):
        store = MagicMock()
        conn = MagicMock()
        store._get_conn.return_value = conn
        cur = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur

        # Return none as applied
        cur.fetchall.return_value = []

        applied = run_migrations(store)
        self.assertEqual(len(applied), 7)
        self.assertEqual(applied[0], 'V001')
        self.assertEqual(applied[-1], 'V007')

    def test_migration_failure_rolls_back(self):
        store = MagicMock()
        conn = MagicMock()
        store._get_conn.return_value = conn
        cur = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur

        cur.fetchall.return_value = []

        def side_effect(*args, **kwargs):
            if 'schema_migrations' in str(args[0]):
                raise RuntimeError("DB Error")
            return None

        cur.execute.side_effect = side_effect

        try:
            run_migrations(store)
        except Exception:
            pass

        self.assertTrue(conn.rollback.called)
