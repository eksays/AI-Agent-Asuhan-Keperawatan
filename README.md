# CDSS AI Keperawatan

CDSS AI Keperawatan is a **clinical sandbox prototype** for exploring nursing documentation workflows. It is not approved for autonomous clinical decision-making, clinical deployment, or regulatory use. AI-generated suggestions require review by a qualified nurse or clinical reviewer.

The current safety posture is intentionally fail-closed: unsupported or unverified features are disabled by default, and the backend is the source of truth for capability availability through `GET /capabilities`. Phase 7 adds a local HMAC-chained audit ledger, but identity, rate limits, sessions, and audit storage remain sandbox controls rather than production distributed enforcement.

## Current Safety Position

- Default application mode: `APP_MODE=clinical_sandbox`.
- External LLM analysis is disabled by default until outbound PHI firewall verification is complete.
- Evidence retrieval from external scholarly services is disabled by default until de-identification enforcement is verified.
- Clinical photo analysis is unavailable; validated OCR or vision processing is not implemented.
- Mermaid pathway rendering is disabled by default until strict SVG sanitization and XSS regression tests pass.
- Phase 9 RAG corpus foundations are default-off. P9-B adds governed synthetic ingestion, deterministic chunking, and PostgreSQL lexical FTS retrieval for explicit synthetic tests only; product retrieval routes, hybrid retrieval, embeddings, vector retrieval, reranking, and external embedding providers are not implemented.
- Local registry files are not approved authoritative clinical references.
- API keys are accepted only through Authorization: Bearer <key>; body, query-string, and cookie API-key transport is not supported.
- Browser-carried shared API keys are visible to the browser client; this is a sandbox containment control, not confidential server-side authentication.
- Server-issued `session_id` values must be paired with the per-session `X-Session-Token`; the server stores only a token digest.
- Director MFA includes replay rejection and lockout, but replay and rate-limit state is in memory only.
- The audit ledger is a development-only HMAC-chained local ledger. It is tamper-evident only while the key remains secret; it is not WORM, immutable storage, a digital signature, external append-only storage, or valid-prefix truncation proof without an external checkpoint/archive.
- No legal, regulatory, privacy, clinical, controlled-pilot, hospital, or production-readiness claim is made by this repository.

## Capability Matrix

| Capability | Status | Reason |
|---|---|---|
| External LLM analysis | Disabled by default | Awaiting verified outbound PHI firewall |
| EBP external search | Disabled by default | Awaiting de-identification enforcement |
| Clinical photo analysis | Unavailable | Validated OCR or vision workflow not implemented |
| Mermaid pathway rendering | Disabled by default | Awaiting SVG sanitization and XSS regression suite |
| Governed RAG corpus | Synthetic test pipeline only | P9-B supports generated synthetic ingestion, chunking, lexical FTS retrieval, citation packaging, abstention, and metadata telemetry for explicit tests; no real corpus or product retrieval |
| Hybrid/vector retrieval | Not implemented | pgvector is proposed/probed only; embeddings are not implemented |
| SDKI authoritative grounding | Unavailable for production | Registry governance incomplete |
| SLKI/SIKI | Unavailable | Approved registries unavailable |
| NANDA/NOC/NIC | Unavailable | Approved registries unavailable |
| Audit ledger | Development only | Local HMAC tamper evidence; not WORM, immutable storage, non-repudiation, or complete truncation detection |

## Application Modes

Supported modes:

```text
clinical_sandbox
controlled_pilot
production
```

`clinical_sandbox` is the default when `APP_MODE` is absent. `controlled_pilot` and `production` must be set explicitly. Controlled-pilot and production modes fail startup if API keys, the server secret, or director bootstrap values are missing, weak, or placeholder-like. Production mode also fails startup unless explicit safety prerequisite flags are present; those flags are placeholders for later verification gates and are not evidence of clinical or regulatory approval by themselves.

## Key Environment Flags

All unsafe feature flags default to `false`.

```text
APP_MODE=clinical_sandbox
FEATURE_EXTERNAL_LLM=false
FEATURE_EBP_EXTERNAL_SEARCH=false
FEATURE_CLINICAL_PHOTO_ANALYSIS=false
FEATURE_MERMAID_PATHWAY_RENDERING=false
ALLOW_UNSAFE_EXTERNAL_LLM_FOR_LOCAL_DEBUG=false
CDSS_API_KEYS=test-key
CDSS_SECRET_KEY=local-sandbox-secret-change-me
DIRECTOR_ENROLLMENT_ENABLED=false
AUDIT_LEDGER_HMAC_KEY=
AUDIT_LEDGER_KEY_ID=audit-ledger-local-v1
AUDIT_LEDGER_PATH=
RAG_RUNTIME_MODE=disabled
RAG_STORE_ENABLED=false
RAG_INGESTION_ENABLED=false
RAG_LEXICAL_RETRIEVAL_ENABLED=false
RAG_VECTOR_RETRIEVAL_ENABLED=false
RAG_INDEX_ACTIVATION_ENABLED=false
RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED=false
RAG_SYNTHETIC_FIXTURE_ROOT=
RAG_MAX_DOCUMENT_CHARS=12000
RAG_MAX_STAGING_CHUNKS=200
RAG_CHUNK_TARGET_WORDS=90
RAG_CHUNK_OVERLAP_WORDS=12
RAG_MAX_RESULTS=5
RAG_MAX_EXCERPT_CHARS=360
RAG_MIN_LEXICAL_RANK=0.01
RAG_MAX_SELECTED_CHUNK_IDS=8
RAG_STAGING_TTL_SECONDS=3600
```

`ALLOW_UNSAFE_EXTERNAL_LLM_FOR_LOCAL_DEBUG=true` is accepted only in `clinical_sandbox` mode. It must not be used with real patient data. `test-key` is a sandbox default only; controlled-pilot and production modes require explicit strong `CDSS_API_KEYS`, `CDSS_SECRET_KEY`, `DIRECTOR_BOOTSTRAP`, and `AUDIT_LEDGER_HMAC_KEY` values. In sandbox mode, persistent local audit ledger storage also requires an explicit strong `AUDIT_LEDGER_HMAC_KEY`; otherwise the backend uses an ephemeral in-process ledger for local development.

## Repository Structure

```text
backend/                  FastAPI backend
frontend/                 Next.js frontend
docs/remediation/         Remediation evidence, risk register, release gates
dokumen pendukung/        Local supporting assets/uploads
```

Important local data and runtime files are intentionally ignored by git, including local secrets, audit logs, virtual environments, generated build artifacts, PDFs, and `backend/data_terstruktur/`. Clinical registry reproducibility, licensing, provenance, and approval are not solved yet. Local session, MFA replay, and rate-limit state are in memory and are not durable across restarts or multiple instances.

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

Phase 9 P9-A source checkpoint `96024f43f41b1f1d9afca08b6b2d5db4b167cb9a` was merged into dev at `59884ecfba983d02924fb1cd4d5a81ff0af46455`, with dev GitHub Actions passing after merge.

Phase 9 P9-B adds generated synthetic fixture ingestion, deterministic hierarchy-aware chunking, synthetic-only PostgreSQL lexical FTS retrieval, safe citation packaging, typed abstention, and metadata-only retrieval telemetry for explicit local tests only. At this checkpoint P9-B is a closure-reviewed checkpoint candidate on the review branch and has not been merged into dev. It does not add a product retrieval route, frontend integration, real corpus ingestion, licensed clinical content copying, patient data ingestion, PHI storage, embeddings, vector retrieval, hybrid retrieval, reranking, external embedding providers, or registry activation. pgvector remains available but not installed; the optional vector schema remains defined but unapplied.

## Remediation Roadmap

See `docs/remediation/` for the remediation plan, verification log, risk register, data governance notes, and release gates.

Gate A is not passed yet. Phase 0B through Phase 9 P9-B controls are sandbox checkpoints only. Later work still needs durable identity/session/rate-limit storage, formal registry and clinical review, browser-rendered QA disposition, hard parser resource controls, external immutable audit storage or equivalent audit service, CI enforcement, governed real corpus approval, benchmarked retrieval, and legal/regulatory review before any pilot or production claim.


Director MFA enrollment is disabled by default. Local sandbox provisioning requires DIRECTOR_ENROLLMENT_ENABLED=true and X-Director-Bootstrap; controlled-pilot and production provisioning workflows are not implemented.
