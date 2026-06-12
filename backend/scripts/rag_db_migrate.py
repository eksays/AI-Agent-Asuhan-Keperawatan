"""Phase 9 P9-C - explicit RAG schema migration CLI.

Mutations are allowed only through this operator-invoked CLI, never API startup.
Core lexical migrations, pgvector extension installation, and optional vector
schema application are kept as separate operator decisions.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_ALLOWED_FAILURE_REASON_CODES = {
    'admin_url_missing',
    'app_mode_not_sandbox',
    'isolated_test_database_not_confirmed',
    'migration_failed_safely',
    'pgvector_not_installed',
    'pgvector_unavailable',
    'rag_external_embedding_provider_enabled',
    'rag_index_activation_enabled',
    'rag_runtime_mode_not_synthetic_corpus_test',
    'rag_vector_retrieval_enabled',
    'registry_activation_enabled',
    'vector_schema_not_ready',
}


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


def _safe_reason_code(raw: str) -> str:
    return raw if raw in _ALLOWED_FAILURE_REASON_CODES else 'migration_failed_safely'


def _bounded_lock_timeout(raw_timeout: float) -> float:
    try:
        timeout = float(raw_timeout)
    except (TypeError, ValueError):
        return 5.0
    return min(max(timeout, 0.1), 30.0)


def _validate_operator_mode() -> str:
    app_mode = os.environ.get('APP_MODE', '').strip().lower()
    rag_runtime_mode = os.environ.get('RAG_RUNTIME_MODE', '').strip().lower()
    if app_mode != 'clinical_sandbox':
        raise RuntimeError('app_mode_not_sandbox')
    if rag_runtime_mode != 'synthetic_corpus_test':
        raise RuntimeError('rag_runtime_mode_not_synthetic_corpus_test')
    if _enabled(os.environ.get('REGISTRY_ACTIVATION_ENABLED', 'false')):
        raise RuntimeError('registry_activation_enabled')
    if _enabled(os.environ.get('RAG_VECTOR_RETRIEVAL_ENABLED', 'false')):
        raise RuntimeError('rag_vector_retrieval_enabled')
    if _enabled(os.environ.get('RAG_EXTERNAL_EMBEDDING_PROVIDER_ENABLED', 'false')):
        raise RuntimeError('rag_external_embedding_provider_enabled')
    if not _enabled(os.environ.get('RAG_ISOLATED_TEST_DATABASE_CONFIRMED', 'false')):
        raise RuntimeError('isolated_test_database_not_confirmed')
    admin_url = os.environ.get('REGISTRY_DATABASE_ADMIN_URL', '').strip()
    if not admin_url:
        raise RuntimeError('admin_url_missing')
    return admin_url


def _operation_name(args: argparse.Namespace) -> str:
    if args.enable_pgvector:
        return 'enable_pgvector'
    if args.apply_vector_schema:
        return 'apply_vector_schema'
    return 'core_migrations'


def _vector_schema_ready(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", ('rag_chunk_embeddings',))
        row = cur.fetchone()
    return bool(row and row[0])


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Run explicit P9-C RAG migrations. Mutating actions are mutually exclusive.'
    )
    parser.add_argument('--env-file', default='', help='Optional env file path. Contents are never printed.')
    parser.add_argument('--dry-run', action='store_true', help='List migration counts without mutating the database.')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--enable-pgvector', action='store_true', help='Install the pgvector extension only.')
    actions.add_argument('--apply-vector-schema', action='store_true', help='Apply optional vector schema migrations only.')
    parser.add_argument('--lock-timeout-sec', type=float, default=5.0, help='Bounded advisory-lock wait time.')
    args = parser.parse_args()
    operation = _operation_name(args)
    lock_timeout_sec = _bounded_lock_timeout(args.lock_timeout_sec)

    _load_env(args.env_file)

    try:
        admin_url = _validate_operator_mode()
    except RuntimeError as error:
        failure_reason_code = _safe_reason_code(str(error))
        print(f'operation={operation}')
        print('operation_status=blocked')
        print(f'registry_activation_enabled={_safe_bool(_enabled(os.environ.get("REGISTRY_ACTIVATION_ENABLED", "false")))}')
        print(f'vector_retrieval_enabled={_safe_bool(_enabled(os.environ.get("RAG_VECTOR_RETRIEVAL_ENABLED", "false")))}')
        print(f'failure_reason_code={failure_reason_code}')
        return 2

    from rag_migrations import CORE_MIGRATIONS, PGVECTOR_EXTENSION_MIGRATIONS, PGVECTOR_SCHEMA_MIGRATIONS

    print(f'operation={operation}')
    print(f'registry_activation_enabled={_safe_bool(_enabled(os.environ.get("REGISTRY_ACTIVATION_ENABLED", "false")))}')
    print(f'vector_retrieval_enabled={_safe_bool(_enabled(os.environ.get("RAG_VECTOR_RETRIEVAL_ENABLED", "false")))}')
    print(f'core_migration_count={len(CORE_MIGRATIONS)}')
    print(f'pgvector_requested={_safe_bool(args.enable_pgvector)}')
    print(f'vector_schema_requested={_safe_bool(args.apply_vector_schema)}')
    if args.dry_run:
        print('operation_status=dry_run')
        print('dry_run=true')
        print(f'pgvector_extension_migration_count={len(PGVECTOR_EXTENSION_MIGRATIONS) if args.enable_pgvector else 0}')
        print(f'vector_schema_migration_count={len(PGVECTOR_SCHEMA_MIGRATIONS) if args.apply_vector_schema else 0}')
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
            locked = False
            try:
                acquire_advisory_lock(conn, timeout_sec=lock_timeout_sec)
                locked = True
                available = pgvector_available(conn)
                installed, version_present = pgvector_installed(conn)
                vector_schema_ready = _vector_schema_ready(conn)
                vector_schema_applied = False

                if args.enable_pgvector:
                    if not available:
                        print('operation_status=blocked')
                        print('pgvector_available=false')
                        print(f'pgvector_installed={_safe_bool(installed)}')
                        print(f'pgvector_version_present={_safe_bool(version_present)}')
                        print(f'vector_schema_ready={_safe_bool(vector_schema_ready)}')
                        print('failure_reason_code=pgvector_unavailable')
                        return 3
                    applied = run_migrations(
                        conn,
                        include_pgvector_extension=True,
                        include_vector_schema=False,
                    )
                    installed, version_present = pgvector_installed(conn)
                    vector_schema_ready = _vector_schema_ready(conn)
                elif args.apply_vector_schema:
                    if not installed:
                        print('operation_status=blocked')
                        print(f'pgvector_available={_safe_bool(available)}')
                        print('pgvector_installed=false')
                        print(f'pgvector_version_present={_safe_bool(version_present)}')
                        print(f'vector_schema_ready={_safe_bool(vector_schema_ready)}')
                        print('failure_reason_code=pgvector_not_installed')
                        return 3
                    applied = run_migrations(
                        conn,
                        include_pgvector_extension=False,
                        include_vector_schema=True,
                    )
                    vector_schema_ready = _vector_schema_ready(conn)
                    vector_schema_ids = {migration.migration_id for migration in PGVECTOR_SCHEMA_MIGRATIONS}
                    vector_schema_applied = any(migration_id in vector_schema_ids for migration_id in applied)
                else:
                    applied = run_migrations(
                        conn,
                        include_pgvector_extension=False,
                        include_vector_schema=False,
                    )
                    installed, version_present = pgvector_installed(conn)
                    vector_schema_ready = _vector_schema_ready(conn)

                if args.apply_vector_schema and not vector_schema_ready:
                    print('operation_status=failed')
                    print(f'pgvector_available={_safe_bool(available)}')
                    print(f'pgvector_installed={_safe_bool(installed)}')
                    print(f'pgvector_version_present={_safe_bool(version_present)}')
                    print('vector_schema_ready=false')
                    print('failure_reason_code=vector_schema_not_ready')
                    return 4
            finally:
                if locked:
                    release_advisory_lock(conn)

        print('operation_status=succeeded')
        print(f'pgvector_available={_safe_bool(available)}')
        print(f'pgvector_installed={_safe_bool(installed)}')
        print(f'pgvector_version_present={_safe_bool(version_present)}')
        print(f'vector_schema_applied={_safe_bool(vector_schema_applied)}')
        print(f'vector_schema_ready={_safe_bool(vector_schema_ready)}')
        print(f'applied_migration_count={len(applied)}')
        return 0
    except Exception:
        print('operation_status=failed')
        print('failure_reason_code=migration_failed_safely')
        return 1


if __name__ == '__main__':
    sys.exit(main())
