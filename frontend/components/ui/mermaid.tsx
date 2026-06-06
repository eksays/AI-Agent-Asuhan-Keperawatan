"use client";
import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

import { sanitizeMermaidSvg, SVG_SANITIZER_BOUNDARY } from "@/lib/svg-sanitize";

let init = false;
function ensure() {
  if (init) return;
  mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "base", flowchart: { htmlLabels: false }, themeVariables: {
    primaryColor: "#dbeafe", primaryTextColor: "#1e3a8a", primaryBorderColor: "#3b82f6",
    lineColor: "#2563eb", secondaryColor: "#e0e7ff", tertiaryColor: "#eff6ff", fontFamily: "inherit" } });
  init = true;
}

export function Mermaid({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState<string | null>(null);
  const [svg, setSvg] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false; ensure();
    mermaid.render("m" + Math.random().toString(36).slice(2, 8), code)
      .then(({ svg: rendered }) => {
        const sanitized = sanitizeMermaidSvg(rendered);
        if (!cancelled) {
          if (sanitized) { setSvg(sanitized); setErr(null); }
          else { setSvg(null); setErr("unsafe_svg_rejected"); }
        }
      })
      .catch((e) => { if (!cancelled) { setSvg(null); setErr(e instanceof Error ? e.message : String(e)); } });
    return () => { cancelled = true; };
  }, [code]);
  if (err) return <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">Pathway tidak dapat dirender dengan aman.</div>;
  if (!svg) return <div className="rounded-lg border border-zinc-700/60 bg-white/[0.03] p-3 text-sm text-zinc-300">Menyiapkan pathway...</div>;
  return <div className="mermaid-box" ref={ref} aria-label="Clinical pathway" data-sanitizer-boundary={SVG_SANITIZER_BOUNDARY} dangerouslySetInnerHTML={{ __html: svg }} />;
}
