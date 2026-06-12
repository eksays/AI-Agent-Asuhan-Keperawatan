export type Framework = "3S" | "3N";
export type Tab = "Analisis" | "Pathway" | "Referensi";
export type Tier = "flash" | "medium" | "pro";

export type ProviderId =
  | "gemini" | "openai" | "claude" | "deepseek" | "groq"
  | "xai" | "mistral" | "together" | "openrouter" | "shopee" | "sumopod";

export interface Credentials { name: string; apiKey: string; provider: ProviderId }

export const FW_BOOKS: Record<Framework, string[]> = {
  "3S": ["SDKI", "SLKI", "SIKI"],
  "3N": ["NANDA", "NIC", "NOC"],
};

/** Detect provider from key prefix. Name returned capitalized via PROVIDER_LABEL. */
export function detectProvider(key: string): ProviderId {
  const k = key.trim();
  if (k.startsWith("sk-ant-")) return "claude";
  if (k.startsWith("AIza")) return "gemini";
  if (k.startsWith("gsk_")) return "groq";
  if (k.startsWith("xai-")) return "xai";
  if (k.startsWith("sk-or-")) return "openrouter";
  if (/^shpe|^shopee|^spc_/i.test(k)) return "shopee";       // ShopeeAI
  if (k.startsWith("sp-") || k.startsWith("sumo-")) return "sumopod"; // Sumopod
  if (k.startsWith("sk-")) return "openai";
  return "openrouter"; // universal fallback (OpenRouter)
}

export const PROVIDER_LABEL: Record<ProviderId, string> = {
  gemini: "Gemini", openai: "OpenAI", claude: "Claude", deepseek: "DeepSeek",
  groq: "Groq", xai: "Grok", mistral: "Mistral", together: "Together AI",
  openrouter: "OpenRouter", shopee: "ShopeeAI", sumopod: "Sumopod",
};

export function resolveModel(provider: ProviderId, tier: Tier): string {
  const M: Record<ProviderId, Record<Tier, string>> = {
    gemini: { flash: "gemini-2.5-flash", medium: "gemini-2.5-flash", pro: "gemini-2.5-pro" },
    openai: { flash: "gpt-4o-mini", medium: "gpt-4o", pro: "gpt-4o" },
    claude: { flash: "claude-haiku-4-5", medium: "claude-sonnet-4-6", pro: "claude-sonnet-4-6" },
    deepseek: { flash: "deepseek-chat", medium: "deepseek-chat", pro: "deepseek-reasoner" },
    groq: { flash: "llama-3.1-8b-instant", medium: "llama-3.3-70b-versatile", pro: "llama-3.3-70b-versatile" },
    xai: { flash: "grok-2-latest", medium: "grok-2-latest", pro: "grok-2-latest" },
    mistral: { flash: "mistral-small-latest", medium: "mistral-large-latest", pro: "mistral-large-latest" },
    together: { flash: "meta-llama/Llama-3.3-70B-Instruct-Turbo", medium: "meta-llama/Llama-3.3-70B-Instruct-Turbo", pro: "meta-llama/Llama-3.3-70B-Instruct-Turbo" },
    openrouter: { flash: "openai/gpt-4o-mini", medium: "openai/gpt-4o", pro: "anthropic/claude-sonnet-4" },
    shopee: { flash: "shopee-llm", medium: "shopee-llm", pro: "shopee-llm" },
    sumopod: { flash: "deepseek-v4-pro", medium: "deepseek-v4-pro", pro: "deepseek-v4-pro" },
  };
  return M[provider][tier];
}
