# easy-english-pipeline

Durable master copy of the Easy English Stories render pipeline. The Composio
sandbox is wiped often, so everything needed to rebuild it lives here.

    curl -sL -o /tmp/B.sh https://raw.githubusercontent.com/AbedAlrifae/easy-english-pipeline/main/BOOTSTRAP.sh && bash /tmp/B.sh

Prints `PIPELINE READY`. Idempotent. Never store anything in /mnt/files.

## Scripts

| file | what it does |
|---|---|
| `synth.py` | narration + SRT + audio_meta.json. Piper or Kokoro, one or two speakers |
| `render.py` | 1080p / 24fps / CRF21 / High profile / 48kHz stereo video with burned-in subs |
| `thumb.py` | 1280x720 PNG thumbnail from title + level + trend phrase |
| `level_check.py` | CEFR gate: min zipf frequency and max sentence length |
| `frame_check.py` | samples frames and reports where the subtitle band landed |

## TTS engines

**Kokoro (default, natural)** - `--engine kokoro`, voices `af_heart` (female)
and `am_michael` (male). Markedly less robotic than Piper.

> The sandbox has under 1 GB of RAM. The fp32 Kokoro model gets OOM-killed
> (rc=-9) partway through an episode. Use the **fp16** model, which bootstrap
> installs as `kokoro/k_fp16.onnx`, and **always pass `--chunk 20`** so each
> block of sentences runs in its own process. Peak RSS is then about 510 MB.

**Piper (fallback)** - `--engine piper --model <voice>.onnx`, optional
`--model-b` for a second speaker. Lower quality, much lighter.

## Two-speaker podcast format

Lines in the script may start with `A:` or `B:`. `--label-a` / `--label-b`
put the host name on the first subtitle cue of each turn.

    A: Hello, and welcome to Easy English Stories.

    B: And I am Tom. Hello, everybody.

## Prosody

Pause length is not constant - that was the biggest "this is AI" tell. The gap
after each sentence is the `--pause` base, multiplied by 1.18 after `?`/`!`,
1.9 at a paragraph break and 0.75 on a speaker change, then jittered +/-18%.
Each sentence also gets +/-3% speed jitter. A low room-tone bed and a soft
limiter run over the finished track so the silences are not digitally dead.

## Measured settings

| slot | level | engine | voices | speed / length-scale | pause | zipf | max words |
|---|---|---|---|---|---|---|---|
| 09 UTC | A2 | kokoro | af_heart + am_michael | `--speed 0.78` | `0.40` | 4.3 | 12 |
| 16 UTC | B1 | kokoro | af_heart + am_michael | `--speed 0.82` | `0.45` | 3.8 | 18 |

Measured word counts, target 600-660s:

- **A2 podcast, two speakers, kokoro speed 0.78 / pause 0.40**: 1518 words /
  224 sentences -> **657.6s**. About 0.43 s/word including pauses.
- **B1 solo, piper ryan-high, length-scale 1.45 / pause 0.6**: 1640 words /
  157 sentences -> 630.8s. About 0.385 s/word.

Never change speed or pause to fix length - those set how the narration lands
for learners. Change the word count.

## YouTube notes

- Upload with `YOUTUBE_MULTIPART_UPLOAD_VIDEO`. `YOUTUBE_UPLOAD_VIDEO` creates
  the record but the bytes never arrive ("Processing abandoned").
- `YOUTUBE_UPDATE_THUMBNAIL` takes a **public URL**, not a file. Upload the PNG
  with the workbench `upload_local_file` and pass the returned s3 URL.
- Playlists: `Easy Stories - Level A2` = `PLKgDjxlpklzo`,
  `Mystery Nights - Level B1` = `PLBeLbL9FFMV0`.
- **No caption-upload tool exists** in this Composio YouTube toolkit - only
  list and download. Subtitles are burned into the picture.
- Always upload private, confirm `uploadStatus: processed`, then go public.
