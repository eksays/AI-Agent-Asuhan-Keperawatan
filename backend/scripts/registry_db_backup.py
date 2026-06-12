import os
import json
import hashlib
import sys
from datetime import datetime

# To allow running directly or as module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from registry_store import RegistryStoreConfig, PostgresRegistryStore
from registry_runtime import _probe_health

def backup_metadata(output_path: str):
    config = RegistryStoreConfig(
        backend='postgres',
        database_url=os.environ.get('REGISTRY_DATABASE_ADMIN_URL') or os.environ.get('REGISTRY_DATABASE_URL', ''),
        activation_enabled=False
    )
    if not config.is_enabled:
        print("Database not configured")
        raise RuntimeError("Backup failed")

    store = PostgresRegistryStore(config)
    health = _probe_health(store.pool)
    if not health.get('healthy'):
        print("Database unhealthy")
        raise RuntimeError("Backup failed")

    backup_data = {
        'schema_version': health.get('schema_version'),
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'active_releases': [],
        'release_manifests': [],
        'release_approval_artifacts': [],
        'release_history': []
    }

    with store.pool.connection() as conn:
        with conn.cursor() as cur:
            # ONLY backup synthetic metadata for P8-F rehearsal
            cur.execute("SELECT framework, manifest_id, activated_at FROM active_releases WHERE framework LIKE 'SYN-%'")
            for row in cur.fetchall():
                backup_data['active_releases'].append({
                    'framework': row[0], 'manifest_id': row[1],
                    'activated_at': row[2].isoformat() if row[2] else None
                })

            cur.execute("SELECT manifest_id, framework, status, manifest_hash, release_version, created_at, activated_at FROM release_manifests WHERE manifest_id LIKE 'SYN-%'")
            for row in cur.fetchall():
                backup_data['release_manifests'].append({
                    'manifest_id': row[0], 'framework': row[1], 'status': row[2], 'manifest_hash': row[3],
                    'release_version': row[4], 'created_at': row[5].isoformat() if row[5] else None,
                    'activated_at': row[6].isoformat() if row[6] else None
                })

            cur.execute("SELECT approval_id, manifest_id, approver_id, approval_decision, manifest_hash_at_approval, approved_at, rationale FROM release_approval_artifacts WHERE manifest_id LIKE 'SYN-%'")
            for row in cur.fetchall():
                backup_data['release_approval_artifacts'].append({
                    'approval_id': row[0], 'manifest_id': row[1], 'approver_id': row[2],
                    'approval_decision': row[3], 'manifest_hash_at_approval': row[4],
                    'approved_at': row[5].isoformat() if row[5] else None,
                    'rationale': row[6]
                })

            cur.execute("SELECT framework, manifest_id, action, performed_by, notes, performed_at FROM release_history WHERE framework LIKE 'SYN-%'")
            for row in cur.fetchall():
                backup_data['release_history'].append({
                    'framework': row[0], 'manifest_id': row[1], 'action': row[2],
                    'performed_by': row[3], 'notes': row[4],
                    'performed_at': row[5].isoformat() if row[5] else None
                })

    # compute manifest hash
    raw = json.dumps(backup_data, sort_keys=True).encode('utf-8')
    backup_hash = hashlib.sha256(raw).hexdigest()

    final_output = {
        'hash': backup_hash,
        'data': backup_data
    }

    with open(output_path, 'w') as f:
        json.dump(final_output, f, indent=2)

    print(f"Synthetic metadata backup successful. Schema: {backup_data['schema_version']}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: registry_db_backup.py <output_file>")
        sys.exit(1)
    backup_metadata(sys.argv[1])
