import { Packet, Role, WorkerReport } from "./types.js";
import { runFrontendWorker } from "./workers/frontend.js";
import { runBackendWorker } from "./workers/backend.js";
import { runQaWorker } from "./workers/qa.js";
import { runDebuggerWorker } from "./workers/debugger.js";
import { runDesignerWorker } from "./workers/designer.js";
import { runReviewerWorker } from "./workers/reviewer.js";
import { runPlannerWorker } from "./workers/planner.js";

/**
 * Role → worker function map. The orchestrator calls `dispatch(packet)`
 * once per packet and awaits all of them in parallel via `Promise.all`.
 *
 * This is the only module that imports the worker set. Add a new role
 * here (and in `../agents/<new-role>.md`) and the orchestrator picks it up.
 */

export interface DispatchOptions {
  projectRoot: string;
  mockRunner?: (opts: {
    systemPrompt: string;
    packet: Packet;
  }) => Promise<WorkerReport>;
}

const WORKERS: Record<
  Role,
  (args: {
    packet: Packet;
    projectRoot: string;
    mockRunner?: DispatchOptions["mockRunner"];
  }) => Promise<WorkerReport>
> = {
  "frontend-engineer": runFrontendWorker,
  "backend-engineer": runBackendWorker,
  "qa-engineer": runQaWorker,
  debugger: runDebuggerWorker,
  designer: runDesignerWorker,
  reviewer: runReviewerWorker,
  planner: runPlannerWorker,
  // The orchestrator never dispatches to itself — if a packet claims role
  // "orchestrator" something upstream is confused. We reject it loudly.
  orchestrator: async () => {
    throw new Error(
      "refusing to dispatch a packet with role=orchestrator; workers never recurse",
    );
  },
};

export async function dispatch(
  packet: Packet,
  opts: DispatchOptions,
): Promise<WorkerReport> {
  const worker = WORKERS[packet.role];
  return worker({
    packet,
    projectRoot: opts.projectRoot,
    mockRunner: opts.mockRunner,
  });
}

/**
 * Dispatch many packets in parallel. Caps concurrency at 4 (matches the
 * orchestrator.md rule — never more than 4 parallel workers without
 * explicit user confirmation). Over 4, the caller must batch.
 */
export async function dispatchAll(
  packets: Packet[],
  opts: DispatchOptions,
): Promise<WorkerReport[]> {
  if (packets.length > 4) {
    throw new Error(
      `dispatchAll: ${packets.length} packets exceeds the 4-parallel cap; batch first`,
    );
  }
  return Promise.all(packets.map((p) => dispatch(p, opts)));
}
