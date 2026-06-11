# Phase 9 P9-C Vector Readiness Plan

P9-C is a synthetic-only vector readiness and retrieval infrastructure benchmark checkpoint. pgvector was installed explicitly on an operator-attested isolated test database only, and the optional vector schema was applied explicitly for synthetic testing only.

## Scope

- Define an explicit operator-controlled split between pgvector extension installation and optional vector schema application.
- Add deterministic `synthetic-hash-vector-v1` vectors for generated synthetic fixtures only.
- Add an exact-cosine synthetic vector baseline for infrastructure testing only.
- Add synthetic benchmark and red-team tests for retrieval plumbing, cleanup, and telemetry boundaries.

## Non-Goals

- No product API route.
- No frontend integration.
- No real corpus ingestion.
- No licensed clinical body copying.
- No patient data or PHI.
- No external embedding provider, LLM, or EBP call.
- No ANN index, HNSW, IVFFlat, hybrid retrieval, reranking, or Qdrant.
- No clinical registry activation.

## Truthful Status

- P9-B checkpoint `5df6af6b952d50f58b9743a42ca24d3bbf72b14e` was merged into dev at `9dbb6470fc4aea446f9108133bbd262c213113ca`; P9-B dev GitHub Actions passed.
- P9-C checkpoint committed at `eac151638f5f294cd21ac634c08d5bac41fe130a` was merged into dev at `8c9e0927ab26be381334a9a2222080671fb6df0f`; review-branch and dev GitHub Actions passed.
- Phase 9 is technically closed for synthetic infrastructure scope only.
- Phase 10 has not started.
- P9-C focused tests are unittest-discovered: synthetic vectors 8, benchmark 5, red-team 9, and PostgreSQL vector integration 3.
- pgvector extension installation completed only through the explicit isolated admin path.
- vector-schema application completed only through the explicit isolated admin path.
- Integration inserted 54 synthetic vectors across test runs, executed 4 exact-cosine queries, 1 lexical query, 3 benchmark runs, and 6 red-team rejection checks.
- Cleanup verified synthetic vector rows 0, synthetic corpus rows 0, staging rows 0, active synthetic pointers 0, real corpus rows 0, registry activation false, and external provider calls 0.
- `synthetic-hash-vector-v1` is deterministic plumbing only.
- The exact-cosine baseline is not semantic retrieval-quality validation and not clinical retrieval-quality validation.
- The benchmark does not decide pgvector versus Qdrant.
- Gate A, Gate B, and Gate C remain unmet.
- This is not patient-care software, not clinically validated, not hospital-ready, not production-ready, and not compliant.
