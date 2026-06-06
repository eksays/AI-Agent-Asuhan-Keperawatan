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
   - Status: applied on 2026-06-06 for governance infrastructure, dry-run import, deterministic quarantine rules, release-manifest validation, and rollback abstraction using synthetic fixtures only.
   - Add registry lifecycle states and provenance metadata.
   - Quarantine invalid, LLM-assisted, OCR-derived, or unapproved entries.
   - Disable missing datasets instead of simulating them.

5. **Phase 4 - Mermaid, Markdown, and Browser Rendering Hardening**
   - Status: applied on 2026-06-06 for tested browser rendering sinks, strict Mermaid settings, SVG sanitization, Markdown raw-HTML disabling, safe URL validation, export HTML sanitization, CSP tightening, and sink scanning.
   - Switch Mermaid to strict mode.
   - Sanitize generated SVG before DOM insertion.
   - Tighten markdown link protocols and CSP.

6. **Phase 5 - Isolated Document Upload Parsing**
   - Status: applied locally on 2026-06-06 for tested document-upload parser isolation and hostile-file rejection; closure review evidence has been prepared, but no checkpoint commit has been created yet.
   - Use content sniffing and magic bytes.
   - Parse in a killable process with bounded parser limits; hard OS-level CPU/RAM caps remain residual work.
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

## Phase 3 Closure Notes

Phase 3 verification uses synthetic fixtures and local dry-run metadata only. It does not import, modify, stage, or activate real local registry files.

Implemented scope:

- Added a governance model with explicit lifecycle states, mandatory provenance fields, quarantine reason codes, and dry-run import reporting.
- Added importer source-path safety, registry import resource limits, canonical content hashing, and batch duplicate/conflict detection across explicit import files.
- Added a versioned release manifest and rollback abstraction that rejects quarantined entries, missing approval records, unknown license status, implicit activation, incomplete 3S/3N component families, and duplicate release entries across component manifests.
- Added synthetic registry governance fixtures and tests covering OCR-derived, LLM-assisted, extraction-unverified, under-review, malformed, duplicate, missing-provenance, unknown-license, hash-mismatch, deprecated, and manually quarantined entries.
- Added safe local dry-run reports for ignored SDKI files. All local SDKI current/backups remain quarantined, not release eligible, and non-authoritative.

Out of scope for Phase 3:

- No real registry activation.
- No formal clinical approval.
- No license approval.
- No OCR implementation or parser isolation changes.
- No Mermaid hardening, authentication changes, retrieval changes, embeddings, or external capability enablement.
- No Gate A claim yet.

Closure review evidence added after conditional acceptance:

- Explicit source file import is allowed; directory import excludes backups by default.
- Traversal, absolute outside-root paths, symlink-resolved escapes, unsupported extensions, missing files, oversized files, deep JSON, excessive entries, and oversized fields fail closed.
- Canonical hashes remain stable across harmless JSON formatting changes and change when stable clinical content changes.
- Candidate and approved-for-activation release artifacts do not become active until explicit activation is called.
- Complete 3S and 3N release families are required before framework activation can proceed.
- API grounding remains unavailable unless a synthetic complete registry is injected in tests; Phase 2 validation still applies.

Active release storage remains an in-memory test abstraction. A durable governed release store remains required before any controlled pilot claim.

Next phase remains Phase 4 only after Phase 3 closure review. Phase 8 remains required for completing and validating governed clinical registries.

## Phase 4 Closure Notes

Phase 4 verification is frontend/browser-rendering hardening only. It does not enable Mermaid, EBP, external LLM, clinical photo analysis, OCR, embeddings, retrieval, upload parsing, authentication/session/MFA/rate limits, Redis, audit-ledger redesign, registry activation, prompt tuning, or UI redesign.

Implemented scope:

- Mermaid is configured with strict security mode and HTML labels disabled when explicitly capability-enabled in controlled paths.
- Mermaid SVG output is treated as untrusted and sanitized through a DOMPurify SVG allowlist before insertion.
- Sanitization failure renders an inert fallback instead of the original SVG.
- Markdown raw HTML parsing is disabled by removing `rehypeRaw`; Markdown links pass through a narrow safe-URL allowlist; Markdown images are disabled.
- Exported PDF/Word HTML is re-sanitized at the export boundary and title text is escaped.
- CSP removes production `unsafe-eval`, adds `frame-src 'none'`, keeps required `object-src`, `base-uri`, `form-action`, and `frame-ancestors` directives, and narrows `img-src`.
- A Phase 4 bypass scanner documents allowed raw DOM sinks and flags unsafe protocols or sink regressions.
- Closure review expanded static/unit coverage for SVG namespace handling, nested SVG rejection, `xml:base`/`xlink:href`, encoded and control-character URL schemes, Mermaid callback/HTML-label-like SVG output, export re-sanitization, and source-wide frontend sink scanning.
- The dev Bandit B310 hotfix is now an ancestor of the Phase 4 branch; local Bandit reports Medium 0 and High 0.

Residuals:

- Production CSP still permits `script-src 'unsafe-inline'` and `style-src 'unsafe-inline'`. Nonce/hash-based CSP architecture remains required before stronger browser-security or release-gate claims.
- Browser-rendered QA must be recorded honestly as passed or deferred depending on runtime availability.
- Gate A remains unmet until upload parser isolation and all gate evidence are completed and verified.

## Phase 5 Implementation Notes

Phase 5 is limited to backend document-upload parsing and hostile-file handling for `/analisis` and `/analisis_multi`. It does not change registry governance, browser-security design, authentication/session/MFA/rate limits, Redis, audit-ledger architecture, OCR quality, embeddings, retrieval ranking, prompts, or frontend layout. External LLM, EBP, Mermaid, clinical-photo analysis, and authoritative registry grounding remain disabled by default.

Implemented scope:

- Added `backend/upload_security.py` with bounded intake, deterministic content sniffing, explicit type allowlist, DOCX ZIP validation, spawned parser child process, timeout termination, sanitized parser outcomes, temporary workspace cleanup, and child runtime guards for sockets, URL openers, and subprocess command execution.
- Added explicit upload parser limits in `backend/config.py`: 10 MiB upload bytes, 180-character filenames, 50,000 extracted characters, 30 PDF pages, 100 DOCX entries, 5 MiB total DOCX expansion, 2 MiB single-entry DOCX expansion, 100:1 DOCX compression ratio, 20-second parser timeout, and 100 KiB parser result payload.
- Replaced the `/analisis` and `/analisis_multi` document path with `extract_upload_document`, preserving PHI redaction after extraction and returning structured upload errors before provider construction.
- Preserved default-off clinical photo analysis and did not add OCR or image analysis.
- Added synthetic adversarial tests for valid PDF/DOCX/text, spoofed extensions, MIME mismatch, generic ZIP, traversal, macro content, nested archives, zip-bomb indicators, page and extracted-text limits, parser crash, parser hang termination, cleanup, network deny, route integration, and owned-source bypass scanning.
- Closure review expanded tests for 20 sequential parser timeouts, queue cleanup, oversized parser result payloads, parent-controlled copied input, Unicode traversal variants, encrypted ZIP members, duplicate DOCX entries, active PDF markers, invalid UTF-8/NUL/control-character text, requests/httpx/getaddrinfo/os.system denial, raw parser exception containment, and structured route-level oversize errors.

Residuals:

- The parser boundary is killable but not a full OS sandbox; hard CPU and memory caps remain required before pilot or production claims.
- Process-tree isolation is not claimed; stronger host/container controls remain required for portable descendant-process containment even though the tested child guard blocks subprocess creation.
- Parser libraries still execute inside a child process and must remain covered by dependency review and crash tests.
- Frontend accept hints are not authoritative and may be narrowed later, but server-side validation is the safety control.
- Gate A remains unmet until Phase 5 closure review accepts the evidence, resource-control residuals are resolved or explicitly accepted for sandbox-only use, browser-rendered QA disposition is settled, and all Phase 1-5 controls remain enforced.
