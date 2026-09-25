#!/usr/bin/env python3
"""Narrate a script with Piper or Kokoro.

v2 changes:
  - two-speaker support: lines may start with "A:" / "B:" (or "A -" / "B -")
  - natural pause model: pause length varies by punctuation, speaker change,
    paragraph break, plus per-gap random jitter
  - per-sentence speed jitter so the delivery is not metronomic
  - low room-tone bed + soft limiter so it sounds recorded, not synthesised
Emits narration.wav + subtitles.srt + audio_meta.json (same contract as v1).
"""
import argparse, json, os, random, re, sys, textwrap, wave
import numpy as np

WRAP = 42
MAXLINES = 2
SPK_RE = re.compile(r'^\s*([AB])\s*[:\-]\s*(.*)$')


def parse_script(text):
    """-> list of (speaker, sentence, para_break_before)."""
    text = re.sub(r'^#.*$', '', text, flags=re.M)
    text = text.replace('"', '').replace('“', '').replace('”', '')
    out, speaker, fresh_para = [], 'A', False
    for block in re.split(r'\n\s*\n', text):
        block = re.sub(r'\s+', ' ', block).strip()
        if not block:
            continue
        m = SPK_RE.match(block)
        if m:
            speaker, block = m.group(1), m.group(2).strip()
        fresh_para = True
        for s in re.split(r'(?<=[.!?])\s+', block):
            s = s.strip()
            if s:
                out.append((speaker, s, fresh_para))
                fresh_para = False
    return out


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
    words, out, per = s.split(), [], max(1, len(s) // MAXLINES)
    cur = ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > per and len(out) < MAXLINES - 1:
            out.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    out.append(cur)
    return '\n'.join(out)


def gap_for(sent, speaker_changed, para_break, base, rng):
    """Human-ish silence: not one constant value everywhere."""
    g = base
    if sent.endswith('?') or sent.endswith('!'):
        g *= 1.18
    if para_break:
        g *= 1.9
    if speaker_changed:
        g *= 0.75          # people answer each other quickly
    return max(0.12, g * rng.uniform(0.82, 1.18))


def room_tone(n, sr, rng):
    """Very low brown-ish noise so the silences are not digitally dead."""
    w = rng.normal(0, 1, n)
    b = np.cumsum(w)
    b -= b.mean()
    b /= (np.abs(b).max() + 1e-9)
    return (b * 0.0022 * 32767).astype(np.int16)


def soft_limit(x):
    """Gentle tanh limiter + headroom, in float, returns int16."""
    f = x.astype(np.float32) / 32768.0
    peak = np.abs(f).max() + 1e-9
    f = f / peak * 0.92
    f = np.tanh(f * 1.12) / np.tanh(1.12)
    return (f * 0.95 * 32767).astype(np.int16)


class PiperEngine:
    def __init__(self, models, length_scale):
        from piper import PiperVoice, SynthesisConfig
        self.cfgcls = SynthesisConfig
        self.ls = length_scale
        self.voices, self.srs = {}, {}
        for key, path in models.items():
            if not os.path.exists(path):
                path = os.path.join('voices', os.path.basename(path))
            if not os.path.exists(path):
                sys.exit(f"model not found: {models[key]}")
            v = PiperVoice.load(path)
            self.voices[key] = v
            self.srs[key] = v.config.sample_rate
        self.sr = max(self.srs.values())

    def say(self, key, text, jitter):
        v = self.voices[key]
        cfg = self.cfgcls(length_scale=self.ls * jitter, normalize_audio=True)
        chunks = [c.audio_int16_array for c in v.synthesize(text, cfg)]
        a = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
        src = self.srs[key]
        if src != self.sr:                      # linear resample to common rate
            n = int(len(a) * self.sr / src)
            a = np.interp(np.linspace(0, len(a) - 1, n),
                          np.arange(len(a)), a.astype(np.float32)).astype(np.int16)
        return a


class KokoroEngine:
    def __init__(self, voices, speed, root='kokoro', model='kokoro-v1.0.fp16.onnx'):
        from kokoro_onnx import Kokoro
        self.k = Kokoro(os.path.join(root, model),
                        os.path.join(root, 'voices-v1.0.bin'))
        self.voices = voices
        self.speed = speed
        self.sr = 24000

    def say(self, key, text, jitter):
        s, sr = self.k.create(text, voice=self.voices[key],
                              speed=self.speed / jitter, lang='en-us')
        return (np.clip(s, -1, 1) * 32767).astype(np.int16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('script')
    ap.add_argument('--engine', choices=['piper', 'kokoro'], default='piper')
    ap.add_argument('--model')
    ap.add_argument('--model-b')
    ap.add_argument('--kokoro-model', default='k_fp16.onnx')
    ap.add_argument('--voice-a', default='af_heart')
    ap.add_argument('--voice-b', default='am_michael')
    ap.add_argument('--length-scale', type=float, default=1.45)
    ap.add_argument('--speed', type=float, default=0.85)
    ap.add_argument('--pause', type=float, required=True)
    ap.add_argument('--label-a', default='')
    ap.add_argument('--label-b', default='')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--outdir', required=True)
    # chunked mode: the 1 GB sandbox cannot hold a whole episode in one process
    ap.add_argument('--range', dest='rng_', default=None, help='A:B sentence slice')
    ap.add_argument('--partdir', default=None)
    ap.add_argument('--merge', action='store_true')
    ap.add_argument('--chunk', type=int, default=0, help='auto-run in chunks of N')
    a = ap.parse_args()

    items = parse_script(open(a.script, encoding='utf-8').read())
    n = len(items)
    partdir = a.partdir or os.path.join(a.outdir, 'parts')

    if a.chunk:
        os.makedirs(partdir, exist_ok=True)
        base = [sys.executable, os.path.abspath(__file__), os.path.abspath(a.script)]
        for k, v in [('--engine', a.engine), ('--voice-a', a.voice_a), ('--voice-b', a.voice_b),
                     ('--speed', a.speed), ('--pause', a.pause), ('--length-scale', a.length_scale),
                     ('--label-a', a.label_a), ('--label-b', a.label_b), ('--seed', a.seed),
                     ('--outdir', a.outdir), ('--partdir', partdir), ('--kokoro-model', a.kokoro_model)]:
            if v not in (None, ''):
                base += [k, str(v)]
        if a.model: base += ['--model', a.model]
        if a.model_b: base += ['--model-b', a.model_b]
        import subprocess
        print(f"sentences: {n}  (chunks of {a.chunk})", flush=True)
        for s in range(0, n, a.chunk):
            e = min(s + a.chunk, n)
            if os.path.exists(os.path.join(partdir, f'p{s:05d}.json')):
                print(f"  {e}/{n}  cached", flush=True); continue
            r = subprocess.run(base + ['--range', f'{s}:{e}'],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if r.returncode != 0:
                sys.exit(f"chunk {s}:{e} failed rc={r.returncode}\n" + r.stdout.decode()[-1500:])
            print(f"  {e}/{n}  done", flush=True)
        return merge(a, partdir, n)

    if a.merge:
        return merge(a, partdir, n)

    lo, hi = (0, n) if not a.rng_ else map(int, a.rng_.split(':'))

    if a.engine == 'kokoro':
        eng = KokoroEngine({'A': a.voice_a, 'B': a.voice_b}, a.speed, model=a.kokoro_model)
    else:
        models = {'A': a.model}
        if a.model_b:
            models['B'] = a.model_b
        eng = PiperEngine(models, a.length_scale)
        if 'B' not in models:
            eng.voices['B'] = eng.voices['A']; eng.srs['B'] = eng.srs['A']

    sr = eng.sr
    labels = {'A': a.label_a, 'B': a.label_b}
    pieces, cues, cursor = [], [], 0.0
    for i in range(lo, hi):
        spk, sent, para = items[i]
        prev = items[i - 1][0] if i > 0 else None
        changed = prev is not None and spk != prev
        r = random.Random(a.seed * 1000003 + i)
        audio = eng.say(spk, sent, r.uniform(0.97, 1.03))
        dur = len(audio) / sr
        txt = f"{labels[spk]}: {sent}" if labels[spk] and (changed or prev is None) else sent
        cues.append([round(cursor, 4), round(cursor + dur, 4), wrap_cue(txt)])
        pieces.append(audio)
        g = gap_for(sent, changed, para and prev is not None, a.pause, r)
        pieces.append(np.zeros(int(sr * g), dtype=np.int16))
        cursor += dur + g
        if (i - lo + 1) % 10 == 0 or i == hi - 1:
            print(f"  {i+1}/{n}  t={cursor:.1f}s", flush=True)

    os.makedirs(partdir, exist_ok=True)
    buf = np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.int16)
    buf.tofile(os.path.join(partdir, f'p{lo:05d}.raw'))
    json.dump({'sr': sr, 'dur': cursor, 'cues': cues},
              open(os.path.join(partdir, f'p{lo:05d}.json'), 'w'))


def merge(a, partdir, n):
    import glob
    parts = sorted(glob.glob(os.path.join(partdir, 'p*.json')))
    if not parts:
        sys.exit('no parts to merge')
    sr = json.load(open(parts[0]))['sr']
    nrng = np.random.default_rng(a.seed)
    lead = np.zeros(int(sr * 0.7), dtype=np.int16)
    chunks, cues, off = [lead], [], 0.7
    for pj in parts:
        m = json.load(open(pj))
        chunks.append(np.fromfile(pj[:-5] + '.raw', dtype=np.int16))
        for st, en, txt in m['cues']:
            cues.append((st + off, en + off, txt))
        off += m['dur']

    full = np.concatenate(chunks).astype(np.int32)
    full += room_tone(len(full), sr, nrng).astype(np.int32)
    full = soft_limit(np.clip(full, -32768, 32767).astype(np.int16))

    os.makedirs(a.outdir, exist_ok=True)
    wav_path = os.path.join(a.outdir, 'narration.wav')
    with wave.open(wav_path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(full.tobytes())

    srt_path = os.path.join(a.outdir, 'subtitles.srt')
    with open(srt_path, 'w', encoding='utf-8') as f:
        for k, (st, en, t) in enumerate(cues, 1):
            f.write(f"{k}\n{srt_time(st)} --> {srt_time(en)}\n{t}\n\n")

    duration = len(full) / sr
    meta = {'duration_sec': round(duration, 3), 'sentences': n, 'sample_rate': sr,
            'engine': a.engine, 'pause_base': a.pause,
            'voices': ({'A': a.voice_a, 'B': a.voice_b} if a.engine == 'kokoro'
                       else {'A': a.model, 'B': a.model_b}),
            'speed': a.speed if a.engine == 'kokoro' else a.length_scale}
    json.dump(meta, open(os.path.join(a.outdir, 'audio_meta.json'), 'w'), indent=2)
    print(f"\nwrote {wav_path}")
    print(f"wrote {srt_path}  ({len(cues)} cues)")
    print(f"duration: {duration:.1f}s  ({int(duration//60)}m{int(duration%60):02d}s)")


if __name__ == '__main__':
    main()
