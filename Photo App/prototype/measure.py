"""Print the look statistics in LOOK.md for one or more images.

Usage: python measure.py image.png [image2.png ...]
Inputs should be sRGB and the same pixel size (convert HEIC first, see LOOK.md).
"""

import sys

import numpy as np
from colorspace import LUMA, lab_to_lch, rgb_to_lab
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

HUE_FAMILIES: dict[str, tuple[int, int]] = {
    "sky/blue": (200, 290),
    "foliage": (95, 140),
    "brick/red": (10, 50),
    "yellow/orange": (50, 95),
}
NEUTRAL_BANDS: list[tuple[int, int]] = [(5, 30), (30, 60), (60, 85), (85, 101)]
L_PCTS: list[int] = [1, 5, 25, 50, 75, 95, 99]


def load(path: str) -> np.ndarray:
    """Load an image as float sRGB in [0, 1]."""
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float64) / 255.0


def high_pass(gray: np.ndarray, k: int = 3) -> np.ndarray:
    """Pixel minus its k×k box mean (sharpening + grain energy); the box mean is separable."""
    r = k // 2
    box = sliding_window_view(sliding_window_view(gray, k, axis=1).mean(-1), k, axis=0).mean(-1)
    return gray[r:-r, r:-r] - box


def flat_grain(rgb: np.ndarray, tile: int = 64) -> float:
    """Grain strength: 10th-percentile 7×7 high-pass std of luma over tiles (flat tiles ≈ pure grain)."""
    hp = high_pass(rgb @ LUMA, 7)
    H, W = (s // tile * tile for s in hp.shape)
    if not H or not W:
        raise ValueError(f"image too small for {tile}px grain tiles")
    tiles = hp[:H, :W].reshape(H // tile, tile, W // tile, tile).std((1, 3))
    return float(np.percentile(tiles, 10) * 255)


def stats(rgb: np.ndarray) -> dict[str, float]:
    """The look metrics LOOK.md tracks, as a flat dict (missing hue families/bands are omitted)."""
    L, a, b = rgb_to_lab(rgb).reshape(-1, 3).T
    C, h = lab_to_lch(a, b)
    out: dict[str, float] = {f"L_p{p}": float(v) for p, v in zip(L_PCTS, np.percentile(L, L_PCTS))}
    out |= {
        "mean_chroma": float(C.mean()),
        "p90_chroma": float(np.percentile(C, 90)),
        "clipped_pct": float((rgb.reshape(-1, 3).max(1) >= 0.995).mean() * 100),
        "crushed_pct": float((L < 3).mean() * 100),
        "high_pass": float(high_pass(rgb.mean(-1)).std() * 255),
        "flat_grain": flat_grain(rgb),
    }
    neutral = C < 12
    for lo, hi in NEUTRAL_BANDS:
        m = neutral & (L >= lo) & (L < hi)
        if m.sum() > 500:
            out[f"neutral_a_{lo}"] = float(a[m].mean())
            out[f"neutral_b_{lo}"] = float(b[m].mean())
    for fam, (lo, hi) in HUE_FAMILIES.items():
        m = (C > 15) & (h >= lo) & (h < hi)
        if m.sum() > 500:
            out[f"{fam}_share"] = float(m.mean() * 100)
            out[f"{fam}_hue"] = float(h[m].mean())
            out[f"{fam}_chroma"] = float(C[m].mean())
    return out


def report(name: str, rgb: np.ndarray) -> None:
    """Print stats() in a readable layout."""
    s = stats(rgb)
    print(f"\n=== {name}")
    print("L* p1/5/25/50/75/95/99:", [round(s[f"L_p{p}"], 1) for p in L_PCTS])
    print(f"mean chroma {s['mean_chroma']:.1f}  p90 chroma {s['p90_chroma']:.1f}  clipped {s['clipped_pct']:.2f}%  crushed {s['crushed_pct']:.2f}%")
    for lo, hi in NEUTRAL_BANDS:
        if f"neutral_a_{lo}" in s:
            print(f"  neutral cast L*{lo}-{hi}: a*={s[f'neutral_a_{lo}']:+.1f} b*={s[f'neutral_b_{lo}']:+.1f}")
    for fam in HUE_FAMILIES:
        if f"{fam}_share" in s:
            print(f"  {fam:14s} share {s[f'{fam}_share']:5.1f}%  hue {s[f'{fam}_hue']:6.1f}  chroma {s[f'{fam}_chroma']:5.1f}")
    print(f"  high-pass {s['high_pass']:.2f}  flat-area grain {s['flat_grain']:.2f} (8-bit units)")


if __name__ == "__main__":
    for path in sys.argv[1:]:
        report(path, load(path))
