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
