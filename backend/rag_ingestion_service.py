from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from rag_chunking import ChunkingConfig, RagChunk, chunk_document
from rag_fixture_loader import SyntheticFixture, load_manifest
from rag_release_service import SyntheticReleaseResult, build_and_activate_synthetic_release
from rag_repository import RagRepository, ensure_core_schema, sha256_hex


class RagIngestionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SyntheticIngestionConfig:
    fixture_root: Path
    max_document_chars: int = 12000
    max_staging_chunks: int = 200
    chunk_target_words: int = 90
    chunk_overlap_words: int = 12
    staging_ttl_seconds: int = 3600


@dataclass(frozen=True)
class SyntheticIngestionResult:
    ingestion_status: str
    run_id: str
    fixture_case_ids: tuple[str, ...]
    document_count: int
    chunk_count: int
    release_id: str
    activation_status: str
    synthetic_only: bool = True
    authority: bool = False
    clinical_use_allowed: bool = False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            'ingestion_status': self.ingestion_status,
            'run_id': self.run_id,
            'fixture_case_id': ','.join(self.fixture_case_ids),
            'document_count': self.document_count,
            'chunk_count': self.chunk_count,
            'release_id': self.release_id,
            'activation_status': self.activation_status,
            'synthetic_only': True,
            'authority': False,
            'clinical_use_allowed': False,
        }


def new_run_prefix() -> str:
    return 'SYN-P9B-' + uuid.uuid4().hex[:12]


def _safe_fragment(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9_-]+', '-', value).strip('-')[:32] or 'fixture'


def _validate_fixture(fixture: SyntheticFixture) -> None:
    if not fixture.synthetic_only or fixture.authority or fixture.clinical_use_allowed:
        raise RagIngestionError('unsafe_fixture_state')
    if fixture.license_status != 'synthetic_only' or fixture.review_status != 'approved_for_synthetic_test':
        raise RagIngestionError('unsafe_fixture_state')


def ingest_synthetic_fixtures(conn, config: SyntheticIngestionConfig, *, prefix: str | None = None) -> SyntheticIngestionResult:
    run_prefix = prefix or new_run_prefix()
    repo = RagRepository(conn)
    ensure_core_schema(conn)
    fixtures = load_manifest(config.fixture_root, max_document_chars=config.max_document_chars)
    if not fixtures:
        raise RagIngestionError('no_synthetic_fixtures')

    source_id = f'{run_prefix}-SRC'
    source_version_id = f'{run_prefix}-VER'
    run_id = f'{run_prefix}-RUN'
    all_content = ''.join(fixture.content for fixture in fixtures)
    version_hash = sha256_hex(all_content)
    all_chunks: list[RagChunk] = []

    try:
        repo.create_source_version(
            source_id=source_id,
            source_version_id=source_version_id,
            title='P9-B generated synthetic fixture pack',
            version_hash=version_hash,
        )
        repo.create_ingestion_run(run_id=run_id, source_version_id=source_version_id)
        chunk_cfg = ChunkingConfig(
            target_words=config.chunk_target_words,
            overlap_words=config.chunk_overlap_words,
            max_chunks=config.max_staging_chunks,
        )
        for fixture in fixtures:
            _validate_fixture(fixture)
            fragment = _safe_fragment(fixture.case_id)
            document_id = f'{run_prefix}-DOC-{fragment}'[:96]
            staging_document_id = f'{run_prefix}-ST-DOC-{fragment}'[:96]
            document_hash = sha256_hex(fixture.content)
            repo.insert_staging_document(
                staging_document_id=staging_document_id,
                run_id=run_id,
                source_version_id=source_version_id,
                document_hash=document_hash,
                title=fixture.title,
                ttl_seconds=config.staging_ttl_seconds,
            )
            chunks = chunk_document(
                fixture.content,
                document_id=document_id,
                source_version_id=source_version_id,
                config=chunk_cfg,
            )
            if len(all_chunks) + len(chunks) > config.max_staging_chunks:
                raise RagIngestionError('too_many_staging_chunks')
            for chunk in chunks:
                staging_chunk_id = f'{run_prefix}-ST-CHUNK-{chunk.chunk_ordinal:04d}-{_safe_fragment(fixture.case_id)}'[:96]
                repo.insert_staging_chunk(
                    staging_chunk_id=staging_chunk_id,
                    staging_document_id=staging_document_id,
                    chunk=chunk,
                )
            repo.promote_document(
                document_id=document_id,
                source_version_id=source_version_id,
                document_hash=document_hash,
                title=fixture.title,
            )
            for chunk in chunks:
                repo.promote_chunk(chunk=chunk)
            all_chunks.extend(chunks)
        release: SyntheticReleaseResult = build_and_activate_synthetic_release(repo, prefix=run_prefix, chunks=all_chunks)
        repo.finish_ingestion_run(run_id=run_id, document_count=len(fixtures), chunk_count=len(all_chunks))
        conn.commit()
        return SyntheticIngestionResult(
            ingestion_status='succeeded',
            run_id=run_id,
            fixture_case_ids=tuple(fixture.case_id for fixture in fixtures),
            document_count=len(fixtures),
            chunk_count=len(all_chunks),
            release_id=release.release_id,
            activation_status=release.activation_status,
        )
    except Exception:
        conn.rollback()
        raise RagIngestionError('synthetic_ingestion_failed')
