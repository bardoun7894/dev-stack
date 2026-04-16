import { z } from "zod";

/**
 * A role-specialist subagent. Matches the files in `../agents/*.md`.
 */
export const Role = z.enum([
  "orchestrator",
  "planner",
  "frontend-engineer",
  "backend-engineer",
  "qa-engineer",
  "debugger",
  "designer",
  "reviewer",
]);
export type Role = z.infer<typeof Role>;

/**
 * Model complexity class, used to pick the actual Claude model per packet.
 * Matches the rubric in `../agents/orchestrator.md`.
 */
export const ModelClass = z.enum(["trivial", "simple", "medium", "hard"]);
export type ModelClass = z.infer<typeof ModelClass>;

/**
 * The actual Claude model identifier used by the Agent SDK.
 * Trivial packets go to Haiku; hard packets go to Opus; everything else is Sonnet.
 */
export const ClaudeModel = z.enum([
  "claude-haiku-4-5",
  "claude-sonnet-4-6",
  "claude-opus-4-6",
]);
export type ClaudeModel = z.infer<typeof ClaudeModel>;

/**
 * One unit of work dispatched to one worker. Packets with distinct scope
 * run in parallel; packets with overlapping scope must run sequentially.
 */
export const Packet = z.object({
  id: z.string(),
  role: Role,
  label: z.string(),
  tasks: z.array(z.string()).min(1),
  filesInScope: z.array(z.string()),
  complexity: ModelClass,
  model: ClaudeModel,
  dependencies: z.array(z.string()).default([]),
  kbContext: z
    .array(z.object({ wikilink: z.string(), summary: z.string() }))
    .default([]),
});
export type Packet = z.infer<typeof Packet>;

/**
 * A worker's structured return value. All workers must produce this shape.
 * Matches the RETURN block in every `../agents/*.md` prompt template.
 */
export const WorkerReport = z.object({
  role: Role,
  packetId: z.string(),
  tasksCompleted: z.number().int().nonnegative(),
  tasksTotal: z.number().int().positive(),
  filesChanged: z.array(z.string()),
  testsRun: z.number().int().nonnegative().optional(),
  testsPassed: z.number().int().nonnegative().optional(),
  failures: z.array(z.string()).default([]),
  openQuestions: z.array(z.string()).default([]),
  newKbCandidates: z.array(z.string()).default([]),
  summary: z.string(),
});
export type WorkerReport = z.infer<typeof WorkerReport>;

/**
 * The orchestrator's aggregate log across all workers for one task.
 */
export const OrchestratorLog = z.object({
  task: z.string(),
  niu: z.number().int().positive(),
  packets: z.array(Packet),
  reports: z.array(WorkerReport),
  startedAt: z.string().datetime(),
  finishedAt: z.string().datetime(),
});
export type OrchestratorLog = z.infer<typeof OrchestratorLog>;

/**
 * Pure mapping: complexity class → Claude model.
 * Do not inline this elsewhere — keep the rule in one place.
 */
export function pickModel(complexity: ModelClass): ClaudeModel {
  switch (complexity) {
    case "trivial":
      return "claude-haiku-4-5";
    case "simple":
    case "medium":
      return "claude-sonnet-4-6";
    case "hard":
      return "claude-opus-4-6";
  }
}
