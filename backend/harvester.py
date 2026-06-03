"""
Scheduled Knowledge Harvester — penjadwal aman (stdlib, daemon thread; tanpa Celery).
Secara berkala (default mingguan) menarik jurnal open-access dari database publik (PubMed/Europe PMC)
untuk sekumpulan TOPIK benih keperawatan, lalu MENGHANGATKAN cache jurnal bersama (ebp_memory) yang
dipakai Agen Referensi sebagai RAG tambahan. TIDAK mengubah kode aplikasi.

Konfigurasi via env:
  HARVEST_INTERVAL_SEC  (default 604800 = 1 minggu; <=0 menonaktifkan)
  HARVEST_TOPICS        (dipisah koma)
"""
from __future__ import annotations
import os, threading, time
import ebp

_INTERVAL = int(os.environ.get("HARVEST_INTERVAL_SEC", str(7 * 24 * 3600)))
_TOPICS = [t.strip() for t in os.environ.get(
    "HARVEST_TOPICS",
    "nursing care plan,pressure injury prevention,fall prevention elderly,"
    "pain management nursing intervention,diabetes self management education,"
    "post operative wound care nursing,patient education hypertension"
).split(",") if t.strip()]


def run_once(audit=None) -> int:
    total = 0
    for topic in _TOPICS:
        try:
            arts, _tier = ebp.retrieve(topic, topic)   # hangatkan cache jurnal bersama (RAG)
            total += len(arts or [])
            if audit:
                audit("-", "KnowledgeHarvest", f"OK:{topic[:30]}:{len(arts or [])}")
        except Exception:
            if audit:
                audit("-", "KnowledgeHarvest", "Fail")
        time.sleep(2)   # sopan ke API publik
    return total


def start(audit=None) -> bool:
    if _INTERVAL <= 0:
        return False

    def _loop():
        while True:
            time.sleep(_INTERVAL)
            run_once(audit)

    threading.Thread(target=_loop, daemon=True, name="knowledge-harvester").start()
    return True
