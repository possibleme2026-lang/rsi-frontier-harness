"""Which failures produced no artifact at all?

The question this answers is narrow and worth stating precisely, because the two halves of
the suite do not publish the same thing.

* The repository (`datacurve`) tasks grade the **git diff**, which the harness collects as
  `model.patch`.  A zero-byte collection there means the agent changed nothing, and that is
  exactly what the harness's artifact gate is meant to prevent.
* The `terminal-bench` tasks grade **container state in place** and define no collect step,
  so their collected artifact is empty by construction.  A zero there says nothing about
  whether the agent did any work, and reporting it as "produced nothing" would be wrong.

So the failure census is restricted to the half where the artifact is the deliverable, and
the terminal half is reported by turns and exit reason instead.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The configuration quoted in the write-up: gen1 over all 30 cells.
REPORTED_RUNS = ("gen0-probe-g0-gen0", "holdout-gen1", "close-polyglot", "deepswe-9")


def main() -> int:
    rows = []
    for run_name in REPORTED_RUNS:
        for path in (ROOT / "runs" / run_name).glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if trial["status"] != "failure":
                continue
            rows.append(
                {
                    "task": trial["id"],
                    "suite": trial["id"].split("/")[0],
                    "bytes": trial.get("submitted_bytes") or 0,
                    "turns": trial.get("turns") or 0,
                    "exit": trial.get("exit_reason"),
                }
            )

    diffs = [r for r in rows if r["suite"] == "datacurve"]
    terminal = [r for r in rows if r["suite"] == "terminal-bench"]

    print(f"failures: {len(rows)}  (datacurve {len(diffs)}, terminal-bench {len(terminal)})")
    print()
    print("repository tasks, where the collected diff IS the deliverable")
    print(f"{'task':<46}{'bytes':>10}{'turns':>7}  exit")
    for row in sorted(diffs, key=lambda r: r["bytes"]):
        note = "  <- nothing collected" if row["bytes"] == 0 else (
            "  <- scratch-only" if row["bytes"] < 4096 else ""
        )
        print(
            f"{row['task'].split('/')[-1][:44]:<46}{row['bytes']:>10}{row['turns']:>7}"
            f"  {row['exit']}{note}"
        )
    never = [r for r in diffs if r["bytes"] == 0]
    scratch = [r for r in diffs if 0 < r["bytes"] < 4096]
    print()
    print(f"  no artifact at all : {len(never)}/{len(diffs)}")
    print(f"  scratch-sized only : {len(scratch)}/{len(diffs)}")
    print(f"  a real attempt     : {len(diffs) - len(never) - len(scratch)}/{len(diffs)}")
    print()
    print("terminal tasks: no collect step is defined, so artifact size is not evidence")
    print(f"{'task':<46}{'turns':>7}  exit")
    for row in sorted(terminal, key=lambda r: r["task"]):
        print(f"{row['task'].split('/')[-1][:44]:<46}{row['turns']:>7}  {row['exit']}")
    print()
    print("  -> for these, only the exit reason is informative; the artifact gate cannot")
    print("     judge them from a diff, and a terminal container that is not a git")
    print("     worktree makes the gate stay quiet rather than guess.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
