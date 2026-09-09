import { attr, escapeHtml } from "../html.js";
import type { TypeRole } from "../tokens/index.js";

export const TEXT_ROLES = ["display", "heading", "body", "label", "meta", "fact"] as const;

export type TextTag = "p" | "span" | "h1" | "h2" | "h3" | "strong";

export interface TextProps {
  role: TypeRole;
  text: string;
  as?: TextTag;
}

const DEFAULT_TAG: Record<TypeRole, TextTag> = {
  display: "h1",
  heading: "h2",
  body: "p",
  label: "span",
  meta: "p",
  fact: "span",
};

export function textHtml(props: TextProps): string {
  const tag = props.as ?? DEFAULT_TAG[props.role];
  return `<${tag} class="itaa-text itaa-text--${props.role}"${attr("data-role", props.role)}>${escapeHtml(props.text)}</${tag}>`;
}
