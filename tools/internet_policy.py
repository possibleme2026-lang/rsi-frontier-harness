"""Does the harness let the agent reach the network, and does the benchmark expect that?

Three of the repository failures spent their budget fetching upstream commits, the hidden
test patch, or another team's published results instead of implementing the change. That is
either a legitimate research strategy or the single largest waste in the suite, and which one
depends entirely on what the task declares. This prints the declaration next to what the
sandbox actually does.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT.parent / "_ref-frontier-eval"

benchmark = json.loads((REF / "benchmark.json").read_text(encoding="utf-8"))
tasks = benchmark.get("tasks") or benchmark.get("task_ids") or []

INTERESTING = [
    "datacurve/arktype-json-schema-refs-dependencies",
    "datacurve/meriyah-explicit-resource-declarations",
    "datacurve/python-statemachine-state-data-scoping",
    "datacurve/expr-try-catch-errors",
    "terminal-bench/regex-log",
]

print("benchmark.json keys:", sorted(benchmark.keys())[:12])
print()


def field(task, name):
    for key in (name, name.replace("_", ""), f"allow{name.title()}"):
        if key in task:
            return task[key]
    return "<absent>"


if isinstance(tasks, list) and tasks and isinstance(tasks[0], dict):
    by_id = {t.get("id") or t.get("task_id"): t for t in tasks}
    interesting = INTERESTING
    print(f"{'task':<52} {'allow_internet':>14} {'timeout':>10}")
    for task_id in interesting:
        task = by_id.get(task_id, {})
        print(f"{task_id:<52} {str(field(task, 'allow_internet')):>14} "
              f"{str(task.get('agent_timeout_s', task.get('timeout_s', '?'))):>10}")
    print()
    counts: dict[str, int] = {}
    for task in tasks:
        counts[str(field(task, "allow_internet"))] = counts.get(str(field(task, "allow_internet")), 0) + 1
    print("allow_internet across all tasks:", counts)
    absent = [t.get("id") for t in tasks if field(t, "allow_internet") == "<absent>"]
    if absent:
        print(f"tasks with no allow_internet field: {len(absent)}")
else:
    print("task entries are ids, not objects; ids:", tasks[:5])
    print()
    print("checking the local task loader instead")
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from rsih.bench.tasks import load_tasks

    loaded = load_tasks()
    index = {t.id: t for t in loaded}
    for task_id in INTERESTING:
        task = index.get(task_id)
        if task:
            print(f"{task_id:<52} allow_internet={task.allow_internet} "
                  f"agent_timeout={task.agent_timeout_s} declared={task.agent_timeout_declared_s}")
    counts = {}
    for task in loaded:
        key = f"{task.suite}:{task.allow_internet}"
        counts[key] = counts.get(key, 0) + 1
    print("allow_internet by suite:", counts)

