import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import app. Note: api.py creates the app
from api import app, REGISTRY_RUNTIME_INFO
from registry_runtime import RegistryRuntimeStatus

class TestP8FRegistryApiStatus(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        import api
        self.original_info = api.REGISTRY_RUNTIME_INFO
        from api import RegistryRuntimeInfo, RegistryRuntimeStatus
        api.REGISTRY_RUNTIME_INFO = RegistryRuntimeInfo(status=RegistryRuntimeStatus.UNAVAILABLE, failure_reason_code='not_started', store_backend='postgres')

    def tearDown(self):
        import api
        api.REGISTRY_RUNTIME_INFO = self.original_info

    def test_auth_required(self):
        response = self.client.get("/registry/status")
        self.assertEqual(response.status_code, 401)

    def test_bearer_auth(self):
        response = self.client.get("/registry/status", headers={"Authorization": "Bearer invalid_key"})
        # We assume invalid key gives 401
        self.assertEqual(response.status_code, 401)

    @patch('api._auth_context')
    def test_auth_route_class_limit_and_fingerprint(self, mock_auth):
        # mock_auth returns (principal, key, error)
        # simulate 429 Retry-After
        from fastapi.responses import JSONResponse
        mock_auth.return_value = (None, None, JSONResponse({"error": "rate_limited"}, status_code=429, headers={"Retry-After": "60"}))

        response = self.client.get("/registry/status", headers={"Authorization": "Bearer some_key"})
        self.assertEqual(response.status_code, 429)
        self.assertIn("retry-after", response.headers)
        self.assertEqual(response.headers["retry-after"], "60")

        # Verify it passed the right route class 'AUTH'
        mock_auth.assert_called_once()
        self.assertEqual(mock_auth.call_args[0][2], 'AUTH')

    @patch('api._auth_context')
    def test_safe_metadata_allowlist(self, mock_auth):
        mock_auth.return_value = ("test_user", "test_key", None)

        import api
        from api import RegistryRuntimeStatus, RegistryRuntimeInfo
        api.REGISTRY_RUNTIME_INFO = RegistryRuntimeInfo(
            status=RegistryRuntimeStatus.READY,
            failure_reason_code='test',
            store_backend='postgres',
            release_id='M1',
            family_completeness={"3S": {"SDKI": True}}
        )

        response = self.client.get("/registry/status", headers={"Authorization": "Bearer valid"})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["registry_runtime_status"], "registry_ready")
        self.assertEqual(data["registry_active_release_id"], "M1")
        # Ensure no URL, no password, no tracebacks
        self.assertNotIn("database_url", data)
        self.assertNotIn("password", data)
        self.assertNotIn("traceback", data)
        self.assertNotIn("exception", data)

    @patch('api._auth_context')
    def test_fail_closed_before_lifespan(self, mock_auth):
        mock_auth.return_value = ("test_user", "test_key", None)
        import api
        from api import RegistryRuntimeStatus, RegistryRuntimeInfo
        api.REGISTRY_RUNTIME_INFO = RegistryRuntimeInfo(
            status=RegistryRuntimeStatus.UNAVAILABLE,
            failure_reason_code='pending_startup',
            store_backend='postgres'
        )

        response = self.client.get("/registry/status", headers={"Authorization": "Bearer valid"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["registry_runtime_status"], "registry_unavailable")
        self.assertEqual(data["registry_failure_reason_code"], "pending_startup")
