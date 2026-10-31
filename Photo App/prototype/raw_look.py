"""The look, v3: a fixed negative -> print rendering of an iPhone ProRAW DNG (see LOOK.md, "The soul").

Two things adapt to the scene. Exposure is metered for the highlights the way a cinematographer would
spot-meter the brightest thing that matters, but never set brighter than a normal average exposure. The
print is timed the way a lab times a print: a fixed share of the light's colour comes out (WHITE_BALANCE).
Everything else is one fixed rendering applied to scene-linear light:

  DNG camera RGB -> XYZ at a fixed daylight white -> linear sRGB (a daylight negative; Apple's own white
  balance and brightening are ignored, only the as-shot white is read)
  -> a touch of lens softness -> exposure -> print timing x dye crosstalk -> vignette + halation (in light,
  before the film) -> the negative in stops, where colour moves with density -> grain (in stops)
  -> per-channel print curve -> sRGB, 6 MP

The print curve is one curve applied to each channel separately; its neutral axis is the measured
Chromagraph grey scale; its toe and shoulder compress whichever channel is extreme, so every hue converges
on that grey scale toward paper white (warm highlights go cream). Before the curve, colour moves with density
the way Chromagraph's does (LOOK.md, "Density"): dense colours lose chroma and swing toward the magenta axis
(warm light goes redder, blue goes violet), light colours keep their hue and gain chroma, and neutrals never
move. Needs rawpy: see LOOK.md, "Reproduce".

Usage: python raw_look.py in.dng out.jpg
"""

import sys
from collections.abc import Mapping

import numpy as np
import rawpy
from colorspace import LUMA as LUMA_64
from colorspace import lab_to_rgb
from look import pchip, smoothstep
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

# DNG tags read from IFD0 (rawpy doesn't expose the color matrices of linear DNGs)
TAG_COLOR_MATRIX_2, TAG_ANALOG_BALANCE, TAG_AS_SHOT_NEUTRAL, TAG_ORIENTATION = 50722, 50727, 50728, 274

_XYZ_D65 = np.array([0.95047, 1.0, 1.08883])
XYZ_TO_SRGB = np.linalg.inv(np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]))

# Exposure: the highlight that matters (99.5th percentile of luminance) is placed this many stops above
# mid grey (0.18). That's on the print's shoulder (L* 90 of a 93.5 ceiling), where Chromagraph's p99.5 sits
HIGHLIGHT_PERCENTILE = 99.5
HIGHLIGHT_STOPS = 6.0
# ...but highlight metering only ever pulls exposure down. In an evenly lit scene the brightest areas
# are only ~2.5 stops over the average (a tungsten hallway), and pinning them to paper white would
# overexpose everything by ~2.5 stops. So exposure is capped where the scene's log-average luminance
# lands this many stops from mid grey ("normal" exposure)
AVERAGE_STOPS = 0.0

# Print timing: the lab takes this share of the light's colour out when it prints, as a Bradford
# (cone-space) adaptation from the camera's as-shot white toward daylight. Daylight scenes barely move;
# tungsten keeps half its warmth instead of turning the whole frame lemon-yellow. 0 = a pure daylight print
WHITE_BALANCE = 0.5
BRADFORD = np.array([[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]])

# Print curve: stops from mid grey -> L*. Dmax toe near L* 1, dense mids (grey at 42), a shoulder that
# puts +6 stops at L* 90 and ends at the exports' ceiling, L* 93.5
TONE_STOPS = [-12.0, -7.0, -5.0, -3.5, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 12.0]
TONE_L = [0.6, 1.8, 4.5, 10.0, 21.0, 31.0, 42.0, 53.0, 64.0, 74.0, 82.5, 87.5, 90.0, 92.5, 93.5]

# The print's grey scale (L* -> a*, b*). Only the parts that held in all six daylight scenes are
# strong: cream near white (b* +13 at L* 88, measured on every pixel, not just the near-neutral ones), a
# less yellow paper white at the ceiling (b* +10), and a little green in the upper mids. Mid warmth varied
# with white balance (b* -1 to +7), so it's kept light; more of it turns skin yellow and skies grey
AXIS_L = [0.0, 15.0, 45.0, 72.0, 88.0, 93.5, 100.0]
AXIS_A = [0.0, -1.0, -1.5, -4.2, 0.3, 0.0, 0.0]
AXIS_B = [0.0, 0.3, 3.0, 6.5, 13.0, 10.0, 10.0]

# Dye crosstalk, applied to linear light: blue leaks into green (print film's cyan dye), which turns
# skies teal, then a mild saturation boost the per-channel shoulder takes back in bright colors.
# Fit so the street and Toronto skies land on Chromagraph's 225° and skin stays warm (hue ~50°)
BLUE_TO_GREEN = 0.12
DYE_SATURATION = 1.15
CROSSTALK = ((DYE_SATURATION * np.eye(3) + (1 - DYE_SATURATION) / 3)
             @ np.array([[1.0, 0.0, 0.0], [0.0, 1 - BLUE_TO_GREEN, BLUE_TO_GREEN], [0.0, 0.0, 1.0]]))

# Colour moves with density (LOOK.md, "Density"). In the negative's stops a pixel's colour is its departure
# from the grey at its luminance, of some size (stops). Part of it moves from green to the magenta axis, two
# ways. In dense colour every departure moves, SHIFT_DENSE per stop of size: the green record runs ahead of
# the others in a dense print, so warm light goes redder, yellow goes orange, blue goes violet and reds stay
# red. In the mids a saturated colour moves more, SHIFT_SATURATED per stop of size squared: a faint colour
# keeps its hue and a strong one swings, as Chromagraph's do. The dense term is gone by mid grey, the saturated
# one by +4.5 stops (L* 85), where the cream grey scale takes over. The departure is then scaled by
# CHROMA_GAIN: dense colours lose half their chroma, light ones gain. Neutrals never move, so the grey scale
# above stays exactly as measured. Density is the pixel's luminance in stops from mid grey. The shift's size
# law saturates at DENSITY_CHROMA_CAP stops of colour: a channel with no light (the clamp floor, 21 stops
# down) and a saturated light source both swing as a 4-stop colour
DENSITY_STOPS = [-8.0, -3.0, -1.5, 0.0, 1.5, 3.0, 4.5, 8.0]
CHROMA_GAIN = [0.42, 0.42, 0.5, 0.8, 1.0, 1.4, 1.6, 1.6]
SHIFT_DENSE = [0.26, 0.26, 0.18, 0.02, 0.0, 0.0, 0.0, 0.0]
SHIFT_SATURATED = [0.0, 0.0, 0.02, 0.035, 0.03, 0.015, 0.0, 0.0]
DENSITY_CHROMA_CAP = 4.0
if not np.all(np.diff(DENSITY_STOPS) > 0):   # np.interp returns garbage, not an error, on a non-increasing axis
    raise ValueError("DENSITY_STOPS must increase")

SOFTEN_SIGMA = 0.55          # lens and scan softness in output px: Chromagraph's edges rise over 2.2-2.9 px
VIGNETTE_STOPS = 0.12        # light lost at the exact corner
HALATION_STOPS = 3.0         # light more than this many stops over mid grey scatters back into the film
HALATION_SIGMA = 0.003       # glow radius, as a fraction of the image's long side
HALATION_STRENGTH = 0.12     # share of the excess light that returns, almost all of it into red
HALATION_TINT = np.array([1.0, 0.22, 0.0])
GRAIN_STOPS = 0.20           # grain std in the negative; the print curve's slope shapes it (mid-weighted)
GRAIN_SIGMA = 0.55           # clump size in output px: fine, with Chromagraph's share of energy above 0.4 c/px
OUT_LONG_SIDE = 2880         # 6 MP, like Chromagraph

# Structural constants of the model (named so the app can load them from film_params.json, see APP_SPEC.md §2)
LUMA = LUMA_64.astype(np.float32)   # Rec.709 luminance weights, float32 like the image
MID_GREY = 0.18
METER_FLOOR = 1e-6           # floor on luminance before the percentile and log-average
CLAMP_FLOOR = 1e-7           # floor on light after crosstalk, so log2 stays finite
VIGNETTE_START, VIGNETTE_END, VIGNETTE_POWER = 0.45, 1.0, 1.5   # radius (corner = 1) where falloff starts / ends
HALATION_DOWNSAMPLE = 4      # wide_blur works at 1/4 size
BLUR_TRUNCATION = 3          # Gaussian kernels are cut at this many sigma
LUT_SIZE = 4096              # print LUT samples over TONE_STOPS[0]..TONE_STOPS[-1]
GREEN_MAGENTA = np.array([-1.0, 2.0, -1.0]) / np.sqrt(6)   # unit vector in stops from magenta to green, orthogonal to neutral


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
    xyz_to_cam = _xyz_to_cam(tags)
    # Fixed daylight balance: a D65 white in the scene becomes display white, whatever the light was
    cam_to_xyz = np.linalg.inv(xyz_to_cam)
    cam_to_xyz *= (_XYZ_D65[1] / (cam_to_xyz @ (xyz_to_cam @ _XYZ_D65))[1])
    rgb = cam @ (XYZ_TO_SRGB @ cam_to_xyz).T.astype(np.float32)
    return rgb, int(tags.get(TAG_ORIENTATION, 1))


def _xyz_to_cam(tags: Mapping) -> np.ndarray:
    """XYZ (D65) -> camera RGB: AnalogBalance (identity if absent, per the DNG spec) times ColorMatrix2."""
    balance = np.array(tags.get(TAG_ANALOG_BALANCE, (1.0, 1.0, 1.0)), float)
    return np.diag(balance) @ np.array(tags[TAG_COLOR_MATRIX_2], float).reshape(3, 3)


def as_shot_white(path: str) -> np.ndarray | None:
    """The light's colour: the camera's as-shot white in read_dng's linear sRGB, G = 1 (None if untagged, or
    if the tags give no finite white with light in green)."""
    tags = Image.open(path).tag_v2
    if TAG_AS_SHOT_NEUTRAL not in tags:
        return None
    white = XYZ_TO_SRGB @ np.linalg.solve(_xyz_to_cam(tags), np.array(tags[TAG_AS_SHOT_NEUTRAL], float))
    if not (np.all(np.isfinite(white)) and white[1] > 0):
        return None
    return white / white[1]


def print_timing(white: np.ndarray | None) -> np.ndarray:
    """Print timing as a 3×3 on linear sRGB: adapt the light's colour WHITE_BALANCE of the way to daylight
    in Bradford cone space, keeping the white's luminance. Identity without a white (the print is then a
    daylight print) or for a white whose cone responses aren't all positive and finite."""
    if white is None:
        return np.eye(3)
    w = np.asarray(white, float)
    to_lms = BRADFORD @ np.linalg.inv(XYZ_TO_SRGB)
    light = to_lms @ w
    if not np.all(np.isfinite(light) & (light > 0)):
        return np.eye(3)
    gain = ((to_lms @ np.ones(3)) / light) ** WHITE_BALANCE
    a = np.linalg.inv(to_lms) @ np.diag(gain) @ to_lms
    luma = LUMA.astype(float)
    return a * ((luma @ w) / (luma @ (a @ w)))


def orient(img: np.ndarray, orientation: int) -> np.ndarray:
    """Apply the EXIF orientation (1, 3, 6 or 8) to an H×W×C array."""
    return {3: lambda a: np.rot90(a, 2), 6: lambda a: np.rot90(a, -1), 8: lambda a: np.rot90(a, 1)}.get(
        orientation, lambda a: a)(img)


def resize(img: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Lanczos resize of a float H×W×C array in linear light. No sharpening is added, but a box filter
    at a non-integer ratio (12 MP -> 6 MP) visibly softens fine detail, and Lanczos doesn't."""
    return np.stack([np.asarray(Image.fromarray(img[..., c]).resize(size, Image.LANCZOS)) for c in range(img.shape[2])], -1)


def blur(x: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur of a 2-D float array."""
    r = max(1, int(BLUR_TRUNCATION * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    for axis in (0, 1):
        pad = [(r, r) if a == axis else (0, 0) for a in (0, 1)]
        x = (sliding_window_view(np.pad(x, pad, mode="edge"), 2 * r + 1, axis=axis) * k).sum(-1)
    return x


def wide_blur(x: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur for large sigma: blur at 1/HALATION_DOWNSAMPLE size, then scale back up."""
    h, w = x.shape
    d = HALATION_DOWNSAMPLE
    small = np.asarray(Image.fromarray(x.astype(np.float32)).resize((w // d, h // d), Image.BOX))
    return np.asarray(Image.fromarray(blur(small, sigma / d).astype(np.float32)).resize((w, h), Image.BILINEAR))


def print_lut() -> tuple[np.ndarray, np.ndarray]:
    """Per-channel print curve as a lookup table: stops from mid grey -> linear display RGB.

    For a neutral (all channels at the same stops) the result lands exactly on the print's grey scale.
    """
    stops = np.linspace(TONE_STOPS[0], TONE_STOPS[-1], LUT_SIZE)
    L = pchip(stops, TONE_STOPS, TONE_L)
    lab = np.stack([L, pchip(L, AXIS_L, AXIS_A), pchip(L, AXIS_L, AXIS_B)], -1)
    srgb = lab_to_rgb(lab[None])[0]
    lin = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    return stops, lin


def prepare(rgb: np.ndarray) -> np.ndarray:
    """Scene-linear sRGB (H×W×3, upright) -> the same at 6 MP (Lanczos, negatives kept)."""
    h, w = rgb.shape[:2]
    scale = OUT_LONG_SIDE / max(h, w)
    return resize(rgb, (round(w * scale), round(h * scale)))


def meter(rgb: np.ndarray) -> tuple[float, float]:
    """(k_highlight, k_average): exposure metered for the highlights, and the cap at a normal exposure.

    Both are float32 like the image; the log-average is accumulated and exponentiated in float64 and rounded
    once, so the app can reproduce k bit for bit (APP_SPEC.md §5.2 step 1, §11 rev 4).
    """
    lum = rgb @ LUMA
    k_highlight = MID_GREY * 2**HIGHLIGHT_STOPS / max(np.percentile(lum, HIGHLIGHT_PERCENTILE), METER_FLOOR)
    log_mean = np.mean(np.log(np.maximum(lum, METER_FLOOR), dtype=np.float64))
    k_average = np.float32(MID_GREY * 2**AVERAGE_STOPS / np.exp(log_mean))
    return k_highlight, k_average


def grain_field(h: int, w: int, seed: int = 0) -> np.ndarray:
    """Monochrome grain: white noise blurred to the grain size (film() scales it to unit std)."""
    return blur(np.random.default_rng(seed).standard_normal((h, w)), GRAIN_SIGMA)


def soften(rgb: np.ndarray) -> np.ndarray:
    """Lens and scan softness: a small Gaussian on each channel of the linear image, float32 like it."""
    return np.stack([blur(rgb[..., c], SOFTEN_SIGMA) for c in range(3)], -1).astype(np.float32)


def density(stops: np.ndarray, luminance: np.ndarray) -> np.ndarray:
    """Colour moves with density (see DENSITY_STOPS). `luminance` is the pixel's luminance in stops from mid
    grey: its density on the curve, and the grey its colour is scaled about (not the channel mean, which a
    channel at the clamp floor drags down with it). float32 out; float64 in between, in the order the app
    repeats, so the two agree to a float32 rounding."""
    s = stops.astype(np.float64, copy=False)
    p = luminance.astype(np.float64, copy=False)
    d = s - p[..., None]
    # In place from here: the same operations in the same order, without 150 MB temporaries at 6 MP
    size = d[..., 0] ** 2
    size += d[..., 1] ** 2
    size += d[..., 2] ** 2
    np.sqrt(size, out=size)
    np.minimum(size, DENSITY_CHROMA_CAP, out=size)
    shift = size * (np.interp(p, DENSITY_STOPS, SHIFT_DENSE) + np.interp(p, DENSITY_STOPS, SHIFT_SATURATED) * size)
    gain = np.interp(p, DENSITY_STOPS, CHROMA_GAIN)
    for c in range(3):
        d[..., c] -= shift * GREEN_MAGENTA[c]
    d *= gain[..., None]
    d += p[..., None]
    return d.astype(np.float32)


def film(rgb: np.ndarray, noise: np.ndarray | None, stages: dict | None = None, *,
         white: np.ndarray | None = None) -> np.ndarray:
    """6 MP scene-linear sRGB -> display sRGB in [0, 1]. noise=None renders without grain.

    `white` is the light's colour (as_shot_white) for print_timing. If given, `stages` is filled with the
    intermediate results the app's parity tests compare against.
    """
    h, w = rgb.shape[:2]

    # Lens, in light: a touch of softness before anything is metered
    rgb = soften(rgb)

    # Exposure, metered for the highlights, never brighter than normal
    k_highlight, k_average = meter(rgb)
    rgb = rgb * min(k_highlight, k_average)
    # ...then the print is timed (the lab times the print, not the exposure), folded into the dye crosstalk
    rgb = np.clip(rgb @ (CROSSTALK @ print_timing(white)).T, CLAMP_FLOOR, None)

    # Lens and film, in light
    y, x = np.ogrid[0:h, 0:w]
    r = np.hypot((x - w / 2) / (w / 2), (y - h / 2) / (h / 2)) / np.sqrt(2)
    rgb = rgb * (2 ** (-VIGNETTE_STOPS * smoothstep(r, VIGNETTE_START, VIGNETTE_END) ** VIGNETTE_POWER))[..., None]
    lum = rgb @ LUMA
    excess = np.clip(lum - MID_GREY * 2**HALATION_STOPS, 0, None)
    glow = wide_blur(excess, HALATION_SIGMA * max(h, w))
    rgb = rgb + (HALATION_STRENGTH * glow)[..., None] * HALATION_TINT

    # Negative: exposure in stops, colour moving with density, plus monochrome grain
    stops = density(np.log2(rgb / MID_GREY), np.log2((rgb @ LUMA) / MID_GREY))
    if stages is not None:
        stages.update(k_highlight=float(k_highlight), k_average=float(k_average), glow=glow, stops_pregrain=stops)
    if noise is not None:
        stops = stops + (GRAIN_STOPS * noise / noise.std())[..., None]

    # Print
    lut_x, lut_rgb = print_lut()
    lin = np.stack([np.interp(stops[..., c], lut_x, lut_rgb[:, c]) for c in range(3)], -1)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.clip(lin, 0, 1) ** (1 / 2.4) - 0.055)


def render(rgb: np.ndarray, seed: int = 0, white: np.ndarray | None = None) -> np.ndarray:
    """Scene-linear sRGB (H×W×3, upright) -> display sRGB in [0, 1] at 6 MP."""
    rgb = prepare(rgb)
    return film(rgb, grain_field(*rgb.shape[:2], seed), white=white)


def to_8bit(img: np.ndarray) -> np.ndarray:
    """Display sRGB float -> 8-bit levels (numpy rounds half to even; the app does too)."""
    return (np.clip(img, 0, 1) * 255).round().astype(np.uint8)


def develop(path: str, seed: int = 0) -> Image.Image:
    """DNG path -> the rendered 6 MP image."""
    rgb, orientation = read_dng(path)
    out = render(orient(rgb, orientation).copy(), seed, as_shot_white(path))
    return Image.fromarray(to_8bit(out))


if __name__ == "__main__":
    develop(sys.argv[1]).save(sys.argv[2], quality=95)
