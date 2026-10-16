// YouTube Shorts via the API, run on MyContabo (yt_publish.cjs). No browser.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ssh, scp } from '../lib/remote.mjs';
import { scheduleParts } from '../lib/post.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = '/root/media-uploads/reel-publish';

export default {
  name: 'youtube',
  async run(ctx) {
    const yt = ctx.platform;
    await ssh(`mkdir -p ${ROOT}`);
    await scp(path.join(HERE, '../server/yt_publish.cjs'), `${ROOT}/yt_publish.cjs`);
    if (ctx.mode === 'dryrun') {
      const out = await ssh(`cd /root/tokyo && node ${ROOT}/yt_publish.cjs --check`);
      return { ok: true, url: null, note: `dry-run channel check: ${out.trim()}` };
    }
    const remoteDir = `${ROOT}/${ctx.post.slug}`;
    const meta = {
      title: yt.title,
      description: yt.description || '',
      tags: yt.tags || [],
      publishAt: ctx.post.schedule ? scheduleParts(ctx.post.schedule).iso : null,
    };
    const metaPath = path.join(ctx.runDir, 'youtube-meta.json');
    fs.mkdirSync(ctx.runDir, { recursive: true });
    fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));
    await ssh(`mkdir -p ${remoteDir}`);
    await scp(ctx.post.video, `${remoteDir}/video.mp4`);
    await scp(metaPath, `${remoteDir}/meta.json`);
    const out = await ssh(`cd /root/tokyo && node ${ROOT}/yt_publish.cjs ${ctx.post.slug}`);
    const parsed = JSON.parse(out.trim().split('\n').at(-1));
    return { ok: true, url: parsed.url, note: meta.publishAt ? `scheduled ${meta.publishAt}` : null };
  },
};
