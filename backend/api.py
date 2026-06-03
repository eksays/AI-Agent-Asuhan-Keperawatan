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
import metrics
import director
import harvester
from agents import bersihkan, bersihkan_stream, GUARDRAILS

# ============================ KONFIGURASI ====================================
BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data_terstruktur")

# ----- Keamanan: batas upload, sandbox parsing, audit log, sanitasi error -----
MAX_UPLOAD = 10 * 1024 * 1024     # 10 MB — divalidasi di BACKEND (jangan percaya frontend)
_PARSE_TIMEOUT = 20               # detik — sandbox parsing PDF/DOCX agar file jebakan tak menggantung server
_LEDGER = os.path.join(BASE, "audit_ledger.jsonl")   # WORM hash-chain audit ledger (tamper-evident)
_ledger_lock = threading.Lock()
_GENESIS = "0" * 64
_last_hash = None


def _log_err(e) -> None:
    """Catat detail teknis HANYA ke konsol server internal — jangan pernah dikirim ke user/LLM."""
    try:
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
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
    """Audit mediko-legal WORM (hash-chain, tamper-evident). Hanya metadata (tanpa PHI); session_id disamarkan jadi hash."""
    try:
        with _ledger_lock:
            global _last_hash
            prev = _ledger_last_hash()
            ts = datetime.datetime.utcnow().isoformat() + "Z"
            sid = _sid_tag(session_id)
            cur = _entry_hash(prev, ts, sid, action, status)
            rec = {"prev_hash": prev, "timestamp": ts, "sid": sid, "action": action, "status": status, "current_hash": cur}
            with open(_LEDGER, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            _last_hash = cur
    except Exception:
        pass


def verify_audit_chain():
    """Verifikasi integritas rantai audit (WORM). Return (ok, jumlah). Alarm bila ada entri yang diubah/dirusak."""
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
    "shopee": os.environ.get("SHOPEE_BASE_URL", "https://openrouter.ai/api/v1"),
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


def bangun_konteks(framework: str, query: str, k: int = 5) -> str:
    """RAG token-diet: hanya menyuntik entri RELEVAN dari tiap buku referensi yang TERMUAT
    (bukan seluruh file JSON). Otomatis mencakup SDKI/SLKI/SIKI atau NANDA/NOC/NIC bila ada."""
    q = _tok(query)
    if not q:
        return ""
    blocks: List[str] = []
    for buku in FRAMEWORK_BOOKS.get(framework, ()):
        data = DATA.get(buku) or []
        if not data:
            continue
        scored: List[Tuple[int, dict]] = []
        for e in data:
            sc = len(q & _tok(_entry_text(e)))
            if sc:
                scored.append((sc, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:k]
        if not top:
            continue
        lines = [f"REFERENSI {buku} RELEVAN (pakai kode & nama persis seperti ini, sertakan 'Sumber: {buku}'):"]
        for _, e in top:
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
def get_llm(provider: str, model: str, api_key: str, temperature: float = 0.0):
    provider = (provider or "").lower().strip()
    if provider == "claude":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=api_key, temperature=temperature, max_tokens=4096)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=temperature, max_output_tokens=4096)
    # OpenAI-compatible: openai / groq / xai / deepseek / mistral / together / openrouter / shopee
    from langchain_openai import ChatOpenAI
    kw = dict(model=model, api_key=api_key, temperature=temperature, max_tokens=4096)
    base = OPENAI_COMPATIBLE.get(provider)
    if base:
        kw["base_url"] = base
    return ChatOpenAI(**kw)


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

FORMAT PENULISAN (HIERARKI VERTIKAL & RAPAT):
- DILARANG menuliskan narasi proses di dalam jawaban (mis. "sedang membaca/menelaah dokumen..."). Langsung kalimat pengantar singkat lalu isi.
- Judul bagian: Heading 2 berabjad pada baris sendiri: "## A. ...", "## B. ...", "## C. ...".
- Bagian "A. Analisis Data" WAJIB disajikan sebagai TABEL Markdown dengan kolom: No. | Data Subjektif | Data Objektif | Masalah. Header kolom pertama ditulis "No." (PAKAI titik); isi kolom itu ditulis "1.", "2.", "3." (dengan titik). Setiap sel Data Subjektif dan Data Objektif WAJIB diakhiri tanda titik (.). Bila satu sel memuat lebih dari satu poin, beri penomoran "1.", "2.", "3." dan pisahkan antar poin dengan tag <br> di dalam sel.
- Di dalam tiap bagian gunakan DAFTAR MARKDOWN BERTINGKAT (nested ordered list): tulis penanda "1." untuk SETIAP butir dan beri INDENTASI 3 spasi untuk sub-butir di bawah induknya. SETIAP butir WAJIB pada barisnya sendiri (KE BAWAH); DILARANG menulis beberapa butir dalam satu baris (ke samping). Sistem otomatis menampilkan penanda sesuai kedalaman: 1. lalu a. lalu 1) lalu a) lalu i. Contoh:
  1. Defisit Pengetahuan (D.0111)
     1. Definisi: ...
     1. Tanda Mayor (Subjektif):
        1. Poin pertama
        1. Poin kedua
- KETERANGAN TUNGGAL: bila sebuah label/butir hanya memiliki SATU keterangan, tulis keterangan itu LANGSUNG pada baris yang SAMA setelah tanda titik dua — JANGAN dipindah ke baris baru dan JANGAN diberi penanda terpisah. Contoh BENAR: "b. Tanda Mayor (Objektif): Pasangan tampak antusias namun belum mampu menjelaskan pilihan kontrasepsi." Gunakan sub-daftar bernomor (ke bawah) HANYA bila keterangannya LEBIH dari satu.
- JANGAN memakai bullet (-, •). Sertakan KODE standar. Tulis RAPAT: maksimal SATU baris kosong antar bagian, dan JANGAN ada baris kosong berlebih sebelum kalimat penutup/pertanyaan. **Tebal** hanya untuk label penting. Pakai tabel Markdown bila membandingkan data; pada kolom nomor tabel tulis nomor dengan titik (1., 2., 3.).
{GUARDRAILS}{socratic}{books_note(framework)}
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

FORMAT JAWABAN (Markdown rapi & RAPAT, tanpa emoji, maksimal SATU baris kosong antar bagian):
- Awali SATU kalimat pengantar singkat.
- "## Jurnal yang Direkomendasikan": DAFTAR BERTINGKAT (tulis "1." untuk tiap jurnal, indentasi 3 spasi untuk sub-butir):
  1. **Judul jurnal** (nama jurnal, tahun).
  1. Ringkasan isi: 1-2 kalimat yang menyimpulkan temuan kunci dari abstrak (hasil bacaan Anda).
  1. Relevansi dengan kasus: satu kalimat.
  1. Akses: tautan Markdown [Buka jurnal] memakai URL PERSIS dari daftar.
- WAJIB diakhiri "## Ringkasan Intervensi (EBP)" berupa TABEL Markdown kolom: No. | Problem/Diagnosis | Intervensi (EBP) | Bukti dari Jurnal | Akses. Kolom No. ditulis "1.", "2." (dengan titik). Intervensi DISESUAIKAN dengan problem/diagnosis pasien; kolom Bukti merujuk temuan jurnal terkait; kolom Akses memuat tautan [Buka] ke URL jurnal.

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
    konteks = bangun_konteks(framework, pertanyaan)
    konteks = ("\n\nREFERENSI STANDAR:\n" + konteks) if konteks else ""
    if extra_ctx:
        konteks += extra_ctx
    koreksi = memory.recall_block(framework, pertanyaan, session_id) or ""   # isolasi per-sesi (anti poisoning)
    msgs = [SystemMessage(content=sys_for_agent(agent, framework, konteks, koreksi, tier) + agents.ANTI_INJECTION)]
    for role, content in SESI.history(session_id):
        msgs.append(HumanMessage(content=content) if role == "user" else AIMessage(content=content))
    msgs.append(HumanMessage(content=pertanyaan))
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
FRONTEND_ORIGINS = [o.strip() for o in os.environ.get(
    "FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
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
        print(f"[SECURITY-INCIDENT][ERROR] POTENSI INSIDEN KEAMANAN: {count} request gagal (401/403/409) dalam "
              f"{_INCIDENT_WINDOW} detik terakhir (terakhir: {path} -> {status}). Segera periksa; UU PDP mewajibkan "
              f"pelaporan 3x24 jam bila terbukti kebocoran.", file=sys.stderr)


@app.middleware("http")
async def security_monitor(request, call_next):
    path = request.url.path
    if (".." in path) or ("%2e" in path.lower()) or ("%2f" in path.lower()):   # percobaan manipulasi path
        print(f"[SECURITY-INCIDENT][ERROR] POTENSI INSIDEN KEAMANAN: percobaan manipulasi path terdeteksi: {path}", file=sys.stderr)
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
        print(f"[SECURITY-INCIDENT][ERROR] RASP memblokir pola berbahaya pada URL: {request.url.path}", file=sys.stderr)
        return JSONResponse({"status": "error", "pesan": "Permintaan ditolak."}, status_code=403)
    return await call_next(request)


# Muat basis pengetahuan saat modul di-import (robust: tidak bergantung pada event startup).
muat_data()
_ledger_ok, _ledger_n = verify_audit_chain()   # verifikasi integritas WORM ledger saat start
print(f"[audit] ledger {'OK' if _ledger_ok else 'RUSAK/TAMPERED!'} ({_ledger_n} entri)")
_dsec, _dnew = director.ensure_secret()
if _dnew:   # cetak URI enrollment MFA HANYA sekali saat secret pertama dibuat (akses konsol server-only)
    print("[director] Enrollment MFA — pindai ke aplikasi authenticator:", director.otpauth_uri())
if harvester.start(audit_log):
    print("[harvester] Knowledge Harvester aktif (interval mingguan, menghangatkan cache jurnal RAG).")


@app.get("/")
def root():
    return {"app": "CDSS AI Keperawatan", "status": "aktif", "versi": "3.0"}


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
    boot = os.environ.get("DIRECTOR_BOOTSTRAP", "")
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
    if not framework_available(framework):
        return {"status": "sukses", "jawaban": REF_REFUSAL}
    try:
        llm = get_llm(provider, model, key)
        extra = ebp.retrieve_context(llm, pertanyaan) if (agent or "").lower() == "referensi" else ""   # jurnal NYATA
        msgs = build_messages(framework, session_id, pertanyaan, tier, agent, extra)
        ans = agents.orchestrate_answer(llm, msgs, pertanyaan, tier)   # kedalaman sesuai tier (flash/medium/pro)
        if (agent or "analisis").lower() == "analisis":
            ans = maybe_degrade_note(framework, ans)
        ans = phi.sanitize_phi(ans)   # redaksi PII pada OUTPUT (jaring pengaman akhir)
        SESI.add(session_id, "user", pertanyaan)
        SESI.add(session_id, "assistant", ans)
        metrics.record_job(agent, tier, True, (len(pertanyaan) + len(ans)) // 4)
        return {"status": "sukses", "jawaban": ans}
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
    if not framework_available(framework):
        return StreamingResponse(iter([REF_REFUSAL]), media_type="text/plain; charset=utf-8")

    # Mulai di sini agar error auth/kuota tertangkap SEBELUM body 200 terkirim.
    tier_l = (tier or "medium").lower()
    try:
        llm = get_llm(provider, model, key)
        extra = ebp.retrieve_context(llm, pertanyaan) if (agent or "").lower() == "referensi" else ""   # jurnal NYATA
        msgs = build_messages(framework, session_id, pertanyaan, tier, agent, extra)
        if tier_l == "flash":                       # FLASH: 1 agen, streaming token langsung (tercepat)
            precomputed = None
            it = llm.stream(msgs)
            try:
                first = next(it)
            except StopIteration:
                first = None
        else:                                       # MEDIUM/PRO: multi-agen + review (blocking) lalu dipancarkan
            it = first = None
            precomputed = agents.orchestrate_answer(llm, msgs, pertanyaan, tier_l)
    except Exception as e:  # noqa
        code, pesan = err_status(e)
        return JSONResponse({"status": "error", "pesan": pesan}, status_code=code)

    def gen():
        acc: list[str] = []
        if tier_l == "flash":
            def emit(chunk) -> str:
                c = bersihkan_stream(getattr(chunk, "content", "") or "")   # JANGAN strip per-token
                if c:
                    acc.append(c)
                return c
            if first is not None:
                c = emit(first)
                if c:
                    yield c
            try:
                for ch in it:
                    c = emit(ch)
                    if c:
                        yield c
            except Exception:  # noqa  (stream terputus di tengah)
                pass
        else:
            text = precomputed or ""               # jawaban final hasil multi-agen -> dipancarkan bertahap
            acc.append(text)
            for i in range(0, len(text), 120):
                yield text[i:i + 120]
        full = "".join(acc)
        if (agent or "analisis").lower() == "analisis" and (not askep_refs_available(framework)) and ("Informasi Sistem" not in full) and _ASKEP_RE.search(full):
            yield DEGRADE_NOTE          # notifikasi degradasi di akhir
            full += DEGRADE_NOTE
        SESI.add(session_id, "user", pertanyaan)
        SESI.add(session_id, "assistant", phi.sanitize_phi(bersihkan(full)))
        metrics.record_job(agent, tier, True, (len(pertanyaan) + len(full)) // 4)

    # Header anti-buffering agar token mengalir real-time (tanpa ditahan proxy/uvicorn).
    return StreamingResponse(
        gen(), media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache, no-transform"},
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

    cmd = (gejala or "").strip()
    doc = extract_text(file_dokumen)
    doc_block = ("\n\n<dokumen_pasien>\n" + doc + "\n</dokumen_pasien>") if doc else ""   # isolasi anti-injeksi (T4)
    if file_foto is not None:
        doc_block += "\n[Catatan: foto rekam medis dilampirkan oleh perawat.]"
    if not (cmd or doc_block.strip()):
        return JSONResponse({"status": "error", "pesan": "Tidak ada data untuk dianalisis."}, status_code=400)
    if not framework_available(framework):
        return {"status": "sukses", "hasil": REF_REFUSAL}
    # File diunggah TANPA teks -> interaktif: simpan dokumen ke memori lalu tanya (tidak auto-analisis).
    if not cmd:
        SESI.add(session_id, "user", "[Dokumen rekam medis diunggah]" + doc_block)
        SESI.add(session_id, "assistant", DOC_RECEIVED)
        audit_log(session_id, "Upload", "Success")
        return {"status": "sukses", "hasil": DOC_RECEIVED}
    try:
        llm = get_llm(provider, model, key)
        extra = ebp.retrieve_context(llm, cmd + doc_block) if (agent or "").lower() == "referensi" else ""
        # file + perintah spesifik; kedalaman multi-agen mengikuti tier (flash/medium/pro).
        msgs = build_messages(framework, session_id, cmd + doc_block, tier, agent, extra)
        hasil = agents.orchestrate_answer(llm, msgs, cmd + doc_block, tier)
        if (agent or "analisis").lower() == "analisis":
            hasil = maybe_degrade_note(framework, hasil)
        hasil = phi.sanitize_phi(hasil)   # redaksi PII pada OUTPUT
        SESI.add(session_id, "user", cmd)
        SESI.add(session_id, "assistant", hasil)
        audit_log(session_id, "Analisis", "Success")
        metrics.record_job(agent, tier, True, (len(cmd) + len(hasil)) // 4, doc=True)
        return {"status": "sukses", "hasil": hasil}
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
    if not framework_available(framework):
        return {"status": "sukses", "hasil": REF_REFUSAL}
    doc = extract_text(file_dokumen)
    data = (gejala or "").strip()
    if doc:
        data += ("\n\n<dokumen_pasien>\n" + doc + "\n</dokumen_pasien>")   # isolasi anti-injeksi (T4)
    if file_foto is not None:
        data += "\n[Catatan: foto rekam medis dilampirkan.]"
    data = data.strip()
    if not data:
        return JSONResponse({"status": "error", "pesan": "Tidak ada data untuk dianalisis."}, status_code=400)
    konteks = bangun_konteks(framework, data)
    koreksi = (memory.recall_block(framework, data, session_id) or "") + books_note(framework)   # isolasi per-sesi + degradasi anggun
    try:
        llm = get_llm(provider, model, key)
        hasil = phi.sanitize_phi(maybe_degrade_note(framework, bersihkan(agents.single_askep(llm, framework, data, konteks, koreksi, iq_text(tier)))))
        SESI.add(session_id, "user", gejala.strip() or "[analisis rekam medis terlampir]")
        SESI.add(session_id, "assistant", hasil)
        audit_log(session_id, "Analisis", "Success")
        metrics.record_job("analisis", tier, True, (len(data) + len(hasil)) // 4, doc=True)
        return {"status": "sukses", "hasil": hasil}
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
    if not framework_available(framework):
        return {"status": "error", "pesan": REF_REFUSAL, "mermaid": ""}
    hist = SESI.history(session_id)
    base = "\n".join((("Perawat" if r == "user" else "Sistem") + ": " + c) for r, c in hist[-6:])
    konteks = (base + (("\n\n" + gejala) if gejala.strip() else "")).strip() or gejala.strip()
    if not konteks:
        return {"status": "error", "pesan": "Tidak ada konteks untuk membuat pathway.", "mermaid": ""}
    try:
        llm = get_llm(provider, model, key)
        code = extract_mermaid(agents.gen_pathway(llm, framework, konteks))
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
    memory.store_feedback(framework, pertanyaan, jawaban, rating, koreksi, session_id)   # diikat ke sesi (anti poisoning lintas-user)
    audit_log(session_id, "Feedback", "Success")
    return {"status": "ok", **memory.stats()}


if __name__ == "__main__":
    import uvicorn
    muat_data()
    uvicorn.run(app, host="127.0.0.1", port=8000)
