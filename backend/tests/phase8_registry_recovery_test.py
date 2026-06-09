import unittest
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from unittest.mock import patch, MagicMock

from registry_runtime import probe_registry_store, RegistryRuntimeStatus, _load_active_release
from registry_store import RegistryStoreConfig

class TestP8FRecovery(unittest.TestCase):
    def setUp(self):
        self.cfg = RegistryStoreConfig(
            backend='postgres',
            database_url='postgresql://x:x@localhost/test',
            activation_enabled=True
        )

    def test_a_invalid_active_pointer_missing_release(self):
        # Pointer references missing release -> load fails -> unavailable
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V007'}):
            with patch('registry_runtime._load_active_release', return_value=None):
                info = probe_registry_store(self.cfg)
                self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)
                self.assertEqual(info.failure_reason_code, 'no_active_release')

    def test_b_manifest_hash_corruption(self):
        # Active release manifest hash altered -> validation_error
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V007'}):
            with patch('registry_runtime._load_active_release', return_value={'validation_error': 'manifest_hash_mismatch'}):
                info = probe_registry_store(self.cfg)
                self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)
                self.assertEqual(info.failure_reason_code, 'manifest_hash_mismatch')

    def test_c_entry_content_hash_corruption(self):
        # Entry hash mismatch -> validation_error
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V007'}):
            with patch('registry_runtime._load_active_release', return_value={'validation_error': 'entry_hash_mismatch'}):
                info = probe_registry_store(self.cfg)
                self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)
                self.assertEqual(info.failure_reason_code, 'entry_hash_mismatch')

    def test_d_missing_approval(self):
        # Missing approval -> validation_error
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V007'}):
            with patch('registry_runtime._load_active_release', return_value={'validation_error': 'missing_release_approval'}):
                info = probe_registry_store(self.cfg)
                self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)
                self.assertEqual(info.failure_reason_code, 'missing_release_approval')

    def test_e_incomplete_family(self):
        # SDKI only -> registry_incomplete
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V007'}):
            with patch('registry_runtime._load_active_release', return_value={
                'manifest_id': 'M1', 'framework': '3S', 'family_complete': False,
                'family_completeness': {'3S': {'SDKI': True, 'SLKI': False, 'SIKI': False}}
            }):
                info = probe_registry_store(self.cfg)
                self.assertEqual(info.status, RegistryRuntimeStatus.INCOMPLETE)
                self.assertFalse(all(info.family_completeness['3S'].values()))

    def test_f_unsupported_schema_version(self):
        # Schema version newer than supported (e.g. V999) -> unavailable
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V999'}):
            info = probe_registry_store(self.cfg)
            self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)
            self.assertEqual(info.failure_reason_code, 'unsupported_schema')

    def test_g_connection_failure(self):
        # Probe failure -> unavailable
        with patch('registry_runtime._probe_health', return_value={'healthy': False, 'reason': 'connection_failed'}):
            info = probe_registry_store(self.cfg)
            self.assertEqual(info.status, RegistryRuntimeStatus.UNAVAILABLE)
            self.assertEqual(info.failure_reason_code, 'connection_failed')

    def test_h_restart_recovery(self):
        # Restart simulation -> same valid release loads safely
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V007'}):
            with patch('registry_runtime._load_active_release', return_value={
                'manifest_id': 'M1', 'framework': '3S', 'family_complete': True,
                'family_completeness': {'3S': {'SDKI': True, 'SLKI': True, 'SIKI': True}}
            }):
                info = probe_registry_store(self.cfg)
                self.assertEqual(info.status, RegistryRuntimeStatus.READY)
                self.assertTrue(all(info.family_completeness['3S'].values()))

    def test_i_rollback_recovery(self):
        # Rollback simulation -> loads previous valid release A
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V007'}):
            with patch('registry_runtime._load_active_release', return_value={
                'manifest_id': 'M-ROLLBACK-A', 'framework': '3S', 'family_complete': True,
                'family_completeness': {'3S': {'SDKI': True, 'SLKI': True, 'SIKI': True}}
            }):
                info = probe_registry_store(self.cfg)
                self.assertEqual(info.status, RegistryRuntimeStatus.READY)
                self.assertEqual(info.release_id, 'M-ROLLBACK-A')

    def test_j_partial_transaction_failure(self):
        # Transaction fails before commit -> pointer remains unchanged -> loads previous state
        with patch('registry_runtime._probe_health', return_value={'healthy': True, 'schema_version': 'V007'}):
            with patch('registry_runtime._load_active_release', return_value={
                'manifest_id': 'M-PREVIOUS', 'framework': '3S', 'family_complete': True,
                'family_completeness': {'3S': {'SDKI': True, 'SLKI': True, 'SIKI': True}}
            }):
                info = probe_registry_store(self.cfg)
                self.assertEqual(info.status, RegistryRuntimeStatus.READY)
                self.assertEqual(info.release_id, 'M-PREVIOUS')
