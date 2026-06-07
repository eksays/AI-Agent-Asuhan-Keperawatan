from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lab_core import FEATURE_LABELS, PROTOTYPE_STATUS
from lab_rag import LabRagResult
from lab_registry import LabRegistryResult

STAGE_ORDER = ["retrieval", "assessment", "reviewer", "critic", "synthesis", "validator_boundary"]

@dataclass(frozen=True)
class LabStage:
    name: str
    status: str
    latency_ms: int
    reason_code: str

@dataclass(frozen=True)
class LabOrchestrationResult:
    feature_label: str
    stages: list[LabStage]
    clinical_status: str
    missing_data: list[str]
    validation_issue_codes: list[str]
    prototype_candidates: list[dict[str, Any]]
    critic_applied: bool

def run_deterministic_orchestration(
    *,
    case_fixture: dict[str, Any],
    rag_result: LabRagResult | None,
    registry_result: LabRegistryResult | None,
    force_stage_failure: str = "",
    force_timeout: bool = False,
) -> LabOrchestrationResult:
    if force_timeout:
        return _abstain("stage_timeout", ["deterministic stage timeout"])
    if force_stage_failure:
        if force_stage_failure not in STAGE_ORDER:
            raise ValueError("Unknown synthetic lab stage.")
        return _abstain("stage_failure", [f"stage failed: {force_stage_failure}"])

    stages: list[LabStage] = []
    weak_context = bool(rag_result.weak_context) if rag_result else True
    registry_missing = registry_result is None
    stages.append(LabStage("retrieval", "weak_context" if weak_context else "complete", 1, "synthetic_fixture_retrieval"))
    stages.append(LabStage("assessment", "abstain" if weak_context else "complete", 1, "safe_assessment_metadata"))
    stages.append(LabStage("reviewer", "complete", 1, "nurse_review_required"))
    critic_reason = "critic_forced_abstention" if weak_context or registry_missing else "critic_added_prototype_warning"
    stages.append(LabStage("critic", "requires_abstention" if weak_context or registry_missing else "complete", 1, critic_reason))
    stages.append(LabStage("synthesis", "abstain", 1, "accepted_recommendations_false"))
    stages.append(LabStage("validator_boundary", "complete", 1, "clinical_use_forbidden"))

    missing = []
    issues = ["synthetic_only_not_clinical"]
    if weak_context:
        missing.append("strong synthetic retrieval context")
        issues.append("weak_context")
    if registry_missing:
        missing.append("synthetic registry fixture")
        issues.append("registry_fixture_missing")
    candidates = registry_result.prototype_candidates if registry_result else []
    return LabOrchestrationResult(
        feature_label=FEATURE_LABELS["run"],
        stages=stages,
        clinical_status=PROTOTYPE_STATUS,
        missing_data=missing,
        validation_issue_codes=issues,
        prototype_candidates=candidates,
        critic_applied=True,
    )

def _abstain(reason_code: str, missing_data: list[str]) -> LabOrchestrationResult:
    stages = [
        LabStage(name, "failed" if name == "assessment" else "abstain", 0, reason_code)
        for name in STAGE_ORDER
    ]
    return LabOrchestrationResult(
        feature_label=FEATURE_LABELS["run"],
        stages=stages,
        clinical_status=PROTOTYPE_STATUS,
        missing_data=missing_data,
        validation_issue_codes=[reason_code, "synthetic_only_not_clinical"],
        prototype_candidates=[],
        critic_applied=True,
    )
