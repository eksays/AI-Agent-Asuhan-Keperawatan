from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lab_config import ensure_approved_fixture_root


class LabFixtureError(ValueError):
    pass


FORBIDDEN_PATH_PARTS = {
    "data_terstruktur",
    "patient_records",
    "patient-records",
    "hospital_documents",
    "hospital-documents",
    ".next",
    "node_modules",
}
ALLOWED_TOP_LEVEL_DIRS = {
    "cases",
    "rag",
    "registries",
    "ebp",
    "uploads",
    "rendering",
    "images",
    "expected_outputs",
}
MAX_FIXTURE_BYTES = 64 * 1024
MAX_JSON_DEPTH = 12


@dataclass(frozen=True)
class LabFixtureManifest:
    fixture_set: str
    fixture_version: str
    files: tuple[str, ...]


class SyntheticFixtureLoader:
    def __init__(self, fixture_root: str | Path) -> None:
        self.root = Path(fixture_root)
        self._manifest: LabFixtureManifest | None = None

    def load_manifest(self) -> LabFixtureManifest:
        root = self._trusted_root()
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise LabFixtureError("Synthetic fixture manifest is missing.")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LabFixtureError("Synthetic fixture manifest is invalid.") from exc
        if not isinstance(manifest, dict):
            raise LabFixtureError("Synthetic fixture manifest must be an object.")
        self._validate_manifest_metadata(manifest)
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise LabFixtureError("Synthetic fixture manifest requires an allowlist.")
        allowed = []
        seen_paths: set[str] = set()
        for entry in files:
            normalized = self._validate_relative_entry(entry, root)
            if normalized in seen_paths:
                raise LabFixtureError("Synthetic fixture manifest contains duplicate paths.")
            seen_paths.add(normalized)
            allowed.append(normalized)
        seen_fixture_ids: set[str] = set()
        for entry in allowed:
            payload = self._read_fixture_payload(entry, root)
            fixture_id = str(payload.get("fixture_id") or "")
            if fixture_id in seen_fixture_ids:
                raise LabFixtureError("Synthetic fixture manifest contains duplicate fixture ids.")
            seen_fixture_ids.add(fixture_id)
        loaded = LabFixtureManifest(
            fixture_set=str(manifest.get("fixture_set") or ""),
            fixture_version=str(manifest.get("fixture_version") or ""),
            files=tuple(allowed),
        )
        self._manifest = loaded
        return loaded

    def load_fixture(self, relative_path: str) -> dict[str, Any]:
        manifest = self._manifest or self.load_manifest()
        normalized = _normalize_entry(relative_path)
        if normalized not in set(manifest.files):
            raise LabFixtureError("Synthetic fixture is not listed in the manifest allowlist.")
        path = self._resolve_allowed_path(normalized, self._trusted_root())
        payload = self._read_fixture_payload(normalized, self._trusted_root())
        return payload

    def _read_fixture_payload(self, normalized: str, root: Path) -> dict[str, Any]:
        path = self._resolve_allowed_path(normalized, root)
        try:
            if path.stat().st_size > MAX_FIXTURE_BYTES:
                raise LabFixtureError("Synthetic fixture body exceeds size limit.")
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LabFixtureError("Synthetic fixture body is invalid.") from exc
        if not isinstance(payload, dict):
            raise LabFixtureError("Synthetic fixture body must be an object.")
        if _json_depth(payload) > MAX_JSON_DEPTH:
            raise LabFixtureError("Synthetic fixture body exceeds nesting limit.")
        self._validate_fixture_metadata(payload)
        return payload

    def load_fixture_by_id(self, fixture_id: str, *, prefix: str | None = None) -> dict[str, Any]:
        wanted = (fixture_id or "").strip()
        if not wanted:
            raise LabFixtureError("Synthetic fixture id is required.")
        manifest = self._manifest or self.load_manifest()
        normalized_prefix = (prefix or "").strip().replace("\\", "/")
        for entry in manifest.files:
            if normalized_prefix and not entry.startswith(normalized_prefix):
                continue
            payload = self.load_fixture(entry)
            if payload.get("fixture_id") == wanted:
                return payload
        raise LabFixtureError("Synthetic fixture id is not listed in the manifest allowlist.")

    def _trusted_root(self) -> Path:
        try:
            root = Path(ensure_approved_fixture_root(self.root))
        except RuntimeError as exc:
            raise LabFixtureError("Synthetic fixture root is not approved.") from exc
        if not root.is_dir():
            raise LabFixtureError("Synthetic fixture root is unavailable.")
        return root

    def _validate_manifest_metadata(self, manifest: dict[str, Any]) -> None:
        if not manifest.get("fixture_set") or not manifest.get("fixture_version"):
            raise LabFixtureError("Synthetic fixture manifest identity is incomplete.")
        self._validate_common_metadata(manifest)

    def _validate_fixture_metadata(self, payload: dict[str, Any]) -> None:
        required = (
            "fixture_id",
            "fixture_version",
            "synthetic_only",
            "authoritative",
            "clinical_use_allowed",
            "source_type",
            "created_for",
        )
        if any(key not in payload for key in required):
            raise LabFixtureError("Synthetic fixture metadata is incomplete.")
        self._validate_common_metadata(payload)

    def _validate_common_metadata(self, payload: dict[str, Any]) -> None:
        if payload.get("synthetic_only") is not True:
            raise LabFixtureError("Synthetic fixtures must be synthetic-only.")
        if payload.get("authoritative") is not False:
            raise LabFixtureError("Synthetic fixtures must be non-authoritative.")
        if payload.get("clinical_use_allowed") is not False:
            raise LabFixtureError("Synthetic fixtures must forbid clinical use.")
        if payload.get("source_type") != "generated_fixture":
            raise LabFixtureError("Synthetic fixtures must be generated fixtures.")

    def _validate_relative_entry(self, entry: Any, root: Path) -> str:
        normalized = _normalize_entry(entry)
        self._resolve_allowed_path(normalized, root)
        return normalized

    def _resolve_allowed_path(self, normalized: str, root: Path) -> Path:
        parts = Path(normalized).parts
        lowered = {part.lower() for part in parts}
        if not parts or parts[0].lower() not in ALLOWED_TOP_LEVEL_DIRS:
            raise LabFixtureError("Synthetic fixture path uses an unknown category.")
        if Path(normalized).suffix.lower() != ".json":
            raise LabFixtureError("Synthetic fixture path must use a JSON extension.")
        if lowered & FORBIDDEN_PATH_PARTS:
            raise LabFixtureError("Synthetic fixture path uses a forbidden location.")
        if any("patient" in part.lower() or "hospital" in part.lower() for part in parts):
            raise LabFixtureError("Synthetic fixture path resembles patient or hospital material.")
        candidate = root / normalized
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise LabFixtureError("Synthetic fixture path escapes the trusted root.") from exc
        if not candidate.is_file():
            raise LabFixtureError("Synthetic fixture file is missing.")
        if candidate.is_symlink():
            try:
                candidate.resolve(strict=True).relative_to(root)
            except (OSError, ValueError) as exc:
                raise LabFixtureError("Synthetic fixture symlink escapes the trusted root.") from exc
        return candidate


def _normalize_entry(entry: Any) -> str:
    if not isinstance(entry, str) or not entry.strip():
        raise LabFixtureError("Synthetic fixture path must be a relative string.")
    raw = entry.strip().replace("\\", "/")
    if raw.startswith(("/", "//")) or Path(raw).is_absolute():
        raise LabFixtureError("Synthetic fixture path must be relative.")
    parts = Path(raw).parts
    if any(part in {"..", ""} for part in parts):
        raise LabFixtureError("Synthetic fixture path traversal is forbidden.")
    return "/".join(parts)

def _json_depth(value: Any) -> int:
    if isinstance(value, dict):
        if not value:
            return 1
        return 1 + max(_json_depth(item) for item in value.values())
    if isinstance(value, list):
        if not value:
            return 1
        return 1 + max(_json_depth(item) for item in value)
    return 1
