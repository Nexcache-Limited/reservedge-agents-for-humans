# packages/ui-kit

Shared, framework-agnostic design system for ITAA web and mobile wrappers.

This package is the single semantic token contract for UI-00. Applications must consume these roles instead of defining Google, AWS, web, or mobile color systems. React, Vite, Expo, and Storybook remain deferred (ADR-0001).

## Public contract

- Package name: `@itaa/ui-kit`
- Status: `design-system`
- TypeScript entry: `src/index.ts`
- Stylesheet: `@itaa/ui-kit/itaa-ui-kit.css`, also available as `renderStylesheet()`

Primitives return HTML strings. They do not mount a framework, fetch, or encode purchase, approval, or supplier rules.

## Tokens

Typed source: `src/tokens/index.ts`. CSS custom properties are generated from that source.

Locked light colors (Reservedge workspace palette):

| Role                       | Value     | Use                                                    |
| -------------------------- | --------- | ------------------------------------------------------ |
| `text.primary` / ink       | `#221F1A` | Primary text                                           |
| `text.secondary` / muted   | `#6C685F` | Secondary text and metadata                            |
| `surface.page` / desk      | `#E9E6DF` | Outermost page                                         |
| `surface.canvas`           | `#F6F3EE` | App canvas                                             |
| `surface.raised` / surface | `#FFFFFF` | Cards                                                  |
| `surface.rail`             | `#1A1714` | Dark navigation rail                                   |
| `action.primary` / accent  | `#E85D2C` | Primary actions                                        |
| `status.confidence`        | `#1BA672` | Verified, safe completion, consent. Never “best deal”. |
| `status.attention`         | `#CB8A1B` | Needs review or factual caution. Not urgency.          |
| `status.denial`            | `#D9483B` | Failure, destructive warning, invalidated approval     |
| `border.default` / rule    | `#E6E1D8` | Decorative separators only                             |

Tinted fills use the exact Reservedge soft tokens (`#E3F4EB`, `#FBEFD6`, `#FBE3E0`, `#FBE9DE`). Dark mode is not painted; `themeSlots` includes `dark` for later work.

Typography (self-hosted, no runtime Google Fonts request):

- Interface and headings: Schibsted Grotesk (no serif headings in the product)
- Facts: JetBrains Mono, ui-monospace, with `tabular-nums`

Spacing base 4px; scale 4, 8, 12, 16, 24, 32, 40. Card radius 14–20px (default 16). Status pills are full-radius. Touch target 44×44. Motion 300ms `cubic-bezier(0.2, 0.7, 0.3, 1)`. `prefers-reduced-motion: reduce` sets duration to 0.

Layout tokens: rail 236px, intent list 320px, detail header 60px, detail max 940px, wide breakpoint 1180px.

Reservedge is the public product identity. ITAA remains the internal technical namespace (`@itaa/ui-kit`, `--itaa-*` custom properties) during the competition cut.

## Primitives

`textHtml`, `surfaceHtml`, `buttonHtml`, `statusIndicatorHtml`, `simulationBannerHtml`, `withFocusRing` / `FOCUS_RING_CLASS`, `visuallyHiddenHtml`, `liveRegionHtml`.

Button variants: `primary`, `consent`, `ghost`, `destructive`. States: default, hover, focus-visible, pressed, disabled, busy. A consequential disabled control must pass `id` plus `disabledReason`. `disabledReason` may be supplied only when the button is effectively disabled (`disabled === true` or `busy === true`); supplying it on an operable control fails closed. `disabledReason` still requires `id`. Busy exposes `aria-busy` and “Working”; it does not imply authorization.

`StatusIndicator` always requires a visible label. Color is supplementary.

`SimulationBanner` default label is exactly `SIMULATED - NO REAL CHARGES OR RESERVATIONS`. It is not dismissible. Placement values: `offers`, `authorization`, `receipt`, `demo-shell`.

## Contrast

Text pairs are checked at 4.5:1 and large text at 3:1 in `src/contrast.test.ts`. Meaningful control boundaries use `border.strong` (muted) or the ink focus ring. `border.default` / `rule` on white is a documented decorative-separator exception and is below 3:1; it must not be the only indicator of an interactive control.

## Harness

Open `harness/index.html` in a browser. It shows token swatches, typography, spacing and radius, primitive states, compact and wide SimulationBanner, a 200% zoom candidate, a reduced-motion candidate, and a keyboard focus sequence.

## Quality

```bash
pnpm --filter @itaa/ui-kit lint
pnpm --filter @itaa/ui-kit typecheck
pnpm --filter @itaa/ui-kit test
```
