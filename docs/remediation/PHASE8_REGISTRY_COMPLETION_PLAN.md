# Phase 8 — Governed Registry Completion Plan

## Purpose

Phase 8 connects the governance infrastructure built in Phase 3 to durable storage,
formal review artifacts, governed import quality reporting, persistent release
activation, startup integration, CI enforcement, and operational controls.

Phase 8 does not approve clinical content, issue license verdicts, enable external
providers, activate real registry data, or satisfy any release gate by itself.

## Current State Summary

### Implemented Controls (Phase 3)

| Control | Status | File |
|---|---|---|
| Lifecycle states and provenance schema | Implemented | `backend/registry_governance.py` |
| Deterministic quarantine rules | Implemented | `backend/registry_governance.py` |
| Dry-run-only import with resource limits | Implemented | `backend/scripts/registry_import.py` |
| Canonical content hashing | Implemented | `backend/registry_governance.py` |
| Batch duplicate and conflict detection | Implemented | `backend/registry_governance.py` |
| Release manifest validation | Implemented | `backend/registry_release.py` |
| Complete framework family requirement | Implemented | `backend/registry_release.py` |
| Rollback abstraction | Implemented | `backend/registry_release.py` |

### In-Memory Limitations (Phase 3 → Phase 8 Progress)

| Limitation | Phase 3 State | Phase 8 State |
|---|---|---|
| Active release store | In-memory dict; resets on restart | P8-A: PostgreSQL `active_releases` (committed) |
| Active release pointer | In-memory; no persistence | P8-A: atomic pointer with SELECT FOR UPDATE (committed) |
| Approval records | Test fixtures only; no durable store | P8-BE: durable `approval_artifacts` + `release_approval_artifacts` tables |
| Reviewer identity | Test string only; no identity binding | P8-BE: approver_id in approval artifacts + verified_by in extraction verification |
| Startup registry loading | Not implemented; default unavailable | P8-BE: bounded startup probe with fail-closed loading |
| Extraction verification | Not implemented | P8-BE: `extraction_verifications` table; OCR/LLM entries require human verification |
| Release-level approval | Not separated from entry approval | P8-BE: separate `release_approval_artifacts` table |
| Authenticated status endpoint | Not implemented | P8-BE: `GET /registry/status` with bearer auth |

### Local Ignored Registry Data (Phase 0.5 Metadata Inspection)

| Dataset | File | Entries | Size | Key Issues |
|---|---|---|---|---|
| SDKI current | `SDKI.json` | 152 | 187 KiB | All entries use `kode`/`nama`; 0 framework fields; 0 provenance fields; 2 malformed codes (if matched as `D.xxxx`/`D.L` by prior analysis); 1 duplicate key |
| SDKI backups (×6) | `SDKI.json.bak-*` | 152 each | 67–163 KiB each | Historical extraction/population artifacts; same quarantine profile |
| Population report | `SDKI_population_report.json` | 1 metadata | 5.6 KiB | LLM-assisted population report; not an approval record |
| SLKI | not found | 0 | — | Feature unavailable |
| SIKI | not found | 0 | — | Feature unavailable |
| NANDA | not found | 0 | — | Feature unavailable |
| NOC | not found | 0 | — | Feature unavailable |
| NIC | not found | 0 | — | Feature unavailable |

All local SDKI data dry-runs as **152 quarantined, 0 release-eligible, 0 authoritative**.

### Phase 2 Fail-Closed Policy (Preserved)

| Scenario | Required Behavior |
|---|---|
| Missing diagnosis registry | `registry_unavailable` |
| Diagnosis available, outcome/intervention missing | `registry_incomplete`, `accepted_recommendations=false` |
| Quarantined, unapproved, extraction-unverified data | No authoritative grounding |
| Model memory for missing components | Forbidden |

## Phase 8 Slices Status

### P8-A — Durable Registry Store and Manifest Schema ✅ COMMITTED

**Scope**: PostgreSQL (Neon) durable registry store with migration CLI (V001–V004),
`PostgresRegistryStore`, connection pool/admin URL separation, retry bounds, and
`DisabledRegistryStore` fail-closed default.

**Committed**: `4050791ebae94739fbdefd25f75346c548020de6`

---

### P8-BE — Governed Registry Workflow, Import, Activation, Rollback, and Startup (COMBINED B+C+D+E)

**Scope**: Accelerated combined slice implementing review queue, human extraction
verification, entry/release approval separation, governed explicit-source import,
deterministic manifest hashing, atomic activation/rollback, bounded startup probe,
authenticated registry metadata endpoint, and complete-family policy.

**Status**: Implemented (synthetic-only). Closure-reviewed.

**Files** (new):
- `backend/registry_workflow.py` — review queue, approval artifacts, extraction verification
- `backend/registry_import_service.py` — governed explicit-source import
- `backend/registry_release_service.py` — release, activation, rollback, manifest hash
- `backend/registry_runtime.py` — startup loader, safe metadata, bounded probe (~51s worst case)

**Migrations** (new):
- V005: extraction verification table + performance indexes
- V006: release-level approval artifacts table
- V007: reconcile entry lifecycle and release status CHECK constraints with P8-BE states

**Tests** (new):
- `backend/tests/phase8_registry_workflow_test.py`
- `backend/tests/phase8_registry_import_test.py`
- `backend/tests/phase8_registry_release_runtime_test.py` (includes import-time safety tests)
- `backend/tests/phase8_registry_workflow_postgres_integration_test.py`

**Closure Review Findings** (resolved):
- Startup probe moved from module import to FastAPI lifespan (no DB connection at import)
- First-activation pointer serialization hardened in both activate and rollback paths
- Outbound allowlist updated (api.py line shift from lifespan insertion)
- Startup bound documentation corrected from ~45s/~75s to ~51s
- V007 migration added to reconcile CHECK constraints with P8-BE lifecycle states
- Integration test cleanup fixed (classmethod tearDown, prefixed release versions)
- No real registry body imported during P8-BE
- Synthetic fixture content only used for integration tests
- Registry bodies never enter logs, audit metadata, or safe status responses
- Local SDKI remains ignored, quarantined, and non-authoritative

**Non-Goals**:
- Real registry activation
- Real clinical approval
- Production deployment

---

## Historical Pre-Acceleration Plan — Superseded by P8-BE

**Historical Note**: The standalone P8-B, P8-C, P8-D, and P8-E sections below remain only as historical planning evidence and were consolidated into P8-BE.

### P8-B — Clinical Review Queue and Approval Artifacts

**Scope**: Add a local approval-record schema and review-queue model that captures
reviewer identity, review timestamp, review scope, review decision, and non-
repudiable approval artifact references.

**Files**:
- `backend/registry_review.py` (new) — approval record schema and queue model
- `backend/tests/phase8_registry_review_test.py` (new)

**Tests**:
- Approval record creation with required fields
- Rejection of unsigned or incomplete approval records
- Queue lifecycle: pending → reviewed → approved / rejected
- Approval records reference governed entries by content hash
- No real reviewer identity is fabricated

**Risks**:
- Approval records without identity binding are weaker than cryptographic signatures
- Informal approval records could be mistaken for formal clinical validation

**Rollback**: Remove `registry_review.py`.

**Exit Criteria**:
- Approval record schema captures reviewer identity, timestamp, scope, decision
- Queue model supports pending/reviewed/approved/rejected states
- Tests prove incomplete approval records are rejected

**Non-Goals**:
- Real identity provider binding
- Digital signatures
- Formal clinical validation

---

### P8-C — Governed Import and Extraction-Quality Reporting

**Scope**: Extend the dry-run importer to produce structured extraction-quality
reports including schema coverage, field-completeness metrics, duplicate analysis,
code-format validation, provenance-gap analysis, and license-status summaries. Add
a quality-threshold evaluator that gates import acceptance.

**Files**:
- `backend/registry_governance.py` — add quality report model
- `backend/scripts/registry_import.py` — structured quality output
- `backend/tests/phase8_import_quality_test.py` (new)

**Tests**:
- Quality report captures field coverage, malformed counts, missing provenance
- Import below quality threshold is rejected
- Quality report is metadata-only; no registry body text
- Network deny preserved during import

**Risks**:
- Quality thresholds that are too strict could block all imports
- Quality thresholds that are too lenient could pass bad data

**Rollback**: Revert quality-report additions; keep Phase 3 import behavior.

**Exit Criteria**:
- Structured quality report with field-level metrics
- Configurable quality threshold with fail-closed default
- Tests prove sub-threshold imports are rejected

**Non-Goals**:
- OCR debugging
- Extraction pipeline changes
- LLM-assisted quality improvement

---

### P8-D — Persistent Release Activation, Active Pointer, and Rollback

**Scope**: Connect the durable store (P8-A) to the release activation and rollback
workflow. Persist active release pointers and rollback history. Add release
version exposure through capabilities metadata.

**Files**:
- `backend/registry_release.py` — durable activation methods
- `backend/registry_store.py` — activation persistence
- `backend/config.py` — registry version metadata
- `backend/tests/phase8_release_activation_test.py` (new)

**Tests**:
- Activation persists to durable store
- Rollback persists to durable store and restores previous pointer
- Double-activation of the same release is idempotent or rejected
- Deprecation persists and prevents re-activation
- Release version appears in capabilities metadata

**Risks**:
- Stale pointer after filesystem failure → mitigate with startup verification
- Version metadata exposure could mislead about approval status

**Rollback**: Revert to in-memory activation; remove durable activation code.

**Exit Criteria**:
- Active release pointer survives process restart
- Rollback history survives process restart
- Capabilities metadata includes registry version safely

**Non-Goals**:
- Real registry activation
- Production deployment
- External registry distribution

---

### P8-E — Startup Integration and Server-Authoritative Registry Metadata

**Scope**: Add startup-time loading of the durable release store. If no approved
active release exists at startup, the registry remains unavailable. Add
server-authoritative registry version and approval status to the capabilities
endpoint. Verify fail-closed behavior when the store is absent, corrupt, or
contains an incomplete framework family.

**Files**:
- `backend/api.py` — startup registry loading
- `backend/config.py` — registry store path configuration
- `backend/tests/phase8_startup_test.py` (new)

**Tests**:
- Startup with no store → registry unavailable
- Startup with corrupt store → registry unavailable, error logged
- Startup with valid store but incomplete family → registry incomplete
- Startup with valid complete store → registry available
- Fail-closed on missing HMAC key for ledger at startup

**Risks**:
- Startup failure could block server boot → mitigate with graceful degradation
- Registry version at startup could become stale during runtime

**Rollback**: Remove startup loading; revert to default unavailable.

**Exit Criteria**:
- Server starts with valid durable store and exposes registry metadata
- Server starts safely without a store and remains unavailable
- Phase 2 abstention preserved in all failure cases

**Non-Goals**:
- Runtime registry hot-reload
- Multi-instance coordination
- External registry distribution

---

### P8-F — CI Enforcement, Migrations, Backup, Recovery, Concurrency, and Closure

**Status**: Closure-reviewed and staged, awaiting checkpoint commit.

**Scope**: Actual recovery handling, concurrency pointer locking, backup-restore rehearsals, artifact scanner integration, and CI enforcement files.

**Files**:
- `.github/workflows/security-scan.yml`
- `backend/scripts/ci_artifact_scan.py`
- `backend/scripts/registry_db_backup.py`
- `backend/scripts/registry_db_restore_verify.py`
- `backend/tests/phase8_registry_api_status_test.py`
- `backend/tests/phase8_registry_backup_restore_test.py`
- `backend/tests/phase8_registry_concurrency_postgres_integration_test.py`
- `backend/tests/phase8_registry_migration_safety_test.py`
- `backend/tests/phase8_registry_recovery_test.py`
- `docs/remediation/PHASE8_REGISTRY_COMPLETION_PLAN.md`
- `docs/remediation/VERIFICATION_LOG.md`

**Tests**:
- CI runs Phase 8 tests alongside Phase 1-7
- Concurrent read during write does not corrupt store
- Backup and restore round-trip for durable store

**Risks**:
- CI expansion could increase build times

**Rollback**: Revert CI changes; keep Phase 8 code as local-only.

**Exit Criteria**:
- CI enforces Phase 8 tests
- Operations documentation covers backup, recovery, migration
- Concurrency limitations are documented honestly
- Phase 8 closure evidence is recorded

**Non-Goals**:
- Multi-process distributed store
- Production deployment procedures

## Dependency Graph

```
P8-A → P8-D → P8-E
P8-B → P8-D (approval records referenced by releases)
P8-C → P8-B (quality threshold gates review queue)
P8-E → P8-F (startup must work before CI can enforce)
```

## Phase 8 Non-Goals

- No real registry activation
- No formal clinical approval
- No license approval
- No external provider enablement
- No patient data processing
- No production deployment
- No hospital readiness claim
- No compliance claim
- No Gate A, B, or C claim
- No synthetic lab merge
- No synthetic lab code copy
- No model memory completion of missing registries

## Release Gate Impact

Phase 8 completion would reduce but not eliminate Gate A blockers:

| Gate A Remaining After P8 | Status |
|---|---|
| Formal clinical review with real reviewer | Still required |
| License review for real registry content | Still required |
| Browser-rendered QA | Still required or explicitly deferred |
| Hard parser resource controls | Still required or explicitly accepted |
| Nonce/hash CSP | Still required |
| CI enforcement of all phases | Addressed in P8-F |
| Durable release store | Addressed in P8-A/D/E |

Gate B and Gate C remain fully unmet after Phase 8.
