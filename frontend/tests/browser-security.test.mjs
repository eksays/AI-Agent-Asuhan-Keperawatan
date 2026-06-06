import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import createDOMPurify from 'dompurify';
import { JSDOM } from 'jsdom';
import { toSafeHref } from '../lib/safe-url.ts';
import { sanitizeMermaidSvg } from '../lib/svg-sanitize.ts';

const root = new URL('..', import.meta.url);
const rootPath = fileURLToPath(root);
const read = (path) => readFileSync(new URL(path, root), 'utf8');
const purifier = createDOMPurify(new JSDOM('<!doctype html>').window);

function sanitizedSvg(payload) {
  return sanitizeMermaidSvg(`<svg xmlns="http://www.w3.org/2000/svg"><g><text>ok</text>${payload}</g></svg>`, purifier);
}

function collectSourceFiles(start) {
  const entries = readdirSync(start, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = join(start, entry.name);
    if (entry.isDirectory()) {
      if (['node_modules', '.next', 'tests'].includes(entry.name)) continue;
      files.push(...collectSourceFiles(full));
      continue;
    }
    if (/\.(?:js|mjs|ts|tsx)$/.test(entry.name)) files.push(relative(rootPath, full).replace(/\\/g, '/'));
  }
  return files;
}

test('safe URL validation uses a narrow allowlist', () => {
  assert.equal(toSafeHref('https://example.com'), 'https://example.com/');
  assert.equal(toSafeHref('/internal-path'), '/internal-path');
  assert.equal(toSafeHref('./relative'), './relative');
  assert.equal(toSafeHref('../relative'), '../relative');
  assert.equal(toSafeHref('#section'), '#section');
  assert.equal(toSafeHref('http://example.com'), null);
  assert.equal(toSafeHref('//evil.example'), null);
  assert.equal(toSafeHref('https://user:pass@example.com'), null);
  assert.equal(toSafeHref('javascript:alert(1)'), null);
  assert.equal(toSafeHref('JaVaScRiPt:alert(1)'), null);
  assert.equal(toSafeHref(' javascript:alert(1)'), null);
  assert.equal(toSafeHref('java\u0000script:alert(1)'), null);
  assert.equal(toSafeHref('java%0Ascript:alert(1)'), null);
  assert.equal(toSafeHref('%6a%61%76%61%73%63%72%69%70%74%3Aalert(1)'), null);
  assert.equal(toSafeHref('%256a%2561%2576%2561%2573%2563%2572%2569%2570%2574%253Aalert(1)'), null);
  assert.equal(toSafeHref('data:text/html,<script>alert(1)</script>'), null);
  assert.equal(toSafeHref('vbscript:msgbox(1)'), null);
  assert.equal(toSafeHref('file:///etc/passwd'), null);
  assert.equal(toSafeHref('blob:https://example.com/id'), null);
  assert.equal(toSafeHref('about:blank'), null);
  assert.equal(toSafeHref('unknown-scheme:test'), null);
});

test('Mermaid is configured for strict SVG rendering', () => {
  const source = read('components/ui/mermaid.tsx');
  assert.match(source, /securityLevel:\s*"strict"/);
  assert.match(source, /flowchart:\s*\{\s*htmlLabels:\s*false\s*\}/);
  assert.match(source, /sanitizeMermaidSvg\(rendered\)/);
  assert.match(source, /unsafe_svg_rejected/);
  assert.match(source, /data-sanitizer-boundary=\{SVG_SANITIZER_BOUNDARY\}/);
});

test('SVG sanitizer strips or rejects executable SVG payloads', () => {
  const payloads = [
    '<script>alert(1)</script>',
    '<svg onload="alert(1)">',
    '<img src="x" onerror="alert(1)">',
    '<a href="javascript:alert(1)">click</a>',
    '<use href="javascript:alert(1)"></use>',
    '<path onclick="alert(1)" d="M0 0"></path>',
    '<path onmouseover="alert(1)" d="M0 0"></path>',
    '<path href=" JaVaScRiPt:alert(1)" d="M0 0"></path>',
    '<path href="%6a%61%76%61%73%63%72%69%70%74:alert(1)" d="M0 0"></path>',
    '<path href="java&#x0a;script:alert(1)" d="M0 0"></path>',
  ];
  for (const payload of payloads) {
    const clean = sanitizedSvg(payload) || '';
    assert.doesNotMatch(clean, /<script|onload|onclick|onerror|onmouseover|javascript:|%6a%61|java&#x0a;script|<use|<a\b/i, payload);
  }
});

test('SVG sanitizer blocks embedded documents and data HTML', () => {
  const payloads = [
    '<foreignObject><iframe srcdoc="<script>alert(1)</script>"></iframe></foreignObject>',
    '<image href="data:text/html,<script>alert(1)</script>"></image>',
    '<iframe src="https://evil.example"></iframe>',
    '<svg><foreignObject><div onclick="alert(1)">html label</div></foreignObject></svg>',
    '<evil:svg xmlns:evil="https://evil.example"><evil:script>alert(1)</evil:script></evil:svg>',
  ];
  for (const payload of payloads) {
    const clean = sanitizedSvg(payload) || '';
    assert.doesNotMatch(clean, /foreignObject|<iframe|srcdoc|data:text\/html|<image|evil:|<script/i, payload);
  }
});

test('SVG sanitizer removes style imports and external references', () => {
  const payloads = [
    '<style>@import url(https://evil.example)</style>',
    '<path style="fill:url(https://evil.example/x)" d="M0 0"></path>',
    '<path href="https://evil.example/x" d="M0 0"></path>',
    '<path xlink:href="javascript:alert(1)" d="M0 0"></path>',
    '<path xml:base="https://evil.example/" d="M0 0"></path>',
    '<use href="#safe-node"></use>',
    '<image href="https://evil.example/pixel.png"></image>',
    '<rect fill="url(https://evil.example/paint)" />',
  ];
  for (const payload of payloads) {
    const clean = sanitizedSvg(payload) || '';
    assert.doesNotMatch(clean, /@import|https:\/\/evil\.example|javascript:|href=|xml:base|<use|<image/i, payload);
  }
});

test('SVG sanitizer rejects nested, namespaced, and malformed active payloads', () => {
  assert.equal(sanitizedSvg('<svg><g><text>nested</text></g></svg>'), null);

  const unknownNamespace = sanitizedSvg('<foo:bar xmlns:foo="https://evil.example"><foo:baz /></foo:bar>') || '';
  assert.doesNotMatch(unknownNamespace, /foo:|evil\.example/i);

  const malformed = sanitizeMermaidSvg('<svg><g><text>ok</text><script>alert(1)', purifier) || '';
  assert.doesNotMatch(malformed, /script|alert\(1\)/i);
});

test('Mermaid callback and HTML-label hazards stay behind strict sanitizer boundaries', () => {
  const callbackSvg = sanitizedSvg('<a href="javascript:alert(1)"><text>click callback</text></a>') || '';
  assert.doesNotMatch(callbackSvg, /<a\b|javascript:|onclick/i);

  const htmlLabelSvg = sanitizedSvg('<foreignObject><div onclick="alert(1)">HTML label</div></foreignObject>') || '';
  assert.doesNotMatch(htmlLabelSvg, /foreignObject|onclick|<div\b/i);
});

test('Markdown renderer disables raw HTML, images, and unsafe links', () => {
  const source = read('components/messages.tsx');
  assert.doesNotMatch(source, /rehypeRaw/);
  assert.match(source, /img:\s*\(\)\s*=>\s*null/);
  assert.match(source, /toSafeHref\(href\)/);
  assert.match(source, /noopener noreferrer/);
  assert.match(source, /if \(!safeHref\) return <span>\{children\}<\/span>/);

  for (const href of [
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    '%6a%61%76%61%73%63%72%69%70%74:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'vbscript:msgbox(1)',
  ]) assert.equal(toSafeHref(href), null);

  assert.equal(toSafeHref('https://example.com'), 'https://example.com/');
  assert.equal(toSafeHref('/internal-path'), '/internal-path');
  assert.equal(toSafeHref('#section'), '#section');
});

test('export sanitizer has a strict allowlist boundary and re-sanitizes captured HTML', () => {
  const source = read('lib/export.ts');
  for (const forbidden of ['script', 'iframe', 'style', 'img', 'object', 'svg', 'math', 'foreignObject']) {
    assert.match(source, new RegExp(`EXPORT_FORBID_TAGS = \\[.*"${forbidden}"`, 's'));
  }
  assert.match(source, /ALLOW_DATA_ATTR:\s*false/);
  assert.match(source, /ALLOW_ARIA_ATTR:\s*false/);
  assert.match(source, /ALLOWED_URI_REGEXP/);
  assert.match(source, /toSafeHref\(link\.getAttribute\("href"\)\)/);
  assert.match(source, /link\.removeAttribute\("href"\)/);
  assert.match(source, /link\.setAttribute\("href", safeHref\)/);
  assert.match(source, /noopener noreferrer/);
  assert.match(source, /EXPORT_SANITIZER_BOUNDARY/);
  assert.match(source, /title = escapeHtml\(title\)/);
  assert.match(source, /sanitizeExportHtml\(html\)/);
  assert.match(source, /c\.innerHTML = body\(title, html\)/);
  assert.match(source, /new Blob\(\["\\uFEFF"/);
});

test('CSP keeps required browser hardening directives', () => {
  const csp = read('next.config.mjs');
  for (const directive of ['object-src', 'base-uri', 'frame-ancestors', 'form-action', 'frame-src']) assert.match(csp, new RegExp(directive));
  assert.match(csp, /scriptSrc = isDev/);
  assert.match(csp, /\? "script-src 'self' 'unsafe-inline' 'unsafe-eval'" : "script-src 'self' 'unsafe-inline'"/);
  assert.doesNotMatch(csp.match(/: "(script-src [^"]+)";/)?.[1] || '', /unsafe-eval/);
  assert.match(csp, /img-src 'self' data: blob:/);
  assert.match(csp, /connect-src 'self'/);
  assert.match(csp, /style-src 'self' 'unsafe-inline'/);
});

test('dangerous rendering sink scanner has only documented source matches', () => {
  const files = [
    ...collectSourceFiles(join(rootPath, 'components')),
    ...collectSourceFiles(join(rootPath, 'lib')),
    'next.config.mjs',
  ];
  const sourceByFile = new Map(files.map((file) => [file, read(file)]));

  const unexpectedPatterns = [/securityLevel:\s*["']loose/, /rehypeRaw/, /insertAdjacentHTML/, /outerHTML/, /document\.write/, /eval\(/, /new Function\(/];
  for (const [file, source] of sourceByFile) {
    for (const pattern of unexpectedPatterns) assert.doesNotMatch(source, pattern, `${file} unexpectedly matched ${pattern}`);
  }

  const joined = [...sourceByFile].map(([file, source]) => `\n/* ${file} */\n${source}`).join('\n');
  assert.equal((joined.match(/dangerouslySetInnerHTML/g) || []).length, 1);
  assert.match(read('components/ui/mermaid.tsx'), /sanitizeMermaidSvg/);
  assert.match(read('components/ui/mermaid.tsx'), /SVG_SANITIZER_BOUNDARY/);
  assert.equal((joined.match(/innerHTML/g) || []).length, 4);
  assert.match(read('components/messages.tsx'), /ref\.current\?\.innerHTML/);
  assert.match(read('lib/export.ts'), /container\.innerHTML = clean/);
  assert.match(read('lib/export.ts'), /return container\.innerHTML/);
  assert.match(read('lib/export.ts'), /c\.innerHTML = body\(title, html\)/);

  assert.match(read('lib/svg-sanitize.ts'), /srcdoc/);
  assert.match(read('lib/svg-sanitize.ts'), /xlink:href/);
  assert.match(read('lib/svg-sanitize.ts'), /xml:base/);
  assert.match(read('lib/svg-sanitize.ts'), /data:text\/html/);
});
