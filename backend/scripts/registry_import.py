from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from registry_governance import dry_run_import, manifest_only  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run clinical registry governance import.")
    parser.add_argument("source", type=Path, help="Registry JSON source to inspect read-only.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode is always enabled by default.")
    parser.add_argument("--quarantine-report", action="store_true", help="Emit safe quarantine reason counts.")
    parser.add_argument("--manifest-only", action="store_true", help="Emit safe manifest metadata only.")
    parser.add_argument("--dataset-name", default=None, help="Optional dataset label for the report.")
    parser.add_argument("--framework", default=None, help="Optional source framework label for metadata only.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = dry_run_import(args.source, dataset_name=args.dataset_name, source_framework=args.framework)
    output = manifest_only(report) if args.manifest_only else report.to_safe_dict()
    if args.quarantine_report:
        output["quarantine_reason_counts"] = dict(sorted(report.reason_counts.items()))
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
