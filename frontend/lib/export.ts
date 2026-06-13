import createDOMPurify from "dompurify";
import { isExternalHref, toSafeHref } from "./safe-url";

const LIGHT_CSS = `*{box-sizing:border-box}body{font-family:'Segoe UI',Arial,sans-serif;color:#16181d;line-height:1.6;font-size:13px}.doc{max-width:760px;margin:0 auto;padding:36px}h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:18px 0 8px}h3{font-size:14px;margin:14px 0 6px}p{margin:8px 0}ul,ol{padding-left:20px}table{border-collapse:collapse;width:100%;margin:12px 0}th,td{border:1px solid #cbd5e1;padding:8px 11px;text-align:left;vertical-align:top}th{background:#f1f5f9}.meta{color:#64748b;font-size:11px;border-top:1px solid #e2e8f0;margin-top:24px;padding-top:12px}`;
const slug = (s: string) => (s || "dokumen").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48) || "dokumen";
const escapeHtml = (s: string) => s.replace(/[&<>'"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c] || c));
const EXPORT_ALLOWED_TAGS = ["p", "br", "hr", "strong", "b", "em", "i", "u", "s", "del", "ins", "mark", "sub", "sup", "small", "span", "blockquote", "code", "pre", "kbd", "a", "ul", "ol", "li", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "h1", "h2", "h3", "h4", "h5", "h6"];
const EXPORT_ALLOWED_ATTR = ["href", "title", "colspan", "rowspan", "scope", "start"];
const EXPORT_FORBID_TAGS = ["script", "iframe", "style", "img", "object", "embed", "svg", "math", "foreignObject", "form", "input", "button", "textarea", "select", "audio", "video", "canvas", "link", "meta", "base"];
export const EXPORT_SANITIZER_BOUNDARY = "sanitized export HTML insertion";

function currentWindow(): Window | null {
  return typeof window === "undefined" ? null : window;
}

export function sanitizeExportHtml(html: string, browserWindow: Window | null = currentWindow()) {
  if (!browserWindow) return "";
  const clean = createDOMPurify(browserWindow as unknown as typeof globalThis).sanitize(html, {
    ALLOWED_TAGS: EXPORT_ALLOWED_TAGS,
    ALLOWED_ATTR: EXPORT_ALLOWED_ATTR,
    FORBID_TAGS: EXPORT_FORBID_TAGS,
    ALLOW_ARIA_ATTR: false,
    ALLOW_DATA_ATTR: false,
    ALLOWED_URI_REGEXP: /^(?:https:\/\/|#|\/(?!\/)|\.\.?\/)/i,
  });
  const container = browserWindow.document.createElement("div");
  container.setAttribute("data-sanitizer-boundary", EXPORT_SANITIZER_BOUNDARY);
  container.innerHTML = clean;
  container.querySelectorAll("a[href]").forEach((link) => {
    const safeHref = toSafeHref(link.getAttribute("href"));
    if (!safeHref) {
      link.removeAttribute("href");
      return;
    }
    link.setAttribute("href", safeHref);
    if (isExternalHref(safeHref)) link.setAttribute("rel", "noopener noreferrer");
  });
  return container.innerHTML;
}

function body(title: string, html: string) {
  const d = new Date().toLocaleString("id-ID", { dateStyle: "long", timeStyle: "short" });
  title = escapeHtml(title);
  html = sanitizeExportHtml(html);
  return `<div class="doc"><h1>${title}</h1><p class="meta" style="border:0;margin:0 0 16px;padding:0">CDSS AI Keperawatan - ${d}</p>${html}<p class="meta">Dihasilkan oleh CDSS AI Keperawatan - perlu validasi penilaian klinis perawat.</p></div>`;
}
function dl(blob: Blob, name: string) { const u = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = u; a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 1000); }

export function exportWord(title: string, html: string) {
  dl(new Blob(["\uFEFF", `<!doctype html><html><head><meta charset="utf-8"><style>${LIGHT_CSS}</style></head><body>${body(title, html)}</body></html>`], { type: "application/msword" }), `${slug(title)}.doc`);
}
export async function exportPDF(title: string, html: string) {
  const html2pdf = (await import("html2pdf.js")).default;
  const h = document.createElement("div"); h.style.position = "fixed"; h.style.left = "-9999px"; h.style.background = "#fff";
  const st = document.createElement("style"); st.textContent = LIGHT_CSS; h.appendChild(st);
  const c = document.createElement("div"); c.setAttribute("data-sanitizer-boundary", EXPORT_SANITIZER_BOUNDARY); c.innerHTML = body(title, html); h.appendChild(c); document.body.appendChild(h);
  try { await html2pdf().set({ margin: [10, 10, 12, 10], filename: `${slug(title)}.pdf`, image: { type: "jpeg", quality: 0.96 }, html2canvas: { scale: 2, backgroundColor: "#ffffff" }, jsPDF: { unit: "mm", format: "a4", orientation: "portrait" } }).from(c).save(); }
  finally { h.remove(); }
}