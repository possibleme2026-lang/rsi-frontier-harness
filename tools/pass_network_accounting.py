"""Of the runs that passed, how many had reached off-host first?

Every cell-level pass in this repository was produced with unrestricted network access.  This
counts how many of them also ran a command that can leave the host, and how many of those
commands show no sign of being refused -- which is the only way to know how much of the
reported score was the harness and how much was the network.

It does not claim every network-using pass depended on the network.  It separates the passes
that never touched it, which are evidence about the harness, from the ones that did, which
need a re-run under the corrected policy before they can be used for anything.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from network_census import BLOCKED, NETWORK_COMMAND  # noqa: E402

clean: list[str] = []
networked: list[tuple[str, str, int, bool]] = []
for run in sorted(p for p in (ROOT / "runs").iterdir() if p.is_dir()):
    for path in run.glob("trials/*/trial.json"):
        try:
            trial = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if trial.get("status") != "success":
            continue
        episode_path = path.parent / "episode.json"
        episode = json.loads(episode_path.read_text(encoding="utf-8")) if episode_path.is_file() else {}
        commands = []
        any_refused = False
        for step in episode.get("steps") or []:
            for call in step.get("tool_calls") or []:
                command = str((call.get("arguments") or {}).get("command") or "")
                if command and NETWORK_COMMAND.search(command):
                    commands.append(command)
                    if BLOCKED.search(str(call.get("observation") or "")):
                        any_refused = True
        if commands:
            networked.append((run.name, trial["id"], len(commands), any_refused))
        else:
            clean.append(trial["id"])

print(f"successful trials stored                  : {len(clean) + len(networked)}")
print(f"  ... that never ran a network command    : {len(clean)}"
      f"  <- these are evidence about the harness")
print(f"  ... that did run one                    : {len(networked)}")
print(f"      of those, with any refusal in view  : {sum(1 for r in networked if r[3])}")
print()

by_task = collections.Counter(task for _, task, _, _ in networked)
print("passing tasks that used the network, by number of passing runs:")
for task, count in by_task.most_common(24):
    marker = ""
    bare = task.split("/")[-1]
    if len(bare) > 40:
        bare = bare[:40]
    print(f"  {task:<52} {count}")
print()
clean_tasks = sorted({task.split("/")[-1] for task in clean})
networked_tasks = {task.split("/")[-1] for task, _ in
                   ((t, c) for t, c in by_task.items())}
mixed = sorted(clean_tasks)
print(f"tasks with at least one network-free pass ({len(clean_tasks)}):")
for task in mixed:
    also = "  (but other runs of it did use it)" if any(
        task in t for t in networked_tasks
    ) else ""
    print(f"  {task}{also}")
