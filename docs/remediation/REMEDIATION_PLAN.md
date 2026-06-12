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
   - Status: applied on 2026-06-06 for tested document-upload parser isolation and hostile-file rejection; closure accepted, checkpoint committed, and merged into `dev`.
   - Use content sniffing and magic bytes.
   - Parse in a killable process with bounded parser limits; hard OS-level CPU/RAM caps remain residual work.
   - Disable unsupported clinical photo analysis.

7. **Phase 6 - Authentication, Session Security, Secrets, MFA, and Rate Limits**
   - Status: applied and checkpoint committed; merged into `dev` based on `git merge-base --is-ancestor 36efc613556c706fe89fe2af5f14abd05850c1f9 origin/dev` returning exit code 0.
   - Remove API keys from request bodies.
   - Authenticate and authorize session mutation endpoints.
   - Add TOTP replay prevention, lockout, and rate limits.

8. **Phase 7 - Audit Ledger Redesign**
   - Status: applied, checkpoint committed, merged into `dev` at `adc712f`.
   - Rename local ledger honestly as tamper-evident only.
   - Add HMAC/signature and verifier tooling.
   - Separate local and production storage adapters.

9. **Phase 8 - Complete and Govern Clinical Registries**
   - Status:
     - P8-A committed and pushed at: 4050791ebae94739fbdefd25f75346c548020de6
     - P8-BE committed and pushed at: 34c5797a0d0464fc429a15777e9299b970d5d297
     - P8-F committed at: 34808a8823e224bcf4ccb9ca6d7d8ba48750d12d
     - P8-F CI follow-up committed at: 04dee8c55d786e2c6cc32360f78d557c2e7d127e
     - Phase 8 merged into dev at: 281738e3bbf824f565c820dd21cd31a876474b86
     - Dev GitHub Actions passed.
     - No real registry imported.
     - No real registry activated.
     - Operator activation remains false.
   - Add durable registry store and manifest schema (P8-A).
   - Add clinical review queue and approval artifacts (P8-B).
   - Add governed import and extraction-quality reporting (P8-C).
   - Add persistent release activation, active pointer, and rollback (P8-D).
   - Add startup integration and server-authoritative registry metadata (P8-E).
   - Add CI enforcement, migrations, backup, recovery, concurrency, and closure (P8-F).
   - Import only approved reference data with provenance and clinical review.

10. **Phase 9 - Governed RAG Corpus Foundation, Retrieval, and Explainability**
- Status: P9-C checkpoint committed at `eac151638f5f294cd21ac634c08d5bac41fe130a` was merged into dev at `8c9e0927ab26be381334a9a2222080671fb6df0f`; review-branch and dev GitHub Actions passed. Phase 9 is technically closed for synthetic infrastructure scope only. Gate A/B/C remain unmet, and Phase 10 has not started. pgvector was installed and optional vector schema applied on an isolated test database only. Focused unittest counts are synthetic vectors 8, benchmark 5, red-team 9, and PostgreSQL vector integration 3; full discovery ran 494 tests with 18 expected skips and no failures or errors. No product route, frontend integration, external providers, real corpus ingestion, patient data, PHI, licensed clinical body copying, or registry activation is added.
- P9-A adds separate RAG migrations, migration checksum journal, bounded explicit migration lock, read-only pgvector probe, optional admin-only pgvector migration path, and metadata-only governance tables.
- P9-A source checkpoint: `96024f43f41b1f1d9afca08b6b2d5db4b167cb9a`; P9-A dev merge: `59884ecfba983d02924fb1cd4d5a81ff0af46455`; P9-A dev GitHub Actions: PASS.
- P9-B adds generated synthetic fixture ingestion, deterministic hierarchy-aware chunking, PostgreSQL lexical FTS retrieval, citation packaging, typed abstention, and metadata-only telemetry for explicit synthetic tests.
- P9-B checkpoint `5df6af6b952d50f58b9743a42ca24d3bbf72b14e` was merged into dev at `9dbb6470fc4aea446f9108133bbd262c213113ca`; P9-B dev GitHub Actions passed.
- P9-C adds deterministic `synthetic-hash-vector-v1` plumbing and an exact-cosine synthetic vector baseline for infrastructure benchmarking only. Integration inserted 54 synthetic vectors across test runs, executed 4 exact-cosine queries, 1 lexical query, 3 benchmark runs, and 6 red-team rejection checks; cleanup verified synthetic vector rows 0, staging rows 0, active synthetic pointers 0, real corpus rows 0, registry activation false, and external provider calls 0. It makes no semantic retrieval-quality claim, no clinical retrieval-quality claim, no pgvector-versus-Qdrant decision, and adds no ANN index, HNSW, IVFFlat, hybrid retrieval, reranking, or Qdrant.
    - Later Phase 9 slices may add governed real-corpus approval, product integration, and clinically meaningful benchmarks only after safety review.

11. **Phase 10 - EBP Retrieval, OCR, Feedback Governance, and Reliability**
    - Govern EBP/OCR/feedback and complete release reliability gates.

## Phase Boundaries

Changes made in Phase 0A are limited to `docs/remediation/*` evidence files. Production backend/frontend logic remains unchanged.

Phase 0B changes are intentionally limited to truthful sandbox configuration, server-authoritative capability metadata, frontend fail-closed rendering, background harvester default-off configuration, and documentation corrections. Phase 0B does not implement the PHI firewall, typed clinical validation, registry quarantine, Mermaid hardening, isolated upload parsing, session hardening, MFA hardening, or production audit storage.

Phase 1 changes are intentionally limited to outbound data policy, mocked-provider canary tests, EBP concept-query de-identification, safe LLM wrapping, safe output chunking for `/chat_stream`, and log/audit free-text sanitization. Phase 1 does not implement typed clinical schemas, registry quarantine, Mermaid hardening, isolated upload parsing, authentication hardening, MFA hardening, or production audit storage.

Phase 2 changes are intentionally limited to typed clinical response schemas, deterministic clinical validation, trusted evidence binding, server-owned status/provenance fields, a fixture-friendly registry abstraction, fail-fast approved-registry checks, API-boundary abstention for clinical analysis output, synthetic adversarial tests, and nursing review documentation. Phase 2 does not approve local registry data, implement governed registry import/release workflow, enrich SDKI/SLKI/SIKI/NANDA/NOC/NIC datasets, optimize prompts for more diagnoses, add embeddings/vector databases, harden Mermaid, isolate parsers, change authentication/MFA/rate limits, redesign the audit ledger, or enable external capabilities by default.

Phase 9 P9-A changes are intentionally limited to default-off governed RAG corpus foundation tables, safe configuration, read-only pgvector probing, and explicit admin-only migrations. P9-A does not modify Phase 8 registry migrations, edit frontend files, enable product retrieval, implement hybrid retrieval, add reranking, integrate embedding providers, ingest real or licensed corpus bodies, ingest patient data, use PHI, activate RAG index releases, activate registry data, or satisfy Gate A/B/C.

Phase 9 P9-C changes are intentionally limited to synthetic vector readiness and infrastructure benchmarking. P9-C does not modify frontend files, CI YAML, `backend/api.py`, or `backend/registry_migrations.py`; does not add product API routes, external embedding providers, Qdrant, ANN indexes, HNSW, IVFFlat, hybrid retrieval, reranking, real corpus ingestion, licensed clinical body copying, patient data, PHI, or registry activation; and does not satisfy Gate A/B/C.

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
- Gate A remains unmet after Phase 5 closure acceptance and checkpointing. Remaining blockers include resource-control residuals resolved or explicitly accepted for sandbox-only use, browser-rendered QA disposition settled, formal registry/clinical review, and all Phase 1-7 controls enforced in CI.

## Phase 6 Implementation Notes

Phase 6 is limited to authentication, session ownership, MFA replay resistance, bounded in-memory rate limiting, CORS-adjacent transport, frontend secret transport, and secret-loading fail-closed behavior. It does not add OAuth/OIDC/SSO, Redis, database migrations, cloud secret management, audit-ledger redesign, OCR, embeddings, retrieval, prompt tuning, or infrastructure deployment code.

Implemented scope:

- Added `backend/security_controls.py` with Bearer parsing, constant-time API-key comparison, keyed credential fingerprints, server-safe security statuses, session-token digest helpers, conservative client-IP handling, and bounded in-memory rate limiting.
- Updated `backend/config.py` so `controlled_pilot` and `production` reject missing/weak/placeholder API keys, server secret, and director bootstrap values; wildcard CORS is rejected outside sandbox.
- Replaced active session handling with `SecureSessionMemory`: server-issued `session_id`, per-session secret token, token digest storage, owner binding, TTL, idle timeout, max active session bound, cleanup, delete invalidation, and reset token rotation.
- Updated protected API routes to require Authorization plus `X-Session-Token` where session reuse or mutation is involved; body/query/cookie API-key transport is rejected or ignored safely.
- Hardened director MFA with accepted-step replay detection, per-principal/per-IP failure counters, lockout, and `Retry-After`; `/director/enroll` uses `X-Director-Bootstrap` rather than query secrets.
- Removed frontend API-key FormData transport and browser storage persistence for API credentials, session tokens, and director tokens.
- Added Phase 6 runtime and static scanner tests, including frontend transport tests.

Residuals:

- Session, MFA replay, director-token, and rate-limit state are in memory only and reset on process restart.
- Shared API keys are application credentials, not hospital user identity or RBAC.
- No cloud secret manager, OAuth/OIDC/SSO, Redis, durable session store, or distributed rate limiter exists in this phase.
- Gate A remains unmet; no controlled-pilot, hospital, compliance, or production-readiness claim is made.

## Phase 6 Director Enrollment Supplement

The director enrollment boundary is explicitly local-sandbox-only. The API no longer prints an enrollment URI at startup. `/director/enroll` requires all of the following: `APP_MODE=clinical_sandbox`, `DIRECTOR_ENROLLMENT_ENABLED=true`, a configured `DIRECTOR_BOOTSTRAP`, a matching `X-Director-Bootstrap` header, and no existing director TOTP seed. Body, query-string, FormData, and cookie bootstrap fallbacks are rejected. Controlled-pilot and production provisioning workflows remain undefined and out of scope.

Browser-carried shared API keys remain visible to the browser client. Header-only transport is a leak-reduction measure, not a confidential server-side credential model.

## Phase 7 Implementation Notes

Phase 7 is limited to tamper-evident audit ledger hardening. It adds a structured event schema, canonical JSON serialization, HMAC-SHA256 record chaining, safe actor fingerprinting, bounded allowlisted metadata, local append-only writes with flush/fsync, a verification CLI, and local segment rotation linkage.

Closure hardening adds direct tests for canonical field coverage, non-finite JSON rejection, append fail-closed behavior on mutated/reordered/malformed/wrong-key ledgers, valid-prefix tail-truncation limitations, path normalization and unsafe file-type rejection, privileged audit failure semantics, recursion safety, and expanded PHI/secret canaries.

The ledger remains a local sandbox evidence control only. It is not WORM storage, not immutable filesystem storage, not a digital signature, and not asymmetric non-repudiation. A host administrator with both ledger and key access can still rewrite history. A valid-prefix tail truncation may still verify locally without an external checkpoint/footer/archive. Segment rotation is implemented; key rotation is not implemented. Multi-process correctness is not claimed; a durable centralized ledger service or external immutable archive remains required before controlled-pilot, compliance, hospital, or production claims.

## Phase 10 P10-A1 Implementation Notes

Phase 10 P10-A1 is limited to the metadata-only governed corpus-intake contract and quarantine-decision foundation.

Implemented scope:
- Added experimental flags in `backend/config.py` and `backend/.env.example` (default-off).
- Added `backend/rag_intake_policy.py` containing explicit enums for source classes, status outcomes, safe field limits, character/nul checks, opaque references, and classification rules.
- Added `backend/rag_intake_service.py` to evaluate metadata-only submissions, calculate cleanup TTL, and emit in-memory decision events.
- Appended `MIGRATION_RAG_CORE_V008` migration SQL in `backend/rag_migrations.py` containing schema definitions for companion tables `rag_intake_submissions`, `rag_intake_decision_events`, and `rag_intake_quarantine_records`.
- Added unit tests for policy, service gating, and static migrations.

Residuals:
- Static migration definitions are committed but remain unapplied. No PostgreSQL mutation has been executed. P10-A1 is not merged into dev, and P10-A2 has not started.
- No document bodies or excerpts are stored.
- Real corpus ingestion, licensed clinical body copying, patient data, and PHI are forbidden.
- Gate A, B, and C remain unmet. Not patient-care software, not clinically validated, not hospital-ready, not production-ready, and not compliant.
