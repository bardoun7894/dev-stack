// Runs on MyContabo. Uploads one reel to YouTube with Tokyo's stored OAuth refresh token.
//   node yt_publish.cjs --check        refresh token, confirm the upload scope, no upload
//   node yt_publish.cjs <slug>         upload /root/media-uploads/reel-publish/<slug>/video.mp4 with meta.json
// Idempotent: if <slug>/result.json exists the upload is not repeated.
const fs = require("fs");
const path = require("path");
const { createRequire } = require("module");

const TOKYO = "/root/tokyo";
const tokyo = createRequire(path.join(TOKYO, "package.json"));
tokyo("dotenv").config({ path: path.join(TOKYO, ".env") });
const Database = tokyo("better-sqlite3");

const ROOT = "/root/media-uploads/reel-publish";
const CHUNK = 8 * 1024 * 1024;

async function token() {
  const db = new Database(path.join(TOKYO, "life.db"), { readonly: true });
  const row = db.prepare("select refresh_token from social_accounts where platform='youtube'").get();
  db.close();
  if (!row || !row.refresh_token) throw new Error("no youtube refresh token in life.db");
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    body: new URLSearchParams({
      client_id: process.env.YOUTUBE_CLIENT_ID,
      client_secret: process.env.YOUTUBE_CLIENT_SECRET,
      refresh_token: row.refresh_token,
      grant_type: "refresh_token",
    }),
  });
  const j = await res.json();
  if (!j.access_token) throw new Error("token refresh failed: " + JSON.stringify(j).slice(0, 300));
  return j.access_token;
}

async function check() {
  // The stored token is upload-only (youtube.upload), so channels.list?mine=true answers 403.
  // tokeninfo proves the refresh works and that the scope covers uploads.
  const tok = await token();
  const r = await fetch(`https://oauth2.googleapis.com/tokeninfo?access_token=${encodeURIComponent(tok)}`);
  const j = await r.json();
  if (!r.ok) throw new Error(`tokeninfo ${r.status}: ${JSON.stringify(j).slice(0, 300)}`);
  const scopes = String(j.scope || "").split(" ");
  if (!scopes.some((s) => /auth\/youtube(\.upload|\.force-ssl)?$/.test(s))) throw new Error(`token lacks an upload scope: ${j.scope}`);
  console.log(JSON.stringify({ ok: true, scope: j.scope, expires_in: Number(j.expires_in) }));
}

async function upload(slug) {
  const dir = path.join(ROOT, slug);
  const resultFile = path.join(dir, "result.json");
  if (fs.existsSync(resultFile)) {
    console.log(fs.readFileSync(resultFile, "utf8").trim());
    return;
  }
  const m = JSON.parse(fs.readFileSync(path.join(dir, "meta.json"), "utf8"));
  const file = path.join(dir, "video.mp4");
  const total = fs.statSync(file).size;
  const tok = await token();
  const meta = {
    snippet: {
      title: m.title,
      description: m.description,
      tags: m.tags || [],
      categoryId: "28",
      defaultLanguage: "ar",
      defaultAudioLanguage: "ar",
    },
    status: {
      privacyStatus: m.publishAt ? "private" : "public",
      selfDeclaredMadeForKids: false,
      ...(m.publishAt ? { publishAt: m.publishAt } : {}),
    },
  };
  const init = await fetch("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${tok}`,
      "Content-Type": "application/json; charset=UTF-8",
      "X-Upload-Content-Type": "video/mp4",
      "X-Upload-Content-Length": String(total),
    },
    body: JSON.stringify(meta),
  });
  if (!init.ok) throw new Error(`init ${init.status}: ${(await init.text()).slice(0, 400)}`);
  const session = init.headers.get("location");
  const fd = fs.openSync(file, "r");
  let offset = 0;
  let final = null;
  try {
    while (offset < total) {
      const size = Math.min(CHUNK, total - offset);
      const buf = Buffer.alloc(size);
      fs.readSync(fd, buf, 0, size, offset);
      const r = await fetch(session, {
        method: "PUT",
        headers: { "Content-Length": String(size), "Content-Range": `bytes ${offset}-${offset + size - 1}/${total}` },
        body: buf,
      });
      if (r.status === 308) {
        offset += size;
        continue;
      }
      if (!r.ok) throw new Error(`chunk ${r.status}: ${(await r.text()).slice(0, 400)}`);
      final = await r.json();
      offset += size;
    }
  } finally {
    fs.closeSync(fd);
  }
  if (!final || !final.id) throw new Error("upload finished without a video id");
  const out = JSON.stringify({ id: final.id, url: `https://youtube.com/shorts/${final.id}`, privacy: final.status && final.status.privacyStatus });
  fs.writeFileSync(resultFile, out + "\n");
  console.log(out);
}

(async () => {
  const arg = process.argv[2];
  if (!arg) throw new Error("usage: yt_publish.cjs --check | <slug>");
  if (arg === "--check") return check();
  if (!/^[a-z0-9-]+$/.test(arg)) throw new Error(`bad slug ${arg}`);
  return upload(arg);
})().catch((e) => {
  console.error("FAILED:", e.message);
  process.exit(1);
});
