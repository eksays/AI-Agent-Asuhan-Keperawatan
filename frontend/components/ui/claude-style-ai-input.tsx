"use client";

import type React from "react";
import { useState, useRef, useEffect, useCallback, type RefObject } from "react";
import { Plus, ArrowUp, X, FileText, ImageIcon, ChevronDown, Check, Loader2, Camera, Aperture, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface FileWithPreview { id: string; file: File; preview?: string; type: string; textContent?: string }
export interface PastedContent { id: string; content: string; wordCount: number }
export interface ModelOption { id: string; name: string; description: string }
export type Framework = "3S" | "3N";
type Availability = { enabled: boolean; reason: string };

interface ChatInputProps {
  onSendMessage?: (message: string, files: FileWithPreview[], pasted: PastedContent[]) => void;
  disabled?: boolean;
  placeholder?: string;
  models?: ModelOption[];
  defaultModel?: string;
  onModelChange?: (modelId: string) => void;
  framework?: Framework;
  onFrameworkChange?: (fw: Framework) => void;
  showFramework?: boolean;
  fileInputRef?: RefObject<HTMLInputElement | null>;
  disabledReason?: string;
  allowUpload?: boolean;
  allowCamera?: boolean;
  allowSearch?: boolean;
  frameworkAvailability?: Record<Framework, Availability>;
}

const MAX_FILES = 8;
const MAX_FILE_SIZE = 50 * 1024 * 1024;
const PASTE_THRESHOLD = 240;
const DEFAULT_MODELS: ModelOption[] = [
  { id: "flash", name: "Analisa Cepat (Flash)", description: "Jawaban tercepat" },
  { id: "medium", name: "Analisa Standar (Medium)", description: "Jawaban standar" },
  { id: "pro", name: "Analisa Kompleks (Pro)", description: "Jawaban kompleks" },
];

const isTextual = (f: File) => /^(text\/|application\/(json|xml|javascript|typescript))/.test(f.type.toLowerCase());
const readText = (f: File) => new Promise<string>((res, rej) => { const r = new FileReader(); r.onload = (e) => res((e.target?.result as string) || ""); r.onerror = rej; r.readAsText(f); });

/* ---------- Camera modal (getUserMedia, bukan file explorer) ---------- */
export function CameraCapture({ onCapture, onClose }: { onCapture: (f: File) => void; onClose: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [err, setErr] = useState<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    let active = true;
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then((stream) => { if (!active) { stream.getTracks().forEach((t) => t.stop()); return; } streamRef.current = stream; if (videoRef.current) videoRef.current.srcObject = stream; })
      .catch(() => setErr("Tidak dapat mengakses kamera. Periksa izin browser."));
    return () => { active = false; streamRef.current?.getTracks().forEach((t) => t.stop()); };
  }, []);

  function snap() {
    const v = videoRef.current; if (!v) return;
    const c = document.createElement("canvas"); c.width = v.videoWidth || 1280; c.height = v.videoHeight || 720;
    c.getContext("2d")?.drawImage(v, 0, 0, c.width, c.height);
    c.toBlob((blob) => { if (blob) { onCapture(new File([blob], `kamera-${Date.now()}.jpg`, { type: "image/jpeg" })); onClose(); } }, "image/jpeg", 0.92);
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-zinc-900 p-4" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-medium text-zinc-200">Ambil gambar rekam klinis</span>
          <button onClick={onClose} className="rounded-md p-1 text-zinc-400 hover:bg-white/10 hover:text-zinc-100"><X className="h-5 w-5" /></button>
        </div>
        {err ? (
          <div className="rounded-lg bg-red-500/10 p-4 text-sm text-red-300">{err}</div>
        ) : (
          <>
            <video ref={videoRef} autoPlay playsInline className="w-full rounded-xl bg-black aspect-video object-cover" />
            <button onClick={snap} className="glass mt-3 flex w-full items-center justify-center gap-2 rounded-xl py-2.5 text-sm font-medium text-zinc-100">
              <Aperture className="h-4 w-4" /> Jepret
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function ModelDropdown({ models, selected, onChange }: { models: ModelOption[]; selected: string; onChange: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const cur = models.find((m) => m.id === selected) || models[0];
  useEffect(() => {
    const h = (e: globalThis.MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div className="relative" ref={ref}>
      <Button variant="ghost" size="sm" className="h-9 px-2.5 text-sm font-medium text-zinc-300 hover:bg-white/10 hover:text-zinc-100" onClick={() => setOpen(!open)}>
        <span className="truncate max-w-[150px] sm:max-w-[210px]">{cur.name}</span>
        <ChevronDown className={cn("ml-1 h-4 w-4 transition-transform", open && "rotate-180")} />
      </Button>
      {open && (
        <div className="absolute bottom-full right-0 z-[120] mb-2 w-64 rounded-xl border border-zinc-700/50 bg-[#2B2A27] p-1.5 text-zinc-200 shadow-2xl">
          {models.map((m) => (
            <button key={m.id} onClick={() => { onChange(m.id); setOpen(false); }} className={cn("flex w-full items-center justify-between rounded-lg p-2.5 text-left transition-colors hover:bg-white/10", m.id === selected && "bg-white/10")}>
              <div><div className="text-sm font-medium text-zinc-100">{m.name}</div><div className="mt-0.5 text-xs text-zinc-400">{m.description}</div></div>
              {m.id === selected && <Check className="h-4 w-4 flex-shrink-0 text-blue-400" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* Dropdown menu untuk tombol "+" (ala Claude): Unggah Dokumen / Kamera Klinis / Cari Jurnal. */
function PlusMenu({ disabled, onUpload, onCamera, onSearch, allowUpload, allowCamera, allowSearch, uploadReason, cameraReason, searchReason }: {
  disabled?: boolean;
  onUpload: () => void;
  onCamera: () => void;
  onSearch: () => void;
  allowUpload: boolean;
  allowCamera: boolean;
  allowSearch: boolean;
  uploadReason: string;
  cameraReason: string;
  searchReason: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: globalThis.MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h);
  }, []);
  const items = [
    { label: "Unggah Dokumen Medis", icon: FileText, onClick: onUpload, enabled: allowUpload, reason: uploadReason },
    { label: "Buka Kamera Klinis", icon: Camera, onClick: onCamera, enabled: allowCamera, reason: cameraReason },
    { label: "Cari Jurnal (Web Search)", icon: Globe, onClick: onSearch, enabled: allowSearch, reason: searchReason },
  ];
  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((o) => !o)} disabled={disabled} aria-label="Tambah lampiran atau aksi" className="flex h-9 w-9 items-center justify-center rounded-full text-zinc-300 transition-colors hover:bg-[#3F3E3A]">
        <Plus className={cn("h-5 w-5 transition-transform duration-200", open && "rotate-45")} />
      </button>
      {open && (
        <div className="absolute bottom-full left-0 z-[120] mb-2 w-60 rounded-xl border border-zinc-700/50 bg-[#2B2A27] p-1.5 shadow-2xl">
          {items.map(({ label, icon: Icon, onClick, enabled, reason }) => (
            <button key={label} type="button" disabled={!enabled} title={enabled ? undefined : reason} onClick={() => { if (!enabled) return; onClick(); setOpen(false); }}
              className={cn("flex w-full items-start gap-3 rounded-lg px-2.5 py-2 text-left text-sm transition-colors duration-200", enabled ? "text-zinc-200 hover:bg-white/10" : "cursor-not-allowed text-zinc-500 opacity-70")}>
              <Icon className="mt-0.5 h-4 w-4 flex-shrink-0 text-zinc-400" />
              <span className="flex min-w-0 flex-col">
                <span>{label}</span>
                {!enabled && <span className="mt-0.5 text-[0.68rem] leading-snug text-zinc-500">{reason}</span>}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export const ClaudeChatInput: React.FC<ChatInputProps> = ({
  onSendMessage, disabled = false, placeholder = "Ada yang bisa saya bantu?",
  models = DEFAULT_MODELS, defaultModel, onModelChange, framework = "3S", onFrameworkChange, showFramework = true, fileInputRef: extRef,
  disabledReason = "", allowUpload = true, allowCamera = true, allowSearch = true, frameworkAvailability,
}) => {
  const [message, setMessage] = useState("");
  const [files, setFiles] = useState<FileWithPreview[]>([]);
  const [pasted, setPasted] = useState<PastedContent[]>([]);
  const [selModel, setSelModel] = useState(defaultModel || models[0]?.id || "");
  const [cameraOpen, setCameraOpen] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const internalRef = useRef<HTMLInputElement>(null);
  const fileRef = extRef || internalRef;

  useEffect(() => { if (taRef.current) { taRef.current.style.height = "auto"; taRef.current.style.height = `${Math.min(taRef.current.scrollHeight, 160)}px`; } }, [message]);

  const addFiles = useCallback((list: FileList | File[] | null) => {
    if (!list) return;
    const arr = Array.from(list).slice(0, MAX_FILES - files.length).filter((f) => f.size <= MAX_FILE_SIZE && (allowCamera || !f.type.startsWith("image/")));
    const mapped = arr.map((file) => ({ id: Math.random().toString(36).slice(2), file, preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined, type: file.type || "application/octet-stream" }));
    setFiles((p) => [...p, ...mapped]);
    mapped.forEach((m) => { if (isTextual(m.file)) readText(m.file).then((t) => setFiles((p) => p.map((f) => f.id === m.id ? { ...f, textContent: t } : f))).catch(() => {}); });
  }, [allowCamera, files.length]);

  const removeFile = useCallback((id: string) => setFiles((p) => { const r = p.find((f) => f.id === id); if (r?.preview) URL.revokeObjectURL(r.preview); return p.filter((f) => f.id !== id); }), []);

  const onPaste = useCallback((e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = Array.from(e.clipboardData.items).filter((i) => i.kind === "file");
    if (items.length && files.length < MAX_FILES) { e.preventDefault(); addFiles(items.map((i) => i.getAsFile()).filter(Boolean) as File[]); return; }
    const txt = e.clipboardData.getData("text");
    if (txt && txt.length > PASTE_THRESHOLD && pasted.length < 5) { e.preventDefault(); setPasted((p) => [...p, { id: Math.random().toString(36).slice(2), content: txt, wordCount: txt.split(/\s+/).filter(Boolean).length }]); }
  }, [addFiles, files.length, pasted.length]);

  const send = useCallback(() => {
    if (disabled || (!message.trim() && files.length === 0 && pasted.length === 0)) return;
    onSendMessage?.(message, files, pasted);
    setMessage(""); files.forEach((f) => { if (f.preview) URL.revokeObjectURL(f.preview); }); setFiles([]); setPasted([]);
    if (taRef.current) taRef.current.style.height = "auto";
  }, [message, files, pasted, disabled, onSendMessage]);

  const canSend = (message.trim() || files.length > 0 || pasted.length > 0) && !disabled;

  return (
    <div className="relative mx-auto w-full max-w-4xl">
      {cameraOpen && <CameraCapture onCapture={(f) => addFiles([f])} onClose={() => setCameraOpen(false)} />}

      {/* Claude-style input surface */}
      <div className="flex flex-col rounded-2xl border border-zinc-700/50 bg-[#30302E] p-3 shadow-lg">
        {(files.length > 0 || pasted.length > 0) && (
          <div className="hide-scroll-bar w-full overflow-x-auto p-3">
            <div className="flex gap-2.5">
              {pasted.map((c) => (
                <div key={c.id} className="relative size-[92px] flex-shrink-0 overflow-hidden rounded-xl bg-zinc-700/70 p-2 text-[8px] text-zinc-300">
                  {c.content.slice(0, 120)}…
                  <button onClick={() => setPasted((p) => p.filter((x) => x.id !== c.id))} className="absolute right-1 top-1 rounded bg-black/40 p-0.5"><X className="h-3 w-3" /></button>
                </div>
              ))}
              {files.map((f) => (
                <div key={f.id} className="group relative size-[92px] flex-shrink-0 overflow-hidden rounded-xl bg-[#3A3937]">
                  {f.preview ? <img src={f.preview} alt={f.file.name} className="h-full w-full object-cover" /> : (
                    <div className="flex h-full flex-col justify-between p-2"><FileText className="h-4 w-4 text-zinc-400" /><span className="truncate text-[9px] text-zinc-300">{f.file.name}</span></div>
                  )}
                  <button onClick={() => removeFile(f.id)} className="absolute right-1 top-1 rounded bg-black/50 p-0.5 opacity-0 transition group-hover:opacity-100"><X className="h-3 w-3 text-white" /></button>
                </div>
              ))}
            </div>
          </div>
        )}

        <textarea ref={taRef} value={message} onChange={(e) => setMessage(e.target.value)} onPaste={onPaste}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }}
          placeholder={placeholder} disabled={disabled} rows={1}
          className="max-h-[160px] min-h-[44px] w-full resize-none bg-transparent px-2 pt-1 text-zinc-200 outline-none ring-0 placeholder:text-zinc-500" />

        {/* Bottom row: + (kiri); 3S/3N + model + kirim bulat (kanan) — ala Claude */}
        <div className="mt-2 flex items-end justify-between gap-2">
          {/* KIRI: + dan toggle 3S/3N */}
          <div className="flex items-center justify-start gap-1.5">
            <PlusMenu disabled={disabled}
              onUpload={() => fileRef.current?.click()}
              onCamera={() => setCameraOpen(true)}
              onSearch={() => { setMessage((m) => m || "Carikan jurnal ilmiah terkini mengenai "); taRef.current?.focus(); }}
              allowUpload={allowUpload}
              allowCamera={allowCamera}
              allowSearch={allowSearch}
              uploadReason={disabledReason || "External analysis is disabled."}
              cameraReason="Validated OCR or vision analysis is not implemented."
              searchReason="EBP external search is disabled until de-identification enforcement passes." />
            {showFramework && (
              <div className="flex items-center rounded-full bg-white/[0.04] p-0.5 text-xs">
                {(["3S", "3N"] as Framework[]).map((fw) => (
                  <button key={fw} type="button" disabled={frameworkAvailability?.[fw]?.enabled === false} title={frameworkAvailability?.[fw]?.enabled === false ? frameworkAvailability[fw].reason : undefined} onClick={() => onFrameworkChange?.(fw)} className={cn("rounded-full px-2.5 py-1 font-medium transition-colors", frameworkAvailability?.[fw]?.enabled === false ? "cursor-not-allowed text-zinc-600" : framework === fw ? "bg-white/10 text-zinc-200" : "text-zinc-500 hover:text-zinc-300")}>{fw}</button>
                ))}
              </div>
            )}
          </div>
          {/* KANAN: dropdown model + kirim */}
          <div className="flex items-center gap-3">
            <ModelDropdown models={models} selected={selModel} onChange={(id) => { setSelModel(id); onModelChange?.(id); }} />
            <button onClick={send} disabled={!canSend} aria-label="Kirim"
              className={cn("flex h-9 w-9 items-center justify-center rounded-full transition", canSend ? "bg-blue-600 text-white hover:bg-blue-500" : "bg-white/10 text-zinc-500")}>
              <ArrowUp className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
      {disabledReason && <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[0.74rem] leading-snug text-amber-100">{disabledReason}</p>}
      <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.txt,.md,.csv" className="hidden" onChange={(e) => { addFiles(e.target.files); if (e.target) e.target.value = ""; }} />
    </div>
  );
};
