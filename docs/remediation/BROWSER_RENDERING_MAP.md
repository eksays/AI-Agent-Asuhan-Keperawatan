# Browser Rendering Map - Phase 4

Status: Phase 4 browser rendering hardening implemented for Mermaid, SVG, Markdown, safe URLs, export HTML, CSP, and source-level sink scanning. All backend, LLM, registry, Markdown, Mermaid, and browser-storage strings remain untrusted unless a deterministic client-side boundary says otherwise.

Phase 4 scope is limited to Mermaid, SVG, Markdown, URL, CSP, and browser rendering hardening. Mermaid and external capabilities remain disabled by default.

## Guidance Inspected Read-Only

| Source | Practice Adopted |
|---|---|
| `https://github.com/openai/skills` | Inspect guidance only; do not install broad collections or execute scripts. |
| `https://github.com/trailofbits/skills` `audit-context-building` | Build bottom-up context before fixes. |
| `https://github.com/OWASP/secure-agent-playbook` `agent-security-audit` | Map prompt/output injection and data-exfiltration surfaces. |
| `https://github.com/OWASP/secure-agent-playbook` `ai-security-verification` | Verify output controls, input validation, and deployment configuration with evidence. |
| `https://github.com/OWASP/secure-agent-playbook` `web-security-review` | Review web sinks for XSS and security misconfiguration risk. |

## Trusted Rendering Rule

```text
LLM output
-> untrusted text
-> explicit parser
-> strict allowlist sanitization
-> safe rendering
```

## Rendering Sink Inventory

| Sink ID | File | Component/Function | Input Source | Previous Risk | Applied Mitigation | Test Case | Status |
|---|---|---|---|---|---|---|---|
| BR-001 | `frontend/components/ui/mermaid.tsx` | `Mermaid` | `Msg.mermaid` from backend/provider text | Loose Mermaid mode and unsanitized SVG DOM insertion | Mermaid `securityLevel: "strict"`, `flowchart.htmlLabels=false`, post-render SVG sanitizer, inert fallback, default capability disabled | `Mermaid is configured for strict SVG rendering`; SVG payload tests | Implemented |
| BR-002 | `frontend/components/messages.tsx` | `ReactMarkdown` | assistant message content | `rehypeRaw` parsed raw HTML before sanitizer | Removed `rehypeRaw`; raw HTML stays inert text; `rehypeSanitizeStrict` keeps a narrow Markdown allowlist | Markdown renderer source test | Implemented |
| BR-003 | `frontend/components/messages.tsx` | `MdLink` | Markdown links | Regex allowed ambiguous protocols and external links used only `noreferrer` | Central `toSafeHref` allowlist; unsafe links render inert; external links use `noopener noreferrer` | safe URL validation and Markdown link tests | Implemented |
| BR-004 | `frontend/components/messages.tsx` | export capture | rendered message DOM | `innerHTML` read could serialize unsafe DOM if renderer regresses | Read-only capture remains; export sink is sanitized again; bypass scanner documents the read | sink scanner allowlist | Implemented with residual dependency on renderer boundary |
| BR-005 | `frontend/lib/export.ts` | `sanitizeExportHtml` / `body` / `exportPDF` | rendered message HTML and title | wrapper/title were not escaped at export boundary; export inserted HTML into hidden DOM | title escaping, DOMPurify export allowlist, forbidden active tags, safe-link cleanup, documented export boundary | export sanitizer source test; sink scanner allowlist | Implemented |
| BR-006 | `frontend/next.config.mjs` | CSP | response headers | production `unsafe-eval`, broad `img-src`, missing explicit `frame-src` | dev-only `unsafe-eval`; `img-src` restricted; `frame-src 'none'` added; required directives preserved | CSP source test | Implemented with residual inline allowances |
| BR-007 | `frontend/components/dashboard.tsx` | static external EBP links | static source | external links require link hygiene | Existing static external links retain `noopener noreferrer`; no Phase 4 redesign | sink search and static review | Verified |
| BR-008 | `frontend/components/*` | image `src` values | static assets and local previews | capability-gated local image previews; no Phase 4 expansion | Markdown images disabled; CSP image sources restricted; photo analysis remains disabled by default | Markdown image test and CSP test | Implemented for Markdown; app image previews deferred to upload phase |

## Sanitization Boundaries

| Boundary | Location | Allowed Raw DOM Use | Reason | Guard |
|---|---|---|---|---|
| Sanitized Mermaid SVG insertion only | `frontend/components/ui/mermaid.tsx` | `dangerouslySetInnerHTML` | Mermaid returns SVG strings; sanitized SVG insertion remains required to display diagrams when explicitly enabled | `sanitizeMermaidSvg`, strict tag/attribute allowlists, unsafe-content post-check, inert fallback |
| Sanitized export HTML insertion | `frontend/lib/export.ts` | `innerHTML` on an isolated hidden export container | PDF/Word export needs a DOM/html serialization boundary | `sanitizeExportHtml`, export tag/attribute allowlists, safe-link cleanup, data boundary marker |
| Rendered message export capture | `frontend/components/messages.tsx` | read-only `ref.current?.innerHTML` | Existing export captures already rendered Markdown content | Markdown raw HTML disabled plus export re-sanitization |

## Sink Search Evidence

Search patterns included `innerHTML`, `dangerouslySetInnerHTML`, `insertAdjacentHTML`, `outerHTML`, `document.write`, `createContextualFragment`, `srcdoc`, `eval(`, `new Function(`, `javascript:`, `data:`, `foreignObject`, `mermaid`, `ReactMarkdown`, `rehypeRaw`, `remark`, `iframe`, `window.open`, `target=_blank`, `href=`, `src=`, and `style=`.

The Phase 4 bypass scanner allows exactly one `dangerouslySetInnerHTML` occurrence, documented as sanitized Mermaid SVG insertion only. It also documents four `innerHTML` occurrences: one read-only message export capture and three export-sanitizer/export-insertion boundaries.

## Closure Review Evidence

| Area | Evidence | Status |
|---|---|---|
| Sanitizer dependency | One direct sanitizer dependency is present: `dompurify@3.4.8`, locked in `frontend/package-lock.json`. It was selected because it provides maintained browser DOM/SVG sanitization with explicit SVG profiles and allowlist controls. | Verified |
| SVG adversarial coverage | Tests cover script, event handlers, iframe/srcdoc, `foreignObject`, `image`, `use`, external hrefs, `xlink:href`, `xml:base`, CSS `url(...)`, CSS `@import`, nested SVG, unknown namespace tags, malformed active SVG, Mermaid callback-like links, and Mermaid HTML-label-like `foreignObject` output. | Verified |
| URL canonicalization | `toSafeHref` decodes URL protocol syntax before validation, strips control/whitespace ambiguity, allows only HTTPS, relative paths, and anchors, and rejects encoded JavaScript/data/vbscript/file/blob/about/unknown/protocol-relative/credentialed URLs. | Verified |
| Markdown boundary | `rehypeRaw` is absent, raw HTML is not parsed, Markdown images render `null`, unsafe links render inert spans, and HTTPS links use `rel="noopener noreferrer"`. | Verified |
| Mermaid boundary | Mermaid rendering stays capability-gated and default-off; when enabled, Mermaid uses strict mode, `htmlLabels=false`, sanitizer output only reaches `dangerouslySetInnerHTML`, and raw SVG is never used as a fallback. | Verified |
| Export boundary | Export capture reads already-rendered HTML, then `sanitizeExportHtml` re-sanitizes with a strict tag/attribute allowlist, cleans links through `toSafeHref`, strips active SVG/iframe/script/image content, and escapes the export title. | Verified |
| CSP boundary | Production removes `unsafe-eval`; `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`, `form-action 'self'`, and `frame-src 'none'` are present. Production CSP still permits `script-src 'unsafe-inline'` and `style-src 'unsafe-inline'`. Nonce/hash-based CSP architecture remains required before stronger browser-security or release-gate claims. | Verified with residual |
| CI Bandit baseline | Dev Bandit hotfix `1904214bfd32b9e500cf1b75c04d9c1002fc265c` is an ancestor of the Phase 4 branch; local Bandit reports Medium 0 and High 0. | Verified |

## Residuals

| Residual | Severity | Status | Next Action |
|---|---|---|---|
| Production CSP still permits `script-src 'unsafe-inline'` and `style-src 'unsafe-inline'` | Medium | Documented residual; removing it safely requires nonce/hash architecture for Next.js hydration and generated styles. Nonce/hash-based CSP architecture remains required before stronger browser-security or release-gate claims. | Add nonce/hash-based CSP in a later frontend security hardening phase |
| Browser-rendered QA depends on local browser runtime availability | Medium | Phase 4 will attempt Browser QA; if unavailable, visual QA remains deferred and must not be claimed | Re-run Browser QA with active in-app browser before release-gate claims |
| Markdown export still relies on sanitized HTML serialization | Medium | DOMPurify and safe URL cleanup protect the export boundary, but export rendering remains an HTML sink | Keep scanner in CI and review any new export sink changes |
| Mermaid remains disabled by default | Safety control | Expected; no production enablement in Phase 4 | Enable only through a later controlled gate after security and clinical workflow review |

Gate A remains unmet until upload parser isolation and remaining gate controls are completed and verified. Phase 4 does not claim clinical approval, compliance, hospital readiness, or production readiness.
