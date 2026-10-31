import { api, waitForJob } from "../api";
import type { Step, ToolResult } from "../types";
import type { Options, ProcessingEngine, Progress } from "./types";

/** Runs any tool (or workflow) on the API's worker queue. */
export class ServerEngine implements ProcessingEngine {
  readonly where = "server" as const;

  unsupportedReason(): string | null {
    return null;
  }

  run(toolId: string, files: File[], options: Options, progress: Progress, signal?: AbortSignal) {
    // Keys starting with "_" are UI-only state (e.g. a picked file's name) and never reach the API.
    const sent = Object.fromEntries(Object.entries(options).filter(([k]) => !k.startsWith("_")));
    return this.runSteps([{ tool: toolId, options: sent }], files, progress, signal);
  }

  async runSteps(steps: Step[], files: File[], progress: Progress, signal?: AbortSignal): Promise<ToolResult> {
    progress("Uploading securely…", 0.1);
    const created = await api.createJob(files, steps);
    progress("Processing…", 0.4);
    const job = await waitForJob(
      created.id,
      (j) => progress(j.status === "running" ? "Processing…" : "Waiting in queue…", j.status === "running" ? 0.6 : 0.45),
      signal,
    );
    if (job.status === "failed") throw new Error(job.error ?? "Processing failed.");
    progress("Downloading result…", 0.9);
    const blob = await api.download(job);
    return { blob, name: job.output_name!, where: "server", job };
  }
}
