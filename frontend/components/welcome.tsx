"use client";
import { useState } from "react";
import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { LandingPage } from "@/components/landing/landing-page";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useApp } from "@/components/app-context";
import { detectProvider, PROVIDER_LABEL, type ProviderId } from "@/lib/types";

export function Welcome() {
  const { login } = useApp();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [remember, setRemember] = useState(true);
  const [selectedProvider, setSelectedProvider] = useState<ProviderId | "auto">("auto");

  const detected = key.trim() ? detectProvider(key) : null;
  const activeProvider = selectedProvider === "auto" ? detected : selectedProvider;
  const providerLabel = activeProvider ? PROVIDER_LABEL[activeProvider] : null;

  return (
    <>
      <LandingPage onGetStarted={() => setOpen(true)} />

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogTitle className="sr-only">Setup Workspace</DialogTitle>
          <DialogDescription className="sr-only">Masukkan nama lengkap dan API key Anda untuk memulai.</DialogDescription>
          <div className="flex flex-col gap-4">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Isikan nama lengkap anda"
              className="w-full rounded-xl bg-zinc-800/70 px-4 py-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-500 focus:ring-2 focus:ring-blue-500/40" />
            <div className="relative">
              <input type={show ? "text" : "password"} value={key} onChange={(e) => setKey(e.target.value)} placeholder="Masukkan API Key anda"
                onKeyDown={(e) => { if (e.key === "Enter" && key.trim()) login(name, key, remember, activeProvider || undefined); }}
                className="w-full rounded-xl bg-zinc-800/70 px-4 py-3 pr-11 text-sm text-zinc-100 outline-none placeholder:text-zinc-500 focus:ring-2 focus:ring-blue-500/40" />
              <button onClick={() => setShow(!show)} aria-label="Tampilkan API key" className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200">
                {show ? <EyeOff className="h-[18px] w-[18px]" /> : <Eye className="h-[18px] w-[18px]" />}
              </button>
            </div>
            
            <div className="flex flex-col gap-1.5">
              <label className="text-[0.74rem] text-zinc-400 font-medium">Provider API</label>
              <select
                value={selectedProvider}
                onChange={(e) => setSelectedProvider(e.target.value as ProviderId | "auto")}
                className="w-full rounded-xl bg-zinc-800/70 border border-zinc-700/50 px-4 py-3 text-sm text-zinc-100 outline-none focus:ring-2 focus:ring-blue-500/40 appearance-none cursor-pointer"
                style={{ 
                  backgroundImage: `url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3E%3Cpath stroke='%23a1a1aa' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='m6 8 4 4 4-4'/%3E%3C/svg%3E")`, 
                  backgroundPosition: 'right 1rem center', 
                  backgroundSize: '1.25rem', 
                  backgroundRepeat: 'no-repeat' 
                }}
              >
                <option value="auto">Deteksi Otomatis {detected ? `(${PROVIDER_LABEL[detected]})` : ""}</option>
                {Object.entries(PROVIDER_LABEL).map(([id, label]) => (
                  <option key={id} value={id}>{label}</option>
                ))}
              </select>
            </div>

            {providerLabel && <p className="-mt-1 text-[0.74rem] text-zinc-400">Aktif: <span className="font-medium text-blue-300">{providerLabel}</span></p>}
            <label className="flex cursor-pointer items-center gap-2.5 text-[0.82rem] text-zinc-400">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="h-4 w-4 rounded bg-zinc-800 accent-blue-600" />
              Ingat kredensial ini untuk sesi berikutnya
            </label>
            <button onClick={() => key.trim() && login(name, key, remember, activeProvider || undefined)} disabled={!key.trim()}
              className="glass mt-1 flex w-full items-center justify-center gap-2 rounded-xl py-3 text-sm font-semibold text-white disabled:opacity-40">
              Get Start <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
