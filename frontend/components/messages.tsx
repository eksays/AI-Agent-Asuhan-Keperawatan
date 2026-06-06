"use client";
import { useEffect, useMemo, useRef, useState, type ComponentPropsWithoutRef, type RefObject } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion } from "framer-motion";
import { Loader2, CheckCircle2, ThumbsUp, ThumbsDown, FileText, FileDown, ExternalLink, Send, Copy, RotateCcw, ChevronDown, Clock } from "lucide-react";
import { useApp, type Msg } from "@/components/app-context";
import { Mermaid } from "@/components/ui/mermaid";
import { exportPDF, exportWord } from "@/lib/export";
import { isExternalHref, toSafeHref } from "@/lib/safe-url";

/* Deterministic Markdown allowlist. Raw HTML parsing stays disabled; this pass keeps allowed Markdown nodes and attributes narrow if renderer behavior changes. */
type HastNode = { type?: string; tagName?: string; properties?: Record<string, unknown>; children?: HastNode[]; [k: string]: unknown };
const ALLOWED_TAGS = new Set(["p", "br", "hr", "b", "strong", "i", "em", "u", "s", "del", "ins", "mark", "sub", "sup", "small", "span", "blockquote", "code", "pre", "kbd", "a", "ul", "ol", "li", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "h1", "h2", "h3", "h4", "h5", "h6"]);
const ALLOWED_ATTR: Record<string, Set<string>> = { a: new Set(["href", "title"]) };
function rehypeSanitizeStrict() {
  const clean = (node: HastNode): void => {
    if (!Array.isArray(node.children)) return;
    node.children = node.children.filter((child) => {
      if (child.type === "element") {
        const tag = String(child.tagName || "").toLowerCase();
        if (!ALLOWED_TAGS.has(tag)) return false;                       // buang elemen non-allowlist seutuhnya
        const props = (child.properties || {}) as Record<string, unknown>;
        const allow = ALLOWED_ATTR[tag] || EMPTY_ATTR;
        for (const key of Object.keys(props)) {
          if (!allow.has(key.toLowerCase())) { delete props[key]; continue; }   // default-deny (on*, style, class, src, ...)
          if (key.toLowerCase() === "href") {
            const safeHref = toSafeHref(props[key]);
            if (safeHref) props[key] = safeHref;
            else delete props[key];
          }
        }
        child.properties = props;
        clean(child);
      }
      return true;
    });
  };
  return (tree: HastNode): void => clean(tree);
}
const EMPTY_ATTR = new Set<string>();

/* Normalizer output (content-agnostic): mencegah SPACE KOSONG & <br> berlebih pada jawaban user.
   Selalu berjalan apa pun isinya -> tetap bekerja walau kualitas/format output terus diperbarui. */
function normalizeMarkdown(s: string): string {
  return s
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+$/gm, "")                             // spasi/tab di akhir baris
    .replace(/(?:[ \t]*<br\s*\/?>[ \t]*){2,}/gi, "<br>")   // <br> beruntun -> satu
    .replace(/<br\s*\/?>[ \t]*(?=\n)/gi, "")              // <br> tepat sebelum newline -> buang (redundan)
    .replace(/\n[ \t]+\n/g, "\n\n")                       // baris "kosong" berisi spasi -> benar-benar kosong
    .replace(/\n{3,}/g, "\n\n")                           // baris kosong berlebih -> satu
    .replace(/^\s+/, "")
    .replace(/\s+$/, "");
}

export function Messages() {
  const { messages, send, setFeedback, submitFeedback, runOnTab, revealMsg, capabilityAvailable, capabilityReason } = useApp();
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  const regen = (id: string) => { const i = messages.findIndex((x) => x.id === id); for (let j = i - 1; j >= 0; j--) if (messages[j].role === "user") { send(messages[j].content, []); break; } };
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-5 px-4 py-6">
      {messages.map((m) => m.role === "user"
        ? (<motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col items-end gap-2">
            {m.attachment && (
              <div className="flex max-w-[85%] items-center gap-3 rounded-xl border border-zinc-700/50 bg-[#3A3937] px-3 py-2.5">
                <FileText className="h-5 w-5 flex-shrink-0 text-zinc-400" />
                <span className="truncate text-[0.82rem] text-zinc-200">{m.attachment.name}</span>
                <span className="ml-auto rounded bg-zinc-700/70 px-1.5 py-0.5 text-[0.62rem] font-semibold uppercase text-zinc-300">{m.attachment.ext}</span>
              </div>
            )}
            {m.content && <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-[#1F1E1D] px-4 py-2.5 text-[0.92rem] leading-relaxed text-zinc-200">{m.content}</div>}
          </motion.div>)
        : <Bot key={m.id} m={m}
            onFeedback={setFeedback} onCorrect={submitFeedback} onRegen={regen}
            onReveal={() => revealMsg(m.id)}
            onPathway={() => runOnTab("Pathway", "Buatkan clinical pathway berdasarkan asuhan keperawatan berikut:\n\n" + m.content)}
            onEbp={() => runOnTab("Referensi", "Carikan jurnal EBP terbaru yang relevan untuk kasus/asuhan berikut:\n\n" + m.content)}
            pathwayEnabled={capabilityAvailable("mermaid_pathway_rendering")}
            ebpEnabled={capabilityAvailable("ebp_external_search")}
            pathwayReason={capabilityReason("mermaid_pathway_rendering")}
            ebpReason={capabilityReason("ebp_external_search")} />)}
      <div ref={endRef} />
    </div>
  );
}

const JOURNAL = ["pubmed", "ncbi.nlm", "doi.org", "europepmc", "ebi.ac.uk", "semanticscholar", "researchgate", "biomedcentral", "springer", "nature.com", "sciencedirect"];
function MdLink({ href = "", children }: ComponentPropsWithoutRef<"a">) {
  const safeHref = toSafeHref(href);
  if (!safeHref) return <span>{children}</span>;
  const external = isExternalHref(safeHref);
  const rel = external ? "noopener noreferrer" : undefined;
  const target = external ? "_blank" : undefined;
  if (external && JOURNAL.some((h) => safeHref.toLowerCase().includes(h)))
    return <a href={safeHref} target={target} rel={rel} className="mx-0.5 inline-flex items-center gap-1.5 rounded-full border border-zinc-600/50 bg-[#3A3937] px-2.5 py-0.5 align-middle text-[0.78rem] font-medium text-zinc-100 no-underline hover:bg-[#45443F]"><ExternalLink className="h-3 w-3 text-zinc-400" />{children}</a>;
  return <a href={safeHref} target={target} rel={rel}>{children}</a>;
}
const deriveTitle = (c: string) => { const h = c.match(/^#{1,3}\s+(.+)$/m); return h ? h[1].replace(/[*_`]/g, "").trim().slice(0, 60) : "Asuhan Keperawatan"; };

/* Agentic "Thought Process" dropdown - log status proses (font mono, English, ikon clock/check). */
function ThoughtProcess({ status }: { status: string[] }) {
  const [open, setOpen] = useState(true);
  const last = status[status.length - 1];
  return (
    <div className="mb-3 max-w-md rounded-xl border border-zinc-700/50 bg-white/[0.02] font-mono">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-zinc-400">
        <Clock className="h-3.5 w-3.5 flex-shrink-0 animate-pulse text-zinc-500" />
        <span className="flex-1 truncate">{last || "Working..."}</span>
        <ChevronDown className={`h-3.5 w-3.5 flex-shrink-0 text-zinc-500 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="flex flex-col gap-1.5 border-t border-zinc-800 px-3 py-2 pl-5">
          {status.map((s, i) => {
            const isLast = i === status.length - 1;
            return (
              <div key={i} className="flex items-center gap-2 text-[0.72rem]">
                {isLast ? <Loader2 className="h-3 w-3 flex-shrink-0 animate-spin text-zinc-500" /> : <CheckCircle2 className="h-3 w-3 flex-shrink-0 text-emerald-500" />}
                <span className={isLast ? "text-zinc-300" : "text-zinc-500"}>{s}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* Typing effect: ungkap teks per beberapa token. Animasi hanya saat `animate` true (belum revealed). */
function useTypewriter(text: string, animate: boolean): string {
  const [n, setN] = useState(0);
  const tokens = useMemo(() => text.split(/(\s+)/), [text]);
  useEffect(() => {
    if (!animate || n >= tokens.length) return;
    const t = setInterval(() => setN((p) => (p >= tokens.length ? p : p + 2)), 24);
    return () => clearInterval(t);
  }, [tokens, n, animate]);
  const visibleN = Math.min(n, tokens.length);
  return animate ? tokens.slice(0, visibleN).join("") : text;
}

/* Jawaban AI: font serif + typing effect SEKALI. Setelah selesai (revealed) tampil utuh tanpa mengetik ulang. */
function BotContent({ content, done, revealed, onReveal, forwardRef }: { content: string; done?: boolean; revealed?: boolean; onReveal: () => void; forwardRef: RefObject<HTMLDivElement | null> }) {
  const clean = normalizeMarkdown(content);   // cegah space kosong & <br> berlebih (selalu jalan, apa pun isinya)
  const typed = useTypewriter(clean, !revealed);
  const caughtUp = typed.length >= clean.length;
  useEffect(() => { if (!revealed && done && caughtUp && clean.length > 0) onReveal(); }, [revealed, done, caughtUp, clean.length, onReveal]);
  return (
    <div ref={forwardRef} className="prose prose-invert max-w-4xl bg-transparent font-serif text-[17px] leading-7 text-zinc-100 prose-headings:font-serif prose-headings:mb-1.5 prose-headings:mt-3 prose-p:my-1 prose-p:leading-7 prose-ol:my-1 prose-ul:my-1 prose-ol:list-outside">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitizeStrict]} components={{ a: MdLink, img: () => null }}>{revealed ? clean : typed}</ReactMarkdown>
    </div>
  );
}

function Bot({ m, onFeedback, onCorrect, onRegen, onReveal, onPathway, onEbp, pathwayEnabled, ebpEnabled, pathwayReason, ebpReason }: { m: Msg; onFeedback: (id: string, fb: "up" | "down") => void; onCorrect: (id: string, k: string) => void; onRegen: (id: string) => void; onReveal: () => void; onPathway: () => void; onEbp: () => void; pathwayEnabled: boolean; ebpEnabled: boolean; pathwayReason: string; ebpReason: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [cor, setCor] = useState("");
  const [busy, setBusy] = useState<"" | "pdf" | "word">("");
  const [copied, setCopied] = useState(false);
  // Tombol aksi (PDF/Word/Pathway/EBP) HANYA untuk Askep hasil generate - bukan obrolan biasa, sapaan, atau daftar fitur.
  const showActions = m.done && m.kind === "askep";
  async function ex(k: "pdf" | "word") { const html = ref.current?.innerHTML; if (!html) return; setBusy(k); try { if (k === "pdf") await exportPDF(deriveTitle(m.content), html); else exportWord(deriveTitle(m.content), html); } finally { setBusy(""); } }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="w-full">
      <div className="min-w-0">
        {!m.content && !m.mermaid && m.status && m.status.length > 0 && <ThoughtProcess status={m.status} />}
        {m.content && <BotContent content={m.content} done={m.done} revealed={m.revealed} onReveal={onReveal} forwardRef={ref} />}
        {m.done && m.mermaid && pathwayEnabled && (
          <div className="mt-3 overflow-x-auto rounded-2xl bg-white/[0.04] p-4"><Mermaid code={m.mermaid} /></div>
        )}
        {m.done && m.mermaid && !pathwayEnabled && <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">{pathwayReason}</div>}

        {/* AI toolbar ikon - baris tersendiri, RATA KIRI, tepat di bawah teks */}
        {m.done && (
          <div className="mt-2 flex w-full items-center justify-start gap-2">
            <button onClick={() => { navigator.clipboard?.writeText(m.content); setCopied(true); setTimeout(() => setCopied(false), 2000); }} aria-label="Salin" className="rounded-md border-none bg-transparent p-1.5 text-zinc-500 transition-colors hover:bg-[#3F3E3A] hover:text-zinc-200">{copied ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}</button>
            <button onClick={() => onFeedback(m.id, "up")} aria-label="Bagus" className={`rounded-md border-none bg-transparent p-1.5 transition-colors hover:bg-[#3F3E3A] ${m.feedback === "up" ? "text-emerald-400" : "text-zinc-500 hover:text-zinc-200"}`}><ThumbsUp className="h-4 w-4" /></button>
            <button onClick={() => onFeedback(m.id, "down")} aria-label="Kurang" className={`rounded-md border-none bg-transparent p-1.5 transition-colors hover:bg-[#3F3E3A] ${m.feedback === "down" ? "text-rose-400" : "text-zinc-500 hover:text-zinc-200"}`}><ThumbsDown className="h-4 w-4" /></button>
            <button onClick={() => onRegen(m.id)} aria-label="Regenerasi" className="rounded-md border-none bg-transparent p-1.5 text-zinc-500 transition-colors hover:bg-[#3F3E3A] hover:text-zinc-200"><RotateCcw className="h-4 w-4" /></button>
          </div>
        )}

        {/* Tombol aksi besar - HANYA untuk Askep hasil generate. Pathway -> tab Pathway, EBP -> tab Referensi. */}
        {showActions && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button onClick={() => ex("pdf")} disabled={!!busy} className="glass inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[0.76rem] font-medium text-zinc-200 disabled:opacity-50">{busy === "pdf" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileDown className="h-3.5 w-3.5" />} PDF</button>
            <button onClick={() => ex("word")} disabled={!!busy} className="glass inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[0.76rem] font-medium text-zinc-200 disabled:opacity-50"><FileText className="h-3.5 w-3.5" /> Word</button>
            <button onClick={onPathway} disabled={!pathwayEnabled} title={pathwayEnabled ? undefined : pathwayReason} className={`glass rounded-full px-3 py-1.5 text-[0.78rem] text-zinc-200 ${!pathwayEnabled ? "cursor-not-allowed opacity-55" : ""}`}>Buat Clinical Pathway</button>
            <button onClick={onEbp} disabled={!ebpEnabled} title={ebpEnabled ? undefined : ebpReason} className={`glass rounded-full px-3 py-1.5 text-[0.78rem] text-zinc-200 ${!ebpEnabled ? "cursor-not-allowed opacity-55" : ""}`}>Cari Jurnal EBP</button>
          </div>
        )}
        {m.done && m.feedback === "down" && !m.feedbackSent && (
          <div className="mt-2 rounded-lg bg-white/[0.04] p-3">
            <p className="mb-2 text-[0.82rem] text-zinc-400">Koreksi klinis Anda akan membantu sistem ini belajar. Apa yang perlu diperbaiki?</p>
            <textarea value={cor} onChange={(e) => setCor(e.target.value)} rows={2} className="w-full resize-none rounded-md bg-zinc-800 px-3 py-2 text-[0.82rem] text-zinc-100 outline-none focus:ring-2 focus:ring-blue-500/40" />
            <div className="mt-2 flex justify-end"><button onClick={() => cor.trim() && onCorrect(m.id, cor.trim())} disabled={!cor.trim()} className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-[0.78rem] font-medium text-white hover:bg-blue-500 disabled:opacity-40"><Send className="h-3.5 w-3.5" /> Kirim koreksi</button></div>
          </div>
        )}
        {m.done && m.feedbackSent && <div className="mt-2 text-[0.78rem] text-blue-400">Terima kasih, koreksi tersimpan ke memori sistem.</div>}
      </div>
    </motion.div>
  );
}
