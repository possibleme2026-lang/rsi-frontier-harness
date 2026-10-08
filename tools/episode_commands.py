"""What did the agent actually do, step by step, in one episode?

Reads `steps`, not `messages`: the loop compacts its message list, so an episode that
compacted has far fewer assistant messages than it took steps, and counting tool calls from
`messages` silently reports the post-compaction remainder.  An earlier version of this tool
did exactly that and made a hundred-step episode look like a twenty-nine-call one.

An episode that ends with an empty product diff has either been exploring and never
converted, or been writing to the wrong place, and the commands say which.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WRITE_TOKENS = ("cat >", "cat >>", "tee ", ">>", "sed -i", "apply_patch", "patch ", "write_file")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("task")
    parser.add_argument("--full", action="store_true", help="print every call, not a summary")
    parser.add_argument("--tail", type=int, default=0, help="print the last N calls")
    args = parser.parse_args()

    path = ROOT / "runs" / args.run / "trials" / args.task / "episode.json"
    if not path.is_file():
        print(f"no episode at {path}")
        return 1
    episode = json.loads(path.read_text(encoding="utf-8"))
    steps = episode["steps"]

    calls = []
    for step in steps:
        for call in step.get("tool_calls") or []:
            arguments = call.get("arguments") or {}
            detail = (
                arguments.get("command")
                or arguments.get("path")
                or arguments.get("summary")
                or ""
            )
            calls.append((call.get("name", "?"), str(detail), step.get("index")))

    print(f"genome={episode.get('genome_id')} task={args.task}")
    print(
        f"steps={len(steps)} calls={len(calls)} exit={episode.get('exit_reason')} "
        f"compactions={episode.get('compactions')} warnings={episode.get('artifact_warnings')} "
        f"rejections={episode.get('submit_rejections')} empty_rejections={episode.get('empty_artifact_rejections')}"
    )
    print()

    kinds = collections.Counter(name for name, _, _ in calls)
    print("calls by tool: " + ", ".join(f"{k}={v}" for k, v in kinds.most_common()))

    writes = [c for c in calls if any(token in c[1] for token in WRITE_TOKENS)]
    product_writes = [c for c in writes if "/tmp/" not in c[1] and "scratch" not in c[1].lower()]
    print(f"  calls that write anything      : {len(writes)}")
    print(f"  calls that write to /tmp or scratch: {len(writes) - len(product_writes)}")
    print(f"  calls that write into the repo : {len(product_writes)}")
    print()

    if product_writes:
        print("repo-writing calls, in order:")
        for name, detail, index in product_writes[:25]:
            print(f"  step {index:>3}  {name}: {detail[:150]}")
    else:
        print("This episode never ran a command that writes into the repository.")
        print()
        print("The last 12 calls, to show what it was doing instead:")
        for name, detail, index in calls[-12:]:
            print(f"  step {index:>3}  {name}: {detail[:150]}")

    if args.full:
        print()
        for name, detail, index in calls:
            print(f"  step {index:>3}  {name}: {detail[:150]}")
    if args.tail:
        print()
        for name, detail, index in calls[-args.tail :]:
            print(f"  step {index:>3}  {name}: {detail[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
