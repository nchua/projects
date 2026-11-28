"""Parity and look metrics between a reference render A and a candidate B (APP_SPEC.md M0).

Every app gate (tests A-D, the on-device check) uses these definitions; the Swift tests only write
images. Inputs are .png/.jpg (8-bit sRGB) or .f32 (little-endian float32, planar R, G, B, row-major;
H and W come from a meta.json next to the file or one directory up).

Default mode compares display sRGB images; --linear compares two linear 6 MP decodes (test C).
Thresholds: --max metric=value fails when |metric| > value, --min metric=value when metric < value.

Usage: python compare.py A B [--linear] [--max mean_db=0.3 ...] [--min pct_exact=99.99 ...]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import raw_look as R
from colorspace import LUMA, rgb_to_lab
from PIL import Image

GRAIN_TILE = 64
GRAIN_FLAT_PERCENTILE = 10
FINE_SIGMA, MEDIUM_SIGMA = 1.5, 4.0
NEUTRAL_C, NEUTRAL_L, NEUTRAL_MIN_PX = 12, 85, 2000
MIDTONE_STOPS = 2          # test C normalises on reference pixels within this many stops of mid grey
MASK_STOPS = 6             # ...and ignores pixels darker than this many stops under it
COLOR_DOWNSAMPLE = 8
OPTIONAL_METRICS = {"neutral_db", "neutral_b_ref"}   # absent when the neutral-highlight mask is too small


def load(path: Path) -> np.ndarray:
    """H×W×3 float array: sRGB in [0, 1] for 8-bit images, the stored values for .f32."""
    if path.suffix != ".f32":
        return np.asarray(Image.open(path).convert("RGB")).astype(np.float64) / 255
    meta = next(p for p in (path.parent / "meta.json", path.parent.parent / "meta.json") if p.exists())
    m = json.loads(meta.read_text())
    planar = np.fromfile(path, dtype="<f4").reshape(3, m["H"], m["W"])
    return np.moveaxis(planar, 0, -1).astype(np.float64)


def quantise(x: np.ndarray) -> np.ndarray:
    """Float sRGB -> 8-bit levels, the way the app and raw_look.develop() encode."""
    return R.to_8bit(x).astype(np.int16)


def grain_bands(rgb: np.ndarray, tiles_from: np.ndarray) -> dict[str, float]:
    """LOOK.md grain split on the flattest tiles: fine = std(luma - blur σ1.5), medium = std(σ1.5 - σ4).

    Tiles are GRAIN_TILE px; the flattest GRAIN_FLAT_PERCENTILE % are chosen by the structure
    (std of blur σ4) of `tiles_from`, so both images are measured on the same tiles. 8-bit units.
    """
    def tiled(x: np.ndarray) -> np.ndarray:
        H, W = (s // GRAIN_TILE * GRAIN_TILE for s in x.shape)
        return x[:H, :W].reshape(H // GRAIN_TILE, GRAIN_TILE, W // GRAIN_TILE, GRAIN_TILE).std((1, 3)).ravel()

    structure = tiled(R.blur(tiles_from @ LUMA, MEDIUM_SIGMA))
    flat = structure <= np.percentile(structure, GRAIN_FLAT_PERCENTILE)
    luma = rgb @ LUMA * 255
    b1, b4 = R.blur(luma, FINE_SIGMA), R.blur(luma, MEDIUM_SIGMA)
    return {"grain_fine": float(tiled(luma - b1)[flat].mean()), "grain_medium": float(tiled(b1 - b4)[flat].mean())}


def display_metrics(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    """Pixel, look and grain metrics of display sRGB B against reference A."""
    out: dict[str, float] = {}
    d = np.abs(b - a)
    out["max_d16"], out["mean_d16"] = float(d.max() * 65535), float(d.mean() * 65535)
    q = np.abs(quantise(b) - quantise(a)).max(-1)
    out["max_d8"] = float(q.max())
    out["pct_exact"] = float((q == 0).mean() * 100)
    out["pct_within1"] = float((q <= 1).mean() * 100)

    la, lb = rgb_to_lab(np.clip(a, 0, 1)), rgb_to_lab(np.clip(b, 0, 1))
    for p in (1, 50, 99):
        out[f"dL_p{p}"] = float(np.percentile(lb[..., 0], p) - np.percentile(la[..., 0], p))
    out["mean_da"] = float((lb[..., 1] - la[..., 1]).mean())
    out["mean_db"] = float((lb[..., 2] - la[..., 2]).mean())
    de = np.sqrt(((lb - la) ** 2).sum(-1))
    out["de_mean"], out["de_p95"] = float(de.mean()), float(np.percentile(de, 95))
    mask = (np.hypot(la[..., 1], la[..., 2]) < NEUTRAL_C) & (la[..., 0] >= NEUTRAL_L)
    out["neutral_px"] = float(mask.sum())
    if mask.sum() >= NEUTRAL_MIN_PX:
        out["neutral_b_ref"] = float(la[..., 2][mask].mean())
        out["neutral_db"] = float(lb[..., 2][mask].mean() - out["neutral_b_ref"])

    ga, gb = grain_bands(a, a), grain_bands(b, a)
    for k in ga:
        out[f"{k}_ref"], out[k] = ga[k], gb[k]
        out[f"{k}_ratio"] = gb[k] / ga[k] - 1
    return out


def phase_offset(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Sub-pixel (dx, dy) of b relative to a by phase correlation with a parabolic peak fit."""
    fa, fb = np.fft.rfft2(a - a.mean()), np.fft.rfft2(b - b.mean())
    cross = fb * np.conj(fa)
    corr = np.fft.irfft2(cross / np.maximum(np.abs(cross), 1e-12), s=a.shape)
    iy, ix = np.unravel_index(np.argmax(corr), corr.shape)

    def sub(c_m: float, c_0: float, c_p: float) -> float:
        den = c_m - 2 * c_0 + c_p
        return 0.0 if den == 0 else 0.5 * (c_m - c_p) / den

    h, w = corr.shape
    dy = iy + sub(corr[iy - 1, ix], corr[iy, ix], corr[(iy + 1) % h, ix])
    dx = ix + sub(corr[iy, ix - 1], corr[iy, ix], corr[iy, (ix + 1) % w])
    return float((dx + w / 2) % w - w / 2), float((dy + h / 2) % h - h / 2)


def box(x: np.ndarray, f: int) -> np.ndarray:
    """f×f mean downsample (cropping the remainder)."""
    H, W = x.shape[0] // f * f, x.shape[1] // f * f
    return x[:H, :W].reshape(H // f, f, W // f, f, *x.shape[2:]).mean((1, 3))


def linear_metrics(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    """Test C: decode parity of two linear 6 MP images (exposure, geometry, colour, tone)."""
    out: dict[str, float] = {}
    (ka_h, ka_a), (kb_h, kb_a) = R.meter(a.astype(np.float32)), R.meter(b.astype(np.float32))
    ka, kb = min(ka_h, ka_a), min(kb_h, kb_a)
    out["k_ref"], out["k"] = float(ka), float(kb)

    lum_a, lum_b = a @ LUMA, b @ LUMA
    mid = np.abs(np.log2(np.maximum(ka * lum_a, 1e-12) / R.MID_GREY)) <= MIDTONE_STOPS
    med_a, med_b = np.median(lum_a[mid]), np.median(lum_b[mid])
    # Core Image scales the decode by 2^BaselineExposure × the camera neutral's largest channel; rawpy
    # doesn't. Metering cancels a pure gain, so exposure parity is the metered result net of it
    out["decode_gain_stops"] = float(np.log2(med_b / med_a))
    out["exposure_stops"] = float(np.log2(kb * med_b / (ka * med_a)))
    a = a * (R.MID_GREY / med_a)
    b = b * (R.MID_GREY / med_b)
    floor = R.MID_GREY * 2.0**-MASK_STOPS
    mask = (a > floor).all(-1) & (b > floor).all(-1)
    out["mask_pct"] = float(mask.mean() * 100)

    la, lb = a @ LUMA, b @ LUMA
    out["dx"], out["dy"] = phase_offset(np.log2(np.maximum(la, floor)), np.log2(np.maximum(lb, floor)))

    ma = box(mask.astype(float), COLOR_DOWNSAMPLE) == 1
    ratio = np.log2(np.maximum(box(b, COLOR_DOWNSAMPLE), 1e-12) / np.maximum(box(a, COLOR_DOWNSAMPLE), 1e-12))[ma]
    for c, name in enumerate("rgb"):
        out[f"median_log2_{name}"] = float(np.median(ratio[:, c]))
    out["p95_abs_log2"] = float(np.percentile(np.abs(ratio), 95))

    x = np.log2(la[mask])
    y = np.log2(lb[mask]) - x
    out["tone_slope"] = float(np.polyfit(x, y, 1)[0])
    return out


def check(metrics: dict[str, float], bounds: list[str], upper: bool) -> list[str]:
    """Failures of metric=value bounds. A bound on an optional metric that wasn't computed is reported as n/a;
    any other unknown name fails, so a typo can't turn a gate into a silent pass."""
    fails = []
    for bound in bounds:
        key, value = bound.split("=")
        if key not in metrics:
            if key not in OPTIONAL_METRICS:
                fails.append(f"{key}: unknown metric")
            else:
                print(f"  {key}: n/a")
            continue
        v = metrics[key]
        if (abs(v) > float(value)) if upper else (v < float(value)):
            fails.append(f"{key} = {v:.6g} ({'|x| >' if upper else '<'} {value})")
    return fails


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", type=Path, help="reference")
    ap.add_argument("b", type=Path, help="candidate")
    ap.add_argument("--linear", action="store_true", help="test C: compare linear decodes")
    ap.add_argument("--max", action="append", default=[], metavar="METRIC=VALUE")
    ap.add_argument("--min", action="append", default=[], metavar="METRIC=VALUE")
    args = ap.parse_args()
    a, b = load(args.a), load(args.b)
    if a.shape != b.shape:
        sys.exit(f"size mismatch: {a.shape} vs {b.shape}")
    metrics = linear_metrics(a, b) if args.linear else display_metrics(a, b)
    print(f"{args.b} vs {args.a}")
    for k, v in metrics.items():
        print(f"  {k:18s} {v:.6g}")
    fails = check(metrics, args.max, True) + check(metrics, args.min, False)
    for f in fails:
        print(f"  FAIL {f}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
