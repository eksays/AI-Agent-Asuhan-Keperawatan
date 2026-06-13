import createDOMPurify from 'dompurify';

type Purifier = { sanitize: (dirty: string, config: Record<string, unknown>) => string };

export const SVG_SANITIZER_BOUNDARY = 'sanitized Mermaid SVG insertion only';

const MAX_SVG_BYTES = 200_000;
const ALLOWED_TAGS = ['svg', 'g', 'path', 'line', 'polyline', 'polygon', 'rect', 'circle', 'ellipse', 'text', 'tspan', 'defs', 'marker', 'linearGradient', 'radialGradient', 'stop', 'title', 'desc'];
const ALLOWED_ATTR = ['xmlns', 'viewBox', 'role', 'aria-label', 'aria-hidden', 'width', 'height', 'x', 'y', 'x1', 'x2', 'y1', 'y2', 'cx', 'cy', 'r', 'rx', 'ry', 'd', 'points', 'transform', 'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'opacity', 'fill-opacity', 'stroke-opacity', 'font-family', 'font-size', 'font-weight', 'text-anchor', 'dominant-baseline', 'marker-start', 'marker-mid', 'marker-end', 'id', 'class', 'offset', 'stop-color', 'stop-opacity'];
const FORBID_TAGS = ['script', 'foreignObject', 'iframe', 'style', 'image', 'use', 'audio', 'video', 'canvas', 'html', 'body', 'a'];

function getDefaultPurifier(): Purifier | null {
  if (typeof window === 'undefined') return null;
  return createDOMPurify(window) as unknown as Purifier;
}

export function hasUnsafeSvgContent(svg: string): boolean {
  const compact = svg.replace(/[\u0000-\u001F\u007F\s]+/g, '').toLowerCase();
  if (/<svg[\s>][\s\S]*<svg[\s>]/i.test(svg)) return true;
  if (/<\/?[a-z][\w.-]*:[\w.-]+[\s>]/i.test(svg)) return true;
  if (/<(?:script|foreignobject|iframe|image|use|a)\b/i.test(svg)) return true;
  if (/\son[a-z]+\s*=/i.test(svg)) return true;
  if (/\sxml:base\s*=/i.test(svg)) return true;
  if (/srcdoc\s*=/i.test(svg)) return true;
  if (compact.includes('javascript:') || compact.includes('data:text/html')) return true;
  if (/@import\s+url/i.test(svg)) return true;
  if (/\b(?:href|xlink:href)\s*=\s*['"](?!#)/i.test(svg)) return true;
  if (/url\(\s*(?!['"]?#)/i.test(svg)) return true;
  return false;
}

export function sanitizeMermaidSvg(svg: string, purifier: Purifier | null = getDefaultPurifier()): string | null {
  if (!purifier || typeof svg !== 'string' || !svg.trim()) return null;
  if (new TextEncoder().encode(svg).length > MAX_SVG_BYTES) return null;
  const clean = purifier.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: false }, ALLOWED_TAGS, ALLOWED_ATTR, FORBID_TAGS,
    ALLOW_DATA_ATTR: false, ALLOW_ARIA_ATTR: true, ALLOWED_URI_REGEXP: /^#[-_a-zA-Z0-9:.]+$/, KEEP_CONTENT: true,
  }).trim();
  if (!/^<svg[\s>]/i.test(clean)) return null;
  if (hasUnsafeSvgContent(clean)) return null;
  return clean;
}
