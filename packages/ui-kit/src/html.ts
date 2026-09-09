export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function attr(name: string, value: string | boolean | undefined): string {
  if (value === undefined || value === false) {
    return "";
  }
  if (value === true) {
    return ` ${name}`;
  }
  return ` ${name}="${escapeHtml(value)}"`;
}
