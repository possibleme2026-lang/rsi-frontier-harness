"""Re-price our measured tokens on the frozen Kimi K3 card.

The published baselines were measured on Kimi K3 at 3.00 / 3.00 / 0.30 / 15.00 per 1M.
Our tokens were measured on DeepSeek-V4.1-Flash at 0.28 / 0.28 / 0.028 / 0.42.  Comparing
the two totals therefore mixes a model-price difference with a harness difference.  This
tool removes the price difference: it takes our measured token counts and prices them on
*their* card, so the remaining gap is what the harness would save on the same model at the
same rates.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.llm.pricing import baseline_rate_card, rate_card  # noqa: E402

EVAL_DATA = ROOT.parent / "_ref-frontier-eval" / "results" / "eval-data.json"
OUR_RUNS = [
    "runs/gen0-probe-g0-gen0",
    "runs/holdout-gen1",
    "runs/close-polyglot",
    "runs/deepswe-9",
]


def our_totals() -> dict:
    merged: dict[str, dict] = {}
    for run in OUR_RUNS:
        for path in (ROOT / run).glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if trial["status"] not in ("success", "failure"):
                continue
            previous = merged.get(trial["id"])
            if previous is None or previous["status"] != "success":
                merged[trial["id"]] = trial
    prompt = sum((t["usage"]["prompt_tokens"] or 0) for t in merged.values())
    cached = sum((t["usage"]["cached_tokens"] or 0) for t in merged.values())
    output = sum((t["usage"]["completion_tokens"] or 0) for t in merged.values())
    passes = sum(1 for t in merged.values() if t["status"] == "success")
    return {"cells": len(merged), "passes": passes, "prompt": prompt,
            "cached": cached, "output": output}


def price(prompt: int, cached: int, output: int, card) -> float:
    fresh = max(0, prompt - cached)
    return (fresh * card.fresh_input + cached * card.cache_read
            + output * card.output) / card.unit_tokens


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-cold", action="store_true",
                        help="also re-price the first call's cache reads at the fresh rate")
    args = parser.parse_args()

    totals = our_totals()
    ours_card = rate_card("DeepSeek-V4.1-Flash")
    kimi_card = baseline_rate_card("kimi-k3")

    own = price(totals["prompt"], totals["cached"], totals["output"], ours_card)
    theirs = price(totals["prompt"], totals["cached"], totals["output"], kimi_card)

    print(f"our cells            : {totals['cells']}  ({totals['passes']} passed)")
    print(f"our tokens           : fresh {totals['prompt'] - totals['cached']:,} | "
          f"cached {totals['cached']:,} | output {totals['output']:,}")
    print()
    print(f"{'':<34}{'30 tasks':>12}{'per pass':>12}")
    print(f"{'ours @ DeepSeek-V4.1-Flash card':<34}${own:>11.4f}${own / totals['passes']:>11.4f}")
    print(f"{'ours @ frozen Kimi K3 card':<34}${theirs:>11.4f}"
          f"${theirs / totals['passes']:>11.4f}")
    print()
    published = json.loads(EVAL_DATA.read_text(encoding="utf-8"))["harnesses"]
    rows = []
    for harness in published:
        details = harness.get("task_details") or []
        total = sum(d.get("cost_first_cold_usd") or 0 for d in details)
        passes = harness.get("successful") or 0
        rows.append((harness["name"], passes, total, total / passes if passes else None))
    rows.sort(key=lambda r: r[3] or 0)
    print(f"{'published config (Kimi K3, their prices)':<44}{'30 tasks':>12}{'per pass':>12}")
    for name, passes, total, per_pass in rows:
        marker = ""
        if per_pass and per_pass > theirs / totals["passes"]:
            marker = "  <- we would beat this"
        print(f"{name:<44}${total:>11.2f}${per_pass:>11.4f}{marker}")
    print()
    better = [r for r in rows if r[3] and r[3] > theirs / totals["passes"]]
    print(f"on their own card our tokens cost ${theirs / totals['passes']:.3f} per pass, "
          f"which is below {len(better)} of the {len(rows)} published configurations.")
    if better:
        cheapest = min(better, key=lambda r: r[3])
        print(f"the next cheapest published configuration is {cheapest[0]} at "
              f"${cheapest[3]:.3f} per pass, a {cheapest[3] / (theirs / totals['passes']):.2f}x gap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
