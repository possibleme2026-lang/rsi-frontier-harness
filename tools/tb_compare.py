"""Per-cell terminal-bench comparison between the reported configuration and a candidate.

The repository half has one run per configuration; the terminal half has many, spread over
several run directories from earlier experiments.  This collects every scored trial of the
baseline genome across all of them and lines it up against one candidate run, so a cell is
only reported as won or lost when both sides have actually been measured.  Cells the
baseline was run more than once on are marked, because a 1-of-2 cell cannot carry a verdict.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BASELINE_GENOME_ID = "gen1"


def load_trials(pattern: str) -> dict[str, list[dict]]:
    cells: dict[str, list[dict]] = collections.defaultdict(list)
    for run_dir in sorted((ROOT / "runs").glob(pattern)):
        for path in run_dir.glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if trial["status"] not in ("success", "failure"):
                continue
            trial["_run"] = run_dir.name
            cells[trial["id"]].append(trial)
    return cells


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", default="gen7-tb")
    parser.add_argument("--suite", default="terminal-bench")
    parser.add_argument(
        "--baseline-genome",
        default=BASELINE_GENOME_ID,
        help="gen6 is the only configuration with a single clean 21-cell terminal-bench "
        "run, so it makes the tightest comparison even though it differs from gen1 in two "
        "ways; gen1 is the reported harness but its terminal half is pooled over runs",
    )
    args = parser.parse_args()

    baseline = load_trials("*")
    candidate = {
        task: trials
        for task, trials in load_trials(args.candidate).items()
        if task.startswith(args.suite + "/")
    }
    if not candidate:
        print(f"{args.candidate}: no {args.suite} trials yet")
        return 0

    print(f"{'task':<34}{'baseline':>22}{'candidate':>12}   verdict")
    won = lost = same_pass = same_fail = 0
    for task in sorted(candidate):
        base = [t for t in baseline.get(task, []) if t.get("genome_id") == args.baseline_genome]
        cand = candidate[task][0]
        cand_pass = cand["status"] == "success"
        if not base:
            print(f"{task.split('/')[-1][:32]:<34}{'not measured':>22}"
                  f"{'pass' if cand_pass else 'fail':>12}   uncomparable")
            continue
        base_pass = sum(1 for t in base if t["status"] == "success")
        note = f"{base_pass}/{len(base)}" + ("*" if len(base) > 1 and 0 < base_pass < len(base) else "")
        if base_pass == len(base):
            verdict = "held" if cand_pass else "LOST"
            if cand_pass:
                same_pass += 1
            else:
                lost += 1
        elif base_pass == 0:
            if cand_pass:
                verdict = "WON"
                won += 1
            else:
                verdict = "still failing"
                same_fail += 1
        else:
            verdict = "mixed baseline" if cand_pass else "mixed baseline"
        print(f"{task.split('/')[-1][:32]:<34}{note:>22}"
              f"{'pass' if cand_pass else 'fail':>12}   {verdict}")

    measured = won + lost + same_pass + same_fail
    print()
    print(f"cells with a baseline verdict: {measured}")
    print(f"  baseline passed, candidate passed (held) : {same_pass}")
    print(f"  baseline passed, candidate failed (LOST) : {lost}")
    print(f"  baseline failed, candidate passed (WON)  : {won}")
    print(f"  both failed                              : {same_fail}")
    if measured:
        print(f"  net                                      : {won - lost:+d}")
    print()
    print("* = the baseline was run more than once on this cell with both outcomes, so a")
    print("    single candidate run cannot settle it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

