"""Census of how episodes actually end, before changing anything.

The research on this benchmark says two things that should stop a harness author from
guessing: the Terminal-Bench 2 paper reports no correlation between turns-per-trial and
success, and SWE-agent reports that 93% of resolved instances submit before exhausting the
step budget.  So "ran out of steps" has to be counted, not assumed.

This aggregates every trial in the workspace: how episodes ended, how much of the step
budget they used, whether compaction ever fired, and — for the failures — whether the
agent had already produced something (a non-empty patch) when it ran out.
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="*", default=None,
                        help="run directories; default every runs/* except discarded ones")
    args = parser.parse_args()

    run_dirs = [ROOT / r for r in args.runs] if args.runs else sorted(
        p for p in (ROOT / "runs").glob("*")
        if p.is_dir() and not p.name.startswith("_")
    )

    trials: list[dict] = []
    for run in run_dirs:
        for path in run.glob("trials/*/trial.json"):
            try:
                trial = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            trial["_run"] = run.name
            trial["_dir"] = str(path.parent)
            trials.append(trial)

    scored = [t for t in trials if t["status"] in ("success", "failure")]
    print(f"trials on disk      : {len(trials)}")
    print(f"scored (s/f)        : {len(scored)}")
    print(f"infra_invalid       : {len(trials) - len(scored)}")
    print()

    for label, group in (("ALL", scored),
                         ("passed", [t for t in scored if t["status"] == "success"]),
                         ("failed", [t for t in scored if t["status"] == "failure"])):
        counts = collections.Counter(t.get("exit_reason") or "?" for t in group)
        total = len(group) or 1
        parts = " ".join(
            f"{name}={n} ({n / total:.0%})" for name, n in counts.most_common()
        )
        print(f"{label:<8} n={len(group):<5} {parts}")
    print()

    failed = [t for t in scored if t["status"] == "failure"]
    step_limited = [t for t in failed if t.get("exit_reason") == "step_limit"]
    print(f"failures that hit the step cap : {len(step_limited)}/{len(failed)}")
    if step_limited:
        turns = [t.get("turns") or 0 for t in step_limited]
        print(f"  their turn counts            : median {statistics.median(turns):.0f}, "
              f"max {max(turns)}")
        with_bytes = [
            t for t in step_limited
            if (t.get("submitted_bytes") or 0) > 0
        ]
        print(f"  of those, a non-empty diff   : {len(with_bytes)}/{len(step_limited)}")

    submitted = [t for t in scored if t.get("exit_reason") == "submitted"]
    if submitted:
        passed = sum(1 for t in submitted if t["status"] == "success")
        print(f"\nepisodes that ended by submitting: {len(submitted)} "
              f"({passed} passed = {passed / len(submitted):.0%})")
    limited = [t for t in scored if t.get("exit_reason") not in (None, "submitted")]
    if limited:
        passed = sum(1 for t in limited if t["status"] == "success")
        print(f"episodes that ended at a limit   : {len(limited)} "
              f"({passed} passed = {passed / len(limited):.0%})")

    compactions = sum(t.get("compactions") or 0 for t in trials)
    fired = [t for t in trials if (t.get("compactions") or 0) > 0]
    print(f"\ncompaction events total          : {compactions}")
    print(f"episodes where compaction fired  : {len(fired)}/{len(trials)}")

    durations = [t.get("duration_seconds") for t in scored if t.get("duration_seconds")]
    if durations:
        print(f"duration seconds                 : median "
              f"{statistics.median(durations):.0f}, mean {statistics.fmean(durations):.0f}, "
              f"max {max(durations):.0f}")

    by_exit: dict[str, list[float]] = collections.defaultdict(list)
    for trial in scored:
        if trial.get("duration_seconds"):
            by_exit[trial.get("exit_reason") or "?"].append(trial["duration_seconds"])
    print("\nmedian duration by exit reason")
    for reason, values in sorted(by_exit.items(), key=lambda kv: -len(kv[1])):
        print(f"  {reason:<20} n={len(values):<4} median {statistics.median(values):>7.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
