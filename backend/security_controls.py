from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import hmac
import ipaddress
import secrets
import time
from typing import Iterable, Sequence

SANDBOX_DEFAULT_API_KEYS = ('test-key',)
PLACEHOLDER_SECRETS = {'', 'change-me', 'changeme', 'default', 'password', 'secret', 'test', 'test-key', 'dev-key', 'development'}


@dataclass(frozen=True)
class AuthPrincipal:
    principal_id: str
    credential_fingerprint: str
    roles: tuple[str, ...] = ('clinical_app',)
    auth_method: str = 'api_key_bearer'


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    status: str
    principal: AuthPrincipal | None = None
    raw_credential: str = ''


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    status: str = 'ok'
    retry_after: int = 0


def is_placeholder_secret(value: str) -> bool:
    cleaned = (value or '').strip().lower()
    return cleaned in PLACEHOLDER_SECRETS or cleaned.startswith('replace-') or 'placeholder' in cleaned


def is_weak_secret(value: str, min_length: int = 16) -> bool:
    cleaned = (value or '').strip()
    return len(cleaned) < min_length or is_placeholder_secret(cleaned)


def secret_fingerprint(value: str, pepper: str, purpose: str) -> str:
    key = (pepper or 'clinical-sandbox-only-pepper').encode('utf-8')
    msg = (purpose + ':' + (value or '')).encode('utf-8')
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def issue_secret_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str, pepper: str) -> str:
    return secret_fingerprint(token, pepper, 'session-token')


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left or '', right or '')


def parse_bearer_authorization(authorization):
    header = (authorization or '').strip()
    if not header:
        return '', 'authentication_required'
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return '', 'authentication_failed'
    token = parts[1].strip()
    return (token, 'ok') if token else ('', 'authentication_required')


def authenticate_api_key(authorization, allowed_keys: Sequence[str], pepper: str) -> AuthResult:
    token, parse_status = parse_bearer_authorization(authorization)
    if parse_status != 'ok':
        return AuthResult(False, parse_status)
    for allowed in allowed_keys:
        if constant_time_equal(token, allowed):
            fp = secret_fingerprint(token, pepper, 'api-key')
            return AuthResult(True, 'authenticated', AuthPrincipal('api:' + fp[:16], fp), token)
    return AuthResult(False, 'authentication_failed')


def _safe_ip(value: str) -> str:
    try:
        return ipaddress.ip_address((value or '').strip()).compressed
    except ValueError:
        return 'unknown'


def direct_client_ip(request) -> str:
    client = getattr(request, 'client', None)
    return _safe_ip(getattr(client, 'host', '') or 'unknown')


def client_ip_from_request(request, trusted_proxies: Iterable[str] = ()) -> str:
    direct = direct_client_ip(request)
    trusted = {_safe_ip(item) for item in trusted_proxies if item}
    if direct not in trusted:
        return direct
    forwarded = (request.headers.get('x-forwarded-for') or '').split(',', 1)[0].strip()
    forwarded_ip = _safe_ip(forwarded)
    return forwarded_ip if forwarded_ip != 'unknown' else direct


def rate_subject(principal, client_ip: str, pepper: str) -> str:
    ip_part = secret_fingerprint(client_ip, pepper, 'client-ip')[:16]
    principal_part = principal.principal_id if principal else 'anonymous'
    return principal_part + ':ip:' + ip_part


class BoundedRateLimiter:
    def __init__(self, max_keys: int = 2048, now_func=time.monotonic):
        self.max_keys = max(1, int(max_keys))
        self._events: dict[str, deque[float]] = {}
        self._now = now_func

    @property
    def key_count(self) -> int:
        return len(self._events)

    def clear(self) -> None:
        self._events.clear()

    def _cleanup(self, now: float, window: int) -> None:
        cutoff = now - max(1, int(window))
        for key in list(self._events):
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                self._events.pop(key, None)

    def check(self, key: str, limit: int, window: int) -> RateLimitDecision:
        now = self._now()
        limit = max(1, int(limit))
        window = max(1, int(window))
        self._cleanup(now, window)
        if key not in self._events and len(self._events) >= self.max_keys:
            return RateLimitDecision(False, 'rate_limited', 1)
        events = self._events.setdefault(key, deque())
        while events and events[0] <= now - window:
            events.popleft()
        if len(events) >= limit:
            retry = max(1, int(window - (now - events[0]))) if events else 1
            return RateLimitDecision(False, 'rate_limited', retry)
        events.append(now)
        return RateLimitDecision(True)


def limit_key(route_class: str, subject: str, pepper: str) -> str:
    fp = secret_fingerprint(subject, pepper, 'rate-limit:' + route_class)[:32]
    return route_class + ':' + fp


def response_status_message(status: str) -> str:
    if status == 'authentication_required':
        return 'Authentication is required.'
    if status == 'authentication_failed':
        return 'Authentication failed.'
    if status == 'rate_limited':
        return 'Too many requests. Please retry later.'
    if status.startswith('mfa_'):
        return 'MFA verification failed.'
    if status.startswith('session_'):
        return 'Session is not available.'
    if status == 'authorization_failed':
        return 'Authorization failed.'
    return 'Request rejected.'


def status_code_for(status: str) -> int:
    if status in {'authentication_required', 'authentication_failed'}:
        return 401
    if status in {'authorization_failed', 'session_owner_mismatch'}:
        return 403
    if status == 'session_not_found':
        return 404
    if status in {'session_expired', 'session_token_invalid'}:
        return 409
    if status in {'rate_limited', 'mfa_locked'}:
        return 429
    if status == 'mfa_replay_rejected':
        return 401
    return 400


def safe_security_payload(status: str) -> dict[str, str]:
    return {'status': 'error', 'security_status': status, 'pesan': response_status_message(status)}
