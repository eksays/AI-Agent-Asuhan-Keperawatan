"""Phase 10 P10-A1 - Governed Corpus Ingestion Service.

This service validates intake metadata and returns bounded status and decision events.
It executes entirely in-memory for P10-A1 and avoids database writes, network calls,
or external provider interaction.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple

from config import AppConfig
from rag_intake_policy import (
    IntakeReason,
    IntakeStatus,
    validate_intake_metadata,
)


class IntakeServiceError(RuntimeError):
    pass


class IngestionDecisionEvent(NamedTuple):
    event_id: str
    source_id: str
    status: str
    reason_code: str
    created_by_actor_ref: str
    quarantine_reason_code: str
    cleanup_after: datetime | None
    created_at: datetime


class IngestionIntakeResult(NamedTuple):
    status: IntakeStatus
    reason_code: IntakeReason
    decision_event: IngestionDecisionEvent | None


class RagIntakeService:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg

    def process_metadata_submission(
        self,
        metadata: dict[str, Any],
        *,
        body_payload: str | None = None,
        excerpt_payload: str | None = None,
    ) -> IngestionIntakeResult:
        """Process a metadata-only corpus ingestion submission."""
        # 1. Enforce AppConfig default-off gating
        if not self.cfg.rag_corpus_intake_enabled:
            raise IntakeServiceError("Corpus intake service is disabled by configuration.")

        # Hard blocks on safety configurations
        if self.cfg.app_mode != "clinical_sandbox":
            raise IntakeServiceError("Corpus intake is allowed only in clinical_sandbox mode.")
        if self.cfg.rag_runtime_mode != "synthetic_corpus_test":
            raise IntakeServiceError("Corpus intake is allowed only in synthetic_corpus_test runtime mode.")
        if self.cfg.registry_activation_enabled:
            raise IntakeServiceError("Corpus intake is forbidden when registry activation is true.")
        if self.cfg.rag_body_storage_enabled:
            raise IntakeServiceError("RAG body storage is forbidden during metadata intake.")
        if self.cfg.rag_real_corpus_ingestion_enabled:
            raise IntakeServiceError("Real corpus ingestion is forbidden during metadata intake.")
        if self.cfg.rag_corpus_promotion_enabled:
            raise IntakeServiceError("RAG clinical use promotion is forbidden during metadata intake.")

        # 2. Reject body/excerpt payloads if passed
        if body_payload is not None:
            return IngestionIntakeResult(
                IntakeStatus.REJECT,
                IntakeReason.REJECT_BODY_STORAGE_FORBIDDEN,
                None,
            )
        if excerpt_payload is not None:
            return IngestionIntakeResult(
                IntakeStatus.REJECT,
                IntakeReason.REJECT_BODY_STORAGE_FORBIDDEN,
                None,
            )

        # 3. Validate metadata via policy module
        status, reason_code, validated = validate_intake_metadata(metadata)
        if status == IntakeStatus.REJECT or not validated:
            return IngestionIntakeResult(status, reason_code, None)

        # 4. Calculate cleanup time if quarantined
        cleanup_after: datetime | None = None
        quarantine_reason = ""
        now = datetime.now(timezone.utc)

        if status == IntakeStatus.QUARANTINE:
            if not self.cfg.rag_corpus_quarantine_enabled:
                # If quarantine is disabled, reject review-required documents
                return IngestionIntakeResult(
                    IntakeStatus.REJECT,
                    IntakeReason.REJECT_INVALID_METADATA,
                    None,
                )
            quarantine_reason = validated.get("quarantine_reason_code", "quarantine_review_required")
            ttl_hours = max(1, min(self.cfg.rag_quarantine_metadata_ttl_hours, 168))
            cleanup_after = now + timedelta(hours=ttl_hours)

        # 5. Emit metadata-only decision event object
        event_id = f"EVT-INTAKE-{uuid.uuid4().hex[:12]}"
        decision_event = IngestionDecisionEvent(
            event_id=event_id,
            source_id=validated["source_id"],
            status=status.value,
            reason_code=reason_code.value,
            created_by_actor_ref=validated.get("created_by_actor_ref", "opaque_local_sandbox_actor_id"),
            quarantine_reason_code=quarantine_reason,
            cleanup_after=cleanup_after,
            created_at=now,
        )

        return IngestionIntakeResult(status, reason_code, decision_event)
