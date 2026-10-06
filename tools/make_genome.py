"""Write a single-mutation genome next to the library's entries.

The evolution loop reaches a mutation through a sampled proposal; a controlled A/B
needs the same edit applied deliberately, with nothing else changed, so the measured
difference can only be that edit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.agent.genome import GenomeLibrary  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", help="genome id to start from")
    parser.add_argument("new_id")
    parser.add_argument("edits", nargs="+", help="field=value, e.g. max_output_tokens=2048")
    args = parser.parse_args()

    library = GenomeLibrary(ROOT / "genomes")
    genome = library.load(args.base)
    payload = genome.to_dict()
    for edit in args.edits:
        key, _, raw = edit.partition("=")
        if key not in payload:
            raise SystemExit(f"unknown field {key!r}")
        current = payload[key]
        if isinstance(current, bool):
            value: object = raw.lower() in ("1", "true", "yes")
        elif isinstance(current, int) and not isinstance(current, bool):
            value = int(raw)
        elif isinstance(current, float):
            value = float(raw)
        else:
            value = raw
        payload[key] = value
    payload["id"] = args.new_id
    payload["parent_id"] = genome.id
    payload["label"] = " + ".join(args.edits)
    child = type(genome).from_dict(payload)
    library.save(child)
    print(
        f"{child.id}: parent={genome.id} fingerprint={child.fingerprint()} "
        f"edits={args.edits}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



