"""One table for the DeepSWE half: our cell next to the published cells.

The binary reward is what the eval scores, so it is the first column.  The fraction of
required tests that passed is the more informative number when the reward is zero, and
the baseline's cheapest successful run is what our spend should be compared against.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.config import settings  # noqa: E402
from rsih.rsi.report import load_baselines  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", help="runs/<run-id> holding datacurve trials")
    args = parser.parse_args()

    run_dir = Path(args.run)
    _, baselines = load_baselines(settings().eval_repo)

    rows = []
    for trial_path in sorted(run_dir.glob("trials/*/trial.json")):
        trial = json.loads(trial_path.read_text(encoding="utf-8"))
        if not trial["id"].startswith("datacurve/"):
            continue
        rows.append(trial)
    resolved: dict[str, dict] = {}
    for trial in rows:
        previous = resolved.get(trial["id"])
        if previous is None or previous["status"] == "infra_invalid":
            resolved[trial["id"]] = trial
    rows = sorted(resolved.values(), key=lambda t: t["id"])

    print(
        f"{'task':<44}{'reward':>7}{'f2p':>9}{'p2p':>8}{'turns':>7}{'cost':>10}"
        f"{'baselines':>11}{'cheapest pass':>15}"
    )
    ours_cost = 0.0
    ours_pass = 0
    for trial in rows:
        detail = trial.get("extra", {}).get("verifier_detail") or {}
        f2p = (
            f"{detail.get('f2p_passed')}/{detail.get('f2p_total')}" if detail.get("f2p_total") else "-"
        )
        p2p = (
            f"{detail.get('p2p_passed')}/{detail.get('p2p_total')}" if detail.get("p2p_total") else "-"
        )
        passed = [b for b in baselines if (b["task_details"].get(trial["id"]) or {}).get("success")]
        costs = [
            b["task_details"][trial["id"]]["cost_first_cold_usd"]
            for b in passed
            if b["task_details"][trial["id"]].get("cost_first_cold_usd") is not None
        ]
        cheapest = f"${min(costs):.3f}" if costs else "nobody"
        cost = trial.get("cost_usd") or 0.0
        ours_cost += cost
        ours_pass += trial["status"] == "success"
        print(
            f"{trial['id'].split('/')[-1]:<44}{trial.get('reward') if trial.get('reward') is not None else '-':>7}"
            f"{f2p:>9}{p2p:>8}{trial.get('turns', 0):>7}{cost:>10.4f}"
            f"{len(passed):>7}/12{cheapest:>15}"
        )
    print(f"\nours: {ours_pass}/{len(rows)} passed, total ${ours_cost:.4f}")

    for baseline in baselines:
        details = [baseline["task_details"].get(t["id"]) for t in rows]
        successes = [d for d in details if d and d.get("success")]
        costs = [d["cost_first_cold_usd"] for d in details if d and d.get("cost_first_cold_usd") is not None]
        total = sum(costs) if costs else None
        per_pass = total / len(successes) if successes and total else None
        print(
            f"  {baseline['name']:<14} {len(successes)}/{len(rows)} "
            f"total=${total if total is None else round(total, 2)} "
            f"cost/pass={'n/a' if per_pass is None else round(per_pass, 2)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
