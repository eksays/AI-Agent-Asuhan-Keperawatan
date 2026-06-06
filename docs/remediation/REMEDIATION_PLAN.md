# Remediation Plan

Phase 0A preflight was performed on 2026-06-06 local time. No production logic was changed.

## Current Verdict

The repository is a clinical sandbox candidate only. Phase 0B fail-closed containment, Phase 1 outbound PHI containment, and Phase 2 typed clinical validation/abstention have been applied for tested paths, but the system is not production-ready, not compliance-proven, not clinically validated, and not safe for autonomous clinical decision-making.

## Proposed Phase Sequence

1. **Phase 0B - Truthful Sandbox Mode and Immediate Risk Reduction**
   - Status: applied on 2026-06-06 for default sandbox mode and capability containment.
   - Add explicit `APP_MODE=clinical_sandbox` default.
   - Add server-authoritative capability metadata and disable unsupported features.
   - Remove overstated README/compliance/WORM/photo-analysis claims.
   - Add persistent UI sandbox notice.

2. **Phase 1 - Outbound PHI Firewall and Safe Streaming**
   - Status: applied on 2026-06-06 for tested outbound canary classes and active streaming path.
   - Centralize outbound data policy.
   - Route all model and EBP calls through one wrapper.
   - Sanitize before every external call, including review passes.
   - Precompute, sanitize, validate, then stream.

3. **Phase 2 - Typed Clinical Schema, Registry Validation, and Abstention**
   - Status: applied on 2026-06-06 for typed schema validation, synthetic-fixture registry validation, trusted evidence binding, server-authoritative validation status, fail-fast approved-registry handling, and safe abstention. Informal nursing-perspective feedback was recorded with a disclaimer on 2026-06-06; it is not formal clinical approval.
   - Add typed clinical response schemas.
   - Validate generated codes against approved synthetic registry fixtures.
   - Reject unsupported, malformed, untraceable, registry-invalid, or raw-prose clinical recommendations.
   - Implement abstention for insufficient evidence or unavailable approved registry data.

4. **Phase 3 - Dataset Quarantine and Clinical Governance**
   - Add registry lifecycle states and provenance metadata.
   - Quarantine invalid, LLM-assisted, OCR-derived, or unapproved entries.
   - Disable missing datasets instead of simulating them.

5. **Phase 4 - Mermaid, Markdown, and Browser Rendering Hardening**
   - Switch Mermaid to strict mode.
   - Sanitize generated SVG before DOM insertion.
   - Tighten markdown link protocols and CSP.

6. **Phase 5 - Isolated Document Upload Parsing**
   - Use content sniffing and magic bytes.
   - Parse in a killable process with hard resource limits.
   - Disable unsupported clinical photo analysis.

7. **Phase 6 - Authentication, Session Security, Secrets, MFA, and Rate Limits**
   - Remove API keys from request bodies.
   - Authenticate and authorize session mutation endpoints.
   - Add TOTP replay prevention, lockout, and rate limits.

8. **Phase 7 - Audit Ledger Redesign**
   - Rename local ledger honestly as tamper-evident only.
   - Add HMAC/signature and verifier tooling.
   - Separate local and production storage adapters.

9. **Phase 8 - Complete and Govern Clinical Registries**
   - Import only approved reference data with provenance and clinical review.

10. **Phase 9 - Hybrid Retrieval and Explainability**
    - Add hybrid retrieval and objective evaluation without replacing deterministic validation.

11. **Phase 10 - EBP Retrieval, OCR, Feedback Governance, and Reliability**
    - Govern EBP/OCR/feedback and complete release reliability gates.

## Phase Boundaries

Changes made in Phase 0A are limited to `docs/remediation/*` evidence files. Production backend/frontend logic remains unchanged.

Phase 0B changes are intentionally limited to truthful sandbox configuration, server-authoritative capability metadata, frontend fail-closed rendering, background harvester default-off configuration, and documentation corrections. Phase 0B does not implement the PHI firewall, typed clinical validation, registry quarantine, Mermaid hardening, isolated upload parsing, session hardening, MFA hardening, or production audit storage.

Phase 1 changes are intentionally limited to outbound data policy, mocked-provider canary tests, EBP concept-query de-identification, safe LLM wrapping, safe output chunking for `/chat_stream`, and log/audit free-text sanitization. Phase 1 does not implement typed clinical schemas, registry quarantine, Mermaid hardening, isolated upload parsing, authentication hardening, MFA hardening, or production audit storage.

Phase 2 changes are intentionally limited to typed clinical response schemas, deterministic clinical validation, trusted evidence binding, server-owned status/provenance fields, a fixture-friendly registry abstraction, fail-fast approved-registry checks, API-boundary abstention for clinical analysis output, synthetic adversarial tests, and nursing review documentation. Phase 2 does not approve local registry data, implement governed registry import/release workflow, enrich SDKI/SLKI/SIKI/NANDA/NOC/NIC datasets, optimize prompts for more diagnoses, add embeddings/vector databases, harden Mermaid, isolate parsers, change authentication/MFA/rate limits, redesign the audit ledger, or enable external capabilities by default.

## Phase 0B Closure Notes

Phase 0B closure verification confirmed fail-closed containment with default-disabled unsafe capabilities and network-deny tests for the relevant default route paths. This checkpoint remains rollback-friendly and does not stage ignored local registry data, runtime logs, generated caches, or local secrets.

Operational follow-ups:

- Browser-rendered QA is deferred because the Browser runtime exposed no available browser client; HTTP-level validation is not a substitute for rendered interaction testing.
- Frontend lint remains at the Phase 0A baseline of 7 errors and 6 warnings; no unrelated lint cleanup is included in Phase 0B closure.
- Node v24.0.2 is the current local runtime. Production/pilot runtime standardization should choose and document an approved Node LTS version.
- Future `compileall` baseline commands should reliably exclude `backend/venv`, `__pycache__`, and generated artifacts. The requested closure command still traversed `backend/venv` despite the exclusion expression.

## Phase 1 Closure Notes

Phase 1 verification used mocks only. External capabilities remain disabled by default, and the unsafe local debug override remains a sandbox-only mechanism. The outbound policy detects the required canary categories and common Indonesian identifiers, but it is not complete PHI detection and must not be described as compliance-grade.

Closure review expanded Phase 1 proof to include sanitized session-memory writes, follow-up history reuse, feedback/correction storage and recall, non-stream JSON routes, buffered streaming with split identifiers, clinical measurement preservation, adversarial synthetic identifiers, EBP query minimization, log/ledger/exception handling, utility-script error handling, and owned-backend bypass scanning.

Operational follow-ups:

- Add the Phase 1 canary suite to CI before any controlled pilot claim.
- Keep external LLM and EBP disabled by default until later release gates also pass.
- Proceed next to typed clinical schema validation and abstention; do not improve recall or completeness by forcing model output.
- Maintain `docs/remediation/PHI_BOUNDARY_MAP.md` whenever outbound paths change.

## Phase 2 Closure Notes

Phase 2 verification used mocked providers and synthetic registry fixtures only. The default registry remains unavailable, so real/local clinical data is not treated as authoritative. Clinical analysis responses must parse as a bounded raw JSON object and pass deterministic registry/evidence checks before being rendered as validated recommendations. Provider-authored evidence must bind back to trusted patient input or extracted document text; provider-authored validation status, nurse-review flags, registry source/version, provenance, and confidence claims are overwritten or rejected. Malformed provider prose, Markdown-fenced JSON, duplicate keys, invented codes, wrong framework family, missing evidence, contradictory numeric/negated evidence, missing or incomplete approved registries, and fabricated outcomes/interventions trigger abstention.

Partial registry availability contract for Phase 2 closure: complete care-plan abstention is the selected interim safe default. For 3S, approved SDKI without approved SLKI and SIKI returns `registry_incomplete`; for 3N, approved NANDA without approved NOC and NIC returns `registry_incomplete`. `accepted_recommendations=false` and `nurse_review_required=true` are preserved. Nursing-informatics review should assess whether the abstention wording is understandable and appropriate for the workflow.

Informal nursing-perspective feedback received on 2026-06-06 stated that supporting 3S and 3N documents are not yet concrete enough because extraction of writing remains problematic, so the resulting documents are not yet maximal. This feedback is recorded as non-authoritative nursing-informatics design input only. It does not approve registries, clinical behavior, compliance, legal readiness, hospital readiness, or production use.

The strict Phase 2 policy remains unchanged after the feedback: missing, unapproved, quarantined, or extraction-unverified SDKI/SLKI/SIKI/NANDA/NOC/NIC registries require complete care-plan abstention. Diagnosis-only accepted output remains disallowed in the normal hospital-facing workflow, and missing outcomes/interventions must not be completed from model memory.

Extraction-quality debugging and governed quarantine/review workflow are deferred to Phase 3 and Phase 8. Phase 2 documents `extraction_unverified`, `ocr_extracted`, and `llm_assisted` as non-authoritative states only; it does not implement the full registry lifecycle workflow.

Operational follow-ups:

- Create the governed registry import, quarantine, clinical review, approval, release, and rollback workflow in Phase 3 before treating any dataset as authoritative.
- In Phase 3, quarantine extraction-unverified, OCR-derived, and LLM-assisted registry content until extraction debugging, provenance verification, clinical content review, and release approval are complete.
- Keep abstention behavior visible; do not bypass it by adding prompt-only instructions or second-pass LLM audits.
- Preserve machine-readable `clinical_status`, `accepted_recommendations`, `nurse_review_required`, and `validation_issue_codes` in clinical API responses.
- Consider a minimal validation-status UI later, but do not hide validation failures.
- Preserve the recorded nursing-perspective feedback in `docs/remediation/NURSING_REVIEW_PHASE2.md`; treat it as design input, not formal clinical validation.
- Gate A remains unmet until registry governance, Mermaid hardening, and isolated upload parsing are completed and verified.
