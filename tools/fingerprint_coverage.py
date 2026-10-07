"""How much of each suite does a given genome fingerprint actually cover?

The reported 30-task table was assembled from several runs of the same configuration rather
than from one run of all thirty cells, so before a new configuration is compared against it,
the coverage of the baseline has to be stated.  This prints, per suite, which cells the
fingerprint has been measured on and what the verdict was, so an unmeasured cell is visible
as unmeasured instead of being silently absent.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = Path(r"D:\codebase\agentharness\_ref-frontier-eval\benchmark.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--genome-id",
        default="gen1",
        help="matches the genome_id recorded on each trial, which is stable across the "
        "fingerprint rewrite; a fingerprint recorded before that rewrite no longer matches",
    )
    parser.add_argument("--fingerprint", default=None, help="optional extra constraint")
    parser.add_argument("--label", default=None)
    args = parser.parse_args()
    label = args.label or args.genome_id

    tasks = json.loads(BENCHMARK.read_text(encoding="utf-8"))["task_ids"]
    trials: dict[str, list[dict]] = collections.defaultdict(list)
    for run_dir in sorted((ROOT / "runs").glob("*")):
        if not run_dir.is_dir():
            continue
        for path in run_dir.glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if trial.get("genome_id") != args.genome_id:
                continue
            if args.fingerprint and trial.get("genome_fingerprint") != args.fingerprint:
                continue
            if trial["status"] not in ("success", "failure"):
                continue
            trial["_run"] = run_dir.name
            trials[trial["id"]].append(trial)

    missing = [t for t in tasks if t not in trials]
    covered = [t for t in tasks if t in trials]
    print(f"{label} (matched on genome_id)")
    print(f"  cells in the suite : {len(tasks)}")
    print(f"  cells measured     : {len(covered)}")
    print(f"  cells never run    : {len(missing)}")
    print()
    passes = 0
    for task in tasks:
        if task not in trials:
            print(f"  {'--':>5}  {task:<52} never run")
            continue
        group = trials[task]
        passed = sum(1 for t in group if t["status"] == "success")
        passes += 1 if passed else 0
        n = len(group)
        note = f"{passed}/{n}"
        if n > 1 and 0 < passed < n:
            note += " unstable"
        mark = "pass" if passed else "fail"
        print(f"  {mark:>5}  {task:<52} {note:<18} {', '.join(sorted({t['_run'] for t in group}))}")
    print()
    print(f"  cells passed (any run): {passes}")
    print()
    print("A cell that passed at least once is counted as passed here, which is the")
    print("generous reading; the 'unstable' marker shows where that matters.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
