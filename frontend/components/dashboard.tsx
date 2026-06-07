"use client";
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Menu, Plus, Settings, NotebookPen, Workflow, BookOpen,
  Trash2, KeyRound, User, AlertTriangle, Upload, ImageIcon, Camera,
  ExternalLink, Pin, Pencil, Folder, MoreVertical, Search, PanelLeftClose, PanelLeft, LogOut, ChevronsUpDown,
} from "lucide-react";
import { useApp } from "@/components/app-context";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Banner } from "@/components/ui/banner";
import { Messages } from "@/components/messages";
import { ChatboxMaster } from "@/components/chatbox-master";
import { CameraCapture } from "@/components/ui/claude-style-ai-input";
import { type Tab } from "@/lib/types";

const TABS: { id: Tab; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "Analisis", icon: NotebookPen }, { id: "Pathway", icon: Workflow }, { id: "Referensi", icon: BookOpen },
];
const TAB_ICON: Record<Tab, React.ComponentType<{ className?: string }>> = { Analisis: NotebookPen, Pathway: Workflow, Referensi: BookOpen };
const ease = [0.16, 1, 0.3, 1] as const;

function Typewriter({ text }: { text: string }) {
  return <TypewriterText key={text} text={text} />;
}

function TypewriterText({ text }: { text: string }) {
  const [n, setN] = useState(0);
  const done = n >= text.length;
  useEffect(() => { const t = setInterval(() => setN((p) => { if (p >= text.length) { clearInterval(t); return p; } return p + 1; }), 35); return () => clearInterval(t); }, [text]);
  return <span>{text.slice(0, n)}{!done && <span className="ml-0.5 inline-block h-[1em] w-[2px] -translate-y-[2px] animate-pulse bg-zinc-400 align-middle" />}</span>;
}

/* Menu pengaturan (gerigi) — dropdown minimalis ala menu avatar. */
function SettingsMenu({ onProfile, onLogout }: { onProfile: () => void; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: globalThis.MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h);
  }, []);
  const items = [
    { label: "Profil Perawat", icon: User, onClick: onProfile, danger: false },
    { label: "Panduan Standar 3S/3N", icon: BookOpen, onClick: () => console.log("[settings] panduan 3S/3N"), danger: false },
    { label: "Pengaturan Tampilan (Tema)", icon: Settings, onClick: () => console.log("[settings] tema"), danger: false },
    { label: "Keluar", icon: LogOut, onClick: onLogout, danger: true },
  ];
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} aria-label="Menu pengaturan" className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-400 transition hover:bg-white/10 hover:text-zinc-200"><ChevronsUpDown className="h-4 w-4" /></button>
      {open && (
        <div className="absolute bottom-0 left-full z-[9999] ml-4 flex w-64 flex-col rounded-xl border border-zinc-700/50 bg-[#2B2A27] py-2 shadow-2xl">
          {items.map(({ label, icon: Icon, onClick, danger }) => (
            <button key={label} onClick={() => { onClick(); setOpen(false); }}
              className={`flex w-full items-center gap-2.5 px-3 py-2 text-left text-[0.84rem] transition-colors duration-200 hover:bg-zinc-700/50 ${danger ? "text-rose-400 hover:text-rose-300" : "text-zinc-200"}`}>
              <Icon className="h-4 w-4" /> {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* Kebab menu (tiga titik) per item riwayat chat — UI skeleton, aksi masih console.log. */
function ChatRowMenu({ sessionId }: { sessionId: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: globalThis.MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h);
  }, []);
  const items = [
    { label: "Pin", icon: Pin, danger: false, onClick: () => console.log("[chat-menu] pin", sessionId) },
    { label: "Rename", icon: Pencil, danger: false, onClick: () => console.log("[chat-menu] rename", sessionId) },
    { label: "Add to project", icon: Folder, danger: false, onClick: () => console.log("[chat-menu] add-to-project", sessionId) },
    { label: "Delete", icon: Trash2, danger: true, onClick: () => console.log("[chat-menu] delete", sessionId) },
  ];
  return (
    <div className="relative" ref={ref}>
      <button onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }} aria-label="Menu chat"
        className={`flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 transition-colors duration-200 hover:bg-white/10 hover:text-zinc-200 ${open ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}>
        <MoreVertical className="h-4 w-4" />
      </button>
      {open && (
        <div className="absolute right-0 top-8 z-[100] w-44 rounded-xl border border-zinc-700/50 bg-[#2B2A27] py-1 shadow-2xl">
          {items.map(({ label, icon: Icon, onClick, danger }) => (
            <button key={label} onClick={(e) => { e.stopPropagation(); onClick(); setOpen(false); }}
              className={`flex w-full items-center gap-2.5 px-3 py-2 text-left text-[0.82rem] transition-colors duration-200 hover:bg-zinc-700/50 ${danger ? "text-rose-400 hover:text-rose-300" : "text-zinc-200"}`}>
              <Icon className="h-4 w-4" /> {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function Dashboard() {
  const { creds, tab, setTab, sessions, activeId, messages, newChat, selectSession, sidebarOpen, setSidebarOpen, settingsOpen, setSettingsOpen, send, banner, dismissBanner, logoutCreds, hardReset, changeName, deleteMyData, capabilityAvailable, capabilityReason } = useApp();
  const [editName, setEditName] = useState(false);
  const [nameDraft, setNameDraft] = useState(creds?.name ?? "");
  const [cameraOpen, setCameraOpen] = useState(false);
  const [railOpen, setRailOpen] = useState(true);
  const docInputRef = useRef<HTMLInputElement>(null);
  const galleryInputRef = useRef<HTMLInputElement>(null);
  const name = creds?.name ?? "Perawat";
  const initials = name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const empty = messages.length === 0;
  const syntheticDemo = capabilityAvailable("local_synthetic_demo");
  const syntheticDemoReason = capabilityReason("local_synthetic_demo");
  const analysisReason = !syntheticDemo && !capabilityAvailable("external_llm") ? capabilityReason("external_llm") : !syntheticDemo && !capabilityAvailable("sdki_authoritative_grounding") ? capabilityReason("sdki_authoritative_grounding") : "";
  const photoReason = capabilityReason("clinical_photo_analysis");
  const pathwayReason = capabilityReason("mermaid_pathway_rendering");
  const ebpReason = capabilityReason("ebp_external_search");
  const tabReason = (id: Tab) => id === "Pathway" && !capabilityAvailable("mermaid_pathway_rendering") ? pathwayReason : id === "Referensi" && !capabilityAvailable("ebp_external_search") ? ebpReason : "";
  const openDocumentUpload = () => { if (!analysisReason) docInputRef.current?.click(); };
  const openGalleryUpload = () => { if (capabilityAvailable("clinical_photo_analysis")) galleryInputRef.current?.click(); };

  const Sidebar = (
    <div className="relative m-2 flex h-[calc(100dvh-1rem)] w-[340px] flex-col rounded-2xl border-r border-white/10 bg-[#1F1E1D]">
      {/* Segmented control (pill) ala toggle Chat/Cowork/Code di Claude */}
      <div className="p-3">
        <div className="mb-4 flex w-full items-center rounded-xl bg-white/5 p-1">
          {TABS.map(({ id, icon: Icon }) => (
            <button key={id} disabled={!!tabReason(id) && tab !== id} title={tabReason(id) || undefined} onClick={() => !tabReason(id) && setTab(id)}
              className={`relative flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg py-1.5 text-sm transition-all ${tabReason(id) && tab !== id ? "cursor-not-allowed text-zinc-600" : tab === id ? "bg-white/10 font-medium text-white shadow-sm" : "text-zinc-400 hover:text-zinc-200"}`}>
              <Icon className="h-4 w-4 flex-shrink-0" />
              <span>{id}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="px-3 pb-2">
        <button onClick={newChat} className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-[0.86rem] text-zinc-50 transition hover:bg-white/5">
          <Plus className="h-[18px] w-[18px] text-zinc-200" /> Konsultasi baru
        </button>
        <button onClick={() => console.log("[search] telusuri percakapan")} className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-[0.86rem] text-zinc-50 transition hover:bg-white/5">
          <Search className="h-[18px] w-[18px] text-zinc-200" /> Telusuri percakapan
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-3">
        <div className="px-2 py-1.5 text-xs font-medium text-zinc-500">Terbaru</div>
        {sessions.length === 0 && <p className="px-2 py-1 text-[0.78rem] text-zinc-600">Belum ada riwayat.</p>}
        {sessions.map((s) => { const RowIcon = TAB_ICON[s.tab]; return (
          <div key={s.id} className={`group relative flex items-center gap-1 rounded-lg pr-1 transition-colors duration-200 ${activeId === s.id ? "bg-white/10" : "hover:bg-white/5"}`}>
            <button onClick={() => selectSession(s.id)} className={`flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[0.82rem] ${activeId === s.id ? "text-zinc-50" : "text-zinc-200"}`}>
              <RowIcon className="h-3.5 w-3.5 flex-shrink-0 opacity-60" /><span className="truncate">{s.title}</span>
              <span className="ml-auto flex-shrink-0 rounded bg-white/10 px-1.5 py-0.5 text-[0.58rem] font-medium uppercase tracking-wide text-zinc-400">{s.tab}</span>
            </button>
            <ChatRowMenu sessionId={s.id} />
          </div>
        ); })}
      </div>
      <div className="flex items-center gap-2.5 p-3">
        <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-zinc-700 text-[10px] font-bold text-white">{initials}</div>
        <div className="flex min-w-0 flex-1 items-center gap-1.5 truncate">
          <span className="truncate text-sm text-zinc-200">{name}</span>
        </div>
        <SettingsMenu onProfile={() => setSettingsOpen(true)} onLogout={logoutCreds} />
      </div>
    </div>
  );

  return (
    <div className="flex h-[100dvh] overflow-hidden bg-[#262624]">
      <aside className={`hidden flex-shrink-0 transition-[width] duration-300 ease-in-out lg:block ${railOpen ? "lg:w-[360px]" : "lg:w-0 overflow-hidden"}`}>{Sidebar}</aside>
      <AnimatePresence>
        {sidebarOpen && (<>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setSidebarOpen(false)} className="fixed inset-0 z-40 bg-black/60 lg:hidden" />
          <motion.aside initial={{ x: -300 }} animate={{ x: 0 }} exit={{ x: -300 }} transition={{ type: "spring", stiffness: 320, damping: 32 }} className="fixed inset-y-0 left-0 z-50 lg:hidden">{Sidebar}</motion.aside>
        </>)}
      </AnimatePresence>

      <main className="flex min-w-0 flex-1 flex-col bg-[#262624]">
        <header className="sticky top-0 z-40 flex w-full flex-shrink-0 items-center gap-3 border-none bg-[#262624] px-4 py-3">
          <button onClick={() => setRailOpen((v) => !v)} aria-label="Sembunyikan atau tampilkan sidebar" className="hidden h-9 w-9 items-center justify-center rounded-full text-zinc-400 transition hover:bg-white/10 hover:text-zinc-200 lg:flex">
            {railOpen ? <PanelLeftClose className="h-5 w-5" /> : <PanelLeft className="h-5 w-5" />}
          </button>
          <button onClick={() => setSidebarOpen(true)} className="glass flex h-9 w-9 items-center justify-center rounded-full text-zinc-300 lg:hidden"><Menu className="h-5 w-5" /></button>
        </header>

        {syntheticDemo && <div className="px-4 pb-2"><Banner show title="LOCAL SYNTHETIC DEMO — DO NOT ENTER REAL PATIENT DATA." description={syntheticDemoReason} icon={<AlertTriangle className="h-5 w-5" />} closable={false} className="border-amber-400/40 bg-amber-500/10 text-amber-100" /></div>}
        {banner.show && <div className="px-4 pb-2"><Banner show title={banner.title} description={banner.description} icon={<AlertTriangle className="h-5 w-5" />} onHide={dismissBanner} action={<button onClick={logoutCreds} className="rounded-md bg-red-500/20 px-3 py-1 text-xs font-semibold text-red-100 hover:bg-red-500/30">Perbarui Kunci API</button>} /></div>}

        <div className="relative flex-1 overflow-y-auto">
          <AnimatePresence mode="wait">
            <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.25, ease }} className="min-h-full">
              {tab === "Analisis" && (empty ? (
                <div className="mx-auto flex min-h-[70vh] w-full max-w-3xl flex-1 flex-col items-center justify-center gap-4 px-6">
                  <div className="text-center">
                    <h1 className="font-serif text-3xl font-medium text-zinc-100 sm:text-4xl"><Typewriter text={`Selamat datang, ${name}`} /></h1>
                    <p className="mt-3 text-[0.95rem] text-zinc-500">Ada yang bisa saya bantu?</p>
                  </div>
                  <div className="grid w-full gap-3 sm:grid-cols-3">
                    <button disabled={!!analysisReason} title={analysisReason || undefined} onClick={openDocumentUpload} className={`glass flex flex-col items-start gap-3 rounded-2xl p-5 text-left ${analysisReason ? "cursor-not-allowed opacity-55" : ""}`}>
                      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10"><Upload className="h-5 w-5 text-zinc-200" /></span>
                      <div>
                        <div className="text-[0.92rem] font-semibold text-zinc-100">Unggah Dokumen</div>
                        <div className="mt-0.5 text-[0.76rem] text-zinc-400">{analysisReason || "PDF, Word, atau teks rekam medis"}</div>
                      </div>
                    </button>
                    <button disabled={!capabilityAvailable("clinical_photo_analysis")} title={!capabilityAvailable("clinical_photo_analysis") ? photoReason : undefined} onClick={openGalleryUpload} className={`glass flex flex-col items-start gap-3 rounded-2xl p-5 text-left ${!capabilityAvailable("clinical_photo_analysis") ? "cursor-not-allowed opacity-55" : ""}`}>
                      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10"><ImageIcon className="h-5 w-5 text-zinc-200" /></span>
                      <div>
                        <div className="text-[0.92rem] font-semibold text-zinc-100">Pilih dari Galeri</div>
                        <div className="mt-0.5 text-[0.76rem] text-zinc-400">{photoReason}</div>
                      </div>
                    </button>
                    <button disabled={!capabilityAvailable("clinical_photo_analysis")} title={!capabilityAvailable("clinical_photo_analysis") ? photoReason : undefined} onClick={() => { if (capabilityAvailable("clinical_photo_analysis")) setCameraOpen(true); }} className={`glass flex flex-col items-start gap-3 rounded-2xl p-5 text-left ${!capabilityAvailable("clinical_photo_analysis") ? "cursor-not-allowed opacity-55" : ""}`}>
                      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10"><Camera className="h-5 w-5 text-zinc-200" /></span>
                      <div>
                        <div className="text-[0.92rem] font-semibold text-zinc-100">Buka Kamera</div>
                        <div className="mt-0.5 text-[0.76rem] text-zinc-400">{photoReason}</div>
                      </div>
                    </button>
                  </div>
                </div>
              ) : <Messages />)}

              {tab === "Pathway" && (empty ? (
                <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-6 py-10 text-center">
                  <h1 className="text-2xl font-semibold text-zinc-100 sm:text-3xl"><Typewriter text={`Halo, ${name}.`} /></h1>
                  <p className="mt-2 text-[0.95rem] text-zinc-500">{capabilityAvailable("mermaid_pathway_rendering") ? "Jelaskan kasusnya, saya akan membuatkan clinical pathway (diagram alur) untuk Anda." : pathwayReason}</p>
                </div>
              ) : <Messages />)}

              {tab === "Referensi" && (empty ? (
                <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-6 py-10">
                  <div className="text-center">
                    <h1 className="font-serif text-2xl font-medium text-zinc-100 sm:text-3xl"><Typewriter text={`Halo, ${name}.`} /></h1>
                    <p className="mt-2 text-[0.95rem] text-zinc-500">{capabilityAvailable("ebp_external_search") ? "Ada yang bisa saya bantu dalam pencarian Evidence-Based Practice?" : ebpReason}</p>
                  </div>
                  {capabilityAvailable("ebp_external_search") && <div className="mt-8 grid gap-4 sm:grid-cols-2">
                    {[
                      { name: "PubMed", logo: "/pubmed.png", fallback: "/assets/pubmed.svg", desc: "Riset biomedis & life sciences — NLM.", href: "https://pubmed.ncbi.nlm.nih.gov" },
                      { name: "ScienceDirect", logo: "/sciencedirect.png", fallback: "/assets/sciencedirect.svg", desc: "Jurnal ilmiah peer-reviewed — Elsevier.", href: "https://www.sciencedirect.com" },
                    ].map(({ name: n, logo, fallback, desc, href }) => (
                      <a key={n} href={href} target="_blank" rel="noopener noreferrer" className="glass group flex flex-col rounded-2xl p-3 transition-transform duration-200 hover:-translate-y-0.5">
                        <div className="flex h-24 w-full items-center justify-center rounded-lg bg-white p-4">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={logo} alt={`Logo ${n}`} className="h-full w-full object-contain" onError={(e) => { const t = e.currentTarget; if (!t.src.includes(fallback)) t.src = fallback; }} />
                        </div>
                        <div className="flex items-start justify-between gap-2 px-2 pb-1 pt-3">
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5 text-[0.95rem] font-semibold text-zinc-100">{n} <ExternalLink className="h-3.5 w-3.5 flex-shrink-0 text-zinc-400" /></div>
                            <div className="mt-0.5 text-[0.78rem] text-zinc-400">{desc}</div>
                          </div>
                        </div>
                      </a>
                    ))}
                  </div>}
                </div>
              ) : <Messages />)}
            </motion.div>
          </AnimatePresence>
        </div>

        <div className="sticky bottom-0 mx-auto w-full max-w-4xl bg-gradient-to-t from-[#262624] via-[#262624] to-transparent px-4 pb-6 pt-4">
          {/* Chatbox terpisah per tab: tiap fitur punya draft & lampiran sendiri (tidak bocor antar tab) */}
          {TABS.map(({ id }) => (<div key={id} className={tab === id ? "" : "hidden"}><ChatboxMaster forTab={id} /></div>))}
        </div>
      </main>

      {/* Beranda quick-actions: pemicu input file tersembunyi + modal kamera (getUserMedia) */}
      <input ref={docInputRef} type="file" accept=".pdf,.doc,.docx,.txt,.md,.csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f && !analysisReason) send("", [f]); if (e.target) e.target.value = ""; }} />
      <input ref={galleryInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f && capabilityAvailable("clinical_photo_analysis")) send("", [f]); if (e.target) e.target.value = ""; }} />
      {cameraOpen && capabilityAvailable("clinical_photo_analysis") && <CameraCapture onCapture={(f) => send("", [f])} onClose={() => setCameraOpen(false)} />}

      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogTitle className="sr-only">Profil Perawat</DialogTitle>
          <DialogDescription className="sr-only">Kelola nama lengkap, kunci API, batas penggunaan, dan memori sesi.</DialogDescription>
          <div className="flex flex-col gap-3">
            <div className="rounded-xl bg-white/[0.04] p-4">
              <div className="mb-1 flex items-center gap-2 text-[0.84rem] font-medium text-zinc-100"><User className="h-4 w-4 text-zinc-400" /> Nama Lengkap</div>
              {editName ? (
                <div className="flex gap-2"><input value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} className="flex-1 rounded-md bg-zinc-800 px-3 py-1.5 text-sm text-zinc-100 outline-none" /><button onClick={() => { changeName(nameDraft); setEditName(false); }} className="glass rounded-md px-3 text-[0.78rem] text-zinc-200">Simpan</button></div>
              ) : (<div className="flex items-center justify-between"><span className="text-[0.82rem] text-zinc-300">{name}</span><button onClick={() => { setNameDraft(name); setEditName(true); }} className="text-[0.76rem] text-blue-400 hover:underline">Ganti</button></div>)}
            </div>
            <button onClick={() => { setSettingsOpen(false); logoutCreds(); }} className="flex items-center gap-3 rounded-xl bg-white/[0.04] p-4 text-left transition hover:bg-white/[0.07]"><KeyRound className="h-4 w-4 text-zinc-400" /><div><div className="text-[0.84rem] font-medium text-zinc-100">Kunci API</div><div className="text-[0.72rem] text-zinc-400">Ganti API key</div></div></button>
            <button onClick={() => { hardReset(); setSettingsOpen(false); }} className="flex items-center gap-3 rounded-xl bg-white/[0.04] p-4 text-left transition hover:bg-red-500/10"><Trash2 className="h-4 w-4 text-red-400" /><div><div className="text-[0.84rem] font-medium text-zinc-100">Hapus Memori Sesi</div><div className="text-[0.72rem] text-zinc-400">Bersihkan riwayat &amp; konteks</div></div></button>
            <button onClick={async () => { await deleteMyData(); setSettingsOpen(false); }} className="flex items-center gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-left transition hover:bg-rose-500/20"><Trash2 className="h-4 w-4 flex-shrink-0 text-rose-400" /><div><div className="text-[0.84rem] font-medium text-rose-200">Hapus Seluruh Riwayat Data Saya</div><div className="text-[0.72rem] text-rose-300/70">Memusnahkan permanen percakapan &amp; feedback Anda dari server (Hak Hapus Data — UU PDP)</div></div></button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
