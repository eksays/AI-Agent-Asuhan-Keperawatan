"""
Penyimpanan TERENKRIPSI (data-at-rest) untuk file JSON yang dapat memuat data sensitif/PHI.
Memakai Fernet (AES-128-CBC + HMAC-SHA256, pustaka `cryptography`).
Kunci: env CDSS_SECRET_KEY; bila tidak ada -> dibuat & disimpan di file kunci lokal (.cdss_key, gitignored).
File didekripsi HANYA saat diload ke RAM; dienkripsi kembali saat save().
"""
from __future__ import annotations
import os, json, base64, hashlib, threading

_KEYFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cdss_key")
_DEKFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".dek_store")   # registry session_id -> DEK (terenkripsi master)
_fernet_cache = None
_dek_lock = threading.Lock()


def _get_fernet():
    global _fernet_cache
    if _fernet_cache is not None:
        return _fernet_cache
    from cryptography.fernet import Fernet
    raw = os.environ.get("CDSS_SECRET_KEY", "").strip()
    if raw:
        try:
            f = Fernet(raw.encode())                                   # sudah berupa Fernet key valid
        except Exception:
            f = Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()))   # derive dari passphrase
    elif os.path.exists(_KEYFILE):
        with open(_KEYFILE, "rb") as fh:
            f = Fernet(fh.read().strip())
    else:
        key = Fernet.generate_key()
        try:
            with open(_KEYFILE, "wb") as fh:
                fh.write(key)
            try:
                os.chmod(_KEYFILE, 0o600)
            except Exception:
                pass
        except Exception:
            pass
        f = Fernet(key)
    _fernet_cache = f
    return f


def encrypt_save(path: str, obj) -> None:
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    try:
        token = _get_fernet().encrypt(data)
        with open(path, "wb") as f:
            f.write(token)
    except Exception:
        # Gagal-aman: JANGAN pernah menulis PHI plaintext sebagai fallback (lebih baik tidak menyimpan).
        pass


def decrypt_load(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "rb") as f:
            blob = f.read()
        if not blob:
            return default
        try:
            return json.loads(_get_fernet().decrypt(blob).decode("utf-8"))
        except Exception:
            # Migrasi mulus: file lama plaintext JSON -> dibaca, lalu tersimpan terenkripsi saat save berikutnya.
            try:
                return json.loads(blob.decode("utf-8"))
            except Exception:
                return default
    except Exception:
        return default


# ===================== CRYPTO-SHREDDING: DEK unik per-session =====================
# Tiap session_id punya Data Encryption Key (DEK) acak sendiri; registry DEK disimpan
# TERENKRIPSI di bawah Master Key. Hapus DEK = data milik sesi itu jadi sampah kriptografis
# yang mustahil dikembalikan (pemusnahan absolut tanpa harus menghapus file datanya).
def _load_deks() -> dict:
    return decrypt_load(_DEKFILE, {})


def dek_get_or_create(sid: str) -> str:
    from cryptography.fernet import Fernet
    with _dek_lock:
        d = _load_deks()
        if sid not in d:
            d[sid] = Fernet.generate_key().decode()
            encrypt_save(_DEKFILE, d)
        return d[sid]


def dek_destroy(sid: str) -> bool:
    """Crypto-shred: musnahkan DEK milik sesi -> seluruh datanya tak dapat didekripsi selamanya."""
    with _dek_lock:
        d = _load_deks()
        if sid in d:
            del d[sid]
            encrypt_save(_DEKFILE, d)
            return True
    return False


def dek_encrypt(sid: str, text: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(dek_get_or_create(sid).encode()).encrypt((text or "").encode("utf-8")).decode()


def dek_decrypt(sid: str, token: str):
    """Kembalikan plaintext, atau None bila DEK sudah dimusnahkan / token rusak (= telah di-shred)."""
    from cryptography.fernet import Fernet
    with _dek_lock:
        key = _load_deks().get(sid)
    if not key:
        return None
    try:
        return Fernet(key.encode()).decrypt((token or "").encode()).decode("utf-8")
    except Exception:
        return None
