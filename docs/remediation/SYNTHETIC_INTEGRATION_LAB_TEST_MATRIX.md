# Synthetic Integration Lab Test Matrix

This matrix defines required synthetic-only coverage before the lab can be used
as a feature-surface test harness. Lab 0A does not create fixtures or tests.
Lab Sprint A adds foundation-only tests and one harmless generated fixture case;
Lab Sprint B adds offline synthetic core feature tests and generated fixtures;
Sprint C scenarios remain pending until the pitch-ready closure patch.

## Fixture Metadata Requirements

| Field | Required Value |
| --- | --- |
| `fixture_id` | Stable fake id, for example `SYN-D-001`, `SYN-O-001`, or `SYN-I-001`. |
| `fixture_version` | Explicit version string. |
| `synthetic_only` | `true`. |
| `authoritative` | `false`. |
| `clinical_use_allowed` | `false`. |
| `source_type` | `generated_fixture`. |
| `created_for` | `security_ux_orchestration_testing`. |

## Truthful Capability Labels Under Test

| Feature | Required Label |
| --- | --- |
| Multi-agent behavior | multi-stage agent orchestration prototype |
| Swarm coordination | NOT SUPPORTED |
| RAG behavior | synthetic lexical RAG prototype |
| Hybrid / embedding / reranking | NOT SUPPORTED |
| OCR | DETERMINISTIC MOCK ONLY UNDER `/lab/ocr` |
| Photo workflow | DETERMINISTIC MOCK ONLY UNDER `/lab/photo` |

Forbidden wording in test fixtures, UI labels, and docs: validated swarm,
clinical swarm intelligence, hybrid clinical RAG, validated clinical RAG, and
production-ready.

## Three-Sprint Test Coverage

| Sprint | Coverage Focus | Closure Evidence |
| --- | --- | --- |
| Lab Sprint A - Showcase Foundation | Default-false flags, sandbox-only mode, pilot/production rejection, central kill-switch, `/lab/*` namespace, strict fixture loader, trusted root containment, bounded safe trace store, banner contract, normal-route non-regression, offline network deny. | All flags false by default; kill-switch closes lab routes; loader cannot escape root; trace stores no PHI/secrets; no internet required. |
| Lab Sprint B - Core Feature Activation | Real local auth/session/MFA/rate/audit/upload/validator/abstention/Mermaid paths; isolated feedback; deterministic orchestration mocks; synthetic lexical RAG; synthetic registry; offline EBP; OCR/photo mocks; safe trace panel. | Stage invocation, critic influence, retrieval ids/scores, synthetic registry only under `/lab/*`, `SYN-D-001` rejected on normal routes, malicious Mermaid inert, OCR/photo mock labels. |
| Lab Sprint C - Pitch-Ready Closure | PHI canary red-team, hostile uploads, network deny, browser QA, secret scan, full regression, demo/kill-switch/audit-ledger rehearsals, runbook, feature matrix, limitations. | Full tests pass; Bandit Medium 0 High 0; lint/build/audit pass; canaries absent from outbound/trace/UI/logs/ledger; offline showcase works; normal routes fail-closed. |

## Sprint A Implemented Test Coverage

| Area | Implemented Evidence | Remaining Scope |
| --- | --- | --- |
| Mode gates | Flags default false; sandbox requires lab mode plus synthetic-data-only; pilot/production reject lab flags; offline lab profile rejects external LLM, EBP search, photo analysis, Mermaid rendering, and harvester activity. | Sprint B feature-specific flags now add per-route fail-closed checks. |
| Kill-switch | Disabled `/lab/status`, `/lab/session`, and `/lab/trace/*` return `synthetic_lab_disabled` before side effects. | Future lab routes must use the same guard. |
| Fixtures | Manifest metadata, approved synthetic parent containment, traversal, absolute path, outside-manifest, missing file, forbidden `data_terstruktur`, upload/runtime/hospital/patient-record roots, invalid metadata, external absolute roots, and symlink escape where detectable are tested. | Sprint B adds generated cases, RAG, registry, EBP, upload, rendering, image/mock, and expected-output fixtures. |
| Trace | Opaque `run_id`, TTL, max active runs, stage/document bounds, metadata byte bound, unknown-field rejection, PHI canary rejection, and secret canary rejection are tested. | Sprint B adds feature-stage trace emission, safe audit metadata, and source-tested trace-panel labels. |
| Frontend banner | Source test verifies server-authoritative `synthetic_lab_enabled`, non-closable banner text, and no browser storage. | Browser-rendered QA remains a Sprint C closure item. |
| Offline network deny | Sprint A test denies `socket.create_connection`, external `socket.connect`, `urllib.request.urlopen`, provider factory, and HTTP client transports while lab status/session, loader, and trace operations pass. | Future adapters must add their own network-deny assertions. |

## Sprint B Implemented Test Coverage

| Area | Implemented Evidence | Remaining Scope |
| --- | --- | --- |
| Sprint B flags | Default false; require `APP_MODE=clinical_sandbox`, `SYNTHETIC_LAB_MODE=true`, and `SYNTHETIC_DATA_ONLY=true`; controlled-pilot and production reject Sprint B flags. | None for offline core flags; external-provider opt-in remains separate. |
| Guarded lab routes | `/lab/run`, `/lab/rag`, `/lab/registry`, `/lab/ebp`, `/lab/upload`, `/lab/pathway`, `/lab/ocr`, `/lab/photo`, and `/lab/feedback` require auth, lab session headers, route-class rate limit, and feature-specific flags. | Browser interaction QA remains Sprint C. |
| Trace ownership | Trace reads require the creating bearer principal, matching lab session id, and matching lab session token; random ids, expired traces, cross-session reads, cross-principal reads, missing token, wrong token, and `run_id` alone are denied safely. | Browser-rendered trace retrieval remains Sprint C. |
| Fixture containment | Manifest coverage, duplicate paths, duplicate fixture ids, unknown categories, non-JSON entries, oversized fixtures, deeply nested fixtures, forbidden roots, traversal, absolute paths, and symlink escapes where detectable are rejected. | Windows symlink creation may still skip where OS privilege is unavailable. |
| Multi-stage prototype | Stage order, critic influence, stage failure, timeout abstention, and unknown stage rejection are tested. | No swarm coordination or real provider orchestration is claimed. |
| Synthetic lexical RAG | Stable document ids/scores, top-k bounding, empty-query weak context, unknown corpus rejection, and no raw corpus body in trace are tested. | No embedding, hybrid retrieval, reranking, or evidence-quality claim. |
| Synthetic registry | `SYN-D-001` is lab-only, authoritative false, clinical-use false, and rejected by normal code-format policy. | No official registry activation. |
| Offline EBP | Fixture-only adapter works while EBP internet connector is patched to fail. | Fixture is not current medical evidence. |
| Uploads and Mermaid | Safe TXT, hostile PDF, hostile DOCX, safe Mermaid, and malicious Mermaid tests pass through lab-only boundaries. | Full rendered Mermaid browser QA remains Sprint C. |
| OCR/photo mocks | Mock labels are explicit and always return `clinical_use_allowed=false`. | No OCR SDK, image model, or clinical interpretation. |
| Feedback memory | Cross-session and normal/lab namespace isolation are tested with PHI/secret canary rejection. | No authoritative learning or durable memory. |
| Audit/trace/UI | Safe audit metadata, safe trace allowlist, PHI/secret absence, and trace-panel labels are tested. | PHI canary red-team across UI/logs/ledger remains Sprint C closure. |
| Normal-route non-regression | Normal chat, stream, analysis, pathway, feedback, registry, EBP, photo, Mermaid, and harvester gates remain unchanged even when all lab flags are true. | Full regression and browser QA remain Sprint C. |

External-provider work remains separate: `review/synthetic-integration-lab` is
offline synthetic showcase only, while `review/synthetic-external-provider` is
the optional later branch for DeepSeek or another provider. External-provider
work is not required for Sprint C closure.

## Required Scenarios

| Area | Scenario ID | Scenario | Expected Result | Evidence |
| --- | --- | --- | --- | --- |
| Mode gates | LAB-TM-001 | Lab flags absent | All lab capabilities disabled; `/lab/*` closed. | Capability response and route denial. |
| Mode gates | LAB-TM-002 | Lab enabled in `clinical_sandbox` | Only selected synthetic capabilities enabled. | Server metadata and audit enablement event. |
| Mode gates | LAB-TM-003 | Lab enabled in `controlled_pilot` | Config rejects lab flags. | Runtime/config test. |
| Mode gates | LAB-TM-004 | Lab enabled in `production` | Config rejects lab flags. | Runtime/config test. |
| Kill-switch | LAB-TM-005 | Kill-switch off | All `/lab/*` paths close before side effects. | Route tests and no provider/upload/trace work. |
| Fixtures | LAB-TM-006 | Fixture manifest invalid | Loader rejects safely without body leak. | Safe reason code. |
| Fixtures | LAB-TM-007 | Fixture `synthetic_only` missing | Loader rejects. | Validation issue code. |
| Forbidden data | LAB-TM-008 | Real registry path access attempt | Non-fixture registry path rejected. | Safe denial without path leak. |
| Forbidden data | LAB-TM-009 | `backend/data_terstruktur` access attempt | Lab loader refuses ignored/local registry data. | Scanner and route denial. |
| Network | LAB-TM-010 | External provider without opt-in | Blocked before network call. | Monkeypatched network count = 0. |
| Network | LAB-TM-011 | Harvester activity attempt | Harvester remains inactive. | Interval zero and no background call. |
| Auth/session/control | LAB-TM-012 | Auth missing | Protected lab route rejects safely. | HTTP status and safe body. |
| Auth/session/control | LAB-TM-013 | Session token missing | Session-bound lab route rejects. | `session_token_invalid` or equivalent. |
| Auth/session/control | LAB-TM-014 | Rate-limit enforcement | Route-class limiter returns safe 429. | Retry-After and audit event. |
| Auth/session/control | LAB-TM-015 | MFA lockout | Director sandbox MFA locks after failures. | `mfa_locked`; no seed/OTP leak. |
| Audit ledger | LAB-TM-016 | Audit ledger event emission | Lab route emits safe event ids. | Event id list and verifier success. |
| Audit ledger | LAB-TM-017 | Audit ledger PHI absence | PHI canary absent from ledger. | Ledger scan. |
| Uploads | LAB-TM-018 | Upload safe TXT | Parser accepts synthetic TXT but no clinical authority. | Parser ok; clinical_use_allowed=false. |
| Uploads | LAB-TM-019 | Upload hostile PDF | Active/malformed PDF rejected safely. | Safe parser reason. |
| Uploads | LAB-TM-020 | Upload hostile DOCX | Macro/archive/path/external DOCX rejected safely. | Reason code and workspace cleanup. |
| Mermaid | LAB-TM-021 | Mermaid safe payload | Safe fixture renders through sanitizer. | Sanitizer boundary present. |
| Mermaid | LAB-TM-022 | Mermaid malicious payload | Malicious fixture rejected. | No script/style/link execution. |
| Multi-agent | LAB-TM-023 | Multi-agent stage invocation | Deterministic mocks invoked in expected order. | Trace stage labels only. |
| Multi-agent | LAB-TM-024 | Critic influence | Critic mock notes affect synthesis deterministically. | Expected output and trace. |
| Multi-agent | LAB-TM-025 | Synthesis behavior | One final mock answer; raw notes not leaked. | Output assertion and forbidden-field scan. |
| RAG/registry/status | LAB-TM-026 | RAG fixture retrieval | Expected document ids and scores returned. | Trace ids and scores. |
| RAG/registry/status | LAB-TM-027 | RAG weak-context abstention | Weak/no context yields explicit abstention. | `accepted_recommendations=false`. |
| RAG/registry/status | LAB-TM-028 | Registry-authoritative false | Synthetic registry reports false authority. | Response and trace assertion. |
| RAG/registry/status | LAB-TM-029 | Clinical-use allowed false | Lab output reports `clinical_use_allowed=false`. | Response and UI assertion. |
| OCR/photo | LAB-TM-030 | OCR mock label | OCR route returns explicit MOCK label only. | Response and trace label. |
| OCR/photo | LAB-TM-031 | Photo mock label | Photo route returns explicit MOCK label only. | Response and trace label. |
| Feedback | LAB-TM-032 | Feedback cross-session isolation | Session A feedback cannot influence Session B. | Isolation assertions. |
| PHI/secret canaries | LAB-TM-033 | PHI canary absence from UI | Canary not rendered. | DOM/text scan. |
| PHI/secret canaries | LAB-TM-034 | PHI canary absence from outbound | Canary absent from mocked provider payloads. | Mock provider capture. |
| PHI/secret canaries | LAB-TM-035 | PHI canary absence from trace | Canary absent from trace JSON. | Trace scan. |
| PHI/secret canaries | LAB-TM-036 | PHI canary absence from ledger | Canary absent from ledger lines. | Ledger scan. |
| PHI/secret canaries | LAB-TM-037 | Secret absence from trace | API keys, tokens, OTPs, bootstrap secrets, and provider keys absent. | Trace forbidden-token scan. |
| PHI/secret canaries | LAB-TM-038 | Secret absence from frontend storage | No API key/session/director secret in browser storage. | Static and browser storage tests. |

## Scenario Count Summary

| Area | Scenario Count | Key Scenarios |
| --- | --- | --- |
| Mode gates | 4 | Flags absent, sandbox allowed, pilot rejected, production rejected. |
| Kill-switch | 1 | Kill-switch closes all lab paths. |
| Fixtures | 2 | Invalid manifest and missing `synthetic_only`. |
| Forbidden data | 2 | Real registry path and `backend/data_terstruktur` blocked. |
| Network | 2 | External provider without opt-in and harvester activity attempt. |
| Auth/session/control | 4 | Auth missing, session missing, rate limit, MFA lockout. |
| Audit ledger | 2 | Event emission and PHI absence. |
| Uploads | 3 | Safe TXT, hostile PDF, hostile DOCX. |
| Mermaid | 2 | Safe payload and malicious payload. |
| Multi-agent | 3 | Stage invocation, critic influence, synthesis. |
| RAG/registry/status | 4 | Fixture retrieval, weak-context abstention, authority false, clinical-use false. |
| OCR/photo | 2 | OCR mock label and photo mock label. |
| Feedback | 1 | Cross-session isolation. |
| PHI/secret canaries | 6 | UI, outbound, trace, ledger, trace secrets, frontend storage. |
| Total | 38 | Full synthetic lab acceptance matrix. |

## Forbidden Shortcut Assertions

| Shortcut | Required Assertion |
| --- | --- |
| Enable `backend/data_terstruktur/*` | Lab attempt to read it fails. |
| Copy licensed registry content | Fixture scanner rejects non-synthetic source metadata. |
| Call external providers by default | Network monkeypatch records zero provider calls. |
| Call EBP internet endpoints by default | EBP HTTP functions are not reached. |
| Simulate unsupported features on normal routes | Normal routes keep capability-denied behavior. |
| Mark mock output as validated | Mock traces show MOCK/PROTOTYPE and accepted=false. |
| Bypass typed validator | Lab clinical-like paths pass validator or explicit abstention boundary. |
| Bypass abstention | Weak or missing context returns abstention. |
| Expose chain-of-thought | Trace rejects chain-of-thought/raw prompt/raw output fields. |
| Merge lab code into dev automatically | Branch and staging checks remain explicit and review-only. |
