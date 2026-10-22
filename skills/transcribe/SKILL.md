---
name: transcribe
description: Download and transcribe audio/video from YouTube (or ~1800 other sites) and from local files, using yt-dlp + whisper.cpp — fully local, no API key, no upload. Also covers the full yt-dlp download surface (formats, playlists, sections, subtitles, thumbnails, metadata, private/age-gated media). Use on "transcribe this video", "get the transcript", "subtitle this", "what does this video say", "download this video/audio", "rip the audio", "grab this playlist", "extract subtitles", "convert this talk to text", "summarize this YouTube video" (transcribe first, then summarize). Handles 1h+ media natively.
---

# transcribe

Turn any video or audio — a URL or a file on disk — into text, locally.

Two tools do the work:

| Tool | Role |
|---|---|
| `yt-dlp` | fetches media from YouTube + ~1800 sites; also extracts existing captions |
| `whisper.cpp` (`whisper-cli`) | speech-to-text on Apple Silicon via Metal; used only when no captions exist |

`yt-transcribe` (in `~/.local/bin/`) wires them together and is the **default entry point**. Reach for raw `yt-dlp` only for download-shaped tasks (see [references/yt-dlp.md](references/yt-dlp.md)).

`yt-transcribe` is a separately provisioned helper, not shipped with this repo. If `command -v yt-transcribe` finds nothing, fall back to the manual pipeline: fetch captions with `yt-dlp --skip-download --write-auto-subs --sub-langs <lang> -- <url>`; if none exist, download the audio with `yt-dlp -x --audio-format wav -o audio.wav -- <url>`, convert it to what whisper.cpp expects (16 kHz, mono, 16-bit PCM) and pass the model as a **file path**:

```bash
ffmpeg -i audio.wav -ar 16000 -ac 1 -c:a pcm_s16le audio-16k.wav
whisper-cli -m ~/.cache/whisper.cpp/ggml-large-v3-turbo.bin -l auto -f audio-16k.wav -otxt -osrt
```

`-m` takes a path to a `.bin` file, not a model name.

## The one rule that matters: captions before ASR

**Always let the captions fast path run first.** Most YouTube videos already have captions (including auto-generated ones). Pulling them takes ~30 seconds and zero compute. Running whisper on the same video takes minutes.

`yt-transcribe` does this automatically. Only pass `--force-asr` when the user explicitly wants a fresh transcription — e.g. the auto-captions are visibly garbage, or they need accurate timestamps for a language YouTube mis-detected.

Measured on a 20-minute talk (M4, `large-v3-turbo`): **captions 31 s · full ASR 117 s**. On a 1-hour video the gap is ~1 min vs ~6 min.

## Usage

```bash
yt-transcribe <url|file> [options]
```

Both a URL and a local path go in the same argument slot — the script detects which.

```bash
# YouTube — captions if they exist, else whisper
yt-transcribe "https://www.youtube.com/watch?v=VIDEO_ID"

# Local file (any format ffmpeg reads: mp4, mp3, m4a, aiff, wav, mkv, voice notes…)
yt-transcribe ~/Downloads/meeting.m4a

# Force a real transcription, ignore the platform's captions
yt-transcribe "<url>" --force-asr

# Non-English — see the language note below
yt-transcribe "<url>" --lang ar
yt-transcribe "<url>" --lang fr --translate     # French speech → English text

# Only part of a long video
yt-transcribe "<url>" --section "*00:10:00-00:20:00"

# Private / age-gated / members-only
yt-transcribe "<url>" --cookies-browser chrome
```

### Options

| Flag | Effect |
|---|---|
| `-l, --lang LANG` | spoken language or `auto` (**default `auto`**) |
| `--force-asr` | skip captions, always run whisper |
| `--translate` | translate speech to English |
| `-f, --formats LIST` | `srt,txt,md,vtt,json,csv,lrc` (default `srt,txt,md`) |
| `-m, --model NAME` | whisper model (default `ggml-large-v3-turbo`) |
| `-o, --outdir DIR` | output dir (default `./transcripts`) |
| `-n, --name SLUG` | override output basename |
| `--prompt TEXT` | seed names/jargon so whisper spells them correctly |
| `--section RANGE` | e.g. `*00:10:00-00:20:00` |
| `--cookies-browser B` | `chrome`, `safari`, `firefox`… for private media |
| `--playlist` | process every entry instead of just one |
| `--keep-audio` / `--keep-subs` | keep intermediates |
| `-t, --threads N` | whisper threads (default: all cores) |
| `--whisper-arg` / `--ytdlp-arg` | raw passthrough (repeatable) |

Outputs land at `<outdir>/<slug>.{srt,txt,md,…}`. The `.wav` is deleted unless `--keep-audio`.

## Language — the trap

**whisper.cpp defaults to `en`.** Given Arabic or French audio with no language set, it does not detect and adapt — it force-decodes as English and returns confident nonsense.

`yt-transcribe` therefore defaults to `--lang auto`. Two consequences worth knowing:

- If you *know* the language, **pass it** (`--lang ar`). It is more reliable than auto-detect, which samples only the first ~30 s and can be misled by a music intro or an English greeting.
- `--translate` always outputs English, whatever the source.

## Choosing a model

Installed: `ggml-large-v3-turbo` (1.6 GB) at `~/.cache/whisper.cpp/`. It is the right default — near-large accuracy, several times faster.

Drop to a smaller model only when speed matters more than accuracy on a long, clean recording:

```bash
curl -fL --create-dirs -o ~/.cache/whisper.cpp/ggml-base.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin
# verify before use; delete the file if this does not print OK
echo "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe  $HOME/.cache/whisper.cpp/ggml-base.bin" | shasum -a 256 -c
yt-transcribe <input> --model ggml-base
```

SHA-256 of the other models in the same repo (the LFS object id on Hugging Face, checked 2026-10-22):
`ggml-small.bin` `1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b`,
`ggml-large-v3-turbo.bin` `1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69`.
For any other model, compare against the `sha256` shown on its Hugging Face file page.

`tiny` < `base` < `small` < `medium` < `large-v3-turbo` < `large-v3`. Append `.en` (e.g. `ggml-small.en`) for English-only variants — slightly better on English, useless for anything else.

## Long media

whisper.cpp streams audio in chunks — a 1h+ file needs no splitting. Just expect wall-clock time and run it in the background rather than blocking a conversation. Rough guide on an M4 with `large-v3-turbo`: **~1 min of compute per 10 min of audio**.

For a first pass on something long, `--section` a representative slice before committing to the whole thing.

## Downloading without transcribing

For "download this video", "rip the audio", "grab the playlist", "get the thumbnail" — call `yt-dlp` directly. The full cookbook is in [references/yt-dlp.md](references/yt-dlp.md): format selection, quality caps, playlists, sections, subtitles, metadata/JSON, chapters, thumbnails, cookies, archives, rate limits, SponsorBlock.

## Feeding transcripts into other work

A transcript is usually a means, not the end. When the user wants a *summary* of a video, transcribe first, then work from the `.md`.

If the material is worth keeping, drop the `.md` into `ai-knowledge-base/raw/` and run `/kb-ingest` — that is how the transcript becomes queryable prior art instead of a stray file. Long transcripts are also good `/opencode` work (summarization is exactly its lane), which keeps the main context free.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `model not found` | the `curl` line in the error message downloads it |
| `could not read video info` | private/geo-blocked → `--cookies-browser chrome` |
| Output is English gibberish | wrong language decode → pass `--lang` explicitly |
| Names/jargon misspelled | `--prompt "<speaker names>, <product names>, <jargon>"`, e.g. `--prompt "Kubernetes, PostgreSQL, whisper.cpp"` |
| Captions exist but are poor | `--force-asr` |
| `whisper-cli not found` | `brew install whisper-cpp` |
| Sped-up / distorted audio | stale download — delete the `.wav` and retry |

## Requirements

`yt-dlp` (`~/.local/bin/`), `whisper-cli` (`brew install whisper-cpp`), `ffmpeg`, and one model in `~/.cache/whisper.cpp/`. Everything runs on-device: no API key, no upload, no per-minute cost.
