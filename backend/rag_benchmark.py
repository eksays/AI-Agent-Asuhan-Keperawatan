"""Phase 9 P9-C - RAG retrieval benchmark harness.

Calculates standard retrieval metrics (Hit Rate, Recall, MRR, Latency)
for both lexical and vector baselines.

THIS IS FOR SYNTHETIC INFRASTRUCTURE READINESS ONLY.
IT IS NOT A CLINICAL VALIDATION OR PRODUCTION EVALUATION.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Sequence

from rag_lexical_retrieval import retrieve_lexical, LexicalRetrievalConfig
from rag_vector_retrieval import retrieve_exact_cosine_vector, VectorRetrievalConfig


@dataclass(frozen=True)
class BenchmarkQuery:
    query_id: str
    query_text: str
    expected_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkMetrics:
    query_count: int
    top_k: int
    hit_rate_at_k: float
    recall_at_k: float
    mean_reciprocal_rank: float
    abstention_count: int
    latency_ms_min: int
    latency_ms_max: int
    latency_ms_mean: float


def _calculate_metrics(
    queries: Sequence[BenchmarkQuery],
    results: list[tuple[bool, tuple[str, ...], int]],
    top_k: int,
) -> BenchmarkMetrics:
    query_count = len(queries)
    if not query_count:
        return BenchmarkMetrics(0, top_k, 0.0, 0.0, 0.0, 0, 0, 0, 0.0)

    abstention_count = 0
    hit_count = 0
    total_recall = 0.0
    total_mrr = 0.0
    latencies = []

    for i, (retrieved, retrieved_ids, latency) in enumerate(results):
        latencies.append(latency)
        if not retrieved:
            abstention_count += 1
            continue

        expected = set(queries[i].expected_chunk_ids)
        if not expected:
            continue

        bounded_retrieved = list(retrieved_ids)[:top_k]

        # Hit Rate @ K
        hits = [chunk_id for chunk_id in bounded_retrieved if chunk_id in expected]
        if hits:
            hit_count += 1

        # Recall @ K
        recall = len(hits) / len(expected)
        total_recall += recall

        # MRR
        rank = 0
        for idx, chunk_id in enumerate(bounded_retrieved):
            if chunk_id in expected:
                rank = idx + 1
                break
        if rank > 0:
            total_mrr += 1.0 / rank

    hit_rate_at_k = hit_count / query_count
    mean_recall = total_recall / query_count
    mean_mrr = total_mrr / query_count

    return BenchmarkMetrics(
        query_count=query_count,
        top_k=top_k,
        hit_rate_at_k=hit_rate_at_k,
        recall_at_k=mean_recall,
        mean_reciprocal_rank=mean_mrr,
        abstention_count=abstention_count,
        latency_ms_min=min(latencies) if latencies else 0,
        latency_ms_max=max(latencies) if latencies else 0,
        latency_ms_mean=sum(latencies) / len(latencies) if latencies else 0.0,
    )


def run_lexical_benchmark(conn, queries: Sequence[BenchmarkQuery], top_k: int = 5) -> BenchmarkMetrics:
    cfg = LexicalRetrievalConfig(max_results=top_k, max_selected_chunk_ids=top_k, event_prefix='SYN-BM-LEX')
    results = []

    for query in queries:
        t0 = time.monotonic()
        outcome = retrieve_lexical(conn, query.query_text, cfg)
        latency = int((time.monotonic() - t0) * 1000)

        retrieved_ids = tuple(cit.chunk_id for cit in outcome.citations) if outcome.retrieved else ()
        results.append((outcome.retrieved, retrieved_ids, latency))

    return _calculate_metrics(queries, results, top_k)


def run_vector_benchmark(conn, queries: Sequence[BenchmarkQuery], top_k: int = 5) -> BenchmarkMetrics:
    cfg = VectorRetrievalConfig(max_results=top_k, max_selected_chunk_ids=top_k, event_prefix='SYN-BM-VEC')
    results = []

    for query in queries:
        t0 = time.monotonic()
        outcome = retrieve_exact_cosine_vector(conn, query.query_text, cfg)
        latency = int((time.monotonic() - t0) * 1000)

        retrieved_ids = tuple(cit.chunk_id for cit in outcome.citations) if outcome.retrieved else ()
        results.append((outcome.retrieved, retrieved_ids, latency))

    return _calculate_metrics(queries, results, top_k)
