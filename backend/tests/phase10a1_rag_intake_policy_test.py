from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag_intake_policy import (
    IntakeReason,
    IntakeStatus,
    SourceClass,
    validate_intake_metadata,
)


def make_valid_metadata(**kwargs) -> dict:
    base = {
        "source_id": "src-valid-123",
        "source_type": "synthetic_fixture",
        "source_title": "Synthetic Nursing Guideline",
        "source_owner_ref": "actor-opaque-1",
        "source_version": "1.0.0",
        "source_version_date": "2026-06-11",
        "license_status": "approved",
        "license_evidence_ref": "evidence-lic-123",
        "provenance_status": "approved",
        "provenance_evidence_ref": "evidence-prov-456",
        "content_hash": "a" * 64,
        "content_language": "id",
        "content_domain": "nursing",
        "synthetic_only": True,
        "contains_patient_data": False,
        "contains_phi": False,
        "deidentification_disposition": "metadata_only_sandbox",
        "clinical_review_status": "approved",
        "qa_status": "passed",
        "retrieval_eligibility": True,
        "clinical_use_allowed": False,
        "retention_policy": "sandbox_ttl",
        "created_by_actor_ref": "actor-opaque-1"
    }
    base.update(kwargs)
    return base


class P10A1RagIntakePolicyTests(unittest.TestCase):
    def test_accept_synthetic_fixture(self):
        meta = make_valid_metadata(source_type=SourceClass.SYNTHETIC_FIXTURE.value)
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.ACCEPT)
        self.assertEqual(reason, IntakeReason.ACCEPTED_SYNTHETIC_FIXTURE)
        self.assertIsNotNone(validated)

    def test_accept_reviewer_authored_synthetic(self):
        meta = make_valid_metadata(source_type=SourceClass.REVIEWER_AUTHORED_SYNTHETIC_EDUCATIONAL.value)
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.ACCEPT)
        self.assertEqual(reason, IntakeReason.ACCEPTED_REVIEWER_AUTHORED_SYNTHETIC)
        self.assertIsNotNone(validated)

    def test_reject_real_patient_document(self):
        meta = make_valid_metadata(source_type=SourceClass.REAL_PATIENT_DOCUMENT.value)
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_REAL_PATIENT_DOCUMENT)
        self.assertIsNone(validated)

    def test_reject_user_uploaded_document(self):
        meta = make_valid_metadata(source_type=SourceClass.USER_UPLOADED_DOCUMENT.value)
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_USER_UPLOAD)
        self.assertIsNone(validated)

    def test_reject_web_scraped_content(self):
        meta = make_valid_metadata(source_type=SourceClass.WEB_SCRAPED_CLINICAL_CONTENT.value)
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_WEB_SCRAPED_CONTENT)
        self.assertIsNone(validated)

    def test_reject_unclear_license(self):
        meta = make_valid_metadata(source_type=SourceClass.COPYRIGHTED_CLINICAL_STANDARD_UNCLEAR_LICENSE.value)
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_UNCLEAR_LICENSE)
        self.assertIsNone(validated)

    def test_quarantine_openly_licensed_public_guideline(self):
        # Approved licenses go to content policy review
        meta = make_valid_metadata(source_type=SourceClass.OPENLY_LICENSED_PUBLIC_GUIDELINE.value, license_status="approved", provenance_status="approved")
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.QUARANTINE)
        self.assertEqual(reason, IntakeReason.QUARANTINE_CONTENT_POLICY_REVIEW_REQUIRED)
        self.assertEqual(validated["quarantine_reason_code"], "quarantine_content_policy_review_required")

        # Pending license status quarantines for license review
        meta = make_valid_metadata(source_type=SourceClass.OPENLY_LICENSED_PUBLIC_GUIDELINE.value, license_status="pending_review", provenance_status="approved")
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.QUARANTINE)
        self.assertEqual(reason, IntakeReason.QUARANTINE_LICENSE_REVIEW_REQUIRED)

        # Pending provenance quarantines for provenance review
        meta = make_valid_metadata(source_type=SourceClass.OPENLY_LICENSED_PUBLIC_GUIDELINE.value, license_status="approved", provenance_status="pending_review")
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.QUARANTINE)
        self.assertEqual(reason, IntakeReason.QUARANTINE_PROVENANCE_REVIEW_REQUIRED)

    def test_quarantine_explicitly_licensed_standard(self):
        meta = make_valid_metadata(source_type=SourceClass.LICENSED_CLINICAL_STANDARD.value, license_status="approved", provenance_status="approved")
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.QUARANTINE)
        self.assertEqual(reason, IntakeReason.QUARANTINE_CONTENT_POLICY_REVIEW_REQUIRED)

    def test_reject_patient_data_flag(self):
        meta = make_valid_metadata(contains_patient_data=True)
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_PATIENT_DATA_FLAG)
        self.assertIsNone(validated)

    def test_reject_phi_flag(self):
        meta = make_valid_metadata(contains_phi=True)
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_PHI_FLAG)
        self.assertIsNone(validated)

    def test_reject_clinical_use_flag(self):
        meta = make_valid_metadata(clinical_use_allowed=True)
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_CLINICAL_USE_FORBIDDEN)
        self.assertIsNone(validated)

    def test_reject_synthetic_only_false(self):
        meta = make_valid_metadata(synthetic_only=False)
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_INVALID_METADATA)
        self.assertIsNone(validated)

    def test_reject_url_shaped_evidence_reference(self):
        meta = make_valid_metadata(license_evidence_ref="https://example.com/license")
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_UNSAFE_REFERENCE)

    def test_reject_path_shaped_evidence_reference(self):
        meta = make_valid_metadata(provenance_evidence_ref="/etc/passwd")
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_UNSAFE_REFERENCE)

        meta = make_valid_metadata(provenance_evidence_ref="..\\docs\\test.txt")
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_UNSAFE_REFERENCE)

    def test_reject_credential_shaped_evidence_reference(self):
        meta = make_valid_metadata(license_evidence_ref="secret=mysecrettoken")
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_UNSAFE_REFERENCE)

    def test_reject_nul_byte(self):
        meta = make_valid_metadata(source_title="Canary\x00Title")
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_CONTROL_CHARACTER)

    def test_reject_control_character(self):
        meta = make_valid_metadata(source_title="Canary\nTitle")
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_CONTROL_CHARACTER)

    def test_reject_oversized_value(self):
        meta = make_valid_metadata(source_title="A" * 300)
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_OVERSIZED_VALUE)

    def test_reject_invalid_content_hash(self):
        meta = make_valid_metadata(content_hash="not-a-hash")
        status, reason, validated = validate_intake_metadata(meta)
        self.assertEqual(status, IntakeStatus.REJECT)
        self.assertEqual(reason, IntakeReason.REJECT_INVALID_METADATA)

    def test_forbidden_keys_rejected(self):
        for key in ("body", "excerpt", "prompt", "query", "raw_query", "url", "path", "credential", "patient_identifier"):
            meta = make_valid_metadata()
            meta[key] = "some content"
            with self.subTest(key=key):
                status, reason, validated = validate_intake_metadata(meta)
                self.assertEqual(status, IntakeStatus.REJECT)
                self.assertEqual(reason, IntakeReason.REJECT_BODY_STORAGE_FORBIDDEN)


if __name__ == "__main__":
    unittest.main()
