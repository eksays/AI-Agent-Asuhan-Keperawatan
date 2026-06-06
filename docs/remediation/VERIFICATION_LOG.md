# Verification Log

## Repository State

| Check | Result |
|---|---|
| Branch | `dev` |
| `git status --short` before docs | `?? AUDIT.md` |
| Root files | FastAPI backend, Next.js frontend, `.github/workflows/security-scan.yml`, two Dockerfiles |
| Root `AGENTS.md` / `CLAUDE.md` | Not present |
| Frontend instructions | `frontend/AGENTS.md` says this is a changed Next.js version; `frontend/CLAUDE.md` references `@AGENTS.md` |
| Ignored local runtime/data files | `backend/.cdss_key`, `backend/.director_totp`, `backend/Pdf_Buku_SDKI_OCR.pdf`, `backend/data_terstruktur/`, `backend/venv/`, `frontend/node_modules/`, `frontend/.next/` |

## Baseline Commands

| Command | Result | Notes |
|---|---|---|
| `git status --short` | PASS | Initially `?? AUDIT.md`; after Phase 0A docs, docs are also new. |
| `git branch --show-current` | PASS | `dev` |
| `git log --oneline -n 10` | PASS | Latest commit `57e6820 feat: implement secure message UI with sanitization, typewriter effect, and AI process tracking` |
| `git ls-files` | PASS | Tracked inventory captured. `backend/data_terstruktur` is not tracked. |
| `python -m compileall backend` | PASS | Compiled 3 packages. |
| `python -m unittest discover -s backend/tests -p "*_test.py"` | FAIL | `ImportError: Start directory is not importable: 'backend/tests'` |
| `pytest -q` | UNAVAILABLE | `pytest` not found on PATH. |
| `npm --prefix frontend run lint` | FAIL | 7 errors and 6 warnings, including React set-state-in-effect and ref access during render. |
| `npm --prefix frontend run build` | INCONCLUSIVE | `.next` artifacts and `BUILD_ID` were generated, but shell capture returned only `Finished TypeScript...` and no reliable terminal status. |
| `npm --prefix frontend audit --audit-level=moderate` | PASS | `found 0 vulnerabilities` |
| `bandit -r backend` | UNAVAILABLE | `bandit` not found on PATH. |
| `pip-audit` | UNAVAILABLE | `pip-audit` not found on PATH. |
| `semgrep` | UNAVAILABLE | `semgrep` not found on PATH. |

## Local Reproductions

| Finding | Result | Evidence |
|---|---|---|
| EBP PHI path | CONFIRMED | Monkeypatched `/chat` with `agent=referensi`; captured EBP case contained synthetic canary identifiers. Details are isolated in `reproductions/PHI_LEAK_REPRO.md`. |
| Streaming PHI path | CONFIRMED | Monkeypatched `/chat_stream` flash response returned synthetic canary identifiers to the client. Details are isolated in `reproductions/PHI_LEAK_REPRO.md`. |
| Orchestration review PHI path | CONFIRMED | `build_messages` redacted the line-start synthetic name, but `agents.orchestrate_answer(..., human=raw)` sent raw synthetic canary fields in the medium review pass. |
| Reset authorization | CONFIRMED | `POST /reset` with `fake-session-id` returned `200 {'status': 'ok'}`. |
| Delete unknown session | PARTIAL | `POST /delete_my_data` with fake session returned `409 SESSION_INVALID`; endpoint still relies on session ID possession only. |
| PHI detector coverage | CONFIRMED INCOMPLETE | Sanitizer left email, address, MRN with separators, date of birth, and formatted phone number. |

## External Skill and Governance Sources

Read-only inspection was performed for the requested repositories. No third-party scripts, hooks, or installers were executed.

| Source | What Was Inspected | Practice Adopted |
|---|---|---|
| `https://github.com/openai/skills` | README, `security-best-practices/SKILL.md` | Language/framework security review workflow; secure-by-default boundary checks. |
| `https://github.com/trailofbits/skills` | README, AGENTS, `audit-context-building`, `agentic-actions-auditor`, `insecure-defaults`, hooks listing | Bottom-up context building, fail-open default detection, CI/agent workflow scrutiny. Hooks were not used. |
| `https://github.com/semgrep/skills` | README, AGENTS, `code-security`, `llm-security`, `semgrep` | Pattern-oriented security issue mapping and OWASP LLM risk framing. CLI unavailable locally. |
| `https://github.com/addyosmani/agent-skills` | README, AGENTS, `security-and-hardening`, `code-review-and-quality`, `ci-cd-and-automation`, hooks/scripts listing | Incremental review, CI quality gates, user-input/security boundary checklist. Hooks/scripts were not used. |
| `https://github.com/anthropics/skills` | README, skill tree listing | Skill format/progressive-disclosure reference only; no domain skill adopted. |
| `https://github.com/OWASP/secure-agent-playbook` | README, `agent-security-audit`, `api-security-review`, `web-security-review`, `sca-audit`, `secrets-scan`, scripts requirements | Agent/API/web/SCA/secrets audit structure; no playbook scripts executed. |
| `https://github.com/OWASP/www-project-agentic-skills-top-10` | README, AST01, AST02 | Treat community skills as supply-chain risk; do not execute hooks/scripts blindly. |
| `https://github.com/GSTT-CSC/QMS-Template` | README, hazard log and clinical safety case templates | Hazard-log and safety-case style evidence preservation; non-authoritative reference. |
| `https://github.com/johner-institut/ai-guideline` | README, English guideline opening section | AI medical-device verification/governance checklist framing; non-authoritative reference. |

## Phase 0B Verification - 2026-06-06

| Command | Result | Notes |
|---|---|---|
| `python --version` | PASS | Python 3.11.9 |
| `node --version` | PASS | Node v24.0.2 |
| `npm --version` | PASS | npm 11.3.0 |
| `python -m compileall backend` | PASS | Completed; command also walked ignored `backend/venv`, so output was noisy. |
| `backend\\venv\\Scripts\\python.exe -m unittest discover -s backend\\tests -p "*_test.py"` | PASS | 10 Phase 0B tests passed; FastAPI TestClient emitted a Starlette deprecation warning. |
| `node --test frontend\\tests\\capabilities-fallback.test.mjs` | PASS | 2 tests passed. |
| `npm --prefix frontend run build` | PASS | Captured through `Start-Process`; exit code 0, duration 9099 ms, stderr empty, routes generated. |
| `npm --prefix frontend run lint` | FAIL | 7 errors and 6 warnings remain, including pre-existing React `set-state-in-effect` and ref access findings. |
| `npm --prefix frontend audit --audit-level=moderate` | PASS | `found 0 vulnerabilities`. |
| Browser plugin smoke validation | BLOCKED | Browser runtime loaded, but `agent.browsers.list()` returned `[]`; no in-app browser client was available. |
| HTTP frontend/backend smoke | PASS | `GET /` on port 3000 returned 200 with sandbox and unsupported-feature notices; `GET /capabilities` on port 8000 returned default-disabled unsafe capabilities. Temporary servers were stopped after validation. |

## Phase 0B Capability Evidence

| Capability | Default Result | Evidence |
|---|---|---|
| Application mode | `clinical_sandbox` | `GET /capabilities` returned `app_mode=clinical_sandbox`. |
| External LLM | Disabled | `/chat` Phase 0B test returned 503 with `capability=external_llm`. |
| EBP external search | Disabled | `/chat` Phase 0B test returned 503 with `capability=ebp_external_search`. |
| Clinical photo analysis | Disabled | `/analisis_multi` Phase 0B test returned 503 with `capability=clinical_photo_analysis`. |
| Mermaid pathway rendering | Disabled | `/pathway` Phase 0B test returned 503 with empty `mermaid`. |
| SDKI/SLKI/SIKI/NANDA/NOC/NIC authoritative grounding | Disabled | `/capabilities` returns all registry grounding features disabled. |

## Phase 0B Closure Verification - 2026-06-06

| Check | Result | Evidence |
|---|---|---|
| Repository hygiene | PASS | `git diff --check` is clean after whitespace cleanup. Ignored secrets/runtime/registry files remain ignored. |
| Secret/data scan | PASS | Candidate files contain no `.env`, key files, TOTP seeds, runtime audit logs, raw uploads, or `backend/data_terstruktur/*`. Synthetic canaries are isolated to `docs/remediation/reproductions/PHI_LEAK_REPRO.md`. |
| Route inventory | PASS | FastAPI routes include `/capabilities`, `/chat`, `/chat_stream`, `/analisis`, `/analisis_multi`, `/pathway`, `/daftar/{buku}`, `/entri/{buku}/{kode}`, `/session`, `/reset`, `/delete_my_data`, `/feedback`, and director routes. |
| Environment fail-closed matrix | PASS | Backend unittest suite covers absent APP_MODE, absent flags, sandbox defaults, unsafe override sandbox-only warning, controlled pilot/production override rejection, production prerequisite failure, and malformed APP_MODE failure. |
| Network-deny smoke | PASS | `test_network_deny_smoke_default_sandbox_routes` patches LLM/EBP connectors to raise and exercises `/capabilities`, `/chat`, `/chat_stream`, `/analisis`, `/analisis_multi`, `/pathway`, referensi action, and photo rejection with zero connector invocation. |
| Harvester default-off | PASS | Test verifies `harvester.start(interval=0, topics=(...))` and `harvester.start(interval>0, topics=())` return false while EBP retrieve is patched to raise. |
| Browser-rendered QA | DEFERRED | Browser setup loaded but no browser client was available; `agent.browsers.list()` returned `[]`. HTTP-level validation passed earlier, but visual interaction testing remains pending. |
| Node runtime | FOLLOW-UP | Local verification used Node v24.0.2. Production/pilot runtime should standardize on an approved Node LTS version. |
| Compileall exclusion | FOLLOW-UP | `python -m compileall backend -x "backend[\\/](venv|__pycache__)"` exited 0 but still traversed `backend/venv`; future baseline should use a verified exclusion command. |

## Phase 0B Closure Regression Commands

| Command | Exit Code | Duration | Summary |
|---|---:|---:|---|
| `python -m compileall backend -x "backend[\\/](venv|__pycache__)"` | 0 | 5052 ms | Completed with no stderr, but still walked ignored `backend/venv`. |
| `backend\\venv\\Scripts\\python.exe -m unittest discover -s backend\\tests -p "*_test.py" -v` | 0 | 1020 ms | 17 tests passed. |
| `node --test frontend\\tests\\capabilities-fallback.test.mjs` | 0 | 1020 ms | 4 tests passed. |
| `npm --prefix frontend run build` | 0 | 10103 ms | Next build succeeded; static routes generated; stderr empty. |
| `npm --prefix frontend run lint` | 1 | 5066 ms | 13 problems: 7 errors, 6 warnings. Same count as Phase 0A. |
| `npm --prefix frontend audit --audit-level=moderate` | 0 | 2038 ms | `found 0 vulnerabilities`. |

## Phase 0B Closure Lint Delta

| Metric | Phase 0A | Phase 0B | New Violations Introduced |
|---|---:|---:|---:|
| Errors | 7 | 7 | 0 by count; current errors are existing React `set-state-in-effect` / `refs` findings. |
| Warnings | 6 | 6 | 0 by count; warnings include pre-existing unused imports/no-img/no-unused-expression findings. |
