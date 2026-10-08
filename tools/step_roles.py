"""Where did the steps go?  Read one episode's per-step record."""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "runs" / sys.argv[1] / "trials" / sys.argv[2] / "episode.json"
episode = json.loads(path.read_text(encoding="utf-8"))

print("roles:", dict(collections.Counter(m.get("role") for m in episode["messages"])))
steps = episode.get("steps") or []
print("steps recorded:", len(steps))
if steps:
    print("step keys:", sorted(steps[0].keys()))

empty = [s for s in steps if not (s.get("tool_calls") or [])]
print(f"steps with NO tool call: {len(empty)} of {len(steps)}")
print("  finish reasons:", dict(collections.Counter(s.get("finish_reason") for s in empty)))
total = sum(s.get("completion_tokens") or 0 for s in empty)
print(f"  completion tokens spent on them: {total}")
if empty:
    print(f"  max in one such step: {max(s.get('completion_tokens') or 0 for s in empty)}")
    print("  first five, in order:")
    for s in empty[:5]:
        print(f"    index={s.get('index')} finish={s.get('finish_reason')} "
              f"completion={s.get('completion_tokens')} chars={len(s.get('content') or '')}")
