from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass


CHUNKING_PROFILE = 'synthetic-lexical-v1'
_SPACE_RE = re.compile(r'[ \t]+')
_BLANK_RE = re.compile(r'\n{3,}')
_HEADING_RE = re.compile(r'^(#{1,4})\s+(.+)$')
_LIST_RE = re.compile(r'^\s*(?:[-*]|\d+[.)])\s+')
_TABLE_RE = re.compile(r'^\s*\|.*\|\s*$')


class RagChunkingError(ValueError):
    pass


@dataclass(frozen=True)
class ChunkingConfig:
    target_words: int = 90
    overlap_words: int = 12
    max_chunks: int = 200
    language_code: str = 'id'
    fts_config_code: str = 'simple'

    def bounded(self) -> 'ChunkingConfig':
        target = max(40, min(int(self.target_words), 300))
        overlap = max(0, min(int(self.overlap_words), min(60, target // 2)))
        max_chunks = max(1, min(int(self.max_chunks), 1000))
        language = self.language_code if self.language_code in {'id', 'en'} else 'id'
        return ChunkingConfig(target, overlap, max_chunks, language, 'simple')


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    document_id: str
    source_version_id: str
    section_path: str
    chunk_ordinal: int
    chunk_hash: str
    chunk_text: str
    word_count: int
    language_code: str
    fts_config_code: str
    retrieval_eligible: bool
    synthetic_only: bool
    authority: bool
    clinical_use_allowed: bool
    chunking_profile: str = CHUNKING_PROFILE


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize('NFKC', text or '')
    normalized = normalized.replace('\x00', '')
    normalized = normalized.replace('\r\n', '\n').replace('\r', '\n')
    for char in normalized:
        code = ord(char)
        if code < 32 and char not in {'\n', '\t'}:
            raise RagChunkingError('unsafe_control_character')
    lines = [_SPACE_RE.sub(' ', line).strip() for line in normalized.split('\n')]
    compact = '\n'.join(lines)
    compact = _BLANK_RE.sub('\n\n', compact).strip()
    if not compact:
        raise RagChunkingError('empty_document')
    return compact


def _section_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    heading_stack: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        body = '\n'.join(buffer).strip()
        if body:
            path = ' > '.join(heading_stack) if heading_stack else 'root'
            blocks.append((path, body))
        buffer = []

    lines = text.split('\n')
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        heading = _HEADING_RE.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()[:120]
            heading_stack = heading_stack[: level - 1] + [title]
            idx += 1
            continue
        if not line.strip():
            flush()
            idx += 1
            continue
        group = [line]
        predicate = None
        if _LIST_RE.match(line):
            predicate = _LIST_RE
        elif _TABLE_RE.match(line):
            predicate = _TABLE_RE
        if predicate is not None:
            idx += 1
            while idx < len(lines) and predicate.match(lines[idx]):
                group.append(lines[idx])
                idx += 1
            buffer.extend(group)
            flush()
            continue
        buffer.append(line)
        idx += 1
    flush()
    return blocks


def _split_words(text: str, target: int, overlap: int) -> list[str]:
    words = text.split()
    if len(words) <= target:
        return [text]
    pieces: list[str] = []
    step = max(1, target - overlap)
    start = 0
    while start < len(words):
        piece = ' '.join(words[start : start + target]).strip()
        if piece:
            pieces.append(piece)
        if start + target >= len(words):
            break
        start += step
    return pieces


def _safe_id_fragment(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9_-]+', '-', value).strip('-')[:36] or 'chunk'


def chunk_document(
    text: str,
    *,
    document_id: str,
    source_version_id: str,
    config: ChunkingConfig | None = None,
) -> list[RagChunk]:
    cfg = (config or ChunkingConfig()).bounded()
    normalized = normalize_text(text)
    chunks: list[RagChunk] = []
    seen_hashes: set[str] = set()
    ordinal = 0
    for section_path, block in _section_blocks(normalized):
        for piece in _split_words(block, cfg.target_words, cfg.overlap_words):
            words = piece.split()
            if not words:
                continue
            chunk_hash = hashlib.sha256(piece.encode('utf-8')).hexdigest()
            if chunk_hash in seen_hashes:
                continue
            seen_hashes.add(chunk_hash)
            source_material = f'{source_version_id}|{section_path}|{ordinal}|{chunk_hash}'
            suffix = hashlib.sha256(source_material.encode('utf-8')).hexdigest()[:20]
            chunk_id = f'{_safe_id_fragment(source_version_id)}-CHK-{ordinal:04d}-{suffix}'[:96]
            chunks.append(
                RagChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    source_version_id=source_version_id,
                    section_path=section_path[:512],
                    chunk_ordinal=ordinal,
                    chunk_hash=chunk_hash,
                    chunk_text=piece,
                    word_count=len(words),
                    language_code=cfg.language_code,
                    fts_config_code=cfg.fts_config_code,
                    retrieval_eligible=True,
                    synthetic_only=True,
                    authority=False,
                    clinical_use_allowed=False,
                )
            )
            ordinal += 1
            if len(chunks) > cfg.max_chunks:
                raise RagChunkingError('too_many_chunks')
    if not chunks:
        raise RagChunkingError('empty_chunks')
    return chunks
