"use client";
import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

let init = false;
function ensure() {
  if (init) return;
  mermaid.initialize({ startOnLoad: false, securityLevel: "loose", theme: "base", themeVariables: {
    primaryColor: "#dbeafe", primaryTextColor: "#1e3a8a", primaryBorderColor: "#3b82f6",
    lineColor: "#2563eb", secondaryColor: "#e0e7ff", tertiaryColor: "#eff6ff", fontFamily: "inherit" } });
  init = true;
}

export function Mermaid({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false; ensure();
    mermaid.render("m" + Math.random().toString(36).slice(2, 8), code)
      .then(({ svg }) => { if (!cancelled && ref.current) { ref.current.innerHTML = svg; setErr(null); } })
      .catch((e) => { if (!cancelled) setErr(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [code]);
  if (err) return <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">Gagal merender pathway.</div>;
  return <div className="mermaid-box" ref={ref} aria-label="Clinical pathway" />;
}
