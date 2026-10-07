"""Pull the published chart's per-configuration colours and marker shapes.

Their asset encodes one colour and one marker per configuration; reusing them means a
reader who knows the original chart recognises every point except the new one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ASSET = (Path(__file__).resolve().parents[2] / "_ref-frontier-eval" / "assets"
         / "frontier-harness-chart.svg")
OUT = Path(__file__).resolve().parents[1] / "assets" / "published-style.json"


def marker(block: str) -> tuple[str, str] | None:
    """Return (colour, shape) of the marker element, skipping the label backdrop."""
    for element in re.findall(r"<(circle|path|rect)\b[^>]*>", block):
        pass
    for match in re.finditer(r"<(circle|path|rect)\b([^>]*)>", block):
        tag, attrs = match.group(1), match.group(2)
        fill = re.search(r'fill="(#[0-9a-fA-F]{6}|none)"', attrs)
        if not fill or fill.group(1) == "#020202":
            continue
        if tag == "circle":
            return fill.group(1), "circle"
        if tag == "rect":
            return fill.group(1), "square"
        points = re.findall(r"[ML]\s*[\d.]+", attrs)
        return fill.group(1), {3: "triangle", 4: "diamond"}.get(len(points), "path")
    return None


def main() -> int:
    svg = ASSET.read_text(encoding="utf-8")
    style: dict[str, dict] = {}
    for block in re.findall(r"<g>.*?</g>", svg, re.S):
        name = re.search(r'<tspan[^>]*>([^<]+)</tspan>', block)
        value = re.search(r'class="point-value"[^>]*>([^<]+)</tspan>', block)
        found = marker(block)
        if not (name and found):
            continue
        colour, shape = found
        style[name.group(1).strip()] = {
            "colour": colour,
            "shape": shape,
            "printed": value.group(1).strip() if value else None,
        }
    for name, entry in style.items():
        print(f"{name:<16}{entry['colour']}  {entry['shape']:<9}{entry['printed']}")
    OUT.write_text(json.dumps(style, indent=2), encoding="utf-8")
    print(f"\n{len(style)} configurations -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
