# Synthetic Showcase Limitations

The Synthetic Integration Lab is an offline synthetic showcase for contributor
review and technical pitching. It is not patient-care software, not production
ready, not hospital ready, not clinically validated, and not compliance evidence.

## Scope Limits

| Limitation | Status |
| --- | --- |
| Synthetic-only inputs | Required. Do not enter real patient data, hospital documents, uploads, identifiers, or operational records. |
| Patient-care use | Not allowed. Outputs may be mocked or prototype-only. |
| Clinical validation | Not established. No formal clinical reviewer approval workflow is completed. |
| Compliance | Not established. The lab is not HIPAA, local health-regulation, or hospital compliance evidence. |
| Hospital readiness | Not established. No deployment identity, RBAC, SSO, durable state, or operational governance exists. |
| Production readiness | Not established. Normal release gates remain unmet. |

## Capability Limits

| Capability | Limitation |
| --- | --- |
| Multi-stage orchestration | Prototype only. Swarm coordination is not supported; there are no autonomous role-specific workers, delegation loop, independent worker outputs, or validated aggregation workflow. |
| RAG | Synthetic lexical prototype only. No embedding retrieval, vector database, hybrid retrieval, reranking, or evidence-quality claim is implemented. |
| Registry | Synthetic fake-code registry only. It is non-authoritative, `clinical_use_allowed=false`, and not an official clinical registry. |
| EBP | Offline synthetic fixture only. It is not current medical evidence and does not call evidence-search endpoints. |
| OCR | Deterministic mock only. It is not clinical OCR and does not invoke an OCR SDK. |
| Photo workflow | Deterministic mock only. It is not clinical image analysis and does not invoke an image model. |
| External provider | Disabled during Sprint A-C. No external LLM, DeepSeek, or provider adapter is enabled in this branch. |
| Real registry grounding | Disabled. `backend/data_terstruktur/*` remains ignored/local-only and forbidden for lab activation. |
| Mermaid | Lab route and synthetic-lab-only UI runner use generated fixtures and the existing sanitizer boundary. Normal Mermaid capability remains disabled. |
| Feedback memory | In-memory synthetic namespace only; no authoritative learning, durable memory, or registry update. |

## Security and Privacy Limits

| Area | Residual |
| --- | --- |
| Browser-carried API key | Local sandbox header-only transport avoids body/query/storage transport, but the shared key is still visible to client code and is not user identity. |
| Lab state | Sessions, traces, feedback, MFA/rate-limit state, and similar controls are in-memory and not durable or distributed. |
| Audit ledger | Local HMAC chain is not WORM storage, not immutable storage, not a digital signature, not non-repudiation, and not compliance evidence. |
| Audit truncation | A locally valid-prefix tail truncation can verify without external checkpointing or immutable archive. |
| Symlink verification | Windows symlink tests may skip where privileges are unavailable. Do not claim cross-platform symlink verification unless rerun on Linux CI or a symlink-capable Windows host. |
| Parser isolation | Upload parser uses a child process, timeout, and cleanup, but portable OS-level CPU/RAM quotas and full process-tree containment remain residuals. |
| Browser QA | Preferred in-app Browser runtime may be unavailable due a tooling asset-path error. Reproducible localhost headless-Chrome QA is local showcase evidence only, not cross-browser certification or hospital UI readiness. |

## Forbidden Shortcuts

- Do not enable `backend/data_terstruktur/*`.
- Do not copy licensed SDKI, SLKI, SIKI, NANDA, NOC, NIC, hospital, or patient content.
- Do not call external providers by default.
- Do not call EBP internet endpoints by default.
- Do not silently simulate unsupported features on normal routes.
- Do not mark mock output as validated.
- Do not bypass the typed abstention boundary.
- Do not expose chain-of-thought, raw prompts, raw outputs, uploaded text, PHI,
  tokens, OTPs, filesystem paths, stack traces, or provider keys.
- Do not merge lab code into `dev` automatically.

## Required Wording

Use these labels when presenting the lab:

- Offline synthetic showcase.
- Multi-stage agent orchestration prototype.
- Synthetic lexical RAG prototype.
- Offline synthetic EBP fixture.
- Deterministic OCR mock.
- Deterministic photo mock.
- Local HMAC audit ledger only.

Avoid these claims:

- Clinical swarm intelligence.
- Hybrid clinical RAG.
- Current medical evidence retrieval.
- Clinical OCR.
- Clinical image analysis.
- Official clinical registry grounding.
- Controlled-pilot readiness.
- Hospital readiness.
- Production readiness.
