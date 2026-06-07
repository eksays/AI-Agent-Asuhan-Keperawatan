# Synthetic Integration Lab Map

Lab 0A is an inspection and design-freeze artifact only. It does not implement
routes, flags, fixtures, mock providers, adapters, dependencies, or frontend
changes. The lab is synthetic-only and must not activate official registry
grounding or patient-care behavior.

Lab Sprint A implements the showcase foundation only: default-false lab flags,
server-authoritative capability metadata, a guarded `/lab/*` namespace,
strict generated-fixture loading, bounded in-memory trace metadata, and a
persistent non-closable synthetic-lab banner. It does not activate multi-agent
orchestration, RAG, registry grounding, Mermaid rendering, EBP retrieval, OCR,
photo analysis, feedback memory, external providers, or patient-care behavior.

Lab Sprint B activates the offline synthetic core feature surface under
`/lab/*` only. It adds default-false Sprint B flags, guarded lab routes,
manifest-backed generated fixtures, deterministic multi-stage orchestration
mocks, synthetic lexical RAG, a lab-only non-authoritative synthetic registry,
offline EBP fixtures, synthetic upload fixture execution, Mermaid fixture
sanitizer routing, deterministic OCR/photo mocks, isolated lab feedback memory,
safe audit events, and a source-tested frontend trace panel. Normal routes keep
their existing fail-closed behavior. External providers, EBP internet endpoints,
the harvester, real registry grounding, real OCR, real photo analysis, real
patient data, patient-care behavior, and production readiness remain disabled or
unsupported.

Strict distinctions:

- feature exists != feature is safe to activate
- agent prompt != real agent orchestration
- multiple LLM calls != swarm coordination
- lexical search != hybrid RAG
- mock adapter != implemented clinical feature
- synthetic registry != authoritative clinical registry
- offline fixture != EBP evidence source
- sanitized trace != chain-of-thought
- demo-ready != release-ready

## Classification Key

| Class | Meaning |
| --- | --- |
| REAL_PATH | Implemented path exists under current sandbox constraints. |
| REAL_PATH_GATED | Implemented path exists but is blocked by config, auth, registry, or capability gates. |
| PROTOTYPE_PATH | Code exists but safety, trace, or evaluation boundaries are incomplete. |
| MOCK_REQUIRED | Deterministic synthetic adapter or fixture is required before lab use. |
| UNSUPPORTED | No usable current implementation exists. |
| FORBIDDEN_IN_LAB | Path must not be used in the lab. |

## Truthful Claim Freeze

| Capability | Current Label |
| --- | --- |
| CURRENT MULTI-AGENT LABEL | multi-stage agent orchestration prototype |
| CURRENT SWARM COORDINATION CLAIM | NOT SUPPORTED |
| CURRENT RAG LABEL | synthetic lexical RAG prototype |
| HYBRID / EMBEDDING / RERANKING CLAIM | NOT SUPPORTED |
| OCR | DETERMINISTIC MOCK ONLY UNDER `/lab/ocr` |
| PHOTO WORKFLOW | DETERMINISTIC MOCK ONLY UNDER `/lab/photo` |

Forbidden claims: validated swarm, clinical swarm intelligence, hybrid clinical
RAG, validated clinical RAG, and production-ready.

## Feature-Surface Inventory

Column shorthand: `Surface` records owned files, routes, and UI entry points.
`Runtime` records dependencies, network behavior, and data source. `Safety`
records privacy risk, security boundary, and audit events. `Lab` records normal
default, target state, recommended adapter, required tests, and limitations.

| Feature ID | Feature | Current Classification | Surface | Runtime | Safety | Lab |
| --- | --- | --- | --- | --- | --- | --- |
| LAB-AUTH-001 | Auth and API key transport | REAL_PATH | `backend/api.py`, `security_controls.py`, `frontend/lib/api.ts`; all protected routes; frontend sends `Authorization: Bearer`. | Sandbox default key or `CDSS_API_KEYS`; no network; browser memory/header key. | Browser-carried shared key is not identity; header-only transport, safe errors; auth success/failure audit. | Default enabled sandbox auth; lab reuses real auth on `/lab/*`; no adapter; test missing/bad auth and no body/query/storage key; limitation: no RBAC/SSO/OIDC. |
| LAB-SES-001 | Session creation, ownership, rotation, expiry | REAL_PATH | `SecureSessionMemory`, `/session`, `/reset`, `/delete_my_data`; frontend session binding in React refs. | In-memory session records with TTL/idle/max; no network. | Session history can hold sanitized clinical text; owner fingerprint, token digest, mutation audit. | Default after auth; lab uses isolated lab sessions; no adapter; test token missing/wrong/stale/reset/delete; limitation: not durable/distributed. |
| LAB-MFA-001 | Director enrollment, MFA replay, lockout | REAL_PATH_GATED | `backend/director.py`, `/director/enroll`, `/director/login`, `/director/metrics`, director dashboard. | Local encrypted `.director_totp`; `DIRECTOR_BOOTSTRAP`, `DIRECTOR_ENROLLMENT_ENABLED`; no network. | Seed/bootstrap/OTP must never trace; local-mode gate, replay cache, lockout; director/MFA audit. | Enrollment default-off; lab may verify sandbox MFA only; deterministic test TOTP only; test replay/lockout/redaction; limitation: not phishing-resistant and state is local. |
| LAB-RATE-001 | Route-class rate limiting | REAL_PATH | `BoundedRateLimiter`; route classes AUTH, MFA, SESSION_MUTATION, CHAT, UPLOAD, DIRECTOR_PRIVILEGED. | In-memory bounded deques; no network. | Usage patterns may leak if overexposed; HMAC subject, bounded keys; `rate_limited` audit. | Default enabled; lab adds route class limits; no adapter; test 429/retry/eviction; limitation: restart resets state. |
| LAB-AUD-001 | HMAC audit ledger and verifier CLI | REAL_PATH_GATED | `backend/audit_ledger.py`, `api.py`, `scripts/verify_audit_ledger.py`; no UI trace yet. | In-memory unless strong key/path configured; no network; local JSONL optional. | Ledger metadata must not contain PHI, prompts, outputs, tokens, paths, or stack traces; HMAC chain and safe metadata allowlist. | Default in-memory sandbox; lab emits safe event ids only; no adapter; test event emission, verifier, PHI/secret absence; limitation: not WORM, not immutable, not non-repudiation. |
| LAB-UPL-001 | TXT, PDF, DOCX upload parsing | REAL_PATH_GATED | `backend/upload_security.py`, `/analisis`, `/analisis_multi`, frontend file upload. | Parser libs and spawn multiprocessing; child blocks network/commands; upload bytes. | Raw uploaded text must not trace, ledger, or outbound; sniffing, type match, hostile PDF/DOCX rejection, killable child. | Default available only inside gated analysis; lab uses synthetic files; hostile fixture adapter; test safe TXT, hostile PDF/DOCX, timeout cleanup; limitation: no hard OS CPU/RAM quotas/process-tree containment. |
| LAB-VAL-001 | Typed clinical validation | REAL_PATH | `clinical_schema.py`, `clinical_validator.py`, analysis routes. | Validator plus registry object; no network; provider output and registry metadata. | Raw provider output/patient narrative must not expose; strict parsing, duplicate-key rejection, evidence/registry checks; `clinical_abstention` audit. | Default active when analysis reaches validation; lab uses synthetic non-authoritative registry; no adapter beyond fixtures; test malformed/accepted-false cases; limitation: formal clinical approval workflow incomplete. |
| LAB-ABS-001 | Safe abstention | REAL_PATH | `clinical_validator.py`, `api.py`; analysis responses and headers. | No network; missing/invalid registry/provider status. | UI must not hide abstention; server emits accepted=false and nurse_review_required=true; registry/clinical audit. | Default active; lab exposes abstention in UI and trace; no adapter; test weak context and missing registry; limitation: formal wording review needed. |
| LAB-AGT-001 | Agent orchestration | PROTOTYPE_PATH | `agents.py`, `api.py`, `backend/lab_orchestration.py`, `/lab/run`; frontend tabs/status labels. | Normal routes require external LLM gate; lab route uses deterministic mock stages only and no provider factory. | Prompts/outputs/clinical text must not trace; lab emits safe stage metadata and abstention only. | Sprint B implements lab-only deterministic stages `retrieval`, `assessment`, `reviewer`, `critic`, `synthesis`, and `validator_boundary`; critic affects synthesis; limitation: no autonomous swarm coordination and no real provider orchestration. |
| LAB-RAG-001 | Retrieval and RAG | PROTOTYPE_PATH | `api.py` local `bangun_konteks`, `ebp.py`, ignored `backend/data_terstruktur/*`, `backend/lab_rag.py`, `/lab/rag`. | Normal local lexical JSON may be empty; lab uses generated offline corpus fixtures only; no network. | Licensed registry and PHI must not be used; lab trace exposes only document ids, scores, corpus version, and weak-context flag. | Sprint B implements synthetic lexical RAG prototype; weak context abstains; limitation: no embeddings, hybrid retrieval, or reranking. |
| LAB-REG-001 | Registry grounding | REAL_PATH_GATED | `clinical_registry.py`, `registry_governance.py`, `registry_release.py`, `backend/lab_registry.py`, `/lab/registry`. | Explicit release abstractions; no active authoritative runtime registry; lab loads manifest-approved fake codes only. | Licensed/local files must not become authoritative; lab always reports `registry_authoritative=false` and `clinical_use_allowed=false`. | Sprint B implements lab-only synthetic registry fixture; `SYN-D-001` works only under `/lab/*` and remains rejected by normal code-format policy; limitation: formal approval and durable active release store incomplete. |
| LAB-EBP-001 | EBP retrieval | REAL_PATH_GATED | `ebp.py`, `harvester.py`, `backend/lab_ebp.py`, `/lab/ebp`. | External EBP APIs remain default-off; lab uses generated offline fixture references only. | PHI query/citation/cache risks avoided in lab by no network and safe source labels. | Sprint B implements offline synthetic EBP fixture adapter; limitation: fixture is not current medical evidence. |
| LAB-OCR-001 | OCR and extraction utilities | PROTOTYPE_PATH | `ekstraksi.py`, `upload_security.py`, `backend/lab_mocks.py`, `/lab/ocr`. | Manual OCR utility remains out of scope; lab uses fixture-id deterministic mock only. | Real image text must not trace; lab response is labeled `DETERMINISTIC OCR MOCK - EXTRACTION UNVERIFIED`. | Sprint B implements mock-only OCR route; limitation: validated OCR is not implemented. |
| LAB-IMG-001 | Photo or image workflow | PROTOTYPE_PATH | `api.py`, upload controls, `backend/lab_mocks.py`, `/lab/photo`. | Browser media/file input exists; backend vision model remains unavailable; lab uses fixture metadata only. | Real photos are PHI; normal capability gate denies unavailable photo path; lab response is labeled not clinical image analysis. | Sprint B implements mock-only photo route; limitation: no clinical-photo implementation. |
| LAB-MMD-001 | Mermaid pathway rendering | REAL_PATH_GATED | `/pathway`, `agents.gen_pathway`, `frontend/components/ui/mermaid.tsx`, `svg-sanitize.ts`, `backend/lab_mermaid.py`, `/lab/pathway`. | Mermaid and DOMPurify; normal external LLM path remains disabled; lab loads generated fixtures only. | SVG XSS risk; lab rejects unsafe fixture content and still relies on existing frontend sanitizer boundary. | Sprint B implements safe/malicious fixture route; malicious payload is rejected or inert; limitation: full browser QA remains Sprint C. |
| LAB-MEM-001 | Feedback memory | REAL_PATH_GATED | `memory.py`, `/feedback`, `/delete_my_data`, `backend/lab_feedback.py`, `/lab/feedback`. | Normal encrypted local feedback store remains separate; lab store is bounded in memory with TTL and no network. | PHI retention and cross-session poisoning risk; lab rejects PHI/secret canaries and stores safe lengths only. | Sprint B implements isolated synthetic feedback memory; no cross-session or normal/lab recall; limitation: local in-memory lab store is not durable. |
| LAB-HRV-001 | Background harvester | REAL_PATH_GATED | `harvester.py`, startup hook. | `HARVEST_INTERVAL_SEC`, topics; EBP network if started. | Uncontrolled background network/cache writes; default interval 0 and audit callback. | Default off; lab policy disabled except inactive-state test; no adapter; test harvester activity attempt; limitation: no lab worker planned. |
| LAB-EXT-001 | External model provider boundary | REAL_PATH_GATED | `api.py`, `outbound_policy.py`, provider selector, LLM routes. | Provider SDKs/base URLs; API key from header; network only when enabled. | PHI leakage/key exposure/provider retention; feature gate, outbound wrapper, browser sanitization. | Default `FEATURE_EXTERNAL_LLM=false`; lab mock provider first, optional real synthetic opt-in only in LAB-12; test no network without opt-in; limitation: no activation in Lab 0A. |
| LAB-UI-001 | Visible lab banner and trace panel | REAL_PATH_GATED | `frontend/lib/capabilities.ts`, `frontend/lib/api.ts`, `frontend/components/dashboard.tsx`, `frontend/components/synthetic-lab-trace-panel.tsx`. | Frontend only; fetches backend metadata and has a typed lab trace fetcher; no browser env-variable enablement or storage. | Trace could leak prompts, outputs, PHI, secrets; panel renders only safe fields and never raw prompts, outputs, uploaded text, paths, stack traces, or chain-of-thought. | Sprint B adds safe trace panel labels and source tests; limitation: no browser-rendered QA claim until Sprint C. |
| LAB-KILL-001 | Lab kill-switch | REAL_PATH_GATED | `backend/config.py`, `backend/lab_config.py`, `backend/lab_routes.py`, `backend/api.py`, frontend capability metadata. | `SYNTHETIC_LAB_MODE=false`, `SYNTHETIC_DATA_ONLY=false`, and all Sprint B flags default false; no data source; no network. | Partial lab activation risk is reduced by a central guard before lab sessions, traces, fixtures, audit events, parser calls, or mock adapters. | Flags absent close `/lab/*`; sandbox requires both lab and data-only flags; pilot/production reject lab flags; Sprint B feature-specific flags close their routes when false. |

## Multi-Agent Reality Check

Evidence: `agents._run` calls `llm.invoke`; `run_swarm` performs diagnosis then
parallel outcome/intervention; `_review_once` is medium review; `_swarm_review`
runs three role-specific critics in parallel and synthesizes notes; API routes
call `orchestrate_answer` and then typed validation for analysis outputs.
Sprint B adds a separate lab-only deterministic path in
`backend/lab_orchestration.py` for `/lab/run`; it does not call provider
factories or normal agent routes.

| Check | Result |
| --- | --- |
| Agent roles actually present | Prompt roles for analysis/pathway/EBP, reviewer, critics, diagnosis, outcome, intervention, and audit. |
| Agent factory behavior | No independent factory; roles are prompt builders/helper functions. |
| Execution | Flash single call; medium draft then review; pro draft plus parallel critics then synthesis; `run_swarm` diagnosis then two parallel workers. |
| Model invocations | Flash 1; medium 2; pro `orchestrate_answer` 5; older `run_swarm` pro path 4 including audit. |
| Review/critic/synthesis | Normal routes have review/critic helpers without safe per-stage trace; Sprint B lab route emits safe stage names/statuses and critic reason codes only. |
| Fallback/error | Routes catch provider exceptions and return sanitized status; streaming can fall back to `/chat` only before text. |
| Memory/RAG injection | Session history, feedback recall, local context, and optional EBP context can enter prompts after sanitization. |
| Typed-validator boundary | Analysis outputs are validated after orchestration before browser response. |

CURRENT MULTI-AGENT LABEL: multi-stage agent orchestration prototype

CURRENT SWARM COORDINATION CLAIM: NOT SUPPORTED

The code supports multi-stage orchestration prototypes. Sprint B proves only a
deterministic lab showcase path with separate stages and safe trace metadata. It
does not prove autonomous swarm coordination: no planner, durable task
delegation, tool negotiation, inter-agent state, or validated clinical decision
flow.

## RAG Reality Check

Evidence: `api.muat_data` loads ignored local JSON; `api.bangun_konteks`
performs lexical token-overlap scoring; `ebp._recall_cached` recalls cached
articles by token overlap; `ebp.retrieve_context` builds a deidentified concept
query and retrieves external open-access article metadata only when gated paths
are enabled. Sprint B adds `backend/lab_rag.py`, which performs deterministic
token-overlap scoring over generated fixture documents only.

| Check | Result |
| --- | --- |
| Retrieval function | Local `bangun_konteks`; external `ebp.retrieve_context` and `retrieve`. |
| Corpus source | Ignored local JSON, external EBP APIs, encrypted EBP cache. |
| Query/scoring | Simple lowercase token set and intersection count; EBP year/citation sorting. |
| Top-k/dedupe | Local top-k; EBP cap 12; DOI/PMID/title uid dedupe. |
| Provenance/citations | EBP formats metadata; local registry authority unavailable. |
| Filtering | 3S/3N book selection; no learned framework classifier. |
| Embeddings/reranking | None found. |
| Failure/abstention | Empty EBP returns no-journal instruction; clinical analysis abstains on missing registry; Sprint B weak-context retrieval returns `accepted_recommendations=false`, `clinical_use_allowed=false`, and `nurse_review_required=true`. |

CURRENT RAG LABEL: synthetic lexical RAG prototype

HYBRID / EMBEDDING / RERANKING CLAIM: NOT SUPPORTED

Do not claim embeddings, hybrid retrieval, or reranking until source code and
tests prove those mechanisms.

OCR: DETERMINISTIC MOCK ONLY

PHOTO WORKFLOW: DETERMINISTIC MOCK ONLY

Sprint B update: OCR and photo are implemented only as deterministic `/lab/*`
mocks with explicit labels. They are not clinical OCR or clinical image
analysis.

## Outbound Network Map

| Path | Default | Lab Policy | Evidence |
| --- | --- | --- | --- |
| External LLM | Disabled by `FEATURE_EXTERNAL_LLM=false`. | Mock adapter only until LAB-12 explicit synthetic opt-in. | `config.build_capabilities`, `_blocked_llm_capability`, `wrap_llm`. |
| EBP connector | Disabled because EBP requires external LLM and `FEATURE_EBP_EXTERNAL_SEARCH=true`. | Offline fixture only. | `ebp.py` host allowlist and `api.py` Referensi gate. |
| Harvester | Off because `HARVEST_INTERVAL_SEC=0`. | Must remain disabled; test attempted activity. | `harvester.start` returns false for interval <= 0. |
| `populate_sdki.py` | Manual script only. | FORBIDDEN_IN_LAB; do not call. | HTTPS-only `api.anthropic.com` validator and `# nosec B310` on validated line. |
| `ekstraksi.py` | Manual OCR/LLM utility only. | FORBIDDEN_IN_LAB for real OCR/licensed PDFs; mock OCR only. | Env API key, provider SDKs, `wrap_llm`. |
| Upload parser child | No intended outbound; runtime guards block socket/urlopen/subprocess. | Real parser with synthetic fixtures only. | `_install_parser_runtime_guards`. |
| Sprint B lab core routes | Default-off unless lab profile and feature flag are true. | Offline fixture only; no provider, EBP internet, harvester, OCR SDK, or photo analyzer calls. | `backend/lab_routes.py`, `backend/lab_*`, `synthetic_lab_core_features_test.py`. |
| Frontend fetch | Backend API only through `NEXT_PUBLIC_API_BASE`. | Future `/lab/*` only after server metadata. | `frontend/lib/api.ts`. |
| Director dashboard fetch | Backend director endpoints only. | Sandbox-only verification; no seed/OTP in trace. | `frontend/app/director-dashboard/page.tsx`. |

## Lab Isolation Design

Selected design: dedicated namespace plus server-authoritative lab metadata.

Target namespace:

```text
/lab/status
/lab/session
/lab/run
/lab/rag
/lab/registry
/lab/ebp
/lab/upload
/lab/pathway
/lab/ocr
/lab/photo
/lab/feedback
/lab/trace/{run_id}
```

| Item | Decision | Reason |
| --- | --- | --- |
| Namespace | Use `/lab/*`. | Prevents silent simulation on normal routes. |
| Capability source | Server-authoritative metadata. | Frontend must not infer enablement. |
| Mode gate | `APP_MODE=clinical_sandbox` only. | Lab flags rejected in controlled_pilot and production. |
| Data gate | Require `SYNTHETIC_DATA_ONLY=true`. | Blocks patient, hospital, and real registry content. |
| Kill-switch | Central guard before route logic. | One switch closes all lab paths before side effects. |
| Trace | Sanitized trace by `run_id`. | Supports UX debugging without chain-of-thought or PHI. |
| Normal routes | Keep fail-closed behavior. | Lab work must not alter clinical route claims. |

## Three-Sprint Plan Freeze

| Sprint | Scope | Exit Criteria |
| --- | --- | --- |
| Lab Sprint A - Showcase Foundation | Default-false lab flags, clinical_sandbox-only enforcement, controlled_pilot and production rejection, offline-profile rejection of external LLM/EBP/photo/Mermaid/harvester settings, central kill-switch, `/lab/*` namespace, strict fixture loader, approved synthetic fixture parent, manifest allowlist, resolved-path containment, traversal/absolute/outside-manifest/symlink escape rejection where detectable, `backend/data_terstruktur/*` plus upload/runtime/hospital/patient-record path rejection, bounded in-memory trace store, opaque `run_id`, TTL, capacity limits, safe field allowlist, persistent non-closable banner, normal-route non-regression tests, offline network-deny tests. | All flags default false; kill-switch closes every `/lab/*` route; normal routes unchanged; fixture loader cannot escape the approved synthetic fixture parent or trusted root; trace stores no PHI or secrets; foundation works without internet. |
| Lab Sprint B - Core Feature Activation | Real local auth/session, MFA/rate limit, HMAC audit ledger, upload parser, typed validator, abstention, Mermaid sanitizer, isolated lab feedback memory, deterministic per-stage orchestration mocks, synthetic lexical RAG fixtures, lab-only synthetic registry adapter, offline EBP fixture adapter, OCR deterministic mock, photo deterministic mock, safe trace panel. | Each agent stage invoked; critic affects synthesis; retrieval document IDs and scores visible; synthetic registry works only under `/lab/*`; `SYN-D-001` rejected on normal routes; normal validator rules unchanged; malicious Mermaid inert; feedback memory isolated; OCR/photo explicitly mock. |
| Lab Sprint C - Pitch-Ready Closure | PHI canary red-team, hostile PDF/DOCX tests, offline network-deny closure, browser QA, secret scan, full regression, demo rehearsal, kill-switch rehearsal, audit-ledger verification rehearsal, contributor runbook, feature matrix, known limitations. | Full tests pass; Bandit Medium 0 High 0; frontend lint clean; frontend build pass; npm audit 0 vulnerabilities; PHI canaries absent from outbound, trace, UI, logs, and ledger; offline showcase works; normal routes fail-closed; banner visible/non-closable; kill-switch closes all lab routes. |

## Lab Flag Design

All flags default false. Sprint A implements the foundation flags. Sprint B
implements the offline core flags below under the same `clinical_sandbox` and
`SYNTHETIC_DATA_ONLY=true` requirements.

| Flag | Default | Allowed Mode | Purpose |
| --- | --- | --- | --- |
| `SYNTHETIC_LAB_MODE` | `false` | `clinical_sandbox` | Enables lab namespace when paired with data-only and kill-switch checks. |
| `SYNTHETIC_DATA_ONLY` | `false` | `clinical_sandbox` | Requires generated fixtures and rejects real data. |
| `SYNTHETIC_MULTI_AGENT` | `false` | `clinical_sandbox` | Deterministic multi-stage mock orchestration. |
| `SYNTHETIC_RAG` | `false` | `clinical_sandbox` | Fixture-backed lexical retrieval and safe scores. |
| `SYNTHETIC_REGISTRY` | `false` | `clinical_sandbox` | Fake-code registry fixture, authoritative false. |
| `SYNTHETIC_EBP` | `false` | `clinical_sandbox` | Offline EBP fixture adapter. |
| `SYNTHETIC_MERMAID` | `false` | `clinical_sandbox` | Mermaid fixture route through existing sanitizer. |
| `SYNTHETIC_UPLOADS` | `false` | `clinical_sandbox` | Synthetic upload fixture tests. |
| `SYNTHETIC_OCR_MOCK` | `false` | `clinical_sandbox` | Explicit OCR mock outputs. |
| `SYNTHETIC_PHOTO_MOCK` | `false` | `clinical_sandbox` | Explicit photo mock outputs. |
| `SYNTHETIC_FEEDBACK_MEMORY` | `false` | `clinical_sandbox` | Isolated synthetic feedback memory. |
| `SYNTHETIC_EXTERNAL_PROVIDER_OPT_IN` | `false` | `clinical_sandbox` | Later synthetic-only real provider opt-in. |

Preserve existing defaults: `FEATURE_EXTERNAL_LLM=false`,
`FEATURE_EBP_EXTERNAL_SEARCH=false`, `FEATURE_CLINICAL_PHOTO_ANALYSIS=false`,
`FEATURE_MERMAID_PATHWAY_RENDERING=false`, `HARVEST_INTERVAL_SEC=0`, and real
registry grounding unavailable.

## Fixture-Pack Design

Sprint B creates this generated fixture structure:

```text
backend/tests/fixtures/synthetic_lab/
  manifest.json
  cases/
  registries/
  rag/
  ebp/
  uploads/
  images/
  expected_outputs/
```

Sprint A creates only `manifest.json` and `cases/foundation_case.json` as
generated non-authoritative foundation fixtures. Registries, RAG, EBP, uploads,
images, OCR/photo mocks, and expected-output fixture bodies remain uncreated.

Sprint B expands the manifest with generated synthetic cases, RAG, registry,
offline EBP, upload, rendering, image/mock, and expected-output fixtures. All
fixtures are generated, non-authoritative, `clinical_use_allowed=false`, and use
fake identifiers such as `SYN-D-001`, `SYN-O-001`, and `SYN-I-001`.

Sprint B closure review hardens the fixture loader with duplicate path and
duplicate fixture-id rejection, an approved top-level category allowlist,
`.json` extension enforcement, a per-fixture size bound, and a JSON nesting
depth bound. Every fixture body remains manifest-listed and manifest-backed;
callers cannot supply arbitrary filesystem paths or reach `backend/data_terstruktur/*`.

Every fixture must carry `fixture_id`, `fixture_version`,
`synthetic_only=true`, `authoritative=false`, `clinical_use_allowed=false`,
`source_type=generated_fixture`, and
`created_for=security_ux_orchestration_testing`.

Categories: respiratory monitoring, pain observation, fluid balance,
temperature monitoring, fall-risk observation, wound-care workflow mock,
medication-administration workflow mock, hostile PDF, hostile DOCX, safe
Mermaid, malicious Mermaid, synthetic OCR image, synthetic photo mock, and PHI
canary input. Use fake codes such as `SYN-D-001`, `SYN-O-001`, and `SYN-I-001`.
Do not copy licensed SDKI, SLKI, SIKI, NANDA, NOC, NIC, hospital, or patient
content.

## Safe Execution-Trace Contract

Allowed fields: `run_id`, `mode`, `fixture_case_id`, `route`, `feature_label`,
`agent_stages`, `stage_status`, `stage_latency_ms`, `stage_reason_codes`,
`latency_ms`, `provider_type`, `retrieved_document_ids`, `retrieval_scores`,
`retrieval_source`, `corpus_version`, `weak_context`, `registry_source`,
`registry_authoritative`, `clinical_use_allowed`, `clinical_status`,
`accepted_recommendations`, `nurse_review_required`, `prototype_candidate_ids`,
`missing_data`, `validation_issue_codes`, `audit_event_ids`, and
`sanitization_status`.

Never include chain-of-thought, raw prompt, raw model output, raw patient
narrative, raw uploaded text, API key, session token, OTP, director seed,
bootstrap secret, provider key, filesystem path, or stack trace.

Sprint B closure review binds stored trace records out-of-band to the creating
principal fingerprint and lab session id. `GET /lab/trace/{run_id}` requires the
same bearer principal, `X-Lab-Session-Id`, and `X-Lab-Session-Token`; possession
of a `run_id` alone is insufficient. The owner and session bindings are not
included in the trace payload returned to the frontend.

## UI Contract

Persistent non-closable banner:

```text
SYNTHETIC INTEGRATION LAB — DO NOT ENTER REAL PATIENT DATA.
NOT FOR PATIENT CARE.
OUTPUTS MAY BE MOCKED OR PROTOTYPE-ONLY.
```

Trace panel labels every feature as `REAL LOCAL PATH`, `SYNTHETIC PROTOTYPE`,
`DETERMINISTIC MOCK`, `DISABLED`, or `FORBIDDEN IN LAB`. The UI must not hide abstention and must expose
`registry_authoritative=false`, `clinical_use_allowed=false`,
`accepted_recommendations=false`, and `nurse_review_required=true` where
relevant.

Sprint B implements the safe trace panel as a frontend component driven by
backend capability metadata and server-returned safe trace metadata. It does not
use browser persistence and does not render raw prompts, raw outputs, uploaded
text, chain-of-thought, filesystem paths, stack traces, tokens, or secrets.

## External-Provider Policy

Default: `FEATURE_EXTERNAL_LLM=false` and
`SYNTHETIC_EXTERNAL_PROVIDER_OPT_IN=false`.

Optional later activation only when all are true:

```text
APP_MODE=clinical_sandbox
SYNTHETIC_LAB_MODE=true
SYNTHETIC_DATA_ONLY=true
FEATURE_EXTERNAL_LLM=true
SYNTHETIC_EXTERNAL_PROVIDER_OPT_IN=true
```

Provider API keys are environment or in-memory header only: never frontend
storage, never query string, never trace output, never committed. Inputs must be
synthetic fixtures or manually entered text that passes the outbound PHI
firewall.

Branch separation:

| Branch | Scope |
| --- | --- |
| `review/synthetic-integration-lab` | offline synthetic showcase only |
| `review/synthetic-external-provider` | optional later branch for DeepSeek or another provider |

External-provider work is not required for Sprint C closure.

## Forbidden Shortcuts

| Shortcut | Reason |
| --- | --- |
| Enable `backend/data_terstruktur/*` | Local files are ignored/local-only and not approved registry releases. |
| Copy licensed registry content | Fixtures must be generated synthetic material only. |
| Call external providers by default | Later explicit synthetic opt-in is required. |
| Call EBP internet endpoints by default | Offline fixtures are required first. |
| Run the harvester | Harvester remains off for Sprint A-C. |
| Simulate unsupported features on normal routes | Lab behavior must stay under `/lab/*`. |
| Mark mock output as validated | Mock output is not clinical validation. |
| Bypass typed validator | Validation and abstention boundaries remain visible. |
| Bypass abstention | Weak evidence and missing registry stay blocked. |
| Expose chain-of-thought | Trace contains safe stage status only. |
| Expose raw prompts, raw outputs, uploaded text, PHI, tokens, OTPs, paths, or stack traces | Trace storage uses a safe field allowlist. |
| Merge lab code into dev automatically | Lab work remains review-only until approved. |
