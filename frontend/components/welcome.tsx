"use client";
import { useState } from "react";
import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { HeroLanding } from "@/components/ui/hero-1";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useApp } from "@/components/app-context";
import { detectProvider, PROVIDER_LABEL } from "@/lib/types";

export function Welcome() {
  const { login } = useApp();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [remember, setRemember] = useState(true);
  const provider = key.trim() ? PROVIDER_LABEL[detectProvider(key)] : null;

  return (
    <>
      <HeroLanding
        title="CDSS AI Keperawatan"
        titleClassName="bg-gradient-to-b from-white via-white to-zinc-500 bg-clip-text text-transparent text-5xl font-bold tracking-tight sm:text-7xl"
        description="Sistem Pendukung Keputusan Klinis Berbasis Standar 3S & 3N. Cepat, akurat, dan berbasis bukti klinis (EBP)."
        callToActions={[{ text: "Get Start", variant: "primary", onClick: () => setOpen(true), icon: <ArrowRight className="h-4 w-4" /> }]}
      />

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogTitle className="sr-only">Setup Workspace</DialogTitle>
          <DialogDescription className="sr-only">Masukkan nama lengkap dan API key Anda untuk memulai.</DialogDescription>
          <div className="flex flex-col gap-4">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Isikan nama lengkap anda"
              className="w-full rounded-xl bg-zinc-800/70 px-4 py-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-500 focus:ring-2 focus:ring-blue-500/40" />
            <div className="relative">
              <input type={show ? "text" : "password"} value={key} onChange={(e) => setKey(e.target.value)} placeholder="Masukkan API Key anda"
                onKeyDown={(e) => { if (e.key === "Enter" && key.trim()) login(name, key, remember); }}
                className="w-full rounded-xl bg-zinc-800/70 px-4 py-3 pr-11 text-sm text-zinc-100 outline-none placeholder:text-zinc-500 focus:ring-2 focus:ring-blue-500/40" />
              <button onClick={() => setShow(!show)} aria-label="Tampilkan API key" className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200">
                {show ? <EyeOff className="h-[18px] w-[18px]" /> : <Eye className="h-[18px] w-[18px]" />}
              </button>
            </div>
            {provider && <p className="-mt-1 text-[0.74rem] text-zinc-400">Terdeteksi: <span className="font-medium text-blue-300">{provider}</span></p>}
            <label className="flex cursor-pointer items-center gap-2.5 text-[0.82rem] text-zinc-400">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="h-4 w-4 rounded bg-zinc-800 accent-blue-600" />
              Ingat kredensial ini untuk sesi berikutnya
            </label>
            <button onClick={() => key.trim() && login(name, key, remember)} disabled={!key.trim()}
              className="glass mt-1 flex w-full items-center justify-center gap-2 rounded-xl py-3 text-sm font-semibold text-white disabled:opacity-40">
              Get Start <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
