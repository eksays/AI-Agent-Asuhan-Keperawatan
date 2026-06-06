# Remediation Plan

Phase 0A preflight was performed on 2026-06-06 local time. No production logic was changed.

## Current Verdict

The repository is a clinical sandbox candidate only. Phase 0B fail-closed containment has been applied, but the system is not production-ready, not compliance-proven, and not safe for autonomous clinical decision-making.

## Proposed Phase Sequence

1. **Phase 0B - Truthful Sandbox Mode and Immediate Risk Reduction**
   - Status: applied on 2026-06-06 for default sandbox mode and capability containment.
   - Add explicit `APP_MODE=clinical_sandbox` default.
   - Add server-authoritative capability metadata and disable unsupported features.
   - Remove overstated README/compliance/WORM/photo-analysis claims.
   - Add persistent UI sandbox notice.

2. **Phase 1 - Outbound PHI Firewall and Safe Streaming**
   - Centralize outbound data policy.
   - Route all model and EBP calls through one wrapper.
   - Sanitize before every external call, including review passes.
   - Precompute, sanitize, validate, then stream.

3. **Phase 2 - Typed Clinical Schema, Registry Validation, and Abstention**
   - Add typed clinical response schemas.
   - Validate generated codes against approved registries.
   - Reject unsupported or malformed recommendations.
   - Implement abstention for insufficient evidence.

4. **Phase 3 - Dataset Quarantine and Clinical Governance**
   - Add registry lifecycle states and provenance metadata.
   - Quarantine invalid, LLM-assisted, OCR-derived, or unapproved entries.
   - Disable missing datasets instead of simulating them.

5. **Phase 4 - Mermaid, Markdown, and Browser Rendering Hardening**
   - Switch Mermaid to strict mode.
   - Sanitize generated SVG before DOM insertion.
   - Tighten markdown link protocols and CSP.

6. **Phase 5 - Isolated Document Upload Parsing**
   - Use content sniffing and magic bytes.
   - Parse in a killable process with hard resource limits.
   - Disable unsupported clinical photo analysis.

7. **Phase 6 - Authentication, Session Security, Secrets, MFA, and Rate Limits**
   - Remove API keys from request bodies.
   - Authenticate and authorize session mutation endpoints.
   - Add TOTP replay prevention, lockout, and rate limits.

8. **Phase 7 - Audit Ledger Redesign**
   - Rename local ledger honestly as tamper-evident only.
   - Add HMAC/signature and verifier tooling.
   - Separate local and production storage adapters.

9. **Phase 8 - Complete and Govern Clinical Registries**
   - Import only approved reference data with provenance and clinical review.

10. **Phase 9 - Hybrid Retrieval and Explainability**
    - Add hybrid retrieval and objective evaluation without replacing deterministic validation.

11. **Phase 10 - EBP Retrieval, OCR, Feedback Governance, and Reliability**
    - Govern EBP/OCR/feedback and complete release reliability gates.

## Phase Boundaries

Changes made in Phase 0A are limited to `docs/remediation/*` evidence files. Production backend/frontend logic remains unchanged.

Phase 0B changes are intentionally limited to truthful sandbox configuration, server-authoritative capability metadata, frontend fail-closed rendering, background harvester default-off configuration, and documentation corrections. Phase 0B does not implement the PHI firewall, typed clinical validation, registry quarantine, Mermaid hardening, isolated upload parsing, session hardening, MFA hardening, or production audit storage.

## Phase 0B Closure Notes

Phase 0B closure verification confirmed fail-closed containment with default-disabled unsafe capabilities and network-deny tests for the relevant default route paths. This checkpoint remains rollback-friendly and does not stage ignored local registry data, runtime logs, generated caches, or local secrets.

Operational follow-ups:

- Browser-rendered QA is deferred because the Browser runtime exposed no available browser client; HTTP-level validation is not a substitute for rendered interaction testing.
- Frontend lint remains at the Phase 0A baseline of 7 errors and 6 warnings; no unrelated lint cleanup is included in Phase 0B closure.
- Node v24.0.2 is the current local runtime. Production/pilot runtime standardization should choose and document an approved Node LTS version.
- Future `compileall` baseline commands should reliably exclude `backend/venv`, `__pycache__`, and generated artifacts. The requested closure command still traversed `backend/venv` despite the exclusion expression.
