import { Packet, WorkerReport } from "../types.js";
import { systemPromptForRole } from "../skill-loader.js";

export interface WorkerOptions {
  packet: Packet;
  projectRoot: string;
  mockRunner?: (opts: {
    systemPrompt: string;
    packet: Packet;
  }) => Promise<WorkerReport>;
}

export async function runReviewerWorker(
  opts: WorkerOptions,
): Promise<WorkerReport> {
  const systemPrompt = await systemPromptForRole("reviewer");
  if (opts.mockRunner) {
    return opts.mockRunner({ systemPrompt, packet: opts.packet });
  }
  throw new Error(
    "reviewer worker: SDK integration not yet implemented. Pass `mockRunner` or wire the Agent SDK.",
  );
}
