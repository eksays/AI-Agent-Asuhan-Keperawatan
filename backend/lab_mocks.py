from __future__ import annotations

from dataclasses import dataclass

from lab_fixture_loader import LabFixtureError, SyntheticFixtureLoader

@dataclass(frozen=True)
class LabMockResult:
    fixture_id: str
    label: str
    extracted_fields: dict[str, str]

def run_ocr_mock(loader: SyntheticFixtureLoader, *, fixture_id: str) -> LabMockResult:
    fixture = loader.load_fixture_by_id(fixture_id, prefix="images/")
    if fixture.get("mock_type") != "ocr":
        raise LabFixtureError("Synthetic OCR mock fixture type is invalid.")
    return LabMockResult(
        fixture_id=fixture_id,
        label="DETERMINISTIC OCR MOCK - EXTRACTION UNVERIFIED",
        extracted_fields={"document_label": str(fixture.get("document_label") or "synthetic note")},
    )

def run_photo_mock(loader: SyntheticFixtureLoader, *, fixture_id: str) -> LabMockResult:
    fixture = loader.load_fixture_by_id(fixture_id, prefix="images/")
    if fixture.get("mock_type") != "photo":
        raise LabFixtureError("Synthetic photo mock fixture type is invalid.")
    return LabMockResult(
        fixture_id=fixture_id,
        label="DETERMINISTIC PHOTO MOCK - NOT CLINICAL IMAGE ANALYSIS",
        extracted_fields={"image_label": str(fixture.get("image_label") or "synthetic photo placeholder")},
    )
