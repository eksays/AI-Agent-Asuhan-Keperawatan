from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from rag_repository import RagRepository


@dataclass(frozen=True)
class RetrievalTelemetry:
    retrieval_event_id: str
    index_release_id: str | None
    retrieval_backend: str
    filter_summary_code: str
    selected_chunk_ids: tuple[str, ...]
    result_count: int
    score_min: float
    score_max: float
    score_mean: float
    abstention_reason_code: str
    latency_ms: int


def summarize_scores(scores: list[float]) -> tuple[float, float, float]:
    if not scores:
        return 0.0, 0.0, 0.0
    bounded = [max(0.0, min(float(score), 1000.0)) for score in scores]
    return min(bounded), max(bounded), sum(bounded) / len(bounded)


def new_event_id(prefix: str = 'SYN-P9B') -> str:
    return f'{prefix}-RET-{uuid.uuid4().hex[:12]}'


def bounded_latency_ms(started_at: float) -> int:
    elapsed = int((time.monotonic() - started_at) * 1000)
    return max(0, min(elapsed, 300000))


def record_metadata_only_event(repo: RagRepository, telemetry: RetrievalTelemetry) -> None:
    bounded_ids = [value[:96] for value in telemetry.selected_chunk_ids[:20]]
    safe_metadata = {
        'retrieval_event_id': telemetry.retrieval_event_id[:96],
        'index_release_id': (telemetry.index_release_id or '')[:96],
        'retrieval_backend': telemetry.retrieval_backend[:32],
        'filter_summary_code': telemetry.filter_summary_code[:64],
        'score_min': max(0.0, min(float(telemetry.score_min), 1000.0)),
        'score_max': max(0.0, min(float(telemetry.score_max), 1000.0)),
        'score_mean': max(0.0, min(float(telemetry.score_mean), 1000.0)),
        'latency_ms': max(0, min(int(telemetry.latency_ms), 300000)),
    }
    repo.insert_retrieval_event(
        event_id=telemetry.retrieval_event_id,
        release_id=telemetry.index_release_id,
        event_type='abstained' if telemetry.abstention_reason_code else 'retrieved',
        retrieval_backend=telemetry.retrieval_backend,
        result_count=max(0, min(int(telemetry.result_count), 50)),
        selected_chunk_ids=bounded_ids,
        abstention_reason=telemetry.abstention_reason_code,
        safe_metadata=safe_metadata,
    )
