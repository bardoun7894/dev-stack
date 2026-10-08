import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, chmodSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const BIN = resolve(dirname(fileURLToPath(import.meta.url)), "..", "bin", "pr-review");
const SHA = "abcdef1234567890";

// Stub runner: PR_REVIEW_RUNNER=<this file> receives argv = [cmd, ...args], logs the call, answers from scenario.json.
const STUB = `#!/usr/bin/env node
import { readFileSync, appendFileSync } from "node:fs";
const dir = process.env.STUB_DIR;
const sc = JSON.parse(readFileSync(dir + "/scenario.json", "utf8"));
const [cmd, ...args] = process.argv.slice(2);
let stdin = ""; try { stdin = readFileSync(0, "utf8"); } catch {}
let bodyFile = null;
const bi = args.indexOf("--body-file");
if (bi >= 0) bodyFile = readFileSync(args[bi + 1], "utf8");
appendFileSync(dir + "/calls.jsonl", JSON.stringify({ cmd, args, stdin, bodyFile }) + "\\n");
const out = (s) => process.stdout.write(s);
if (cmd === "claude") { if (sc.claudeFail) { process.stderr.write("boom"); process.exit(1); } out(sc.claudeOut ?? "No blocking issues"); }
else if (args[0] === "search") out(JSON.stringify(sc.search ?? []));
else if (args[0] === "pr" && args[1] === "view") out(JSON.stringify(args.join(" ").includes("mergeStateStatus") ? (sc.prMerge ?? sc.pr) : sc.pr));
else if (args[0] === "api") {
  const m = args[1].match(/contents\\/\\.github\\/workflows(?:\\/([^?]+))?/);
  if (m && !m[1]) { if (!sc.workflows) { process.stderr.write("gh: Not Found (HTTP 404)"); process.exit(1); } out(JSON.stringify(Object.keys(sc.workflows).map((name) => ({ name })))); }
  else if (m) out(JSON.stringify({ content: Buffer.from(sc.workflows[m[1]]).toString("base64") }));
}
else if (args[0] === "pr" && (args[1] === "merge" || args[1] === "comment")) out("");
else if (args[0] === "pr" && args[1] === "diff") out(sc.diff ?? "diff --git a/x.js b/x.js\\n+1\\n");
else if (args[0] === "pr" && args[1] === "review") out("");
`;

function run(argv, scenario) {
  const dir = mkdtempSync(join(tmpdir(), "pr-review-test-"));
  writeFileSync(join(dir, "stub.mjs"), STUB);
  chmodSync(join(dir, "stub.mjs"), 0o755);
  writeFileSync(join(dir, "scenario.json"), JSON.stringify(scenario));
  const r = spawnSync(BIN, argv, {
    encoding: "utf8",
    env: { ...process.env, PR_REVIEW_RUNNER: join(dir, "stub.mjs"), STUB_DIR: dir },
  });
  const f = join(dir, "calls.jsonl");
  const calls = existsSync(f) ? readFileSync(f, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];
  return { ...r, calls, posts: calls.filter((c) => c.args[0] === "pr" && c.args[1] === "review"), claudes: calls.filter((c) => c.cmd === "claude") };
}

const pr = (over = {}) => ({
  headRefOid: SHA, title: "t", body: "b", isDraft: false, comments: [], reviews: [],
  files: [{ path: "src/a.js" }], ...over,
});

test("marker for current sha -> skipped-seen", () => {
  const r = run(["o/r", "1"], { pr: pr({ comments: [{ body: `x <!-- haiku-review sha=${SHA} -->` }] }) });
  assert.equal(r.status, 0);
  assert.match(r.stdout, /o\/r#1 abcdef1 skipped-seen/);
  assert.equal(r.claudes.length, 0);
  assert.equal(r.posts.length, 0);
});

test("marker inside a review body counts as seen", () => {
  const r = run(["o/r", "1"], { pr: pr({ reviews: [{ body: `<!-- haiku-review sha=${SHA} -->` }] }) });
  assert.match(r.stdout, /skipped-seen/);
});

test("marker for an older sha -> reviewed", () => {
  const r = run(["o/r", "1"], { pr: pr({ comments: [{ body: "<!-- haiku-review sha=0000000 -->" }] }) });
  assert.equal(r.status, 0);
  assert.match(r.stdout, /reviewed/);
  assert.equal(r.posts.length, 1);
});

test("draft -> skipped-draft", () => {
  const r = run(["o/r", "1"], { pr: pr({ isDraft: true }) });
  assert.match(r.stdout, /skipped-draft/);
  assert.equal(r.claudes.length, 0);
});

test("docs-only -> skipped-docs", () => {
  const r = run(["o/r", "1"], { pr: pr({ files: [{ path: "README.md" }, { path: "docs/a.png" }, { path: "n.txt" }] }) });
  assert.match(r.stdout, /skipped-docs/);
  assert.equal(r.claudes.length, 0);
  assert.equal(r.posts.length, 0);
});

test("mixed files -> reviewed", () => {
  const r = run(["o/r", "1"], { pr: pr({ files: [{ path: "README.md" }, { path: "src/a.js" }] }) });
  assert.match(r.stdout, /reviewed/);
  assert.equal(r.posts.length, 1);
});

test("claude failure -> nothing posted, non-zero exit, error logged", () => {
  const r = run(["o/r", "1"], { pr: pr(), claudeFail: true });
  assert.notEqual(r.status, 0);
  assert.match(r.stdout, /error/);
  assert.equal(r.posts.length, 0);
});

test("empty claude output -> error, nothing posted", () => {
  const r = run(["o/r", "1"], { pr: pr(), claudeOut: "   \n" });
  assert.notEqual(r.status, 0);
  assert.equal(r.posts.length, 0);
});

test("posted body carries header and marker with head sha; diff goes to claude on stdin", () => {
  const r = run(["o/r", "1"], { pr: pr(), claudeOut: "P1 src/a.js:3 fix it" });
  const body = r.posts[0].bodyFile;
  assert.ok(body.startsWith("**Haiku 5.5 review**\n\n"));
  assert.ok(body.includes("P1 src/a.js:3 fix it"));
  assert.ok(body.endsWith(`\n\n<!-- haiku-review sha=${SHA} -->`));
  assert.ok(r.claudes[0].stdin.includes("diff --git"));
  assert.ok(r.claudes[0].args.includes("claude-haiku-5-5"));
});

test("--dry-run prints and does not post", () => {
  const r = run(["o/r", "1", "--dry-run"], { pr: pr(), claudeOut: "No blocking issues" });
  assert.equal(r.posts.length, 0);
  assert.match(r.stdout, /No blocking issues/);
  assert.match(r.stdout, /reviewed/);
});

test("oversize diff is truncated to 120000 chars and the comment says so", () => {
  const r = run(["o/r", "1"], { pr: pr(), diff: "x".repeat(130000) });
  assert.match(r.posts[0].bodyFile, /truncated/i);
  assert.ok(r.claudes[0].stdin.length < 125000);
});

test("sweep respects --max, newest first", () => {
  const search = [1, 2, 3, 4, 5].map((n) => ({ repository: { nameWithOwner: "bardoun7894/r" }, number: n, updatedAt: `2026-10-0${n}T00:00:00Z` }));
  const r = run(["--sweep", "--max", "2"], { search, pr: pr() });
  assert.equal(r.status, 0);
  assert.equal(r.posts.length, 2);
  assert.deepEqual(r.posts.map((p) => p.args[2]), ["5", "4"]);
});

test("sweep continues past a failing PR", () => {
  const search = [1, 2].map((n) => ({ repository: { nameWithOwner: "bardoun7894/r" }, number: n, updatedAt: `2026-10-0${n}T00:00:00Z` }));
  const r = run(["--sweep"], { search, pr: pr(), claudeFail: true });
  assert.equal(r.claudes.length, 2);
  assert.equal(r.posts.length, 0);
});

// ---- auto-merge on VERDICT: PASS ----
const PASS = "No blocking issues\nVERDICT: PASS";
const green = (over = {}) => ({
  isDraft: false, mergeable: "MERGEABLE", mergeStateStatus: "CLEAN", labels: [], baseRefName: "main",
  statusCheckRollup: [{ __typename: "CheckRun", status: "COMPLETED", conclusion: "SUCCESS" }, { __typename: "StatusContext", state: "SUCCESS" }],
  headRefOid: SHA, comments: [], ...over,
});
const merges = (r) => r.calls.filter((c) => c.args[0] === "pr" && c.args[1] === "merge");
const skipComments = (r) => r.calls.filter((c) => c.args[0] === "pr" && c.args[1] === "comment");
const go = (sc, extra = []) => run(["o/r", "1", ...extra], { pr: pr(), prMerge: green(), claudeOut: PASS, ...sc });

test("PASS + all green -> merge with --match-head-commit", () => {
  const r = go({});
  assert.equal(r.status, 0);
  assert.equal(merges(r).length, 1);
  assert.deepEqual(merges(r)[0].args, ["pr", "merge", "1", "-R", "o/r", "--merge", "--match-head-commit", SHA]);
  assert.match(r.stdout, /merged/);
  assert.ok(r.posts[0].bodyFile.includes("VERDICT: PASS"));
});

test("BLOCK -> no merge", () => {
  const r = go({ claudeOut: "P1 a.js:1 bad\nVERDICT: BLOCK" });
  assert.equal(merges(r).length, 0);
  assert.equal(r.posts.length, 1);
});

test("missing or garbled verdict -> no merge", () => {
  for (const claudeOut of ["No blocking issues", "VERDICT: PASS\nthanks", "verdict: pass maybe"]) {
    assert.equal(merges(go({ claudeOut })).length, 0, claudeOut);
  }
});

test("pending check -> no merge", () => {
  const r = go({ prMerge: green({ statusCheckRollup: [{ __typename: "CheckRun", status: "IN_PROGRESS", conclusion: "" }] }) });
  assert.equal(merges(r).length, 0);
  const r2 = go({ prMerge: green({ statusCheckRollup: [{ __typename: "StatusContext", state: "PENDING" }] }) });
  assert.equal(merges(r2).length, 0);
});

test("failed check -> no merge", () => {
  const r = go({ prMerge: green({ statusCheckRollup: [{ __typename: "CheckRun", status: "COMPLETED", conclusion: "FAILURE" }] }) });
  assert.equal(merges(r).length, 0);
});

test("label no-automerge -> no merge", () => {
  assert.equal(merges(go({ prMerge: green({ labels: [{ name: "no-automerge" }] }) })).length, 0);
});

test("draft, conflicting, UNSTABLE -> no merge", () => {
  assert.equal(merges(go({ prMerge: green({ isDraft: true }) })).length, 0);
  assert.equal(merges(go({ prMerge: green({ mergeable: "CONFLICTING" }) })).length, 0);
  assert.equal(merges(go({ prMerge: green({ mergeStateStatus: "UNSTABLE" }) })).length, 0);
  assert.equal(merges(go({ prMerge: green({ mergeStateStatus: "HAS_HOOKS" }) })).length, 1);
});

test("new head sha since review -> no merge", () => {
  assert.equal(merges(go({ prMerge: green({ headRefOid: "ffffffffff" }) })).length, 0);
});

test("deploy workflow on push -> no merge, skip comment posted once", () => {
  const workflows = { "ci.yml": "name: CI\non: [pull_request]\n", "deploy.yml": "name: Deploy\non:\n  push:\n    branches: [main]\n" };
  const r = go({ workflows });
  assert.equal(merges(r).length, 0);
  assert.equal(skipComments(r).length, 1);
  assert.match(skipComments(r)[0].bodyFile, /not merged automatically: merging into main runs a deploy workflow \(deploy\.yml\)/);
  assert.ok(skipComments(r)[0].bodyFile.includes(`<!-- haiku-merge-skip sha=${SHA} -->`));
  const r2 = go({ workflows, prMerge: green({ comments: [{ body: `x <!-- haiku-merge-skip sha=${SHA} -->` }] }) });
  assert.equal(skipComments(r2).length, 0);
  assert.equal(merges(r2).length, 0);
});

test("workflow without deploy -> merge", () => {
  const r = go({ workflows: { "ci.yml": "name: CI\non:\n  push:\n  pull_request:\njobs: {}\n" } });
  assert.equal(merges(r).length, 1);
});

test("already-reviewed PASS unmerged -> merge re-check, no new review", () => {
  const body = `**Haiku 5.5 review**\n\nok\nVERDICT: PASS\n\n<!-- haiku-review sha=${SHA} -->`;
  const r = run(["--sweep"], {
    search: [{ repository: { nameWithOwner: "bardoun7894/r" }, number: 3, updatedAt: "2026-10-01T00:00:00Z" }],
    pr: pr({ comments: [{ body }] }), prMerge: green(),
  });
  assert.equal(r.claudes.length, 0);
  assert.equal(r.posts.length, 0);
  assert.equal(merges(r).length, 1);
});

test("--dry-run and --no-merge -> no merge", () => {
  const d = go({}, ["--dry-run"]);
  assert.equal(merges(d).length, 0);
  assert.match(d.stdout, /would-merge/);
  const n = go({}, ["--no-merge"]);
  assert.equal(merges(n).length, 0);
  assert.equal(n.posts.length, 1);
});
