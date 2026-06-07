export type CapabilityKey =
  | "external_llm"
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
  synthetic_lab_enabled: boolean;
  synthetic_data_only: boolean;
  lab_namespace: "/lab";
  lab_external_provider_enabled: boolean;
  lab_feature_activation_status: "disabled" | "foundation_only" | "offline_core_features";
  synthetic_multi_agent_enabled: boolean;
  synthetic_rag_enabled: boolean;
  synthetic_registry_enabled: boolean;
  synthetic_ebp_enabled: boolean;
  synthetic_mermaid_enabled: boolean;
  synthetic_uploads_enabled: boolean;
  synthetic_ocr_mock_enabled: boolean;
  synthetic_photo_mock_enabled: boolean;
  synthetic_feedback_memory_enabled: boolean;
  capabilities: Record<CapabilityKey, CapabilityState>;
  metadata_unavailable?: boolean;
}

export const CAPABILITY_KEYS: CapabilityKey[] = [
  "external_llm",
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
  synthetic_lab_enabled: false,
  synthetic_data_only: false,
  lab_namespace: "/lab",
  lab_external_provider_enabled: false,
  lab_feature_activation_status: "disabled",
  synthetic_multi_agent_enabled: false,
  synthetic_rag_enabled: false,
  synthetic_registry_enabled: false,
  synthetic_ebp_enabled: false,
  synthetic_mermaid_enabled: false,
  synthetic_uploads_enabled: false,
  synthetic_ocr_mock_enabled: false,
  synthetic_photo_mock_enabled: false,
  synthetic_feedback_memory_enabled: false,
  metadata_unavailable: true,
  capabilities: {
    external_llm: { enabled: false, reason: DEFAULT_REASON },
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
    synthetic_lab_enabled: raw?.synthetic_lab_enabled === true,
    synthetic_data_only: raw?.synthetic_data_only === true,
    lab_namespace: raw?.lab_namespace === "/lab" ? raw.lab_namespace : base.lab_namespace,
    lab_external_provider_enabled: false,
    lab_feature_activation_status: raw?.lab_feature_activation_status === "offline_core_features" ? "offline_core_features" : raw?.lab_feature_activation_status === "foundation_only" ? "foundation_only" : "disabled",
    synthetic_multi_agent_enabled: raw?.synthetic_multi_agent_enabled === true,
    synthetic_rag_enabled: raw?.synthetic_rag_enabled === true,
    synthetic_registry_enabled: raw?.synthetic_registry_enabled === true,
    synthetic_ebp_enabled: raw?.synthetic_ebp_enabled === true,
    synthetic_mermaid_enabled: raw?.synthetic_mermaid_enabled === true,
    synthetic_uploads_enabled: raw?.synthetic_uploads_enabled === true,
    synthetic_ocr_mock_enabled: raw?.synthetic_ocr_mock_enabled === true,
    synthetic_photo_mock_enabled: raw?.synthetic_photo_mock_enabled === true,
    synthetic_feedback_memory_enabled: raw?.synthetic_feedback_memory_enabled === true,
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
