"""Scorecard: apply look.py to each stock image and compare against its Chromagraph twin.

Pairs must be sRGB, same size and orientation. With --out, writes stock | look | target triptychs.
Exits 1 if any metric is outside tolerance.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from look import apply_look
from measure import stats
from PIL import Image

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


def to_float(img: Image.Image) -> np.ndarray:
    """PIL RGB image -> float sRGB array in [0, 1]."""
    return np.asarray(img).astype(np.float64) / 255.0


def score_pair(stock_path: str, target_path: str, out_dir: Path | None) -> int:
    """Print one pair's scorecard; return the number of metrics outside tolerance."""
    stock_img = Image.open(stock_path).convert("RGB")
    target_img = Image.open(target_path).convert("RGB")
    look_img = apply_look(stock_img)
    s_stock, s_look, s_target = (stats(to_float(im)) for im in (stock_img, look_img, target_img))
    print(f"\n=== {Path(stock_path).name} -> {Path(target_path).name}")
    print(f"{'metric':22s} {'stock':>7s} {'look':>7s} {'target':>7s} {'delta':>7s}")
    misses = 0
    for key, label, tol in METRICS:
        if key not in s_target:
            continue  # the target scene has no such population (e.g. no sky): not applicable
        look = s_look.get(key)
        if look is None:  # the look wiped out a population the target has
            look_cell, delta_cell, flag = f"{'-':>7s}", f"{'-':>7s}", "MISS (absent in look)"
        else:
            delta = look - s_target[key]
            look_cell, delta_cell = f"{look:7.1f}", f"{delta:+7.2f}"
            flag = f"{'ok' if abs(delta) <= tol else 'MISS'} (tol {tol})"
        misses += "MISS" in flag
        print(f"{label:22s} {s_stock.get(key, float('nan')):7.1f} {look_cell} {s_target[key]:7.1f} {delta_cell}  {flag}")
    if out_dir:
        w, h = 540, 720
        canvas = Image.new("RGB", (w * 3 + 20, h), "white")
        for i, im in enumerate([stock_img, look_img, target_img]):
            canvas.paste(im.resize((w, h)), (i * (w + 10), 0))
        canvas.save(out_dir / f"{Path(stock_path).stem}_triptych.jpg", quality=90)
    return misses


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pairs", nargs="+", metavar="STOCK TARGET", help="stock / Chromagraph image pairs")
    parser.add_argument("--out", type=Path, help="directory for triptychs")
    args = parser.parse_args()
    if len(args.pairs) % 2:
        parser.error("images must come in STOCK TARGET pairs")
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    total = sum(score_pair(args.pairs[i], args.pairs[i + 1], args.out) for i in range(0, len(args.pairs), 2))
    print(f"\n{total} metric(s) outside tolerance")
    sys.exit(1 if total else 0)
