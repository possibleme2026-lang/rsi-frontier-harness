"""Draw the FrontierHarness Eval cost/pass chart with RSIH added.

The published chart plots each configuration's pass rate against its effective cost per
pass on a log axis, with one colour and one marker per configuration.  This reproduces
that chart and extends the x axis two decades to the left, because every published
configuration sits between $1.05 and $18.34 per pass and the harness measured here sits
at $0.098.

It also plots a second RSIH point: the same measured tokens re-priced on the frozen Kimi
K3 card the baselines used.  The gap between the two RSIH points is what the model's
price contributes; the distance from the repriced point to the published ones is what the
harness contributes.

Two renderers, one layout: SVG (vector, same style as the published asset) and PNG
(rasterised at 3x and downsampled, because that is what a browser and a chat window can
show inline).
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WIDTH, HEIGHT = 1200, 660
LEFT, RIGHT, TOP, BOTTOM = 76, 1178, 74, 556
X_MIN, X_MAX = 0.02, 40.0
Y_MIN, Y_MAX = 0.48, 0.70
X_TICKS = [0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20]
Y_TICKS = [0.50, 0.55, 0.60, 0.65, 0.70]
X_LABELS = {0.02: "$0.02", 0.05: "$0.05", 0.1: "$0.10", 0.2: "$0.20", 0.5: "$0.50",
            1: "$1", 2: "$2", 5: "$5", 10: "$10", 20: "$20"}

TITLE = "FrontierHarness Eval v1 · 30 tasks"
SUBTITLE = ("pass rate against effective cost per pass · x is logarithmic · "
            "21 terminal-bench + 9 datacurve")
FOOT1 = ("RSIH: 30/30 cells measured here with DeepSeek-V4.1-Flash @ tierflow.cn · "
         "every other point is read from the eval's own results file (Kimi K3)")
FOOT2 = ("the published asset labels this axis \"median cost per task\" but its plotted "
         "values are effective cost per pass, which is what this chart uses")
LEGEND = [
    ("RSIH (this harness)", "measured here · DeepSeek-V4.1-Flash"),
    ("RSIH, Kimi K3 rate card", "same tokens, their prices"),
    ("RSIH gen6 (long budget)", "more steps, same score, +20% spend"),
]

BG = "#020202"
FG = "#ececec"
GRID = "#323232"
OURS = "#4ade80"
OURS_DIM = "#22c55e"

# The published asset's names, in the order chart-data.json emits them.
STYLE_KEY = {
    "codex": "Codex",
    "dsh-creator": "DSH Creator",
    "claude-code": "Claude Code",
    "pi-responses": "Pi",
    "dsh-ptc": "DSH PTC",
    "dsh-standard": "DSH Standard",
    "oh-my-pi": "Oh My Pi",
    "kimi-code": "Kimi Code",
    "dsh-minimal": "DSH Minimal",
    "exo": "Exo Harness",
    "opencode": "OpenCode",
    "hermes": "Hermes",
}

SHAPE_RADIUS = {"circle": 8.5, "triangle": 10.0, "square": 8.5, "diamond": 10.0,
                "path": 9.5}
RING_RADIUS = 7.5


def sx(cost: float) -> float:
    lo, hi = math.log10(X_MIN), math.log10(X_MAX)
    return LEFT + (math.log10(cost) - lo) / (hi - lo) * (RIGHT - LEFT)


def sy(rate: float) -> float:
    return BOTTOM - (rate - Y_MIN) / (Y_MAX - Y_MIN) * (BOTTOM - TOP)


@dataclass
class Point:
    label: str
    rate: float
    cost: float
    colour: str
    shape: str
    note: str = ""
    emphasis: bool = False
    ring: bool = False
    box: tuple[float, float, float, float] | None = field(default=None, repr=False)
    leader: bool = field(default=False, repr=False)

    @property
    def x(self) -> float:
        return sx(self.cost)

    @property
    def y(self) -> float:
        return sy(self.rate)

    @property
    def radius(self) -> float:
        return 20.0 if self.emphasis else SHAPE_RADIUS.get(self.shape, 9.0) + 4


def load_points(price_repriced: float | None) -> list[Point]:
    rows = json.loads((ROOT / "assets" / "chart-data.json").read_text(encoding="utf-8"))
    style = json.loads((ROOT / "assets" / "published-style.json").read_text(encoding="utf-8"))
    points: list[Point] = []
    for row in rows:
        if row["kind"] == "published":
            key = STYLE_KEY.get(row["name"])
            if key is None or key not in style:
                continue
            points.append(
                Point(
                    label=key,
                    rate=row["pass_rate"],
                    cost=row["cost_per_pass_usd"],
                    colour=style[key]["colour"],
                    shape=style[key]["shape"],
                )
            )
    for row in rows:
        if row["kind"] != "ours":
            continue
        if row["name"].startswith("rsih gen1"):
            points.append(
                Point(label="RSIH", rate=row["pass_rate"],
                      cost=row["cost_per_pass_usd"], colour=OURS, shape="circle",
                      emphasis=True)
            )
            if price_repriced:
                points.append(
                    Point(label="RSIH @ Kimi K3 card", rate=row["pass_rate"],
                          cost=price_repriced, colour=OURS_DIM, shape="circle",
                          ring=True)
                )
        elif row["name"].startswith("rsih gen6"):
            points.append(
                Point(label="RSIH gen6", rate=row["pass_rate"],
                      cost=row["cost_per_pass_usd"], colour=OURS_DIM, shape="diamond",
                      ring=True)
            )
    return points


def place_labels(points: list[Point], char_w: float = 7.6, line_h: float = 15.0) -> None:
    """Place each label near its marker, avoiding every marker and every other label.

    Greedy: candidates are eight directions at two distances; the first that touches
    nothing wins, otherwise the least-overlapping one.  A label that had to travel gets a
    leader line back to its marker.
    """
    width_of = lambda text: len(text) * char_w  # noqa: E731
    markers = [(p.x - p.radius, p.y - p.radius, p.x + p.radius, p.y + p.radius)
               for p in points]
    placed: list[tuple[float, float, float, float]] = []

    for point in sorted(points, key=lambda p: p.cost):
        name = point.label
        value = f"{point.rate:.1%} · ${point.cost:,.2f}"
        w = max(width_of(name), width_of(value)) + 8
        h = line_h * 2 + 4
        gap = point.radius + 9
        candidates: list[tuple[float, float]] = []
        for distance in (gap, gap + 26, gap + 52):
            candidates += [
                (point.x + distance, point.y - h / 2),
                (point.x - distance - w, point.y - h / 2),
                (point.x - w / 2, point.y - distance - h),
                (point.x - w / 2, point.y + distance),
                (point.x + distance * 0.72, point.y - distance * 0.72 - h),
                (point.x - distance * 0.72 - w, point.y - distance * 0.72 - h),
                (point.x + distance * 0.72, point.y + distance * 0.72),
                (point.x - distance * 0.72 - w, point.y + distance * 0.72),
            ]

        best: tuple[float, tuple[float, float, float, float]] | None = None
        for index, (dx, dy) in enumerate(candidates):
            box = (dx, dy, dx + w, dy + h)
            if box[0] < LEFT + 2 or box[2] > RIGHT - 2:
                continue
            if box[1] < TOP - 8 or box[3] > BOTTOM + 10:
                continue
            score = 0.0
            for marker in markers:
                if marker[0] <= point.x <= marker[2] and marker[1] <= point.y <= marker[3]:
                    continue
                score += _overlap_area(box, marker)
            for other in placed:
                score += _overlap_area(box, other) * 3
            if score == 0:
                best = (0.0, box)
                break
            if best is None or score < best[0]:
                best = (score, box)
        assert best is not None, f"no room for {name}"
        point.box = best[1]
        point.leader = edge_distance(best[1], point) > 34
        placed.append(best[1])


def edge_distance(box: tuple[float, float, float, float], point: Point) -> float:
    dx = max(box[0] - point.x, point.x - box[2], 0.0)
    dy = max(box[1] - point.y, point.y - box[3], 0.0)
    return math.hypot(dx, dy)


def _overlap_area(a, b, pad: float = 4.0) -> float:
    dx = min(a[2], b[2]) - max(a[0], b[0]) + pad
    dy = min(a[3], b[3]) - max(a[1], b[1]) + pad
    return dx * dy if dx > 0 and dy > 0 else 0.0


def marker_path(shape: str, x: float, y: float, radius: float | None = None) -> str:
    r = radius if radius is not None else SHAPE_RADIUS.get(shape, 9.0)
    if shape == "circle":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{{colour}}" stroke="#d8d8d8" stroke-width="1.2"/>'
    if shape == "square":
        s = r * 1.05
        return (f'<rect x="{x - s:.1f}" y="{y - s:.1f}" width="{2 * s:.1f}" '
                f'height="{2 * s:.1f}" fill="{{colour}}" stroke="#d8d8d8" stroke-width="1.2"/>')
    if shape == "triangle":
        pts = f"{x:.1f},{y - r:.1f} {x + r:.1f},{y + r * 0.8:.1f} {x - r:.1f},{y + r * 0.8:.1f}"
        return f'<polygon points="{pts}" fill="{{colour}}" stroke="#d8d8d8" stroke-width="1.2"/>'
    if shape == "diamond":
        pts = (f"{x:.1f},{y - r:.1f} {x + r:.1f},{y:.1f} {x:.1f},{y + r:.1f} "
               f"{x - r:.1f},{y:.1f}")
        return f'<polygon points="{pts}" fill="{{colour}}" stroke="#d8d8d8" stroke-width="1.2"/>'
    import math as _m
    pts = " ".join(
        f"{x + r * _m.cos(_m.radians(60 * i)):.1f},{y + r * _m.sin(_m.radians(60 * i)):.1f}"
        for i in range(6)
    )
    return f'<polygon points="{pts}" fill="{{colour}}" stroke="#d8d8d8" stroke-width="1.2"/>'


def build_svg(points: list[Point], repriced: float | None) -> str:
    out: list[str] = []
    add = out.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
        f'aria-label="FrontierHarness Eval cost against pass rate, with RSIH added">')
    add(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{BG}"/>')
    add('<style>text{font-family:Arial,Helvetica,sans-serif}'
        '.mono,.axis,.point-value{font-family:"SFMono-Regular",Menlo,monospace}'
        f'.axis{{fill:{FG}}}.point-value{{fill:#bdbdbd}}</style>')

    add('<g class="axis">')
    for tick in X_TICKS:
        x = sx(tick)
        add(f'<line x1="{x:.1f}" y1="{TOP}" x2="{x:.1f}" y2="{BOTTOM}" stroke="{GRID}" '
            f'stroke-dasharray="3 3"/>')
        add(f'<text x="{x:.1f}" y="{BOTTOM + 22}" text-anchor="middle" font-size="12" '
            f'class="mono">{X_LABELS[tick]}</text>')
    for tick in Y_TICKS:
        y = sy(tick)
        add(f'<line x1="{LEFT}" y1="{y:.1f}" x2="{RIGHT}" y2="{y:.1f}" stroke="{GRID}" '
            f'stroke-dasharray="3 3"/>')
        add(f'<text x="{LEFT - 12}" y="{y + 4:.1f}" text-anchor="end" font-size="12" '
            f'class="mono">{tick:.0%}</text>')
    add('</g>')
    add(f'<path d="M {LEFT} {TOP} V {BOTTOM} H {RIGHT}" fill="none" stroke="#eeeeee" '
        f'stroke-width="1.25"/>')

    # the published frontier, and the same frontier with us on it
    published_frontier = [p for p in points if p.label in ("Exo Harness", "Codex")]
    if len(published_frontier) == 2:
        (a, b) = published_frontier
        add(f'<line x1="{a.x:.1f}" y1="{a.y:.1f}" x2="{b.x:.1f}" y2="{b.y:.1f}" '
            f'stroke="#ff7a12" stroke-width="1.6" stroke-dasharray="6 4" opacity="0.55"/>')
    ours = next((p for p in points if p.emphasis), None)
    codex = next((p for p in points if p.label == "Codex"), None)
    if ours and codex:
        add(f'<line x1="{ours.x:.1f}" y1="{ours.y:.1f}" x2="{codex.x:.1f}" '
            f'y2="{codex.y:.1f}" stroke="#ff7a12" stroke-width="2.2" '
            f'stroke-linecap="round"/>')

    rep = next((p for p in points if p.ring and p.label.startswith("RSIH, Kimi")), None)
    if ours and rep:
        add(f'<line x1="{ours.x:.1f}" y1="{ours.y:.1f}" x2="{rep.x:.1f}" '
            f'y2="{rep.y:.1f}" stroke="{OURS_DIM}" stroke-width="1.4" '
            f'stroke-dasharray="4 3" opacity="0.9"/>')

    for point in points:
        if point.leader and point.box is not None:
            bx, by, bw, bh = point.box
            tx = min(max(point.x, bx), bw)
            ty = min(max(point.y, by), bh)
            add(f'<line x1="{point.x:.1f}" y1="{point.y:.1f}" x2="{tx:.1f}" '
                f'y2="{ty:.1f}" stroke="{point.colour}" stroke-width="1" '
                f'opacity="0.5"/>')
    for point in points:
        if point.box is None:
            continue
        bx, by, bw, bh = point.box
        colour = point.colour
        weight = "700" if point.emphasis else "400"
        size = 14.5 if point.emphasis else 13.0
        add(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw - bx:.1f}" '
            f'height="{bh - by:.1f}" rx="3" fill="{BG}"/>')
        add(f'<text x="{bx + 4:.1f}" y="{by + 13:.1f}" fill="{colour}" '
            f'font-size="{size}" font-weight="{weight}">{point.label}</text>')
        add(f'<text x="{bx + 4:.1f}" y="{by + 28:.1f}" class="point-value" '
            f'font-size="11.5">{point.rate:.1%} · ${point.cost:,.2f}'
            f'{" per pass" if point.emphasis else ""}</text>')

    # markers last, so no label backdrop can cut a marker in half; ours on top of theirs
    for point in draw_order(points):
        fill = "none" if point.ring else point.colour
        radius = RING_RADIUS if point.ring else None
        shape = marker_path(point.shape, point.x, point.y, radius).replace("{colour}", fill)
        if point.ring:
            shape = shape.replace('stroke="#d8d8d8"', f'stroke="{point.colour}"')
        if point.emphasis:
            add(f'<circle cx="{point.x:.1f}" cy="{point.y:.1f}" r="17" fill="none" '
                f'stroke="{OURS}" stroke-width="1.2" opacity="0.45"/>')
        add(shape)

    add(f'<text x="24" y="34" fill="{FG}" font-size="19" font-weight="700">{TITLE}</text>')
    add(f'<text x="24" y="54" fill="#9d9d9d" font-size="12">'
        f'{SUBTITLE}</text>')
    legend_svg(add, points)
    add(f'<text x="{(LEFT + RIGHT) / 2:.0f}" y="{BOTTOM + 44}" fill="{FG}" '
        f'text-anchor="middle" font-size="13" class="mono">'
        f'Effective cost per pass (log scale)</text>')
    add(f'<text x="{LEFT}" y="{HEIGHT - 34}" fill="#9d9d9d" font-size="11.5" '
        f'class="mono">{FOOT1}</text>')
    add(f'<text x="{LEFT}" y="{HEIGHT - 14}" fill="#9d9d9d" font-size="11.5" '
        f'class="mono">{FOOT2}</text>')
    add(f'<text x="26" y="{(TOP + BOTTOM) / 2:.0f}" fill="{FG}" text-anchor="middle" '
        f'font-size="13" class="mono" transform="rotate(-90 26 '
        f'{(TOP + BOTTOM) / 2:.0f})">Pass rate</text>')
    add('</svg>')
    return "\n".join(out)


def draw_order(points: list[Point]) -> list[Point]:
    """Published markers first, then our hollow ones, then the emphasised one on top."""
    return (sorted(points, key=lambda p: (p.emphasis, p.ring))
            if len({p.emphasis for p in points}) > 1 else points)


def legend_anchor() -> float:
    longest = max(len(text) for _, text in LEGEND)
    return RIGHT - (230 + longest * 6.9)


def legend_svg(add, points: list[Point]) -> None:
    x0 = legend_anchor()
    for index, (name, note) in enumerate(LEGEND):
        y = 32 + index * 18
        point = next((p for p in points if p.label == name), None)
        if point is None:
            continue
        shape = marker_path(point.shape, x0 + 8, y - 4).replace(
            "{colour}", "none" if point.ring else point.colour)
        if point.ring:
            shape = shape.replace('stroke="#d8d8d8"', f'stroke="{point.colour}"')
        add(shape)
        add(f'<text x="{x0 + 24:.1f}" y="{y:.1f}" fill="{point.colour}" '
            f'font-size="12.5">{name}</text>')
        add(f'<text x="{x0 + 230:.1f}" y="{y:.1f}" fill="#9d9d9d" '
            f'font-size="11.5">{note}</text>')


def build_png(points: list[Point], repriced: float | None, out: Path,
              scale: int = 3, final: float = 2.0) -> None:
    from PIL import Image, ImageDraw, ImageFont

    def font(paths: list[str], size: float):
        for path in paths:
            try:
                return ImageFont.truetype(path, int(size * scale))
            except OSError:
                continue
        return ImageFont.load_default()

    sans = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]
    sans_bold = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]
    mono = ["C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf"]

    image = Image.new("RGB", (WIDTH * scale, HEIGHT * scale), BG)
    draw = ImageDraw.Draw(image)

    def S(value: float) -> float:
        return value * scale

    for tick in X_TICKS:
        x = sx(tick)
        _dashed(draw, (S(x), S(TOP)), (S(x), S(BOTTOM)), GRID, scale)
        _text(draw, (S(x), S(BOTTOM + 22)), X_LABELS[tick], font(mono, 12), "#ececec",
              anchor="ma")
    for tick in Y_TICKS:
        y = sy(tick)
        _dashed(draw, (S(LEFT), S(y)), (S(RIGHT), S(y)), GRID, scale)
        _text(draw, (S(LEFT - 12), S(y + 4)), f"{tick:.0%}", font(mono, 12), "#ececec",
              anchor="rm")
    draw.line([S(LEFT), S(TOP), S(LEFT), S(BOTTOM), S(RIGHT), S(BOTTOM)], fill="#eeeeee",
              width=max(1, int(1.25 * scale)))

    published_frontier = [p for p in points if p.label in ("Exo Harness", "Codex")]
    if len(published_frontier) == 2:
        a, b = published_frontier
        _dashed(draw, (S(a.x), S(a.y)), (S(b.x), S(b.y)), "#8a5a20", scale, dash=6)
    ours = next((p for p in points if p.emphasis), None)
    codex = next((p for p in points if p.label == "Codex"), None)
    if ours and codex:
        draw.line([S(ours.x), S(ours.y), S(codex.x), S(codex.y)], fill="#ff7a12",
                  width=max(2, int(2.2 * scale)))
    rep = next((p for p in points if p.ring and p.label.startswith("RSIH, Kimi")), None)
    if ours and rep:
        _dashed(draw, (S(ours.x), S(ours.y)), (S(rep.x), S(rep.y)), OURS_DIM, scale, dash=4)

    for point in points:
        if point.leader and point.box is not None:
            bx, by, bw, bh = point.box
            draw.line([S(point.x), S(point.y),
                       S(min(max(point.x, bx), bw)), S(min(max(point.y, by), bh))],
                      fill=point.colour, width=max(1, scale // 2))
    for point in points:
        if point.box is None:
            continue
        bx, by, bw, bh = (S(v) for v in point.box)
        draw.rounded_rectangle([bx, by, bw, bh], radius=int(3 * scale), fill=BG)
        size = 14.5 if point.emphasis else 13.0
        _text(draw, (bx + S(4), by + S(13)), point.label,
              font(sans_bold if point.emphasis else sans, size), point.colour, anchor="lm")
        _text(draw, (bx + S(4), by + S(28)),
              f"{point.rate:.1%} · ${point.cost:,.2f}"
              f"{' per pass' if point.emphasis else ''}",
              font(mono, 11.5), "#bdbdbd", anchor="lm")

    for point in draw_order(points):
        _marker(draw, point, scale, font)

    _text(draw, (S(24), S(34)), TITLE, font(sans_bold, 19), "#ececec", anchor="lm")
    _text(draw, (S(24), S(54)), SUBTITLE, font(sans, 12), "#9d9d9d", anchor="lm")

    x0 = legend_anchor()
    for index, (name, note) in enumerate(LEGEND):
        point = next((p for p in points if p.label == name), None)
        if point is None:
            continue
        y = 32 + index * 18
        _marker(draw, point, scale, font, override=(x0 + 8, y - 4, 7.0))
        _text(draw, (S(x0 + 24), S(y)), name, font(sans, 12.5), point.colour, anchor="lm")
        _text(draw, (S(x0 + 230), S(y)), note, font(sans, 11.5), "#9d9d9d", anchor="lm")

    _text(draw, (S((LEFT + RIGHT) / 2), S(BOTTOM + 44)),
          "Effective cost per pass (log scale)", font(mono, 13), "#ececec", anchor="mm")
    _text(draw, (S(LEFT), S(HEIGHT - 34)), FOOT1, font(mono, 11.5), "#9d9d9d", anchor="lm")
    _text(draw, (S(LEFT), S(HEIGHT - 14)), FOOT2, font(mono, 11.5), "#9d9d9d", anchor="lm")
    y_font = font(mono, 13)
    box = draw.textbbox((0, 0), "Pass rate", font=y_font)
    strip = Image.new("RGBA", (box[2] - box[0] + int(S(10)), box[3] - box[1] + int(S(10))),
                      (0, 0, 0, 0))
    ImageDraw.Draw(strip).text((S(5), S(5) - box[1]), "Pass rate", font=y_font,
                               fill="#ececec")
    strip = strip.rotate(90, expand=True)
    image.paste(strip, (int(S(26) - strip.width / 2),
                        int(S((TOP + BOTTOM) / 2) - strip.height / 2)), strip)

    size = (int(WIDTH * final), int(HEIGHT * final))
    image.resize(size, Image.LANCZOS).save(out)


def _marker(draw, point: Point, scale: int, font, override=None) -> None:
    r = (RING_RADIUS if point.ring else SHAPE_RADIUS.get(point.shape, 9.0)) * scale
    if override is not None:
        cx, cy, radius = override
        r = radius * scale
        x, y = cx * scale, cy * scale
    else:
        x, y = point.x * scale, point.y * scale
    fill = None if point.ring else point.colour
    outline = point.colour if point.ring else "#d8d8d8"
    width = max(1, int(1.2 * scale))
    if point.emphasis and override is None:
        rr = 17 * scale
        draw.ellipse([x - rr, y - rr, x + rr, y + rr], outline=OURS, width=width)
    if point.shape == "circle":
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill, outline=outline, width=width)
    elif point.shape == "square":
        s = r * 1.05
        draw.rectangle([x - s, y - s, x + s, y + s], fill=fill, outline=outline,
                       width=width)
    elif point.shape == "triangle":
        draw.polygon([(x, y - r), (x + r, y + r * 0.8), (x - r, y + r * 0.8)], fill=fill,
                     outline=outline)
    elif point.shape == "diamond":
        draw.polygon([(x, y - r), (x + r, y), (x, y + r), (x - r, y)], fill=fill,
                     outline=outline)
    else:
        pts = [(x + r * math.cos(math.radians(60 * i)), y + r * math.sin(math.radians(60 * i)))
               for i in range(6)]
        draw.polygon(pts, fill=fill, outline=outline)


def _dashed(draw, start, end, colour, scale: int, dash: int = 3) -> None:
    (x1, y1), (x2, y2) = start, end
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        return
    steps = int(length // (dash * scale)) + 1
    for i in range(steps):
        if i % 2:
            continue
        t0, t1 = i / steps, min((i + 1) / steps, 1.0)
        draw.line([x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0,
                   x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1],
                  fill=colour, width=max(1, scale // 2))


def _text(draw, xy, text, font, fill, anchor="la"):
    """Draw with a vertical-centre anchor, which PIL does not provide for 'm'."""
    if anchor.endswith("m") or anchor == "mm":
        box = draw.textbbox((0, 0), text, font=font)
        xy = (xy[0], xy[1] - (box[1] + box[3]) / 2)
        anchor = anchor[:-1] + "a" if anchor != "mm" else "ma"
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repriced", type=float, default=None,
                        help="our cost per pass re-priced on the Kimi K3 card")
    parser.add_argument("--svg", default=str(ROOT / "assets" / "frontier-harness-with-rsih.svg"))
    parser.add_argument("--png", default=str(ROOT / "assets" / "frontier-harness-with-rsih.png"))
    args = parser.parse_args()

    points = load_points(args.repriced)
    place_labels(points)
    Path(args.svg).write_text(build_svg(points, args.repriced), encoding="utf-8")
    build_png(points, args.repriced, Path(args.png))
    print(f"{len(points)} points")
    for point in sorted(points, key=lambda p: p.cost):
        print(f"  {point.label:<26}{point.rate:>7.1%}{point.cost:>10.4f}")
    print(f"\nwrote {args.svg}\nwrote {args.png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
