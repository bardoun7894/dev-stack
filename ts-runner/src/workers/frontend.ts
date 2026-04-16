import { Packet, WorkerReport } from "../types.js";
import { systemPromptForRole } from "../skill-loader.js";

/**
 * frontend-engineer worker.
 *
 * Loads `../agents/frontend-engineer.md` as the system prompt and calls the
 * Claude Agent SDK to run the packet. Returns a structured WorkerReport.
 *
 * This is the "proof of shape" worker. The remaining 6 workers follow this
 * exact same pattern — only the role name changes — so once this one compiles
 * and runs, the others are template fill-ins.
 */

/**
 * Options passed to every worker. Kept minimal on purpose — the system prompt
 * from the Markdown agent file already carries all the role-specific guidance.
 */
export interface WorkerOptions {
  packet: Packet;
  projectRoot: string;
  /**
   * Optional override for tests. When provided, the worker returns this
   * instead of calling the SDK. Lets the orchestrator's dispatch path be
   * unit-tested without needing a real API key.
   */
  mockRunner?: (opts: {
    systemPrompt: string;
    packet: Packet;
  }) => Promise<WorkerReport>;
}

export async function runFrontendWorker(
  opts: WorkerOptions,
): Promise<WorkerReport> {
  const systemPrompt = await systemPromptForRole("frontend-engineer");

  if (opts.mockRunner) {
    return opts.mockRunner({ systemPrompt, packet: opts.packet });
  }

  // Real SDK call is wired up once the consumer decides how to stream tool use.
  // Kept as a stub so the package typechecks without the SDK installed.
  throw new Error(
    "frontend worker: SDK integration not yet implemented. " +
      "Pass `mockRunner` to test the dispatch path, or wire the Agent SDK here.",
  );
}
