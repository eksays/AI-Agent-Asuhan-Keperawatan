from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

import api  # noqa: E402
import agents  # noqa: E402
import config  # noqa: E402
import ebp  # noqa: E402
import ekstraksi  # noqa: E402
import memory  # noqa: E402
from clinical_registry import ClinicalRegistry  # noqa: E402
from outbound_policy import OutboundDataPolicy, OutboundPolicyError, SafeLLM, wrap_llm  # noqa: E402
from scripts import populate_sdki  # noqa: E402


CANARY = """Nama pasien: Budi Santoso
NIK: 3273010101990001
No. BPJS: 0001234567890
MRN: RM-2026-001928
Telepon: +62 812-3456-7890
Email: budi.patient@example.com
Alamat: Jalan Merdeka No. 12 Bandung
Tanggal lahir: 1 Januari 1990
Keluhan nyeri dan sesak."""

RAW_CANARY_PARTS = (
    "Budi Santoso",
    "Siti Santoso",
    "3273010101990001",
    "0001234567890",
    "RM-2026-001928",
    "2026/001928-A",
    "+62 812-3456-7890",
    "(0812) 3456 7890",
    "0812-1111-2222",
    "budi.patient@example.com",
    "Jalan Merdeka No. 12 Bandung",
    "1 Januari 1990",
    "1990-01-01",
)

ADVERSARIAL_CASES = (
    "Nama pasien: Budi Santoso",
    "Pasien Budi Santoso datang dengan sesak.",
    "NIK: 3273010101990001",
    "No. BPJS: 0001234567890",
    "No. RM: RM-2026-001928",
    "MRN: 2026/001928-A",
    "Telepon: +62 812-3456-7890",
    "No. HP: (0812) 3456 7890",
    "Email: budi.patient@example.com",
    "Alamat: Jalan Merdeka No. 12 Bandung",
    "Tanggal lahir: 1 Januari 1990",
    "DOB: 1990-01-01",
    "Kontak keluarga: Siti Santoso, 0812-1111-2222",
    "nama pasien   :   budi santoso",
    "NAMA PASIEN: BUDI SANTOSO",
    "Nama Pasien: Budi Santoso, NIK: 3273010101990001, Email: budi.patient@example.com",
    "Riwayat: pasien Budi Santoso\nNo. BPJS: 0001234567890\nKeluhan sesak.",
    "Catatan menyebut MRN: 2026/001928-A di tengah kalimat.",
    "Provider echo Nama pasien: Budi Santoso dan Telepon: +62 812-3456-7890",
    "Feedback text Kontak keluarga: Siti Santoso, 0812-1111-2222",
    "Correction text DOB: 1990-01-01 dan No. RM: RM-2026-001928",
    "Uploaded-document content Alamat: Jalan Merdeka No. 12 Bandung",
)

CLINICAL_MEASUREMENTS = (
    "TD 120/80 mmHg",
    "RR 28 x/menit",
    "SpO2 92%",
    "Suhu 38.5 C",
    "Nadi 110 x/menit",
    "GCS 15",
    "Hb 10.2 g/dL",
    "Glukosa 180 mg/dL",
    "Na 138 mmol/L",
    "K 4.1 mmol/L",
    "BB 65 kg",
    "TB 170 cm",
    "D.0005",
    "SDKI",
    "SLKI",
    "SIKI",
    "NANDA",
    "NOC",
    "NIC",
)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class RecordingLLM:
    def __init__(self, response: str = "Jawaban aman.", responses: list[str] | None = None) -> None:
        self.response = response
        self.responses = list(responses or [])
        self.calls: list = []
        self.stream_called = False

    def invoke(self, messages, *_args, **_kwargs):
        self.calls.append(messages)
        if self.responses:
            return FakeResponse(self.responses.pop(0))
        return FakeResponse(self.response)

    def stream(self, *_args, **_kwargs):
        self.stream_called = True
        raise AssertionError("Raw token streaming must not be used.")


class MockHTTPResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"content": [{"type": "text", "text": "[]"}]}).encode("utf-8")

class RaisingLLM:
    def __init__(self, message: str) -> None:
        self.message = message

    def invoke(self, *_args, **_kwargs):
        raise RuntimeError(self.message)

class FakePdfPage:
    def extract_text(self):
        return "OCR halaman uji"

class FakePdf:
    pages = [FakePdfPage()]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def joined_messages(messages) -> str:
    if isinstance(messages, str):
        return messages
    return "\n".join(str(getattr(message, "content", "")) for message in messages)


def assert_no_raw_canary(testcase: unittest.TestCase, text: str) -> None:
    for raw in RAW_CANARY_PARTS:
        testcase.assertNotIn(raw, text)

def assert_raw_canary_absent_from_calls(testcase: unittest.TestCase, llm: RecordingLLM) -> None:
    for call in llm.calls:
        assert_no_raw_canary(testcase, joined_messages(call))

def enabled_config(**extra: str):
    env = {
        "APP_MODE": "clinical_sandbox",
        "ALLOW_UNSAFE_EXTERNAL_LLM_FOR_LOCAL_DEBUG": "true",
    }
    env.update(extra)
    return config.load_config(env)

def phase1_synthetic_registry() -> ClinicalRegistry:
    return ClinicalRegistry.from_entries([{
        "framework": "SDKI",
        "code": "D.0001",
        "name": "Synthetic Phase 1 Diagnosis",
        "source_title": "Synthetic Phase 1 registry fixture",
        "source_version": "phase1-fixture-v1",
        "source_page": "1",
        "source_section": "synthetic",
        "extraction_method": "manual_test_fixture",
        "reviewer": "synthetic reviewer",
        "review_date": "2026-01-01",
        "approval_status": "approved",
        "content_hash": "phase1-fixture-hash",
    }, {
        "framework": "SLKI",
        "code": "L.0001",
        "name": "Synthetic Phase 1 Outcome",
        "source_title": "Synthetic Phase 1 registry fixture",
        "source_version": "phase1-fixture-v1",
        "source_page": "1",
        "source_section": "synthetic",
        "extraction_method": "manual_test_fixture",
        "reviewer": "synthetic reviewer",
        "review_date": "2026-01-01",
        "approval_status": "approved",
        "content_hash": "phase1-fixture-hash-slki",
    }, {
        "framework": "SIKI",
        "code": "I.0001",
        "name": "Synthetic Phase 1 Intervention",
        "source_title": "Synthetic Phase 1 registry fixture",
        "source_version": "phase1-fixture-v1",
        "source_page": "1",
        "source_section": "synthetic",
        "extraction_method": "manual_test_fixture",
        "reviewer": "synthetic reviewer",
        "review_date": "2026-01-01",
        "approval_status": "approved",
        "content_hash": "phase1-fixture-hash-siki",
    }])


class Phase1PolicyTests(unittest.TestCase):
    def test_policy_redacts_required_canary_identifiers(self):
        policy = OutboundDataPolicy()
        sanitized = policy.sanitize_for_external_provider(CANARY)

        assert_no_raw_canary(self, sanitized.text)
        kinds = {d.kind for d in sanitized.detections}
        self.assertTrue({
            "patient_name",
            "email",
            "phone",
            "address",
            "date_of_birth",
            "nik",
            "bpjs",
            "medical_record_number",
        }.issubset(kinds))

    def test_clinical_measurements_and_registry_terms_are_preserved(self):
        policy = OutboundDataPolicy()
        for value in CLINICAL_MEASUREMENTS:
            with self.subTest(value=value):
                sanitized = policy.sanitize_for_external_provider(value).text
                self.assertEqual(sanitized, value)

    def test_adversarial_identifier_variants_are_redacted(self):
        policy = OutboundDataPolicy()
        for case in ADVERSARIAL_CASES:
            with self.subTest(case=case):
                sanitized = policy.sanitize_for_external_provider(case).text
                assert_no_raw_canary(self, sanitized)

    def test_policy_fails_closed_when_identifier_remains(self):
        policy = OutboundDataPolicy()
        with self.assertRaises(OutboundPolicyError):
            policy.assert_safe_for_external_provider("identifier 3273010101990001 remained")

    def test_safe_llm_sanitizes_messages_and_blocks_direct_streaming(self):
        raw = RecordingLLM()
        llm = wrap_llm(raw, OutboundDataPolicy())

        llm.invoke([SystemMessage(content="Sistem"), HumanMessage(content=CANARY)])

        self.assertEqual(len(raw.calls), 1)
        assert_no_raw_canary(self, joined_messages(raw.calls[0]))
        with self.assertRaises(OutboundPolicyError):
            llm.stream([HumanMessage(content=CANARY)])

    def test_get_llm_returns_safe_boundary(self):
        raw = RecordingLLM()
        with mock.patch.object(api, "_create_raw_llm", return_value=raw):
            llm = api.get_llm("openai", "mock", "test-key")

        self.assertIsInstance(llm, SafeLLM)
        llm.invoke([HumanMessage(content=CANARY)])
        assert_no_raw_canary(self, joined_messages(raw.calls[0]))

    def test_no_direct_streaming_path_remains_in_api(self):
        api_source = os.path.join(os.path.dirname(__file__), "..", "api.py")
        with open(api_source, encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn(".stream(", source)

    def test_audit_log_sanitizes_action_and_status_fields(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = os.path.join(td, "audit.jsonl")
            with mock.patch.object(api, "_LEDGER", ledger), mock.patch.object(api, "_last_hash", None):
                api.audit_log("session-with-phi", "Action " + CANARY, "Status " + CANARY)

            with open(ledger, encoding="utf-8") as fh:
                line = fh.read()

        assert_no_raw_canary(self, line)

    def test_console_error_log_sanitizes_canary_text(self):
        stderr = StringIO()
        with redirect_stderr(stderr):
            api._log_err(RuntimeError(CANARY))

        assert_no_raw_canary(self, stderr.getvalue())

    def test_incident_print_helpers_sanitize_path_text(self):
        stderr = StringIO()
        with redirect_stderr(stderr):
            with mock.patch.object(api, "_fail_times", api.deque()):
                for _ in range(api._INCIDENT_THRESHOLD + 1):
                    api._note_access_failure("/x/" + CANARY, 401)

        assert_no_raw_canary(self, stderr.getvalue())

    def test_medium_and_pro_review_inputs_are_sanitized(self):
        for tier in ("medium", "pro"):
            with self.subTest(tier=tier):
                raw = RecordingLLM(response="Provider echo " + CANARY)
                llm = wrap_llm(raw, OutboundDataPolicy())
                msgs = [SystemMessage(content="System " + CANARY), HumanMessage(content="Human " + CANARY)]

                agents.orchestrate_answer(llm, msgs, "Review human " + CANARY, tier)

                self.assertGreaterEqual(len(raw.calls), 2)
                assert_raw_canary_absent_from_calls(self, raw)


class Phase1EbpBoundaryTests(unittest.TestCase):
    def test_retrieve_context_deidentifies_llm_prompt_and_search_query(self):
        raw_llm = RecordingLLM(response="Nama pasien: Budi Santoso AND NIK: 3273010101990001 AND dyspnea nursing")
        llm = wrap_llm(raw_llm, OutboundDataPolicy())
        seen: dict[str, str] = {}

        def fake_retrieve(query: str, recall_text: str = "", k: int = 10):
            seen["query"] = query
            seen["recall_text"] = recall_text
            return [], ""

        with mock.patch.object(ebp, "retrieve", side_effect=fake_retrieve):
            ebp.retrieve_context(llm, CANARY)

        assert_no_raw_canary(self, joined_messages(raw_llm.calls[0]))
        assert_no_raw_canary(self, seen["query"])
        assert_no_raw_canary(self, seen["recall_text"])

    def test_ebp_query_is_compact_bounded_and_clinically_meaningful(self):
        narrative = CANARY + "\nPasien mengalami nyeri akut dan sesak napas setelah aktivitas. TD 120/80 mmHg."
        raw_llm = RecordingLLM(response="acute pain dyspnea nursing intervention evidence")
        llm = wrap_llm(raw_llm, OutboundDataPolicy())
        seen: dict[str, str] = {}

        def fake_retrieve(query: str, recall_text: str = "", k: int = 10):
            seen["query"] = query
            seen["recall_text"] = recall_text
            return [], ""

        with mock.patch.object(ebp, "retrieve", side_effect=fake_retrieve):
            ebp.retrieve_context(llm, narrative)

        query = seen["query"]
        assert_no_raw_canary(self, query)
        self.assertLessEqual(len(query), 240)
        self.assertIn("pain", query.lower())
        self.assertIn("nursing", query.lower())
        self.assertNotIn("Nama pasien", query)
        self.assertNotIn("Pasien mengalami nyeri akut dan sesak napas setelah aktivitas", query)

    def test_ebp_llm_error_falls_back_to_safe_concept_query(self):
        llm = wrap_llm(RaisingLLM(CANARY), OutboundDataPolicy())
        seen: dict[str, str] = {}

        def fake_retrieve(query: str, recall_text: str = "", k: int = 10):
            seen["query"] = query
            seen["recall_text"] = recall_text
            return [], ""

        with mock.patch.object(ebp, "retrieve", side_effect=fake_retrieve):
            ebp.retrieve_context(llm, CANARY + " nyeri sesak")

        assert_no_raw_canary(self, seen["query"])
        assert_no_raw_canary(self, seen["recall_text"])
        self.assertIn("nyeri", seen["query"])

    def test_population_script_sanitizes_payload_before_http(self):
        captured: dict[str, str] = {}

        def fake_urlopen(req, timeout=0):
            captured["body"] = req.data.decode("utf-8")
            captured["timeout"] = str(timeout)
            return MockHTTPResponse()

        with mock.patch.object(populate_sdki.request, "urlopen", side_effect=fake_urlopen):
            populate_sdki.anthropic_messages(
                api_key="test-key",
                model="mock-model",
                system="system",
                user=CANARY,
                max_tokens=100,
                timeout=1,
            )

        assert_no_raw_canary(self, captured["body"])
        self.assertNotIn("test-key", captured["body"])

    def test_population_script_preserves_registry_codes_in_payload(self):
        captured: dict[str, str] = {}

        def fake_urlopen(req, timeout=0):
            captured["body"] = req.data.decode("utf-8")
            return MockHTTPResponse()

        user = "Kode D.0005 SDKI SLKI SIKI NANDA NOC NIC tetap referensi klinis."
        with mock.patch.object(populate_sdki.request, "urlopen", side_effect=fake_urlopen):
            populate_sdki.anthropic_messages(
                api_key="test-key",
                model="mock-model",
                system="system D.0005",
                user=user,
                max_tokens=100,
                timeout=1,
            )

        for value in ("D.0005", "SDKI", "SLKI", "SIKI", "NANDA", "NOC", "NIC"):
            self.assertIn(value, captured["body"])

    def test_population_script_http_error_sanitizes_provider_detail(self):
        err = populate_sdki.error.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=500,
            msg="Server Error",
            hdrs=None,
            fp=BytesIO(CANARY.encode("utf-8")),
        )

        with mock.patch.object(populate_sdki.request, "urlopen", side_effect=err):
            with self.assertRaises(RuntimeError) as ctx:
                populate_sdki.call_with_retries(
                    api_key="test-key",
                    model="mock-model",
                    system="system",
                    user="user",
                    max_tokens=100,
                    timeout=1,
                    attempts=1,
                )

        assert_no_raw_canary(self, str(ctx.exception))

    def test_ekstraksi_error_print_sanitizes_exception_text(self):
        stdout = StringIO()
        with tempfile.TemporaryDirectory() as td:
            pdf_path = os.path.join(td, "dummy.pdf")
            open(pdf_path, "wb").close()
            with mock.patch.object(ekstraksi, "FOLDER_OUTPUT", td), \
                 mock.patch.object(ekstraksi.pdfplumber, "open", return_value=FakePdf()), \
                 mock.patch.object(ekstraksi, "panggil_llm", side_effect=RuntimeError(CANARY)), \
                 mock.patch.object(ekstraksi.time, "sleep", return_value=None), \
                 redirect_stdout(stdout):
                ekstraksi.ekstrak_buku("SDKI", pdf_path, "diagnosis")

        assert_no_raw_canary(self, stdout.getvalue())


class Phase1ApiStreamingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)

    def _session_id(self) -> str:
        data = self.client.post("/session", headers=self._headers()).json()
        self._session_headers = {"Authorization": "Bearer test-key", "X-Session-Token": data["session_token"]}
        return data["session_id"]

    def _headers(self) -> dict[str, str]:
        return getattr(self, "_session_headers", {"Authorization": "Bearer test-key"})

    def test_chat_stream_precomputes_then_emits_sanitized_chunks(self):
        raw_llm = RecordingLLM(response="Analisis selesai.\n" + CANARY)
        enabled_cfg = enabled_config()

        with mock.patch.object(api, "CONFIG", enabled_cfg), \
             mock.patch.object(api, "_create_raw_llm", return_value=raw_llm), \
             mock.patch.object(api, "framework_available", return_value=True), \
             mock.patch.object(api, "askep_refs_available", return_value=True), \
             mock.patch.object(api, "bangun_konteks", return_value=""), \
             mock.patch.object(api, "CLINICAL_REGISTRY", phase1_synthetic_registry()), \
             mock.patch.object(api.memory, "recall_block", return_value=""):
            response = self.client.post(
                "/chat_stream",
                data={
                    "provider": "openai",
                    "model": "mock",
                    "framework": "3S",
                    "session_id": self._session_id(),
                    "tier": "flash",
                    "agent": "general",
                    "pertanyaan": CANARY,
                },
                headers=self._headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(raw_llm.stream_called)
        assert_no_raw_canary(self, joined_messages(raw_llm.calls[0]))
        assert_no_raw_canary(self, response.text)

    def test_chat_stream_buffers_split_identifier_fragments_before_chunking(self):
        split_output = (
            "TD 120/80 mmHg, RR 28 x/menit. Nama pasien: Bu"
            "di Sant"
            "oso. NIK: 3273"
            "010101990001. Telepon: (0812) 3456 7890."
        )
        raw_llm = RecordingLLM(response=split_output)

        with mock.patch.object(api, "CONFIG", enabled_config()), \
             mock.patch.object(api, "_create_raw_llm", return_value=raw_llm), \
             mock.patch.object(api, "framework_available", return_value=True), \
             mock.patch.object(api, "askep_refs_available", return_value=True), \
             mock.patch.object(api, "bangun_konteks", return_value=""), \
             mock.patch.object(api, "CLINICAL_REGISTRY", phase1_synthetic_registry()), \
             mock.patch.object(api.memory, "recall_block", return_value=""):
            response = self.client.post(
                "/chat_stream",
                data={
                    "provider": "openai",
                    "model": "mock",
                    "framework": "3S",
                    "session_id": self._session_id(),
                    "tier": "flash",
                    "agent": "general",
                    "pertanyaan": "lanjutkan analisis klinis",
                },
                headers=self._headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(raw_llm.stream_called)
        assert_no_raw_canary(self, response.text)
        self.assertIn("TD 120/80 mmHg", response.text)
        self.assertIn("RR 28 x/menit", response.text)

class Phase1ApiNonStreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)

    def _session_id(self) -> str:
        data = self.client.post("/session", headers=self._headers()).json()
        self._session_headers = {"Authorization": "Bearer test-key", "X-Session-Token": data["session_token"]}
        return data["session_id"]

    def _headers(self) -> dict[str, str]:
        return getattr(self, "_session_headers", {"Authorization": "Bearer test-key"})

    def _common_patches(self, raw_llm: RecordingLLM | RaisingLLM, cfg=None):
        return mock.patch.multiple(
            api,
            CONFIG=cfg or enabled_config(),
            _create_raw_llm=mock.Mock(return_value=raw_llm),
            framework_available=mock.Mock(return_value=True),
            askep_refs_available=mock.Mock(return_value=True),
            bangun_konteks=mock.Mock(return_value=""),
            CLINICAL_REGISTRY=phase1_synthetic_registry(),
        )

    def test_chat_json_response_sanitizes_provider_output_and_memory(self):
        raw_llm = RecordingLLM(response="Jawaban raw " + CANARY)
        sid = self._session_id()

        with self._common_patches(raw_llm), mock.patch.object(api.memory, "recall_block", return_value=""):
            response = self.client.post(
                "/chat",
                data={
                    "provider": "openai",
                    "model": "mock",
                    "framework": "3S",
                    "session_id": sid,
                    "tier": "flash",
                    "agent": "analisis",
                    "pertanyaan": CANARY,
                },
                headers=self._headers(),
            )

        self.assertEqual(response.status_code, 200)
        assert_no_raw_canary(self, response.text)
        assert_raw_canary_absent_from_calls(self, raw_llm)
        assert_no_raw_canary(self, joined_messages([FakeResponse(c) for _, c in api.SESI.history(sid)]))

    def test_same_session_followup_history_reuse_does_not_reintroduce_raw_phi(self):
        raw_llm = RecordingLLM(responses=["Jawaban pertama aman.", "Jawaban kedua aman."])
        sid = self._session_id()

        with self._common_patches(raw_llm), mock.patch.object(api.memory, "recall_block", return_value=""):
            first = self.client.post(
                "/chat",
                data={"provider": "openai", "model": "mock", "framework": "3S", "session_id": sid, "tier": "flash", "agent": "analisis", "pertanyaan": CANARY},
                headers=self._headers(),
            )
            second = self.client.post(
                "/chat",
                data={"provider": "openai", "model": "mock", "framework": "3S", "session_id": sid, "tier": "flash", "agent": "analisis", "pertanyaan": "lanjutkan evaluasi nyeri dan sesak"},
                headers=self._headers(),
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        assert_raw_canary_absent_from_calls(self, raw_llm)
        assert_no_raw_canary(self, joined_messages([FakeResponse(c) for _, c in api.SESI.history(sid)]))

    def test_feedback_correction_recall_is_sanitized_before_outbound_prompt(self):
        raw_llm = RecordingLLM(response="Jawaban aman.")
        sid = self._session_id()

        with tempfile.TemporaryDirectory() as td:
            feedback_file = os.path.join(td, "feedback_memory.json")
            with mock.patch.object(memory, "_FILE", feedback_file):
                feedback = self.client.post(
                    "/feedback",
                    data={
                        "framework": "3S",
                        "session_id": sid,
                        "pertanyaan": CANARY + " keluhan nyeri sesak",
                        "jawaban": "Jawaban " + CANARY,
                        "rating": "down",
                        "koreksi": "Correction text " + CANARY,
                    },
                    headers=self._headers(),
                )
                with self._common_patches(raw_llm), mock.patch.object(api.memory, "_FILE", feedback_file):
                    response = self.client.post(
                        "/chat",
                        data={"provider": "openai", "model": "mock", "framework": "3S", "session_id": sid, "tier": "flash", "agent": "analisis", "pertanyaan": "keluhan nyeri sesak"},
                        headers=self._headers(),
                    )
                with open(feedback_file, encoding="utf-8") as fh:
                    stored = fh.read()

        self.assertEqual(feedback.status_code, 200)
        self.assertEqual(response.status_code, 200)
        assert_no_raw_canary(self, stored)
        assert_raw_canary_absent_from_calls(self, raw_llm)

    def test_analisis_fallback_json_response_sanitizes_uploaded_context(self):
        raw_llm = RecordingLLM(response="Fallback raw " + CANARY)
        sid = self._session_id()

        with self._common_patches(raw_llm), mock.patch.object(api.memory, "recall_block", return_value=""):
            response = self.client.post(
                "/analisis",
                data={"provider": "openai", "model": "mock", "framework": "3S", "session_id": sid, "tier": "flash", "gejala": CANARY},
                files={"file_dokumen": ("case.txt", CANARY.encode("utf-8"), "text/plain")},
                headers=self._headers(),
            )

        self.assertEqual(response.status_code, 200)
        assert_no_raw_canary(self, response.text)
        assert_raw_canary_absent_from_calls(self, raw_llm)

    def test_analisis_multi_json_response_sanitizes_uploaded_document_context(self):
        raw_llm = RecordingLLM(response="Multi raw " + CANARY)
        sid = self._session_id()

        with self._common_patches(raw_llm), mock.patch.object(api.memory, "recall_block", return_value=""):
            response = self.client.post(
                "/analisis_multi",
                data={"provider": "openai", "model": "mock", "framework": "3S", "session_id": sid, "tier": "flash", "agent": "analisis", "gejala": "analisis nyeri sesak"},
                files={"file_dokumen": ("case.txt", CANARY.encode("utf-8"), "text/plain")},
                headers=self._headers(),
            )

        self.assertEqual(response.status_code, 200)
        assert_no_raw_canary(self, response.text)
        assert_raw_canary_absent_from_calls(self, raw_llm)

    def test_pathway_json_response_sanitizes_reachable_mocked_output(self):
        raw_llm = RecordingLLM(response="```mermaid\nflowchart TD\nA[Nama pasien: Budi Santoso]\n```")
        cfg = enabled_config(FEATURE_EXTERNAL_LLM="true", FEATURE_MERMAID_PATHWAY_RENDERING="true")
        sid = self._session_id()

        with self._common_patches(raw_llm, cfg=cfg):
            response = self.client.post(
                "/pathway",
                data={"provider": "openai", "model": "mock", "framework": "3S", "session_id": sid, "gejala": CANARY},
                headers=self._headers(),
            )

        self.assertEqual(response.status_code, 200)
        assert_no_raw_canary(self, response.text)
        assert_raw_canary_absent_from_calls(self, raw_llm)

    def test_error_json_response_sanitizes_provider_exception(self):
        sid = self._session_id()

        with self._common_patches(RaisingLLM(CANARY)), mock.patch.object(api.memory, "recall_block", return_value=""):
            response = self.client.post(
                "/chat",
                data={"provider": "openai", "model": "mock", "framework": "3S", "session_id": sid, "tier": "flash", "agent": "analisis", "pertanyaan": "analisis nyeri"},
                headers=self._headers(),
            )

        self.assertEqual(response.status_code, 500)
        assert_no_raw_canary(self, response.text)


if __name__ == "__main__":
    unittest.main()
