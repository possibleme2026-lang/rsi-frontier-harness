"""How much does a single cell move when nothing changes?

A cell that passes one time in four under an identical configuration cannot be used to
argue that a change won or lost it.  This collects every task that has been run at least
three times under the same genome and reports the spread, which sets the width of the error
bar the write-up has to respect.

Runs are grouped by (task, genome fingerprint).  Fingerprint is the right key rather than
genome id, because two ids can name the same configuration.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-runs", type=int, default=3)
    args = parser.parse_args()

    groups: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for run_dir in sorted((ROOT / "runs").iterdir()):
        if not run_dir.is_dir():
            continue
        for path in run_dir.glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if trial["status"] not in ("success", "failure"):
                continue
            groups[(trial["id"], trial.get("genome_fingerprint") or "?")].append(trial)

    repeated = {k: v for k, v in groups.items() if len(v) >= args.min_runs}
    if not repeated:
        print(f"no task has {args.min_runs} scored runs under one configuration")
        return 0

    print(f"{'task':<46}{'fp':>18}{'n':>4}{'pass':>7}{'credit':>9}  verdicts")
    unstable = 0
    for (task, fingerprint), trials in sorted(repeated.items(), key=lambda kv: kv[0][0]):
        n = len(trials)
        passes = sum(1 for t in trials if t["status"] == "success")
        credits = []
        for trial in trials:
            detail = trial.get("verifier_detail") or {}
            f2p, p2p = detail.get("f2p"), detail.get("p2p")
            if trial["status"] == "success":
                credits.append(1.0)
            elif f2p is None:
                credits.append(0.0)
            else:
                credits.append(min(0.99, float(f2p) * (1.0 if p2p is None else float(p2p))))
        seen = collections.Counter(t["status"] for t in trials)
        if 0 < passes < n:
            unstable += 1
        print(
            f"{task.split('/')[-1][:44]:<46}{fingerprint:>18}{n:>4}"
            f"{passes:>6}/{n:<3}{sum(credits) / n:>9.3f}  "
            + ", ".join(f"{k}x{v}" for k, v in sorted(seen.items()))
        )

    print()
    print(f"cells run {args.min_runs}+ times under one configuration: {len(repeated)}")
    print(f"of those, cells that both passed and failed: {unstable}")
    print()
    print("A cell in the second count cannot be cited as won or lost by a single run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
