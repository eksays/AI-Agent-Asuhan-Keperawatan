"""
Scheduled Knowledge Harvester.

The application default is off. Startup must pass an explicit interval and topic
list from config.py before this module starts any background network activity.
"""
from __future__ import annotations

import threading
import time

import ebp


_started = False
_lock = threading.Lock()


def run_once(audit=None, topics: tuple[str, ...] = ()) -> int:
    total = 0
    for topic in topics:
        try:
            arts, _tier = ebp.retrieve(topic, topic)
            total += len(arts or [])
            if audit:
                audit("-", "KnowledgeHarvest", f"OK:{topic[:30]}:{len(arts or [])}")
        except Exception:
            if audit:
                audit("-", "KnowledgeHarvest", "Fail")
        time.sleep(2)
    return total


def start(audit=None, interval: int = 0, topics: tuple[str, ...] = ()) -> bool:
    global _started
    if interval <= 0 or not topics:
        return False

    with _lock:
        if _started:
            return True
        _started = True

        def _loop():
            while True:
                time.sleep(interval)
                run_once(audit, topics)

        threading.Thread(target=_loop, daemon=True, name="knowledge-harvester").start()
        return True
