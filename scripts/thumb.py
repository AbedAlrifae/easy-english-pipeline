#!/usr/bin/env python3
"""Build a 1280x720 YouTube thumbnail for an episode."""
import argparse, math, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1280, 720
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


FB = _font(True)
FR = _font(False)


def hexrgb(s):
    s = s.lstrip('#')
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def wrap(d, text, path, size, maxw):
    f = ImageFont.truetype(path, size)
    words, lines, cur = text.split(), [], ''
    for w in words:
        t = f"{cur} {w}".strip()
        if d.textbbox((0, 0), t, font=f)[2] <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines, f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--title', required=True)
    ap.add_argument('--series', required=True)
    ap.add_argument('--level', required=True)      # e.g. "A2"
    ap.add_argument('--kicker', default='')        # e.g. "HOME CAFE"
    ap.add_argument('--bg', required=True)
    ap.add_argument('--accent', required=True)
    a = ap.parse_args()

    bg, acc = hexrgb(a.bg), hexrgb(a.accent)
    rng = random.Random(11)

    # soft radial-ish gradient background
    img = Image.new('RGB', (W, H), bg)
    grad = Image.new('RGB', (W, H))
    gd = ImageDraw.Draw(grad)
    top = mix(bg, acc, 0.16)
    for y in range(H):
        gd.line([(0, y), (W, y)], fill=mix(top, mix(bg, (0, 0, 0), 0.35), y / H))
    img = grad

    d = ImageDraw.Draw(img, 'RGBA')

    # faint accent arc bottom-right, gives depth without clutter
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W - 430, H - 400, W + 190, H + 220],
                                 fill=acc + (70,))
    img = Image.alpha_composite(img.convert('RGBA'),
                                glow.filter(ImageFilter.GaussianBlur(95))).convert('RGB')
    d = ImageDraw.Draw(img, 'RGBA')

    # thin accent rule top-left
    d.rectangle([70, 78, 70 + 96, 78 + 9], fill=acc)

    # kicker (the trend phrase) above the title
    y = 112
    if a.kicker:
        kf = ImageFont.truetype(FB, 34)
        d.text((70, y), a.kicker.upper(), font=kf, fill=acc)
        y += 62

    # title - shrink until at most 3 lines fit
    for size in (108, 96, 84, 74, 64):
        lines, tf = wrap(d, a.title, FB, size, W - 300)
        if len(lines) <= 3:
            break
    lh = int(size * 1.14)
    for ln in lines:
        d.text((70, y), ln, font=tf, fill=(247, 247, 245))
        y += lh

    # level badge bottom-left
    by = H - 132
    lf = ImageFont.truetype(FB, 54)
    lw = d.textbbox((0, 0), a.level, font=lf)[2]
    d.rounded_rectangle([70, by, 70 + lw + 58, by + 86], 16, fill=acc)
    d.text((70 + 29, by + 14), a.level, font=lf, fill=hexrgb(a.bg))

    # series name next to the badge
    sf = ImageFont.truetype(FR, 30)
    d.text((70 + lw + 86, by + 28), a.series.upper(),
           font=sf, fill=mix(bg, (255, 255, 255), 0.62))

    img.save(a.out, 'PNG', optimize=True)
    print(f"wrote {a.out}  {img.size}")


if __name__ == '__main__':
    main()
