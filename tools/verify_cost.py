"""Recompute a trial's spend from its raw per-call records and compare.

Money is the headline number in this project, so it should be auditable from the call
log rather than trusted from a summary field.  This also reports whether the reasoning
channel is inside or beside the billed completion.
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
    parser.add_argument("trial_dir")
    parser.add_argument("--model", default="DeepSeek-V4.1-Flash")
    args = parser.parse_args()

    directory = Path(args.trial_dir)
    trial = json.loads((directory / "trial.json").read_text(encoding="utf-8"))
    card = rate_card(args.model)

    calls = [
        json.loads(line)
        for line in (directory / "llm-calls.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    prompt = completion = cached = reasoning = 0
    missing = 0
    for call in calls:
        usage = call.get("usage") or {}
        if usage.get("prompt_tokens") is None and usage.get("completion_tokens") is None:
            missing += 1
            continue
        prompt += usage.get("prompt_tokens") or 0
        completion += usage.get("completion_tokens") or 0
        cached += usage.get("cached_tokens") or 0
        reasoning += usage.get("reasoning_tokens") or 0

    fresh = max(0, prompt - cached)
    unit = card.unit_tokens
    d_fresh = fresh * card.fresh_input / unit
    d_cached = cached * card.cache_read / unit
    d_out = completion * card.output / unit
    recomputed = d_fresh + d_cached + d_out

    print(f"trial              : {trial['id']}")
    print(f"model              : {args.model}  ({card.fresh_input}/{card.cache_write}/"
          f"{card.cache_read}/{card.output} per 1M fresh/write/read/output)")
    print(f"calls in log       : {len(calls)}  (missing usage: {missing})")
    print()
    print(f"{'component':<16}{'tokens':>14}{'rate/1M':>10}{'usd':>11}")
    print(f"{'fresh input':<16}{fresh:>14,}{card.fresh_input:>10.3f}{d_fresh:>11.5f}")
    print(f"{'cached input':<16}{cached:>14,}{card.cache_read:>10.3f}{d_cached:>11.5f}")
    print(f"{'output':<16}{completion:>14,}{card.output:>10.3f}{d_out:>11.5f}")
    print(f"{'recomputed':<16}{'':>14}{'':>10}{recomputed:>11.5f}")
    print()
    print(f"trial.json cost_usd            : {trial.get('cost_usd')}")
    print(f"trial.json cost_first_cold_usd : {trial.get('cost_first_cold_usd')}")
    print(f"trial.json usage               : {trial.get('usage')}")
    first_cached = next(
        (c["usage"]["cached_tokens"] for c in calls if (c.get("usage") or {}).get("cached_tokens")),
        0,
    )
    cold = recomputed + first_cached * (card.fresh_input - card.cache_read) / unit
    print(f"recomputed first-cold           : {cold:.5f}")
    print()
    print(f"reasoning tokens               : {reasoning:,}"
          f"  ({reasoning / completion:.1%} of completion)" if completion else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
