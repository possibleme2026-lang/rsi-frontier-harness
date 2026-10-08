"""How often does an agent *choose* to submit an empty artifact?

The empty-artifact submit guard is only worth its turn if agents actually do this.  The
three zero-byte repository failures in the reported configuration are not evidence: they ran
out of steps and were auto-submitted by the harness, which is a different situation and one
the guard cannot help with, because the guard only speaks when the agent calls submit itself.

So this counts the trials where `exit_reason == "submitted"` -- the agent's own decision --
and the collected artifact was empty or contained no product file.  That is the population
the guard can act on, and if it is empty the mechanism is speculation and should be labelled
as such rather than shipped as a fix.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys_path_added = False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-run", default=None, help="restrict to one run directory")
    args = parser.parse_args()

    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from rsih.agent.tools import _is_product_path

    rows = []
    patterns = [args.min_run] if args.min_run else [p.name for p in (ROOT / "runs").iterdir() if p.is_dir()]
    for name in patterns:
        for path in (ROOT / "runs" / name).glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if trial["status"] not in ("success", "failure"):
                continue
            # Only this suite collects a diff.  A terminal-bench trial reports zero bytes
            # because no collect step is defined, not because the agent changed nothing, and
            # counting those as "empty submits" would overstate the guard's population by
            # two orders of magnitude -- which is what an earlier version of this tool did.
            if not trial["id"].startswith("datacurve/"):
                continue
            rows.append(
                {
                    "run": name,
                    "task": trial["id"],
                    "exit": trial.get("exit_reason"),
                    "bytes": trial.get("submitted_bytes") or 0,
                    "status": trial["status"],
                }
            )

    scored = len(rows)
    submitted = [r for r in rows if r["exit"] == "submitted"]
    empty_submit = [r for r in submitted if r["bytes"] == 0]
    limit_exits = [r for r in rows if r["exit"] in ("step_limit", "wall_clock_budget")]
    empty_limit = [r for r in limit_exits if r["bytes"] == 0]

    print(f"scored trials                              : {scored}")
    print(f"the agent called submit itself             : {len(submitted)}")
    print(f"  of those, empty artifact                 : {len(empty_submit)}  <- the guard's target")
    print(f"the budget ended the episode for it        : {len(limit_exits)}")
    print(f"  of those, empty artifact                 : {len(empty_limit)}  <- the guard cannot help")
    print()
    if empty_submit:
        print("guard target population:")
        for row in sorted(empty_submit, key=lambda r: r["task"]):
            print(f"  {row['task']:<50} {row['status']:<8} {row['run']}")
    else:
        print("No trial in this repository shows an agent choosing to submit an empty diff.")
        print("The guard therefore has no measured target here and is a precaution, not a fix.")
    print()
    print("Artifact size is only meaningful for tasks that collect a diff; terminal-bench")
    print("tasks define no collect step, so their zeros are structural and are not counted")
    print("as empty.  The counts above are over all suites, which is generous to the guard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
