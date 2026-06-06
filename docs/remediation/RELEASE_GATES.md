# Release Gates

## Gate A - Clinical Sandbox

Status: **Not met**

Completed Phase 0B controls:

- Truthful sandbox documentation and persistent sandbox labeling.
- Server-authoritative `APP_MODE` and feature availability metadata.
- Unsupported clinical photo, EBP external search, Mermaid pathway rendering, and unapproved registry grounding are disabled by default.
- Background harvester is default-off.
- Local audit wording is corrected to tamper-evident local ledger, not WORM.

Completed Phase 1 controls:

- Deterministic outbound PHI policy for tested canary identifiers.
- Safe LLM wrapper for active API model calls.
- De-identified concept-query path for EBP retrieval.
- `/chat_stream` precomputes, sanitizes, then chunks output instead of streaming raw tokens.
- Console/audit free-text fields are sanitized before logging.
- Session memory, feedback memory, correction recall, non-stream JSON routes, and reviewed utility-script payload/error paths are covered by synthetic canary tests.
- Owned backend source has a Phase 1 outbound bypass scanner with a narrow allowlist.

Remaining missing or failing controls:

- PHI firewall completeness beyond tested canary classes and future integrations.
- Safe streaming with typed clinical validation.
- Basic typed clinical schema validation.
- Registry quarantine.
- Mermaid/SVG hardening.
- Upload isolation with killable parser process.

Gate A is still not passed until Phase 2, Phase 4, and Phase 5 controls are implemented and verified, and Phase 1 controls are kept enforced in CI.

Phase 1 closure verification improves outbound PHI containment and streaming behavior for tested paths. It does not satisfy Gate A requirements for deterministic clinical validation, registry quarantine, Mermaid/SVG hardening, or isolated upload parsing. Browser-rendered QA remains deferred, and frontend lint remains failing at the Phase 0A baseline.

## Gate B - Controlled Pilot Candidate

Status: **Not met**

Missing or failing controls:

- All Gate A controls.
- Clinical reviewer approval workflow.
- Approved registry releases.
- Session hardening and persistent sessions where required.
- MFA replay protection and throttling.
- Rate limiting.
- Tamper-evident audit verifier with HMAC/signature.
- Clinical regression suite.
- CI enforcement of build, lint, test, and safety gates.
- Human confirmation workflow.

## Gate C - Production Evaluation Candidate

Status: **Not met**

Missing or failing controls:

- All Gate B controls.
- External append-only audit storage.
- Formal privacy review.
- Formal security review.
- Clinical validation study.
- Incident response process.
- Model rollback process.
- Registry rollback process.
- Operational monitoring.
- Documented responsibility model.
- Legal and regulatory review.

No phase, command, or local build should be interpreted as Gate C approval.
