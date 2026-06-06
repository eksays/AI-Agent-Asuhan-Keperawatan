from __future__ import annotations

import json
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
import config  # noqa: E402
from clinical_registry import ClinicalRegistry  # noqa: E402
from clinical_validator import validate_clinical_output  # noqa: E402


PATIENT_CONTEXT = "Pasien batuk, sputum kental, RR 28 x/menit, SpO2 90%, suara napas ronki."


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class RecordingLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list = []

    def invoke(self, messages, *_args, **_kwargs):
        self.calls.append(messages)
        return FakeResponse(self.response)

    def stream(self, *_args, **_kwargs):
        raise AssertionError("Direct streaming must not be used")


def enabled_config(**extra: str):
    env = {"APP_MODE": "clinical_sandbox", "ALLOW_UNSAFE_EXTERNAL_LLM_FOR_LOCAL_DEBUG": "true"}
    env.update(extra)
    return config.load_config(env)


def approved_entry(framework="SDKI", code="D.0001", name="Bersihan Jalan Napas Tidak Efektif"):
    return {
        "framework": framework,
        "code": code,
        "name": name,
        "source_title": "Synthetic nursing registry fixture",
        "source_version": "fixture-v1",
        "source_page": "1",
        "source_section": "synthetic",
        "extraction_method": "manual_test_fixture",
        "reviewer": "synthetic reviewer",
        "review_date": "2026-01-01",
        "approval_status": "approved",
        "content_hash": f"hash-{framework}-{code}",
    }


def registry_with(*entries: dict) -> ClinicalRegistry:
    return ClinicalRegistry.from_entries(entries)

def approved_registry_3s() -> ClinicalRegistry:
    return registry_with(
        approved_entry("SDKI", "D.0001", "Bersihan Jalan Napas Tidak Efektif"),
        approved_entry("SLKI", "L.0001", "Status Pernapasan"),
        approved_entry("SIKI", "I.0001", "Manajemen Jalan Napas"),
    )

def approved_registry_3n() -> ClinicalRegistry:
    return registry_with(
        approved_entry("NANDA", "00031", "Ineffective Airway Clearance"),
        approved_entry("NOC", "1234", "Respiratory Status"),
        approved_entry("NIC", "1234", "Airway Management"),
    )


def clinical_payload(**overrides):
    payload = {
        "status": "validated",
        "framework": "3S",
        "diagnoses": [{
            "framework": "SDKI",
            "code": "D.0001",
            "name": "Bersihan Jalan Napas Tidak Efektif",
            "supporting_evidence": [{
                "patient_fact": "RR 28 x/menit dan SpO2 90%",
                "source": "patient_record",
                "matched_criterion": "gangguan oksigenasi",
            }],
            "missing_required_evidence": [],
            "confidence_band": "medium",
            "validation_status": "validated",
            "nurse_review_required": True,
        }],
        "outcomes": [],
        "interventions": [],
        "missing_data": [],
        "validation_issues": [],
        "nurse_review_required": True,
    }
    payload.update(overrides)
    return payload

def diagnosis_candidate(**overrides):
    candidate = dict(clinical_payload()["diagnoses"][0])
    candidate.update(overrides)
    return candidate

def outcome_candidate(**overrides):
    candidate = {
        "framework": "SLKI",
        "code": "L.0001",
        "name": "Status Pernapasan",
        "supporting_evidence": [{"patient_fact": "RR 28 x/menit dan SpO2 90%", "source": "patient_record"}],
        "validation_status": "validated",
        "nurse_review_required": True,
    }
    candidate.update(overrides)
    return candidate

def intervention_candidate(**overrides):
    candidate = {
        "framework": "SIKI",
        "code": "I.0001",
        "name": "Manajemen Jalan Napas",
        "rationale": "Synthetic fixture rationale.",
        "supporting_evidence": [{"patient_fact": "batuk dan sputum kental", "source": "patient_record"}],
        "validation_status": "validated",
        "nurse_review_required": True,
    }
    candidate.update(overrides)
    return candidate


def validate(payload, registry=None, framework="3S", context=PATIENT_CONTEXT):
    raw = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else payload
    return validate_clinical_output(raw, framework, registry or approved_registry_3s(), patient_context=context)


class Phase2RegistryTests(unittest.TestCase):
    def test_valid_registry_backed_candidate_passes(self):
        outcome = validate(clinical_payload())
        self.assertTrue(outcome.accepted)
        self.assertEqual(outcome.response.status, "validated")
        self.assertEqual(len(outcome.response.diagnoses), 1)

    def test_duplicate_registry_code_rejected(self):
        reg = registry_with(
            approved_entry(code="D.0001", name="Bersihan Jalan Napas Tidak Efektif"),
            approved_entry(code="D.0001", name="Pola Napas Tidak Efektif"),
        )
        self.assertEqual(reg.approved_count, 0)
        self.assertTrue(any(issue.code == "duplicate_code" for issue in reg.issues))

    def test_missing_provenance_rejected_from_authoritative_registry(self):
        entry = approved_entry()
        entry.pop("reviewer")
        reg = registry_with(entry)
        self.assertEqual(reg.approved_count, 0)
        self.assertTrue(any(issue.code == "missing_provenance" for issue in reg.issues))

    def test_unapproved_and_quarantined_entries_excluded(self):
        draft = approved_entry(code="D.0002", name="Pola Napas Tidak Efektif")
        draft["approval_status"] = "under_clinical_review"
        quarantined = approved_entry(code="D.0003", name="Gangguan Pertukaran Gas")
        quarantined["approval_status"] = "quarantined"
        reg = registry_with(draft, quarantined)
        self.assertIsNone(reg.lookup("SDKI", "D.0002"))
        self.assertIsNone(reg.lookup("SDKI", "D.0003"))


class Phase2ValidatorTests(unittest.TestCase):
    def test_malformed_codes_are_rejected(self):
        for code in ("D.xxxx", "D.L"):
            with self.subTest(code=code):
                payload = clinical_payload(diagnoses=[{**clinical_payload()["diagnoses"][0], "code": code}])
                outcome = validate(payload)
                self.assertFalse(outcome.accepted)
                self.assertIn("malformed_code", [issue.code for issue in outcome.response.validation_issues])

    def test_unknown_well_formatted_code_rejected(self):
        payload = clinical_payload(diagnoses=[{**clinical_payload()["diagnoses"][0], "code": "D.9999"}])
        outcome = validate(payload)
        self.assertFalse(outcome.accepted)
        self.assertIn("unknown_code", [issue.code for issue in outcome.response.validation_issues])

    def test_code_name_mismatch_rejected(self):
        payload = clinical_payload(diagnoses=[{**clinical_payload()["diagnoses"][0], "name": "Pola Napas Tidak Efektif"}])
        outcome = validate(payload)
        self.assertFalse(outcome.accepted)
        self.assertIn("code_name_mismatch", [issue.code for issue in outcome.response.validation_issues])

    def test_wrong_framework_rejected(self):
        payload = clinical_payload(diagnoses=[{**clinical_payload()["diagnoses"][0], "framework": "NANDA"}])
        outcome = validate(payload)
        self.assertFalse(outcome.accepted)
        self.assertIn("framework_mismatch", [issue.code for issue in outcome.response.validation_issues])

    def test_missing_sdki_registry_causes_abstention(self):
        outcome = validate(clinical_payload(), registry=ClinicalRegistry.unavailable())
        self.assertFalse(outcome.accepted)
        self.assertEqual(outcome.response.status, "registry_unavailable")
        self.assertIn("registry_unavailable", [issue.code for issue in outcome.response.validation_issues])

    def test_missing_slki_siki_prevents_fabricated_outcomes_and_interventions(self):
        payload = clinical_payload(
            outcomes=[{
                "framework": "SLKI", "code": "L.12111", "name": "Status Pernapasan",
                "supporting_evidence": [{"patient_fact": "SpO2 90%", "source": "patient_record"}],
                "validation_status": "validated", "nurse_review_required": True,
            }],
            interventions=[{
                "framework": "SIKI", "code": "I.12383", "name": "Manajemen Jalan Napas", "rationale": "fixture",
                "supporting_evidence": [{"patient_fact": "sputum kental", "source": "patient_record"}],
                "validation_status": "validated", "nurse_review_required": True,
            }],
        )
        outcome = validate(payload, registry=registry_with(approved_entry()))
        self.assertFalse(outcome.accepted)
        self.assertEqual(outcome.response.status, "registry_incomplete")
        self.assertIn("registry_incomplete", [issue.code for issue in outcome.response.validation_issues])
        self.assertIn("SLKI", outcome.response.missing_data[0].question_for_nurse)
        self.assertIn("SIKI", outcome.response.missing_data[0].question_for_nurse)

    def test_missing_nanda_noc_nic_prevents_fabricated_3n_output(self):
        payload = clinical_payload(framework="3N", diagnoses=[{**clinical_payload()["diagnoses"][0], "framework": "NANDA", "code": "00031"}])
        outcome = validate(payload, registry=ClinicalRegistry.unavailable(), framework="3N")
        self.assertFalse(outcome.accepted)
        self.assertIn("registry_unavailable", [issue.code for issue in outcome.response.validation_issues])

    def test_malformed_json_and_raw_prose_rejected(self):
        for raw in ("{not-json", "Diagnosis meyakinkan D.9999 tampak tepat."):
            with self.subTest(raw=raw):
                outcome = validate(raw)
                self.assertFalse(outcome.accepted)
                self.assertIn(outcome.response.status, {"malformed_output", "insufficient_data"})

    def test_diagnosis_without_supporting_evidence_rejected(self):
        payload = clinical_payload(diagnoses=[{**clinical_payload()["diagnoses"][0], "supporting_evidence": []}])
        outcome = validate(payload)
        self.assertFalse(outcome.accepted)
        self.assertIn("missing_supporting_evidence", [issue.code for issue in outcome.response.validation_issues])

    def test_insufficient_evidence_triggers_abstention(self):
        payload = clinical_payload(diagnoses=[{**clinical_payload()["diagnoses"][0], "missing_required_evidence": ["SpO2 belum ada"]}])
        outcome = validate(payload)
        self.assertFalse(outcome.accepted)
        self.assertEqual(outcome.response.status, "insufficient_data")
        self.assertTrue(outcome.response.missing_data)

    def test_no_forced_minimum_number_of_diagnoses(self):
        outcome = validate(clinical_payload())
        self.assertTrue(outcome.accepted)
        self.assertEqual(len(outcome.response.diagnoses), 1)

    def test_nurse_review_required_remains_true(self):
        outcome = validate(clinical_payload())
        self.assertTrue(outcome.response.nurse_review_required)
        self.assertTrue(outcome.response.diagnoses[0].nurse_review_required)
        payload = clinical_payload(nurse_review_required=False)
        forced = validate(payload)
        self.assertTrue(forced.response.nurse_review_required)
        self.assertTrue(forced.response.diagnoses[0].nurse_review_required)

class Phase2TrustedEvidenceBindingTests(unittest.TestCase):
    def test_numeric_and_negation_contradiction_rejected(self):
        payload = clinical_payload(diagnoses=[diagnosis_candidate(supporting_evidence=[{
            "patient_fact": "RR 32 x/menit, SpO2 88%, pasien sesak.",
            "source": "patient_record",
        }])])
        outcome = validate(payload, context="RR 20 x/menit, SpO2 98%, tidak sesak.")
        issue_codes = [issue.code for issue in outcome.response.validation_issues]
        self.assertFalse(outcome.accepted)
        self.assertIn("measurement_mismatch", issue_codes)
        self.assertIn("negation_contradiction", issue_codes)

    def test_negated_ronki_not_converted_to_positive(self):
        payload = clinical_payload(diagnoses=[diagnosis_candidate(supporting_evidence=[{
            "patient_fact": "Suara napas ronki.",
            "source": "patient_record",
        }])])
        outcome = validate(payload, context="Tidak terdapat ronki.")
        self.assertFalse(outcome.accepted)
        self.assertIn("negation_contradiction", [issue.code for issue in outcome.response.validation_issues])

    def test_matching_numeric_evidence_passes(self):
        payload = clinical_payload(diagnoses=[diagnosis_candidate(supporting_evidence=[{
            "patient_fact": "RR 28 x/menit dan SpO2 90%.",
            "source": "patient_record",
        }])])
        outcome = validate(payload, context="RR 28 x/menit dan SpO2 90%.")
        self.assertTrue(outcome.accepted)

    def test_hallucinated_symptoms_rejected(self):
        payload = clinical_payload(diagnoses=[diagnosis_candidate(supporting_evidence=[{
            "patient_fact": "Demam tinggi dan sianosis.",
            "source": "patient_record",
        }])])
        outcome = validate(payload, context="Batuk dan sputum kental.")
        self.assertFalse(outcome.accepted)
        self.assertIn("unsupported_claim", [issue.code for issue in outcome.response.validation_issues])

    def test_negated_chest_pain_not_converted_to_positive(self):
        payload = clinical_payload(diagnoses=[diagnosis_candidate(supporting_evidence=[{
            "patient_fact": "Nyeri dada.",
            "source": "patient_record",
        }])])
        outcome = validate(payload, context="Tidak ada nyeri dada.")
        self.assertFalse(outcome.accepted)
        self.assertIn("negation_contradiction", [issue.code for issue in outcome.response.validation_issues])

    def test_provider_draft_source_is_untrusted(self):
        payload = clinical_payload(diagnoses=[diagnosis_candidate(supporting_evidence=[{
            "patient_fact": "RR 28 x/menit dan SpO2 90%.",
            "source": "provider_draft",
        }])])
        outcome = validate(payload)
        self.assertFalse(outcome.accepted)
        self.assertIn("unsupported_evidence_source", [issue.code for issue in outcome.response.validation_issues])

class Phase2ServerAuthorityTests(unittest.TestCase):
    def test_provider_validation_status_cannot_override_unsupported_evidence(self):
        payload = clinical_payload(diagnoses=[diagnosis_candidate(
            validation_status="validated",
            supporting_evidence=[{"patient_fact": "Demam tinggi dan sianosis.", "source": "patient_record"}],
        )])
        outcome = validate(payload, context="Batuk dan sputum kental.")
        self.assertFalse(outcome.accepted)
        self.assertIn("unsupported_claim", [issue.code for issue in outcome.response.validation_issues])

    def test_provider_registry_metadata_overwritten_from_registry(self):
        payload = clinical_payload(diagnoses=[diagnosis_candidate(
            registry_version="fake-provider-version",
            registry_source="fake-provider-source",
            confidence_band="high",
        )])
        outcome = validate(payload)
        self.assertTrue(outcome.accepted)
        diagnosis = outcome.response.diagnoses[0]
        self.assertEqual(diagnosis.registry_version, "fixture-v1")
        self.assertEqual(diagnosis.registry_source, "Synthetic nursing registry fixture")
        self.assertEqual(diagnosis.confidence_band, "unknown")

    def test_provider_confidence_certain_rejected_by_schema(self):
        payload = clinical_payload(diagnoses=[diagnosis_candidate(confidence_band="certain")])
        outcome = validate(payload)
        self.assertFalse(outcome.accepted)
        self.assertEqual(outcome.response.status, "malformed_output")

class Phase2FrameworkFamilyMappingTests(unittest.TestCase):
    def test_sdki_diagnosis_inside_3n_rejected(self):
        payload = clinical_payload(framework="3N", diagnoses=[diagnosis_candidate(framework="SDKI", code="D.0001")])
        outcome = validate(payload, registry=approved_registry_3n(), framework="3N")
        self.assertFalse(outcome.accepted)
        self.assertIn("framework_mismatch", [issue.code for issue in outcome.response.validation_issues])

    def test_nanda_diagnosis_inside_3s_rejected(self):
        payload = clinical_payload(diagnoses=[diagnosis_candidate(framework="NANDA", code="00031")])
        outcome = validate(payload)
        self.assertFalse(outcome.accepted)
        self.assertIn("framework_mismatch", [issue.code for issue in outcome.response.validation_issues])

    def test_slki_outcome_as_siki_intervention_rejected(self):
        payload = clinical_payload(interventions=[intervention_candidate(framework="SLKI", code="L.0001", name="Status Pernapasan")])
        outcome = validate(payload, registry=approved_registry_3s())
        self.assertFalse(outcome.accepted)
        self.assertIn("framework_mismatch", [issue.code for issue in outcome.response.validation_issues])

    def test_noc_outcome_inside_3s_rejected(self):
        payload = clinical_payload(outcomes=[outcome_candidate(framework="NOC", code="1234", name="Respiratory Status")])
        outcome = validate(payload, registry=approved_registry_3s())
        self.assertFalse(outcome.accepted)
        self.assertIn("framework_mismatch", [issue.code for issue in outcome.response.validation_issues])

    def test_nic_intervention_inside_3s_rejected(self):
        payload = clinical_payload(interventions=[intervention_candidate(framework="NIC", code="1234", name="Airway Management")])
        outcome = validate(payload, registry=approved_registry_3s())
        self.assertFalse(outcome.accepted)
        self.assertIn("framework_mismatch", [issue.code for issue in outcome.response.validation_issues])

    def test_partial_registry_availability_abstains_complete_care_plan(self):
        outcome = validate(clinical_payload(), registry=registry_with(approved_entry()))
        self.assertFalse(outcome.accepted)
        self.assertEqual(outcome.response.status, "registry_incomplete")
        self.assertFalse(outcome.response.diagnoses)
        self.assertIn("SLKI", outcome.response.missing_data[0].question_for_nurse)
        self.assertIn("SIKI", outcome.response.missing_data[0].question_for_nurse)

class Phase2StrictParsingTests(unittest.TestCase):
    def assert_rejected(self, raw):
        outcome = validate(raw)
        self.assertFalse(outcome.accepted)
        self.assertIn(outcome.response.status, {"malformed_output", "insufficient_data"})

    def test_raw_prose_only_rejected(self):
        self.assert_rejected("Diagnosis terlihat meyakinkan namun tidak berupa JSON terstruktur.")

    def test_malformed_json_rejected(self):
        self.assert_rejected("{not-json")

    def test_json_markdown_fence_rejected(self):
        self.assert_rejected("```json\n" + json.dumps(clinical_payload(), ensure_ascii=False) + "\n```")

    def test_leading_prose_before_json_rejected(self):
        self.assert_rejected("Berikut hasilnya:\n" + json.dumps(clinical_payload(), ensure_ascii=False))

    def test_trailing_prose_after_json_rejected(self):
        self.assert_rejected(json.dumps(clinical_payload(), ensure_ascii=False) + "\nSemoga membantu.")

    def test_duplicate_json_keys_rejected(self):
        base = json.dumps(clinical_payload(), ensure_ascii=False)
        self.assert_rejected('{"status":"validated",' + base.lstrip("{") )

    def test_unknown_extra_fields_rejected(self):
        payload = clinical_payload(unexpected_provider_field="not allowed")
        outcome = validate(payload)
        self.assertFalse(outcome.accepted)
        self.assertEqual(outcome.response.status, "malformed_output")

    def test_empty_object_rejected(self):
        self.assert_rejected("{}")

    def test_oversized_model_response_rejected(self):
        self.assert_rejected('{"status":"' + ("x" * 70000) + '"}')

    def test_deeply_nested_response_rejected(self):
        self.assert_rejected('{"status":' + ("[" * 20) + '"x"' + ("]" * 20) + '}')

class Phase2PrivacyContainmentTests(unittest.TestCase):
    SYNTHETIC_CANARY = "Synthetic Patient Alpha, email alpha.patient@example.invalid, RR 20 x/menit."

    def test_validation_issues_do_not_echo_raw_phi_canary(self):
        payload = clinical_payload(diagnoses=[diagnosis_candidate(supporting_evidence=[{
            "patient_fact": "Demam tinggi dan sianosis.",
            "source": "patient_record",
        }])])
        outcome = validate(payload, context=self.SYNTHETIC_CANARY)
        rendered = outcome.display_text + json.dumps(outcome.payload, ensure_ascii=False)
        self.assertNotIn("Synthetic Patient Alpha", rendered)
        self.assertNotIn("alpha.patient@example.invalid", rendered)

    def test_evidence_matching_does_not_log_raw_phi_canary(self):
        payload = clinical_payload(diagnoses=[diagnosis_candidate(supporting_evidence=[{
            "patient_fact": "Demam tinggi dan sianosis.",
            "source": "patient_record",
        }])])
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            validate(payload, context=self.SYNTHETIC_CANARY)
        self.assertNotIn("Synthetic Patient Alpha", stderr.getvalue())
        self.assertNotIn("alpha.patient@example.invalid", stderr.getvalue())

    def test_registry_errors_do_not_reveal_patient_narrative(self):
        outcome = validate(clinical_payload(), registry=ClinicalRegistry.unavailable(), context=self.SYNTHETIC_CANARY)
        rendered = outcome.display_text + json.dumps(outcome.payload, ensure_ascii=False)
        self.assertNotIn("Synthetic Patient Alpha", rendered)
        self.assertNotIn("alpha.patient@example.invalid", rendered)


class Phase2ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)

    def _session_id(self) -> str:
        return self.client.post("/session").json()["session_id"]

    def _chat_form(self, **overrides):
        data = {
            "provider": "openai",
            "model": "mock",
            "framework": "3S",
            "session_id": self._session_id(),
            "tier": "flash",
            "agent": "analisis",
            "pertanyaan": PATIENT_CONTEXT,
        }
        data.update(overrides)
        return data

    def _analysis_form(self, **overrides):
        data = {
            "provider": "openai",
            "model": "mock",
            "framework": "3S",
            "session_id": self._session_id(),
            "tier": "flash",
            "gejala": PATIENT_CONTEXT,
        }
        data.update(overrides)
        return data

    def _enabled_registry_unavailable_context(self, provider_mock):
        return mock.patch.multiple(
            api,
            CONFIG=enabled_config(),
            _create_raw_llm=provider_mock,
            framework_available=mock.Mock(return_value=True),
            askep_refs_available=mock.Mock(return_value=True),
            CLINICAL_REGISTRY=ClinicalRegistry.unavailable(),
        )

    def _enabled_registry_incomplete_context(self, provider_mock):
        return mock.patch.multiple(
            api,
            CONFIG=enabled_config(),
            _create_raw_llm=provider_mock,
            framework_available=mock.Mock(return_value=True),
            askep_refs_available=mock.Mock(return_value=True),
            CLINICAL_REGISTRY=registry_with(approved_entry()),
        )

    def test_confident_prose_with_invented_code_returns_safe_abstention(self):
        raw_llm = RecordingLLM("Diagnosis sangat yakin: D.9999 Bersihan Jalan Napas Tidak Efektif.")
        with mock.patch.object(api, "CONFIG", enabled_config()), \
             mock.patch.object(api, "_create_raw_llm", return_value=raw_llm), \
             mock.patch.object(api, "framework_available", return_value=True), \
             mock.patch.object(api, "askep_refs_available", return_value=True), \
             mock.patch.object(api, "bangun_konteks", return_value=""), \
             mock.patch.object(api.memory, "recall_block", return_value=""), \
             mock.patch.object(api, "CLINICAL_REGISTRY", approved_registry_3s()):
            response = self.client.post(
                "/chat",
                data={
                    "provider": "openai", "model": "mock", "framework": "3S", "session_id": self._session_id(),
                    "tier": "flash", "agent": "analisis", "pertanyaan": PATIENT_CONTEXT,
                },
                headers={"Authorization": "Bearer test-key"},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["clinical_validation"]["status"], "malformed_output")
        self.assertFalse(data["clinical_validation"]["accepted"])
        self.assertIn("Data klinis belum cukup", data["jawaban"])
        self.assertNotIn("D.9999", data["jawaban"])

    def test_provider_false_nurse_review_is_forced_true_by_api(self):
        payload = clinical_payload(nurse_review_required=False, diagnoses=[diagnosis_candidate(nurse_review_required=False)])
        raw_llm = RecordingLLM(json.dumps(payload, ensure_ascii=False))
        with mock.patch.object(api, "CONFIG", enabled_config()), \
             mock.patch.object(api, "_create_raw_llm", return_value=raw_llm), \
             mock.patch.object(api, "framework_available", return_value=True), \
             mock.patch.object(api, "askep_refs_available", return_value=True), \
             mock.patch.object(api, "bangun_konteks", return_value=""), \
             mock.patch.object(api.memory, "recall_block", return_value=""), \
             mock.patch.object(api, "CLINICAL_REGISTRY", approved_registry_3s()):
            response = self.client.post("/chat", data=self._chat_form(), headers={"Authorization": "Bearer test-key"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["nurse_review_required"])
        self.assertTrue(data["clinical_validation"]["nurse_review_required"])

    def test_chat_registry_unavailable_fails_fast_without_provider(self):
        provider_mock = mock.Mock(side_effect=AssertionError("provider must not be called"))
        with self._enabled_registry_unavailable_context(provider_mock):
            response = self.client.post("/chat", data=self._chat_form(), headers={"Authorization": "Bearer test-key"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["clinical_status"], "registry_unavailable")
        self.assertFalse(data["accepted_recommendations"])
        self.assertTrue(data["nurse_review_required"])
        self.assertIn("registry_unavailable", data["validation_issue_codes"])
        self.assertEqual(provider_mock.call_count, 0)

    def test_chat_stream_registry_unavailable_fails_fast_without_provider(self):
        provider_mock = mock.Mock(side_effect=AssertionError("provider must not be called"))
        with self._enabled_registry_unavailable_context(provider_mock):
            response = self.client.post("/chat_stream", data=self._chat_form(), headers={"Authorization": "Bearer test-key"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Clinical-Status"), "registry_unavailable")
        self.assertEqual(response.headers.get("X-Accepted-Recommendations"), "false")
        self.assertEqual(response.headers.get("X-Nurse-Review-Required"), "true")
        self.assertIn("Data klinis belum cukup", response.text)
        self.assertEqual(provider_mock.call_count, 0)

    def test_analisis_registry_unavailable_fails_fast_without_provider(self):
        provider_mock = mock.Mock(side_effect=AssertionError("provider must not be called"))
        with self._enabled_registry_unavailable_context(provider_mock):
            response = self.client.post("/analisis", data=self._analysis_form(), headers={"Authorization": "Bearer test-key"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["clinical_status"], "registry_unavailable")
        self.assertFalse(data["accepted_recommendations"])
        self.assertEqual(provider_mock.call_count, 0)

    def test_analisis_multi_registry_unavailable_fails_fast_without_provider(self):
        provider_mock = mock.Mock(side_effect=AssertionError("provider must not be called"))
        with self._enabled_registry_unavailable_context(provider_mock):
            response = self.client.post("/analisis_multi", data={**self._analysis_form(), "agent": "analisis"}, headers={"Authorization": "Bearer test-key"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["clinical_status"], "registry_unavailable")
        self.assertFalse(data["accepted_recommendations"])
        self.assertEqual(provider_mock.call_count, 0)

    def test_chat_registry_incomplete_fails_fast_without_provider(self):
        provider_mock = mock.Mock(side_effect=AssertionError("provider must not be called"))
        with self._enabled_registry_incomplete_context(provider_mock):
            response = self.client.post("/chat", data=self._chat_form(), headers={"Authorization": "Bearer test-key"})
        data = response.json()
        self.assertEqual(data["clinical_status"], "registry_incomplete")
        self.assertFalse(data["accepted_recommendations"])
        self.assertTrue(data["nurse_review_required"])
        self.assertIn("registry_incomplete", data["validation_issue_codes"])
        self.assertEqual(data["missing_registries"], ["SLKI", "SIKI"])
        self.assertEqual(data["clinical_validation"]["missing_registries"], ["SLKI", "SIKI"])
        self.assertIn("SLKI", data["jawaban"])
        self.assertIn("SIKI", data["jawaban"])
        self.assertEqual(provider_mock.call_count, 0)

    def test_chat_stream_registry_incomplete_fails_fast_without_provider(self):
        provider_mock = mock.Mock(side_effect=AssertionError("provider must not be called"))
        with self._enabled_registry_incomplete_context(provider_mock):
            response = self.client.post("/chat_stream", data=self._chat_form(), headers={"Authorization": "Bearer test-key"})
        self.assertEqual(response.headers.get("X-Clinical-Status"), "registry_incomplete")
        self.assertEqual(response.headers.get("X-Accepted-Recommendations"), "false")
        self.assertEqual(response.headers.get("X-Missing-Registries"), "SLKI,SIKI")
        self.assertIn("SLKI", response.text)
        self.assertIn("SIKI", response.text)
        self.assertEqual(provider_mock.call_count, 0)

    def test_analisis_registry_incomplete_fails_fast_without_provider(self):
        provider_mock = mock.Mock(side_effect=AssertionError("provider must not be called"))
        with self._enabled_registry_incomplete_context(provider_mock):
            response = self.client.post("/analisis", data=self._analysis_form(), headers={"Authorization": "Bearer test-key"})
        data = response.json()
        self.assertEqual(data["clinical_status"], "registry_incomplete")
        self.assertFalse(data["accepted_recommendations"])
        self.assertEqual(data["missing_registries"], ["SLKI", "SIKI"])
        self.assertIn("SLKI", data["hasil"])
        self.assertIn("SIKI", data["hasil"])
        self.assertEqual(provider_mock.call_count, 0)

    def test_analisis_multi_registry_incomplete_fails_fast_without_provider(self):
        provider_mock = mock.Mock(side_effect=AssertionError("provider must not be called"))
        with self._enabled_registry_incomplete_context(provider_mock):
            response = self.client.post("/analisis_multi", data={**self._analysis_form(), "agent": "analisis"}, headers={"Authorization": "Bearer test-key"})
        data = response.json()
        self.assertEqual(data["clinical_status"], "registry_incomplete")
        self.assertFalse(data["accepted_recommendations"])
        self.assertEqual(data["missing_registries"], ["SLKI", "SIKI"])
        self.assertIn("SLKI", data["hasil"])
        self.assertIn("SIKI", data["hasil"])
        self.assertEqual(provider_mock.call_count, 0)

    def test_structured_abstention_does_not_echo_phi_canary_to_browser(self):
        provider_mock = mock.Mock(side_effect=AssertionError("provider must not be called"))
        form = self._chat_form(pertanyaan="Synthetic Patient Alpha alpha.patient@example.invalid mengeluh sesak.")
        with self._enabled_registry_unavailable_context(provider_mock):
            response = self.client.post("/chat", data=form, headers={"Authorization": "Bearer test-key"})
        body = response.text
        self.assertNotIn("Synthetic Patient Alpha", body)
        self.assertNotIn("alpha.patient@example.invalid", body)


if __name__ == "__main__":
    unittest.main()
