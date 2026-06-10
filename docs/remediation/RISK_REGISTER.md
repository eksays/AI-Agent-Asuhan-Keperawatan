# Risk Register

Checkpoint references:

- Phase 0B = `cef16b14166ebc5ad19b67c1a607bbdd9054956a`
- Phase 1 = `1fd224367457e7db50e15d1cc87d76d599c4e2ff`
- frontend lint-clean = `a3f11dcd36c7c5c2b5d4504104514a6578fbe324`
- Phase 2 = `f08592ca493ff00f1693b63315e49b68d0c4c09c`
- Phase 3 = `f9678a61ca44e55a4003e98039a1a185a314feab`
- Phase 4 = `681175b485ef17a08c2b0b62fdb246b6b66f7f05`
- Phase 5 = `cc42bec837d5e5458bf768fae6f2da26d1966d62`
- Phase 6 = `36efc613556c706fe89fe2af5f14abd05850c1f9`
- Phase 7 = `52eb16d1916bb6089a2e342e3da54f6efe9549d4`
- Phase 8A = 4050791ebae94739fbdefd25f75346c548020de6
- Phase 8BE = 34c5797a0d0464fc429a15777e9299b970d5d297
- Phase 8F = 34808a8823e224bcf4ccb9ca6d7d8ba48750d12d
- Phase 8 CI follow-up = 04dee8c55d786e2c6cc32360f78d557c2e7d127e
- Phase 8 dev merge = 281738e3bbf824f565c820dd21cd31a876474b86

Phase 0A documentation evidence has no separate checkpoint commit recorded here.

| ID | Domain | Severity | Evidence | Affected Files | Impact | Root Cause | Proposed Fix | Acceptance Test | Status | Residual Risk |
|---|---|---|---|---|---|---|---|---|---|---|
| SEC-PHI-001 | Privacy / outbound data | Critical | EBP receives raw canary in `api.py`; medium/pro review reinserts raw `human` in `agents.py`; `/analisis` fallback passes raw `data` to `single_askep`. | `backend/api.py`, `backend/agents.py`, `backend/ebp.py`, `backend/phi.py` | PHI can reach external LLM or search services. | Redaction is scattered and output-focused; no centralized outbound policy. | Add `OutboundDataPolicy`; sanitize before every external call; remove raw `human` from review passes. | Mock all providers and assert canary identifiers never leave policy boundary. | Confirmed | Existing sanitizer is incomplete and should not be called compliance-grade. |
| SEC-PHI-002 | Privacy / streaming | Critical | Monkeypatched flash stream returned raw name and NIK to browser before output redaction. | `backend/api.py` | Browser receives unsanitized model output. | Direct token streaming path emits before final sanitization/validation. | Precompute, sanitize, validate, then chunk for sandbox/pilot modes. | SSE test asserts canary never appears in chunks. | Confirmed | Dev-only raw streaming must be explicitly gated if retained. |
| SEC-UPL-001 | Upload security | Critical | Parsing uses `ThreadPoolExecutor(...).result(timeout=...)`; worker thread cannot be killed if parser hangs. | `backend/api.py` | Malicious document can tie up server resources. | Timeout is not an isolation boundary. | Parse in terminable process/container with CPU/RAM/time limits. | Hanging parser fixture is terminated and temp files cleaned. | Confirmed | No page/decompression/character limits beyond first 30 pages. |
| SEC-UPL-002 | Upload security | High | Parser branches on `filename.endswith(...)`, not content type/magic bytes. | `backend/api.py` | Spoofed files may reach unsafe parsers or be silently accepted/ignored. | Extension trusted as type signal. | Sniff magic bytes/container structure and fail closed. | Spoofed `.pdf` and `.docx` rejected with safe error. | Confirmed | Current frontend accept list is only a hint. |
| SEC-XSS-001 | Browser security | Critical | Historical issue: Mermaid used `securityLevel: "loose"` and assigned rendered SVG to `innerHTML`; CSP permitted production eval. Phase 4 now adds strict Mermaid mode, DOMPurify SVG sanitization, safe URL validation, export re-sanitization, and production removal of `unsafe-eval`. | `frontend/components/ui/mermaid.tsx`, `frontend/lib/svg-sanitize.ts`, `frontend/lib/safe-url.ts`, `frontend/lib/export.ts`, `frontend/next.config.mjs`, `frontend/components/messages.tsx` | LLM-controlled pathway and Markdown/export content can become browser XSS surfaces if sanitizer boundaries regress. | Untrusted diagram/rendered HTML output needs explicit allowlisted sink boundaries. | Keep Mermaid default-off, strict mode, SVG/URL/export sanitizers, CSP residual tracking, and bypass scanner. | Malicious Mermaid/SVG/Markdown/export payload tests are inert; Bandit baseline Medium 0/High 0 remains restored. | Partially mitigated | Production CSP still permits `script-src 'unsafe-inline'` and `style-src 'unsafe-inline'`; nonce/hash-based CSP architecture remains required before stronger browser-security or release-gate claims. Browser-rendered QA remains environment-dependent and must not be claimed if deferred. |
| CLI-VAL-001 | Clinical safety | Critical | LLM output is accepted as strings; no Pydantic clinical schema or deterministic post-generation code validation. | `backend/api.py`, `backend/agents.py` | Plausible but unsupported recommendations can be accepted. | Prompt/audit-pass used as final authority. | Add typed schemas, registry validator, evidence links, abstention. | Malformed/unknown/code-name mismatch cases fail deterministically. | Confirmed | Clinical review remains required even after schema validation. |
| CLI-VAL-002 | Clinical registry | Critical | Local SDKI has 152 entries, 2 invalid codes (`D.xxxx`, `D.L`), 152 missing framework/provenance markers, 35 missing objective major signs. | `backend/data_terstruktur/SDKI.json` (ignored local data), `backend/scripts/populate_sdki.py` | Invalid/incomplete data can ground clinical output. | No approved registry lifecycle or loader quarantine. | Versioned registry loader with quarantine and approval states. | Invalid entries quarantined; only approved data used. | Confirmed | Current registry is untracked and not reproducible from git. |
| SEC-API-001 | API key handling | High | Frontend appends `api_key` to every FormData while also sending Authorization header; backend accepts form fallback. | `frontend/lib/api.ts`, `backend/api.py` | API keys may appear in body logs/proxies. | Legacy compatibility preserved without server-side deprecation. | Require Authorization header; remove form key; scrub logs. | Request body contains no API key in tests. | Confirmed | TLS requirements outside local dev are not enforced. |
| SEC-SES-001 | Session security | High | `/reset` accepts arbitrary `session_id` and returns 200 for fake ID; `/delete_my_data` has no auth header and relies on session ID possession. | `backend/api.py`, `frontend/lib/api.ts` | Session manipulation/deletion boundary is weak. | Session ID is treated as sole authority and reset lacks validation. | Add authenticated/authorized mutation endpoints, TTL, owner scoping, rate limits. | Unknown/unauthorized reset/delete fail. | Confirmed | Current sessions are in-memory and vanish on restart. |
| SEC-MFA-001 | Authentication | High | TOTP verifier has no attempt counters, lockout, IP/user throttling, or replay prevention. | `backend/director.py`, `backend/api.py` | Director login can be brute-forced over time; valid codes can be reused in window. | Stateless TOTP verification. | Track last accepted counter and throttled attempts; audit failures. | Replayed TOTP fails; failed attempts trigger lockout. | Confirmed | Local secret file exists outside git and needs operational handling. |
| SEC-AUD-001 | Audit logging | High | Historical ledger was a local SHA-256 hash chain named/described as WORM; Phase 7 replaces active storage with an HMAC-chained local ledger and removes the plain-hash block. | `backend/api.py`, `backend/audit_ledger.py`, `README.md` | Local attacker with file and key access can still rewrite history; local filesystem can still delete/truncate records. | Local storage has no external immutable anchor or managed key custody. | Keep HMAC verifier, add external immutable archive/attestation and managed key custody before pilot. | Tamper verifier detects modification/reorder/invalid HMAC; closure test documents valid-prefix tail-truncation limitation. | Partially mitigated | Not WORM, not immutable, not non-repudiation, not compliance evidence; valid-prefix tail truncation requires external checkpoint/archive to detect. |
| CLI-IMG-001 | Clinical safety / UI truthfulness | High | Backend adds only a note for `file_foto`; UI exposes gallery/camera clinical image actions. | `backend/api.py`, `frontend/components/dashboard.tsx`, `frontend/components/ui/claude-style-ai-input.tsx` | Nurse may believe photo was analyzed. | Feature exists in UI without validated OCR/vision pipeline. | Disable photo analysis visibly and server-side until validated. | Photo upload disabled or returns explicit unsupported capability. | Confirmed | OCR/vision needs separate privacy and clinical validation. |
| CLI-RAG-001 | Retrieval quality | Medium | `bangun_konteks` and EBP cache recall use lexical token overlap; no embedding/reranker/rule validation. | `backend/api.py`, `backend/ebp.py` | Relevant diagnoses/evidence may be missed or misranked. | Lexical-only retrieval and prompt-based selection. | Hybrid retrieval with registry filters and objective evaluation. | Hybrid retrieval beats lexical baseline on agreed test set. | Confirmed | Do not improve recall before safety validators are in place. |
| OPS-DEP-001 | Dependencies | Medium | Backend `requirements.txt` has unpinned packages; frontend has lockfile but several `package.json` ranges. | `backend/requirements.txt`, `frontend/package.json`, `frontend/package-lock.json` | Builds are not reproducible, Python dependency risk cannot be audited exactly. | No pinned/locked backend dependency set. | Pin backend deps or add lock/constraints; keep frontend lock enforced. | Fresh install reproduces exact versions; SCA runs against lock/constraints. | Confirmed | `pip-audit` unavailable locally. |
| OPS-CI-001 | CI / release gates | High | CI only runs Bandit and npm audit. Local lint fails. No backend tests, frontend build, clinical/security regression suite, Semgrep, PHI canary tests. | `.github/workflows/security-scan.yml`, frontend source | Unsafe changes can merge. | Release gates are incomplete. | Expand CI gates phase by phase. | CI blocks lint/build/test/security/clinical failures. | Confirmed | Bandit is installed in CI but unavailable locally. |
| OPS-HRV-001 | Operations / outbound network | Medium | `harvester.start(audit_log)` runs at app import; default interval is weekly and enabled unless env <=0. | `backend/api.py`, `backend/harvester.py` | Background network activity may occur unexpectedly. | Default-on background harvester. | Default off; require explicit feature flag and outbound policy. | Import does not start network worker unless enabled. | Confirmed | Phase 0A tests disabled it with `HARVEST_INTERVAL_SEC=0`. |
| DOC-TRUTH-001 | Documentation truthfulness | High | README claims production-grade, official-grade, no hallucinated codes, HIPAA/UU PDP compliance, WORM ledger, clinical photos. | `README.md`, `backend/Dockerfile` comments | Users may overtrust sandbox. | Documentation overstates unverified capabilities. | Rewrite docs for clinical sandbox, human review, partial registry, tamper-evident local ledger. | Forbidden claims absent unless evidence-backed. | Confirmed | Must avoid replacing claims with new unsupported compliance language. |

## Phase 0B Status Update

| ID | Phase 0B Status | Evidence | Residual Risk |
|---|---|---|---|
| DOC-TRUTH-001 | Mitigated for README/container comments | README rewritten as clinical sandbox documentation; Dockerfile comment no longer claims production-grade; backend ledger comments now say tamper-evident local ledger, not WORM. | Other UI/legal phrasing still needs review in later auth/audit phases. |
| CLI-IMG-001 | Mitigated for default sandbox | Backend rejects photo analysis with 503 when disabled; frontend disables gallery/camera upload surfaces by capability metadata. | Real OCR/vision pipeline remains unimplemented and must stay unavailable. |
| OPS-HRV-001 | Mitigated for default sandbox | Harvester startup is now default-off and config-driven with interval 0 unless explicitly configured. | Harvester still needs outbound policy and de-identification before being enabled. |
| CLI-VAL-002 | Contained, not remediated | `/capabilities` marks all authoritative registry grounding disabled even though ignored local SDKI data is present. | Registry loader, provenance, quarantine, licensing review, and clinical approval remain unresolved. |
| SEC-AUD-001 | Wording mitigated; design partially mitigated | Positive WORM wording removed from README/backend comments; Phase 7 adds HMAC-chained verification and removes active plain-hash ledger code. | No external append-only storage, managed key custody, asymmetric signature, or valid-prefix truncation anchor yet. |
| SEC-PHI-001 / SEC-PHI-002 | Not remediated | External LLM/EBP are disabled by default, but no outbound PHI firewall or safe streaming implementation exists. | If unsafe debug override is enabled with real patient data, PHI exposure risk remains. |

## Phase 0B Closure Residuals

| Risk | Severity | Status | Next Action |
|---|---|---|---|
| Phase 0B is containment, not a PHI firewall | Critical | Default unsafe execution is blocked, but no deterministic outbound data policy exists. | Phase 1 |
| Browser-rendered QA deferred | Medium | No Browser client was available; HTTP-level validation is not rendered interaction validation. | Re-run browser QA before pilot/gate claims. |
| Lint baseline unresolved | Medium | Lint remains 7 errors and 6 warnings, same count as Phase 0A. | Address in quality/CI gate work without mixing into Phase 0B. |
| Node runtime standardization | Medium | Local tests used Node v24.0.2, not an explicitly approved production/pilot runtime. | Select and document approved Node LTS runtime. |
| Compileall exclusion reliability | Low | Requested compileall command exited 0 but still traversed `backend/venv`. | Use a verified exclusion command or explicit source list. |

## Phase 1 Status Update

| ID | Phase 1 Status | Evidence | Residual Risk |
|---|---|---|---|
| SEC-PHI-001 | Mitigated for tested outbound boundaries | `backend/outbound_policy.py` centralizes deterministic outbound sanitization; API LLM calls return `SafeLLM`; EBP receives de-identified concept text; extraction utilities sanitize outbound model payloads. Phase 1 tests assert canaries do not reach mocked LLM, EBP, or Anthropic HTTP bodies. | Detection is not complete and is not compliance proof. External capabilities remain disabled by default. Future outbound integrations must use the same policy and canary tests. |
| SEC-PHI-002 | Mitigated for active `/chat_stream` path | Direct `llm.stream(...)` was removed from `backend/api.py`; `/chat_stream` precomputes output, sanitizes for browser, then emits chunks. Test asserts raw mocked stream is not called and response text excludes canaries. | Clinical schema validation is still absent, so safe streaming here means PHI containment, not clinical correctness. |
| SEC-AUD-001 | Privacy aspect partially mitigated | `_log_err()` and `audit_log()` sanitize free-text values before console/ledger output; Phase 1 test writes canary action/status to a temporary ledger and checks raw canaries are absent. | Ledger design remains local tamper-evident only, without HMAC/signature, protected key, external append-only storage, or hardened verifier. |
| CLI-RAG-001 | Privacy aspect partially mitigated for EBP | `retrieve_context()` converts case text to de-identified concept query before LLM query generation and search retrieval. | Retrieval remains lexical/basic and should not be treated as quality-improved or citation-governed. |
| CLI-VAL-001 | Not remediated | Phase 1 does not add typed clinical output schemas or deterministic registry validation. | Phase 2 remains required before clinical output can be accepted as structured recommendations. |

## Phase 1 Closure Residuals

| Risk | Severity | Status | Next Action |
|---|---|---|---|
| Regex PHI detection is incomplete | High | Tested against required synthetic canaries and variants, but unlabeled names, uncommon addresses, OCR distortions, and non-Indonesian identifiers can still pass. | Keep external capabilities disabled by default; expand canary fixtures as new patterns are found. |
| False positive redaction can remove useful clinical text | Medium | Long numeric strings and some label-adjacent tokens may be redacted conservatively. Clinical measurement preservation tests reduce but do not eliminate this risk. | Review false positives during Phase 2 schema work and clinician sandbox testing. |
| Local session and feedback memory are sanitized but not full data governance | High | Raw canaries no longer persist in tested session/feedback paths; storage remains local/in-memory or encrypted local file. | Phase 6 session design and Phase 10 feedback governance remain required. |
| Bypass scanner is allowlist-based | Medium | Scanner fails on new outbound primitives outside reviewed files, but allowlist line numbers must be maintained when files change. | Add scanner to CI and update allowlist only with security review. |
| Utility scripts still generate non-authoritative clinical data | Critical | Utility outbound payloads/errors are sanitized, but generated registry content remains unapproved. | Phase 3/8 registry quarantine, provenance, clinical review, and release workflow. |
| Gate A remains unmet | High | Phase 1 closure improves PHI containment and safe buffered streaming only. | Complete Phase 2, Phase 4, and Phase 5 controls before Gate A claims. |

## Phase 2 Status Update

| ID | Phase 2 Status | Evidence | Residual Risk |
|---|---|---|---|
| CLI-VAL-001 | Partially mitigated with closure hardening | `backend/clinical_schema.py` and `backend/clinical_validator.py` add typed clinical response models, deterministic parse/schema checks, registry lookup, trusted evidence binding, server-derived status fields, and safe abstention. `/chat`, `/chat_stream`, `/analisis_multi`, and `/analisis` apply validation for clinical analysis outputs and expose machine-readable clinical status. Phase 2 closure tests cover malformed JSON, raw prose, Markdown-fenced JSON, duplicate JSON keys, oversized/deeply nested output, `D.xxxx`, `D.L`, unknown codes, code-name mismatch, wrong framework family, missing evidence, contradictory numeric/negated evidence, provider-authored status/provenance attempts, fail-fast registry unavailable behavior, and invented-code API rejection. | This is deterministic containment, not clinical validation certification. The default registry remains unavailable, so real clinical recommendations abstain unless a controlled approved fixture is supplied. Nursing review is still mandatory. |
| CLI-VAL-002 | Contained for authoritative use, not remediated as governance | `backend/clinical_registry.py` distinguishes approved, quarantined, and unavailable entries and rejects duplicates, malformed codes, missing framework/name, missing provenance, unapproved, and quarantined entries in synthetic fixtures. Local ignored registry files are not approved, committed, or allowed to activate grounding. API routes fail fast before provider construction with `registry_unavailable` when diagnosis registry is missing and `registry_incomplete` when outcome/intervention registries are missing. Informal nursing-perspective feedback on 2026-06-06 states supporting 3S/3N documents are not concrete enough because writing extraction remains problematic. | Phase 3 still must implement governed import/review/release/rollback workflow. Existing SDKI and future extracted 3S/3N data remain non-authoritative, may be incomplete/invalid, and must stay inactive until extraction debugging, provenance verification, clinical review, and release approval are complete. |
| SEC-PHI-002 | Extended for clinical validation path | `/chat_stream` now validates the complete clinical analysis output before chunking. Malformed clinical prose streams abstention text rather than accepted recommendations. | Streaming transport is safer for clinical recommendations, but Mermaid/XSS hardening and upload-parser isolation remain unresolved. |

## Phase 2 Closure Residuals

| Risk | Severity | Status | Next Action |
|---|---|---|---|
| Schema validity is not clinical correctness | Critical | Pydantic and registry checks can reject malformed or unsupported output but cannot prove a recommendation is clinically appropriate. | Nursing review, clinical validation study, and governed registry release workflow remain required. |
| Default registry is unavailable | High | `CLINICAL_REGISTRY` defaults to unavailable and only synthetic fixtures are approved in tests. | Phase 3/8 registry governance and reviewer approval. |
| Raw provider prose is rejected for clinical analysis | Medium | This improves safety but may reduce apparent feature completeness until model output is structured and approved registries exist. | Add structured generation prompts only after validators are authoritative; do not bypass abstention. |
| Evidence binding is deterministic containment only | High | It preserves numeric measurements and negation for tested synthetic cases, but does not prove clinical reasoning correctness or complete natural-language entailment. | Nursing review and clinical validation study remain required before pilot/production claims. |
| Provider-authored confidence is not authoritative | Medium | `confidence_band` is overwritten to `unknown` for accepted diagnoses unless future deterministic confidence rules exist; invalid values fail schema validation. | Define clinical confidence policy only with governance/reviewer input. |
| Informal nursing feedback is not formal validation | High | Nursing-perspective feedback was received on 2026-06-06 with a disclaimer that 3S/3N supporting documents remain insufficiently concrete due to extraction issues. | Keep registries non-authoritative; complete Phase 3 quarantine/review workflow and Phase 8 governed registry validation before activation. |
| Complete care-plan abstention wording still needs formal review | Medium | Interim policy reduces automation-bias risk by not accepting diagnosis-only output when SLKI/SIKI or NOC/NIC are missing; informal feedback did not constitute formal clinical approval. | Use the recorded feedback to refine wording later, then conduct formal clinical validation before pilot/production claims. |
| Frontend renders abstention as ordinary markdown | Medium | Existing frontend can display the abstention text, but it does not yet have a dedicated validation-status UI. | Minimal UI status work may be considered later without hiding failures. |
| Gate A remains unmet | High | Phase 2 adds basic schema/registry validation, but registry quarantine workflow, Mermaid hardening, and isolated upload parsing remain incomplete. | Continue to Phase 3/4/5 as separate closures. |

## Phase 3 Status Update

| ID | Phase 3 Status | Evidence | Residual Risk |
|---|---|---|---|
| CLI-VAL-002 | Governance infrastructure added, real data still not approved | `backend/registry_governance.py` adds lifecycle/provenance/quarantine controls, source-path safety, import resource limits, canonical hashing, and batch duplicate/conflict handling; `backend/scripts/registry_import.py` dry-runs local data without activation; `backend/registry_release.py` validates release manifests, complete framework release sets, and rollback. Local ignored SDKI dry-run: 152 entries, 152 quarantined, 2 malformed-code records, 0 release-eligible, 0 authoritative. | Real SDKI/SLKI/SIKI/NANDA/NOC/NIC content still requires formal source licensing, provenance verification, clinical review, approval records, durable release storage, release artifacts, and operational activation controls. |
| CLI-VAL-001 | Strict abstention preserved | Phase 3 regression tests verify local ignored registry presence does not activate grounding and incomplete 3S registry set returns `registry_incomplete` with no accepted recommendations. | Schema/quarantine checks still do not prove clinical correctness. Formal clinical validation remains required. |
| OPS-CI-001 | More tests available, not yet CI-enforced | `backend/tests/phase3_registry_governance_test.py` covers dry-run import, quarantine, release validation, rollback, network-deny, and Phase 2 abstention regression. | CI still needs expansion to enforce Phase 1/2/3 tests before release claims. |

## Phase 3 Closure Residuals

| Risk | Severity | Status | Next Action |
|---|---|---|---|
| Governance model is not a real registry approval | Critical | Phase 3 creates controls and testable abstractions only. No real registry has license approval, formal clinical review, or active release status. | Phase 8 governed registry completion and formal review. |
| Active release pointer is in-memory for tests | High | Rollback behavior and complete-family activation are testable, but no durable release-store adapter exists. | Add persistent governed release storage before controlled pilot. |
| Local SDKI data remains extraction-unverified | High | Dry-run quarantines all local SDKI current/backups and reports extraction/provenance gaps. | Phase 3/8 extraction debugging, provenance verification, content review, and release approval. |
| Informal nursing feedback remains non-authoritative | Medium | Feedback is documented as disclaimer/design input only. | Formal clinical review workflow and approval records remain required. |
| Gate A remains unmet | High | Registry governance infrastructure exists, but Mermaid hardening and upload isolation remain incomplete. | Continue to Phase 4 and Phase 5 after Phase 3 closure. |

## Phase 4 Status Update

| ID | Phase 4 Status | Evidence | Residual Risk |
|---|---|---|---|
| SEC-XSS-001 | Partially mitigated for tested browser rendering sinks | Mermaid now uses strict mode and post-render SVG sanitization; Markdown raw HTML parsing is disabled; unsafe Markdown links become inert; Markdown images are disabled; export HTML is sanitized; CSP removes production `unsafe-eval`; Phase 4 browser-security tests passed. | Production CSP still permits `script-src 'unsafe-inline'` and `style-src 'unsafe-inline'`; nonce/hash-based CSP architecture remains required before stronger browser-security or release-gate claims. Browser-rendered QA must be completed with an available browser runtime before release-gate claims. |

## Phase 4 Residuals

| Risk | Severity | Status | Next Action |
|---|---|---|---|
| CSP inline allowances remain | Medium | Production `script-src` and `style-src` still include `unsafe-inline`; `unsafe-eval` is dev-only. | Add nonce/hash-based CSP when the Next.js rendering path is prepared for it. |
| Sanitized Mermaid SVG still uses a raw insertion boundary | Medium | Boundary is explicit and scanner-limited to sanitized Mermaid SVG only. | Keep the scanner in CI and review any Mermaid dependency/config changes. |
| Export HTML remains an HTML serialization boundary | Medium | Export HTML is re-sanitized and link-cleaned before insertion/serialization. | Keep export sanitizer tests and avoid adding new export sources without review. |
| Browser-rendered QA may remain environment-dependent | Medium | Static/unit verification is complete; visual QA must not be claimed if Browser runtime is unavailable. | Re-run with Browser plugin active before Gate A or pilot claims. |
| Gate A remains unmet | High | Phase 4 addresses browser rendering only; upload isolation and remaining gate evidence are incomplete. | Continue to Phase 5 after closure. |

## Phase 5 Status Update

| ID | Phase 5 Status | Evidence | Residual Risk |
|---|---|---|---|
| SEC-UPL-001 | Partially mitigated for tested upload parser paths | `backend/upload_security.py` parses documents through a spawned child process with wall-clock timeout, termination/kill escalation, sanitized parser outcomes, child runtime guards for sockets/URL openers/subprocess command execution, and temporary workspace cleanup. `/analisis` and `/analisis_multi` use the structured parser result before provider construction. | This is a killable process boundary, not a full OS sandbox. Portable CPU and memory quotas are not implemented yet. Parser libraries still run with inherited package code inside the child process. |
| SEC-UPL-002 | Partially mitigated for tested content-type spoofing cases | Upload dispatch now uses PDF signature, DOCX OOXML container structure, or clean UTF-8 text. Filename extension and browser MIME type are not authoritative; mismatches fail closed. Tests cover valid PDF/DOCX/text, fake PDF, fake DOCX, generic ZIP, image-as-PDF, executable-as-text, empty file, binary garbage, and MIME mismatch. | Frontend accept hints still include some legacy extensions, but backend remains authoritative. Future upload surfaces must call the same parser boundary. |
| CLI-IMG-001 | Preserved fail-closed behavior | Phase 5 API regression confirms `file_foto` still returns `clinical_photo_analysis` unavailable and does not call providers. | No OCR or clinical photo analysis exists; implementing it remains out of scope and would require separate safety/privacy validation. |
| SEC-UPL-003 | Partially mitigated for tested hostile parser lifecycle cases | Closure tests cover single and 20 sequential parser timeouts, child exit, queue close/join, workspace deletion, crash-safe responses, oversized parser result rejection, active PDF marker rejection, encrypted/duplicate/Unicode-path DOCX rejection, runtime network/command deny, and parent-controlled copied input. | Process-tree isolation and hard CPU/RAM limits are still absent; parser dependency vulnerabilities remain possible inside the child process. |

## Phase 5 Residuals

| Risk | Severity | Status | Next Action |
|---|---|---|---|
| Process isolation lacks hard CPU/RAM quotas | High | Parser process can be terminated on timeout, but portable memory and CPU caps are not implemented. | Add container, Linux cgroup, Windows job-object, or equivalent hard resource controls before pilot. |
| Parser dependency risk remains | Medium | PDF and DOCX libraries run only in the child process, but dependency parser bugs can still crash the child. | Keep dependency scanning and parser crash tests in CI; consider hardened parser containers. |
| Frontend accept hints are advisory | Low | Backend rejects unsupported or mismatched content regardless of browser metadata. | Optionally narrow frontend accept hints later without redesign, but do not rely on them. |
| Gate A remains unmet after Phase 5 checkpoint | High | Phase 5 closure is accepted, checkpoint committed, and merged into `dev`, but Gate A still requires expanded CI enforcement, hard parser resource-control resolution or explicit sandbox residual acceptance, registry/formal clinical review, and browser-rendered QA disposition. | Plan CI/resource-control follow-up before any gate claim. |

## Phase 6 Status Update

| ID | Phase 6 Status | Evidence | Residual Risk |
|---|---|---|---|
| SEC-API-001 | Partially mitigated for sandbox/API transport | `backend/security_controls.py` authenticates only `Authorization: Bearer` API keys with constant-time compare and keyed fingerprints. Protected clinical routes no longer define body `api_key` form parameters, and frontend transport no longer appends `api_key` to `FormData`. Tests reject form, JSON, query-string, and cookie API-key transport. | Shared API key authentication is not hospital user identity, RBAC, SSO, OAuth/OIDC, or user-level authorization. TLS and operational key rotation remain deployment responsibilities. |
| SEC-SES-001 | Partially mitigated for in-memory sessions | `SecureSessionMemory` issues server `session_id` plus per-session `session_token`, stores only token digest, enforces principal ownership, TTL, idle timeout, max active session bound, cleanup, and reset token rotation. Tests reject fake session reset, no-auth reset/delete, wrong owner, wrong token, expired session, and old token after reset. | Session store is in memory and not distributed or durable. Restart clears sessions; multi-instance coordination is absent. |
| SEC-MFA-001 | Partially mitigated for director TOTP sandbox | Director TOTP verification tracks accepted time steps, rejects replay, rate-limits failures by principal/IP, applies lockout with `Retry-After`, and avoids logging raw seed/OTP. Tests cover first-use acceptance, replay rejection, invalid-code lockout, lockout response, and unlock behavior. | MFA state and director tokens remain in memory. Restart clears counters and replay memory; enrollment governance and phishing-resistant MFA are not implemented. |
| SEC-RATE-001 | Added bounded in-memory limiter | `BoundedRateLimiter` uses per-principal/per-IP/route-class keys, TTL cleanup, max key count, and safe `429` responses with `Retry-After`. Applied to AUTH, MFA, SESSION_MUTATION, CHAT, UPLOAD, and DIRECTOR_PRIVILEGED route classes. | In-memory rate limiting is sandbox containment only. Distributed enforcement requires a shared durable store before controlled pilot. |
| SEC-SEC-001 | Secret loading hardened for non-sandbox modes | `controlled_pilot` and `production` reject missing, weak, or placeholder `CDSS_API_KEYS`, `CDSS_SECRET_KEY`, and `DIRECTOR_BOOTSTRAP`; production still requires safety prerequisite flags. Capabilities do not expose secret values. | No cloud/KMS secret manager, no rotation workflow enforcement, and no formal operational secret handling exists in Phase 6. |
| SEC-CORS-001 | CORS boundary tightened for Phase 6 transport | Wildcard CORS origins are rejected outside `clinical_sandbox`; credentials are disabled; `X-Session-Token` is explicitly allowed for browser requests. | Deployment-specific trusted origins and proxy configuration still need operational review before pilot. |

## Phase 6 Residuals

| Risk | Severity | Status | Next Action |
|---|---|---|---|
| Shared API key is not user identity | High | Phase 6 derives an application principal fingerprint but does not identify individual nurses or hospital users. | Add real identity provider/RBAC in a later scoped phase before pilot claims. |
| In-memory session/MFA/rate-limit state | High | Controls work in a single-process sandbox but are not durable or distributed. | Add durable shared stores and operational eviction/rollback behavior before controlled pilot. |
| Local secrets are not managed secrets | Medium | Weak defaults fail closed outside sandbox, but local files/env vars remain the mechanism. | Add formal secret manager or deployment secret controls later; do not commit `.env`, `.cdss_key`, `.director_totp`, or seeds. |
| Trusted proxy deployment is not configured by default | Medium | Forwarded headers are ignored unless `TRUSTED_PROXY_HOSTS` is explicitly configured. | Document and test proxy topology before deployment. |
| Gate A remains unmet | High | Phase 6 improves auth/session/MFA/rate-limit/secrets only. | Continue evidence-driven release-gate work without pilot, hospital, compliance, or production claims. |

## Phase 6 Director Enrollment Supplement

| Risk | Severity | Status | Recommended Action |
|---|---|---|---|
| Browser-carried shared API key is visible to client code | High | Documented as a local sandbox containment control only; header-only transport avoids body/query/storage leakage but does not make the key server-confidential. | Use real identity provider, RBAC/SSO, or server-side mediation before controlled pilot. |
| Director enrollment provisioning is local-sandbox only | High | `/director/enroll` is disabled by default, sandbox-only when explicitly enabled, header-bootstrap-only, rate-limited, and one-time unless future reset workflow is designed. | Define a formal provisioning lifecycle before pilot/production; do not use ad hoc browser enrollment. |

## Phase 7 Status Update

| ID | Phase 7 Status | Evidence | Residual Risk |
|---|---|---|---|
| SEC-AUD-001 | Partially mitigated for local sandbox tamper evidence | `backend/audit_ledger.py` adds structured audit events, canonical JSON, HMAC-SHA256 chaining, actor fingerprints, metadata minimization, verification summaries, and local rotation linkage. `backend/scripts/verify_audit_ledger.py` verifies local segments without printing secrets. | HMAC is not a digital signature; host administrator compromise of ledger plus key can rewrite history; local append-only API is not filesystem immutability or WORM storage. |
| SEC-AUD-002 | Added PHI/secret minimization for audit metadata | Phase 7 tests assert synthetic patient, API key, session token, OTP/TOTP, bootstrap, provider-key, path, and upload-body canaries are absent from ledger records. | Sanitization is a containment control, not a complete PHI classifier or compliance guarantee. |
| OPS-AUD-001 | Local rotation and CLI verification available | Rotation preserves old segment bytes and links the new segment to the prior terminal MAC in tests; CLI exits non-zero for tampered or missing-key cases. | No external immutable archive, SIEM integration, durable centralized ledger service, signed retention manifest, or multi-process lock is implemented. |

## Phase 7 Residuals

| Risk | Severity | Status | Next Action |
|---|---|---|---|
| HMAC key compromise allows rewrite | High | Documented residual. | Move keys to managed secret storage and add external integrity anchors before pilot. |
| Local filesystem is mutable | High | Local append API uses append mode but cannot prevent host-level edits/deletion. | Add external immutable archive or WORM-capable storage before compliance or production claims. |
| Multi-process correctness is not proven | Medium | Phase 7 uses a process-local thread lock. | Use centralized durable ledger service or portable file-locking design before multi-worker deployment. |
| Valid-prefix tail truncation is not fully detectable locally | Medium | Closure test shows removing only the final record leaves a locally valid prefix that verifies. | Add signed segment footers, externally persisted checkpoints, immutable archive, or external attestation before pilot/compliance claims. |
| Key rotation is not implemented | Medium | Phase 7 stores a `key_id` identifier and tests wrong-key failure, but no key-rotation ceremony or dual-key verification workflow exists. | Define key rotation, retirement, and re-verification workflow with managed key custody. |

## Phase 8 Status Update

Current Phase 8 closure status: durable PostgreSQL registry infrastructure is technically implemented and synthetic-only verification is completed. Real registry approval remains absent, formal reviewer identity binding remains absent, official sourcing and license review remain incomplete, and Gate A/B/C remain unmet.

Historical planning snapshot before implementation.

| Risk | Severity | Phase 8 Status | Recommended Action |
|---|---|---|---|
| CLI-VAL-002 | Critical | Governance infrastructure exists (Phase 3); durable store, clinical review queue, approval artifacts, startup integration remain pending | Implement Phase 8 slices P8-A through P8-F |
| Active release store is in-memory | High | Pending P8-A/P8-D | Add durable store before pilot |
| No formal clinical review workflow | Critical | Pending P8-B | Add approval record schema and review queue |
| Import quality reporting is metadata-only | Medium | Pending P8-C | Add structured extraction-quality reports |
| No startup registry loading | High | Pending P8-E | Add startup integration with fail-closed default |
| CI enforcement incomplete | High | Pending P8-F | Extend CI to include Phase 8 tests |
| Gate A remains unmet | High | Unchanged | Phase 8 reduces but does not eliminate Gate A blockers |

## Phase 9 P9-A Status Update

| Risk | Severity | P9-A Status | Recommended Action |
|---|---|---|---|
| CLI-RAG-001 | Medium | Separate default-off RAG corpus foundation added; product RAG remains lexical prototype only | Do not enable retrieval until governed corpus ingestion, benchmark, and closure review are complete |
| RAG-GOV-001 | High | `rag_schema_migrations` records migration checksums and fails closed on drift | Keep RAG migrations forward-only and separate from registry migrations |
| RAG-GOV-002 | High | Core lexical schema succeeds without pgvector; pgvector is optional explicit admin migration only | Keep vector retrieval disabled until embeddings and benchmark policy are reviewed |
| RAG-PRIV-001 | Critical | Retrieval telemetry schema is bounded metadata-only and excludes raw query/prompt/hash/fingerprint/HMAC/path/URL/credentials/PHI/body fields | Maintain canary tests whenever retrieval events change |
| RAG-STAGE-001 | Medium | Staging rows include TTL/cleanup metadata, are non-searchable, and cannot enter release manifests | Add cleanup operations in a later governed ingestion slice |
| Gate A remains unmet | High | Unchanged after P9-A | Complete formal registry/corpus governance, retrieval benchmarks, browser QA disposition, and remaining release-gate work before any pilot claim |
