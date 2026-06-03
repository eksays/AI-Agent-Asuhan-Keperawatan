"""
Otentikasi DIREKTUR — MFA berbasis TOTP (RFC 6238, implementasi stdlib, tanpa dependency).
Role "DIRECTOR" = pemilik TOTP secret. Login dengan kode 6-digit dari aplikasi authenticator
-> token sesi direktur berumur pendek (30 menit). Secret disimpan TERENKRIPSI (master key).
Enrollment: otpauth:// URI dicetak ke KONSOL SERVER sekali saat pertama dibuat (akses server-only),
atau diambil via /director/enroll yang dijaga env DIRECTOR_BOOTSTRAP.
(WebAuthn/passkey phishing-resistant dapat dilapiskan kemudian; butuh HTTPS + ceremony perangkat.)
"""
from __future__ import annotations
import os, time, hmac, hashlib, struct, base64, secrets, threading
import crypto_store

_SECRET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".director_totp")
_lock = threading.Lock()
_tokens: dict[str, float] = {}   # director_token -> expiry ts
_TOKEN_TTL = 30 * 60


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


def otpauth_uri(issuer: str = "CDSS Keperawatan", account: str = "Direktur") -> str:
    sec, _ = ensure_secret()
    return f"otpauth://totp/{issuer}:{account}?secret={sec}&issuer={issuer}&digits=6&period=30"


def _totp(secret_b32: str, t: float, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8), casefold=True)
    h = hmac.new(key, struct.pack(">Q", int(t // step)), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify_totp(code: str, window: int = 1) -> bool:
    sec = _load_secret()
    code = (code or "").strip()
    if not sec or not code.isdigit():
        return False
    now = time.time()
    return any(_totp(sec, now + w * 30) == code for w in range(-window, window + 1))


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
