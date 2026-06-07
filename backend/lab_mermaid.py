from __future__ import annotations

import re
from dataclasses import dataclass

from lab_fixture_loader import LabFixtureError, SyntheticFixtureLoader

UNSAFE_MERMAID_PATTERNS = (
    re.compile(r"<\s*script", re.I),
    re.compile(r"on[a-z]+\s*=", re.I),
    re.compile(r"javascript\s*:", re.I),
    re.compile(r"https?://", re.I),
    re.compile(r"<\s*foreignObject", re.I),
    re.compile(r"<\s*iframe", re.I),
    re.compile(r"<\s*img", re.I),
    re.compile(r"<\s*a\b", re.I),
)

@dataclass(frozen=True)
class LabMermaidResult:
    fixture_id: str
    mermaid_code: str
    sanitizer_boundary: str

def load_safe_mermaid_fixture(loader: SyntheticFixtureLoader, *, fixture_id: str) -> LabMermaidResult:
    fixture = loader.load_fixture_by_id(fixture_id, prefix="rendering/")
    code = str(fixture.get("mermaid") or "")
    if not code.strip():
        raise LabFixtureError("Synthetic Mermaid fixture is empty.")
    if any(pattern.search(code) for pattern in UNSAFE_MERMAID_PATTERNS):
        raise LabFixtureError("Synthetic Mermaid fixture contains unsafe content.")
    if not code.strip().lower().startswith(("flowchart", "graph")):
        raise LabFixtureError("Synthetic Mermaid fixture must use a simple graph declaration.")
    return LabMermaidResult(
        fixture_id=fixture_id,
        mermaid_code=code,
        sanitizer_boundary="frontend_strict_mermaid_svg_sanitizer",
    )
