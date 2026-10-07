"""Summarize why each failed cell failed, from the verifier and episode it left behind.

The failure taxonomy in the report has to be built from what the verifiers said, not
from what the agent's transcript looks like it was doing.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FAIL_LINE = re.compile(r"^(FAILED|ERROR)\s+(\S+)")
SUMMARY = re.compile(r"^(?:=+\s*)?(?:short test summary|FAILURES|ERRORS)", re.I)


def last_failures(log: Path, limit: int = 4) -> list[str]:
    if not log.exists():
        return []
    text = log.read_text(encoding="utf-8", errors="replace")
    found = [f"{m.group(2)}" for m in FAIL_LINE.finditer(text)]
    if found:
        # keep the last occurrences, deduplicated, in order
        seen: list[str] = []
        for name in found:
            if name not in seen:
                seen.append(name)
        return seen[-limit:]
    tail = [line for line in text.strip().splitlines() if line.strip()][-limit:]
    return tail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="+", default=["runs/gen0-probe-g0-gen0"])
    parser.add_argument("--only-failed", action="store_true", default=True)
    args = parser.parse_args()

    for run in args.runs:
        run_dir = Path(run)
        if not run_dir.is_dir():
            continue
        print(f"\n=== {run_dir.name} ===")
        for trial_path in sorted(run_dir.glob("trials/*/trial.json")):
            trial = json.loads(trial_path.read_text(encoding="utf-8"))
            if args.only_failed and trial["status"] == "success":
                continue
            directory = trial_path.parent
            reason = last_failures(directory / "verifier.log")
            print(
                f"{trial['id'].split('/')[-1]:<46} {trial['status']:<14}"
                f"turns={trial['turns']:<4}exit={trial.get('exit_reason') or '?':<18}"
                f"{(trial.get('error') or '')[:40]}"
            )
            for line in reason:
                print(f"      ! {line[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
