"""Compare the eval's two cache-hit fields, because the report quotes one of them.

``cache_hit_rate_normalized`` and ``cache_hit_rate_typical`` are different statistics and
a report that says "our 96% vs theirs" has to say which one it means.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = (Path(__file__).resolve().parents[2] / "_ref-frontier-eval" / "results"
        / "eval-data.json")


def fmt(value: object) -> str:
    return f"{value:.4f}" if isinstance(value, (int, float)) else str(value)


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    print(f"{'harness':<15}{'normalized':>11}{'typical':>10}{'q1':>9}{'q3':>9}{'n':>5}")
    for harness in data["harnesses"]:
        get = harness.get
        print(
            f"{harness['name']:<15}{fmt(get('cache_hit_rate_normalized')):>11}"
            f"{fmt(get('cache_hit_rate_typical')):>10}{fmt(get('cache_hit_rate_typical_q1')):>9}"
            f"{fmt(get('cache_hit_rate_typical_q3')):>9}{str(get('cache_hit_rate_typical_n')):>5}"
        )
    print()
    for key in ("cache_hit_rate_normalized", "cache_hit_rate_typical",
                "cache_hit_rate_typical_q1", "cache_hit_rate_typical_q3"):
        print(f"overview.{key:<30}{fmt(data['overview'].get(key))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
