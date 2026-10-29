// LinkedIn personal profile: feed > Video. Schedule via the clock icon. Text goes in via the Quill editor.
import { typeAndVerify, stopDryRun } from '../lib/browser.mjs';
import { scheduleParts } from '../lib/post.mjs';

const SEL = {
  feed: 'https://www.linkedin.com/feed/',
  videoButton: 'button:has-text("Video")',
  fileInput: 'input[type=file][accept*=video]',
  next: 'button:has-text("Next")',
  editor: '.ql-editor[contenteditable=true]',
  clock: 'button[aria-label*="chedule" i]',
  dateInput: 'input[aria-label*="date" i]',
  timeInput: 'input[aria-label*="time" i]',
  confirm: 'button:has-text("Confirm")',
  post: 'button:has-text("Post"), button:has-text("Schedule")',
  viewPost: 'a:has-text("View post")',
};

export default {
  name: 'linkedin',
  async run(ctx) {
    const page = await ctx.newPage();
    await page.goto(SEL.feed, { waitUntil: 'domcontentloaded' });
    await page.locator(SEL.videoButton).first().click({ timeout: 60_000 });
    await page.locator(SEL.fileInput).first().setInputFiles(ctx.post.video, { timeout: 300_000 });
    await page.locator(SEL.next).first().click({ timeout: 300_000 });
    await typeAndVerify(page, page.locator(SEL.editor).first(), ctx.platform.text, { label: 'linkedin text' });

    if (ctx.post.schedule) {
      const s = scheduleParts(ctx.post.schedule);
      await page.locator(SEL.clock).first().click();
      await page.locator(SEL.dateInput).first().fill(s.date.split('-').reverse().join('/'));
      await page.locator(SEL.timeInput).first().fill(s.time12);
      await page.locator(SEL.confirm).first().click();
      await page.waitForTimeout(3000);
    }

    if (ctx.mode === 'dryrun') return stopDryRun(page, ctx, 'linkedin');

    await page.locator(SEL.post).last().click({ timeout: 120_000 });
    await page.waitForTimeout(6000);
    const href = await page.locator(SEL.viewPost).first().getAttribute('href', { timeout: 30_000 }).catch(() => null);
    await page.close().catch(() => {});
    return { ok: true, url: href || null, note: href ? null : 'posted; "View post" link not captured' };
  },
};
