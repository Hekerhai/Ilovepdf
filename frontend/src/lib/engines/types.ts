import type { ToolResult } from "../types";

export type Options = Record<string, unknown>;

export type Progress = (message: string, fraction?: number) => void;

/**
 * Where a tool runs. The tool page asks each engine in turn; the first that can run the tool with the
 * chosen options wins. New engines (WebAssembly OCR, a desktop bridge...) plug in without touching the UI.
 */
export interface ProcessingEngine {
  readonly where: ToolResult["where"];
  /** null when this engine can run the tool, otherwise a short reason it can't. */
  unsupportedReason(toolId: string, options: Options, files: File[]): string | null;
  run(toolId: string, files: File[], options: Options, progress: Progress, signal?: AbortSignal): Promise<ToolResult>;
}
