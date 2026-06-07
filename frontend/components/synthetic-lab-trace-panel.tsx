import type { CapabilitiesResponse } from "@/lib/capabilities";

export interface SyntheticLabTraceMetadata {
  run_id?: string;
  feature_label?: string;
  agent_stages?: string[];
  stage_status?: string[] | string;
  stage_latency_ms?: number[];
  retrieved_document_ids?: string[];
  retrieval_scores?: number[];
  registry_authoritative?: boolean;
  clinical_use_allowed?: boolean;
  accepted_recommendations?: boolean;
  nurse_review_required?: boolean;
  sanitization_status?: string;
}

const LABELS = [
  "REAL LOCAL PATH",
  "SYNTHETIC PROTOTYPE",
  "DETERMINISTIC MOCK",
  "DISABLED",
  "FORBIDDEN IN LAB",
];

function asList(value: string[] | string | undefined): string[] {
  if (Array.isArray(value)) return value.slice(0, 12);
  return value ? [value] : [];
}

export function SyntheticLabTracePanel({ capabilities, trace }: { capabilities: CapabilitiesResponse; trace?: SyntheticLabTraceMetadata | null }) {
  if (!capabilities.synthetic_lab_enabled) return null;
  const stages = asList(trace?.agent_stages);
  const statuses = asList(trace?.stage_status);
  return (
    <aside className="mx-4 mb-3 rounded-lg border border-amber-300/25 bg-black/20 p-3 text-xs text-amber-50" aria-label="Synthetic lab safe trace panel">
      <div className="mb-2 flex flex-wrap gap-1.5">
        {LABELS.map((label) => <span key={label} className="rounded border border-amber-200/20 px-2 py-0.5 font-semibold">{label}</span>)}
      </div>
      <div className="grid gap-1 sm:grid-cols-2">
        <div>run_id: {trace?.run_id || "no_run_selected"}</div>
        <div>feature: {trace?.feature_label || capabilities.lab_feature_activation_status}</div>
        <div>registry_authoritative={String(trace?.registry_authoritative === true)}</div>
        <div>clinical_use_allowed={String(trace?.clinical_use_allowed === true)}</div>
        <div>accepted_recommendations={String(trace?.accepted_recommendations === true)}</div>
        <div>nurse_review_required={String(trace?.nurse_review_required !== false)}</div>
      </div>
      {stages.length > 0 && <ol className="mt-2 space-y-1">
        {stages.map((stage, index) => <li key={`${stage}-${index}`} className="flex justify-between gap-2"><span>{stage}</span><span>{statuses[index] || "pending"}</span></li>)}
      </ol>}
      {trace?.retrieved_document_ids?.length ? <div className="mt-2">retrieved_document_ids: {trace.retrieved_document_ids.join(", ")}</div> : null}
      {trace?.retrieval_scores?.length ? <div className="mt-1">retrieval_scores: {trace.retrieval_scores.map((score) => score.toFixed(3)).join(", ")}</div> : null}
    </aside>
  );
}
