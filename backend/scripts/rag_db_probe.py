"""Phase 9 P9-A - read-only RAG database readiness probe.

This script prints safe booleans only. It never installs extensions, runs
migrations, prints connection details, or activates retrieval/registry data.
"""
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
            load_dotenv(str(candidate), override=True)
        except ImportError:
            pass


def _enabled(raw: str) -> bool:
    return (raw or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _relation_exists(conn, relation_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute('SELECT to_regclass(%s)', (relation_name,))
        row = cur.fetchone()
    return bool(row and row[0])


def _index_exists(conn, index_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = %s)',
            (index_name,),
        )
        row = cur.fetchone()
    return bool(row and row[0])


def main() -> int:
    _load_env()
    admin_url = os.environ.get('REGISTRY_DATABASE_ADMIN_URL', '').strip()
    runtime_url = os.environ.get('REGISTRY_DATABASE_URL', '').strip()
    activation_enabled = _enabled(os.environ.get('REGISTRY_ACTIVATION_ENABLED', 'false'))
    rag_runtime_mode = (os.environ.get('RAG_RUNTIME_MODE') or 'disabled').strip().lower()

    print(f'admin_url_present={str(bool(admin_url)).lower()}')
    print(f'runtime_url_present={str(bool(runtime_url)).lower()}')
    print(f'registry_activation_enabled={str(activation_enabled).lower()}')
    print(f'rag_runtime_mode={rag_runtime_mode}')

    if activation_enabled:
        print('configuration_error=registry_activation_enabled')
        return 2

    url = admin_url or runtime_url
    if not url:
        print('pgvector_available=false')
        print('pgvector_installed=false')
        print('pgvector_version_present=false')
        print('rag_store_schema_ready=false')
        print('rag_lexical_schema_ready=false')
        print('rag_vector_schema_ready=false')
        return 0

    try:
        import psycopg
        from rag_migrations import pgvector_available, pgvector_installed

        with psycopg.connect(url, connect_timeout=15, autocommit=True) as conn:
            available = pgvector_available(conn)
            installed, version_present = pgvector_installed(conn)
            store_ready = _relation_exists(conn, 'rag_schema_migrations')
            lexical_ready = (
                _relation_exists(conn, 'rag_chunks')
                and _relation_exists(conn, 'rag_index_release_manifests')
                and _index_exists(conn, 'idx_rag_chunks_fts')
            )
            vector_ready = installed and _relation_exists(conn, 'rag_chunk_embeddings')
        print(f'pgvector_available={str(available).lower()}')
        print(f'pgvector_installed={str(installed).lower()}')
        print(f'pgvector_version_present={str(version_present).lower()}')
        print(f'rag_store_schema_ready={str(store_ready).lower()}')
        print(f'rag_lexical_schema_ready={str(lexical_ready).lower()}')
        print(f'rag_vector_schema_ready={str(vector_ready).lower()}')
        return 0
    except Exception:
        print('pgvector_available=false')
        print('pgvector_installed=false')
        print('pgvector_version_present=false')
        print('rag_store_schema_ready=false')
        print('rag_lexical_schema_ready=false')
        print('rag_vector_schema_ready=false')
        print('probe_error=true')
        return 1


if __name__ == '__main__':
    sys.exit(main())
