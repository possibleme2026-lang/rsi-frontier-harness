"""Show the observation for every network-shaped command, so 'blocked' can be judged."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import json

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from network_census import BLOCKED, NETWORK_COMMAND  # noqa: E402

run = sys.argv[1]
tasks = sys.argv[2:] or [p.name for p in (ROOT / "runs" / run / "trials").iterdir()]

for task in tasks:
    path = ROOT / "runs" / run / "trials" / task / "episode.json"
    if not path.is_file():
        continue
    episode = json.loads(path.read_text(encoding="utf-8"))
    for step in episode.get("steps") or []:
        for call in step.get("tool_calls") or []:
            command = str((call.get("arguments") or {}).get("command") or "")
            if not command or not NETWORK_COMMAND.search(command):
                continue
            observation = str(call.get("observation") or "")
            verdict = "BLOCKED" if BLOCKED.search(observation) else "??? reached or unclear"
            print(f"[{task} step {step.get('index')}] {verdict}")
            print(f"  cmd : {command[:150]}")
            print(f"  out : {observation[:300].replace(chr(10), ' | ')}")
            print()
