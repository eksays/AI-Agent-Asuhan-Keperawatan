"""Phase 9 P9-A - explicit RAG schema migration CLI.

Mutations are allowed only through this operator-invoked CLI, never API startup.
The lexical core can run without pgvector. pgvector installation and embedding
schema require --enable-pgvector.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_env(env_file: str = '') -> None:
    candidate = Path(env_file) if env_file else ROOT / '.env'
    if candidate.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(str(candidate), override=False)
        except ImportError:
            pass


def _safe_bool(value: bool) -> str:
    return str(bool(value)).lower()


def _enabled(raw: str) -> bool:
    return (raw or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _validate_operator_mode() -> str:
    app_mode = os.environ.get('APP_MODE', '').strip().lower()
    rag_runtime_mode = os.environ.get('RAG_RUNTIME_MODE', '').strip().lower()
    if app_mode != 'clinical_sandbox':
        raise RuntimeError('app_mode_not_sandbox')
    if rag_runtime_mode != 'synthetic_corpus_test':
        raise RuntimeError('rag_runtime_mode_not_synthetic_corpus_test')
    if _enabled(os.environ.get('REGISTRY_ACTIVATION_ENABLED', 'false')):
        raise RuntimeError('registry_activation_enabled')
    if _enabled(os.environ.get('RAG_INDEX_ACTIVATION_ENABLED', 'false')):
        raise RuntimeError('rag_index_activation_enabled')
    if _enabled(os.environ.get('RAG_VECTOR_RETRIEVAL_ENABLED', 'false')):
        raise RuntimeError('rag_vector_retrieval_enabled')
    if _enabled(os.environ.get('RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED', 'false')):
        raise RuntimeError('rag_external_embedding_provider_enabled')
    admin_url = os.environ.get('REGISTRY_DATABASE_ADMIN_URL', '').strip()
    if not admin_url:
        raise RuntimeError('admin_url_missing')
    return admin_url


def main() -> int:
    parser = argparse.ArgumentParser(description='Run explicit P9-A RAG schema migrations.')
    parser.add_argument('--env-file', default='', help='Optional env file path. Contents are never printed.')
    parser.add_argument('--dry-run', action='store_true', help='List migration counts without mutating the database.')
    parser.add_argument('--enable-pgvector', action='store_true', help='Explicitly allow pgvector extension/table migrations.')
    parser.add_argument('--lock-timeout-sec', type=float, default=5.0, help='Bounded advisory-lock wait time.')
    args = parser.parse_args()

    _load_env(args.env_file)

    try:
        admin_url = _validate_operator_mode()
    except Exception as exc:
        print(f'configuration_error={type(exc).__name__}')
        print('migration_allowed=false')
        return 2

    from rag_migrations import CORE_MIGRATIONS, PGVECTOR_MIGRATIONS

    print('migration_allowed=true')
    print(f'core_migration_count={len(CORE_MIGRATIONS)}')
    print(f'pgvector_requested={_safe_bool(args.enable_pgvector)}')
    if args.dry_run:
        print('dry_run=true')
        print(f'optional_pgvector_migration_count={len(PGVECTOR_MIGRATIONS) if args.enable_pgvector else 0}')
        return 0

    try:
        import psycopg
        from rag_migrations import (
            acquire_advisory_lock,
            pgvector_available,
            pgvector_installed,
            release_advisory_lock,
            run_migrations,
        )

        with psycopg.connect(admin_url, connect_timeout=15, autocommit=False) as conn:
            acquire_advisory_lock(conn, timeout_sec=args.lock_timeout_sec)
            try:
                available = pgvector_available(conn)
                if args.enable_pgvector and not available:
                    print('pgvector_available=false')
                    print('migration_failed=pgvector_unavailable')
                    return 3
                applied = run_migrations(conn, include_pgvector=args.enable_pgvector)
                installed, version_present = pgvector_installed(conn)
            finally:
                release_advisory_lock(conn)

        print(f'pgvector_available={_safe_bool(available)}')
        print(f'pgvector_installed={_safe_bool(installed)}')
        print(f'pgvector_version_present={_safe_bool(version_present)}')
        print(f'applied_migration_count={len(applied)}')
        return 0
    except Exception as exc:
        print(f'migration_error={type(exc).__name__}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
