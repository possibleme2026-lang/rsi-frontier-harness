"""List the shell commands a trial actually ran, and where it ran them."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trial_dir")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--width", type=int, default=160)
    args = parser.parse_args()

    episode = json.loads((Path(args.trial_dir) / "episode.json").read_text(encoding="utf-8"))
    steps = episode.get("steps") or episode.get("turns") or []
    print(f"{len(steps)} step(s); showing {min(args.limit, len(steps))}")
    shown = 0
    for step in steps:
        for call in step.get("tool_calls") or []:
            name = call.get("name")
            arguments = call.get("arguments") or {}
            if isinstance(arguments, str):
                text = arguments
            else:
                text = arguments.get("command") or arguments.get("path") or json.dumps(arguments)
            print(f"  {name}: {str(text)[: args.width]}")
            shown += 1
            if shown >= args.limit:
                return 0
        for entry in step.get("tool_results") or step.get("observations") or []:
            text = entry.get("output") if isinstance(entry, dict) else entry
            print(f"    -> {str(text)[: args.width]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
