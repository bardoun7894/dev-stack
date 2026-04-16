import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Loads Markdown SKILL.md and agent definition files from the dev-stack tree.
 *
 * Source of truth lives at `../skills/`, `../vendor/kb-skill/skills/`,
 * `../vendor/superpowers/skills/`, `../vendor/local/skills/`, and `../agents/`.
 * Never duplicates content — always reads the current file on disk, so edits
 * to the Markdown propagate automatically to the runner.
 */

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEV_STACK_ROOT = path.resolve(__dirname, "..", "..");

const SKILL_DIRS = [
  path.join(DEV_STACK_ROOT, "skills"),
  path.join(DEV_STACK_ROOT, "vendor", "kb-skill", "skills"),
  path.join(DEV_STACK_ROOT, "vendor", "superpowers", "skills"),
  path.join(DEV_STACK_ROOT, "vendor", "local", "skills"),
] as const;

const AGENTS_DIR = path.join(DEV_STACK_ROOT, "agents");

export interface LoadedSkill {
  name: string;
  absolutePath: string;
  frontmatter: Record<string, string>;
  body: string;
}

/**
 * Find the SKILL.md file for a given skill name across all 4 skill tiers.
 * Throws if the skill doesn't exist.
 */
export function resolveSkillPath(name: string): string {
  for (const dir of SKILL_DIRS) {
    const candidate = path.join(dir, name, "SKILL.md");
    if (existsSync(candidate)) return candidate;
  }
  throw new Error(
    `skill not found: ${name} (looked in ${SKILL_DIRS.join(", ")})`,
  );
}

/**
 * Load a skill by name and return its frontmatter + body separately.
 * Strips the YAML header so the body can be dropped into a system prompt
 * without the frontmatter noise.
 */
export async function loadSkill(name: string): Promise<LoadedSkill> {
  const absolutePath = resolveSkillPath(name);
  const raw = await readFile(absolutePath, "utf8");
  const { frontmatter, body } = splitFrontmatter(raw);
  return { name, absolutePath, frontmatter, body };
}

/**
 * Load an agent definition by name (e.g. "frontend-engineer").
 * Agents live in `../agents/*.md` with the same frontmatter shape.
 */
export async function loadAgent(name: string): Promise<LoadedSkill> {
  const absolutePath = path.join(AGENTS_DIR, `${name}.md`);
  if (!existsSync(absolutePath)) {
    throw new Error(`agent not found: ${name} (${absolutePath})`);
  }
  const raw = await readFile(absolutePath, "utf8");
  const { frontmatter, body } = splitFrontmatter(raw);
  return { name, absolutePath, frontmatter, body };
}

/**
 * Parse a minimal YAML frontmatter block. Handles the shape used by every
 * SKILL.md and agent file: `---\nkey: value\n---\n`. Values are always
 * strings — we don't support nested YAML because the skills don't use it.
 */
export function splitFrontmatter(raw: string): {
  frontmatter: Record<string, string>;
  body: string;
} {
  if (!raw.startsWith("---\n")) {
    return { frontmatter: {}, body: raw };
  }
  const end = raw.indexOf("\n---\n", 4);
  if (end === -1) {
    return { frontmatter: {}, body: raw };
  }
  const fmRaw = raw.slice(4, end);
  const body = raw.slice(end + 5);
  const frontmatter: Record<string, string> = {};
  for (const line of fmRaw.split("\n")) {
    const colon = line.indexOf(":");
    if (colon === -1) continue;
    const key = line.slice(0, colon).trim();
    const value = line.slice(colon + 1).trim();
    if (key) frontmatter[key] = value;
  }
  return { frontmatter, body };
}

/**
 * For a given role, return the agent's body as a system-prompt string that
 * can be dropped directly into an Agent SDK call. This is the only surface
 * a worker module uses — it never parses the Markdown itself.
 */
export async function systemPromptForRole(role: string): Promise<string> {
  const agent = await loadAgent(role);
  return agent.body;
}
