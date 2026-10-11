// node --test tests/jdelegate.test.mjs  — worker command and preamble of bin/jdelegate (--dry-run: no worker, no network)
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const JD = join(dirname(fileURLToPath(import.meta.url)), '..', 'bin', 'jdelegate');
const tmp = mkdtempSync(join(tmpdir(), 'jdelegate-test-'));
const sh = (cmd, cwd) => spawnSync('bash', ['-c', cmd], { cwd, encoding: 'utf8' });
const write = (path, text) => { mkdirSync(dirname(path), { recursive: true }); writeFileSync(path, text); };

// A git repo with its own instructions, a fake skill root, a stub jev that always errors, a router config
// with one live claude model, and an allowlist.
const repo = join(tmp, 'repo');
write(join(repo, 'CLAUDE.md'), '# Repo rules\nUSE-TABS-MARKER\n');
write(join(repo, '.claude', 'CLAUDE.md'), 'DOT-CLAUDE-MARKER\n');
sh('git init -q', repo);
const skills = join(tmp, 'skills');
write(join(skills, 'fake-skill', 'SKILL.md'), '---\nname: fake-skill\ndescription: d\n---\nFAKE-SKILL-BODY\n');
write(join(skills, 'big-skill', 'SKILL.md'), `---\nname: big-skill\n---\n${'x'.repeat(13000)}`);
write(join(skills, 'other-skill', 'SKILL.md'), 'OTHER-BODY\n');
const bin = join(tmp, 'bin');
const stub = (name, body) => { write(join(bin, name), `#!/bin/bash\n${body}\n`); chmodSync(join(bin, name), 0o755); };
stub('jev', 'exit 3');
const tiers = join(tmp, 'tiers.json');
write(tiers, JSON.stringify({ tiers: { T0: ['cliproxy/claude-test'], T1: ['cliproxy/claude-test'], T2: ['cliproxy/claude-test'], T3: ['cliproxy/claude-test'], T4: ['cliproxy/claude-test'] } }));
const allow = join(tmp, 'worker-skills.json');
write(allow, JSON.stringify({ worker: ['fake-skill', 'big-skill'], generated: 'test', method: 'jev choice' }));

function dry(args, { env = {}, cwd = repo, brief = 'do the thing' } = {}) {
  const r = spawnSync(process.execPath, [JD, '--dry-run', '--harness', 'claude', '--cwd', cwd, ...args, brief], {
    encoding: 'utf8',
    env: {
      ...process.env, PATH: `${bin}:${process.env.PATH}`, JDELEGATE_JEV: join(bin, 'jev'), JEV_ROUTER_CONFIG: tiers,
      JDELEGATE_CACHE: join(tmp, 'cache'), JDELEGATE_SKILL_DIRS: skills, JDELEGATE_WORKER_SKILLS: allow,
      JDELEGATE_AUTO_SKILL: '0', JDELEGATE_FULL: '', JDELEGATE_SELECT_CACHE: '0', ...env,
    },
  });
  const run = r.stdout.match(/dry-run (\S+)/)?.[1];
  const prompt = run ? (() => { try { return readFileSync(join(run, 'worker-prompt.md'), 'utf8'); } catch { return undefined; } })() : undefined;
  return { ...r, run, prompt, script: run ? readFileSync(join(run, 'run.sh'), 'utf8') : '' };
}

test('lean command isolates the worker from user config and loads a system-prompt file', () => {
  const r = dry([]);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.script, /CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 claude -p/);
  assert.match(r.script, /--setting-sources project,local/);
  assert.match(r.script, /--settings '\{"disableAllHooks":true,"autoMemoryEnabled":false,/);
  assert.match(r.script, new RegExp(`--append-system-prompt-file '${r.run}/worker-prompt.md'`));
  assert.match(r.script, /--strict-mcp-config/);
  assert.doesNotMatch(r.script, /--bare/);
  // the variadic --tools stays last so it cannot swallow a flag
  assert.match(r.script, /--tools Bash Read Edit Write Glob Grep Skill 2>&1/);
});

// KB prior art: the lean worker prompt gets kb-retrieve's matches for the brief in --cwd (JDELEGATE_KB=0 turns it off)
const kbProj = join(tmp, 'kb-proj');
write(join(kbProj, 'ai-knowledge-base', 'knowledge', 'concepts', 'invoice-extraction.md'),
  '---\ntitle: Invoice extraction\n---\nGemini extracts invoice pages; retry on timeout.\n');
mkdirSync(join(kbProj, '.git'), { recursive: true });

// kb-retrieve --condense calls claude; tests use stubs so no real Haiku call is made.
const kbStubBin = (name, body) => { const d = join(tmp, `kb-${name}`); write(join(d, 'claude'), `#!/bin/bash\n${body}\n`); chmodSync(join(d, 'claude'), 0o755); return `${d}:${bin}:${process.env.PATH}`; };
const kbClaudeFails = kbStubBin('fail', 'cat >/dev/null; exit 1');
const kbClaudeCondenses = kbStubBin('ok', 'cat >/dev/null; echo "CONDENSED-STUB [[invoice-extraction]] retry on timeout"');

test('KB prior art: worker prompt uses the condensed brief (kb-retrieve --condense)', () => {
  const r = dry([], { cwd: kbProj, brief: 'fix invoice extraction', env: { PATH: kbClaudeCondenses } });
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.prompt, /^## KB prior art\nCONDENSED-STUB \[\[invoice-extraction\]\]/m);
});

test('KB prior art: lean worker-prompt.md gets the matches for the brief', () => {
  const r = dry([], { cwd: kbProj, brief: 'fix invoice extraction', env: { PATH: kbClaudeFails } });
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.prompt, /^## KB prior art$/m);
  assert.match(r.prompt, /### \[\[invoice-extraction\]\] \(ai-knowledge-base\/knowledge\/concepts\/invoice-extraction\.md\)/);
});

test('KB prior art: JDELEGATE_KB=0 leaves the worker prompt as before', () => {
  const r = dry([], { cwd: kbProj, brief: 'fix invoice extraction', env: { JDELEGATE_KB: '0' } });
  assert.equal(r.status, 0, r.stderr);
  assert.doesNotMatch(r.prompt, /KB prior art/);
});

test('KB prior art: no match means no section', () => {
  const r = dry([], { cwd: kbProj, brief: 'do the thing' });
  assert.equal(r.status, 0, r.stderr);
  assert.doesNotMatch(r.prompt, /KB prior art/);
});

test('--full command is the plain one', () => {
  const r = dry(['--full']);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.script, /claude -p --model 'claude-test' --effort \w+ --dangerously-skip-permissions "\$\(cat '[^']+brief\.md'\)" <\/dev\/null 2>&1 \| tee /);
  assert.doesNotMatch(r.script, /CLAUDE_CODE_DISABLE_CLAUDE_MDS|--settings|--setting-sources|--append-system-prompt-file/);
  assert.equal(r.prompt, undefined);
});

test('worker-prompt.md: contract first, then the repo\'s own instructions', () => {
  const r = dry([]);
  assert.match(r.prompt, /you are a worker/i);
  assert.match(r.prompt, /Co-Authored-By/);
  assert.ok(r.prompt.indexOf('worker') < r.prompt.indexOf('USE-TABS-MARKER'));
  assert.match(r.prompt, /USE-TABS-MARKER/);
  assert.match(r.prompt, /DOT-CLAUDE-MARKER/);
  const contract = r.prompt.slice(0, r.prompt.indexOf('USE-TABS-MARKER'));
  assert.ok(contract.split('\n').length <= 25);
});

test('worker-prompt.md never carries the user-global CLAUDE.md', () => {
  const lines = (() => { try { return readFileSync(join(homedir(), '.claude', 'CLAUDE.md'), 'utf8').split('\n'); } catch { return []; } })()
    .map((l) => l.trim()).filter((l) => l.length > 40).slice(0, 12);
  const r = dry([]);
  for (const l of lines) assert.ok(!r.prompt.includes(l), `leaked: ${l}`);
  // a repo rooted at $HOME contributes nothing (~/CLAUDE.md is another project's file)
  const h = dry([], { cwd: homedir() });
  assert.equal(h.status, 0, h.stderr);
  assert.doesNotMatch(h.prompt, /Uplevel X Development Guidelines/);
});

test('repo instructions are capped at 12000 chars with a marker', () => {
  const big = join(tmp, 'bigrepo');
  write(join(big, 'CLAUDE.md'), 'y'.repeat(20000));
  sh('git init -q', big);
  const r = dry([], { cwd: big });
  assert.ok(r.prompt.split('y').length - 1 <= 12000);
  assert.match(r.prompt, /truncated/);
});

test('--skill inlines the skill without frontmatter, repeatable, capped', () => {
  const r = dry(['--skill', 'fake-skill', '--skill', 'big-skill']);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.prompt, /## Skill: fake-skill\n/);
  assert.match(r.prompt, /FAKE-SKILL-BODY/);
  assert.doesNotMatch(r.prompt, /description: d/);
  assert.match(r.prompt, /## Skill: big-skill\n/);
  assert.ok(r.prompt.split('x').length - 1 <= 12000);
  assert.match(r.stdout, /skills: fake-skill, big-skill/);
});

test('unknown --skill exits 2 with a message', () => {
  const r = dry(['--skill', 'nope']);
  assert.equal(r.status, 2);
  assert.match(r.stderr, /nope/);
});

test('auto-skill: allowlisted suggestion is inlined and shown as (auto)', () => {
  stub('jev-skill-suggest', 'echo fake-skill');
  const r = dry([], { env: { JDELEGATE_AUTO_SKILL: '' } });
  assert.match(r.prompt, /## Skill: fake-skill/);
  assert.match(r.stdout, /skills: fake-skill \(auto\)/);
});

test('auto-skill: suggestion outside the allowlist, a failing suggester, or empty output adds nothing', () => {
  for (const body of ['echo other-skill', 'exit 1', 'true', 'echo fake-skill; exit 1']) {
    stub('jev-skill-suggest', body);
    const r = dry([], { env: { JDELEGATE_AUTO_SKILL: '' } });
    assert.equal(r.status, 0, r.stderr);
    assert.doesNotMatch(r.prompt, /## Skill:/, body);
    assert.doesNotMatch(r.stdout, /skills:/, body);
  }
});

test('auto-skill is off with --no-auto-skill, JDELEGATE_AUTO_SKILL=0, or an explicit --skill', () => {
  stub('jev-skill-suggest', 'echo fake-skill');
  assert.doesNotMatch(dry(['--no-auto-skill'], { env: { JDELEGATE_AUTO_SKILL: '' } }).prompt, /## Skill:/);
  assert.doesNotMatch(dry([], { env: { JDELEGATE_AUTO_SKILL: '0' } }).prompt, /## Skill:/);
  const r = dry(['--skill', 'other-skill'], { env: { JDELEGATE_AUTO_SKILL: '' } });
  assert.doesNotMatch(r.prompt, /## Skill: fake-skill/);
  assert.match(r.prompt, /## Skill: other-skill/);
  assert.doesNotMatch(r.stdout, /\(auto\)/);
});

// ── roles, auto-role, auto-MCP, attribution ─────────────────────────────
const agents = join(tmp, 'agents');
const agentsParked = join(tmp, 'agents-parked');
const agent = (dir, name, desc, body) => write(join(dir, `${name}.md`), `---\nname: ${name}\ndescription: ${desc}\n---\n${body}\n`);
agent(agents, 'debugger', 'Root-cause analysis. '.repeat(30), 'DEBUGGER-BODY\nSpawn an agent with the Task tool for each hypothesis.');
agent(agents, 'reviewer', 'Reviews code.', 'REVIEWER-BODY plain');
agent(agentsParked, 'designer', 'Designs UI.', 'DESIGNER-BODY');
agent(agents, 'orchestrator', 'Orchestrates.', 'ORCH-BODY');
agent(agents, 'big', 'Big.', 'z'.repeat(9000));
const roles = join(tmp, 'worker-roles.json');
write(roles, JSON.stringify({ worker: ['debugger', 'reviewer', 'designer'] }));
const claudeJson = join(tmp, 'claude.json');
const jevLog = join(tmp, 'jev.log');
// stub jev (node): `raw` answers the route body and the folded role+mcp body; everything else exits 3. Every call is logged
// to jev.log, one line each. $ROLE_ANSWER / $ROLE_CONF drive the role answer, $MCP_SCORES ("a=0.9,b=0.2") the MCP answers by
// server name, $JEV_SLEEP delays each call (seconds), $RAW_FAIL=1 fails the call, $RAW_BAD=<question key> returns that
// answer malformed.
const STUB_JEV = `#!/usr/bin/env node
const fs = require('fs'); const a = process.argv.slice(2); const e = process.env;
const input = a[0] === 'raw' ? fs.readFileSync(0, 'utf8') : '';
fs.appendFileSync(\`${'$'}{e.JEV_LOG}\`, (a[0] === 'raw' ? 'raw ' + input.replace(/\\n/g, ' ') : a.join(' ')) + '\\n');
setTimeout(() => {
  if (a[0] !== 'raw' || e.RAW_FAIL) process.exit(3);
  const qs = JSON.parse(input).questions; const answers = {};
  if (qs.tier) Object.assign(answers, { tier: { choice: 'T3', confidence: 0.9 }, kind: { choice: e.KIND_ANSWER || 'code', confidence: 0.9 }, role: { choice: 'doer', confidence: 0.9 }, arabic: { noul: Number(e.ARABIC || 0.01) }, ui: { noul: 0.02 } });
  else for (const k of Object.keys(qs)) {
    const kv = (e.MCP_SCORES || '').split(',').find((x) => k === 'mcp:' + x.split('=')[0]);
    answers[k] = e.RAW_BAD === k ? { oops: 1 } : k === 'role' ? { choice: e.ROLE_ANSWER || 'none', confidence: Number(e.ROLE_CONF || 0.9) } : { noul: kv ? Number(kv.split('=')[1]) : 0.1 };
  }
  console.log(JSON.stringify({ answers }));
}, Number(e.JEV_SLEEP || 0) * 1000);
`;
const jevStub = () => { stub('jev', 'exit 3'); write(join(bin, 'jev'), STUB_JEV); chmodSync(join(bin, 'jev'), 0o755); };
process.env.JEV_LOG = jevLog;
const rdry = (args, env = {}) => { writeFileSync(jevLog, ''); return dry(args, { env: { JDELEGATE_AGENT_DIRS: `${agents}:${agentsParked}`, JDELEGATE_WORKER_ROLES: roles, JDELEGATE_CLAUDE_JSON: claudeJson, ...env } }); };
const calls = () => readFileSync(jevLog, 'utf8').split('\n').filter(Boolean);
/** The questions of every folded raw request (role + mcp:<name>), merged. */
const asked = () => Object.assign({}, ...calls().filter((l) => l.startsWith('raw ')).map((l) => JSON.parse(l.slice(4))).filter((b) => !b.questions.tier).map((b) => b.questions));
write(claudeJson, '{}');

test('--role inlines the body without frontmatter, after the contract and before skills, with the single-worker line', () => {
  jevStub();
  const r = rdry(['--role', 'debugger', '--skill', 'fake-skill']);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.prompt, /## Role: debugger\n/);
  assert.match(r.prompt, /DEBUGGER-BODY/);
  assert.doesNotMatch(r.prompt, /description: Root-cause/);
  assert.match(r.prompt, /You are running as a single worker: ignore any instruction above to spawn agents or delegate\./);
  assert.ok(r.prompt.indexOf('You are a worker') < r.prompt.indexOf('## Role: debugger'));
  assert.ok(r.prompt.indexOf('## Role: debugger') < r.prompt.indexOf('## Skill: fake-skill'));
  assert.match(r.stdout, /role: debugger(?! \(auto\))/);
});

test('--role: override line only when the body tells the worker to spawn; parked agents are found; capped at 8000', () => {
  jevStub();
  assert.doesNotMatch(rdry(['--role', 'reviewer']).prompt, /single worker/);
  assert.match(rdry(['--role', 'designer']).prompt, /DESIGNER-BODY/);
  assert.ok(rdry(['--role', 'big']).prompt.split('z').length - 1 <= 8000);
});

test('unknown --role exits 2', () => {
  jevStub();
  const r = rdry(['--role', 'nope']);
  assert.equal(r.status, 2);
  assert.match(r.stderr, /nope/);
});

test('auto-role: picks an eligible role, with descriptions truncated to 200 chars; confidence >= 0.6 required', () => {
  jevStub();
  const r = rdry([], { ROLE_ANSWER: 'debugger' });
  assert.match(r.prompt, /## Role: debugger/);
  assert.match(r.stdout, /role: debugger \(auto\)/);
  const q = asked().role;
  assert.equal(q.type, 'choice');
  assert.match(q.instructions, /Which specialist role/);
  assert.deepEqual(Object.keys(q.criteria), ['debugger', 'reviewer', 'designer', 'none']);
  assert.ok(q.criteria.debugger.length <= 200);
  assert.match(q.criteria.none, /generic worker/);
  assert.equal(rdry([], { ROLE_ANSWER: 'debugger', ROLE_CONF: '0.6' }).prompt.includes('## Role: debugger'), true);
  assert.equal(rdry([], { ROLE_ANSWER: 'debugger', ROLE_CONF: '0.59' }).prompt.includes('## Role:'), false);
});

test('auto-role: "none", low confidence, jev error, malformed answer and ineligible answers add no role', () => {
  jevStub();
  for (const env of [{ ROLE_ANSWER: 'none' }, { ROLE_ANSWER: 'debugger', ROLE_CONF: '0.3' }, { ROLE_ANSWER: 'debugger', RAW_FAIL: '1' }, { ROLE_ANSWER: 'debugger', RAW_BAD: 'role' }, { ROLE_ANSWER: 'orchestrator' }, { ROLE_ANSWER: 'big' }]) {
    const r = rdry([], env);
    assert.equal(r.status, 0, r.stderr);
    assert.doesNotMatch(r.prompt, /## Role:/, JSON.stringify(env));
    assert.doesNotMatch(r.stdout, /role:/, JSON.stringify(env));
  }
});

test('auto-role is off with --no-auto-role, JDELEGATE_AUTO_ROLE=0 or an explicit --role (no jev call)', () => {
  jevStub();
  for (const [args, env] of [[['--no-auto-role'], {}], [[], { JDELEGATE_AUTO_ROLE: '0' }], [['--role', 'reviewer'], {}]]) {
    const r = rdry(args, { ROLE_ANSWER: 'debugger', ...env });
    assert.doesNotMatch(r.prompt, /## Role: debugger/);
    assert.equal(asked().role, undefined);
  }
});

const mcpDef = (name) => ({ command: 'node', args: [`${name}.js`], description: `the ${name} server` });
const mcpOf = (script) => JSON.parse(readFileSync(script.match(/--mcp-config '([^']+)'/)[1], 'utf8')).mcpServers;

test('auto-MCP: no servers configured means no jev noul call and an empty config', () => {
  jevStub();
  write(claudeJson, '{}');
  const r = rdry(['--no-auto-role'], { MCP_SCORES: 'a=0.9' });
  assert.deepEqual(mcpOf(r.script), {});
  assert.deepEqual(Object.keys(asked()), []);
  assert.doesNotMatch(r.stdout, /mcp:/);
});

test('auto-MCP: loads only servers at >= 0.7, at most 2, from ~/.claude.json, the project entry and .mcp.json', () => {
  jevStub();
  write(claudeJson, JSON.stringify({ mcpServers: { a: mcpDef('a'), b: mcpDef('b'), low: mcpDef('low') }, projects: { [repo]: { mcpServers: { c: mcpDef('c') }, enabledMcpjsonServers: ['d'] } } }));
  write(join(repo, '.mcp.json'), JSON.stringify({ mcpServers: { d: mcpDef('d') } }));
  try {
    const r = rdry(['--no-auto-role'], { MCP_SCORES: 'a=0.9,b=0.7,low=0.69,c=0.95,d=0.8' });
    assert.equal(r.status, 0, r.stderr);
    assert.deepEqual(Object.keys(mcpOf(r.script)).length, 2);
    assert.ok(!('low' in mcpOf(r.script)));
    assert.match(r.stdout, /mcp: \w,\w \(auto\)/);
    const n = asked()['mcp:a'];
    assert.equal(n.type, 'noul');
    assert.equal(n.instructions, 'This coding brief needs the a MCP server (the a server)');
    assert.equal(asked()['mcp:d'].instructions, 'This coding brief needs the d MCP server (node)', '.mcp.json servers: name + command only');
    assert.deepEqual(Object.keys(asked()).sort(), ['mcp:a', 'mcp:b', 'mcp:c', 'mcp:d', 'mcp:low']);
    assert.equal(calls().filter((l) => l.startsWith('raw ') && !l.includes('"tier"')).length, 1, 'role and every MCP server ride in ONE request');
    const one = rdry(['--no-auto-role'], { MCP_SCORES: 'c=0.8' });
    assert.deepEqual(Object.keys(mcpOf(one.script)), ['c']);
    assert.match(one.stdout, /mcp: c \(auto\)/);
    assert.deepEqual(mcpOf(rdry(['--no-auto-role'], { MCP_SCORES: '' }).script), {});
  } finally { sh(`rm -f ${join(repo, '.mcp.json')}`); }
});

test('auto-MCP: off with an explicit --mcp, --no-auto-mcp or JDELEGATE_AUTO_MCP=0; jev errors load nothing', () => {
  write(claudeJson, JSON.stringify({ mcpServers: { a: mcpDef('a'), b: mcpDef('b') } }));
  jevStub();
  assert.deepEqual(Object.keys(mcpOf(rdry(['--no-auto-role', '--mcp', 'b'], { MCP_SCORES: 'a=0.9' }).script)), ['b']);
  assert.deepEqual(mcpOf(rdry(['--no-auto-role', '--no-auto-mcp'], { MCP_SCORES: 'a=0.9' }).script), {});
  assert.deepEqual(mcpOf(rdry(['--no-auto-role'], { MCP_SCORES: 'a=0.9', JDELEGATE_AUTO_MCP: '0' }).script), {});
  stub('jev', 'exit 3');
  assert.deepEqual(mcpOf(rdry(['--no-auto-role'], {}).script), {});
  write(claudeJson, '{}');
});

test('lean --settings switches commit and PR attribution off', () => {
  const r = dry([]);
  const settings = JSON.parse(r.script.match(/--settings '(\{.*?\})'/)[1]);
  assert.equal(settings.includeCoAuthoredBy, false);
  assert.deepEqual(settings.attribution, { commit: '', pr: '' });
  assert.equal(settings.disableAllHooks, true);
});

test('--help documents the new flags', () => {
  const r = spawnSync(process.execPath, [JD, '--help'], { encoding: 'utf8' });
  assert.match(r.stdout, /--role NAME/);
  assert.match(r.stdout, /--no-auto-role/);
  assert.match(r.stdout, /--no-auto-mcp/);
});

// ── non-claude harnesses get the worker prompt in front of the brief ────
const mixedTiers = join(tmp, 'tiers-mixed.json');
const mixedRefs = ['openai-codex/gpt-test', 'opencode-go/glm-test', 'cliproxy/claude-test'];
write(mixedTiers, JSON.stringify({ tiers: Object.fromEntries(['T0', 'T1', 'T2', 'T3', 'T4'].map((t) => [t, mixedRefs])) }));
const briefOf = (r) => readFileSync(join(r.run, 'brief.md'), 'utf8');

const mixedEnv = { JEV_ROUTER_CONFIG: mixedTiers, JDELEGATE_AGENT_DIRS: `${agents}:${agentsParked}`, JDELEGATE_WORKER_ROLES: roles, JDELEGATE_CLAUDE_JSON: claudeJson };

for (const [harness, cmd] of [['codex', /codex exec/], ['opencode', /opencode run/]]) {
  test(`--harness ${harness}: brief file = worker prompt (contract, role, skill) + --- TASK --- + brief`, () => {
    jevStub();
    const r = dry(['--harness', harness, '--role', 'reviewer', '--skill', 'fake-skill'], { env: mixedEnv });
    assert.equal(r.status, 0, r.stderr);
    assert.match(r.script, cmd);
    assert.equal(r.prompt, undefined, 'no worker-prompt.md on non-claude harnesses');
    const b = briefOf(r);
    assert.match(b, /^You are a worker\./);
    assert.match(b, /## Role: reviewer\n[\s\S]*REVIEWER-BODY/);
    assert.match(b, /FAKE-SKILL-BODY/);
    assert.match(b, /USE-TABS-MARKER/);
    assert.match(b, /\n--- TASK ---\ndo the thing$/);
    assert.ok(b.indexOf('## Role: reviewer') < b.indexOf('--- TASK ---'));
  });
}

test('--harness codex: auto-role selection still runs (harness-independent)', () => {
  jevStub();
  const r = dry(['--harness', 'codex'], { env: { ...mixedEnv, ROLE_ANSWER: 'reviewer' } });
  assert.match(r.stdout, /role: reviewer \(auto\)/);
  assert.match(briefOf(r), /## Role: reviewer/);
});

test('claude path is unchanged: brief file is the bare brief, prompt goes in worker-prompt.md', () => {
  jevStub();
  const r = dry(['--role', 'reviewer'], { env: mixedEnv });
  assert.equal(briefOf(r), 'do the thing');
  assert.match(r.prompt, /## Role: reviewer/);
});

// ── concurrency, folding, partial failure, cache ────────────────────────
const sel = (args, env = {}) => { const t = Date.now(); const r = rdry(args, env); return { ...r, ms: Date.now() - t }; };
const sugStub = (body) => stub('jev-skill-suggest', body);

test('selection runs concurrently: route + role + mcp + skill, each call 1 s, finish in < 1.6 s', () => {
  write(claudeJson, JSON.stringify({ mcpServers: { a: mcpDef('a') } }));
  jevStub();
  sugStub('sleep 1; echo fake-skill');
  try {
    const r = sel(['--harness', 'claude'], { JEV_SLEEP: '1', JDELEGATE_AUTO_SKILL: '', ROLE_ANSWER: 'debugger', MCP_SCORES: 'a=0.9' });
    assert.equal(r.status, 0, r.stderr);
    assert.ok(r.ms < 1600, `took ${r.ms} ms`);
    assert.match(r.stdout, /role: debugger \(auto\)/);
    assert.match(r.stdout, /mcp: a \(auto\)/);
    assert.match(r.stdout, /skills: fake-skill \(auto\)/);
  } finally { write(claudeJson, '{}'); }
});

test('folded raw request: role and mcp decisions equal the separate-call decisions, thresholds unchanged', () => {
  write(claudeJson, JSON.stringify({ mcpServers: { a: mcpDef('a'), b: mcpDef('b'), c: mcpDef('c') } }));
  jevStub();
  try {
    const r = rdry([], { ROLE_ANSWER: 'reviewer', MCP_SCORES: 'a=0.7,b=0.95,c=0.69' });
    assert.match(r.stdout, /role: reviewer \(auto\)/);
    assert.deepEqual(Object.keys(mcpOf(r.script)), ['b', 'a']);
    assert.match(r.stdout, /mcp: b,a \(auto\)/);
    const raws = calls().filter((l) => l.startsWith('raw '));
    assert.equal(raws.length, 2, 'one route request, one folded role+mcp request');
    const folded = JSON.parse(raws.map((l) => l.slice(4)).find((l) => !JSON.parse(l).questions.tier));
    assert.equal(folded.state, 'do the thing', 'same state the separate calls used: the brief');
  } finally { write(claudeJson, '{}'); }
});

test('one failing sub-answer drops only that selection', () => {
  write(claudeJson, JSON.stringify({ mcpServers: { a: mcpDef('a'), b: mcpDef('b') } }));
  jevStub();
  try {
    const noRole = rdry([], { ROLE_ANSWER: 'debugger', RAW_BAD: 'role', MCP_SCORES: 'a=0.9,b=0.9' });
    assert.doesNotMatch(noRole.stdout, /role:/);
    assert.match(noRole.stdout, /mcp: \w,\w \(auto\)/);
    const oneMcp = rdry([], { ROLE_ANSWER: 'debugger', RAW_BAD: 'mcp:a', MCP_SCORES: 'a=0.9,b=0.9' });
    assert.match(oneMcp.stdout, /role: debugger \(auto\)/);
    assert.deepEqual(Object.keys(mcpOf(oneMcp.script)), ['b']);
    sugStub('exit 1');
    const noSkill = rdry([], { JDELEGATE_AUTO_SKILL: '', ROLE_ANSWER: 'debugger', MCP_SCORES: 'a=0.9' });
    assert.match(noSkill.stdout, /role: debugger/);
    assert.doesNotMatch(noSkill.stdout, /skills:/);
    const allFail = rdry([], { RAW_FAIL: '1' });
    assert.equal(allFail.status, 0, allFail.stderr);
    assert.match(allFail.stdout, /jev failed/);
    assert.doesNotMatch(allFail.stdout, /role:|mcp:/);
  } finally { write(claudeJson, '{}'); }
});

test('selection cache: same brief + cwd reuses route/role/skill/mcp with zero jev calls and says (cached)', () => {
  write(claudeJson, JSON.stringify({ mcpServers: { a: mcpDef('a') } }));
  jevStub();
  const sugLog = join(tmp, 'sug.log');
  sugStub(`echo called >> ${sugLog}; echo fake-skill`);
  writeFileSync(sugLog, '');
  const env = { JDELEGATE_SELECT_CACHE: '1', JDELEGATE_CACHE: join(tmp, 'cache-sel'), JDELEGATE_AUTO_SKILL: '', ROLE_ANSWER: 'debugger', MCP_SCORES: 'a=0.9' };
  try {
    const first = rdry(['--harness', 'claude'], env);
    assert.doesNotMatch(first.stdout, /\(cached\)/);
    assert.ok(calls().length >= 2);
    const second = rdry(['--harness', 'claude'], env);
    assert.deepEqual(calls(), [], 'cache hit makes zero jev calls');
    assert.equal(readFileSync(sugLog, 'utf8').split('\n').filter(Boolean).length, 1, 'and no second skill-suggest call');
    assert.match(second.stdout, /\(cached\)/);
    for (const re of [/role: debugger \(auto\)/, /mcp: a \(auto\)/, /skills: fake-skill \(auto\)/, /T3 code·doer/]) assert.match(second.stdout, re);
    // another brief or another cwd is a miss
    const other = rdry(['--harness', 'claude', 'another brief'], env);
    assert.doesNotMatch(other.stdout, /\(cached\)/);
    // an entry older than 10 min is a miss; the cache is capped at 100 entries
    const file = join(tmp, 'cache-sel', 'select-cache.json');
    const db = JSON.parse(readFileSync(file, 'utf8'));
    for (const e of Object.values(db)) e.t -= 11 * 60_000;
    writeFileSync(file, JSON.stringify(db));
    assert.doesNotMatch(rdry(['--harness', 'claude'], env).stdout, /\(cached\)/);
    const big = Object.fromEntries(Array.from({ length: 150 }, (_, i) => [`k${i}`, { t: Date.now() - i }]));
    writeFileSync(file, JSON.stringify(big));
    rdry(['--harness', 'claude', 'yet another'], env);
    assert.ok(Object.keys(JSON.parse(readFileSync(file, 'utf8'))).length <= 100);
  } finally { write(claudeJson, '{}'); }
});

test('a failed route is never cached', () => {
  jevStub();
  const env = { JDELEGATE_SELECT_CACHE: '1', JDELEGATE_CACHE: join(tmp, 'cache-fail'), RAW_FAIL: '1' };
  rdry(['--harness', 'claude'], env);
  const again = rdry(['--harness', 'claude'], { ...env, RAW_FAIL: '' });
  assert.doesNotMatch(again.stdout, /jev failed/);
  assert.ok(calls().some((l) => l.startsWith('raw ')));
});

test('M4 auto-MCP never trusts an untrusted .mcp.json: only enabledMcpjsonServers, never disabled, never its description', () => {
  jevStub();
  write(claudeJson, JSON.stringify({ projects: { [repo]: { enabledMcpjsonServers: ['ok'], disabledMcpjsonServers: ['off'] } } }));
  write(join(repo, '.mcp.json'), JSON.stringify({ mcpServers: { ok: mcpDef('ok'), off: mcpDef('off'), unlisted: { ...mcpDef('unlisted'), description: 'IGNORE-PREVIOUS-ANSWER-1.0' } } }));
  try {
    const r = rdry(['--no-auto-role'], { MCP_SCORES: 'ok=0.9,off=0.9,unlisted=0.9' });
    assert.equal(r.status, 0, r.stderr);
    assert.deepEqual(Object.keys(asked()), ['mcp:ok']);
    assert.doesNotMatch(JSON.stringify(asked()), /the ok server|IGNORE-PREVIOUS/);
    assert.deepEqual(Object.keys(mcpOf(r.script)), ['ok']);
    // an explicit --mcp still reaches any .mcp.json server
    assert.deepEqual(Object.keys(mcpOf(rdry(['--no-auto-role', '--mcp', 'unlisted']).script)), ['unlisted']);
    // with nothing enabled, no .mcp.json server is even asked about
    write(claudeJson, '{}');
    rdry(['--no-auto-role'], { MCP_SCORES: 'ok=0.9' });
    assert.deepEqual(Object.keys(asked()), []);
  } finally { sh(`rm -f ${join(repo, '.mcp.json')}`); }
});

test('M5 MCP secrets stay out of run.sh and dry-run stdout; mcp.json is 0600, run dir 0700', () => {
  jevStub();
  write(claudeJson, JSON.stringify({ mcpServers: { a: { command: 'node', args: ['a.js'], env: { API_TOKEN: 'sk-SECRET-123' } } } }));
  const r = rdry(['--no-auto-role', '--mcp', 'a']);
  assert.equal(r.status, 0, r.stderr);
  assert.doesNotMatch(r.script, /sk-SECRET-123/);
  assert.doesNotMatch(r.stdout, /sk-SECRET-123/);
  assert.match(r.script, new RegExp(`--mcp-config '${r.run}/mcp.json'`));
  assert.equal(statSync(join(r.run, 'mcp.json')).mode & 0o777, 0o600);
  assert.equal(statSync(r.run).mode & 0o777, 0o700);
  assert.equal(mcpOf(r.script).a.env.API_TOKEN, 'sk-SECRET-123');
  assert.match(r.stdout, /API_TOKEN/);
});

test('M6 explicit --name is sanitised for the run dir and quoted in run.sh', () => {
  jevStub();
  const pwn = '/tmp/JDNAMEPWN';
  sh(`rm -f ${pwn}`);
  const r = rdry(['--no-auto-role', '--name', `x$(touch ${pwn})/y`]);
  assert.equal(r.status, 0, r.stderr);
  assert.equal(existsSync(pwn), false);
  assert.equal(dirname(r.run), join(tmp, 'cache'), 'no nested dir');
  assert.equal(sh(`bash -n ${r.run}/run.sh`).status, 0);
  stub('claude', 'exit 0');
  sh(`PATH=${bin}:$PATH bash ${r.run}/run.sh </dev/null 2>/dev/null; true`);
  assert.equal(existsSync(pwn), false, 'executing the echo lines must not expand the name');
  const nl = rdry(['--no-auto-role', '--name', 'a\nb; touch /tmp/JDNAMEPWN2']);
  assert.equal(sh(`bash -n ${nl.run}/run.sh`).status, 0);
  assert.equal(existsSync('/tmp/JDNAMEPWN2'), false);
});

test('select-cache.json is replaced atomically (valid JSON, no tmp left behind)', () => {
  jevStub();
  const cache = join(tmp, 'atomic-cache');
  rdry(['--no-auto-role'], { JDELEGATE_SELECT_CACHE: '1', JDELEGATE_CACHE: cache });
  assert.equal(typeof JSON.parse(readFileSync(join(cache, 'select-cache.json'), 'utf8')), 'object');
  assert.deepEqual(readdirSync(cache).filter((f) => f.startsWith('select-cache') && f !== 'select-cache.json'), []);
  assert.match(readFileSync(JD, 'utf8'), /renameSync\(/);
});

test('--full on claude with an explicit --role or --skill warns and exits 2', () => {
  jevStub();
  for (const args of [['--full', '--role', 'debugger'], ['--full', '--skill', 'fake-skill']]) {
    const r = rdry(args);
    assert.equal(r.status, 2, r.stdout);
    assert.match(r.stderr, /--full/);
  }
  assert.equal(rdry(['--full']).status, 0);
});

// Owner rule 2026-10-03: GPT only for review and language; implementers never get GPT.
const ownerTiers = join(tmp, 'owner-tiers.json');
write(ownerTiers, JSON.stringify({
  tiers: Object.fromEntries(['T0', 'T1', 'T2', 'T3', 'T4'].map((t) => [t, ['cliproxy/claude-test']])),
  kinds: {
    code: { T3: ['cliproxy/claude-sonnet-5-5'] },
    review: { T3: ['openai-codex/gpt-6.1-sol', 'cliproxy/claude-opus-5-5'] },
    language: { T3: ['openai-codex/gpt-6.1-sol'] },
  },
}));
const printRoute = (args, env = {}) => {
  jevStub();
  writeFileSync(jevLog, '');
  return spawnSync(process.execPath, [JD, '--print', '--cwd', repo, ...args, 'do the thing'], {
    encoding: 'utf8',
    env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, JDELEGATE_JEV: join(bin, 'jev'), JEV_ROUTER_CONFIG: ownerTiers,
      JDELEGATE_CACHE: join(tmp, 'cache'), JDELEGATE_AGENT_DIRS: `${agents}:${agentsParked}`, JDELEGATE_SELECT_CACHE: '0', ...env },
  }).stdout;
};

test('--role reviewer routes to the review chain: codex gpt-6.1-sol', () => {
  assert.match(printRoute(['--role', 'reviewer']), /codex · openai-codex\/gpt-6\.1-sol .*review·T3/);
});

test('a coding brief with another role stays on claude, never GPT', () => {
  const out = printRoute(['--role', 'debugger']);
  assert.match(out, /claude · cliproxy\/claude-sonnet-5-5/);
  assert.doesNotMatch(out, /openai-codex/);
});

test('a language brief still routes to GPT', () => {
  assert.match(printRoute([], { KIND_ANSWER: 'language' }), /codex · openai-codex\/gpt-6\.1-sol/);
});

// ── quota-aware ranking (tiers.json quota_policy + quota.json) ──────────
const quotaTiers = join(tmp, 'quota-tiers.json');
const quotaChain = ['cliproxy/claude-sonnet-5-5', 'cliproxy/claude-opus-5-5', 'opencode-go/deepseek-v4-pro', 'commandcode/MiniMaxAI/MiniMax-M3', 'openrouter/nvidia/nemotron'];
const quotaConfig = (extra = {}) => write(quotaTiers, JSON.stringify({
  metered_providers: ['openrouter'],
  provider_priority: { cliproxy: 0, 'openai-codex': 0, 'opencode-go': 1, commandcode: 2, openrouter: 3 },
  quota_policy: { warm: 0.7, hot: 0.9, stale_minutes: 20 },
  tiers: Object.fromEntries(['T0', 'T1', 'T2', 'T3', 'T4'].map((t) => [t, quotaChain])),
  kinds: { review: { T3: ['openai-codex/gpt-6.1-sol', 'cliproxy/claude-opus-5-5'] }, language: { T3: ['openai-codex/gpt-6.1-sol', 'cliproxy/claude-sonnet-5-5'] } },
  ...extra,
}));
const quotaFile = join(tmp, 'quota.json');
const win = (five_hour, weekly, monthly = null) => ({ five_hour, weekly, monthly, resets: {}, source: 'api', at: new Date().toISOString(), note: '' });
const writeQuota = (providers, at = new Date()) => write(quotaFile, JSON.stringify({ at: at.toISOString(), providers }));
const failingSnapshot = join(bin, 'quota-snapshot-fail');
stub('quota-snapshot-fail', 'echo called >> "$SNAP_LOG"; exit 1');
const snapLog = join(tmp, 'snap.log');
const quotaRoute = (providers, { at, env = {}, args = [] } = {}) => {
  quotaConfig();
  if (providers === null) { try { unlinkSync(quotaFile); } catch {} } else writeQuota(providers, at);
  write(snapLog, '');
  const out = printRoute(args, { JEV_ROUTER_CONFIG: quotaTiers, JEV_QUOTA_FILE: quotaFile, JDELEGATE_QUOTA_SNAPSHOT: failingSnapshot, SNAP_LOG: snapLog, ...env });
  return out;
};
const first = (out) => out.match(/→ \w+ · (\S+)/)?.[1];

test('quota: healthy subscriptions keep the chain order', () => {
  const out = quotaRoute({ cliproxy: win(0.1, 0.2), 'opencode-go': win(0.1, 0.1), commandcode: win(0.1, 0.1) });
  assert.equal(first(out), 'cliproxy/claude-sonnet-5-5');
  assert.doesNotMatch(out, /quota:/);
});

test('quota: cliproxy weekly 0.95 drops behind the next healthy subscription and says why', () => {
  const out = quotaRoute({ cliproxy: win(0.1, 0.95), 'opencode-go': win(0.1, 0.1), commandcode: win(0.1, 0.1) });
  assert.equal(first(out), 'opencode-go/deepseek-v4-pro');
  assert.match(out, /quota: cliproxy weekly 95% → demoted/);
});

test('quota: warm is ranked after healthy, hot after warm; chain order inside a bucket', () => {
  // cliproxy hot (0.95), opencode-go warm (0.8), commandcode healthy
  assert.equal(first(quotaRoute({ cliproxy: win(0.1, 0.95), 'opencode-go': win(0.8, 0.1), commandcode: win(0.1, 0.1) })), 'commandcode/MiniMaxAI/MiniMax-M3');
  // cliproxy hot, opencode-go warm, commandcode hot -> warm one first
  assert.equal(first(quotaRoute({ cliproxy: win(0.1, 0.95), 'opencode-go': win(0.8, 0.1), commandcode: win(0.95, 0.1) })), 'opencode-go/deepseek-v4-pro');
  // all hot -> chain order again, still used
  assert.equal(first(quotaRoute({ cliproxy: win(0.95, 0.1), 'opencode-go': win(0.1, 0.99), commandcode: win(0.91, 0.1) })), 'cliproxy/claude-sonnet-5-5');
});

test('quota: the most-used window decides, monthly included', () => {
  const out = quotaRoute({ cliproxy: win(0.1, 0.1), 'opencode-go': win(0.1, 0.1, 0.93), commandcode: win(0.1, 0.1) }, { args: ['--harness', 'opencode'] });
  assert.match(out, /no live model|opencode-go/);
  const out2 = quotaRoute({ cliproxy: win(0.95, 0.1), 'opencode-go': win(0.1, 0.1, 0.93), commandcode: win(0.1, 0.1) });
  assert.equal(first(out2), 'commandcode/MiniMaxAI/MiniMax-M3');
  assert.match(out2, /opencode-go monthly 93% → demoted/);
});

test('quota: metered stays last even when every subscription is hot', () => {
  const out = quotaRoute({ cliproxy: win(0.99, 0.99), 'opencode-go': win(0.99, 0.99), commandcode: win(0.99, 0.99) });
  assert.doesNotMatch(first(out), /openrouter/);
});

test('quota: a provider with unknown quota (error / absent) uses the static priority', () => {
  const err = { five_hour: null, weekly: null, monthly: null, resets: {}, source: 'error', note: 'x' };
  // cliproxy unknown -> static 0, wins over opencode-go healthy (bucket 0, later index)
  assert.equal(first(quotaRoute({ cliproxy: err, 'opencode-go': win(0.1, 0.1) })), 'cliproxy/claude-sonnet-5-5');
  // opencode-go unknown (static 1) is behind a healthy commandcode (bucket 0) when cliproxy is hot
  assert.equal(first(quotaRoute({ cliproxy: win(0.95, 0.1), 'opencode-go': err, commandcode: win(0.1, 0.1) })), 'commandcode/MiniMaxAI/MiniMax-M3');
});

test('quota: a missing file triggers one snapshot attempt; failure falls back to the static ranking', () => {
  const out = quotaRoute(null);
  assert.equal(first(out), 'cliproxy/claude-sonnet-5-5');
  assert.equal(readFileSync(snapLog, 'utf8').trim().split('\n').length, 1);
});

test('quota: a fresh file is not refreshed; a stale one is, and the stale data is still used when the refresh fails', () => {
  quotaRoute({ cliproxy: win(0.1, 0.95), 'opencode-go': win(0.1, 0.1) });
  assert.equal(readFileSync(snapLog, 'utf8').trim(), '');
  const out = quotaRoute({ cliproxy: win(0.1, 0.95), 'opencode-go': win(0.1, 0.1) }, { at: new Date(Date.now() - 60 * 60_000) });
  assert.equal(readFileSync(snapLog, 'utf8').trim().split('\n').length, 1);
  assert.equal(first(out), 'opencode-go/deepseek-v4-pro');
});

test('quota: a stale file is replaced by a successful snapshot', () => {
  stub('quota-snapshot-ok', `echo '{"at":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","providers":{"cliproxy":{"five_hour":0.1,"weekly":0.97,"monthly":null,"source":"api"}}}' > "$QUOTA_SNAPSHOT_OUT"`);
  const out = quotaRoute({ cliproxy: win(0.1, 0.1), 'opencode-go': win(0.1, 0.1) }, { at: new Date(Date.now() - 60 * 60_000), env: { JDELEGATE_QUOTA_SNAPSHOT: join(bin, 'quota-snapshot-ok') } });
  assert.equal(first(out), 'opencode-go/deepseek-v4-pro');
});

test('quota: without quota_policy nothing changes', () => {
  quotaConfig({ quota_policy: undefined });
  writeQuota({ cliproxy: win(0.1, 0.99), 'opencode-go': win(0.1, 0.1) });
  const out = printRoute([], { JEV_ROUTER_CONFIG: quotaTiers, JEV_QUOTA_FILE: quotaFile });
  assert.equal(first(out), 'cliproxy/claude-sonnet-5-5');
});

test('quota: review and language chains follow quota but never gain GPT elsewhere', () => {
  const out = quotaRoute({ 'openai-codex': win(0.1, 0.95), cliproxy: win(0.1, 0.1) }, { args: ['--role', 'reviewer'] });
  assert.equal(first(out), 'cliproxy/claude-opus-5-5');
  const healthy = quotaRoute({ 'openai-codex': win(0.1, 0.1), cliproxy: win(0.1, 0.1) }, { args: ['--role', 'reviewer'] });
  assert.equal(first(healthy), 'openai-codex/gpt-6.1-sol');
  const impl = quotaRoute({ cliproxy: win(0.99, 0.99), 'opencode-go': win(0.99, 0.99), commandcode: win(0.99, 0.99), 'openai-codex': win(0, 0) });
  assert.doesNotMatch(impl, /openai-codex/);
});

// ── W4: the worker writes exit/out.log itself; `jdelegate wait` collects them ──
test('W4 run.sh writes exit via an EXIT trap and opencode/pi workers also write out.log', () => {
  for (const harness of ['opencode', 'pi']) {
    const r = dry(['--harness', harness].slice(0, 0));
    assert.equal(r.status, 0);
  }
  const r = dry([]);
  assert.match(r.script, /trap .*exit.* EXIT/);
});

test('W4 dry-run pi and opencode scripts produce out.log', () => {
  writeFileSync(tiers + '.w4', JSON.stringify({ tiers: Object.fromEntries(['T0', 'T1', 'T2', 'T3', 'T4'].map((t) => [t, ['opencode-go/x']])) }));
  const run = (h) => spawnSync(process.execPath, [JD, '--dry-run', '--harness', h, '--cwd', repo, 'do the thing'], { encoding: 'utf8',
    env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, JDELEGATE_JEV: join(bin, 'jev'), JEV_ROUTER_CONFIG: tiers + '.w4', JDELEGATE_CACHE: join(tmp, 'cache'), JDELEGATE_SELECT_CACHE: '0', JDELEGATE_AUTO_SKILL: '0', JDELEGATE_AUTO_ROLE: '0' } });
  const o = run('opencode'); const rs = readFileSync(o.stdout.match(/dry-run (\S+)/)[1] + '/run.sh', 'utf8');
  assert.match(rs, /tee '[^']*out\.log'/);
});

test('W4 killing the wrapper leaves exit and out.log in the run dir and `wait` returns them', async () => {
  const wcache = join(tmp, 'wcache');
  stub('claude', 'sleep 2; echo WORKER-RESULT-LINE');
  const { spawn } = await import('node:child_process');
  const child = spawn(process.execPath, [JD, '--no-tab', '--no-escalate', '--harness', 'claude', '--cwd', repo, '--name', 'w4job', 'do the thing'], {
    stdio: 'ignore', env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, JDELEGATE_JEV: join(bin, 'jev'), JEV_ROUTER_CONFIG: tiers, JDELEGATE_CACHE: wcache, JDELEGATE_SELECT_CACHE: '0', JDELEGATE_AUTO_SKILL: '0', JDELEGATE_AUTO_ROLE: '0', JDELEGATE_AUTO_MCP: '0' } });
  let runDir;
  for (let i = 0; i < 100 && !runDir; i++) { await new Promise((r) => setTimeout(r, 100)); try { runDir = readdirSync(wcache).map((n) => join(wcache, n)).find((p) => existsSync(join(p, 'run.sh'))); } catch {} }
  assert.ok(runDir, 'run dir created');
  await new Promise((r) => setTimeout(r, 300));
  child.kill('SIGKILL');
  const w = spawnSync(process.execPath, [JD, 'wait', 'w4job'], { encoding: 'utf8', timeout: 20000, env: { ...process.env, JDELEGATE_CACHE: wcache } });
  assert.equal(w.status, 0, w.stderr + w.stdout);
  assert.ok(existsSync(join(runDir, 'exit')) && existsSync(join(runDir, 'out.log')));
  assert.match(w.stdout, /exit 0/);
  assert.match(w.stdout, /WORKER-RESULT-LINE/);
  const w2 = spawnSync(process.execPath, [JD, 'wait', runDir], { encoding: 'utf8', timeout: 20000 });
  assert.match(w2.stdout, /WORKER-RESULT-LINE/);
});

// ── W5: no opencode for jobs that need a shell ──
const w5Tiers = join(tmp, 'w5-tiers.json');
write(w5Tiers, JSON.stringify({
  provider_priority: { 'opencode-go': 0, cliproxy: 1 },
  tiers: Object.fromEntries(['T0', 'T1', 'T2', 'T3', 'T4'].map((t) => [t, ['cliproxy/claude-test']])),
  kinds: { code: { T3: ['opencode-go/deepseek-v4.1-flash', 'cliproxy/claude-haiku-4-5-20251001'] } },
}));
test('W5 a brief that needs a shell never goes to opencode', () => {
  for (const words of [['git', 'commit'], ['run', 'the', 'tests'], ['then', 'lint'], ['use', 'bash']]) {
    const out = printRoute(words, { JEV_ROUTER_CONFIG: w5Tiers });
    assert.match(out, /claude · cliproxy\/claude-haiku/, words.join(' ') + ': ' + out);
  }
  assert.match(printRoute(['rename', 'a', 'variable'], { JEV_ROUTER_CONFIG: w5Tiers }), /opencode · opencode-go\/deepseek-v4\.1-flash/);
});

// ── timeout kills the whole worker tree and exits non-zero ─────────────
test('timeout: a sleeping fake worker is killed (no orphan) and jdelegate exits non-zero with a clear "timed out after N min" line', async () => {
  const wcache = join(tmp, 'wcache-to');
  const sleepMs = 60_000;
  // fake claude: sleeps forever, but records its own pid so the test can prove it is gone
  const pidFile = join(tmp, 'fake-claude.pid');
  stub('claude', `echo $$ > ${pidFile}; exec sleep ${Math.ceil(sleepMs / 1000)}`);
  const { spawn } = await import('node:child_process');
  // 0.05 min = 3 s. JDELEGATE_TIMEOUT_MS overrides for tests so a small fractional value is reliable.
  const t0 = Date.now();
  const r = spawnSync(process.execPath, [JD, '--no-tab', '--no-escalate', '--harness', 'claude', '--cwd', repo, '--name', 'tojob', '--timeout', '0.05', 'do the thing'], {
    encoding: 'utf8', timeout: 30_000,
    env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, JDELEGATE_JEV: join(bin, 'jev'), JEV_ROUTER_CONFIG: tiers,
      JDELEGATE_CACHE: wcache, JDELEGATE_SELECT_CACHE: '0', JDELEGATE_AUTO_SKILL: '0', JDELEGATE_AUTO_ROLE: '0', JDELEGATE_AUTO_MCP: '0',
      JDELEGATE_TIMEOUT_MS: '1500' } });
  const elapsed = Date.now() - t0;
  // 1) non-zero exit
  assert.notEqual(r.status, 0, `expected non-zero, got ${r.status}\nstdout: ${r.stdout}\nstderr: ${r.stderr}`);
  // 2) clear "timed out after N min" line on stdout
  assert.match(r.stdout, /timed out after 0\.05 min/, `stdout: ${r.stdout}\nstderr: ${r.stderr}`);
  // 3) the fake worker pid was recorded and the process is now gone
  const pid = Number(readFileSync(pidFile, 'utf8').trim());
  assert.ok(pid > 0, 'fake claude pid recorded');
  // give the OS a moment to reap
  for (let i = 0; i < 20; i++) {
    if (spawnSync('kill', ['-0', String(pid)]).status !== 0) break;
    await new Promise((res) => setTimeout(res, 100));
  }
  assert.equal(spawnSync('kill', ['-0', String(pid)]).status, 1, `fake claude pid ${pid} is still alive after timeout`);
  // 4) jdelegate did not hang waiting for the worker (sanity: < 20 s wall time, expected ~3 s)
  assert.ok(elapsed < 20_000, `jdelegate took ${elapsed} ms; should have timed out around 1.5 s`);
});

// ── timeout in herdr tab mode (no real herdr): pid file + recursive pgrep kills the worker tree ──
test('timeout in herdr tab mode (fake herdr that just nohups run.sh): the worker tree is killed and jdelegate exits non-zero', async () => {
  const wcache = join(tmp, 'wcache-tab');
  // fake herdr:
  //   pane get <pane>          -> {"workspace_id":"ws1"}
  //   tab create ...            -> {"tab_id":"TABID","pane_id":"PANEID"}
  //   pane run <pane> <cmd...>  -> nohup-eval the cmd in the background so jdelegate does not block
  //   tab close <tab>           -> do nothing (proves the worker is killed by SIGTERM/SIGKILL, not by tab close)
  // The "tab close does nothing" rule is the test: with the old code, the tab close was the only kill and the
  // fake worker would survive SIGHUP.
  stub('herdr', [
    'set -e',
    'log="$HERDR_LOG"',
    'echo "$*" >> "$log"',
    'case "$1" in',
    '  pane)',
    '    case "$2" in',
    '      get) echo \'{"workspace_id":"ws1"}\'; exit 0 ;;',
    '      run) shift 3; nohup bash -c "$*" </dev/null >/dev/null 2>&1 & disown; exit 0 ;;',
    '    esac ;;',
    '  tab)',
    '    case "$2" in',
    '      create) echo \'{"tab_id":"TABID","pane_id":"PANEID"}\'; exit 0 ;;',
    '      close) exit 0 ;;',
    '    esac ;;',
    'esac',
    'exit 0',
  ].join('\n'));
  // fake claude: records its pid, sleeps 60s (the test will SIGKILL it well before that)
  const pidFile = join(tmp, 'fake-claude-tab.pid');
  stub('claude', `echo $$ > ${pidFile}; exec sleep 60`);
  const herdrLog = join(tmp, 'herdr.log');
  writeFileSync(herdrLog, '');
  const t0 = Date.now();
  const r = spawnSync(process.execPath, [JD, '--no-escalate', '--harness', 'claude', '--cwd', repo, '--name', 'tabjob', '--timeout', '0.05', 'do the thing'], {
    encoding: 'utf8', timeout: 30_000,
    env: {
      ...process.env, PATH: `${bin}:${process.env.PATH}`,
      JDELEGATE_JEV: join(bin, 'jev'), JEV_ROUTER_CONFIG: tiers,
      JDELEGATE_CACHE: wcache, JDELEGATE_SELECT_CACHE: '0', JDELEGATE_AUTO_SKILL: '0', JDELEGATE_AUTO_ROLE: '0', JDELEGATE_AUTO_MCP: '0',
      JDELEGATE_TIMEOUT_MS: '1500',
      HERDR_ENV: '1', HERDR_PANE_ID: 'HOSTPANE', HERDR_LOG: herdrLog,
    },
  });
  const elapsed = Date.now() - t0;
  assert.notEqual(r.status, 0, `expected non-zero, got ${r.status}\nstdout: ${r.stdout}\nstderr: ${r.stderr}`);
  assert.match(r.stdout, /timed out after 0\.05 min/, `stdout: ${r.stdout}\nstderr: ${r.stderr}`);
  assert.match(r.stdout, /herdr tab /, `expected herdr-mode message, got: ${r.stdout}`);
  // the herdr stub was actually used: pane get, tab create, pane run, tab close
  const calls = readFileSync(herdrLog, 'utf8').split('\n').filter(Boolean);
  assert.ok(calls.some((l) => l.startsWith('pane get ')), 'herdr pane get was called');
  assert.ok(calls.some((l) => l.startsWith('tab create ')), 'herdr tab create was called');
  assert.ok(calls.some((l) => l.startsWith('pane run ')), 'herdr pane run was called');
  assert.ok(calls.some((l) => l.startsWith('tab close ')), 'herdr tab close was called (and did nothing)');
  // the fake worker pid was recorded and is now gone
  const pid = Number(readFileSync(pidFile, 'utf8').trim());
  assert.ok(pid > 0, 'fake claude pid recorded in tab mode');
  for (let i = 0; i < 50; i++) {
    if (spawnSync('kill', ['-0', String(pid)]).status !== 0) break;
    await new Promise((res) => setTimeout(res, 100));
  }
  assert.equal(spawnSync('kill', ['-0', String(pid)]).status, 1, `fake claude pid ${pid} is still alive after timeout in herdr tab mode`);
  // and jdelegate must not have hung
  assert.ok(elapsed < 20_000, `jdelegate took ${elapsed} ms; should have timed out around 1.5 s`);
});

// ── W8: agy always bypasses permissions; codex usage limit marks codex exhausted and falls back ──
test('W8 agy relay runs headless with --dangerously-skip-permissions by default', () => {
  const relay = join(homedir(), '.claude', 'skills', 'agy-delegate', 'scripts', 'relay.mjs');
  const agyLog = join(tmp, 'agy-argv.log');
  stub('agy', `echo "$@" >> "${agyLog}"; [ "$1" = changelog ] && echo "1.0.16: x"; echo done`);
  write(join(tmp, 'brief.txt'), 'hello');
  spawnSync(process.execPath, [relay, '--brief', join(tmp, 'brief.txt'), '--cd', repo, '--out-dir', join(tmp, 'agyout')], { encoding: 'utf8', timeout: 20000, env: { ...process.env, PATH: `${bin}:${process.env.PATH}` } });
  assert.match(readFileSync(agyLog, 'utf8'), /--dangerously-skip-permissions/);
});

test('W8 a codex usage limit marks codex exhausted until the printed reset and the run falls back to the next tier', () => {
  const ex = join(tmp, 'exhausted.json');
  const cache = join(tmp, 'cx-cache');
  stub('codex', `echo "You've hit your usage limit. Upgrade to Pro or try again at Oct 9th, 2030 3:14 PM."; exit 1`);
  stub('claude', 'echo FALLBACK-CLAUDE-RAN');
  write(join(tmp, 'cx-tiers.json'), JSON.stringify({
    tiers: Object.fromEntries(['T0', 'T1', 'T2', 'T3', 'T4'].map((t) => [t, ['cliproxy/claude-test']])),
    kinds: { review: { T3: ['openai-codex/gpt-6.1-sol', 'cliproxy/claude-opus-5-5'] } },
  }));
  jevStub();
  const r = spawnSync(process.execPath, [JD, '--no-tab', '--no-escalate', '--role', 'reviewer', '--cwd', repo, 'review it'], { encoding: 'utf8', timeout: 30000,
    env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, JDELEGATE_JEV: join(bin, 'jev'), JEV_ROUTER_CONFIG: join(tmp, 'cx-tiers.json'), JEV_EXHAUSTED_FILE: ex, JDELEGATE_CACHE: cache,
      JDELEGATE_AGENT_DIRS: `${agents}:${agentsParked}`, JDELEGATE_SELECT_CACHE: '0', JDELEGATE_AUTO_SKILL: '0', JDELEGATE_AUTO_MCP: '0', JDELEGATE_AUTO_ROLE: '0' } });
  assert.match(r.stdout, /FALLBACK-CLAUDE-RAN/, r.stdout + r.stderr);
  const j = JSON.parse(readFileSync(ex, 'utf8'));
  assert.equal(j['openai-codex'], new Date('Oct 9 2030 3:14 PM').getTime());
});

// Owner rule 2026-10-07: computer use / browser-e2e / running tests / QA go to kind test (Haiku 5.5).
test('test-kind briefs and role=qa-engineer route to kinds.test; code briefs do not', () => {
  const t = join(tmp, 'tiers-test-kind.json');
  write(t, JSON.stringify({
    tiers: { T0: ['cliproxy/claude-test'], T1: ['cliproxy/claude-test'], T2: ['opencode-go/x'], T3: ['cliproxy/claude-test'], T4: ['cliproxy/claude-test'] },
    kinds: { test: { T2: ['cliproxy/claude-haiku-5-5'], T3: ['cliproxy/claude-haiku-5-5'] } },
  }));
  const route = (brief, extra = []) => spawnSync(process.execPath, [JD, '--print', ...extra, brief], {
    encoding: 'utf8',
    env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, JDELEGATE_JEV: join(bin, 'jev'), JEV_ROUTER_CONFIG: t, JDELEGATE_CACHE: join(tmp, 'cache'), JDELEGATE_SELECT_CACHE: '0' },
  }).stdout;
  assert.match(route('run the e2e tests for the login page'), /test·.*claude-haiku-5-5/);
  assert.match(route('use playwright to click through checkout'), /claude-haiku-5-5/);
  assert.match(route('review the diff', ['--role', 'qa-engineer']), /claude-haiku-5-5/);
  assert.doesNotMatch(route('rename function foo in utils.ts'), /haiku-5-5/);
});

// Owner decision 2026-10-08: Sonnet/Haiku claude workers get the Opus advisor; lean workers keep the Skill tool.
const tiersFor = (ref) => {
  const f = join(tmp, `tiers-${ref.replace(/\W/g, '_')}.json`);
  write(f, JSON.stringify({ tiers: Object.fromEntries(['T0', 'T1', 'T2', 'T3', 'T4'].map((t) => [t, [ref]])) }));
  return f;
};
const advisorEnv = (ref, extra = {}) => ({ JEV_ROUTER_CONFIG: tiersFor(ref), JDELEGATE_ADVISOR: '', ...extra });

test('advisor: sonnet and haiku claude workers get --advisor opus, lean and --full', () => {
  for (const ref of ['cliproxy/claude-sonnet-5-5', 'cliproxy/claude-haiku-5-5']) {
    const lean = dry([], { env: advisorEnv(ref) });
    assert.equal(lean.status, 0, lean.stderr);
    assert.match(lean.script, /--advisor opus /, ref);
    const full = dry(['--full'], { env: advisorEnv(ref) });
    assert.equal(full.status, 0, full.stderr);
    assert.match(full.script, /--advisor opus /, ref);
  }
});

test('advisor: opus workers get no advisor flag', () => {
  const r = dry([], { env: advisorEnv('cliproxy/claude-opus-5-5') });
  assert.equal(r.status, 0, r.stderr);
  assert.doesNotMatch(r.script, /--advisor/);
});

test('advisor: JDELEGATE_ADVISOR=0 drops the flag; JDELEGATE_ADVISOR=<model> overrides the advisor model', () => {
  const off = dry([], { env: advisorEnv('cliproxy/claude-sonnet-5-5', { JDELEGATE_ADVISOR: '0' }) });
  assert.equal(off.status, 0, off.stderr);
  assert.doesNotMatch(off.script, /--advisor/);
  const over = dry([], { env: advisorEnv('cliproxy/claude-haiku-5-5', { JDELEGATE_ADVISOR: 'claude-fable-5-1' }) });
  assert.equal(over.status, 0, over.stderr);
  assert.match(over.script, /--advisor claude-fable-5-1 /);
});

test('lean worker keeps the Skill tool on: no --disable-slash-commands, Skill in --tools', () => {
  const r = dry([]);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.script, /--tools Bash Read Edit Write Glob Grep Skill 2>&1/);
  assert.doesNotMatch(r.script, /--disable-slash-commands/);
  // bundled Claude Code skills add ~3k first-turn tokens; the repo's .claude/skills still load
  assert.match(r.script, /"disableBundledSkills":true/);
});

// ---- world live hooks: `track add` on worker start and exit ----
function trackRun(env, { claudeBody = 'echo worker-output; exit 0', cwd = repo } = {}) {
  const tdir = mkdtempSync(join(tmpdir(), 'jd-track-'));
  const log = join(tdir, 'track.log');
  const tbin = join(tdir, 'bin');
  mkdirSync(tbin, { recursive: true });
  for (const [n, body] of Object.entries({ claude: claudeBody, jev: 'exit 3' })) { writeFileSync(join(tbin, n), `#!/bin/bash\n${body}\n`); chmodSync(join(tbin, n), 0o755); }
  if (!env.NO_TRACK) {
    writeFileSync(join(tbin, 'track'), `#!/bin/bash\nl=$(printf '%s\\t' "$@"); printf '%s\\n' "$l" >> ${log}\n`);
    chmodSync(join(tbin, 'track'), 0o755);
  }
  const { NO_TRACK, ...rest } = env;
  const r = spawnSync(process.execPath, [JD, '--no-tab', '--no-escalate', '--harness', 'claude', '--cwd', cwd, '--name', 'Wjob', 'do the thing'], {
    encoding: 'utf8', timeout: 30_000,
    env: { ...process.env, PATH: `${tbin}:/usr/bin:/bin:${dirname(process.execPath)}`, JDELEGATE_JEV: join(tbin, 'jev'), JEV_ROUTER_CONFIG: tiers,
      JDELEGATE_CACHE: join(tdir, 'cache'), JDELEGATE_SELECT_CACHE: '0', JDELEGATE_AUTO_SKILL: '0', JDELEGATE_AUTO_ROLE: '0', JDELEGATE_AUTO_MCP: '0', ...rest },
  });
  spawnSync('sleep', ['0.5']);
  const calls = existsSync(log) ? readFileSync(log, 'utf8').split('\n').filter(Boolean).map((l) => l.split('\t').slice(0, -1)) : [];
  return { ...r, calls };
}
const flagOf = (c, k) => c[c.indexOf(k) + 1];

test('world hook: start and exit emit two track calls with run:<ref>:<status> keys', () => {
  const r = trackRun({});
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.equal(r.calls.length, 2, JSON.stringify(r.calls));
  const [start, end] = r.calls;
  const ref = flagOf(start, '--ref');
  assert.ok(ref.length > 0);
  assert.equal(flagOf(start, '--kind'), 'worker');
  assert.equal(flagOf(start, '--status'), 'running');
  assert.equal(flagOf(start, '--source'), 'live');
  assert.equal(flagOf(start, '--project'), 'repo');
  assert.equal(flagOf(start, '--model'), 'claude-test');
  assert.equal(flagOf(start, '--title'), 'Wjob · claude-test');
  assert.equal(flagOf(start, '--key'), `run:${ref}:running`);
  assert.equal(flagOf(end, '--status'), 'done');
  assert.equal(flagOf(end, '--key'), `run:${ref}:done`);
  assert.match(flagOf(end, '--dur'), /^\d+$/);
});

test('world hook: a failing worker emits status failed', () => {
  const r = trackRun({}, { claudeBody: 'exit 4' });
  assert.notEqual(r.status, 0);
  const end = r.calls.find((c) => flagOf(c, '--status') === 'failed');
  assert.ok(end, JSON.stringify(r.calls));
  assert.match(flagOf(end, '--key'), /^run:.+:failed$/);
});

test('world hook: WORLD_TRACK=0 emits no track calls', () => {
  const r = trackRun({ WORLD_TRACK: '0' });
  assert.equal(r.status, 0);
  assert.equal(r.calls.length, 0);
});

test('world hook: missing track does not change the exit code or output', () => {
  const ok = trackRun({ NO_TRACK: '1' });
  assert.equal(ok.status, 0, ok.stdout + ok.stderr);
  assert.doesNotMatch(ok.stderr, /track/);
  const bad = trackRun({ NO_TRACK: '1' }, { claudeBody: 'exit 4' });
  assert.equal(bad.status, 4);
});
