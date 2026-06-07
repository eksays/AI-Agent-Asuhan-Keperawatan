export type CapabilityKey =
  | "external_llm"
  | "local_synthetic_demo"
  | "ebp_external_search"
  | "clinical_photo_analysis"
  | "mermaid_pathway_rendering"
  | "sdki_authoritative_grounding"
  | "slki"
  | "siki"
  | "nanda"
  | "noc"
  | "nic";

export interface CapabilityState { enabled: boolean; reason: string }
export interface CapabilitiesResponse {
  app_mode: "clinical_sandbox" | "controlled_pilot" | "production";
  safety_notice: string;
  unsupported_notice: string;
  capabilities: Record<CapabilityKey, CapabilityState>;
  metadata_unavailable?: boolean;
}

export const CAPABILITY_KEYS: CapabilityKey[] = [
  "external_llm",
  "local_synthetic_demo",
  "ebp_external_search",
  "clinical_photo_analysis",
  "mermaid_pathway_rendering",
  "sdki_authoritative_grounding",
  "slki",
  "siki",
  "nanda",
  "noc",
  "nic",
];

const DEFAULT_REASON = "Backend capability metadata is unavailable; unsafe features are disabled.";

export const FAIL_CLOSED_CAPABILITIES: CapabilitiesResponse = {
  app_mode: "clinical_sandbox",
  safety_notice: "Clinical sandbox — AI-generated suggestions require nurse review.",
  unsupported_notice: "Unsupported or unverified features are disabled.",
  metadata_unavailable: true,
  capabilities: {
    external_llm: { enabled: false, reason: DEFAULT_REASON },
    local_synthetic_demo: { enabled: false, reason: DEFAULT_REASON },
    ebp_external_search: { enabled: false, reason: DEFAULT_REASON },
    clinical_photo_analysis: { enabled: false, reason: DEFAULT_REASON },
    mermaid_pathway_rendering: { enabled: false, reason: DEFAULT_REASON },
    sdki_authoritative_grounding: { enabled: false, reason: DEFAULT_REASON },
    slki: { enabled: false, reason: DEFAULT_REASON },
    siki: { enabled: false, reason: DEFAULT_REASON },
    nanda: { enabled: false, reason: DEFAULT_REASON },
    noc: { enabled: false, reason: DEFAULT_REASON },
    nic: { enabled: false, reason: DEFAULT_REASON },
  },
};

export function normalizeCapabilities(raw: Partial<CapabilitiesResponse> | null | undefined): CapabilitiesResponse {
  const base = FAIL_CLOSED_CAPABILITIES;
  const capabilities = CAPABILITY_KEYS.reduce((acc, key) => {
    const incoming = raw?.capabilities?.[key];
    acc[key] = {
      enabled: incoming?.enabled === true,
      reason: incoming?.reason || base.capabilities[key].reason,
    };
    return acc;
  }, {} as Record<CapabilityKey, CapabilityState>);

  return {
    app_mode: raw?.app_mode || base.app_mode,
    safety_notice: raw?.safety_notice || base.safety_notice,
    unsupported_notice: raw?.unsupported_notice || base.unsupported_notice,
    metadata_unavailable: raw?.metadata_unavailable === true || !raw,
    capabilities,
  };
}

export function isCapabilityEnabled(caps: CapabilitiesResponse, key: CapabilityKey): boolean {
  return caps.capabilities[key]?.enabled === true;
}

export function capabilityReason(caps: CapabilitiesResponse, key: CapabilityKey): string {
  return caps.capabilities[key]?.reason || DEFAULT_REASON;
}
