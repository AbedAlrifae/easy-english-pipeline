#!/usr/bin/env python3
"""Sample frames and report where bright (subtitle) pixel bands land."""
import subprocess, sys
import numpy as np
from PIL import Image

video = sys.argv[1]
times = [int(x) for x in sys.argv[2:]] or [30, 200, 400, 560]
ok = 0
for t in times:
    png = f"/tmp/fc{t}.png"
    subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t), '-i', video,
                    '-frames:v', '1', '-y', png], check=True)
    a = np.array(Image.open(png).convert('L'))
    rows = (a > 170).sum(axis=1)
    hot = [i for i, v in enumerate(rows) if v > 3]
    bands = []
    for i in hot:
        if bands and i - bands[-1][1] <= 6:
            bands[-1][1] = i
        else:
            bands.append([i, i])
    low = [(b[0], b[1]) for b in bands if b[0] > 600]
    good = any(850 <= b[0] <= 1000 or 850 <= b[1] <= 1000 for b in low)
    ok += good
    print(f"{t:>4}s  all={[(b[0],b[1]) for b in bands]}")
    print(f"      below600={low}  {'OK' if good else 'NO CUE / MISPLACED'}")
print(f"\n{ok}/{len(times)} sampled seconds show a subtitle band in rows 850-1000")
