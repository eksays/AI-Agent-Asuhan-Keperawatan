import subprocess
import sys
import re

FORBIDDEN_PATHS = [
    re.compile(r'^backend/\.env$'),
    re.compile(r'^\.env$'),
    re.compile(r'^\.env\..+$'),
    re.compile(r'^\.cdss_key$'),
    re.compile(r'^\.director_totp$'),
    re.compile(r'^backend/data_terstruktur/.*'),
    re.compile(r'^backend/audit_ledger\.jsonl$'),
    re.compile(r'.*\.dump$'),
    re.compile(r'.*\.backup$'),
    re.compile(r'.*\.sql\.gz$'),
    re.compile(r'^frontend/\.next/.*'),
    re.compile(r'^frontend/node_modules/.*')
]

ALLOWLIST_PATHS = [
    re.compile(r'^backend/\.env\.example$')
]

def get_tracked_files():
    try:
        result = subprocess.run(['git', 'ls-files'], capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n')
    except subprocess.CalledProcessError:
        print("Not a git repository or git error.")
        return []

def scan():
    files = get_tracked_files()
    violations = []

    for f in files:
        if not f: continue

        # Check allowlist first
        if any(p.match(f) for p in ALLOWLIST_PATHS):
            continue

        # Check forbidden
        for p in FORBIDDEN_PATHS:
            if p.match(f):
                violations.append(f)
                break

    if violations:
        print("ERROR: Forbidden tracked files detected:")
        for v in violations:
            print(f" - {v}")
        sys.exit(1)

    print("Artifact scan passed. No forbidden tracked files.")

if __name__ == '__main__':
    scan()
