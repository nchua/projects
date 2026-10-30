"""The look, v2: a fixed negative -> print rendering of an iPhone ProRAW DNG (see LOOK.md, "The soul").

Nothing here adapts to the scene except exposure, which is metered for the highlights the way a
cinematographer would spot-meter the brightest thing that matters. Everything else is one fixed
rendering applied to scene-linear light:

  DNG camera RGB -> XYZ at a fixed daylight white (Apple's auto white balance is ignored)
  -> linear sRGB -> dye crosstalk -> vignette + halation (in light, before the film)
  -> grain (in the negative, in stops) -> per-channel print curve -> sRGB, 6 MP

The print curve is one curve applied to each channel separately, so color shifts with density the
way film's does (warm light goes redder in shadow, yellower in highlight) without any per-hue rules.
Its neutral axis is the measured Chromagraph grey scale. Needs rawpy: see LOOK.md, "Reproduce".

Usage: python raw_look.py in.dng out.jpg
"""

import sys

import numpy as np
import rawpy
from colorspace import lab_to_rgb
from look import pchip, smoothstep
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

# DNG tags read from IFD0 (rawpy doesn't expose the color matrices of linear DNGs)
TAG_COLOR_MATRIX_2, TAG_ANALOG_BALANCE, TAG_ORIENTATION = 50722, 50727, 274

_XYZ_D65 = np.array([0.95047, 1.0, 1.08883])
_XYZ_TO_SRGB = np.linalg.inv(np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]))

# Exposure: the highlight that matters (99.5th percentile of luminance) is placed this many stops above
# mid grey (0.18). That's on the print's shoulder, so it holds just under paper white.
HIGHLIGHT_PERCENTILE = 99.5
HIGHLIGHT_STOPS = 5.0

# Print curve: stops from mid grey -> L*. Dmax toe near L* 1, dense mids (grey at 42), paper white ~92
TONE_STOPS = [-12.0, -7.0, -5.0, -3.5, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 12.0]
TONE_L = [0.6, 1.8, 4.5, 10.0, 21.0, 31.0, 42.0, 53.0, 64.0, 74.0, 82.5, 87.5, 90.0, 91.5, 92.0]

# The print's grey scale (L* -> a*, b*). Only the parts that held in all six daylight scenes are
# strong: cream paper white and a little green in the upper mids. Mid warmth varied with white
# balance (b* -1 to +7), so it's kept light; more of it turns skin yellow and skies grey
AXIS_L = [0.0, 15.0, 45.0, 72.0, 92.0, 100.0]
AXIS_A = [0.0, -1.0, -1.5, -4.2, -0.5, 0.0]
AXIS_B = [0.0, 0.3, 3.0, 6.5, 10.7, 11.0]

# Dye crosstalk, applied to linear light: blue leaks into green (print film's cyan dye), which turns
# skies teal, then a mild saturation boost the per-channel shoulder takes back in bright colors.
# Fit so the street and Toronto skies land on Chromagraph's 225° and skin stays warm (hue ~50°)
BLUE_TO_GREEN = 0.12
DYE_SATURATION = 1.15
CROSSTALK = ((DYE_SATURATION * np.eye(3) + (1 - DYE_SATURATION) / 3)
             @ np.array([[1.0, 0.0, 0.0], [0.0, 1 - BLUE_TO_GREEN, BLUE_TO_GREEN], [0.0, 0.0, 1.0]]))

VIGNETTE_STOPS = 0.35        # light lost at the exact corner
HALATION_STOPS = 3.0         # light more than this many stops over mid grey scatters back into the film
HALATION_SIGMA = 0.006       # glow radius, as a fraction of the image's long side
HALATION_STRENGTH = 0.12     # share of the excess light that returns, almost all of it into red
HALATION_TINT = np.array([1.0, 0.22, 0.0])
GRAIN_STOPS = 0.20           # grain std in the negative; the print curve's slope shapes it (mid-weighted)
GRAIN_SIGMA = 0.4            # clump size in output px: near per-pixel, like Chromagraph's fine grain
OUT_LONG_SIDE = 2880         # 6 MP, like Chromagraph


def read_dng(path: str) -> tuple[np.ndarray, int]:
    """Linear camera RGB in [0, 1] (unrotated) and the EXIF orientation."""
    Image.MAX_IMAGE_PIXELS = None
    tags = Image.open(path).tag_v2
    with rawpy.imread(path) as raw:
        if raw.raw_type != rawpy.RawType.Stack:
            raise ValueError("expected a linear (demosaiced) DNG such as Apple ProRAW")
        cam = raw.raw_image_visible[..., :3].astype(np.float32)
        black = float(np.mean(raw.black_level_per_channel[:3]))
        cam = (cam - black) / (raw.white_level - black)
    xyz_to_cam = np.diag(np.array(tags[TAG_ANALOG_BALANCE], float)) @ np.array(tags[TAG_COLOR_MATRIX_2], float).reshape(3, 3)
    # Fixed daylight balance: a D65 white in the scene becomes display white, whatever the light was
    cam_to_xyz = np.linalg.inv(xyz_to_cam)
    cam_to_xyz *= (_XYZ_D65[1] / (cam_to_xyz @ (xyz_to_cam @ _XYZ_D65))[1])
    rgb = cam @ (_XYZ_TO_SRGB @ cam_to_xyz).T.astype(np.float32)
    return rgb, int(tags.get(TAG_ORIENTATION, 1))


def orient(img: np.ndarray, orientation: int) -> np.ndarray:
    """Apply the EXIF orientation (1, 3, 6 or 8) to an H×W×C array."""
    return {3: lambda a: np.rot90(a, 2), 6: lambda a: np.rot90(a, -1), 8: lambda a: np.rot90(a, 1)}.get(
        orientation, lambda a: a)(img)


def resize(img: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Area-style resize of a float H×W×C array in linear light (no sharpening)."""
    return np.stack([np.asarray(Image.fromarray(img[..., c]).resize(size, Image.BOX)) for c in range(img.shape[2])], -1)


def blur(x: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur of a 2-D float array."""
    r = max(1, int(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    for axis in (0, 1):
        pad = [(r, r) if a == axis else (0, 0) for a in (0, 1)]
        x = (sliding_window_view(np.pad(x, pad, mode="edge"), 2 * r + 1, axis=axis) * k).sum(-1)
    return x


def wide_blur(x: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur for large sigma: blur at 1/4 size, then scale back up."""
    h, w = x.shape
    small = np.asarray(Image.fromarray(x.astype(np.float32)).resize((w // 4, h // 4), Image.BOX))
    return np.asarray(Image.fromarray(blur(small, sigma / 4).astype(np.float32)).resize((w, h), Image.BILINEAR))


def print_lut() -> tuple[np.ndarray, np.ndarray]:
    """Per-channel print curve as a lookup table: stops from mid grey -> linear display RGB.

    For a neutral (all channels at the same stops) the result lands exactly on the print's grey scale.
    """
    stops = np.linspace(TONE_STOPS[0], TONE_STOPS[-1], 4096)
    L = pchip(stops, TONE_STOPS, TONE_L)
    lab = np.stack([L, pchip(L, AXIS_L, AXIS_A), pchip(L, AXIS_L, AXIS_B)], -1)
    srgb = lab_to_rgb(lab[None])[0]
    lin = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    return stops, lin


def render(rgb: np.ndarray, seed: int = 0) -> np.ndarray:
    """Scene-linear sRGB (H×W×3, upright) -> display sRGB in [0, 1] at 6 MP."""
    h, w = rgb.shape[:2]
    scale = OUT_LONG_SIDE / max(h, w)
    rgb = resize(rgb, (round(w * scale), round(h * scale)))
    h, w = rgb.shape[:2]

    # Exposure, metered for the highlights
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    rgb = rgb * (0.18 * 2**HIGHLIGHT_STOPS / max(np.percentile(lum, HIGHLIGHT_PERCENTILE), 1e-6))
    rgb = np.clip(rgb @ CROSSTALK.T, 1e-7, None)

    # Lens and film, in light
    y, x = np.ogrid[0:h, 0:w]
    r = np.hypot((x - w / 2) / (w / 2), (y - h / 2) / (h / 2)) / np.sqrt(2)
    rgb = rgb * (2 ** (-VIGNETTE_STOPS * smoothstep(r, 0.45, 1.0) ** 1.5))[..., None]
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    excess = np.clip(lum - 0.18 * 2**HALATION_STOPS, 0, None)
    glow = wide_blur(excess, HALATION_SIGMA * max(h, w))
    rgb = rgb + (HALATION_STRENGTH * glow)[..., None] * HALATION_TINT

    # Negative: exposure in stops, plus monochrome grain
    stops = np.log2(rgb / 0.18)
    noise = blur(np.random.default_rng(seed).standard_normal((h, w)), GRAIN_SIGMA)
    stops = stops + (GRAIN_STOPS * noise / noise.std())[..., None]

    # Print
    lut_x, lut_rgb = print_lut()
    lin = np.stack([np.interp(stops[..., c], lut_x, lut_rgb[:, c]) for c in range(3)], -1)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.clip(lin, 0, 1) ** (1 / 2.4) - 0.055)


def develop(path: str, seed: int = 0) -> Image.Image:
    """DNG path -> the rendered 6 MP image."""
    rgb, orientation = read_dng(path)
    out = render(orient(rgb, orientation).copy(), seed)
    return Image.fromarray((np.clip(out, 0, 1) * 255).round().astype(np.uint8))


if __name__ == "__main__":
    develop(sys.argv[1]).save(sys.argv[2], quality=95)
