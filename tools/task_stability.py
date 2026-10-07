"""Collect every trial recorded for one task across runs, to see how stable it is.

A single pass on a single run is not a harness result if re-runs disagree, so the
reports need a way to show that disagreement rather than average it away.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--runs", default="runs")
    parser.add_argument("--detail", action="store_true", help="show the failing test names")
    args = parser.parse_args()

    rows = []
    for run_dir in sorted(Path(args.runs).iterdir()):
        if not run_dir.is_dir():
            continue
        for trial_path in run_dir.glob(f"trials/*{args.task}*/trial.json"):
            trial = json.loads(trial_path.read_text(encoding="utf-8"))
            if args.task not in trial["id"]:
                continue
            rows.append((run_dir.name, trial, trial_path.parent))
    if not rows:
        print("no trials found")
        return 1

    passes = 0
    valid = 0
    print(f"{'run':<30}{'status':<14}{'turns':>6}{'cost':>9}  failing test")
    for run, trial, directory in sorted(rows, key=lambda row: row[0]):
        detail = ""
        if args.detail:
            log = directory / "verifier.log"
            if log.exists():
                for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("FAILED "):
                        detail = line.split("::")[-1].split(" ")[0]
                        break
        print(
            f"{run:<30}{trial['status']:<14}{trial['turns']:>6}"
            f"{trial.get('cost_usd') or 0:>9.4f}  {detail}"
        )
        valid += trial["status"] in ("success", "failure")
        passes += trial["status"] == "success"
    print(f"\n{passes}/{valid} valid runs passed; {len(rows) - valid} infra_invalid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
