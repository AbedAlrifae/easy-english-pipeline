#!/usr/bin/env bash
# Easy English Stories - set up the render pipeline in a LOCAL folder.
#
#   bash BOOTSTRAP_LOCAL.sh [target_folder]
#
# Default target: ./easy-english. Works on macOS and Linux. Idempotent.
# Unlike the Composio sandbox this machine has real RAM, so it installs the
# FULL-PRECISION Kokoro model and synth.py runs without --chunk.
set -eu
REPO="AbedAlrifae/easy-english-pipeline"
ROOT="${1:-$PWD/easy-english}"
RAW="https://raw.githubusercontent.com/$REPO/main"
KURL="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

mkdir -p "$ROOT"/{scripts,ep,voices,kokoro,fonts}
cd "$ROOT"

echo "[1/5] ffmpeg"
if ! command -v ffmpeg > /dev/null; then
  echo "  ffmpeg is missing. Install it first:"
  echo "    macOS:  brew install ffmpeg"
  echo "    Debian: sudo apt-get install -y ffmpeg"
  exit 1
fi
echo "      $(ffmpeg -version | head -1 | cut -c1-40)"

echo "[2/5] scripts"
for f in synth.py render.py level_check.py frame_check.py thumb.py; do
  curl -fsSL -o "scripts/$f" "$RAW/scripts/$f"
  echo "      scripts/$f  $(wc -c < "scripts/$f" | tr -d ' ') bytes"
done

echo "[3/5] python venv + packages"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/python -c "import piper, wordfreq, PIL, kokoro_onnx" 2>/dev/null \
  || ./.venv/bin/pip install -q piper-tts wordfreq pillow kokoro-onnx soundfile numpy

echo "[4/5] models + fonts"
# Full fp32 Kokoro: better quality, needs ~1.5 GB RAM. fp16 also fetched as a fallback.
[ -s kokoro/kokoro-v1.0.onnx ] || curl -fsSL -o kokoro/kokoro-v1.0.onnx "$KURL/kokoro-v1.0.onnx"
[ -s kokoro/k_fp16.onnx ]      || curl -fsSL -o kokoro/k_fp16.onnx      "$KURL/kokoro-v1.0.fp16.onnx"
[ -s kokoro/voices-v1.0.bin ]  || curl -fsSL -o kokoro/voices-v1.0.bin  "$KURL/voices-v1.0.bin"
# DejaVu, so render.py and thumb.py look identical on every OS
DJ="https://github.com/dejavu-fonts/dejavu-fonts/raw/master/build/dejavu-fonts-ttf-2.37/ttf"
[ -s fonts/DejaVuSans-Bold.ttf ] || curl -fsSL -o fonts/DejaVuSans-Bold.ttf "$DJ/DejaVuSans-Bold.ttf"
[ -s fonts/DejaVuSans.ttf ]      || curl -fsSL -o fonts/DejaVuSans.ttf      "$DJ/DejaVuSans.ttf"
# Piper voices, only needed for the --engine piper fallback
HF="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US"
[ -s voices/en-us-ryan-high.onnx ] || {
  curl -fsSL -o voices/en-us-ryan-high.onnx      "$HF/ryan/high/en_US-ryan-high.onnx"
  curl -fsSL -o voices/en-us-ryan-high.onnx.json "$HF/ryan/high/en_US-ryan-high.onnx.json"; }

echo "[5/5] verifying"
export EES_FONT_DIR="$ROOT/fonts"
for s in level_check synth render thumb; do
  ./.venv/bin/python "scripts/$s.py" --help > /dev/null || { echo "FATAL: $s.py broken"; exit 1; }
done
ksz=$(wc -c < kokoro/kokoro-v1.0.onnx | tr -d ' ')
[ "$ksz" -gt 300000000 ] || { echo "FATAL: kokoro model truncated ($ksz)"; exit 1; }
echo "      kokoro/kokoro-v1.0.onnx  $ksz bytes"

cat > run.sh <<'RUN'
#!/usr/bin/env bash
# Build one episode. Edit ep/script.md first, then: bash run.sh
set -eu
cd "$(dirname "$0")"
export EES_FONT_DIR="$PWD/fonts"
PY=./.venv/bin/python
LEVEL="${LEVEL:-A2}"
if [ "$LEVEL" = "A2" ]; then
  ZIPF=4.3; MAXW=12; SPEED=0.78; PAUSE=0.40; BG="#1a2332"; ACC="#f5b942"
  SERIES="Easy Stories"; LBL="A2  .  Elementary"
else
  ZIPF=3.8; MAXW=18; SPEED=0.82; PAUSE=0.45; BG="#12141c"; ACC="#7ec8e3"
  SERIES="Mystery Nights"; LBL="B1  .  Intermediate"
fi
TITLE="${TITLE:?set TITLE=\"The Episode Title\"}"
KICKER="${KICKER:-}"

$PY scripts/level_check.py ep/script.md --min-zipf $ZIPF --max-words $MAXW --names "${NAMES:-}"
$PY scripts/synth.py ep/script.md --engine kokoro --kokoro-model kokoro-v1.0.onnx \
    --voice-a af_heart --voice-b am_michael --speed $SPEED --pause $PAUSE \
    --label-a Maya --label-b Tom --outdir ep
$PY -c "import json;print('duration',json.load(open('ep/audio_meta.json'))['duration_sec'])"
$PY scripts/render.py --audio ep/narration.wav --srt ep/subtitles.srt --out ep/video.mp4 \
    --series-title "$SERIES" --episode-title "$TITLE" --level "$LBL" \
    --bg "$BG" --accent "$ACC" --preset veryfast
$PY scripts/thumb.py --out ep/thumb.png --title "$TITLE" --series "$SERIES" \
    --level "$LEVEL" --kicker "$KICKER" --bg "$BG" --accent "$ACC"
$PY scripts/frame_check.py ep/video.mp4 35 200 420 600
echo "DONE -> ep/video.mp4  ep/thumb.png"
RUN
chmod +x run.sh

echo
echo "PIPELINE READY (local)  ->  $ROOT"
echo "  write ep/script.md, then:  TITLE=\"My Title\" KICKER=\"home cafe\" LEVEL=A2 bash run.sh"
