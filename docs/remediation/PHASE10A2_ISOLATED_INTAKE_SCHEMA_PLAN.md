# Phase 10 P10-A2 — Isolated Database Mutation and Ingestion Integration Plan (P10-A2A)

This document records the design, implementation guards, and verification architecture established in Phase 10 P10-A2A.

## Scope & Purpose (P10-A2A)
P10-A2A hardens the operator-controlled mutation boundary for the intake companion schema and defines isolated integration tests.

> [!WARNING]
> - **Zero Database Mutation**: P10-A2A is strictly non-mutating. No migrations have been run and no DDL/DML has been executed against PostgreSQL.
> - **Integration Tests Not Run**: The integration test module is defined but skipped safely until explicit opt-ins are provided in a later phase.
> - **Product Safety Status**: This software is **not patient-care software**, **not clinically validated**, **not hospital-ready**, and **not compliant** with clinical production environments.

## Healthtech Safety Boundaries & Status

| Invariant | Safety Status in P10-A2A |
| :--- | :--- |
| **PostgreSQL Mutation** | Zero database mutation has occurred. `RAG_CORE_V008` remains unapplied. |
| **Corpus Body Storage** | Disabled (`RAG_BODY_STORAGE_ENABLED=false`). |
| **Real Corpus Ingestion** | Disabled (`RAG_REAL_CORPUS_INGESTION_ENABLED=false`). |
| **Corpus Promotion** | Disabled (`RAG_CORPUS_PROMOTION_ENABLED=false`). |
| **Patient Data & PHI** | Forbidden and not used. |
| **Registry Activation** | Disabled (`REGISTRY_ACTIVATION_ENABLED=false`). |
| **External Providers** | Disabled; no external LLM or embedding provider calls. |
| **Release Gates** | Gates A, B, and C remain unmet. |

## Implementation Details

### 1. Hardened Migration CLI (`rag_db_migrate.py`)
- Exposed `--apply-intake-schema` flag to run `RAG_CORE_V008` only.
- Added early block that returns `no_mutation_flag_specified` and prevents database connection if no flag is specified.
- Validates all 9 environment guards before connection:
  - `APP_MODE == 'clinical_sandbox'`
  - `RAG_RUNTIME_MODE == 'synthetic_corpus_test'`
  - `RAG_ISOLATED_TEST_DATABASE_CONFIRMED == 'true'`
  - `REGISTRY_ACTIVATION_ENABLED == 'false'`
  - `RAG_BODY_STORAGE_ENABLED == 'false'`
  - `RAG_REAL_CORPUS_INGESTION_ENABLED == 'false'`
  - `RAG_CORPUS_PROMOTION_ENABLED == 'false'`
  - `RAG_VECTOR_RETRIEVAL_ENABLED == 'false'`
  - `RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED == 'false'`
- Connects using `REGISTRY_DATABASE_ADMIN_URL` only; pooled runtime URL `REGISTRY_DATABASE_URL` is blocked.
- Safe output prints bounded reason codes only; never prints credentials, URLs, hostnames, database names, usernames, passwords, or raw exceptions.

### 2. Read-Only Database Probe (`rag_db_probe.py`)
- Reports `rag_runtime_mode` as a safe enum string (`disabled`, `synthetic_corpus_test`, or `unknown`).
- Exposes table readiness booleans for:
  - `rag_intake_submissions`
  - `rag_intake_decision_events`
  - `rag_intake_quarantine_records`
- Exposes boolean settings for body storage, real ingestion, promotion, and isolated database attestation.
- Guarantees zero DDL, zero DML, and zero advisory locks during probe execution.

### 3. Isolated Integration Test (`phase10a2_rag_intake_postgres_integration_test.py`)
- Designed to run the intake schema migration and perform checks on an isolated Neon database.
- Verifies exact table and column allowlists.
- Inserts synthetic metadata with prefix `SYN-P10A2-` and verifies constraint rejections.
- Performs mandatory cleanup inside `finally` blocks to return synthetic row counts to zero.
- Skips execution automatically unless `P10A2_POSTGRES_INTEGRATION_TEST=true` is set.
