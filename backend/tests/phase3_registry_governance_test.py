from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
import sys
import tempfile
import unittest
import urllib.request
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
import config  # noqa: E402
from clinical_registry import ClinicalRegistry  # noqa: E402
from clinical_validator import validate_clinical_output  # noqa: E402
from registry_governance import (  # noqa: E402
    GovernedRegistryEntry,
    MAX_IMPORT_ENTRY_COUNT,
    MAX_JSON_DEPTH,
    MAX_REGISTRY_FILE_BYTES,
    MAX_STRING_LENGTH,
    QuarantineReason,
    RegistryImportError,
    compute_entry_content_hash,
    dry_run_import_batch,
    dry_run_import,
    resolve_import_source,
    validate_registry_entries,
)
from registry_release import (  # noqa: E402
    RegistryReleaseStore,
    make_release_manifest,
    validate_framework_release_set,
    validate_release_candidate,
)

try:  # noqa: E402
    import requests  # type: ignore
except Exception:  # pragma: no cover - dependency may be absent in minimal envs
    requests = None

try:  # noqa: E402
    import httpx  # type: ignore
except Exception:  # pragma: no cover - dependency may be absent in minimal envs
    httpx = None

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "registry_governance" / "synthetic_registry_entries.json"


def base_entry(framework="SDKI", component_type="diagnosis", code="D.0001", name="Synthetic Airway Clearance Diagnosis") -> dict:
    raw = {
        "framework": framework,
        "component_type": component_type,
        "code": code,
        "name": name,
        "source_title": "Synthetic registry governance fixture",
        "source_version": "fixture-v1",
        "source_page": "1",
        "source_section": "synthetic",
        "source_identifier": f"synthetic-source-{framework}-{code}",
        "source_license_status": "approved",
        "extraction_method": "manual_fixture",
        "extraction_tool": "none",
        "extraction_timestamp": "2026-06-06T00:00:00Z",
        "reviewer_role": "synthetic clinical reviewer",
        "reviewer_identifier": "synthetic-reviewer",
        "review_date": "2026-06-06",
        "approval_status": "approved",
        "approval_record_id": "APR-SYN-001",
        "registry_version": "fixture-v1",
        "release_id": "REL-SYN-001",
        "lifecycle_state": "approved",
    }
    raw["content_hash"] = compute_entry_content_hash(raw)
    return raw


def governed_entry(**overrides) -> GovernedRegistryEntry:
    raw = base_entry()
    raw.update(overrides)
    if overrides.get("content_hash") != "wrong-hash":
        raw["content_hash"] = compute_entry_content_hash(raw)
    return validate_registry_entries([raw])[0]


def validated_entries(*raw_entries: dict) -> tuple[GovernedRegistryEntry, ...]:
    return validate_registry_entries(raw_entries)


def enabled_config(**extra: str):
    env = {"APP_MODE": "clinical_sandbox", "ALLOW_UNSAFE_EXTERNAL_LLM_FOR_LOCAL_DEBUG": "true"}
    env.update(extra)
    return config.load_config(env)


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


class Phase3LifecycleAndQuarantineTests(unittest.TestCase):
    def test_approved_synthetic_3s_entries_are_release_eligible_but_not_authoritative(self):
        entries = validated_entries(
            base_entry("SDKI", "diagnosis", "D.0001", "Synthetic Airway Clearance Diagnosis"),
            base_entry("SLKI", "outcome", "L.0001", "Synthetic Respiratory Outcome"),
            base_entry("SIKI", "intervention", "I.0001", "Synthetic Airway Intervention"),
        )
        self.assertTrue(all(entry.release_eligible for entry in entries))
        self.assertTrue(all(not entry.authoritative for entry in entries))

    def test_ocr_derived_entry_is_non_authoritative(self):
        entry = governed_entry(lifecycle_state="ocr_extracted", approval_status="draft", extraction_method="ocr")
        self.assertFalse(entry.release_eligible)
        self.assertIn(QuarantineReason.OCR_REVIEW_REQUIRED, entry.quarantine_reasons)

    def test_llm_assisted_entry_is_non_authoritative(self):
        entry = governed_entry(lifecycle_state="llm_assisted", approval_status="draft", extraction_method="llm_assisted")
        self.assertFalse(entry.release_eligible)
        self.assertIn(QuarantineReason.LLM_ASSISTED_REVIEW_REQUIRED, entry.quarantine_reasons)

    def test_extraction_unverified_entry_is_non_authoritative(self):
        entry = governed_entry(lifecycle_state="extraction_unverified", approval_status="draft")
        self.assertFalse(entry.release_eligible)
        self.assertIn(QuarantineReason.EXTRACTION_UNVERIFIED, entry.quarantine_reasons)

    def test_under_clinical_review_entry_is_non_authoritative(self):
        entry = governed_entry(lifecycle_state="under_clinical_review", approval_status="under_clinical_review")
        self.assertFalse(entry.release_eligible)
        self.assertIn(QuarantineReason.UNDER_CLINICAL_REVIEW, entry.quarantine_reasons)

    def test_approved_entry_with_missing_provenance_is_quarantined(self):
        raw = base_entry()
        raw.pop("source_title")
        raw["content_hash"] = compute_entry_content_hash(raw)
        entry = validate_registry_entries([raw])[0]
        self.assertIn(QuarantineReason.MISSING_PROVENANCE, entry.quarantine_reasons)
        self.assertFalse(entry.release_eligible)

    def test_approved_entry_with_unknown_license_is_quarantined(self):
        raw = base_entry()
        raw["source_identifier"] = "synthetic-source-unknown-license"
        raw["source_license_status"] = "unknown"
        raw["content_hash"] = compute_entry_content_hash(raw)
        entry = validate_registry_entries([raw])[0]
        self.assertIn(QuarantineReason.LICENSE_STATUS_UNKNOWN, entry.quarantine_reasons)
        self.assertFalse(entry.release_eligible)

    def test_malformed_codes_are_quarantined(self):
        entries = validated_entries(base_entry(code="D.xxxx"), base_entry(code="D.L"))
        for entry in entries:
            self.assertIn(QuarantineReason.MALFORMED_CODE, entry.quarantine_reasons)

    def test_duplicate_code_and_code_name_conflict_are_quarantined(self):
        first = base_entry(code="D.0002", name="Synthetic Duplicate One")
        second = base_entry(code="D.0002", name="Synthetic Duplicate Two")
        entries = validated_entries(first, second)
        for entry in entries:
            self.assertIn(QuarantineReason.DUPLICATE_CODE, entry.quarantine_reasons)
            self.assertIn(QuarantineReason.CODE_NAME_CONFLICT, entry.quarantine_reasons)

    def test_wrong_component_type_is_quarantined(self):
        entry = governed_entry(framework="SLKI", component_type="intervention", code="L.0001", name="Synthetic Respiratory Outcome")
        self.assertIn(QuarantineReason.WRONG_COMPONENT_TYPE, entry.quarantine_reasons)

    def test_content_hash_mismatch_is_quarantined(self):
        entry = governed_entry(content_hash="wrong-hash")
        self.assertIn(QuarantineReason.CONTENT_HASH_MISMATCH, entry.quarantine_reasons)

    def test_deprecated_entry_is_non_authoritative(self):
        entry = governed_entry(lifecycle_state="deprecated")
        self.assertIn(QuarantineReason.DEPRECATED_ENTRY, entry.quarantine_reasons)
        self.assertFalse(entry.release_eligible)

    def test_manual_quarantine_is_enforced(self):
        entry = governed_entry(lifecycle_state="quarantined", manual_quarantine=True)
        self.assertIn(QuarantineReason.MANUAL_QUARANTINE, entry.quarantine_reasons)
        self.assertFalse(entry.release_eligible)

    def test_synthetic_fixture_covers_required_cases(self):
        report = dry_run_import(FIXTURE, dataset_name="synthetic registry governance fixture")
        reasons = report.reason_counts
        self.assertGreaterEqual(report.entry_count, 18)
        for reason in {
            QuarantineReason.OCR_REVIEW_REQUIRED,
            QuarantineReason.LLM_ASSISTED_REVIEW_REQUIRED,
            QuarantineReason.EXTRACTION_UNVERIFIED,
            QuarantineReason.MALFORMED_CODE,
            QuarantineReason.DUPLICATE_CODE,
            QuarantineReason.MISSING_PROVENANCE,
            QuarantineReason.LICENSE_STATUS_UNKNOWN,
            QuarantineReason.CONTENT_HASH_MISMATCH,
            QuarantineReason.DEPRECATED_ENTRY,
            QuarantineReason.MANUAL_QUARANTINE,
        }:
            self.assertGreater(reasons[reason], 0, reason)

    def test_all_non_approved_lifecycle_states_never_auto_promote(self):
        for state in (
            "draft",
            "ocr_extracted",
            "llm_assisted",
            "extraction_unverified",
            "under_clinical_review",
            "deprecated",
            "quarantined",
        ):
            with self.subTest(state=state):
                entry = governed_entry(lifecycle_state=state, approval_status=state, manual_quarantine=(state == "quarantined"))
                self.assertFalse(entry.authoritative)
                self.assertFalse(entry.release_eligible)
                self.assertTrue(entry.quarantine_reasons)


class Phase3DryRunImportTests(unittest.TestCase):
    def test_dry_run_import_does_not_activate_registry(self):
        report = dry_run_import(FIXTURE)
        self.assertTrue(report.dry_run)
        self.assertEqual(report.authoritative_count, 0)
        self.assertGreater(report.quarantined_count, 0)

    def test_dry_run_import_does_not_mutate_source(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        dry_run_import(FIXTURE)
        after = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_manifest_only_exposes_safe_metadata_only(self):
        report = dry_run_import(FIXTURE)
        safe = report.to_safe_dict()
        self.assertIn("entry_count", safe)
        self.assertIn("quarantine_reason_counts", safe)
        self.assertNotIn("entries", safe)

    def test_network_deny_for_registry_import_dry_run(self):
        calls = {"socket": 0, "urlopen": 0, "requests": 0, "httpx": 0, "llm": 0, "ebp": 0}

        def fail_socket(*_args, **_kwargs):
            calls["socket"] += 1
            raise AssertionError("registry dry-run import must not open sockets")

        def fail_urlopen(*_args, **_kwargs):
            calls["urlopen"] += 1
            raise AssertionError("registry dry-run import must not make HTTP requests")

        def fail_requests(*_args, **_kwargs):
            calls["requests"] += 1
            raise AssertionError("registry dry-run import must not use requests")

        def fail_httpx(*_args, **_kwargs):
            calls["httpx"] += 1
            raise AssertionError("registry dry-run import must not use httpx")

        def fail_llm(*_args, **_kwargs):
            calls["llm"] += 1
            raise AssertionError("registry dry-run import must not create LLM clients")

        def fail_ebp(*_args, **_kwargs):
            calls["ebp"] += 1
            raise AssertionError("registry dry-run import must not call EBP retrieval")

        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(socket.socket, "connect", fail_socket))
            stack.enter_context(mock.patch.object(urllib.request, "urlopen", fail_urlopen))
            stack.enter_context(mock.patch.object(api, "_create_raw_llm", fail_llm))
            stack.enter_context(mock.patch.object(api.ebp, "retrieve_context", fail_ebp))
            if requests is not None:
                stack.enter_context(mock.patch.object(requests.sessions.Session, "request", fail_requests))
            if httpx is not None:
                stack.enter_context(mock.patch.object(httpx.Client, "request", fail_httpx))
            report = dry_run_import(FIXTURE)
        self.assertEqual(report.entry_count, 18)
        self.assertEqual(calls, {"socket": 0, "urlopen": 0, "requests": 0, "httpx": 0, "llm": 0, "ebp": 0})

    def test_explicit_source_file_only_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_json(root / "SDKI.json", [base_entry()])
            report = dry_run_import(source, import_root=root, source_framework="SDKI")
        self.assertEqual(report.entry_count, 1)
        self.assertEqual(Path(report.source_path).name, "SDKI.json")

    def test_directory_import_excludes_backups_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "SDKI.json", [base_entry(code="D.0008", name="Synthetic Primary")])
            write_json(root / "SDKI.json.bak-20260606", [base_entry(code="D.xxxx", name="Synthetic Backup")])
            report = dry_run_import(root, import_root=root, source_framework="SDKI")
        self.assertEqual(report.entry_count, 1)
        self.assertNotIn(QuarantineReason.MALFORMED_CODE, report.reason_counts)

    def test_traversal_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            root = temp / "allowed"
            root.mkdir()
            outside = write_json(temp / "outside.json", [base_entry()])
            traversal = root / ".." / outside.name
            with self.assertRaisesRegex(RegistryImportError, "outside the approved import root"):
                dry_run_import(traversal, import_root=root, source_framework="SDKI")

    def test_absolute_path_outside_import_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            root = temp / "allowed"
            root.mkdir()
            outside = write_json(temp / "outside.json", [base_entry()])
            with self.assertRaisesRegex(RegistryImportError, "outside the approved import root"):
                dry_run_import(outside.resolve(), import_root=root, source_framework="SDKI")

    def test_symlink_escaping_import_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            root = temp / "allowed"
            root.mkdir()
            outside = write_json(temp / "outside.json", [base_entry()])
            link = root / "escape.json"
            link.write_text("[]", encoding="utf-8")
            original_resolve = Path.resolve

            def fake_resolve(path: Path, *args, **kwargs):
                if str(path) == str(link):
                    return original_resolve(outside, *args, **kwargs)
                return original_resolve(path, *args, **kwargs)

            with mock.patch.object(Path, "resolve", fake_resolve), \
                 self.assertRaisesRegex(RegistryImportError, "outside the approved import root"):
                dry_run_import(link, import_root=root, source_framework="SDKI")

    def test_unsupported_extension_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_json(root / "SDKI.txt", [base_entry()])
            with self.assertRaisesRegex(RegistryImportError, "Unsupported registry import extension"):
                dry_run_import(source, import_root=root, source_framework="SDKI")

    def test_missing_file_is_rejected_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(RegistryImportError, "source file is missing"):
                dry_run_import(root / "missing.json", import_root=root, source_framework="SDKI")

    def test_oversized_json_file_is_rejected_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "SDKI.json"
            source.write_text("[" + (" " * (MAX_REGISTRY_FILE_BYTES + 1)) + "]", encoding="utf-8")
            with self.assertRaisesRegex(RegistryImportError, "maximum file size"):
                dry_run_import(source, import_root=root, source_framework="SDKI")

    def test_deeply_nested_json_is_rejected_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value: object = "leaf"
            for _ in range(MAX_JSON_DEPTH + 2):
                value = {"nested": value}
            source = write_json(root / "SDKI.json", value)
            with self.assertRaisesRegex(RegistryImportError, "maximum JSON nesting depth"):
                dry_run_import(source, import_root=root, source_framework="SDKI")

    def test_excessive_entry_count_is_rejected_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_json(root / "SDKI.json", [{} for _ in range(MAX_IMPORT_ENTRY_COUNT + 1)])
            with self.assertRaisesRegex(RegistryImportError, "maximum entry count"):
                dry_run_import(source, import_root=root, source_framework="SDKI")

    def test_oversized_field_content_is_quarantined(self):
        raw = base_entry(name="X" * (MAX_STRING_LENGTH + 1))
        raw["content_hash"] = compute_entry_content_hash(raw)
        entry = validate_registry_entries([raw])[0]
        self.assertIn(QuarantineReason.FIELD_TOO_LONG, entry.quarantine_reasons)

    def test_canonical_hash_stable_for_key_order_and_whitespace(self):
        raw = base_entry()
        reordered = json.loads(json.dumps(raw, sort_keys=False, indent=4))
        self.assertEqual(compute_entry_content_hash(raw), compute_entry_content_hash(reordered))

    def test_canonical_hash_changes_when_clinical_content_changes(self):
        raw = base_entry()
        changed = copy.deepcopy(raw)
        changed["name"] = "Synthetic Changed Clinical Name"
        self.assertNotEqual(compute_entry_content_hash(raw), compute_entry_content_hash(changed))

    def test_canonical_hash_excludes_documented_volatile_runtime_fields(self):
        raw = base_entry()
        volatile = copy.deepcopy(raw)
        volatile["review_date"] = "2099-01-01"
        volatile["release_id"] = "REL-RUNTIME-CHANGED"
        volatile["reviewer_identifier"] = "different-reviewer"
        self.assertEqual(compute_entry_content_hash(raw), compute_entry_content_hash(volatile))

    def test_duplicate_code_across_explicit_import_files_is_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = write_json(root / "first.json", [base_entry(code="D.0200", name="Synthetic Duplicate One")])
            second = write_json(root / "second.json", [base_entry(code="D.0200", name="Synthetic Duplicate Two")])
            report = dry_run_import_batch([first, second], import_root=root, source_framework="SDKI")
        self.assertEqual(report.entry_count, 2)
        self.assertGreater(report.reason_counts[QuarantineReason.DUPLICATE_CODE], 0)
        self.assertGreater(report.reason_counts[QuarantineReason.CODE_NAME_CONFLICT], 0)


class Phase3ReleaseAndRollbackTests(unittest.TestCase):
    def approved_entries(self) -> tuple[GovernedRegistryEntry, ...]:
        return validated_entries(
            base_entry("SDKI", "diagnosis", "D.0001", "Synthetic Airway Clearance Diagnosis"),
            base_entry("SDKI", "diagnosis", "D.0003", "Synthetic Follow-up Diagnosis"),
        )

    def entries_for(self, framework: str, component_type: str, code: str, name: str) -> tuple[GovernedRegistryEntry, ...]:
        return validated_entries(base_entry(framework, component_type, code, name))

    def manifest_for(self, release_id: str, framework: str, component_type: str, entries: tuple[GovernedRegistryEntry, ...]):
        return make_release_manifest(release_id, "fixture-v1", framework, component_type, entries, release_status="approved_for_activation")

    def release_set_3s(self, *components: str):
        specs = {
            "SDKI": ("diagnosis", "D.0001", "Synthetic Airway Clearance Diagnosis"),
            "SLKI": ("outcome", "L.0001", "Synthetic Respiratory Outcome"),
            "SIKI": ("intervention", "I.0001", "Synthetic Airway Intervention"),
        }
        entries_by_release = {}
        manifests = []
        for framework in components:
            component_type, code, name = specs[framework]
            entries = self.entries_for(framework, component_type, code, name)
            release_id = f"REL-{framework}"
            entries_by_release[release_id] = entries
            manifests.append(self.manifest_for(release_id, framework, component_type, entries))
        return tuple(manifests), entries_by_release

    def release_set_3n(self, *components: str):
        specs = {
            "NANDA": ("diagnosis", "00031", "Synthetic NANDA Diagnosis"),
            "NOC": ("outcome", "1234", "Synthetic NOC Outcome"),
            "NIC": ("intervention", "1234", "Synthetic NIC Intervention"),
        }
        entries_by_release = {}
        manifests = []
        for framework in components:
            component_type, code, name = specs[framework]
            entries = self.entries_for(framework, component_type, code, name)
            release_id = f"REL-{framework}"
            entries_by_release[release_id] = entries
            manifests.append(self.manifest_for(release_id, framework, component_type, entries))
        return tuple(manifests), entries_by_release

    def test_candidate_release_rejects_quarantined_entries(self):
        entries = (governed_entry(), governed_entry(code="D.xxxx"))
        manifest = make_release_manifest("REL-SYN-Q", "fixture-v1", "SDKI", "diagnosis", entries)
        result = validate_release_candidate(manifest, entries)
        self.assertFalse(result.accepted)
        self.assertIn("QUARANTINED_ENTRY", [issue.code for issue in result.issues])

    def test_candidate_release_rejects_missing_approval_records(self):
        entries = self.approved_entries()
        manifest = make_release_manifest("REL-SYN-MISSING-APPROVAL", "fixture-v1", "SDKI", "diagnosis", entries)
        manifest = replace(manifest, approval_record_ids=())
        result = validate_release_candidate(manifest, entries)
        self.assertFalse(result.accepted)
        self.assertIn("MISSING_APPROVAL_RECORD", [issue.code for issue in result.issues])

    def test_candidate_release_rejects_unknown_license_status(self):
        raw = base_entry(code="D.0004", name="Synthetic Unknown License")
        raw["source_license_status"] = "unknown"
        raw["content_hash"] = compute_entry_content_hash(raw)
        entries = validate_registry_entries([raw])
        manifest = make_release_manifest("REL-SYN-UNKNOWN-LICENSE", "fixture-v1", "SDKI", "diagnosis", entries)
        result = validate_release_candidate(manifest, entries)
        self.assertFalse(result.accepted)
        self.assertIn(QuarantineReason.LICENSE_STATUS_UNKNOWN, [issue.code for issue in result.issues])

    def test_activation_requires_explicit_approved_release_artifact(self):
        entries = self.approved_entries()
        manifest = make_release_manifest("REL-SYN-CANDIDATE", "fixture-v1", "SDKI", "diagnosis", entries, release_status="candidate")
        store = RegistryReleaseStore()
        self.assertIsNone(store.active_release("SDKI", "diagnosis"))
        with self.assertRaisesRegex(ValueError, "approved_for_activation"):
            store.activate_release(manifest, entries)

    def test_approved_for_activation_release_is_not_active_until_explicit_call(self):
        entries = self.approved_entries()
        manifest = make_release_manifest("REL-SYN-APPROVED", "fixture-v1", "SDKI", "diagnosis", entries, release_status="approved_for_activation")
        store = RegistryReleaseStore()
        self.assertIsNone(store.active_release("SDKI", "diagnosis"))
        active = store.activate_release(manifest, entries)
        self.assertEqual(active.release_status, "active")
        self.assertEqual(store.active_release("SDKI", "diagnosis").release_id, "REL-SYN-APPROVED")

    def test_activation_preserves_previous_release_pointer(self):
        entries_v1 = self.approved_entries()
        entries_v2 = validate_registry_entries([
            base_entry("SDKI", "diagnosis", "D.0005", "Synthetic Replacement Diagnosis")
        ])
        store = RegistryReleaseStore()
        rel1 = make_release_manifest("REL-SYN-1", "fixture-v1", "SDKI", "diagnosis", entries_v1, release_status="approved_for_activation")
        active1 = store.activate_release(rel1, entries_v1)
        rel2 = make_release_manifest("REL-SYN-2", "fixture-v2", "SDKI", "diagnosis", entries_v2, release_status="approved_for_activation")
        active2 = store.activate_release(rel2, entries_v2)
        self.assertEqual(active1.release_status, "active")
        self.assertEqual(active2.previous_release_id, "REL-SYN-1")
        self.assertEqual(store.active_release("SDKI", "diagnosis").release_id, "REL-SYN-2")

    def test_rollback_restores_previous_release_pointer(self):
        entries_v1 = self.approved_entries()
        entries_v2 = validate_registry_entries([
            base_entry("SDKI", "diagnosis", "D.0005", "Synthetic Replacement Diagnosis")
        ])
        store = RegistryReleaseStore()
        store.activate_release(make_release_manifest("REL-SYN-1", "fixture-v1", "SDKI", "diagnosis", entries_v1, release_status="approved_for_activation"), entries_v1)
        store.activate_release(make_release_manifest("REL-SYN-2", "fixture-v2", "SDKI", "diagnosis", entries_v2, release_status="approved_for_activation"), entries_v2)
        restored = store.rollback("SDKI", "diagnosis")
        self.assertEqual(restored.release_id, "REL-SYN-1")
        self.assertEqual(store.active_release("SDKI", "diagnosis").release_id, "REL-SYN-1")

    def test_rollback_with_no_previous_release_is_rejected(self):
        entries = self.approved_entries()
        store = RegistryReleaseStore()
        store.activate_release(make_release_manifest("REL-SYN-1", "fixture-v1", "SDKI", "diagnosis", entries, release_status="approved_for_activation"), entries)
        with self.assertRaisesRegex(ValueError, "No previous active release"):
            store.rollback("SDKI", "diagnosis")

    def test_attempt_to_activate_quarantined_release_is_rejected(self):
        entries = (governed_entry(code="D.xxxx"),)
        manifest = make_release_manifest("REL-SYN-Q-ACT", "fixture-v1", "SDKI", "diagnosis", entries, release_status="approved_for_activation")
        with self.assertRaisesRegex(ValueError, "QUARANTINED_ENTRY"):
            RegistryReleaseStore().activate_release(manifest, entries)

    def test_attempt_to_activate_missing_approval_record_is_rejected(self):
        raw = base_entry()
        raw["approval_record_id"] = ""
        raw["content_hash"] = compute_entry_content_hash(raw)
        entries = validate_registry_entries([raw])
        manifest = make_release_manifest("REL-SYN-NO-APPROVAL", "fixture-v1", "SDKI", "diagnosis", entries, release_status="approved_for_activation")
        with self.assertRaisesRegex(ValueError, "MISSING_APPROVAL_RECORD|ENTRY_NOT_RELEASE_ELIGIBLE"):
            RegistryReleaseStore().activate_release(manifest, entries)

    def test_attempt_to_reactivate_deprecated_release_is_rejected(self):
        entries = self.approved_entries()
        manifest = make_release_manifest("REL-SYN-DEPRECATED", "fixture-v1", "SDKI", "diagnosis", entries, release_status="deprecated")
        with self.assertRaisesRegex(ValueError, "approved_for_activation"):
            RegistryReleaseStore().activate_release(manifest, entries)

    def test_3s_framework_release_completeness(self):
        cases = [
            (("SDKI",), False),
            (("SDKI", "SLKI"), False),
            (("SDKI", "SIKI"), False),
            (("SDKI", "SLKI", "SIKI"), True),
        ]
        for components, expected in cases:
            with self.subTest(components=components):
                manifests, entries_by_release = self.release_set_3s(*components)
                result = validate_framework_release_set("3S", manifests, entries_by_release)
                self.assertEqual(result.accepted, expected)

    def test_3n_framework_release_completeness(self):
        cases = [
            (("NANDA",), False),
            (("NANDA", "NOC"), False),
            (("NANDA", "NIC"), False),
            (("NANDA", "NOC", "NIC"), True),
        ]
        for components, expected in cases:
            with self.subTest(components=components):
                manifests, entries_by_release = self.release_set_3n(*components)
                result = validate_framework_release_set("3N", manifests, entries_by_release)
                self.assertEqual(result.accepted, expected)

    def test_framework_release_activation_requires_complete_component_family(self):
        manifests, entries_by_release = self.release_set_3s("SDKI", "SLKI")
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_FRAMEWORK_RELEASE"):
            RegistryReleaseStore().activate_framework_release_set("3S", manifests, entries_by_release)
        manifests, entries_by_release = self.release_set_3s("SDKI", "SLKI", "SIKI")
        activated = RegistryReleaseStore().activate_framework_release_set("3S", manifests, entries_by_release)
        self.assertEqual({release.release_status for release in activated}, {"active"})

    def test_duplicate_release_entry_across_component_manifests_is_rejected(self):
        shared = self.entries_for("SDKI", "diagnosis", "D.0009", "Synthetic Shared Entry")
        sdki = self.manifest_for("REL-SDKI", "SDKI", "diagnosis", shared)
        slki = self.manifest_for("REL-SLKI", "SLKI", "outcome", shared)
        siki_entries = self.entries_for("SIKI", "intervention", "I.0001", "Synthetic Airway Intervention")
        siki = self.manifest_for("REL-SIKI", "SIKI", "intervention", siki_entries)
        result = validate_framework_release_set("3S", (sdki, slki, siki), {
            "REL-SDKI": shared,
            "REL-SLKI": shared,
            "REL-SIKI": siki_entries,
        })
        self.assertFalse(result.accepted)
        self.assertIn("DUPLICATE_RELEASE_ENTRY", [issue.code for issue in result.issues])


class Phase3Phase2RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)

    def test_local_ignored_registry_presence_does_not_activate_grounding(self):
        self.assertTrue(api.CLINICAL_REGISTRY.is_unavailable)
        self.assertEqual(api.CLINICAL_REGISTRY.approved_count, 0)

    def test_dry_run_report_does_not_activate_api_grounding(self):
        report = dry_run_import(FIXTURE)
        self.assertEqual(report.authoritative_count, 0)
        self.assertTrue(api.CLINICAL_REGISTRY.is_unavailable)

    def test_candidate_release_does_not_activate_api_grounding(self):
        entries = validated_entries(base_entry())
        make_release_manifest("REL-CANDIDATE-NOT-ACTIVE", "fixture-v1", "SDKI", "diagnosis", entries, release_status="candidate")
        self.assertTrue(api.CLINICAL_REGISTRY.is_unavailable)

    def test_approved_for_activation_release_without_activation_does_not_activate_api_grounding(self):
        entries = validated_entries(base_entry())
        make_release_manifest("REL-APPROVED-NOT-ACTIVE", "fixture-v1", "SDKI", "diagnosis", entries, release_status="approved_for_activation")
        self.assertTrue(api.CLINICAL_REGISTRY.is_unavailable)

    def test_phase2_strict_abstention_remains_active_without_complete_active_release(self):
        sdki_only = ClinicalRegistry.from_entries([
            {
                "framework": "SDKI",
                "code": "D.0001",
                "name": "Bersihan Jalan Napas Tidak Efektif",
                "source_title": "Synthetic nursing registry fixture",
                "source_version": "fixture-v1",
                "reviewer": "synthetic reviewer",
                "review_date": "2026-01-01",
                "approval_status": "approved",
                "content_hash": "hash-SDKI-D.0001",
            }
        ])
        output = {
            "status": "validated",
            "framework": "3S",
            "diagnoses": [
                {
                    "framework": "SDKI",
                    "code": "D.0001",
                    "name": "Bersihan Jalan Napas Tidak Efektif",
                    "supporting_evidence": [{"patient_fact": "RR 28 x/menit", "source": "patient_record"}],
                    "missing_required_evidence": [],
                    "confidence_band": "medium",
                    "validation_status": "validated",
                    "nurse_review_required": False,
                }
            ],
            "outcomes": [],
            "interventions": [],
            "missing_data": [],
            "validation_issues": [],
            "nurse_review_required": False,
        }
        outcome = validate_clinical_output(json.dumps(output), "3S", sdki_only, patient_context="RR 28 x/menit")
        self.assertFalse(outcome.accepted)
        self.assertEqual(outcome.response.status, "registry_incomplete")
        self.assertFalse(bool(outcome.response.diagnoses))
        self.assertTrue(outcome.response.nurse_review_required)

    def test_informal_nursing_feedback_is_not_approval_record(self):
        entry = governed_entry(reviewer_role="nursing perspective reviewer", approval_record_id="")
        self.assertIn(QuarantineReason.MISSING_PROVENANCE, entry.quarantine_reasons)
        self.assertFalse(entry.release_eligible)

    def test_synthetic_complete_registry_injected_in_api_tests_still_uses_phase2_validation(self):
        payload = {
            "status": "validated",
            "framework": "3S",
            "diagnoses": [
                {
                    "framework": "SDKI",
                    "code": "D.0001",
                    "name": "Bersihan Jalan Napas Tidak Efektif",
                    "supporting_evidence": [{"patient_fact": "RR 28 x/menit", "source": "patient_record"}],
                    "missing_required_evidence": [],
                    "confidence_band": "medium",
                    "validation_status": "validated",
                    "nurse_review_required": False,
                }
            ],
            "outcomes": [{"framework": "SLKI", "code": "L.0001", "name": "Status Pernapasan", "supporting_evidence": [{"patient_fact": "RR 28 x/menit", "source": "patient_record"}], "validation_status": "validated", "nurse_review_required": False}],
            "interventions": [{"framework": "SIKI", "code": "I.0001", "name": "Manajemen Jalan Napas", "rationale": "synthetic", "supporting_evidence": [{"patient_fact": "RR 28 x/menit", "source": "patient_record"}], "validation_status": "validated", "nurse_review_required": False}],
            "missing_data": [],
            "validation_issues": [],
            "nurse_review_required": False,
        }
        registry = ClinicalRegistry.from_entries([
            {"framework": "SDKI", "code": "D.0001", "name": "Bersihan Jalan Napas Tidak Efektif", "source_title": "Synthetic fixture", "source_version": "fixture-v1", "reviewer": "synthetic", "review_date": "2026-06-06", "approval_status": "approved", "content_hash": "hash-sdk"},
            {"framework": "SLKI", "code": "L.0001", "name": "Status Pernapasan", "source_title": "Synthetic fixture", "source_version": "fixture-v1", "reviewer": "synthetic", "review_date": "2026-06-06", "approval_status": "approved", "content_hash": "hash-slk"},
            {"framework": "SIKI", "code": "I.0001", "name": "Manajemen Jalan Napas", "source_title": "Synthetic fixture", "source_version": "fixture-v1", "reviewer": "synthetic", "review_date": "2026-06-06", "approval_status": "approved", "content_hash": "hash-sik"},
        ])
        raw_llm = mock.Mock()
        raw_llm.invoke.return_value = type("Response", (), {"content": json.dumps(payload, ensure_ascii=False)})()
        raw_llm.stream.side_effect = AssertionError("direct stream must not be used")
        with mock.patch.object(api, "CONFIG", enabled_config()), \
             mock.patch.object(api, "_create_raw_llm", return_value=raw_llm), \
             mock.patch.object(api, "framework_available", return_value=True), \
             mock.patch.object(api, "askep_refs_available", return_value=True), \
             mock.patch.object(api, "bangun_konteks", return_value=""), \
             mock.patch.object(api.memory, "recall_block", return_value=""), \
             mock.patch.object(api, "CLINICAL_REGISTRY", registry):
            session = self.client.post("/session", headers={"Authorization": "Bearer test-key"}).json()
            session_id = session["session_id"]
            response = self.client.post(
                "/chat",
                data={"provider": "openai", "model": "mock", "framework": "3S", "session_id": session_id, "tier": "flash", "agent": "analisis", "pertanyaan": "Pasien batuk dengan RR 28 x/menit dan perlu analisis keperawatan."},
                headers={"Authorization": "Bearer test-key", "X-Session-Token": session["session_token"]},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["clinical_status"], "validated")
        self.assertTrue(data["accepted_recommendations"])
        self.assertTrue(data["nurse_review_required"])


if __name__ == "__main__":
    unittest.main()
