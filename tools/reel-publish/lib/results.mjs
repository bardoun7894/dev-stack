// results.json lives next to post.json: {platform: {ok, url, error, at}}.
// An ok platform is never overwritten, so a re-run cannot double-post.
import fs from 'node:fs';
import path from 'node:path';

const FILE = 'results.json';

export function readResults(dir) {
  const p = path.join(dir, FILE);
  if (!fs.existsSync(p)) return {};
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

export function recordResult(dir, platform, { ok, url = null, error = null }) {
  const all = readResults(dir);
  if (all[platform] && all[platform].ok === true) return all[platform];
  const entry = { ok: Boolean(ok), url: url || null, error: error || null, at: new Date().toISOString() };
  all[platform] = entry;
  const tmp = path.join(dir, `${FILE}.tmp`);
  fs.writeFileSync(tmp, JSON.stringify(all, null, 2) + '\n');
  fs.renameSync(tmp, path.join(dir, FILE));
  return entry;
}
