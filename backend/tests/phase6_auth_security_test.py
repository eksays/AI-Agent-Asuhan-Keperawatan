from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from dataclasses import replace
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
import config  # noqa: E402
import director  # noqa: E402
from security_controls import AuthPrincipal, BoundedRateLimiter, client_ip_from_request, token_digest  # noqa: E402


class FakeClient:
    host = '10.0.0.5'


class FakeRequest:
    client = FakeClient()

    def __init__(self, headers=None):
        self.headers = headers or {}


class Phase6AuthSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)

    def setUp(self):
        api.RATE_LIMITER.clear()
        with api._fail_lock:
            api._fail_times.clear()
        director.reset_mfa_state_for_tests()

    def session(self, key='test-key'):
        headers = {'Authorization': 'Bearer ' + key}
        data = self.client.post('/session', headers=headers).json()
        self.assertIn('session_token', data)
        headers['X-Session-Token'] = data['session_token']
        return data['session_id'], headers

    def test_header_only_api_key_transport(self):
        self.assertEqual(self.client.get('/status', headers={'Authorization': 'Bearer test-key'}).status_code, 200)
        self.assertEqual(self.client.get('/status').status_code, 401)
        wrong = self.client.get('/status', headers={'Authorization': 'Bearer wrong-key'})
        self.assertEqual(wrong.status_code, 401)
        self.assertNotIn('wrong-key', wrong.text)
        self.assertEqual(self.client.get('/status?api_key=test-key').status_code, 401)
        self.assertEqual(self.client.get('/status', cookies={'api_key': 'test-key'}).status_code, 401)
        self.assertEqual(self.client.post('/session', data={'api_key': 'test-key'}).status_code, 401)
        self.assertEqual(self.client.post('/session', json={'api_key': 'test-key'}).status_code, 401)

    def test_raw_key_not_logged_or_returned_on_auth_failures(self):
        secret = 'super-secret-phase6-test-key'
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            for _ in range(12):
                response = self.client.get('/status?api_key=' + secret)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn(secret, response.text)
        self.assertNotIn(secret, stderr.getvalue())

    def test_session_owner_token_delete_and_rotation(self):
        sid, headers = self.session()
        self.assertEqual(self.client.post('/reset', data={'session_id': sid}).status_code, 401)
        self.assertNotEqual(self.client.post('/reset', data={'session_id': 'fake-session'}, headers=headers).status_code, 200)
        wrong = dict(headers)
        wrong['X-Session-Token'] = 'wrong-token'
        self.assertEqual(self.client.post('/reset', data={'session_id': sid}, headers=wrong).status_code, 409)
        self.assertEqual(self.client.post('/delete_my_data', data={'session_id': sid}).status_code, 401)
        self.assertEqual(self.client.post('/delete_my_data', data={'session_id': sid}, headers=wrong).status_code, 409)
        reset = self.client.post('/reset', data={'session_id': sid}, headers=headers)
        self.assertEqual(reset.status_code, 200)
        new_token = reset.json()['session_token']
        self.assertNotEqual(new_token, headers['X-Session-Token'])
        self.assertEqual(self.client.post('/feedback', data={'framework': '3S', 'session_id': sid}, headers=headers).status_code, 409)
        headers['X-Session-Token'] = new_token
        self.assertEqual(self.client.post('/feedback', data={'framework': '3S', 'session_id': sid}, headers=headers).status_code, 200)
        self.assertEqual(self.client.post('/delete_my_data', data={'session_id': sid}, headers=headers).status_code, 200)
        self.assertEqual(self.client.post('/feedback', data={'framework': '3S', 'session_id': sid}, headers=headers).status_code, 404)

    def test_session_wrong_owner_expiry_and_capacity_reject(self):
        cfg = config.load_config({'CDSS_API_KEYS': 'test-key,other-key', 'CDSS_SECRET_KEY': 'sandbox-secret-for-tests'})
        with mock.patch.object(api, 'CONFIG', cfg):
            sid, headers = self.session('test-key')
            other = {'Authorization': 'Bearer other-key', 'X-Session-Token': headers['X-Session-Token']}
            self.assertEqual(self.client.post('/reset', data={'session_id': sid}, headers=other).status_code, 403)
        api.SESI.force_expire_for_tests(sid)
        self.assertEqual(self.client.post('/feedback', data={'framework': '3S', 'session_id': sid}, headers=headers).status_code, 404)

        store = api.SecureSessionMemory(max_active=1, pepper='pepper')
        principal = AuthPrincipal('api:test', 'fingerprint')
        first_sid, _ = store.issue(principal)
        second_sid, second_token = store.issue(principal)
        self.assertFalse(store.valid(first_sid))
        self.assertEqual(store.validate(second_sid, principal, second_token), 'ok')

    def test_session_digest_storage_idle_expiry_and_last_access(self):
        clock = {'now': 100.0}
        store = api.SecureSessionMemory(ttl=120, idle=30, max_active=4, pepper='pepper', now_func=lambda: clock['now'])
        principal = AuthPrincipal('api:test', 'fingerprint')
        sid, token = store.issue(principal)
        rec = store._records[sid]
        self.assertNotEqual(rec['owner'], 'test-key')
        self.assertEqual(rec['owner'], principal.principal_id)
        self.assertNotEqual(rec['token_digest'], token)
        self.assertEqual(rec['token_digest'], token_digest(token, 'pepper'))
        clock['now'] = 125.0
        self.assertEqual(store.validate(sid, principal, token), 'ok')
        clock['now'] = 154.0
        self.assertEqual(store.validate(sid, principal, token), 'ok')
        clock['now'] = 185.0
        self.assertIn(store.validate(sid, principal, token), {'session_expired', 'session_not_found'})
    def test_totp_replay_lockout_and_unlock(self):
        secret = 'JBSWY3DPEHPK3PXP'
        now = 1_700_000_000.0
        code = director._totp(secret, now)
        with mock.patch.object(director, '_load_secret', return_value=secret):
            first = director.verify_totp_attempt(code, ip='10.0.0.5', now=now, failure_limit=3, lockout=60)
            replay = director.verify_totp_attempt(code, ip='10.0.0.5', now=now + 1, failure_limit=3, lockout=60)
            self.assertTrue(first.ok)
            self.assertEqual(replay.status, 'mfa_replay_rejected')
            for _ in range(3):
                locked = director.verify_totp_attempt('000000', ip='10.0.0.6', now=now + 2, failure_limit=3, lockout=60)
            self.assertEqual(locked.status, 'mfa_locked')
            self.assertGreaterEqual(locked.retry_after, 1)
            during_lockout = director.verify_totp_attempt(director._totp(secret, now + 90), ip='10.0.0.6', now=now + 10, failure_limit=3, lockout=60)
            self.assertEqual(during_lockout.status, 'mfa_locked')
            after_unlock = director.verify_totp_attempt(director._totp(secret, now + 120), ip='10.0.0.6', now=now + 120, failure_limit=3, lockout=60)
            self.assertTrue(after_unlock.ok)
            replay_after_success = director.verify_totp_attempt(code, ip='10.0.0.5', now=now + 1, failure_limit=3, lockout=60)
            self.assertEqual(replay_after_success.status, 'mfa_replay_rejected')
            old_code = director._totp(secret, now - 90)
            future_code = director._totp(secret, now + 240)
            self.assertEqual(director.verify_totp_attempt(old_code, ip='10.0.0.7', now=now, failure_limit=3, lockout=60).status, 'mfa_invalid')
            self.assertEqual(director.verify_totp_attempt(future_code, ip='10.0.0.8', now=now, failure_limit=3, lockout=60).status, 'mfa_invalid')

    def test_totp_success_resets_failure_counters(self):
        secret = 'JBSWY3DPEHPK3PXP'
        now = 1_700_010_000.0
        with mock.patch.object(director, '_load_secret', return_value=secret):
            self.assertEqual(director.verify_totp_attempt('000000', ip='10.0.0.9', now=now, failure_limit=3, lockout=60).status, 'mfa_invalid')
            self.assertEqual(director.verify_totp_attempt('000000', ip='10.0.0.9', now=now + 1, failure_limit=3, lockout=60).status, 'mfa_invalid')
            success = director.verify_totp_attempt(director._totp(secret, now + 30), ip='10.0.0.9', now=now + 30, failure_limit=3, lockout=60)
            self.assertTrue(success.ok)
            self.assertEqual(director.verify_totp_attempt('000000', ip='10.0.0.9', now=now + 31, failure_limit=3, lockout=60).status, 'mfa_invalid')

    def test_rate_limit_is_bounded_and_uses_retry_after(self):
        clock = {'now': 100.0}
        limiter = BoundedRateLimiter(max_keys=1, now_func=lambda: clock['now'])
        self.assertTrue(limiter.check('a', 1, 60).allowed)
        denied = limiter.check('a', 1, 60)
        self.assertFalse(denied.allowed)
        self.assertGreaterEqual(denied.retry_after, 1)
        self.assertFalse(limiter.check('b', 1, 60).allowed)
        clock['now'] = 200.0
        self.assertTrue(limiter.check('b', 1, 60).allowed)

    def test_route_rate_limit_response_is_safe(self):
        original = dict(api.RATE_LIMITS)
        try:
            api.RATE_LIMITS['AUTH'] = (1, 60)
            api.RATE_LIMITER.clear()
            self.assertEqual(self.client.get('/status', headers={'Authorization': 'Bearer test-key'}).status_code, 200)
            limited = self.client.get('/status', headers={'Authorization': 'Bearer test-key'})
            self.assertEqual(limited.status_code, 429)
            self.assertEqual(limited.json()['security_status'], 'rate_limited')
            self.assertIn('Retry-After', limited.headers)
            self.assertNotIn('test-key', limited.text)
        finally:
            api.RATE_LIMITS.clear()
            api.RATE_LIMITS.update(original)
            api.RATE_LIMITER.clear()

    def test_all_route_classes_are_bounded_and_rate_limited(self):
        original = dict(api.RATE_LIMITS)
        principal = AuthPrincipal('api:test', 'fingerprint')
        request = FakeRequest()
        try:
            for route_class in ('AUTH', 'MFA', 'SESSION_MUTATION', 'CHAT', 'UPLOAD', 'DIRECTOR_PRIVILEGED'):
                api.RATE_LIMITS.clear()
                api.RATE_LIMITS.update(original)
                api.RATE_LIMITS[route_class] = (1, 60)
                api.RATE_LIMITER.clear()
                self.assertIsNone(api._apply_rate_limit(request, route_class, principal))
                limited = api._apply_rate_limit(request, route_class, principal)
                self.assertIsNotNone(limited)
                self.assertEqual(limited.status_code, 429)
                self.assertIn('Retry-After', limited.headers)
        finally:
            api.RATE_LIMITS.clear()
            api.RATE_LIMITS.update(original)
            api.RATE_LIMITER.clear()
    def test_spoofed_forwarded_header_is_ignored_without_trusted_proxy(self):
        req = FakeRequest({'x-forwarded-for': '203.0.113.9'})
        self.assertEqual(client_ip_from_request(req, ()), '10.0.0.5')
        self.assertEqual(client_ip_from_request(req, ('10.0.0.5',)), '203.0.113.9')
        malformed = FakeRequest({'x-forwarded-for': 'not-an-ip'})
        self.assertEqual(client_ip_from_request(malformed, ('10.0.0.5',)), '10.0.0.5')

    def test_cors_allows_session_token_header_without_wildcard_credentials(self):
        response = self.client.options(
            '/chat',
            headers={
                'Origin': 'http://localhost:3000',
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'Authorization, X-Session-Token',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('x-session-token', response.headers.get('access-control-allow-headers', '').lower())
        self.assertNotEqual(response.headers.get('access-control-allow-origin'), '*')

    def test_secret_config_fails_closed_for_pilot_and_production(self):
        with self.assertRaises(RuntimeError):
            config.load_config({'APP_MODE': 'controlled_pilot'})
        with self.assertRaises(RuntimeError):
            config.load_config({'APP_MODE': 'controlled_pilot', 'CDSS_API_KEYS': 'test-key', 'CDSS_SECRET_KEY': 'placeholder', 'DIRECTOR_BOOTSTRAP': 'placeholder'})
        with self.assertRaises(RuntimeError):
            config.load_config({'APP_MODE': 'production', 'CDSS_API_KEYS': 'strong-api-key-value-12345', 'CDSS_SECRET_KEY': 'strong-secret-key-value-123456789012345', 'DIRECTOR_BOOTSTRAP': 'strong-bootstrap-value-12345'})
        cfg = config.load_config({'APP_MODE': 'clinical_sandbox', 'CDSS_API_KEYS': 'test-key', 'CDSS_SECRET_KEY': 'sandbox-secret'})
        self.assertEqual(cfg.app_mode, 'clinical_sandbox')
        caps = self.client.get('/capabilities').json()
        self.assertNotIn('test-key', str(caps))
        self.assertNotIn('sandbox-secret', str(caps))

    def _enrollment_config(self, enabled=True, mode='clinical_sandbox'):
        return config.load_config({
            'APP_MODE': mode,
            'CDSS_API_KEYS': 'strong-api-key-value-12345',
            'CDSS_SECRET_KEY': 'strong-secret-key-value-123456789012345',
            'DIRECTOR_BOOTSTRAP': 'strong-bootstrap-value-12345',
            'DIRECTOR_ENROLLMENT_ENABLED': 'true' if enabled else 'false',
        })

    def test_director_enroll_requires_header_explicit_sandbox_enablement_and_one_time_provisioning(self):
        state = {'secret': ''}
        saved_payloads = []

        def fake_save(path, payload):
            saved_payloads.append((path, payload))
            state['secret'] = payload['secret']

        cfg = self._enrollment_config(enabled=True)
        with mock.patch.object(api, 'CONFIG', cfg), \
             mock.patch.object(director, '_load_secret', side_effect=lambda: state['secret']), \
             mock.patch.object(director.crypto_store, 'encrypt_save', side_effect=fake_save), \
             redirect_stderr(io.StringIO()) as stderr:
            missing = self.client.get('/director/enroll')
            wrong = self.client.get('/director/enroll', headers={'X-Director-Bootstrap': 'wrong-bootstrap-secret'})
            query = self.client.get('/director/enroll?bootstrap=strong-bootstrap-value-12345')
            body_json = self.client.request('GET', '/director/enroll', json={'X-Director-Bootstrap': 'strong-bootstrap-value-12345'})
            body_form = self.client.request('GET', '/director/enroll', data={'X-Director-Bootstrap': 'strong-bootstrap-value-12345'})
            cookie = self.client.get('/director/enroll', cookies={'X-Director-Bootstrap': 'strong-bootstrap-value-12345'})
            ok = self.client.get('/director/enroll', headers={'X-Director-Bootstrap': 'strong-bootstrap-value-12345'})
            repeat = self.client.get('/director/enroll', headers={'X-Director-Bootstrap': 'strong-bootstrap-value-12345'})

        for response in (missing, wrong, query, body_json, body_form, cookie, repeat):
            self.assertEqual(response.status_code, 403)
            self.assertNotIn('strong-bootstrap-value-12345', response.text)
            self.assertNotIn('wrong-bootstrap-secret', response.text)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()['status'], 'sukses')
        self.assertIn('otpauth://totp/', ok.json()['otpauth_uri'])
        self.assertEqual(1, len(saved_payloads))
        self.assertNotIn('strong-bootstrap-value-12345', stderr.getvalue())
        self.assertNotIn(state['secret'], stderr.getvalue())

    def test_director_enroll_mode_restrictions_and_default_disabled(self):
        with mock.patch.object(api, 'CONFIG', self._enrollment_config(enabled=False)):
            sandbox_disabled = self.client.get('/director/enroll', headers={'X-Director-Bootstrap': 'strong-bootstrap-value-12345'})
        with mock.patch.object(api, 'CONFIG', self._enrollment_config(enabled=False, mode='controlled_pilot')):
            pilot_default = self.client.get('/director/enroll', headers={'X-Director-Bootstrap': 'strong-bootstrap-value-12345'})
        production_cfg = replace(self._enrollment_config(enabled=False), app_mode='production')
        with mock.patch.object(api, 'CONFIG', production_cfg):
            production_default = self.client.get('/director/enroll', headers={'X-Director-Bootstrap': 'strong-bootstrap-value-12345'})
        self.assertEqual(sandbox_disabled.status_code, 403)
        self.assertEqual(pilot_default.status_code, 403)
        self.assertEqual(production_default.status_code, 403)

    def test_director_enroll_rate_limit_and_metadata_redaction(self):
        original = dict(api.RATE_LIMITS)
        cfg = self._enrollment_config(enabled=True)
        try:
            api.RATE_LIMITS['DIRECTOR_PRIVILEGED'] = (1, 60)
            api.RATE_LIMITER.clear()
            with mock.patch.object(api, 'CONFIG', cfg):
                first = self.client.get('/director/enroll', headers={'X-Director-Bootstrap': 'wrong-bootstrap-secret'})
                limited = self.client.get('/director/enroll', headers={'X-Director-Bootstrap': 'wrong-bootstrap-secret'})
            self.assertEqual(first.status_code, 403)
            self.assertEqual(limited.status_code, 429)
            self.assertIn('Retry-After', limited.headers)
            self.assertNotIn('wrong-bootstrap-secret', limited.text)
        finally:
            api.RATE_LIMITS.clear()
            api.RATE_LIMITS.update(original)
            api.RATE_LIMITER.clear()

        token = director.issue_token()
        metrics_response = self.client.get('/director/metrics', headers={'Authorization': 'Bearer ' + token})
        capabilities_response = self.client.get('/capabilities')
        joined = metrics_response.text + capabilities_response.text
        self.assertNotIn('otpauth://', joined)
        self.assertNotIn('DIRECTOR_BOOTSTRAP', joined)
        self.assertNotIn('strong-bootstrap-value-12345', joined)
        self.assertNotIn('secret=', joined)
    def test_frontend_transport_static_guards(self):
        root = Path(__file__).resolve().parents[2] / 'frontend'
        sources = [root / 'lib' / 'api.ts', root / 'components' / 'app-context.tsx', root / 'app' / 'director-dashboard' / 'page.tsx']
        joined = '\n'.join(path.read_text(encoding='utf-8') for path in sources)
        self.assertNotIn('api_key', joined)
        self.assertNotIn('localStorage', joined)
        self.assertNotIn('sessionStorage', joined)
        self.assertIn('X-Session-Token', joined)
        self.assertIn('Authorization', joined)
        self.assertNotIn('X-Director-Bootstrap', joined)
        self.assertNotIn('DIRECTOR_BOOTSTRAP=', joined)
        self.assertNotIn('?bootstrap=', joined)
        self.assertNotIn('console.log(api', joined)

    def test_owned_source_bypass_scanner(self):
        root = Path(__file__).resolve().parents[2]
        production_sources = [
            root / 'backend' / 'api.py',
            root / 'backend' / 'security_controls.py',
            root / 'backend' / 'director.py',
            root / 'backend' / 'config.py',
            root / 'frontend' / 'lib' / 'api.ts',
            root / 'frontend' / 'components' / 'app-context.tsx',
            root / 'frontend' / 'app' / 'director-dashboard' / 'page.tsx',
        ]
        patterns = {
            'FormData api_key append': 'append("api_key"',
            'FormData api_key append single quote': "append('api_key'",
            'backend form api_key fallback': 'api_key: str = Form',
            'backend form get api_key': 'form.get("api_key"',
            'legacy resolver': 'resolve_key(',
            'local storage': 'localStorage',
            'session storage': 'sessionStorage',
            'console secret log': 'console.log(api',
            'print api secret': 'print(api',
            'weak equality secret compare': '== secret',
            'noncrypto random': 'random.random(',
            'uuid1': 'uuid.uuid1(',
            'wildcard cors list': 'allow_origins=["*"]',
        }
        unexpected = []
        for path in production_sources:
            text = path.read_text(encoding='utf-8')
            for label, needle in patterns.items():
                if needle in text:
                    unexpected.append((path.relative_to(root).as_posix(), label, needle))
        self.assertEqual([], unexpected)


if __name__ == '__main__':
    unittest.main()