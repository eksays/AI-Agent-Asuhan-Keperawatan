---
name: Clinical Noir
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#353534'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1b1c1b'
  surface-container: '#1f201f'
  surface-container-high: '#2a2a29'
  surface-container-highest: '#353534'
  on-surface: '#e4e2e0'
  on-surface-variant: '#c4c7c7'
  inverse-surface: '#e4e2e0'
  inverse-on-surface: '#303030'
  outline: '#8e9192'
  outline-variant: '#444748'
  surface-tint: '#c6c6c6'
  primary: '#c6c6c6'
  on-primary: '#2f3131'
  primary-container: '#767777'
  on-primary-container: '#e4e2e0'
  inverse-primary: '#5d5e5f'
  secondary: '#c7c6c6'
  on-secondary: '#2f3131'
  secondary-container: '#464747'
  on-secondary-container: '#e3e2e2'
  tertiary: '#c6c6c7'
  on-tertiary: '#2f3131'
  tertiary-container: '#464747'
  on-tertiary-container: '#e3e2e2'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  background: '#131313'
  on-background: '#e4e2e0'
  surface-variant: '#353534'
typography:
  headline-xl:
    fontFamily: Outfit
    fontSize: 64px
    fontWeight: '600'
    lineHeight: '1.1'
    letterSpacing: -0.04em
  headline-lg:
    fontFamily: Outfit
    fontSize: 40px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.03em
  headline-md:
    fontFamily: Outfit
    fontSize: 24px
    fontWeight: '500'
    lineHeight: '1.3'
    letterSpacing: -0.02em
  title-lg:
    fontFamily: Outfit
    fontSize: 18px
    fontWeight: '500'
    lineHeight: '1.4'
    letterSpacing: -0.02em
  body-lg:
    fontFamily: Outfit
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: -0.01em
  body-md:
    fontFamily: Outfit
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: '0'
  mono-label:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: '1.4'
    letterSpacing: 0.02em
  mono-metric:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: '1.2'
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.125rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  gutter: 24px
  margin: 48px
  section-v-space: 120px
  card-padding: 32px
---

## 1. Visual Theme & Atmosphere

This design system is engineered for a high-stakes clinical decision-support environment where dense data must coexist with cognitive calm. The aesthetic is **Clinical Noir** — a monochrome fusion of high-end medical instrumentation and a developer-grade terminal. It is authoritative, quiet, and unmistakably "system-grade," never marketing-glossy.

The atmosphere is dark-mode-first and strictly **achromatic**: ink-charcoal canvases layered with brushed-silver foreground. There is no brand color competing for attention — the silver *is* the brand. Depth comes from tonal layering and hairline strokes, never from shadows, gradients, or glows. Layouts are editorial and asymmetric, built on a structured laboratory grid rather than the generic centered-SaaS template.

Density baseline **5** (Daily App Balanced), Variance **7** (Offset Asymmetric), Motion **5** (Fluid CSS with one perpetual signature loop).

## 2. Color Palette & Roles

The palette is intentionally **monochrome** — a single silver value carries every accent duty. Saturation is effectively zero except for the medical-coral reserved exclusively for errors.

- **Ink Charcoal** (`#131313`) — Primary canvas / background. Ink-like depth, never pure black.
- **Deep Bay** (`#0e0e0e`) — Lowest container (footer, terminal wells), one notch below canvas.
- **Surface Low / Container** (`#1b1c1b` → `#1f201f`) — Card and tile fills; subtle hierarchy through tonal lift.
- **Surface High / Highest** (`#2a2a29` → `#353534`) — Elevated panels, hover states, CTA wells.
- **Bright Silver** (`#e4e2e0`) — Primary text and headlines. The brightest value in the system.
- **Muted Silver** (`#c4c7c7`) — Secondary text, descriptions, narrative metadata.
- **Brushed Silver** (`#c6c6c6`) — **The singular accent.** Primary buttons, active states, focus, status pulses, the heartbeat indicator. On-accent text is **Slate Ink** (`#2f3131`).
- **Steel Outline** (`#8e9192`) — Mono labels, muted captions, idle indicators.
- **Hairline** (`#444748`) — 1px structural borders; often rendered as `rgba(255,255,255,0.05–0.10)` for floating panels.
- **Medical Coral** (`#ffb4ab`) — Introduced **only** for errors, alerts, and critical guardrail states. Never decorative.

**Banned:** any chromatic accent (teal, blue, purple, gold, amber, green), neon glows, gradient-filled headlines, multi-hue palettes, pure black `#000000`.

## 3. Typography Rules

A weight-driven, two-typeface system that separates *narrative content* from *system data*.

- **Display & Body — Outfit:** Modern geometric sans. Headlines tracked tight (`-0.02em` to `-0.04em`) for a dense, authoritative feel; body at generous `1.6` line-height, max ~65ch, in Muted Silver for long clinical logs.
- **Labels, Metrics & Chips — JetBrains Mono:** Reserved for timestamps, codes (SDKI/NANDA), terminal output, status tags, and clinical metrics. Uppercase mono with `0.05em` tracking signals "this is machine data," differentiating it from prose.
- **Emphasis:** Use font weight and the Brushed Silver accent — never italics.
- **Banned:** Inter, generic system-ui for display, all serif fonts, gradient text, oversized screaming headlines.

## 4. Component Stylings

- **Buttons:** Flat, square-ish (`2px` radius). Primary = Brushed Silver fill with Slate Ink text; secondary = ghost with hairline border and Bright Silver text. Tactile `active:scale-95` press feedback. No glow, no gradient, no custom cursor.
- **Cards / Bento Tiles:** Surface Low fill, `8px` radius, `32px` internal padding, 1px hairline border that warms to a silver border on hover. Depth via tone, not shadow. Tiles vary in column-span (8/4/6) to form an asymmetric bento — never three equal columns.
- **Inputs:** Surface-colored fill or hairline outline only. Label above, error (Medical Coral) below. Focus = simple silver border, no glow, no floating label.
- **Clinical Chips:** JetBrains Mono `11px`, rectangular `2px` radius, `rgba(255,255,255,0.05)` fill, hairline border. For LLM/standard badges (CLAUDE, GPT-4O, SDKI…).
- **Terminal Panels:** Surface-lowest well with a traffic-light header (coral/silver dots) and a `TERMINAL_VIEW` mono caption; used for live-analysis previews.
- **Status Indicators:** 8px solid dots — Brushed Silver = active/healthy (with a perpetual pulse-ring), Steel = idle, Medical Coral = alert.
- **Data Grids:** Hairline row dividers; headers in uppercase Mono-Metric / Steel.
- **Loaders:** Skeletal shimmer matching layout dimensions — never circular spinners.

## 5. Layout Principles

- Strict **12-column CSS grid**, max-width `1536px` (screen-2xl), `48px` page margins, `24px` gutters.
- **Asymmetric by default:** hero content occupies 8 columns with a 4-column instrumentation/terminal panel — centered hero is banned.
- Generous **`120px` vertical rhythm** between sections so clinical data breathes.
- All spacing is a multiple of the `4px` base unit. CSS Grid over flexbox `calc()` math.
- Full-height regions use `min-h-[100dvh]`, never `h-screen`.
- No overlapping elements — every element owns a clean spatial zone.
- **Mobile (<768px):** 12-col collapses to single column; side-aligned metadata reflows above the headline; no horizontal scroll ever.

## 6. Motion & Interaction

- **Spring-physics feel** (`stiffness 100, damping 20`) for interactive transitions; no linear easing.
- **Signature perpetual loop:** the `heartbeat` pulse-ring on the brand mark and active status dots — a slow `cl-pulse-ring` that conveys a live, monitored system.
- **Staggered reveals:** hero and tile groups cascade in via `cl-fade-up` with incremental delays — never mount instantly.
- Animate only `transform` and `opacity` (hardware-accelerated). Honor `prefers-reduced-motion`.
- Iconography via **Material Symbols Outlined** (weight 300), thin and instrument-like.

## 7. Anti-Patterns (Banned)

- No chromatic accents — this is a **monochrome** system; the only non-gray is error-coral.
- No emojis, no Inter, no serif fonts, no `system-ui` for display.
- No pure black `#000000`; no neon / outer-glow shadows; no gradient-filled headlines.
- No centered hero; no three-equal-column feature row; no overlapping layers.
- No drop shadows for elevation — tonal layering + hairlines only.
- No custom mouse cursors, no filler UI ("Scroll to explore", bouncing chevrons).
- No AI copy clichés ("Elevate", "Seamless", "Unleash", "Next-Gen"); no fake round metrics; no generic placeholder names.
- No broken Unsplash links — use `picsum.photos` or inline SVG.
