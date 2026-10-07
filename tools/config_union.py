"""What would a per-task choice between two configurations have scored?

Two genomes have now been run over the same 30 cells and they disagree on six of them:
`gen1` (60 steps) wins anko, fastapi and sanitize-git-repo; `gen6` (100 steps plus a
self-check block) wins katex, python-statemachine and extract-elf.  Neither is better
overall — both are 18/30.

If a rule could pick the right one per task, the union is the score.  This computes that
union, and also the union with the third and fourth configurations that were run over
subsets, so the ceiling is visible before spending anything on a selector.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SETS = {
    "gen1 (60 steps)": ["runs/gen0-probe-g0-gen0", "runs/holdout-gen1",
                        "runs/close-polyglot", "runs/deepswe-9"],
    "gen6 (100 steps + self-check)": ["runs/gen6-full"],
    "gen1-steps100 (100 steps)": ["runs/attr-100"],
    "gen1-vreq (+verify.requirements)": ["runs/attr-vreq"],
    "gen1-sum (+compaction=summarize)": ["runs/attr-sum"],
}


def outcomes(runs: list[str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for run in runs:
        for path in (ROOT / run).glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if trial["status"] not in ("success", "failure"):
                continue
            if merged.get(trial["id"]) != "success":
                merged[trial["id"]] = "pass" if trial["status"] == "success" else "fail"
    return merged


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--union-of", nargs="+", default=None,
                        help="configuration names to union; default: all")
    args = parser.parse_args()

    table = {name: outcomes(runs) for name, runs in SETS.items()}
    names = list(table)

    print(f"{'task':<46}" + "".join(f"{n.split(' ')[0]:>12}" for n in names))
    for task in sorted(set().union(*[set(v) for v in table.values()])):
        row = "".join(
            f"{table[n].get(task, '-'):>12}" for n in names
        )
        print(f"{task:<46}{row}")

    print()
    for name in names:
        cells = table[name]
        passes = sum(1 for v in cells.values() if v == "pass")
        print(f"{name:<34}{passes:>3}/{len(cells):<3} on the cells it ran")

    chosen = args.union_of or names
    union_cells = [t for t in set().union(*[set(table[n]) for n in chosen])
                   if all(t in table[n] for n in chosen)]
    union = sum(1 for t in union_cells
                if any(table[n][t] == "pass" for n in chosen))
    print(f"\nunion over {len(chosen)} configurations on the {len(union_cells)} cells "
          f"all of them ran: {union}/{len(union_cells)} = {union / len(union_cells):.1%}")
    disagreements = [t for t in union_cells
                     if len({table[n][t] for n in chosen}) > 1]
    print(f"cells where they disagree: {len(disagreements)}")
    for task in disagreements:
        detail = "  ".join(f"{n.split(' ')[0]}={table[n][task]}" for n in chosen)
        print(f"  {task:<46}{detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
