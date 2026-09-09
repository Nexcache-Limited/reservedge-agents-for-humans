import { attr, escapeHtml } from "../html.js";

export const STATUS_VARIANTS = [
  "neutral",
  "working",
  "attention",
  "confidence",
  "denial",
  "offline",
] as const;
export type StatusVariant = (typeof STATUS_VARIANTS)[number];

export interface StatusIndicatorProps {
  variant: StatusVariant;
  label: string;
}

export function statusIndicatorHtml(props: StatusIndicatorProps): string {
  if (props.label.trim() === "") {
    throw new Error(
      "StatusIndicator requires a visible text label; color must not replace the label",
    );
  }

  return `<span class="itaa-status itaa-status--${props.variant}" role="status"${attr("data-variant", props.variant)}><span class="itaa-status__swatch" aria-hidden="true"></span><span class="itaa-status__label">${escapeHtml(props.label)}</span></span>`;
}
