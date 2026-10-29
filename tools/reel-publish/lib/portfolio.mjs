// Pure helpers for mbardouni.dev's social-videos.json (the TikTok list on /ar/videos).
const TIKTOK_ID_RE = /\/video\/(\d+)/;

export function tiktokIdFromUrl(url) {
  if (typeof url !== 'string') return null;
  const m = url.match(TIKTOK_ID_RE);
  return m ? m[1] : null;
}

// Prepends {url, title} to doc.tiktok unless the same video id is already listed.
// Returns a new object; keeps every other key (_note, instagram) as they were.
export function addTiktokEntry(doc, { url, title }) {
  const id = tiktokIdFromUrl(url);
  if (!id) throw new Error(`not a TikTok video url: ${url}`);
  const list = Array.isArray(doc.tiktok) ? doc.tiktok : [];
  if (list.some((e) => tiktokIdFromUrl(e.url) === id)) {
    return { doc: { ...doc, tiktok: list }, added: false };
  }
  return { doc: { ...doc, tiktok: [{ url, title }, ...list] }, added: true };
}

export function serializeSocialVideos(doc) {
  return JSON.stringify(doc, null, 2) + '\n';
}
