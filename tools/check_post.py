"""Check the launch posts fit.

X counts a post at 280 characters for most scripts, but CJK characters count double, so a
Chinese post has an effective budget of 140 characters.  This measures both and reports
the worst offender, because a launch post that gets truncated at the interesting part is
not a launch post.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 280


def is_cjk(char: str) -> bool:
    code = ord(char)
    return (0x3000 <= code <= 0x9FFF) or (0xFF00 <= code <= 0xFFEF)


URL = r"(?:https?://\S+|\b[\w-]+\.[a-z]{2,6}/\S+)"


def weight(text: str) -> int:
    """X counts CJK as 2 and any URL as a fixed 23 regardless of length.

    The domain pattern requires an alphabetic TLD so that a price like ``0.28/$0.42`` is
    not mistaken for a link.
    """
    stripped = re.sub(URL, "", text)
    urls = len(re.findall(URL, text))
    return sum(2 if is_cjk(c) else 1 for c in stripped) + 23 * urls


def posts(path: Path) -> list[tuple[str, str]]:
    """Return (heading, body) for every post in the file."""
    found: list[tuple[str, str]] = []
    current: str | None = None
    buffer: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\*\*\d+/\d+\*\*", stripped) or stripped == "## Single post":
            if current is not None:
                found.append((current, "\n".join(buffer).strip()))
            current = stripped
            buffer = []
            continue
        if stripped.startswith("## ") or stripped.startswith("---"):
            if current is not None:
                found.append((current, "\n".join(buffer).strip()))
            current = None
            buffer = []
            continue
        if current is not None and stripped:
            buffer.append(stripped)
    if current is not None:
        found.append((current, "\n".join(buffer).strip()))
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=str(ROOT / "LAUNCH.md"))
    args = parser.parse_args()

    worst = 0
    for heading, body in posts(args.path):
        count = weight(body)
        if "Long-form" in heading:
            print(f"SKIP {heading:<14}{count:>5} / {LIMIT}  (intentionally long)")
            continue
        worst = max(worst, count)
        flag = "OK  " if count <= LIMIT else "OVER"
        print(f"{flag} {heading:<14}{count:>5} / {LIMIT}")
    print(f"\nworst post: {worst} weighted characters")
    return 0 if worst <= LIMIT else 1


if __name__ == "__main__":
    raise SystemExit(main())
