from __future__ import annotations

from dataclasses import dataclass

from rag_repository import RagRepository, sha256_hex


@dataclass(frozen=True)
class SyntheticReleaseResult:
    release_id: str
    release_hash: str
    chunk_count: int
    activation_status: str


def build_and_activate_synthetic_release(repo: RagRepository, *, prefix: str, chunks: list) -> SyntheticReleaseResult:
    if not chunks:
        raise ValueError('no_approved_synthetic_chunks')
    if not all(chunk.synthetic_only and not chunk.authority and not chunk.clinical_use_allowed for chunk in chunks):
        raise ValueError('unsafe_fixture_state')
    release_id = f'{prefix}-REL'
    release_hash = sha256_hex('|'.join(chunk.chunk_hash for chunk in chunks))
    repo.create_release(
        release_id=release_id,
        release_version=f'{prefix}-synthetic-lexical-v1',
        release_hash=release_hash,
        chunks=chunks,
    )
    repo.activate_release(release_id=release_id)
    return SyntheticReleaseResult(
        release_id=release_id,
        release_hash=release_hash,
        chunk_count=len(chunks),
        activation_status='active_synthetic_only',
    )
