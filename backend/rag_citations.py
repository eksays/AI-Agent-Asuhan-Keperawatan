from __future__ import annotations

import html
import re
from dataclasses import dataclass


_TAG_RE = re.compile(r'<[^>]*>')
_SPACE_RE = re.compile(r'\s+')


@dataclass(frozen=True)
class CitationPackage:
    citation_id: str
    chunk_id: str
    document_id: str
    source_version_id: str
    source_title_safe: str
    section_path: str
    chunk_ordinal: int
    chunk_hash: str
    excerpt_plain_text: str
    retrieval_score: float
    synthetic_only: bool
    authority: bool
    clinical_use_allowed: bool
    retrieval_backend: str = 'lexical'

    def as_dict(self) -> dict[str, object]:
        return {
            'citation_id': self.citation_id,
            'chunk_id': self.chunk_id,
            'document_id': self.document_id,
            'source_version_id': self.source_version_id,
            'source_title_safe': self.source_title_safe,
            'section_path': self.section_path,
            'chunk_ordinal': self.chunk_ordinal,
            'chunk_hash': self.chunk_hash,
            'excerpt_plain_text': self.excerpt_plain_text,
            'retrieval_score': self.retrieval_score,
            'synthetic_only': self.synthetic_only,
            'authority': self.authority,
            'clinical_use_allowed': self.clinical_use_allowed,
            'retrieval_backend': self.retrieval_backend,
        }


def plain_excerpt(text: str, max_chars: int) -> str:
    cleaned = html.unescape(text or '')
    cleaned = _TAG_RE.sub(' ', cleaned)
    cleaned = _SPACE_RE.sub(' ', cleaned).strip()
    limit = max(40, min(int(max_chars), 1200))
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip()


def package_citation(row: dict[str, object], *, ordinal: int, max_excerpt_chars: int) -> CitationPackage:
    chunk_id = str(row.get('chunk_id', ''))[:96]
    citation_id = f'CIT-{ordinal:02d}-{chunk_id[:40]}'[:64]
    return CitationPackage(
        citation_id=citation_id,
        chunk_id=chunk_id,
        document_id=str(row.get('document_id', ''))[:96],
        source_version_id=str(row.get('source_version_id', ''))[:96],
        source_title_safe=str(row.get('source_title_safe', ''))[:256],
        section_path=str(row.get('section_path', ''))[:512],
        chunk_ordinal=int(row.get('chunk_ordinal', 0) or 0),
        chunk_hash=str(row.get('chunk_hash', ''))[:64],
        excerpt_plain_text=plain_excerpt(str(row.get('chunk_text', '')), max_excerpt_chars),
        retrieval_score=float(row.get('retrieval_score', 0.0) or 0.0),
        synthetic_only=bool(row.get('synthetic_only', False)),
        authority=bool(row.get('authority', False)),
        clinical_use_allowed=bool(row.get('clinical_use_allowed', False)),
    )
