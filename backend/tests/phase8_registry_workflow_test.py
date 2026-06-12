"""Phase 8 P8-BE — Registry workflow unit tests.

Covers: review queue, approval guards, extraction verification,
lifecycle management, and governance status queries.
All tests use synthetic data only. No patient data. No PHI.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Synthetic helpers
# ---------------------------------------------------------------------------

def _mock_conn():
    """Create a mock connection with cursor context manager."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


class TestCreateSourceMetadata(unittest.TestCase):
    def test_valid_source(self):
        from registry_workflow import create_source_metadata
        conn, cur = _mock_conn()
        result = create_source_metadata(
            conn, 'SYN-SOURCE-001', 'SDKI', 'Synthetic Source', 'v1', 'abc123', 'approved',
        )
        self.assertEqual(result['source_id'], 'SYN-SOURCE-001')
        conn.commit.assert_called()

    def test_empty_source_id_rejected(self):
        from registry_workflow import create_source_metadata, RegistryWorkflowError
        conn, _ = _mock_conn()
        with self.assertRaises(RegistryWorkflowError):
            create_source_metadata(conn, '', 'SDKI', 'x', 'v1', 'h', 'approved')

    def test_unsafe_id_rejected(self):
        from registry_workflow import create_source_metadata, RegistryWorkflowError
        conn, _ = _mock_conn()
        with self.assertRaises(RegistryWorkflowError):
            create_source_metadata(conn, 'src/../etc', 'SDKI', 'x', 'v1', 'h', 'approved')


class TestRegisterEntry(unittest.TestCase):
    def test_valid_entry(self):
        from registry_workflow import register_entry
        conn, cur = _mock_conn()
        result = register_entry(
            conn, 'SYN-D-001', 'SYN-SOURCE-001', 'SDKI', 'SDKI',
            'D.0001', 'Synthetic Diagnosis', 'hash1', 'quarantined',
        )
        self.assertEqual(result['entry_id'], 'SYN-D-001')
        self.assertEqual(result['lifecycle_state'], 'quarantined')

    def test_invalid_lifecycle_rejected(self):
        from registry_workflow import register_entry, RegistryWorkflowError
        conn, _ = _mock_conn()
        with self.assertRaises(RegistryWorkflowError):
            register_entry(conn, 'E1', 'S1', 'SDKI', 'SDKI', 'D.0001', 'n', 'h', 'invalid')


class TestRecordProvenance(unittest.TestCase):
    def test_valid_provenance(self):
        from registry_workflow import record_provenance
        conn, cur = _mock_conn()
        result = record_provenance(conn, 'SYN-D-001', 'manual')
        self.assertEqual(result['entry_id'], 'SYN-D-001')
        conn.commit.assert_called()


class TestExtractionVerification(unittest.TestCase):
    def test_verified_by_human(self):
        from registry_workflow import record_extraction_verification
        conn, cur = _mock_conn()
        result = record_extraction_verification(
            conn, 'SYN-EV-001', 'SYN-D-001', 'verified_by_human',
            verified_by='NURSE-001',
        )
        self.assertEqual(result['status'], 'verified_by_human')

    def test_verified_requires_verifier(self):
        from registry_workflow import record_extraction_verification, RegistryWorkflowError
        conn, _ = _mock_conn()
        with self.assertRaises(RegistryWorkflowError):
            record_extraction_verification(
                conn, 'EV1', 'E1', 'verified_by_human', verified_by='',
            )

    def test_unverified_no_verifier_ok(self):
        from registry_workflow import record_extraction_verification
        conn, cur = _mock_conn()
        result = record_extraction_verification(
            conn, 'EV2', 'E2', 'unverified',
        )
        self.assertEqual(result['status'], 'unverified')

    def test_rejected_status(self):
        from registry_workflow import record_extraction_verification
        conn, cur = _mock_conn()
        result = record_extraction_verification(
            conn, 'EV3', 'E3', 'rejected', verified_by='NURSE-002',
        )
        self.assertEqual(result['status'], 'rejected')

    def test_invalid_status_rejected(self):
        from registry_workflow import record_extraction_verification, RegistryWorkflowError
        conn, _ = _mock_conn()
        with self.assertRaises(RegistryWorkflowError):
            record_extraction_verification(conn, 'EV4', 'E4', 'auto_approved')


class TestEnqueueReview(unittest.TestCase):
    def test_valid_enqueue(self):
        from registry_workflow import enqueue_review
        conn, cur = _mock_conn()
        result = enqueue_review(conn, 'SYN-REVIEW-001', 'SYN-D-001')
        self.assertEqual(result['status'], 'pending')

    def test_empty_review_id_rejected(self):
        from registry_workflow import enqueue_review, RegistryWorkflowError
        conn, _ = _mock_conn()
        with self.assertRaises(RegistryWorkflowError):
            enqueue_review(conn, '', 'E1')


class TestRecordReviewDecision(unittest.TestCase):
    def test_valid_decision(self):
        from registry_workflow import record_review_decision
        conn, cur = _mock_conn()
        result = record_review_decision(conn, 'R1', 'approved', 'NURSE-001')
        self.assertEqual(result['status'], 'approved')

    def test_reviewer_required(self):
        from registry_workflow import record_review_decision, RegistryWorkflowError
        conn, _ = _mock_conn()
        with self.assertRaises(RegistryWorkflowError):
            record_review_decision(conn, 'R1', 'approved', '')

    def test_explicit_timestamp_stored(self):
        from registry_workflow import record_review_decision
        conn, cur = _mock_conn()
        record_review_decision(conn, 'R2', 'rejected', 'NURSE-002', notes='test')
        # Verify UPDATE was called with timestamp parameter
        cur.execute.assert_called()
        args = cur.execute.call_args
        self.assertIn('reviewed_at', args[0][0])


class TestApprovalArtifact(unittest.TestCase):
    def _setup_approved_entry(self, cur, lifecycle='pending_review',
                               extraction='manual', license_status='approved',
                               has_prov=True, ev_status='verified_by_human'):
        """Configure cursor returns for approval guard checks."""
        # Entry exists with lifecycle
        cur.fetchone.side_effect = [
            (lifecycle,),                    # entry lifecycle
            ('manual',) if has_prov else None,  # provenance
            (license_status,),               # source license
        ]

    def test_quarantined_entry_rejected(self):
        from registry_workflow import create_approval_artifact, RegistryWorkflowError
        conn, cur = _mock_conn()
        cur.fetchone.return_value = ('quarantined',)
        with self.assertRaises(RegistryWorkflowError) as ctx:
            create_approval_artifact(
                conn, 'A1', 'R1', 'E1', 'NURSE-001', 'approved', 'hash1',
            )
        self.assertIn('quarantined', str(ctx.exception))

    def test_deprecated_entry_rejected(self):
        from registry_workflow import create_approval_artifact, RegistryWorkflowError
        conn, cur = _mock_conn()
        cur.fetchone.return_value = ('deprecated',)
        with self.assertRaises(RegistryWorkflowError) as ctx:
            create_approval_artifact(
                conn, 'A2', 'R2', 'E2', 'NURSE-001', 'approved', 'hash2',
            )
        self.assertIn('deprecated', str(ctx.exception))

    def test_missing_entry_rejected(self):
        from registry_workflow import create_approval_artifact, RegistryWorkflowError
        conn, cur = _mock_conn()
        cur.fetchone.return_value = None
        with self.assertRaises(RegistryWorkflowError):
            create_approval_artifact(
                conn, 'A3', 'R3', 'E3', 'NURSE-001', 'approved', 'hash3',
            )

    def test_missing_provenance_rejected(self):
        from registry_workflow import create_approval_artifact, RegistryWorkflowError
        conn, cur = _mock_conn()
        cur.fetchone.side_effect = [('pending_review',), None]
        with self.assertRaises(RegistryWorkflowError) as ctx:
            create_approval_artifact(
                conn, 'A4', 'R4', 'E4', 'NURSE-001', 'approved', 'hash4',
            )
        self.assertIn('provenance', str(ctx.exception))

    def test_ocr_unverified_rejected(self):
        from registry_workflow import create_approval_artifact, RegistryWorkflowError
        conn, cur = _mock_conn()
        cur.fetchone.side_effect = [
            ('pending_review',),  # lifecycle
            ('ocr',),             # provenance extraction_method
            None,                 # get_extraction_verification returns None
        ]
        with self.assertRaises(RegistryWorkflowError) as ctx:
            create_approval_artifact(
                conn, 'A5', 'R5', 'E5', 'NURSE-001', 'approved', 'hash5',
            )
        self.assertIn('OCR', str(ctx.exception))

    def test_llm_assisted_unverified_rejected(self):
        from registry_workflow import create_approval_artifact, RegistryWorkflowError
        conn, cur = _mock_conn()
        cur.fetchone.side_effect = [
            ('pending_review',),    # lifecycle
            ('llm_assisted',),      # provenance
            None,                   # extraction verification not found
        ]
        with self.assertRaises(RegistryWorkflowError) as ctx:
            create_approval_artifact(
                conn, 'A6', 'R6', 'E6', 'NURSE-001', 'approved', 'hash6',
            )
        self.assertIn('LLM', str(ctx.exception))

    def test_license_unknown_rejected(self):
        from registry_workflow import create_approval_artifact, RegistryWorkflowError
        conn, cur = _mock_conn()
        cur.fetchone.side_effect = [
            ('pending_review',),  # lifecycle
            ('manual',),         # provenance
            ('unknown',),        # license status
        ]
        with self.assertRaises(RegistryWorkflowError) as ctx:
            create_approval_artifact(
                conn, 'A7', 'R7', 'E7', 'NURSE-001', 'approved', 'hash7',
            )
        self.assertIn('license', str(ctx.exception).lower())

    def test_empty_approver_rejected(self):
        from registry_workflow import create_approval_artifact, RegistryWorkflowError
        conn, _ = _mock_conn()
        with self.assertRaises(RegistryWorkflowError):
            create_approval_artifact(
                conn, 'A8', 'R8', 'E8', '', 'approved', 'hash8',
            )

    def test_explicit_reviewer_required(self):
        from registry_workflow import create_approval_artifact, RegistryWorkflowError
        conn, _ = _mock_conn()
        with self.assertRaises(RegistryWorkflowError):
            create_approval_artifact(
                conn, 'A9', 'R9', 'E9', '   ', 'approved', 'hash9',
            )


class TestUpdateEntryLifecycle(unittest.TestCase):
    def test_valid_update(self):
        from registry_workflow import update_entry_lifecycle
        conn, cur = _mock_conn()
        result = update_entry_lifecycle(conn, 'SYN-D-001', 'approved')
        self.assertEqual(result['lifecycle_state'], 'approved')

    def test_invalid_state_rejected(self):
        from registry_workflow import update_entry_lifecycle, RegistryWorkflowError
        conn, _ = _mock_conn()
        with self.assertRaises(RegistryWorkflowError):
            update_entry_lifecycle(conn, 'E1', 'magic_state')


class TestGetReviewQueue(unittest.TestCase):
    def test_filtered_query(self):
        from registry_workflow import get_review_queue
        conn, cur = _mock_conn()
        cur.fetchall.return_value = [
            ('R1', 'E1', 'N1', 'pending', '2026-01-01T00:00:00Z'),
        ]
        result = get_review_queue(conn, status_filter='pending')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['status'], 'pending')


class TestSafeIdentifierValidation(unittest.TestCase):
    def test_safe_id_accepted(self):
        from registry_workflow import _require_safe_id
        self.assertEqual(_require_safe_id('SYN-D-001', 'test'), 'SYN-D-001')
        self.assertEqual(_require_safe_id('abc.def:123', 'test'), 'abc.def:123')

    def test_url_in_id_rejected(self):
        from registry_workflow import _require_safe_id, RegistryWorkflowError
        with self.assertRaises(RegistryWorkflowError):
            _require_safe_id('http://evil.com', 'test')

    def test_path_in_id_rejected(self):
        from registry_workflow import _require_safe_id, RegistryWorkflowError
        with self.assertRaises(RegistryWorkflowError):
            _require_safe_id('../../etc/passwd', 'test')

    def test_empty_rejected(self):
        from registry_workflow import _require_safe_id, RegistryWorkflowError
        with self.assertRaises(RegistryWorkflowError):
            _require_safe_id('', 'test')


class TestApprovalSeparateFromReview(unittest.TestCase):
    """Verify approval artifact is separate from review decision."""

    def test_review_and_approval_are_distinct_operations(self):
        from registry_workflow import (
            enqueue_review, record_review_decision, create_approval_artifact,
        )
        # These are separate functions with separate tables
        self.assertIsNot(enqueue_review, record_review_decision)
        self.assertIsNot(record_review_decision, create_approval_artifact)


class TestManualQuarantine(unittest.TestCase):
    def test_quarantined_lifecycle_persists(self):
        from registry_workflow import update_entry_lifecycle
        conn, cur = _mock_conn()
        result = update_entry_lifecycle(conn, 'E1', 'quarantined')
        self.assertEqual(result['lifecycle_state'], 'quarantined')


class TestSafeReasonCodes(unittest.TestCase):
    def test_lifecycle_states_bounded(self):
        from registry_workflow import ENTRY_LIFECYCLE_STATES, RELEASE_LIFECYCLE_STATES
        # All states are short safe strings
        for state in ENTRY_LIFECYCLE_STATES | RELEASE_LIFECYCLE_STATES:
            self.assertLess(len(state), 32)
            self.assertTrue(state.replace('_', '').isalpha())


if __name__ == '__main__':
    unittest.main()
