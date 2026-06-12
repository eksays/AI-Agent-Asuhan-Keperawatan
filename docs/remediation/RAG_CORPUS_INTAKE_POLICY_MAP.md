# RAG Corpus-Intake Policy Map

This document defines the policy actions and validation limits applied to source metadata submissions during RAG corpus intake.

## Source Class Dispositions

| Source Class (`source_type`) | Status | Reason Code / Action | Notes |
| :--- | :--- | :--- | :--- |
| `synthetic_fixture` | **ACCEPT** | `accepted_synthetic_fixture` | Fully synthetic test fixture. |
| `reviewer_authored_synthetic_educational` | **ACCEPT** | `accepted_reviewer_authored_synthetic` | Reviewer-authored synthetic educational text. |
| `openly_licensed_public_guideline` | **QUARANTINE** | `quarantine_license_review_required` or `quarantine_provenance_review_required` or `quarantine_content_policy_review_required` | Bounded review process. |
| `licensed_clinical_standard` | **QUARANTINE** | `quarantine_content_policy_review_required` | Requires verification of the licensing status. |
| `internal_educational_handout` | **QUARANTINE** | `quarantine_content_policy_review_required` | Requires institution-level policy verification. |
| `deidentified_retrospective_document` | **QUARANTINE** | `quarantine_content_policy_review_required` | Bounded for metadata review. |
| `real_patient_document` | **REJECT** | `reject_real_patient_document` | Strictly forbidden. |
| `user_uploaded_document` | **REJECT** | `reject_user_upload` | No user-submitted files allowed. |
| `web_scraped_clinical_content` | **REJECT** | `reject_web_scraped_content` | Strictly forbidden. |
| `copyrighted_clinical_standard_unclear_license` | **REJECT** | `reject_unclear_license` | Strictly forbidden. |
| `unknown` | **REJECT** | `reject_invalid_metadata` | Default fallback rejection. |

## Metadata Contract Boundaries

| Field | Max Length | Validations |
| :--- | :--- | :--- |
| `source_id` | 96 | Opaque pattern `[A-Za-z0-9_-]{3,96}` |
| `source_type` | 64 | Match standard enums. |
| `source_title` | 256 | Control char filter. |
| `source_owner_ref` | 128 | Opaque indicator check. |
| `source_version` | 128 | Control char filter. |
| `license_evidence_ref` | 256 | No URL, path shapes, or credential shapes. |
| `provenance_evidence_ref` | 256 | No URL, path shapes, or credential shapes. |
| `content_hash` | 64 | SHA-256 Hex matching (`^[a-fA-F0-9]{64}$`) |
| `created_by_actor_ref` | 128 | Opaque actor reference checks. |

## Explicit Rejection Reason Codes
Rejections must map to one of the following bounded reason codes:
- `accepted_synthetic_fixture`
- `accepted_reviewer_authored_synthetic`
- `quarantine_license_review_required`
- `quarantine_provenance_review_required`
- `quarantine_content_policy_review_required`
- `reject_real_patient_document`
- `reject_patient_data_flag`
- `reject_phi_flag`
- `reject_user_upload`
- `reject_web_scraped_content`
- `reject_unclear_license`
- `reject_body_storage_forbidden`
- `reject_invalid_metadata`
- `reject_unsafe_reference`
- `reject_control_character`
- `reject_oversized_value`
- `reject_clinical_use_forbidden`
