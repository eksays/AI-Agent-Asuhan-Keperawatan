from __future__ import annotations

import inspect
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag_benchmark import BenchmarkQuery, run_lexical_benchmark, run_vector_benchmark
import rag_benchmark


def _outcome(retrieved: bool, chunk_ids: tuple[str, ...]):
    citations = tuple(SimpleNamespace(chunk_id=chunk_id) for chunk_id in chunk_ids)
    return SimpleNamespace(retrieved=retrieved, citations=citations)


class P9CBenchmarkTests(unittest.TestCase):
    def test_empty_fixture_set_returns_zeroed_metrics(self):
        metrics = run_lexical_benchmark(None, (), top_k=5)
        self.assertEqual(metrics.query_count, 0)
        self.assertEqual(metrics.top_k, 5)
        self.assertEqual(metrics.hit_rate_at_k, 0.0)
        self.assertEqual(metrics.recall_at_k, 0.0)
        self.assertEqual(metrics.mean_reciprocal_rank, 0.0)
        self.assertEqual(metrics.abstention_count, 0)
        self.assertEqual(metrics.latency_ms_min, 0)
        self.assertEqual(metrics.latency_ms_max, 0)
        self.assertEqual(metrics.latency_ms_mean, 0.0)

    def test_lexical_baseline_metrics_are_deterministic_for_fixed_synthetic_fixture(self):
        queries = (
            BenchmarkQuery('SYN-Q1', 'synthetic breathing comfort', ('SYN-C1', 'SYN-C9')),
            BenchmarkQuery('SYN-Q2', 'synthetic posture review', ('SYN-C8',)),
            BenchmarkQuery('SYN-Q3', 'synthetic missing target', ('SYN-C5',)),
        )
        with patch('rag_benchmark.retrieve_lexical') as mock_retrieve:
            mock_retrieve.side_effect = (
                _outcome(True, ('SYN-C2', 'SYN-C1')),
                _outcome(True, ('SYN-C8',)),
                _outcome(False, ()),
            )
            metrics = run_lexical_benchmark(None, queries, top_k=5)

        self.assertEqual(metrics.query_count, 3)
        self.assertEqual(metrics.top_k, 5)
        self.assertEqual(metrics.abstention_count, 1)
        self.assertTrue(math.isclose(metrics.hit_rate_at_k, 2 / 3, rel_tol=1e-6))
        self.assertTrue(math.isclose(metrics.recall_at_k, 0.5, rel_tol=1e-6))
        self.assertTrue(math.isclose(metrics.mean_reciprocal_rank, 0.5, rel_tol=1e-6))
        self.assertGreaterEqual(metrics.latency_ms_min, 0)
        self.assertGreaterEqual(metrics.latency_ms_max, metrics.latency_ms_min)
        self.assertLessEqual(metrics.latency_ms_max, 300000)

    def test_vector_baseline_is_measured_separately_from_lexical(self):
        queries = (
            BenchmarkQuery('SYN-VQ1', 'synthetic vector respiratory', ('SYN-V1',)),
            BenchmarkQuery('SYN-VQ2', 'synthetic vector markup', ('SYN-V2',)),
        )
        with patch('rag_benchmark.retrieve_exact_cosine_vector') as mock_vector, patch('rag_benchmark.retrieve_lexical') as mock_lexical:
            mock_vector.side_effect = (
                _outcome(True, ('SYN-V1',)),
                _outcome(True, ('SYN-MISS', 'SYN-V2')),
            )
            metrics = run_vector_benchmark(None, queries, top_k=2)

        mock_lexical.assert_not_called()
        self.assertEqual(metrics.query_count, 2)
        self.assertEqual(metrics.top_k, 2)
        self.assertEqual(metrics.abstention_count, 0)
        self.assertEqual(metrics.hit_rate_at_k, 1.0)
        self.assertEqual(metrics.recall_at_k, 1.0)
        self.assertTrue(math.isclose(metrics.mean_reciprocal_rank, 0.75, rel_tol=1e-6))

    def test_benchmark_queries_are_synthetic_and_non_phi(self):
        queries = (
            BenchmarkQuery('SYN-Q1', 'synthetic breathing comfort', ('SYN-C1',)),
            BenchmarkQuery('SYN-Q2', 'synthetic markup fixture', ('SYN-C2',)),
        )
        forbidden = ('patient', 'mrn', 'rekam medis', 'phi_canary', 'credential', 'password')
        joined = ' '.join(query.query_text for query in queries).lower()
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, joined)

    def test_source_has_no_hybrid_reranking_qdrant_or_quality_claim(self):
        source = inspect.getsource(rag_benchmark).lower()
        self.assertIn('synthetic infrastructure readiness only', source)
        self.assertIn('not a clinical validation', source)
        for token in ('hybrid', 'rerank', 'qdrant', 'semantic-quality', 'clinical-quality'):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


if __name__ == '__main__':
    unittest.main()
