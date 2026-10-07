"""Where did the wall clock actually go?

A cell that passed in 60 steps and now stops at 45 with an empty diff either got slower
per step or spent its steps differently, and the two have different fixes.  This compares
two episodes of the same task step by step.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(run: str, task: str) -> dict | None:
    path = ROOT / "runs" / run / "trials" / task / "episode.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def summarise(label: str, episode: dict, task: str) -> None:
    steps = episode["steps"]
    latencies = [s["latency_s"] for s in steps]
    completion = [(s["usage"] or {}).get("completion_tokens") or 0 for s in steps]
    reasoning_share = [s.get("reasoning_chars") or 0 for s in steps]
    turns = len(steps)
    print(f"{label}")
    print(f"  genome={episode['genome_id']}  turns={turns}  exit={episode['exit_reason']}  "
          f"duration={episode['duration_s']:.0f}s")
    print(f"  step latency  : sum={sum(latencies):.0f}s  median={statistics.median(latencies):.1f}s  "
          f"max={max(latencies):.1f}s")
    print(f"  completion    : total={sum(completion)}  median={statistics.median(completion):.0f}  "
          f"max={max(completion)}")
    if reasoning_share:
        print(f"  reasoning chars: total={sum(reasoning_share)}")
    if latencies:
        slowest = sorted(range(turns), key=lambda i: -latencies[i])[:5]
        print(f"  slowest steps : {[(i, round(latencies[i])) for i in slowest]}")
    for key in ("artifact_warnings", "nudges", "model_retries", "truncation_recoveries"):
        if key in episode:
            print(f"  {key}: {episode[key]}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args()

    for run in args.runs:
        episode = load(run, args.task)
        if episode is None:
            print(f"{run}: no episode.json for {args.task}\n")
            continue
        summarise(run, episode, args.task)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
