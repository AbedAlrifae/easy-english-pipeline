#!/usr/bin/env python3
"""Narrate a story script with Piper, one cue per sentence, and emit WAV + SRT + meta."""
import argparse, json, os, re, sys, textwrap, wave
import numpy as np
from piper import PiperVoice, SynthesisConfig

WRAP = 42
MAXLINES = 2

def split_sentences(text):
    text = re.sub(r'^#.*$', '', text, flags=re.M)
    text = text.replace('"', '').replace('“', '').replace('”', '')
    text = re.sub(r'\s+', ' ', text).strip()
    return [p.strip() for p in re.split(r'(?<=[.!?])\s+', text) if p.strip()]

def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def wrap_cue(s):
    lines = textwrap.wrap(s, WRAP)
    if len(lines) <= MAXLINES:
        return '\n'.join(lines)
    # rebalance into MAXLINES roughly equal lines
    words, out, per = s.split(), [], max(1, len(s) // MAXLINES)
    cur = ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > per and len(out) < MAXLINES - 1:
            out.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    out.append(cur)
    return '\n'.join(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('script')
    ap.add_argument('--model', required=True)
    ap.add_argument('--length-scale', type=float, required=True)
    ap.add_argument('--pause', type=float, required=True)
    ap.add_argument('--outdir', required=True)
    a = ap.parse_args()

    model = a.model
    if not os.path.exists(model):
        model = os.path.join('voices', os.path.basename(a.model))
    if not os.path.exists(model):
        sys.exit(f"model not found: {a.model}")

    sents = split_sentences(open(a.script, encoding='utf-8').read())
    print(f"sentences: {len(sents)}", flush=True)

    voice = PiperVoice.load(model)
    sr = voice.config.sample_rate
    cfg = SynthesisConfig(length_scale=a.length_scale, normalize_audio=True)
    gap = np.zeros(int(sr * a.pause), dtype=np.int16)
    lead = np.zeros(int(sr * 0.6), dtype=np.int16)

    pieces, cues = [lead], []
    cursor = len(lead) / sr
    for i, s in enumerate(sents, 1):
        chunks = [c.audio_int16_array for c in voice.synthesize(s, cfg)]
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
        dur = len(audio) / sr
        cues.append((cursor, cursor + dur, wrap_cue(s)))
        pieces.append(audio)
        pieces.append(gap)
        cursor += dur + a.pause
        if i % 25 == 0 or i == len(sents):
            print(f"  {i}/{len(sents)}  t={cursor:.1f}s", flush=True)

    full = np.concatenate(pieces)
    os.makedirs(a.outdir, exist_ok=True)
    wav_path = os.path.join(a.outdir, 'narration.wav')
    with wave.open(wav_path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(full.tobytes())

    srt_path = os.path.join(a.outdir, 'subtitles.srt')
    with open(srt_path, 'w', encoding='utf-8') as f:
        for n, (st, en, txt) in enumerate(cues, 1):
            f.write(f"{n}\n{srt_time(st)} --> {srt_time(en)}\n{txt}\n\n")

    duration = len(full) / sr
    meta = {'duration_sec': round(duration, 3), 'sentences': len(sents),
            'sample_rate': sr, 'length_scale': a.length_scale, 'pause': a.pause,
            'model': os.path.basename(model)}
    json.dump(meta, open(os.path.join(a.outdir, 'audio_meta.json'), 'w'), indent=2)

    print(f"\nwrote {wav_path}")
    print(f"wrote {srt_path}  ({len(cues)} cues)")
    print(f"duration: {duration:.1f}s  ({int(duration//60)}m{int(duration%60):02d}s)")

if __name__ == '__main__':
    main()
