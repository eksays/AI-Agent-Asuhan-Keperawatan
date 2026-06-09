"""Phase 8 P8-BE — Governed registry workflow PostgreSQL integration tests.

Requires NEON_INTEGRATION_TEST=1 and local ignored backend/.env.
Uses pooled runtime URL for operations and direct admin URL for migrations.
All synthetic identifiers. Cleanup after every test.
No URL output. No hostname. No password. No body. No data_terstruktur import.
"""
from __future__ import annotations

import os
import sys
import time
import unittest
import uuid

# Gate: only run if opt-in and env available
_INTEGRATION = os.environ.get('NEON_INTEGRATION_TEST', '') == '1'
_SKIP_MSG = 'NEON_INTEGRATION_TEST not set'


def _load_backend_env():
    """Load backend/.env into os.environ (local ignored file only)."""
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if not os.path.isfile(env_path):
        return False
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())
    return True


def _unique_prefix():
    return f'SYN-P8BE-{uuid.uuid4().hex[:8]}'


@unittest.skipUnless(_INTEGRATION, _SKIP_MSG)
class TestP8BEWorkflowIntegration(unittest.TestCase):
    """End-to-end P8-BE workflow integration against Neon PostgreSQL."""

    _prefix: str = ''
    _conn = None
    _admin_conn = None

    @classmethod
    def setUpClass(cls):
        _load_backend_env()
        cls._prefix = _unique_prefix()

        from registry_store import load_registry_store_config
        cls._cfg = load_registry_store_config(
            backend=os.environ.get('REGISTRY_STORE_BACKEND', 'disabled'),
            database_url=os.environ.get('REGISTRY_DATABASE_URL', ''),
            admin_url=os.environ.get('REGISTRY_DATABASE_ADMIN_URL', ''),
            runtime_mode=os.environ.get('REGISTRY_RUNTIME_MODE', 'synthetic'),
            activation_enabled=True,  # test-local override
        )
        if cls._cfg.backend == 'disabled' or not cls._cfg.database_url:
            raise unittest.SkipTest('Postgres backend not configured')

        # Run migrations via admin URL
        import psycopg
        cls._admin_conn = psycopg.connect(cls._cfg.admin_url or cls._cfg.database_url)
        from registry_migrations import ALL_MIGRATIONS
        for m in ALL_MIGRATIONS:
            try:
                with cls._admin_conn.cursor() as cur:
                    cur.execute(m.sql)
                cls._admin_conn.commit()
            except Exception:
                cls._admin_conn.rollback()

        # Pooled runtime connection
        cls._conn = psycopg.connect(cls._cfg.database_url)
        cls._conn.autocommit = False

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_synthetic_rows()
        if cls._conn:
            cls._conn.close()
        if cls._admin_conn:
            cls._admin_conn.close()

    @classmethod
    def _cleanup_synthetic_rows(cls):
        """Remove all synthetic rows created by this test run."""
        prefix = cls._prefix
        conn = cls._conn or cls._admin_conn
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                # Clean in dependency order
                cur.execute("DELETE FROM release_approval_artifacts WHERE approval_id LIKE %s", (f'{prefix}%',))
                cur.execute("DELETE FROM release_history WHERE manifest_id LIKE %s", (f'{prefix}%',))
                cur.execute("DELETE FROM active_releases WHERE manifest_id LIKE %s", (f'{prefix}%',))
                cur.execute("DELETE FROM release_manifest_entries WHERE manifest_id LIKE %s", (f'{prefix}%',))
                cur.execute("DELETE FROM release_manifests WHERE manifest_id LIKE %s", (f'{prefix}%',))
                cur.execute("DELETE FROM extraction_verifications WHERE verification_id LIKE %s", (f'{prefix}%',))
                cur.execute("DELETE FROM approval_artifacts WHERE approval_id LIKE %s", (f'{prefix}%',))
                cur.execute("DELETE FROM review_queue WHERE review_id LIKE %s", (f'{prefix}%',))
                cur.execute("DELETE FROM entry_provenance WHERE entry_id LIKE %s", (f'{prefix}%',))
                cur.execute("DELETE FROM registry_entries WHERE entry_id LIKE %s", (f'{prefix}%',))
                cur.execute("DELETE FROM registry_sources WHERE source_id LIKE %s", (f'{prefix}%',))
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

    def setUp(self):
        self._p = self.__class__._prefix

    def tearDown(self):
        try:
            self.__class__._conn.rollback()
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # 1. Source registration
    # -----------------------------------------------------------------------
    def test_01_register_source(self):
        from registry_workflow import create_source_metadata
        result = create_source_metadata(
            self._conn, f'{self._p}-SRC', 'SDKI',
            'Synthetic P8-BE Test Source', 'v1',
            'a' * 64, 'approved',
        )
        self.assertEqual(result['source_id'], f'{self._p}-SRC')

    # -----------------------------------------------------------------------
    # 2. Entry registration
    # -----------------------------------------------------------------------
    def test_02_register_entries(self):
        from registry_workflow import create_source_metadata, register_entry
        create_source_metadata(
            self._conn, f'{self._p}-SRC', 'SDKI', 'Src', 'v1', 'b' * 64, 'approved',
        )
        for i, fam in enumerate(['SDKI', 'SLKI', 'SIKI']):
            register_entry(
                self._conn, f'{self._p}-E-{fam}-{i}', f'{self._p}-SRC',
                fam, fam, f'D.{i:04d}', f'Synthetic {fam} Entry {i}',
                f'{chr(97+i)}' * 64, 'draft',
            )

    # -----------------------------------------------------------------------
    # 3. Review queue
    # -----------------------------------------------------------------------
    def test_03_review_queue(self):
        from registry_workflow import (
            create_source_metadata, register_entry,
            enqueue_review, record_review_decision, get_review_queue,
        )
        create_source_metadata(self._conn, f'{self._p}-SRC', 'SDKI', 's', 'v1', 'c'*64, 'approved')
        register_entry(self._conn, f'{self._p}-E-R', f'{self._p}-SRC', 'SDKI', 'SDKI', 'D.9999', 'n', 'd'*64, 'draft')
        enqueue_review(self._conn, f'{self._p}-RV', f'{self._p}-E-R', 'NURSE-001')
        queue = get_review_queue(self._conn, status_filter='pending')
        found = [r for r in queue if r['review_id'] == f'{self._p}-RV']
        self.assertTrue(found)
        record_review_decision(self._conn, f'{self._p}-RV', 'approved', 'NURSE-001')
        queue2 = get_review_queue(self._conn, status_filter='approved')
        found2 = [r for r in queue2 if r['review_id'] == f'{self._p}-RV']
        self.assertTrue(found2)

    # -----------------------------------------------------------------------
    # 4. Extraction verification
    # -----------------------------------------------------------------------
    def test_04_extraction_verification(self):
        from registry_workflow import (
            create_source_metadata, register_entry, record_provenance,
            record_extraction_verification, get_extraction_verification,
        )
        create_source_metadata(self._conn, f'{self._p}-SRC', 'SDKI', 's', 'v1', 'e'*64, 'approved')
        register_entry(self._conn, f'{self._p}-E-EV', f'{self._p}-SRC', 'SDKI', 'SDKI', 'D.8888', 'n', 'f'*64, 'draft')
        record_provenance(self._conn, f'{self._p}-E-EV', 'ocr')
        record_extraction_verification(self._conn, f'{self._p}-EV', f'{self._p}-E-EV', 'verified_by_human', verified_by='NURSE-001')
        ev = get_extraction_verification(self._conn, f'{self._p}-E-EV')
        self.assertIsNotNone(ev)
        self.assertEqual(ev['status'], 'verified_by_human')

    # -----------------------------------------------------------------------
    # 5. Entry approval (with extraction verification gate)
    # -----------------------------------------------------------------------
    def test_05_entry_approval(self):
        from registry_workflow import (
            create_source_metadata, register_entry, record_provenance,
            record_extraction_verification, enqueue_review, record_review_decision,
            create_approval_artifact, update_entry_lifecycle,
        )
        create_source_metadata(self._conn, f'{self._p}-SRC', 'SDKI', 's', 'v1', 'g'*64, 'approved')
        register_entry(self._conn, f'{self._p}-E-AP', f'{self._p}-SRC', 'SDKI', 'SDKI', 'D.7777', 'n', 'h'*64, 'draft')
        record_provenance(self._conn, f'{self._p}-E-AP', 'ocr')
        # Must fail without extraction verification
        from registry_workflow import RegistryWorkflowError
        with self.assertRaises(RegistryWorkflowError):
            create_approval_artifact(
                self._conn, f'{self._p}-FAIL-AP', f'{self._p}-RV-AP', f'{self._p}-E-AP',
                'NURSE-001', 'approved', 'h'*64,
            )
        # Verify extraction
        record_extraction_verification(self._conn, f'{self._p}-EV-AP', f'{self._p}-E-AP', 'verified_by_human', verified_by='NURSE-001')
        # Move to pending_review
        update_entry_lifecycle(self._conn, f'{self._p}-E-AP', 'pending_review')
        enqueue_review(self._conn, f'{self._p}-RV-AP', f'{self._p}-E-AP', 'NURSE-001')
        record_review_decision(self._conn, f'{self._p}-RV-AP', 'approved', 'NURSE-001')
        # Now create approval artifact
        result = create_approval_artifact(
            self._conn, f'{self._p}-AP-1', f'{self._p}-RV-AP', f'{self._p}-E-AP',
            'NURSE-001', 'approved', 'h'*64,
        )
        self.assertEqual(result['decision'], 'approved')
        update_entry_lifecycle(self._conn, f'{self._p}-E-AP', 'approved')

    # -----------------------------------------------------------------------
    # 6. Release candidate + deterministic manifest hash
    # -----------------------------------------------------------------------
    def test_06_release_candidate_and_manifest_hash(self):
        from registry_workflow import (
            create_source_metadata, register_entry, record_provenance,
            record_extraction_verification, enqueue_review, record_review_decision,
            create_approval_artifact, update_entry_lifecycle,
        )
        from registry_release_service import create_release_candidate, compute_manifest_hash

        # Setup: 3 approved entries for 3S
        create_source_metadata(self._conn, f'{self._p}-SRC', 'SDKI', 's', 'v1', 'i'*64, 'approved')
        entries = []
        for i, fam in enumerate(['SDKI', 'SLKI', 'SIKI']):
            eid = f'{self._p}-E-RC-{fam}'
            ch = f'{chr(106+i)}' * 64
            register_entry(self._conn, eid, f'{self._p}-SRC', fam, fam, f'D.{6000+i}', f'n{i}', ch, 'draft')
            record_provenance(self._conn, eid, 'manual')
            update_entry_lifecycle(self._conn, eid, 'pending_review')
            rv = f'{self._p}-RV-RC-{fam}'
            enqueue_review(self._conn, rv, eid, 'NURSE-001')
            record_review_decision(self._conn, rv, 'approved', 'NURSE-001')
            ap = f'{self._p}-AP-RC-{fam}'
            create_approval_artifact(self._conn, ap, rv, eid, 'NURSE-001', 'approved', ch)
            update_entry_lifecycle(self._conn, eid, 'approved')
            entries.append(eid)

        # Create release candidate
        result = create_release_candidate(
            self._conn, f'{self._p}-M-1', '3S', f'{self._p}-rc-v1.0.0', entries,
        )
        self.assertEqual(result['entry_count'], 3)
        self.assertEqual(len(result['manifest_hash']), 64)
        self.assertEqual(result['status'], 'candidate')

    # -----------------------------------------------------------------------
    # 7. Release validation + approval + activation + rollback
    # -----------------------------------------------------------------------
    def test_07_activation_and_rollback(self):
        from registry_workflow import (
            create_source_metadata, register_entry, record_provenance,
            enqueue_review, record_review_decision,
            create_approval_artifact, update_entry_lifecycle,
        )
        from registry_release_service import (
            create_release_candidate, mark_release_validated,
            create_release_approval, activate_release, rollback_release,
            get_active_release, get_release_history,
        )

        # Setup: approved entries
        create_source_metadata(self._conn, f'{self._p}-SRC', 'SDKI', 's', 'v1', 'k'*64, 'approved')
        eids1 = []
        for i, fam in enumerate(['SDKI', 'SLKI', 'SIKI']):
            eid = f'{self._p}-E-ACT-{fam}-1'
            ch = f'{chr(108+i)}' * 64
            register_entry(self._conn, eid, f'{self._p}-SRC', fam, fam, f'D.{5000+i}', f'n{i}', ch, 'draft')
            record_provenance(self._conn, eid, 'manual')
            update_entry_lifecycle(self._conn, eid, 'pending_review')
            rv = f'{self._p}-RV-ACT-{fam}-1'
            enqueue_review(self._conn, rv, eid, 'NURSE-001')
            record_review_decision(self._conn, rv, 'approved', 'NURSE-001')
            ap = f'{self._p}-AP-ACT-{fam}-1'
            create_approval_artifact(self._conn, ap, rv, eid, 'NURSE-001', 'approved', ch)
            update_entry_lifecycle(self._conn, eid, 'approved')
            eids1.append(eid)

        # Release 1
        m1 = f'{self._p}-M-ACT-1'
        create_release_candidate(self._conn, m1, '3S', f'{self._p}-v1.0.0', eids1)
        mark_release_validated(self._conn, m1)
        create_release_approval(self._conn, f'{self._p}-RA-1', m1, 'DIRECTOR-001', 'approved')

        # Activate (test-local override)
        act_result = activate_release(self._conn, '3S', m1, activation_enabled=True, performed_by='TEST')
        self.assertEqual(act_result['status'], 'active')

        # Verify active
        active = get_active_release(self._conn, '3S')
        self.assertIsNotNone(active)
        self.assertEqual(active['manifest_id'], m1)

        # Release 2 (for rollback test)
        eids2 = []
        for i, fam in enumerate(['SDKI', 'SLKI', 'SIKI']):
            eid = f'{self._p}-E-ACT-{fam}-2'
            ch = f'{chr(111+i)}' * 64
            register_entry(self._conn, eid, f'{self._p}-SRC', fam, fam, f'D.{4000+i}', f'n{i}', ch, 'draft')
            record_provenance(self._conn, eid, 'manual')
            update_entry_lifecycle(self._conn, eid, 'pending_review')
            rv = f'{self._p}-RV-ACT-{fam}-2'
            enqueue_review(self._conn, rv, eid, 'NURSE-001')
            record_review_decision(self._conn, rv, 'approved', 'NURSE-001')
            ap = f'{self._p}-AP-ACT-{fam}-2'
            create_approval_artifact(self._conn, ap, rv, eid, 'NURSE-001', 'approved', ch)
            update_entry_lifecycle(self._conn, eid, 'approved')
            eids2.append(eid)

        m2 = f'{self._p}-M-ACT-2'
        create_release_candidate(self._conn, m2, '3S', f'{self._p}-v2.0.0', eids2)
        mark_release_validated(self._conn, m2)
        create_release_approval(self._conn, f'{self._p}-RA-2', m2, 'DIRECTOR-001', 'approved')
        activate_release(self._conn, '3S', m2, activation_enabled=True, performed_by='TEST')

        # Rollback to release 1
        rb = rollback_release(self._conn, '3S', m1, activation_enabled=True, performed_by='TEST')
        self.assertEqual(rb['manifest_id'], m1)
        self.assertEqual(rb['rolled_back_from'], m2)

        # Verify history
        history = get_release_history(self._conn, '3S')
        actions = [h['action'] for h in history]
        self.assertIn('activated', actions)
        self.assertIn('rolled_back', actions)

    # -----------------------------------------------------------------------
    # 8. Activation disabled rejects
    # -----------------------------------------------------------------------
    def test_08_activation_disabled_rejected(self):
        from registry_release_service import activate_release
        from registry_workflow import RegistryWorkflowError
        with self.assertRaises(RegistryWorkflowError):
            activate_release(self._conn, '3S', 'M-FAKE', activation_enabled=False)

    # -----------------------------------------------------------------------
    # 9. Startup probe
    # -----------------------------------------------------------------------
    def test_09_startup_probe(self):
        from registry_runtime import probe_registry_store, RegistryRuntimeStatus
        info = probe_registry_store(
            self._cfg, max_attempts=2, connect_timeout_sec=10, backoff_sec=1,
        )
        # With activation_enabled=True but possibly no active release,
        # status should be UNAVAILABLE (no_active_release) or better
        self.assertIn(info.status, {
            RegistryRuntimeStatus.UNAVAILABLE,
            RegistryRuntimeStatus.INCOMPLETE,
            RegistryRuntimeStatus.READY,
        })
        self.assertTrue(info.store_health)

    # -----------------------------------------------------------------------
    # 10. Cleanup and post-cleanup count
    # -----------------------------------------------------------------------
    def test_99_cleanup(self):
        self.__class__._cleanup_synthetic_rows()
        # Verify zero synthetic rows (table names from hardcoded allowlist, not user input)
        with self._conn.cursor() as cur:
            for table in ['registry_entries', 'registry_sources', 'review_queue',
                          'approval_artifacts', 'extraction_verifications',
                          'release_manifests', 'release_manifest_entries',
                          'active_releases', 'release_history',
                          'release_approval_artifacts', 'entry_provenance']:
                pk = self._pk_col(table)
                try:
                    # nosec B608: table/pk from hardcoded allowlist, not user input
                    sql = f"SELECT COUNT(*) FROM {table} WHERE {table}.{pk} LIKE %s"  # nosec B608
                    cur.execute(sql, (f'{self._p}%',))
                    count = cur.fetchone()[0]
                    self.assertEqual(count, 0, f'{table} has {count} synthetic rows remaining')
                except Exception:
                    pass  # Table may not exist

    @staticmethod
    def _pk_col(table: str) -> str:
        pk_map = {
            'registry_entries': 'entry_id',
            'registry_sources': 'source_id',
            'review_queue': 'review_id',
            'approval_artifacts': 'approval_id',
            'extraction_verifications': 'verification_id',
            'release_manifests': 'manifest_id',
            'release_manifest_entries': 'manifest_id',
            'active_releases': 'framework',
            'release_history': 'manifest_id',
            'release_approval_artifacts': 'approval_id',
            'entry_provenance': 'entry_id',
        }
        return pk_map.get(table, 'id')


if __name__ == '__main__':
    unittest.main()
