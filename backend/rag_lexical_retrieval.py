from __future__ import annotations

import re
import time
from dataclasses import dataclass

from rag_abstention import RagAbstention, abstain
from rag_citations import CitationPackage, package_citation
from rag_repository import RagRepository
from rag_telemetry import RetrievalTelemetry, bounded_latency_ms, new_event_id, record_metadata_only_event, summarize_scores


class RagRetrievalError(RuntimeError):
    pass


@dataclass(frozen=True)
class LexicalRetrievalConfig:
    max_results: int = 5
    max_excerpt_chars: int = 360
    min_lexical_rank: float = 0.01
    max_selected_chunk_ids: int = 8
    min_result_count: int = 1
    max_query_chars: int = 160
    event_prefix: str = 'SYN-P9B'

    def bounded(self) -> 'LexicalRetrievalConfig':
        return LexicalRetrievalConfig(
            max_results=max(1, min(int(self.max_results), 20)),
            max_excerpt_chars=max(80, min(int(self.max_excerpt_chars), 1200)),
            min_lexical_rank=max(0.0, min(float(self.min_lexical_rank), 10.0)),
            max_selected_chunk_ids=max(1, min(int(self.max_selected_chunk_ids), 20)),
            min_result_count=max(1, min(int(self.min_result_count), 20)),
            max_query_chars=max(8, min(int(self.max_query_chars), 300)),
            event_prefix=self.event_prefix[:32] or 'SYN-P9B',
        )


@dataclass(frozen=True)
class LexicalRetrievalOutcome:
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


def validate_query(query: str, *, max_query_chars: int = 160) -> str:
    raw = (query or '').strip()
    if not raw:
        raise RagRetrievalError('query_empty')
    if len(raw) > max_query_chars:
        raise RagRetrievalError('query_rejected')
    for char in raw:
        code = ord(char)
        if code < 32 and char not in {'\t', '\n'}:
            raise RagRetrievalError('query_rejected')
    compact = re.sub(r'\s+', ' ', raw).strip()
    if not compact:
        raise RagRetrievalError('query_empty')
    return compact


def _record_abstention(
    repo: RagRepository,
    *,
    event_id: str,
    release_id: str | None,
    reason_code: str,
    latency_ms: int,
) -> LexicalRetrievalOutcome:
    reason = abstain(reason_code)
    record_metadata_only_event(
        repo,
        RetrievalTelemetry(
            retrieval_event_id=event_id,
            index_release_id=release_id,
            retrieval_backend='lexical',
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
    return LexicalRetrievalOutcome(False, release_id, (), reason, event_id)


def retrieve_lexical(conn, query: str, config: LexicalRetrievalConfig | None = None) -> LexicalRetrievalOutcome:
    cfg = (config or LexicalRetrievalConfig()).bounded()
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
        release_id, rows = repo.fetch_active_lexical(safe_query=safe_query, max_results=cfg.max_results)
        if not release_id:
            outcome = _record_abstention(repo, event_id=event_id, release_id=None, reason_code='no_active_synthetic_release', latency_ms=bounded_latency_ms(started))
            conn.commit()
            return outcome
        filtered = [row for row in rows if float(row.get('retrieval_score', 0.0) or 0.0) >= cfg.min_lexical_rank]
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
        score_min, score_max, score_mean = summarize_scores(scores)
        record_metadata_only_event(
            repo,
            RetrievalTelemetry(
                retrieval_event_id=event_id,
                index_release_id=release_id,
                retrieval_backend='lexical',
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
        return LexicalRetrievalOutcome(True, release_id, citations, None, event_id)
    except Exception:
        conn.rollback()
        try:
            outcome = _record_abstention(repo, event_id=event_id, release_id=None, reason_code='internal_safe_failure', latency_ms=bounded_latency_ms(started))
            conn.commit()
            return outcome
        except Exception as exc:
            conn.rollback()
            raise RagRetrievalError('retrieval_backend_unavailable') from exc
