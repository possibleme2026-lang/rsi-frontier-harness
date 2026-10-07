"""Both cost conventions for a set of runs, so the quoted total can name its convention.

`cost_usd` prices cache reads at the cache rate from the first call on;
`cost_first_cold_usd` re-prices the first call's cache reads at the fresh-input rate,
which is the convention the published baselines use. They differ, and a headline that
does not say which one it is cannot be compared with anything.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def cells(run_dirs: list[str]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for run in run_dirs:
        for path in sorted(Path(run).glob("trials/*/trial.json")):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if trial["status"] not in ("success", "failure"):
                continue
            previous = merged.get(trial["id"])
            if previous is None or previous["status"] != "success":
                merged[trial["id"]] = trial
    return merged


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args()
    found = cells(args.runs)

    warm = sum(t.get("cost_usd") or 0.0 for t in found.values())
    cold = sum(t.get("cost_first_cold_usd") or 0.0 for t in found.values())
    passes = sum(1 for t in found.values() if t["status"] == "success")
    print(f"cells                 : {len(found)}  ({passes} passed)")
    print(f"sum cost_usd          : ${warm:.4f}   per pass ${warm / passes:.4f}")
    print(f"sum cost_first_cold   : ${cold:.4f}   per pass ${cold / passes:.4f}")
    print(f"first-cold premium    : {cold / warm - 1:+.3%}")
    worst = sorted(
        found.items(),
        key=lambda kv: (kv[1].get("cost_first_cold_usd") or 0) - (kv[1].get("cost_usd") or 0),
        reverse=True,
    )[:3]
    print("\nlargest first-cold premiums:")
    for task, trial in worst:
        w = trial.get("cost_usd") or 0.0
        c = trial.get("cost_first_cold_usd") or 0.0
        print(f"  {task:<46} ${w:.4f} -> ${c:.4f}  (+{c - w:.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
