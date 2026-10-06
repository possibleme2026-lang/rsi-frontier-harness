"""Aggregate spend for a set of runs, split by what the provider bills.

The harness's headline number is a spend figure, so it should be decomposable into the
four things the provider charges for, across every run that contributed a cell.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.llm.pricing import rate_card  # noqa: E402


def cells(run_dir: Path, model: str) -> dict[str, dict]:
    card = rate_card(model)
    out: dict[str, dict] = {}
    for path in sorted(run_dir.glob("trials/*/trial.json")):
        trial = json.loads(path.read_text(encoding="utf-8"))
        previous = out.get(trial["id"])
        if previous is not None and previous["status"] != "infra_invalid":
            continue
        usage = trial.get("usage") or {}
        prompt = usage.get("prompt_tokens") or 0
        cached = usage.get("cached_tokens") or 0
        output = usage.get("completion_tokens") or 0
        fresh = max(0, prompt - cached)
        out[trial["id"]] = {
            "status": trial["status"],
            "fresh": fresh,
            "cached": cached,
            "output": output,
            "cost": trial.get("cost_usd") or 0.0,
            "d_fresh": fresh * card.fresh_input / card.unit_tokens,
            "d_cached": cached * card.cache_read / card.unit_tokens,
            "d_output": output * card.output / card.unit_tokens,
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--model", default="DeepSeek-V4.1-Flash")
    parser.add_argument("--group", action="store_true", help="one row per run")
    args = parser.parse_args()

    merged: dict[str, dict] = {}
    per_run: list[tuple[str, dict[str, dict]]] = []
    for run in args.runs:
        found = cells(Path(run), args.model)
        per_run.append((Path(run).name, found))
        for key, value in found.items():
            merged[key] = value

    def line(label: str, values: list[dict]) -> None:
        fresh = sum(v["fresh"] for v in values)
        cached = sum(v["cached"] for v in values)
        output = sum(v["output"] for v in values)
        d_fresh = sum(v["d_fresh"] for v in values)
        d_cached = sum(v["d_cached"] for v in values)
        d_output = sum(v["d_output"] for v in values)
        total = d_fresh + d_cached + d_output
        passes = sum(1 for v in values if v["status"] == "success")
        print(
            f"{label:<28}{len(values):>5}{passes:>7}{fresh:>11,}{cached:>12,}{output:>10,}"
            f"{d_fresh:>9.4f}{d_cached:>9.4f}{d_output:>9.4f}{total:>9.4f}"
            f"{(d_output / total if total else 0):>9.1%}"
        )

    print(
        f"{'run':<28}{'cells':>5}{'pass':>7}{'in_fresh':>11}{'in_cached':>12}{'out':>10}"
        f"{'$fresh':>9}{'$cached':>9}{'$output':>9}{'$total':>9}{'out share':>10}"
    )
    if args.group:
        for name, found in per_run:
            line(name, list(found.values()))
    line("TOTAL", list(merged.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
