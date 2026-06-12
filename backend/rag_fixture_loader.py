from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class RagFixtureError(ValueError):
    pass


PHI_CANARY_PATTERNS = (
    re.compile(r'PHI_CANARY', re.IGNORECASE),
    re.compile(r'MRN_CANARY', re.IGNORECASE),
    re.compile(r'CONTACT_CANARY', re.IGNORECASE),
    re.compile(r'\b\d{16}\b'),
)


@dataclass(frozen=True)
class SyntheticFixture:
    case_id: str
    title: str
    relative_path: str
    content: str
    synthetic_only: bool
    authority: bool
    clinical_use_allowed: bool
    provenance_status: str
    license_status: str
    review_status: str
    language_code: str = 'id'


def default_fixture_root() -> Path:
    return Path(__file__).resolve().parent / 'tests' / 'fixtures' / 'rag_synthetic'


def _safe_case_id(value: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,80}', value or ''):
        raise RagFixtureError('unsafe_case_id')
    return value


def _validate_metadata(entry: dict) -> None:
    if entry.get('synthetic_only') is not True:
        raise RagFixtureError('synthetic_only_required')
    if entry.get('authority') is not False:
        raise RagFixtureError('authority_must_be_false')
    if entry.get('clinical_use_allowed') is not False:
        raise RagFixtureError('clinical_use_not_allowed')
    if entry.get('provenance_status') != 'synthetic_generated':
        raise RagFixtureError('invalid_provenance_status')
    if entry.get('license_status') != 'synthetic_only':
        raise RagFixtureError('invalid_license_status')
    if entry.get('review_status') != 'approved_for_synthetic_test':
        raise RagFixtureError('invalid_review_status')


def _resolve_fixture_path(root: Path, relative_path: str) -> Path:
    rel = Path(relative_path)
    if rel.is_absolute() or '..' in rel.parts:
        raise RagFixtureError('unsafe_fixture_path')
    base = root.resolve()
    candidate = (base / rel).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise RagFixtureError('fixture_path_escape') from exc
    if candidate.is_symlink():
        raise RagFixtureError('fixture_symlink_rejected')
    return candidate


def _reject_canaries(text: str) -> None:
    for pattern in PHI_CANARY_PATTERNS:
        if pattern.search(text or ''):
            raise RagFixtureError('phi_canary_rejected')


def load_manifest(root: Path | None = None, *, max_document_chars: int = 12000) -> list[SyntheticFixture]:
    fixture_root = root or default_fixture_root()
    manifest_path = _resolve_fixture_path(fixture_root, 'manifest.json')
    try:
        raw = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise RagFixtureError('manifest_unreadable') from exc
    entries = raw.get('fixtures')
    if not isinstance(entries, list):
        raise RagFixtureError('manifest_fixtures_required')
    fixtures: list[SyntheticFixture] = []
    seen: set[str] = set()
    allowed_paths: set[str] = set()
    limit = max(1, min(int(max_document_chars), 50000))
    for entry in entries:
        if not isinstance(entry, dict):
            raise RagFixtureError('invalid_manifest_entry')
        case_id = _safe_case_id(str(entry.get('case_id', '')))
        if case_id in seen:
            raise RagFixtureError('duplicate_case_id')
        seen.add(case_id)
        _validate_metadata(entry)
        rel = str(entry.get('relative_path', ''))
        if rel in allowed_paths:
            raise RagFixtureError('duplicate_fixture_path')
        allowed_paths.add(rel)
        path = _resolve_fixture_path(fixture_root, rel)
        if not path.is_file():
            raise RagFixtureError('fixture_file_missing')
        content = path.read_text(encoding='utf-8')
        if len(content) > limit:
            raise RagFixtureError('fixture_too_large')
        _reject_canaries(content)
        fixtures.append(
            SyntheticFixture(
                case_id=case_id,
                title=str(entry.get('title', case_id))[:256],
                relative_path=rel,
                content=content,
                synthetic_only=True,
                authority=False,
                clinical_use_allowed=False,
                provenance_status='synthetic_generated',
                license_status='synthetic_only',
                review_status='approved_for_synthetic_test',
                language_code=str(entry.get('language_code', 'id')) if entry.get('language_code') in {'id', 'en'} else 'id',
            )
        )
    return fixtures


def load_fixture_case(case_id: str, root: Path | None = None, *, max_document_chars: int = 12000) -> SyntheticFixture:
    safe_case = _safe_case_id(case_id)
    for fixture in load_manifest(root, max_document_chars=max_document_chars):
        if fixture.case_id == safe_case:
            return fixture
    raise RagFixtureError('fixture_not_manifested')


def fixture_case_ids(fixtures: Iterable[SyntheticFixture]) -> tuple[str, ...]:
    return tuple(fixture.case_id for fixture in fixtures)
