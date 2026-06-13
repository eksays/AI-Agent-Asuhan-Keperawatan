from __future__ import annotations

from dataclasses import dataclass


ABSTENTION_REASON_CODES = {
    'query_empty',
    'query_rejected',
    'no_active_synthetic_release',
    'no_approved_synthetic_chunks',
    'filter_no_match',
    'below_minimum_rank',
    'insufficient_result_count',
    'retrieval_backend_unavailable',
    'unsafe_fixture_state',
    'internal_safe_failure',
}


@dataclass(frozen=True)
class RagAbstention:
    reason_code: str
    retrieval_backend: str = 'lexical'
    clinical_recommendation_allowed: bool = False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            'abstained': True,
            'reason_code': self.reason_code,
            'retrieval_backend': self.retrieval_backend,
            'clinical_recommendation_allowed': False,
        }


def abstain(reason_code: str) -> RagAbstention:
    if reason_code not in ABSTENTION_REASON_CODES:
        reason_code = 'internal_safe_failure'
    return RagAbstention(reason_code=reason_code)
