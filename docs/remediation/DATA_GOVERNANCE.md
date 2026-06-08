# Data Governance

## Current Registry Inventory

| Dataset | Location | Git State | Count | Observations |
|---|---|---|---:|---|
| SDKI | `backend/data_terstruktur/SDKI.json` | Ignored / untracked | 152 | Contains invalid codes `D.xxxx` and `D.L`; lacks framework/provenance markers. |
| SDKI population report | `backend/data_terstruktur/SDKI_population_report.json` | Ignored / untracked | 1 | Documents LLM-assisted population (`deepseek-v4-flash`). |
| SLKI | Not found | N/A | 0 | Feature should be unavailable. |
| SIKI | Not found | N/A | 0 | Feature should be unavailable. |
| NANDA | Not found | N/A | 0 | Feature should be unavailable. |
| NOC | Not found | N/A | 0 | Feature should be unavailable. |
| NIC | Not found | N/A | 0 | Feature should be unavailable. |

## Validation Observations

Local analysis of `SDKI.json` found:

- `entries`: 152
- `invalid_codes`: 2 (`D.xxxx`, `D.L`)
- `duplicates`: 0
- `missing_name`: 0
- `missing_framework_field`: 152
- `missing_any_provenance_marker`: 152
- `missing_objective_major`: 35
- `no_gejala_major_or_minor`: 34

## Governance Position

The current registry must not be treated as an approved clinical reference dataset. It can be used only as sandbox data until a governed import/review/release process exists.

## Phase 0B Position

Phase 0B does not make any registry clinically approved or reproducible. `backend/data_terstruktur/` remains ignored and untracked, so the local SDKI files are not reproducible from git. The observed SDKI content requires licensing, provenance, and clinical review before any authoritative use.

Server capability metadata now marks SDKI authoritative grounding, SLKI, SIKI, NANDA, NOC, and NIC unavailable by default. This is a containment measure only; it is not registry validation, quarantine, or approval.

Raw clinical datasets, licensed reference extracts, OCR outputs, or LLM-populated registry files must not be committed casually. Future registry work must use the governed import, quarantine, clinical review, versioned release, and rollback process planned for Phase 3 and Phase 8.

## Phase 1 Position

Phase 1 adds outbound sanitization to the LLM-assisted registry extraction/population utilities, but this does not approve or validate any generated registry content. LLM-assisted reference data remains non-authoritative until schema validation, provenance, quarantine, clinical review, versioned release, and rollback controls exist.

Required controls for future phases:

- Data lifecycle states: `draft`, `ocr_extracted`, `llm_assisted`, `under_clinical_review`, `approved`, `deprecated`, `quarantined`.
- Approved-only grounding.
- Provenance fields for source title, source version, page/section, extraction method, reviewer, review date, approval status, content hash, and registry version.
- Quarantine invalid/malformed/duplicate/unapproved entries at load time.
- Disable missing frameworks instead of generating content from model memory.

## Phase 2 Position

Phase 2 introduces a registry-validation abstraction but does not approve, enrich, import, or commit local registry data.

Implemented controls:

- `backend/clinical_registry.py` can load controlled synthetic entries and separate approved entries from quarantined or unavailable entries.
- Approved synthetic entries require framework, valid code format, name, approval status, source title, source version, reviewer, review date, and content hash.
- Duplicate codes, malformed codes, missing names, missing frameworks, missing provenance, unapproved states, and quarantined states are excluded from authoritative lookup.
- `backend/clinical_validator.py` refuses clinical output when the approved registry for the requested framework is unavailable.
- API clinical-analysis routes fail fast before provider construction when the approved registry set is unavailable or incomplete, even if ignored local files are present. Missing diagnosis registry returns `registry_unavailable`; missing outcome/intervention registries return `registry_incomplete`.
- Provider-authored registry version/source/provenance claims are not trusted. Accepted diagnosis metadata is overwritten from the approved registry object; provider-authored confidence is not treated as clinical truth.
- Provider-authored evidence is bound deterministically to trusted patient input or extracted document text using allowed evidence sources, clinical measurement matching, negation preservation, and conservative token containment.

Current governance stance:

- `backend/data_terstruktur/*` is still ignored or local-only and must not be treated as an approved registry release.
- The default application registry object is unavailable; tests patch synthetic approved fixtures explicitly.
- Missing SLKI, SIKI, NANDA, NOC, and NIC registries block fabricated outcomes/interventions rather than allowing model-memory completion.
- Partial registry availability safe default: complete care-plan abstention. For 3S, approved SDKI without approved SLKI and SIKI returns `registry_incomplete`; for 3N, approved NANDA without approved NOC and NIC returns `registry_incomplete`. Diagnosis-only output is not accepted for the normal hospital-facing care-plan workflow while outcome/intervention registries are missing.
- Phase 2 schema/registry validation is a safety gate, not formal clinical validation, not licensing approval, and not production registry governance.

Informal nursing-perspective feedback received on 2026-06-06 adds a specific disclaimer: supporting 3S and 3N documents are not yet concrete enough because writing extraction issues remain, so extraction quality and completeness are not maximal. This feedback is non-authoritative design input only, but it reinforces the current fail-closed position: extracted registries must not be activated for hospital care-plan generation until extraction debugging, content review, provenance verification, and further validation are complete.

Extraction-quality states that remain non-authoritative until Phase 3 governance exists:

| State | Authoritative | Required Handling |
|---|---|---|
| `extraction_unverified` | No | Quarantine or disable for grounding; require extraction debugging, provenance checks, and review before approval. |
| `ocr_extracted` | No | Treat as raw extraction output; require schema validation, deduplication, provenance, clinical review, and release approval. |
| `llm_assisted` | No | Treat as generated assistance only; do not use as authoritative content without human review, provenance verification, and approved release. |

Conservative registry rules:

- File presence is not approved registry availability.
- OCR output is not approved registry content.
- LLM-assisted population is not approved registry content.
- Only explicitly reviewed and approved release artifacts may become authoritative.
- Missing, unapproved, quarantined, or extraction-unverified SDKI/SLKI/SIKI/NANDA/NOC/NIC registries must preserve complete care-plan abstention.

Still required in Phase 3/8:

- Governed import workflow.
- Clinical review queue and approval records.
- Versioned registry release artifacts.
- Rollback and release traceability.
- Reviewer identity, source licensing checks, and content-hash verification for real datasets.

## Phase 3 Position

Phase 3 adds governance infrastructure, dry-run import, deterministic quarantine rules, release manifest validation, and rollback abstractions. It does not activate real registry data and does not approve local SDKI content.

Implemented controls:

- `backend/registry_governance.py` defines lifecycle states: `draft`, `ocr_extracted`, `llm_assisted`, `extraction_unverified`, `under_clinical_review`, `approved`, `deprecated`, and `quarantined`.
- All lifecycle states except `approved` are non-authoritative. `approved` means release-eligible only after provenance, license, clinical-review, content-hash, approval-record, and release-manifest checks pass.
- `backend/scripts/registry_import.py` performs dry-run-only imports by default and emits safe metadata without activating registries or mutating source files.
- Import source resolution is constrained to an approved import root. Explicit files are imported directly; directory imports require an explicit framework and load only `<FRAMEWORK>.json`, excluding backups by default.
- Registry import parsing is bounded by maximum file size, entry count, JSON depth, string length, and quarantine-report size. These are Phase 3 registry-import limits only, not upload-parser sandboxing.
- Quarantine reason codes include malformed code, duplicate code, missing name/framework/provenance, wrong component type, unknown license status, OCR review required, LLM-assisted review required, extraction unverified, code-name conflict, content-hash mismatch, deprecated entry, and manual quarantine.
- Canonical content hashes are stable across JSON whitespace/key-order changes, change when stable clinical/source identity fields change, and exclude documented volatile workflow fields such as reviewer identity, review date, release id, approval status, and lifecycle state.
- `backend/registry_release.py` models candidate, approved-for-activation, active, deprecated, and rolled-back release states. Activation requires an explicit approved-for-activation release artifact and rejects quarantined entries, missing approval records, and unknown license status.
- Framework release validation requires complete component families: SDKI+SLKI+SIKI for 3S and NANDA+NOC+NIC for 3N. Diagnosis-only active releases are rejected for the normal hospital-facing care-plan workflow.
- Rollback restores the previous active release pointer in synthetic tests.

Local dry-run result for ignored SDKI data:

- Current `SDKI.json`: 152 entries, 152 quarantined, 2 malformed-code records, 0 release-eligible, 0 authoritative.
- Ignored SDKI backups: 152 entries each, 152 quarantined each, 2 malformed-code records each, 0 release-eligible, 0 authoritative.
- `SDKI_population_report.json` remains local LLM-assisted metadata only and is not an approval record.

Phase 3 preserves the strict Phase 2 abstention contract. Missing, unapproved, quarantined, extraction-unverified, or not-active SDKI/SLKI/SIKI/NANDA/NOC/NIC registry families keep the complete care-plan workflow in abstention.

Still required after Phase 3:

- Formal clinical review queue with reviewer identities and non-repudiable approval records.
- License review and source-access documentation for real reference datasets.
- Approved release artifacts for each registry family before authoritative grounding.
- Operational storage for active release pointers; Phase 3 uses testable in-memory abstractions only.
- Durable governed release storage remains required before controlled pilot evaluation; the Phase 3 active-release store is an in-memory test abstraction only.

## Phase 7 Audit Metadata Governance

Phase 7 audit records are governed as security metadata, not clinical narrative storage and not application logs. The ledger schema stores event category, actor fingerprint, route class, outcome, status code, security tags, and bounded allowlisted metadata only.

Audit records must not contain raw patient narrative, uploaded document text, prompts, model output, correction text, API keys, session tokens, OTP codes, TOTP seeds, director bootstrap secrets, provider keys, filesystem paths, or stack traces. Synthetic canary tests cover these categories.

The local ledger path and any rotated segment or export are runtime evidence artifacts and must remain untracked. `.gitignore` excludes `backend/audit_ledger*.jsonl` and `backend/audit_exports/`. Local ledger content is not a registry artifact, not formal clinical evidence, not a compliance record, and not production audit storage.

HMAC verification depends on secret key control. If the host and key are compromised, audit history can be rewritten. A valid-prefix tail truncation may still verify locally unless an external checkpoint, signed footer, immutable archive, or attestation exists. Segment rotation is local-linkage only; key rotation is not implemented. External immutable archive storage and managed key custody remain required before controlled-pilot, hospital, compliance, or production claims.

## Phase 8 Registry Completion Planning Position

Phase 8 inventory and planning has begun. No implementation, registry activation, or code changes are included in the planning checkpoint.

Current local registry status at Phase 8 planning:

| Dataset | Entries | Quarantined | Release Eligible | Authoritative |
|---|---|---|---|---|
| SDKI current | 152 | 152 | 0 | 0 |
| SDKI backups (×6) | 152 each | 152 each | 0 | 0 |
| SDKI population report | metadata | N/A | 0 | 0 |
| SLKI | 0 | N/A | 0 | 0 |
| SIKI | 0 | N/A | 0 | 0 |
| NANDA | 0 | N/A | 0 | 0 |
| NOC | 0 | N/A | 0 | 0 |
| NIC | 0 | N/A | 0 | 0 |

Conservative registry rules remain unchanged:

- File presence is not approved registry availability.
- OCR output is not approved registry content.
- LLM-assisted population is not approved registry content.
- Only explicitly reviewed and approved release artifacts may become authoritative.
- Missing, unapproved, quarantined, or extraction-unverified SDKI/SLKI/SIKI/NANDA/NOC/NIC registries must preserve complete care-plan abstention.
- License review remains incomplete unless formal evidence exists.
- Formal clinical review remains incomplete unless formal evidence exists.
- Durable release storage remains pending until Phase 8 implementation.
- Gate A remains unmet.
- Gate B remains unmet.
- Gate C remains unmet.
- Not patient-care software.
- Not production-ready.
- Not hospital-ready.
- Not compliant.
