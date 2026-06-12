from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import ValidationError

from clinical_registry import ClinicalRegistry, normalize_registry_framework, valid_code_format
from clinical_schema import (
    ClinicalResponse,
    ClinicalValidationIssue,
    DiagnosisCandidate,
    InterventionCandidate,
    MissingClinicalData,
    OutcomeCandidate,
)


STANDARD_MAP = {
    "3S": {"diagnosis": "SDKI", "outcome": "SLKI", "intervention": "SIKI"},
    "3N": {"diagnosis": "NANDA", "outcome": "NOC", "intervention": "NIC"},
}

ALLOWED_EVIDENCE_SOURCES = {
    "patient_record",
    "patient_input",
    "uploaded_document",
    "nurse_entered_data",
    "clinical_observation",
}

MAX_CLINICAL_RESPONSE_BYTES = 64 * 1024
MAX_CLINICAL_RESPONSE_DEPTH = 12

STOPWORDS = {
    "ada",
    "dan",
    "dengan",
    "dalam",
    "dari",
    "hasil",
    "ini",
    "itu",
    "pada",
    "pasien",
    "terdapat",
    "tidak",
    "tanpa",
    "yang",
}

NEGATION_TERMS = (
    "tidak",
    "tanpa",
    "negatif",
    "menyangkal",
    "bukan",
)

CLINICAL_CONCEPTS = {
    "batuk": ("batuk",),
    "demam": ("demam", "febris"),
    "nyeri_dada": ("nyeri dada",),
    "ronki": ("ronki", "rhonki", "ronkhi"),
    "sesak": ("sesak", "dispnea", "dyspnea", "napas pendek"),
    "sianosis": ("sianosis",),
    "sputum": ("sputum", "dahak"),
}

MEASUREMENT_PATTERNS = {
    "rr": re.compile(r"\b(?:rr|respirasi|frekuensi\s+napas)\s*[:=]?\s*(\d{1,3})\s*(?:x\s*/\s*menit|kali\s*/\s*menit|/\s*menit)?\b", re.I),
    "spo2": re.compile(r"\bspo\s*2\s*[:=]?\s*(\d{1,3})\s*%?\b", re.I),
    "nadi": re.compile(r"\b(?:nadi|hr)\s*[:=]?\s*(\d{1,3})\s*(?:x\s*/\s*menit|/\s*menit)?\b", re.I),
    "suhu": re.compile(r"\b(?:suhu|temp(?:eratur)?)\s*[:=]?\s*(\d{2}(?:[.,]\d)?)\s*(?:c|celcius)?\b", re.I),
    "td": re.compile(r"\b(?:td|tekanan\s+darah)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})\s*(?:mmhg)?\b", re.I),
    "gcs": re.compile(r"\bgcs\s*[:=]?\s*(\d{1,2})\b", re.I),
}


@dataclass(frozen=True)
class ValidationOutcome:
    accepted: bool
    response: ClinicalResponse
    display_text: str

    @property
    def payload(self) -> dict[str, Any]:
        return self.response.model_dump(mode="json")


def validate_clinical_output(
    raw_output: str | dict[str, Any],
    selected_framework: str,
    registry: ClinicalRegistry,
    patient_context: str = "",
) -> ValidationOutcome:
    framework = _normalize_standard(selected_framework)
    issues: list[ClinicalValidationIssue] = []
    parsed = _parse_structured_output(raw_output)
    if parsed is None:
        missing = _measurement_missing_data(str(raw_output))
        return _abstain(
            framework,
            issues=[_issue("malformed_provider_output", "critical", "Provider output was not valid structured clinical JSON.")],
            field="structured_clinical_output",
            reason="Model output could not be parsed as the required typed clinical schema.",
            question="Mohon ulangi dengan data klinis terstruktur atau lengkapi data pengkajian utama.",
            status="malformed_output",
            missing_data=missing or None,
        )
    try:
        response = ClinicalResponse.model_validate(parsed)
    except ValidationError as exc:
        return _abstain(
            framework,
            issues=[_issue("schema_invalid", "critical", _short(str(exc)))],
            field="structured_clinical_output",
            reason="Model output did not match the required typed clinical schema.",
            question="Mohon lengkapi data klinis dan hasilkan ulang dalam format terstruktur yang valid.",
            status="malformed_output",
        )

    provider_framework = _normalize_standard(str(parsed.get("framework", framework)))
    response.framework = framework
    response.nurse_review_required = True
    for candidate in response.diagnoses + response.outcomes + response.interventions:
        candidate.nurse_review_required = True
        candidate.validation_status = "unvalidated"

    if response.status == "insufficient_data" and not (response.diagnoses or response.outcomes or response.interventions):
        return ValidationOutcome(False, response, render_clinical_response(response))

    if provider_framework != framework:
        issues.append(_issue("framework_mismatch", "critical", "Clinical response framework does not match the selected framework."))

    expected = STANDARD_MAP.get(framework)
    if not expected:
        issues.append(_issue("unsupported_framework", "critical", "Selected clinical framework is unsupported."))
        expected = {"diagnosis": "", "outcome": "", "intervention": ""}

    missing_registries = _missing_expected_registries(expected, registry)
    if missing_registries:
        status = "registry_unavailable" if expected["diagnosis"] in missing_registries else "registry_incomplete"
        issue_code = "registry_unavailable" if status == "registry_unavailable" else "registry_incomplete"
        issues.append(_issue(
            issue_code,
            "critical",
            "Missing approved registries: " + ", ".join(missing_registries) + ".",
        ))
        return _abstain(
            framework,
            issues=issues,
            missing_data=_missing_data_for_registries(missing_registries, status),
            status=status,
        )

    for candidate in response.diagnoses:
        issues.extend(_validate_diagnosis(candidate, expected["diagnosis"], registry, patient_context))
    for candidate in response.outcomes:
        issues.extend(_validate_supporting_item(candidate, expected["outcome"], registry, patient_context, "outcome"))
    for candidate in response.interventions:
        issues.extend(_validate_supporting_item(candidate, expected["intervention"], registry, patient_context, "intervention"))

    if issues:
        missing = _missing_data_from_issues(issues)
        status = "registry_unavailable" if any(issue.code == "registry_unavailable" for issue in issues) else "insufficient_data"
        return _abstain(framework, issues=issues, missing_data=missing, status=status)

    response.status = "validated"
    _apply_server_authority(response, expected, registry)
    return ValidationOutcome(True, response, render_clinical_response(response))


def safe_abstention(
    framework: str,
    reason: str = "Required evidence is insufficient.",
    status: str = "insufficient_data",
    issue_code: str | None = None,
    field: str = "objective_respiratory_findings",
    question: str = "Mohon lengkapi RR, SpO2, pola napas, penggunaan otot bantu napas, data subjektif, dan data objektif utama.",
) -> ClinicalResponse:
    return ClinicalResponse(
        status=status,  # type: ignore[arg-type]
        framework=_normalize_standard(framework),
        diagnoses=[],
        outcomes=[],
        interventions=[],
        missing_data=[MissingClinicalData(
            field=field,
            reason=reason,
            question_for_nurse=question,
        )],
        validation_issues=[_issue(issue_code, "critical", reason)] if issue_code else [],
        nurse_review_required=True,
    )


def render_clinical_response(response: ClinicalResponse) -> str:
    if response.status != "validated":
        lines = [
            "Data klinis belum cukup untuk menyarankan diagnosis secara aman.",
            "",
            "## Status Validasi",
            "Rekomendasi klinis tidak ditampilkan sebagai hasil tervalidasi. Perawat tetap wajib melakukan penilaian klinis mandiri.",
        ]
        if response.validation_issues:
            lines.extend(["", "## Alasan Penolakan"])
            for issue in response.validation_issues:
                lines.append(f"1. {issue.code}: {issue.message}")
        if response.missing_data:
            lines.extend(["", "## Data yang Perlu Dilengkapi"])
            for item in response.missing_data:
                lines.append(f"1. {item.question_for_nurse}")
        lines.extend(["", "Nurse review required: ya."])
        return "\n".join(lines).strip()

    lines = [
        "Hasil berikut lolos validasi skema dan registry fixture sintetis. Tetap wajib ditinjau perawat.",
        "",
        "## Diagnosis Keperawatan Tervalidasi",
    ]
    if not response.diagnoses:
        lines.append("Tidak ada diagnosis yang tervalidasi.")
    for diagnosis in response.diagnoses:
        lines.append(f"1. **{diagnosis.name} ({diagnosis.code})**")
        lines.append(f"   1. Framework: {diagnosis.framework}.")
        for evidence in diagnosis.supporting_evidence:
            lines.append(f"   1. Bukti pasien: {evidence.patient_fact}.")
        lines.append("   1. Nurse review required: ya.")
    if response.outcomes:
        lines.extend(["", "## Luaran Tervalidasi"])
        for outcome in response.outcomes:
            code = f" ({outcome.code})" if outcome.code else ""
            lines.append(f"1. **{outcome.name}{code}**")
    if response.interventions:
        lines.extend(["", "## Intervensi Tervalidasi"])
        for intervention in response.interventions:
            code = f" ({intervention.code})" if intervention.code else ""
            lines.append(f"1. **{intervention.name}{code}**")
    lines.extend(["", "Nurse review required: ya."])
    return "\n".join(lines).strip()


def _missing_expected_registries(expected: dict[str, str], registry: ClinicalRegistry) -> list[str]:
    missing: list[str] = []
    for framework in (expected.get("diagnosis"), expected.get("outcome"), expected.get("intervention")):
        if framework and not registry.approved_available(framework):
            missing.append(framework)
    return missing

def _missing_data_for_registries(missing_registries: list[str], status: str) -> list[MissingClinicalData]:
    missing = ", ".join(missing_registries)
    if status == "registry_incomplete":
        reason = "Approved registry set is incomplete for a complete nursing care-plan response."
        question = f"Approved registries missing: {missing}. The care plan cannot be generated safely until these registries are approved."
    else:
        reason = "Approved diagnosis registry is unavailable for authoritative grounding."
        question = f"Approved registries missing: {missing}. Clinical recommendations cannot be generated safely."
    return [MissingClinicalData(field="approved_registries", reason=reason, question_for_nurse=question)]

def _validate_diagnosis(
    candidate: DiagnosisCandidate,
    expected_framework: str,
    registry: ClinicalRegistry,
    patient_context: str,
) -> list[ClinicalValidationIssue]:
    issues = _candidate_common_issues(candidate.framework, candidate.code, candidate.name, expected_framework, registry, "diagnosis")
    if candidate.missing_required_evidence:
        issues.append(_issue("missing_required_evidence", "high", "Diagnosis candidate declares missing required evidence."))
    issues.extend(_evidence_issues(candidate.supporting_evidence, patient_context, "diagnosis"))
    return issues


def _validate_supporting_item(
    candidate: OutcomeCandidate | InterventionCandidate,
    expected_framework: str,
    registry: ClinicalRegistry,
    patient_context: str,
    kind: str,
) -> list[ClinicalValidationIssue]:
    issues: list[ClinicalValidationIssue] = []
    if not registry.approved_available(expected_framework):
        issues.append(_issue("registry_unavailable", "critical", f"Approved {expected_framework} registry is unavailable; {kind} cannot be authoritative."))
    if not candidate.code:
        issues.append(_issue("missing_code", "critical", f"{kind.title()} candidate is missing a registry code."))
    else:
        issues.extend(_candidate_common_issues(candidate.framework, candidate.code, candidate.name, expected_framework, registry, kind))
    issues.extend(_evidence_issues(candidate.supporting_evidence, patient_context, kind))
    return issues


def _candidate_common_issues(
    candidate_framework: str,
    code: str,
    name: str,
    expected_framework: str,
    registry: ClinicalRegistry,
    kind: str,
) -> list[ClinicalValidationIssue]:
    issues: list[ClinicalValidationIssue] = []
    actual_framework = normalize_registry_framework(candidate_framework)
    if actual_framework != expected_framework:
        issues.append(_issue("framework_mismatch", "critical", f"{kind.title()} framework does not match selected standard."))
    if not valid_code_format(expected_framework, code):
        issues.append(_issue("malformed_code", "critical", f"Malformed {expected_framework} code."))
        return issues
    if not registry.approved_available(expected_framework):
        issues.append(_issue("registry_unavailable", "critical", f"Approved {expected_framework} registry is unavailable."))
        return issues
    entry = registry.lookup(expected_framework, code)
    if entry is None:
        issues.append(_issue("unknown_code", "critical", f"{expected_framework} code is not present in the approved registry."))
        return issues
    if entry.name.casefold().strip() != (name or "").casefold().strip():
        issues.append(_issue("code_name_mismatch", "critical", f"{expected_framework} code and name do not match the approved registry."))
    return issues


def _apply_server_authority(response: ClinicalResponse, expected: dict[str, str], registry: ClinicalRegistry) -> None:
    response.nurse_review_required = True
    for kind, candidates in (
        ("diagnosis", response.diagnoses),
        ("outcome", response.outcomes),
        ("intervention", response.interventions),
    ):
        expected_framework = expected[kind]
        for candidate in candidates:
            candidate.framework = expected_framework
            candidate.nurse_review_required = True
            candidate.validation_status = "validated"
            entry = registry.lookup(expected_framework, getattr(candidate, "code", "") or "")
            if entry is not None:
                candidate.name = entry.name
                if isinstance(candidate, DiagnosisCandidate):
                    candidate.registry_version = entry.source_version
                    candidate.registry_source = entry.source_title
                    candidate.confidence_band = "unknown"

def _evidence_issues(evidence: Iterable[Any], patient_context: str, kind: str) -> list[ClinicalValidationIssue]:
    items = list(evidence or [])
    if not items:
        return [_issue("missing_supporting_evidence", "critical", f"{kind.title()} candidate has no supporting patient evidence.")]
    issues: list[ClinicalValidationIssue] = []
    for item in items:
        source = (getattr(item, "source", "") or "").strip().lower()
        if source not in ALLOWED_EVIDENCE_SOURCES:
            issues.append(_issue("unsupported_evidence_source", "high", f"{kind.title()} evidence source is not accepted."))
            continue
        fact = getattr(item, "patient_fact", "") or ""
        if not _meaningful_tokens(fact) and not _extract_measurements(fact):
            issues.append(_issue("empty_patient_fact", "critical", f"{kind.title()} evidence has an empty patient fact."))
            continue
        supported, support_issues = _evidence_supported(fact, patient_context)
        if not supported:
            issues.extend(_issue(code, "critical", f"{kind.title()} evidence is not traceable to trusted patient context.") for code in support_issues)
    return issues

def _evidence_supported(fact: str, patient_context: str) -> tuple[bool, list[str]]:
    if not (patient_context or "").strip():
        return False, ["missing_trusted_patient_context"]
    fact_norm = _normalize_evidence_text(fact)
    context_norm = _normalize_evidence_text(patient_context)
    issues: list[str] = []

    fact_measurements = _extract_measurements(fact_norm)
    context_measurements = _extract_measurements(context_norm)
    for key, values in fact_measurements.items():
        if key not in context_measurements or context_measurements[key] != values:
            issues.append("measurement_mismatch")

    fact_polarity = _concept_polarity(fact_norm)
    context_polarity = _concept_polarity(context_norm)
    for concept, polarities in fact_polarity.items():
        trusted = context_polarity.get(concept)
        if not trusted:
            issues.append("unsupported_claim")
            continue
        if "positive" in polarities and "positive" not in trusted:
            issues.append("negation_contradiction")
        if "negative" in polarities and "negative" not in trusted:
            issues.append("negation_contradiction")

    fact_tokens = _meaningful_tokens(fact_norm)
    context_tokens = _meaningful_tokens(context_norm)
    if fact_tokens and not fact_tokens.issubset(context_tokens):
        issues.append("unsupported_claim")

    return not issues, sorted(set(issues))

def _normalize_evidence_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    normalized = normalized.replace("spo 2", "spo2")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()

def _extract_measurements(text: str) -> dict[str, tuple[str, ...]]:
    normalized = _normalize_evidence_text(text)
    result: dict[str, tuple[str, ...]] = {}
    for key, pattern in MEASUREMENT_PATTERNS.items():
        values: list[str] = []
        for match in pattern.findall(normalized):
            if isinstance(match, tuple):
                values.append("/".join(part.replace(",", ".") for part in match if part))
            else:
                values.append(str(match).replace(",", "."))
        if values:
            result[key] = tuple(values)
    return result

def _concept_polarity(text: str) -> dict[str, set[str]]:
    normalized = _normalize_evidence_text(text)
    result: dict[str, set[str]] = {}
    for concept, variants in CLINICAL_CONCEPTS.items():
        for variant in variants:
            pattern = re.compile(rf"\b{re.escape(variant)}\b")
            for match in pattern.finditer(normalized):
                polarity = "negative" if _is_negated(normalized, match.start()) else "positive"
                result.setdefault(concept, set()).add(polarity)
    return result

def _is_negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 48):start]
    words = re.findall(r"[a-z0-9]+", prefix)[-5:]
    return any(term in words for term in NEGATION_TERMS)

def _meaningful_tokens(text: str) -> set[str]:
    return {token for token in _tokens(_normalize_evidence_text(text)) if token not in STOPWORDS}


def _abstain(
    framework: str,
    issues: list[ClinicalValidationIssue],
    field: str = "clinical_evidence",
    reason: str = "Required evidence is insufficient or registry validation failed.",
    question: str = "Mohon lengkapi data subjektif, data objektif, tanda mayor/minor, dan hasil pemeriksaan yang relevan.",
    status: str = "insufficient_data",
    missing_data: list[MissingClinicalData] | None = None,
) -> ValidationOutcome:
    response = ClinicalResponse(
        status=status,  # type: ignore[arg-type]
        framework=framework,
        diagnoses=[],
        outcomes=[],
        interventions=[],
        missing_data=missing_data or [MissingClinicalData(field=field, reason=reason, question_for_nurse=question)],
        validation_issues=issues,
        nurse_review_required=True,
    )
    return ValidationOutcome(False, response, render_clinical_response(response))


def _missing_data_from_issues(issues: list[ClinicalValidationIssue]) -> list[MissingClinicalData]:
    if any(issue.code == "registry_incomplete" for issue in issues):
        return [MissingClinicalData(
            field="approved_registries",
            reason="Approved registry set is incomplete for a complete nursing care-plan response.",
            question_for_nurse="Approved SLKI/SIKI or NOC/NIC registry components are missing; the complete care plan cannot be generated safely.",
        )]
    if any(issue.code == "registry_unavailable" for issue in issues):
        return [MissingClinicalData(
            field="approved_registry",
            reason="Approved registry fixture is unavailable for the requested framework.",
            question_for_nurse="Registry resmi/terverifikasi belum tersedia; rekomendasi tidak dapat ditampilkan sebagai authoritative grounding.",
        )]
    if any(issue.code in {"missing_supporting_evidence", "unsupported_claim", "missing_required_evidence"} for issue in issues):
        return [MissingClinicalData(
            field="supporting_patient_evidence",
            reason="Required patient evidence is insufficient or not traceable.",
            question_for_nurse="Mohon lengkapi data subjektif, data objektif, tanda mayor/minor, dan hasil pemeriksaan yang mendukung diagnosis.",
        )]
    return [MissingClinicalData(
        field="structured_clinical_output",
        reason="Structured output failed deterministic validation.",
        question_for_nurse="Mohon lengkapi data klinis dan ulangi penilaian dengan keluaran terstruktur yang valid.",
    )]


def _measurement_missing_data(text: str) -> list[MissingClinicalData]:
    patterns = [
        r"\bTD\s*\d{2,3}\s*/\s*\d{2,3}\s*mmHg\b",
        r"\bRR\s*\d{1,3}\s*x\s*/\s*menit\b",
        r"\bSpO2\s*\d{1,3}\s*%",
        r"\bSuhu\s*\d{2}(?:\.\d)?\s*C\b",
        r"\bNadi\s*\d{1,3}\s*x\s*/\s*menit\b",
        r"\bGCS\s*\d{1,2}\b",
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text or "", flags=re.IGNORECASE):
            value = re.sub(r"\s+", " ", match).strip()
            if value not in found:
                found.append(value)
    if not found:
        return []
    return [MissingClinicalData(
        field="confirm_observed_measurements",
        reason="Non-identifying measurements were observed in malformed provider output but were not accepted as clinical recommendations.",
        question_for_nurse="Konfirmasi ulang data berikut dari catatan pasien sebelum penilaian klinis: " + "; ".join(found) + ".",
    )]


def _parse_structured_output(raw_output: str | dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(raw_output, dict):
        return raw_output if raw_output and _json_depth(raw_output) <= MAX_CLINICAL_RESPONSE_DEPTH else None
    text = (raw_output or "").strip()
    if not text or len(text.encode("utf-8")) > MAX_CLINICAL_RESPONSE_BYTES:
        return None
    if text.startswith("```") or text.endswith("```"):
        return None
    try:
        parsed = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except Exception:
        return None
    if not isinstance(parsed, dict) or not parsed:
        return None
    if _json_depth(parsed) > MAX_CLINICAL_RESPONSE_DEPTH:
        return None
    return parsed

def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result

def _json_depth(value: Any, current: int = 0) -> int:
    if isinstance(value, dict):
        return max([current + 1, *(_json_depth(v, current + 1) for v in value.values())])
    if isinstance(value, list):
        return max([current + 1, *(_json_depth(v, current + 1) for v in value)])
    return current


def _issue(code: str, severity: str, message: str) -> ClinicalValidationIssue:
    return ClinicalValidationIssue(code=code, severity=severity, message=message)


def _normalize_standard(framework: str) -> str:
    f = (framework or "3S").strip().upper()
    if f in {"SDKI", "SLKI", "SIKI"}:
        return "3S"
    if f in {"NANDA", "NANDA-I", "NOC", "NIC"}:
        return "3N"
    return f or "3S"


def _tokens(text: str) -> set[str]:
    return {token for token in re.sub(r"[^0-9a-zA-ZÀ-ÿ]+", " ", text or "").lower().split() if len(token) > 2}


def _short(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:limit] + ("..." if len(text) > limit else "")
