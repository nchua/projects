"""Print's app icon: light, dark and tinted 1024 px PNGs into ios/Print/Assets.xcassets/AppIcon.appiconset.

    .venv/bin/python -I ios/scripts/app_icon.py      # from Photo App/ (needs numpy + Pillow, both in the venv)

A portrait print lying at a slight tilt on graphite, the same object as the `print.mark` symbol (it leans the
same way). Cream paper with a mounted print's deeper bottom margin, not an instant-film frame. The image is a
quiet horizon in the look's palette (LOOK.md): a slate sky warming to cream at the horizon, a near-neutral dark
ground, and a little amber halation where the light meets the horizon. Drawn at 4x and downsampled.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFilter

SS = 4                      # supersampling
N = 1024 * SS
TILT = 8.0                  # degrees, counter-clockwise: glyphs.py's TILT = -8 in its y-down coordinates
SKY = [(0.0, "#58687a"), (0.7, "#a9aead"), (1.0, "#e6d9bd")]
AMBER = "#e8a86a"


def gradient(h: int, stops: list[tuple[float, str]]) -> np.ndarray:
    """An h x 1 x 3 vertical gradient through (position 0..1, colour) stops; broadcasts across a row."""
    ys = np.linspace(0, 1, h)
    rgb = [ImageColor.getrgb(c) for _, c in stops]
    cols = np.stack([np.interp(ys, [p for p, _ in stops], [c[k] for c in rgb]) for k in range(3)], axis=1)
    return cols[:, None, :]


def the_print(paper: str, ground: str, glow: float, mono: bool = False) -> Image.Image:
    """The print, upright, on a transparent icon-sized canvas."""
    pw, ph = 580 * SS, 680 * SS
    x0, y0 = (N - pw) / 2, (N - ph) / 2 - 10 * SS
    layer = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((x0, y0, x0 + pw, y0 + ph), radius=14 * SS, fill=paper)
    side, bottom = 40 * SS, 72 * SS
    iw, ih = pw - 2 * side, ph - side - bottom
    horizon = int(ih * 0.60)
    img = np.zeros((ih, iw, 3))
    img[:horizon] = gradient(horizon, SKY)
    img[horizon:] = np.array(ImageColor.getrgb(ground), float) * np.linspace(1.0, 0.8, ih - horizon)[:, None, None]
    yy, xx = np.ogrid[0:ih, 0:iw]
    a = glow * np.exp(-((yy - horizon) / (ih * 0.05)) ** 2) * np.clip((xx / iw - 0.15) / 0.85, 0, 1) ** 1.5
    img = img * (1 - a[..., None]) + np.array(ImageColor.getrgb(AMBER), float) * a[..., None]
    if mono:
        img = np.repeat((img @ [0.2126, 0.7152, 0.0722])[..., None], 3, axis=2)
    tile = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    mask = Image.new("L", (iw, ih), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, iw, ih), radius=4 * SS, fill=255)
    layer.paste(tile, (int(x0 + side), int(y0 + side)), mask)
    return layer


def icon(background: str, layer: Image.Image, shadow: float) -> Image.Image:
    """The print tilted onto the background with a soft shadow, as an opaque 1024 px RGB image."""
    base = Image.new("RGBA", (N, N), background)
    tilted = layer.rotate(TILT, resample=Image.BICUBIC, center=(N / 2, N / 2))
    if shadow > 0:
        soft = Image.new("RGBA", (N, N), (0, 0, 0, 0))
        soft.putalpha(tilted.split()[3].filter(ImageFilter.GaussianBlur(28 * SS)).point(lambda v: int(v * shadow)))
        base.alpha_composite(soft, (0, 18 * SS))
    base.alpha_composite(tilted)
    return base.convert("RGB").resize((1024, 1024), Image.LANCZOS)   # opaque, as App Store icons must be


if __name__ == "__main__":
    here = Path(__file__).resolve().parent.parent / "Print" / "Assets.xcassets" / "AppIcon.appiconset"
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else here
    out.mkdir(parents=True, exist_ok=True)
    light = the_print(paper="#ece4d3", ground="#2b2622", glow=0.55)
    dark = the_print(paper="#d8d0bf", ground="#26221f", glow=0.50)
    tinted = the_print(paper="#e6e6e6", ground="#2b2622", glow=0.55, mono=True)
    icon("#1a1917", light, shadow=0.55).save(out / "icon.png")
    icon("#0b0b0a", dark, shadow=0.70).save(out / "icon-dark.png")
    icon("#000000", tinted, shadow=0.0).save(out / "icon-tinted.png")
