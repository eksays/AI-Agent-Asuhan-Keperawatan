"""Phase 9 P9-C - Deterministic synthetic vector generator.

This module provides a deterministic vector generator using SHA-256 hashing.
It generates bounded, unit-normalized vectors of a fixed dimension (8) for
synthetic chunk testing.

THIS IS A NON-CLINICAL TEST FIXTURE MECHANISM ONLY.
IT IS NOT A SEMANTIC EMBEDDING MODEL.
IT MUST NEVER BE USED FOR PATIENT-CARE CLAIMS OR PRODUCTION RETRIEVAL.
"""
from __future__ import annotations

import hashlib
import math


SYNTHETIC_MODEL_ID = "synthetic-hash-vector-v1"
SYNTHETIC_DIMENSION = 8
MAX_SYNTHETIC_VECTOR_TEXT_CHARS = 4096


class SyntheticVectorError(ValueError):
    pass


def _validate_synthetic_text(text: str) -> str:
    if not isinstance(text, str):
        raise SyntheticVectorError("synthetic_vector_text_required")
    if not text.strip():
        raise SyntheticVectorError("synthetic_vector_text_empty")
    if len(text) > MAX_SYNTHETIC_VECTOR_TEXT_CHARS:
        raise SyntheticVectorError("synthetic_vector_text_too_large")
    for char in text:
        code = ord(char)
        if code == 0 or (code < 32 and char not in {'\t', '\n'}):
            raise SyntheticVectorError("synthetic_vector_text_unsafe_control")
    return text


def generate_synthetic_vector(text: str) -> list[float]:
    """
    Generate a deterministic, unit-normalized 8-dimensional vector from text
    using SHA-256. This is purely test plumbing.
    """
    text = _validate_synthetic_text(text)

    text_bytes = text.encode("utf-8")
    hash_obj = hashlib.sha256(text_bytes)
    digest = hash_obj.digest()

    # We need 8 floats. Digest is 32 bytes. We can take 4 bytes per float.
    # We will interpret each 4 bytes as a 32-bit signed integer and scale it to [-1, 1].
    vector = []
    for i in range(SYNTHETIC_DIMENSION):
        # Interpret 4 bytes as a big-endian signed integer
        val = int.from_bytes(digest[i * 4:(i + 1) * 4], byteorder='big', signed=True)
        # Max positive int32 is 2147483647
        vector.append(val / 2147483648.0)

    # L2 Normalization (unit-normalized)
    magnitude = math.sqrt(sum(v * v for v in vector))
    if magnitude == 0:
        return [0.0] * SYNTHETIC_DIMENSION

    return [v / magnitude for v in vector]
