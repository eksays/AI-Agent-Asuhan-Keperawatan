# Phase 9 P9-B - Governed Synthetic Lexical RAG Plan

P9-B implements a synthetic-only lexical retrieval pipeline for explicit local and PostgreSQL integration testing. It does not add a product API route, frontend integration, real corpus ingestion, licensed clinical body copying, patient data processing, PHI processing, embeddings, vector retrieval, hybrid retrieval, reranking, external provider calls, registry activation, or clinical validation claims.

Implemented scope:

- Generated synthetic fixture pack under `backend/tests/fixtures/rag_synthetic/` with manifest-only loading and synthetic safety labels.
- Deterministic hierarchy-aware chunking using NFKC normalization, heading association, list/table grouping, bounded overlap, duplicate suppression, stable chunk IDs, and `fts_config_code=simple`.
- Governed synthetic ingestion service for explicit operator/test invocation only.
- Synthetic release manifest creation and synthetic-only active pointer update for test retrieval.
- PostgreSQL lexical FTS retrieval using parameterized `websearch_to_tsquery('simple', ...)`.
- Safe citation packaging with bounded plain-text excerpts and inert markup handling.
- Typed abstention reason codes with no raw query, raw exception, stack trace, corpus body, PHI, or prompt returned.
- Metadata-only telemetry in `rag_retrieval_events` using bounded allowlisted fields.

Truthful labels:

- P9-A foundation schema: implemented.
- Governed synthetic ingestion: implemented for explicit synthetic tests only.
- Deterministic lexical chunking: implemented for generated synthetic fixtures only.
- Lexical PostgreSQL FTS service: implemented for explicit synthetic tests only.
- Product retrieval route: disabled and not implemented.
- pgvector: available but not installed.
- Optional vector schema: defined but not applied.
- Embeddings, vector retrieval, hybrid retrieval, reranking, and external embedding providers: not implemented.
- Real corpus ingestion and licensed clinical body copying: forbidden.
- Registry activation: false.
- Gate A/B/C: unmet.

P9-B remains a sandbox checkpoint only. It is not patient-care software, not clinically validated, not hospital-ready, not production-ready, and not compliant.
