// mbardouni.dev update, last step, no browser. Runs after every other platform.
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { ssh } from '../lib/remote.mjs';
import { tiktokIdFromUrl, addTiktokEntry, serializeSocialVideos } from '../lib/portfolio.mjs';

const run = promisify(execFile);
const SOCIAL = '/root/portfolio-next/public/content/social-videos.json';
const YT_JSON = '/var/lib/mbardouni/content/youtube.json';
const SITE = 'https://www.mbardouni.dev/ar/videos';

// /ar/videos is ISR (revalidate 300 s, stale-while-revalidate): the first hit after a write
// serves the old page and triggers a rebuild, so poll for up to 8 minutes.
async function verifyOnSite(id, { tries = 16, waitMs = 30_000 } = {}) {
  for (let i = 0; i < tries; i++) {
    const { stdout } = await run('curl', ['-s', SITE]);
    const n = stdout.split(id).length - 1;
    if (n >= 1) return n;
    if (i < tries - 1) await new Promise((r) => setTimeout(r, waitMs));
  }
  throw new Error(`${id} not found on ${SITE} after ${(tries * waitMs) / 60000} min`);
}

export default {
  name: 'portfolio',
  async run(ctx) {
    if (ctx.mode === 'dryrun') return { ok: true, url: null, note: 'dry-run: portfolio skipped (no writes)' };
    const notes = [];

    const tt = ctx.results.tiktok;
    if (tt && tt.ok && tt.url && ctx.post.schedule) {
      notes.push('tiktok scheduled: not listed yet (a card for an unpublished post would be broken); backfill after it goes live');
    } else if (tt && tt.ok && tt.url) {
      const id = tiktokIdFromUrl(tt.url);
      const doc = JSON.parse(await ssh(`cat ${SOCIAL}`));
      const { doc: next, added } = addTiktokEntry(doc, { url: tt.url, title: ctx.platform.title });
      if (added) {
        const tmp = `${SOCIAL}.tmp`;
        await ssh(`cat > ${tmp} && mv ${tmp} ${SOCIAL}`, { input: serializeSocialVideos(next) });
      }
      await verifyOnSite(id);
      notes.push(added ? `tiktok ${id} prepended` : `tiktok ${id} already listed`);
    } else {
      notes.push('tiktok: no url in results, skipped');
    }

    const yt = ctx.results.youtube;
    if (yt && yt.ok && yt.url && !ctx.post.schedule) {
      const id = yt.url.split('/').pop();
      await ssh('cd /root/portfolio-next && CONTENT_DIR=/var/lib/mbardouni/content flock -w 600 /tmp/youtube-sync.lock node scripts/youtube-sync.mjs');
      const found = (await ssh(`grep -c ${id} ${YT_JSON} || true`)).trim();
      if (Number(found) < 1) throw new Error(`youtube ${id} missing from ${YT_JSON} after sync`);
      notes.push(`youtube ${id} synced`);
    } else if (yt && yt.ok && ctx.post.schedule) {
      notes.push('youtube scheduled: skipped, the 6-hourly cron picks it up after it goes public');
    }

    return { ok: true, url: SITE, note: notes.join('; ') };
  },
};
