from __future__ import annotations

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


def _require_operator_env() -> str:
    if os.environ.get('APP_MODE', '').strip().lower() != 'clinical_sandbox':
        raise RuntimeError('app_mode_not_sandbox')
    if os.environ.get('RAG_RUNTIME_MODE', '').strip().lower() != 'synthetic_corpus_test':
        raise RuntimeError('rag_runtime_mode_not_synthetic')
    if _enabled('REGISTRY_ACTIVATION_ENABLED'):
        raise RuntimeError('registry_activation_enabled')
    for name in ('RAG_STORE_ENABLED', 'RAG_INGESTION_ENABLED', 'RAG_LEXICAL_RETRIEVAL_ENABLED', 'RAG_INDEX_ACTIVATION_ENABLED'):
        if not _enabled(name):
            raise RuntimeError('rag_required_flag_disabled')
    for name in ('RAG_VECTOR_RETRIEVAL_ENABLED', 'RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED'):
        if _enabled(name):
            raise RuntimeError('rag_forbidden_flag_enabled')
    admin_url = os.environ.get('REGISTRY_DATABASE_ADMIN_URL', '').strip()
    if not admin_url:
        raise RuntimeError('admin_url_missing')
    return admin_url


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, '') or default)
    except ValueError:
        return default


def main() -> int:
    _load_env()
    try:
        admin_url = _require_operator_env()
        import psycopg
        from rag_fixture_loader import default_fixture_root
        from rag_ingestion_service import SyntheticIngestionConfig, ingest_synthetic_fixtures
        from rag_migrations import acquire_advisory_lock, release_advisory_lock

        fixture_root_raw = os.environ.get('RAG_SYNTHETIC_FIXTURE_ROOT', '').strip()
        fixture_root = Path(fixture_root_raw) if fixture_root_raw else default_fixture_root()
        with psycopg.connect(admin_url, connect_timeout=15, autocommit=False) as conn:
            acquire_advisory_lock(conn, timeout_sec=5.0)
            try:
                result = ingest_synthetic_fixtures(
                    conn,
                    SyntheticIngestionConfig(
                        fixture_root=fixture_root,
                        max_document_chars=_int_env('RAG_MAX_DOCUMENT_CHARS', 12000),
                        max_staging_chunks=_int_env('RAG_MAX_STAGING_CHUNKS', 200),
                        chunk_target_words=_int_env('RAG_CHUNK_TARGET_WORDS', 90),
                        chunk_overlap_words=_int_env('RAG_CHUNK_OVERLAP_WORDS', 12),
                        staging_ttl_seconds=_int_env('RAG_STAGING_TTL_SECONDS', 3600),
                    ),
                )
            finally:
                release_advisory_lock(conn)
        for key, value in result.as_safe_dict().items():
            print(f'{key}={value}')
        return 0
    except Exception as exc:
        print(f'ingestion_status=failed')
        print(f'error_type={type(exc).__name__}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
