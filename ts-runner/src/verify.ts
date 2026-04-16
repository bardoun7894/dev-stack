import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

/**
 * Runs the project's test suite and returns a structured pass/fail result.
 * Auto-detects the test runner by looking at the project root — npm test,
 * pytest, phpunit, go test, or flutter test. Returns stdout + parsed counts.
 *
 * This is the TypeScript equivalent of the `verification-before-completion`
 * skill — workers call this instead of interpreting the skill's prose.
 */

export type TestRunner = "npm" | "pytest" | "phpunit" | "go" | "flutter";

export interface VerificationResult {
  runner: TestRunner | null;
  passed: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  summary: string;
}

/**
 * Detect which test runner a project uses by inspecting its root files.
 * Order of precedence: flutter (pubspec.yaml with dependencies), phpunit,
 * pytest, go test, then npm as the fallback because it's the most common.
 */
export function detectRunner(projectRoot: string): TestRunner | null {
  if (existsSync(path.join(projectRoot, "pubspec.yaml"))) return "flutter";
  if (existsSync(path.join(projectRoot, "phpunit.xml"))) return "phpunit";
  if (
    existsSync(path.join(projectRoot, "pytest.ini")) ||
    existsSync(path.join(projectRoot, "pyproject.toml"))
  ) {
    return "pytest";
  }
  if (existsSync(path.join(projectRoot, "go.mod"))) return "go";
  if (existsSync(path.join(projectRoot, "package.json"))) return "npm";
  return null;
}

/**
 * Run the full test suite for a project and return a structured result.
 * Never throws on test failure — the caller inspects `passed` and acts on it.
 * Only throws when the runner itself cannot be invoked (missing binary, etc).
 */
export async function runVerification(
  projectRoot: string = process.cwd(),
): Promise<VerificationResult> {
  const runner = detectRunner(projectRoot);
  if (!runner) {
    return {
      runner: null,
      passed: false,
      exitCode: -1,
      stdout: "",
      stderr: "no supported test runner detected",
      summary: "no runner",
    };
  }

  const command = testCommandFor(runner);
  try {
    const { stdout, stderr } = await execFileAsync(command.bin, command.args, {
      cwd: projectRoot,
      timeout: 10 * 60_000,
      maxBuffer: 50 * 1024 * 1024,
    });
    return {
      runner,
      passed: true,
      exitCode: 0,
      stdout,
      stderr,
      summary: `${runner}: all tests passed`,
    };
  } catch (err) {
    const e = err as NodeJS.ErrnoException & {
      stdout?: string;
      stderr?: string;
      code?: number;
    };
    return {
      runner,
      passed: false,
      exitCode: typeof e.code === "number" ? e.code : 1,
      stdout: e.stdout ?? "",
      stderr: e.stderr ?? e.message ?? "",
      summary: `${runner}: test run failed`,
    };
  }
}

function testCommandFor(runner: TestRunner): { bin: string; args: string[] } {
  switch (runner) {
    case "npm":
      return { bin: "npm", args: ["test", "--silent"] };
    case "pytest":
      return { bin: "pytest", args: ["-q"] };
    case "phpunit":
      return { bin: "./vendor/bin/phpunit", args: [] };
    case "go":
      return { bin: "go", args: ["test", "./..."] };
    case "flutter":
      return { bin: "flutter", args: ["test"] };
  }
}
