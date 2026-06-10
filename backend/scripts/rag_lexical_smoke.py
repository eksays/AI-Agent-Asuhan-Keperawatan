from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    candidate = ROOT / '.env'
    if candidate.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(str(candidate), override=False)
        except ImportError:
            pass


def _enabled(name: str) -> bool:
    return os.environ.get(name, '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _require_query_env() -> str:
    if os.environ.get('APP_MODE', '').strip().lower() != 'clinical_sandbox':
        raise RuntimeError('app_mode_not_sandbox')
    if os.environ.get('RAG_RUNTIME_MODE', '').strip().lower() != 'synthetic_corpus_test':
        raise RuntimeError('rag_runtime_mode_not_synthetic')
    if _enabled('REGISTRY_ACTIVATION_ENABLED') or _enabled('RAG_VECTOR_RETRIEVAL_ENABLED') or _enabled('RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED'):
        raise RuntimeError('forbidden_activation_flag')
    if not _enabled('RAG_LEXICAL_RETRIEVAL_ENABLED'):
        raise RuntimeError('lexical_retrieval_disabled')
    admin_url = os.environ.get('REGISTRY_DATABASE_ADMIN_URL', '').strip()
    if not admin_url:
        raise RuntimeError('admin_url_missing')
    return admin_url


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, '') or default)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, '') or default)
    except ValueError:
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description='Run a safe synthetic lexical RAG smoke query.')
    parser.add_argument('--query', required=True, help='Bounded synthetic test query. It is never printed or persisted.')
    args = parser.parse_args()
    _load_env()
    try:
        admin_url = _require_query_env()
        import psycopg
        from rag_lexical_retrieval import LexicalRetrievalConfig, retrieve_lexical

        with psycopg.connect(admin_url, connect_timeout=15, autocommit=False) as conn:
            outcome = retrieve_lexical(
                conn,
                args.query,
                LexicalRetrievalConfig(
                    max_results=_int_env('RAG_MAX_RESULTS', 5),
                    max_excerpt_chars=_int_env('RAG_MAX_EXCERPT_CHARS', 360),
                    min_lexical_rank=_float_env('RAG_MIN_LEXICAL_RANK', 0.01),
                    max_selected_chunk_ids=_int_env('RAG_MAX_SELECTED_CHUNK_IDS', 8),
                ),
            )
        safe = outcome.as_safe_dict()
        print(f'retrieved={safe["retrieved"]}')
        print(f'release_id={safe["release_id"]}')
        print(f'citation_count={len(safe["citations"])}')
        print(f'abstention_reason={safe["abstention"]["reason_code"] if safe["abstention"] else ""}')
        print(f'telemetry_event_id={safe["telemetry_event_id"]}')
        return 0
    except Exception as exc:
        print('retrieved=false')
        print(f'error_type={type(exc).__name__}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
