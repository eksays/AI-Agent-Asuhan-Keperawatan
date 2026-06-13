"use client";
/**
 * CDSS AI Keperawatan — landing page.
 * Faithful implementation of the Stitch screen "Yosy Project AI Identity Edition"
 * (clinical-noir monochrome palette). All CTAs call `onGetStarted`, which opens the
 * API-key login dialog owned by the Welcome shell.
 */
import { useEffect, useRef } from "react";
import { ArrowRight, Workflow, ScanText, Network, FlaskConical, ShieldCheck, Globe, Languages } from "lucide-react";

interface LandingPageProps {
  onGetStarted: () => void;
}

const NAV_LINKS = ["Fitur", "Cara Kerja", "Standar", "Keamanan", "EBP"];
const LLM_BADGES = ["CLAUDE 3.5 OPUS", "GPT-4O", "GEMINI 1.5 PRO", "LLAMA 3 70B"];

/** Interactive constellation — monochrome particles that drift and repel from the cursor. */
function useHeroParticles() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const cnv = canvas;
    const c = ctx;
    const COLORS = ["#c6c6c6", "#e4e2e0", "#8e9192"];
    const mouse: { x: number | null; y: number | null; radius: number } = { x: null, y: null, radius: 150 };
    let raf = 0;

    class Particle {
      x = Math.random() * cnv.width;
      y = Math.random() * cnv.height;
      size = Math.random() * 2 + 0.5;
      density = Math.random() * 30 + 1;
      color = COLORS[Math.floor(Math.random() * COLORS.length)];
      vx = (Math.random() - 0.5) * 0.4;
      vy = (Math.random() - 0.5) * 0.4;

      draw() {
        c.fillStyle = this.color;
        c.beginPath();
        c.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        c.fill();
      }

      update() {
        this.x += this.vx;
        this.y += this.vy;
        if (this.x < 0 || this.x > cnv.width) this.vx = -this.vx;
        if (this.y < 0 || this.y > cnv.height) this.vy = -this.vy;
        if (mouse.x != null && mouse.y != null) {
          const dx = mouse.x - this.x;
          const dy = mouse.y - this.y;
          const dist = Math.hypot(dx, dy);
          if (dist < mouse.radius && dist > 0) {
            const force = (mouse.radius - dist) / mouse.radius;
            this.x -= (dx / dist) * force * this.density;
            this.y -= (dy / dist) * force * this.density;
          }
        }
      }
    }

    let particles: Particle[] = [];
    const initParticles = () => {
      particles = [];
      const count = Math.min((cnv.width * cnv.height) / 12000, 150);
      for (let i = 0; i < count; i++) particles.push(new Particle());
    };

    const animate = () => {
      c.clearRect(0, 0, cnv.width, cnv.height);
      for (const p of particles) {
        p.update();
        p.draw();
      }
      c.lineWidth = 0.5;
      for (let a = 0; a < particles.length; a++) {
        for (let b = a + 1; b < particles.length; b++) {
          const dx = particles[a].x - particles[b].x;
          const dy = particles[a].y - particles[b].y;
          const d2 = dx * dx + dy * dy;
          if (d2 < 12000) {
            c.strokeStyle = `rgba(198, 198, 198, ${(1 - d2 / 12000) * 0.2})`;
            c.beginPath();
            c.moveTo(particles[a].x, particles[a].y);
            c.lineTo(particles[b].x, particles[b].y);
            c.stroke();
          }
        }
      }
      raf = requestAnimationFrame(animate);
    };

    const onMove = (e: MouseEvent) => {
      const rect = wrap.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
    };
    const onLeave = () => {
      mouse.x = null;
      mouse.y = null;
    };
    wrap.addEventListener("mousemove", onMove);
    wrap.addEventListener("mouseleave", onLeave);

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        cnv.width = entry.contentRect.width;
        cnv.height = entry.contentRect.height;
        initParticles();
      }
    });
    ro.observe(wrap);

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduceMotion) animate();
    else {
      initParticles();
      for (const p of particles) p.draw();
    }

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      wrap.removeEventListener("mousemove", onMove);
      wrap.removeEventListener("mouseleave", onLeave);
    };
  }, []);

  return { canvasRef, wrapRef };
}

export function LandingPage({ onGetStarted }: LandingPageProps) {
  const { canvasRef, wrapRef } = useHeroParticles();

  return (
    <div className="cdss-landing min-h-[100dvh] w-full overflow-x-hidden bg-cl-bg font-cl-display text-cl-on-surface antialiased selection:bg-cl-primary/20 selection:text-cl-primary">
      {/* ── Top nav ─────────────────────────────────────────────── */}
      <nav className="fixed top-0 z-50 w-full border-b border-white/5 bg-cl-bg/80 backdrop-blur-md">
        <div className="mx-auto flex h-20 max-w-screen-2xl items-center justify-between px-6 md:px-12">
          <div className="flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/yosy-logo.png" alt="Yosy Project" className="h-10 w-10 object-contain" />
          </div>
          <div className="hidden items-center gap-8 md:flex">
            {NAV_LINKS.map((label) => (
              <a key={label} href="#" className="text-base text-cl-on-surface-variant transition-colors hover:text-cl-primary">
                {label}
              </a>
            ))}
          </div>
          <div className="flex items-center gap-4">
            <button onClick={onGetStarted} className="hidden font-cl-label text-[13px] font-medium tracking-[0.02em] text-cl-on-surface-variant transition-colors hover:text-cl-primary md:block">
              Masuk
            </button>
            <button
              onClick={onGetStarted}
              className="rounded-[2px] border border-cl-primary/30 bg-cl-primary/10 px-6 py-2 font-cl-label text-[13px] font-medium tracking-[0.02em] text-cl-primary transition-all duration-300 hover:scale-105 hover:bg-cl-primary hover:text-cl-on-primary active:scale-95"
            >
              Mulai Sekarang
            </button>
          </div>
        </div>
      </nav>

      <main className="pb-[120px] pt-32">
        {/* ── Hero (with particle constellation) ────────────────── */}
        <div ref={wrapRef} className="relative mb-[120px] w-full">
          <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 z-0 h-full w-full" />
          <section className="relative z-10 mx-auto max-w-screen-2xl px-6 md:px-12">
            <div className="grid min-h-[716px] grid-cols-1 items-center gap-6 md:grid-cols-12">
              <div className="cl-stagger pr-0 md:col-span-8 md:pr-12">
                <h1 className="mb-8 text-5xl font-semibold leading-[1.1] tracking-[-0.04em] md:text-[64px]">CDSS for Nursing</h1>
                <p className="mb-12 max-w-2xl border-l-2 border-cl-outline-variant pl-6 text-lg leading-relaxed tracking-[-0.01em] text-cl-on-surface-variant">
                  Sistem pendukung pengambilan keputusan klinis keperawatan berbasis Multi Agentic Artificial Intelligence dan
                  Retrieval-Augmented Generation (RAG)
                </p>
                <div className="flex flex-wrap items-center gap-6">
                  <button
                    onClick={onGetStarted}
                    className="flex items-center gap-2 rounded-[2px] bg-cl-primary px-8 py-4 font-cl-label text-[13px] font-medium tracking-[0.02em] text-cl-on-primary shadow-[0_4px_14px_0_rgba(198,198,198,0.39)] transition-all duration-300 hover:scale-105 hover:bg-cl-primary-container"
                  >
                    Mulai Analisis
                    <ArrowRight className="h-[18px] w-[18px]" />
                  </button>
                </div>
              </div>
              <div className="cl-fade-in relative mt-12 md:col-span-4 md:mt-0">
                <div className="absolute inset-0 rounded-full bg-cl-primary/5 blur-3xl" />
                <div className="cl-shimmer relative flex aspect-[3/4] flex-col overflow-hidden rounded-[8px] border border-white/10 bg-cl-surface-lowest p-2 shadow-2xl">
                  <div className="relative flex-1 overflow-hidden rounded-[4px] bg-cl-surface">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      alt="AI Nurse Assistant"
                      src="/hero-ai-nurse.png"
                      className="absolute inset-0 h-full w-full object-cover opacity-60 mix-blend-luminosity"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-cl-bg via-transparent to-transparent" />
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>

        {/* ── Trust strip ───────────────────────────────────────── */}
        <section className="mb-[120px] border-y border-white/5 bg-cl-surface-lowest py-8">
          <div className="mx-auto flex max-w-screen-2xl flex-col items-center justify-between gap-8 px-6 md:flex-row md:px-12">
            <span className="font-cl-label text-[13px] font-medium uppercase tracking-widest text-cl-outline">Supported 11 Provider LLM</span>
            <div className="flex flex-wrap items-center gap-4">
              {LLM_BADGES.map((b) => (
                <span key={b} className="rounded-[2px] border border-cl-outline-variant bg-cl-surface px-3 py-1 font-cl-label text-[11px] tracking-[0.05em] text-cl-on-surface-variant shadow-md shadow-black/20">
                  {b}
                </span>
              ))}
              <span className="font-cl-label text-[11px] tracking-[0.05em] text-cl-outline">+7 Other</span>
            </div>
          </div>
        </section>

        {/* ── Core capabilities (bento) ─────────────────────────── */}
        <section id="fitur" className="mx-auto mb-[120px] max-w-screen-2xl scroll-mt-24 px-6 md:px-12">
          <h2 className="mb-12 text-3xl font-semibold leading-[1.2] tracking-[-0.03em] md:text-[40px]">Kapabilitas Klinis</h2>
          <div className="grid auto-rows-[240px] grid-cols-1 gap-6 md:grid-cols-12">
            {/* Large tile */}
            <div className="group flex flex-col justify-between rounded-[8px] border border-white/5 bg-cl-surface-low p-8 shadow-xl shadow-black/40 transition-colors hover:border-cl-primary/30 md:col-span-8 md:row-span-2">
              <div>
                <Workflow className="mb-4 h-8 w-8 text-cl-primary" strokeWidth={1.5} />
                <h3 className="mb-2 text-2xl font-medium tracking-[-0.02em]">Multi-Agent Swarm</h3>
                <p className="max-w-md text-base leading-relaxed text-cl-on-surface-variant">
                  Arsitektur agen ganda yang memisahkan tugas ekstraksi, penalaran patofisiologi, dan pemetaan standar untuk akurasi optimal
                </p>
              </div>
              <div className="mt-auto border-t border-white/5 pt-4">
                <div className="flex items-center gap-4 font-cl-label text-[11px] tracking-[0.05em]">
                  <span className="flex items-center gap-1 text-cl-primary"><span className="h-1.5 w-1.5 rounded-full bg-cl-primary" /> EXTRACTOR</span>
                  <span className="flex items-center gap-1 text-cl-tertiary"><span className="h-1.5 w-1.5 rounded-full bg-cl-tertiary" /> REASONER</span>
                  <span className="flex items-center gap-1 text-cl-secondary"><span className="h-1.5 w-1.5 rounded-full bg-cl-secondary" /> MAPPER</span>
                </div>
              </div>
            </div>
            {/* Small tile */}
            <div className="flex flex-col justify-between rounded-[8px] border border-white/5 bg-cl-surface p-8 shadow-lg shadow-black/30 transition-colors hover:bg-cl-surface-container md:col-span-4">
              <ScanText className="mb-4 h-7 w-7 text-cl-secondary" strokeWidth={1.5} />
              <h3 className="mb-2 text-lg font-medium tracking-[-0.02em]">Document &amp; Photo Reader</h3>
              <p className="text-sm leading-relaxed text-cl-on-surface-variant">Ekstraksi data vital langsung dari rekam medis fisik atau monitor</p>
            </div>
            {/* Small tile */}
            <div className="flex flex-col justify-between rounded-[8px] border border-white/5 bg-cl-surface p-8 shadow-lg shadow-black/30 transition-colors hover:bg-cl-surface-container md:col-span-4">
              <Network className="mb-4 h-7 w-7 text-cl-tertiary" strokeWidth={1.5} />
              <h3 className="mb-2 text-lg font-medium tracking-[-0.02em]">3S &amp; 3N Aware</h3>
              <p className="text-sm leading-relaxed text-cl-on-surface-variant">Pemetaan nomenklatur otomatis ke standar asuhan nasional dan global</p>
            </div>
            {/* Medium tile */}
            <div className="relative flex flex-col justify-between overflow-hidden rounded-[8px] border border-white/5 bg-cl-surface-low p-8 shadow-xl shadow-black/40 md:col-span-6">
              <div className="absolute right-0 top-0 p-4 opacity-10">
                <FlaskConical className="h-[120px] w-[120px]" strokeWidth={1} />
              </div>
              <div className="relative z-10">
                <h3 className="mb-2 text-2xl font-medium tracking-[-0.02em]">Grounding RAG &amp; EBP</h3>
                <p className="text-base leading-relaxed text-cl-on-surface-variant">
                  Keputusan didasarkan pada literatur Evidence-Based Practice terbaru, bukan halusinasi generatif
                </p>
              </div>
            </div>
            {/* Medium tile */}
            <div className="flex flex-col justify-between rounded-[8px] border border-white/5 bg-cl-surface-low p-8 shadow-xl shadow-black/40 md:col-span-6">
              <div>
                <div className="mb-4 flex items-start justify-between">
                  <ShieldCheck className="h-7 w-7 text-cl-error" strokeWidth={1.5} />
                </div>
                <h3 className="mb-2 text-2xl font-medium tracking-[-0.02em]">20+ Guardrails Klinis</h3>
                <p className="text-base leading-relaxed text-cl-on-surface-variant">
                  Proteksi anti prompt-injection dan verifikasi dosis/intervensi kritis secara real-time.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ── Standards split ───────────────────────────────────── */}
        <section id="standar" className="mb-[120px] scroll-mt-24 border-y border-cl-outline-variant bg-cl-surface py-[120px]">
          <div className="mx-auto grid max-w-screen-2xl grid-cols-1 gap-0 px-6 md:grid-cols-2 md:px-12">
            <div className="border-cl-outline-variant pb-12 md:border-r md:pb-0 md:pr-16">
              <h3 className="mb-6 flex items-center gap-3 text-2xl font-medium tracking-[-0.02em]">
                <Globe className="h-5 w-5 text-cl-primary" strokeWidth={1.5} />
                Standar Indonesia (3S)
              </h3>
              <p className="mb-8 text-base leading-relaxed text-cl-on-surface-variant">
                Integrasi penuh dengan pedoman PPNI untuk kompatibilitas rekam medis elektronik nasional.
              </p>
              <ul className="space-y-3 font-cl-label text-[11px] tracking-[0.05em]">
                {[
                  ["SDKI", "Standar Diagnosis"],
                  ["SLKI", "Standar Luaran"],
                  ["SIKI", "Standar Intervensi"],
                ].map(([code, desc]) => (
                  <li key={code} className="flex items-center gap-3 text-cl-outline">
                    <span className="block h-4 w-1 bg-cl-primary/50" />
                    <span className="text-cl-on-surface">{code}</span> - {desc}
                  </li>
                ))}
              </ul>
            </div>
            <div className="border-t border-cl-outline-variant pt-12 md:border-t-0 md:pl-16 md:pt-0">
              <h3 className="mb-6 flex items-center gap-3 text-2xl font-medium tracking-[-0.02em]">
                <Languages className="h-5 w-5 text-cl-secondary" strokeWidth={1.5} />
                Standar Internasional (3N)
              </h3>
              <p className="mb-8 text-base leading-relaxed text-cl-on-surface-variant">
                Pemetaan sekunder untuk kebutuhan riset, publikasi, atau rumah sakit bertaraf internasional.
              </p>
              <ul className="space-y-3 font-cl-label text-[11px] tracking-[0.05em]">
                {[
                  ["NANDA", "Nursing Diagnoses"],
                  ["NOC", "Outcomes Classification"],
                  ["NIC", "Interventions Classification"],
                ].map(([code, desc]) => (
                  <li key={code} className="flex items-center gap-3 text-cl-outline">
                    <span className="block h-4 w-1 bg-cl-secondary/50" />
                    <span className="text-cl-on-surface">{code}</span> - {desc}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* ── Final CTA ─────────────────────────────────────────── */}
        <section className="mx-auto mb-[120px] max-w-screen-2xl px-6 text-center md:px-12">
          <div className="relative overflow-hidden rounded-2xl border border-cl-outline-variant bg-cl-surface-high p-16 shadow-2xl shadow-black/50">
            <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-cl-primary/5 to-transparent" />
            <h2 className="relative z-10 mb-6 text-3xl font-semibold leading-[1.2] tracking-[-0.03em] md:text-[40px]">
              Susun Asuhan Keperawatan hari ini
            </h2>
            <p className="relative z-10 mx-auto mb-10 max-w-xl text-lg leading-relaxed tracking-[-0.01em] text-cl-on-surface-variant">
              Tingkatkan akurasi pembuatan asuhan keperawatan anda
            </p>
            <button
              onClick={onGetStarted}
              className="relative z-10 rounded-[2px] bg-cl-primary px-8 py-4 font-cl-label text-[13px] font-medium tracking-[0.02em] text-cl-on-primary shadow-[0_4px_14px_0_rgba(198,198,198,0.39)] transition-all duration-300 hover:scale-105 hover:bg-cl-primary-container"
            >
              Mulai Evaluasi Klinis
            </button>
          </div>
        </section>
      </main>

      {/* ── Footer ──────────────────────────────────────────────── */}
      <footer className="w-full border-t border-cl-outline-variant bg-cl-surface-lowest py-[120px]">
        <div className="mx-auto grid max-w-screen-2xl grid-cols-1 gap-6 px-6 md:grid-cols-12 md:px-12">
          <div className="mb-8 md:col-span-4 md:mb-0">
            <div className="mb-4 flex items-center gap-2 text-2xl font-bold tracking-[-0.02em]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/yosy-logo.png" alt="Yosy Project" className="h-10 w-10 object-contain" />
              Yosy Project
            </div>
            <p className="mb-6 font-cl-label text-[11px] tracking-[0.05em] text-cl-outline">
              Sistem ini adalah pendukung keputusan klinis, bukan pengganti penilaian profesional perawat berlisensi.
            </p>
            <p className="font-cl-label text-[13px] font-medium tracking-[0.02em] text-cl-on-surface-variant">© 2026 Yosy Project.</p>
          </div>
          <div className="flex flex-wrap gap-x-16 gap-y-8 md:col-span-8 md:justify-end">
            {[
              { title: "PLATFORM", links: ["Produk", "Fitur", "EBP"] },
              { title: "RESOURCES", links: ["Dokumentasi", "Keamanan", "Pusat Bantuan"] },
              { title: "LEGAL", links: ["Kebijakan Privasi", "Syarat & Ketentuan"] },
            ].map((col) => (
              <div key={col.title} className="flex flex-col gap-3">
                <span className="mb-2 font-cl-label text-[11px] tracking-[0.05em] text-cl-outline">{col.title}</span>
                {col.links.map((l) => (
                  <a key={l} href="#" className="text-base text-cl-on-surface-variant transition-colors hover:text-cl-primary">
                    {l}
                  </a>
                ))}
              </div>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}
