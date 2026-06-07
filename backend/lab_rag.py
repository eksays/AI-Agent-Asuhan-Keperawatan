from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from lab_fixture_loader import LabFixtureError, SyntheticFixtureLoader

TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
MAX_TOP_K = 5

@dataclass(frozen=True)
class LabRagResult:
    fixture_id: str
    corpus_version: str
    retrieved_document_ids: list[str]
    retrieval_scores: list[float]
    weak_context: bool
    retrieval_source: str = "synthetic_fixture_lexical"

def normalize_tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text or "") if len(token) > 2}

def retrieve_synthetic_context(
    loader: SyntheticFixtureLoader,
    *,
    fixture_id: str,
    query: str,
    top_k: int = 3,
) -> LabRagResult:
    corpus = loader.load_fixture_by_id(fixture_id, prefix="rag/")
    documents = corpus.get("documents")
    if not isinstance(documents, list) or not documents:
        raise LabFixtureError("Synthetic RAG corpus is empty.")
    query_tokens = normalize_tokens(query)
    bounded_top_k = max(1, min(int(top_k or 3), MAX_TOP_K))
    scored: list[tuple[float, str]] = []
    for item in documents:
        if not isinstance(item, dict):
            continue
        document_id = str(item.get("document_id") or "")
        if not document_id.startswith("SYN-DOC-"):
            continue
        haystack = " ".join(str(item.get(key) or "") for key in ("title", "body", "tags"))
        doc_tokens = normalize_tokens(haystack)
        overlap = len(query_tokens & doc_tokens)
        score = round(overlap / max(len(query_tokens), 1), 3) if query_tokens else 0.0
        scored.append((score, document_id))
    ranked = sorted(scored, key=lambda row: (-row[0], row[1]))[:bounded_top_k]
    positive = [(score, doc_id) for score, doc_id in ranked if score > 0]
    weak = not positive
    selected = positive if positive else ranked[:1]
    return LabRagResult(
        fixture_id=fixture_id,
        corpus_version=str(corpus.get("fixture_version") or ""),
        retrieved_document_ids=[doc_id for _score, doc_id in selected],
        retrieval_scores=[score for score, _doc_id in selected],
        weak_context=weak,
    )

def rag_payload(result: LabRagResult) -> dict[str, Any]:
    return {
        "retrieved_document_ids": result.retrieved_document_ids,
        "retrieval_scores": result.retrieval_scores,
        "retrieval_source": result.retrieval_source,
        "corpus_version": result.corpus_version,
        "weak_context": result.weak_context,
    }
