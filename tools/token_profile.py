"""Token profile for our cells next to the published harnesses'.

This is the price-independent part of the cost comparison: tokens and cache behaviour are
provider-reported on both sides, so the difference between 0.81 M and 4.7 M input tokens
per task survives any argument about whose rate card is right.  It is also the part that
shows the cost advantage is *not* simply a higher cache hit rate.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DATA = ROOT.parent / "_ref-frontier-eval" / "results" / "eval-data.json"

OUR_RUNS = [
    "runs/gen0-probe-g0-gen0",
    "runs/holdout-gen1",
    "runs/close-polyglot",
    "runs/deepswe-9",
]


def our_cells() -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for run in OUR_RUNS:
        for path in (ROOT / run).glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if trial["status"] not in ("success", "failure"):
                continue
            previous = merged.get(trial["id"])
            if previous is None or previous["status"] != "success":
                merged[trial["id"]] = trial
    return merged


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="rsih gen1")
    args = parser.parse_args()

    cells = our_cells()
    valid = list(cells.values())
    successes = [t for t in valid if t["status"] == "success"]

    def usage(trial: dict) -> dict:
        return trial.get("usage") or {}

    prompt = sum(usage(t)["prompt_tokens"] or 0 for t in valid)
    cached = sum(usage(t)["cached_tokens"] or 0 for t in valid)
    output = sum(usage(t)["completion_tokens"] or 0 for t in valid)
    turns = sum(t.get("turns") or 0 for t in valid)
    weighted = cached / prompt if prompt else None
    medians = [
        (usage(t)["cached_tokens"] or 0) / usage(t)["prompt_tokens"]
        for t in successes
        if usage(t).get("prompt_tokens")
    ]

    published = json.loads(EVAL_DATA.read_text(encoding="utf-8"))["harnesses"]

    header = (
        f"{'configuration':<16}{'mean in':>11}{'mean out':>10}{'turns':>7}"
        f"{'cache wtd':>11}{'cache typ':>11}"
    )
    print(header)
    print("-" * len(header))
    for harness in published:
        print(
            f"{harness['name']:<16}{harness.get('mean_input_tokens') or 0:>11,.0f}"
            f"{harness.get('mean_output_tokens') or 0:>10,.0f}"
            f"{harness.get('mean_turns') or 0:>7.1f}"
            f"{harness.get('cache_hit_rate_normalized') or 0:>11.1%}"
            f"{harness.get('cache_hit_rate_typical') or 0:>11.1%}"
        )
    print("-" * len(header))
    print(
        f"{args.name:<16}{prompt / len(valid):>11,.0f}{output / len(valid):>10,.0f}"
        f"{turns / len(valid):>7.1f}{weighted:>11.1%}"
        f"{(statistics.median(medians) if medians else 0):>11.1%}"
    )

    codex = next(h for h in published if h["name"] == "codex")
    print()
    print(f"input tokens per task : ours {prompt / len(valid):,.0f} vs "
          f"codex {codex['mean_input_tokens']:,.0f} "
          f"({codex['mean_input_tokens'] / (prompt / len(valid)):.2f}x)")
    print(f"output tokens per task: ours {output / len(valid):,.0f} vs "
          f"codex {codex['mean_output_tokens']:,.0f} "
          f"({(output / len(valid)) / codex['mean_output_tokens']:.2f}x)")
    print(f"cache hit (weighted)  : ours {weighted:.1%} vs "
          f"codex {codex['cache_hit_rate_normalized']:.1%} normalized / "
          f"{codex['cache_hit_rate_typical']:.1%} typical  <- ours is LOWER")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
