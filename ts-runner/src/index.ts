import { planDispatch, aggregate } from "./orchestrator.js";
import { dispatchAll } from "./dispatcher.js";
import { Packet, WorkerReport } from "./types.js";

/**
 * CLI entry. Usage:
 *
 *   tsx src/index.ts "<free-form task>"
 *
 * MVP behavior: the CLI is a smoke-test harness right now. It does NOT
 * yet auto-decompose a free-form task into packets — that's the planner's
 * job, and the planner worker is wired but the SDK integration is a stub.
 * For now this runs a fixed 2-packet demo so the dispatch path is exercisable.
 */

async function main(): Promise<void> {
  const [, , ...args] = process.argv;
  const task = args.join(" ").trim();
  if (!task) {
    console.error("usage: dev-team \"<task description>\"");
    process.exit(2);
  }

  console.log(`dev-team: ${task}`);
  console.log(
    "note: MVP — full planner auto-decomposition not wired yet. Running a fixed 2-packet demo.",
  );

  const demo = planDispatch([
    {
      role: "frontend-engineer",
      label: "demo-frontend",
      tasks: [task + " (frontend side)"],
      filesInScope: ["src/frontend/placeholder.ts"],
      complexity: "simple",
    },
    {
      role: "backend-engineer",
      label: "demo-backend",
      tasks: [task + " (backend side)"],
      filesInScope: ["src/backend/placeholder.ts"],
      complexity: "simple",
    },
  ]);

  console.log(
    `orchestrator: NIU=${demo.niu}, mode=${demo.dispatchMode}, packets=${demo.packets.length}`,
  );

  // Use a mock runner so the smoke test passes without the Anthropic API.
  const mockRunner = async ({ packet }: { packet: Packet }): Promise<WorkerReport> => ({
    role: packet.role,
    packetId: packet.id,
    tasksCompleted: packet.tasks.length,
    tasksTotal: packet.tasks.length,
    filesChanged: packet.filesInScope,
    failures: [],
    openQuestions: [],
    newKbCandidates: [],
    summary: `[mock] ${packet.role} processed ${packet.tasks.length} task(s)`,
  });

  const startedAt = new Date();
  const reports = await dispatchAll(demo.packets, {
    projectRoot: process.cwd(),
    mockRunner,
  });
  const finishedAt = new Date();

  const log = aggregate(task, demo, reports, startedAt, finishedAt);
  console.log(JSON.stringify(log, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
