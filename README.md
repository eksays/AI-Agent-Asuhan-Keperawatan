# CDSS AI Keperawatan

CDSS AI Keperawatan is a **clinical sandbox prototype** for exploring nursing documentation workflows. It is not approved for autonomous clinical decision-making, clinical deployment, or regulatory use. AI-generated suggestions require review by a qualified nurse or clinical reviewer.

The current Phase 0B safety posture is intentionally fail-closed: unsupported or unverified features are disabled by default, and the backend is the source of truth for capability availability through `GET /capabilities`.

## Current Safety Position

- Default application mode: `APP_MODE=clinical_sandbox`.
- External LLM analysis is disabled by default until outbound PHI firewall verification is complete.
- Evidence retrieval from external scholarly services is disabled by default until de-identification enforcement is verified.
- Clinical photo analysis is unavailable; validated OCR or vision processing is not implemented.
- Mermaid pathway rendering is disabled by default until strict SVG sanitization and XSS regression tests pass.
- Local registry files are not approved authoritative clinical references.
- The audit log is a development-only tamper-evident local log, not external append-only storage.
- No legal, regulatory, privacy, clinical, or production-readiness claim is made by this repository.

## Capability Matrix

| Capability | Status | Reason |
|---|---|---|
| External LLM analysis | Disabled by default | Awaiting verified outbound PHI firewall |
| EBP external search | Disabled by default | Awaiting de-identification enforcement |
| Clinical photo analysis | Unavailable | Validated OCR or vision workflow not implemented |
| Mermaid pathway rendering | Disabled by default | Awaiting SVG sanitization and XSS regression suite |
| SDKI authoritative grounding | Unavailable for production | Registry governance incomplete |
| SLKI/SIKI | Unavailable | Approved registries unavailable |
| NANDA/NOC/NIC | Unavailable | Approved registries unavailable |
| Audit ledger | Development only | Local tamper-evident log, not WORM |

## Application Modes

Supported modes:

```text
clinical_sandbox
controlled_pilot
production
```

`clinical_sandbox` is the default when `APP_MODE` is absent. `controlled_pilot` and `production` must be set explicitly. Production mode fails startup unless explicit safety prerequisite flags are present; those flags are placeholders for later verification gates and are not evidence of clinical or regulatory approval by themselves.

## Key Environment Flags

All unsafe feature flags default to `false`.

```text
APP_MODE=clinical_sandbox
FEATURE_EXTERNAL_LLM=false
FEATURE_EBP_EXTERNAL_SEARCH=false
FEATURE_CLINICAL_PHOTO_ANALYSIS=false
FEATURE_MERMAID_PATHWAY_RENDERING=false
ALLOW_UNSAFE_EXTERNAL_LLM_FOR_LOCAL_DEBUG=false
```

`ALLOW_UNSAFE_EXTERNAL_LLM_FOR_LOCAL_DEBUG=true` is accepted only in `clinical_sandbox` mode. It must not be used with real patient data.

## Repository Structure

```text
backend/                  FastAPI backend
frontend/                 Next.js frontend
docs/remediation/         Remediation evidence, risk register, release gates
dokumen pendukung/        Local supporting assets/uploads
```

Important local data and runtime files are intentionally ignored by git, including local secrets, audit logs, virtual environments, generated build artifacts, PDFs, and `backend/data_terstruktur/`. Clinical registry reproducibility, licensing, provenance, and approval are not solved yet.

## Running Locally

Backend:

```bash
cd backend
python -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Verification

Useful local checks:

```bash
python -m compileall backend
backend\venv\Scripts\python.exe -m unittest discover -s backend/tests -p "*_test.py"
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend audit --audit-level=moderate
node --test frontend/tests/capabilities-fallback.test.mjs
```

Some optional security tools may not be installed locally. Do not report unavailable tools as passing.

## Clinical Data Governance

Do not commit local secrets, TOTP seed files, raw patient content, raw clinical uploads, runtime audit logs, or clinical registry files unless licensing, provenance, governance status, and clinical approval are explicitly resolved.

The current local registry data is sandbox-only. Missing or unapproved SDKI/SLKI/SIKI/NANDA/NOC/NIC content must not be filled from model memory or treated as authoritative.

## Remediation Roadmap

See `docs/remediation/` for the remediation plan, verification log, risk register, data governance notes, and release gates.

Gate A is not passed yet. Later phases still need verified PHI firewall controls, safe streaming, typed clinical validation, registry quarantine, Mermaid hardening, upload isolation, authentication/session improvements, and audit redesign.
