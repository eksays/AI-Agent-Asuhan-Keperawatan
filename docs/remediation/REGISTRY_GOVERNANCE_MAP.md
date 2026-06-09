# Registry Governance Map - Phase 3

Phase 3 implements governance infrastructure only. It does not activate real registry data, approve local datasets, certify clinical content, or make any production-readiness claim.

Guidance inspected read-only and adopted:

| Source | Relevant Practice Adopted |
|---|---|
| https://github.com/openai/skills | Secure-by-default boundary review and minimal adoption of guidance only; no third-party scripts executed. |
| https://github.com/trailofbits/skills | Bottom-up context mapping, fail-open/default-state review, and explicit audit evidence before remediation. |
| https://github.com/GSTT-CSC/QMS-Template | Hazard-log style residual-risk records, change traceability, release evidence, and rollback-oriented documentation. |
| https://github.com/johner-institut/ai-guideline | Data-management, dataset exclusion, provenance, and verification controls treated as non-authoritative reference guidance. |

## Trusted Authority Boundary

Only explicitly released, approved registry artifacts may become authoritative. The following are not authoritative by themselves:

- JSON file presence.
- Schema-valid content.
- Correct-looking code format.
- OCR completion.
- LLM-assisted field population.
- Informal nursing perspective feedback.
- Local reviewer comments without a governed approval record.

## Data-Flow Map

| Source Type | Source Path | Framework | Extraction Method | Current Lifecycle State | Schema Validation Result | Provenance Status | Licensing-Review Status | Clinical-Review Status | Release Eligibility | Quarantine Reason | Authoritative Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Runtime registry boundary | `backend/api.py` `CLINICAL_REGISTRY` | 3S/3N families | N/A | unavailable | N/A | N/A | N/A | N/A | not eligible | no active approved registry release configured | non-authoritative |
| Phase 2 synthetic registry fixture loader | `backend/clinical_registry.py` | SDKI/SLKI/SIKI/NANDA/NOC/NIC | synthetic fixture only | approved fixture in tests only | validates code/name/provenance minimums | synthetic only | synthetic only | synthetic only | test-only | not a real release artifact | non-authoritative outside tests |
| Phase 2 validator | `backend/clinical_validator.py` | 3S/3N | N/A | requires approved registries | deterministic schema/registry/evidence gate | uses registry object metadata | not a license validator | not clinical approval | N/A | abstains on missing/incomplete registries | non-authoritative without approved registry object |
| Current ignored SDKI data | `backend/data_terstruktur/SDKI.json` | SDKI by source filename only; entries lack framework field | OCR-derived and LLM-assisted local population indicated by local report | extraction_unverified / llm_assisted | dry-run parse: 152 entries | missing mandatory provenance for all entries | unknown | informal disclaimer says extraction remains insufficient | 0 release-eligible | missing framework, missing provenance, unknown license, wrong component type, not approved lifecycle, 2 malformed codes | non-authoritative |
| Ignored SDKI backups | `backend/data_terstruktur/SDKI.json.bak-*` | SDKI by filename only; entries lack framework field | historical local extraction/population artifacts | extraction_unverified | dry-run parse: 152 entries each | missing mandatory provenance for all entries | unknown | not reviewed | 0 release-eligible | same dry-run quarantine profile as current SDKI | non-authoritative |
| Population report | `backend/data_terstruktur/SDKI_population_report.json` | SDKI | LLM-assisted population report | llm_assisted | metadata object only, not registry release | not an approval manifest | unknown | not reviewed | not eligible | LLM-assisted output cannot be approval record | non-authoritative |
| OCR/LLM extraction utility | `backend/ekstraksi.py` | SDKI default; other books commented | OCR plus LLM cleanup | ocr_extracted / llm_assisted / extraction_unverified until reviewed | not a governed import | no release provenance | unknown | not reviewed | not eligible | OCR and LLM review required | non-authoritative |
| LLM-assisted population utility | `backend/scripts/populate_sdki.py` | SDKI | external Anthropic-assisted population utility | llm_assisted | not a governed import | output report is not approval | unknown | not reviewed | not eligible | LLM-assisted review required | non-authoritative |
| Informal nursing feedback | `docs/remediation/NURSING_REVIEW_PHASE2.md` | 3S/3N | human feedback note | design feedback only | N/A | no approval record | no license approval | informal feedback with disclaimer | not eligible | cannot be converted into approval record | non-authoritative |

## Phase 3 Required Validator

| Boundary ID | Source File | Function / Boundary | Input Type | Current Output Type | Registry Dependency | Validation Gap Addressed | Required Validator | Test Case | Status |
|---|---|---|---|---|---|---|---|---|---|
| REG-GOV-001 | `backend/registry_governance.py` | `validate_registry_entries` | synthetic or local JSON mappings | governed entries with quarantine reasons | source framework metadata only, no activation | file presence could be mistaken for approval | lifecycle/provenance/quarantine validator | OCR/LLM/extraction-unverified entries are non-authoritative | implemented |
| REG-GOV-002 | `backend/scripts/registry_import.py` | dry-run CLI | registry JSON source path | safe metadata report | none | import could mutate or activate data | dry-run-only import service | dry run does not mutate source or activate registry | implemented |
| REG-GOV-003 | `backend/registry_release.py` | `validate_release_candidate` | release manifest and governed entries | release validation result | governed entries | release could include quarantined or unapproved data | release manifest validator | candidate rejects quarantined/missing approval/unknown license | implemented |
| REG-GOV-004 | `backend/registry_release.py` | `RegistryReleaseStore.activate_release` | approved-for-activation manifest | active release pointer | release manifest | active pointer could move implicitly | explicit activation only | candidate release cannot activate | implemented |
| REG-GOV-005 | `backend/registry_release.py` | `RegistryReleaseStore.rollback` | framework/component key | restored active release pointer | release history | rollback traceability missing | previous-release pointer | rollback restores previous release | implemented |
| REG-GOV-006 | `backend/api.py` | clinical-analysis routes | patient request | clinical status envelope | `CLINICAL_REGISTRY` | local ignored data could activate grounding | default unavailable registry plus Phase 2 abstention | local ignored registry presence does not activate grounding | preserved |
| REG-GOV-007 | `backend/registry_governance.py` | `resolve_import_source` | source file or approved directory | resolved JSON source file | approved import root | import path could traverse, escape, or pull backups implicitly | root-bound explicit path resolver | traversal, outside absolute path, unsupported extension, missing file, backup exclusion, and symlink-resolved escape tests | implemented |
| REG-GOV-008 | `backend/registry_governance.py` | `_load_json` and entry validation | registry JSON | bounded safe parse or quarantine | none | hostile registry JSON could be oversized/deeply nested/noisy | file-size, entry-count, depth, string-length, and report-size limits | oversized file, deep JSON, excessive entries, oversized field tests | implemented |
| REG-GOV-009 | `backend/registry_release.py` | `validate_framework_release_set` | component release manifests | framework release validation | SDKI/SLKI/SIKI or NANDA/NOC/NIC component sets | diagnosis-only release could appear complete | complete-family validator | SDKI-only, SDKI+SLKI, SDKI+SIKI, NANDA-only, NANDA+NOC, NANDA+NIC tests | implemented |

## Lifecycle Rules

| Lifecycle State | Authoritative | Handling |
|---|---|---|
| `draft` | No | Exclude from release and authoritative lookup. |
| `ocr_extracted` | No | Quarantine or hold for OCR review and provenance verification. |
| `llm_assisted` | No | Quarantine or hold for human review; never use model-filled content as approval. |
| `extraction_unverified` | No | Quarantine until extraction quality is debugged and verified. |
| `under_clinical_review` | No | Exclude until formal approval record exists. |
| `approved` | Eligible only | May enter release validation only if provenance, license, approval records, and hashes pass. |
| `deprecated` | No | Exclude from new requests. |
| `quarantined` | No | Exclude until a governed remediation and new approval release occurs. |

## Phase 3 Non-Activation Statement

No active release pointer is created for real local registry data in Phase 3. `backend/data_terstruktur/*` remains ignored/local-only and must not be staged.

## Import Source Safety

`registry_import.py` and `registry_governance.py` accept explicit JSON files or an approved directory plus explicit framework. Directory import resolves only the primary `<FRAMEWORK>.json` file and excludes backups such as `SDKI.json.bak-*` by default. The importer rejects path traversal, absolute paths outside the approved import root, symlink-resolved escapes, unsupported extensions, and missing files with metadata-only errors.

Resource limits for Phase 3 registry import parsing:

| Limit | Value | Handling |
|---|---:|---|
| Maximum file size | 512 KiB | Reject safely before parsing. |
| Maximum entry count | 500 | Reject safely before validation. |
| Maximum JSON nesting depth | 16 | Reject safely before validation. |
| Maximum string length | 4096 characters | Quarantine entry with `FIELD_TOO_LONG`. |
| Maximum quarantine reason-code count | 64 | Reject report generation if exceeded. |

These limits apply only to registry governance import. They are not Phase 5 upload-parser isolation controls.

## Canonical Hash Strategy

Entry content hashes are computed from canonical JSON with sorted keys and compact separators. The hash includes stable clinical/source identity fields: framework, component type, code, name, source title, source version, source page, source section, and source identifier. It intentionally excludes volatile workflow fields such as reviewer identifier, review date, release id, approval status, and lifecycle state. Tests verify that harmless key ordering/whitespace changes keep the same hash, clinical name changes alter the hash, and content-hash mismatch is quarantined.

## Framework Release Completeness

Normal hospital-facing care-plan activation must use complete registry families:

| Framework | Required Components | Incomplete Handling |
|---|---|---|
| 3S | SDKI diagnosis, SLKI outcome, SIKI intervention | Activation rejected; Phase 2 `registry_incomplete` abstention remains active. |
| 3N | NANDA diagnosis, NOC outcome, NIC intervention | Activation rejected; Phase 2 `registry_incomplete` abstention remains active. |

No diagnosis-only active release is allowed for the normal care-plan workflow.

## Release Store Limitation

The active release store added in Phase 3 is an in-memory test abstraction. It proves explicit activation and rollback behavior but is not durable, pilot-ready, or production-ready storage. A durable governed release store remains required before controlled pilot evaluation.

## Phase 8 Planning Status

Phase 8 inventory and planning has begun on `audit/phase8-registry-completion` from `origin/dev` at `adc712f`. No implementation, registry activation, or code changes are included in the planning checkpoint.

The detailed Phase 8 plan is documented in `docs/remediation/PHASE8_REGISTRY_COMPLETION_PLAN.md`.

Phase 8 slices:

| Slice | Scope | Status |
|---|---|---|
| P8-A | Durable PostgreSQL registry store (Neon) and migration CLI | ✅ Committed |
| P8-BE | Review queue, human extraction verification, entry/release approval, governed import, deterministic manifest hash, atomic activation/rollback, bounded startup probe, authenticated `/registry/status`, complete-family policy | Implemented (synthetic-only) |
| P8-F | CI enforcement, migrations, backup, recovery, concurrency, and closure | Planned |

All local registry data remains ignored, untracked, non-authoritative, and fully quarantined. No registry activation, formal clinical review, or license approval has occurred.

### P8-BE Extraction Verification (New)

OCR-derived or LLM-assisted entries are never permanently blocked. Instead, human extraction verification is required before approval:
- Extraction review statuses: `unverified`, `verified_by_human`, `rejected`
- OCR or LLM-assisted entry with `unverified` status → approval rejected
- OCR or LLM-assisted entry with `verified_by_human` → approval may proceed if all other governance checks pass
- Auto-approval of OCR-derived or LLM-assisted entries is never allowed
