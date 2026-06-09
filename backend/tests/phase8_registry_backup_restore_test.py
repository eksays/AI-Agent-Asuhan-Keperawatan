import unittest
import os
import tempfile
import json
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))

from registry_db_backup import backup_metadata
from registry_db_restore_verify import restore_verify

@unittest.skipUnless(os.environ.get('NEON_INTEGRATION_TEST'), "NEON_INTEGRATION_TEST not set")
class TestP8FBackupRestore(unittest.TestCase):
    def test_backup_restore_rehearsal(self):
        # We need a temporary file
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            # Run backup
            backup_metadata(path)

            # Verify file exists and has correct format
            with open(path, 'r') as f:
                data = json.load(f)
            self.assertIn('hash', data)
            self.assertIn('data', data)
            self.assertIn('schema_version', data['data'])

            # Run restore and verify it passes
            # (restore_verify throws SystemExit on failure)
            restore_verify(path, cleanup=True)

            # Test tampering
            data['data']['schema_version'] = 'V999'
            with open(path, 'w') as f:
                json.dump(data, f)
            with self.assertRaises(RuntimeError):
                restore_verify(path, cleanup=True)
        finally:
            os.remove(path)
