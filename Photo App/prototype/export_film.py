"""Export the film model for the iPhone app (APP_SPEC.md §2, M0).

Default: write film_params.json and print_lut.bin into the app's FilmCore resources, so a retune
here is "re-run the export, rebuild". With --reference, also write stage-by-stage fixtures for one
DNG to Photo App/fixtures/<stem>/ (git-ignored: they are renders of personal photos).

All .f32 fixtures are little-endian float32, planar (R, G, B planes), row-major.

Usage: python export_film.py [--reference in.dng ...]
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import PIL
import raw_look as R
import rawpy
from PIL import Image

APP_DIR = Path(__file__).resolve().parent.parent
RESOURCES = APP_DIR / "ios/FilmCore/Sources/FilmCore/Resources"
FIXTURES = APP_DIR / "fixtures"
REFERENCE_SEED = 0
PARAMS_VERSION = 1


def lut_bytes() -> bytes:
    """The print LUT as LUT_SIZE rows × 3 channels of little-endian float32, row-major."""
    _, lin = R.print_lut()
    return np.ascontiguousarray(lin, dtype="<f4").tobytes()


def params(lut_sha256: str) -> dict:
    """Every constant FilmCore needs, by its raw_look.py name in snake case."""
    return {
        "version": PARAMS_VERSION,
        "out_long_side": R.OUT_LONG_SIDE,
        "luma": R.LUMA.astype(float).tolist(),
        "mid_grey": R.MID_GREY,
        "highlight_percentile": R.HIGHLIGHT_PERCENTILE,
        "highlight_stops": R.HIGHLIGHT_STOPS,
        "average_stops": R.AVERAGE_STOPS,
        "meter_floor": R.METER_FLOOR,
        "crosstalk": R.CROSSTALK.tolist(),
        "clamp_floor": R.CLAMP_FLOOR,
        "vignette_stops": R.VIGNETTE_STOPS,
        "vignette_start": R.VIGNETTE_START,
        "vignette_end": R.VIGNETTE_END,
        "vignette_power": R.VIGNETTE_POWER,
        "halation_stops": R.HALATION_STOPS,
        "halation_sigma": R.HALATION_SIGMA,
        "halation_strength": R.HALATION_STRENGTH,
        "halation_tint": R.HALATION_TINT.tolist(),
        "halation_downsample": R.HALATION_DOWNSAMPLE,
        "blur_truncation": R.BLUR_TRUNCATION,
        "grain_stops": R.GRAIN_STOPS,
        "grain_sigma": R.GRAIN_SIGMA,
        "lut_min": R.TONE_STOPS[0],
        "lut_max": R.TONE_STOPS[-1],
        "lut_size": R.LUT_SIZE,
        "lut_sha256": lut_sha256,
    }


def export_params(out_dir: Path) -> str:
    """Write film_params.json + print_lut.bin; returns the LUT's sha256."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lut = lut_bytes()
    sha = hashlib.sha256(lut).hexdigest()
    (out_dir / "print_lut.bin").write_bytes(lut)
    (out_dir / "film_params.json").write_text(json.dumps(params(sha), indent=2) + "\n")
    return sha


def write_f32(path: Path, img: np.ndarray) -> None:
    """H×W or H×W×3 array -> planar little-endian float32."""
    planar = img[None] if img.ndim == 2 else np.moveaxis(img, -1, 0)
    path.write_bytes(np.ascontiguousarray(planar, dtype="<f4").tobytes())


def export_reference(dng: Path, lut_sha256: str) -> Path:
    """Stage-by-stage fixtures for one DNG (APP_SPEC.md M0)."""
    out = FIXTURES / dng.stem
    out.mkdir(parents=True, exist_ok=True)
    rgb, orientation = R.read_dng(str(dng))
    linear = R.prepare(R.orient(rgb, orientation).copy())
    h, w = linear.shape[:2]
    noise = R.grain_field(h, w, REFERENCE_SEED)
    stages: dict = {}
    img = R.film(linear, noise, stages)
    nograin = R.film(linear, None)

    write_f32(out / "linear6mp.f32", linear)
    write_f32(out / "noise.f32", noise / noise.std())
    write_f32(out / "glow.f32", stages["glow"])
    write_f32(out / "stops_pregrain.f32", stages["stops_pregrain"])
    write_f32(out / "out_nograin.f32", nograin)
    write_f32(out / "out.f32", img)
    Image.fromarray(R.to_8bit(img)).save(out / "out.png")

    lum = linear @ R.LUMA
    n = lum.size
    k_h, k_a = stages["k_highlight"], stages["k_average"]
    meta = {
        "dng": dng.name, "H": h, "W": w, "seed": REFERENCE_SEED, "N": n,
        "percentile_rank_q": (n - 1) * R.HIGHLIGHT_PERCENTILE / 100,
        "p": float(np.percentile(lum, R.HIGHLIGHT_PERCENTILE)),
        "k_highlight": k_h, "k_average": k_a, "k": min(k_h, k_a),
        "metering": "highlight" if k_h <= k_a else "average",
        "numpy": np.__version__, "pillow": PIL.__version__, "rawpy": rawpy.__version__,
        "lut_sha256": lut_sha256,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reference", nargs="+", type=Path, default=[], metavar="DNG")
    args = ap.parse_args()
    sha = export_params(RESOURCES)
    print(f"wrote {RESOURCES} (lut_sha256 {sha[:12]})")
    for dng in args.reference:
        print(f"wrote {export_reference(dng, sha)}")


if __name__ == "__main__":
    main()
