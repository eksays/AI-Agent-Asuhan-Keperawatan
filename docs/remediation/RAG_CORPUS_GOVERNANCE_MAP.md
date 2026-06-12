# RAG Corpus Governance Map - Phase 9 P9-A

P9-A creates governance foundations for a future corpus-backed retrieval system. It does not create an approved corpus, activate retrieval, or make clinical-readiness claims.

## Truthful Current State

| Area | State |
|---|---|
| Product RAG | Synthetic lexical prototype only |
| Hybrid retrieval | Not implemented |
| Embeddings | Not implemented |
| External embedding provider | Disabled and not integrated |
| pgvector | Proposed and safely probed during P9-A |
| Qdrant | Deferred optional adapter only if benchmarks require it |
| Registry activation | Remains false |
| Gate A/B/C | Remain unmet |

## Corpus Lifecycle

| Entity | Lifecycle | P9-A Safety Rule |
|---|---|---|
| Source | proposed -> license_review -> approved/rejected/deprecated/quarantined | Unapproved or unclear-license sources cannot become release content |
| Source version | draft -> verified/approved/rejected/superseded/quarantined | Hash locked; version changes require a new row |
| Ingestion run | pending -> running -> succeeded/failed/rejected | Synthetic-only runtime metadata; no body dumps in reports |
| Staging document/chunk | staged -> quarantined/rejected/expired/promoted | Non-searchable, TTL-bound, cleanup-tracked, cannot enter release manifests |
| Document/chunk | quarantined -> approved/deprecated | Retrieval-eligible rows are separate from staging |
| Index release manifest | candidate -> validated/approved/active/superseded/deprecated/rolled_back | Schema only in P9-A; no activation service is implemented |
| Active index pointer | mutable pointer row | Table remains empty in P9-A |
| Retrieval event | metadata-only event | No raw query, prompt, PHI, path, URL, credential, exception, stack trace, or corpus body |

## Metadata Filtering Policy

Future retrieval must filter by active index release, approved source version, approved document and chunk lifecycle, license status, language, corpus type, and retrieval eligibility before ranking. P9-A creates schema support only; it does not expose product retrieval.

## Privacy Boundary

The RAG corpus is not patient memory and not a clinical registry activation mechanism. Patient cases, uploads, chats, feedback, and PHI must never enter corpus ingestion tables. P9-A tests use synthetic-only identifiers and cleanup prefixes.

## pgvector Boundary

The lexical schema succeeds without pgvector. Optional pgvector installation and `rag_chunk_embeddings` creation require explicit admin CLI invocation with `--enable-pgvector`; API startup never installs extensions or runs migrations. Vector retrieval remains disabled even if the extension exists.
