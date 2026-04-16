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

export async function runQaWorker(opts: WorkerOptions): Promise<WorkerReport> {
  const systemPrompt = await systemPromptForRole("qa-engineer");
  if (opts.mockRunner) {
    return opts.mockRunner({ systemPrompt, packet: opts.packet });
  }
  throw new Error(
    "qa worker: SDK integration not yet implemented. Pass `mockRunner` or wire the Agent SDK.",
  );
}
