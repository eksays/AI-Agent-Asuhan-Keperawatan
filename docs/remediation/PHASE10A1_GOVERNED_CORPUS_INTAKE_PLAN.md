# Phase 10 P10-A1 Governed Corpus-Intake Plan

This document records the architectural foundation, safety boundaries, and design policies implemented for Phase 10 P10-A1.

## Scope & Purpose
P10-A1 builds a metadata-only governed corpus-intake and quarantine foundation. It establishes the typed metadata contract and synthetic-only policy validator to process document metadata submissions and emit in-memory decision events.

> [!IMPORTANT]
> - Phase 9 remains closed for synthetic retrieval infrastructure scope only.
> - P10-A1 adds the metadata-only intake contract and quarantine foundation. No database schema changes have been applied.
> - This software is **not patient-care software**, **not clinically validated**, **not hospital-ready**, and **not compliant** with clinical production environments.

## Safety & Quarantine Invariants

| Invariant | Safety Strategy / Rule | Status in P10-A1 |
| :--- | :--- | :--- |
| **PostgreSQL Mutation** | Do not modify the active database schema or run migrations. | Static migration definitions are committed but remain unapplied. No PostgreSQL mutation has been executed. |
| **Corpus Body Storage** | No document bodies or excerpts are accepted or stored. | Disabled. |
| **Patient Data & PHI** | Submissions containing patient identifiers, PHI, or patient data flags are rejected. | Forbidden. |
| **Licensed Clinical Text** | No SDKI, SLKI, SIKI, NANDA, NOC, or NIC clinical body copying is performed. | Forbidden. |
| **External Integrations** | No LLM provider, embedding API, or external EBP search queries are called. | Disabled. |
| **Clinical Use Eligibility** | Every source is evaluated as `clinical_use_allowed = false` with no exceptions. | Enforced. |
| **De-identification** | disposition metadata only; no automated or clinically validated de-identification engine exists. | Metadata Only. |
| **Reviewer Identity** | Opaque sandbox actor IDs only (`created_by_actor_ref`). No hospital IAM or verified clinical reviewer identity is configured. | Opaque Sandbox Reference. |
| **Product Retrieval Routes** | No API routes or product endpoints are created. | Not Implemented. |
| **Registry Activation** | The clinical registry remains disabled (`REGISTRY_ACTIVATION_ENABLED=false`). | Disabled. |
| **Release Gates** | Gates A, B, and C remain unmet. | Unmet. |

## Companion Schema Definitions
We defined companion tables to track metadata without modifying the core Phase 9 retrieval schemas:
- `rag_intake_submissions`: Bounded, checked metadata storage verifying `synthetic_only=true`, `contains_phi=false`, `contains_patient_data=false`, and `clinical_use_allowed=false`.
- `rag_intake_decision_events`: Append-only records containing the event outcome, actor reference, and quarantine reasons (no raw bodies or prompts).
- `rag_intake_quarantine_records`: Tracks quarantine expiration TTLs and cleanup statuses.
