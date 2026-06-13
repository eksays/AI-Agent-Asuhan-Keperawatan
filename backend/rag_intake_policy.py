"""Phase 10 P10-A1 - Governed Corpus-Intake Policy Validator.

This module defines the metadata contract and validators for governed corpus intake.
All validations are metadata-only; no body storage is allowed.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, NamedTuple


class SourceClass(str, Enum):
    SYNTHETIC_FIXTURE = "synthetic_fixture"
    REVIEWER_AUTHORED_SYNTHETIC_EDUCATIONAL = "reviewer_authored_synthetic_educational"
    OPENLY_LICENSED_PUBLIC_GUIDELINE = "openly_licensed_public_guideline"
    INTERNAL_EDUCATIONAL_HANDOUT = "internal_educational_handout"
    COPYRIGHTED_CLINICAL_STANDARD_UNCLEAR_LICENSE = "copyrighted_clinical_standard_unclear_license"
    LICENSED_CLINICAL_STANDARD = "licensed_clinical_standard"
    DEIDENTIFIED_RETROSPECTIVE_DOCUMENT = "deidentified_retrospective_document"
    REAL_PATIENT_DOCUMENT = "real_patient_document"
    WEB_SCRAPED_CLINICAL_CONTENT = "web_scraped_clinical_content"
    USER_UPLOADED_DOCUMENT = "user_uploaded_document"
    UNKNOWN = "unknown"


class IntakeStatus(str, Enum):
    ACCEPT = "accept"
    QUARANTINE = "quarantine"
    REJECT = "reject"


class IntakeReason(str, Enum):
    ACCEPTED_SYNTHETIC_FIXTURE = "accepted_synthetic_fixture"
    ACCEPTED_REVIEWER_AUTHORED_SYNTHETIC = "accepted_reviewer_authored_synthetic"
    QUARANTINE_LICENSE_REVIEW_REQUIRED = "quarantine_license_review_required"
    QUARANTINE_PROVENANCE_REVIEW_REQUIRED = "quarantine_provenance_review_required"
    QUARANTINE_CONTENT_POLICY_REVIEW_REQUIRED = "quarantine_content_policy_review_required"
    REJECT_REAL_PATIENT_DOCUMENT = "reject_real_patient_document"
    REJECT_PATIENT_DATA_FLAG = "reject_patient_data_flag"
    REJECT_PHI_FLAG = "reject_phi_flag"
    REJECT_USER_UPLOAD = "reject_user_upload"
    REJECT_WEB_SCRAPED_CONTENT = "reject_web_scraped_content"
    REJECT_UNCLEAR_LICENSE = "reject_unclear_license"
    REJECT_BODY_STORAGE_FORBIDDEN = "reject_body_storage_forbidden"
    REJECT_INVALID_METADATA = "reject_invalid_metadata"
    REJECT_UNSAFE_REFERENCE = "reject_unsafe_reference"
    REJECT_CONTROL_CHARACTER = "reject_control_character"
    REJECT_OVERSIZED_VALUE = "reject_oversized_value"
    REJECT_CLINICAL_USE_FORBIDDEN = "reject_clinical_use_forbidden"


FORBIDDEN_INPUT_KEYS = {
    "body", "excerpt", "prompt", "query", "raw_query", "url", "path",
    "credential", "credentials", "patient_identifier"
}

REQUIRED_METADATA_KEYS = {
    "source_id", "source_type", "source_title", "source_owner_ref",
    "source_version", "source_version_date", "license_status", "license_evidence_ref",
    "provenance_status", "provenance_evidence_ref", "content_hash", "content_language",
    "content_domain", "synthetic_only", "contains_patient_data", "contains_phi",
    "deidentification_disposition", "clinical_review_status", "qa_status",
    "retrieval_eligibility", "clinical_use_allowed", "retention_policy", "created_by_actor_ref"
}

ALLOWED_METADATA_KEYS = REQUIRED_METADATA_KEYS | {"quarantine_reason_code", "review_notes_code"}


class PolicyValidationResult(NamedTuple):
    status: IntakeStatus
    reason_code: IntakeReason
    validated_metadata: dict[str, Any] | None


def _check_unsafe_strings(value: str) -> bool:
    """Return True if the string contains unsafe indicators (URLs, paths, credentials)."""
    val_lower = value.lower()
    # Check URL shapes
    if any(prefix in val_lower for prefix in ("http://", "https://", "ftp://")):
        return True
    # Check Path shapes (absolute or relative backslashes/slashes with extensions or drive letters)
    if any(char in value for char in ("/", "\\", ":")) or ".." in value:
        # Exclude typical date format like YYYY-MM-DD or hash strings
        # Opaque reference identifiers shouldn't contain path separators
        return True
    # Check Credential indicators
    if any(cred in val_lower for cred in ("password=", "key=", "secret=", "token=")):
        return True
    return False


def _check_control_chars(value: str) -> bool:
    """Return True if control characters or NUL bytes are present."""
    if "\x00" in value:
        return True
    for char in value:
        if ord(char) < 32:
            return True
    return False


def validate_intake_metadata(metadata: dict[str, Any]) -> PolicyValidationResult:
    """Validate intake metadata against the safety contract."""
    # 1. Reject any forbidden storage columns/keys
    found_forbidden = FORBIDDEN_INPUT_KEYS & set(metadata.keys())
    if found_forbidden:
        return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_BODY_STORAGE_FORBIDDEN, None)

    # 2. Check for missing required metadata keys
    missing_keys = REQUIRED_METADATA_KEYS - set(metadata.keys())
    if missing_keys:
        return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_INVALID_METADATA, None)

    # 3. Check for unexpected keys
    extra_keys = set(metadata.keys()) - ALLOWED_METADATA_KEYS
    if extra_keys:
        return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_INVALID_METADATA, None)

    # 4. Strict Type & Bounds checks on safe fields
    # Booleans
    synthetic_only = metadata.get("synthetic_only")
    contains_patient_data = metadata.get("contains_patient_data")
    contains_phi = metadata.get("contains_phi")
    clinical_use_allowed = metadata.get("clinical_use_allowed")
    retrieval_eligibility = metadata.get("retrieval_eligibility")

    if not isinstance(synthetic_only, bool) or not isinstance(contains_patient_data, bool) or \
            not isinstance(contains_phi, bool) or not isinstance(clinical_use_allowed, bool) or \
            not isinstance(retrieval_eligibility, bool):
        return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_INVALID_METADATA, None)

    # Check database-level safety invariant matches
    if not synthetic_only:
        return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_INVALID_METADATA, None)
    if contains_patient_data:
        return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_PATIENT_DATA_FLAG, None)
    if contains_phi:
        return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_PHI_FLAG, None)
    if clinical_use_allowed:
        return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_CLINICAL_USE_FORBIDDEN, None)

    # String validation
    string_bounds = {
        "source_id": 96,
        "source_type": 64,
        "source_title": 256,
        "source_owner_ref": 128,
        "source_version": 128,
        "source_version_date": 32,
        "license_status": 32,
        "license_evidence_ref": 256,
        "provenance_status": 32,
        "provenance_evidence_ref": 256,
        "content_hash": 64,
        "content_language": 16,
        "content_domain": 64,
        "deidentification_disposition": 64,
        "clinical_review_status": 32,
        "qa_status": 32,
        "retention_policy": 64,
        "created_by_actor_ref": 128,
        "quarantine_reason_code": 96,
        "review_notes_code": 96
    }

    validated: dict[str, Any] = {}

    for key, max_len in string_bounds.items():
        if key in metadata:
            val = metadata[key]
            if not isinstance(val, str):
                return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_INVALID_METADATA, None)
            if len(val) > max_len:
                return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_OVERSIZED_VALUE, None)
            if _check_control_chars(val):
                return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_CONTROL_CHARACTER, None)
            if key in ("license_evidence_ref", "provenance_evidence_ref"):
                if _check_unsafe_strings(val):
                    return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_UNSAFE_REFERENCE, None)
            validated[key] = val

    # Verify SHA-256 content_hash format
    content_hash = validated.get("content_hash", "")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", content_hash):
        return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_INVALID_METADATA, None)

    # Verify Opaque source_id format
    source_id = validated.get("source_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,96}", source_id):
        return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_INVALID_METADATA, None)

    # 5. Check Source Class Policy
    source_type_raw = validated.get("source_type", "")
    try:
        source_class = SourceClass(source_type_raw)
    except ValueError:
        return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_INVALID_METADATA, None)

    # Populate verified booleans
    validated["synthetic_only"] = synthetic_only
    validated["contains_patient_data"] = contains_patient_data
    validated["contains_phi"] = contains_phi
    validated["clinical_use_allowed"] = clinical_use_allowed
    validated["retrieval_eligibility"] = retrieval_eligibility

    # Apply Policy Rules by Class
    if source_class == SourceClass.SYNTHETIC_FIXTURE:
        return PolicyValidationResult(IntakeStatus.ACCEPT, IntakeReason.ACCEPTED_SYNTHETIC_FIXTURE, validated)

    if source_class == SourceClass.REVIEWER_AUTHORED_SYNTHETIC_EDUCATIONAL:
        return PolicyValidationResult(IntakeStatus.ACCEPT, IntakeReason.ACCEPTED_REVIEWER_AUTHORED_SYNTHETIC, validated)

    if source_class in (SourceClass.REAL_PATIENT_DOCUMENT, SourceClass.USER_UPLOADED_DOCUMENT,
                        SourceClass.WEB_SCRAPED_CLINICAL_CONTENT, SourceClass.COPYRIGHTED_CLINICAL_STANDARD_UNCLEAR_LICENSE):
        # Explicit rejection classes
        reason_map = {
            SourceClass.REAL_PATIENT_DOCUMENT: IntakeReason.REJECT_REAL_PATIENT_DOCUMENT,
            SourceClass.USER_UPLOADED_DOCUMENT: IntakeReason.REJECT_USER_UPLOAD,
            SourceClass.WEB_SCRAPED_CLINICAL_CONTENT: IntakeReason.REJECT_WEB_SCRAPED_CONTENT,
            SourceClass.COPYRIGHTED_CLINICAL_STANDARD_UNCLEAR_LICENSE: IntakeReason.REJECT_UNCLEAR_LICENSE
        }
        return PolicyValidationResult(IntakeStatus.REJECT, reason_map[source_class], None)

    # Others are Quarantine
    if source_class in (SourceClass.OPENLY_LICENSED_PUBLIC_GUIDELINE, SourceClass.LICENSED_CLINICAL_STANDARD,
                        SourceClass.INTERNAL_EDUCATIONAL_HANDOUT, SourceClass.DEIDENTIFIED_RETROSPECTIVE_DOCUMENT):
        # We quarantine openly_licensed_public_guideline and others for review
        # Map reasons based on metadata review states
        license_status = validated.get("license_status", "")
        provenance_status = validated.get("provenance_status", "")
        qa_status = validated.get("qa_status", "")

        if license_status != "approved":
            validated["quarantine_reason_code"] = "quarantine_license_review_required"
            return PolicyValidationResult(IntakeStatus.QUARANTINE, IntakeReason.QUARANTINE_LICENSE_REVIEW_REQUIRED, validated)
        if provenance_status != "approved":
            validated["quarantine_reason_code"] = "quarantine_provenance_review_required"
            return PolicyValidationResult(IntakeStatus.QUARANTINE, IntakeReason.QUARANTINE_PROVENANCE_REVIEW_REQUIRED, validated)

        validated["quarantine_reason_code"] = "quarantine_content_policy_review_required"
        return PolicyValidationResult(IntakeStatus.QUARANTINE, IntakeReason.QUARANTINE_CONTENT_POLICY_REVIEW_REQUIRED, validated)

    # Catch-all
    return PolicyValidationResult(IntakeStatus.REJECT, IntakeReason.REJECT_INVALID_METADATA, None)
