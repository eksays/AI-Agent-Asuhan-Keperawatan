# Synthetic Showcase Feature Matrix

This matrix describes the offline synthetic showcase on
`review/synthetic-integration-lab`. It does not establish patient-care,
clinical-validation, hospital-readiness, compliance, or production-readiness
claims.

| Feature | Implementation Type | Demo Status | Limitations |
| --- | --- | --- | --- |
| Auth and API key transport | REAL LOCAL PATH | Available for lab routes with `Authorization: Bearer test-key` placeholder. | Shared API key is not user identity, RBAC, SSO, or OAuth/OIDC. |
| Lab session | REAL LOCAL PATH | `/lab/session` issues digest-stored lab session id/token. | In-memory only; restart clears state; not durable or distributed. |
| Rate limit | REAL LOCAL PATH | LAB route class rate limit applies. | In-memory only; no shared distributed limiter. |
| Audit ledger | REAL LOCAL PATH | Lab routes emit safe metadata event types and Sprint C rehearses verifier pass/fail. | Local HMAC ledger is not WORM, not immutable storage, not a digital signature, not non-repudiation, and not compliance evidence. |
| Upload parser | REAL LOCAL PATH | `/lab/upload` runs manifest-approved synthetic TXT/PDF/DOCX fixtures through existing parser boundary. | Parser process has timeout cleanup but no portable hard CPU/RAM quota. |
| Typed abstention | REAL LOCAL PATH | Lab responses keep `accepted_recommendations=false`, `clinical_use_allowed=false`, and `nurse_review_required=true`. | No validated clinical recommendation is produced. |
| Multi-stage orchestration | SYNTHETIC PROTOTYPE | `/lab/run` invokes deterministic stages and trace metadata. | Prototype only; no swarm coordination, task delegation, autonomous workers, or real provider orchestration. |
| RAG | SYNTHETIC PROTOTYPE | `/lab/rag` uses generated offline corpus, token overlap scoring, stable ids/scores, and weak-context abstention. | Lexical prototype only; no embeddings, vector database, hybrid retrieval, or reranking. |
| Registry | SYNTHETIC PROTOTYPE | `/lab/registry` loads fake codes such as `SYN-D-001` from manifest fixtures. | Synthetic registry is non-authoritative and not an official clinical registry. |
| EBP | SYNTHETIC PROTOTYPE | `/lab/ebp` returns generated offline fixture references. | Not current medical evidence and not external evidence retrieval. |
| Mermaid | SYNTHETIC PROTOTYPE | `/lab/pathway` returns safe fixture content, rejects malicious fixture content, and is visible through a synthetic-lab-only UI runner using the existing Mermaid sanitizer boundary. | Fixture IDs are manifest-backed only; normal Mermaid feature flag stays disabled. |
| OCR | DETERMINISTIC MOCK | `/lab/ocr` returns `DETERMINISTIC OCR MOCK - EXTRACTION UNVERIFIED`. | No OCR SDK, no text extraction validation, and no clinical OCR. |
| Photo | DETERMINISTIC MOCK | `/lab/photo` returns `DETERMINISTIC PHOTO MOCK - NOT CLINICAL IMAGE ANALYSIS`. | No image model, no clinical-photo inference, no diagnostic analysis. |
| Feedback memory | SYNTHETIC PROTOTYPE | `/lab/feedback` stores bounded synthetic feedback by lab session only. | In-memory only; no authoritative learning, registry update, or durable feedback governance. |
| External LLM | FORBIDDEN IN LAB | Disabled during Sprint A-C. | Optional external-provider work belongs on a separate later branch only. |
| Real registry grounding | FORBIDDEN IN LAB | Disabled and unavailable on normal routes. | `backend/data_terstruktur/*` remains ignored/local-only and forbidden for lab fixtures. |
| Real patient data | FORBIDDEN IN LAB | Not accepted by policy; warning banner is persistent. | Synthetic-only showcase must never process patient or hospital documents. |
| WORM audit storage | DISABLED | Not implemented. | Requires external immutable or WORM-capable storage before any stronger audit claim. |
| Production identity/RBAC/SSO | DISABLED | Not implemented. | Required before controlled pilot or hospital deployment discussion. |
| Clinical validation | DISABLED | Not established. | Requires formal clinical review, approved registry releases, and governance outside this lab. |

## Truthful Labels

- `REAL LOCAL PATH` means the local sandbox implementation path exists and is
  exercised with synthetic inputs.
- `SYNTHETIC PROTOTYPE` means the feature is a deterministic or fixture-backed
  demonstration path only.
- `DETERMINISTIC MOCK` means no clinical engine or provider is invoked.
- `DISABLED` means no demo activation exists.
- `FORBIDDEN IN LAB` means the feature must not be activated in the offline
  synthetic showcase.
