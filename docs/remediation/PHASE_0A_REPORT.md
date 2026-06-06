# Phase 0A Snapshot - Preflight Inspection

Phase 0A was completed on 2026-06-06. This snapshot summarizes the accepted preflight findings without embedding secrets, raw runtime logs, real patient information, raw clinical uploads, or licensed clinical dataset content.

## Repository State

- Branch: `dev`.
- Pre-existing untracked audit input: `AUDIT.md`.
- Phase 0A added remediation evidence under `docs/remediation/` only.
- Ignored/untracked local runtime and data files include `backend/.cdss_key`, `backend/.director_totp`, `backend/Pdf_Buku_SDKI_OCR.pdf`, `backend/data_terstruktur/`, `backend/venv/`, `frontend/node_modules/`, and `frontend/.next/`.

## Baseline Summary

- Backend compile passed.
- Backend unittest discovery failed because `backend/tests` was absent/not importable.
- `pytest`, `bandit`, `pip-audit`, and `semgrep` were unavailable locally.
- Frontend lint failed with existing React compiler/hook errors and warnings.
- Frontend `npm audit --audit-level=moderate` reported no vulnerabilities.
- Frontend build capture was ambiguous in Phase 0A and must be recaptured reliably in Phase 0B.

## Verified Findings

- Raw synthetic PHI canaries could reach outbound LLM/EBP/streaming paths.
- Upload parsing used extension-based routing and a non-killable thread timeout.
- Mermaid rendering used loose security and direct SVG `innerHTML` injection.
- Clinical output lacked deterministic schema and registry validation.
- Local SDKI data was ignored/untracked, incomplete, and not clinically approved.
- API keys were sent in request bodies as well as Authorization headers.
- Session reset and director MFA controls were insufficient.
- The local hash-chain audit ledger was overstated as WORM.
- Clinical photo analysis was implied by UI but not actually implemented.
- CI and dependency reproducibility gates were incomplete.
- Documentation overstated production, compliance, and clinical readiness.

## Phase 0B Starting Position

Gate A is not passed. Phase 0B may make the system truthful and fail-closed by default, but Gate A still requires later verification of PHI firewall, safe streaming, clinical validation, registry quarantine, Mermaid hardening, and isolated upload parsing.

## Phase 0B Follow-Up

Phase 0B was applied on 2026-06-06. It added default `clinical_sandbox` mode, server-authoritative capability metadata, frontend fail-closed capability handling, visible sandbox labeling, default-off harvester startup, and truthful sandbox documentation.

Phase 0B also recaptured the frontend build reliably: `npm --prefix frontend run build` exited 0 in 9099 ms with empty stderr. Frontend lint still fails with existing React hook/ref errors, and Gate A remains not passed until later safety controls are complete.
