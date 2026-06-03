"""
Chaos Monkey — penguji keamanan DINAMIS (OPT-IN, dijalankan MANUAL terhadap instance lokal).

Mengirim serangan SIMULASI ke backend lalu MEMASTIKAN server MENOLAKnya (bukan HTTP 200 sukses).
Bila server merespons 200 terhadap serangan -> "CRITICAL ALERT: CHAOS MONKEY BREACHED THE SYSTEM!".

Jalankan:
    python chaos_monkey.py            # satu siklus uji, exit 1 bila ada breach (cocok untuk CI/cron)
    python chaos_monkey.py --loop     # ulang tiap jam (opsional)

CATATAN: skrip ini TERISOLASI — BUKAN bagian dari runtime FastAPI dan tidak berjalan otomatis di server.
"""
import os, sys, time, secrets, urllib.request, urllib.error, urllib.parse

BASE = os.environ.get("CDSS_API_BASE", "http://127.0.0.1:8000")
_breaches = 0


def _post(path, fields, headers=None):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(BASE + path, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:   # nosec B310 - alat uji ke host lokal
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def _get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as r:   # nosec B310 - alat uji ke host lokal
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def _check(name, status):
    global _breaches
    ok = status != 200                                   # serangan TIDAK BOLEH berhasil (200)
    print(f"[{'OK  ' if ok else 'FAIL'}] {name} -> HTTP {status}")
    if not ok:
        _breaches += 1
        print("  !!! CRITICAL ALERT: CHAOS MONKEY BREACHED THE SYSTEM!", file=sys.stderr)


def run_cycle():
    global _breaches
    _breaches = 0
    print(f"== Chaos Monkey @ {time.strftime('%Y-%m-%d %H:%M:%S')} (target {BASE}) ==")
    fake_sid = secrets.token_hex(16)
    _check("Fake/random session_id ke /chat",
           _post("/chat", {"provider": "openai", "model": "gpt-4o", "session_id": fake_sid,
                           "agent": "analisis", "pertanyaan": "halo"}, {"Authorization": "Bearer palsu-123"}))
    _check("SQLi/XSS payload ke /feedback",
           _post("/feedback", {"framework": "3S", "session_id": fake_sid, "pertanyaan": "1' OR '1'='1",
                               "jawaban": "<script>alert(1)</script>", "rating": "down", "koreksi": "DROP TABLE users;--"}))
    _check("Path-traversal/RCE pada URL", _get("/daftar/..%2f..%2fetc%2fpasswd"))
    _check("Erasure dengan session_id acak", _post("/delete_my_data", {"session_id": secrets.token_hex(16)}))
    print(f"== Selesai: {_breaches} BREACH terdeteksi ==\n")
    return _breaches


if __name__ == "__main__":
    if "--loop" not in sys.argv:
        sys.exit(1 if run_cycle() else 0)
    while True:
        run_cycle()
        time.sleep(3600)
