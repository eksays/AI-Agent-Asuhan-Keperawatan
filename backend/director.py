"""
Otentikasi DIREKTUR — MFA berbasis TOTP (RFC 6238, implementasi stdlib, tanpa dependency).
Role "DIRECTOR" = pemilik TOTP secret. Login dengan kode 6-digit dari aplikasi authenticator
-> token sesi direktur berumur pendek (30 menit). Secret disimpan TERENKRIPSI (master key).
Enrollment: local sandbox provisioning is explicit through /director/enroll only when enabled and guarded by X-Director-Bootstrap.
(WebAuthn/passkey phishing-resistant dapat dilapiskan kemudian; butuh HTTPS + ceremony perangkat.)
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import os, time, hmac, hashlib, struct, base64, secrets, threading
import crypto_store

_SECRET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".director_totp")
_lock = threading.Lock()
_tokens: dict[str, float] = {}   # director_token -> expiry ts
_TOKEN_TTL = 30 * 60
_failures: dict[str, deque[float]] = {}
_lockouts: dict[str, float] = {}
_accepted_steps: dict[str, float] = {}
_MFA_STATE_MAX = 512


@dataclass(frozen=True)
class MFAAttemptResult:
    ok: bool
    status: str
    retry_after: int = 0
    token: str = ''

@dataclass(frozen=True)
class EnrollmentResult:
    ok: bool
    status: str
    otpauth_uri: str = ''


def _load_secret() -> str:
    return (crypto_store.decrypt_load(_SECRET_FILE, {}) or {}).get("secret", "")


def ensure_secret() -> tuple[str, bool]:
    """(secret, baru_dibuat). Buat & simpan terenkripsi bila belum ada."""
    with _lock:
        sec = _load_secret()
        if sec:
            return sec, False
        sec = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
        crypto_store.encrypt_save(_SECRET_FILE, {"secret": sec})
        return sec, True


def _build_otpauth_uri(secret: str, issuer: str = "CDSS Keperawatan", account: str = "Direktur") -> str:
    return f"otpauth://totp/{issuer}:{account}?secret={secret}&issuer={issuer}&digits=6&period=30"

def otpauth_uri(issuer: str = "CDSS Keperawatan", account: str = "Direktur") -> str:
    sec = _load_secret()
    return _build_otpauth_uri(sec, issuer, account) if sec else ""

def provision_otpauth_uri(issuer: str = "CDSS Keperawatan", account: str = "Direktur") -> EnrollmentResult:
    with _lock:
        if _load_secret():
            return EnrollmentResult(False, 'director_enrollment_already_provisioned')
        sec = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
        crypto_store.encrypt_save(_SECRET_FILE, {"secret": sec})
        return EnrollmentResult(True, 'director_enrollment_provisioned', _build_otpauth_uri(sec, issuer, account))

def _totp(secret_b32: str, t: float, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8), casefold=True)
    h = hmac.new(key, struct.pack(">Q", int(t // step)), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def _matching_step(secret_b32: str, code: str, now: float, window: int = 1, step: int = 30) -> int | None:
    base = int(now // step)
    for offset in range(-window, window + 1):
        candidate_step = base + offset
        if hmac.compare_digest(_totp(secret_b32, candidate_step * step), code):
            return candidate_step
    return None


def _cleanup_mfa_state(now: float) -> None:
    for key in list(_failures):
        events = _failures[key]
        while events and events[0] < now - 3600:
            events.popleft()
        if not events:
            _failures.pop(key, None)
    for key, expires in list(_lockouts.items()):
        if expires <= now:
            _lockouts.pop(key, None)
    for key, expires in list(_accepted_steps.items()):
        if expires <= now:
            _accepted_steps.pop(key, None)


def _trim_mfa_capacity() -> None:
    while len(_failures) > _MFA_STATE_MAX:
        _failures.pop(next(iter(_failures)), None)
    while len(_accepted_steps) > _MFA_STATE_MAX:
        _accepted_steps.pop(next(iter(_accepted_steps)), None)


def _lockout_retry(keys: list[str], now: float) -> int:
    active = [int(exp - now) for key, exp in _lockouts.items() if key in keys and exp > now]
    return max(active) if active else 0


def _record_failure(keys: list[str], now: float, limit: int, window: int, lockout: int) -> int:
    cutoff = now - window
    locked_for = 0
    for key in keys:
        events = _failures.setdefault(key, deque())
        while events and events[0] <= cutoff:
            events.popleft()
        events.append(now)
        if len(events) >= limit:
            _lockouts[key] = now + lockout
            locked_for = max(locked_for, lockout)
    _trim_mfa_capacity()
    return locked_for


def verify_totp(code: str, window: int = 1) -> bool:
    sec = _load_secret()
    code = (code or "").strip()
    if not sec or not code.isdigit():
        return False
    now = time.time()
    return any(_totp(sec, now + w * 30) == code for w in range(-window, window + 1))


def verify_totp_attempt(
    code: str,
    principal: str = 'director',
    ip: str = 'unknown',
    now: float | None = None,
    failure_limit: int = 5,
    failure_window: int = 300,
    lockout: int = 300,
) -> MFAAttemptResult:
    sec = _load_secret()
    now = time.time() if now is None else now
    code = (code or '').strip()
    keys = ['p:' + (principal or 'director'), 'ip:' + (ip or 'unknown')]
    with _lock:
        _cleanup_mfa_state(now)
        retry = _lockout_retry(keys, now)
        if retry:
            return MFAAttemptResult(False, 'mfa_locked', retry)
        if not sec or not code.isdigit():
            locked = _record_failure(keys, now, failure_limit, failure_window, lockout)
            return MFAAttemptResult(False, 'mfa_locked' if locked else 'mfa_invalid', locked)
        step = _matching_step(sec, code, now)
        if step is None:
            locked = _record_failure(keys, now, failure_limit, failure_window, lockout)
            return MFAAttemptResult(False, 'mfa_locked' if locked else 'mfa_invalid', locked)
        replay_key = (principal or 'director') + ':' + str(step)
        if replay_key in _accepted_steps:
            return MFAAttemptResult(False, 'mfa_replay_rejected')
        _accepted_steps[replay_key] = now + 3600
        for key in keys:
            _failures.pop(key, None)
        _trim_mfa_capacity()
    return MFAAttemptResult(True, 'authenticated', token=issue_token())


def reset_mfa_state_for_tests() -> None:
    with _lock:
        _failures.clear()
        _lockouts.clear()
        _accepted_steps.clear()


def issue_token() -> str:
    tok = secrets.token_urlsafe(32)
    with _lock:
        now = time.time()
        _tokens[tok] = now + _TOKEN_TTL
        for k in [k for k, exp in _tokens.items() if exp < now]:
            _tokens.pop(k, None)
    return tok


def valid_token(tok: str) -> bool:
    with _lock:
        exp = _tokens.get(tok or "")
        return bool(exp and exp > time.time())
