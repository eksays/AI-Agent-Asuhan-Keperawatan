from __future__ import annotations

import inspect
import math
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag_synthetic_vectors import (
    MAX_SYNTHETIC_VECTOR_TEXT_CHARS,
    SYNTHETIC_DIMENSION,
    SYNTHETIC_MODEL_ID,
    SyntheticVectorError,
    generate_synthetic_vector,
)
import rag_synthetic_vectors


class P9CSyntheticVectorTests(unittest.TestCase):
    def test_model_identity_and_dimension_are_fixed(self):
        self.assertEqual(SYNTHETIC_MODEL_ID, 'synthetic-hash-vector-v1')
        self.assertEqual(SYNTHETIC_DIMENSION, 8)

    def test_same_text_is_deterministic_and_different_text_differs(self):
        first = generate_synthetic_vector('synthetic respiratory fixture text')
        second = generate_synthetic_vector('synthetic respiratory fixture text')
        third = generate_synthetic_vector('synthetic pain fixture text')

        self.assertEqual(first, second)
        self.assertNotEqual(first, third)
        self.assertEqual(len(first), SYNTHETIC_DIMENSION)

    def test_vector_values_are_bounded_finite_and_unit_normalized(self):
        vector = generate_synthetic_vector('synthetic bounded vector fixture')

        self.assertTrue(all(math.isfinite(value) for value in vector))
        self.assertTrue(all(-1.0 <= value <= 1.0 for value in vector))
        magnitude = math.sqrt(sum(value * value for value in vector))
        self.assertTrue(math.isclose(magnitude, 1.0, rel_tol=1e-6))

    def test_empty_input_is_rejected_safely(self):
        for value in ('', '   '):
            with self.subTest(value=repr(value)):
                with self.assertRaises(SyntheticVectorError):
                    generate_synthetic_vector(value)

    def test_nul_and_unsafe_control_characters_are_rejected(self):
        for value in ('synthetic\x00fixture', 'synthetic\x1ffixture'):
            with self.subTest(value=repr(value)):
                with self.assertRaises(SyntheticVectorError):
                    generate_synthetic_vector(value)

    def test_oversized_input_is_rejected_safely(self):
        with self.assertRaises(SyntheticVectorError):
            generate_synthetic_vector('x' * (MAX_SYNTHETIC_VECTOR_TEXT_CHARS + 1))

    def test_no_tokenizer_model_network_or_provider_sdk(self):
        source = inspect.getsource(rag_synthetic_vectors).lower()
        forbidden = (
            'tokenizer', 'transformers', 'sentence_transformers', 'openai',
            'requests.', 'httpx.', 'urllib.request', 'qdrant', 'pinecone',
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_source_records_no_semantic_or_clinical_quality_claim(self):
        source = inspect.getsource(rag_synthetic_vectors).lower()
        self.assertIn('not a semantic embedding model', source)
        self.assertIn('non-clinical test fixture', source)
        self.assertNotIn('semantic-quality validation', source)
        self.assertNotIn('clinical-quality validation', source)


if __name__ == '__main__':
    unittest.main()
