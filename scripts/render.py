#!/usr/bin/env python3
"""Render a 1080p still-frame episode: PIL title card + burned-in subtitles + AAC audio."""
import argparse, os, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
def _font(bold=True):
    """Find a usable sans font: bundled fonts/ dir, EES_FONT_DIR, then system paths."""
    import os
    names = (['DejaVuSans-Bold.ttf', 'Arial Bold.ttf', 'arialbd.ttf', 'Helvetica.ttc']
             if bold else
             ['DejaVuSans.ttf', 'Arial.ttf', 'arial.ttf', 'Helvetica.ttc'])
    dirs = [os.environ.get('EES_FONT_DIR', ''),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts'),
            'fonts',
            '/usr/share/fonts/truetype/dejavu',
            '/System/Library/Fonts/Supplemental',
            '/Library/Fonts',
            '/System/Library/Fonts',
            'C:\\Windows\\Fonts']
    for d in dirs:
        for n in names:
            if d and os.path.exists(os.path.join(d, n)):
                return os.path.join(d, n)
    raise SystemExit('no usable font found; set EES_FONT_DIR')


FONT_B = _font(True)
FONT_R = _font(False)
SAFE_TOP = 600          # nothing bright below this row: subtitles own the lower third

def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def fit(draw, text, font_path, size, maxw):
    """Shrink until the line fits, then return (font, width)."""
    while size > 20:
        f = ImageFont.truetype(font_path, size)
        w = draw.textbbox((0, 0), text, font=f)[2]
        if w <= maxw:
            return f, w
        size -= 2
    return ImageFont.truetype(font_path, size), draw.textbbox((0, 0), text, font=ImageFont.truetype(font_path, size))[2]

def wrap_title(draw, text, font_path, size, maxw):
    f = ImageFont.truetype(font_path, size)
    words, lines, cur = text.split(), [], ''
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textbbox((0, 0), t, font=f)[2] <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines, f

def build_frame(path, bg, accent, series, episode, level):
    bgc, acc = hex2rgb(bg), hex2rgb(accent)
    img = Image.new('RGB', (W, H), bgc)
    d = ImageDraw.Draw(img)

    # soft vignette: darken toward the edges, never brighten
    for i in range(60):
        k = 1 - i / 60.0
        c = tuple(max(0, int(v * (1 - 0.30 * k))) for v in bgc)
        d.rectangle([i * 2, i * 2, W - i * 2, H - i * 2], outline=c)

    # series title
    sf, sw = fit(d, series.upper(), FONT_B, 44, W - 400)
    d.text(((W - sw) // 2, 132), series.upper(), font=sf, fill=acc)

    # accent rule
    d.rectangle([W // 2 - 90, 206, W // 2 + 90, 210], fill=acc)

    # episode title, up to 2 lines
    lines, ef = wrap_title(d, episode, FONT_B, 82, W - 360)
    if len(lines) > 2:
        lines, ef = wrap_title(d, episode, FONT_B, 66, W - 360)
        lines = lines[:2]
    y = 300
    for ln in lines:
        lw = d.textbbox((0, 0), ln, font=ef)[2]
        d.text(((W - lw) // 2, y), ln, font=ef, fill=(245, 245, 245))
        y += ef.size + 18

    # level label
    lf, lw = fit(d, level, FONT_R, 36, W - 400)
    d.text(((W - lw) // 2, min(y + 30, SAFE_TOP - 70)), level, font=lf, fill=acc)

    img.save(path)
    return path

def ass_time(t):
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"

def srt_to_ass(srt, out):
    """libass assumes a 384x288 script for .srt - always convert with explicit PlayRes."""
    txt = open(srt, encoding='utf-8').read().replace('\r\n', '\n')
    cues = []
    for block in re.split(r'\n\s*\n', txt.strip()):
        ls = [l for l in block.split('\n') if l.strip()]
        if len(ls) < 2:
            continue
        m = re.search(r'(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)', block)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        st = g[0]*3600 + g[1]*60 + g[2] + g[3]/1000.0
        en = g[4]*3600 + g[5]*60 + g[6] + g[7]/1000.0
        body = '\\N'.join(l.strip() for l in ls[2:]) if len(ls) > 2 else ls[-1].strip()
        cues.append((st, en, body))

    with open(out, 'w', encoding='utf-8') as f:
        f.write("[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\n"
                f"PlayResX: {W}\nPlayResY: {H}\nScaledBorderAndShadow: yes\n\n")
        f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
                "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
                "MarginV, Encoding\n")
        f.write("Style: Sub,DejaVu Sans,52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,"
                "0,0,0,0,100,100,0,0,1,3,0,2,200,200,85,1\n\n")
        f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
                "MarginV, Effect, Text\n")
        for st, en, body in cues:
            f.write(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},Sub,,0,0,0,,{body}\n")
    return len(cues)

def audio_duration(path):
    out = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                                   'format=duration', '-of', 'csv=p=0', path])
    return float(out.decode().strip())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--audio', required=True)
    ap.add_argument('--srt', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--series-title', required=True)
    ap.add_argument('--episode-title', required=True)
    ap.add_argument('--level', required=True)
    ap.add_argument('--bg', required=True)
    ap.add_argument('--accent', required=True)
    ap.add_argument('--preset', default='veryfast')
    a = ap.parse_args()

    workdir = os.path.dirname(os.path.abspath(a.out)) or '.'
    frame = os.path.join(workdir, 'frame.png')
    assf = os.path.join(workdir, 'subtitles.ass')

    build_frame(frame, a.bg, a.accent, a.series_title, a.episode_title, a.level)
    n = srt_to_ass(a.srt, assf)
    dur = audio_duration(a.audio)
    print(f"frame: {frame}\nass: {assf} ({n} cues)\naudio: {dur:.2f}s", flush=True)

    # explicit -t: -shortest with -loop 1 produces a 48-byte file
    cmd = ['ffmpeg', '-y', '-loop', '1', '-framerate', '24', '-i', frame,
           '-i', a.audio, '-t', f"{dur:.3f}",
           '-vf', f"ass={assf}", '-r', '24', '-s', f"{W}x{H}",
           '-c:v', 'libx264', '-preset', a.preset, '-tune', 'stillimage',
           '-crf', '21', '-profile:v', 'high', '-level', '4.0',
           '-pix_fmt', 'yuv420p', '-threads', '2',
           '-x264-params', 'rc-lookahead=20:ref=2:bframes=2',
           '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
           '-movflags', '+faststart', a.out]
    print(' '.join(cmd), flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed: {r.returncode}")
    print(f"\nwrote {a.out}  ({os.path.getsize(a.out)/1e6:.1f} MB)")

if __name__ == '__main__':
    main()
