import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

/**
 * Thin wrapper around the Python KB runtime. Every project with a KB has
 * `<project>/ai-knowledge-base/scripts/query.py` and the same `uv run` command
 * pattern the hooks use. This module shells out to it — no re-implementation
 * of retrieval, no parallel TypeScript KB. Exactly one KB per project.
 */

export interface KbQueryResult {
  answer: string;
  citations: Array<{ wikilink: string; snippet?: string }>;
  raw: string;
}

/**
 * Walk up from `cwd` to find the nearest project with a KB.
 * Returns the KB root (`<project>/ai-knowledge-base/`) or null.
 */
export function findKbRoot(cwd: string = process.cwd()): string | null {
  let dir = path.resolve(cwd);
  while (dir !== path.dirname(dir)) {
    const candidate = path.join(dir, "ai-knowledge-base", "scripts", "query.py");
    if (existsSync(candidate)) {
      return path.join(dir, "ai-knowledge-base");
    }
    dir = path.dirname(dir);
  }
  return null;
}

/**
 * Run a query against the KB. Returns the raw output for the caller to parse,
 * plus an extracted wikilink list if the result looks like the standard
 * cited-answer format.
 */
export async function queryKb(
  question: string,
  cwd: string = process.cwd(),
): Promise<KbQueryResult> {
  const kbRoot = findKbRoot(cwd);
  if (!kbRoot) {
    throw new Error(
      `no ai-knowledge-base found walking up from ${cwd}. run /kb-setup in the project first.`,
    );
  }

  // Match the same `uv run --directory <kb> python <kb>/scripts/query.py ...`
  // invocation the hooks use, so there's exactly one runtime path.
  const { stdout } = await execFileAsync(
    "uv",
    [
      "run",
      "--directory",
      kbRoot,
      "python",
      path.join(kbRoot, "scripts", "query.py"),
      question,
    ],
    { timeout: 60_000 },
  );

  return {
    answer: stdout,
    citations: extractWikilinks(stdout),
    raw: stdout,
  };
}

export function extractWikilinks(
  text: string,
): Array<{ wikilink: string; snippet?: string }> {
  const out: Array<{ wikilink: string; snippet?: string }> = [];
  const re = /\[\[([^\]]+)\]\]/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    out.push({ wikilink: match[1]! });
  }
  return out;
}
