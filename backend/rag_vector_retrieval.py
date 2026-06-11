"""Phase 9 P9-C - Exact-cosine synthetic vector baseline retrieval.

This module provides a baseline vector retrieval implementation using
exact cosine distance (pgvector `<=>`). It relies exclusively on
the deterministic synthetic vector generator.

THIS IS NOT A CLINICAL RETRIEVAL SYSTEM.
NO PRODUCT ROUTE EXPOSES THIS.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from rag_abstention import RagAbstention, abstain
from rag_citations import CitationPackage, package_citation
from rag_repository import RagRepository
from rag_synthetic_vectors import generate_synthetic_vector, SYNTHETIC_DIMENSION
from rag_telemetry import RetrievalTelemetry, bounded_latency_ms, new_event_id, record_metadata_only_event
from rag_lexical_retrieval import RagRetrievalError, validate_query


@dataclass(frozen=True)
class VectorRetrievalConfig:
    max_results: int = 5
    max_excerpt_chars: int = 360
    min_vector_score: float = 0.5  # Cosine similarity minimum (1 - distance)
    max_selected_chunk_ids: int = 8
    min_result_count: int = 1
    max_query_chars: int = 160
    event_prefix: str = 'SYN-V-P9C'

    def bounded(self) -> 'VectorRetrievalConfig':
        return VectorRetrievalConfig(
            max_results=max(1, min(int(self.max_results), 20)),
            max_excerpt_chars=max(80, min(int(self.max_excerpt_chars), 1200)),
            min_vector_score=max(0.0, min(float(self.min_vector_score), 1.0)),
            max_selected_chunk_ids=max(1, min(int(self.max_selected_chunk_ids), 20)),
            min_result_count=max(1, min(int(self.min_result_count), 20)),
            max_query_chars=max(8, min(int(self.max_query_chars), 300)),
            event_prefix=self.event_prefix[:32] or 'SYN-V-P9C',
        )


@dataclass(frozen=True)
class VectorRetrievalOutcome:
    retrieved: bool
    release_id: str | None
    citations: tuple[CitationPackage, ...]
    abstention: RagAbstention | None
    telemetry_event_id: str

    def as_safe_dict(self) -> dict[str, object]:
        return {
            'retrieved': self.retrieved,
            'release_id': self.release_id or '',
            'citations': [citation.as_dict() for citation in self.citations],
            'abstention': self.abstention.as_safe_dict() if self.abstention else None,
            'telemetry_event_id': self.telemetry_event_id,
        }


def _record_abstention(
    repo: RagRepository,
    *,
    event_id: str,
    release_id: str | None,
    reason_code: str,
    latency_ms: int,
) -> VectorRetrievalOutcome:
    reason = abstain(reason_code)
    record_metadata_only_event(
        repo,
        RetrievalTelemetry(
            retrieval_event_id=event_id,
            index_release_id=release_id,
            retrieval_backend='vector',
            filter_summary_code='synthetic_only_v1',
            selected_chunk_ids=(),
            result_count=0,
            score_min=0.0,
            score_max=0.0,
            score_mean=0.0,
            abstention_reason_code=reason.reason_code,
            latency_ms=latency_ms,
        ),
    )
    return VectorRetrievalOutcome(False, release_id, (), reason, event_id)


def retrieve_exact_cosine_vector(conn, query: str, config: VectorRetrievalConfig | None = None) -> VectorRetrievalOutcome:
    cfg = (config or VectorRetrievalConfig()).bounded()
    repo = RagRepository(conn)
    started = time.monotonic()
    event_id = new_event_id(cfg.event_prefix)
    try:
        safe_query = validate_query(query, max_query_chars=cfg.max_query_chars)
    except RagRetrievalError as exc:
        outcome = _record_abstention(repo, event_id=event_id, release_id=None, reason_code=str(exc), latency_ms=bounded_latency_ms(started))
        conn.commit()
        return outcome

    try:
        query_vector = generate_synthetic_vector(safe_query)
        if len(query_vector) != SYNTHETIC_DIMENSION:
            raise RuntimeError('invalid_synthetic_dimension')

        release_id, rows = repo.fetch_active_vector(query_vector=query_vector, max_results=cfg.max_results)
        if not release_id:
            outcome = _record_abstention(repo, event_id=event_id, release_id=None, reason_code='no_active_synthetic_release', latency_ms=bounded_latency_ms(started))
            conn.commit()
            return outcome

        # Cosine similarity is 1 - distance, handled in SQL query as `retrieval_score`
        filtered = [row for row in rows if float(row.get('retrieval_score', 0.0) or 0.0) >= cfg.min_vector_score]
        if not filtered:
            outcome = _record_abstention(repo, event_id=event_id, release_id=release_id, reason_code='below_minimum_rank', latency_ms=bounded_latency_ms(started))
            conn.commit()
            return outcome

        if len(filtered) < cfg.min_result_count:
            outcome = _record_abstention(repo, event_id=event_id, release_id=release_id, reason_code='insufficient_result_count', latency_ms=bounded_latency_ms(started))
            conn.commit()
            return outcome

        selected = filtered[: cfg.max_selected_chunk_ids]
        citations = tuple(
            package_citation(row, ordinal=idx + 1, max_excerpt_chars=cfg.max_excerpt_chars)
            for idx, row in enumerate(selected)
        )
        scores = [citation.retrieval_score for citation in citations]

        from rag_telemetry import summarize_scores
        score_min, score_max, score_mean = summarize_scores(scores)

        record_metadata_only_event(
            repo,
            RetrievalTelemetry(
                retrieval_event_id=event_id,
                index_release_id=release_id,
                retrieval_backend='vector',
                filter_summary_code='synthetic_only_v1',
                selected_chunk_ids=tuple(citation.chunk_id for citation in citations),
                result_count=len(citations),
                score_min=score_min,
                score_max=score_max,
                score_mean=score_mean,
                abstention_reason_code='',
                latency_ms=bounded_latency_ms(started),
            ),
        )
        conn.commit()
        return VectorRetrievalOutcome(True, release_id, citations, None, event_id)

    except Exception:
        conn.rollback()
        try:
            outcome = _record_abstention(repo, event_id=event_id, release_id=None, reason_code='internal_safe_failure', latency_ms=bounded_latency_ms(started))
            conn.commit()
            return outcome
        except Exception as exc:
            conn.rollback()
            raise RagRetrievalError('retrieval_backend_unavailable') from exc
