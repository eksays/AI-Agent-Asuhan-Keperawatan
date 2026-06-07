from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lab_fixture_loader import LabFixtureError, SyntheticFixtureLoader

@dataclass(frozen=True)
class LabEbpResult:
    fixture_id: str
    source_label: str
    reference_ids: list[str]
    summaries: list[dict[str, str]]

def load_offline_ebp_fixture(loader: SyntheticFixtureLoader, *, fixture_id: str) -> LabEbpResult:
    fixture = loader.load_fixture_by_id(fixture_id, prefix="ebp/")
    references = fixture.get("references")
    if not isinstance(references, list) or not references:
        raise LabFixtureError("Synthetic EBP fixture is empty.")
    summaries: list[dict[str, str]] = []
    for item in references:
        if not isinstance(item, dict):
            continue
        ref_id = str(item.get("reference_id") or "")
        if not ref_id.startswith("SYN-EBP-"):
            raise LabFixtureError("Synthetic EBP reference id is invalid.")
        summaries.append({
            "reference_id": ref_id,
            "title": str(item.get("title") or "Generated synthetic evidence placeholder"),
            "source_label": "offline synthetic EBP fixture",
        })
    return LabEbpResult(
        fixture_id=fixture_id,
        source_label="offline synthetic EBP fixture",
        reference_ids=[item["reference_id"] for item in summaries],
        summaries=summaries,
    )

def ebp_payload(result: LabEbpResult) -> dict[str, Any]:
    return {
        "source_label": result.source_label,
        "reference_ids": result.reference_ids,
        "references": result.summaries,
        "clinical_use_allowed": False,
    }
