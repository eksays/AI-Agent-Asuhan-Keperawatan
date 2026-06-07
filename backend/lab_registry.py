from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from lab_fixture_loader import LabFixtureError, SyntheticFixtureLoader

SYNTHETIC_CODE_RE = re.compile(r"^SYN-[DOI]-\d{3}$")

@dataclass(frozen=True)
class LabRegistryResult:
    fixture_id: str
    registry_source: str
    candidate_ids: list[str]
    prototype_candidates: list[dict[str, Any]]

def load_synthetic_registry(loader: SyntheticFixtureLoader, *, fixture_id: str) -> LabRegistryResult:
    fixture = loader.load_fixture_by_id(fixture_id, prefix="registries/")
    entries = fixture.get("entries")
    if not isinstance(entries, list) or not entries:
        raise LabFixtureError("Synthetic registry fixture is empty.")
    candidates: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise LabFixtureError("Synthetic registry entry must be an object.")
        code = str(entry.get("code") or "")
        if not SYNTHETIC_CODE_RE.match(code):
            raise LabFixtureError("Synthetic registry code is outside the fake-code namespace.")
        candidates.append({
            "code": code,
            "label": str(entry.get("label") or "synthetic fixture candidate"),
            "framework": str(entry.get("framework") or "SYN"),
            "authority": "synthetic_fixture_non_authoritative",
        })
    return LabRegistryResult(
        fixture_id=fixture_id,
        registry_source="synthetic_fixture_non_authoritative",
        candidate_ids=[item["code"] for item in candidates],
        prototype_candidates=candidates,
    )

def reject_non_manifest_code(loader: SyntheticFixtureLoader, *, registry_fixture_id: str, code: str) -> bool:
    result = load_synthetic_registry(loader, fixture_id=registry_fixture_id)
    return code not in set(result.candidate_ids)
