from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import socket
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
import config  # noqa: E402
from lab_fixture_loader import LabFixtureError, SyntheticFixtureLoader  # noqa: E402
from lab_routes import LabSessionStore  # noqa: E402
from lab_trace_store import SAFE_TRACE_FIELDS, LabTraceStore, LabTraceValidationError  # noqa: E402
from security_controls import AuthPrincipal, token_digest  # noqa: E402


class SyntheticLabFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)
        cls.fixture_root = Path(__file__).resolve().parent / 'fixtures' / 'synthetic_lab'

    def setUp(self):
        api.RATE_LIMITER.clear()
        api.LAB_SESSION_STORE.clear()
        api.LAB_TRACE_STORE.clear()
        with api._fail_lock:
            api._fail_times.clear()

    def enabled_config(self):
        return config.load_config({
            'APP_MODE': 'clinical_sandbox',
            'CDSS_API_KEYS': 'test-key',
            'CDSS_SECRET_KEY': 'sandbox-secret-for-tests',
            'SYNTHETIC_LAB_MODE': 'true',
            'SYNTHETIC_DATA_ONLY': 'true',
        })

    def trace_payload(self, **overrides):
        payload = {
            'mode': 'clinical_sandbox',
            'fixture_case_id': 'SYN-FOUNDATION-001',
            'route': '/lab/status',
            'agent_stages': ['foundation'],
            'stage_status': 'complete',
            'latency_ms': 1,
            'provider_type': 'none',
            'retrieved_document_ids': [],
            'retrieval_scores': [],
            'retrieval_source': 'none',
            'registry_source': 'none',
            'registry_authoritative': False,
            'clinical_use_allowed': False,
            'clinical_status': 'not_for_patient_care',
            'accepted_recommendations': False,
            'nurse_review_required': True,
            'audit_event_ids': [],
            'sanitization_status': 'safe_metadata_only',
        }
        payload.update(overrides)
        return payload

    def test_lab_flags_default_false_and_fail_closed_by_mode(self):
        cfg = config.load_config({})
        self.assertFalse(cfg.synthetic_lab_mode)
        self.assertFalse(cfg.synthetic_data_only)
        caps = config.build_capabilities(cfg)
        self.assertFalse(caps['synthetic_lab_enabled'])
        self.assertFalse(caps['synthetic_data_only'])
        self.assertEqual('/lab', caps['lab_namespace'])
        self.assertFalse(caps['lab_external_provider_enabled'])
        self.assertEqual('disabled', caps['lab_feature_activation_status'])

        enabled = self.enabled_config()
        self.assertTrue(config.build_capabilities(enabled)['synthetic_lab_enabled'])
        self.assertEqual('foundation_only', config.build_capabilities(enabled)['lab_feature_activation_status'])

        with self.assertRaises(RuntimeError):
            config.load_config({'SYNTHETIC_LAB_MODE': 'true'})
        with self.assertRaises(RuntimeError):
            config.load_config({'APP_MODE': 'controlled_pilot', 'SYNTHETIC_DATA_ONLY': 'true'})
        with self.assertRaises(RuntimeError):
            config.load_config({'APP_MODE': 'production', 'SYNTHETIC_LAB_MODE': 'true', 'SYNTHETIC_DATA_ONLY': 'true'})

        bounded = config.load_config({
            'SYNTHETIC_LAB_MODE': 'true',
            'SYNTHETIC_DATA_ONLY': 'true',
            'SYNTHETIC_LAB_TRACE_MAX_RUNS': '-1',
            'SYNTHETIC_LAB_TRACE_MAX_METADATA_BYTES': '999999999',
        })
        self.assertEqual(128, bounded.synthetic_lab_trace_max_runs)
        self.assertEqual(8192, bounded.synthetic_lab_trace_max_metadata_bytes)

    def test_lab_profile_rejects_offline_incompatible_settings(self):
        base = {
            'APP_MODE': 'clinical_sandbox',
            'CDSS_API_KEYS': 'test-key',
            'CDSS_SECRET_KEY': 'sandbox-secret-for-tests',
            'SYNTHETIC_LAB_MODE': 'true',
            'SYNTHETIC_DATA_ONLY': 'true',
        }
        incompatible = (
            {'FEATURE_EXTERNAL_LLM': 'true'},
            {'FEATURE_EBP_EXTERNAL_SEARCH': 'true'},
            {'FEATURE_CLINICAL_PHOTO_ANALYSIS': 'true'},
            {'FEATURE_MERMAID_PATHWAY_RENDERING': 'true'},
            {'HARVEST_INTERVAL_SEC': '1'},
        )
        for extra in incompatible:
            with self.subTest(extra=extra), self.assertRaises(RuntimeError):
                config.load_config({**base, **extra})

        non_lab = config.load_config({'FEATURE_MERMAID_PATHWAY_RENDERING': 'true', 'HARVEST_INTERVAL_SEC': '1'})
        self.assertFalse(non_lab.synthetic_lab_mode)
        self.assertTrue(non_lab.feature_mermaid_pathway_rendering)
        self.assertEqual(1, non_lab.harvest_interval_sec)

    def test_config_and_loader_reject_unapproved_fixture_roots(self):
        lab_env = {
            'APP_MODE': 'clinical_sandbox',
            'SYNTHETIC_LAB_MODE': 'true',
            'SYNTHETIC_DATA_ONLY': 'true',
        }
        with tempfile.TemporaryDirectory() as outside:
            for root in (outside, str(Path(api.BASE) / 'data_terstruktur'), str(Path(outside) / 'external-fixtures')):
                with self.subTest(root=root), self.assertRaises(RuntimeError):
                    config.load_config({**lab_env, 'SYNTHETIC_LAB_FIXTURE_ROOT': root})
                with self.subTest(loader_root=root), self.assertRaises(LabFixtureError):
                    SyntheticFixtureLoader(root).load_manifest()

        with tempfile.TemporaryDirectory(dir=self.fixture_root.parent) as approved_tmp:
            for forbidden_name in ('uploads', 'runtime_logs', 'hospital_documents', 'patient_records'):
                root = Path(approved_tmp) / forbidden_name
                with self.subTest(forbidden_name=forbidden_name), self.assertRaises(RuntimeError):
                    config.load_config({**lab_env, 'SYNTHETIC_LAB_FIXTURE_ROOT': str(root)})
                with self.subTest(loader_forbidden_name=forbidden_name), self.assertRaises(LabFixtureError):
                    SyntheticFixtureLoader(root).load_manifest()

        with tempfile.TemporaryDirectory(dir=self.fixture_root.parent) as approved_tmp:
            approved = Path(approved_tmp) / 'synthetic_lab_case'
            (approved / 'cases').mkdir(parents=True)
            (approved / 'manifest.json').write_text(json.dumps({
                'fixture_set': 'synthetic_lab_test',
                'fixture_version': '1',
                'synthetic_only': True,
                'authoritative': False,
                'clinical_use_allowed': False,
                'source_type': 'generated_fixture',
                'files': ['cases/ok.json'],
            }), encoding='utf-8')
            (approved / 'cases' / 'ok.json').write_text(json.dumps({
                'fixture_id': 'SYN-TEST-001',
                'fixture_version': '1',
                'synthetic_only': True,
                'authoritative': False,
                'clinical_use_allowed': False,
                'source_type': 'generated_fixture',
                'created_for': 'security_ux_orchestration_testing',
            }), encoding='utf-8')
            cfg = config.load_config({**lab_env, 'SYNTHETIC_LAB_FIXTURE_ROOT': str(approved)})
            self.assertEqual(str(approved.resolve(strict=False)), cfg.synthetic_lab_fixture_root)
            self.assertEqual('synthetic_lab_test', SyntheticFixtureLoader(approved).load_manifest().fixture_set)

    def test_config_rejects_root_symlink_escape_where_supported(self):
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory(dir=self.fixture_root.parent) as approved_tmp:
            link = Path(approved_tmp) / 'root-link'
            try:
                os.symlink(outside, link, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f'symlink creation unavailable on this platform: {exc}')
            with self.assertRaises(RuntimeError):
                config.load_config({
                    'APP_MODE': 'clinical_sandbox',
                    'SYNTHETIC_LAB_MODE': 'true',
                    'SYNTHETIC_DATA_ONLY': 'true',
                    'SYNTHETIC_LAB_FIXTURE_ROOT': str(link),
                })

    def test_kill_switch_closes_lab_routes_without_side_effects(self):
        self.assertEqual(0, api.LAB_SESSION_STORE.count())
        self.assertEqual(0, api.LAB_TRACE_STORE.count())
        with mock.patch.object(api, 'get_llm', side_effect=AssertionError('provider must not be called')) as provider, \
             mock.patch.object(SyntheticFixtureLoader, 'load_manifest', side_effect=AssertionError('fixture loader must not be called')) as loader, \
             mock.patch.object(socket, 'create_connection', side_effect=AssertionError('network denied')) as create_connection:
            status = self.client.get('/lab/status')
            self.assertEqual(503, status.status_code)
            self.assertEqual({'status', 'error_code', 'message'}, set(status.json()))
            self.assertEqual('synthetic_lab_disabled', status.json()['error_code'])
            self.assertEqual('Synthetic integration lab is unavailable.', status.json()['message'])

            session = self.client.post('/lab/session', headers={'Authorization': 'Bearer test-key'})
            self.assertEqual(503, session.status_code)

            trace = self.client.get(
                '/lab/trace/not-real',
                headers={
                    'Authorization': 'Bearer test-key',
                    'X-Lab-Session-Id': 'not-real',
                    'X-Lab-Session-Token': 'not-real',
                },
            )
            self.assertEqual(503, trace.status_code)
            provider.assert_not_called()
            loader.assert_not_called()
            create_connection.assert_not_called()
        self.assertEqual(0, api.LAB_SESSION_STORE.count())
        self.assertEqual(0, api.LAB_TRACE_STORE.count())

    def test_lab_route_registration_is_guarded_router_only(self):
        lab_routes = {getattr(route, 'path', ''): route for route in api.app.routes if getattr(route, 'path', '').startswith('/lab/')}
        self.assertEqual({'/lab/status', '/lab/session', '/lab/trace/{run_id}'}, set(lab_routes))
        for route in lab_routes.values():
            self.assertEqual('lab_routes', route.endpoint.__module__)

    def test_enabled_lab_routes_require_auth_and_keep_session_namespace_isolated(self):
        cfg = self.enabled_config()
        with mock.patch.object(api, 'CONFIG', cfg):
            status = self.client.get('/lab/status')
            self.assertEqual(200, status.status_code)
            self.assertEqual({
                'mode',
                'synthetic_lab_enabled',
                'synthetic_data_only',
                'feature_activation_status',
                'external_provider_enabled',
                'authoritative_registry_enabled',
                'clinical_use_allowed',
            }, set(status.json()))
            self.assertEqual('foundation_only', status.json()['feature_activation_status'])
            self.assertFalse(status.json()['external_provider_enabled'])
            self.assertFalse(status.json()['authoritative_registry_enabled'])
            self.assertFalse(status.json()['clinical_use_allowed'])

            self.assertEqual(401, self.client.post('/lab/session').status_code)
            self.assertEqual(401, self.client.post('/lab/session', headers={'Authorization': 'Bearer wrong-key'}).status_code)
            lab_session = self.client.post('/lab/session', headers={'Authorization': 'Bearer test-key'})
            self.assertEqual(200, lab_session.status_code)
            lab_payload = lab_session.json()
            self.assertTrue(lab_payload['lab_session_id'].startswith('lab_'))
            self.assertEqual(1, api.LAB_SESSION_STORE.count())

            missing_lab_id = self.client.get('/lab/trace/not-real', headers={'Authorization': 'Bearer test-key', 'X-Lab-Session-Token': lab_payload['lab_session_token']})
            self.assertNotEqual(200, missing_lab_id.status_code)
            missing_lab_token = self.client.get('/lab/trace/not-real', headers={'Authorization': 'Bearer test-key', 'X-Lab-Session-Id': lab_payload['lab_session_id']})
            self.assertNotEqual(200, missing_lab_token.status_code)
            wrong_lab_token = self.client.get('/lab/trace/not-real', headers={'Authorization': 'Bearer test-key', 'X-Lab-Session-Id': lab_payload['lab_session_id'], 'X-Lab-Session-Token': 'wrong-token'})
            self.assertNotEqual(200, wrong_lab_token.status_code)

            normal_session = self.client.post('/session', headers={'Authorization': 'Bearer test-key'}).json()
            normal_unlock = self.client.get(
                '/lab/trace/not-real',
                headers={
                    'Authorization': 'Bearer test-key',
                    'X-Lab-Session-Id': normal_session['session_id'],
                    'X-Lab-Session-Token': normal_session['session_token'],
                },
            )
            self.assertNotEqual(200, normal_unlock.status_code)

            cfg_two_keys = config.load_config({
                'APP_MODE': 'clinical_sandbox',
                'CDSS_API_KEYS': 'test-key,other-key',
                'CDSS_SECRET_KEY': 'sandbox-secret-for-tests',
                'SYNTHETIC_LAB_MODE': 'true',
                'SYNTHETIC_DATA_ONLY': 'true',
            })
            with mock.patch.object(api, 'CONFIG', cfg_two_keys):
                wrong_owner = self.client.get(
                    '/lab/trace/not-real',
                    headers={
                        'Authorization': 'Bearer other-key',
                        'X-Lab-Session-Id': lab_payload['lab_session_id'],
                        'X-Lab-Session-Token': lab_payload['lab_session_token'],
                    },
                )
            self.assertEqual(403, wrong_owner.status_code)

            lab_unlock_normal = self.client.post(
                '/feedback',
                data={'framework': '3S', 'session_id': lab_payload['lab_session_id']},
                headers={'Authorization': 'Bearer test-key', 'X-Session-Token': lab_payload['lab_session_token']},
            )
            self.assertNotEqual(200, lab_unlock_normal.status_code)

            created = api.LAB_TRACE_STORE.create(self.trace_payload())
            trace = self.client.get(
                f"/lab/trace/{created['run_id']}",
                headers={
                    'Authorization': 'Bearer test-key',
                    'X-Lab-Session-Id': lab_payload['lab_session_id'],
                    'X-Lab-Session-Token': lab_payload['lab_session_token'],
                },
            )
            self.assertEqual(200, trace.status_code)
            self.assertEqual(created['run_id'], trace.json()['trace']['run_id'])
            self.assertLessEqual(set(trace.json()['trace']), SAFE_TRACE_FIELDS)
            joined = json.dumps(trace.json())
            self.assertNotIn(lab_payload['lab_session_token'], joined)
            self.assertNotIn('test-key', joined)

    def test_lab_session_store_digest_owner_ttl_capacity_and_safe_metadata(self):
        clock = {'now': 100.0}
        store = LabSessionStore(ttl_sec=60, max_active=1, now_func=lambda: clock['now'])
        principal = AuthPrincipal('api:test', 'fingerprint-test')
        other = AuthPrincipal('api:other', 'fingerprint-other')
        sid, token = store.issue(principal, 'pepper')
        rec = store._records[sid]
        self.assertTrue(sid.startswith('lab_'))
        self.assertNotIn(token, str(rec))
        self.assertEqual(token_digest(token, 'pepper'), rec['token_digest'])
        self.assertEqual('session_owner_mismatch', store.validate(sid, other, token, 'pepper'))
        self.assertEqual('session_token_invalid', store.validate(sid, principal, 'wrong-token', 'pepper'))
        sid2, token2 = store.issue(principal, 'pepper')
        self.assertEqual('session_not_found', store.validate(sid, principal, token, 'pepper'))
        self.assertEqual('ok', store.validate(sid2, principal, token2, 'pepper'))
        clock['now'] = 200.0
        self.assertEqual('session_not_found', store.validate(sid2, principal, token2, 'pepper'))

    def test_fixture_loader_accepts_only_manifest_allowlisted_synthetic_files(self):
        loader = SyntheticFixtureLoader(self.fixture_root)
        manifest = loader.load_manifest()
        self.assertEqual(('cases/foundation_case.json',), manifest.files)
        case = loader.load_fixture('cases/foundation_case.json')
        self.assertTrue(case['synthetic_only'])
        self.assertFalse(case['authoritative'])
        self.assertFalse(case['clinical_use_allowed'])
        with self.assertRaises(LabFixtureError):
            loader.load_fixture('cases/not-in-manifest.json')

    def test_fixture_loader_rejects_traversal_absolute_forbidden_and_invalid_manifest(self):
        with tempfile.TemporaryDirectory(dir=self.fixture_root.parent) as tmp:
            root = Path(tmp)
            (root / 'cases').mkdir()
            valid_body = {
                'fixture_id': 'SYN-TEST-001',
                'fixture_version': '1',
                'synthetic_only': True,
                'authoritative': False,
                'clinical_use_allowed': False,
                'source_type': 'generated_fixture',
                'created_for': 'security_ux_orchestration_testing',
            }
            (root / 'cases' / 'ok.json').write_text(__import__('json').dumps(valid_body), encoding='utf-8')

            def write_manifest(files, **metadata):
                payload = {
                    'fixture_set': 'synthetic_lab_test',
                    'fixture_version': '1',
                    'synthetic_only': True,
                    'authoritative': False,
                    'clinical_use_allowed': False,
                    'source_type': 'generated_fixture',
                    'files': files,
                }
                payload.update(metadata)
                (root / 'manifest.json').write_text(__import__('json').dumps(payload), encoding='utf-8')

            for bad_files in (["../escape.json"], [str(root / 'cases' / 'ok.json')], ['backend/data_terstruktur/registry.json'], ['cases/missing.json']):
                write_manifest(bad_files)
                with self.assertRaises(LabFixtureError):
                    SyntheticFixtureLoader(root).load_manifest()

            write_manifest(['cases/ok.json'], synthetic_only=False)
            with self.assertRaises(LabFixtureError):
                SyntheticFixtureLoader(root).load_manifest()

            write_manifest(['cases/ok.json'])
            loaded = SyntheticFixtureLoader(root).load_fixture('cases/ok.json')
            self.assertEqual('SYN-TEST-001', loaded['fixture_id'])

    def test_fixture_loader_rejects_symlink_escape_where_supported(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory(dir=self.fixture_root.parent) as approved_tmp:
            root = Path(approved_tmp) / 'root'
            outside = Path(tmp) / 'outside.json'
            (root / 'cases').mkdir(parents=True)
            outside.write_text('{}', encoding='utf-8')
            link = root / 'cases' / 'escape.json'
            try:
                os.symlink(outside, link)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f'symlink creation unavailable on this platform: {exc}')
            (root / 'manifest.json').write_text(json.dumps({
                'fixture_set': 'synthetic_lab_test',
                'fixture_version': '1',
                'synthetic_only': True,
                'authoritative': False,
                'clinical_use_allowed': False,
                'source_type': 'generated_fixture',
                'files': ['cases/escape.json'],
            }), encoding='utf-8')
            with self.assertRaises(LabFixtureError):
                SyntheticFixtureLoader(root).load_manifest()

    def test_trace_store_opaque_bounded_ttl_and_safe_metadata_only(self):
        clock = {'now': 100.0}
        store = LabTraceStore(
            ttl_sec=10,
            max_runs=1,
            max_stages=1,
            max_document_ids=1,
            max_metadata_bytes=600,
            now_func=lambda: clock['now'],
        )
        payload = {
            'mode': 'clinical_sandbox',
            'fixture_case_id': 'SYN-FOUNDATION-001',
            'route': '/lab/status',
            'agent_stages': ['foundation'],
            'stage_status': 'complete',
            'latency_ms': 1,
            'provider_type': 'none',
            'retrieved_document_ids': ['SYN-DOC-001'],
            'retrieval_scores': [1.0],
            'retrieval_source': 'none',
            'registry_source': 'none',
            'registry_authoritative': False,
            'clinical_use_allowed': False,
            'clinical_status': 'not_for_patient_care',
            'accepted_recommendations': False,
            'nurse_review_required': True,
            'audit_event_ids': [],
            'sanitization_status': 'safe_metadata_only',
        }
        first = store.create(payload)
        self.assertIn('run_id', first)
        self.assertNotIn('SYN-FOUNDATION-001', first['run_id'])
        with self.assertRaises(LabTraceValidationError):
            store.create({**payload, 'raw_prompt': 'never store this'})
        with self.assertRaises(LabTraceValidationError):
            store.create({**payload, 'clinical_status': 'PHI-CANARY-123'})
        with self.assertRaises(LabTraceValidationError):
            store.create({**payload, 'clinical_status': 'secret-canary'})
        with self.assertRaises(LabTraceValidationError):
            store.create({**payload, 'audit_event_ids': ['raw prompt should never appear']})
        with self.assertRaises(LabTraceValidationError):
            store.create({**payload, 'audit_event_ids': [{'clinical_status': 'api key leaked'}]})
        with self.assertRaises(LabTraceValidationError):
            store.create({**payload, 'agent_stages': ['one', 'two']})
        with self.assertRaises(LabTraceValidationError):
            store.create({**payload, 'clinical_status': 'x' * 1000})

        second = store.create(payload)
        self.assertIsNone(store.get(first['run_id']))
        self.assertIsNotNone(store.get(second['run_id']))
        clock['now'] = 111.0
        self.assertIsNone(store.get(second['run_id']))

    def test_offline_network_deny_still_allows_sprint_a_foundation(self):
        cfg = self.enabled_config()
        original_socket_connect = socket.socket.connect

        def deny_external_socket_connect(sock, address):
            host = address[0] if isinstance(address, tuple) and address else ''
            if host in {'127.0.0.1', '::1', 'localhost'}:
                return original_socket_connect(sock, address)
            raise AssertionError('network denied')

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(api, 'CONFIG', cfg))
            stack.enter_context(mock.patch.object(api, 'get_llm', side_effect=AssertionError('provider must not be called')))
            stack.enter_context(mock.patch.object(api.ebp, 'retrieve_context', side_effect=AssertionError('EBP must not be called')))
            stack.enter_context(mock.patch.object(api.harvester, 'start', side_effect=AssertionError('harvester must not start')))
            stack.enter_context(mock.patch.object(socket, 'create_connection', side_effect=AssertionError('network denied')))
            stack.enter_context(mock.patch.object(socket.socket, 'connect', new=deny_external_socket_connect))
            stack.enter_context(mock.patch.object(urllib.request, 'urlopen', side_effect=AssertionError('network denied')))
            if importlib.util.find_spec('requests'):
                import requests  # noqa: WPS433
                stack.enter_context(mock.patch.object(requests.sessions.Session, 'request', side_effect=AssertionError('network denied')))
            if importlib.util.find_spec('httpx'):
                import httpx  # noqa: WPS433
                stack.enter_context(mock.patch.object(httpx.HTTPTransport, 'handle_request', side_effect=AssertionError('network denied')))
                stack.enter_context(mock.patch.object(httpx.AsyncHTTPTransport, 'handle_async_request', side_effect=AssertionError('network denied')))
            self.assertEqual(200, self.client.get('/lab/status').status_code)
            lab_session = self.client.post('/lab/session', headers={'Authorization': 'Bearer test-key'})
            self.assertEqual(200, lab_session.status_code)
            self.assertEqual('synthetic_lab_foundation', SyntheticFixtureLoader(self.fixture_root).load_manifest().fixture_set)
            trace = api.LAB_TRACE_STORE.create(self.trace_payload())
            self.assertIn('run_id', trace)
            lab_payload = lab_session.json()
            trace_response = self.client.get(
                f"/lab/trace/{trace['run_id']}",
                headers={
                    'Authorization': 'Bearer test-key',
                    'X-Lab-Session-Id': lab_payload['lab_session_id'],
                    'X-Lab-Session-Token': lab_payload['lab_session_token'],
                },
            )
            self.assertEqual(200, trace_response.status_code)

    def test_normal_route_behavior_unchanged_with_lab_absent_or_enabled(self):
        self.assertEqual(401, self.client.get('/status').status_code)
        self.assertEqual(200, self.client.get('/status', headers={'Authorization': 'Bearer test-key'}).status_code)
        with mock.patch.object(api, 'CONFIG', self.enabled_config()):
            self.assertEqual(401, self.client.get('/status').status_code)
            self.assertEqual(200, self.client.get('/status', headers={'Authorization': 'Bearer test-key'}).status_code)
            caps = self.client.get('/capabilities').json()
            self.assertFalse(caps['capabilities']['external_llm']['enabled'])
            self.assertFalse(caps['capabilities']['ebp_external_search']['enabled'])
            self.assertFalse(caps['capabilities']['clinical_photo_analysis']['enabled'])
            self.assertFalse(caps['capabilities']['mermaid_pathway_rendering']['enabled'])

    def test_sprint_a_bypass_scanner_has_only_reviewed_matches(self):
        root = Path(__file__).resolve().parents[2]
        sources = [
            root / 'backend' / 'api.py',
            root / 'backend' / 'config.py',
            root / 'backend' / 'lab_config.py',
            root / 'backend' / 'lab_fixture_loader.py',
            root / 'backend' / 'lab_routes.py',
            root / 'backend' / 'lab_trace_store.py',
            root / 'frontend' / 'lib' / 'capabilities.ts',
            root / 'frontend' / 'components' / 'dashboard.tsx',
        ]
        allowed = {
            'SYNTHETIC_LAB_MODE': {'backend/config.py'},
            'backend/data_terstruktur': set(),
            '/lab/': set(),
            'raw prompt': {'backend/lab_trace_store.py'},
            'raw output': {'backend/lab_trace_store.py'},
            'chain-of-thought': {'backend/lab_trace_store.py'},
            'localStorage': set(),
            'sessionStorage': set(),
            'fixture root': {'backend/lab_fixture_loader.py', 'backend/lab_config.py'},
            'open(': {'backend/api.py'},
            'Path(': {'backend/lab_fixture_loader.py', 'backend/lab_config.py'},
            'resolve(': {'backend/lab_fixture_loader.py', 'backend/lab_config.py'},
            'requests.': set(),
            'httpx.': set(),
            'urlopen(': set(),
            'socket.': set(),
        }
        unexpected = []
        for path in sources:
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding='utf-8')
            for needle, allowed_files in allowed.items():
                if needle in text and rel not in allowed_files:
                    unexpected.append((rel, needle))
        self.assertEqual([], unexpected)


if __name__ == '__main__':
    unittest.main()
