// grok.mjs — ask the Grok CLI (Grok Build, `grok -p`) to search X for design posts about the
// idea. Grok has X search built in, so it reaches posts and accounts that no web search
// engine has indexed. It runs `grok` on this machine when it is installed, else over ssh on
// the host in XDESIGN_GROK_SSH (default MyContabo, when ~/.ssh/config knows that name).
// XDESIGN_GROK_SSH="" turns the ssh fallback off.
//
// Grok's answer is only a list of links. Every link is then read through the post API
// (hydrate in xdesign.mjs), so an id Grok made up is dropped there, never shown.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { extractPostRefs, slugify } from './lib.mjs';

const CACHE = process.env.XDESIGN_CACHE || path.join(os.homedir(), '.cache', 'xdesign');
const TTL_MS = 24 * 3600e3, TIMEOUT_MS = 300e3;

export function grokPrompt(idea, days = 90) {
  return `Use your X (Twitter) search tool, not general web search. Find up to 20 X posts from the last ${days} days `
    + `that show a UI/UX DESIGN close to this idea: "${String(idea).replace(/"/g, "'")}". `
    + 'Designers posting an image or video of the screen. Posts about the same kind of screen for another business are fine '
    + 'when the design is strong. Prefer posts with many likes and bookmarks. Skip news, job posts, memes, tutorials and '
    + 'Power BI or Excel course projects. Reply with ONLY a JSON array, no prose: '
    + '[{"url":"https://x.com/<handle>/status/<id>","why":"<6 words>"}]. '
    + 'Only include URLs you actually saw in search results; never invent ids.';
}

function sshHost() {
  const env = process.env.XDESIGN_GROK_SSH;
  if (env !== undefined) return env || null;
  try { return /^\s*Host\s+.*\bMyContabo\b/im.test(fs.readFileSync(path.join(os.homedir(), '.ssh', 'config'), 'utf8')) ? 'MyContabo' : null; } catch { return null; }
}

export function grokWhere() {
  if (spawnSync('grok', ['--version'], { stdio: 'ignore', timeout: 10000 }).status === 0) return { where: 'local' };
  const host = sshHost();
  return host ? { where: 'ssh', host } : null;
}

// Returns { ok, refs: [{id, handle}], note }.
export function searchGrok(idea, { days = 90 } = {}) {
  const prompt = grokPrompt(idea, days);
  const file = path.join(CACHE, 'grok', `${slugify(idea)}-${days}.json`);
  try { const hit = JSON.parse(fs.readFileSync(file, 'utf8')); if (Date.now() - hit.at < TTL_MS) return { ok: true, refs: hit.refs, note: `grok: ${hit.refs.length} links (saved today)` }; } catch { /* no cache */ }
  const at = grokWhere();
  if (!at) return { ok: false, refs: [], note: 'grok: skipped, no grok CLI here and no ssh host (XDESIGN_GROK_SSH)' };
  const args = ['--prompt-file', '/dev/stdin', '--output-format', 'plain', '--max-turns', '8', '--disallowed-tools', 'bash,edit,write'];
  const r = at.where === 'local'
    ? spawnSync('grok', args, { input: prompt, encoding: 'utf8', timeout: TIMEOUT_MS, cwd: os.tmpdir() })
    : spawnSync('ssh', ['-o', 'ConnectTimeout=15', '-o', 'BatchMode=yes', at.host, `cd /tmp && grok ${args.join(' ')}`], { input: prompt, encoding: 'utf8', timeout: TIMEOUT_MS });
  const where = at.where === 'local' ? 'local' : `on ${at.host}`;
  if (r.error || r.status !== 0) return { ok: false, refs: [], note: `grok (${where}): failed (${r.error?.code || 'exit ' + r.status}) ${String(r.stderr || '').trim().split('\n').pop()?.slice(0, 120) || ''}` };
  const refs = extractPostRefs(r.stdout);
  if (refs.length) { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, JSON.stringify({ at: Date.now(), refs })); }
  return { ok: true, refs, note: `grok (${where}): ${refs.length} links` };
}
