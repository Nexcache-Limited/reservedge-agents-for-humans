import { FOCUS_RING_CLASS, visuallyHiddenHtml } from "../accessibility/index.js";
import { attr, escapeHtml } from "../html.js";

export const BUTTON_VARIANTS = ["primary", "consent", "ghost", "destructive"] as const;
export type ButtonVariant = (typeof BUTTON_VARIANTS)[number];

export const BUTTON_STATES = [
  "default",
  "hover",
  "focus-visible",
  "pressed",
  "disabled",
  "busy",
] as const;
export type ButtonState = (typeof BUTTON_STATES)[number];

export interface ButtonProps {
  label: string;
  variant?: ButtonVariant;
  disabled?: boolean;
  busy?: boolean;
  disabledReason?: string;
  type?: "button" | "submit";
  id?: string;
}

export function buttonHtml(props: ButtonProps): string {
  if (props.disabledReason !== undefined && props.id === undefined) {
    throw new Error("Button disabledReason requires id for aria-describedby");
  }

  const variant = props.variant ?? "primary";
  const type = props.type ?? "button";
  const busy = props.busy === true;
  const disabled = props.disabled === true || busy;

  if (props.disabledReason !== undefined && !disabled) {
    throw new Error("Button disabledReason may be supplied only when disabled or busy");
  }

  const state: ButtonState = busy ? "busy" : disabled ? "disabled" : "default";
  const reasonId = props.disabledReason !== undefined ? `${props.id}-reason` : undefined;

  const button = `<button${attr("id", props.id)} type="${type}" class="itaa-button itaa-button--${variant} ${FOCUS_RING_CLASS}"${attr("data-variant", variant)}${attr("data-state", state)}${attr("disabled", disabled)}${attr("aria-disabled", disabled ? "true" : undefined)}${attr("aria-busy", busy ? "true" : undefined)}${attr("aria-describedby", reasonId)}><span class="itaa-button__label">${escapeHtml(props.label)}</span>${busy ? visuallyHiddenHtml("Working") : ""}</button>`;

  if (props.disabledReason === undefined || reasonId === undefined) {
    return button;
  }

  return `${button}${visuallyHiddenHtml(props.disabledReason, reasonId)}`;
}
