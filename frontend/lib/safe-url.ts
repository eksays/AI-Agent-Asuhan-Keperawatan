const UNSAFE_PROTOCOLS = new Set(['javascript', 'data', 'vbscript', 'file', 'blob', 'about']);

function decodeProtocolSyntax(value: string): string {
  let current = value.replace(/&(?:#0*58|#x0*3a|colon);/gi, ':');
  for (let i = 0; i < 3; i += 1) {
    try {
      const decoded = decodeURIComponent(current);
      if (decoded === current) break;
      current = decoded;
    } catch {
      break;
    }
  }
  return current;
}

function compactSchemePrefix(value: string): string {
  return decodeProtocolSyntax(value).replace(/[\u0000-\u001F\u007F\s]+/g, '').toLowerCase();
}

export function isSafeHref(raw: unknown): raw is string {
  return toSafeHref(raw) !== null;
}

export function isExternalHref(href: string): boolean {
  try {
    return new URL(href).protocol === 'https:';
  } catch {
    return false;
  }
}

export function toSafeHref(raw: unknown): string | null {
  if (typeof raw !== 'string') return null;
  const href = raw.trim();
  if (!href || /[\u0000-\u001F\u007F]/.test(href)) return null;
  if (href.startsWith('//') || href.startsWith('\\\\')) return null;

  const compact = compactSchemePrefix(href);
  const schemeMatch = compact.match(/^([a-z][a-z0-9+.-]*):/i);
  if (schemeMatch) {
    const scheme = schemeMatch[1].toLowerCase();
    if (UNSAFE_PROTOCOLS.has(scheme)) return null;
    if (scheme !== 'https') return null;
    try {
      const url = new URL(href);
      if (url.username || url.password) return null;
      return url.href;
    } catch {
      return null;
    }
  }

  if (href.startsWith('#')) return href;
  if (href.startsWith('/')) return href.startsWith('//') ? null : href;
  if (href.startsWith('./') || href.startsWith('../')) return href;
  return null;
}
