"""Check the declared rate card against one real billed call from the provider console.

The card in ``pricing.json`` was declared by the operator; the eval's README explicitly
says a harness being benchmarked must check that its provider's token prices match the
declared ones.  The provider's own consumption record does that check.

One call cannot pin down three rates.  This one has 11,145 fresh input, 88,832 cache reads
and 196 output tokens, so the input rates are well determined and the output rate is
almost unconstrained.  The tool therefore solves for the fresh-input rate under the card's
own ratio structure (cache read = 10% of fresh, output = 1.5x fresh) and reports how far
the output rate can move without changing the bill.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.llm.pricing import rate_card  # noqa: E402

# From the provider console, 2026-10-07 17:37:05, request
# 20261007093700161641441d02b631o7o1FLd5, status 200, streaming, 65 tok/s.
OBSERVED = {
    "fresh_tokens": 11_145,
    "cached_tokens": 88_832,
    "output_tokens": 196,
    "charged_cny": 0.013706,
}

OUR_30_TASK_TOKENS = {"fresh": 967_573, "cached": 23_204_992, "output": 2_026_535}
OUR_PASSES = 18


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--usd-cny", type=float, default=7.2,
                        help="conversion used only to compare with the USD card")
    args = parser.parse_args()

    # Equivalent fresh-input units under the card's ratio structure.
    units = (OBSERVED["fresh_tokens"] + OBSERVED["cached_tokens"] * 0.1
             + OBSERVED["output_tokens"] * 1.5)
    fresh_cny = OBSERVED["charged_cny"] * 1_000_000 / units

    card = rate_card("DeepSeek-V4.1-Flash")
    declared_fresh_cny = card.fresh_input * args.usd_cny

    print(f"billed call        : {OBSERVED['fresh_tokens']:,} fresh | "
          f"{OBSERVED['cached_tokens']:,} cached | {OBSERVED['output_tokens']:,} output")
    print(f"charged            : {OBSERVED['charged_cny']:.6f} CNY")
    print(f"equivalent units   : {units:,.1f} fresh-input-equivalents")
    print()
    print(f"{'rate (CNY per 1M)':<24}{'implied by the bill':>21}{'declared card':>15}{'ratio':>8}")
    rows = [("fresh input", fresh_cny, declared_fresh_cny),
            ("cache read", fresh_cny * 0.1, card.cache_read * args.usd_cny),
            ("output", fresh_cny * 1.5, card.output * args.usd_cny)]
    for name, implied, declared in rows:
        print(f"{name:<24}{implied:>21.4f}{declared:>15.4f}"
              f"{implied / declared:>8.2f}")
    print(f"\nfresh-input rate implied by the bill : {fresh_cny:.4f} CNY/1M "
          f"= ${fresh_cny / args.usd_cny:.4f}/1M at {args.usd_cny} CNY/USD")
    print(f"declared card fresh-input rate       : {card.fresh_input:.4f} USD/1M "
          f"= {declared_fresh_cny:.4f} CNY/1M")
    print(f"the declared card is {declared_fresh_cny / fresh_cny:.2f}x the billed rate")

    ratio = OBSERVED["output_tokens"] * 1.5 / units
    print(f"\nthe output term is {ratio:.2%} of this bill, so the output rate is "
          f"not constrained by it.")

    print("\nour 30 measured cells under three assumptions:")
    for label, fresh, cached, output in [
        ("declared card (quoted in the report)", card.fresh_input, card.cache_read,
         card.output),
        ("billed input rates, declared output rate",
         fresh_cny / args.usd_cny, fresh_cny * 0.1 / args.usd_cny, card.output),
        ("billed input rates, output rate scaled too",
         fresh_cny / args.usd_cny, fresh_cny * 0.1 / args.usd_cny,
         fresh_cny * 1.5 / args.usd_cny),
    ]:
        total = (OUR_30_TASK_TOKENS["fresh"] * fresh
                 + OUR_30_TASK_TOKENS["cached"] * cached
                 + OUR_30_TASK_TOKENS["output"] * output) / 1_000_000
        print(f"  {label:<44}${total:>8.4f} for 30 tasks   "
              f"${total / OUR_PASSES:>7.4f} per pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
