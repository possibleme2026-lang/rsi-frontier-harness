"""Paired comparison of two runs on the tasks they share.

Used for the one comparison that matters: the seed and the candidate genome on the
holdout set, where neither was selected on the outcome.  Prints the discordant cells
explicitly, because the verdict of the gate is entirely a statement about those cells
and nothing about the rest.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def load(run: Path) -> dict[str, dict]:
    cells: dict[str, dict] = {}
    for trial_path in sorted(run.glob("trials/*/trial.json")):
        trial = json.loads(trial_path.read_text(encoding="utf-8"))
        cells[trial["id"]] = trial
    return cells


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left", help="runs/<run-id>")
    parser.add_argument("right", help="runs/<run-id>")
    parser.add_argument("--z", type=float, default=2.0)
    parser.add_argument("--cost-margin", type=float, default=0.85)
    args = parser.parse_args()

    left_run, right_run = Path(args.left), Path(args.right)
    left, right = load(left_run), load(right_run)
    shared = [i for i in left if i in right and left[i]["status"] != "infra_invalid" and right[i]["status"] != "infra_invalid"]
    if not shared:
        print("no shared valid cells")
        return 1

    print(f"{'task':<46}{'left':>8}{'right':>8}{'$left':>10}{'$right':>10}")
    b = c = 0
    left_cost = right_cost = 0.0
    for task_id in sorted(shared):
        lt, rt = left[task_id], right[task_id]
        lp = lt["status"] == "success"
        rp = rt["status"] == "success"
        b += (not lp) and rp
        c += lp and (not rp)
        lc, rc = lt.get("cost_usd") or 0.0, rt.get("cost_usd") or 0.0
        left_cost += lc
        right_cost += rc
        flag = "  <-- flipped" if lp != rp else ""
        print(
            f"{task_id.split('/')[-1]:<46}{'pass' if lp else 'fail':>8}{'pass' if rp else 'fail':>8}"
            f"{lc:>10.4f}{rc:>10.4f}{flag}"
        )
    n = len(shared)
    diff = (b - c) / n
    floor = args.z * math.sqrt(b + c) / n
    print(
        f"\ncells={n} left={sum(1 for i in shared if left[i]['status'] == 'success')}/{n} "
        f"right={sum(1 for i in shared if right[i]['status'] == 'success')}/{n}"
    )
    print(f"discordant b={b} c={c} diff={diff:+.3f} floor={floor:.3f} (z={args.z:g})")
    if b + c == 0:
        print("pass-rate verdict: identical")
    else:
        print(
            "pass-rate verdict: "
            + ("improvement clears the floor" if diff > floor else "within the noise floor")
        )
    ratio = (right_cost / left_cost) if left_cost else float("nan")
    print(
        f"cost: left=${left_cost:.4f} right=${right_cost:.4f} ratio={ratio:.3f} "
        f"(margin {args.cost_margin:g}) -> "
        + (
            "cost win"
            if ratio <= args.cost_margin and diff >= -floor
            else "no cost win"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
