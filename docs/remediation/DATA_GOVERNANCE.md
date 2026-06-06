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

Required controls for future phases:

- Data lifecycle states: `draft`, `ocr_extracted`, `llm_assisted`, `under_clinical_review`, `approved`, `deprecated`, `quarantined`.
- Approved-only grounding.
- Provenance fields for source title, source version, page/section, extraction method, reviewer, review date, approval status, content hash, and registry version.
- Quarantine invalid/malformed/duplicate/unapproved entries at load time.
- Disable missing frameworks instead of generating content from model memory.
