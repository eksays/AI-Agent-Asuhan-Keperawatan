# Synthetic Integration Lab Backlog

This backlog freezes the three-sprint implementation plan for the synthetic
showcase. Lab 0A is documentation only. Sprint A is now the controlled
foundation implementation patch; Sprint B and Sprint C remain future controlled
patches with focused tests, explicit staging allowlists, and rollback evidence.

Global constraints for every sprint:

- Synthetic data only.
- Normal routes must never silently change behavior.
- Mock adapters are accessible through `/lab/*` only.
- Synthetic registry must never weaken normal validator rules.
- `backend/data_terstruktur/*` remains forbidden.
- Licensed registry content must not be copied.
- External LLM remains disabled during Sprint A-C.
- EBP internet endpoints remain disabled.
- Harvester remains off.
- Trace must not expose chain-of-thought.
- Trace must not contain raw prompts, raw outputs, uploaded text, PHI, tokens,
  OTPs, paths, or stack traces.

## Lab Sprint A - Showcase Foundation

| Scope | Files | Tests | Risks | Rollback |
| --- | --- | --- | --- | --- |
| `SYNTHETIC_LAB_MODE=false` and `SYNTHETIC_DATA_ONLY=false` by default. | `backend/config.py`, capability metadata docs/tests. | Defaults false; malformed env rejected safely. | Accidental lab enablement. | Revert Sprint A config patch. |
| `clinical_sandbox`-only enforcement with `controlled_pilot` and `production` rejection. | Config validation and tests. | Pilot/production reject every lab flag. | Mode confusion. | Revert mode-gate patch. |
| Central kill-switch and `/lab/*` namespace. | Lab route shell or router guard only. | Kill-switch closes every `/lab/*` route. | Partial route activation. | Remove lab router/guard. |
| Strict fixture loader with trusted fixture root and manifest allowlist. | Fixture loader only; no fixture bodies yet except minimal manifest test files if approved in Sprint A. | Path traversal, absolute path, outside-manifest, symlink escape where detectable, and `backend/data_terstruktur/*` rejected. | Fixture escape or local registry exposure. | Remove loader and manifest test assets. |
| Bounded in-memory trace store. | Trace store helper and tests. | Opaque `run_id`, TTL, capacity limits, safe field allowlist, no PHI/secrets. | Trace leakage. | Remove trace store. |
| Persistent non-closable banner contract. | Frontend lab shell only if approved in Sprint A. | Banner visible and non-closable. | UI implies readiness. | Remove lab shell. |
| Normal-route non-regression and offline network-deny tests. | Backend/frontend tests. | Normal routes unchanged; no internet required. | Hidden behavior drift. | Revert Sprint A tests/fixes. |

Sprint A exit criteria:

- all flags default false
- kill-switch closes every `/lab/*` route
- normal routes remain unchanged
- fixture loader cannot escape trusted root
- trace stores no PHI or secrets
- foundation works without internet

Sprint A implementation checkpoint:

- Added default-false `SYNTHETIC_LAB_MODE` and `SYNTHETIC_DATA_ONLY`.
- Added guarded Sprint-A-only routes: `GET /lab/status`, `POST /lab/session`,
  and `GET /lab/trace/{run_id}`.
- Added strict generated-fixture manifest loading with only a harmless
  foundation fixture body.
- Added bounded in-memory trace metadata with opaque `run_id` and safe field
  allowlist.
- Added server-authoritative capability metadata and a persistent non-closable
  frontend banner.
- Did not add mock providers, RAG, registry adapters, EBP fixtures, OCR/photo
  mocks, Mermaid activation, feedback-memory behavior, or external-provider
  adapters.

## Lab Sprint B - Core Feature Activation

Required labels for all UI and traces: REAL LOCAL PATH, SYNTHETIC PROTOTYPE,
DETERMINISTIC MOCK, DISABLED, FORBIDDEN IN LAB.

| Scope | Files | Tests | Risks | Rollback |
| --- | --- | --- | --- | --- |
| Real local auth/session on lab routes. | Lab auth/session route code and tests. | Missing auth/session, wrong owner, expiry, reset/delete. | Weakening normal sessions. | Revert lab routes. |
| Real local MFA/rate limit. | Reuse director/rate-limit controls. | MFA replay/lockout, route-class rate limit. | Treating local MFA as hospital identity. | Disable lab route class. |
| Real HMAC audit ledger. | Reuse audit ledger with safe lab metadata. | Event emission and verifier pass; no PHI/secrets. | Ledger overclaiming. | Revert lab audit integration. |
| Real upload parser. | Lab upload route bound to parser. | Safe TXT, hostile PDF/DOCX, timeout cleanup. | Host isolation limitations. | Disable synthetic uploads. |
| Real typed validator and real abstention. | Lab validator adapter. | Normal validator unchanged; abstention visible. | Synthetic adapter weakens normal rules. | Revert adapter. |
| Real Mermaid sanitizer. | Lab Mermaid route/UI. | Safe payload renders; malicious payload inert. | XSS regression. | Disable lab Mermaid. |
| Isolated lab feedback memory. | Lab memory namespace/store. | No cross-namespace or cross-session recall. | Memory poisoning. | Remove lab store. |
| Deterministic per-stage orchestration mocks. | Lab orchestration mock helpers. | Each stage invoked; critic affects synthesis. | Mock mistaken for swarm intelligence. | Disable multi-agent mock flag. |
| Synthetic lexical RAG fixtures. | Lab RAG fixtures/adapter. | Retrieval document IDs and scores visible. | Hybrid/embedding overclaim. | Remove RAG fixtures/adapter. |
| Lab-only synthetic registry adapter. | Synthetic registry adapter. | Works only under `/lab/*`; `SYN-D-001` rejected on normal routes. | Normal validator weakening. | Remove adapter. |
| Offline EBP fixture adapter. | EBP fixture adapter. | No EBP internet endpoint reached. | Fixture mistaken as evidence source. | Remove adapter. |
| OCR deterministic mock and photo deterministic mock. | Mock adapters and labels. | OCR/photo explicitly labeled mock. | Mock mistaken for clinical feature. | Remove mocks. |
| Safe trace panel. | Frontend trace panel. | Safe field allowlist only; labels visible. | Trace leakage. | Remove panel. |

Sprint B exit criteria:

- each agent stage is invoked
- critic affects synthesis
- retrieval document IDs and scores are visible
- synthetic registry works only under `/lab/*`
- `SYN-D-001` is rejected on normal routes
- normal validator rules remain unchanged
- Mermaid malicious payload is inert
- feedback memory does not cross namespaces
- OCR and photo remain explicitly labeled mock

## Lab Sprint C - Pitch-Ready Closure

| Scope | Files | Tests | Risks | Rollback |
| --- | --- | --- | --- | --- |
| PHI canary red-team. | Backend/frontend red-team tests. | PHI absent from outbound, trace, UI, logs, and ledger. | Missed secondary metadata leak. | Disable lab routes and revert tests/fixes. |
| Hostile PDF and DOCX tests. | Upload security regression fixtures/tests. | Hostile files rejected safely. | Parser bypass. | Disable synthetic uploads. |
| Offline network-deny closure. | Network monkeypatch tests. | Showcase works without internet. | Hidden external call. | Revert offending route/adapter. |
| Browser QA. | Browser-rendered lab tests. | Banner visible/non-closable; trace labels intact. | UI drift. | Revert lab UI patch. |
| Secret scan. | Static and runtime scans. | No keys/tokens/OTP/bootstrap/provider secret in trace/storage. | Secret leakage. | Revert offending code. |
| Full regression. | Backend tests, compileall, Bandit, frontend tests, lint, build, npm audit. | All gates pass. | Regression in earlier phases. | Roll back Sprint C commit. |
| Demo, kill-switch, and audit-ledger rehearsals. | Runbook and verification docs. | Demo path, kill-switch closure, and ledger verifier rehearsed. | Overstated readiness. | Update docs or stop closure. |
| Contributor runbook, feature matrix, known limitations. | Docs only. | Limitations explicit; no production/pilot claims. | Ambiguous handoff. | Revert docs. |

Sprint C exit criteria:

- full tests pass
- Bandit Medium 0 High 0
- frontend lint clean
- frontend build pass
- npm audit 0 vulnerabilities
- PHI canaries absent from outbound, trace, UI, logs, and ledger
- offline showcase works without internet
- normal routes remain fail-closed
- banner is visible and non-closable
- kill-switch closes all lab routes

## External Provider Branch Separation

| Branch | Scope |
| --- | --- |
| `review/synthetic-integration-lab` | offline synthetic showcase only |
| `review/synthetic-external-provider` | optional later branch for DeepSeek or another provider |

External-provider work is not required for Sprint C closure.

## Dependency Freeze

Lab 0A adds no dependencies. Sprint A-C should prefer current project helpers.
Any dependency requires separate risk review, license check, lockfile review, and
audit evidence.
