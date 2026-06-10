from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class P9BConfigTests(unittest.TestCase):
    def test_defaults_remain_disabled_and_full_synthetic_posture_is_allowed(self):
        from config import load_config

        default = load_config({'APP_MODE': 'clinical_sandbox'})
        self.assertEqual(default.rag_runtime_mode, 'disabled')
        self.assertFalse(default.rag_store_enabled)
        self.assertFalse(default.rag_ingestion_enabled)
        self.assertFalse(default.rag_lexical_retrieval_enabled)
        self.assertFalse(default.rag_index_activation_enabled)
        self.assertFalse(default.rag_vector_retrieval_enabled)
        self.assertFalse(default.rag_external_embedding_provider_enabled)
        enabled = load_config({
            'APP_MODE': 'clinical_sandbox',
            'RAG_RUNTIME_MODE': 'synthetic_corpus_test',
            'REGISTRY_ACTIVATION_ENABLED': 'false',
            'RAG_STORE_ENABLED': 'true',
            'RAG_INGESTION_ENABLED': 'true',
            'RAG_LEXICAL_RETRIEVAL_ENABLED': 'true',
            'RAG_INDEX_ACTIVATION_ENABLED': 'true',
        })
        self.assertTrue(enabled.rag_db_mutation_allowed)
        self.assertTrue(enabled.rag_index_activation_enabled)
        self.assertFalse(enabled.registry_activation_enabled)

    def test_vector_provider_and_registry_activation_remain_rejected(self):
        from config import load_config

        base = {
            'APP_MODE': 'clinical_sandbox',
            'RAG_RUNTIME_MODE': 'synthetic_corpus_test',
            'RAG_STORE_ENABLED': 'true',
            'RAG_INGESTION_ENABLED': 'true',
            'RAG_LEXICAL_RETRIEVAL_ENABLED': 'true',
            'RAG_INDEX_ACTIVATION_ENABLED': 'true',
        }
        for flag in ('RAG_VECTOR_RETRIEVAL_ENABLED', 'RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED', 'REGISTRY_ACTIVATION_ENABLED'):
            env = dict(base)
            env[flag] = 'true'
            with self.subTest(flag=flag), self.assertRaises(RuntimeError):
                load_config(env)


class P9BLexicalRetrievalTests(unittest.TestCase):
    def test_query_validation_bounds_empty_control_and_injection_shape(self):
        from rag_lexical_retrieval import RagRetrievalError, validate_query

        with self.assertRaises(RagRetrievalError):
            validate_query('')
        with self.assertRaises(RagRetrievalError):
            validate_query('unsafe\x02query')
        shaped = validate_query("synthetic'; drop table rag_chunks; --")
        self.assertIn('drop table', shaped)

    def test_citation_packaging_plain_text_bounded_and_synthetic(self):
        from rag_citations import package_citation

        citation = package_citation(
            {
                'chunk_id': 'SYN-P9B-CHK',
                'document_id': 'SYN-P9B-DOC',
                'source_version_id': 'SYN-P9B-VER',
                'source_title_safe': 'Synthetic Source',
                'section_path': 'Root > Markup',
                'chunk_ordinal': 1,
                'chunk_hash': 'a' * 64,
                'chunk_text': "<script>alert('x')</script> plain synthetic excerpt",
                'retrieval_score': 0.5,
                'synthetic_only': True,
                'authority': False,
                'clinical_use_allowed': False,
            },
            ordinal=1,
            max_excerpt_chars=80,
        )
        self.assertNotIn('<script>', citation.excerpt_plain_text.lower())
        self.assertLessEqual(len(citation.excerpt_plain_text), 80)
        self.assertTrue(citation.synthetic_only)
        self.assertFalse(citation.authority)
        self.assertFalse(citation.clinical_use_allowed)

    def test_abstention_is_typed_and_safe(self):
        from rag_abstention import abstain

        result = abstain('query_empty').as_safe_dict()
        self.assertTrue(result['abstained'])
        self.assertEqual(result['reason_code'], 'query_empty')
        self.assertFalse(result['clinical_recommendation_allowed'])
        self.assertEqual(abstain('unknown').reason_code, 'internal_safe_failure')

    def test_telemetry_allowlist_bounds_selected_ids_and_scores(self):
        from rag_telemetry import RetrievalTelemetry, record_metadata_only_event


        class FakeRepo:
            def __init__(self):
                self.kwargs = None

            def insert_retrieval_event(self, **kwargs):
                self.kwargs = kwargs

        repo = FakeRepo()
        record_metadata_only_event(
            repo,
            RetrievalTelemetry(
                retrieval_event_id='SYN-P9B-RET',
                index_release_id='SYN-P9B-REL',
                retrieval_backend='lexical',
                filter_summary_code='synthetic_only_v1',
                selected_chunk_ids=tuple('chunk-' + str(i) for i in range(30)),
                result_count=100,
                score_min=-1.0,
                score_max=2000.0,
                score_mean=3.0,
                abstention_reason_code='',
                latency_ms=999999,
            ),
        )
        self.assertEqual(repo.kwargs['result_count'], 50)
        self.assertEqual(len(repo.kwargs['selected_chunk_ids']), 20)
        metadata = repo.kwargs['safe_metadata']
        self.assertNotIn('query', metadata)
        self.assertNotIn('prompt', metadata)
        self.assertLessEqual(metadata['score_max'], 1000.0)
        self.assertLessEqual(metadata['latency_ms'], 300000)

    def test_repository_uses_parameterized_simple_fts_and_no_vector_query(self):
        source = (ROOT / 'rag_repository.py').read_text(encoding='utf-8').lower()
        self.assertIn("websearch_to_tsquery('simple', %s)", source)
        self.assertNotIn('rag_chunk_embeddings c', source)
        self.assertNotIn('embedding <->', source)
        retrieval_source = (ROOT / 'rag_lexical_retrieval.py').read_text(encoding='utf-8').lower()
        for token in ('openai', 'anthropic', 'embedding', 'rerank'):
            self.assertNotIn(token, retrieval_source)


if __name__ == '__main__':
    unittest.main()
