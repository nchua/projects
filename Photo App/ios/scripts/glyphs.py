"""Print's custom SF Symbols, written as Apple custom-symbol templates into the app's asset catalog.

    python3 ios/scripts/glyphs.py            # rewrites ios/Print/Assets.xcassets/print.*.symbolset

- print.mark      the empty state: a portrait print lying at a slight tilt, paper (primary layer) around the image
                  (secondary layer), the bottom margin a mounted print's deeper one. The tilt makes it an object,
                  not a screen.
- print.negative  Pick Photos: a strip of 35 mm negative, two frames and two rows of perforations cut out of the base.

How the templates are built (all found the hard way, 2026-10-31):
- Static template, all 27 weight x scale glyphs. Xcode 26's actool reads a hand-written variable template
  (Ultralight/Regular/Black-S only) as static and fails with "must have a glyph for Regular weight Medium size",
  so each variant is drawn here at its own stroke instead of being interpolated.
- Strokes and sizes are SF's own, measured from `rectangle` rendered at 100 pt: Regular-S is 90.7 x 72 with a 7.0
  stroke; M is 1.289x S and L 1.631x S, and the stroke grows with both weight and scale (STROKE).
- No `SFSymbolsPreviewWireframe` class and no <style>: inside iOS 26 button labels the symbol renderer applies that
  class's `fill:none`, and the glyph draws as a 0.5 pt hairline (it looked fine in toolbars and on its own).
- Holes are contours reversed against their outline (nonzero winding), so no boolean geometry is needed.

Units: the template's S row at 100 pt (baseline y = 0, cap height 70.459, up is -y); glyphs centre on CAP_MID.
"""
from __future__ import annotations

import math
import sys
from collections.abc import Callable
from pathlib import Path

K = 0.5522847498            # cubic quarter-circle constant
CAP = 70.459                # the template's cap height at 100 pt
CAP_MID = -35.23            # half the cap height: SF Symbols centre on it
TILT = -8.0                 # the print's tilt, degrees (screen coordinates: negative leans it left)
WEIGHTS = ["Ultralight", "Thin", "Light", "Regular", "Medium", "Semibold", "Bold", "Heavy", "Black"]
STROKE = {                  # SF's stroke per weight, by scale, in template units
    "S": [2.25, 3.25, 5.50, 7.00, 8.25, 9.25, 10.50, 12.50, 14.25],
    "M": [2.50, 3.75, 6.00, 8.00, 9.75, 11.00, 12.75, 15.25, 17.50],
    "L": [2.50, 4.00, 6.50, 8.75, 10.75, 12.25, 14.50, 17.50, 20.00],
}
SCALE = {"S": 1.0, "M": 117.0 / 90.75, "L": 148.0 / 90.75}
BASELINE = {"S": 696.0, "M": 1126.0, "L": 1556.0}

Pt = tuple[float, float]


class Contour:
    """A closed contour: a start point and segments ('L', p) or ('C', c1, c2, p)."""

    def __init__(self, start: Pt) -> None:
        self.start = start
        self.segs: list[tuple] = []   # ("L", p) or ("C", c1, c2, p)

    def line(self, p: Pt) -> "Contour":
        """Appends a straight segment to p."""
        self.segs.append(("L", p))
        return self

    def curve(self, c1: Pt, c2: Pt, p: Pt) -> "Contour":
        """Appends a cubic Bezier segment to p with control points c1, c2."""
        self.segs.append(("C", c1, c2, p))
        return self

    def reversed(self) -> "Contour":
        """The same outline traced the other way: a hole when it sits inside a filled contour."""
        pts = [self.start] + [s[-1] for s in self.segs]
        out = Contour(pts[-1])
        for i in range(len(self.segs) - 1, -1, -1):
            s, p = self.segs[i], pts[i]
            out.segs.append(("L", p) if s[0] == "L" else ("C", s[2], s[1], p))
        return out

    def mapped(self, t: Callable[[Pt], Pt]) -> "Contour":
        """The contour with every point (control points included) passed through t."""
        out = Contour(t(self.start))
        out.segs = [(s[0],) + tuple(t(q) for q in s[1:]) for s in self.segs]
        return out

    def svg(self, dx: float = 0.0) -> str:
        """SVG path data, shifted right by dx."""
        def f(p: Pt) -> str:
            return f"{p[0] + dx:.3f} {p[1]:.3f}"

        d = [f"M{f(self.start)}"]
        for s in self.segs:
            d.append(f"L{f(s[1])}" if s[0] == "L" else f"C{f(s[1])} {f(s[2])} {f(s[3])}")
        return "".join(d) + "Z"

    def points(self) -> list[Pt]:
        """Every point, control points included (for bounds)."""
        return [self.start] + [q for s in self.segs for q in s[1:]]


Layers = list[list[Contour]]


def rrect(cx: float, cy: float, w: float, h: float, r: float) -> Contour:
    """Rounded rect, clockwise on screen (y down): 4 lines and 4 quarter arcs."""
    r = max(min(r, w / 2 - 0.01, h / 2 - 0.01), 0.01)
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    k = r * K
    c = Contour((x0 + r, y0))
    c.line((x1 - r, y0)).curve((x1 - r + k, y0), (x1, y0 + r - k), (x1, y0 + r))
    c.line((x1, y1 - r)).curve((x1, y1 - r + k), (x1 - r + k, y1), (x1 - r, y1))
    c.line((x0 + r, y1)).curve((x0 + r - k, y1), (x0, y1 - r + k), (x0, y1 - r))
    c.line((x0, y0 + r)).curve((x0, y0 + r - k), (x0 + r - k, y0), (x0 + r, y0))
    return c


def ring(cx: float, cy: float, w: float, h: float, r: float, s: float) -> list[Contour]:
    """A stroked rounded rect: centreline w x h, corner radius r, stroke s."""
    return [rrect(cx, cy, w + s, h + s, r + s / 2), rrect(cx, cy, w - s, h - s, r - s / 2).reversed()]


def rotated(contours: list[Contour], deg: float, about: Pt) -> list[Contour]:
    """The contours rotated by deg (screen coordinates) about a point."""
    ca, sa = math.cos(math.radians(deg)), math.sin(math.radians(deg))

    def t(q: Pt) -> Pt:
        return (about[0] + (q[0] - about[0]) * ca - (q[1] - about[1]) * sa,
                about[1] + (q[0] - about[0]) * sa + (q[1] - about[1]) * ca)

    return [c.mapped(t) for c in contours]


def print_mark(s: float) -> Layers:
    """The print at stroke s: paper (layer 0) and image (layer 1), tilted."""
    cw, ch = 60.0 - s / 2, 76.0 - s / 2             # paper centreline
    paper = ring(0, CAP_MID, cw, ch, 5.0, s)
    g = 6.5 - 0.25 * s                               # visible paper at the top and sides
    gb = 1.8 * g                                     # and the deeper bottom
    ix0, ix1 = -cw / 2 + s / 2 + g, cw / 2 - s / 2 - g
    iy0, iy1 = CAP_MID - ch / 2 + s / 2 + g, CAP_MID + ch / 2 - s / 2 - gb
    image = [rrect((ix0 + ix1) / 2, (iy0 + iy1) / 2, ix1 - ix0, iy1 - iy0, 0.8)]
    about = (0.0, CAP_MID)
    return [rotated(paper, TILT, about), rotated(image, TILT, about)]


def negative(s: float) -> Layers:
    """The negative strip at stroke s: one layer, the base with its holes."""
    W, H = 88.0 + s / 2, 58.0 + s / 2
    m = 0.55 * s + 1.4                               # film between the holes tracks the stroke
    holes: list[Contour] = []
    perf_h = 7.2 - 0.25 * s
    perfs = 5                                        # per row
    band_y = H / 2 - m - perf_h / 2                  # perforation rows, from the strip's centre
    pitch = (W - 2 * m) / perfs
    for row in (-1, 1):
        for i in range(perfs):
            x = -W / 2 + m + pitch * (i + 0.5)
            holes.append(rrect(x, CAP_MID + row * band_y, pitch - 1.25 * m, perf_h, 1.2).reversed())
    fh = H - 2 * (2 * m + perf_h)
    fw = (W - 3 * m) / 2
    for side in (-1, 1):
        holes.append(rrect(side * (m / 2 + fw / 2), CAP_MID, fw, fh, 2.0).reversed())
    return [[rrect(0, CAP_MID, W, H, 5.0 + s / 3)] + holes]


GLYPHS = {"print.mark": print_mark, "print.negative": negative}


def template(name: str) -> str:
    """The glyph's complete custom-symbol template SVG (27 weight x scale variants)."""
    margins, symbols = [], []
    for scale, f in SCALE.items():
        def up(q: Pt) -> Pt:
            return q[0] * f, CAP_MID + (q[1] - CAP_MID) * f

        for i, weight in enumerate(WEIGHTS):
            # geometry at S with the stroke in S units, then scaled about the cap-height centre
            layers = [[c.mapped(up) for c in layer] for layer in GLYPHS[name](STROKE[scale][i] / f)]
            xs = [p[0] for layer in layers for c in layer for p in c.points()]
            x0, x1 = min(xs), max(xs)
            left = 560.0 + 296.7 * i + x0             # the weight's column
            gid = f"{weight}-{scale}"
            for side, x in (("left", left), ("right", left + x1 - x0)):
                margins.append(f'  <rect height="2200" id="{side}-margin-{gid}" style="fill:#00AEEF;stroke:none;opacity:0.4;" width="0.5" x="{x:.3f}" y="1"/>')
            paths = []
            for j, layer in enumerate(layers):
                role = "primary" if j == 0 else "secondary"
                d = "".join(c.svg(dx=-x0) for c in layer)
                paths.append(f'   <path class="monochrome-{j} hierarchical-{j}:{role}" d="{d}"/>')
            body = "\n".join(paths)
            symbols.append(f'  <g id="{gid}" transform="matrix(1 0 0 1 {left:.3f} {BASELINE[scale]:.0f})">\n{body}\n  </g>')
    rules = [f'  <line id="{kind}-{scale}" style="fill:none;stroke:#27AAE1;opacity:1;stroke-width:0.5;" x1="263" x2="3036" y1="{y:g}" y2="{y:g}"/>'
             for scale, base in BASELINE.items() for kind, y in (("Baseline", base), ("Capline", base - CAP))]
    guides = "\n".join(rules + margins)
    glyphs = "\n".join(symbols)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="3300" height="2200">
 <!--glyph: "{name}", point size: 100.0, generated by ios/scripts/glyphs.py-->
 <g id="Notes">
  <rect height="2200" id="artboard" style="fill:white;opacity:1" width="3300" x="0" y="0"/>
  <text style="stroke:none;fill:black;font-family:sans-serif;font-size:13;" transform="matrix(1 0 0 1 263 1933)">Template v.2.0</text>
  <text style="stroke:none;fill:black;font-family:sans-serif;font-size:13;" transform="matrix(1 0 0 1 263 1951)">Generated by ios/scripts/glyphs.py; edit the script, not this file</text>
 </g>
 <g id="Guides">
{guides}
 </g>
 <g id="Symbols">
{glyphs}
 </g>
</svg>
"""


def write_catalog(root: Path) -> None:
    """Writes <root>/<name>.symbolset/{<name>.svg, Contents.json} for every glyph."""
    for name in GLYPHS:
        d = root / f"{name}.symbolset"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.svg").write_text(template(name))
        (d / "Contents.json").write_text(
            '{\n  "info" : { "author" : "xcode", "version" : 1 },\n'
            f'  "symbols" : [ {{ "filename" : "{name}.svg", "idiom" : "universal" }} ]\n}}\n')


if __name__ == "__main__":
    default = Path(__file__).resolve().parent.parent / "Print" / "Assets.xcassets"
    write_catalog(Path(sys.argv[1]) if len(sys.argv) > 1 else default)
