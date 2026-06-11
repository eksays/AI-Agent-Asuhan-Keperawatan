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


Completed Phase 4 controls:

- Mermaid strict security mode and HTML labels disabled for explicitly capability-enabled rendering paths.
- Mermaid SVG output is sanitized through a strict SVG allowlist before the only allowed `dangerouslySetInnerHTML` boundary.
- Unsafe SVG payload categories including script, event handlers, `foreignObject`, iframe/srcdoc, JavaScript URLs, encoded JavaScript URL attempts, `data:text/html`, `xlink:href`, `xml:base`, nested SVG, unknown namespaces, external references, and style imports are covered by tests.
- Markdown raw HTML parsing is disabled; Markdown images are disabled; Markdown links use a narrow safe-URL allowlist and external links use `noopener noreferrer`.
- PDF/Word export HTML is sanitized again at the export boundary.
- CSP removes production `unsafe-eval`, adds `frame-src 'none'`, preserves required browser hardening directives, and narrows `img-src`.
- Frontend browser-security regression test and sink scanner are available locally.

Phase 5 controls checkpointed and merged into dev:

- Document uploads for `/analisis` and `/analisis_multi` use bounded intake and deterministic content sniffing for PDF, DOCX, and clean UTF-8 text.
- Filename extension and browser MIME type are treated as non-authoritative hints; mismatches fail closed.
- DOCX containers are validated before parsing for required OOXML members, unsafe archive paths, symlink-like entries, excessive entries, oversized expansion, compression-ratio risk, nested archives, macro/active content, executable member types, and external relationships.
- Parser libraries run in a spawned child process with wall-clock timeout, terminate/kill escalation, sanitized outcomes, and temporary workspace cleanup.
- Parser child runtime guards block sockets, URL openers, and subprocess command execution.
- Parser failures return structured `upload_status`, `accepted_upload=false`, and browser-safe messages.
- Clinical photo analysis remains default-off and unsupported server-side.
- Closure tests cover 20 sequential parser timeouts, queue close/join cleanup, parser crash containment, oversized parser result rejection, DOCX Unicode/duplicate/encrypted/member-size cases, explicit PDF active-content marker rejection, plain-text binary/encoding rejection, parent-controlled copied input, and network/process denial for socket, urllib, requests, httpx, subprocess, `os.system`, and `shell=True` attempts.

Checkpoint reconciliation:

- Phase 5 closure is accepted, checkpoint committed, and merged into `dev`.
- Phase 6 auth-security checkpoint is implemented.
- Phase 7 audit-ledger checkpoint is implemented and merged into dev
at adc712f2d44b0c0c387e2c38d0155eddfcce2d34.
Remaining missing or failing controls:

- PHI firewall completeness beyond tested canary classes and future integrations.
- Formal clinical review workflow for real/local datasets, including reviewer identity, approval records, license review, durable active release storage, and operational rollback evidence.
- Extraction-quality debugging and review for real `extraction_unverified`, `ocr_extracted`, and `llm_assisted` registry content.
- Browser-rendered QA for Mermaid/SVG hardening remains deferred unless a working Browser runtime completes visual verification.
- Hard OS-level parser CPU and memory caps before pilot or production claims.
- Portable process-tree isolation or equivalent host/container controls before stronger isolation claims.
- Full CI enforcement of Phase 1/2/3/4/5/6/7 safety gates remains incomplete.
- Dedicated validation-status UI and formal clinical/nursing validation of abstention wording.

Gate A is still not passed until registry governance is connected to formally reviewed approved release artifacts, formal clinical review workflow is completed, browser-rendered QA is completed or explicitly accepted as deferred for sandbox-only closure, hard parser resource-control and process-tree residuals are resolved or explicitly accepted for the sandbox boundary, validation-status UI and abstention wording receive formal review, and Phase 1/2/3/4/5/6/7 controls are kept enforced in CI.

Phase 2 closure verification improves deterministic clinical validation, trusted evidence containment, machine-readable abstention status, and fail-fast registry-unavailable handling for tested paths. Informal nursing-perspective feedback received on 2026-06-06 says supporting 3S and 3N documents remain insufficiently concrete because extraction issues remain; this reinforces keeping extracted registries non-authoritative and fail-closed. It does not satisfy registry governance, Mermaid/SVG hardening, isolated upload parsing, formal clinical validation, compliance review, hospital readiness, or production readiness. Browser-rendered QA remains deferred.

Phase 3 closure verification adds governance infrastructure and dry-run evidence. Phase 4 browser rendering hardening reduces tested XSS/browser-sink risk and restores the Bandit Medium 0/High 0 baseline on the synced branch, but production CSP still permits `script-src 'unsafe-inline'` and `style-src 'unsafe-inline'`; nonce/hash-based CSP architecture remains required before stronger browser-security or release-gate claims. Phase 4 does not provide formal clinical validation, license approval, active real registry releases, compliance review, hospital readiness, Gate A approval, or production readiness.

## Gate B - Controlled Pilot Candidate

Status: **Not met**

Missing or failing controls:

- All Gate A controls.
- Real user identity and RBAC / SSO / OAuth-OIDC or approved equivalent.
- Durable distributed session, MFA, token, and rate-limit state.
- Managed secret custody and rotation workflow.
- Formal clinical reviewer approval workflow.
- Approved real registry releases remain missing.
The PostgreSQL durable registry store exists as synthetic-only technical
infrastructure, but controlled-pilot operational approval, formal review,
and approved real registry activation remain absent.
- Human confirmation workflow.
- Expanded CI enforcement of build, lint, test, clinical, privacy, upload, browser, auth, audit, and safety gates.
- External ledger anchors or approved audit-storage strategy where required.

Implemented sandbox checkpoints with residuals:

- Session ownership and TTL controls are implemented in Phase 6 as in-memory sandbox controls; they are not durable distributed identity/session infrastructure.
- MFA replay protection and lockout are implemented in Phase 6 as in-memory sandbox controls; restart and distributed-state residuals remain.
- Bounded rate limiting is implemented in Phase 6 as an in-memory sandbox control; distributed enforcement remains missing.
- Local HMAC-chained tamper-evident verifier is implemented in Phase 7; it is not WORM storage, immutable storage, asymmetric non-repudiation, external anchoring, or compliance evidence.

## Gate C - Production Evaluation Candidate

Status: **Not met**

Missing or failing controls:

- All Gate B controls.
- External immutable or WORM-capable audit storage.
- Formal privacy review.
- Formal security review.
- Clinical validation study.
- Incident response process.
- Model and registry rollback procedures.
- Operational monitoring.
- Documented responsibility model.
- Legal and regulatory review.

No phase, command, or local build should be interpreted as Gate C approval.

## Phase 6 Auth-Security Checkpoint

Phase 6 local controls now available for sandbox verification:

- API keys are accepted only through `Authorization: Bearer <key>`; form, JSON, query-string, and cookie key transport is rejected or ignored safely.
- The backend derives a one-way application principal fingerprint rather than using the raw key as an owner identifier.
- Protected session routes require authenticated application principal plus server-issued `X-Session-Token`; session token digests are stored server-side.
- Sessions have absolute TTL, idle timeout, bounded max active count, cleanup, expiry rejection, delete invalidation, and reset token rotation.
- Director TOTP verification rejects same-step replay, tracks per-principal/per-IP failures, applies lockout, and returns safe `Retry-After` responses.
- Route-class rate limiting is bounded and in memory for AUTH, MFA, SESSION_MUTATION, CHAT, UPLOAD, and DIRECTOR_PRIVILEGED classes.
- Forwarded client-IP headers are ignored unless trusted proxies are explicitly configured.
- Wildcard CORS origins are rejected outside sandbox, credentials are disabled, and `X-Session-Token` is explicitly allowed.
- Non-sandbox modes fail closed for missing, weak, or placeholder `CDSS_API_KEYS`, `CDSS_SECRET_KEY`, and `DIRECTOR_BOOTSTRAP`.
- Frontend transport no longer appends `api_key` to FormData and does not use `localStorage` or `sessionStorage` for API credentials, session tokens, or director tokens.

Gate A remains **Not met**. Phase 6 does not provide durable identity, RBAC, SSO/OAuth/OIDC, distributed sessions, distributed rate limits, formal secret management, hospital readiness, controlled-pilot readiness, compliance, or production readiness.

Phase 6 closure UI smoke note: `http://localhost:3000` rendered normally in Incognito, while `http://172.16.0.2:3000` reproduced a blank page because Next.js development resources were blocked cross-origin by default. This is classified as a local development-origin configuration issue, not an application startup regression. It is not full browser-rendered QA and does not change Gate A status.

Phase 6 director-enrollment supplement: `/director/enroll` is disabled by default and is local-sandbox provisioning only when explicitly enabled. Startup no longer emits an enrollment URI. Browser-carried shared API keys remain visible to the browser and are not hospital identity, RBAC, SSO, OAuth/OIDC, controlled-pilot readiness, or production authentication. Gate A remains unmet.

## Phase 7 Audit-Ledger Checkpoint

Phase 7 local controls now available for sandbox verification:

- Structured audit records include schema version, opaque event ID, UTC timestamp, sequence, event type, actor type, actor fingerprint, route class, action, outcome, status code, security tags, allowlisted metadata, previous record MAC, record MAC, and key ID.
- Canonical JSON serialization uses sorted keys, compact separators, UTF-8, and excludes `record_mac` from authenticated bytes.
- HMAC-SHA256 chains each record to the previous record MAC and detects field mutation, reordering, middle deletion, duplicate insertion, wrong keys, malformed JSON, partial lines, sequence rollback, and previous-MAC mismatch in tests.
- Local backend appends newline-delimited records, flushes, fsyncs, and verifies persistent ledgers before append.
- Verification CLI emits safe summaries only and exits non-zero for tampered ledgers or missing/weak keys.
- Phase 7 tests prove raw synthetic PHI, API keys, session tokens, OTP/TOTP seed, director bootstrap, provider key, filesystem path, and uploaded-document body canaries are absent from ledger records.
- Closure verification proves persistent verify-before-append fails closed for mutated, reordered, middle-deleted, partial-line, malformed, and wrong-key ledgers without overwriting prior bytes. It also documents that final-record tail truncation can leave a locally valid prefix.

Residuals: this is not WORM storage, not immutable storage, not a digital signature, not asymmetric non-repudiation, not multi-process correctness, and not compliance evidence. Segment rotation is implemented, but key rotation and valid-prefix tail-truncation anchoring are not. Gate A remains **Not met**. External immutable storage, managed keys, durable centralized audit service, incident-response procedures, and formal review remain required before controlled-pilot, hospital, compliance, or production claims.

Do not enable real registry activation merely by changing REGISTRY_ACTIVATION_ENABLED.
Real activation still requires official sourcing, license review, provenance
verification, complete approved registry families, formal clinical review,
release approval, controlled operational review, browser-QA disposition,
parser host-isolation disposition, and CI evidence.

## Phase 9 P9-A RAG Foundation Checkpoint

P9-A adds default-off governed RAG corpus foundation tables, separate RAG migration journaling, read-only pgvector probing, and optional explicit admin-only pgvector schema preparation. It does not ingest real corpus bodies, copy licensed clinical content, ingest patient data, store PHI, enable product lexical retrieval, enable vector retrieval, implement hybrid retrieval, integrate embedding providers, rerank results, activate a RAG index release, or activate registry data.

Checkpoint provenance: P9-A source checkpoint `96024f43f41b1f1d9afca08b6b2d5db4b167cb9a`; P9-A dev merge `59884ecfba983d02924fb1cd4d5a81ff0af46455`; P9-A dev GitHub Actions PASS.

Gate A remains **Not met**. P9-A is not clinical validation, registry approval, corpus approval, privacy compliance, controlled-pilot readiness, hospital readiness, or production readiness.

Gate B remains **Not met** because Gate A remains unmet and identity/RBAC, durable distributed controls, formal operational review, approved corpus releases, and external audit/storage controls remain absent.

Gate C remains **Not met** because Gate B remains unmet and formal privacy/security/legal/regulatory review, clinical validation study, incident response, monitoring, and production responsibility model remain absent.

## Phase 9 P9-B Governed Synthetic Lexical RAG Checkpoint

P9-B adds governed synthetic ingestion, deterministic hierarchy-aware chunking, explicit synthetic-only PostgreSQL lexical FTS retrieval, safe citation packaging, typed abstention, and metadata-only telemetry for local and optional PostgreSQL integration testing. P9-B checkpoint `5df6af6b952d50f58b9743a42ca24d3bbf72b14e` was merged into dev at `9dbb6470fc4aea446f9108133bbd262c213113ca`; dev GitHub Actions passed after merge. It does not add a product API route, frontend integration, real corpus ingestion, licensed clinical body copying, patient data processing, PHI processing, embeddings, vector retrieval, hybrid retrieval, reranking, external provider calls, pgvector installation, optional vector migration application, Qdrant integration, or clinical registry activation.

Gate A remains **Not met**. P9-B is a sandbox technical checkpoint only and does not provide formal corpus approval, real clinical source licensing, clinical validation, browser QA completion, parser host-isolation closure, or production-grade operational review.

Gate B remains **Not met** because Gate A remains unmet and identity/RBAC, durable distributed controls, managed secret custody, formal operational review, approved real registry/corpus releases, and external audit/storage controls remain absent.

Gate C remains **Not met** because Gate B remains unmet and formal privacy/security/legal/regulatory review, clinical validation study, incident response, monitoring, and production responsibility model remain absent.

## Phase 9 P9-C Synthetic Vector Readiness Checkpoint

P9-C installed pgvector explicitly on an operator-attested isolated test database only and applied the optional vector schema explicitly for synthetic testing only. Focused P9-C tests are unittest-discovered: synthetic vectors 8, benchmark 5, red-team 9, and PostgreSQL vector integration 3. Full discovery ran 494 tests with 18 expected skips and no failures or errors. The deterministic `synthetic-hash-vector-v1` generator and exact-cosine synthetic vector baseline are retrieval infrastructure plumbing only, not semantic retrieval-quality validation, not clinical retrieval-quality validation, and not a pgvector-versus-Qdrant architecture decision. P9-C checkpoint committed at `eac151638f5f294cd21ac634c08d5bac41fe130a` was merged into dev at `8c9e0927ab26be381334a9a2222080671fb6df0f`; review-branch and dev GitHub Actions passed. Phase 9 is technically closed for synthetic infrastructure scope only. Phase 10 has not started.

Integration evidence: 54 synthetic vectors inserted across test runs, 4 exact-cosine queries, 1 lexical query, 3 benchmark runs, 6 red-team rejection checks, synthetic vector rows 0 after cleanup, synthetic corpus rows 0, staging rows 0, active synthetic pointers 0, real corpus rows 0, registry activation false, external provider calls 0.

P9-C does not add a product API route, frontend integration, real corpus ingestion, licensed clinical body copying, patient data processing, PHI processing, external embedding providers, ANN indexes, HNSW, IVFFlat, hybrid retrieval, reranking, Qdrant integration, or clinical registry activation.

Gate A remains **Not met**. P9-C is not clinical validation, corpus approval, controlled-pilot readiness, hospital readiness, production readiness, or compliance evidence.

Gate B remains **Not met** because Gate A remains unmet and identity/RBAC, durable distributed controls, managed secret custody, formal operational review, approved real registry/corpus releases, and external audit/storage controls remain absent.

Gate C remains **Not met** because Gate B remains unmet and formal privacy/security/legal/regulatory review, clinical validation study, incident response, monitoring, and production responsibility model remain absent.
