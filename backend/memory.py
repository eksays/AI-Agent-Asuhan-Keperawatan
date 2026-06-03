"""
Crowdsourced clinical memory (RLHF) — JSON store, keyword similarity.
Koreksi 👎 dari perawat disuntik ke kasus serupa berikutnya.
"""
import os, time, threading, difflib
import crypto_store

_FILE = os.path.join(os.path.dirname(__file__), "feedback_memory.json")
_LOCK = threading.Lock()


def _load():
    return crypto_store.decrypt_load(_FILE, [])   # TERENKRIPSI at-rest


def _save(items):
    crypto_store.encrypt_save(_FILE, items)       # TERENKRIPSI at-rest


def _tokens(s):
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in (s or "")).split() if len(w) > 2}


def store_feedback(framework, pertanyaan, jawaban, rating, koreksi="", session_id=""):
    enc = bool(session_id)
    e = (lambda t: crypto_store.dek_encrypt(session_id, t)) if enc else (lambda t: t or "")   # crypto-shredding: enkripsi pakai DEK sesi
    with _LOCK:
        items = _load()
        items.append({"framework": framework, "session_id": session_id or "", "enc": enc,
                       "pertanyaan": e((pertanyaan or "")[:2000]),
                       "jawaban": e((jawaban or "")[:4000]), "rating": rating,
                       "koreksi": e((koreksi or "")[:2000]), "ts": time.time()})
        if len(items) > 1000:
            items = items[-1000:]
        _save(items)
    return True


def purge_session(session_id):
    """Hak Hapus Data: buang permanen seluruh feedback milik session_id. Kembalikan jumlah yang dihapus."""
    if not session_id:
        return 0
    with _LOCK:
        items = _load()
        kept = [it for it in items if it.get("session_id") != session_id]
        removed = len(items) - len(kept)
        if removed:
            _save(kept)
    return removed


def recall_block(framework, query, session_id=""):
    # ISOLASI TENANT MUTLAK: hanya recall koreksi dari session_id yang SAMA (cegah data poisoning lintas-user).
    if not session_id:
        return ""
    raw = [it for it in _load() if it.get("rating") == "down"
           and it.get("framework") == framework and it.get("session_id") == session_id]
    if not raw:
        return ""
    qtok = _tokens(query)
    scored = []
    for it in raw:
        kor = crypto_store.dek_decrypt(session_id, it.get("koreksi")) if it.get("enc") else it.get("koreksi")
        per = crypto_store.dek_decrypt(session_id, it.get("pertanyaan")) if it.get("enc") else it.get("pertanyaan")
        if not kor or not per:   # DEK sudah di-shred / data tak terbaca -> lewati (data telah dimusnahkan)
            continue
        ptok = _tokens(per)
        overlap = len(qtok & ptok) / (len(qtok | ptok) or 1)
        seq = difflib.SequenceMatcher(None, (query or "")[:400].lower(), per[:400].lower()).ratio()
        s = 0.6 * overlap + 0.4 * seq
        if s >= 0.18:
            scored.append((s, kor))
    scored.sort(key=lambda x: x[0], reverse=True)
    cor = [c for _, c in scored[:3]]
    if not cor:
        return ""
    return ("\n--- KOREKSI KLINIS DARI PERAWAT (WAJIB DIPERTIMBANGKAN) ---\n"
            + "\n".join(f"- {c}" for c in cor) + "\n")


def stats():
    items = _load()
    return {"total": len(items), "koreksi": sum(1 for i in items if i.get("rating") == "down" and i.get("koreksi"))}
