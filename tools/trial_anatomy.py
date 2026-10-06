"""Count tool usage and find the write attempts in a trial's episode."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trial_dir")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    episode = json.loads((Path(args.trial_dir) / "episode.json").read_text(encoding="utf-8"))
    steps = episode.get("steps") or episode.get("turns") or []
    counts: collections.Counter = collections.Counter()
    writes: list[str] = []
    errors: list[str] = []
    for step in steps:
        for call in step.get("tool_calls") or []:
            name = call.get("name") or "?"
            counts[name] += 1
            arguments = call.get("arguments")
            text = arguments if isinstance(arguments, str) else json.dumps(arguments or {})
            if name != "bash":
                writes.append(f"{name}: {text[:200]}")
            elif any(token in text for token in ("cat >", "<<'EOF'", ">>", "sed -i", "tee ", "python - <<")):
                writes.append(f"bash(write): {text[:200]}")
        for entry in step.get("tool_results") or []:
            output = entry.get("output") if isinstance(entry, dict) else entry
            if output and ("error" in str(output).lower()[:400] or "Traceback" in str(output)[:400]):
                errors.append(str(output)[:200])
    print("tool usage:", dict(counts))
    print(f"\n{len(writes)} write-ish call(s):")
    for line in writes[: args.limit]:
        print("  " + line)
    print(f"\n{len(errors)} result(s) mentioning an error:")
    for line in errors[: args.limit]:
        print("  " + line.replace("\n", " ")[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
