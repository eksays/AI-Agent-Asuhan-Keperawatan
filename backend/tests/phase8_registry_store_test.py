"""Phase 8 P8-A — Durable registry-store unit tests.

These tests run entirely without a real PostgreSQL/Neon connection.
They verify:
- Configuration defaults and fail-closed behavior
- Credential redaction safety
- Store protocol compliance
- Disabled store behavior
- Migration definitions integrity
- Phase 2/3 regression preservation
- No registry activation
- No real registry body loading
- No external provider calls
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure backend is importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class P8AConfigDefaultsTests(unittest.TestCase):
    """Verify registry store config defaults are fail-closed."""

    def test_default_backend_is_disabled(self):
        from config import load_config
        cfg = load_config({'APP_MODE': 'clinical_sandbox'})
        self.assertEqual(cfg.registry_store_backend, 'disabled')

    def test_default_activation_is_false(self):
        from config import load_config
        cfg = load_config({'APP_MODE': 'clinical_sandbox'})
        self.assertFalse(cfg.registry_activation_enabled)

    def test_default_runtime_mode_is_synthetic(self):
        from config import load_config
        cfg = load_config({'APP_MODE': 'clinical_sandbox'})
        self.assertEqual(cfg.registry_runtime_mode, 'synthetic_governance_test')

    def test_default_database_url_is_empty(self):
        from config import load_config
        cfg = load_config({'APP_MODE': 'clinical_sandbox'})
        self.assertEqual(cfg.registry_database_url, '')

    def test_default_admin_url_is_empty(self):
        from config import load_config
        cfg = load_config({'APP_MODE': 'clinical_sandbox'})
        self.assertEqual(cfg.registry_database_admin_url, '')

    def test_connect_timeout_bounded(self):
        from config import load_config
        cfg = load_config({
            'APP_MODE': 'clinical_sandbox',
            'REGISTRY_DATABASE_CONNECT_TIMEOUT_SEC': '999',
        })
        # Config module passes raw int; registry_store validates bounds
        self.assertIsInstance(cfg.registry_database_connect_timeout_sec, int)

    def test_max_retries_bounded(self):
        from config import load_config
        cfg = load_config({
            'APP_MODE': 'clinical_sandbox',
            'REGISTRY_DATABASE_MAX_RETRIES': '999',
        })
        self.assertIsInstance(cfg.registry_database_max_retries, int)


class P8AStoreConfigTests(unittest.TestCase):
    """Verify RegistryStoreConfig validation."""

    def test_disabled_backend_is_valid(self):
        from registry_store import load_registry_store_config
        cfg = load_registry_store_config(backend='disabled')
        self.assertFalse(cfg.is_enabled)
        self.assertEqual(cfg.backend, 'disabled')

    def test_postgres_without_url_raises(self):
        from registry_store import load_registry_store_config, RegistryStoreConfigError
        with self.assertRaises(RegistryStoreConfigError):
            load_registry_store_config(backend='postgres', database_url='')

    def test_invalid_backend_raises(self):
        from registry_store import load_registry_store_config, RegistryStoreConfigError
        with self.assertRaises(RegistryStoreConfigError):
            load_registry_store_config(backend='mysql')

    def test_invalid_runtime_mode_raises(self):
        from registry_store import load_registry_store_config, RegistryStoreConfigError
        with self.assertRaises(RegistryStoreConfigError):
            load_registry_store_config(
                backend='postgres',
                database_url='postgresql://x:y@host/db',
                runtime_mode='invalid_mode',
            )

    def test_valid_postgres_config(self):
        from registry_store import load_registry_store_config
        cfg = load_registry_store_config(
            backend='postgres',
            database_url='postgresql://user:pass@host/db',
            runtime_mode='synthetic_governance_test',
        )
        self.assertTrue(cfg.is_enabled)
        self.assertEqual(cfg.backend, 'postgres')

    def test_connect_timeout_clamped(self):
        from registry_store import load_registry_store_config
        cfg = load_registry_store_config(
            backend='disabled',
            connect_timeout_sec=999,
        )
        self.assertLessEqual(cfg.connect_timeout_sec, 60)

    def test_max_retries_clamped(self):
        from registry_store import load_registry_store_config
        cfg = load_registry_store_config(
            backend='disabled',
            max_retries=999,
        )
        self.assertLessEqual(cfg.max_retries, 10)

    def test_backoff_ms_clamped(self):
        from registry_store import load_registry_store_config
        cfg = load_registry_store_config(
            backend='disabled',
            retry_backoff_ms=99999,
        )
        self.assertLessEqual(cfg.retry_backoff_ms, 10_000)

    def test_activation_false_by_default(self):
        from registry_store import load_registry_store_config
        cfg = load_registry_store_config(backend='disabled')
        self.assertFalse(cfg.activation_enabled)


class P8ACredentialRedactionTests(unittest.TestCase):
    """Verify connection strings are never exposed."""

    def test_redact_password_in_url(self):
        from registry_store import redact_connection_string
        url = 'postgresql://user:s3cr3tP@ss@host.neon.tech/db'
        redacted = redact_connection_string(url)
        self.assertNotIn('s3cr3tP@ss', redacted)
        self.assertIn('[REDACTED]', redacted)

    def test_redact_hostname(self):
        from registry_store import redact_hostname
        url = 'postgresql://user:pass@ep-cool-name-123456.us-east-2.neon.tech/db'
        redacted = redact_hostname(url)
        self.assertNotIn('neon.tech', redacted)
        self.assertIn('[HOST]', redacted)

    def test_empty_url_safe(self):
        from registry_store import redact_connection_string, redact_hostname
        self.assertEqual(redact_connection_string(''), '')
        self.assertEqual(redact_hostname(''), '')

    def test_safe_diagnostic_no_credentials(self):
        from registry_store import load_registry_store_config
        cfg = load_registry_store_config(
            backend='postgres',
            database_url='postgresql://user:secret@host/db',
        )
        diag = cfg.safe_diagnostic
        self.assertNotIn('secret', str(diag))
        self.assertNotIn('postgresql://', str(diag))
        self.assertTrue(diag['has_database_url'])

    def test_url_never_in_safe_log(self):
        """URL must not appear in safe diagnostic output."""
        from registry_store import DisabledRegistryStore
        store = DisabledRegistryStore()
        diag = store.safe_diagnostic
        self.assertNotIn('postgresql://', str(diag))

    def test_password_never_in_safe_log(self):
        """Password must not appear in safe diagnostic output."""
        from registry_store import load_registry_store_config
        cfg = load_registry_store_config(
            backend='postgres',
            database_url='postgresql://user:mypassword@host/db',
        )
        diag_str = str(cfg.safe_diagnostic)
        self.assertNotIn('mypassword', diag_str)
        self.assertNotIn('postgresql://', diag_str)


class P8ADisabledStoreTests(unittest.TestCase):
    """Verify disabled store behavior."""

    def test_disabled_store_not_healthy(self):
        from registry_store import DisabledRegistryStore
        store = DisabledRegistryStore()
        self.assertFalse(store.is_healthy())

    def test_disabled_store_no_version(self):
        from registry_store import DisabledRegistryStore
        store = DisabledRegistryStore()
        self.assertIsNone(store.schema_version())

    def test_disabled_store_close_safe(self):
        from registry_store import DisabledRegistryStore
        store = DisabledRegistryStore()
        store.close()  # No-op, should not raise

    def test_disabled_store_diagnostic(self):
        from registry_store import DisabledRegistryStore
        store = DisabledRegistryStore()
        diag = store.safe_diagnostic
        self.assertEqual(diag['backend'], 'disabled')
        self.assertFalse(diag['activation_enabled'])


class P8AStoreFactoryTests(unittest.TestCase):
    """Verify create_registry_store factory."""

    def test_disabled_config_returns_disabled_store(self):
        from registry_store import load_registry_store_config, create_registry_store, DisabledRegistryStore
        cfg = load_registry_store_config(backend='disabled')
        store = create_registry_store(cfg)
        self.assertIsInstance(store, DisabledRegistryStore)

    def test_postgres_config_returns_postgres_store(self):
        from registry_store import load_registry_store_config, create_registry_store, PostgresRegistryStore
        cfg = load_registry_store_config(
            backend='postgres',
            database_url='postgresql://user:pass@host/db',
        )
        store = create_registry_store(cfg)
        self.assertIsInstance(store, PostgresRegistryStore)


class P8AMigrationDefinitionTests(unittest.TestCase):
    """Verify migration definitions are well-formed."""

    def test_all_migrations_have_versions(self):
        from registry_migrations import ALL_MIGRATIONS
        for m in ALL_MIGRATIONS:
            self.assertTrue(m.version, f'Migration missing version: {m}')
            self.assertTrue(m.description, f'Migration missing description: {m}')
            self.assertTrue(m.sql.strip(), f'Migration missing SQL: {m}')

    def test_migrations_are_ordered(self):
        from registry_migrations import ALL_MIGRATIONS
        versions = [m.version for m in ALL_MIGRATIONS]
        self.assertEqual(versions, sorted(versions))

    def test_migration_count(self):
        from registry_migrations import ALL_MIGRATIONS
        self.assertEqual(len(ALL_MIGRATIONS), 4)

    def test_v001_creates_schema_migrations(self):
        from registry_migrations import MIGRATION_V001_BOOTSTRAP
        self.assertIn('schema_migrations', MIGRATION_V001_BOOTSTRAP.sql)
        self.assertIn('PRIMARY KEY', MIGRATION_V001_BOOTSTRAP.sql)

    def test_v002_creates_core_tables(self):
        from registry_migrations import MIGRATION_V002_CORE_TABLES
        for table in ('registry_sources', 'registry_entries', 'entry_provenance'):
            self.assertIn(table, MIGRATION_V002_CORE_TABLES.sql)

    def test_v003_creates_review_tables(self):
        from registry_migrations import MIGRATION_V003_REVIEW_APPROVAL
        for table in ('review_queue', 'approval_artifacts'):
            self.assertIn(table, MIGRATION_V003_REVIEW_APPROVAL.sql)

    def test_v004_creates_release_tables(self):
        from registry_migrations import MIGRATION_V004_RELEASE_TABLES
        for table in ('release_manifests', 'release_manifest_entries', 'active_releases', 'release_history'):
            self.assertIn(table, MIGRATION_V004_RELEASE_TABLES.sql)

    def test_v002_has_foreign_keys(self):
        from registry_migrations import MIGRATION_V002_CORE_TABLES
        self.assertIn('REFERENCES', MIGRATION_V002_CORE_TABLES.sql)

    def test_v002_has_unique_constraints(self):
        from registry_migrations import MIGRATION_V002_CORE_TABLES
        self.assertIn('UNIQUE', MIGRATION_V002_CORE_TABLES.sql)

    def test_v002_has_check_constraints(self):
        from registry_migrations import MIGRATION_V002_CORE_TABLES
        self.assertIn('CHECK', MIGRATION_V002_CORE_TABLES.sql)

    def test_v002_lifecycle_states(self):
        from registry_migrations import MIGRATION_V002_CORE_TABLES
        for state in ('quarantined', 'pending_review', 'approved', 'rejected', 'deprecated'):
            self.assertIn(state, MIGRATION_V002_CORE_TABLES.sql)

    def test_v002_registry_families(self):
        from registry_migrations import MIGRATION_V002_CORE_TABLES
        for family in ('SDKI', 'SLKI', 'SIKI', 'NANDA', 'NOC', 'NIC'):
            self.assertIn(family, MIGRATION_V002_CORE_TABLES.sql)

    def test_no_real_registry_body_in_migrations(self):
        """Migration SQL must not contain real registry content."""
        from registry_migrations import ALL_MIGRATIONS
        forbidden = ['Bersihan Jalan Napas', 'Ketidakmampuan', 'Gangguan', 'PPNI']
        for m in ALL_MIGRATIONS:
            for word in forbidden:
                self.assertNotIn(word, m.sql, f'{m.version} contains forbidden registry body text: {word}')


class P8ANoActivationTests(unittest.TestCase):
    """Verify P8-A does not activate registry grounding."""

    def test_clinical_registry_unavailable_by_default(self):
        from clinical_registry import ClinicalRegistry
        reg = ClinicalRegistry.unavailable()
        self.assertFalse(reg.approved_available('SDKI'))
        self.assertFalse(reg.approved_available('SLKI'))
        self.assertFalse(reg.approved_available('SIKI'))

    def test_config_activation_false_by_default(self):
        from config import load_config
        cfg = load_config({'APP_MODE': 'clinical_sandbox'})
        self.assertFalse(cfg.registry_activation_enabled)

    def test_disabled_store_not_healthy(self):
        from registry_store import DisabledRegistryStore
        store = DisabledRegistryStore()
        self.assertFalse(store.is_healthy())


class P8ANoDataTerstrukturLoadingTests(unittest.TestCase):
    """Verify data_terstruktur is never loaded by P8-A code."""

    def test_registry_store_no_file_import(self):
        import registry_store
        source = open(registry_store.__file__, 'r', encoding='utf-8').read()
        self.assertNotIn('data_terstruktur', source)

    def test_registry_migrations_no_file_import(self):
        import registry_migrations
        source = open(registry_migrations.__file__, 'r', encoding='utf-8').read()
        self.assertNotIn('data_terstruktur', source)

    def test_registry_store_no_sdki_reference(self):
        """Store code must not reference SDKI bodies."""
        import registry_store
        source = open(registry_store.__file__, 'r', encoding='utf-8').read()
        self.assertNotIn('Bersihan', source)
        self.assertNotIn('Ketidakmampuan', source)


class P8AEnvExampleTests(unittest.TestCase):
    """Verify backend/.env.example is placeholder-only."""

    def setUp(self):
        self.env_example_path = ROOT / '.env.example'
        if not self.env_example_path.exists():
            self.skipTest('backend/.env.example not found')
        self.content = self.env_example_path.read_text(encoding='utf-8')

    def test_no_real_connection_string(self):
        self.assertNotIn('neon.tech', self.content)
        self.assertNotIn('ep-', self.content)

    def test_no_real_password(self):
        # Placeholders use angle brackets
        import re
        url_lines = [l for l in self.content.splitlines() if 'DATABASE_URL=' in l and not l.strip().startswith('#')]
        for line in url_lines:
            value = line.split('=', 1)[1] if '=' in line else ''
            self.assertIn('<', value, f'Expected placeholder in: {line}')

    def test_activation_false(self):
        self.assertIn('REGISTRY_ACTIVATION_ENABLED=false', self.content)

    def test_store_backend_disabled(self):
        self.assertIn('REGISTRY_STORE_BACKEND=disabled', self.content)

    def test_contains_required_variables(self):
        required = [
            'APP_MODE', 'CDSS_API_KEYS', 'CDSS_SECRET_KEY',
            'REGISTRY_STORE_BACKEND', 'REGISTRY_DATABASE_URL',
            'FEATURE_EXTERNAL_LLM', 'AUDIT_LEDGER_HMAC_KEY',
            'SESSION_TTL_SEC', 'MFA_FAILURE_LIMIT', 'RATE_LIMIT_WINDOW_SEC',
            'UPLOAD_MAX_BYTES', 'TRUSTED_PROXY_HOSTS', 'FRONTEND_ORIGINS',
        ]
        for var in required:
            self.assertIn(var, self.content, f'Missing variable: {var}')


class P8AEnvIgnoredTests(unittest.TestCase):
    """Verify backend/.env is properly ignored by Git."""

    def test_backend_env_ignored(self):
        import subprocess
        result = subprocess.run(
            ['git', 'check-ignore', '-v', 'backend/.env'],
            capture_output=True, text=True, cwd=str(ROOT.parent),
        )
        self.assertEqual(result.returncode, 0, 'backend/.env should be ignored by git')

    def test_backend_env_example_not_ignored(self):
        import subprocess
        result = subprocess.run(
            ['git', 'add', '--dry-run', 'backend/.env.example'],
            capture_output=True, text=True, cwd=str(ROOT.parent),
        )
        self.assertEqual(result.returncode, 0, 'backend/.env.example should be trackable by git')


class P8ANoExternalCallTests(unittest.TestCase):
    """Verify P8-A code makes no external provider calls."""

    def test_registry_store_no_http_calls(self):
        import registry_store
        source = open(registry_store.__file__, 'r', encoding='utf-8').read()
        self.assertNotIn('requests.', source)
        self.assertNotIn('httpx.', source)
        self.assertNotIn('urllib.request', source)
        self.assertNotIn('aiohttp', source)

    def test_registry_migrations_no_http_calls(self):
        import registry_migrations
        source = open(registry_migrations.__file__, 'r', encoding='utf-8').read()
        self.assertNotIn('requests.', source)
        self.assertNotIn('httpx.', source)


class P8ANoConnectionStringCommittedTests(unittest.TestCase):
    """Verify no connection string credentials are tracked in the repository."""

    def test_env_example_no_credentials(self):
        env_path = ROOT / '.env.example'
        if not env_path.exists():
            self.skipTest('backend/.env.example not found')
        content = env_path.read_text(encoding='utf-8')
        # Must not contain real connection strings
        self.assertNotRegex(content, r'postgresql://\w+:\w+@\w+')


if __name__ == '__main__':
    unittest.main()
