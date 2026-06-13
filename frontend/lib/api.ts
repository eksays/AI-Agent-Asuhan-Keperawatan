import type { ProviderId, Tier, Framework } from "./types";
import { resolveModel } from "./types";
import { FAIL_CLOSED_CAPABILITIES, normalizeCapabilities, type CapabilitiesResponse } from "./capabilities";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8000";

export interface StatusResponse { status: string; detail: Record<string, string>; providers: string[] }
export interface ChatResponse { status: "sukses" | "error"; jawaban?: string; pesan?: string }
export interface AnalisisResponse { status: "sukses" | "error"; hasil?: string; pesan?: string }
export interface ChatCtx { provider: ProviderId; apiKey: string; tier: Tier; framework: Framework }
export interface SessionBinding { sessionId: string; sessionToken: string }

async function postForm<T>(path: string, apiKey: string, fields: Record<string, string | Blob | undefined>, session?: SessionBinding): Promise<T> {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== null) fd.append(k, v);
  const headers: Record<string, string> = {};
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
  if (session?.sessionToken) headers['X-Session-Token'] = session.sessionToken;
  const r = await fetch(`${API_BASE}${path}`, { method: "POST", headers: Object.keys(headers).length ? headers : undefined, body: fd });
  return (await r.json()) as T;
}

export async function getStatus(apiKey: string): Promise<StatusResponse> {
  const r = await fetch(`${API_BASE}/status`, { headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : undefined });
  return (await r.json()) as StatusResponse;
}

export async function getCapabilities(): Promise<CapabilitiesResponse> {
  try {
    const r = await fetch(`${API_BASE}/capabilities`);
    if (!r.ok) throw new Error(String(r.status));
    return normalizeCapabilities((await r.json()) as Partial<CapabilitiesResponse>);
  } catch {
    return FAIL_CLOSED_CAPABILITIES;
  }
}

/** Minta session_id kriptografis (CSPRNG) yang diterbitkan backend. Klien TIDAK membuat session_id sendiri. */
export async function createSession(apiKey: string): Promise<SessionBinding> {
  const r = await fetch(`${API_BASE}/session`, { method: "POST", headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : undefined });
  const d = (await r.json()) as { session_id?: string; session_token?: string };
  if (!d.session_id || !d.session_token) throw new Error("Gagal membuat sesi.");
  return { sessionId: d.session_id, sessionToken: d.session_token };
}

export function chat(ctx: ChatCtx, session: SessionBinding, pertanyaan: string, agent: string = "analisis") {
  return postForm<ChatResponse>("/chat", ctx.apiKey, {
    provider: ctx.provider, model: resolveModel(ctx.provider, ctx.tier), tier: ctx.tier,
    framework: ctx.framework, session_id: session.sessionId, agent, pertanyaan,
  }, session);
}

export function analisis(ctx: ChatCtx, session: SessionBinding, gejala: string, fileDokumen?: File, fileFoto?: File, agent: string = "analisis") {
  return postForm<AnalisisResponse>("/analisis_multi", ctx.apiKey, {
    provider: ctx.provider, model: resolveModel(ctx.provider, ctx.tier), tier: ctx.tier,
    framework: ctx.framework, session_id: session.sessionId, agent, consent: "true", gejala,
    file_dokumen: fileDokumen, file_foto: fileFoto,
  }, session).then(async (d) => {
    if (d.status === "sukses" && d.hasil != null) return d;
    // fallback to single-agent endpoint
    return postForm<AnalisisResponse>("/analisis", ctx.apiKey, {
      provider: ctx.provider, model: resolveModel(ctx.provider, ctx.tier), tier: ctx.tier,
      framework: ctx.framework, session_id: session.sessionId, agent, consent: "true", gejala, file_dokumen: fileDokumen, file_foto: fileFoto,
    }, session);
  });
}

/** Hak Hapus Data (UU PDP): musnahkan permanen riwayat percakapan & feedback milik session_id ini di server. */
export function deleteMyData(ctx: ChatCtx, session: SessionBinding) {
  return postForm<{ status: string }>("/delete_my_data", ctx.apiKey, { session_id: session.sessionId }, session).catch(() => ({ status: "error" as const }));
}

/** Streaming chat (typewriter). Yields incremental text chunks. */
export async function* chatStream(ctx: ChatCtx, session: SessionBinding, pertanyaan: string, agent: string = "analisis"): AsyncGenerator<string> {
  const fd = new FormData();
  fd.append("provider", ctx.provider);
  fd.append("model", resolveModel(ctx.provider, ctx.tier)); fd.append("tier", ctx.tier); fd.append("framework", ctx.framework);
  fd.append("session_id", session.sessionId); fd.append("agent", agent); fd.append("pertanyaan", pertanyaan);
  const r = await fetch(`${API_BASE}/chat_stream`, { method: "POST", headers: { Authorization: `Bearer ${ctx.apiKey}`, "X-Session-Token": session.sessionToken }, body: fd });
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
export function pathway(ctx: ChatCtx, session: SessionBinding, konteks?: string) {
  return postForm<{ status: string; mermaid?: string; pesan?: string }>("/pathway", ctx.apiKey, {
    provider: ctx.provider, model: resolveModel(ctx.provider, ctx.tier), tier: ctx.tier,
    framework: ctx.framework, session_id: session.sessionId, gejala: konteks ?? "",
  }, session).catch(() => ({ status: "error" as const, mermaid: "" }));
}

export function resetSesi(ctx: ChatCtx, session: SessionBinding) {
  return postForm<{ status: string; session_token?: string }>("/reset", ctx.apiKey, { session_id: session.sessionId }, session);
}

export function sendFeedback(ctx: ChatCtx, session: SessionBinding, p: { framework: Framework; pertanyaan: string; jawaban: string; rating: "up" | "down"; koreksi?: string }) {
  return postForm<{ status: string }>("/feedback", ctx.apiKey, {
    framework: p.framework, session_id: session.sessionId, pertanyaan: p.pertanyaan, jawaban: p.jawaban.slice(0, 6000), rating: p.rating, koreksi: p.koreksi ?? "",
  }, session).catch(() => ({ status: "error" as const }));
}
