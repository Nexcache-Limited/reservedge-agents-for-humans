import { attr, escapeHtml } from "../html.js";

export const FOCUS_RING_CLASS = "itaa-focus-ring";
export const VISUALLY_HIDDEN_CLASS = "itaa-visually-hidden";
export const LIVE_REGION_CLASS = "itaa-live-region";

export function withFocusRing(className: string): string {
  return `${className} ${FOCUS_RING_CLASS}`;
}

export function visuallyHiddenHtml(text: string, id?: string): string {
  return `<span class="${VISUALLY_HIDDEN_CLASS}"${attr("id", id)}>${escapeHtml(text)}</span>`;
}

export type LivePoliteness = "polite" | "assertive";

export interface LiveRegionProps {
  message: string;
  politeness?: LivePoliteness;
  atomic?: boolean;
  visible?: boolean;
}

export function shouldAnnounce(previous: string, next: string): boolean {
  return next !== "" && next !== previous;
}

export function liveRegionHtml(props: LiveRegionProps): string {
  const politeness = props.politeness ?? "polite";
  const role = politeness === "assertive" ? "alert" : "status";
  const classes = [LIVE_REGION_CLASS];
  if (props.visible !== true) {
    classes.push(VISUALLY_HIDDEN_CLASS);
  }
  return `<div class="${classes.join(" ")}" role="${role}"${attr("aria-live", politeness)}${attr("aria-atomic", props.atomic === true ? "true" : "false")}>${escapeHtml(props.message)}</div>`;
}
