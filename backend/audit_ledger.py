from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
from typing import Any, Iterable

SCHEMA_VERSION = 'audit-ledger.v1'
GENESIS_MARKER = 'GENESIS:phase7-audit-ledger-v1'
MAC_ALGORITHM = 'HMAC-SHA256'
MIN_AUDIT_KEY_BYTES = 32
MAX_METADATA_ITEMS = 16
MAX_METADATA_STRING = 160
MAX_METADATA_LIST = 10

REQUIRED_RECORD_FIELDS = frozenset({
    'schema_version', 'event_id', 'timestamp_utc', 'sequence', 'event_type',
    'actor_type', 'actor_fingerprint', 'route_class', 'action', 'outcome',
    'status_code', 'security_tags', 'metadata', 'previous_record_mac',
    'record_mac', 'key_id',
})

ALLOWED_EVENT_TYPES = frozenset({
    'authentication_succeeded', 'authentication_failed', 'authorization_failed',
    'session_created', 'session_reset', 'session_deleted', 'session_expired',
    'session_token_invalid', 'rate_limited', 'mfa_succeeded', 'mfa_failed',
    'mfa_replay_rejected', 'mfa_locked', 'director_enrollment_attempt',
    'director_enrollment_succeeded', 'upload_rejected', 'upload_accepted',
    'upload_parser_timeout', 'upload_parser_crashed', 'outbound_policy_blocked',
    'clinical_abstention', 'registry_unavailable', 'registry_incomplete',
    'capability_denied', 'ledger_verification_failed', 'consent_recorded',
    'analysis_succeeded', 'analysis_failed', 'feedback_recorded', 'legacy_event',
})

ALLOWED_METADATA_KEYS = frozenset({
    'status', 'reason_code', 'clinical_status', 'capability', 'parser_status',
    'route_class', 'retry_after_bucket', 'missing_registries', 'framework',
    'legacy_action', 'legacy_status', 'upload_status', 'status_code', 'segment_id',
    'verified_count', 'error_code', 'agent', 'accepted_recommendations',
    'nurse_review_required',
})

SAFE_SECURITY_TAGS = frozenset({
    'auth', 'session', 'rate_limit', 'mfa', 'director', 'upload', 'clinical',
    'registry', 'capability', 'ledger', 'privacy',
})

SENSITIVE_WORDS = (
    'budi santoso', 'bpjs', 'nik', 'mrn', 'rekam medis', 'no. rm',
    'totp seed', 'director bootstrap', 'provider key', 'raw api key',
    'uploaded-document body', 'synthetic nik', 'synthetic bpjs',
    'synthetic mrn', 'synthetic phone', 'synthetic email', 'synthetic address',
    'synthetic dob', 'session token', 'otp code', 'temporary file path',
    'raw prompt', 'raw model output', 'model output', 'provider api key',
    'stack trace', 'traceback',
)


class AuditLedgerError(RuntimeError):
    pass


class AuditLedgerVerificationError(AuditLedgerError):
    pass


@dataclass(frozen=True)
class LedgerVerificationResult:
    ok: bool
    record_count: int = 0
    first_failure_index: int | None = None
    failure_code: str = ''
    last_sequence: int = 0
    last_record_mac: str = GENESIS_MARKER
    key_id: str = ''
    segment_id: str = ''

    def safe_summary(self) -> dict[str, Any]:
        return {
            'ok': self.ok,
            'record_count': self.record_count,
            'first_failure_index': self.first_failure_index,
            'failure_code': self.failure_code,
            'last_sequence': self.last_sequence,
            'last_record_mac': self.last_record_mac,
            'key_id': self.key_id,
            'segment_id': self.segment_id,
            'integrity': MAC_ALGORITHM,
        }


@dataclass(frozen=True)
class AuditEventInput:
    event_type: str
    actor_type: str = 'system'
    actor_id: str = ''
    route_class: str = 'system'
    action: str = ''
    outcome: str = ''
    status_code: int | None = None
    security_tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return canonical_json(payload).encode('utf-8')


def _key_bytes(key: str | bytes) -> bytes:
    if isinstance(key, bytes):
        return key
    return (key or '').encode('utf-8')


def audit_key_is_weak(key: str | bytes) -> bool:
    raw = _key_bytes(key)
    if len(raw) < MIN_AUDIT_KEY_BYTES:
        return True
    lowered = raw.decode('utf-8', errors='ignore').strip().lower()
    return lowered in {'', 'change-me', 'changeme', 'default', 'password', 'secret', 'test', 'placeholder'} or 'placeholder' in lowered


def compute_record_mac(record_without_record_mac: dict[str, Any], key: str | bytes) -> str:
    return hmac.new(_key_bytes(key), canonical_bytes(record_without_record_mac), hashlib.sha256).hexdigest()


def actor_fingerprint(actor_id: str, key: str | bytes, actor_type: str = 'actor') -> str:
    if not actor_id:
        return 'anonymous'
    msg = (actor_type + ':' + actor_id).encode('utf-8', errors='ignore')
    return 'act:' + hmac.new(_key_bytes(key), msg, hashlib.sha256).hexdigest()[:32]


def _looks_sensitive(text: str) -> bool:
    lowered = text.lower()
    if any(word in lowered for word in SENSITIVE_WORDS):
        return True
    if '@' in text or '://' in text or ':\\' in text:
        return True
    digits = [char for char in text if char.isdigit()]
    return len(digits) >= 10


def _clean_token(value: str, limit: int = MAX_METADATA_STRING) -> str:
    text = ' '.join(str(value or '').replace('\r', ' ').replace('\n', ' ').split())
    text = ''.join(char if (char.isalnum() or char in '_.:/ -') else '_' for char in text)
    if _looks_sensitive(text):
        return '[REDACTED]'
    return text[:limit]


def _sanitize_scalar(value: Any) -> str | int | bool | None:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return '[FILTERED]'
    return _clean_token(str(value))


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in list((metadata or {}).items())[:MAX_METADATA_ITEMS]:
        clean_key = _clean_token(str(key), 64)
        if clean_key not in ALLOWED_METADATA_KEYS:
            continue
        if isinstance(value, (list, tuple)):
            safe[clean_key] = [_sanitize_scalar(item) for item in value[:MAX_METADATA_LIST]]
        elif isinstance(value, dict):
            safe[clean_key] = '[FILTERED]'
        else:
            safe[clean_key] = _sanitize_scalar(value)
    return safe


def sanitize_security_tags(tags: Iterable[str] | None) -> list[str]:
    result: list[str] = []
    for tag in tags or ():
        clean = _clean_token(str(tag), 48).lower()
        if clean in SAFE_SECURITY_TAGS and clean not in result:
            result.append(clean)
    return result[:8]


def _validate_record_shape(record: Any) -> tuple[bool, str]:
    if not isinstance(record, dict):
        return False, 'record_not_object'
    if set(record.keys()) != REQUIRED_RECORD_FIELDS:
        return False, 'record_fields_invalid'
    if record.get('schema_version') != SCHEMA_VERSION:
        return False, 'schema_version_invalid'
    if record.get('event_type') not in ALLOWED_EVENT_TYPES:
        return False, 'event_type_invalid'
    if not isinstance(record.get('sequence'), int) or record.get('sequence') < 1:
        return False, 'sequence_invalid'
    if not isinstance(record.get('metadata'), dict):
        return False, 'metadata_invalid'
    if not isinstance(record.get('security_tags'), list):
        return False, 'security_tags_invalid'
    for name in ('event_id', 'timestamp_utc', 'actor_type', 'actor_fingerprint', 'route_class', 'action', 'outcome', 'previous_record_mac', 'record_mac', 'key_id'):
        if not isinstance(record.get(name), str):
            return False, name + '_invalid'
    return True, ''


def _record_without_mac(record: dict[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    payload.pop('record_mac', None)
    return payload


def verify_ledger_lines(lines: Iterable[str], key: str | bytes, *, previous_record_mac: str = GENESIS_MARKER, key_id: str = '', segment_id: str = '') -> LedgerVerificationResult:
    prev = previous_record_mac
    expected_sequence = 1
    count = 0
    for index, raw in enumerate(lines, start=1):
        if not raw.endswith('\n'):
            return LedgerVerificationResult(False, count, index, 'partial_trailing_line', expected_sequence - 1, prev, key_id, segment_id)
        line = raw[:-1]
        if not line:
            return LedgerVerificationResult(False, count, index, 'empty_line', expected_sequence - 1, prev, key_id, segment_id)
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return LedgerVerificationResult(False, count, index, 'malformed_json', expected_sequence - 1, prev, key_id, segment_id)
        valid, code = _validate_record_shape(record)
        if not valid:
            return LedgerVerificationResult(False, count, index, code, expected_sequence - 1, prev, key_id, segment_id)
        if record['sequence'] != expected_sequence:
            return LedgerVerificationResult(False, count, index, 'sequence_mismatch', expected_sequence - 1, prev, key_id, segment_id)
        if record['previous_record_mac'] != prev:
            return LedgerVerificationResult(False, count, index, 'previous_mac_mismatch', expected_sequence - 1, prev, key_id, segment_id)
        expected_mac = compute_record_mac(_record_without_mac(record), key)
        if not hmac.compare_digest(str(record['record_mac']), expected_mac):
            return LedgerVerificationResult(False, count, index, 'record_mac_mismatch', expected_sequence - 1, prev, key_id, segment_id)
        prev = record['record_mac']
        key_id = record['key_id']
        count += 1
        expected_sequence += 1
    return LedgerVerificationResult(True, count, None, '', expected_sequence - 1, prev, key_id, segment_id)


class LocalAppendOnlyLedgerBackend:
    '''Local sandbox append-only API with HMAC tamper evidence.

    This is not immutable filesystem storage and not WORM storage.
    '''

    @staticmethod
    def _normalize_path(path: str | os.PathLike[str]) -> Path:
        raw = Path(path)
        if raw.is_symlink():
            raise AuditLedgerError('Refusing symlink audit ledger path.')
        resolved = raw.resolve()
        parent = resolved.parent
        if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
            raise AuditLedgerError('Audit ledger parent path is not a safe directory.')
        if resolved.exists() and (resolved.is_symlink() or not resolved.is_file()):
            raise AuditLedgerError('Audit ledger path must be a regular file.')
        return resolved

    def __init__(self, path: str | os.PathLike[str] | None, key: str | bytes, *, key_id: str = 'audit-ledger-local-v1', segment_id: str | None = None, previous_segment_terminal_mac: str = GENESIS_MARKER, verify_before_append: bool = True) -> None:
        if audit_key_is_weak(key):
            raise AuditLedgerError('Audit ledger key is missing or weak.')
        self.path = None if path in (None, '', ':memory:') else self._normalize_path(path)
        self.key = _key_bytes(key)
        self.key_id = _clean_token(key_id or 'audit-ledger-local-v1', 80)
        self.segment_id = _clean_token(segment_id or secrets.token_hex(12), 80)
        self.previous_segment_terminal_mac = previous_segment_terminal_mac or GENESIS_MARKER
        self.verify_before_append = bool(verify_before_append)
        self._lock = threading.Lock()
        self._memory_lines: list[str] = []
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def persistent(self) -> bool:
        return self.path is not None

    def _read_lines(self) -> list[str]:
        if self.path is None:
            return list(self._memory_lines)
        if not self.path.exists():
            return []
        return self.path.read_text(encoding='utf-8').splitlines(keepends=True)

    def verify(self) -> LedgerVerificationResult:
        return verify_ledger_lines(
            self._read_lines(),
            self.key,
            previous_record_mac=self.previous_segment_terminal_mac,
            key_id=self.key_id,
            segment_id=self.segment_id,
        )

    def append_event(self, event: AuditEventInput | None = None, **kwargs: Any) -> dict[str, Any]:
        event = event or AuditEventInput(**kwargs)
        if event.event_type not in ALLOWED_EVENT_TYPES:
            raise AuditLedgerError('Unsupported audit event type.')
        with self._lock:
            state = self.verify()
            if self.verify_before_append and not state.ok:
                raise AuditLedgerVerificationError('Audit ledger verification failed before append.')
            previous_mac = state.last_record_mac if state.ok else self.previous_segment_terminal_mac
            sequence = state.last_sequence + 1 if state.ok else 1
            metadata = sanitize_metadata({**(event.metadata or {}), 'segment_id': self.segment_id})
            payload = {
                'schema_version': SCHEMA_VERSION,
                'event_id': secrets.token_hex(16),
                'timestamp_utc': utc_now_iso(),
                'sequence': sequence,
                'event_type': event.event_type,
                'actor_type': _clean_token(event.actor_type or 'system', 64),
                'actor_fingerprint': actor_fingerprint(event.actor_id or '', self.key, event.actor_type or 'system'),
                'route_class': _clean_token(event.route_class or 'system', 64),
                'action': _clean_token(event.action or event.event_type, 96),
                'outcome': _clean_token(event.outcome or 'recorded', 96),
                'status_code': int(event.status_code or 0),
                'security_tags': sanitize_security_tags(event.security_tags),
                'metadata': metadata,
                'previous_record_mac': previous_mac,
                'key_id': self.key_id,
            }
            record = {**payload, 'record_mac': compute_record_mac(payload, self.key)}
            line = canonical_json(record) + '\n'
            if self.path is None:
                self._memory_lines.append(line)
            else:
                with self.path.open('a', encoding='utf-8', newline='\n') as handle:
                    handle.write(line)
                    handle.flush()
                    os.fsync(handle.fileno())
            return record

    def export_summary(self) -> dict[str, Any]:
        return self.verify().safe_summary()

    def rotate_to(self, new_path: str | os.PathLike[str] | None, *, segment_id: str | None = None) -> 'LocalAppendOnlyLedgerBackend':
        state = self.verify()
        if not state.ok:
            raise AuditLedgerVerificationError('Cannot rotate an unverifiable ledger segment.')
        if new_path not in (None, '', ':memory:'):
            path = Path(new_path).resolve()
            if path.exists() and path.stat().st_size > 0:
                raise AuditLedgerError('Refusing to overwrite an existing ledger segment.')
        return LocalAppendOnlyLedgerBackend(
            new_path,
            self.key,
            key_id=self.key_id,
            segment_id=segment_id,
            previous_segment_terminal_mac=state.last_record_mac,
            verify_before_append=self.verify_before_append,
        )


def verify_ledger_file(path: str | os.PathLike[str], key: str | bytes, *, previous_record_mac: str = GENESIS_MARKER, key_id: str = '', segment_id: str = '') -> LedgerVerificationResult:
    p = Path(path)
    if not p.exists():
        return LedgerVerificationResult(True, 0, None, '', 0, previous_record_mac, key_id, segment_id)
    return verify_ledger_lines(
        p.read_text(encoding='utf-8').splitlines(keepends=True),
        key,
        previous_record_mac=previous_record_mac,
        key_id=key_id,
        segment_id=segment_id,
    )


def verify_segment_chain(segments: Iterable[LocalAppendOnlyLedgerBackend]) -> LedgerVerificationResult:
    previous = GENESIS_MARKER
    count = 0
    last: LedgerVerificationResult | None = None
    for idx, segment in enumerate(segments, start=1):
        if segment.previous_segment_terminal_mac != previous:
            return LedgerVerificationResult(False, count, idx, 'segment_link_mismatch', 0, previous, segment.key_id, segment.segment_id)
        result = segment.verify()
        if not result.ok:
            return result
        previous = result.last_record_mac
        count += result.record_count
        last = result
    return LedgerVerificationResult(True, count, None, '', (last.last_sequence if last else 0), previous, (last.key_id if last else ''), (last.segment_id if last else ''))
