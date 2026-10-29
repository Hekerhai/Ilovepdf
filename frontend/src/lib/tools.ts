import generated from "./tools.generated.json";
import type { Catalog, ToolInfo } from "./types";

/** The catalog snapshot exported from the backend registry (see backend/app/tools/export.py). */
export const catalog = generated as unknown as Catalog;

const byId = new Map(catalog.tools.map((t) => [t.id, t]));

export function getTool(id: string): ToolInfo | undefined {
  return byId.get(id);
}

export function categoryName(id: string): string {
  return catalog.categories.find((c) => c.id === id)?.name ?? id;
}

/** Tools that can take a PDF, i.e. that can follow another tool in a workflow. */
export function acceptsPdf(tool: ToolInfo): boolean {
  return tool.accepts.includes(".pdf");
}
