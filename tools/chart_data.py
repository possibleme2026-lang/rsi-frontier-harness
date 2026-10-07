"""Assemble the chart's data: the published configurations plus ours.

The published side comes from the eval's own results file; our side comes from the trial
records.  Written out as JSON so a plotter never has to parse either format.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.llm.pricing import baseline_rate_card  # noqa: E402

EVAL_DATA = ROOT.parent / "_ref-frontier-eval" / "results" / "eval-data.json"


def published() -> list[dict]:
    data = json.loads(EVAL_DATA.read_text(encoding="utf-8"))
    out = []
    for harness in data.get("harnesses", []):
        raw = harness.get("task_details") or harness.get("tasks") or []
        cells = raw if isinstance(raw, dict) else {str(t.get("id")): t for t in raw}
        cells = {k: v for k, v in cells.items() if v.get("included_in_efficiency", True)}
        passes = harness.get("successful")
        if passes is None:
            passes = sum(1 for c in cells.values() if c.get("success"))
        costs = [c.get("cost_first_cold_usd") for c in cells.values()
                 if c.get("cost_first_cold_usd") is not None]
        total = sum(costs)
        declared = harness.get("effective_cost_per_pass")
        out.append(
            {
                "name": harness.get("name"),
                "kind": "published",
                "cells": harness.get("completed") or len(cells),
                "passes": passes,
                "pass_rate": harness.get("pass_rate")
                or (passes / len(cells) if cells else None),
                "total_cost_usd": total,
                "cost_per_pass_usd": declared if declared is not None
                else (total / passes if passes else None),
                "cost_per_pass_from_cells_usd": total / passes if passes else None,
                "median_cost_per_task_usd": statistics.median(costs) if costs else None,
                "mean_input_tokens": harness.get("mean_input_tokens"),
                "mean_output_tokens": harness.get("mean_output_tokens"),
                "mean_turns": harness.get("mean_turns"),
                "cache_hit_rate": harness.get("cache_hit_rate_normalized"),
            }
        )
    return out


OUR_RUNS = {
    "rsih gen1 (60 steps)": ["runs/gen0-probe-g0-gen0", "runs/holdout-gen1",
                             "runs/close-polyglot", "runs/deepswe-9"],
    "rsih gen6 (long budget)": ["runs/gen6-full"],
}


def ours() -> list[dict]:
    out = []
    for label, runs in OUR_RUNS.items():
        merged: dict[str, dict] = {}
        for run in runs:
            for path in (ROOT / run).glob("trials/*/trial.json"):
                trial = json.loads(path.read_text(encoding="utf-8"))
                if trial["status"] not in ("success", "failure"):
                    continue
                previous = merged.get(trial["id"])
                if previous is None or previous["status"] != "success":
                    merged[trial["id"]] = trial
        passes = sum(1 for t in merged.values() if t["status"] == "success")
        costs = [t["cost_first_cold_usd"] for t in merged.values()
                 if t.get("cost_first_cold_usd") is not None]
        total = sum(costs)
        out.append(
            {
                "name": label,
                "kind": "ours",
                "cells": len(merged),
                "passes": passes,
                "pass_rate": passes / len(merged) if merged else None,
                "total_cost_usd": total,
                "cost_per_pass_usd": total / passes if passes else None,
                "median_cost_per_task_usd": statistics.median(costs) if costs else None,
                "cache_hit_rate": (
                    sum(t["usage"]["cached_tokens"] or 0 for t in merged.values())
                    / max(1, sum(t["usage"]["prompt_tokens"] or 0 for t in merged.values()))
                ),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "assets" / "chart-data.json"))
    args = parser.parse_args()
    rows = published() + ours()
    Path(args.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    card = baseline_rate_card("kimi-k3")
    print(f"published rate card : {card.source}")
    print(f"{'configuration':<26}{'cells':>6}{'pass':>6}{'rate':>8}{'$/pass':>10}{'median$/task':>14}")
    for row in rows:
        rate = f"{row['pass_rate']:.1%}" if row["pass_rate"] else "n/a"
        per_pass = f"{row['cost_per_pass_usd']:.3f}" if row["cost_per_pass_usd"] else "n/a"
        median = (f"{row['median_cost_per_task_usd']:.4f}"
                  if row["median_cost_per_task_usd"] is not None else "n/a")
        print(f"{row['name']:<26}{row['cells']:>6}{row['passes']:>6}{rate:>8}{per_pass:>10}{median:>14}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
