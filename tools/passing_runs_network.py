"""Did a cell's passing run download the reference implementation?

If a cell passed while fetching its upstream package from a registry, the pass is not
evidence about the harness.  This finds every run where a named task ended in `success`, and
prints the network commands that run issued together with what the observation shows -- so
"it passed because it fetched the answer" can be confirmed or ruled out rather than assumed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from network_census import BLOCKED, NETWORK_COMMAND  # noqa: E402

task_filter = sys.argv[1] if len(sys.argv) > 1 else ""
for run in sorted(p for p in (ROOT / "runs").iterdir() if p.is_dir()):
    for path in run.glob("trials/*/trial.json"):
        try:
            trial = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if trial.get("status") != "success":
            continue
        if task_filter and task_filter not in trial["id"]:
            continue
        episode_path = path.parent / "episode.json"
        if not episode_path.is_file():
            continue
        episode = json.loads(episode_path.read_text(encoding="utf-8"))
        found = []
        for step in episode.get("steps") or []:
            for call in step.get("tool_calls") or []:
                command = str((call.get("arguments") or {}).get("command") or "")
                if command and NETWORK_COMMAND.search(command):
                    observation = str(call.get("observation") or "")
                    found.append((step.get("index"), command, observation,
                                  bool(BLOCKED.search(observation))))
        if found:
            print(f"=== {run.name} / {trial['id']}  ({len(found)} network command(s)) ===")
            for index, command, observation, blocked in found[:6]:
                tag = "BLOCKED" if blocked else "not refused"
                print(f"  step {index} [{tag}] {command[:130]}")
                print(f"      out: {observation[:200].replace(chr(10), ' | ')}")
            print()
