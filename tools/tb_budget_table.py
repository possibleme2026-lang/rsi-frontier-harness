"""Terminal-bench cells by declared budget, next to how they actually went.

The step-budget policy keys off the declared budget, so this is the table that says
which cells it can possibly reach and whether the long-budget ones are the ones that
ran out of room.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.bench.tasks import load_tasks  # noqa: E402
from rsih.config import settings  # noqa: E402

DEFAULT_RUNS = ("runs/gen0-probe-g0-gen0", "runs/holdout-gen1", "runs/close-polyglot")


def main() -> int:
    results: dict[str, dict] = {}
    for run in DEFAULT_RUNS:
        for path in pathlib.Path(run).glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if trial["status"] in ("success", "failure"):
                results[trial["id"]] = trial

    tasks = sorted(
        (t for t in load_tasks(settings()) if t.suite == "terminal-bench"),
        key=lambda t: -t.agent_timeout_declared_s,
    )
    print(f"{'task':<46}{'declared':>9}{'status':>10}{'turns':>7}{'exit':>20}{'spend':>9}")
    for task in tasks:
        trial = results.get(task.id)
        status = trial["status"] if trial else "not run"
        turns = str(trial["turns"]) if trial else "-"
        exit_reason = (trial.get("exit_reason") or "-") if trial else "-"
        spend = f"{trial.get('cost_usd') or 0:.4f}" if trial else "-"
        print(
            f"{task.short:<46}{task.agent_timeout_declared_s:>8.0f}s{status:>10}"
            f"{turns:>7}{exit_reason:>20}{spend:>9}"
        )

    budget_bound = [
        t
        for t in tasks
        if (r := results.get(t.id))
        and r["status"] == "failure"
        and r.get("exit_reason") in ("step_limit", "wall_clock_budget")
    ]
    print(f"\nfailures that ran out of budget: {len(budget_bound)}")
    for task in budget_bound:
        print(f"  {task.short} (declared {task.agent_timeout_declared_s:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
