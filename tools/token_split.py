"""Compare the token split of the same task across several runs.

Used to check *why* a cost change moved: a saving in output tokens and a saving in
cached input tokens are different mechanisms, and only one of them is what the edit
claimed to do.
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
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--task", required=True)
    parser.add_argument("--model", default="DeepSeek-V4.1-Flash")
    args = parser.parse_args()

    card = rate_card(args.model)
    print(
        f"{'run':<34}{'status':>10}{'turns':>7}{'out_tok':>10}{'$out':>9}"
        f"{'cached':>11}{'$cached':>9}{'fresh':>9}{'$fresh':>9}{'$total':>9}"
    )
    for run in args.runs:
        run_dir = Path(run)
        trial_path = run_dir / "trials" / args.task / "trial.json"
        if not trial_path.is_file():
            print(f"{run_dir.name:<34}{'n/a':>10}")
            continue
        trial = json.loads(trial_path.read_text(encoding="utf-8"))
        usage = trial.get("usage") or {}
        prompt = usage.get("prompt_tokens") or 0
        cached = usage.get("cached_tokens") or 0
        output = usage.get("completion_tokens") or 0
        fresh = max(0, prompt - cached)
        d_out = output * card.output / card.unit_tokens
        d_cached = cached * card.cache_read / card.unit_tokens
        d_fresh = fresh * card.fresh_input / card.unit_tokens
        print(
            f"{run_dir.name:<34}{trial['status']:>10}{trial.get('turns', 0):>7}{output:>10,}"
            f"{d_out:>9.4f}{cached:>11,}{d_cached:>9.4f}{fresh:>9,}{d_fresh:>9.4f}"
            f"{d_out + d_cached + d_fresh:>9.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
