# yt-dlp cookbook

Reference for **download-shaped** tasks. For transcription use `yt-transcribe` (see SKILL.md).

Binary: `~/.local/bin/yt-dlp`. Works on YouTube plus ~1800 other sites (Vimeo, Twitter/X, TikTok, Instagram, Twitch, SoundCloud, Reddit, direct media URLs…). `yt-dlp --list-extractors` prints them all.

Keep it current — extractors break when sites change:

```bash
yt-dlp -U
```

## Inspect before downloading

```bash
yt-dlp -F "<url>"                    # list available formats
yt-dlp --print "%(title)s" "<url>"   # one field
yt-dlp -j "<url>"                    # full metadata as JSON (no download)
yt-dlp --list-subs "<url>"           # available caption tracks
```

`-j` piped into `jq` is the fastest way to answer "how long is this", "who uploaded it", "how many views".

## Format selection

```bash
yt-dlp "<url>"                                       # best video+audio, merged
yt-dlp -f "bv*[height<=1080]+ba/b[height<=1080]" "<url>"   # cap at 1080p
yt-dlp -f "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]" "<url>"  # mp4-only
yt-dlp -f worst "<url>"                              # smallest
yt-dlp -f 137+140 "<url>"                            # exact IDs from -F
```

Grammar: `bv*` best video (any container), `ba` best audio, `b` best combined, `+` merge, `/` fallback. Filters chain: `[height<=1080][fps<=30][vcodec^=avc1]`.

Force a container regardless of source:

```bash
yt-dlp --merge-output-format mp4 "<url>"
yt-dlp --recode-video mp4 "<url>"      # re-encodes — slow, lossy, last resort
```

## Audio only

```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 "<url>"   # best-quality mp3
yt-dlp -x --audio-format m4a "<url>"                     # usually no re-encode
yt-dlp -f ba "<url>"                                     # native audio, untouched
```

`--audio-quality 0` is best, `9` worst. Prefer `m4a` when the source is YouTube — it avoids a lossy re-encode.

## Output naming

```bash
yt-dlp -o "%(title)s.%(ext)s" "<url>"
yt-dlp -o "%(upload_date>%Y-%m-%d)s - %(title)s.%(ext)s" "<url>"
yt-dlp -o "~/Media/%(uploader)s/%(title)s.%(ext)s" "<url>"
yt-dlp --restrict-filenames "<url>"    # ASCII-only, no spaces — safest for scripts
```

Useful fields: `title`, `id`, `ext`, `uploader`, `channel`, `upload_date`, `duration`, `resolution`, `playlist_index`, `autonumber`.

## Playlists and channels

```bash
yt-dlp "<playlist-url>"                              # whole playlist
yt-dlp --no-playlist "<url>"                         # just this video
yt-dlp --playlist-items 1-5,8,10- "<playlist-url>"   # a subset
yt-dlp --flat-playlist -j "<playlist-url>"           # enumerate without downloading
yt-dlp -o "%(playlist_index)03d - %(title)s.%(ext)s" "<playlist-url>"

# whole channel
yt-dlp "https://www.youtube.com/@handle/videos"
```

Filter what gets pulled:

```bash
yt-dlp --match-filter "duration > 300 & view_count > 1000" "<url>"
yt-dlp --dateafter 20260101 "<url>"
yt-dlp --break-on-existing --download-archive archive.txt "<channel-url>"
```

`--download-archive` records completed IDs, so re-running only fetches what is new — the right way to follow a channel.

## Partial downloads

```bash
yt-dlp --download-sections "*00:10:00-00:20:00" --force-keyframes-at-cuts "<url>"
yt-dlp --download-sections "*intro"   # by chapter name (regex)
```

Without `--force-keyframes-at-cuts` the cut lands on the nearest keyframe and drifts by seconds.

## Subtitles

```bash
yt-dlp --list-subs "<url>"
yt-dlp --write-subs --sub-langs en --sub-format srt --skip-download "<url>"
yt-dlp --write-auto-subs --sub-langs "en.*,en" --skip-download "<url>"   # auto-generated
yt-dlp --write-subs --sub-langs all --skip-download "<url>"
yt-dlp --embed-subs "<url>"                                             # burn into container
```

`--skip-download` is what makes this instant. Note auto-subs arrive as rolling VTT with each line repeated — deduplicate before treating it as prose (`yt-transcribe` already does).

## Metadata, thumbnails, chapters

```bash
yt-dlp --write-info-json --skip-download "<url>"
yt-dlp --write-thumbnail --convert-thumbnails jpg --skip-download "<url>"
yt-dlp --write-description --skip-download "<url>"
yt-dlp --embed-metadata --embed-thumbnail --embed-chapters "<url>"
yt-dlp --split-chapters "<url>"        # one file per chapter
```

## Private, age-gated, login-required

```bash
yt-dlp --cookies-from-browser chrome "<url>"
yt-dlp --cookies-from-browser "firefox:profile_name" "<url>"
yt-dlp --cookies cookies.txt "<url>"
```

`--cookies-from-browser` reads the live browser profile — close the browser first if it holds a lock. Safari needs Full Disk Access for the terminal.

## Network

```bash
yt-dlp --limit-rate 2M "<url>"
yt-dlp --retries 10 --fragment-retries 10 "<url>"
yt-dlp --concurrent-fragments 4 "<url>"      # faster on fragmented streams
yt-dlp --proxy "socks5://127.0.0.1:1080" "<url>"
yt-dlp --sleep-interval 5 --max-sleep-interval 15 "<url>"   # be polite on bulk jobs
```

Add `--sleep-interval` on any channel-wide sweep. Hammering earns a rate-limit.

## SponsorBlock

```bash
yt-dlp --sponsorblock-remove sponsor,selfpromo,interaction "<url>"
yt-dlp --sponsorblock-mark all "<url>"    # chapter markers instead of cuts
```

## Live streams

```bash
yt-dlp --live-from-start "<live-url>"
yt-dlp --wait-for-video 60 "<scheduled-url>"
```

## Recipes

```bash
# Archive a channel as audio, incrementally, resumable
yt-dlp -x --audio-format m4a \
  --download-archive ~/Media/archive.txt \
  -o "~/Media/%(uploader)s/%(upload_date>%Y-%m-%d)s - %(title)s.%(ext)s" \
  --sleep-interval 5 \
  "https://www.youtube.com/@handle/videos"

# Everything about one video, no media
yt-dlp --skip-download --write-info-json --write-thumbnail \
  --write-subs --write-auto-subs --sub-langs "en.*,en" "<url>"

# 1080p mp4 with metadata, thumbnail and chapters embedded
yt-dlp -f "bv*[height<=1080]+ba/b[height<=1080]" --merge-output-format mp4 \
  --embed-metadata --embed-thumbnail --embed-chapters "<url>"
```

## Gotchas

| Symptom | Fix |
|---|---|
| `Unsupported URL` / extractor errors | `yt-dlp -U` — the site changed |
| `Sign in to confirm you're not a bot` | `--cookies-from-browser chrome` |
| Merged file has no audio | ffmpeg missing → `brew install ffmpeg` |
| Playlist pulled when one video wanted | `--no-playlist` |
| Filenames break scripts | `--restrict-filenames` |
| Download stalls near the end | `--concurrent-fragments 1 --retries 10` |
| Section cut is off by seconds | add `--force-keyframes-at-cuts` |
