import {
  breakpointsPx,
  colorRoles,
  CSS_VAR,
  elevation,
  focusTreatment,
  fontFamilies,
  layers,
  layoutPx,
  motion,
  radiusPx,
  spacingPx,
  touchTargetPx,
  typeRoles,
} from "./tokens/index.js";

function px(value: number): string {
  return `${value}px`;
}

function fontFaces(): string {
  return `@font-face {
  font-family: "Schibsted Grotesk";
  font-style: normal;
  font-weight: 400 800;
  font-display: swap;
  src: url("./fonts/schibsted-grotesk-latin-wght-normal.woff2") format("woff2");
}
@font-face {
  font-family: "JetBrains Mono";
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url("./fonts/jetbrains-mono-latin-400-normal.woff2") format("woff2");
}
@font-face {
  font-family: "JetBrains Mono";
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url("./fonts/jetbrains-mono-latin-500-normal.woff2") format("woff2");
}
@font-face {
  font-family: "JetBrains Mono";
  font-style: normal;
  font-weight: 600;
  font-display: swap;
  src: url("./fonts/jetbrains-mono-latin-600-normal.woff2") format("woff2");
}
`;
}

function customProperties(): string {
  const pairs: readonly (readonly [string, string])[] = [
    [CSS_VAR.textPrimary, colorRoles.text.primary],
    [CSS_VAR.textSecondary, colorRoles.text.secondary],
    [CSS_VAR.textTertiary, colorRoles.text.tertiary],
    [CSS_VAR.textInverse, colorRoles.text.inverse],
    [CSS_VAR.surfacePage, colorRoles.surface.page],
    [CSS_VAR.surfaceCanvas, colorRoles.surface.canvas],
    [CSS_VAR.surfaceRaised, colorRoles.surface.raised],
    [CSS_VAR.surfaceMuted, colorRoles.surface.muted],
    [CSS_VAR.surfaceRail, colorRoles.surface.rail],
    [CSS_VAR.surfaceConfidenceTint, colorRoles.surface.confidenceTint],
    [CSS_VAR.surfaceAttentionTint, colorRoles.surface.attentionTint],
    [CSS_VAR.surfaceDenialTint, colorRoles.surface.denialTint],
    [CSS_VAR.surfaceInfoTint, colorRoles.surface.infoTint],
    [CSS_VAR.surfaceAccentSoft, colorRoles.surface.accentSoft],
    [CSS_VAR.surfaceNeutralTint, colorRoles.surface.neutralTint],
    [CSS_VAR.surfaceSimulation, colorRoles.surface.simulation],
    [CSS_VAR.statusNeutral, colorRoles.status.neutral],
    [CSS_VAR.statusWorking, colorRoles.status.working],
    [CSS_VAR.statusAttention, colorRoles.status.attention],
    [CSS_VAR.statusConfidence, colorRoles.status.confidence],
    [CSS_VAR.statusDenial, colorRoles.status.denial],
    [CSS_VAR.statusInfo, colorRoles.status.info],
    [CSS_VAR.statusOffline, colorRoles.status.offline],
    [CSS_VAR.borderDefault, colorRoles.border.default],
    [CSS_VAR.borderSubtle, colorRoles.border.subtle],
    [CSS_VAR.borderStrong, colorRoles.border.strong],
    [CSS_VAR.borderFocus, colorRoles.border.focus],
    [CSS_VAR.actionPrimary, colorRoles.action.primary],
    [CSS_VAR.actionPressed, colorRoles.action.pressed],
    [CSS_VAR.actionConsent, colorRoles.action.consent],
    [CSS_VAR.actionDestructive, colorRoles.action.destructive],
    [CSS_VAR.actionGhost, colorRoles.action.ghost],
    [CSS_VAR.focusRing, colorRoles.focus.ring],
    [CSS_VAR.layoutRail, px(layoutPx.rail)],
    [CSS_VAR.layoutList, px(layoutPx.list)],
    [CSS_VAR.layoutDetailHeader, px(layoutPx.detailHeader)],
    [CSS_VAR.layoutDetailMax, px(layoutPx.detailMax)],
    [CSS_VAR.spaceXs, px(spacingPx.xs)],
    [CSS_VAR.spaceSm, px(spacingPx.sm)],
    [CSS_VAR.spaceMd, px(spacingPx.md)],
    [CSS_VAR.spaceLg, px(spacingPx.lg)],
    [CSS_VAR.spaceXl, px(spacingPx.xl)],
    [CSS_VAR.space2xl, px(spacingPx["2xl"])],
    [CSS_VAR.space3xl, px(spacingPx["3xl"])],
    [CSS_VAR.radiusCard, px(radiusPx.card)],
    [CSS_VAR.radiusCardMin, px(radiusPx.cardMin)],
    [CSS_VAR.radiusCardMax, px(radiusPx.cardMax)],
    [CSS_VAR.radiusPill, px(radiusPx.pill)],
    [CSS_VAR.touchMin, px(touchTargetPx.min)],
    [CSS_VAR.motionDuration, `${motion.durationMs.standard}ms`],
    [CSS_VAR.motionEasing, motion.easing.standard],
    [CSS_VAR.focusWidth, px(focusTreatment.widthPx)],
    [CSS_VAR.focusOffset, px(focusTreatment.offsetPx)],
    [CSS_VAR.fontEditorial, fontFamilies.editorial],
    [CSS_VAR.fontInterface, fontFamilies.interface],
    [CSS_VAR.fontFacts, fontFamilies.facts],
    [CSS_VAR.fontSizeBody, `${typeRoles.body.fontSizeRem}rem`],
    [CSS_VAR.elevationCard, elevation.card],
    [CSS_VAR.zBase, String(layers.base)],
    [CSS_VAR.zRaised, String(layers.raised)],
    [CSS_VAR.zBanner, String(layers.banner)],
    [CSS_VAR.zFocus, String(layers.focus)],
    [CSS_VAR.breakpointWide, px(breakpointsPx.wide)],
  ];

  return pairs.map(([name, value]) => `  ${name}: ${value};`).join("\n");
}

export function renderStylesheet(): string {
  return `/* @itaa/ui-kit — generated from typed semantic tokens. Do not add raw component colors. */
${fontFaces()}
:root {
  color-scheme: light;
${customProperties()}
}

@media (prefers-reduced-motion: reduce) {
  :root {
    ${CSS_VAR.motionDuration}: ${motion.reducedMotionDurationMs}ms;
  }

  .itaa-button,
  .itaa-status,
  .itaa-surface,
  .itaa-text,
  .itaa-simulation-banner {
    transition: none !important;
    animation: none !important;
  }
}

.itaa-visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

.itaa-focus-ring:focus,
.itaa-button:focus {
  outline: none;
}

.itaa-focus-ring:focus-visible,
.itaa-button:focus-visible {
  outline: var(${CSS_VAR.focusWidth}) solid var(${CSS_VAR.focusRing});
  outline-offset: var(${CSS_VAR.focusOffset});
}

.itaa-text {
  margin: 0;
  color: var(${CSS_VAR.textPrimary});
}

.itaa-text--display {
  font-family: var(${CSS_VAR.fontInterface});
  letter-spacing: -0.02em;
  font-size: ${typeRoles.display.fontSizeRem}rem;
  font-weight: ${typeRoles.display.fontWeight};
  line-height: ${typeRoles.display.lineHeight};
}

.itaa-text--heading {
  font-family: var(${CSS_VAR.fontInterface});
  letter-spacing: -0.02em;
  font-size: ${typeRoles.heading.fontSizeRem}rem;
  font-weight: ${typeRoles.heading.fontWeight};
  line-height: ${typeRoles.heading.lineHeight};
}

.itaa-text--body {
  font-family: var(${CSS_VAR.fontInterface});
  font-size: var(${CSS_VAR.fontSizeBody});
  font-weight: ${typeRoles.body.fontWeight};
  line-height: ${typeRoles.body.lineHeight};
}

.itaa-text--label {
  font-family: var(${CSS_VAR.fontInterface});
  font-size: var(${CSS_VAR.fontSizeBody});
  font-weight: ${typeRoles.label.fontWeight};
  line-height: ${typeRoles.label.lineHeight};
}

.itaa-text--meta {
  font-family: var(${CSS_VAR.fontInterface});
  font-size: ${typeRoles.meta.fontSizeRem}rem;
  font-weight: ${typeRoles.meta.fontWeight};
  line-height: ${typeRoles.meta.lineHeight};
  color: var(${CSS_VAR.textSecondary});
}

.itaa-text--fact {
  font-family: var(${CSS_VAR.fontFacts});
  font-size: var(${CSS_VAR.fontSizeBody});
  font-weight: ${typeRoles.fact.fontWeight};
  line-height: ${typeRoles.fact.lineHeight};
  font-variant-numeric: ${typeRoles.fact.fontVariantNumeric};
}

.itaa-surface {
  box-sizing: border-box;
  background: var(${CSS_VAR.surfaceRaised});
  color: var(${CSS_VAR.textPrimary});
  border: 1px solid var(${CSS_VAR.borderDefault});
  border-radius: var(${CSS_VAR.radiusCard});
  z-index: var(${CSS_VAR.zRaised});
}

.itaa-surface--raised {
  box-shadow: var(${CSS_VAR.elevationCard});
}

.itaa-surface--pad-sm {
  padding: var(${CSS_VAR.spaceSm});
}

.itaa-surface--pad-md {
  padding: var(${CSS_VAR.spaceMd});
}

.itaa-surface--pad-lg {
  padding: var(${CSS_VAR.spaceLg});
}

.itaa-surface--pad-xl {
  padding: var(${CSS_VAR.spaceXl});
}

.itaa-button {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(${CSS_VAR.spaceSm});
  min-height: var(${CSS_VAR.touchMin});
  min-width: var(${CSS_VAR.touchMin});
  padding: var(${CSS_VAR.spaceMd}) var(${CSS_VAR.spaceLg});
  border-radius: var(${CSS_VAR.radiusCard});
  border-width: 1px;
  border-style: solid;
  font-family: var(${CSS_VAR.fontInterface});
  font-size: var(${CSS_VAR.fontSizeBody});
  font-weight: 600;
  line-height: 1.25;
  transition-property: background-color, color, border-color, box-shadow;
  transition-duration: var(${CSS_VAR.motionDuration});
  transition-timing-function: var(${CSS_VAR.motionEasing});
  cursor: pointer;
}

.itaa-button--primary {
  background: var(${CSS_VAR.actionPrimary});
  color: var(${CSS_VAR.textInverse});
  border-color: var(${CSS_VAR.actionPrimary});
}

.itaa-button--consent {
  background: var(${CSS_VAR.actionConsent});
  color: var(${CSS_VAR.textInverse});
  border-color: var(${CSS_VAR.actionConsent});
}

.itaa-button--destructive {
  background: var(${CSS_VAR.actionDestructive});
  color: var(${CSS_VAR.textInverse});
  border-color: var(${CSS_VAR.actionDestructive});
}

.itaa-button--ghost {
  background: var(${CSS_VAR.actionGhost});
  color: var(${CSS_VAR.textPrimary});
  border-color: var(${CSS_VAR.borderStrong});
}

@media (hover: hover) {
  .itaa-button--primary:hover:not(:disabled) {
    background: var(${CSS_VAR.actionPressed});
    border-color: var(${CSS_VAR.actionPressed});
  }

  .itaa-button--consent:hover:not(:disabled) {
    filter: brightness(0.96);
  }

  .itaa-button--destructive:hover:not(:disabled) {
    filter: brightness(0.96);
  }

  .itaa-button--ghost:hover:not(:disabled) {
    background: var(${CSS_VAR.surfaceCanvas});
  }
}

.itaa-button:active:not(:disabled) {
  transform: none;
}

.itaa-button:disabled,
.itaa-button[aria-disabled="true"] {
  opacity: 0.48;
  cursor: not-allowed;
}

.itaa-button[aria-busy="true"] {
  cursor: progress;
}

.itaa-status {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  gap: var(${CSS_VAR.spaceSm});
  padding: var(${CSS_VAR.spaceSm}) var(${CSS_VAR.spaceMd});
  border-radius: var(${CSS_VAR.radiusPill});
  border: 1px solid var(${CSS_VAR.borderStrong});
  font-family: var(${CSS_VAR.fontInterface});
  font-size: var(${CSS_VAR.fontSizeBody});
  line-height: 1.3;
  color: var(${CSS_VAR.textPrimary});
  background: var(${CSS_VAR.surfaceRaised});
}

.itaa-status__swatch {
  width: 0.75rem;
  height: 0.75rem;
  border-radius: var(${CSS_VAR.radiusPill});
  background: var(${CSS_VAR.statusNeutral});
  flex: 0 0 auto;
}

.itaa-status--neutral {
  background: var(${CSS_VAR.surfaceNeutralTint});
}

.itaa-status--working {
  background: var(${CSS_VAR.surfaceNeutralTint});
}

.itaa-status--working .itaa-status__swatch {
  background: var(${CSS_VAR.statusWorking});
}

.itaa-status--attention {
  background: var(${CSS_VAR.surfaceAttentionTint});
}

.itaa-status--attention .itaa-status__swatch {
  background: var(${CSS_VAR.statusAttention});
}

.itaa-status--confidence {
  background: var(${CSS_VAR.surfaceConfidenceTint});
}

.itaa-status--confidence .itaa-status__swatch {
  background: var(${CSS_VAR.statusConfidence});
}

.itaa-status--denial {
  background: var(${CSS_VAR.surfaceDenialTint});
}

.itaa-status--denial .itaa-status__swatch {
  background: var(${CSS_VAR.statusDenial});
}

.itaa-status--offline {
  background: var(${CSS_VAR.surfaceNeutralTint});
}

.itaa-status--offline .itaa-status__swatch {
  background: var(${CSS_VAR.statusOffline});
}

.itaa-simulation-banner {
  box-sizing: border-box;
  width: 100%;
  margin: 0;
  background: var(${CSS_VAR.surfaceSimulation});
  color: var(${CSS_VAR.textInverse});
  font-family: var(${CSS_VAR.fontInterface});
  font-size: var(${CSS_VAR.fontSizeBody});
  font-weight: 700;
  line-height: 1.4;
  letter-spacing: 0.02em;
  border: var(${CSS_VAR.focusWidth}) solid var(${CSS_VAR.textPrimary});
  overflow: visible;
  overflow-wrap: anywhere;
  z-index: var(${CSS_VAR.zBanner});
}

.itaa-simulation-banner__label {
  margin: 0;
}

.itaa-simulation-banner--compact {
  max-width: 20rem;
  padding: var(${CSS_VAR.spaceSm}) var(${CSS_VAR.spaceMd});
}

.itaa-simulation-banner--wide {
  max-width: var(${CSS_VAR.breakpointWide});
  padding: var(${CSS_VAR.spaceLg}) var(${CSS_VAR.spaceXl});
}
`;
}
