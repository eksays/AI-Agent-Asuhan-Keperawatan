import unittest
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
import concurrent.futures
from unittest.mock import patch
import psycopg

from registry_store import RegistryStoreConfig, PostgresRegistryStore
from registry_runtime import _load_active_release
from registry_release_service import (
    activate_release,
    rollback_release,
    create_release_candidate,
    create_release_approval,
    get_release_history,
    get_active_release
)

@unittest.skipUnless(os.environ.get('NEON_INTEGRATION_TEST'), "NEON_INTEGRATION_TEST not set")
class TestP8FConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._p = "SYN-P8F-CONC-"
        cls.config = RegistryStoreConfig(
            backend='postgres',
            database_url=os.environ.get('REGISTRY_DATABASE_URL', ''),
            admin_url=os.environ.get('REGISTRY_DATABASE_ADMIN_URL', ''),
            activation_enabled=True,
            runtime_mode='synthetic_governance_test'
        )
        if not cls.config.database_url:
            raise unittest.SkipTest("Postgres backend not configured")

        cls.store = PostgresRegistryStore(cls.config)
        cls._cleanup()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup()

    def setUp(self):
        self._cleanup()

    @classmethod
    def _cleanup(cls):
        try:
            with psycopg.connect(cls.config.database_url) as conn:
                with conn.cursor() as cur:
                    for t in ['active_releases', 'release_history', 'release_manifest_entries',
                              'release_approval_artifacts', 'release_manifests']:
                        try:
                            if t == 'release_manifest_entries':
                                cur.execute(f"DELETE FROM {t} WHERE manifest_id LIKE %s", (f"{cls._p}%",))  # nosec B608
                            elif t == 'release_manifests':
                                cur.execute(f"DELETE FROM {t} WHERE manifest_id LIKE %s", (f"{cls._p}%",))  # nosec B608
                            elif t == 'active_releases':
                                cur.execute(f"DELETE FROM {t} WHERE framework = %s", (f"{cls._p}3S",))  # nosec B608
                            elif t == 'release_history':
                                cur.execute(f"DELETE FROM {t} WHERE framework = %s", (f"{cls._p}3S",))  # nosec B608
                            elif t == 'release_approval_artifacts':
                                cur.execute(f"DELETE FROM {t} WHERE manifest_id LIKE %s", (f"{cls._p}%",))  # nosec B608
                        except Exception:
                            conn.rollback()
        except Exception:
            pass

    def _setup_approved_manifest(self, m_id: str) -> str:
        with psycopg.connect(self.config.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO release_manifests (manifest_id, framework, release_version, status, manifest_hash) VALUES (%s, %s, 'v1', 'approved', 'hash')", (m_id, f"{self._p}3S"))
                cur.execute("INSERT INTO release_approval_artifacts (approval_id, manifest_id, approver_id, approval_decision, manifest_hash_at_approval) VALUES (%s, %s, 'clinical_director', 'approved', 'hash')", (m_id, m_id))
            conn.commit()
        return m_id

    def test_a_two_first_activation_writers(self):
        m1 = self._setup_approved_manifest(f"{self._p}M1")

        def activate():
            with psycopg.connect(self.config.database_url) as conn:
                return activate_release(conn, f"{self._p}3S", m1, activation_enabled=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(activate)
            f2 = executor.submit(activate)
            r1 = f1.result()
            r2 = f2.result()

        with psycopg.connect(self.config.database_url) as conn:
            history = get_release_history(conn, f"{self._p}3S")
            # Should have exactly two history events, or maybe one fails.
            # Actually activate_release doesn't fail if already active, it just activates again.
            self.assertEqual(len(history), 2)
            active = get_active_release(conn, f"{self._p}3S")
            self.assertEqual(active['manifest_id'], m1)

    def test_b_two_activations_against_existing(self):
        m1 = self._setup_approved_manifest(f"{self._p}M1")
        m2 = self._setup_approved_manifest(f"{self._p}M2")
        m3 = self._setup_approved_manifest(f"{self._p}M3")

        with psycopg.connect(self.config.database_url) as conn:
            activate_release(conn, f"{self._p}3S", m1, activation_enabled=True)

        def activate(m_id):
            with psycopg.connect(self.config.database_url) as conn:
                return activate_release(conn, f"{self._p}3S", m_id, activation_enabled=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f2 = executor.submit(activate, m2)
            f3 = executor.submit(activate, m3)
            f2.result()
            f3.result()

        with psycopg.connect(self.config.database_url) as conn:
            history = get_release_history(conn, f"{self._p}3S")
            self.assertEqual(len(history), 3) # M1, then M2/M3
            active = get_active_release(conn, f"{self._p}3S")
            self.assertIn(active['manifest_id'], [m2, m3])

    def test_c_activation_and_rollback_race(self):
        m1 = self._setup_approved_manifest(f"{self._p}M1")
        m2 = self._setup_approved_manifest(f"{self._p}M2")
        m3 = self._setup_approved_manifest(f"{self._p}M3")

        with psycopg.connect(self.config.database_url) as conn:
            activate_release(conn, f"{self._p}3S", m1, activation_enabled=True)
            activate_release(conn, f"{self._p}3S", m2, activation_enabled=True)

        def activate():
            with psycopg.connect(self.config.database_url) as conn:
                return activate_release(conn, f"{self._p}3S", m3, activation_enabled=True)

        def rollback():
            with psycopg.connect(self.config.database_url) as conn:
                return rollback_release(conn, f"{self._p}3S", m1, "race test", activation_enabled=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f_a = executor.submit(activate)
            f_r = executor.submit(rollback)
            f_a.result()
            f_r.result()

        with psycopg.connect(self.config.database_url) as conn:
            active = get_active_release(conn, f"{self._p}3S")
            # The active one will either be M3 or M1 depending on thread execution order,
            # but it MUST be exactly one valid release without corruption
            self.assertIn(active['manifest_id'], [m3, m1])

    def test_d_reader_during_activation(self):
        m1 = self._setup_approved_manifest(f"{self._p}M1")

        with psycopg.connect(self.config.database_url) as conn:
            activate_release(conn, f"{self._p}3S", m1, activation_enabled=True)

        m2 = self._setup_approved_manifest(f"{self._p}M2")

        # Start a slow activation
        def slow_activate():
            with psycopg.connect(self.config.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("BEGIN")
                    cur.execute("SELECT manifest_id FROM active_releases WHERE framework = %s FOR UPDATE", (f"{self._p}3S",))
                    time.sleep(1) # hold lock
                    cur.execute("UPDATE active_releases SET manifest_id = %s WHERE framework = %s", (m2, f"{self._p}3S"))
                    conn.commit()
                return True

        def reader():
            results = []
            for _ in range(5):
                time.sleep(0.3)
                with psycopg.connect(self.config.database_url) as conn:
                    # Reader should not block! `get_active_release` uses simple SELECT.
                    active = get_active_release(conn, f"{self._p}3S")
                    if active:
                        results.append(active['manifest_id'])
            return results

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f_w = executor.submit(slow_activate)
            f_r = executor.submit(reader)
            f_w.result()
            reads = f_r.result()

        self.assertTrue(all(r in [m1, m2] for r in reads), "Readers must never see partial state or missing pointer")

    def test_e_lock_timeout_disposition(self):
        m1 = self._setup_approved_manifest(f"{self._p}M1")
        m2 = self._setup_approved_manifest(f"{self._p}M2")

        with psycopg.connect(self.config.database_url) as conn:
            activate_release(conn, f"{self._p}3S", m1, activation_enabled=True)

        # Thread 1 holds the lock
        lock_held = [False]

        def hold_lock():
            with psycopg.connect(self.config.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("BEGIN")
                    cur.execute("SELECT manifest_id FROM active_releases WHERE framework = %s FOR UPDATE", (f"{self._p}3S",))
                    lock_held[0] = True
                    time.sleep(2)
                    conn.commit()

        def timeout_writer():
            # Wait for thread 1 to hold the lock
            while not lock_held[0]:
                time.sleep(0.1)

            with psycopg.connect(self.config.database_url) as conn:
                with conn.cursor() as cur:
                    # Set a very short lock timeout to force failure
                    cur.execute("SET lock_timeout = '100ms'")
                    try:
                        activate_release(conn, f"{self._p}3S", m2, activation_enabled=True)
                        return "success"
                    except psycopg.errors.LockNotAvailable:
                        conn.rollback()
                        return "lock_timeout"

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(hold_lock)
            f2 = executor.submit(timeout_writer)

            f1.result()
            r2 = f2.result()

        self.assertEqual(r2, "lock_timeout", "Second writer should fail with lock timeout")
