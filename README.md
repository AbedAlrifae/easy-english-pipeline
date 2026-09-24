# Easy English Stories - render pipeline

Durable master copy of the pipeline. The Composio sandbox and its `/mnt/files`
s3fs volume are both wiped regularly, so nothing may be assumed to survive there.
Every run restores itself from this repo.

## Restore (first command of every run)

```bash
export GH=github_pat_xxx
curl -sL -H "Authorization: Bearer $GH" -H "Accept: application/vnd.github.raw" \
  -o /tmp/B.sh https://api.github.com/repos/AbedAlrifae/easy-english-pipeline/contents/BOOTSTRAP.sh \
  && bash /tmp/B.sh "$GH"
```

Prints `PIPELINE READY`. Takes ~4s warm, ~110s in a brand-new sandbox (pip install).
Idempotent - if a later call fails with "No such file or directory" under
`/home/user/eng`, the sandbox was recycled mid-run: run it again and continue.

## Scripts

| file | purpose |
|---|---|
| `scripts/level_check.py` | vocabulary + sentence-length gate (wordfreq zipf) |
| `scripts/synth.py` | Piper narration -> `narration.wav`, `subtitles.srt`, `audio_meta.json` |
| `scripts/render.py` | title card + burned-in subtitles -> 1080p `video.mp4` |
| `scripts/frame_check.py` | samples frames, reports subtitle band rows |

`render.py` builds its title card from `--bg` / `--accent` with PIL. There is no
`bg1080.png` asset any more - one less thing that can go missing.

## Slot settings

| | easy-stories (09 UTC) | mystery-nights (16 UTC) |
|---|---|---|
| level | A2 | B1 |
| model | en-us-amy-low.onnx | en-us-ryan-high.onnx |
| length-scale | 1.55 | 1.45 |
| pause | 0.85 | 0.6 |
| min-zipf | 4.3 | 3.8 |
| max-words | 12 | 18 |
| target words | 930-960 | 1150-1250 |
| bg / accent | `#1a2332` / `#f5b942` | `#12141c` / `#7ec8e3` |
| label | `A2  .  Elementary` | `B1  .  Intermediate` |

## Do not reintroduce these bugs

- **Explicit `-t <audio duration>` from ffprobe.** `-shortest` with `-loop 1` on a
  still image produces a 48-byte file and exits non-zero.
- **SRT is converted to `.ass` with `PlayResX 1920 / PlayResY 1080`.** Passing the
  `.srt` straight to the `subtitles` filter makes libass assume a 384x288 script:
  the subtitles come out oversized and ~360px too high. Invisible in ffprobe,
  reaches YouTube looking broken.
- **Output must be 48 kHz stereo AAC and High profile.** 16 kHz mono / Baseline is
  what YouTube choked on.
- Nothing bright is drawn below row 600 of the title card, so `frame_check.py`
  can tell subtitles apart from the design. Subtitles land on rows ~870-995.

## Upload

`YOUTUBE_UPLOAD_VIDEO` creates the record but the bytes never arrive
("Processing abandoned"). Use **`YOUTUBE_MULTIPART_UPLOAD_VIDEO`**, field
`videoFile` (not `videoFilePath`), always `privacyStatus: private` first, confirm
`uploadStatus == "processed"`, then publish.

Channel: `UCDv-d97vGkYE5VgjK2bomPg`
