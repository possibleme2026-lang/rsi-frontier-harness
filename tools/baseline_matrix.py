"""Print the published baselines' outcomes on a set of tasks.

Used to check the "solved while every baseline failed" claim from raw cells rather
than from aggregate scores, which is what the benchmark's report rules require.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.config import settings  # noqa: E402


def load(eval_repo: Path) -> dict:
    return json.loads((eval_repo / "results" / "eval-data.json").read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    cfg = settings()
    data = load(cfg.eval_repo)
    ids = argv or [t["id"] for t in sorted(data["tasks"], key=lambda t: t["id"])]
    width = max(len(i.split("/")[-1]) for i in ids) + 2
    header = "harness".ljust(14) + "".join(i.split("/")[-1][:width].rjust(width) for i in ids)
    print(header)
    for harness in data["harnesses"]:
        details = {t["id"]: t for t in harness["task_details"]}
        cells = []
        for task_id in ids:
            cell = details.get(task_id)
            cells.append(("PASS" if cell.get("success") else "fail") if cell else "-")
        print(harness["name"].ljust(14) + "".join(c.rjust(width) for c in cells))

    print()
    for task_id in ids:
        cells = [
            (h["name"], next((t for t in h["task_details"] if t["id"] == task_id), None))
            for h in data["harnesses"]
        ]
        passed = [name for name, cell in cells if cell and cell.get("success")]
        missing = [name for name, cell in cells if not cell]
        costs = [cell["cost_first_cold_usd"] for _, cell in cells if cell and cell.get("cost_first_cold_usd")]
        print(
            f"{task_id:<48} baselines_passed={len(passed)}/{len(cells)} "
            f"missing={len(missing)} min_cost=${min(costs):.4f} median_cost=${sorted(costs)[len(costs) // 2]:.4f}"
            if costs
            else f"{task_id:<48} baselines_passed={len(passed)}/{len(cells)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
