"""Would a paired cost gate, rather than a point ratio, have accepted the child?

The pass-rate gate has a floor; the cost gate as first written did not.  This computes
the paired statistic the cost gate would need - the mean per-task log cost ratio
against its own standard error - for any two runs, so the difference between the two
rules is visible on real data instead of asserted.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def costs(run: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    for path in sorted(run.glob("trials/*/trial.json")):
        trial = json.loads(path.read_text(encoding="utf-8"))
        if trial.get("cost_usd") is not None and trial["status"] != "infra_invalid":
            out[trial["id"]] = trial["cost_usd"]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left")
    parser.add_argument("right")
    parser.add_argument("--z", type=float, default=2.0)
    parser.add_argument("--margin", type=float, default=0.85)
    args = parser.parse_args()

    left, right = costs(Path(args.left)), costs(Path(args.right))
    shared = sorted(set(left) & set(right))
    if len(shared) < 2:
        print("need at least two shared cells")
        return 1

    pairs = [(left[t], right[t]) for t in shared if left[t] > 0 and right[t] > 0]
    n = len(pairs)
    # Total spend is the operational quantity, so the statistic that belongs under it is
    # the paired difference of per-task spend, not the ratio of two totals that one
    # expensive task can carry on its own.
    deltas = [right_cost - left_cost for left_cost, right_cost in pairs]
    mean = sum(deltas) / n
    variance = sum((value - mean) ** 2 for value in deltas) / (n - 1)
    sd = math.sqrt(variance)
    se = sd / math.sqrt(n)
    total_left = sum(left_cost for left_cost, _ in pairs)
    total_right = sum(right_cost for _, right_cost in pairs)
    logs = [math.log(right_cost / left_cost) for left_cost, right_cost in pairs]
    cheaper = sum(1 for value in deltas if value < 0)

    print(f"cells={n}  total ratio={total_right / total_left:.3f}  margin={args.margin:g}")
    print(
        f"paired difference: mean=${mean:+.5f} sd=${sd:.5f} se=${se:.5f} "
        f"t={mean / se:+.2f}  total=${total_right - total_left:+.5f}"
    )
    print(f"geometric mean ratio={math.exp(sum(logs) / n):.3f}  cheaper on {cheaper}/{n} cells")
    print("point-ratio rule  : " + ("accept" if total_right / total_left <= args.margin else "reject"))
    print(
        f"paired rule (z={args.z:g}): "
        + (
            "accept"
            if mean < -args.z * se and total_right / total_left <= args.margin
            else "reject"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
