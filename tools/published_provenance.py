"""Describe exactly what the published baseline file contains.

The report compares measured cells against published ones, so the provenance of the
published side has to be readable without guessing.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "_ref-frontier-eval" / "results" / "eval-data.json"


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    print(f"file          : {DATA}")
    print(f"generated_at  : {data.get('generated_at')}")
    print(f"model field   : {data.get('model')}")
    overview = data.get("overview") or {}
    for key in (
        "checkpoint_tasks",
        "expected_cells",
        "completed_cells",
        "harnesses",
        "harness_configurations",
        "infra_invalid_cells",
        "pass_rate",
        "cost_per_success_normalized",
        "cache_hit_rate_normalized",
    ):
        print(f"overview.{key:<32} {overview.get(key)}")
    print()
    print(f"{'harness':<18}{'cells':>7}{'pass':>6}{'cost_usd':>11}{'per_pass':>10}")
    for harness in data.get("harnesses", []):
        raw = harness.get("tasks") or harness.get("task_details") or {}
        tasks = raw if isinstance(raw, dict) else {str(t.get("id")): t for t in raw}
        passed = sum(1 for t in tasks.values() if t.get("success"))
        cost = sum((t.get("cost_first_cold_usd") or 0) for t in tasks.values())
        per_pass = f"{cost / passed:.3f}" if passed else "n/a"
        print(
            f"{str(harness.get('name')):<18}{len(tasks):>7}{passed:>6}{cost:>11.2f}{per_pass:>10}"
        )
    sample = (data.get("harnesses") or [{}])[0]
    raw = sample.get("tasks") or sample.get("task_details") or {}
    tasks = raw if isinstance(raw, dict) else {str(t.get("id")): t for t in raw}
    if tasks:
        key = sorted(tasks)[0]
        print(f"\nsample cell ({sample.get('name')} / {key}):")
        print(json.dumps(tasks[key], indent=2)[:700])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
