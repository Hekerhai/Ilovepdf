import { BrowserEngine } from "./browser";
import { ServerEngine } from "./server";
import type { Options, ProcessingEngine } from "./types";

export const browserEngine = new BrowserEngine();
export const serverEngine = new ServerEngine();

/**
 * Pick where to run a tool. When private mode is on and the browser can do it, files never leave the device;
 * otherwise the server runs it. Returns the engine plus the reason the browser couldn't, for the UI.
 */
export function chooseEngine(
  toolId: string,
  options: Options,
  preferPrivate: boolean,
): { engine: ProcessingEngine; browserBlocker: string | null } {
  const browserBlocker = browserEngine.unsupportedReason(toolId, options);
  if (preferPrivate && browserBlocker === null) return { engine: browserEngine, browserBlocker };
  return { engine: serverEngine, browserBlocker };
}

export type { Options, ProcessingEngine, Progress } from "./types";
