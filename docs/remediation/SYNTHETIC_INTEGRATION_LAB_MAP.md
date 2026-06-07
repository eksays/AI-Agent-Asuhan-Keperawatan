# Synthetic Integration Lab Map

Lab 0A is an inspection and design-freeze artifact only. It does not implement
routes, flags, fixtures, mock providers, adapters, dependencies, or frontend
changes. The lab is synthetic-only and must not activate official registry
grounding or patient-care behavior.

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
| OCR | DETERMINISTIC MOCK REQUIRED |
| PHOTO WORKFLOW | DETERMINISTIC MOCK REQUIRED |

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
| LAB-AGT-001 | Agent orchestration | PROTOTYPE_PATH | `agents.py`, `api.py`; `/chat`, `/chat_stream`, `/analisis_multi`; frontend tabs/status labels. | External LLM only after capability gate; sanitized user/upload text and optional context. | Prompts/outputs/clinical text must not trace; outbound policy wrapper and validator boundary; analysis audit lacks per-stage trace. | Default disabled by external LLM and registry gates; lab needs deterministic per-stage mocks; test stage order, critic influence, synthesis, timeout/error; limitation: no autonomous swarm coordination or safe trace yet. |
| LAB-RAG-001 | Retrieval and RAG | PROTOTYPE_PATH | `api.py` local `bangun_konteks`, `ebp.py`, ignored `backend/data_terstruktur/*`, Referensi tab. | Local lexical JSON if present; EBP external APIs if enabled; encrypted cache recall. | Licensed registry and PHI must not be used; deidentified EBP query, host allowlist, default-off; limited audit. | Default local DATA often empty and non-authoritative; lab uses offline lexical fixtures only; test ids/scores and weak-context abstention; limitation: no embeddings, hybrid retrieval, or reranking. |
| LAB-REG-001 | Registry grounding | REAL_PATH_GATED | `clinical_registry.py`, `registry_governance.py`, `registry_release.py`, `api.py`; validation path and capability metadata. | Explicit release abstractions; no active runtime registry; no network. | Licensed/local files must not become authoritative; lifecycle/provenance/quarantine checks; registry audit. | Default `sdki_authoritative_grounding=false` and components false; lab synthetic registry only; test real path rejection, authoritative=false, clinical_use_allowed=false; limitation: formal approval and durable active release store incomplete. |
| LAB-EBP-001 | EBP retrieval | REAL_PATH_GATED | `ebp.py`, `harvester.py`, Referensi agent and action buttons. | PubMed, Europe PMC, Semantic Scholar, Unpaywall if enabled; cache file; default-off. | PHI query/citation/cache risks; deidentified concept query, host allowlist, no redirects; sparse audit. | Lab offline fixture adapter only; test no network, fixture provenance, PHI absence; limitation: fixture is not evidence. |
| LAB-OCR-001 | OCR and extraction utilities | MOCK_REQUIRED | `ekstraksi.py`, `upload_security.py`; no clinical OCR route. | Manual utility can use PDFs and external LLM; upload parser extracts PDF text, not image OCR. | Licensed OCR PDFs and generated registry bodies are forbidden; no clinical route audit. | Default inactive; lab OCR mock label only; test no raw image text in trace; limitation: validated OCR not implemented. |
| LAB-IMG-001 | Photo or image workflow | UNSUPPORTED | `api.py`, upload controls; `file_foto` branches and camera UI. | Browser media/file input only; no backend vision model; no intended network. | Real photos are PHI; capability gate denies and audits unavailable photo path. | Default unavailable; lab photo mock only with explicit label; test normal route disabled and mock label; limitation: no clinical-photo implementation. |
| LAB-MMD-001 | Mermaid pathway rendering | REAL_PATH_GATED | `/pathway`, `agents.gen_pathway`, `frontend/components/ui/mermaid.tsx`, `svg-sanitize.ts`. | Mermaid and DOMPurify; external LLM only if both gates enabled. | SVG XSS risk; backend capability gate, strict Mermaid config, SVG sanitizer, Markdown sanitizer. | Default disabled; lab may render safe/malicious fixtures through existing sanitizer; test raw SVG never bypasses sanitizer; limitation: full browser QA remains outside Lab 0A. |
| LAB-MEM-001 | Feedback memory | REAL_PATH_GATED | `memory.py`, `/feedback`, `/delete_my_data`, thumbs/correction UI. | Encrypted local `feedback_memory.json`, per-session recall; no network. | PHI retention and cross-session poisoning risk; per-session binding, DEK purge, sanitized writes; feedback audit. | Default available after auth/session; lab must use isolated synthetic namespace/store; test cross-session isolation and PHI canary absence; limitation: local JSON governance only. |
| LAB-HRV-001 | Background harvester | REAL_PATH_GATED | `harvester.py`, startup hook. | `HARVEST_INTERVAL_SEC`, topics; EBP network if started. | Uncontrolled background network/cache writes; default interval 0 and audit callback. | Default off; lab policy disabled except inactive-state test; no adapter; test harvester activity attempt; limitation: no lab worker planned. |
| LAB-EXT-001 | External model provider boundary | REAL_PATH_GATED | `api.py`, `outbound_policy.py`, provider selector, LLM routes. | Provider SDKs/base URLs; API key from header; network only when enabled. | PHI leakage/key exposure/provider retention; feature gate, outbound wrapper, browser sanitization. | Default `FEATURE_EXTERNAL_LLM=false`; lab mock provider first, optional real synthetic opt-in only in LAB-12; test no network without opt-in; limitation: no activation in Lab 0A. |
| LAB-UI-001 | Visible lab banner and trace panel | MOCK_REQUIRED | Existing frontend app/components; no lab banner or trace panel. | Frontend only; fetches backend metadata. | Trace could leak prompts, outputs, PHI, secrets; current UI has sanitized Markdown/Mermaid and fail-closed capabilities. | Default absent; lab needs persistent non-closable banner and safe trace panel; test labels and forbidden-field absence; limitation: requires LAB-10. |
| LAB-KILL-001 | Lab kill-switch | UNSUPPORTED | Future `config.py`, `api.py`, frontend capability metadata; no current route. | Future env flags; no data source. | Missing kill-switch could permit partial lab activation; must audit enable/deny. | Default absent and therefore closed; implement before lab routes; test flags absent, kill-switch off, pilot/production rejection; limitation: must precede all lab features. |

## Multi-Agent Reality Check

Evidence: `agents._run` calls `llm.invoke`; `run_swarm` performs diagnosis then
parallel outcome/intervention; `_review_once` is medium review; `_swarm_review`
runs three role-specific critics in parallel and synthesizes notes; API routes
call `orchestrate_answer` and then typed validation for analysis outputs.

| Check | Result |
| --- | --- |
| Agent roles actually present | Prompt roles for analysis/pathway/EBP, reviewer, critics, diagnosis, outcome, intervention, and audit. |
| Agent factory behavior | No independent factory; roles are prompt builders/helper functions. |
| Execution | Flash single call; medium draft then review; pro draft plus parallel critics then synthesis; `run_swarm` diagnosis then two parallel workers. |
| Model invocations | Flash 1; medium 2; pro `orchestrate_answer` 5; older `run_swarm` pro path 4 including audit. |
| Review/critic/synthesis | Review and critic stages exist, but no safe per-stage trace yet. |
| Fallback/error | Routes catch provider exceptions and return sanitized status; streaming can fall back to `/chat` only before text. |
| Memory/RAG injection | Session history, feedback recall, local context, and optional EBP context can enter prompts after sanitization. |
| Typed-validator boundary | Analysis outputs are validated after orchestration before browser response. |

CURRENT MULTI-AGENT LABEL: multi-stage agent orchestration prototype

CURRENT SWARM COORDINATION CLAIM: NOT SUPPORTED

The code supports multi-stage orchestration with parallel critics and synthesis.
It does not prove autonomous swarm coordination: no planner, durable task
delegation, tool negotiation, inter-agent state, or exposed safe decision trace.

## RAG Reality Check

Evidence: `api.muat_data` loads ignored local JSON; `api.bangun_konteks`
performs lexical token-overlap scoring; `ebp._recall_cached` recalls cached
articles by token overlap; `ebp.retrieve_context` builds a deidentified concept
query and retrieves external open-access article metadata only when gated paths
are enabled.

| Check | Result |
| --- | --- |
| Retrieval function | Local `bangun_konteks`; external `ebp.retrieve_context` and `retrieve`. |
| Corpus source | Ignored local JSON, external EBP APIs, encrypted EBP cache. |
| Query/scoring | Simple lowercase token set and intersection count; EBP year/citation sorting. |
| Top-k/dedupe | Local top-k; EBP cap 12; DOI/PMID/title uid dedupe. |
| Provenance/citations | EBP formats metadata; local registry authority unavailable. |
| Filtering | 3S/3N book selection; no learned framework classifier. |
| Embeddings/reranking | None found. |
| Failure/abstention | Empty EBP returns no-journal instruction; clinical analysis abstains on missing registry. |

CURRENT RAG LABEL: synthetic lexical RAG prototype

HYBRID / EMBEDDING / RERANKING CLAIM: NOT SUPPORTED

Do not claim embeddings, hybrid retrieval, or reranking until source code and
tests prove those mechanisms.

OCR: DETERMINISTIC MOCK REQUIRED

PHOTO WORKFLOW: DETERMINISTIC MOCK REQUIRED

## Outbound Network Map

| Path | Default | Lab Policy | Evidence |
| --- | --- | --- | --- |
| External LLM | Disabled by `FEATURE_EXTERNAL_LLM=false`. | Mock adapter only until LAB-12 explicit synthetic opt-in. | `config.build_capabilities`, `_blocked_llm_capability`, `wrap_llm`. |
| EBP connector | Disabled because EBP requires external LLM and `FEATURE_EBP_EXTERNAL_SEARCH=true`. | Offline fixture only. | `ebp.py` host allowlist and `api.py` Referensi gate. |
| Harvester | Off because `HARVEST_INTERVAL_SEC=0`. | Must remain disabled; test attempted activity. | `harvester.start` returns false for interval <= 0. |
| `populate_sdki.py` | Manual script only. | FORBIDDEN_IN_LAB; do not call. | HTTPS-only `api.anthropic.com` validator and `# nosec B310` on validated line. |
| `ekstraksi.py` | Manual OCR/LLM utility only. | FORBIDDEN_IN_LAB for real OCR/licensed PDFs; mock OCR only. | Env API key, provider SDKs, `wrap_llm`. |
| Upload parser child | No intended outbound; runtime guards block socket/urlopen/subprocess. | Real parser with synthetic fixtures only. | `_install_parser_runtime_guards`. |
| Frontend fetch | Backend API only through `NEXT_PUBLIC_API_BASE`. | Future `/lab/*` only after server metadata. | `frontend/lib/api.ts`. |
| Director dashboard fetch | Backend director endpoints only. | Sandbox-only verification; no seed/OTP in trace. | `frontend/app/director-dashboard/page.tsx`. |

## Lab Isolation Design

Selected design: dedicated namespace plus server-authoritative lab metadata.

Target namespace:

```text
/lab/status
/lab/session
/lab/chat
/lab/chat_stream
/lab/analisis
/lab/analisis_multi
/lab/rag
/lab/ebp
/lab/pathway
/lab/photo
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
| Lab Sprint A - Showcase Foundation | Default-false lab flags, clinical_sandbox-only enforcement, controlled_pilot and production rejection, central kill-switch, `/lab/*` namespace, strict fixture loader, trusted fixture root, manifest allowlist, resolved-path containment, traversal/absolute/outside-manifest/symlink escape rejection where detectable, `backend/data_terstruktur/*` rejection, bounded in-memory trace store, opaque `run_id`, TTL, capacity limits, safe field allowlist, persistent non-closable banner, normal-route non-regression tests, offline network-deny tests. | All flags default false; kill-switch closes every `/lab/*` route; normal routes unchanged; fixture loader cannot escape trusted root; trace stores no PHI or secrets; foundation works without internet. |
| Lab Sprint B - Core Feature Activation | Real local auth/session, MFA/rate limit, HMAC audit ledger, upload parser, typed validator, abstention, Mermaid sanitizer, isolated lab feedback memory, deterministic per-stage orchestration mocks, synthetic lexical RAG fixtures, lab-only synthetic registry adapter, offline EBP fixture adapter, OCR deterministic mock, photo deterministic mock, safe trace panel. | Each agent stage invoked; critic affects synthesis; retrieval document IDs and scores visible; synthetic registry works only under `/lab/*`; `SYN-D-001` rejected on normal routes; normal validator rules unchanged; malicious Mermaid inert; feedback memory isolated; OCR/photo explicitly mock. |
| Lab Sprint C - Pitch-Ready Closure | PHI canary red-team, hostile PDF/DOCX tests, offline network-deny closure, browser QA, secret scan, full regression, demo rehearsal, kill-switch rehearsal, audit-ledger verification rehearsal, contributor runbook, feature matrix, known limitations. | Full tests pass; Bandit Medium 0 High 0; frontend lint clean; frontend build pass; npm audit 0 vulnerabilities; PHI canaries absent from outbound, trace, UI, logs, and ledger; offline showcase works; normal routes fail-closed; banner visible/non-closable; kill-switch closes all lab routes. |

## Lab Flag Design

All flags default false and are design-only in Lab 0A.

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

Target structure, not created in Lab 0A:

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

Allowed fields: `run_id`, `mode`, `fixture_case_id`, `route`, `agent_stages`,
`stage_status`, `latency_ms`, `provider_type`, `retrieved_document_ids`,
`retrieval_scores`, `retrieval_source`, `registry_source`,
`registry_authoritative`, `clinical_use_allowed`, `clinical_status`,
`accepted_recommendations`, `nurse_review_required`, `audit_event_ids`, and
`sanitization_status`.

Never include chain-of-thought, raw prompt, raw model output, raw patient
narrative, raw uploaded text, API key, session token, OTP, director seed,
bootstrap secret, provider key, filesystem path, or stack trace.

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
