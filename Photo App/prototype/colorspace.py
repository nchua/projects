"""sRGB <-> CIELAB (D65) conversions shared by the measurement and look scripts."""

import numpy as np

_M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
_WP = np.array([0.95047, 1.0, 1.08883])
_EPS = 216 / 24389    # CIE linear/cube-root breakpoint
_KAPPA = 24389 / 27

LUMA = _M[1]          # Rec.709 luminance weights (the Y row of _M)


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    """Decode sRGB-encoded values in [0, 1] to linear light."""
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    """Encode linear light to sRGB, clipping to [0, 1]."""
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (H, W, 3) in [0, 1] -> CIELAB (H, W, 3)."""
    xyz = srgb_to_linear(rgb) @ _M.T / _WP
    f = np.where(xyz > _EPS, np.cbrt(xyz), (_KAPPA * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    """CIELAB (H, W, 3) -> sRGB (H, W, 3) in [0, 1]."""
    fy = (lab[..., 0] + 16) / 116
    f = np.stack([fy + lab[..., 1] / 500, fy, fy - lab[..., 2] / 200], -1)
    f3 = f**3
    xyz = np.where(f3 > _EPS, f3, (116 * f - 16) / _KAPPA) * _WP
    return linear_to_srgb(xyz @ np.linalg.inv(_M).T)


def lab_to_lch(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(a*, b*) -> (chroma, hue in degrees [0, 360))."""
    return np.hypot(a, b), np.degrees(np.arctan2(b, a)) % 360
