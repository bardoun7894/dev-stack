# reel-publish

Publish one finished vertical MP4 to YouTube Shorts, TikTok, Facebook Page (Mbardouni.dev), Facebook profile,
LinkedIn profile and Google Drive, then update mbardouni.dev. Replaces the manual steps in
`tools/file-drop/PUBLISH.md` (kept as the manual fallback).

    reel-publish pair                       # once: write the bridge secret, then reload File Drop Bridge
    reel-publish check-login                # open each site in a bridge tab: signed in / SIGNED OUT (exit 1 if any out)
    reel-publish post.json                  # print the plan, post nothing
    reel-publish post.json --dry-run        # drive browsers to the last click, screenshot, leave drafts
    reel-publish post.json --only youtube,tiktok --yes

## post.json

See `post.example.json`. `video` is absolute or relative to the post.json directory. `schedule` is ISO UTC or null.
Only platforms present under `platforms` run. Limits: YouTube title <= 100 chars, TikTok caption <= 2200.

## How it drives Chrome

reel-publish does not launch a browser. It drives the Chrome you are already signed in to, through the unpacked
extension "File Drop Bridge" (`tools/file-drop/extension/`, v1.1.0, permissions debugger/tabs/alarms) using
`chrome.debugger` (CDP inside the real profile). Chrome 136+ ignores `--remote-debugging-port` on the default
profile and copied cookies came back signed out, so this is the route that keeps your sessions.

- The CLI listens on `ws://127.0.0.1:8798/?k=<secret>`; the extension dials in (alarm every 30 s, browser start,
  or click the extension icon). Secret: `~/.reel-publish/bridge-secret` and `extension/bridge-secret.js` (git-ignored),
  both written by `reel-publish pair`. Reload the extension at chrome://extensions after pairing.
- The bridge only touches tabs it opened itself; any other tab id is refused. If the CLI exits, the extension
  detaches and leaves the tabs open so you can see where it stopped.
- Adapters use `BridgePage` (`lib/bridge.mjs`), a Playwright-shaped subset: goto, locator/getByText
  (first/last/nth, click, waitFor, isVisible, setInputFiles, getAttribute, evaluate, fill), waitForEvent('filechooser'),
  keyboard, screenshot. Selectors: comma-separated alternatives of `text=Foo`, `css:has-text("Foo")` or plain CSS
  (`lib/selector.mjs`). Clicks are real mouse input.
- Uploads hand Chrome the absolute local path over CDP: no size cap, no file-drop server.

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

- Needs Chrome running with File Drop Bridge loaded. Keep the tabs it opens in a normal window.
- Browser selectors come from PUBLISH.md and have not been exercised against live sites. The first real run
  needs the owner present. Selectors live in one const object at the top of each adapter.
- Facebook profile and Drive post immediately (no scheduler in those flows). Facebook Page does too, until its
  scheduler is verified.
- The YouTube stored token currently carries only `youtube.upload`. `--check` needs `youtube.readonly` as well.

## Tests

    npm ci   # one dependency: ws
    npm test
