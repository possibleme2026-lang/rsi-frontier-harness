"""One line per genome, so a run can be attributed to a configuration at a glance.

The point of a genome is that two runs are comparable only if they differ in one thing.
This prints the knobs that the experiments actually moved, in the order they matter, and
flags a genome that leaves every mechanism off (which would make it a second copy of the
seed and not an experiment).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

KNOBS = (
    ("max_steps", "steps", 0),
    ("max_output_tokens", "output", 0),
    ("artifact_gate", "gate", 0),
    ("step_countdown", "down", 0),
    ("retry_model_errors", "retry", 0),
    ("truncation_recovery", "trunc", 0),
    ("command_not_found_hint", "path", 0),
)


def main() -> int:
    header = f"{'genome':<10}" + "".join(f"{label:>8}" for _, label, _ in KNOBS) + f"{'blocks':>8}{'fp':>18}"
    print(header)
    for path in sorted((ROOT / "genomes").glob("*.json")):
        genome = json.loads(path.read_text(encoding="utf-8"))
        row = f"{genome['id']:<10}"
        for key, _, _ in KNOBS:
            value = genome.get(key)
            if isinstance(value, bool):
                value = int(value)
            row += f"{str(value):>8}"
        row += f"{len(genome.get('blocks') or []):>8}{genome['fingerprint']:>18}"
        print(row)

    print()
    print("blocks in use:")
    for path in sorted((ROOT / "genomes").glob("*.json")):
        genome = json.loads(path.read_text(encoding="utf-8"))
        extra = [b for b in (genome.get("blocks") or []) if b not in ("protocol.shell", "protocol.submit", "artifact.require_change")]
        if extra:
            print(f"  {genome['id']:<10} {', '.join(extra)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
