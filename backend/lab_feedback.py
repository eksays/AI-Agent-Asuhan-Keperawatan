from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from typing import Callable

FORBIDDEN_FEEDBACK_PATTERNS = (
    re.compile(r"phi[-_ ]canary", re.I),
    re.compile(r"secret[-_ ]canary", re.I),
    re.compile(r"api[_ -]?key", re.I),
    re.compile(r"session[_ -]?token", re.I),
    re.compile(r"otp", re.I),
    re.compile(r"raw\s+(?:prompt|output)", re.I),
    re.compile(r"chain[-_ ]of[-_ ]thought", re.I),
)

class LabFeedbackError(ValueError):
    pass

class LabFeedbackStore:
    def __init__(self, *, ttl_sec: int = 600, max_sessions: int = 128, max_entries_per_session: int = 8, now_func: Callable[[], float] = time.monotonic) -> None:
        self.ttl_sec = max(1, int(ttl_sec))
        self.max_sessions = max(1, int(max_sessions))
        self.max_entries_per_session = max(1, int(max_entries_per_session))
        self._now = now_func
        self._lock = threading.Lock()
        self._records: OrderedDict[str, dict] = OrderedDict()

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def record(self, session_id: str, *, feedback_id: str, rating: str, note: str = "") -> dict[str, object]:
        clean_note = _safe_note(note)
        clean_rating = rating if rating in {"up", "down", "neutral"} else "neutral"
        now = self._now()
        with self._lock:
            self._cleanup_locked(now)
            while session_id not in self._records and len(self._records) >= self.max_sessions:
                self._records.popitem(last=False)
            rec = self._records.setdefault(session_id, {"expires_at": now + self.ttl_sec, "entries": []})
            rec["expires_at"] = now + self.ttl_sec
            entries = rec.setdefault("entries", [])
            entries.append({"feedback_id": feedback_id, "rating": clean_rating, "note_length": len(clean_note)})
            if len(entries) > self.max_entries_per_session:
                del entries[: len(entries) - self.max_entries_per_session]
            self._records.move_to_end(session_id)
            return {"feedback_count": len(entries), "stored": True}

    def recall(self, session_id: str) -> list[dict[str, object]]:
        with self._lock:
            self._cleanup_locked(self._now())
            rec = self._records.get(session_id)
            return list((rec or {}).get("entries", []))

    def _cleanup_locked(self, now: float) -> None:
        for session_id, rec in list(self._records.items()):
            if now >= float(rec.get("expires_at", 0)):
                self._records.pop(session_id, None)

def _safe_note(note: str) -> str:
    text = " ".join(str(note or "").split())[:240]
    if any(pattern.search(text) for pattern in FORBIDDEN_FEEDBACK_PATTERNS):
        raise LabFeedbackError("Synthetic lab feedback contains forbidden content.")
    return text
