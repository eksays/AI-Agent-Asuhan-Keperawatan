"""
Telemetri AGREGAT (bukan surveilans individu). Mengumpulkan metrik sistem real-time untuk
Dasbor Eksekutif: throughput, success rate, latensi, distribusi routing model (CFO), estimasi token & biaya.
Tidak menyimpan PHI, isi prompt, atau perilaku per-perawat.
"""
from __future__ import annotations
import threading, time
from collections import deque, defaultdict

_lock = threading.Lock()
_start = time.time()
_counts: dict[str, int] = defaultdict(int)
_tier: dict[str, int] = defaultdict(int)
_agent: dict[str, int] = defaultdict(int)
_lat = deque(maxlen=3000)        # latensi request (ms)
_req_times = deque(maxlen=50000)  # timestamp untuk hitung per-jam
_tokens = 0
_cache_hits = 0

# Tarif estimasi (Rp per token) — perkiraan kasar untuk visualisasi biaya, bukan tagihan riil.
_RP_PER_TOKEN = 0.00006


def record_request(status: int, latency_ms: float) -> None:
    with _lock:
        _counts["requests"] += 1
        if status >= 500:
            _counts["err5xx"] += 1
        elif status in (401, 403, 409):
            _counts["denied"] += 1
        _lat.append(latency_ms)
        _req_times.append(time.time())


def record_job(agent: str, tier: str, ok: bool, tokens: int = 0, doc: bool = False) -> None:
    global _tokens
    with _lock:
        _counts["jobs"] += 1
        _counts["jobs_ok" if ok else "jobs_fail"] += 1
        _tier[(tier or "?").lower()] += 1
        _agent[(agent or "?").lower()] += 1
        _tokens += max(0, int(tokens or 0))
        if doc:
            _counts["docs"] += 1


def record_cache_hit(n: int = 1) -> None:
    global _cache_hits
    with _lock:
        _cache_hits += max(0, int(n))


def snapshot() -> dict:
    with _lock:
        now = time.time()
        last_hour = sum(1 for t in _req_times if t > now - 3600)
        lat = sorted(_lat)
        p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else 0.0
        avg = sum(_lat) / len(_lat) if _lat else 0.0
        jobs = _counts["jobs"]
        ok = _counts["jobs_ok"]
        return {
            "uptime_s": int(now - _start),
            "requests": _counts["requests"],
            "req_last_hour": last_hour,
            "denied": _counts["denied"],
            "err5xx": _counts["err5xx"],
            "jobs": jobs,
            "jobs_ok": ok,
            "success_rate": round(100.0 * ok / jobs, 1) if jobs else 100.0,
            "docs_processed": _counts["docs"],
            "latency_ms": {"avg": round(avg, 1), "p95": round(float(p95), 1)},
            "routing": dict(_tier),       # CFO: distribusi flash/medium/pro (dynamic routing)
            "agents": dict(_agent),
            "tokens_est": _tokens,
            "biaya_est_rp": round(_tokens * _RP_PER_TOKEN, 2),
            "cache_hits": _cache_hits,    # jurnal disajikan dari cache bersama (hemat panggilan)
        }
