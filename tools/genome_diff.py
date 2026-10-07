"""Show exactly how the budget-experiment genomes differ from the reported harness.

The three wins of `gen6` over `gen1` could come from the longer step budget or from the
added verification block, and the three losses could come from either too.  That
attribution decides the next experiment, so it should be printed rather than remembered.
"""

from __future__ import annotations

import json
from pathlib import Path

GENOMES = Path(__file__).resolve().parents[1] / "genomes"
SHOW = ["gen1", "gen4", "gen5", "gen6"]


def block_names(genome: dict) -> list[str]:
    blocks = genome["blocks"]
    return list(blocks) if isinstance(blocks, dict) else list(blocks)


def main() -> int:
    base = json.loads((GENOMES / "gen1.json").read_text(encoding="utf-8"))
    base_blocks = block_names(base)
    base_tools = base["tools"]

    skip = {"blocks", "tools", "id", "lineage", "notes", "fingerprint"}
    for name in SHOW:
        genome = json.loads((GENOMES / f"{name}.json").read_text(encoding="utf-8"))
        blocks = block_names(genome)
        added = [b for b in blocks if b not in base_blocks]
        removed = [b for b in base_blocks if b not in blocks]
        params = [
            f"{key}={genome[key]!r}"
            for key in base
            if key not in skip and genome.get(key) != base[key]
        ]
        tools_changed = [t for t in genome["tools"] if t not in base_tools]
        print(f"{name}")
        print(f"  blocks added   : {added or '-'}")
        print(f"  blocks removed : {removed or '-'}")
        print(f"  tools added    : {tools_changed or '-'}")
        print(f"  params changed : {'; '.join(params) if params else 'none (identical to gen1)'}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
