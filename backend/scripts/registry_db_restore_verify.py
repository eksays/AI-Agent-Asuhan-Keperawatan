import os
import json
import hashlib
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from registry_store import RegistryStoreConfig, PostgresRegistryStore
from registry_runtime import _probe_health

def restore_verify(input_path: str, cleanup: bool = True):
    with open(input_path, 'r') as f:
        payload = json.load(f)

    if 'hash' not in payload or 'data' not in payload:
        print("Invalid backup format")
        raise RuntimeError("Restore failed")

    raw = json.dumps(payload['data'], sort_keys=True).encode('utf-8')
    computed = hashlib.sha256(raw).hexdigest()
    if computed != payload['hash']:
        print("Backup hash mismatch! Tampering detected.")
        raise RuntimeError("Restore failed")

    data = payload['data']
    schema = data.get('schema_version')
    if not schema:
        print("Backup missing schema version")
        raise RuntimeError("Restore failed")

    config = RegistryStoreConfig(
        backend='postgres',
        database_url=os.environ.get('REGISTRY_DATABASE_ADMIN_URL') or os.environ.get('REGISTRY_DATABASE_URL', ''),
        activation_enabled=False
    )
    if not config.is_enabled:
        print("Database not configured")
        raise RuntimeError("Restore failed")

    store = PostgresRegistryStore(config)
    health = _probe_health(store.pool)
    if not health.get('healthy'):
        print("Database unhealthy")
        raise RuntimeError("Restore failed")

    if health.get('schema_version') != schema:
        print(f"Schema mismatch. DB: {health.get('schema_version')}, Backup: {schema}")
        raise RuntimeError("Restore failed")

    print("Metadata hashes and schema verified successfully.")

    # Restore into database under isolated test prefix and verify constraints
    try:
        with store.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                # We prefix everything with RESTORE- so it doesn't collide
                r_prefix = "RESTORE-"

                for rm in data['release_manifests']:
                    # Reconstruct row
                    cur.execute("INSERT INTO release_manifests (manifest_id, framework, status, manifest_hash, release_version, created_at, activated_at) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                                (r_prefix + rm['manifest_id'], r_prefix + rm['framework'], rm['status'], rm['manifest_hash'], rm['release_version'], rm['created_at'], rm['activated_at']))

                for r in data['release_approval_artifacts']:
                    cur.execute("INSERT INTO release_approval_artifacts (approval_id, manifest_id, approver_id, approval_decision, manifest_hash_at_approval, approved_at, rationale) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                                (r_prefix + r['approval_id'], r_prefix + r['manifest_id'], r['approver_id'], r['approval_decision'], r['manifest_hash_at_approval'], r['approved_at'], r['rationale']))

                for r in data['release_history']:
                    cur.execute("INSERT INTO release_history (framework, manifest_id, action, performed_by, notes, performed_at) VALUES (%s, %s, %s, %s, %s, %s)",
                                (r_prefix + r['framework'], r_prefix + r['manifest_id'], r['action'], r['performed_by'], r['notes'], r['performed_at']))

                for r in data['active_releases']:
                    cur.execute("INSERT INTO active_releases (framework, manifest_id, activated_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                                (r_prefix + r['framework'], r_prefix + r['manifest_id'], r['activated_at']))

                print("Restore verified successfully.")

                if cleanup:
                    cur.execute("DELETE FROM active_releases WHERE framework LIKE 'RESTORE-%'")
                    cur.execute("DELETE FROM release_history WHERE framework LIKE 'RESTORE-%'")
                    cur.execute("DELETE FROM release_approval_artifacts WHERE manifest_id LIKE 'RESTORE-%'")
                    cur.execute("DELETE FROM release_manifests WHERE manifest_id LIKE 'RESTORE-%'")
                    print("Temporary synthetic restore artifacts cleaned up.")

                conn.commit()
    except Exception as e:
        print(f"Restore failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: registry_db_restore_verify.py <input_file> [--no-cleanup]")
        sys.exit(1)
    cleanup = '--no-cleanup' not in sys.argv
    restore_verify(sys.argv[1], cleanup)
