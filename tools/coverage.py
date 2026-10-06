"""Which of the frozen suite's tasks have been measured, and with what verdict.

The headline is a claim about 30 cells, so it should be computed from the cells that
were actually run rather than assembled by hand.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.bench.tasks import load_tasks  # noqa: E402
from rsih.config import settings  # noqa: E402


def collect(run_dir: Path) -> dict[str, dict]:
    cells: dict[str, dict] = {}
    for path in sorted(run_dir.glob("trials/*/trial.json")):
        trial = json.loads(path.read_text(encoding="utf-8"))
        existing = cells.get(trial["id"])
        if existing is None or existing["status"] == "infra_invalid":
            cells[trial["id"]] = trial
    return cells


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+", help="run directories, later ones win")
    parser.add_argument("--label", default="RSIH")
    args = parser.parse_args()

    merged: dict[str, dict] = {}
    for run in args.runs:
        merged.update(collect(Path(run)))

    tasks = load_tasks(settings())
    by_suite: dict[str, list] = {}
    for task in tasks:
        by_suite.setdefault(task.suite, []).append(task)

    total_valid = total_pass = 0
    cost = 0.0
    for suite in sorted(by_suite):
        rows = by_suite[suite]
        valid = [t for t in rows if merged.get(t.id, {}).get("status") in ("success", "failure")]
        passed = [t for t in valid if merged[t.id]["status"] == "success"]
        missing = [t for t in rows if t.id not in merged]
        suite_cost = sum(merged[t.id].get("cost_usd") or 0.0 for t in valid)
        cost += suite_cost
        total_valid += len(valid)
        total_pass += len(passed)
        print(
            f"{suite:<16} {len(passed)}/{len(valid)} measured"
            f"  ({len(rows)} in suite, {len(missing)} unmeasured)  ${suite_cost:.4f}"
        )
        for task in rows:
            cell = merged.get(task.id)
            mark = cell["status"] if cell else "not run"
            print(f"    {task.short:<46} {mark}")
    rate = total_pass / total_valid if total_valid else 0.0
    print(f"\n{args.label}: {total_pass}/{total_valid} valid cells = {rate:.1%}, total ${cost:.4f}")
    if total_pass:
        print(f"effective cost per pass: ${cost / total_pass:.4f}")
    for baseline_name, published_rate in (("codex", 0.667), ("exo", 0.533), ("pi", 0.600)):
        print(f"  published {baseline_name}: {published_rate:.1%} over 30 tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
