"use client";
import { createContext, useContext, useState, useCallback, useRef, useEffect, type ReactNode } from "react";
import type { Credentials, Framework, ProviderId, Tab, Tier } from "@/lib/types";
import { detectProvider } from "@/lib/types";
import * as api from "@/lib/api";

export type Phase = "welcome" | "dashboard";
export type Agent = "analisis" | "pathway" | "referensi";
export interface DocAction { label: string; instruction: string }
export interface Msg {
  id: string; role: "user" | "assistant"; content: string;
  mermaid?: string | null; status?: string[]; done?: boolean; revealed?: boolean;
  kind?: "askep" | "pathway" | "jurnal" | "umum";
  feedback?: "up" | "down" | null; feedbackSent?: boolean;
  attachment?: { name: string; ext: string };
}
// pendingAction: sesi punya dokumen terunggah yang MENUNGGU pilihan aksi (panel pemilih mengambang di atas chatbox).
export interface Session { id: string; title: string; tab: Tab; messages: Msg[]; createdAt: number; pendingAction?: boolean }
export interface BannerState { show: boolean; title: string; description: string }

const LS = "cdss-creds";
const CONSENT_KEY = "cdss-consent";
const AGENT_OF: Record<Tab, Agent> = { Analisis: "analisis", Pathway: "pathway", Referensi: "referensi" };
const EMPTY_ACTIVE: Record<Tab, string | null> = { Analisis: null, Pathway: null, Referensi: null };
// Saat user HANYA mengunggah dokumen (tanpa perintah) di tab Analisis -> tanyakan dulu aksinya (ala Claude).
export const DOC_ACTIONS: DocAction[] = [
  { label: "Susun diagnosis keperawatan", instruction: "Susun diagnosis keperawatan berdasarkan dokumen rekam medis terlampir." },
  { label: "Susun luaran keperawatan", instruction: "Susun luaran keperawatan berdasarkan dokumen rekam medis terlampir." },
  { label: "Susun intervensi keperawatan", instruction: "Susun intervensi keperawatan berdasarkan dokumen rekam medis terlampir." },
  { label: "Susun diagnosis, luaran, dan intervensi keperawatan", instruction: "Susun diagnosis, luaran, dan intervensi keperawatan secara lengkap berdasarkan dokumen rekam medis terlampir." },
];
// Tab Referensi: unggah dokumen saja -> tawarkan pencarian EBP (atau user balas langsung di chatbox).
export const REF_ACTIONS: DocAction[] = [
  { label: "Carikan jurnal EBP terkait", instruction: "Carikan jurnal EBP terbaru yang relevan dengan dokumen/kasus terlampir menggunakan pendekatan PICO." },
];
// Label status (English, gaya agentic) per agen.
const STAGES: Record<Agent, { file: string[]; text: string[] }> = {
  analisis: {
    file: ["Reading the medical record document…", "Extracting subjective & objective data…", "Searching 3S/3N references…", "Formulating the nursing care plan…"],
    text: ["Reviewing the request…", "Searching 3S/3N standards…", "Composing the response…"],
  },
  pathway: {
    file: ["Reading the document…", "Mapping the clinical pathway…", "Rendering the flowchart…"],
    text: ["Analyzing the case…", "Mapping the clinical pathway…", "Rendering the flowchart…"],
  },
  referensi: {
    file: ["Reading the document…", "Searching scholarly databases…", "Reading & analyzing abstracts…", "Compiling EBP recommendations…"],
    text: ["Understanding the case…", "Searching scholarly databases…", "Reading & analyzing abstracts…", "Compiling EBP recommendations…"],
  },
};

const newId = () => Math.random().toString(36).slice(2, 10);
const autoTitle = (t: string) => { const s = t.trim().replace(/\s+/g, " "); return !s ? "Konsultasi baru" : s.length > 36 ? s.slice(0, 36) + "…" : s; };
function splitMermaid(text: string) { const m = text.match(/```mermaid([\s\S]*?)```/i); return m ? { rest: text.replace(/```mermaid[\s\S]*?```/i, "").trim(), mermaid: m[1].trim() } : { rest: text, mermaid: null }; }
// Kode standar NYATA (bukan sekadar disebut): SDKI D.0xxx / SLKI L.xxxxx / SIKI I.xxxxx / NANDA 00xxx.
const CODE_RE = /\b(?:[DLI]\.\d{3,5}|00\d{3})\b/;
// Struktur dokumen Askep: heading bagian (## ...) yang memuat Diagnosis/Luaran/Intervensi/Analisis Data.
const ASKEP_STRUCT_RE = /(?:^|\n)\s{0,3}#{1,3}\s.*(?:diagnos|luaran|intervensi|analisis data)/i;
// Niat user untuk MEN-GENERATE konten klinis = verb aksi + kata benda klinis.
const GEN_VERB_RE = /\b(?:buat|buatkan|buatlah|susun|susunkan|rumus|rumuskan|tegak|tegakkan|analis|analisa|bikin|bikinkan|hasilkan|generate|kelola|tentukan|rancang|kembangkan|carikan|cari)\b/i;
const CLIN_NOUN_RE = /\b(?:asuhan keperawatan|askep|diagnos\w*|luaran|intervensi|rencana keperawatan|clinical pathway|pathway|patofisiologi|rekam medis|pasien|kasus|sdki|slki|siki|nanda|noc|nic|jurnal|ebp)\b/i;

function wantsClinical(req: string, hadFile: boolean): boolean {
  const r = (req || "").trim();
  if (hadFile && r.length > 0) return true;                 // file + perintah apa pun = permintaan klinis
  return GEN_VERB_RE.test(r) && CLIN_NOUN_RE.test(r);
}

/** Jenis jawaban Askep (tab Analisis) -> menentukan tombol PDF/Word/EBP/Pathway.
 *  Butuh NIAT generate + KODE standar nyata + STRUKTUR bagian; obrolan biasa tidak memicu tombol. */
function classifyAskep(req: string, answer: string, hadFile: boolean, hasMermaid: boolean): Msg["kind"] {
  const a = (answer || "").trim();
  if (hasMermaid || /```mermaid/i.test(a)) return "pathway";
  if (/^Dokumen telah diterima/i.test(a)) return "umum";
  if ((/^(mohon maaf|maaf)\b/i.test(a) || /belum tersedia|tidak tersedia|belum ditemukan/i.test(a.slice(0, 220))) && !CODE_RE.test(a)) return "umum";
  if (wantsClinical(req, hadFile) && CODE_RE.test(a) && ASKEP_STRUCT_RE.test(a)) return "askep";
  return "umum";
}

interface Ctx {
  phase: Phase; creds: Credentials | null;
  tier: Tier; setTier: (t: Tier) => void;
  framework: Framework; setFramework: (f: Framework) => void;
  tab: Tab; setTab: (t: Tab) => void;
  status: Record<string, string>;
  sessions: Session[]; activeId: string | null; messages: Msg[]; sending: boolean;
  banner: BannerState; dismissBanner: () => void;
  sidebarOpen: boolean; setSidebarOpen: (b: boolean) => void;
  settingsOpen: boolean; setSettingsOpen: (b: boolean) => void;
  login: (name: string, key: string, remember: boolean, provider?: ProviderId) => void;
  changeName: (name: string) => void;
  logoutCreds: () => void;
  newChat: () => void; selectSession: (id: string) => void;
  send: (text: string, files: File[], targetTab?: Tab, opts?: { suppressChip?: boolean }) => Promise<void>;
  pendingDocAction: boolean;                                  // panel pemilih aksi (file-only) sedang aktif di sesi terpilih
  chooseDocAction: (instruction: string) => void;             // user memilih salah satu aksi -> proses dokumen
  dismissDocPicker: () => void;                               // tutup panel (×/Skip) tanpa memproses
  runOnTab: (targetTab: Tab, text: string) => void;
  revealMsg: (id: string) => void;
  setFeedback: (id: string, fb: "up" | "down") => void;
  submitFeedback: (id: string, koreksi: string) => void;
  hardReset: () => Promise<void>;
  consent: boolean; setConsent: (b: boolean) => void;
  deleteMyData: () => Promise<void>;
}
const C = createContext<Ctx | null>(null);
export function useApp() { const v = useContext(C); if (!v) throw new Error("useApp outside provider"); return v; }

export function AppProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("welcome");
  const [creds, setCreds] = useState<Credentials | null>(null);
  const [tier, setTier] = useState<Tier>("medium");
  const [framework, setFramework] = useState<Framework>("3S");
  const [tab, setTab] = useState<Tab>("Analisis");
  const [status, setStatus] = useState<Record<string, string>>({});
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeByTab, setActiveByTab] = useState<Record<Tab, string | null>>(EMPTY_ACTIVE);
  const [sending, setSending] = useState(false);
  const [banner, setBanner] = useState<BannerState>({ show: false, title: "", description: "" });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [consent, setConsentState] = useState(false);          // persetujuan eksplisit pemrosesan data (UU PDP)
  const backendSidRef = useRef<Record<string, string>>({});   // id sesi LOKAL -> session_id kriptografis dari backend
  const pendingDocRef = useRef<Record<string, File>>({});     // dokumen menunggu aksi (per-sesi) saat unggah dokumen tanpa perintah
  const consentRef = useRef(false);

  // Kredensial HANYA di sessionStorage (per-tab, hilang saat tab ditutup) + bersihkan jejak lama di localStorage.
  useEffect(() => { try { localStorage.removeItem(LS); const r = sessionStorage.getItem(LS); if (r) { const c = JSON.parse(r) as Credentials; if (c?.apiKey) { setCreds(c); setPhase("dashboard"); } } if (sessionStorage.getItem(CONSENT_KEY) === "1") { setConsentState(true); consentRef.current = true; } } catch {} }, []);
  useEffect(() => { if (phase === "dashboard" && creds?.apiKey) api.getStatus(creds.apiKey).then((d) => setStatus(d.detail || {})).catch(() => {}); }, [phase, creds]);

  const login = useCallback((name: string, key: string, remember: boolean, provider?: ProviderId) => {
    const c: Credentials = { name: name.trim() || "Perawat", apiKey: key.trim(), provider: provider || detectProvider(key) };
    setCreds(c); if (remember) try { sessionStorage.setItem(LS, JSON.stringify(c)); } catch {}
    setPhase("dashboard");
  }, []);
  const changeName = useCallback((name: string) => setCreds((c) => { if (!c) return c; const n = { ...c, name: name.trim() || c.name }; try { if (sessionStorage.getItem(LS)) sessionStorage.setItem(LS, JSON.stringify(n)); } catch {} return n; }), []);
  const logoutCreds = useCallback(() => { try { sessionStorage.removeItem(LS); localStorage.removeItem(LS); } catch {} backendSidRef.current = {}; setCreds(null); setSessions([]); setActiveByTab(EMPTY_ACTIVE); setPhase("welcome"); }, []);
  const setConsent = useCallback((b: boolean) => { setConsentState(b); consentRef.current = b; try { if (b) sessionStorage.setItem(CONSENT_KEY, "1"); else sessionStorage.removeItem(CONSENT_KEY); } catch {} }, []);

  const activeId = activeByTab[tab];
  const activeSession = sessions.find((s) => s.id === activeId);
  const messages = activeSession?.messages ?? [];
  const pendingDocAction = !!activeSession?.pendingAction;     // tampilkan panel pemilih bila sesi aktif menunggu aksi

  const ensureSession = useCallback((t: Tab): string => {
    const cur = activeByTab[t];
    if (cur) return cur;
    const id = newId();
    setSessions((p) => [{ id, title: "Konsultasi baru", tab: t, messages: [], createdAt: Date.now() }, ...p]);
    setActiveByTab((p) => ({ ...p, [t]: id }));
    return id;
  }, [activeByTab]);
  const newChat = useCallback(() => setActiveByTab((p) => ({ ...p, [tab]: null })), [tab]);
  const selectSession = useCallback((id: string) => {
    const s = sessions.find((x) => x.id === id); if (!s) return;
    setTab(s.tab); setActiveByTab((p) => ({ ...p, [s.tab]: id })); setSidebarOpen(false);
  }, [sessions]);
  const patch = useCallback((sid: string, mid: string, p: Partial<Msg>) => setSessions((prev) => prev.map((s) => s.id !== sid ? s : { ...s, messages: s.messages.map((m) => m.id === mid ? { ...m, ...p } : m) })), []);
  const revealMsg = useCallback((mid: string) => setSessions((prev) => prev.map((s) => s.messages.some((m) => m.id === mid && !m.revealed) ? { ...s, messages: s.messages.map((m) => m.id === mid ? { ...m, revealed: true } : m) } : s)), []);

  const send = useCallback(async (text: string, files: File[], targetTab?: Tab, opts?: { suppressChip?: boolean }) => {
    if (!creds || (!text.trim() && files.length === 0)) return;
    if (!consentRef.current) { setBanner({ show: true, title: "Persetujuan diperlukan", description: "Centang kotak persetujuan pemrosesan data terlebih dahulu sebelum mengirim." }); return; }
    const t = targetTab ?? tab;
    const agent = AGENT_OF[t];
    if (targetTab && targetTab !== tab) setTab(targetTab);   // jalankan & tampilkan di tab tujuan
    const sid = ensureSession(t);                            // session_id backend = id sesi tab ini
    // Balasan bebas (user mengetik) saat ada dokumen menunggu di sesi ini -> pakai dokumen itu (panel pemilih ikut tertutup karena pendingAction direset di bawah).
    let effFiles = files;
    let suppressChip = !!opts?.suppressChip;                 // dokumen sudah tampil sebagai chip saat diunggah -> jangan duplikasi chip
    if ((agent === "analisis" || agent === "referensi") && files.length === 0 && text.trim() && pendingDocRef.current[sid]) {
      effFiles = [pendingDocRef.current[sid]];
      delete pendingDocRef.current[sid];
      suppressChip = true;
    }
    const file = effFiles[0];
    const userContent = text.trim();
    const att = file && !suppressChip ? { name: file.name, ext: (file.name.split(".").pop() || "FILE").slice(0, 4).toUpperCase() } : undefined;
    // UNGGAH DOKUMEN SAJA (tanpa perintah) di tab Analisis/Referensi -> JANGAN panggil backend; cukup tambahkan pesan dokumen user
    // lalu nyalakan pendingAction supaya PANEL PEMILIH MENGAMBANG muncul di atas chatbox (bukan di thread).
    if ((agent === "analisis" || agent === "referensi") && file && !userContent) {
      pendingDocRef.current[sid] = file;
      setSessions((prev) => prev.map((s) => s.id !== sid ? s : {
        ...s, title: s.messages.length === 0 ? autoTitle(file.name) : s.title, pendingAction: true,
        messages: [...s.messages, { id: newId(), role: "user", content: "", attachment: att, done: true, revealed: true }],
      }));
      return;
    }
    const botId = newId();
    setSessions((prev) => prev.map((s) => s.id !== sid ? s : {
      ...s, title: s.messages.length === 0 ? autoTitle(userContent || (file ? file.name : "")) : s.title, pendingAction: false,
      messages: [...s.messages, { id: newId(), role: "user", content: userContent, attachment: att, done: true, revealed: true }, { id: botId, role: "assistant", content: "", status: ["Initializing…"], done: false }],
    }));
    setSending(true);
    const baseStages = STAGES[agent][file ? "file" : "text"].map((s) => s.replace(/3S\/3N/g, framework));   // tampilkan kerangka pilihan user (3S atau 3N)
    const stages = tier === "flash" ? baseStages : [...baseStages, "Auditing & refining the answer…"];   // medium/pro: ada pass penyempurna
    let si = 0; const timer = setInterval(() => { si = Math.min(si + 1, stages.length); patch(sid, botId, { status: stages.slice(0, si) }); }, 650);
    const ctx: api.ChatCtx = { provider: creds.provider, apiKey: creds.apiKey, tier, framework };
    // session_id WAJIB diterbitkan backend (CSPRNG). Klien tidak lagi membuat sendiri.
    const getBackendSid = async (force = false): Promise<string> => {
      if (!force && backendSidRef.current[sid]) return backendSidRef.current[sid];
      const bs = await api.createSession();
      backendSidRef.current[sid] = bs;
      return bs;
    };
    const runOnce = async (bsid: string): Promise<string> => {
      if (file) {
        const isImg = (file.type || "").startsWith("image/");   // foto -> file_foto; dokumen -> file_dokumen
        const d = await api.analisis(ctx, bsid, userContent, isImg ? undefined : file, isImg ? file : undefined, agent);
        if (d.status === "sukses" && d.hasil != null) return d.hasil;
        if (d.pesan === "SESSION_INVALID") throw new Error("SESSION_INVALID");
        throw new Error(d.pesan || "Gagal.");
      }
      let acc = ""; let firstChunk = true;
      try {
        for await (const chunk of api.chatStream(ctx, bsid, userContent, agent)) {
          if (firstChunk) { clearInterval(timer); firstChunk = false; }
          acc += chunk;
          patch(sid, botId, { content: acc, status: undefined, done: false });
        }
      } catch (streamErr) {
        const code = streamErr instanceof Error ? streamErr.message : "";
        if (code === "409") throw new Error("SESSION_INVALID");
        if (/401|403|429/.test(code)) throw streamErr;            // auth/quota -> banner
        if (!acc.trim()) {                                         // stream tak tersedia -> fallback /chat
          const d = await api.chat(ctx, bsid, userContent, agent);
          if (d.status === "sukses" && d.jawaban != null) return d.jawaban;
          if (d.pesan === "SESSION_INVALID") throw new Error("SESSION_INVALID");
          throw new Error(d.pesan || "Gagal.");
        }
      }
      return acc;
    };
    try {
      let answer = "";
      try {
        answer = await runOnce(await getBackendSid());
      } catch (e) {                                               // id basi (backend restart) -> terbitkan ulang, coba sekali lagi
        if (e instanceof Error && e.message === "SESSION_INVALID") answer = await runOnce(await getBackendSid(true));
        else throw e;
      }
      clearInterval(timer);
      const { rest, mermaid } = splitMermaid(answer);
      const kind: Msg["kind"] = agent === "pathway" ? (mermaid ? "pathway" : "umum")
        : agent === "referensi" ? "jurnal"
          : classifyAskep(userContent, answer, !!file, !!mermaid);
      patch(sid, botId, { content: rest, mermaid, kind, status: undefined, done: true });
    } catch (e) {
      clearInterval(timer);
      const msg = e instanceof Error ? e.message : String(e);
      if (/401|403|429|invalid|auth|exhaust|quota|habis/i.test(msg)) setBanner({ show: true, title: "Token API Habis", description: "Sistem tidak dapat memproses data" });
      patch(sid, botId, { content: "Maaf, sistem tidak dapat memproses permintaan saat ini. Pastikan backend berjalan dan kunci API valid.", status: undefined, done: true, revealed: true, kind: "umum" });
    } finally { setSending(false); }
  }, [creds, tier, framework, tab, ensureSession, patch]);

  // User memilih salah satu aksi pada PANEL PEMILIH (file-only) -> proses dokumen yang menunggu dengan instruksi terpilih.
  const chooseDocAction = useCallback((instruction: string) => {
    const sid = activeByTab[tab];
    if (!sid) return;
    const f = pendingDocRef.current[sid];
    delete pendingDocRef.current[sid];
    setSessions((prev) => prev.map((s) => s.id === sid ? { ...s, pendingAction: false } : s));
    void send(instruction, f ? [f] : [], tab, { suppressChip: true });
  }, [send, activeByTab, tab]);
  // Tutup panel (× / Skip): cukup matikan pendingAction. Dokumen dibiarkan menunggu agar "balas langsung" tetap memakainya.
  const dismissDocPicker = useCallback(() => {
    const sid = activeByTab[tab];
    if (!sid) return;
    setSessions((prev) => prev.map((s) => s.id === sid ? { ...s, pendingAction: false } : s));
  }, [activeByTab, tab]);

  const runOnTab = useCallback((targetTab: Tab, text: string) => { void send(text, [], targetTab); }, [send]);

  const findQA = useCallback((mid: string) => { const s = sessions.find((x) => x.id === activeId); if (!s) return null; const i = s.messages.findIndex((m) => m.id === mid); if (i < 0) return null; let q = ""; for (let j = i - 1; j >= 0; j--) if (s.messages[j].role === "user") { q = s.messages[j].content; break; } return { pertanyaan: q, jawaban: s.messages[i].content }; }, [sessions, activeId]);
  const setFeedback = useCallback((mid: string, fb: "up" | "down") => { if (!activeId) return; patch(activeId, mid, { feedback: fb }); if (fb === "up") { const qa = findQA(mid); if (qa) void api.sendFeedback({ framework, session_id: backendSidRef.current[activeId] || "", ...qa, rating: "up" }); } }, [activeId, patch, findQA, framework]);
  const submitFeedback = useCallback((mid: string, koreksi: string) => { if (!activeId) return; const qa = findQA(mid); if (!qa) return; void api.sendFeedback({ framework, session_id: backendSidRef.current[activeId] || "", ...qa, rating: "down", koreksi }); patch(activeId, mid, { feedback: "down", feedbackSent: true }); }, [activeId, findQA, framework, patch]);
  const hardReset = useCallback(async () => { try { await Promise.all(Object.values(backendSidRef.current).map((b) => api.resetSesi(b))); } catch {} backendSidRef.current = {}; setSessions([]); setActiveByTab(EMPTY_ACTIVE); }, []);
  const deleteMyData = useCallback(async () => { try { await Promise.all(Object.values(backendSidRef.current).map((b) => api.deleteMyData(b))); } catch {} backendSidRef.current = {}; setSessions([]); setActiveByTab(EMPTY_ACTIVE); }, []);

  return <C.Provider value={{ phase, creds, tier, setTier, framework, setFramework, tab, setTab, status, sessions, activeId, messages, sending, banner, dismissBanner: () => setBanner((b) => ({ ...b, show: false })), sidebarOpen, setSidebarOpen, settingsOpen, setSettingsOpen, login, changeName, logoutCreds, newChat, selectSession, send, pendingDocAction, chooseDocAction, dismissDocPicker, runOnTab, revealMsg, setFeedback, submitFeedback, hardReset, consent, setConsent, deleteMyData }}>{children}</C.Provider>;
}
