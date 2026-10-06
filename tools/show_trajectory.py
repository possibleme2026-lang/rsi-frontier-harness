"""Print the first N steps of a trial's trajectory, for eyeballing what the agent did."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trial_dir")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--width", type=int, default=200)
    args = parser.parse_args()

    path = Path(args.trial_dir) / "trajectory.jsonl"
    with path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if index >= args.limit:
                break
            step = json.loads(line)
            kind = step.get("kind") or step.get("role") or "?"
            parts = []
            for key in ("content", "text", "command", "observation", "arguments"):
                value = step.get(key)
                if value:
                    parts.append(f"{key}={str(value)[: args.width // 2]}")
            for call in step.get("tool_calls") or []:
                parts.append(f"call={call.get('name')}({str(call.get('arguments'))[:120]})")
            print(f"[{index}] {kind}: " + " | ".join(parts)[: args.width * 2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
