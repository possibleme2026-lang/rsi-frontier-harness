"""Dump the raw shape of one step so the extraction reads the real fields."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "runs" / sys.argv[1] / "trials" / sys.argv[2] / "episode.json"
episode = json.loads(path.read_text(encoding="utf-8"))
steps = episode["steps"]
print(json.dumps(steps[0], indent=2)[:1500])
print("---- a step with a bash call ----")
for step in steps:
    if step.get("tool_calls"):
        print(json.dumps(step["tool_calls"], indent=2)[:800])
        break
print("---- compaction ----")
print("compacted_before values:", [s.get("compacted_before") for s in steps])
print("episode compactions:", episode.get("compactions"))
