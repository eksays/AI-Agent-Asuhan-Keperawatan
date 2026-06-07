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
import lab_routes  # noqa: E402
import memory  # noqa: E402
from clinical_registry import ClinicalRegistry, valid_code_format  # noqa: E402
from lab_fixture_loader import SyntheticFixtureLoader  # noqa: E402
from lab_feedback import LabFeedbackStore  # noqa: E402
from lab_orchestration import STAGE_ORDER  # noqa: E402
from lab_rag import retrieve_synthetic_context  # noqa: E402
from lab_trace_store import LabTraceStore  # noqa: E402
from lab_trace_store import SAFE_TRACE_FIELDS  # noqa: E402
from registry_release import RegistryReleaseStore  # noqa: E402

SPRINT_B_FLAGS = {
    'SYNTHETIC_MULTI_AGENT': 'synthetic_multi_agent_enabled',
    'SYNTHETIC_RAG': 'synthetic_rag_enabled',
    'SYNTHETIC_REGISTRY': 'synthetic_registry_enabled',
    'SYNTHETIC_EBP': 'synthetic_ebp_enabled',
    'SYNTHETIC_MERMAID': 'synthetic_mermaid_enabled',
    'SYNTHETIC_UPLOADS': 'synthetic_uploads_enabled',
    'SYNTHETIC_OCR_MOCK': 'synthetic_ocr_mock_enabled',
    'SYNTHETIC_PHOTO_MOCK': 'synthetic_photo_mock_enabled',
    'SYNTHETIC_FEEDBACK_MEMORY': 'synthetic_feedback_memory_enabled',
}

LAB_ROUTES = {
    '/lab/run': 'SYNTHETIC_MULTI_AGENT',
    '/lab/rag': 'SYNTHETIC_RAG',
    '/lab/registry': 'SYNTHETIC_REGISTRY',
    '/lab/ebp': 'SYNTHETIC_EBP',
    '/lab/upload': 'SYNTHETIC_UPLOADS',
    '/lab/pathway': 'SYNTHETIC_MERMAID',
    '/lab/ocr': 'SYNTHETIC_OCR_MOCK',
    '/lab/photo': 'SYNTHETIC_PHOTO_MOCK',
    '/lab/feedback': 'SYNTHETIC_FEEDBACK_MEMORY',
}

class SyntheticLabCoreFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)
        cls.fixture_root = Path(__file__).resolve().parent / 'fixtures' / 'synthetic_lab'

    def setUp(self):
        api.RATE_LIMITER.clear()
        api.LAB_SESSION_STORE.clear()
        api.LAB_TRACE_STORE.clear()
        api.LAB_FEEDBACK_STORE.clear()
        api.AUDIT_LEDGER._memory_lines.clear()
        with api._fail_lock:
            api._fail_times.clear()

    def core_env(self, **overrides):
        env = {
            'APP_MODE': 'clinical_sandbox',
            'CDSS_API_KEYS': 'test-key,other-key',
            'CDSS_SECRET_KEY': 'sandbox-secret-for-tests',
            'SYNTHETIC_LAB_MODE': 'true',
            'SYNTHETIC_DATA_ONLY': 'true',
            **{name: 'true' for name in SPRINT_B_FLAGS},
        }
        env.update(overrides)
        return env

    def core_config(self, **overrides):
        return config.load_config(self.core_env(**overrides))

    def lab_session_headers(self):
        lab_session = self.client.post('/lab/session', headers={'Authorization': 'Bearer test-key'})
        self.assertEqual(200, lab_session.status_code, lab_session.text)
        payload = lab_session.json()
        return {
            'Authorization': 'Bearer test-key',
            'X-Lab-Session-Id': payload['lab_session_id'],
            'X-Lab-Session-Token': payload['lab_session_token'],
        }

    def with_config(self, cfg):
        return mock.patch.object(api, 'CONFIG', cfg)

    def test_sprint_b_flags_default_false_and_require_lab_profile(self):
        cfg = config.load_config({})
        caps = config.build_capabilities(cfg)
        for env_name, public_name in SPRINT_B_FLAGS.items():
            self.assertFalse(getattr(cfg, public_name.replace('_enabled', '')))
            self.assertFalse(caps[public_name])
            with self.subTest(env_name=env_name), self.assertRaises(RuntimeError):
                config.load_config({env_name: 'true'})
            with self.subTest(pilot=env_name), self.assertRaises(RuntimeError):
                config.load_config({'APP_MODE': 'controlled_pilot', env_name: 'true'})
            with self.subTest(production=env_name), self.assertRaises(RuntimeError):
                config.load_config({'APP_MODE': 'production', env_name: 'true'})
        enabled = self.core_config()
        enabled_caps = config.build_capabilities(enabled)
        self.assertEqual('offline_core_features', enabled_caps['lab_feature_activation_status'])
        for public_name in SPRINT_B_FLAGS.values():
            self.assertTrue(enabled_caps[public_name])
        self.assertFalse(enabled.feature_external_llm)
        self.assertFalse(enabled.feature_ebp_external_search)
        self.assertFalse(enabled.feature_clinical_photo_analysis)
        self.assertFalse(enabled.feature_mermaid_pathway_rendering)
        self.assertEqual(0, enabled.harvest_interval_sec)

    def test_feature_specific_flag_false_closes_route_after_lab_auth(self):
        for route, flag in LAB_ROUTES.items():
            env = self.core_env(**{flag: 'false'})
            with self.subTest(route=route), self.with_config(config.load_config(env)):
                headers = self.lab_session_headers()
                baseline_ledger = api.AUDIT_LEDGER._read_lines()
                with mock.patch.object(SyntheticFixtureLoader, 'load_fixture_by_id', side_effect=AssertionError('fixture load must not run')), \
                     mock.patch.object(lab_routes.LAB_TRACE_STORE, 'create', side_effect=AssertionError('trace write must not run')), \
                     mock.patch.object(lab_routes, 'run_synthetic_upload_fixture', side_effect=AssertionError('parser must not run')), \
                     mock.patch.object(api, 'get_llm', side_effect=AssertionError('provider must not run')), \
                     mock.patch.object(socket, 'create_connection', side_effect=AssertionError('network denied')):
                    response = self.client.post(route, headers=headers, json={})
                self.assertEqual(503, response.status_code)
                self.assertEqual('lab_feature_disabled', response.json()['error_code'])
                self.assertEqual(0, api.LAB_TRACE_STORE.count())
                self.assertEqual(baseline_ledger, api.AUDIT_LEDGER._read_lines())

    def test_every_sprint_b_route_is_guarded_and_requires_auth_session(self):
        expected = {'/lab/status', '/lab/session', '/lab/trace/{run_id}', *LAB_ROUTES.keys()}
        actual = {getattr(route, 'path', '') for route in api.app.routes if getattr(route, 'path', '').startswith('/lab/')}
        self.assertEqual(expected, actual)
        for route in LAB_ROUTES:
            with self.subTest(disabled=route):
                response = self.client.post(route, json={})
                self.assertEqual(503, response.status_code)
                self.assertEqual('synthetic_lab_disabled', response.json()['error_code'])
        with self.with_config(self.core_config()):
            self.assertEqual(401, self.client.post('/lab/run', json={}).status_code)
            self.assertEqual(404, self.client.post('/lab/run', headers={'Authorization': 'Bearer test-key'}, json={}).status_code)
            headers = self.lab_session_headers()
            response = self.client.post('/lab/run', headers={**headers, 'X-Lab-Session-Token': 'wrong'}, json={})
            self.assertEqual(409, response.status_code)

    def test_lab_route_class_rate_limit_applies(self):
        old = api.RATE_LIMITS['LAB']
        api.RATE_LIMITS['LAB'] = (1, 60)
        try:
            with self.with_config(self.core_config()):
                headers = self.lab_session_headers()
                response = self.client.post('/lab/run', headers=headers, json={})
                self.assertEqual(429, response.status_code)
                self.assertEqual('rate_limited', response.json()['security_status'])
        finally:
            api.RATE_LIMITS['LAB'] = old

    def test_multi_stage_orchestration_trace_and_abstention(self):
        with self.with_config(self.core_config()):
            headers = self.lab_session_headers()
            response = self.client.post('/lab/run', headers=headers, json={'fixture_id': 'SYN-CASE-RESP-001'})
            self.assertEqual(200, response.status_code, response.text)
            payload = response.json()
            self.assertEqual('multi-stage agent orchestration prototype', payload['feature_label'])
            self.assertFalse(payload['accepted_recommendations'])
            self.assertTrue(payload['nurse_review_required'])
            self.assertFalse(payload['registry_authoritative'])
            self.assertFalse(payload['clinical_use_allowed'])
            self.assertTrue(payload['critic_applied'])
            self.assertEqual(['SYN-D-001', 'SYN-O-001', 'SYN-I-001'], [item['code'] for item in payload['prototype_candidates']])
            trace = payload['trace']
            self.assertLessEqual(set(trace), SAFE_TRACE_FIELDS)
            self.assertEqual(STAGE_ORDER, trace['agent_stages'])
            self.assertEqual('deterministic_mock', trace['provider_type'])
            self.assertIn('SYN-DOC-RESP-001', trace['retrieved_document_ids'])
            self.assertFalse(trace['accepted_recommendations'])
            joined = json.dumps(payload)
            for forbidden in ('raw prompt', 'raw output', 'chain-of-thought', 'test-key', headers['X-Lab-Session-Token'], 'PHI-CANARY', 'SECRET-CANARY'):
                self.assertNotIn(forbidden, joined)

            failure = self.client.post('/lab/run', headers=headers, json={'force_stage_failure': 'assessment'}).json()
            self.assertIn('stage_failure', failure['validation_issue_codes'])
            timeout = self.client.post('/lab/run', headers=headers, json={'force_timeout': True}).json()
            self.assertIn('stage_timeout', timeout['validation_issue_codes'])
            unknown = self.client.post('/lab/run', headers=headers, json={'force_stage_failure': 'raw prompt'})
            self.assertEqual(400, unknown.status_code)
            self.assertEqual('lab_safe_failure', unknown.json()['error_code'])

    def test_lab_trace_authorization_is_bound_to_session_and_principal(self):
        with self.with_config(self.core_config()):
            headers_a = self.lab_session_headers()
            run = self.client.post('/lab/run', headers=headers_a, json={'fixture_id': 'SYN-CASE-RESP-001'}).json()
            run_id = run['run_id']
            self.assertEqual(200, self.client.get(f'/lab/trace/{run_id}', headers=headers_a).status_code)
            self.assertIsNone(api.LAB_TRACE_STORE.get(run_id))

            headers_b = self.lab_session_headers()
            cross_session = self.client.get(f'/lab/trace/{run_id}', headers=headers_b)
            self.assertEqual(404, cross_session.status_code)
            self.assertEqual('lab_trace_not_found', cross_session.json()['error_code'])

            other_session = self.client.post('/lab/session', headers={'Authorization': 'Bearer other-key'}).json()
            other_headers = {
                'Authorization': 'Bearer other-key',
                'X-Lab-Session-Id': other_session['lab_session_id'],
                'X-Lab-Session-Token': other_session['lab_session_token'],
            }
            wrong_principal = self.client.get(f'/lab/trace/{run_id}', headers=other_headers)
            self.assertEqual(404, wrong_principal.status_code)

            self.assertNotEqual(200, self.client.get(f'/lab/trace/{run_id}', headers={'Authorization': 'Bearer test-key', 'X-Lab-Session-Id': headers_a['X-Lab-Session-Id']}).status_code)
            self.assertNotEqual(200, self.client.get(f'/lab/trace/{run_id}', headers={**headers_a, 'X-Lab-Session-Token': 'wrong-token'}).status_code)
            self.assertEqual(404, self.client.get('/lab/trace/random-run-id', headers=headers_a).status_code)
            self.assertNotEqual(200, self.client.get(f'/lab/trace/{run_id}', headers={'Authorization': 'Bearer test-key'}).status_code)

        clock = {'now': 100.0}
        expiring_store = LabTraceStore(ttl_sec=1, now_func=lambda: clock['now'])
        with mock.patch.object(lab_routes, 'LAB_TRACE_STORE', expiring_store), mock.patch.object(api, 'LAB_TRACE_STORE', expiring_store), self.with_config(self.core_config()):
            headers = self.lab_session_headers()
            run = self.client.post('/lab/run', headers=headers, json={'fixture_id': 'SYN-CASE-RESP-001'}).json()
            self.assertEqual(200, self.client.get(f"/lab/trace/{run['run_id']}", headers=headers).status_code)
            clock['now'] = 102.0
            expired = self.client.get(f"/lab/trace/{run['run_id']}", headers=headers)
            self.assertEqual(404, expired.status_code)

    def test_synthetic_lexical_rag_stable_scores_and_weak_context_abstention(self):
        with self.with_config(self.core_config()):
            headers = self.lab_session_headers()
            strong = self.client.post('/lab/rag', headers=headers, json={'query': 'respiratory oxygen monitoring'}).json()
            self.assertIn('SYN-DOC-RESP-001', strong['retrieved_document_ids'])
            self.assertEqual('synthetic_fixture_lexical', strong['retrieval_source'])
            self.assertFalse(strong['weak_context'])
            again = self.client.post('/lab/rag', headers=headers, json={'query': 'respiratory oxygen monitoring'}).json()
            self.assertEqual(strong['retrieved_document_ids'], again['retrieved_document_ids'])
            self.assertEqual(strong['retrieval_scores'], again['retrieval_scores'])
            weak = self.client.post('/lab/rag', headers=headers, json={'query': 'zzzz qqqq'}).json()
            self.assertTrue(weak['weak_context'])
            self.assertFalse(weak['accepted_recommendations'])
            self.assertTrue(weak['nurse_review_required'])
            loader = SyntheticFixtureLoader(self.fixture_root)
            bounded = retrieve_synthetic_context(loader, fixture_id='SYN-RAG-RESP-001', query='synthetic observation monitoring', top_k=99)
            self.assertLessEqual(len(bounded.retrieved_document_ids), 5)
            empty = retrieve_synthetic_context(loader, fixture_id='SYN-RAG-RESP-001', query='')
            self.assertTrue(empty.weak_context)
            with self.assertRaises(Exception):
                retrieve_synthetic_context(loader, fixture_id='SYN-RAG-UNKNOWN', query='respiratory')
            trace_text = json.dumps(strong['trace'])
            self.assertNotIn('synthetic respiratory monitoring oxygen saturation breathing observation safety label', trace_text)

    def test_synthetic_registry_is_lab_only_and_normal_policy_unchanged(self):
        with self.with_config(self.core_config()):
            headers = self.lab_session_headers()
            release_store = RegistryReleaseStore()
            self.assertIsNone(release_store.active_release('SDKI', 'diagnosis'))
            lab = self.client.post('/lab/registry', headers=headers, json={'code': 'SYN-D-001'}).json()
            self.assertEqual('SYN-D-001', lab['prototype_candidates'][0]['code'])
            self.assertFalse(lab['registry_authoritative'])
            self.assertFalse(lab['clinical_use_allowed'])
            rejected = self.client.post('/lab/registry', headers=headers, json={'code': 'SYN-D-999'})
            self.assertEqual(400, rejected.status_code)
            self.assertEqual('lab_registry_code_rejected', rejected.json()['error_code'])
            self.assertFalse(valid_code_format('SDKI', 'SYN-D-001'))
            self.assertFalse(api.CLINICAL_REGISTRY.approved_available('SDKI'))
            self.assertIsInstance(api.CLINICAL_REGISTRY, ClinicalRegistry)
            self.assertIsNone(release_store.active_release('SDKI', 'diagnosis'))

    def test_offline_ebp_upload_mermaid_ocr_photo_and_feedback(self):
        with self.with_config(self.core_config()):
            headers = self.lab_session_headers()
            ebp = self.client.post('/lab/ebp', headers=headers, json={}).json()
            self.assertEqual('offline synthetic EBP fixture', ebp['source_label'])
            self.assertFalse(ebp['clinical_use_allowed'])

            safe_txt = self.client.post('/lab/upload', headers=headers, json={'fixture_id': 'SYN-UPLOAD-TXT-001'}).json()
            self.assertEqual('ok', safe_txt['upload_status'])
            hostile_pdf = self.client.post('/lab/upload', headers=headers, json={'fixture_id': 'SYN-UPLOAD-PDF-HOSTILE-001'}).json()
            self.assertEqual('pdf_active_content_rejected', hostile_pdf['upload_status'])
            hostile_docx = self.client.post('/lab/upload', headers=headers, json={'fixture_id': 'SYN-UPLOAD-DOCX-HOSTILE-001'}).json()
            self.assertEqual('docx_macro_content_rejected', hostile_docx['upload_status'])
            for bad_fixture in ('../outside.txt', 'C:/outside.txt', 'backend/data_terstruktur/SDKI.json'):
                with self.subTest(bad_fixture=bad_fixture):
                    rejected_upload = self.client.post('/lab/upload', headers=headers, json={'fixture_id': bad_fixture})
                    self.assertEqual(400, rejected_upload.status_code)
                    self.assertEqual('lab_fixture_rejected', rejected_upload.json()['error_code'])
            ledger_text = '\n'.join(api.AUDIT_LEDGER._read_lines())
            trace_text = json.dumps(safe_txt['trace'])
            self.assertNotIn('Generated synthetic note for upload parser smoke testing only.', trace_text)
            self.assertNotIn('Generated synthetic note for upload parser smoke testing only.', ledger_text)

            pathway = self.client.post('/lab/pathway', headers=headers, json={'fixture_id': 'SYN-MMD-SAFE-001'}).json()
            self.assertIn('flowchart TD', pathway['mermaid'])
            malicious = self.client.post('/lab/pathway', headers=headers, json={'fixture_id': 'SYN-MMD-MAL-001'})
            self.assertEqual(400, malicious.status_code)
            self.assertEqual('lab_fixture_rejected', malicious.json()['error_code'])

            ocr = self.client.post('/lab/ocr', headers=headers, json={}).json()
            self.assertEqual('DETERMINISTIC OCR MOCK - EXTRACTION UNVERIFIED', ocr['mock_label'])
            photo = self.client.post('/lab/photo', headers=headers, json={}).json()
            self.assertEqual('DETERMINISTIC PHOTO MOCK - NOT CLINICAL IMAGE ANALYSIS', photo['mock_label'])

            feedback = self.client.post('/lab/feedback', headers=headers, json={'feedback_id': 'SYN-FB-001', 'rating': 'up', 'note': 'synthetic note'}).json()
            self.assertEqual(1, feedback['feedback_count'])
            blocked = self.client.post('/lab/feedback', headers=headers, json={'feedback_id': 'SYN-FB-002', 'note': 'PHI-CANARY secret-canary'})
            self.assertEqual(400, blocked.status_code)

            other_headers = self.lab_session_headers()
            self.assertEqual([], api.LAB_FEEDBACK_STORE.recall(other_headers['X-Lab-Session-Id']))
            with tempfile.TemporaryDirectory() as td, mock.patch.object(memory, '_FILE', str(Path(td) / 'feedback_memory.json')):
                memory.store_feedback('3S', 'normal question', 'normal answer', 'up', 'normal correction', 'normal-session')
            self.assertEqual([], api.LAB_FEEDBACK_STORE.recall('normal-session'))

            clock = {'now': 100.0}
            store = LabFeedbackStore(ttl_sec=2, max_sessions=1, max_entries_per_session=1, now_func=lambda: clock['now'])
            store.record('session-a', feedback_id='SYN-FB-A', rating='up', note='synthetic note')
            store.record('session-a', feedback_id='SYN-FB-B', rating='down', note='synthetic followup')
            self.assertEqual([{'feedback_id': 'SYN-FB-B', 'rating': 'down', 'note_length': len('synthetic followup')}], store.recall('session-a'))
            store.record('session-b', feedback_id='SYN-FB-C', rating='up', note='synthetic note')
            self.assertEqual([], store.recall('session-a'))
            clock['now'] = 103.0
            self.assertEqual([], store.recall('session-b'))

    def test_normal_routes_unchanged_with_all_lab_flags_enabled(self):
        with self.with_config(self.core_config()):
            normal = self.client.post('/session', headers={'Authorization': 'Bearer test-key'}).json()
            headers = {'Authorization': 'Bearer test-key', 'X-Session-Token': normal['session_token']}
            self.assertEqual(503, self.client.post('/chat', data={'provider': 'openai', 'model': 'x', 'framework': '3S', 'session_id': normal['session_id'], 'tier': 'medium', 'agent': 'analisis', 'pertanyaan': 'buat diagnosis'}, headers=headers).status_code)
            self.assertEqual(503, self.client.post('/chat_stream', data={'provider': 'openai', 'model': 'x', 'framework': '3S', 'session_id': normal['session_id'], 'tier': 'medium', 'agent': 'analisis', 'pertanyaan': 'buat diagnosis'}, headers=headers).status_code)
            self.assertEqual(503, self.client.post('/analisis', data={'provider': 'openai', 'model': 'x', 'framework': '3S', 'session_id': normal['session_id'], 'tier': 'medium', 'gejala': 'synthetic'}, headers=headers).status_code)
            self.assertEqual(503, self.client.post('/analisis_multi', data={'provider': 'openai', 'model': 'x', 'framework': '3S', 'session_id': normal['session_id'], 'tier': 'medium', 'gejala': 'synthetic'}, headers=headers).status_code)
            pathway = self.client.post('/pathway', data={'provider': 'openai', 'model': 'x', 'framework': '3S', 'session_id': normal['session_id'], 'gejala': 'synthetic'}, headers=headers)
            self.assertEqual(503, pathway.status_code)
            feedback = self.client.post('/feedback', data={'framework': '3S', 'session_id': normal['session_id'], 'pertanyaan': 'p', 'jawaban': 'j', 'rating': 'up'}, headers=headers)
            self.assertEqual(200, feedback.status_code)
            caps = self.client.get('/capabilities').json()
            self.assertFalse(caps['capabilities']['external_llm']['enabled'])
            self.assertFalse(caps['capabilities']['ebp_external_search']['enabled'])
            self.assertFalse(caps['capabilities']['clinical_photo_analysis']['enabled'])
            self.assertFalse(caps['capabilities']['mermaid_pathway_rendering']['enabled'])
            self.assertEqual(0, api.CONFIG.harvest_interval_sec)

    def test_offline_network_deny_all_sprint_b_routes(self):
        original_socket_connect = socket.socket.connect

        def deny_external_socket_connect(sock, address):
            host = address[0] if isinstance(address, tuple) and address else ''
            if host in {'127.0.0.1', '::1', 'localhost'}:
                return original_socket_connect(sock, address)
            raise AssertionError('network denied')

        with self.with_config(self.core_config()), contextlib.ExitStack() as stack:
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
            headers = self.lab_session_headers()
            calls = [
                ('/lab/run', {}),
                ('/lab/rag', {'query': 'respiratory oxygen monitoring'}),
                ('/lab/registry', {'code': 'SYN-D-001'}),
                ('/lab/ebp', {}),
                ('/lab/upload', {'fixture_id': 'SYN-UPLOAD-PDF-HOSTILE-001'}),
                ('/lab/pathway', {'fixture_id': 'SYN-MMD-SAFE-001'}),
                ('/lab/ocr', {}),
                ('/lab/photo', {}),
                ('/lab/feedback', {'feedback_id': 'SYN-FB-001'}),
            ]
            run_ids = []
            for route, payload in calls:
                response = self.client.post(route, headers=headers, json=payload)
                self.assertEqual(200, response.status_code, (route, response.text))
                run_ids.append(response.json()['run_id'])
            for run_id in run_ids:
                trace = self.client.get(f'/lab/trace/{run_id}', headers=headers)
                self.assertEqual(200, trace.status_code)

    def test_audit_ledger_safe_metadata_only(self):
        with self.with_config(self.core_config()):
            headers = self.lab_session_headers()
            self.client.post('/lab/run', headers=headers, json={'fixture_id': 'SYN-CASE-RESP-001'})
            self.client.post('/lab/rag', headers=headers, json={'query': 'respiratory oxygen monitoring'})
            self.client.post('/lab/registry', headers=headers, json={'code': 'SYN-D-001'})
            self.client.post('/lab/ebp', headers=headers, json={})
            self.client.post('/lab/upload', headers=headers, json={'fixture_id': 'SYN-UPLOAD-TXT-001'})
            self.client.post('/lab/pathway', headers=headers, json={'fixture_id': 'SYN-MMD-SAFE-001'})
            self.client.post('/lab/ocr', headers=headers, json={})
            self.client.post('/lab/photo', headers=headers, json={})
            self.client.post('/lab/feedback', headers=headers, json={'feedback_id': 'SYN-FB-AUDIT', 'note': 'synthetic note'})
            lines = api.AUDIT_LEDGER._read_lines()
            for event_type in (
                'lab_feature_run',
                'lab_rag_retrieval',
                'lab_registry_fixture_run',
                'lab_ebp_fixture_run',
                'lab_upload_fixture_run',
                'lab_mermaid_fixture_run',
                'lab_mock_ocr_run',
                'lab_mock_photo_run',
                'lab_feedback_recorded',
            ):
                self.assertTrue(any(event_type in line for line in lines), event_type)
            joined = '\n'.join(lines)
            for forbidden in ('PHI-CANARY', 'SECRET-CANARY', headers['X-Lab-Session-Token'], 'test-key', 'synthetic note', 'raw prompt', 'raw output', 'chain-of-thought'):
                self.assertNotIn(forbidden, joined)

    def test_sprint_b_bypass_scanner_has_only_reviewed_matches(self):
        root = Path(__file__).resolve().parents[2]
        sources = [
            *sorted((root / 'backend').glob('lab*.py')),
            root / 'backend' / 'config.py',
            root / 'frontend' / 'lib' / 'capabilities.ts',
            root / 'frontend' / 'lib' / 'api.ts',
            root / 'frontend' / 'components' / 'dashboard.tsx',
            root / 'frontend' / 'components' / 'synthetic-lab-trace-panel.tsx',
        ]
        allowed = {
            'backend/data_terstruktur': set(),
            'FEATURE_EXTERNAL_LLM': {'backend/config.py'},
            'FEATURE_EBP_EXTERNAL_SEARCH': {'backend/config.py'},
            'FEATURE_CLINICAL_PHOTO_ANALYSIS': {'backend/config.py'},
            'FEATURE_MERMAID_PATHWAY_RENDERING': {'backend/config.py'},
            'HARVEST_INTERVAL_SEC': {'backend/config.py'},
            'get_llm(': set(),
            'urlopen(': set(),
            'requests.': set(),
            'httpx.': set(),
            'socket.': set(),
            'Anthropic': set(),
            'OpenAI': set(),
            'DeepSeek': set(),
            'localStorage': set(),
            'sessionStorage': set(),
            'raw prompt': {'backend/lab_trace_store.py', 'frontend/components/synthetic-lab-trace-panel.tsx'},
            'raw output': {'backend/lab_trace_store.py', 'frontend/components/synthetic-lab-trace-panel.tsx'},
            'chain-of-thought': {'backend/lab_trace_store.py', 'frontend/components/synthetic-lab-trace-panel.tsx'},
            'reasoning': set(),
            'filesystem path': {'backend/lab_trace_store.py'},
            'stack trace': {'backend/lab_trace_store.py'},
            'dangerouslySetInnerHTML': set(),
            'innerHTML': set(),
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
