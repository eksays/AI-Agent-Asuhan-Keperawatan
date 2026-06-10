# RAG Lexical Retrieval Map

P9-B retrieval is synthetic-only and explicit-test-only. No normal product API route or frontend integration is added.

## Pipeline

| Stage | Control | Status |
|---|---|---|
| Fixture loading | Manifest allowlist, approved fixture root, no traversal, no absolute path, no symlink escape, synthetic metadata required | Implemented |
| Chunking | Deterministic NFKC normalization, heading/list/table grouping, bounded overlap, stable IDs and hashes | Implemented |
| Staging | Staging documents and chunks remain `searchable=false` and TTL-tagged | Implemented |
| Promotion | Approved generated synthetic fixtures only; `synthetic_only=true`, `authority=false`, `clinical_use_allowed=false` | Implemented |
| Release | Synthetic release manifest contains approved synthetic chunks only | Implemented |
| Active pointer | Transactional synthetic-only pointer update for explicit tests | Implemented |
| Retrieval | PostgreSQL FTS with `simple` config and parameterized query | Implemented |
| Citations | Bounded plain-text excerpts, safe synthetic locator metadata, no path/URL/body/prompt/query | Implemented |
| Abstention | Typed safe reason codes | Implemented |
| Telemetry | Bounded metadata-only event, no raw query, no prompt, no PHI | Implemented |

## Non-Goals

- No real registry or clinical corpus activation.
- No SDKI, SLKI, SIKI, NANDA, NOC, or NIC body text ingestion.
- No embeddings, pgvector table use, vector retrieval, hybrid retrieval, reranking, or Qdrant adapter.
- No external LLM, EBP service, or embedding-provider call.
- No patient memory and no PHI processing.

## Retrieval Filters

Retrieval requires an active synthetic release and filters to approved retrieval-eligible chunks where:

- `synthetic_only=true`
- `authority=false`
- `clinical_use_allowed=false`
- `lifecycle_state='approved'`
- release backend is lexical

Staging tables are never queried for retrieval, and `rag_chunk_embeddings` is not queried.
