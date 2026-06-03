// HTTP Security Headers (Fase 1 "Zero Trust") — CSP dasar agar skrip dari domain asing DITOLAK browser.
const isDev = process.env.NODE_ENV !== "production";
const API = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

const csp = [
  "default-src 'self'",
  // Next butuh inline/eval untuk hidrasi & sebagian lib; namun src dari DOMAIN ASING tetap ditolak.
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  `connect-src 'self' ${API}${isDev ? " ws: wss:" : ""}`,
  "media-src 'self' blob:",          // kamera klinis (getUserMedia)
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(self), microphone=(), geolocation=()" },
  { key: "X-DNS-Prefetch-Control", value: "off" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Hapus console.* pada build PRODUCTION agar alur data tak bocor di console browser user (error tetap disisakan).
  compiler: { removeConsole: process.env.NODE_ENV === "production" ? { exclude: ["error"] } : false },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
