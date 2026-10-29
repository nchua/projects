"""The look, v1: the distilled recipe from LOOK.md, applied to an already-processed sRGB image.

This is a proxy for checking the style description, not the real pipeline. The real one starts
from scene-linear RAW. There the tone curve maps exposure straight to brightness, and highlights the
phone already clipped are still intact. TONE_ANCHORS below are a stock-JPEG → look transfer
curve, so they also undo the iPhone's own curve. Don't reuse them for RAW.

Usage: python look.py in.png out.png
"""

import sys

import numpy as np
from PIL import Image, ImageFilter

from colorspace import lab_to_rgb, linear_to_srgb, rgb_to_lab, srgb_to_linear

# Tone: stock L* -> look L*, read off the street pair's percentiles (black toe ~4, paper white ~91)
TONE_ANCHORS = [(0, 4.0), (1.1, 7.1), (6.3, 10.2), (17.4, 19.0), (40.5, 39.1),
                (67.1, 60.9), (87.9, 80.2), (95.6, 88.5), (100, 91.0)]

# Color: object hue is held, except bright blues -> teal and greens -> yellow-olive
BLUE_HUE_SHIFT = -50.0
BLUE_DESAT = 0.5
GREEN_HUE_SHIFT = -12.0
CHROMA_KNEE = 13.0      # chroma passes through below this...
CHROMA_CEILING = 23.0   # ...and rolls off toward this (Chromagraph's p90 chroma is ~22 in every scene)

# Neutral axis the look pulls low-chroma pixels toward: L* -> (a*, b*), averaged over the three scenes
NEUTRAL_ANCHORS_L = [0, 15, 45, 72, 92, 100]
NEUTRAL_A = [0.0, 0.0, -0.7, -5.8, -0.2, 0.0]   # green lives in the upper mids
NEUTRAL_B = [0.0, 1.5, 7.8, 8.5, 12.2, 12.5]    # cream highlights, b* ~ +11 everywhere

# Texture and lens
UNSHARPEN_SIGMA = 0.75
HALATION_THRESHOLD = 0.80
HALATION_RADIUS = 6
HALATION_TINT = np.array([0.15, 0.05, 0.0])     # restrained: a faint red-brown bleed
GRAIN_AMPLITUDE = 0.018                          # sRGB units at the midtone peak
GRAIN_CLUMP = 1.0                                # blur sigma, px at 6 MP -> 2-3 px clumps
VIGNETTE = 0.18                                  # corner light loss (linear)


def smoothstep(x: np.ndarray, e0: float, e1: float) -> np.ndarray:
    """Hermite ramp from 0 at e0 to 1 at e1."""
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def pchip(x: np.ndarray, xs: list[float], ys: list[float]) -> np.ndarray:
    """Monotone cubic (Fritsch-Carlson) interpolation through (xs, ys), so curves never overshoot."""
    xs_a, ys_a = np.asarray(xs, float), np.asarray(ys, float)
    h = np.diff(xs_a)
    d = np.diff(ys_a) / h
    m = np.zeros_like(xs_a)
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, len(xs_a) - 1):
        if d[i - 1] * d[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    i = np.clip(np.searchsorted(xs_a, x) - 1, 0, len(h) - 1)
    t = (x - xs_a[i]) / h[i]
    return (ys_a[i] * (2 * t**3 - 3 * t**2 + 1) + h[i] * m[i] * (t**3 - 2 * t**2 + t)
            + ys_a[i + 1] * (-2 * t**3 + 3 * t**2) + h[i] * m[i + 1] * (t**3 - t**2))


def tone(L: np.ndarray) -> np.ndarray:
    """Soft toe that never crushes, dense mids, a shoulder that rolls off to paper white."""
    return pchip(np.clip(L, 0, 100), *zip(*TONE_ANCHORS))


def color(L: np.ndarray, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Hue shifts, a soft chroma ceiling, then pull near-neutrals onto the look's warm-olive axis."""
    C = np.hypot(a, b)
    h = np.degrees(np.arctan2(b, a)) % 360
    bright_blue = smoothstep(h, 190, 215) * (1 - smoothstep(h, 285, 310)) * smoothstep(L, 40, 65)
    green = smoothstep(h, 90, 100) * (1 - smoothstep(h, 150, 170))
    h = h + BLUE_HUE_SHIFT * bright_blue + GREEN_HUE_SHIFT * green
    C = C * (1 - BLUE_DESAT * bright_blue)
    span = CHROMA_CEILING - CHROMA_KNEE
    C = np.where(C < CHROMA_KNEE, C, CHROMA_KNEE + span * np.tanh((C - CHROMA_KNEE) / span))
    a2, b2 = C * np.cos(np.radians(h)), C * np.sin(np.radians(h))

    target_a = pchip(L, NEUTRAL_ANCHORS_L, NEUTRAL_A)
    target_b = pchip(L, NEUTRAL_ANCHORS_L, NEUTRAL_B)
    neutral = 1 - smoothstep(C, 6, 18)
    pull = (0.35 + 0.55 * smoothstep(L, 35, 85)) * neutral
    a2 = a2 + pull * (target_a - a2) + (1 - neutral) * 0.3 * target_a
    b2 = b2 + pull * (target_b - b2) + (1 - neutral) * 0.3 * target_b
    return a2, b2


def vignette(rgb: np.ndarray) -> np.ndarray:
    """Rounded corner falloff, applied in linear light."""
    H, W = rgb.shape[:2]
    y, x = np.mgrid[0:H, 0:W]
    r = np.hypot((x - W / 2) / (W / 2), (y - H / 2) / (H / 2)) / np.sqrt(2)
    gain = 1 - VIGNETTE * smoothstep(r, 0.5, 1.05) ** 1.5
    return linear_to_srgb(srgb_to_linear(rgb) * gain[..., None])


def halation(rgb: np.ndarray) -> np.ndarray:
    """Bright areas bleed a faint red-orange glow into their surroundings."""
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    mask = np.clip((lum - HALATION_THRESHOLD) / 0.15, 0, 1)
    glow = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(HALATION_RADIUS))
    glow = np.asarray(glow).astype(np.float64)[..., None] / 255
    return rgb + glow * (1 - rgb) * HALATION_TINT


def grain(rgb: np.ndarray, seed: int = 0) -> np.ndarray:
    """Monochrome grain in 2-3 px clumps, peaking in the midtones (~55% strength at the extremes)."""
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    noise = np.random.default_rng(seed).standard_normal(lum.shape) * 40 + 128   # 8-bit so PIL can blur it
    img = Image.fromarray(noise.clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(GRAIN_CLUMP))
    noise = np.asarray(img).astype(np.float64) - 128
    noise /= noise.std()
    weight = 0.35 + 0.65 * (4 * lum * (1 - lum)).clip(0, 1) ** 1.5
    return rgb + (noise * GRAIN_AMPLITUDE * weight)[..., None]


def apply_look(img: Image.Image, seed: int = 0) -> Image.Image:
    """Run the full v1 recipe on a display-referred sRGB image."""
    img = img.convert("RGB").filter(ImageFilter.GaussianBlur(UNSHARPEN_SIGMA))
    lab = rgb_to_lab(np.asarray(img).astype(np.float64) / 255)
    L = tone(lab[..., 0])
    a, b = color(L, lab[..., 1], lab[..., 2])
    out = grain(halation(vignette(lab_to_rgb(np.stack([L, a, b], -1)))), seed)
    return Image.fromarray((np.clip(out, 0, 1) * 255).round().astype(np.uint8))


if __name__ == "__main__":
    apply_look(Image.open(sys.argv[1])).save(sys.argv[2])
