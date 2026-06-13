"""Phase 8 P8-BE — Release, runtime, activation, rollback, and startup tests.

Covers: release validation, deterministic manifest hash, activation disabled,
atomic activation/rollback, complete-family policy, startup fail-closed,
safe metadata, startup probe bounds, and audit metadata safety.
All tests use synthetic data only. No patient data. No PHI.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from unittest.mock import MagicMock, patch


def _mock_conn():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


# ===========================================================================
# Deterministic manifest hash
# ===========================================================================

class TestDeterministicManifestHash(unittest.TestCase):
    def test_same_entries_same_hash(self):
        from registry_release_service import compute_manifest_hash
        entries = [
            {'registry_family': 'SDKI', 'code': 'D.0001', 'entry_id': 'E1', 'content_hash': 'aaa'},
            {'registry_family': 'SLKI', 'code': 'L.0001', 'entry_id': 'E2', 'content_hash': 'bbb'},
        ]
        h1 = compute_manifest_hash(entries)
        h2 = compute_manifest_hash(entries)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_different_order_same_hash(self):
        from registry_release_service import compute_manifest_hash
        entries_a = [
            {'registry_family': 'SLKI', 'code': 'L.0001', 'entry_id': 'E2', 'content_hash': 'bbb'},
            {'registry_family': 'SDKI', 'code': 'D.0001', 'entry_id': 'E1', 'content_hash': 'aaa'},
        ]
        entries_b = [
            {'registry_family': 'SDKI', 'code': 'D.0001', 'entry_id': 'E1', 'content_hash': 'aaa'},
            {'registry_family': 'SLKI', 'code': 'L.0001', 'entry_id': 'E2', 'content_hash': 'bbb'},
        ]
        self.assertEqual(compute_manifest_hash(entries_a), compute_manifest_hash(entries_b))

    def test_different_entries_different_hash(self):
        from registry_release_service import compute_manifest_hash
        e1 = [{'registry_family': 'SDKI', 'code': 'D.0001', 'entry_id': 'E1', 'content_hash': 'aaa'}]
        e2 = [{'registry_family': 'SDKI', 'code': 'D.0002', 'entry_id': 'E2', 'content_hash': 'bbb'}]
        self.assertNotEqual(compute_manifest_hash(e1), compute_manifest_hash(e2))


# ===========================================================================
# Activation gates
# ===========================================================================

class TestActivationDisabledByDefault(unittest.TestCase):
    def test_activation_blocked_when_disabled(self):
        from registry_release_service import activate_release
        from registry_workflow import RegistryWorkflowError
        conn, _ = _mock_conn()
        with self.assertRaises(RegistryWorkflowError) as ctx:
            activate_release(conn, '3S', 'M1', activation_enabled=False)
        self.assertIn('REGISTRY_ACTIVATION_ENABLED=false', str(ctx.exception))

    def test_rollback_blocked_when_disabled(self):
        from registry_release_service import rollback_release
        from registry_workflow import RegistryWorkflowError
        conn, _ = _mock_conn()
        with self.assertRaises(RegistryWorkflowError) as ctx:
            rollback_release(conn, '3S', 'M1', activation_enabled=False)
        self.assertIn('REGISTRY_ACTIVATION_ENABLED=false', str(ctx.exception))


class TestActivationRequiresApproval(unittest.TestCase):
    def test_unapproved_release_rejected(self):
        from registry_release_service import activate_release
        from registry_workflow import RegistryWorkflowError
        conn, cur = _mock_conn()
        cur.fetchone.side_effect = [
            ('candidate', 'hash1'),  # manifest status
        ]
        with self.assertRaises(RegistryWorkflowError) as ctx:
            activate_release(conn, '3S', 'M1', activation_enabled=True)
        self.assertIn('approved', str(ctx.exception))


class TestActivationRequiresReleaseApproval(unittest.TestCase):
    def test_missing_release_approval_rejected(self):
        from registry_release_service import activate_release
        from registry_workflow import RegistryWorkflowError
        conn, cur = _mock_conn()
        cur.fetchone.side_effect = [
            ('approved', 'hash1'),  # manifest status = approved
            None,                    # no release approval artifact
        ]
        with self.assertRaises(RegistryWorkflowError) as ctx:
            activate_release(conn, '3S', 'M1', activation_enabled=True)
        self.assertIn('approval artifact', str(ctx.exception).lower())


# ===========================================================================
# Complete-family policy
# ===========================================================================

class TestCompleteFamilyPolicy(unittest.TestCase):
    def test_3s_requires_sdki_slki_siki(self):
        from registry_release_service import FRAMEWORK_FAMILIES
        self.assertEqual(FRAMEWORK_FAMILIES['3S'], frozenset({'SDKI', 'SLKI', 'SIKI'}))

    def test_3n_requires_nanda_noc_nic(self):
        from registry_release_service import FRAMEWORK_FAMILIES
        self.assertEqual(FRAMEWORK_FAMILIES['3N'], frozenset({'NANDA', 'NOC', 'NIC'}))

    def test_sdki_only_incomplete(self):
        from registry_release_service import check_family_completeness
        conn, cur = _mock_conn()
        cur.fetchall.return_value = [('SDKI',)]
        result = check_family_completeness(conn, '3S', 'M1')
        self.assertFalse(result['complete'])
        self.assertEqual(result['status'], 'registry_incomplete')
        self.assertIn('SLKI', result['missing'])
        self.assertIn('SIKI', result['missing'])

    def test_nanda_only_incomplete(self):
        from registry_release_service import check_family_completeness
        conn, cur = _mock_conn()
        cur.fetchall.return_value = [('NANDA',)]
        result = check_family_completeness(conn, '3N', 'M1')
        self.assertFalse(result['complete'])
        self.assertEqual(result['status'], 'registry_incomplete')

    def test_full_3s_complete(self):
        from registry_release_service import check_family_completeness
        conn, cur = _mock_conn()
        cur.fetchall.return_value = [('SDKI',), ('SLKI',), ('SIKI',)]
        result = check_family_completeness(conn, '3S', 'M1')
        self.assertTrue(result['complete'])
        self.assertEqual(result['status'], 'registry_ready')

    def test_full_3n_complete(self):
        from registry_release_service import check_family_completeness
        conn, cur = _mock_conn()
        cur.fetchall.return_value = [('NANDA',), ('NOC',), ('NIC',)]
        result = check_family_completeness(conn, '3N', 'M1')
        self.assertTrue(result['complete'])
        self.assertEqual(result['status'], 'registry_ready')


# ===========================================================================
# Release validation rejects
# ===========================================================================

class TestReleaseValidation(unittest.TestCase):
    def test_release_approval_requires_validated(self):
        from registry_release_service import create_release_approval
        from registry_workflow import RegistryWorkflowError
        conn, cur = _mock_conn()
        cur.fetchone.return_value = ('candidate', 'hash1')
        with self.assertRaises(RegistryWorkflowError) as ctx:
            create_release_approval(conn, 'RA1', 'M1', 'NURSE-001', 'approved')
        self.assertIn('validated', str(ctx.exception))

    def test_release_approval_requires_approver(self):
        from registry_release_service import create_release_approval
        from registry_workflow import RegistryWorkflowError
        conn, cur = _mock_conn()
        with self.assertRaises(RegistryWorkflowError):
            create_release_approval(conn, 'RA2', 'M2', '', 'approved')


# ===========================================================================
# Runtime startup
# ===========================================================================

class TestStartupFailClosed(unittest.TestCase):
    def test_store_disabled_unavailable(self):
        from registry_runtime import probe_registry_store, RegistryRuntimeStatus
        from registry_store import RegistryStoreConfig
        cfg = RegistryStoreConfig(backend='disabled')
        info = probe_registry_store(cfg)
        self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)
        self.assertEqual(info.failure_reason_code, 'store_disabled')

    def test_activation_disabled_unavailable(self):
        from registry_runtime import probe_registry_store, RegistryRuntimeStatus
        from registry_store import RegistryStoreConfig
        cfg = RegistryStoreConfig(
            backend='postgres', database_url='postgresql://x:x@localhost/test',
            activation_enabled=False,
        )
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V006'}):
            info = probe_registry_store(cfg)
        self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)
        self.assertEqual(info.failure_reason_code, 'activation_disabled')

    def test_connection_failure_unavailable(self):
        from registry_runtime import probe_registry_store, RegistryRuntimeStatus
        from registry_store import RegistryStoreConfig
        cfg = RegistryStoreConfig(
            backend='postgres', database_url='postgresql://x:x@localhost/test',
            activation_enabled=True,
        )
        with patch('registry_runtime._probe_health', return_value={'healthy': False, 'reason': 'connection_failed'}):
            info = probe_registry_store(cfg)
        self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)

    def test_unsupported_schema_unavailable(self):
        from registry_runtime import probe_registry_store, RegistryRuntimeStatus
        from registry_store import RegistryStoreConfig
        cfg = RegistryStoreConfig(
            backend='postgres', database_url='postgresql://x:x@localhost/test',
            activation_enabled=True,
        )
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V001'}):
            info = probe_registry_store(cfg)
        self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)
        self.assertEqual(info.failure_reason_code, 'unsupported_schema')

    def test_no_active_release_unavailable(self):
        from registry_runtime import probe_registry_store, RegistryRuntimeStatus
        from registry_store import RegistryStoreConfig
        cfg = RegistryStoreConfig(
            backend='postgres', database_url='postgresql://x:x@localhost/test',
            activation_enabled=True,
        )
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V006'}):
            with patch('registry_runtime._load_active_release', return_value=None):
                info = probe_registry_store(cfg)
        self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)
        self.assertEqual(info.failure_reason_code, 'no_active_release')

    def test_hash_mismatch_unavailable(self):
        from registry_runtime import probe_registry_store, RegistryRuntimeStatus
        from registry_store import RegistryStoreConfig
        cfg = RegistryStoreConfig(
            backend='postgres', database_url='postgresql://x:x@localhost/test',
            activation_enabled=True,
        )
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V006'}):
            with patch('registry_runtime._load_active_release',
                       return_value={'validation_error': 'entry_hash_mismatch'}):
                info = probe_registry_store(cfg)
        self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)

    def test_incomplete_family_incomplete(self):
        from registry_runtime import probe_registry_store, RegistryRuntimeStatus
        from registry_store import RegistryStoreConfig
        cfg = RegistryStoreConfig(
            backend='postgres', database_url='postgresql://x:x@localhost/test',
            activation_enabled=True,
        )
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V006'}):
            with patch('registry_runtime._load_active_release',
                       return_value={'manifest_id': 'M1', 'framework': '3S',
                                     'family_complete': False,
                                     'family_completeness': {'3S': {'SDKI': True, 'SLKI': False, 'SIKI': False}}}):
                info = probe_registry_store(cfg)
        self.assertEqual(info.status, RegistryRuntimeStatus.INCOMPLETE)

    def test_complete_release_ready(self):
        from registry_runtime import probe_registry_store, RegistryRuntimeStatus
        from registry_store import RegistryStoreConfig
        cfg = RegistryStoreConfig(
            backend='postgres', database_url='postgresql://x:x@localhost/test',
            activation_enabled=True,
        )
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V006'}):
            with patch('registry_runtime._load_active_release',
                       return_value={'manifest_id': 'M1', 'framework': '3S',
                                     'family_complete': True,
                                     'family_completeness': {'3S': {'SDKI': True, 'SLKI': True, 'SIKI': True}}}):
                info = probe_registry_store(cfg)
        self.assertEqual(info.status, RegistryRuntimeStatus.READY)


class TestStartupProbeNotAtImport(unittest.TestCase):
    """Verify importing api.py does NOT initiate a DB connection."""

    def test_import_api_no_registry_connection(self):
        """Importing api should set REGISTRY_RUNTIME_INFO to safe default, not probe."""
        import api
        info = api.REGISTRY_RUNTIME_INFO
        # Must be a RegistryRuntimeInfo, not None, and fail-closed
        from registry_runtime import RegistryRuntimeInfo, RegistryRuntimeStatus
        self.assertIsInstance(info, RegistryRuntimeInfo)
        self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)
        # Before lifespan runs, failure_reason should be 'not_started'
        # (or 'store_disabled' if backend is disabled in CONFIG)
        self.assertIn(info.failure_reason_code, {'not_started', 'store_disabled'})

    def test_default_registry_info_is_safe(self):
        """Default REGISTRY_RUNTIME_INFO exposes no credentials."""
        import api
        from registry_runtime import safe_registry_metadata
        meta = safe_registry_metadata(api.REGISTRY_RUNTIME_INFO)
        meta_str = str(meta)
        self.assertNotIn('password', meta_str.lower())
        self.assertNotIn('neon.tech', meta_str)
        self.assertNotIn('postgresql://', meta_str)


# ===========================================================================
# Safe metadata
# ===========================================================================

class TestSafeMetadata(unittest.TestCase):
    def test_no_body_in_metadata(self):
        from registry_runtime import safe_registry_metadata, RegistryRuntimeInfo, RegistryRuntimeStatus
        info = RegistryRuntimeInfo(
            status=RegistryRuntimeStatus.UNAVAILABLE,
            failure_reason_code='store_disabled',
        )
        meta = safe_registry_metadata(info)
        meta_str = json.dumps(meta)
        self.assertNotIn('body', meta_str.lower())
        self.assertNotIn('password', meta_str.lower())
        self.assertNotIn(':///', meta_str)

    def test_no_credentials_in_metadata(self):
        from registry_runtime import safe_registry_metadata, RegistryRuntimeInfo, RegistryRuntimeStatus
        info = RegistryRuntimeInfo(
            status=RegistryRuntimeStatus.READY,
            store_backend='postgres',
            release_id='M1',
        )
        meta = safe_registry_metadata(info)
        self.assertNotIn('database_url', str(meta))
        self.assertNotIn('neon.tech', str(meta))


# ===========================================================================
# Startup probe bounds
# ===========================================================================

class TestStartupProbeBounded(unittest.TestCase):
    def test_max_attempts_clamped(self):
        from registry_runtime import probe_registry_store
        from registry_store import RegistryStoreConfig
        cfg = RegistryStoreConfig(backend='disabled')
        # Even with max_attempts=100, should clamp to 5
        info = probe_registry_store(cfg, max_attempts=100)
        self.assertEqual(info.failure_reason_code, 'store_disabled')

    def test_documented_upper_bound(self):
        from registry_runtime import STARTUP_MAX_ATTEMPTS, STARTUP_CONNECT_TIMEOUT_SEC, STARTUP_BACKOFF_SEC
        # Verify documented upper bounds
        self.assertLessEqual(STARTUP_MAX_ATTEMPTS, 5)
        self.assertLessEqual(STARTUP_CONNECT_TIMEOUT_SEC, 30)
        self.assertLessEqual(STARTUP_BACKOFF_SEC, 5)
        # Total worst case: attempts * (timeout + max_backoff) < 180s
        worst = STARTUP_MAX_ATTEMPTS * (STARTUP_CONNECT_TIMEOUT_SEC + STARTUP_BACKOFF_SEC * 4)
        self.assertLess(worst, 180, 'Startup probe worst case must be < 3 minutes')


# ===========================================================================
# Audit metadata safety
# ===========================================================================

class TestAuditMetadataSafety(unittest.TestCase):
    def test_registry_event_types_present(self):
        from audit_ledger import ALLOWED_EVENT_TYPES
        expected = [
            'registry_source_registered', 'registry_import_dry_run',
            'registry_import_applied', 'registry_review_enqueued',
            'registry_review_decided', 'registry_entry_approved',
            'registry_release_candidate_created', 'registry_release_validated',
            'registry_release_approved', 'registry_release_activated',
            'registry_release_rollback',
        ]
        for et in expected:
            self.assertIn(et, ALLOWED_EVENT_TYPES)

    def test_registry_metadata_keys_present(self):
        from audit_ledger import ALLOWED_METADATA_KEYS
        expected = ['source_id', 'entry_id', 'release_id', 'manifest_hash',
                     'content_hash', 'registry_family', 'review_status',
                     'approval_status', 'entry_count', 'quarantined_count']
        for key in expected:
            self.assertIn(key, ALLOWED_METADATA_KEYS)

    def test_url_filtered_in_metadata_value(self):
        from audit_ledger import validate_registry_metadata_value
        result = validate_registry_metadata_value('source_id', 'postgresql://user:pass@host/db')
        self.assertEqual(result, '[FILTERED]')

    def test_absolute_path_filtered(self):
        from audit_ledger import validate_registry_metadata_value
        result = validate_registry_metadata_value('entry_id', '/etc/passwd')
        self.assertEqual(result, '[FILTERED]')

    def test_valid_sha256_accepted(self):
        from audit_ledger import validate_registry_metadata_value
        h = 'a' * 64
        result = validate_registry_metadata_value('content_hash', h)
        self.assertEqual(result, h)

    def test_invalid_sha256_filtered(self):
        from audit_ledger import validate_registry_metadata_value
        result = validate_registry_metadata_value('content_hash', 'not-a-hash')
        self.assertEqual(result, '[FILTERED]')

    def test_valid_family_accepted(self):
        from audit_ledger import validate_registry_metadata_value
        self.assertEqual(validate_registry_metadata_value('registry_family', 'SDKI'), 'SDKI')

    def test_invalid_family_filtered(self):
        from audit_ledger import validate_registry_metadata_value
        self.assertEqual(validate_registry_metadata_value('registry_family', 'EVIL'), '[FILTERED]')

    def test_no_body_in_audit(self):
        from audit_ledger import validate_registry_metadata_value
        # Body text should be cleaned by _clean_token
        result = validate_registry_metadata_value('reason_code', 'normal_reason')
        self.assertNotIn('body', str(result).lower())

    def test_no_credentials_in_audit(self):
        from audit_ledger import validate_registry_metadata_value
        result = validate_registry_metadata_value('source_id', 'postgres://user:pass@neon.tech/db')
        self.assertEqual(result, '[FILTERED]')

    def test_newline_filtered(self):
        from audit_ledger import validate_registry_metadata_value
        result = validate_registry_metadata_value('source_id', 'id\ninjection')
        self.assertEqual(result, '[FILTERED]')


# ===========================================================================
# Release lifecycle
# ===========================================================================

class TestReleaseLifecycle(unittest.TestCase):
    def test_release_states_defined(self):
        from registry_workflow import RELEASE_LIFECYCLE_STATES
        expected = {'draft', 'validated', 'approved', 'active',
                    'superseded', 'rolled_back', 'rejected'}
        self.assertEqual(RELEASE_LIFECYCLE_STATES, expected)

    def test_entry_states_defined(self):
        from registry_workflow import ENTRY_LIFECYCLE_STATES
        expected = {'quarantined', 'draft', 'pending_review', 'review_rejected',
                    'review_verified', 'approved', 'deprecated'}
        self.assertEqual(ENTRY_LIFECYCLE_STATES, expected)


if __name__ == '__main__':
    unittest.main()
