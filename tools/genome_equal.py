"""Field-by-field comparison of two genomes, including the ones a diff tool would hide.

Asking whether two configurations are the same is not the same as asking whether two
genome files are byte-identical: `max_output_tokens: null` and `max_output_tokens: 0` both
mean "no cap" to the loop, and if that is the only difference between two ids then runs
under one are runs under the other.  That distinction decides whether a reported table may
legitimately pool the two, so it is printed field by field rather than assumed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.agent.genome import Genome  # noqa: E402


def load(name: str) -> Genome:
    return Genome.from_dict(json.loads((ROOT / "genomes" / f"{name}.json").read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left")
    parser.add_argument("right")
    args = parser.parse_args()

    left, right = load(args.left), load(args.right)
    a, b = left.to_dict(), right.to_dict()

    print(f"{args.left}  fingerprint {left.fingerprint()}")
    print(f"{args.right}  fingerprint {right.fingerprint()}")
    print(f"behavioural fingerprint equal: {left.fingerprint() == right.fingerprint()}")
    print()
    keys = sorted(set(a) | set(b))
    differences = 0
    for key in keys:
        if a.get(key) == b.get(key):
            continue
        differences += 1
        print(f"  {key}:")
        print(f"    {args.left:<10} {a.get(key)!r}")
        print(f"    {args.right:<10} {b.get(key)!r}")
    if not differences:
        print("  every stored field is equal")
    print()
    print(f"stored fields that differ: {differences}")
    print()
    print("Whether a difference is behavioural is decided by fingerprint() above, which is")
    print("what the runner records on every trial: identical fingerprints mean the runs are")
    print("poolable even when the files differ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
