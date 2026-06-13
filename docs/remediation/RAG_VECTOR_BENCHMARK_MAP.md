# RAG Vector Benchmark Map

P9-C benchmark coverage is synthetic retrieval infrastructure verification only. It does not validate semantic quality, clinical quality, production readiness, hospital readiness, compliance, or a pgvector-versus-Qdrant architecture decision.

## Pipeline

| Stage | Boundary | Status |
|---|---|---|
| Synthetic corpus | Generated fixtures only; no real corpus and no licensed clinical content | Integration passed; cleanup rows 0 |
| Synthetic vectors | `synthetic-hash-vector-v1`, SHA-256 deterministic, dimension 8 | 54 inserted across isolated test runs; cleanup rows 0 |
| Vector storage | pgvector extension and optional schema only after explicit operator action | Installed/applied on isolated test database only |
| Retrieval | Exact-cosine synthetic vector baseline only | 4 exact-cosine queries executed |
| Benchmark | Infrastructure hit-rate/cleanup checks only | 3 benchmark runs executed |
| Red team | Poisoned synthetic corpus, PHI canaries, dimension errors, duplicate rows, leakage checks | 6 isolated DB rejection checks plus unittest red-team coverage |

Focused unittest counts: synthetic vectors 8, benchmark 5, red-team 9, PostgreSQL vector integration 3. Full discovery ran 494 tests with 18 skips and no failures or errors.

## Explicit Exclusions

- No external embedding provider.
- No ML embedding model.
- No tokenizer.
- No network call.
- No ANN index.
- No HNSW.
- No IVFFlat.
- No hybrid fusion.
- No reranking.
- No Qdrant.
- No product API route.
- No frontend integration.
- No registry activation.

## Gate Status

- P9-C checkpoint committed at `eac151638f5f294cd21ac634c08d5bac41fe130a` was merged into dev at `8c9e0927ab26be381334a9a2222080671fb6df0f`; review-branch and dev GitHub Actions passed.
- Phase 9 is technically closed for synthetic infrastructure scope only.
- Phase 10 has not started.

Gate A, Gate B, and Gate C remain unmet. The benchmark is a sandbox checkpoint only and must not be used for patient care, clinical validation, hospital deployment, production readiness, or compliance claims.
