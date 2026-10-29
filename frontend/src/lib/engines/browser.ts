import { zipSync } from "fflate";

import { stem } from "../format";
import type { ToolResult } from "../types";
import type { Options, ProcessingEngine, Progress } from "./types";

/** Tools with an in-browser implementation in ./browser-handlers. */
const BROWSER_TOOLS = new Set(["merge", "split", "remove_pages", "extract_pages", "rotate", "organize", "images_to_pdf", "pdf_to_images"]);

/** Options the browser implementation can't honour; those runs go to the server instead. */
function browserLimitations(toolId: string, o: Options): string | null {
  if (toolId === "merge" && o.add_bookmarks) return "Adding bookmarks runs on our servers.";
  if (toolId === "split" && (o.mode === "size" || o.mode === "bookmarks")) return "Splitting by size or bookmarks runs on our servers.";
  if (toolId === "images_to_pdf" && typeof createImageBitmap === "undefined") return "Your browser can't convert these images.";
  return null;
}

export class BrowserEngine implements ProcessingEngine {
  readonly where = "browser" as const;

  supports(toolId: string): boolean {
    return BROWSER_TOOLS.has(toolId);
  }

  unsupportedReason(toolId: string, options: Options): string | null {
    if (!this.supports(toolId)) return "This tool runs on our servers.";
    return browserLimitations(toolId, options);
  }

  async run(toolId: string, files: File[], options: Options, progress: Progress): Promise<ToolResult> {
    progress("Processing on your device…", 0.05);
    const { handlers } = await import("./browser-handlers");
    const outputs = await handlers[toolId](files, options, progress);
    progress("Done", 1);
    if (outputs.length === 1) {
      const [o] = outputs;
      return { blob: new Blob([o.bytes as BlobPart], { type: o.type }), name: o.name, where: "browser" };
    }
    const entries: Record<string, Uint8Array> = {};
    for (const o of outputs) {
      let name = o.name;
      for (let n = 1; name in entries; n++) name = `${stem(o.name)}-${n}${o.name.slice(stem(o.name).length)}`;
      entries[name] = o.bytes;
    }
    const zip = zipSync(entries, { level: 0 });
    const base = files[0] ? stem(files[0].name) : toolId;
    return { blob: new Blob([zip as BlobPart], { type: "application/zip" }), name: `${base}-${toolId}.zip`, where: "browser" };
  }
}
