// Google Drive on the beldify account (u/1). New > File upload. Drive has no scheduler; posts immediately.
import { stopDryRun } from '../lib/browser.mjs';

const SEL = {
  drive: 'https://drive.google.com/drive/u/1/',
  newButton: 'button:has-text("New"), [aria-label="New"]',
  fileUpload: 'text=File upload',
};

export default {
  name: 'drive',
  async run(ctx) {
    const page = await ctx.newPage();
    await page.goto(SEL.drive, { waitUntil: 'domcontentloaded' });
    await page.locator(SEL.newButton).first().click({ timeout: 60_000 });
    if (ctx.mode === 'dryrun') {
      // Opening the New menu is the last safe step for Drive; uploading is the action itself.
      await page.locator(SEL.fileUpload).first().waitFor({ timeout: 30_000 });
      return stopDryRun(page, ctx, 'drive');
    }
    const chooser = page.waitForEvent('filechooser', { timeout: 60_000 });
    await page.locator(SEL.fileUpload).first().click();
    await (await chooser).setFiles(ctx.post.video);
    await page.locator('text=Upload complete').first().waitFor({ timeout: 30 * 60_000 }).catch(() => {});
    await page.close().catch(() => {});
    return { ok: true, url: null, note: 'uploaded to beldify Drive (no link captured)' };
  },
};
