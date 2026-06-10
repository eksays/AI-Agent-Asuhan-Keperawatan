# Phase 9 - Governed RAG Corpus Foundation Plan

## P9-A Scope

P9-A adds a governed RAG corpus foundation only. It does not enable product retrieval, hybrid retrieval, vector retrieval, reranking, external embedding providers, real corpus ingestion, licensed clinical body storage, patient-data ingestion, PHI processing, registry activation, or clinical validation claims.

Current product RAG remains a synthetic lexical prototype based on local token overlap. Hybrid retrieval, embeddings, and pgvector-backed semantic retrieval are not implemented. pgvector is probed and prepared as a proposed backend only. Qdrant is deferred as an optional future adapter if later benchmarks prove PostgreSQL insufficient.

## Architecture Decisions

| Area | P9-A Decision | Safety Result |
|---|---|---|
| Migration ownership | RAG uses `backend/rag_migrations.py` and `rag_schema_migrations` | Registry migrations remain untouched |
| Migration journal | Stores migration id, name, checksum, and timestamp | Checksum drift fails closed |
| Migration execution | Explicit `rag_db_migrate.py` only, with bounded advisory lock | No API startup mutation |
| Readiness probe | `rag_db_probe.py` is read-only | No extension install or schema mutation |
| Lexical core | Core corpus schema and FTS work without pgvector | PostgreSQL lexical baseline remains usable |
| pgvector | Optional explicit admin migration with `--enable-pgvector` | Extension presence never enables retrieval |
| Active release pointer | Table exists but remains empty in P9-A | No product activation flow |
| Telemetry | Bounded allowlisted metadata only | No raw query, prompt, PHI, path, URL, or credentials |

## Default-Off Runtime

All RAG flags default to disabled:

```text
RAG_RUNTIME_MODE=disabled
RAG_STORE_ENABLED=false
RAG_INGESTION_ENABLED=false
RAG_LEXICAL_RETRIEVAL_ENABLED=false
RAG_VECTOR_RETRIEVAL_ENABLED=false
RAG_INDEX_ACTIVATION_ENABLED=false
RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED=false
```

`RAG_RUNTIME_MODE=synthetic_corpus_test` is allowed only in `APP_MODE=clinical_sandbox` and only while `REGISTRY_ACTIVATION_ENABLED=false`. Controlled-pilot and production modes reject synthetic corpus mode and experimental RAG activation flags.

## Phase Boundaries

- P9-A may create schema and run synthetic-only tests.
- P9-A must not ingest `backend/data_terstruktur/*`.
- P9-A must not copy SDKI, SLKI, SIKI, NANDA, NOC, or NIC body text.
- P9-A must not store patient data or PHI.
- P9-A must not call external LLMs, external EBP services, or embedding APIs.
- P9-A must not activate registry data or RAG index releases.

## Exit Criteria

- Core lexical migrations pass without pgvector.
- Optional pgvector readiness checks report only safe booleans.
- `rag_schema_migrations` detects checksum mismatch.
- Migration attempts use a bounded advisory lock.
- Staging rows remain non-searchable and cannot enter release manifests.
- `rag_retrieval_events` contains only bounded metadata fields.
- Optional PostgreSQL integration is explicit opt-in, synthetic-only, and cleans up to zero synthetic rows.
- Gate A, Gate B, and Gate C remain unmet.
