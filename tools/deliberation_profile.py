"""When did the episode start deliberating?

The 7x increase in completion tokens has to be attributed before anything is concluded from
it.  If the expensive turns cluster after the artifact gate fires, the gate is the cause;
if they are distributed from the first turn, the prompt blocks are.  This prints the
per-step profile with the message positions of the injected notices marked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("task")
    args = parser.parse_args()

    path = ROOT / "runs" / args.run / "trials" / args.task / "episode.json"
    if not path.is_file():
        print(f"no episode at {path}")
        return 1
    episode = json.loads(path.read_text(encoding="utf-8"))
    steps = episode["steps"]

    print(f"genome={episode['genome_id']} task={args.task}")
    print(f"turns={len(steps)} exit={episode['exit_reason']} duration={episode['duration_s']:.0f}s")
    print()

    # which tool observations carried an injected notice, in step order
    notices: dict[int, str] = {}
    step_index = -1
    for message in episode["messages"]:
        if message.get("role") == "assistant":
            step_index += 1
        content = message.get("content") or ""
        if message.get("role") == "tool":
            if "Artifact check" in content:
                notices[step_index] = notices.get(step_index, "") + "G"
            if "Budget notice" in content:
                notices[step_index] = notices.get(step_index, "") + "E"
            if "step " in content and " left]" in content:
                notices[step_index] = notices.get(step_index, "") + "."

    print(f"{'step':>5}{'completion':>12}{'reasoning_ch':>14}{'latency_s':>11}  notices")
    for step in steps:
        index = step["index"]
        usage = step["usage"] or {}
        print(
            f"{index:>5}{usage.get('completion_tokens') or 0:>12}"
            f"{step.get('reasoning_chars') or 0:>14}{step['latency_s']:>11.1f}"
            f"  {notices.get(index, '')}"
        )
    print()
    print("G = artifact gate fired, E = endgame notice, . = plain countdown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
