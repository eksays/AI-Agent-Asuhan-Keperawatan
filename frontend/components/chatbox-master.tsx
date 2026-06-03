"use client";
import { AnimatedAIChat } from "@/components/ui/animated-ai-chat";
import { useApp } from "@/components/app-context";
import type { Tier, Tab } from "@/lib/types";

export function ChatboxMaster({ forTab }: { forTab?: Tab }) {
  const { send, sending, tier, setTier, framework, setFramework, tab, consent, setConsent } = useApp();
  const myTab = forTab ?? tab;
  return (
    <div className="w-full">
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
        placeholder="Ada yang bisa saya bantu?"
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
