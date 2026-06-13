from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
import config  # noqa: E402


class Phase0BConfigTests(unittest.TestCase):
    def test_missing_app_mode_defaults_to_clinical_sandbox(self):
        cfg = config.load_config({})
        self.assertEqual(cfg.app_mode, "clinical_sandbox")

    def test_missing_feature_flags_default_to_disabled(self):
        cfg = config.load_config({})
        caps = config.build_capabilities(cfg)["capabilities"]
        for key in (
            "external_llm",
            "ebp_external_search",
            "clinical_photo_analysis",
            "mermaid_pathway_rendering",
        ):
            self.assertFalse(caps[key]["enabled"], key)

    def test_controlled_pilot_cannot_enable_unsafe_debug_override(self):
        with self.assertRaises(RuntimeError):
            config.load_config({
                "APP_MODE": "controlled_pilot",
                "ALLOW_UNSAFE_EXTERNAL_LLM_FOR_LOCAL_DEBUG": "true",
            })

    def test_production_cannot_enable_unsafe_debug_override(self):
        env = {name: "true" for name in config.PRODUCTION_PREREQUISITES}
        env.update({
            "APP_MODE": "production",
            "ALLOW_UNSAFE_EXTERNAL_LLM_FOR_LOCAL_DEBUG": "true",
        })
        with self.assertRaises(RuntimeError):
            config.load_config(env)

    def test_production_requires_explicit_safety_prerequisites(self):
        with self.assertRaises(RuntimeError):
            config.load_config({"APP_MODE": "production"})

    def test_malformed_app_mode_fails_closed(self):
        with self.assertRaises(RuntimeError):
            config.load_config({"APP_MODE": "prod"})

    def test_unsafe_debug_override_is_sandbox_only_and_visible(self):
        cfg = config.load_config({
            "APP_MODE": "clinical_sandbox",
            "ALLOW_UNSAFE_EXTERNAL_LLM_FOR_LOCAL_DEBUG": "true",
        })
        caps = config.build_capabilities(cfg)["capabilities"]
        self.assertTrue(caps["external_llm"]["enabled"])
        self.assertIn("Unsafe local debug override", caps["external_llm"]["reason"])


class Phase0BApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)

    def _session_id(self) -> str:
        data = self.client.post("/session", headers=self._headers()).json()
        self._session_headers = {"Authorization": "Bearer test-key", "X-Session-Token": data["session_token"]}
        return data["session_id"]

    def _headers(self) -> dict[str, str]:
        return getattr(self, "_session_headers", {"Authorization": "Bearer test-key"})

    def _deny_external_calls(self):
        def fail(*_args, **_kwargs):
            raise AssertionError("External provider or EBP connector must not be invoked in Phase 0B default mode.")

        return mock.patch.multiple(
            api,
            get_llm=fail,
            **{
                "ebp.retrieve_context": fail,
                "ebp.retrieve": fail,
            },
        )

    def test_expected_phase0b_routes_exist(self):
        paths = {getattr(route, "path", "") for route in api.app.routes}
        for path in ("/capabilities", "/chat", "/chat_stream", "/analisis", "/analisis_multi", "/pathway"):
            self.assertIn(path, paths)

    def test_capabilities_returns_server_authoritative_state(self):
        data = self.client.get("/capabilities").json()
        self.assertEqual(data["app_mode"], "clinical_sandbox")
        self.assertIn("safety_notice", data)
        self.assertFalse(data["capabilities"]["external_llm"]["enabled"])
        self.assertFalse(data["capabilities"]["mermaid_pathway_rendering"]["enabled"])
        for key in ("sdki_authoritative_grounding", "slki", "siki", "nanda", "noc", "nic"):
            self.assertFalse(data["capabilities"][key]["enabled"], key)
            self.assertTrue(data["capabilities"][key]["reason"])

    def test_external_llm_requests_are_blocked_by_default(self):
        for tier in ("flash", "medium", "pro"):
            with self.subTest(tier=tier), mock.patch.object(api, "get_llm", side_effect=AssertionError("get_llm called")):
                r = self.client.post(
                    "/chat",
                    data={
                        "provider": "openai",
                        "model": "dummy",
                        "framework": "3S",
                        "session_id": self._session_id(),
                        "tier": tier,
                        "agent": "analisis",
                        "pertanyaan": "susun diagnosis",
                    },
                    headers=self._headers(),
                )
                self.assertEqual(r.status_code, 503)
                self.assertEqual(r.json()["capability"], "external_llm")

    def test_chat_stream_is_blocked_before_provider_stream(self):
        with mock.patch.object(api, "get_llm", side_effect=AssertionError("get_llm called")):
            r = self.client.post(
                "/chat_stream",
                data={
                    "provider": "openai",
                    "model": "dummy",
                    "framework": "3S",
                    "session_id": self._session_id(),
                    "tier": "flash",
                    "agent": "analisis",
                    "pertanyaan": "susun diagnosis",
                },
                headers=self._headers(),
            )
            self.assertEqual(r.status_code, 503)
            self.assertEqual(r.json()["capability"], "external_llm")

    def test_ebp_external_requests_are_blocked_by_default(self):
        with mock.patch.object(api.ebp, "retrieve_context", side_effect=AssertionError("EBP called")):
            r = self.client.post(
                "/chat",
                data={
                    "provider": "openai",
                    "model": "dummy",
                    "framework": "3S",
                    "session_id": self._session_id(),
                    "tier": "medium",
                    "agent": "referensi",
                    "pertanyaan": "carikan jurnal EBP",
                },
                headers=self._headers(),
            )
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["capability"], "ebp_external_search")

    def test_photo_analysis_is_unavailable(self):
        with mock.patch.object(api, "get_llm", side_effect=AssertionError("get_llm called")):
            r = self.client.post(
                "/analisis_multi",
                data={
                    "provider": "openai",
                    "model": "dummy",
                    "framework": "3S",
                    "session_id": self._session_id(),
                    "tier": "medium",
                    "agent": "analisis",
                    "gejala": "analisis foto",
                },
                files={"file_foto": ("synthetic.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
                headers=self._headers(),
            )
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["capability"], "clinical_photo_analysis")

    def test_analysis_routes_with_document_are_blocked_before_llm(self):
        for path in ("/analisis", "/analisis_multi"):
            with self.subTest(path=path), mock.patch.object(api, "get_llm", side_effect=AssertionError("get_llm called")):
                r = self.client.post(
                    path,
                    data={
                        "provider": "openai",
                        "model": "dummy",
                        "framework": "3S",
                        "session_id": self._session_id(),
                        "tier": "pro",
                        "agent": "analisis",
                        "gejala": "susun analisis dari dokumen",
                    },
                    files={"file_dokumen": ("synthetic.txt", b"keluhan nyeri", "text/plain")},
                    headers=self._headers(),
                )
                self.assertEqual(r.status_code, 503)
                self.assertEqual(r.json()["capability"], "external_llm")

    def test_mermaid_pathway_is_disabled(self):
        with mock.patch.object(api, "get_llm", side_effect=AssertionError("get_llm called")):
            r = self.client.post(
                "/pathway",
                data={
                    "provider": "openai",
                    "model": "dummy",
                    "framework": "3S",
                    "session_id": self._session_id(),
                    "gejala": "buat pathway",
                },
                headers=self._headers(),
            )
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["capability"], "mermaid_pathway_rendering")
        self.assertEqual(r.json()["mermaid"], "")

    def test_network_deny_smoke_default_sandbox_routes(self):
        with mock.patch.object(api, "get_llm", side_effect=AssertionError("get_llm called")), \
             mock.patch.object(api.ebp, "retrieve_context", side_effect=AssertionError("EBP context called")), \
             mock.patch.object(api.ebp, "retrieve", side_effect=AssertionError("EBP retrieve called")):
            self.assertEqual(self.client.get("/capabilities").status_code, 200)
            sid = self._session_id()
            common = {"provider": "openai", "model": "dummy", "framework": "3S", "session_id": sid, "tier": "medium"}
            requests = [
                self.client.post("/chat", data={**common, "agent": "analisis", "pertanyaan": "susun diagnosis"}, headers=self._headers()),
                self.client.post("/chat_stream", data={**common, "agent": "analisis", "pertanyaan": "susun diagnosis"}, headers=self._headers()),
                self.client.post("/chat", data={**common, "agent": "referensi", "pertanyaan": "cari jurnal"}, headers=self._headers()),
                self.client.post("/analisis", data={**common, "gejala": "analisis"}, headers=self._headers()),
                self.client.post("/analisis_multi", data={**common, "agent": "analisis", "gejala": "analisis"}, headers=self._headers()),
                self.client.post("/pathway", data={**common, "gejala": "pathway"}, headers=self._headers()),
                self.client.post("/analisis_multi", data={**common, "agent": "analisis", "gejala": "foto"}, files={"file_foto": ("synthetic.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")}, headers=self._headers()),
            ]
        self.assertTrue(all(r.status_code == 503 for r in requests))

    def test_harvester_does_not_start_by_default(self):
        with mock.patch.object(api.harvester.ebp, "retrieve", side_effect=AssertionError("harvester network called")):
            self.assertFalse(api.harvester.start(interval=0, topics=("nursing",)))
            self.assertFalse(api.harvester.start(interval=3600, topics=()))


if __name__ == "__main__":
    unittest.main()
