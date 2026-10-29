"""Scorecard: apply look.py to each stock image and compare against its Chromagraph twin.

Usage: python score.py STOCK.png TARGET.png [STOCK2.png TARGET2.png ...] [--out DIR]
Pairs must be sRGB, same size and orientation. With --out, writes stock | look | target triptychs.
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

from look import apply_look
from measure import load, stats

METRICS: list[tuple[str, str, float]] = [
    # (key, label, tolerance for "ok")
    ("L_p1", "black floor (p1 L*)", 2.0),
    ("L_p50", "median L*", 3.0),
    ("L_p99", "paper white (p99 L*)", 2.0),
    ("clipped_pct", "clipped %", 0.1),
    ("neutral_b_85", "highlight b*", 2.0),
    ("neutral_a_60", "upper-mid a*", 1.5),
    ("neutral_b_30", "mid b*", 2.0),
    ("p90_chroma", "p90 chroma", 2.0),
    ("sky/blue_hue", "sky hue", 10.0),
    ("sky/blue_chroma", "sky chroma", 3.0),
    ("flat_grain", "flat-area grain", 0.6),
    ("high_pass", "high-pass energy", 1.0),
]


def score_pair(stock_path: str, target_path: str, out_dir: Path | None) -> int:
    """Print one pair's scorecard; return the number of metrics outside tolerance."""
    stock_img = Image.open(stock_path).convert("RGB")
    look_img = apply_look(stock_img)
    target = load(target_path)
    s_stock, s_look, s_target = stats(np.asarray(stock_img) / 255.0), stats(np.asarray(look_img) / 255.0), stats(target)
    print(f"\n=== {Path(stock_path).name} -> {Path(target_path).name}")
    print(f"{'metric':22s} {'stock':>7s} {'look':>7s} {'target':>7s} {'delta':>7s}")
    misses = 0
    for key, label, tol in METRICS:
        if key not in s_target or key not in s_look:
            continue
        delta = s_look[key] - s_target[key]
        flag = "ok" if abs(delta) <= tol else "MISS"
        misses += flag == "MISS"
        print(f"{label:22s} {s_stock.get(key, float('nan')):7.1f} {s_look[key]:7.1f} {s_target[key]:7.1f} {delta:+7.1f}  {flag}")
    if out_dir:
        w, h = 540, 720
        canvas = Image.new("RGB", (w * 3 + 20, h), "white")
        for i, im in enumerate([stock_img, look_img, Image.open(target_path).convert("RGB")]):
            canvas.paste(im.resize((w, h)), (i * (w + 10), 0))
        canvas.save(out_dir / f"{Path(stock_path).stem}_triptych.jpg", quality=90)
    return misses


if __name__ == "__main__":
    args = sys.argv[1:]
    out = Path(args.pop(args.index("--out") + 1)) if "--out" in args else None
    if out:
        args.remove("--out")
        out.mkdir(parents=True, exist_ok=True)
    total = sum(score_pair(args[i], args[i + 1], out) for i in range(0, len(args), 2))
    print(f"\n{total} metric(s) outside tolerance")
