// Facebook personal profile (محمد البردوني) via facebook.com/reels/create/. Posts immediately (no scheduler here).
import { typeAndVerify, stopDryRun } from '../lib/browser.mjs';

const SEL = {
  create: 'https://www.facebook.com/reels/create/',
  profileName: 'محمد البردوني',
  reelsList: 'https://www.facebook.com/me/reels/',
  fileInput: 'input[type=file]',
  description: '[contenteditable=true][role=textbox]',
  next: 'div[role=button]:has-text("Next")',
  publicAudience: 'text=Public',
  post: 'div[role=button]:has-text("Post")',
  copyrightCheck: 'text=Checking for copyrighted content',
  reelLink: 'a[href*="/reel/"]',
};

export default {
  name: 'facebook_profile',
  async run(ctx) {
    if (ctx.post.schedule) throw new Error('facebook_profile: no scheduler in this flow; post manually or drop schedule');
    const page = await ctx.newPage();
    await page.goto(SEL.create, { waitUntil: 'domcontentloaded' });
    // The active identity must be the profile, not the Page: fail closed unless the composer shows the profile name.
    const asProfile = await page.getByText(SEL.profileName).first().isVisible({ timeout: 60_000 }).catch(() => false);
    if (!asProfile) throw new Error(`facebook_profile: composer does not show "${SEL.profileName}"; switch from the Page to the profile`);
    await page.locator(SEL.fileInput).first().setInputFiles(ctx.post.video, { timeout: 120_000 });
    await page.locator(SEL.next).first().click({ timeout: 300_000 });
    await page.locator(SEL.next).first().click({ timeout: 300_000 });
    const desc = page.locator(SEL.description).first();
    await typeAndVerify(page, desc, ctx.platform.description, { label: 'facebook_profile description' });
    await page.locator(SEL.publicAudience).first().click({ timeout: 30_000 }).catch(() => {});
    await page.locator(SEL.copyrightCheck).first().waitFor({ state: 'hidden', timeout: 20 * 60_000 }).catch(() => {});

    if (ctx.mode === 'dryrun') return stopDryRun(page, ctx, 'facebook_profile');

    await page.locator(SEL.post).last().click({ timeout: 60_000 });
    await page.waitForTimeout(8000);
    await page.goto(SEL.reelsList, { waitUntil: 'domcontentloaded' });
    const href = await page.locator(SEL.reelLink).first().getAttribute('href', { timeout: 60_000 }).catch(() => null);
    const id = href && href.match(/\/reel\/(\d+)/);
    await page.close().catch(() => {});
    return { ok: true, url: id ? `https://www.facebook.com/reel/${id[1]}` : null,
      note: id ? null : 'posted; reel id not found' };
  },
};
