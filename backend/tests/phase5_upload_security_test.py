from __future__ import annotations

import io
import json
import os
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
import upload_security  # noqa: E402
from upload_security import UploadParserConfig, parse_document_bytes, validate_docx_container  # noqa: E402


def make_pdf(page_count: int = 1) -> bytes:
    from PyPDF2 import PdfWriter

    bio = io.BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    writer.write(bio)
    return bio.getvalue()

def make_encrypted_pdf() -> bytes:
    from PyPDF2 import PdfWriter

    bio = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt('synthetic-password')
    writer.write(bio)
    return bio.getvalue()


def make_docx(text: str = 'RR 28 x/menit dan SpO2 90%.') -> bytes:
    from docx import Document

    bio = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(bio)
    return bio.getvalue()


def make_zip(entries: dict[str, bytes | str], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, 'w', compression=compression) as zf:
        for name, value in entries.items():
            data = value.encode('utf-8') if isinstance(value, str) else value
            zf.writestr(name, data)
    return bio.getvalue()

def mark_zip_members_encrypted(raw: bytes) -> bytes:
    patched = bytearray(raw)
    for signature, flag_offset in ((b'PK\x03\x04', 6), (b'PK\x01\x02', 8)):
        start = 0
        while True:
            idx = patched.find(signature, start)
            if idx < 0:
                break
            patched[idx + flag_offset] |= 0x1
            start = idx + 1
    return bytes(patched)


def make_minimal_docx_zip(extra: dict[str, bytes | str] | None = None) -> bytes:
    entries: dict[str, bytes | str] = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>',
        'word/document.xml': '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>synthetic</w:t></w:r></w:p></w:body></w:document>',
    }
    entries.update(extra or {})
    return make_zip(entries)

def make_duplicate_docx_zip(member_name: str = 'word/document.xml') -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', '<Types></Types>')
        zf.writestr('word/document.xml', '<w:document>first</w:document>')
        zf.writestr(member_name, '<w:document>duplicate</w:document>')
    return bio.getvalue()


def hang_worker(_path: str, _kind: str, _cfg: dict, _queue) -> None:
    while True:
        time.sleep(1)

def large_payload_worker(_path: str, kind: str, _cfg: dict, queue) -> None:
    queue.put({'status': 'ok', 'detected_type': kind, 'text': 'x' * 4096}, block=False)

def workspace_probe_worker(path: str, kind: str, _cfg: dict, queue) -> None:
    p = Path(path)
    queue.put({
        'status': 'ok',
        'detected_type': kind,
        'text': json.dumps({
            'name': p.name,
            'exists': p.exists(),
            'is_symlink': p.is_symlink(),
            'parent_prefix': p.parent.name.startswith('cdss_upload_parse_'),
        }, sort_keys=True),
    }, block=False)


def network_probe_worker(_path: str, kind: str, _cfg: dict, queue) -> None:
    upload_security._install_parser_runtime_guards()
    import httpx
    import requests

    blocked: list[str] = []
    probes = [
        ('socket.connect', lambda: socket.socket().connect(('127.0.0.1', 9))),
        ('socket.create_connection', lambda: socket.create_connection(('127.0.0.1', 9), timeout=0.1)),
        ('socket.getaddrinfo', lambda: socket.getaddrinfo('example.com', 443)),
        ('urllib.request.urlopen', lambda: getattr(urllib.request, 'urlopen')('https://example.com', timeout=0.1)),
        ('requests.get', lambda: requests.get('https://example.com', timeout=0.1)),
        ('httpx.get', lambda: httpx.get('https://example.com', timeout=0.1)),
        ('subprocess.run', lambda: getattr(subprocess, 'run')([sys.executable, '-c', 'print(1)'], check=False)),
        ('subprocess.Popen', lambda: getattr(subprocess, 'Popen')([sys.executable, '-c', 'print(1)'])),
        ('os.system', lambda: os.system('echo blocked')),
        # Intentional hostile probe; parser guard must reject shell execution before command launch.
        ('shell=True', lambda: getattr(subprocess, 'Popen')('echo blocked', shell=True)),  # nosec B604
    ]
    for name, probe in probes:
        try:
            probe()
        except Exception:
            blocked.append(name)
    queue.put({'status': 'ok', 'detected_type': kind, 'text': json.dumps(sorted(blocked))}, block=False)


class Phase5UploadParserTests(unittest.TestCase):
    def test_valid_pdf_docx_and_text_are_accepted(self):
        cases = [
            ('case.pdf', make_pdf(), 'application/pdf', 'pdf'),
            ('case.docx', make_docx(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'docx'),
            ('case.txt', b'RR 28 x/menit dan SpO2 90%.', 'text/plain', 'text'),
        ]
        for filename, raw, mime, expected_type in cases:
            with self.subTest(filename=filename):
                result = parse_document_bytes(raw, filename, mime)
                self.assertEqual(result.status, 'ok')
                self.assertEqual(result.detected_type, expected_type)
                self.assertTrue(result.parser_invoked)

    def test_extension_and_mime_mismatch_handling(self):
        self.assertEqual(parse_document_bytes(b'plain text', 'case.pdf', 'application/pdf').status, 'type_mismatch')
        self.assertEqual(parse_document_bytes(make_pdf(), 'case.txt', 'text/plain').status, 'type_mismatch')
        mime_mismatch = parse_document_bytes(b'plain text', 'case.txt', 'application/pdf')
        self.assertEqual(mime_mismatch.status, 'ok')
        self.assertEqual(mime_mismatch.detected_type, 'text')

    def test_empty_oversized_long_filename_and_binary_garbage_rejected(self):
        self.assertEqual(parse_document_bytes(b'', 'case.txt').status, 'empty_file')
        cfg = UploadParserConfig(max_upload_bytes=8)
        with mock.patch('upload_security._parser_worker', side_effect=AssertionError('parser should not run')):
            self.assertEqual(parse_document_bytes(b'0123456789', 'case.txt', config=cfg).status, 'file_too_large')
        long_name = ('a' * 181) + '.txt'
        self.assertEqual(parse_document_bytes(b'text', long_name).status, 'filename_too_long')
        self.assertEqual(parse_document_bytes(b'MZ\x00\x01binary', 'case.txt').status, 'unsupported_type')
        self.assertEqual(parse_document_bytes(b'\xff\xfe\xfd', 'case.txt').status, 'unsupported_type')
        self.assertEqual(parse_document_bytes(b'clean\x00text', 'case.txt').status, 'unsupported_type')
        self.assertEqual(parse_document_bytes(b'a\x01b\x02c\x03d\x04e\x05', 'case.txt').status, 'unsupported_type')

    def test_fake_and_unsupported_archives_are_rejected(self):
        generic_zip = make_zip({'hello.txt': 'hello'})
        self.assertEqual(parse_document_bytes(generic_zip, 'case.docx').status, 'unsupported_type')
        self.assertEqual(parse_document_bytes(generic_zip, 'case.pdf').status, 'unsupported_type')
        self.assertEqual(parse_document_bytes(b'not a docx', 'case.docx').status, 'type_mismatch')
        self.assertEqual(parse_document_bytes(b'\x89PNG\r\n\x1a\n', 'case.pdf').status, 'unsupported_type')

    def test_docx_container_validation_rejects_hostile_members(self):
        cfg = UploadParserConfig(max_docx_entries=5)
        cases = [
            ('traversal', make_minimal_docx_zip({'../evil.txt': 'x'}), 'docx_path_traversal_rejected'),
            ('absolute-posix', make_minimal_docx_zip({'/evil.xml': 'x'}), 'docx_path_traversal_rejected'),
            ('windows-drive', make_minimal_docx_zip({'C:/evil.xml': 'x'}), 'docx_path_traversal_rejected'),
            ('macro', make_minimal_docx_zip({'word/vbaProject.bin': b'macro'}), 'docx_macro_content_rejected'),
            ('nested', make_minimal_docx_zip({'word/media/payload.zip': b'PK\x03\x04'}), 'docx_nested_archive_rejected'),
            ('external-relationship', make_minimal_docx_zip({'word/_rels/document.xml.rels': '<Relationships><Relationship TargetMode="External" Target="https://evil.example/file" /></Relationships>'}), 'docx_external_relationship_rejected'),
            ('mixed-case-external-relationship', make_minimal_docx_zip({'word/_rels/document.xml.rels': '<Relationships><Relationship TARGETMODE="ExTeRnAl" Target="https://evil.example/file" /></Relationships>'}), 'docx_external_relationship_rejected'),
            ('missing-content-types', make_zip({'word/document.xml': '<w:document></w:document>'}), 'unsupported_type'),
            ('missing-document', make_zip({'[Content_Types].xml': '<Types></Types>'}), 'unsupported_type'),
            ('duplicate-member', make_duplicate_docx_zip('word/document.xml'), 'docx_archive_limit_exceeded'),
            ('case-insensitive-duplicate', make_minimal_docx_zip({'word/Case.xml': 'a', 'word/case.xml': 'b'}), 'docx_archive_limit_exceeded'),
            ('excessive-entries', make_minimal_docx_zip({f'word/item{i}.xml': 'x' for i in range(10)}), 'docx_archive_limit_exceeded'),
        ]
        self.assertIsNone(upload_security._normalize_zip_member('word\\evil.xml'))
        self.assertIsNone(upload_security._normalize_zip_member('C:/evil.xml'))
        self.assertIsNone(upload_security._normalize_zip_member('\\\\server\\share\\evil.xml'))
        self.assertIsNone(upload_security._normalize_zip_member('//server/share/evil.xml'))
        self.assertIsNone(upload_security._normalize_zip_member('\uff0e\uff0e/evil.xml'))
        for label, raw, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(validate_docx_container(raw, cfg).status, expected)

    def test_docx_encrypted_member_and_oversized_single_member_rejected(self):
        encrypted = mark_zip_members_encrypted(make_minimal_docx_zip())
        self.assertEqual(validate_docx_container(encrypted, UploadParserConfig()).status, 'docx_path_traversal_rejected')
        raw = make_minimal_docx_zip({'word/large-single.xml': b'a' * 4096})
        cfg = UploadParserConfig(max_docx_single_entry_uncompressed_bytes=1024, max_docx_total_uncompressed_bytes=8192)
        self.assertEqual(validate_docx_container(raw, cfg).status, 'docx_archive_limit_exceeded')

    def test_docx_size_and_compression_limits_are_enforced(self):
        raw = make_minimal_docx_zip({'word/large.xml': b'a' * 4096})
        total_cfg = UploadParserConfig(max_docx_total_uncompressed_bytes=1024, max_docx_single_entry_uncompressed_bytes=8192)
        self.assertEqual(validate_docx_container(raw, total_cfg).status, 'docx_archive_limit_exceeded')
        ratio_cfg = UploadParserConfig(max_docx_total_uncompressed_bytes=1024 * 1024, max_docx_single_entry_uncompressed_bytes=1024 * 1024, max_docx_compression_ratio=2.0)
        self.assertEqual(validate_docx_container(raw, ratio_cfg).status, 'docx_zip_bomb_suspected')

    def test_pdf_page_and_extracted_character_limits_are_enforced(self):
        pdf_cfg = UploadParserConfig(max_pdf_pages=1)
        self.assertEqual(parse_document_bytes(make_pdf(page_count=2), 'case.pdf', config=pdf_cfg).status, 'pdf_page_limit_exceeded')
        text_cfg = UploadParserConfig(max_upload_bytes=1024, max_extracted_chars=5)
        self.assertEqual(parse_document_bytes(b'0123456789abcdef', 'case.txt', config=text_cfg).status, 'extracted_text_too_large')

    def test_pdf_policy_rejects_malformed_encrypted_and_active_content(self):
        self.assertEqual(parse_document_bytes(make_pdf(), 'case.pdf').status, 'ok')
        self.assertEqual(parse_document_bytes(b'not a pdf', 'case.pdf').status, 'type_mismatch')
        self.assertEqual(parse_document_bytes(b'%PDF-malformed synthetic patient canary', 'case.pdf').status, 'parser_crashed')
        self.assertEqual(parse_document_bytes(make_encrypted_pdf(), 'case.pdf').status, 'unsupported_type')
        self.assertEqual(parse_document_bytes(make_pdf() + b'\n/EmbeddedFile synthetic attachment', 'case.pdf').status, 'pdf_active_content_rejected')
        self.assertEqual(parse_document_bytes(make_pdf() + b'\n/JavaScript /JS synthetic action', 'case.pdf').status, 'pdf_active_content_rejected')

    def test_hung_parser_process_is_terminated_and_workspace_removed(self):
        cfg = UploadParserConfig(parser_timeout_sec=0.2)
        with tempfile.TemporaryDirectory() as root:
            workspace = os.path.join(root, 'parser-workspace')
            with mock.patch.object(upload_security.tempfile, 'mkdtemp', return_value=workspace):
                result = parse_document_bytes(b'valid text', 'case.txt', config=cfg, worker=hang_worker)
            self.assertEqual(result.status, 'parser_timeout')
            self.assertFalse(os.path.exists(workspace))
            self.assertTrue(upload_security.wait_until_process_exits(result.child_pid, timeout_sec=2.0))

    def test_repeated_parser_timeouts_do_not_leak_children_or_workspaces(self):
        cfg = UploadParserConfig(parser_timeout_sec=0.05)
        with tempfile.TemporaryDirectory() as root:
            workspaces = [os.path.join(root, f'timeout-{idx}') for idx in range(20)]
            with mock.patch.object(upload_security.tempfile, 'mkdtemp', side_effect=workspaces):
                results = [parse_document_bytes(b'valid text', 'case.txt', config=cfg, worker=hang_worker) for _ in range(20)]
            self.assertTrue(all(result.status == 'parser_timeout' for result in results))
            self.assertTrue(all(upload_security.wait_until_process_exits(result.child_pid, timeout_sec=2.0) for result in results))
            self.assertTrue(all(not os.path.exists(path) for path in workspaces))
            self.assertEqual(upload_security.multiprocessing.active_children(), [])

    def test_crashed_parser_returns_safe_error_without_path_or_content_leak(self):
        result = parse_document_bytes(b'%PDF-synthetic uploaded patient text', 'case.pdf')
        self.assertEqual(result.status, 'parser_crashed')
        self.assertNotIn('synthetic uploaded patient text', result.message)
        self.assertNotIn('C:/secret/path', result.message)

    def test_parser_result_payload_limit_is_enforced_and_workspace_removed(self):
        cfg = UploadParserConfig(max_parser_result_bytes=128)
        with tempfile.TemporaryDirectory() as root:
            workspace = os.path.join(root, 'large-payload-workspace')
            with mock.patch.object(upload_security.tempfile, 'mkdtemp', return_value=workspace):
                result = parse_document_bytes(b'valid text', 'case.txt', config=cfg, worker=large_payload_worker)
            self.assertEqual(result.status, 'extracted_text_too_large')
            self.assertFalse(os.path.exists(workspace))

    def test_temporary_workspace_cleanup_after_success_and_rejection(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = os.path.join(root, 'success-workspace')
            with mock.patch.object(upload_security.tempfile, 'mkdtemp', return_value=workspace):
                result = parse_document_bytes(b'valid text', 'case.txt')
            self.assertEqual(result.status, 'ok')
            self.assertFalse(os.path.exists(workspace))
        with mock.patch.object(upload_security.tempfile, 'mkdtemp', side_effect=AssertionError('no workspace for pre-parser rejection')):
            self.assertEqual(parse_document_bytes(b'', 'case.txt').status, 'empty_file')

    def test_parent_controlled_workspace_and_copied_input_are_used(self):
        result = parse_document_bytes(b'valid text', 'case.txt', worker=workspace_probe_worker)
        self.assertEqual(result.status, 'ok')
        payload = json.loads(result.text)
        self.assertEqual(payload['name'], 'upload.bin')
        self.assertTrue(payload['exists'])
        self.assertFalse(payload['is_symlink'])
        self.assertTrue(payload['parent_prefix'])

    def test_parser_child_network_and_command_execution_are_blocked(self):
        result = parse_document_bytes(b'valid text', 'case.txt', worker=network_probe_worker)
        self.assertEqual(result.status, 'ok')
        blocked = set(json.loads(result.text))
        self.assertEqual(blocked, {
            'httpx.get', 'os.system', 'requests.get', 'shell=True', 'socket.connect',
            'socket.create_connection', 'socket.getaddrinfo', 'subprocess.Popen',
            'subprocess.run', 'urllib.request.urlopen'
        })


class Phase5ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)

    def _session_id(self) -> str:
        data = self.client.post('/session', headers=self._headers()).json()
        self._session_headers = {'Authorization': 'Bearer test-key', 'X-Session-Token': data['session_token']}
        return data['session_id']

    def _headers(self) -> dict[str, str]:
        return getattr(self, '_session_headers', {'Authorization': 'Bearer test-key'})

    def _common(self) -> dict[str, str]:
        return {
            'provider': 'openai',
            'model': 'dummy',
            'framework': '3S',
            'session_id': self._session_id(),
            'tier': 'medium',
            'agent': 'analisis',
            'gejala': 'susun analisis dari dokumen',
        }

    def test_analysis_routes_reject_hostile_document_before_provider(self):
        for path in ('/analisis', '/analisis_multi'):
            with self.subTest(path=path), mock.patch.object(api, 'get_llm', side_effect=AssertionError('provider must not be called')):
                response = self.client.post(
                    path,
                    data=self._common(),
                    files={'file_dokumen': ('fake.pdf', b'plain text', 'application/pdf')},
                    headers=self._headers(),
                )
            self.assertEqual(response.status_code, 400)
            body = response.json()
            self.assertEqual(body['upload_status'], 'type_mismatch')
            self.assertFalse(body['accepted_upload'])
            self.assertNotIn('plain text', body['pesan'])

    def test_valid_text_hits_existing_external_llm_gate_without_provider_call(self):
        with mock.patch.object(api, 'get_llm', side_effect=AssertionError('provider must not be called')):
            response = self.client.post(
                '/analisis_multi',
                data=self._common(),
                files={'file_dokumen': ('synthetic.txt', b'keluhan nyeri', 'application/pdf')},
                headers=self._headers(),
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['capability'], 'external_llm')

    def test_analysis_routes_return_safe_statuses_for_size_timeout_and_crash(self):
        cases = [
            ('oversized', ('too-big.txt', b'a' * (api.MAX_UPLOAD + 1), 'text/plain'), 413, 'file_too_large', None),
            ('timeout', ('case.txt', b'valid text', 'text/plain'), 422, 'parser_timeout', api.UploadParseResult(status='parser_timeout', message=upload_security.safe_message('parser_timeout'))),
            ('crashed', ('case.txt', b'valid text', 'text/plain'), 422, 'parser_crashed', api.UploadParseResult(status='parser_crashed', message=upload_security.safe_message('parser_crashed'))),
        ]
        for label, upload, expected_code, expected_status, mocked_result in cases:
            for path in ('/analisis', '/analisis_multi'):
                with self.subTest(label=label, path=path), mock.patch.object(api, 'get_llm', side_effect=AssertionError('provider must not be called')):
                    patcher = mock.patch.object(api, 'parse_document_bytes', return_value=mocked_result) if mocked_result else mock.patch.object(api, 'parse_document_bytes', wraps=api.parse_document_bytes)
                    with patcher:
                        response = self.client.post(
                            path,
                            data=self._common(),
                            files={'file_dokumen': upload},
                            headers=self._headers(),
                        )
                self.assertEqual(response.status_code, expected_code)
                body = response.json()
                self.assertEqual(body['upload_status'], expected_status)
                self.assertFalse(body['accepted_upload'])

    def test_raw_parser_exception_path_does_not_expose_path_or_canary(self):
        for path in ('/analisis', '/analisis_multi'):
            with self.subTest(path=path), mock.patch.object(api, 'get_llm', side_effect=AssertionError('provider must not be called')), \
                 mock.patch.object(api, 'parse_document_bytes', side_effect=RuntimeError('C:/tmp/parser synthetic patient canary')):
                response = self.client.post(
                    path,
                    data=self._common(),
                    files={'file_dokumen': ('case.txt', b'synthetic patient canary', 'text/plain')},
                    headers=self._headers(),
                )
            self.assertEqual(response.status_code, 422)
            body = response.json()
            self.assertEqual(body['upload_status'], 'parser_crashed')
            self.assertNotIn('synthetic patient canary', json.dumps(body))
            self.assertNotIn('C:/tmp/parser', json.dumps(body))

    def test_photo_upload_remains_unsupported(self):
        with mock.patch.object(api, 'get_llm', side_effect=AssertionError('provider must not be called')):
            response = self.client.post(
                '/analisis_multi',
                data=self._common(),
                files={'file_foto': ('synthetic.jpg', b'\xff\xd8\xff\xd9', 'image/jpeg')},
                headers=self._headers(),
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['capability'], 'clinical_photo_analysis')


class Phase5BypassScannerTests(unittest.TestCase):
    def test_owned_backend_source_has_no_unreviewed_upload_parser_bypass_patterns(self):
        root = Path(__file__).resolve().parents[1]
        patterns = {
            'ThreadPoolExecutor': 'ThreadPoolExecutor',
            'future.result(timeout=': 'future.result(timeout=',
            'filename.endswith(': 'filename.endswith(',
            'endswith(".pdf")': 'endswith(".pdf")',
            'endswith(".docx")': 'endswith(".docx")',
            'endswith(".txt")': 'endswith(".txt")',
            'ZipFile.extractall(': 'ZipFile.extractall(',
            'shell=True': 'shell=True',
            'os.system(': 'os.system(',
            'subprocess.run(': 'subprocess.run(',
            'subprocess.Popen(': 'subprocess.Popen(',
            'eval(': 'eval(',
            'exec(': 'exec(',
            'compile(': 'compile(',
            'ctx.Process(': 'ctx.Process(',
        }
        allowlist = {
            'ThreadPoolExecutor': {'agents.py', 'ebp.py'},
            'ctx.Process(': {'upload_security.py'},
        }
        unexpected: list[tuple[str, str]] = []
        for path in root.rglob('*.py'):
            rel = path.relative_to(root).as_posix()
            if rel.startswith(('venv/', 'env/', 'tests/')) or '__pycache__' in rel:
                continue
            source = path.read_text(encoding='utf-8', errors='ignore')
            for name, pattern in patterns.items():
                if name == 'compile(':
                    matched = bool(__import__('re').search(r'(?<!\.)\bcompile\s*\(', source))
                else:
                    matched = pattern in source
                if matched and path.name not in allowlist.get(name, set()):
                    unexpected.append((name, rel))
        self.assertEqual(unexpected, [])


if __name__ == '__main__':
    unittest.main()
