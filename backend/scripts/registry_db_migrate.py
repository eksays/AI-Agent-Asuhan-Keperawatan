"""Phase 8 P8-A — Registry database migration CLI.

Usage:
    python -m backend.scripts.registry_db_migrate [--env-file PATH]

Loads configuration from environment variables (optionally from a .env file),
validates the registry store configuration, and runs pending schema migrations.

Safety:
- Never logs database credentials.
- Never imports real registry data.
- Never activates registry grounding.
- Uses standard PostgreSQL interfaces only.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description='Run registry store schema migrations.')
    parser.add_argument(
        '--env-file',
        default='',
        help='Path to .env file (optional). Defaults to backend/.env if it exists.',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show pending migrations without applying them.',
    )
    args = parser.parse_args()

    # Load environment from .env file if available
    env_file = args.env_file
    if not env_file:
        candidate = ROOT / '.env'
        if candidate.exists():
            env_file = str(candidate)
    if env_file:
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=True)
            print(f'[migrate] loaded env from: {os.path.basename(env_file)}')
        except ImportError:
            print('[migrate] python-dotenv not available; using system environment.')

    # Load and validate config
    from registry_store import (
        RegistryStoreConfig,
        RegistryStoreConfigError,
        load_registry_store_config,
        redact_hostname,
    )

    try:
        config = load_registry_store_config(
            backend=os.environ.get('REGISTRY_STORE_BACKEND', 'disabled'),
            database_url=os.environ.get('REGISTRY_DATABASE_ADMIN_URL', '')
                or os.environ.get('REGISTRY_DATABASE_URL', ''),
            admin_url=os.environ.get('REGISTRY_DATABASE_ADMIN_URL', ''),
            runtime_mode=os.environ.get('REGISTRY_RUNTIME_MODE', 'synthetic_governance_test'),
            activation_enabled=False,  # Never enable activation during migration
            connect_timeout_sec=int(os.environ.get('REGISTRY_DATABASE_CONNECT_TIMEOUT_SEC', '15')),
            max_retries=int(os.environ.get('REGISTRY_DATABASE_MAX_RETRIES', '3')),
            retry_backoff_ms=int(os.environ.get('REGISTRY_DATABASE_RETRY_BACKOFF_MS', '750')),
        )
    except (RegistryStoreConfigError, ValueError) as exc:
        print(f'[migrate] config error: {exc}', file=sys.stderr)
        return 1

    if config.backend == 'disabled':
        print('[migrate] REGISTRY_STORE_BACKEND=disabled. No migrations to run.')
        return 0

    print(f'[migrate] backend: {config.backend}')
    print(f'[migrate] runtime_mode: {config.runtime_mode}')
    print(f'[migrate] activation_enabled: {config.activation_enabled}')
    print(f'[migrate] URL provided: {"yes" if config.database_url else "no"}')

    if args.dry_run:
        from registry_migrations import ALL_MIGRATIONS
        print(f'[migrate] dry-run: {len(ALL_MIGRATIONS)} total migrations defined.')
        for m in ALL_MIGRATIONS:
            print(f'  {m.version}: {m.description}')
        return 0

    # Create store and run migrations
    from registry_store import PostgresRegistryStore
    from registry_migrations import run_migrations

    store = PostgresRegistryStore(config)
    try:
        applied = run_migrations(store)
        if applied:
            print(f'[migrate] applied {len(applied)} migration(s): {", ".join(applied)}')
        else:
            print('[migrate] schema is up to date; no new migrations.')
        version = store.schema_version()
        print(f'[migrate] current schema version: {version}')
        return 0
    except Exception as exc:
        safe_msg = redact_hostname(str(exc)) if str(exc) else type(exc).__name__
        print(f'[migrate] migration failed: {type(exc).__name__}: {safe_msg}', file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == '__main__':
    sys.exit(main())
