from __future__ import annotations

import contextlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
import config  # noqa: E402
import lab_routes  # noqa: E402
import upload_security  # noqa: E402
from audit_ledger import AuditEventInput, LocalAppendOnlyLedgerBackend  # noqa: E402
from lab_fixture_loader import SyntheticFixtureLoader  # noqa: E402
from upload_security import UploadParserConfig, parse_document_bytes, validate_docx_container  # noqa: E402

SPRINT_B_FLAGS = {
    'SYNTHETIC_MULTI_AGENT': 'true',
    'SYNTHETIC_RAG': 'true',
    'SYNTHETIC_REGISTRY': 'true',
    'SYNTHETIC_EBP': 'true',
    'SYNTHETIC_MERMAID': 'true',
    'SYNTHETIC_UPLOADS': 'true',
    'SYNTHETIC_OCR_MOCK': 'true',
    'SYNTHETIC_PHOTO_MOCK': 'true',
    'SYNTHETIC_FEEDBACK_MEMORY': 'true',
}

CANARIES = (
    'PHI-CANARY-NAME-ALPHA',
    'PHI-CANARY-MRN-000001',
    'PHI-CANARY-PHONE-080000000001',
    'PHI-CANARY-ADDRESS-ALPHA',
    'SECRET-CANARY-API-KEY',
    'SECRET-CANARY-SESSION-TOKEN',
    'SECRET-CANARY-OTP',
    'SECRET-CANARY-TOTP-SEED',
    'SECRET-CANARY-LEDGER-KEY',
)

LAB_ROUTES = (
    ('/lab/run', {'query': 'respiratory oxygen monitoring ' + CANARIES[0]}),
    ('/lab/rag', {'query': 'respiratory oxygen monitoring ' + CANARIES[1]}),
    ('/lab/registry', {'code': 'SYN-D-001'}),
    ('/lab/ebp', {}),
    ('/lab/upload', {'fixture_id': 'SYN-UPLOAD-TXT-001'}),
    ('/lab/pathway', {'fixture_id': 'SYN-MMD-SAFE-001'}),
    ('/lab/ocr', {}),
    ('/lab/photo', {}),
    ('/lab/feedback', {'feedback_id': 'SYN-FB-REDTEAM', 'note': 'synthetic closure note'}),
)

LAB_EVENT_TYPES = (
    'lab_feature_run',
    'lab_rag_retrieval',
    'lab_registry_fixture_run',
    'lab_ebp_fixture_run',
    'lab_upload_fixture_run',
    'lab_mermaid_fixture_run',
    'lab_mock_ocr_run',
    'lab_mock_photo_run',
    'lab_feedback_recorded',
)


def _make_zip(entries: dict[str, bytes | str], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, 'w', compression=compression) as zf:
        for name, value in entries.items():
            data = value.encode('utf-8') if isinstance(value, str) else value
            zf.writestr(name, data)
    return bio.getvalue()


def _make_minimal_docx(extra: dict[str, bytes | str] | None = None) -> bytes:
    entries: dict[str, bytes | str] = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>',
        'word/document.xml': '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>synthetic</w:t></w:r></w:p></w:body></w:document>',
    }
    entries.update(extra or {})
    return _make_zip(entries)


def _hang_worker(_path: str, _kind: str, _cfg: dict, _queue) -> None:
    while True:
        time.sleep(1)


def _crash_worker(_path: str, _kind: str, _cfg: dict, _queue) -> None:
    raise RuntimeError('synthetic parser crash marker')


class SyntheticLabRedTeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)
        cls.root = Path(__file__).resolve().parents[2]

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
            'FEATURE_EXTERNAL_LLM': 'false',
            'FEATURE_EBP_EXTERNAL_SEARCH': 'false',
            'FEATURE_CLINICAL_PHOTO_ANALYSIS': 'false',
            'FEATURE_MERMAID_PATHWAY_RENDERING': 'false',
            'HARVEST_INTERVAL_SEC': '0',
            **SPRINT_B_FLAGS,
        }
        env.update(overrides)
        return env

    def core_config(self, **overrides):
        return config.load_config(self.core_env(**overrides))

    def with_config(self, cfg):
        return mock.patch.object(api, 'CONFIG', cfg)

    def lab_session_headers(self):
        lab_session = self.client.post('/lab/session', headers={'Authorization': 'Bearer test-key'})
        self.assertEqual(200, lab_session.status_code, lab_session.text)
        payload = lab_session.json()
        return {
            'Authorization': 'Bearer test-key',
            'X-Lab-Session-Id': payload['lab_session_id'],
            'X-Lab-Session-Token': payload['lab_session_token'],
        }

    def assert_no_canaries(self, payload: object, label: str = '') -> None:
        text = json.dumps(payload, sort_keys=True, default=str)
        for canary in CANARIES:
            self.assertNotIn(canary, text, label or canary)

    def test_phi_and_secret_canaries_absent_from_lab_surfaces(self):
        with self.with_config(self.core_config()), contextlib.redirect_stderr(io.StringIO()) as stderr:
            headers = self.lab_session_headers()
            responses = []
            for route, payload in LAB_ROUTES:
                response = self.client.post(route, headers=headers, json=payload)
                self.assertEqual(200, response.status_code, (route, response.text))
                responses.append(response.json())
            rejected_feedback = self.client.post('/lab/feedback', headers=headers, json={'feedback_id': 'SYN-FB-BLOCK', 'note': ' '.join(CANARIES)})
            self.assertEqual(400, rejected_feedback.status_code)
            rejected_run = self.client.post('/lab/run', headers=headers, json={'force_stage_failure': CANARIES[0]})
            self.assertEqual(400, rejected_run.status_code)

            for payload in responses:
                self.assert_no_canaries(payload, 'lab response')
                trace = self.client.get(f"/lab/trace/{payload['run_id']}", headers=headers)
                self.assertEqual(200, trace.status_code)
                self.assert_no_canaries(trace.json(), 'trace API response')

            self.assert_no_canaries(api.LAB_TRACE_STORE._records, 'trace store')
            self.assert_no_canaries(api.LAB_SESSION_STORE._records, 'session store')
            self.assert_no_canaries(api.LAB_FEEDBACK_STORE._records, 'feedback store')
            self.assert_no_canaries(api.AUDIT_LEDGER._read_lines(), 'audit ledger')
            self.assert_no_canaries(rejected_feedback.json(), 'safe feedback error')
            self.assert_no_canaries(rejected_run.json(), 'safe run error')
            self.assert_no_canaries(self.client.get('/capabilities').json(), 'capability metadata')
            self.assert_no_canaries(stderr.getvalue(), 'runtime log capture')

    def test_offline_network_deny_full_route_closure(self):
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
            stack.enter_context(mock.patch.object(api.harvester, 'run_once', side_effect=AssertionError('harvester run must not execute')))
            stack.enter_context(mock.patch.object(socket, 'create_connection', side_effect=AssertionError('network denied')))
            stack.enter_context(mock.patch.object(socket, 'getaddrinfo', side_effect=AssertionError('network denied')))
            stack.enter_context(mock.patch.object(socket.socket, 'connect', new=deny_external_socket_connect))
            stack.enter_context(mock.patch.object(urllib.request, 'urlopen', side_effect=AssertionError('network denied')))
            if self._module_available('requests'):
                import requests  # noqa: WPS433
                stack.enter_context(mock.patch.object(requests.sessions.Session, 'request', side_effect=AssertionError('network denied')))
            if self._module_available('httpx'):
                import httpx  # noqa: WPS433
                stack.enter_context(mock.patch.object(httpx.HTTPTransport, 'handle_request', side_effect=AssertionError('network denied')))
                stack.enter_context(mock.patch.object(httpx.AsyncHTTPTransport, 'handle_async_request', side_effect=AssertionError('network denied')))
            self.assertEqual(200, self.client.get('/lab/status').status_code)
            headers = self.lab_session_headers()
            run_ids: list[str] = []
            for route, payload in LAB_ROUTES:
                response = self.client.post(route, headers=headers, json=payload)
                self.assertEqual(200, response.status_code, (route, response.text))
                run_ids.append(response.json()['run_id'])
            for run_id in run_ids:
                self.assertEqual(200, self.client.get(f'/lab/trace/{run_id}', headers=headers).status_code)
            normal = self.client.post('/session', headers={'Authorization': 'Bearer test-key'}).json()
            normal_headers = {'Authorization': 'Bearer test-key', 'X-Session-Token': normal['session_token']}
            normal_chat = self.client.post('/chat', data={'provider': 'openai', 'model': 'x', 'framework': '3S', 'session_id': normal['session_id'], 'tier': 'medium', 'agent': 'analisis', 'pertanyaan': 'synthetic'}, headers=normal_headers)
            self.assertEqual(503, normal_chat.status_code)
            self.assertEqual(0, api.CONFIG.harvest_interval_sec)

    def test_kill_switch_closes_all_lab_routes_without_side_effects(self):
        disabled_cfg = config.load_config({'APP_MODE': 'clinical_sandbox', 'CDSS_API_KEYS': 'test-key', 'CDSS_SECRET_KEY': 'sandbox-secret-for-tests', 'SYNTHETIC_LAB_MODE': 'false', 'SYNTHETIC_DATA_ONLY': 'false'})
        with self.with_config(disabled_cfg), contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(SyntheticFixtureLoader, 'load_fixture_by_id', side_effect=AssertionError('fixture load must not run')))
            stack.enter_context(mock.patch.object(lab_routes.LAB_TRACE_STORE, 'create', side_effect=AssertionError('trace write must not run')))
            stack.enter_context(mock.patch.object(lab_routes, 'run_synthetic_upload_fixture', side_effect=AssertionError('parser must not run')))
            stack.enter_context(mock.patch.object(api, 'audit_event', side_effect=AssertionError('audit append must not run')))
            stack.enter_context(mock.patch.object(socket, 'create_connection', side_effect=AssertionError('network denied')))
            self.assertEqual(503, self.client.get('/lab/status').status_code)
            self.assertEqual(503, self.client.post('/lab/session', headers={'Authorization': 'Bearer test-key'}).status_code)
            self.assertEqual(0, api.LAB_SESSION_STORE.count())
            for route, payload in LAB_ROUTES:
                response = self.client.post(route, headers={'Authorization': 'Bearer test-key'}, json=payload)
                self.assertEqual(503, response.status_code, route)
                self.assertEqual('synthetic_lab_disabled', response.json()['error_code'])
            trace = self.client.get('/lab/trace/any-run-id', headers={'Authorization': 'Bearer test-key'})
            self.assertEqual(503, trace.status_code)
            self.assertEqual(0, api.LAB_TRACE_STORE.count())
            self.assertEqual([], api.AUDIT_LEDGER._read_lines())

    def test_audit_ledger_verification_rehearsal_uses_temp_ledger_only(self):
        key = 'synthetic-lab-sprint-c-ledger-key-000000000000000000000000'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lab-sprint-c-ledger.jsonl'
            ledger = LocalAppendOnlyLedgerBackend(path, key, key_id='lab-sprint-c-test', segment_id='lab-sprint-c')
            for event_type in LAB_EVENT_TYPES:
                ledger.append_event(AuditEventInput(
                    event_type=event_type,
                    actor_type='api_principal',
                    actor_id='synthetic-lab-principal',
                    route_class='LAB',
                    action='/' + event_type,
                    outcome='synthetic_lab_safe_metadata_only',
                    status_code=200,
                    security_tags=('lab', 'privacy'),
                    metadata={'run_id': 'run_' + event_type, 'fixture_id': 'SYN-FIXTURE', 'feature_label': 'synthetic closure', 'route': '/lab/rehearsal'},
                ))
            verify_cmd = [sys.executable, 'backend/scripts/verify_audit_ledger.py', '--path', str(path), '--key', key, '--key-id', 'lab-sprint-c-test']
            valid = subprocess.run(verify_cmd, cwd=self.root, text=True, capture_output=True, check=False)
            self.assertEqual(0, valid.returncode, valid.stderr + valid.stdout)
            self.assertTrue(json.loads(valid.stdout)['ok'])
            self.assert_no_canaries(path.read_text(encoding='utf-8'), 'temp ledger')
            self.assert_no_canaries(valid.stdout + valid.stderr, 'verifier output')

            lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
            tampered = json.loads(lines[0])
            tampered['outcome'] = 'changed'
            path.write_text(json.dumps(tampered, sort_keys=True, separators=(',', ':')) + '\n' + ''.join(lines[1:]), encoding='utf-8')
            failed = subprocess.run(verify_cmd, cwd=self.root, text=True, capture_output=True, check=False)
            self.assertEqual(1, failed.returncode)
            self.assertFalse(json.loads(failed.stdout)['ok'])
            tracked = subprocess.run(['git', 'ls-files', str(path)], cwd=self.root, text=True, capture_output=True, check=False)
            self.assertEqual('', tracked.stdout)

    def test_hostile_file_rehearsal_and_upload_privacy(self):
        with self.with_config(self.core_config()):
            headers = self.lab_session_headers()
            safe_txt = self.client.post('/lab/upload', headers=headers, json={'fixture_id': 'SYN-UPLOAD-TXT-001'}).json()
            self.assertEqual('ok', safe_txt['upload_status'])
            hostile_pdf = self.client.post('/lab/upload', headers=headers, json={'fixture_id': 'SYN-UPLOAD-PDF-HOSTILE-001'}).json()
            self.assertEqual('pdf_active_content_rejected', hostile_pdf['upload_status'])
            hostile_docx = self.client.post('/lab/upload', headers=headers, json={'fixture_id': 'SYN-UPLOAD-DOCX-HOSTILE-001'}).json()
            self.assertEqual('docx_macro_content_rejected', hostile_docx['upload_status'])
            joined = json.dumps([safe_txt, hostile_pdf, hostile_docx, api.AUDIT_LEDGER._read_lines()], default=str)
            for forbidden in ('Generated synthetic note for upload parser smoke testing only.', 'C:/', 'PHI-CANARY'):
                self.assertNotIn(forbidden, joined)

        cfg = UploadParserConfig(parser_timeout_sec=0.05)
        with tempfile.TemporaryDirectory() as root:
            workspace = os.path.join(root, 'timeout-workspace')
            with mock.patch.object(upload_security.tempfile, 'mkdtemp', return_value=workspace):
                timeout = parse_document_bytes(b'valid text', 'case.txt', config=cfg, worker=_hang_worker)
            self.assertEqual('parser_timeout', timeout.status)
            self.assertFalse(os.path.exists(workspace))
            self.assertTrue(upload_security.wait_until_process_exits(timeout.child_pid, timeout_sec=2.0))
        crashed = parse_document_bytes(b'valid text', 'case.txt', worker=_crash_worker)
        self.assertEqual('parser_crashed', crashed.status)
        self.assert_no_canaries(crashed.message, 'parser crash message')
        self.assertEqual(validate_docx_container(_make_minimal_docx({'word/vbaProject.bin': b'macro'}), UploadParserConfig()).status, 'docx_macro_content_rejected')
        self.assertEqual(validate_docx_container(_make_minimal_docx({'word/media/payload.zip': b'PK\x03\x04'}), UploadParserConfig()).status, 'docx_nested_archive_rejected')
        self.assertEqual(validate_docx_container(_make_minimal_docx({'../evil.txt': 'x'}), UploadParserConfig()).status, 'docx_path_traversal_rejected')
        bomb_cfg = UploadParserConfig(max_docx_total_uncompressed_bytes=1024 * 1024, max_docx_single_entry_uncompressed_bytes=1024 * 1024, max_docx_compression_ratio=2.0)
        self.assertEqual(validate_docx_container(_make_minimal_docx({'word/large.xml': b'a' * 4096}), bomb_cfg).status, 'docx_zip_bomb_suspected')

    def test_static_secret_and_forbidden_artifact_scan(self):
        tracked = subprocess.run(['git', 'ls-files'], cwd=self.root, text=True, capture_output=True, check=False)
        self.assertEqual(0, tracked.returncode)
        files = [line.strip() for line in tracked.stdout.splitlines() if line.strip()]
        forbidden_paths = [
            path for path in files
            if path == 'AUDIT.md'
            or path.startswith('backend/data_terstruktur/')
            or path.startswith('frontend/.next/')
            or path.startswith('frontend/node_modules/')
            or path.endswith(('.cdss_key', '.director_totp'))
            or re.search(r'(?i)(runtime_ledger|audit_export|audit_segment|patient_record|hospital_document|session_snapshot|mfa_snapshot|rate_limit_snapshot)', path)
        ]
        self.assertEqual([], forbidden_paths)

        secret_patterns = [
            ('private-key-marker', re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----'), set()),
            ('provider-key', re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b'), set()),
            ('otpauth-uri', re.compile(r'otpauth://', re.I), {'backend/director.py', 'backend/director_setup.py'}),
            ('audit-key-assignment', re.compile(r'(?i)AUDIT_LEDGER_HMAC_KEY\s*=\s*["\'][^"\']+'), set()),
            ('cdss-secret-assignment', re.compile(r'(?i)CDSS_SECRET_KEY\s*=\s*["\'][^"\']+'), set()),
        ]
        unexpected: list[str] = []
        for rel in files:
            if rel.startswith(('backend/tests/', 'frontend/tests/', 'docs/remediation/')) or rel in {'README.md', 'JALANKAN.md', 'LAPORAN_EVALUASI_SISTEM.md'}:
                continue
            path = self.root / rel
            if path.suffix.lower() not in {'.py', '.ts', '.tsx', '.js', '.mjs', '.md', '.json'}:
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
            for _name, pattern, allowed_files in secret_patterns:
                if pattern.search(text) and rel not in allowed_files:
                    unexpected.append(rel)
        self.assertEqual([], sorted(set(unexpected)))

    @staticmethod
    def _module_available(name: str) -> bool:
        try:
            __import__(name)
            return True
        except Exception:
            return False


if __name__ == '__main__':
    unittest.main()
