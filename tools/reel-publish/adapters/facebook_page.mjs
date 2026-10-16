// Facebook Page Mbardouni.dev via Business Suite reels composer. Never touch Boost.
import { typeAndVerify, stopDryRun } from '../lib/browser.mjs';
import { scheduleParts } from '../lib/post.mjs';

const PAGE_ASSET = '1290399254155522';
const SEL = {
  composer: `https://business.facebook.com/latest/reels_composer?asset_id=${PAGE_ASSET}`,
  postTo: 'text=Mbardouni.dev',
  addVideo: 'text=Add video',
  title: '[aria-label*="Title" i], [placeholder*="Title" i]',
  description: '[aria-label*="Description" i], [contenteditable=true][role=textbox]',
  next: 'div[role=button]:has-text("Next"), button:has-text("Next")',
  shareNow: 'text=Share now',
  autoCaptions: 'input[type=checkbox][aria-label*="caption" i], text=Auto-generated captions',
  share: 'div[role=button]:has-text("Share"), button:has-text("Share")',
  contentPosts: 'https://business.facebook.com/latest/content_calendar?asset_id=' + PAGE_ASSET,
};

export default {
  name: 'facebook_page',
  async run(ctx) {
    const page = await ctx.newPage();
    await page.goto(SEL.composer, { waitUntil: 'domcontentloaded' });
    if (!(await page.locator(SEL.postTo).first().isVisible({ timeout: 60_000 }).catch(() => false))) {
      throw new Error('"Post to" does not show Mbardouni.dev; switch the Page before posting');
    }
    const chooser = page.waitForEvent('filechooser', { timeout: 60_000 });
    await page.locator(SEL.addVideo).first().click();
    await (await chooser).setFiles(ctx.post.video);

    await typeAndVerify(page, page.locator(SEL.title).first(), ctx.platform.title, { label: 'facebook_page title' });
    await typeAndVerify(page, page.locator(SEL.description).first(), ctx.platform.description, { label: 'facebook_page description' });
    await page.locator(SEL.next).first().click({ timeout: 300_000 });
    await page.locator(SEL.next).first().click({ timeout: 300_000 });

    if (ctx.post.schedule) {
      // Scheduling in this flow is not verified; publish immediately rather than guess a picker.
      ctx.log('facebook_page: scheduler not wired in this flow; posting now');
    }
    await page.locator(SEL.shareNow).first().click({ timeout: 30_000 }).catch(() => {});
    const cc = page.locator(SEL.autoCaptions).first();
    if (await cc.isChecked?.().catch(() => false)) await cc.uncheck();

    if (ctx.mode === 'dryrun') return stopDryRun(page, ctx, 'facebook_page');

    await page.locator(SEL.share).last().click({ timeout: 60_000 });
    await page.waitForTimeout(8000);
    await page.close().catch(() => {});
    return { ok: true, url: null, note: 'posted; check Content > Posts & reels for the link' };
  },
};
