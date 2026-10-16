# reel-publish

Publish one finished vertical MP4 to YouTube Shorts, TikTok, Facebook Page (Mbardouni.dev), Facebook profile,
LinkedIn profile and Google Drive, then update mbardouni.dev. Replaces the manual steps in
`tools/file-drop/PUBLISH.md` (kept as the manual fallback).

    reel-publish login                      # once: sign in by hand in the shared Chrome profile
    reel-publish post.json                  # print the plan, post nothing
    reel-publish post.json --dry-run        # drive browsers to the last click, screenshot, leave drafts
    reel-publish post.json --only youtube,tiktok --yes

## post.json

See `post.example.json`. `video` is absolute or relative to the post.json directory. `schedule` is ISO UTC or null.
Only platforms present under `platforms` run. Limits: YouTube title <= 100 chars, TikTok caption <= 2200.

## Behaviour

- Without `--yes` the CLI prints the plan and exits 0. Nothing is contacted.
- `--dry-run` never writes results.json. YouTube runs `yt_publish.cjs --check` on MyContabo only.
- Platforms run one at a time. A failure is recorded and the rest continue. Exit 1 if any failed.
- `results.json` sits next to post.json as `{platform: {ok, url, error, at}}`. An ok platform is never run again.
- Run log: `~/.reel-publish/runs/<slug>/run.log`. Screenshots: `~/.reel-publish/runs/<slug>/<platform>-dryrun.png`.
- YouTube upload runs on MyContabo (`server/yt_publish.cjs`) with Tokyo's stored refresh token. It keeps
  `/root/media-uploads/reel-publish/<slug>/result.json`, so a retry cannot upload twice.
- Portfolio runs last: prepends the TikTok id to `social-videos.json` and runs the YouTube sync.

## Caveats

- Browser selectors come from PUBLISH.md and have not been exercised against live sites. The first real run
  needs the owner present. Selectors live in one const object at the top of each adapter.
- Facebook profile and Drive post immediately (no scheduler in those flows). Facebook Page does too, until its
  scheduler is verified.
- The YouTube stored token currently carries only `youtube.upload`. `--check` needs `youtube.readonly` as well.

## Tests

    npm ci
    npm test
