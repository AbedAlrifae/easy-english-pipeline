#!/usr/bin/env bash
# Easy English Stories - restore the render pipeline into a fresh Composio sandbox.
# Usage:  bash BOOTSTRAP.sh [github_pat_...]
# Idempotent: safe to re-run after a mid-run sandbox recycle.
set -u
REPO="AbedAlrifae/easy-english-pipeline"
ROOT="/home/user/eng"
TOKFILE="/home/user/.ghtok"

# A token is optional: without one the public raw URL is used.
TOK="${1:-${GH_TOKEN:-}}"
if [ -z "$TOK" ] && [ -f "$TOKFILE" ]; then TOK=$(cat "$TOKFILE"); fi
if [ -n "$TOK" ]; then umask 077; printf '%s' "$TOK" > "$TOKFILE"; fi

mkdir -p "$ROOT/scripts" "$ROOT/ep" "$ROOT/voices"

echo "[1/3] fetching scripts from $REPO"
for f in synth.py render.py level_check.py frame_check.py thumb.py; do
  if [ -n "$TOK" ]; then
    code=$(curl -sL -w '%{http_code}' -o "$ROOT/scripts/$f" \
        -H "Authorization: Bearer $TOK" -H "Accept: application/vnd.github.raw" \
        "https://api.github.com/repos/$REPO/contents/scripts/$f")
  else
    code=$(curl -sL -w '%{http_code}' -o "$ROOT/scripts/$f" \
        "https://raw.githubusercontent.com/$REPO/main/scripts/$f")
  fi
  if [ "$code" != "200" ] || [ ! -s "$ROOT/scripts/$f" ]; then
    echo "FATAL: could not fetch $f (HTTP $code)."
    echo "If the repo is private, pass a token: bash BOOTSTRAP.sh github_pat_..."
    exit 1
  fi
  echo "      scripts/$f  $(wc -c < "$ROOT/scripts/$f") bytes"
done

echo "[2/3] python packages + voice models (parallel)"
( python3 -c "import piper, wordfreq, PIL, kokoro_onnx" 2>/dev/null \
    || pip3 install --quiet piper-tts wordfreq pillow kokoro-onnx soundfile ) > /tmp/pip.log 2>&1 &
PIP=$!

# Kokoro fp16 - the natural-sounding engine. fp32 does NOT fit: the sandbox has
# under 1 GB of RAM and gets OOM-killed. Run synth.py with --chunk 20.
mkdir -p "$ROOT/kokoro"
KURL="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
( [ -s "$ROOT/kokoro/k_fp16.onnx" ]   || curl -sL -o "$ROOT/kokoro/k_fp16.onnx"   "$KURL/kokoro-v1.0.fp16.onnx" ) &
K1=$!
( [ -s "$ROOT/kokoro/voices-v1.0.bin" ] || curl -sL -o "$ROOT/kokoro/voices-v1.0.bin" "$KURL/voices-v1.0.bin" ) &
K2=$!

HF="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US"
fetch_voice() {  # $1=local stem  $2=hf subpath  $3=hf filename stem
  if [ ! -s "$ROOT/voices/$1.onnx" ]; then
    curl -sL -o "$ROOT/voices/$1.onnx"      "$HF/$2/$3.onnx"
    curl -sL -o "$ROOT/voices/$1.onnx.json" "$HF/$2/$3.onnx.json"
  fi
}
fetch_voice en-us-amy-low  amy/low   en_US-amy-low  &
A=$!
fetch_voice en-us-ryan-high ryan/high en_US-ryan-high &
R=$!
wait $PIP $A $R $K1 $K2

echo "[3/3] verifying"
python3 -c "import piper, wordfreq, PIL, kokoro_onnx" 2>/dev/null || { echo "FATAL: python packages missing"; tail -5 /tmp/pip.log; exit 1; }
ksz=$(wc -c < "$ROOT/kokoro/k_fp16.onnx" 2>/dev/null || echo 0)
if [ "$ksz" -lt 100000000 ]; then echo "FATAL: kokoro fp16 model missing or truncated ($ksz bytes)"; exit 1; fi
echo "      kokoro/k_fp16.onnx  $ksz bytes"
for v in en-us-amy-low en-us-ryan-high; do
  sz=$(wc -c < "$ROOT/voices/$v.onnx" 2>/dev/null || echo 0)
  if [ "$sz" -lt 1000000 ]; then echo "FATAL: voice $v missing or truncated ($sz bytes)"; exit 1; fi
  echo "      voices/$v.onnx  $sz bytes"
done
python3 "$ROOT/scripts/level_check.py" --help > /dev/null || { echo "FATAL: level_check.py broken"; exit 1; }
python3 "$ROOT/scripts/synth.py"       --help > /dev/null || { echo "FATAL: synth.py broken"; exit 1; }
python3 "$ROOT/scripts/render.py"      --help > /dev/null || { echo "FATAL: render.py broken"; exit 1; }
python3 "$ROOT/scripts/thumb.py"       --help > /dev/null || { echo "FATAL: thumb.py broken"; exit 1; }

echo "PIPELINE READY"
