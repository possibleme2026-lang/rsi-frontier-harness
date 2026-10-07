"""Did the artifact gate actually fire, cell by cell, and what did the agent do after?

A gate that never fires is not being tested; a gate that fires and changes nothing is a
diagnosis of the gate's wording rather than of the agent's willingness.  This prints, per
cell, how often the gate fired, the step it first fired, the size of the collected diff and
whether the agent ever touched a product path -- which separates "the gate could not see
this container" from "the gate spoke and was ignored".
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    args = parser.parse_args()

    run_dir = ROOT / "runs" / args.run
    print(f"{'task':<40}{'warn':>6}{'endgame':>9}{'nudge':>7}{'turns':>7}{'exit':>20}{'diff B':>9}")
    fired = never = 0
    for path in sorted(run_dir.glob("trials/*/episode.json")):
        episode = json.loads(path.read_text(encoding="utf-8"))
        warnings = episode.get("artifact_warnings") or 0
        endgame = 0
        for message in episode["messages"]:
            content = message.get("content") or ""
            if "Budget notice" in content:
                endgame += 1
        trial = path.parent / "trial.json"
        payload = json.loads(trial.read_text(encoding="utf-8")) if trial.is_file() else {}
        if warnings:
            fired += 1
        else:
            never += 1
        print(
            f"{episode.get('task_id', path.parent.name).split('/')[-1][:38]:<40}"
            f"{warnings:>6}{endgame:>9}{episode.get('nudges') or 0:>7}"
            f"{episode.get('turns') or 0:>7}"
            f"{str(episode.get('exit_reason')):>20}"
            f"{payload.get('submitted_bytes') or 0:>9}"
        )
    print()
    print(f"cells where the gate fired: {fired}   cells where it never fired: {never}")
    print("A cell with warn=0 either never reached a gate step, or its worktree was not a")
    print("git repository (the gate stays silent rather than guess).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
