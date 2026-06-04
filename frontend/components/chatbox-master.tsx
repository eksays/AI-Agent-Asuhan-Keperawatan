"use client";
import { X } from "lucide-react";
import { AnimatedAIChat } from "@/components/ui/animated-ai-chat";
import { useApp, DOC_ACTIONS, REF_ACTIONS, type DocAction } from "@/components/app-context";
import type { Tier, Tab } from "@/lib/types";

/* Panel pemilih aksi MENGAMBANG (ala Claude AskUserQuestion) — muncul TEPAT DI ATAS chatbox saat user
   hanya mengunggah dokumen tanpa perintah. Warna mengikuti kolom prompt (bg #30302E, border zinc-700/50). */
function DocActionPicker({ options }: { options: DocAction[] }) {
  const { chooseDocAction, dismissDocPicker } = useApp();
  return (
    <div className="mx-auto mb-2 w-full max-w-3xl overflow-hidden rounded-2xl border border-zinc-700/50 bg-[#30302E] shadow-2xl">
      <div className="flex items-start justify-between gap-3 px-4 pb-2 pt-3">
        <span className="font-serif text-[0.95rem] leading-snug text-zinc-100">Dokumen telah diterima. Apa yang ingin Anda lakukan dengan data ini?</span>
        <button onClick={dismissDocPicker} aria-label="Tutup" className="flex-shrink-0 rounded-md p-1 text-zinc-500 transition-colors hover:bg-white/10 hover:text-zinc-200"><X className="h-4 w-4" /></button>
      </div>
      <div className="pb-2">
        {options.map((opt, i) => (
          <button key={opt.label} type="button" onClick={() => chooseDocAction(opt.instruction)}
            className="group flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-white/[0.05]">
            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md bg-white/[0.05] text-[0.78rem] font-semibold text-zinc-400 transition-colors group-hover:bg-white/10 group-hover:text-zinc-100">{i + 1}</span>
            <span className="text-[0.9rem] text-zinc-200">{opt.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function ChatboxMaster({ forTab }: { forTab?: Tab }) {
  const { send, sending, tier, setTier, framework, setFramework, tab, consent, setConsent, pendingDocAction } = useApp();
  const myTab = forTab ?? tab;
  const showPicker = (myTab === "Analisis" || myTab === "Referensi") && pendingDocAction;   // panel untuk tab Analisis/Referensi saat dokumen menunggu aksi
  const pickerOptions = myTab === "Referensi" ? REF_ACTIONS : DOC_ACTIONS;
  return (
    <div className="w-full">
      {/* Panel pemilih aksi MENGAMBANG di atas chatbox (tersinkron dengan unggahan dokumen user) */}
      {showPicker && <DocActionPicker options={pickerOptions} />}
      {/* Persetujuan eksplisit WAJIB sebelum bisa mengirim/mengunggah (UU PDP Pasal 20/22) */}
      {!consent && (
        <label className="mx-auto mb-2 flex max-w-4xl cursor-pointer items-start gap-2.5 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-[0.78rem] leading-snug text-amber-100">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 h-4 w-4 flex-shrink-0 accent-blue-500" />
          <span>Saya secara sadar memberikan persetujuan untuk memproses data ini guna keperluan ekstraksi medis.</span>
        </label>
      )}
      <AnimatedAIChat
        disabled={sending || !consent}
        defaultModel={tier}
        onModelChange={(id) => setTier(id as Tier)}
        framework={framework}
        onFrameworkChange={setFramework}
        showFramework={myTab === "Analisis"}
        placeholder={showPicker ? "Atau balas langsung…" : "Ada yang bisa saya bantu?"}
        onSendMessage={(message, files, pasted) => {
          const fileObjs = files.map((f) => f.file);
          const pastedText = pasted.map((p) => p.content).join("\n\n");
          send([message, pastedText].filter(Boolean).join("\n\n"), fileObjs);
        }}
      />
      <p className="mx-auto mt-3 max-w-4xl text-center text-[0.7rem] text-zinc-500">
        CDSS adalah AI dan dapat melakukan kesalahan sehingga perlu validasi penilaian klinis perawat.
      </p>
    </div>
  );
}
