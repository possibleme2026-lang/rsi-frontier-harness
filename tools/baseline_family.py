"""Per-task baseline outcomes for one suite family.

The aggregate pass rate hides which cells were solved by nobody: a task that all
twelve published harnesses failed is the most informative cell in the suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.config import settings  # noqa: E402
from rsih.rsi.report import load_baselines  # noqa: E402


def main(family: str = "datacurve") -> int:
    cfg = settings()
    _, baselines = load_baselines(cfg.eval_repo)
    ids: list[str] = []
    for baseline in baselines:
        for detail in baseline["task_details"].values():
            if detail["id"].split("/")[0] == family and detail["id"] not in ids:
                ids.append(detail["id"])
    ids.sort()
    print(f"{family}: {len(ids)} task(s) in the frozen eval, {len(baselines)} published harnesses")
    for task_id in ids:
        cells = [
            (b["name"], b["task_details"].get(task_id)) for b in baselines
        ]
        passed = [name for name, cell in cells if cell and cell.get("success")]
        costs = [c["cost_first_cold_usd"] for _, c in cells if c and c.get("cost_first_cold_usd")]
        print(
            f"  {task_id.split('/')[-1]:<46} passed_by={len(passed):>2}/{len(cells)}"
            + (f" min_cost=${min(costs):.3f}" if costs else "")
        )
    totals = []
    for baseline in baselines:
        details = [d for d in baseline["task_details"].values() if d["id"] in ids]
        successes = [d for d in details if d.get("success")]
        costs = [d["cost_first_cold_usd"] for d in details if d.get("cost_first_cold_usd") is not None]
        total = sum(costs) if costs else None
        per_pass = total / len(successes) if (successes and total is not None) else None
        totals.append(
            f"  {baseline['name']:<14} {len(successes)}/{len(details)} "
            f"total=${total if total is None else round(total, 3)} "
            f"cost_per_pass={'n/a' if per_pass is None else round(per_pass, 3)}"
        )
    print("\npublished harnesses on the same cells:")
    print("\n".join(totals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "datacurve"))
