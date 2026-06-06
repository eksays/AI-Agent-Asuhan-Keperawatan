from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import hashlib
import hmac
import re
import secrets

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

REDACT = "[REDACTED]"
PSEUDONYM_PREFIX = "PATIENT"


@dataclass(frozen=True)
class Detection:
    kind: str
    value: str


@dataclass(frozen=True)
class SanitizedText:
    text: str
    detections: tuple[Detection, ...] = field(default_factory=tuple)

    @property
    def found_sensitive_data(self) -> bool:
        return bool(self.detections)


class OutboundPolicyError(RuntimeError):
    pass


class OutboundDataPolicy:
    """Deterministic PHI containment for outbound boundaries.

    This is a conservative sandbox control, not a completeness claim. It catches
    common patient identifiers and fails closed if high-risk identifiers remain.
    """

    _email = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
    _phone = re.compile(r"(?<!\w)(?:\+?62[ \t-]?8[1-9]|0[ \t-]?8[1-9]|\(0?8[1-9]\d?\))(?:[ \t().-]?\d){5,11}(?!\w)")
    _nik = re.compile(r"(?i)\b(?:NIK|No\.?[ \t]*KTP|KTP)[ \t]*[:#-]?[ \t]*([0-9][0-9 .-]{12,20}[0-9])")
    _bpjs = re.compile(r"(?i)\b(?:No\.?[ \t]*)?BPJS[ \t]*[:#-]?[ \t]*([0-9][0-9 .-]{8,18}[0-9])")
    _mrn = re.compile(r"(?i)\b(?:MRN|No\.?[ \t]*RM|Rekam[ \t]*Medis|RM)[ \t]*[:#-]?[ \t]*([A-Z]{0,4}[- ]?[0-9][A-Z0-9 ./-]{4,28}[A-Z]?)")
    _long_id = re.compile(r"(?<!\w)(?:[A-Z]{1,6}[- ])?\d(?:[ ./-]?\d){9,}(?:[- ]?[A-Z])?(?!\w)", re.I)
    _name_labeled = re.compile(
        r"(?im)\b(Nama(?:[ \t]+(?:pasien|lengkap|klien|ibu|ayah|keluarga|kontak))?|Pasien|Klien|Kontak[ \t]+keluarga)[ \t]*[:#-]?[ \t]*"
        r"([A-Z][A-Za-z'`-]+(?:[ \t]+[A-Z][A-Za-z'`-]+){0,4})"
    )
    _name_embedded = re.compile(
        r"(?i)\b(?:Tn\.?|Ny\.?|Sdr\.?|Sdri\.?|An\.?|Bapak|Ibu|pasien|klien)[ \t]+"
        r"([A-Z][A-Za-z'`-]+(?:[ \t]+[A-Z][A-Za-z'`-]+){1,3})"
    )
    _address = re.compile(
        r"(?im)\b(?:Alamat|Domisili|Tinggal\s+di)\s*[:#-]?\s*"
        r"([^\n,;]*(?:Jalan|Jl\.?|Gang|Gg\.?|No\.?|RT\.?|RW\.?|Kel\.?|Kec\.?|Bandung|Jakarta)[^\n]*)"
    )
    _dob = re.compile(
        r"(?im)\b(?:Tanggal[ \t]+lahir|Tgl\.?[ \t]*lahir|DOB|Date[ \t]+of[ \t]+birth)[ \t]*[:#-]?[ \t]*"
        r"([0-9]{1,2}[ /-](?:[A-Za-z]+|[0-9]{1,2})[ /-][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})"
    )
    _danger_after_sanitize = (
        _email,
        _phone,
        _nik,
        _bpjs,
        _mrn,
        _long_id,
        _dob,
    )
    _stopwords = {
        "nama", "pasien", "klien", "alamat", "jalan", "nomor", "telepon", "email", "tanggal", "lahir",
        "dengan", "pada", "yang", "dan", "atau", "untuk", "dari", "serta", "adalah", "dalam", "karena",
        "tidak", "belum", "sudah", "budi", "santoso", "merdeka", "bandung", "example", "patient",
        "redacted", "patient_name", "patient_address", "patient_dob", "patient_id", "name", "phone",
        "nik", "bpjs", "mrn", "medical", "record", "number", "address", "dob",
    }
    _name_break_words = {
        "datang", "dengan", "sesak", "nyeri", "demam", "batuk", "keluhan", "mengeluh", "dirawat",
        "dibawa", "ke", "rs", "rumah", "sakit", "usia", "umur", "tahun", "td", "rr", "spo2",
    }

    def __init__(self) -> None:
        self._pseudonym_key = secrets.token_bytes(32)

    def _pseudonym_for_name(self, raw: str) -> str:
        normalized = " ".join((raw or "").split()).lower()
        if not normalized:
            return f"[{PSEUDONYM_PREFIX}_NAME]"
        digest = hmac.new(self._pseudonym_key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()[:8]
        return f"[{PSEUDONYM_PREFIX}_NAME_{digest}]"

    def _split_name_candidate(self, raw: str) -> tuple[str, str]:
        parts = (raw or "").split()
        keep: list[str] = []
        rest: list[str] = []
        for part in parts:
            if rest or part.strip(".,;:").lower() in self._name_break_words:
                rest.append(part)
            else:
                keep.append(part)
        return " ".join(keep), " ".join(rest)

    @staticmethod
    def _normalize(text: str) -> str:
        return "\n".join((text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"))

    def _replace(self, text: str, pattern: re.Pattern, kind: str, repl: str, detections: list[Detection]) -> str:
        def sub(match: re.Match) -> str:
            value = match.group(match.lastindex or 0)
            detections.append(Detection(kind, " ".join(str(value).split())))
            if match.lastindex and match.lastindex >= 1:
                return match.group(0).replace(match.group(match.lastindex), repl)
            return repl

        return pattern.sub(sub, text)

    def sanitize_for_external_provider(self, text: str) -> SanitizedText:
        detections: list[Detection] = []
        t = self._normalize(text)

        def name_label_sub(match: re.Match) -> str:
            label = match.group(1)
            name, rest = self._split_name_candidate(match.group(2))
            if not name:
                return match.group(0)
            detections.append(Detection("patient_name", " ".join(name.split())))
            suffix = f" {rest}" if rest else ""
            return f"{label}: {self._pseudonym_for_name(name)}{suffix}"

        def embedded_name_sub(match: re.Match) -> str:
            full = match.group(0)
            name, _rest = self._split_name_candidate(match.group(1))
            if not name:
                return full
            detections.append(Detection("embedded_name", " ".join(name.split())))
            return full.replace(name, self._pseudonym_for_name(name))

        t = self._name_labeled.sub(name_label_sub, t)
        t = self._name_embedded.sub(embedded_name_sub, t)
        t = self._replace(t, self._email, "email", "[PATIENT_EMAIL]", detections)
        t = self._replace(t, self._phone, "phone", "[PATIENT_PHONE]", detections)
        t = self._replace(t, self._address, "address", "[PATIENT_ADDRESS]", detections)
        t = self._replace(t, self._dob, "date_of_birth", "[PATIENT_DOB]", detections)
        t = self._replace(t, self._nik, "nik", "[PATIENT_NIK]", detections)
        t = self._replace(t, self._bpjs, "bpjs", "[PATIENT_BPJS]", detections)
        t = self._replace(t, self._mrn, "medical_record_number", "[PATIENT_MRN]", detections)
        t = self._replace(t, self._long_id, "long_identifier", "[PATIENT_ID]", detections)
        result = SanitizedText(t, tuple(detections))
        self.assert_safe_for_external_provider(result.text)
        return result

    def assert_safe_for_external_provider(self, text: str) -> None:
        remaining = []
        for pattern in self._danger_after_sanitize:
            if pattern.search(text or ""):
                remaining.append(pattern.pattern[:40])
        if remaining:
            raise OutboundPolicyError("High-risk identifier remained after outbound sanitization.")

    def sanitize_for_log(self, text: str) -> SanitizedText:
        try:
            return self.sanitize_for_external_provider(text)
        except OutboundPolicyError:
            return SanitizedText(REDACT, (Detection("unsafe_log_text", REDACT),))

    def sanitize_for_browser(self, text: str) -> SanitizedText:
        return self.sanitize_for_external_provider(text)

    def sanitize_messages_for_external_provider(self, messages: Sequence) -> list:
        sanitized = []
        for msg in messages or []:
            content = self.sanitize_for_external_provider(str(getattr(msg, "content", "") or "")).text
            if isinstance(msg, SystemMessage):
                sanitized.append(SystemMessage(content=content))
            elif isinstance(msg, AIMessage):
                sanitized.append(AIMessage(content=content))
            else:
                sanitized.append(HumanMessage(content=content))
        return sanitized

    def deidentified_concept_query(self, text: str, max_terms: int = 8) -> SanitizedText:
        sanitized = self.sanitize_for_external_provider(text)
        terms: list[str] = []
        for token in re.findall(r"[A-Za-z]{4,}", sanitized.text.lower()):
            if token in self._stopwords or token.startswith("patient"):
                continue
            if token not in terms:
                terms.append(token)
        if not terms:
            terms = ["nursing", "care"]
        query = " ".join(terms[:max_terms] + ["nursing", "intervention", "evidence"])
        self.assert_safe_for_external_provider(query)
        return SanitizedText(query, sanitized.detections)


class SafeLLM:
    def __init__(self, raw_llm, policy: OutboundDataPolicy | None = None) -> None:
        self._raw_llm = raw_llm
        self.policy = policy or DEFAULT_OUTBOUND_POLICY

    def invoke(self, messages, *args, **kwargs):
        if isinstance(messages, str):
            safe_messages = self.policy.sanitize_for_external_provider(messages).text
        else:
            safe_messages = self.policy.sanitize_messages_for_external_provider(messages)
        return self._raw_llm.invoke(safe_messages, *args, **kwargs)

    def stream(self, *_args, **_kwargs):
        raise OutboundPolicyError("Direct external token streaming is disabled; precompute, sanitize, then chunk output.")

    def __getattr__(self, name: str):
        if name == "raw_llm":
            raise AttributeError("Raw LLM access is not exposed; use the SafeLLM boundary.")
        return getattr(self._raw_llm, name)


DEFAULT_OUTBOUND_POLICY = OutboundDataPolicy()


def wrap_llm(raw_llm, policy: OutboundDataPolicy | None = None) -> SafeLLM:
    return SafeLLM(raw_llm, policy or DEFAULT_OUTBOUND_POLICY)
