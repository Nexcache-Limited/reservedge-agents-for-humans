export const LOCKED_LIGHT_COLORS = {
  ink: "#221F1A",
  muted: "#6C685F",
  tertiary: "#9B968B",
  desk: "#E9E6DF",
  canvas: "#F6F3EE",
  surface: "#FFFFFF",
  mutedFill: "#F0EDE6",
  rail: "#1A1714",
  accent: "#E85D2C",
  accentPressed: "#CE4E22",
  accentSoft: "#FBE9DE",
  confidence: "#1BA672",
  attention: "#CB8A1B",
  denial: "#D9483B",
  info: "#2F6FED",
  rule: "#E6E1D8",
  ruleSubtle: "#EFEBE3",
} as const;

export const COLOR_USAGE = {
  ink: "Primary text and neutral high-emphasis controls",
  muted: "Secondary text and metadata",
  desk: "Outermost page / desk around the app canvas",
  surface: "Cards and principal surfaces",
  confidence: "Verified, safe completion, and consent; never color-only; never best deal",
  attention: "Needs-user action, low-confidence review, factual expiry caution; not urgency",
  denial: "Failure, destructive warning, or invalidated approval only",
  rule: "Decorative borders and separators; not a meaningful control boundary",
} as const;

export const TINT_MIX = 0.08;

export type HexColor = `#${string}`;

export function parseHex(hex: string): readonly [number, number, number] {
  const normalized = hex.startsWith("#") ? hex.slice(1) : hex;
  if (normalized.length !== 6) {
    throw new Error(`Unsupported hex color: ${hex}`);
  }
  const red = Number.parseInt(normalized.slice(0, 2), 16);
  const green = Number.parseInt(normalized.slice(2, 4), 16);
  const blue = Number.parseInt(normalized.slice(4, 6), 16);
  if (![red, green, blue].every((channel) => Number.isInteger(channel))) {
    throw new Error(`Unsupported hex color: ${hex}`);
  }
  return [red, green, blue];
}

function toHexByte(channel: number): string {
  return channel.toString(16).toUpperCase().padStart(2, "0");
}

export function mixSrgb(top: string, bottom: string, amount: number): HexColor {
  const [red1, green1, blue1] = parseHex(top);
  const [red2, green2, blue2] = parseHex(bottom);
  const red = Math.round(red1 * amount + red2 * (1 - amount));
  const green = Math.round(green1 * amount + green2 * (1 - amount));
  const blue = Math.round(blue1 * amount + blue2 * (1 - amount));
  return `#${toHexByte(red)}${toHexByte(green)}${toHexByte(blue)}`;
}

export const lightTints = {
  confidence: "#E3F4EB",
  attention: "#FBEFD6",
  denial: "#FBE3E0",
  info: "#E5EDFD",
  neutral: LOCKED_LIGHT_COLORS.mutedFill,
} as const;

export interface ColorRoles {
  readonly text: {
    readonly primary: string;
    readonly secondary: string;
    readonly tertiary: string;
    readonly inverse: string;
  };
  readonly surface: {
    readonly page: string;
    readonly canvas: string;
    readonly raised: string;
    readonly muted: string;
    readonly rail: string;
    readonly confidenceTint: string;
    readonly attentionTint: string;
    readonly denialTint: string;
    readonly infoTint: string;
    readonly accentSoft: string;
    readonly neutralTint: string;
    readonly simulation: string;
  };
  readonly status: {
    readonly neutral: string;
    readonly working: string;
    readonly attention: string;
    readonly confidence: string;
    readonly denial: string;
    readonly info: string;
    readonly offline: string;
  };
  readonly border: {
    readonly default: string;
    readonly subtle: string;
    readonly strong: string;
    readonly focus: string;
  };
  readonly action: {
    readonly primary: string;
    readonly pressed: string;
    readonly consent: string;
    readonly destructive: string;
    readonly ghost: string;
  };
  readonly focus: {
    readonly ring: string;
  };
}

export const lightColorRoles: ColorRoles = {
  text: {
    primary: LOCKED_LIGHT_COLORS.ink,
    secondary: LOCKED_LIGHT_COLORS.muted,
    tertiary: LOCKED_LIGHT_COLORS.tertiary,
    inverse: LOCKED_LIGHT_COLORS.surface,
  },
  surface: {
    page: LOCKED_LIGHT_COLORS.desk,
    canvas: LOCKED_LIGHT_COLORS.canvas,
    raised: LOCKED_LIGHT_COLORS.surface,
    muted: LOCKED_LIGHT_COLORS.mutedFill,
    rail: LOCKED_LIGHT_COLORS.rail,
    confidenceTint: lightTints.confidence,
    attentionTint: lightTints.attention,
    denialTint: lightTints.denial,
    infoTint: lightTints.info,
    accentSoft: LOCKED_LIGHT_COLORS.accentSoft,
    neutralTint: lightTints.neutral,
    simulation: LOCKED_LIGHT_COLORS.rail,
  },
  status: {
    neutral: LOCKED_LIGHT_COLORS.ink,
    working: LOCKED_LIGHT_COLORS.info,
    attention: LOCKED_LIGHT_COLORS.attention,
    confidence: LOCKED_LIGHT_COLORS.confidence,
    denial: LOCKED_LIGHT_COLORS.denial,
    info: LOCKED_LIGHT_COLORS.info,
    offline: LOCKED_LIGHT_COLORS.muted,
  },
  border: {
    default: LOCKED_LIGHT_COLORS.rule,
    subtle: LOCKED_LIGHT_COLORS.ruleSubtle,
    strong: LOCKED_LIGHT_COLORS.muted,
    focus: LOCKED_LIGHT_COLORS.ink,
  },
  action: {
    primary: LOCKED_LIGHT_COLORS.accent,
    pressed: LOCKED_LIGHT_COLORS.accentPressed,
    consent: LOCKED_LIGHT_COLORS.confidence,
    destructive: LOCKED_LIGHT_COLORS.denial,
    ghost: "transparent",
  },
  focus: {
    ring: LOCKED_LIGHT_COLORS.ink,
  },
};

export const themeSlots = ["light", "dark"] as const;
export type ThemeSlot = (typeof themeSlots)[number];
export const implementedThemes = ["light"] as const;

export const colorRoles = lightColorRoles;

export const fontFamilies = {
  editorial: '"Schibsted Grotesk", system-ui, -apple-system, sans-serif',
  interface: '"Schibsted Grotesk", system-ui, -apple-system, sans-serif',
  facts: '"JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace',
} as const;

export const typeRoles = {
  display: {
    family: "interface",
    fontSizeRem: 1.5,
    fontWeight: 700,
    lineHeight: 1.2,
  },
  heading: {
    family: "interface",
    fontSizeRem: 1.375,
    fontWeight: 700,
    lineHeight: 1.25,
  },
  body: {
    family: "interface",
    fontSizeRem: 1,
    fontWeight: 400,
    lineHeight: 1.5,
  },
  label: {
    family: "interface",
    fontSizeRem: 1,
    fontWeight: 600,
    lineHeight: 1.3,
  },
  meta: {
    family: "interface",
    fontSizeRem: 0.875,
    fontWeight: 400,
    lineHeight: 1.4,
  },
  fact: {
    family: "facts",
    fontSizeRem: 1,
    fontWeight: 400,
    lineHeight: 1.4,
    fontVariantNumeric: "tabular-nums",
  },
} as const;

export type TypeRole = keyof typeof typeRoles;

export const spacingPx = {
  base: 4,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  "2xl": 32,
  "3xl": 40,
} as const;

export const spacingScalePx = [4, 8, 12, 16, 24, 32, 40] as const;

export const radiusPx = {
  cardMin: 14,
  card: 16,
  cardMax: 20,
  pill: 999,
} as const;

export const touchTargetPx = {
  min: 44,
} as const;

export const motion = {
  durationMs: {
    min: 150,
    standard: 300,
    max: 400,
  },
  easing: {
    standard: "cubic-bezier(0.2, 0.7, 0.3, 1)",
  },
  reducedMotionDurationMs: 0,
} as const;

export const focusTreatment = {
  widthPx: 2,
  offsetPx: 2,
  color: LOCKED_LIGHT_COLORS.ink,
} as const;

export const elevation = {
  none: "none",
  card: "0 1px 3px rgba(40, 30, 15, 0.14)",
  accent: "0 8px 20px -8px rgba(232, 93, 44, 0.5)",
} as const;

export const layoutPx = {
  rail: 236,
  list: 320,
  detailHeader: 60,
  detailMax: 940,
} as const;

export const breakpointsPx = {
  compact: 0,
  wide: 1180,
} as const;

export const layers = {
  base: 0,
  raised: 1,
  banner: 10,
  focus: 20,
} as const;

export const borderWidthPx = {
  thin: 1,
  thick: 2,
} as const;

export const SEMANTIC_TOKEN_NAMES = [
  "text.primary",
  "text.secondary",
  "text.tertiary",
  "text.inverse",
  "surface.page",
  "surface.canvas",
  "surface.raised",
  "surface.muted",
  "surface.rail",
  "surface.confidenceTint",
  "surface.attentionTint",
  "surface.denialTint",
  "surface.infoTint",
  "surface.accentSoft",
  "surface.neutralTint",
  "surface.simulation",
  "status.neutral",
  "status.working",
  "status.attention",
  "status.confidence",
  "status.denial",
  "status.info",
  "status.offline",
  "border.default",
  "border.subtle",
  "border.strong",
  "border.focus",
  "action.primary",
  "action.pressed",
  "action.consent",
  "action.destructive",
  "action.ghost",
  "focus.ring",
] as const;

export type SemanticTokenName = (typeof SEMANTIC_TOKEN_NAMES)[number];

export function semanticToken(name: SemanticTokenName): string {
  const [group, role] = name.split(".") as [keyof ColorRoles, string];
  const groupValue = colorRoles[group] as Record<string, string>;
  const value = groupValue[role];
  if (value === undefined) {
    throw new Error(`Unknown semantic token: ${name}`);
  }
  return value;
}

export const CSS_VAR = {
  textPrimary: "--itaa-color-text-primary",
  textSecondary: "--itaa-color-text-secondary",
  textTertiary: "--itaa-color-text-tertiary",
  textInverse: "--itaa-color-text-inverse",
  surfacePage: "--itaa-color-surface-page",
  surfaceCanvas: "--itaa-color-surface-canvas",
  surfaceRaised: "--itaa-color-surface-raised",
  surfaceMuted: "--itaa-color-surface-muted",
  surfaceRail: "--itaa-color-surface-rail",
  surfaceConfidenceTint: "--itaa-color-surface-confidence-tint",
  surfaceAttentionTint: "--itaa-color-surface-attention-tint",
  surfaceDenialTint: "--itaa-color-surface-denial-tint",
  surfaceInfoTint: "--itaa-color-surface-info-tint",
  surfaceAccentSoft: "--itaa-color-surface-accent-soft",
  surfaceNeutralTint: "--itaa-color-surface-neutral-tint",
  surfaceSimulation: "--itaa-color-surface-simulation",
  statusNeutral: "--itaa-color-status-neutral",
  statusWorking: "--itaa-color-status-working",
  statusAttention: "--itaa-color-status-attention",
  statusConfidence: "--itaa-color-status-confidence",
  statusDenial: "--itaa-color-status-denial",
  statusInfo: "--itaa-color-status-info",
  statusOffline: "--itaa-color-status-offline",
  borderDefault: "--itaa-color-border-default",
  borderSubtle: "--itaa-color-border-subtle",
  borderStrong: "--itaa-color-border-strong",
  borderFocus: "--itaa-color-border-focus",
  actionPrimary: "--itaa-color-action-primary",
  actionPressed: "--itaa-color-action-pressed",
  actionConsent: "--itaa-color-action-consent",
  actionDestructive: "--itaa-color-action-destructive",
  actionGhost: "--itaa-color-action-ghost",
  focusRing: "--itaa-color-focus",
  layoutRail: "--itaa-layout-rail",
  layoutList: "--itaa-layout-list",
  layoutDetailHeader: "--itaa-layout-detail-header",
  layoutDetailMax: "--itaa-layout-detail-max",
  spaceXs: "--itaa-space-xs",
  spaceSm: "--itaa-space-sm",
  spaceMd: "--itaa-space-md",
  spaceLg: "--itaa-space-lg",
  spaceXl: "--itaa-space-xl",
  space2xl: "--itaa-space-2xl",
  space3xl: "--itaa-space-3xl",
  radiusCard: "--itaa-radius-card",
  radiusCardMin: "--itaa-radius-card-min",
  radiusCardMax: "--itaa-radius-card-max",
  radiusPill: "--itaa-radius-pill",
  touchMin: "--itaa-touch-min",
  motionDuration: "--itaa-motion-duration",
  motionEasing: "--itaa-motion-easing",
  focusWidth: "--itaa-focus-width",
  focusOffset: "--itaa-focus-offset",
  fontEditorial: "--itaa-font-editorial",
  fontInterface: "--itaa-font-interface",
  fontFacts: "--itaa-font-facts",
  fontSizeBody: "--itaa-font-size-body",
  elevationCard: "--itaa-elevation-card",
  zBase: "--itaa-z-base",
  zRaised: "--itaa-z-raised",
  zBanner: "--itaa-z-banner",
  zFocus: "--itaa-z-focus",
  breakpointWide: "--itaa-breakpoint-wide",
} as const;
