"""Audit a run's verifier logs for cells whose zero says nothing about the agent.

The task images contain no test runner: each `tests/test.sh` installs its own before
grading.  When that install fails, `test.sh` still writes `reward.txt = 0`, which looks
exactly like a task the agent failed.  This tool separates the two cases so a pass rate
is never deflated by our own network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.bench.runner import verifier_setup_failure  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", help="path to runs/<run-id>")
    args = parser.parse_args()

    run_dir = Path(args.run)
    suspicious = 0
    for trial_path in sorted(run_dir.glob("trials/*/trial.json")):
        trial = json.loads(trial_path.read_text(encoding="utf-8"))
        log_path = trial_path.parent / "verifier.log"
        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        evidence = verifier_setup_failure(log)
        verdict = "clean"
        if evidence:
            verdict = f"SETUP-FAILED ({evidence})"
            suspicious += 1
        print(f"{trial['status']:<12} {trial['id']:<45} {verdict}")
    print(f"\n{suspicious} cell(s) whose zero is not evidence about the agent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
