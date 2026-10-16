// Shared Playwright helpers for the browser adapters. Adapters never launch a browser themselves.
import fs from 'node:fs';
import path from 'node:path';
import { normalizeText } from './post.mjs';

export const SELECT_ALL = process.platform === 'darwin' ? 'Meta+A' : 'Control+A';

// Focus the field, replace its content with text, then read it back.
// Throws unless the field reads back as the intended text (whitespace-normalised, NFC).
export async function typeAndVerify(page, locator, text, { label }) {
  await locator.first().click();
  await page.keyboard.press(SELECT_ALL);
  await page.keyboard.press('Backspace');
  await page.keyboard.insertText(text);
  const got = await locator.first().evaluate((el) =>
    el.isContentEditable ? el.innerText : 'value' in el ? el.value : el.textContent,
  );
  if (normalizeText(got) !== normalizeText(text)) {
    throw new Error(`${label}: text read back differs (wanted ${normalizeText(text).length} chars, got ${normalizeText(got).length})`);
  }
}

export async function screenshot(page, runDir, platform, mode) {
  fs.mkdirSync(runDir, { recursive: true });
  const file = path.join(runDir, `${platform}-${mode === 'dryrun' ? 'dryrun' : 'final'}.png`);
  await page.screenshot({ path: file, fullPage: false });
  return file;
}

// Dry-run ends here: screenshot, then discard the draft by closing the tab without saving.
export async function stopDryRun(page, ctx, name) {
  const file = await screenshot(page, ctx.runDir, name, 'dryrun');
  await page.close({ runBeforeUnload: false }).catch(() => {});
  return { ok: true, url: null, note: `dry-run: stopped before the final click; screenshot ${file}` };
}
