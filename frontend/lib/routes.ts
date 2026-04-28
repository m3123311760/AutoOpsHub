export function workpieceHref(name: string, suffix = "") {
  return `/workpieces/${encodeURIComponent(name)}${suffix}`;
}
