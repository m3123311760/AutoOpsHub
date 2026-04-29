export function workpieceHref(name: string, suffix = "") {
  return `/workpieces/${encodeURIComponent(name)}${suffix}`;
}

export function workpieceRouteParam(value: string) {
  return value;
}

export function recentTasks<T extends { created_at: string }>(tasks: T[], limit = 5) {
  return [...tasks]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, limit);
}
