"use client";

import { useState } from "react";
import { AlertTriangle, ShieldCheck, Workflow } from "lucide-react";

import { Mermaid } from "@/components/ui/mermaid";
import type { CapabilitiesResponse } from "@/lib/capabilities";
import { createLabSession, runLabPathway, type LabPathwayResponse } from "@/lib/api";

const FIXTURES = [
  { id: "SYN-MMD-SAFE-001", label: "Safe Fixture", icon: ShieldCheck },
  { id: "SYN-MMD-MAL-001", label: "Malicious Fixture Test", icon: AlertTriangle },
] as const;

function safeBoolean(value: boolean | undefined, fallback: boolean): string {
  return String(value ?? fallback);
}

export function SyntheticLabMermaidRunner({ capabilities, credential }: { capabilities: CapabilitiesResponse; credential?: string }) {
  const [selectedFixture, setSelectedFixture] = useState<(typeof FIXTURES)[number]["id"]>("SYN-MMD-SAFE-001");
  const [result, setResult] = useState<LabPathwayResponse | null>(null);
  const [errorCode, setErrorCode] = useState<string>("");
  const [busy, setBusy] = useState(false);

  if (!capabilities.synthetic_lab_enabled) return null;

  const disabled = busy || !credential || !capabilities.synthetic_mermaid_enabled;
  const runFixture = async (fixtureId: (typeof FIXTURES)[number]["id"]) => {
    if (!credential || !capabilities.synthetic_mermaid_enabled) return;
    setSelectedFixture(fixtureId);
    setBusy(true);
    setResult(null);
    setErrorCode("");
    try {
      const labSession = await createLabSession(credential);
      const response = await runLabPathway(credential, labSession, fixtureId);
      if (response.status === "sukses" && response.mermaid) setResult(response);
      else setErrorCode(response.error_code || "lab_mermaid_fixture_rejected");
    } catch {
      setErrorCode("lab_mermaid_runner_failed_closed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mx-4 mb-3 rounded-lg border border-amber-300/25 bg-black/20 p-3 text-xs text-amber-50" aria-label="Synthetic lab Mermaid fixture runner">
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        <span className="rounded border border-amber-200/20 px-2 py-0.5 font-semibold">SYNTHETIC PROTOTYPE</span>
        <span className="rounded border border-amber-200/20 px-2 py-0.5 font-semibold">NOT FOR PATIENT CARE</span>
        <span className="rounded border border-amber-200/20 px-2 py-0.5 font-semibold">SANITIZED MERMAID FIXTURE</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {FIXTURES.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            disabled={disabled}
            onClick={() => void runFixture(id)}
            className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 font-semibold transition ${selectedFixture === id ? "border-amber-200/60 bg-amber-300/15 text-amber-50" : "border-amber-200/20 bg-white/[0.03] text-amber-100 hover:bg-white/[0.07]"} disabled:cursor-not-allowed disabled:opacity-50`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>
      {busy && <div className="mt-3 flex items-center gap-2 text-amber-100"><Workflow className="h-3.5 w-3.5 animate-pulse" />Loading manifest fixture...</div>}
      {errorCode && <div className="mt-3 rounded-md border border-red-400/30 bg-red-500/10 p-2 text-red-100">fixture_status={errorCode}</div>}
      {result?.mermaid && (
        <div className="mt-3 space-y-2">
          <div className="grid gap-1 sm:grid-cols-2">
            <div>fixture_id: {selectedFixture}</div>
            <div>run_id: {result.run_id || "not_recorded"}</div>
            <div>registry_authoritative={safeBoolean(result.registry_authoritative, false)}</div>
            <div>clinical_use_allowed={safeBoolean(result.clinical_use_allowed, false)}</div>
            <div>accepted_recommendations={safeBoolean(result.accepted_recommendations, false)}</div>
            <div>nurse_review_required={safeBoolean(result.nurse_review_required, true)}</div>
          </div>
          <Mermaid code={result.mermaid} />
        </div>
      )}
    </section>
  );
}
