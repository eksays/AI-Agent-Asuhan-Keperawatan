# Release Gates

## Gate A - Clinical Sandbox

Status: **Not met**

Completed Phase 0B controls:

- Truthful sandbox documentation and persistent sandbox labeling.
- Server-authoritative `APP_MODE` and feature availability metadata.
- Unsupported clinical photo, EBP external search, Mermaid pathway rendering, and unapproved registry grounding are disabled by default.
- Background harvester is default-off.
- Local audit wording is corrected to tamper-evident local ledger, not WORM.

Completed Phase 1 controls:

- Deterministic outbound PHI policy for tested canary identifiers.
- Safe LLM wrapper for active API model calls.
- De-identified concept-query path for EBP retrieval.
- `/chat_stream` precomputes, sanitizes, then chunks output instead of streaming raw tokens.
- Console/audit free-text fields are sanitized before logging.
- Session memory, feedback memory, correction recall, non-stream JSON routes, and reviewed utility-script payload/error paths are covered by synthetic canary tests.
- Owned backend source has a Phase 1 outbound bypass scanner with a narrow allowlist.

Completed Phase 2 controls:

- Typed clinical response schemas exist for diagnosis, outcome, intervention, supporting evidence, missing data, and validation issues.
- Deterministic clinical validator rejects malformed JSON, raw prose, Markdown-fenced JSON, duplicate keys, oversized or deeply nested provider output, malformed codes, unknown codes, code-name mismatches, wrong framework family, missing evidence, unsupported claims, contradictory numeric/negated evidence, and fabricated outcomes/interventions when registries are unavailable.
- Provider-authored evidence, validation status, nurse-review flags, registry source/version, provenance claims, and confidence claims are not trusted as clinical facts; accepted status and metadata are server-derived or overwritten from the approved registry object.
- Clinical-analysis routes fail fast before provider construction when the approved registry set is unavailable or incomplete. Missing diagnosis registry returns `registry_unavailable`; missing outcome/intervention registries return `registry_incomplete` with accepted recommendations set to false.
- Clinical-analysis API responses expose machine-readable `clinical_status`, `accepted_recommendations`, `nurse_review_required`, `message`, and `validation_issue_codes`; streamed responses expose equivalent status through response headers.
- Registry abstraction supports approved/quarantined/unavailable states with synthetic fixture validation for duplicate codes, malformed codes, missing provenance, and unapproved entries.
- `/chat`, `/chat_stream`, `/analisis_multi`, and `/analisis` apply clinical validation before returning accepted clinical analysis output.
- Invalid clinical output returns abstention with nurse-review requirement instead of accepted recommendations.

Completed Phase 3 controls:

- Registry lifecycle states and provenance schema support are implemented for governance dry runs.
- Deterministic quarantine rules cover malformed/duplicate/missing metadata, wrong component type, missing provenance, unknown license status, OCR-derived content, LLM-assisted content, extraction-unverified content, code-name conflicts, content-hash mismatch, deprecated entries, and manual quarantine.
- Dry-run registry import is default and does not mutate source files, activate registries, create approved releases, recurse arbitrary directories, import backups implicitly, or contact external providers.
- Registry import source paths are constrained to an approved import root, and registry-import parsing has explicit Phase 3 resource limits.
- Versioned release manifest and rollback abstractions reject quarantined entries, missing approval records, unknown license status, duplicate release entries, incomplete 3S/3N component families, and implicit activation.
- Local ignored SDKI data and backups dry-run as fully quarantined, zero release-eligible, and zero authoritative.
- Informal nursing feedback remains non-authoritative and cannot become an approval record.

Remaining missing or failing controls:

- PHI firewall completeness beyond tested canary classes and future integrations.
- Formal clinical review workflow for real/local datasets, including reviewer identity, approval records, license review, durable active release storage, and operational rollback evidence.
- Extraction-quality debugging and review for real `extraction_unverified`, `ocr_extracted`, and `llm_assisted` registry content.
- Mermaid/SVG hardening.
- Upload isolation with killable parser process.
- Dedicated validation-status UI and formal clinical/nursing validation of abstention wording.

Gate A is still not passed until registry governance is connected to formally reviewed approved release artifacts, Mermaid/SVG hardening and upload isolation controls are implemented and verified, and Phase 1/2/3 controls are kept enforced in CI.

Phase 2 closure verification improves deterministic clinical validation, trusted evidence containment, machine-readable abstention status, and fail-fast registry-unavailable handling for tested paths. Informal nursing-perspective feedback received on 2026-06-06 says supporting 3S and 3N documents remain insufficiently concrete because extraction issues remain; this reinforces keeping extracted registries non-authoritative and fail-closed. It does not satisfy registry governance, Mermaid/SVG hardening, isolated upload parsing, formal clinical validation, compliance review, hospital readiness, or production readiness. Browser-rendered QA remains deferred.

Phase 3 closure verification adds governance infrastructure and dry-run evidence. It does not provide formal clinical validation, license approval, active real registry releases, compliance review, hospital readiness, or production readiness.

## Gate B - Controlled Pilot Candidate

Status: **Not met**

Missing or failing controls:

- All Gate A controls.
- Clinical reviewer approval workflow.
- Approved registry releases.
- Session hardening and persistent sessions where required.
- MFA replay protection and throttling.
- Rate limiting.
- Tamper-evident audit verifier with HMAC/signature.
- Clinical regression suite.
- CI enforcement of build, lint, test, and safety gates.
- Human confirmation workflow.

## Gate C - Production Evaluation Candidate

Status: **Not met**

Missing or failing controls:

- All Gate B controls.
- External append-only audit storage.
- Formal privacy review.
- Formal security review.
- Clinical validation study.
- Incident response process.
- Model rollback process.
- Registry rollback process.
- Operational monitoring.
- Documented responsibility model.
- Legal and regulatory review.

No phase, command, or local build should be interpreted as Gate C approval.
