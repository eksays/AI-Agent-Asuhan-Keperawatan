from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_config
from rag_intake_policy import IntakeReason, IntakeStatus
from rag_intake_service import IntakeServiceError, RagIntakeService
from tests.phase10a1_rag_intake_policy_test import make_valid_metadata


class P10A1RagIntakeServiceTests(unittest.TestCase):
    def _get_base_env(self) -> dict:
        return {
            "APP_MODE": "clinical_sandbox",
            "RAG_RUNTIME_MODE": "synthetic_corpus_test",
            "REGISTRY_ACTIVATION_ENABLED": "false",
            "RAG_CORPUS_INTAKE_ENABLED": "true",
            "RAG_CORPUS_QUARANTINE_ENABLED": "true",
            "RAG_BODY_STORAGE_ENABLED": "false",
            "RAG_REAL_CORPUS_INGESTION_ENABLED": "false",
            "RAG_CORPUS_PROMOTION_ENABLED": "false",
            "RAG_QUARANTINE_METADATA_TTL_HOURS": "24",
        }

    def test_disabled_by_default(self):
        cfg = load_config({"APP_MODE": "clinical_sandbox"})
        service = RagIntakeService(cfg)
        meta = make_valid_metadata()
        with self.assertRaises(IntakeServiceError) as ctx:
            service.process_metadata_submission(meta)
        self.assertIn("Corpus intake service is disabled", str(ctx.exception))

    def test_gating_app_mode(self):
        env = self._get_base_env()
        env["APP_MODE"] = "controlled_pilot"
        # Controlled pilot rejects experimental flags
        with self.assertRaises(RuntimeError):
            load_config(env)

    def test_gating_rag_runtime_mode(self):
        env = self._get_base_env()
        env["RAG_RUNTIME_MODE"] = "disabled"
        with self.assertRaises(RuntimeError):
            load_config(env)

    def test_gating_registry_activation(self):
        env = self._get_base_env()
        env["REGISTRY_ACTIVATION_ENABLED"] = "true"
        # Intake cannot run when registry is active
        with self.assertRaises(RuntimeError):
            load_config(env)

    def test_gating_body_storage_enabled(self):
        env = self._get_base_env()
        env["RAG_BODY_STORAGE_ENABLED"] = "true"
        with self.assertRaises(RuntimeError):
            load_config(env)

    def test_gating_real_corpus_ingestion_enabled(self):
        env = self._get_base_env()
        env["RAG_REAL_CORPUS_INGESTION_ENABLED"] = "true"
        with self.assertRaises(RuntimeError):
            load_config(env)

    def test_gating_corpus_promotion_enabled(self):
        env = self._get_base_env()
        env["RAG_CORPUS_PROMOTION_ENABLED"] = "true"
        with self.assertRaises(RuntimeError):
            load_config(env)

    def test_process_submission_accept(self):
        cfg = load_config(self._get_base_env())
        service = RagIntakeService(cfg)
        meta = make_valid_metadata(source_type="synthetic_fixture")
        result = service.process_metadata_submission(meta)
        self.assertEqual(result.status, IntakeStatus.ACCEPT)
        self.assertEqual(result.reason_code, IntakeReason.ACCEPTED_SYNTHETIC_FIXTURE)
        self.assertIsNotNone(result.decision_event)

        event = result.decision_event
        self.assertTrue(event.event_id.startswith("EVT-INTAKE-"))
        self.assertEqual(event.source_id, meta["source_id"])
        self.assertEqual(event.status, "accept")
        self.assertEqual(event.reason_code, "accepted_synthetic_fixture")
        self.assertEqual(event.created_by_actor_ref, meta["created_by_actor_ref"])
        self.assertEqual(event.quarantine_reason_code, "")
        self.assertIsNone(event.cleanup_after)
        self.assertIsNotNone(event.created_at)

    def test_process_submission_quarantine(self):
        cfg = load_config(self._get_base_env())
        service = RagIntakeService(cfg)
        meta = make_valid_metadata(source_type="openly_licensed_public_guideline", license_status="pending_review")
        result = service.process_metadata_submission(meta)
        self.assertEqual(result.status, IntakeStatus.QUARANTINE)
        self.assertEqual(result.reason_code, IntakeReason.QUARANTINE_LICENSE_REVIEW_REQUIRED)
        self.assertIsNotNone(result.decision_event)

        event = result.decision_event
        self.assertEqual(event.status, "quarantine")
        self.assertEqual(event.reason_code, "quarantine_license_review_required")
        self.assertEqual(event.quarantine_reason_code, "quarantine_license_review_required")
        self.assertIsNotNone(event.cleanup_after)

        # Verify TTL is within 24 hours of now
        delta = event.cleanup_after - event.created_at
        self.assertAlmostEqual(delta.total_seconds(), 24 * 3600, delta=10)

    def test_process_submission_reject_forbidden_payloads(self):
        cfg = load_config(self._get_base_env())
        service = RagIntakeService(cfg)
        meta = make_valid_metadata()

        result_body = service.process_metadata_submission(meta, body_payload="some forbidden body text")
        self.assertEqual(result_body.status, IntakeStatus.REJECT)
        self.assertEqual(result_body.reason_code, IntakeReason.REJECT_BODY_STORAGE_FORBIDDEN)
        self.assertIsNone(result_body.decision_event)

        result_excerpt = service.process_metadata_submission(meta, excerpt_payload="some forbidden excerpt")
        self.assertEqual(result_excerpt.status, IntakeStatus.REJECT)
        self.assertEqual(result_excerpt.reason_code, IntakeReason.REJECT_BODY_STORAGE_FORBIDDEN)
        self.assertIsNone(result_excerpt.decision_event)

    def test_decision_event_safety_audit(self):
        cfg = load_config(self._get_base_env())
        service = RagIntakeService(cfg)
        meta = make_valid_metadata()
        result = service.process_metadata_submission(meta)
        event = result.decision_event
        self.assertIsNotNone(event)

        # Audit that no forbidden terms or credentials/stacktraces exist inside fields
        forbidden_keywords = (
            "body", "excerpt", "prompt", "query", "raw_query", "url", "path",
            "credential", "credentials", "patient_identifier", "secret", "password"
        )

        # Check field values of decision event object
        event_dict = event._asdict()
        for field_name, value in event_dict.items():
            if isinstance(value, str):
                for keyword in forbidden_keywords:
                    self.assertNotIn(keyword, value.lower(), f"Forbidden keyword '{keyword}' found in field '{field_name}' value '{value}'")


if __name__ == "__main__":
    unittest.main()
