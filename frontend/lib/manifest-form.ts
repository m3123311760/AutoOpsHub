import type { ManifestVariable } from "./api";

export type ManifestValueMap = Record<string, string>;

export function buildInitialManifestValues(manifest: Pick<ManifestVariable, "name" | "default_value">[]): ManifestValueMap {
  return Object.fromEntries(manifest.map((item) => [item.name, item.default_value || ""]));
}

export function collectManifestInputVariables(
  manifest: Pick<ManifestVariable, "name" | "direction">[],
  values: ManifestValueMap
): Record<string, unknown> {
  return Object.fromEntries(
    manifest
      .filter((item) => item.direction === "input")
      .filter((item) => values[item.name] !== undefined && String(values[item.name]).trim() !== "")
      .map((item) => [item.name, values[item.name]])
  );
}

export function parseJsonVariableText(text: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(text || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("变量必须是 JSON 对象");
    }
    return parsed as Record<string, unknown>;
  } catch (error) {
    if (error instanceof SyntaxError) {
      throw new Error("变量必须是有效 JSON");
    }
    throw error;
  }
}
