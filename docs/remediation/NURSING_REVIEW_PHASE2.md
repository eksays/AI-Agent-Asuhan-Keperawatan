# Nursing Review Sheet — Phase 2

Purpose: collect nursing-informatics feedback on the Phase 2 abstention and evidence-trace behavior using synthetic examples only.

This is not a request to approve code, approve registry licensing, certify clinical safety, or authorize production use. Informal nursing review does not replace formal clinical validation, privacy review, legal review, or registry governance.

## Review Status

| Item | Status |
|---|---|
| Reviewer role | Nursing perspective reviewer |
| Review date | 2026-06-06 |
| Status | informal nursing-informatics feedback completed with disclaimer |
| Authority | non-authoritative design feedback only |

This sheet remains non-authoritative. It must not be used as production approval, official registry approval, legal approval, hospital readiness approval, compliance certification, or clinical validation certification.

## Informal Nursing Disclaimer

Dokumen pendukung 3S dan 3N belum cukup konkret karena masih terdapat
masalah pada ekstraksi tulisan. Akibatnya, kualitas dan kelengkapan hasil
ekstraksi belum maksimal.

Registry hasil ekstraksi belum boleh dianggap authoritative untuk
menghasilkan care plan rumah sakit sebelum debugging ekstraksi, review
isi, provenance verification, dan validasi lanjutan selesai dilakukan.

## Feedback Classification

| Reviewer Note | Classification | Action |
|---|---|---|
| Dokumen pendukung 3S/3N belum konkret | requires formal clinical review | keep registries non-authoritative |
| Ekstraksi tulisan masih bermasalah | deferred to Phase 3 and Phase 8 | quarantine and governed extraction review workflow |
| Hasil dokumen belum maksimal | requires extraction-quality debugging | do not activate registry |
| Debugging dilanjutkan nanti | deferred implementation | preserve fail-closed behavior now |

## Strict Abstention Policy Preserved

For 3S, SDKI, SLKI, and SIKI must each be explicitly approved, reviewed, and extraction-verified before the normal care-plan workflow may present accepted recommendations. If SDKI, SLKI, or SIKI is missing, unapproved, quarantined, or extraction-unverified, the system must abstain from the complete care-plan response.

For 3N, NANDA, NOC, and NIC must each be explicitly approved, reviewed, and extraction-verified before the normal care-plan workflow may present accepted recommendations. If NANDA, NOC, or NIC is missing, unapproved, quarantined, or extraction-unverified, the system must abstain from the complete care-plan response.

Required response state for incomplete approved registry families remains:

```text
clinical_status = registry_incomplete
accepted_recommendations = false
nurse_review_required = true
```

Diagnosis-only accepted output is not allowed in the normal hospital-facing workflow while outcome or intervention registries are missing or unverified. Missing components must not be filled from model memory.

## Synthetic Example A — Insufficient Data

Input summary:

```text
Pasien batuk dan sesak. Data objektif belum lengkap.
```

Expected system response:

```text
Data klinis belum cukup untuk menyarankan diagnosis secara aman.
Mohon lengkapi RR, SpO2, pola napas, penggunaan otot bantu napas, data subjektif, dan data objektif utama.
Nurse review required: ya.
```

Reviewer questions:

| Question | Reviewer Notes |
|---|---|
| Does the abstention message make sense clinically? |  |
| Does it request useful missing information? |  |
| Is the wording clear that no diagnosis has been accepted? |  |
| Could a nurse mistake this for an authoritative recommendation? |  |

## Synthetic Example B — Registry-Backed Candidate

Input summary:

```text
Pasien batuk, sputum kental, RR 28 x/menit, SpO2 90%, suara napas ronki.
```

Synthetic structured candidate:

```json
{
  "framework": "3S",
  "diagnoses": [
    {
      "framework": "SDKI",
      "code": "D.0001",
      "name": "Bersihan Jalan Napas Tidak Efektif",
      "supporting_evidence": [
        {"patient_fact": "RR 28 x/menit dan SpO2 90%", "source": "patient_record"}
      ],
      "validation_status": "validated",
      "nurse_review_required": true
    }
  ]
}
```

Reviewer questions:

| Question | Reviewer Notes |
|---|---|
| Are supporting-evidence traces understandable? |  |
| Does the evidence look clinically relevant to the candidate? |  |
| Does the output preserve room for professional judgment? |  |
| What additional patient facts should be requested before use? |  |

## Synthetic Example C — Invented Code Rejected

Input summary:

```text
Provider returns confident prose with an invented code: D.9999.
```

Expected behavior:

```text
The system rejects the output as malformed or registry-invalid, returns a safe abstention, and does not display the invented code as an accepted diagnosis.
```

Reviewer questions:

| Question | Reviewer Notes |
|---|---|
| Is the rejection explanation understandable? |  |
| Is the missing-data request clinically useful? |  |
| Could the UI mislead a nurse into treating an invalid result as authoritative? |  |
| Is the nurse-review requirement visible enough? |  |

## Synthetic Example D - Trusted Evidence Binding

Input summary:

```text
RR 20 x/menit, SpO2 98%, tidak sesak.
```

Provider-authored evidence attempt:

```text
RR 32 x/menit, SpO2 88%, pasien sesak.
```

Expected behavior:

```text
The system rejects or abstains because numeric measurements do not match trusted input and a negated finding is converted into a positive finding.
```

Reviewer questions:

| Question | Reviewer Notes |
|---|---|
| Is this rejection explanation clinically understandable? |  |
| Would the requested follow-up data be useful in nursing workflow? |  |
| Should contradictory evidence show more detail, or would that risk overloading the UI? |  |

## Synthetic Example E - Partial Registry Availability

Interim product-safety decision pending informal nursing-informatics review:

```text
For 3S: approved SDKI available but approved SLKI or SIKI unavailable -> abstain from the complete care-plan response.
For 3N: approved NANDA available but approved NOC or NIC unavailable -> abstain from the complete care-plan response.
```

Required system behavior:

```text
clinical_status = registry_incomplete
accepted_recommendations = false
nurse_review_required = true
The response lists missing approved registries and states that the care plan cannot be generated safely.
```

Plain-language explanation:

```text
registry_incomplete means the system has one approved registry family but not every approved registry needed for a complete care plan.
complete care-plan abstention means the system does not present diagnosis, outcome, or intervention recommendations as accepted.
missing registries are named directly, for example SLKI and SIKI.
no diagnosis-only accepted recommendation is shown in the normal hospital-facing workflow while outcome/intervention registries are missing.
no model-memory completion is allowed for missing SLKI, SIKI, NOC, or NIC components.
```

Reviewer questions:

| Question | Reviewer Notes |
|---|---|
| Is complete care-plan abstention understandable and appropriate for the intended nursing workflow? |  |
| Does the wording reduce automation-bias risk compared with diagnosis-only output? |  |
| What wording would make missing approved registries and unavailable care-plan components unmistakable? |  |

## Reviewer Scope Reminder

Please assess clarity, clinical usefulness of missing-data prompts, evidence-trace readability, and automation-bias risk. Do not approve registry content, code implementation, licensing status, or production deployment in this sheet.
