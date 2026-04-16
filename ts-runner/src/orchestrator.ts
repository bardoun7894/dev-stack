import {
  ModelClass,
  OrchestratorLog,
  Packet,
  Role,
  WorkerReport,
  pickModel,
} from "./types.js";
import { randomUUID } from "node:crypto";

/**
 * Orchestrator — the dispatch engine.
 *
 * Encodes in real code what `../agents/orchestrator.md` describes in prose.
 * The same NIU computation, the same role routing, the same model selection
 * rubric, and the same parallel-spawn semantics.
 *
 * This module does NOT call the Agent SDK directly. It produces a plan
 * (`Packet[]`) and hands it to a worker dispatcher. That keeps the routing
 * logic trivially unit-testable without needing network or API keys.
 */

export interface OrchestratorPlan {
  niu: number;
  packets: Packet[];
  dispatchMode: "solo" | "fanout" | "batched" | "reject";
  reason?: string;
}

export interface RawPacketInput {
  role: Role;
  label: string;
  tasks: string[];
  filesInScope: string[];
  complexity: ModelClass;
  dependencies?: string[];
}

/**
 * Main entry: take a list of raw packets (typically from a planner) and
 * decide how to dispatch them. The rule is "fan-out fires at NIU ≥ 2",
 * exactly as written in the Markdown skills.
 */
export function planDispatch(packets: RawPacketInput[]): OrchestratorPlan {
  const niu = countIndependentUnits(packets);

  if (niu === 0) {
    return {
      niu: 0,
      packets: [],
      dispatchMode: "reject",
      reason: "No packets supplied",
    };
  }

  const materialized = packets.map(toPacket);

  if (niu === 1) {
    return { niu: 1, packets: materialized, dispatchMode: "solo" };
  }

  if (niu <= 4) {
    return { niu, packets: materialized, dispatchMode: "fanout" };
  }

  if (niu <= 8) {
    return {
      niu,
      packets: materialized,
      dispatchMode: "batched",
      reason: `NIU=${niu} exceeds the 4-parallel cap; caller should batch into 4 groups`,
    };
  }

  return {
    niu,
    packets: [],
    dispatchMode: "reject",
    reason: `NIU=${niu} is too large — split the task or narrow scope`,
  };
}

/**
 * Count independent units (NIU): the number of packets whose file-scopes
 * do not overlap and whose dependency graph is empty. This is a deliberately
 * simple definition — packets with overlapping files or declared dependencies
 * collapse to a single unit.
 */
export function countIndependentUnits(packets: RawPacketInput[]): number {
  if (packets.length === 0) return 0;

  // Any packet with declared dependencies joins the dependent's cluster.
  // Any two packets sharing a file collapse into one unit.
  const parent: number[] = packets.map((_, i) => i);
  const find = (i: number): number => {
    let r = i;
    while (parent[r] !== r) r = parent[r]!;
    while (parent[i] !== r) {
      const next = parent[i]!;
      parent[i] = r;
      i = next;
    }
    return r;
  };
  const union = (a: number, b: number) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent[ra] = rb;
  };

  const labelToIdx = new Map<string, number>();
  packets.forEach((p, i) => labelToIdx.set(p.label, i));

  for (let i = 0; i < packets.length; i++) {
    const p = packets[i]!;
    for (const dep of p.dependencies ?? []) {
      const j = labelToIdx.get(dep);
      if (j !== undefined) union(i, j);
    }
    for (let j = i + 1; j < packets.length; j++) {
      const q = packets[j]!;
      if (shareFile(p.filesInScope, q.filesInScope)) {
        union(i, j);
      }
    }
  }

  const roots = new Set<number>();
  for (let i = 0; i < packets.length; i++) roots.add(find(i));
  return roots.size;
}

function shareFile(a: string[], b: string[]): boolean {
  const set = new Set(a);
  return b.some((f) => set.has(f));
}

function toPacket(raw: RawPacketInput): Packet {
  return {
    id: randomUUID(),
    role: raw.role,
    label: raw.label,
    tasks: raw.tasks,
    filesInScope: raw.filesInScope,
    complexity: raw.complexity,
    model: pickModel(raw.complexity),
    dependencies: raw.dependencies ?? [],
    kbContext: [],
  };
}

/**
 * Aggregate multiple worker reports into a single orchestrator log.
 * Called after all workers return.
 */
export function aggregate(
  task: string,
  plan: OrchestratorPlan,
  reports: WorkerReport[],
  startedAt: Date,
  finishedAt: Date,
): OrchestratorLog {
  return OrchestratorLog.parse({
    task,
    niu: plan.niu,
    packets: plan.packets,
    reports,
    startedAt: startedAt.toISOString(),
    finishedAt: finishedAt.toISOString(),
  });
}
