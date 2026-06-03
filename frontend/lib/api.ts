import type { ProviderId, Tier, Framework } from "./types";
import { resolveModel } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8000";

export interface StatusResponse { status: string; detail: Record<string, string>; providers: string[] }
export interface ChatResponse { status: "sukses" | "error"; jawaban?: string; pesan?: string }
export interface AnalisisResponse { status: "sukses" | "error"; hasil?: string; pesan?: string }
export interface ChatCtx { provider: ProviderId; apiKey: string; tier: Tier; framework: Framework }

/** All requests carry the key in BOTH the Authorization: Bearer header and the form field
 *  so it works with the re-engineered (header) backend and the legacy (form) one. */
async function postForm<T>(path: string, apiKey: string, fields: Record<string, string | Blob | undefined>): Promise<T> {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== null) fd.append(k, v);
  const r = await fetch(`${API_BASE}${path}`, { method: "POST", headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : undefined, body: fd });
  return (await r.json()) as T;
}

export async function getStatus(apiKey: string): Promise<StatusResponse> {
  const r = await fetch(`${API_BASE}/status`, { headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : undefined });
  return (await r.json()) as StatusResponse;
}

/** Minta session_id kriptografis (CSPRNG) yang diterbitkan backend. Klien TIDAK membuat session_id sendiri. */
export async function createSession(): Promise<string> {
  const r = await fetch(`${API_BASE}/session`, { method: "POST" });
  const d = (await r.json()) as { session_id?: string };
  if (!d.session_id) throw new Error("Gagal membuat sesi.");
  return d.session_id;
}

export function chat(ctx: ChatCtx, sessionId: string, pertanyaan: string, agent: string = "analisis") {
  return postForm<ChatResponse>("/chat", ctx.apiKey, {
    provider: ctx.provider, api_key: ctx.apiKey, model: resolveModel(ctx.provider, ctx.tier), tier: ctx.tier,
    framework: ctx.framework, session_id: sessionId, agent, pertanyaan,
  });
}

export function analisis(ctx: ChatCtx, sessionId: string, gejala: string, fileDokumen?: File, fileFoto?: File, agent: string = "analisis") {
  return postForm<AnalisisResponse>("/analisis_multi", ctx.apiKey, {
    provider: ctx.provider, api_key: ctx.apiKey, model: resolveModel(ctx.provider, ctx.tier), tier: ctx.tier,
    framework: ctx.framework, session_id: sessionId, agent, consent: "true", gejala,
    file_dokumen: fileDokumen, file_foto: fileFoto,
  }).then(async (d) => {
    if (d.status === "sukses" && d.hasil != null) return d;
    // fallback to single-agent endpoint
    return postForm<AnalisisResponse>("/analisis", ctx.apiKey, {
      provider: ctx.provider, api_key: ctx.apiKey, model: resolveModel(ctx.provider, ctx.tier), tier: ctx.tier,
      framework: ctx.framework, session_id: sessionId, agent, consent: "true", gejala, file_dokumen: fileDokumen, file_foto: fileFoto,
    });
  });
}

/** Hak Hapus Data (UU PDP): musnahkan permanen riwayat percakapan & feedback milik session_id ini di server. */
export function deleteMyData(sessionId: string) {
  return postForm<{ status: string }>("/delete_my_data", "", { session_id: sessionId }).catch(() => ({ status: "error" as const }));
}

/** Streaming chat (typewriter). Yields incremental text chunks. */
export async function* chatStream(ctx: ChatCtx, sessionId: string, pertanyaan: string, agent: string = "analisis"): AsyncGenerator<string> {
  const fd = new FormData();
  fd.append("provider", ctx.provider); fd.append("api_key", ctx.apiKey);
  fd.append("model", resolveModel(ctx.provider, ctx.tier)); fd.append("tier", ctx.tier); fd.append("framework", ctx.framework);
  fd.append("session_id", sessionId); fd.append("agent", agent); fd.append("pertanyaan", pertanyaan);
  const r = await fetch(`${API_BASE}/chat_stream`, { method: "POST", headers: { Authorization: `Bearer ${ctx.apiKey}` }, body: fd });
  if (!r.ok || !r.body) { throw new Error(String(r.status)); }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    yield dec.decode(value, { stream: true });
  }
}

/** Generate (or fetch) a clinical pathway as Mermaid for the current session. Used for the
 *  background task after a file analysis and for the "Ya" reveal. */
export function pathway(ctx: ChatCtx, sessionId: string, konteks?: string) {
  return postForm<{ status: string; mermaid?: string; pesan?: string }>("/pathway", ctx.apiKey, {
    provider: ctx.provider, api_key: ctx.apiKey, model: resolveModel(ctx.provider, ctx.tier), tier: ctx.tier,
    framework: ctx.framework, session_id: sessionId, gejala: konteks ?? "",
  }).catch(() => ({ status: "error" as const, mermaid: "" }));
}

export function resetSesi(sessionId: string) {
  return postForm<{ status: string }>("/reset", "", { session_id: sessionId });
}

export function sendFeedback(p: { framework: Framework; session_id: string; pertanyaan: string; jawaban: string; rating: "up" | "down"; koreksi?: string }) {
  return postForm<{ status: string }>("/feedback", "", {
    framework: p.framework, session_id: p.session_id, pertanyaan: p.pertanyaan, jawaban: p.jawaban.slice(0, 6000), rating: p.rating, koreksi: p.koreksi ?? "",
  }).catch(() => ({ status: "error" as const }));
}
