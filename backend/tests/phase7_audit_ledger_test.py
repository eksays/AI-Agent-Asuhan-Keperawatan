from __future__ import annotations

import hashlib
import math
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import audit_ledger  # noqa: E402
import api  # noqa: E402
import config  # noqa: E402
import director  # noqa: E402
from audit_ledger import AuditEventInput, AuditLedgerError, AuditLedgerVerificationError, LocalAppendOnlyLedgerBackend, verify_ledger_file, verify_segment_chain  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

KEY = 'phase7-audit-ledger-hmac-key-for-tests-0001'
WRONG_KEY = 'phase7-audit-ledger-hmac-key-for-tests-9999'


def make_event(event_type: str = 'authentication_succeeded', **metadata):
    return AuditEventInput(
        event_type=event_type,
        actor_type='api_principal',
        actor_id='synthetic-actor-secret-value',
        route_class='AUTH',
        action='synthetic_action',
        outcome='ok',
        status_code=200,
        security_tags=('auth',),
        metadata=metadata,
    )


class Phase7AuditLedgerCoreTests(unittest.TestCase):
    def test_valid_append_verify_and_required_schema_fields(self):
        ledger = LocalAppendOnlyLedgerBackend(':memory:', KEY, key_id='test-key-v1', segment_id='seg-a')
        record = ledger.append_event(make_event(status='ok'))
        self.assertEqual(set(record.keys()), audit_ledger.REQUIRED_RECORD_FIELDS)
        self.assertEqual(record['schema_version'], audit_ledger.SCHEMA_VERSION)
        self.assertEqual(record['sequence'], 1)
        self.assertEqual(record['previous_record_mac'], audit_ledger.GENESIS_MARKER)
        self.assertTrue(ledger.verify().ok)

    def test_restart_append_continues_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.jsonl'
            LocalAppendOnlyLedgerBackend(path, KEY, key_id='test-key-v1', segment_id='seg-a').append_event(make_event())
            restarted = LocalAppendOnlyLedgerBackend(path, KEY, key_id='test-key-v1', segment_id='seg-a')
            second = restarted.append_event(make_event('session_created'))
            result = restarted.verify()
            self.assertTrue(result.ok)
            self.assertEqual(result.record_count, 2)
            self.assertEqual(second['sequence'], 2)

    def test_canonical_serialization_stability(self):
        left = {'b': True, 'a': None, 'c': {'z': 1, 'y': 'two'}}
        right = {'c': {'y': 'two', 'z': 1}, 'a': None, 'b': True}
        self.assertEqual(audit_ledger.canonical_json(left), audit_ledger.canonical_json(right))
        self.assertIn('sort_keys=True', Path(audit_ledger.__file__).read_text(encoding='utf-8'))
        self.assertIn("separators=(',', ':')", Path(audit_ledger.__file__).read_text(encoding='utf-8'))
        self.assertIn('allow_nan=False', Path(audit_ledger.__file__).read_text(encoding='utf-8'))

    def test_canonical_record_fields_are_mac_covered_and_jsonl_safe(self):
        ledger = LocalAppendOnlyLedgerBackend(':memory:', KEY, key_id='test-key-v1', segment_id='seg-a')
        record = ledger.append_event(make_event(status='aman', clinical_status='registry_unavailable'))
        without_mac = audit_ledger._record_without_mac(record)
        self.assertNotIn('record_mac', without_mac)
        self.assertEqual(record['record_mac'], audit_ledger.compute_record_mac(without_mac, KEY))
        for field, value in (
            ('schema_version', 'changed-schema'),
            ('sequence', record['sequence'] + 1),
            ('event_type', 'session_created'),
            ('previous_record_mac', 'changed-previous-mac'),
            ('key_id', 'changed-key-id'),
        ):
            changed = dict(without_mac)
            changed[field] = value
            self.assertNotEqual(record['record_mac'], audit_ledger.compute_record_mac(changed, KEY), field)
        changed = dict(without_mac)
        changed['metadata'] = {**changed['metadata'], 'status': 'changed'}
        self.assertNotEqual(record['record_mac'], audit_ledger.compute_record_mac(changed, KEY))
        line = ledger._memory_lines[0]
        self.assertTrue(line.endswith('\n'))
        self.assertEqual(line.count('\n'), 1)
        self.assertNotIn('\r', line)

    def test_non_finite_and_complex_metadata_are_rejected_or_sanitized(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                audit_ledger.canonical_json({'value': value})

        class SyntheticObject:
            def __str__(self):
                return 'raw prompt synthetic patient name Budi Santoso'

        oversized = 'x' * (audit_ledger.MAX_METADATA_STRING + 50)
        ledger = LocalAppendOnlyLedgerBackend(':memory:', KEY, key_id='test-key-v1', segment_id='seg-a')
        ledger.append_event(AuditEventInput(
            event_type='clinical_abstention',
            actor_type='api_principal\nraw API key',
            actor_id='session token abcdefghijklmnopqrstuvwxyz1234567890',
            route_class='clinical\rvalidation',
            action='raw model output\nBudi Santoso',
            outcome='stack trace\rtemporary file path C:\\tmp\\case.pdf',
            status_code=200,
            security_tags=('clinical', 'unknown'),
            metadata={
                'clinical_status': 'registry_unavailable\nextra',
                'reason_code': b'raw prompt bytes',
                'status': SyntheticObject(),
                'missing_registries': list(range(20)),
                'parser_status': oversized,
                'nested': {'deep': {'value': 'raw model output'}},
                'unknown_metadata_key': 'raw prompt should be omitted',
            },
        ))
        line = ledger._memory_lines[0]
        self.assertEqual(line.count('\n'), 1)
        record = json.loads(line)
        self.assertNotIn('unknown_metadata_key', record['metadata'])
        self.assertEqual(record['metadata']['status'], '[REDACTED]')
        self.assertNotIn('nested', record['metadata'])
        self.assertLessEqual(len(record['metadata']['missing_registries']), audit_ledger.MAX_METADATA_LIST)
        self.assertLessEqual(len(record['metadata']['parser_status']), audit_ledger.MAX_METADATA_STRING)
        lowered = line.lower()
        for canary in ('budi santoso', 'raw prompt', 'raw model output', 'session token', 'temporary file path', 'stack trace', 'c:\\tmp'):
            self.assertNotIn(canary, lowered)

    def _ledger_lines(self, count: int = 3) -> tuple[Path, list[str]]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'audit.jsonl'
        ledger = LocalAppendOnlyLedgerBackend(path, KEY, key_id='test-key-v1', segment_id='seg-a')
        for idx in range(count):
            ledger.append_event(make_event('authentication_succeeded', status='ok', status_code=idx))
        return path, path.read_text(encoding='utf-8').splitlines(keepends=True)

    def test_tamper_mutation_reorder_deletion_duplicate_wrong_key(self):
        path, lines = self._ledger_lines(3)
        mutated = json.loads(lines[0])
        mutated['outcome'] = 'changed'
        path.write_text(audit_ledger.canonical_json(mutated) + '\n' + ''.join(lines[1:]), encoding='utf-8')
        self.assertEqual(verify_ledger_file(path, KEY).failure_code, 'record_mac_mismatch')

        path, lines = self._ledger_lines(3)
        path.write_text(''.join([lines[1], lines[0], lines[2]]), encoding='utf-8')
        self.assertFalse(verify_ledger_file(path, KEY).ok)

        path, lines = self._ledger_lines(3)
        path.write_text(lines[0] + lines[2], encoding='utf-8')
        self.assertEqual(verify_ledger_file(path, KEY).failure_code, 'sequence_mismatch')

        path, lines = self._ledger_lines(3)
        path.write_text(''.join([lines[0], lines[1], lines[1], lines[2]]), encoding='utf-8')
        self.assertEqual(verify_ledger_file(path, KEY).failure_code, 'sequence_mismatch')

        path, _lines = self._ledger_lines(1)
        self.assertEqual(verify_ledger_file(path, WRONG_KEY).failure_code, 'record_mac_mismatch')

    def test_persistent_append_fails_closed_on_unverifiable_existing_ledger(self):
        tamper_cases = []
        path, lines = self._ledger_lines(3)
        mutated = json.loads(lines[0])
        mutated['outcome'] = 'changed'
        tamper_cases.append(('field_mutation', audit_ledger.canonical_json(mutated) + '\n' + ''.join(lines[1:])))
        tamper_cases.append(('reordered', ''.join([lines[1], lines[0], lines[2]])))
        tamper_cases.append(('middle_deleted', lines[0] + lines[2]))
        tamper_cases.append(('partial_trailing_line', ''.join(lines).rstrip('\n')))
        tamper_cases.append(('malformed_trailing_json', ''.join(lines) + '{bad json}\n'))

        for _name, body in tamper_cases:
            with self.subTest(_name):
                with tempfile.TemporaryDirectory() as tmp:
                    ledger_path = Path(tmp) / 'audit.jsonl'
                    ledger_path.write_text(body, encoding='utf-8')
                    before = ledger_path.read_bytes()
                    ledger = LocalAppendOnlyLedgerBackend(ledger_path, KEY, key_id='test-key-v1', segment_id='seg-a')
                    with self.assertRaises(AuditLedgerVerificationError):
                        ledger.append_event(make_event('session_reset'))
                    self.assertEqual(before, ledger_path.read_bytes())

        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / 'audit.jsonl'
            ledger_path.write_text(''.join(lines), encoding='utf-8')
            before = ledger_path.read_bytes()
            wrong_key_ledger = LocalAppendOnlyLedgerBackend(ledger_path, WRONG_KEY, key_id='test-key-v1', segment_id='seg-a')
            with self.assertRaises(AuditLedgerVerificationError):
                wrong_key_ledger.append_event(make_event('session_reset'))
            self.assertEqual(before, ledger_path.read_bytes())

    def test_valid_prefix_tail_truncation_limitation_is_explicit(self):
        path, lines = self._ledger_lines(3)
        path.write_text(''.join(lines[:-1]), encoding='utf-8')
        result = verify_ledger_file(path, KEY)
        self.assertTrue(result.ok)
        self.assertEqual(result.record_count, 2)

    def test_malformed_json_partial_sequence_and_previous_mac_fail(self):
        path, lines = self._ledger_lines(2)
        path.write_text('{bad json}\n', encoding='utf-8')
        self.assertEqual(verify_ledger_file(path, KEY).failure_code, 'malformed_json')

        path.write_text(lines[0].rstrip('\n'), encoding='utf-8')
        self.assertEqual(verify_ledger_file(path, KEY).failure_code, 'partial_trailing_line')

        record = json.loads(lines[1])
        record['sequence'] = 1
        record['record_mac'] = audit_ledger.compute_record_mac(audit_ledger._record_without_mac(record), KEY)
        path.write_text(lines[0] + audit_ledger.canonical_json(record) + '\n', encoding='utf-8')
        self.assertEqual(verify_ledger_file(path, KEY).failure_code, 'sequence_mismatch')

        record = json.loads(lines[1])
        record['previous_record_mac'] = 'wrong-prev'
        record['record_mac'] = audit_ledger.compute_record_mac(audit_ledger._record_without_mac(record), KEY)
        path.write_text(lines[0] + audit_ledger.canonical_json(record) + '\n', encoding='utf-8')
        self.assertEqual(verify_ledger_file(path, KEY).failure_code, 'previous_mac_mismatch')

    def test_concurrent_thread_append_is_monotonic(self):
        ledger = LocalAppendOnlyLedgerBackend(':memory:', KEY, key_id='test-key-v1', segment_id='seg-a')
        threads = [threading.Thread(target=ledger.append_event, args=(make_event('rate_limited'),)) for _ in range(25)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        result = ledger.verify()
        self.assertTrue(result.ok)
        self.assertEqual(result.record_count, 25)
        sequences = [json.loads(line)['sequence'] for line in ledger._memory_lines]
        self.assertEqual(sequences, list(range(1, 26)))

    def test_metadata_bounds_unknown_fields_and_secret_phi_canaries_are_sanitized(self):
        ledger = LocalAppendOnlyLedgerBackend(':memory:', KEY, key_id='test-key-v1', segment_id='seg-a')
        ledger.append_event(AuditEventInput(
            event_type='upload_rejected',
            actor_type='api_principal',
            actor_id='raw API key sk-secret-token-1234567890',
            route_class='UPLOAD',
            action='Budi Santoso synthetic NIK 3174090101010001',
            outcome='temporary file path C:\\tmp\\case.pdf',
            status_code=422,
            security_tags=('upload', 'unknown'),
            metadata={
                'parser_status': 'parser_crashed',
                'unknown_raw_prompt': 'uploaded-document body Budi Santoso',
                'status': 'synthetic email budi@example.test',
                'missing_registries': ['SDKI', 'SLKI'],
                'nested': {'raw': 'secret'},
            },
        ))
        text = ''.join(ledger._memory_lines).lower()
        for canary in ('budi santoso', '3174090101010001', 'budi@example.test', 'sk-secret-token', 'c:\\tmp', 'uploaded-document body'):
            self.assertNotIn(canary.lower(), text)
        record = json.loads(ledger._memory_lines[0])
        self.assertNotIn('unknown_raw_prompt', record['metadata'])
        self.assertEqual(record['metadata']['parser_status'], 'parser_crashed')

    def test_cli_valid_tampered_and_missing_key_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.jsonl'
            LocalAppendOnlyLedgerBackend(path, KEY, key_id='test-key-v1', segment_id='seg-a').append_event(make_event())
            script = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_audit_ledger.py'
            valid = subprocess.run([sys.executable, str(script), '--path', str(path), '--key', KEY], text=True, capture_output=True, check=False)
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertNotIn(KEY, valid.stdout)
            path.write_text(path.read_text(encoding='utf-8').replace('ok', 'changed', 1), encoding='utf-8')
            tampered = subprocess.run([sys.executable, str(script), '--path', str(path), '--key', KEY], text=True, capture_output=True, check=False)
            self.assertNotEqual(tampered.returncode, 0)
            wrong_key = subprocess.run([sys.executable, str(script), '--path', str(path), '--key', WRONG_KEY], text=True, capture_output=True, check=False)
            self.assertNotEqual(wrong_key.returncode, 0)
            self.assertNotIn(WRONG_KEY, wrong_key.stdout + wrong_key.stderr)
            path.write_text('{bad json}\n', encoding='utf-8')
            malformed = subprocess.run([sys.executable, str(script), '--path', str(path), '--key', KEY], text=True, capture_output=True, check=False)
            self.assertNotEqual(malformed.returncode, 0)
            path.write_text('{"partial": true}', encoding='utf-8')
            partial = subprocess.run([sys.executable, str(script), '--path', str(path), '--key', KEY], text=True, capture_output=True, check=False)
            self.assertNotEqual(partial.returncode, 0)
            missing_key = subprocess.run([sys.executable, str(script), '--path', str(path)], text=True, capture_output=True, check=False)
            self.assertNotEqual(missing_key.returncode, 0)
            self.assertNotIn(KEY, missing_key.stdout + missing_key.stderr)

    def test_rotation_preserves_old_segment_and_links_new_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / 'audit-1.jsonl'
            second = Path(tmp) / 'audit-2.jsonl'
            ledger = LocalAppendOnlyLedgerBackend(first, KEY, key_id='test-key-v1', segment_id='seg-a')
            ledger.append_event(make_event('session_created'))
            old_bytes = first.read_bytes()
            rotated = ledger.rotate_to(second, segment_id='seg-b')
            rotated.append_event(make_event('session_reset'))
            self.assertEqual(first.read_bytes(), old_bytes)
            self.assertTrue(verify_segment_chain([ledger, rotated]).ok)
            self.assertEqual(rotated.previous_segment_terminal_mac, ledger.verify().last_record_mac)
            self.assertEqual(verify_segment_chain([rotated]).failure_code, 'segment_link_mismatch')
            rotated.previous_segment_terminal_mac = 'tampered-terminal-mac'
            self.assertEqual(verify_segment_chain([ledger, rotated]).failure_code, 'segment_link_mismatch')

    def test_plain_sha_recomputed_chain_cannot_bypass_hmac(self):
        path, lines = self._ledger_lines(1)
        record = json.loads(lines[0])
        record['action'] = 'attacker_changed_history'
        record['record_mac'] = hashlib.sha256(audit_ledger.canonical_bytes(audit_ledger._record_without_mac(record))).hexdigest()
        path.write_text(audit_ledger.canonical_json(record) + '\n', encoding='utf-8')
        self.assertEqual(verify_ledger_file(path, KEY).failure_code, 'record_mac_mismatch')

    def test_path_safety_rejects_unexpected_file_types_and_normalizes_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            traversal = root / 'nested' / '..' / 'audit.jsonl'
            ledger = LocalAppendOnlyLedgerBackend(traversal, KEY, key_id='test-key-v1')
            self.assertEqual(ledger.path, (root / 'audit.jsonl').resolve())
            directory_path = root / 'directory-ledger'
            directory_path.mkdir()
            with self.assertRaises(AuditLedgerError):
                LocalAppendOnlyLedgerBackend(directory_path, KEY, key_id='test-key-v1')
            target = root / 'target.jsonl'
            target.write_text('', encoding='utf-8')
            symlink = root / 'linked.jsonl'
            try:
                symlink.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest('symlink creation unavailable on this platform')
            with self.assertRaises(AuditLedgerError):
                LocalAppendOnlyLedgerBackend(symlink, KEY, key_id='test-key-v1')

    def test_actor_fingerprint_key_id_and_capabilities_do_not_expose_key_material(self):
        left = audit_ledger.actor_fingerprint('same-raw-actor', KEY, 'api_principal')
        right = audit_ledger.actor_fingerprint('same-raw-actor', KEY, 'api_principal')
        other_domain = audit_ledger.actor_fingerprint('same-raw-actor', KEY, 'director')
        self.assertEqual(left, right)
        self.assertNotEqual(left, other_domain)
        self.assertNotIn('same-raw-actor', left)
        ledger = LocalAppendOnlyLedgerBackend(':memory:', KEY, key_id='safe-key-id-v1')
        record = ledger.append_event(make_event())
        serialized = json.dumps(record)
        self.assertEqual(record['key_id'], 'safe-key-id-v1')
        self.assertNotIn(KEY, serialized)
        cfg = config.load_config({'AUDIT_LEDGER_HMAC_KEY': KEY, 'AUDIT_LEDGER_KEY_ID': 'safe-key-id-v1'})
        capabilities = json.dumps(config.build_capabilities(cfg))
        self.assertNotIn(KEY, capabilities)
        self.assertNotIn('safe-key-id-v1', capabilities)

    def test_verification_failure_event_does_not_recurse_forever(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.jsonl'
            path.write_text('{bad json}\n', encoding='utf-8')
            ledger = LocalAppendOnlyLedgerBackend(path, KEY, key_id='test-key-v1')
            stderr = StringIO()
            with mock.patch.object(api, 'AUDIT_LEDGER', ledger), redirect_stderr(stderr):
                ok, count = api.verify_audit_chain()
            self.assertFalse(ok)
            self.assertEqual(count, 0)
            text = stderr.getvalue().lower()
            self.assertIn('audit ledger verification failed', text)
            self.assertNotIn(KEY.lower(), text)


class Phase7ApiAuditFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)

    def setUp(self):
        api.RATE_LIMITER.clear()
        director.reset_mfa_state_for_tests()

    def _session(self):
        headers = {'Authorization': 'Bearer test-key'}
        response = self.client.post('/session', headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        headers['X-Session-Token'] = body['session_token']
        return body['session_id'], headers

    def _fail_audit(self):
        return mock.patch.object(api.AUDIT_LEDGER, 'append_event', side_effect=AuditLedgerError('synthetic raw API key 3273010101990001'))

    def test_session_reset_and_delete_fail_closed_when_required_audit_append_fails(self):
        sid, headers = self._session()
        with self._fail_audit():
            reset = self.client.post('/reset', data={'session_id': sid}, headers=headers)
        self.assertEqual(reset.status_code, 503)
        self.assertEqual(reset.json()['security_status'], 'audit_required_failed')
        self.assertNotIn('3273010101990001', reset.text)
        self.assertEqual(api.SESI.validate(sid, api.AuthPrincipal('api:' + api.SECURITY_PEPPER[:0], 'unused'), 'bad-token'), 'session_owner_mismatch')
        self.assertEqual(self.client.post('/feedback', data={'framework': '3S', 'session_id': sid}, headers=headers).status_code, 200)

        with self._fail_audit():
            deleted = self.client.post('/delete_my_data', data={'session_id': sid}, headers=headers)
        self.assertEqual(deleted.status_code, 503)
        self.assertEqual(deleted.json()['security_status'], 'audit_required_failed')
        self.assertEqual(self.client.post('/feedback', data={'framework': '3S', 'session_id': sid}, headers=headers).status_code, 200)

    def test_mfa_privileged_results_fail_closed_when_required_audit_append_fails(self):
        with self._fail_audit(), mock.patch.object(director, 'verify_totp_attempt', return_value=director.MFAAttemptResult(True, 'authenticated', token='synthetic-director-token')):
            success = self.client.post('/director/login', data={'code': '123456'})
        self.assertEqual(success.status_code, 503)
        self.assertNotIn('synthetic-director-token', success.text)
        self.assertNotIn('3273010101990001', success.text)

        for status in ('mfa_replay_rejected', 'mfa_locked'):
            with self.subTest(status=status):
                with self._fail_audit(), mock.patch.object(director, 'verify_totp_attempt', return_value=director.MFAAttemptResult(False, status, retry_after=1)):
                    response = self.client.post('/director/login', data={'code': '123456'})
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()['security_status'], 'audit_required_failed')

    def test_director_enrollment_attempt_and_success_fail_closed_before_provisioning(self):
        cfg = config.load_config({
            'DIRECTOR_ENROLLMENT_ENABLED': 'true',
            'DIRECTOR_BOOTSTRAP': 'strong-bootstrap-secret-for-phase7',
        })
        with mock.patch.object(api, 'CONFIG', cfg), self._fail_audit(), mock.patch.object(director, 'provision_otpauth_uri') as provision:
            response = self.client.get('/director/enroll', headers={'X-Director-Bootstrap': cfg.director_bootstrap})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(provision.called)

        calls = {'count': 0}
        original = api.AUDIT_LEDGER.append_event

        def fail_second(event):
            calls['count'] += 1
            if calls['count'] == 2:
                raise AuditLedgerError('synthetic director bootstrap secret')
            return original(event)

        with mock.patch.object(api, 'CONFIG', cfg), mock.patch.object(api.AUDIT_LEDGER, 'append_event', side_effect=fail_second), mock.patch.object(director, 'provision_otpauth_uri') as provision:
            response = self.client.get('/director/enroll', headers={'X-Director-Bootstrap': cfg.director_bootstrap})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(provision.called)


class Phase7ConfigAndScannerTests(unittest.TestCase):
    def test_non_sandbox_modes_require_strong_audit_key(self):
        base = {
            'APP_MODE': 'controlled_pilot',
            'CDSS_API_KEYS': 'strong-api-key-value-12345',
            'CDSS_SECRET_KEY': 'strong-secret-key-value-123456789012345',
            'DIRECTOR_BOOTSTRAP': 'strong-bootstrap-value-12345',
        }
        with self.assertRaises(RuntimeError):
            config.load_config(base)
        cfg = config.load_config({**base, 'AUDIT_LEDGER_HMAC_KEY': KEY})
        self.assertEqual(cfg.audit_ledger_hmac_key, KEY)
        with self.assertRaises(RuntimeError):
            config.load_config({'AUDIT_LEDGER_PATH': 'backend/audit_ledger.jsonl', 'AUDIT_LEDGER_HMAC_KEY': 'short'})

    def test_owned_source_audit_bypass_scanner(self):
        root = Path(__file__).resolve().parents[2]
        audit_source = (root / 'backend' / 'audit_ledger.py').read_text(encoding='utf-8')
        self.assertIn('hmac.new', audit_source)
        self.assertNotIn('truncate(', audit_source)
        self.assertNotIn("open('w'", audit_source)
        self.assertIn('sort_keys=True', audit_source)
        self.assertIn("separators=(',', ':')", audit_source)
        self.assertIn('raw prompt', audit_source.lower())

        risky_prints = []
        for path in (root / 'backend').rglob('*.py'):
            rel = path.relative_to(root).as_posix()
            if rel.startswith(('backend/venv/', 'backend/env/', 'backend/tests/')):
                continue
            text = path.read_text(encoding='utf-8', errors='ignore').lower()
            for match in re.finditer(r'(?<![a-z0-9_])print\s*\(\s*(secret|api|token)', text):
                risky_prints.append((rel, match.group(0)))
        self.assertEqual([], risky_prints)

        worm_lines = []
        for rel in ('README.md', 'JALANKAN.md', '.gitignore'):
            path = root / rel
            if not path.exists():
                continue
            for line_no, line in enumerate(path.read_text(encoding='utf-8', errors='ignore').splitlines(), start=1):
                lower = line.lower()
                if 'worm' in lower and not any(allowed in lower for allowed in ('not worm', 'bukan worm', 'overstated', 'required before', 'named/described as worm')):
                    worm_lines.append((rel, line_no, line))
        self.assertEqual([], worm_lines)


if __name__ == '__main__':
    unittest.main()
