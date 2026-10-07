"""Compare two runs cell by cell: what one won, what it lost, what it cost.

A candidate genome is only interesting through the cells where it disagrees with the
incumbent, so this prints those first.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(run_dir: Path) -> dict[str, dict]:
    cells: dict[str, dict] = {}
    for path in sorted(run_dir.glob("trials/*/trial.json")):
        trial = json.loads(path.read_text(encoding="utf-8"))
        previous = cells.get(trial["id"])
        if previous is None or previous["status"] == "infra_invalid":
            cells[trial["id"]] = trial
    return cells


def load_many(spec: str) -> dict[str, dict]:
    """Merge one or more run directories, later ones overriding earlier ones."""
    cells: dict[str, dict] = {}
    for part in spec.split(","):
        for task, trial in load(Path(part.strip())).items():
            if cells.get(task, {}).get("status") != "success":
                cells[task] = trial
    return cells


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left")
    parser.add_argument("right")
    args = parser.parse_args()

    left = load_many(args.left)
    right = load_many(args.right)
    shared = sorted(set(left) & set(right))

    won, lost, same = [], [], 0
    for task in shared:
        a, b = left[task], right[task]
        if a["status"] == b["status"]:
            same += 1
        elif b["status"] == "success":
            won.append((task, a, b))
        elif a["status"] == "success":
            lost.append((task, a, b))

    def total(cells: dict[str, dict], tasks: list[str]) -> tuple[int, float]:
        passes = sum(1 for t in tasks if cells[t]["status"] == "success")
        cost = sum(cells[t].get("cost_usd") or 0.0 for t in tasks)
        return passes, cost

    lp, lc = total(left, shared)
    rp, rc = total(right, shared)
    print(f"{args.left:<24} {lp}/{len(shared)}  ${lc:.4f}")
    print(f"{args.right:<24} {rp}/{len(shared)}  ${rc:.4f}")
    print(f"\nidentical verdicts: {same}/{len(shared)}")
    for label, rows in (("WON by right", won), ("LOST by right", lost)):
        print(f"\n{label}: {len(rows)}")
        for task, a, b in rows:
            print(
                f"  {task:<46} {a['status']:<8}->{b['status']:<8}"
                f" turns {a['turns']}->{b['turns']}"
                f" ${a.get('cost_usd') or 0:.4f}->${b.get('cost_usd') or 0:.4f}"
            )
    only_left = sorted(set(left) - set(right))
    only_right = sorted(set(right) - set(left))
    if only_left:
        print(f"\nunmeasured by right: {len(only_left)}  {', '.join(only_left[:4])}...")
    if only_right:
        print(f"unmeasured by left: {len(only_right)}  {', '.join(only_right[:4])}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
