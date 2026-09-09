import { attr } from "../html.js";

export interface SurfaceProps {
  children: string;
  raised?: boolean;
  padding?: "sm" | "md" | "lg" | "xl";
}

export function surfaceHtml(props: SurfaceProps): string {
  const raised = props.raised === true;
  const padding = props.padding ?? "lg";
  const classes = ["itaa-surface", `itaa-surface--pad-${padding}`];
  if (raised) {
    classes.push("itaa-surface--raised");
  }
  return `<section class="${classes.join(" ")}"${attr("data-raised", raised ? "true" : "false")}>${props.children}</section>`;
}
