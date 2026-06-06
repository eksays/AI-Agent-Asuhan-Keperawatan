from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ClinicalStatus = Literal["validated", "insufficient_data", "registry_unavailable", "registry_incomplete", "malformed_output", "rejected"]
ValidationStatus = Literal["validated", "unsupported", "rejected", "unvalidated"]
ConfidenceBand = Literal["low", "medium", "high", "unknown"]
IssueSeverity = Literal["low", "medium", "high", "critical"]


class RegistryReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    framework: str
    code: str
    name: str
    registry_version: str | None = None
    registry_source: str | None = None


class SupportingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_fact: str
    source: str
    matched_criterion: str | None = None

    @field_validator("patient_fact", "source")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("supporting evidence fields must not be blank")
        return value


class DiagnosisCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    framework: str
    code: str
    name: str
    supporting_evidence: list[SupportingEvidence] = Field(default_factory=list)
    missing_required_evidence: list[str] = Field(default_factory=list)
    registry_version: str | None = None
    registry_source: str | None = None
    confidence_band: ConfidenceBand = "unknown"
    validation_status: ValidationStatus = "unvalidated"
    nurse_review_required: bool = True


class OutcomeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    framework: str
    code: str | None = None
    name: str
    supporting_evidence: list[SupportingEvidence] = Field(default_factory=list)
    validation_status: ValidationStatus = "unvalidated"
    nurse_review_required: bool = True


class InterventionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    framework: str
    code: str | None = None
    name: str
    rationale: str | None = None
    supporting_evidence: list[SupportingEvidence] = Field(default_factory=list)
    validation_status: ValidationStatus = "unvalidated"
    nurse_review_required: bool = True


class MissingClinicalData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    reason: str
    question_for_nurse: str


class ClinicalValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: IssueSeverity
    message: str


class ClinicalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ClinicalStatus
    framework: str
    diagnoses: list[DiagnosisCandidate] = Field(default_factory=list)
    outcomes: list[OutcomeCandidate] = Field(default_factory=list)
    interventions: list[InterventionCandidate] = Field(default_factory=list)
    missing_data: list[MissingClinicalData] = Field(default_factory=list)
    validation_issues: list[ClinicalValidationIssue] = Field(default_factory=list)
    nurse_review_required: bool = True


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def model_to_json(model: BaseModel) -> str:
    return json.dumps(model_to_dict(model), ensure_ascii=False, separators=(",", ":"))
