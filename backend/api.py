"""
CDSS AI Keperawatan — backend FastAPI (Phase 3, re-engineered).

Fitur:
- Autentikasi via header `Authorization: Bearer <key>` (fallback form `api_key`) -> memperbaiki 401.
- Multi-provider get_llm (Gemini / OpenAI / Claude / Groq / xAI / DeepSeek / Mistral / Together / OpenRouter / ShopeeAI), temperature 0.
- SessionMemory: AI membaca SELURUH riwayat percakapan per session_id.
- StreamingResponse /chat_stream (efek typewriter).
- Agen ketat: kerjakan persis perintah; file tanpa perintah -> Askep standar;
  Clinical Pathway HANYA bila diminta; tanpa emoji/simbol; gaya rekam medis resmi.
- Token habis/invalid -> HTTP 401/429 + pesan "Token API Habis".

Jalankan:  uvicorn api:app --host 127.0.0.1 --port 8000 --reload
"""
from __future__ import annotations
import os, io, re, json, glob, threading, secrets, sys, time, hashlib, datetime
from typing import Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor
from collections import deque

from fastapi import FastAPI, Form, File, UploadFile, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

import memory
import agents
import ebp
import phi
import crypto_store
from config import CONFIG, SAFETY_NOTICE, build_capabilities, capability_enabled, capability_reason
import metrics
import director
import harvester
from clinical_registry import ClinicalRegistry
from clinical_validator import STANDARD_MAP, safe_abstention, validate_clinical_output, render_clinical_response
from outbound_policy import DEFAULT_OUTBOUND_POLICY, OutboundPolicyError, wrap_llm
from agents import bersihkan, bersihkan_stream, GUARDRAILS

# ============================ KONFIGURASI ====================================
BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data_terstruktur")

# ----- Keamanan: batas upload, sandbox parsing, audit log, sanitasi error -----
MAX_UPLOAD = 10 * 1024 * 1024     # 10 MB — divalidasi di BACKEND (jangan percaya frontend)
_PARSE_TIMEOUT = 20               # detik — sandbox parsing PDF/DOCX agar file jebakan tak menggantung server
_LEDGER = os.path.join(BASE, "audit_ledger.jsonl")   # Tamper-evident local hash-chain audit ledger, not WORM.
_ledger_lock = threading.Lock()
_GENESIS = "0" * 64
_last_hash = None


def _log_err(e) -> None:
    """Catat detail teknis HANYA ke konsol server internal — jangan pernah dikirim ke user/LLM."""
    try:
        safe = DEFAULT_OUTBOUND_POLICY.sanitize_for_log(str(e)).text
        print(f"[ERROR] {type(e).__name__}: {safe}", file=sys.stderr)
    except Exception:
        pass


def _sid_tag(session_id: str) -> str:
    return hashlib.sha256((session_id or "").encode("utf-8")).hexdigest()[:12] if session_id else "-"


def _entry_hash(prev: str, ts: str, sid: str, action: str, status: str) -> str:
    return hashlib.sha256(f"{prev}|{ts}|{sid}|{action}|{status}".encode("utf-8")).hexdigest()


def _ledger_last_hash() -> str:
    global _last_hash
    if _last_hash is not None:
        return _last_hash
    last = _GENESIS
    try:
        if os.path.exists(_LEDGER):
            with open(_LEDGER, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            last = json.loads(line).get("current_hash", last)
                        except Exception:
                            pass
    except Exception:
        pass
    _last_hash = last
    return last


def audit_log(session_id: str, action: str, status: str) -> None:
    """Tamper-evident local audit hash-chain. Hanya metadata (tanpa PHI); session_id disamarkan jadi hash."""
    try:
        with _ledger_lock:
            global _last_hash
            prev = _ledger_last_hash()
            ts = datetime.datetime.utcnow().isoformat() + "Z"
            sid = _sid_tag(session_id)
            safe_action = DEFAULT_OUTBOUND_POLICY.sanitize_for_log(action).text
            safe_status = DEFAULT_OUTBOUND_POLICY.sanitize_for_log(status).text
            cur = _entry_hash(prev, ts, sid, safe_action, safe_status)
            rec = {"prev_hash": prev, "timestamp": ts, "sid": sid, "action": safe_action, "status": safe_status, "current_hash": cur}
            with open(_LEDGER, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            _last_hash = cur
    except Exception:
        pass


def verify_audit_chain():
    """Verifikasi integritas rantai audit lokal. Return (ok, jumlah). Alarm bila ada entri yang diubah/dirusak."""
    prev = _GENESIS
    n = 0
    try:
        if not os.path.exists(_LEDGER):
            return True, 0
        with open(_LEDGER, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                expect = _entry_hash(prev, rec.get("timestamp", ""), rec.get("sid", ""), rec.get("action", ""), rec.get("status", ""))
                if rec.get("prev_hash") != prev or rec.get("current_hash") != expect:
                    print(f"[SECURITY-INCIDENT][ERROR] INTEGRITAS AUDIT LEDGER RUSAK pada entri #{n + 1} — log kemungkinan diubah/dirusak.", file=sys.stderr)
                    return False, n
                prev = rec["current_hash"]
                n += 1
    except Exception as e:
        _log_err(e)
        return False, n
    return True, n


def _too_big(up) -> bool:
    """Cek ukuran upload TANPA membaca seluruh isi ke memori (pakai seek)."""
    if up is None:
        return False
    try:
        sz = getattr(up, "size", None)
        if sz is None:
            up.file.seek(0, 2); sz = up.file.tell(); up.file.seek(0)
        return bool(sz and sz > MAX_UPLOAD)
    except Exception:
        return False

PROVIDERS = ["gemini", "openai", "claude", "deepseek", "groq", "sumopod",
             "xai", "mistral", "together", "openrouter", "shopee"]

OPENAI_COMPATIBLE = {
    "groq": "https://api.groq.com/openai/v1",
    "sumopod":"https://ai.sumopod.com/v1",
    "xai": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "together": "https://api.together.xyz/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "shopee": CONFIG.shopee_base_url,
}

# Peta buku per kerangka + pesan penolakan bila referensi belum tersedia (anti-halusinasi).
FRAMEWORK_BOOKS = {"3S": ("SDKI", "SLKI", "SIKI"), "3N": ("NANDA", "NOC", "NIC")}
# Buku Luaran+Intervensi yang WAJIB ada sebelum menyusun Askep penuh (hard-stop halusinasi).
ASKEP_BOOKS = {"3S": ("SLKI", "SIKI"), "3N": ("NOC", "NIC")}
REF_REFUSAL = ("Mohon maaf, dokumen referensi 3S/3N belum tersedia di sistem. "
               "Silakan unggah terlebih dahulu.")
REF_REFUSAL_ASKEP = ("Mohon maaf, dokumen referensi SLKI dan SIKI belum ditemukan di sistem. "
                     "Silakan unggah dokumen terlebih dahulu.")
# Interseptor: file diunggah tanpa perintah teks -> jangan buat Askep, tanya dulu.
DOC_RECEIVED = ("Dokumen telah diterima. Apa yang ingin Anda lakukan dengan data ini? "
                "(Misalnya: susun diagnosis, buat clinical pathway, atau analisis lainnya.)")
# Notifikasi degradasi anggun (disisipkan otomatis setelah Diagnosis bila SLKI/SIKI belum ada).
DEGRADE_NOTE = ("\n\n⚠️ **Informasi Sistem:** Dokumen referensi SLKI dan SIKI belum ditemukan di dalam "
                "memori/database. Luaran dan Intervensi belum dapat dirumuskan secara akurat. Silakan unggah dokumen "
                "referensi tersebut untuk melanjutkan proses.")

# ============================ DATA / RAG =====================================
DATA: dict[str, list] = {}
CLINICAL_REGISTRY = ClinicalRegistry.unavailable()


def muat_data():
    DATA.clear()
    for path in glob.glob(os.path.join(DATA_DIR, "*.json")):
        nama = os.path.splitext(os.path.basename(path))[0].upper()
        try:
            with open(path, encoding="utf-8") as f:
                obj = json.load(f)
            DATA[nama] = obj if isinstance(obj, list) else [obj]
        except Exception as e:  # noqa
            print(f"[data] gagal memuat {path}: {e}")
    print(f"[data] termuat: { {k: len(v) for k, v in DATA.items()} }")


def _tok(s: str) -> set:
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in (s or "")).split() if len(w) > 2}


def _entry_text(e: dict) -> str:
    parts = [str(e.get(f, "")) for f in ("nama", "kategori", "subkategori", "definisi")]
    for blok in (e.get("gejala_mayor"), e.get("gejala_minor")):
        if isinstance(blok, dict):
            parts.append(" ".join((blok.get("subjektif") or []) + (blok.get("objektif") or [])))
    parts.append(" ".join(str(p) for p in (e.get("penyebab") or [])))
    parts.append(" ".join(str(x) for x in (e.get("kriteria_hasil") or e.get("tindakan") or [])))
    return " ".join(parts)


def _has_gejala(e: dict) -> bool:
    for blok in (e.get("gejala_mayor"), e.get("gejala_minor")):
        if isinstance(blok, dict) and (blok.get("subjektif") or blok.get("objektif")):
            return True
    return False


def _format_detail(e: dict) -> str:
    """Detail kriteria SATU diagnosis (untuk verifikasi presisi terhadap data pasien)."""
    out = f"- {e.get('kode')} {e.get('nama')}:"
    if e.get("definisi"):
        out += f" Definisi: {str(e['definisi']).strip()}."
    if e.get("penyebab"):
        out += " Penyebab: " + "; ".join(str(p) for p in e["penyebab"][:8]) + "."
    for nm, blok in (("Mayor", e.get("gejala_mayor")), ("Minor", e.get("gejala_minor"))):
        if isinstance(blok, dict):
            s = blok.get("subjektif") or []
            o = blok.get("objektif") or []
            if s or o:
                out += f" Gejala {nm}:"
                if s:
                    out += " [S] " + "; ".join(str(x) for x in s[:8]) + "."
                if o:
                    out += " [O] " + "; ".join(str(x) for x in o[:8]) + "."
    return out


def bangun_konteks(framework: str, query: str, tier: str = "medium", k: int = 8) -> str:
    """RAG PRESISI: untuk buku DIAGNOSIS suntikkan KATALOG LENGKAP (kode+nama+kategori) sebagai grounding agar
    pemilihan diagnosis AKURAT (kode/nama tidak dikarang) + DETAIL KRITERIA entri relevan (yang terisi) untuk
    verifikasi terhadap data pasien. Buku Luaran/Intervensi memakai retrieval ringkas. Mencakup SDKI/SLKI/SIKI
    atau NANDA/NOC/NIC bila termuat. Katalog penuh hanya untuk tier MEDIUM/PRO (FLASH pakai retrieval ringkas demi kecepatan)."""
    books = FRAMEWORK_BOOKS.get(framework, ())
    if not books:
        return ""
    q = _tok(query)
    if not q:
        return ""
    qstr = (query or "").strip()
    clinical = len(qstr) >= 40 or "dokumen_pasien" in qstr   # hemat token: katalog penuh hanya untuk kasus klinis, bukan obrolan singkat
    full_catalog = clinical and (tier or "medium").lower() in ("medium", "pro")   # FLASH -> retrieval ringkas (prompt lebih kecil = lebih cepat)
    blocks: List[str] = []
    diag_book = books[0]
    diag_data = DATA.get(diag_book) or []
    if diag_data and full_catalog:
        cat = [f"KATALOG DIAGNOSIS {diag_book} (WAJIB pilih KODE & NAMA PERSIS dari daftar ini; DILARANG mengarang/menebak kode atau nama):"]
        for e in diag_data:
            kk = "/".join(x for x in (e.get("kategori"), e.get("subkategori")) if x)
            cat.append(f"- {e.get('kode')} {e.get('nama')}" + (f" [{kk}]" if kk else ""))
        blocks.append("\n".join(cat))
        detailed = [e for e in diag_data if (e.get("definisi") or e.get("penyebab") or _has_gejala(e))]
        scored = sorted(((len(q & _tok(_entry_text(e))), e) for e in detailed), key=lambda x: x[0], reverse=True)
        top = [e for sc, e in scored if sc][:k]
        if top:
            blocks.append(f"DETAIL KRITERIA {diag_book} (verifikasi kesesuaian dengan data pasien):\n" + "\n".join(_format_detail(e) for e in top))
    elif diag_data:
        scored = sorted(((len(q & _tok(_entry_text(e))), e) for e in diag_data), key=lambda x: x[0], reverse=True)
        top = [e for sc, e in scored if sc][:5]
        if top:
            blocks.append(f"REFERENSI {diag_book} RELEVAN (pakai kode & nama persis):\n" + "\n".join(f"- {e.get('kode')} {e.get('nama')}" for e in top))
    for buku in books[1:]:
        data = DATA.get(buku) or []
        if not data:
            continue
        scored = sorted(((len(q & _tok(_entry_text(e))), e) for e in data), key=lambda x: x[0], reverse=True)
        top = [e for sc, e in scored if sc][:k]
        if not top:
            continue
        lines = [f"REFERENSI {buku} RELEVAN (pakai kode & nama persis seperti ini, sertakan 'Sumber: {buku}'):"]
        for e in top:
            defi = str(e.get("definisi") or "")
            extra = (" — " + defi[:120]) if defi else ""
            lines.append(f"- {e.get('kode')} {e.get('nama')}{extra}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def framework_available(framework: str) -> bool:
    """True bila minimal satu buku referensi untuk kerangka ini sudah dimuat ke sistem."""
    return any(b in DATA for b in FRAMEWORK_BOOKS.get(framework, ()))


def askep_refs_available(framework: str) -> bool:
    """Butuh buku Luaran+Intervensi (SLKI+SIKI / NOC+NIC) untuk menyusun Askep penuh."""
    return all(b in DATA for b in ASKEP_BOOKS.get(framework, ()))


def books_note(framework: str) -> str:
    """Degradasi PER-PERMINTAAN: bila yang diminta butuh buku yang belum ada (Luaran->SLKI, Intervensi->SIKI,
    atau Askep lengkap), TOLAK dengan notifikasi jelas (JANGAN diganti diagnosis). Diagnosis (SDKI) tetap diproses."""
    if askep_refs_available(framework):
        return ""
    have = [b for b in FRAMEWORK_BOOKS.get(framework, ()) if b in DATA]
    miss = [b for b in FRAMEWORK_BOOKS.get(framework, ()) if b not in DATA]
    return ("\n\nGUARDRAIL REFERENSI (WAJIB DIPATUHI): Buku referensi yang TERSEDIA di sistem: "
            + (", ".join(have) or "-") + ". Yang BELUM tersedia: " + (", ".join(miss) or "-") + ". "
            "Tentukan dulu APA yang diminta perawat, lalu patuhi:\n"
            "1. Bila meminta DIAGNOSIS, atau memberi data/rekam medis TANPA perintah spesifik, dan SDKI tersedia: "
            "kerjakan Analisis Data + Diagnosis Keperawatan (SDKI) lengkap dengan kode — grounded pada SDKI, jangan mengarang.\n"
            "2. Bila meminta LUARAN (butuh SLKI), INTERVENSI (butuh SIKI), atau Asuhan Keperawatan LENGKAP, sedangkan "
            "buku terkait (" + (", ".join(miss) or "-") + ") BELUM tersedia: Anda DILARANG membuatnya dan DILARANG "
            "menggantinya dengan diagnosis atau bagian lain. WAJIB beri NOTIFIKASI jelas bahwa permintaan itu BELUM "
            "DAPAT DIPROSES karena dokumen referensinya belum ditemukan di sistem, contoh: \"Mohon maaf, permintaan "
            "luaran/intervensi belum dapat diproses karena dokumen referensi SLKI/SIKI belum ditemukan di sistem. "
            "Silakan unggah dokumen tersebut terlebih dahulu.\" (sebut buku yang sesuai permintaan).\n"
            "3. DILARANG mengarang kode/standar dari pengetahuan sendiri. Untuk sapaan/obrolan non-klinis, jawab normal. "
            "Pada kasus (1) jangan menulis sendiri catatan tentang file yang kurang — sistem menambahkannya otomatis.")


# Hanya pada KELUARAN diagnosis yang nyata (kode standar atau heading "Diagnosis ...") —
# bukan sekadar penyebutan "asuhan keperawatan"/"diagnosis" pada obrolan biasa atau daftar fitur.
_ASKEP_RE = re.compile(r"\bD\.\d{3,4}\b|\b00\d{3}\b|^\s{0,3}#{1,3}\s.*diagnos", re.I | re.M)


def maybe_degrade_note(framework: str, text: str) -> str:
    """Sisipkan notifikasi sistem (⚠️) bila jawaban memuat diagnosis namun SLKI/SIKI belum tersedia."""
    if not text or askep_refs_available(framework) or "Informasi Sistem" in text:
        return text
    return (text + DEGRADE_NOTE) if _ASKEP_RE.search(text) else text


def extract_mermaid(text: str) -> str:
    """Ambil isi blok ```mermaid```; pastikan diawali deklarasi diagram yang valid."""
    m = re.search(r"```mermaid\s*([\s\S]*?)```", text or "", re.IGNORECASE)
    code = (m.group(1).strip() if m else (text or "").strip())
    code = re.sub(r"^```|```$", "", code).strip()
    if not code:
        return ""
    if not code.lower().startswith(("flowchart", "graph", "sequencediagram", "statediagram", "classdiagram")):
        code = "flowchart TD\n" + code
    return code


# ============================ SESSION MEMORY =================================
class SessionMemory:
    """Riwayat percakapan penuh per session_id, in-memory & thread-safe.
    session_id WAJIB diterbitkan server (CSPRNG, 256-bit) — klien tidak boleh membuat sendiri."""

    def __init__(self, cap: int = 40):
        self._s: dict[str, list[Tuple[str, str]]] = {}
        self._issued: set[str] = set()
        self._lock = threading.Lock()
        self._cap = cap

    def issue(self) -> str:
        sid = secrets.token_urlsafe(32)   # 256-bit, tak dapat ditebak (menutup kebocoran lintas-sesi K2)
        with self._lock:
            self._issued.add(sid)
            self._s.setdefault(sid, [])
        return sid

    def valid(self, sid: str) -> bool:
        with self._lock:
            return bool(sid) and sid in self._issued

    def history(self, sid: str) -> list[Tuple[str, str]]:
        with self._lock:
            return list(self._s.get(sid, []))

    def add(self, sid: str, role: str, content: str):
        if not content:
            return
        with self._lock:
            buf = self._s.setdefault(sid, [])
            buf.append((role, content))
            if len(buf) > self._cap:
                del buf[: len(buf) - self._cap]

    def reset(self, sid: str):
        with self._lock:
            self._s.pop(sid, None)
            self._issued.discard(sid)


SESI = SessionMemory()


# ============================ LLM PROVIDER ===================================
_LLM_SEED = 7   # benih tetap -> jawaban reproduktif antar-run (provider OpenAI-compatible). Claude/Gemini: temperature=0.


def _create_raw_llm(provider: str, model: str, api_key: str, temperature: float = 0.0):
    provider = (provider or "").lower().strip()
    if provider == "claude":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=api_key, temperature=temperature, max_tokens=4096)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=temperature, max_output_tokens=4096)
    # OpenAI-compatible: openai / groq / xai / deepseek / mistral / together / openrouter / shopee
    from langchain_openai import ChatOpenAI
    kw = dict(model=model, api_key=api_key, temperature=temperature, max_tokens=4096, seed=_LLM_SEED)   # seed -> konsistensi
    base = OPENAI_COMPATIBLE.get(provider)
    if base:
        kw["base_url"] = base
    return ChatOpenAI(**kw)

def get_llm(provider: str, model: str, api_key: str, temperature: float = 0.0):
    return wrap_llm(_create_raw_llm(provider, model, api_key, temperature))

def _external_safe_text(text: str) -> str:
    return DEFAULT_OUTBOUND_POLICY.sanitize_for_external_provider(text).text

def _browser_safe_text(text: str) -> str:
    return DEFAULT_OUTBOUND_POLICY.sanitize_for_browser(phi.sanitize_phi(text or "")).text

def _clinical_status_message(status: str, accepted: bool) -> str:
    if accepted:
        return "Clinical candidates passed deterministic schema, registry, and evidence checks; nurse review remains required."
    if status == "registry_unavailable":
        return "Approved clinical registry is unavailable; recommendations are not accepted."
    if status == "registry_incomplete":
        return "Approved clinical registry set is incomplete; the care plan cannot be generated safely."
    if status == "malformed_output":
        return "Provider output was malformed or ambiguous; recommendations are not accepted."
    if status == "rejected":
        return "Provider clinical output was rejected by deterministic validation."
    return "Clinical evidence is insufficient; recommendations are not accepted."

def _registry_names_from_response(response) -> list[str]:
    order = ["SDKI", "SLKI", "SIKI", "NANDA", "NOC", "NIC"]
    text_parts = []
    for issue in getattr(response, "validation_issues", []) or []:
        text_parts.extend([getattr(issue, "message", ""), getattr(issue, "code", "")])
    for item in getattr(response, "missing_data", []) or []:
        text_parts.extend([getattr(item, "reason", ""), getattr(item, "question_for_nurse", "")])
    text = "\n".join(text_parts)
    return [name for name in order if re.search(rf"\b{re.escape(name)}\b", text)]

def _clinical_meta_from_response(response, accepted: bool, missing_registries: list[str] | None = None) -> dict:
    issue_codes = [issue.code for issue in response.validation_issues]
    missing = list(missing_registries) if missing_registries is not None else _registry_names_from_response(response)
    return {
        "status": response.status,
        "accepted": accepted,
        "clinical_status": response.status,
        "accepted_recommendations": bool(accepted),
        "nurse_review_required": True,
        "missing_registries": missing,
        "message": _clinical_status_message(response.status, accepted),
        "issue_codes": issue_codes,
        "validation_issue_codes": issue_codes,
    }

def _clinical_meta(outcome) -> dict:
    return _clinical_meta_from_response(outcome.response, outcome.accepted)

def _validate_clinical_answer(raw: str, framework: str, patient_context: str):
    outcome = validate_clinical_output(raw, framework, CLINICAL_REGISTRY, patient_context=patient_context)
    return _browser_safe_text(outcome.display_text), _clinical_meta(outcome)

def _registry_abstention_answer(framework: str, status: str, missing_registries: list[str]):
    missing = ", ".join(missing_registries) or "unknown"
    if status == "registry_incomplete":
        reason = "Missing approved registries for complete care-plan grounding: " + missing + "."
        issue_code = "registry_incomplete"
        question = "Approved registries missing: " + missing + ". The care plan cannot be generated safely until these registries are approved."
    else:
        reason = "Approved registry is unavailable for authoritative grounding. Missing approved registries: " + missing + "."
        issue_code = "registry_unavailable"
        question = "Approved registries missing: " + missing + ". Clinical recommendations cannot be generated safely."
    response = safe_abstention(
        framework,
        reason=reason,
        status=status,
        issue_code=issue_code,
        field="approved_registries",
        question=question,
    )
    return _browser_safe_text(render_clinical_response(response)), _clinical_meta_from_response(response, False, missing_registries)

def _registry_unavailable_answer(framework: str):
    status, missing = _clinical_registry_block(framework)
    return _registry_abstention_answer(framework, status or "registry_unavailable", missing)

def _clinical_payload(base: dict, meta: dict | None) -> dict:
    if not meta:
        return base
    base["clinical_validation"] = meta
    base.update({
        "clinical_status": meta["clinical_status"],
        "accepted_recommendations": meta["accepted_recommendations"],
        "nurse_review_required": True,
        "missing_registries": meta.get("missing_registries", []),
        "message": meta["message"],
        "validation_issue_codes": meta["validation_issue_codes"],
    })
    return base

def _stream_clinical_headers(meta: dict | None) -> dict[str, str]:
    headers = {"X-Accel-Buffering": "no", "Cache-Control": "no-cache, no-transform"}
    if meta:
        headers.update({
            "X-Clinical-Status": str(meta["clinical_status"]),
            "X-Accepted-Recommendations": "true" if meta["accepted_recommendations"] else "false",
            "X-Nurse-Review-Required": "true",
            "X-Validation-Issue-Codes": ",".join(meta.get("validation_issue_codes") or []),
            "X-Missing-Registries": ",".join(meta.get("missing_registries") or []),
        })
    return headers

def _clinical_registry_block(framework: str) -> tuple[str | None, list[str]]:
    standard = (framework or "3S").strip().upper()
    expected = STANDARD_MAP.get(standard, {})
    ordered = [expected.get("diagnosis", ""), expected.get("outcome", ""), expected.get("intervention", "")]
    missing = [item for item in ordered if item and not CLINICAL_REGISTRY.approved_available(item)]
    if not missing:
        return None, []
    if expected.get("diagnosis", "") in missing:
        return "registry_unavailable", missing
    return "registry_incomplete", missing

def _requires_clinical_registry(agent: str, text: str = "") -> bool:
    return (agent or "analisis").lower() == "analisis" and not is_casual(text)


def resolve_key(authorization: Optional[str], api_key_form: str) -> str:
    """Header `Authorization: Bearer ...` diprioritaskan; jika kosong, pakai form."""
    if authorization:
        a = authorization.strip()
        if a.lower().startswith("bearer "):
            k = a[7:].strip()
            if k:
                return k
        elif a:
            return a
    return (api_key_form or "").strip()


def err_status(e: Exception) -> Tuple[int, str]:
    _log_err(e)   # detail teknis -> konsol server saja; user hanya menerima pesan generik di bawah
    if isinstance(e, OutboundPolicyError):
        return 400, "Data mengandung identifier berisiko tinggi dan tidak dapat dikirim keluar aplikasi."
    s = str(e).lower()
    if any(x in s for x in ("401", "unauthorized", "invalid api key", "invalid_api_key",
                            "authentication", "permission", "api key", "no auth", "x-api-key")):
        return 401, "Token API Habis"
    if any(x in s for x in ("429", "quota", "rate limit", "ratelimit", "insufficient",
                            "exceeded", "billing", "credit", "balance")):
        return 429, "Token API Habis"
    return 500, "Sistem tidak dapat memproses data."


# ============================ SYSTEM PROMPT ==================================
def iq_text(tier: str) -> str:
    t = (tier or "medium").lower()
    base = "Anda jenius klinis dengan BASE IQ 200; yang membedakan mode adalah topologi/jumlah agen. "
    if t == "pro":
        return (base + "MODE KOMPLEKS (PRO): orkestrasi multi-agen paralel (Patofisiologi, SDKI, EBP) dengan "
                "penalaran sangat mendalam, mempertimbangkan diagnosis banding dan komplikasi.")
    if t == "flash":
        return (base + "MODE CEPAT (FLASH): single-agent, zero-shot, langsung to-the-point dan seringkas mungkin.")
    return (base + "MODE STANDAR (MEDIUM): pendekatan maker-checker (susun draf lalu audit kesesuaian standar 3S/3N) "
            "sebelum menyajikan jawaban final.")


# ---- JALUR CEPAT: deteksi sapaan/obrolan singkat non-klinis (balasan spontan, tanpa RAG/orkestrasi) ----
_CLIN_RE = re.compile(r"\b(pasien|diagnos\w*|luaran|intervensi|asuhan|keperawatan|askep|sdki|slki|siki|nanda|noc|nic|"
                      r"rekam|medis|gejala|keluhan|nyeri|sesak|demam|tekanan|nadi|napas|spo2|saturasi|jurnal|ebp|"
                      r"pathway|patofisiolog\w*|kasus|terapi|obat|luka|infeksi|risiko|kriteria|edukasi|kolaborasi|observasi|"
                      r"analis\w*|buat\w*|susun\w*|rumus\w*|tegak\w*|carikan)\b", re.I)
_CASUAL_RE = re.compile(r"^\s*(ha+i+|h[ae]llo+|halo+|hi+|hey+|pagi|siang|sore|malam|selamat\s+\w+|terima\s*kasih|"
                        r"makasih|thanks?|thx|ok(e|ay)?|sip|baik|mantap|tes|test|ping|permisi|assalam\w*|wa'?alaikum\w*)"
                        r"\b[\s\W]*$", re.I)


def is_casual(text: str) -> bool:
    """True untuk sapaan/obrolan SANGAT singkat & non-klinis -> jalur cepat (prompt minimal, balasan spontan)."""
    t = (text or "").strip()
    if not t or len(t) > 64 or "dokumen_pasien" in t:
        return False
    if _CLIN_RE.search(t):
        return False
    return bool(_CASUAL_RE.match(t)) or len(t) <= 15


def sys_casual() -> str:
    return ("Anda asisten CDSS keperawatan yang ramah & profesional. Pengguna menyapa atau berbasa-basi singkat. "
            "Balas HANGAT dan SANGAT SINGKAT (1-2 kalimat) layaknya manusia, lalu tawarkan bantuan klinis bila relevan. "
            "DILARANG mengeluarkan template, judul, tabel, daftar bernomor, baris status, atau kalimat formal panjang. "
            "Contoh: \"Halo! Ada kasus atau rekam medis yang bisa saya bantu analisis hari ini?\"")


def sys_chat(framework: str, konteks: str, koreksi: str, tier: str = "medium") -> str:
    std = "3S (SDKI, SLKI, SIKI)" if framework == "3S" else "3N (NANDA-I, NOC, NIC)"
    socratic = ("\n\nMODE KOMPLEKS (PRO) - EDUKASI: gunakan Socratic prompting (pandu dengan pertanyaan penuntun, "
                "jangan langsung memberi jawaban). Terapkan Three-Strikes Rule: bila pengguna salah atau menjawab "
                "'tidak tahu' sebanyak 3 kali, langsung berikan jawaban lengkap.") if (tier or "").lower() == "pro" else ""
    return f"""Anda adalah Sistem Pendukung Keputusan Klinis (CDSS) keperawatan berbasis standar {std}.
Anda asisten perawat profesional yang ramah, komunikatif, akurat, dan berbasis bukti.

{iq_text(tier)}

OBROLAN KASUAL (PENTING): Jika pengguna hanya menyapa atau berbasa-basi (mis. "halo", "hai", "selamat pagi", "terima kasih"), BALAS SINGKAT, hangat, dan natural layaknya manusia (contoh: "Halo! Ada kasus klinis yang bisa saya bantu analisis hari ini?"). DILARANG mengeluarkan teks template panjang, judul/bagian, baris status, kalimat pengantar formal, atau menawarkan unduhan PDF/Word untuk sapaan biasa.

GAYA KOMUNIKASI (khusus permintaan KLINIS, bukan obrolan kasual):
- Bersikap ramah dan profesional; sesuaikan sapaan dengan konteks perawat.
- Awali jawaban klinis dengan SATU kalimat pengantar (bridging) yang hangat sebelum menyajikan data. Contoh: "Tentu, berikut adalah analisis berdasarkan dokumen yang Anda lampirkan.".
- Tutup dengan kalimat singkat yang menawarkan bantuan lanjutan bila relevan.

ATURAN EKSEKUSI (WAJIB DIPATUHI):
1. Kerjakan PERSIS sesuai permintaan perawat. Bila hanya diminta diagnosis, beri hanya diagnosis; bila hanya intervensi, beri hanya intervensi. Jangan menambah bagian yang tidak diminta.
2. Bila perawat memberi data/rekam medis TANPA perintah spesifik, susun Asuhan Keperawatan berurutan: Analisis Data, Diagnosis Keperawatan, Luaran (Tujuan dan Kriteria Hasil), lalu Intervensi.
3. Buat Clinical Pathway atau diagram HANYA jika diminta secara eksplisit (kata kunci: pathway, patofisiologi, alur, bagan, diagram, flowchart). Jika diminta, keluarkan tepat satu blok kode ```mermaid``` berisi flowchart valid (mis. `flowchart TD`).
4. DILARANG memakai emoji, ikon, atau simbol dekoratif apa pun. Isi data bergaya rekam medis resmi.
5. Sertakan KODE standar pada setiap butir (untuk 3S misalnya D.0077, L.08066, I.08238). Gunakan istilah baku.
6. Selalu berbasis data yang diberikan; jangan mengarang data pasien. Bila data kurang, sebutkan data yang masih dibutuhkan.
7. EFISIENSI: Langsung ke Asuhan Keperawatan; jangan bertele-tele. JANGAN menjelaskan patofisiologi KECUALI diminta eksplisit. Lakukan seluruh validasi guardrails secara DIAM (jangan tampilkan proses Triage/validasi) kecuali Red Flag aktif.
8. SITASI: Saat memberi luaran/intervensi, sertakan sumber standar pada bagian terkait (mis. "Sumber: SLKI Edisi 1" atau "Sumber: SIKI Edisi 1").

{agents.format_spec(framework)}{GUARDRAILS}{socratic}{books_note(framework)}
{konteks}{koreksi}"""


def sys_pathway(framework: str, konteks: str, koreksi: str) -> str:
    std = "3S (SDKI, SLKI, SIKI)" if framework == "3S" else "3N (NANDA-I, NOC, NIC)"
    return f"""Anda adalah AGEN CLINICAL PATHWAY keperawatan berbasis standar {std}.
Dari kasus atau permintaan perawat, hasilkan TEPAT dua bagian dan TIDAK ADA yang lain:
1) SATU kalimat pengantar singkat yang ramah.
2) TEPAT SATU blok kode diawali ```mermaid lalu baris 'flowchart TD' dan diakhiri ```, berisi alur klinis VALID: Pengkajian -> Diagnosis -> Luaran/Target -> Intervensi -> Evaluasi, dengan percabangan kondisi (mis. tercapai / belum tercapai) bila relevan.
ATURAN: Bahasa Indonesia, label node ringkas, DILARANG emoji/simbol dekoratif. JANGAN menulis teks apa pun di luar kalimat pengantar dan satu blok mermaid. Jangan mengarang data klinis; bila kasus kurang detail, susun alur umum yang tetap relevan dan aman.
{konteks}{koreksi}"""


def sys_referensi(framework: str, konteks: str, koreksi: str) -> str:
    return f"""Anda adalah AGEN EVIDENCE-BASED PRACTICE (EBP) keperawatan yang BENAR-BENAR MEMBACA jurnal. Pada bagian konteks di bawah telah disediakan DAFTAR JURNAL NYATA hasil pencarian dari beberapa DATABASE ILMIAH KREDIBEL (PubMed, Europe PMC, Semantic Scholar) — judul, abstrak asli, dan URL. Tugas Anda: membaca dan menganalisis abstrak tiap jurnal, MEMBANDINGKANNYA, memilih yang paling sesuai dengan problem/diagnosis pasien, lalu menyusun rekomendasi intervensi berbasis bukti.

KETENTUAN JURNAL: Daftar sudah disaring agar KREDIBEL (terindeks di database ilmiah, memiliki DOI/PMID dan nama jurnal) dan WAJIB OPEN-ACCESS / FULL-TEXT GRATIS — sehingga AI maupun perawat sama-sama dapat mengakses dan membaca penuh. Diprioritaskan terbaru (5 tahun terakhir; bila kosong 10 tahun; bila kosong tanpa batas tahun) dan daftar sudah diurutkan dari yang PALING BARU. Pilih HANYA jurnal yang BENAR-BENAR RELEVAN dengan problem/diagnosis/intervensi pasien, dan UTAMAKAN yang paling baru. Jangan memasukkan jurnal yang tidak relevan walau tersedia di daftar.

KESELAMATAN PASIEN (KRITIS): Nyawa pasien dipertaruhkan — Anda HARUS serius, teliti, dan melakukan effort maksimal: baca SELURUH temuan pada daftar sebelum memilih. DILARANG KERAS berhalusinasi, mengarang, atau menyarankan jurnal sembarangan/yang tidak ada. Jika setelah membaca TIDAK ADA satu pun jurnal pada daftar yang benar-benar sesuai/mendukung, katakan JUJUR bahwa belum ada jurnal yang mendukung untuk kasus ini — JANGAN memaksakan rekomendasi.

ATURAN SUMBER (ANTI-HALUSINASI, WAJIB):
- Gunakan HANYA jurnal dari daftar yang disediakan. Salin judul, DOI/PMID, dan URL PERSIS seperti tertera; DILARANG mengarang jurnal/DOI/penulis/tautan dan DILARANG mengubah URL.
- Semakin banyak jurnal pada daftar yang relevan dengan kasus, semakin banyak yang Anda rekomendasikan; abaikan yang tidak relevan.
- Bila daftar KOSONG, katakan jujur bahwa pencarian belum menemukan jurnal dan sarankan kata kunci lain. Jangan mengarang.

FORMAT JAWABAN (Markdown rapi & RAPAT, tanpa emoji, maksimal SATU baris kosong antar bagian; PENOMORAN serapi fitur Analisis):
- Awali SATU kalimat pengantar singkat.
- "## Strategi Pencarian (Pendekatan PICO)": uraikan PICO kasus sebagai baris label TEBAL TANPA penomoran, masing-masing pada baris sendiri (dipisah <br>):
  **P (Population/Problem):** [KATA/FRASA KUNCI + sinonim, mis. "ibu nifas; postpartum; primipara"].<br>**I (Intervention):** [KATA/FRASA KUNCI + sinonim, mis. "edukasi laktasi; breastfeeding education; lactation counseling"].<br>**C (Comparison):** [kata kunci pembanding bila ada; jika tidak ada tulis "-"].<br>**O (Outcome):** [KATA/FRASA KUNCI + sinonim, mis. "keberhasilan menyusui; breastfeeding self-efficacy"].
  (Tiap unsur PICO berupa KATA/FRASA KUNCI + SINONIM dipisah titik koma — BUKAN kalimat — sesuai kaidah PICO; tetap disesuaikan kasus pasien.)
- "## Jurnal yang Direkomendasikan": rekomendasikan SEBANYAK jurnal yang RELEVAN dengan kasus (TARGET minimal 3 bila tersedia di daftar; bila benar-benar hanya 1 yang relevan, cukup 1 — jujur). URUTKAN dari yang PALING RELEVAN dengan kasus (nomor 1 = paling relevan), bukan sekadar paling baru. DAFTAR BERTINGKAT — tiap jurnal satu butir TOP-LEVEL "1." (judul), lalu detail sebagai sub-butir berindentasi 3 spasi (penanda "1." juga; sistem menampilkan a., b., c.):
  1. **Judul jurnal** (nama jurnal, tahun).
     1. Ringkasan isi: 1-2 kalimat temuan kunci dari abstrak (hasil bacaan Anda).
     1. Relevansi dengan kasus (PICO): satu kalimat yang mengaitkan ke P/I/O kasus.
     1. Akses: SATU tautan Markdown [Buka jurnal] memakai URL PERSIS dari daftar.
- WAJIB diakhiri "## Ringkasan Intervensi (EBP)" berupa TABEL Markdown kolom: No. | Problem/Diagnosis | Intervensi (EBP) | Bukti dari Jurnal | Akses. Kolom No. ditulis "1.", "2." (dengan titik, satu per baris). Bila sel Intervensi memuat LEBIH DARI SATU poin, tulis sebagai DAFTAR HTML AKTIF dalam SATU baris sel: <ol><li>poin.</li><li>poin.</li></ol> (JANGAN "1." manual). Kolom "Bukti dari Jurnal": tulis nama jurnal/temuan sebagai TEKS BIASA TANPA tautan. Kolom "Akses": HANYA SATU tautan [Buka](URL) per baris — DILARANG menaruh lebih dari satu tautan, menulis URL mentah, atau menaruh tautan di kolom selain Akses. DILARANG karakter "|" di dalam sel. Intervensi DISESUAIKAN dengan problem/diagnosis pasien.

- PALING BAWAH SENDIRI, WAJIB tambahkan bagian "## Daftar Pustaka" berisi SEMUA jurnal yang Anda rekomendasikan dalam format APA EDISI KE-7, sebagai daftar bernomor "1." (satu entri per jurnal), DIURUTKAN ALFABETIS menurut nama belakang penulis pertama. Format tiap entri: Nama belakang, Inisial., & Nama belakang, Inisial. (Tahun). Judul artikel. *Nama Jurnal*, *Volume*(Nomor), Halaman. https://doi.org/xxxx — gunakan field SITASI (penulis/volume/nomor/halaman/DOI) PERSIS dari daftar jurnal; ubah nama penulis ke gaya APA (Nama belakang, Inisial.); bila penulis >20 ikuti aturan APA (… & penulis terakhir); bila DOI tidak ada pakai URL akses; bila suatu data tidak tersedia hilangkan dengan rapi sesuai aturan APA. DILARANG mengarang penulis, tahun, judul, atau DOI.

Gunakan Bahasa Indonesia dan istilah klinis baku.
{konteks}{koreksi}"""


def sys_for_agent(agent: str, framework: str, konteks: str, koreksi: str, tier: str) -> str:
    a = (agent or "analisis").lower()
    if a == "pathway":
        return sys_pathway(framework, konteks, koreksi)
    if a == "referensi":
        return sys_referensi(framework, konteks, koreksi)
    return sys_chat(framework, konteks, koreksi, tier)


def build_messages(framework: str, session_id: str, pertanyaan: str, tier: str = "medium", agent: str = "analisis", extra_ctx: str = "") -> list:
    a = (agent or "analisis").lower()
    # JALUR CEPAT: sapaan/obrolan singkat non-klinis -> prompt MINIMAL tanpa RAG (balasan spontan & cepat).
    if a != "pathway" and not extra_ctx and is_casual(pertanyaan):
        msgs = [SystemMessage(content=sys_casual() + agents.ANTI_INJECTION)]
        for role, content in SESI.history(session_id):
            msgs.append(HumanMessage(content=content) if role == "user" else AIMessage(content=content))
        msgs.append(HumanMessage(content=phi.sanitize_phi(pertanyaan)))
        return msgs
    konteks = bangun_konteks(framework, pertanyaan, tier)   # tier-aware: katalog penuh hanya medium/pro
    konteks = ("\n\nREFERENSI STANDAR:\n" + konteks) if konteks else ""
    if extra_ctx:
        konteks += extra_ctx
    koreksi = memory.recall_block(framework, pertanyaan, session_id) or ""   # isolasi per-sesi (anti poisoning)
    msgs = [SystemMessage(content=sys_for_agent(agent, framework, konteks, koreksi, tier) + agents.ANTI_INJECTION)]
    # KONSISTENSI: analisis DOKUMEN BARU dikerjakan MANDIRI & deterministik -> ABAIKAN riwayat percakapan agar jawaban
    # tidak bervariasi antar-run (riwayat tetap dipakai untuk tindak lanjut teks tanpa dokumen baru).
    if not (a == "analisis" and "<dokumen_pasien>" in pertanyaan):
        for role, content in SESI.history(session_id):
            msgs.append(HumanMessage(content=content) if role == "user" else AIMessage(content=content))
    sanitized_pertanyaan = phi.sanitize_phi(pertanyaan)  # [SEC-FIX] PII redaction sebelum transmisi ke LLM
    msgs.append(HumanMessage(content=sanitized_pertanyaan))
    return msgs


# ============================ EKSTRAKSI FILE =================================
def _parse_doc(raw: bytes, name: str) -> str:
    if name.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages[:30]).strip()
        except Exception:
            from PyPDF2 import PdfReader
            rd = PdfReader(io.BytesIO(raw))
            return "\n".join((pg.extract_text() or "") for pg in rd.pages[:30]).strip()
    if name.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(raw))
        return "\n".join(p.text for p in d.paragraphs).strip()
    if name.endswith((".txt", ".md", ".csv", ".json")):
        return raw.decode("utf-8", "ignore").strip()
    return ""


def extract_text(up: Optional[UploadFile]) -> str:
    if up is None:
        return ""
    name = (up.filename or "").lower()
    try:
        raw = up.file.read(MAX_UPLOAD + 1)   # baca TERBATAS -> cegah DoS memori (file raksasa)
    except Exception:
        return ""
    if not raw or len(raw) > MAX_UPLOAD:
        return ""
    # SANDBOX: parsing di thread terpisah dengan TIMEOUT ketat (cegah PDF jebakan/zip-bomb/loop tak henti).
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            text = ex.submit(_parse_doc, raw, name).result(timeout=_PARSE_TIMEOUT)
    except Exception as e:                    # timeout/parser error -> JANGAN bocorkan detail teknis ke user/LLM
        _log_err(e)
        return ""
    return phi.sanitize_phi(text or "")       # REDAKSI PII sebelum teks dipakai/dikirim ke LLM


# ============================ APP ============================================
app = FastAPI(title="CDSS AI Keperawatan", version="3.0")
# CORS: HANYA origin frontend yang sah (bukan "*"). Override via env FRONTEND_ORIGINS (pisah koma) untuk produksi.
FRONTEND_ORIGINS = list(CONFIG.frontend_origins)
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_credentials=False,
                   allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])


# ----- Peringatan dini insiden keamanan (UU PDP Pasal 46 — wajib lapor 3x24 jam) -----
_fail_times: deque = deque()
_fail_lock = threading.Lock()
_INCIDENT_WINDOW = 60       # detik
_INCIDENT_THRESHOLD = 10    # > ambang kegagalan auth/akses dalam 1 menit -> potensi insiden


def _note_access_failure(path: str, status: int) -> None:
    now = time.time()
    with _fail_lock:
        _fail_times.append(now)
        while _fail_times and _fail_times[0] < now - _INCIDENT_WINDOW:
            _fail_times.popleft()
        count = len(_fail_times)
    if count > _INCIDENT_THRESHOLD:
        safe_path = DEFAULT_OUTBOUND_POLICY.sanitize_for_log(path).text
        print(f"[SECURITY-INCIDENT][ERROR] POTENSI INSIDEN KEAMANAN: {count} request gagal (401/403/409) dalam "
              f"{_INCIDENT_WINDOW} detik terakhir (terakhir: {safe_path} -> {status}). Segera periksa; UU PDP mewajibkan "
              f"pelaporan 3x24 jam bila terbukti kebocoran.", file=sys.stderr)


@app.middleware("http")
async def security_monitor(request, call_next):
    path = request.url.path
    if (".." in path) or ("%2e" in path.lower()) or ("%2f" in path.lower()):   # percobaan manipulasi path
        safe_path = DEFAULT_OUTBOUND_POLICY.sanitize_for_log(path).text
        print(f"[SECURITY-INCIDENT][ERROR] POTENSI INSIDEN KEAMANAN: percobaan manipulasi path terdeteksi: {safe_path}", file=sys.stderr)
    _t0 = time.time()
    response = await call_next(request)
    metrics.record_request(response.status_code, (time.time() - _t0) * 1000.0)   # telemetri agregat
    if response.status_code in (401, 403, 409):
        _note_access_failure(path, response.status_code)
    return response


# ----- RASP: blokir pola berbahaya (RCE/traversal/akses file rahasia) pada URL sebelum menyentuh endpoint -----
# Catatan: hanya memindai PATH+QUERY (bukan body) agar tidak salah-tolak teks klinis & tidak membuffer upload.
_RASP_RE = re.compile(
    r"(\.\./|/etc/passwd|/etc/shadow|(?:^|[/?&=])\.env\b|\bos\.system\b|\bsubprocess\b|\b__import__\b|"
    r"\beval\s*\(|\bexec\s*\(|;\s*rm\s+-rf|\bunion\s+select\b|\bdrop\s+table\b|<script\b)", re.I)


@app.middleware("http")
async def rasp_filter(request, call_next):
    target = (request.url.path or "") + "?" + (request.url.query or "")
    if _RASP_RE.search(target):
        safe_path = DEFAULT_OUTBOUND_POLICY.sanitize_for_log(request.url.path).text
        print(f"[SECURITY-INCIDENT][ERROR] RASP memblokir pola berbahaya pada URL: {safe_path}", file=sys.stderr)
        return JSONResponse({"status": "error", "pesan": "Permintaan ditolak."}, status_code=403)
    return await call_next(request)


# Muat basis pengetahuan saat modul di-import (robust: tidak bergantung pada event startup).
muat_data()
_ledger_ok, _ledger_n = verify_audit_chain()   # verifikasi integritas ledger lokal saat start
print(f"[audit] ledger {'OK' if _ledger_ok else 'RUSAK/TAMPERED!'} ({_ledger_n} entri)")
_dsec, _dnew = director.ensure_secret()
if _dnew:   # cetak URI enrollment MFA HANYA sekali saat secret pertama dibuat (akses konsol server-only)
    print("[director] Enrollment MFA — pindai ke aplikasi authenticator:", director.otpauth_uri())
if harvester.start(audit_log, interval=CONFIG.harvest_interval_sec, topics=CONFIG.harvest_topics):
    print("[harvester] Knowledge Harvester aktif (interval mingguan, menghangatkan cache jurnal RAG).")


@app.get("/")
def root():
    return {"app": "CDSS AI Keperawatan", "status": "aktif", "versi": "3.0"}


@app.get("/capabilities")
def capabilities():
    return build_capabilities(CONFIG)


@app.get("/status")
def status(authorization: Optional[str] = Header(None)):
    if not resolve_key(authorization, ""):   # lockdown: butuh kunci (anti-enumerasi anonim) — S7
        return JSONResponse({"status": "error", "pesan": "Token API Habis"}, status_code=401)
    detail = {k: f"{len(v)} entri" for k, v in DATA.items()}
    if not detail:
        detail = {"basis_pengetahuan": "kosong"}
    return {"status": "aktif", "detail": detail, "providers": PROVIDERS, **memory.stats(), **ebp.stats()}


def _session_invalid():
    return JSONResponse({"status": "error", "pesan": "SESSION_INVALID"}, status_code=409)


def _unavailable(capability: str, status_code: int = 503, extra: Optional[dict] = None):
    reason = capability_reason(capability, CONFIG)
    payload = {
        "status": "error",
        "capability": capability,
        "enabled": False,
        "app_mode": CONFIG.app_mode,
        "safety_notice": SAFETY_NOTICE,
        "reason": reason,
        "pesan": f"Capability temporarily unavailable in secure sandbox mode: {reason}",
    }
    if extra:
        payload.update(extra)
    return JSONResponse(payload, status_code=status_code)


def _blocked_llm_capability(agent: str) -> Optional[str]:
    a = (agent or "analisis").lower()
    if a == "referensi" and not capability_enabled("ebp_external_search", CONFIG):
        return "ebp_external_search"
    if a == "pathway" and not capability_enabled("mermaid_pathway_rendering", CONFIG):
        return "mermaid_pathway_rendering"
    if not capability_enabled("external_llm", CONFIG):
        return "external_llm"
    return None


@app.post("/session")
def new_session():
    """Terbitkan session_id kriptografis (CSPRNG, 256-bit). Frontend WAJIB memakai ID ini —
    klien DILARANG membuat session_id sendiri (menutup tebak-ID & kebocoran memori lintas pengguna)."""
    return {"status": "sukses", "session_id": SESI.issue()}


# ----- Dasbor Eksekutif Direktur (rute SAH, dijaga MFA/TOTP — bukan backdoor) -----
def _director_token(authorization: Optional[str]) -> str:
    a = (authorization or "").strip()
    return a[7:].strip() if a.lower().startswith("bearer ") else ""


@app.post("/director/login")
def director_login(code: str = Form("")):
    if not director.verify_totp(code):
        return JSONResponse({"status": "error", "pesan": "Kode MFA tidak valid."}, status_code=401)
    audit_log("director", "DirectorLogin", "Success")
    return {"status": "sukses", "director_token": director.issue_token(), "ttl_s": director._TOKEN_TTL}


@app.get("/director/enroll")
def director_enroll(token: str = ""):
    """Ambil otpauth:// URI untuk enrollment MFA — HANYA bila env DIRECTOR_BOOTSTRAP cocok (akses server-only)."""
    boot = CONFIG.director_bootstrap
    if not boot or token != boot:
        return JSONResponse({"status": "error", "pesan": "Akses ditolak."}, status_code=403)
    return {"status": "sukses", "otpauth_uri": director.otpauth_uri()}


@app.get("/director/metrics")
def director_metrics(authorization: Optional[str] = Header(None)):
    if not director.valid_token(_director_token(authorization)):
        return JSONResponse({"status": "error", "pesan": "Sesi direktur tidak valid."}, status_code=401)
    snap = metrics.snapshot()
    snap["status"] = "sukses"
    snap["knowledge"] = ebp.stats()
    return snap


# ----- chat (non-stream) -----------------------------------------------------
@app.post("/chat")
def chat(provider: str = Form(...), api_key: str = Form(""), model: str = Form(...),
         framework: str = Form("3S"), session_id: str = Form("default"), tier: str = Form("medium"),
         agent: str = Form("analisis"),
         pertanyaan: str = Form(...), authorization: Optional[str] = Header(None)):
    key = resolve_key(authorization, api_key)
    if not key:
        return JSONResponse({"status": "error", "pesan": "Token API Habis"}, status_code=401)
    if not SESI.valid(session_id):
        return _session_invalid()
    if not (pertanyaan or "").strip():
        return JSONResponse({"status": "error", "pesan": "Pertanyaan kosong."}, status_code=400)
    blocked = _blocked_llm_capability(agent)
    if blocked:
        return _unavailable(blocked)
    registry_status, missing_registries = _clinical_registry_block(framework)
    if _requires_clinical_registry(agent, pertanyaan) and registry_status:
        ans, meta = _registry_abstention_answer(framework, registry_status, missing_registries)
        return _clinical_payload({"status": "sukses", "jawaban": ans}, meta)
    if not framework_available(framework):
        ans, meta = _registry_unavailable_answer(framework)
        return _clinical_payload({"status": "sukses", "jawaban": ans}, meta)
    try:
        llm = get_llm(provider, model, key)
        safe_question = _external_safe_text(pertanyaan)
        extra = ebp.retrieve_context(llm, safe_question) if (agent or "").lower() == "referensi" else ""   # jurnal NYATA
        msgs = build_messages(framework, session_id, pertanyaan, tier, agent, extra)
        ans = agents.orchestrate_answer(llm, msgs, safe_question, tier)   # kedalaman sesuai tier (flash/medium/pro)
        clinical_meta = None
        if (agent or "analisis").lower() == "analisis" and not is_casual(pertanyaan):
            ans, clinical_meta = _validate_clinical_answer(ans, framework, safe_question)
        elif (agent or "analisis").lower() == "analisis":
            ans = maybe_degrade_note(framework, ans)
            ans = _browser_safe_text(ans)   # redaksi PII pada OUTPUT (jaring pengaman akhir)
        else:
            ans = _browser_safe_text(ans)
        SESI.add(session_id, "user", safe_question)
        SESI.add(session_id, "assistant", ans)
        metrics.record_job(agent, tier, True, (len(pertanyaan) + len(ans)) // 4)
        payload = {"status": "sukses", "jawaban": ans}
        return _clinical_payload(payload, clinical_meta)
    except Exception as e:  # noqa
        code, pesan = err_status(e)
        return JSONResponse({"status": "error", "pesan": pesan}, status_code=code)


# ----- chat streaming (typewriter) ------------------------------------------
@app.post("/chat_stream")
def chat_stream(provider: str = Form(...), api_key: str = Form(""), model: str = Form(...),
                framework: str = Form("3S"), session_id: str = Form("default"), tier: str = Form("medium"),
                agent: str = Form("analisis"),
                pertanyaan: str = Form(...), authorization: Optional[str] = Header(None)):
    key = resolve_key(authorization, api_key)
    if not key:
        return JSONResponse({"status": "error", "pesan": "Token API Habis"}, status_code=401)
    if not SESI.valid(session_id):
        return _session_invalid()
    if not (pertanyaan or "").strip():
        return JSONResponse({"status": "error", "pesan": "Pertanyaan kosong."}, status_code=400)
    blocked = _blocked_llm_capability(agent)
    if blocked:
        return _unavailable(blocked)
    registry_status, missing_registries = _clinical_registry_block(framework)
    if _requires_clinical_registry(agent, pertanyaan) and registry_status:
        ans, meta = _registry_abstention_answer(framework, registry_status, missing_registries)
        return StreamingResponse(iter([ans]), media_type="text/plain; charset=utf-8", headers=_stream_clinical_headers(meta))
    if not framework_available(framework):
        ans, meta = _registry_unavailable_answer(framework)
        return StreamingResponse(iter([ans]), media_type="text/plain; charset=utf-8", headers=_stream_clinical_headers(meta))

    # Mulai di sini agar error auth/kuota tertangkap SEBELUM body 200 terkirim.
    tier_l = (tier or "medium").lower()
    casual = is_casual(pertanyaan)                  # sapaan/obrolan singkat -> jalur stream cepat (1 panggilan), tanpa orkestrasi/EBP
    try:
        clinical_meta = None
        llm = get_llm(provider, model, key)
        safe_question = _external_safe_text(pertanyaan)
        extra = ebp.retrieve_context(llm, safe_question) if ((agent or "").lower() == "referensi" and not casual) else ""   # jurnal NYATA
        msgs = build_messages(framework, session_id, pertanyaan, tier, agent, extra)
        effective_tier = "flash" if casual else tier_l
        precomputed = agents.orchestrate_answer(llm, msgs, safe_question, effective_tier)
        if (agent or "analisis").lower() == "analisis" and not casual:
            precomputed, clinical_meta = _validate_clinical_answer(precomputed, framework, safe_question)
        elif (agent or "analisis").lower() == "analisis":
            precomputed = maybe_degrade_note(framework, precomputed)
            precomputed = _browser_safe_text(precomputed)
        else:
            precomputed = _browser_safe_text(precomputed)
    except Exception as e:  # noqa
        code, pesan = err_status(e)
        return JSONResponse({"status": "error", "pesan": pesan}, status_code=code)

    def gen():
        full = precomputed or ""
        for i in range(0, len(full), 120):
            yield bersihkan_stream(full[i:i + 120])
        SESI.add(session_id, "user", safe_question)
        SESI.add(session_id, "assistant", _browser_safe_text(bersihkan(full)))
        metrics.record_job(agent, tier, True, (len(pertanyaan) + len(full)) // 4)

    # Header anti-buffering agar token mengalir real-time (tanpa ditahan proxy/uvicorn).
    return StreamingResponse(
        gen(), media_type="text/plain; charset=utf-8",
        headers=_stream_clinical_headers(clinical_meta),
    )


# ----- analisis multi-agen (swarm) ------------------------------------------
@app.post("/analisis_multi")
def analisis_multi(provider: str = Form(...), api_key: str = Form(""), model: str = Form(...),
                   framework: str = Form("3S"), session_id: str = Form("default"), tier: str = Form("medium"),
                   agent: str = Form("analisis"), consent: str = Form(""),
                   gejala: str = Form(""),
                   file_dokumen: Optional[UploadFile] = File(None),
                   file_foto: Optional[UploadFile] = File(None),
                   authorization: Optional[str] = Header(None)):
    key = resolve_key(authorization, api_key)
    if not key:
        return JSONResponse({"status": "error", "pesan": "Token API Habis"}, status_code=401)
    if not SESI.valid(session_id):
        return _session_invalid()
    if _too_big(file_dokumen) or _too_big(file_foto):
        audit_log(session_id, "Upload", "Fail(TooLarge)")
        return JSONResponse({"status": "error", "pesan": "Ukuran file melebihi batas 10MB."}, status_code=413)
    if (consent or "").strip().lower() in ("true", "1"):   # CONSENT LOGGING (UU PDP Pasal 20/22)
        audit_log(session_id, "Consent", "Granted")
    if file_foto is not None and not capability_enabled("clinical_photo_analysis", CONFIG):
        audit_log(session_id, "PhotoAnalysis", "Unavailable")
        return _unavailable("clinical_photo_analysis")
    blocked = _blocked_llm_capability(agent)
    if blocked:
        return _unavailable(blocked)

    cmd = (gejala or "").strip()
    doc = extract_text(file_dokumen)
    doc_block = ("\n\n<dokumen_pasien>\n" + doc + "\n</dokumen_pasien>") if doc else ""   # isolasi anti-injeksi (T4)
    if file_foto is not None:
        return _unavailable("clinical_photo_analysis")
    if not (cmd or doc_block.strip()):
        return JSONResponse({"status": "error", "pesan": "Tidak ada data untuk dianalisis."}, status_code=400)
    if not cmd:
        SESI.add(session_id, "user", _external_safe_text("[Dokumen rekam medis diunggah]" + doc_block))
        SESI.add(session_id, "assistant", DOC_RECEIVED)
        audit_log(session_id, "Upload", "Success")
        return {"status": "sukses", "hasil": DOC_RECEIVED}
    registry_status, missing_registries = _clinical_registry_block(framework)
    if _requires_clinical_registry(agent, cmd + doc_block) and registry_status:
        hasil, meta = _registry_abstention_answer(framework, registry_status, missing_registries)
        return _clinical_payload({"status": "sukses", "hasil": hasil}, meta)
    if not framework_available(framework):
        hasil, meta = _registry_unavailable_answer(framework)
        return _clinical_payload({"status": "sukses", "hasil": hasil}, meta)
    try:
        llm = get_llm(provider, model, key)
        safe_case = _external_safe_text(cmd + doc_block)
        extra = ebp.retrieve_context(llm, safe_case) if (agent or "").lower() == "referensi" else ""
        # file + perintah spesifik; kedalaman multi-agen mengikuti tier (flash/medium/pro).
        msgs = build_messages(framework, session_id, cmd + doc_block, tier, agent, extra)
        hasil = agents.orchestrate_answer(llm, msgs, safe_case, tier)
        clinical_meta = None
        if (agent or "analisis").lower() == "analisis":
            hasil, clinical_meta = _validate_clinical_answer(hasil, framework, safe_case)
        else:
            hasil = _browser_safe_text(hasil)   # redaksi PII pada OUTPUT
        SESI.add(session_id, "user", _external_safe_text(cmd))
        SESI.add(session_id, "assistant", hasil)
        audit_log(session_id, "Analisis", "Success")
        metrics.record_job(agent, tier, True, (len(cmd) + len(hasil)) // 4, doc=True)
        payload = {"status": "sukses", "hasil": hasil}
        return _clinical_payload(payload, clinical_meta)
    except Exception as e:  # noqa
        audit_log(session_id, "Analisis", "Fail")
        code, pesan = err_status(e)
        return JSONResponse({"status": "error", "pesan": pesan}, status_code=code)


# ----- analisis single-agent (fallback) -------------------------------------
@app.post("/analisis")
def analisis(provider: str = Form(...), api_key: str = Form(""), model: str = Form(...),
             framework: str = Form("3S"), session_id: str = Form("default"), tier: str = Form("medium"),
             consent: str = Form(""),
             gejala: str = Form(""),
             file_dokumen: Optional[UploadFile] = File(None),
             file_foto: Optional[UploadFile] = File(None),
             authorization: Optional[str] = Header(None)):
    key = resolve_key(authorization, api_key)
    if not key:
        return JSONResponse({"status": "error", "pesan": "Token API Habis"}, status_code=401)
    if not SESI.valid(session_id):
        return _session_invalid()
    if _too_big(file_dokumen) or _too_big(file_foto):
        audit_log(session_id, "Upload", "Fail(TooLarge)")
        return JSONResponse({"status": "error", "pesan": "Ukuran file melebihi batas 10MB."}, status_code=413)
    if (consent or "").strip().lower() in ("true", "1"):   # CONSENT LOGGING (UU PDP Pasal 20/22)
        audit_log(session_id, "Consent", "Granted")
    if file_foto is not None and not capability_enabled("clinical_photo_analysis", CONFIG):
        audit_log(session_id, "PhotoAnalysis", "Unavailable")
        return _unavailable("clinical_photo_analysis")
    blocked = _blocked_llm_capability("analisis")
    if blocked:
        return _unavailable(blocked)
    registry_status, missing_registries = _clinical_registry_block(framework)
    if registry_status:
        hasil, meta = _registry_abstention_answer(framework, registry_status, missing_registries)
        return _clinical_payload({"status": "sukses", "hasil": hasil}, meta)
    if not framework_available(framework):
        hasil, meta = _registry_unavailable_answer(framework)
        return _clinical_payload({"status": "sukses", "hasil": hasil}, meta)
    doc = extract_text(file_dokumen)
    data = (gejala or "").strip()
    if doc:
        data += ("\n\n<dokumen_pasien>\n" + doc + "\n</dokumen_pasien>")   # isolasi anti-injeksi (T4)
    if file_foto is not None:
        return _unavailable("clinical_photo_analysis")
    data = data.strip()
    if not data:
        return JSONResponse({"status": "error", "pesan": "Tidak ada data untuk dianalisis."}, status_code=400)
    konteks = bangun_konteks(framework, data)
    koreksi = (memory.recall_block(framework, data, session_id) or "") + books_note(framework)   # isolasi per-sesi + degradasi anggun
    try:
        llm = get_llm(provider, model, key)
        raw_hasil = bersihkan(agents.single_askep(llm, framework, data, konteks, koreksi, iq_text(tier)))
        hasil, clinical_meta = _validate_clinical_answer(raw_hasil, framework, _external_safe_text(data))
        SESI.add(session_id, "user", _external_safe_text(gejala.strip()) if gejala.strip() else "[analisis rekam medis terlampir]")
        SESI.add(session_id, "assistant", hasil)
        audit_log(session_id, "Analisis", "Success")
        metrics.record_job("analisis", tier, True, (len(data) + len(hasil)) // 4, doc=True)
        return _clinical_payload({"status": "sukses", "hasil": hasil}, clinical_meta)
    except Exception as e:  # noqa
        audit_log(session_id, "Analisis", "Fail")
        code, pesan = err_status(e)
        return JSONResponse({"status": "error", "pesan": pesan}, status_code=code)


# ----- clinical pathway (background / on-demand) ----------------------------
@app.post("/pathway")
def pathway_ep(provider: str = Form(...), api_key: str = Form(""), model: str = Form(...),
               framework: str = Form("3S"), session_id: str = Form("default"),
               gejala: str = Form(""), authorization: Optional[str] = Header(None)):
    key = resolve_key(authorization, api_key)
    if not key:
        return JSONResponse({"status": "error", "pesan": "Token API Habis", "mermaid": ""}, status_code=401)
    if not SESI.valid(session_id):
        return _session_invalid()
    if not capability_enabled("mermaid_pathway_rendering", CONFIG):
        return _unavailable("mermaid_pathway_rendering", extra={"mermaid": ""})
    if not capability_enabled("external_llm", CONFIG):
        return _unavailable("external_llm", extra={"mermaid": ""})
    if not framework_available(framework):
        return {"status": "error", "pesan": REF_REFUSAL, "mermaid": ""}
    hist = SESI.history(session_id)
    base = "\n".join((("Perawat" if r == "user" else "Sistem") + ": " + c) for r, c in hist[-6:])
    konteks = (base + (("\n\n" + gejala) if gejala.strip() else "")).strip() or gejala.strip()
    if not konteks:
        return {"status": "error", "pesan": "Tidak ada konteks untuk membuat pathway.", "mermaid": ""}
    try:
        llm = get_llm(provider, model, key)
        code = extract_mermaid(_browser_safe_text(agents.gen_pathway(llm, framework, konteks)))
        return {"status": "sukses", "mermaid": code}
    except Exception as e:  # noqa
        c, pesan = err_status(e)
        return JSONResponse({"status": "error", "pesan": pesan, "mermaid": ""}, status_code=c)


# ----- referensi (Referensi tab) --------------------------------------------
@app.get("/daftar/{buku}")
def daftar(buku: str, session_id: str = "", authorization: Optional[str] = Header(None)):
    if not resolve_key(authorization, "") or not SESI.valid(session_id):   # lockdown enumerasi (S7)
        return JSONResponse({"status": "error", "pesan": "Akses ditolak."}, status_code=401)
    data = DATA.get(buku.upper())
    if not data:
        return {"status": "error", "pesan": "Buku tidak tersedia", "buku": buku.upper(), "entri": []}
    return {"status": "sukses", "buku": buku.upper(), "jumlah": len(data),
            "entri": [{"kode": e.get("kode"), "nama": e.get("nama"),
                       "kategori": e.get("kategori"), "subkategori": e.get("subkategori")} for e in data]}


@app.get("/entri/{buku}/{kode}")
def entri(buku: str, kode: str, session_id: str = "", authorization: Optional[str] = Header(None)):
    if not resolve_key(authorization, "") or not SESI.valid(session_id):   # lockdown enumerasi (S7)
        return JSONResponse({"status": "error", "pesan": "Akses ditolak."}, status_code=401)
    for e in (DATA.get(buku.upper()) or []):
        if str(e.get("kode", "")).lower() == kode.lower():
            return {"status": "sukses", "entri": e}
    return {"status": "error", "pesan": "Entri tidak ditemukan"}


# ----- reset & feedback ------------------------------------------------------
@app.post("/reset")
def reset(session_id: str = Form("default")):
    SESI.reset(session_id)
    return {"status": "ok"}


@app.post("/delete_my_data")
def delete_my_data(session_id: str = Form(""), authorization: Optional[str] = Header(None)):
    """Hak Hapus Data / Right to be Forgotten (UU PDP Pasal 8 & 43): musnahkan PERMANEN riwayat
    percakapan (PHI) + feedback milik session_id ini. session_id CSPRNG = bukti kepemilikan."""
    if not SESI.valid(session_id):
        return _session_invalid()
    SESI.reset(session_id)                         # hapus riwayat percakapan + invalidasi sesi
    removed = memory.purge_session(session_id)     # hapus seluruh feedback milik sesi ini
    crypto_store.dek_destroy(session_id)           # CRYPTO-SHRED: musnahkan DEK -> data sisa jadi sampah kriptografis
    audit_log(session_id, "DeleteMyData", "Success")
    return {"status": "ok", "feedback_dihapus": removed}


@app.post("/feedback")
def feedback(framework: str = Form("3S"), session_id: str = Form(""), pertanyaan: str = Form(""),
             jawaban: str = Form(""), rating: str = Form("up"), koreksi: str = Form("")):
    if not SESI.valid(session_id):
        return _session_invalid()
    memory.store_feedback(
        framework,
        _external_safe_text(pertanyaan),
        _browser_safe_text(jawaban),
        rating,
        _external_safe_text(koreksi),
        session_id,
    )   # diikat ke sesi (anti poisoning lintas-user)
    audit_log(session_id, "Feedback", "Success")
    return {"status": "ok", **memory.stats()}


if __name__ == "__main__":
    import uvicorn
    muat_data()
    uvicorn.run(app, host="127.0.0.1", port=8000)
