"use client";
import { useState, useEffect, useCallback } from "react";

// Dasbor Eksekutif Direktur — rute SAH (bukan pintu rahasia), dijaga MFA/TOTP.
// Tema "Bloomberg Terminal": True Black + hijau neon + amber, monospace, kepadatan data tinggi.
const API = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8000";
const SS = "cdss-director";

interface Metrics {
  uptime_s: number; requests: number; req_last_hour: number; denied: number; err5xx: number;
  jobs: number; jobs_ok: number; success_rate: number; docs_processed: number;
  latency_ms: { avg: number; p95: number }; routing: Record<string, number>; agents: Record<string, number>;
  tokens_est: number; biaya_est_rp: number; cache_hits: number; knowledge?: Record<string, number>;
}

const fmt = (n: number) => (n ?? 0).toLocaleString("id-ID");
const dur = (s: number) => { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return `${h}j ${m}m`; };

function Cell({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="border border-[#00FF00]/25 bg-[#00FF00]/[0.03] px-3 py-2">
      <div className="text-[0.6rem] uppercase tracking-widest text-[#00FF00]/50">{label}</div>
      <div className={`mt-0.5 text-xl font-bold tabular-nums ${accent ? "text-[#FFBF00]" : "text-[#00FF00]"}`}>{value}</div>
    </div>
  );
}

function Bars({ title, data }: { title: string; data: Record<string, number> }) {
  const entries = Object.entries(data || {});
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <div className="border border-[#00FF00]/25 bg-[#00FF00]/[0.03] p-3">
      <div className="mb-2 text-[0.6rem] uppercase tracking-widest text-[#00FF00]/50">{title}</div>
      {entries.length === 0 && <div className="text-xs text-[#00FF00]/40">—</div>}
      {entries.map(([k, v]) => (
        <div key={k} className="mb-1 flex items-center gap-2 text-xs">
          <span className="w-20 shrink-0 truncate uppercase text-[#00FF00]/70">{k}</span>
          <span className="h-2 flex-1 bg-[#00FF00]/10"><span className="block h-2 bg-[#FFBF00]" style={{ width: `${(v / max) * 100}%` }} /></span>
          <span className="w-10 shrink-0 text-right tabular-nums text-[#FFBF00]">{fmt(v)}</span>
        </div>
      ))}
    </div>
  );
}

export default function DirectorDashboard() {
  const [token, setToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const [m, setM] = useState<Metrics | null>(null);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => { try { const t = sessionStorage.getItem(SS); if (active && t) setToken(t); } catch {} });
    return () => { active = false; };
  }, []);

  const login = async (e: React.FormEvent) => {
    e.preventDefault(); setErr("");
    try {
      const fd = new FormData(); fd.append("code", code.trim());
      const r = await fetch(`${API}/director/login`, { method: "POST", body: fd });
      const d = await r.json();
      if (d.status === "sukses" && d.director_token) { setToken(d.director_token); try { sessionStorage.setItem(SS, d.director_token); } catch {} }
      else setErr(d.pesan || "Otentikasi gagal.");
    } catch { setErr("Tidak dapat terhubung ke server backend."); }
  };

  const poll = useCallback(async () => {
    if (!token) return;
    try {
      const r = await fetch(`${API}/director/metrics`, { headers: { Authorization: `Bearer ${token}` } });
      if (r.status === 401) { setToken(null); try { sessionStorage.removeItem(SS); } catch {} return; }
      setM((await r.json()) as Metrics);
    } catch {}
  }, [token]);

  useEffect(() => {
    if (!token) return;
    const first = setTimeout(() => { void poll(); }, 0);
    const i = setInterval(poll, 3000);
    return () => { clearTimeout(first); clearInterval(i); };
  }, [token, poll]);

  if (!token) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-black font-mono text-[#00FF00]">
        <form onSubmit={login} className="w-full max-w-sm border border-[#00FF00]/30 p-6">
          <div className="text-sm uppercase tracking-[0.3em] text-[#FFBF00]">Singularity Command</div>
          <div className="mt-1 text-[0.7rem] text-[#00FF00]/50">DIRECTOR ACCESS — MFA REQUIRED (TOTP)</div>
          <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoFocus placeholder="6-DIGIT CODE"
            className="mt-5 w-full border border-[#00FF00]/40 bg-black px-3 py-2 text-center text-2xl tracking-[0.5em] tabular-nums text-[#00FF00] outline-none focus:border-[#FFBF00]" />
          {err && <div className="mt-2 text-xs text-red-400">{err}</div>}
          <button type="submit" className="mt-4 w-full border border-[#00FF00] bg-[#00FF00]/10 py-2 text-sm font-bold uppercase tracking-widest hover:bg-[#00FF00]/20">Authenticate</button>
          <div className="mt-4 text-[0.6rem] leading-relaxed text-[#00FF00]/40">Pindai otpauth:// URI (dari konsol server saat start, atau /director/enroll dgn DIRECTOR_BOOTSTRAP) ke aplikasi authenticator.</div>
        </form>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-black p-3 font-mono text-[#00FF00] sm:p-5">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2 border-b border-[#00FF00]/30 pb-2">
        <div className="text-sm uppercase tracking-[0.3em] text-[#FFBF00]">CDSS · SINGULARITY COMMAND CENTER</div>
        <div className="text-[0.65rem] text-[#00FF00]/50">UPTIME {m ? dur(m.uptime_s) : "—"} · LIVE 3s · <button onClick={() => { setToken(null); try { sessionStorage.removeItem(SS); } catch {} }} className="underline hover:text-[#FFBF00]">LOGOUT</button></div>
      </header>

      {!m ? <div className="text-[#00FF00]/50">Memuat telemetri…</div> : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <Cell label="Req / Jam" value={fmt(m.req_last_hour)} />
            <Cell label="Total Job" value={fmt(m.jobs)} />
            <Cell label="Success Rate" value={`${m.success_rate}%`} accent />
            <Cell label="Latensi avg" value={`${m.latency_ms.avg} ms`} />
            <Cell label="Latensi p95" value={`${m.latency_ms.p95} ms`} />
            <Cell label="Dokumen Diproses" value={fmt(m.docs_processed)} />
            <Cell label="Token (est)" value={fmt(m.tokens_est)} />
            <Cell label="Biaya (est)" value={`Rp ${fmt(m.biaya_est_rp)}`} accent />
            <Cell label="Cache Hit (jurnal)" value={fmt(m.cache_hits)} />
            <Cell label="Akses Ditolak" value={fmt(m.denied)} accent />
            <Cell label="Error 5xx" value={fmt(m.err5xx)} />
            <Cell label="Jurnal RAG" value={fmt((m.knowledge?.ebp_jurnal_tersimpan ?? 0))} />
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            <Bars title="CFO · Dynamic Routing (model tier)" data={m.routing} />
            <Bars title="Distribusi Divisi (agen)" data={m.agents} />
          </div>
          <div className="text-[0.6rem] text-[#00FF00]/40">Telemetri AGREGAT (tanpa PHI / tanpa pelacakan ketikan individu). Biaya & token bersifat ESTIMASI.</div>
        </div>
      )}
    </main>
  );
}
