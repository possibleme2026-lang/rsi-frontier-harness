"""Render an evolution ledger as a table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger")
    args = parser.parse_args()
    for line in Path(args.ledger).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        event = entry.get("event")
        if event == "evaluation":
            print(
                f"EVAL   {entry['genome_id']:<8} {entry['fingerprint'][:8]} "
                f"pass={entry['passed']}/{entry['valid']} cost=${entry['cost_usd']:.5f} "
                f"turns={entry['turns']}"
            )
        elif event == "proposal":
            child = entry["child_summary"]
            decision = entry["decision"]
            print(
                f"CHILD  {entry['child']:<8} {entry['mutation']:<30} "
                f"pass={child['passed']}/{child['valid']} cost=${child['cost_usd']:.5f} "
                f"ratio={decision.get('cost_ratio')} diff={decision.get('diff'):+.3f} "
                f"floor={decision.get('floor'):.3f} -> {decision.get('reason')}"
            )
        elif event == "generation_end":
            print(f"ADOPT  generation {entry['generation']}: {entry.get('accepted')}")
        elif event == "end":
            print(
                f"END    incumbent={entry['incumbent']['id']} "
                f"pass={entry['incumbent_summary']['passed']}/"
                f"{entry['incumbent_summary']['valid']} "
                f"cost=${entry['incumbent_summary']['cost_usd']:.5f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
