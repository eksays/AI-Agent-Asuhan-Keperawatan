# Registry Dry-Run Report - Phase 3

Dry-run scope: ignored/local registry files under `backend/data_terstruktur/`. This report records safe metadata only. It does not copy registry body content, activate data, approve licensing, approve clinical content, or create a release artifact.

Dry-run command used for the current SDKI file:

```powershell
backend\venv\Scripts\python.exe backend\scripts\registry_import.py backend\data_terstruktur\SDKI.json --dry-run --quarantine-report --dataset-name SDKI-local-ignored --framework SDKI
```

## Current SDKI Dry Run

| Dataset | Entries | Quarantined | Release Eligible | Authoritative |
|---|---:|---:|---:|---:|
| `SDKI.json` | 152 | 152 | 0 | 0 |

## Quarantine Reason Counts

| Reason Code | Count | Meaning |
|---|---:|---|
| `APPROVAL_STATUS_NOT_APPROVED` | 152 | Entries do not carry formal approved status. |
| `LICENSE_STATUS_UNKNOWN` | 152 | No reviewed source-license status is present. |
| `MALFORMED_CODE` | 2 | Two codes fail SDKI source-framework format validation. |
| `MISSING_FRAMEWORK` | 152 | Entries lack explicit framework metadata. |
| `MISSING_PROVENANCE` | 152 | Mandatory provenance fields are absent. |
| `NOT_APPROVED_LIFECYCLE` | 152 | Entries are not in a governed approved lifecycle state. |
| `WRONG_COMPONENT_TYPE` | 152 | Entries lack explicit component type matching the framework. |

## Ignored Backup Summary

| Dataset | Entries | Quarantined | Malformed Codes | Missing Framework | Missing Provenance | Release Eligible | Authoritative |
|---|---:|---:|---:|---:|---:|---:|---:|
| `SDKI.json` | 152 | 152 | 2 | 152 | 152 | 0 | 0 |
| `SDKI.json.bak-20260604-011749` | 152 | 152 | 2 | 152 | 152 | 0 | 0 |
| `SDKI.json.bak-20260604-063606` | 152 | 152 | 2 | 152 | 152 | 0 | 0 |
| `SDKI.json.bak-20260604-065343` | 152 | 152 | 2 | 152 | 152 | 0 | 0 |
| `SDKI.json.bak-20260604-072849` | 152 | 152 | 2 | 152 | 152 | 0 | 0 |
| `SDKI.json.bak-20260604-074200` | 152 | 152 | 2 | 152 | 152 | 0 | 0 |
| `SDKI.json.bak-20260604-074738` | 152 | 152 | 2 | 152 | 152 | 0 | 0 |

## Population Report Metadata

| File | Type | Handling |
|---|---|---|
| `SDKI_population_report.json` | Local LLM-assisted population report | Non-authoritative metadata only; not a clinical approval record, not license approval, and not a release manifest. |

## Release Eligibility Verdict

`FAIL` for all local ignored registry files. No local SDKI file or backup is release eligible. The registry remains non-authoritative and must stay inactive until Phase 3/8 governance work supplies formal provenance, license review, clinical review, approval records, release manifests, and rollback evidence.

## Safety Notes

- File presence does not imply approved registry availability.
- OCR-derived content remains non-authoritative until reviewed and verified.
- LLM-assisted population remains non-authoritative until reviewed and verified.
- Informal nursing feedback remains non-authoritative and is not an approval record.
- No active release was created.
- No `backend/data_terstruktur/*` file is staged by this phase.

## Closure Safety Verification

Phase 3 closure tests verify the importer is non-destructive and metadata-only:

| Area | Verified Behavior |
|---|---|
| Explicit source path | Explicit JSON file is imported; unsupported extension and missing file are rejected safely. |
| Directory import | Approved directory import resolves only `<FRAMEWORK>.json`; backup files are excluded by default. |
| Path escape | Traversal, absolute outside-root path, and symlink-resolved escape are rejected. |
| Resource limits | Oversized file, excessive entry count, deeply nested JSON, and oversized field content are rejected or quarantined safely. |
| Network deny | Dry-run import performs zero socket, urllib, requests, httpx, external LLM, or EBP calls in tests. |
| Source mutation | Dry-run import leaves source file hash unchanged. |

Canonical content hash strategy: stable fields are serialized as sorted-key compact JSON before SHA-256 hashing. Whitespace and key-order changes do not alter the hash; clinical content changes do alter it; volatile workflow fields such as reviewer identity, review date, and release id are excluded by design.
