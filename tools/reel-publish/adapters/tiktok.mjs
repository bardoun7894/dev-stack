// TikTok Studio upload (browser). Selectors drift; keep them here.
import { typeAndVerify, stopDryRun } from '../lib/browser.mjs';
import { scheduleParts } from '../lib/post.mjs';

const SEL = {
  upload: 'https://www.tiktok.com/tiktokstudio/upload',
  content: 'https://www.tiktok.com/tiktokstudio/content',
  fileInput: 'input[type=file]',
  caption: '.public-DraftEditor-content[contenteditable=true], [contenteditable=true]',
  scheduleRadio: 'text=Schedule',
  post: 'button:has-text("Post"), button:has-text("Schedule")',
  checkDone: 'text=Content check lite',
  contentLink: 'a[href*="/video/"]',
};
const CHECK_TIMEOUT = 20 * 60 * 1000;

export default {
  name: 'tiktok',
  async run(ctx) {
    const page = await ctx.newPage();
    await page.goto(SEL.upload, { waitUntil: 'domcontentloaded' });
    await page.locator(SEL.fileInput).first().setInputFiles(ctx.post.video, { timeout: 120_000 });
    const caption = page.locator(SEL.caption).first();
    await caption.waitFor({ timeout: 120_000 });
    await typeAndVerify(page, caption, ctx.platform.caption, { label: 'tiktok caption' });

    if (ctx.post.schedule) {
      const s = scheduleParts(ctx.post.schedule);
      ctx.log(`tiktok schedule ${s.date} ${s.time24} GMT+0`);
      await page.locator(SEL.scheduleRadio).first().click();
      await page.locator('[class*="date-picker"], input[placeholder*="date" i]').first().click();
      await page.locator(`[aria-label="${s.date}"], [data-date="${s.date}"]`).first().click();
      await page.locator('[class*="timepicker"], input[placeholder*="time" i]').first().click();
      await page.locator('.tiktok-timepicker-option-text', { hasText: s.time24.slice(0, 2) }).first().click();
      await page.locator('.tiktok-timepicker-option-text', { hasText: s.time24.slice(3) }).first().click();
    }

    // Content check lite takes about 10 minutes; clicking Post early turns into a "Post now" prompt.
    // UNVERIFIED: the label may stay on the page after the check passes (then this waits the full timeout).
    // Confirm on the first --dry-run and switch to the passed-state text if so.
    await page.locator(SEL.checkDone).first().waitFor({ state: 'hidden', timeout: CHECK_TIMEOUT }).catch(() => {});

    if (ctx.mode === 'dryrun') return stopDryRun(page, ctx, 'tiktok');

    await page.locator(SEL.post).first().click({ timeout: CHECK_TIMEOUT });
    await page.waitForURL(/tiktokstudio\/content|upload_success|manage/, { timeout: 120_000 }).catch(() => {});

    await page.goto(SEL.content, { waitUntil: 'domcontentloaded' });
    const href = await page.locator(SEL.contentLink).first().getAttribute('href', { timeout: 60_000 }).catch(() => null);
    const id = href && href.match(/\/video\/(\d+)/);
    await page.close().catch(() => {});
    return { ok: true, url: id ? `https://www.tiktok.com/@mbardouni.dev/video/${id[1]}` : null,
      note: id ? (ctx.post.schedule ? 'scheduled' : null) : 'posted; video id not found in Studio content list' };
  },
};
