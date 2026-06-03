"""
Redaksi PII/PHI deterministik SEBELUM teks dokumen dikirim ke LLM pihak ketiga (anti-kebocoran identitas pasien).
Mengganti pola sensitif menjadi [REDACTED]: nomor telepon Indonesia, angka panjang (NIK 16 digit / no. rekam medis),
dan field "Nama:".
"""
from __future__ import annotations
import re

_PHONE = re.compile(r"(?:\+62|62|0)8[1-9][0-9]{6,11}\b")     # nomor HP Indonesia
_LONGNUM = re.compile(r"\b\d{10,}\b")                          # NIK (16), no. rekam medis, dsb. (>=10 digit)
_NAMA_LINE = re.compile(r"(?im)^([ \t]*Nama(?:\s+(?:Pasien|Lengkap|Klien))?\s*[:\-])[ \t]*\S.*$")
REDACT = "[REDACTED]"


def sanitize_phi(text: str) -> str:
    """Redaksi PII pada teks (mis. isi rekam medis) sebelum dikirim ke LLM. Aman bila text kosong/None."""
    if not text:
        return text
    t = _PHONE.sub(REDACT, text)
    t = _LONGNUM.sub(REDACT, t)
    t = _NAMA_LINE.sub(r"\1 " + REDACT, t)
    return t
