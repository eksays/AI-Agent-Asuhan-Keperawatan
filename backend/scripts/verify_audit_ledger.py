from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_ledger import GENESIS_MARKER, audit_key_is_weak, verify_ledger_file  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Verify a local HMAC-chained audit ledger segment.')
    parser.add_argument('--path', default=os.environ.get('AUDIT_LEDGER_PATH', str(ROOT / 'audit_ledger.jsonl')))
    parser.add_argument('--key', default=os.environ.get('AUDIT_LEDGER_HMAC_KEY', ''))
    parser.add_argument('--key-id', default=os.environ.get('AUDIT_LEDGER_KEY_ID', ''))
    parser.add_argument('--previous-record-mac', default=os.environ.get('AUDIT_LEDGER_PREVIOUS_MAC', GENESIS_MARKER))
    args = parser.parse_args(argv)

    if audit_key_is_weak(args.key):
        print(json.dumps({'ok': False, 'failure_code': 'missing_or_weak_key'}, sort_keys=True))
        return 2

    result = verify_ledger_file(
        args.path,
        args.key,
        previous_record_mac=args.previous_record_mac,
        key_id=args.key_id,
    )
    print(json.dumps(result.safe_summary(), sort_keys=True))
    return 0 if result.ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
