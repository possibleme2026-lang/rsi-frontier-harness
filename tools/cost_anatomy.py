"""Where the money actually goes, per task.

The report gives one number per task.  This splits it the way the provider bills it:
fresh input, cache-read input, cache-write input, and output - because "the harness is
cheap" is only meaningful if you can say which decision made it cheap.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.llm.pricing import rate_card  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", help="path to runs/<run-id>")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    run_dir = Path(args.run)
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    model = args.model or meta.get("model", "")
    card = rate_card(model)

    print(f"{run_dir.name}: model={model} card={card.source}")
    header = (
        f"{'task':<44}{'turns':>6}{'in_fresh':>10}{'in_cached':>11}{'out':>9}"
        f"{'$fresh':>9}{'$cached':>9}{'$out':>9}{'$total':>9}{'cache%':>8}"
    )
    print(header)
    totals = [0, 0, 0, 0.0, 0.0, 0.0]
    rows = 0
    for trial_path in sorted(run_dir.glob("trials/*/trial.json")):
        trial = json.loads(trial_path.read_text(encoding="utf-8"))
        usage = trial.get("usage") or {}
        prompt = usage.get("prompt_tokens") or 0
        cached = usage.get("cached_tokens") or 0
        output = usage.get("completion_tokens") or 0
        if not prompt and not output:
            continue
        fresh = max(0, prompt - cached)
        d_fresh = fresh * card.fresh_input / 1e6
        d_cached = cached * card.cache_read / 1e6
        d_out = output * card.output / 1e6
        total = d_fresh + d_cached + d_out
        rows += 1
        totals[0] += fresh
        totals[1] += cached
        totals[2] += output
        totals[3] += d_fresh
        totals[4] += d_cached
        totals[5] += d_out
        print(
            f"{trial['id'].split('/')[-1]:<44}{trial.get('turns', 0):>6}{fresh:>10,}{cached:>11,}{output:>9,}"
            f"{d_fresh:>9.4f}{d_cached:>9.4f}{d_out:>9.4f}{total:>9.4f}"
            f"{(cached / prompt if prompt else 0):>8.1%}"
        )
    grand = totals[3] + totals[4] + totals[5]
    print(
        f"{'TOTAL (' + str(rows) + ' cells)':<44}{'':>6}{totals[0]:>10,}{totals[1]:>11,}{totals[2]:>9,}"
        f"{totals[3]:>9.4f}{totals[4]:>9.4f}{totals[5]:>9.4f}{grand:>9.4f}"
    )
    if grand:
        print(
            f"share of spend: output {totals[5] / grand:.0%}, "
            f"fresh input {totals[3] / grand:.0%}, cached input {totals[4] / grand:.0%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

