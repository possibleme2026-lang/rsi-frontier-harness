"""Print a human-readable transcript of one trial.

Used for evidence review: before any claim about *why* a task passed or failed goes
into a report, the transcript is read.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trial", help="path to runs/<run>/trials/<task>")
    parser.add_argument("--chars", type=int, default=300)
    parser.add_argument("--steps", type=int, default=100)
    args = parser.parse_args()

    trial_dir = Path(args.trial)
    trial = json.loads((trial_dir / "trial.json").read_text(encoding="utf-8"))
    print(
        f"{trial['id']} status={trial['status']} reward={trial['reward']} turns={trial['turns']} "
        f"exit={trial['exit_reason']} cost=${trial.get('cost_first_cold_usd')}"
    )
    episode = json.loads((trial_dir / "episode.json").read_text(encoding="utf-8"))
    for step in episode["steps"][: args.steps]:
        say = (step.get("content") or "").strip()
        print(f"\n--- step {step['index']} (prompt={step['usage'].get('prompt_tokens')} "
              f"cached={step['usage'].get('cached_tokens')} out={step['usage'].get('completion_tokens')})")
        if say:
            print(f"SAY: {say[: args.chars]}")
        for call in step.get("tool_calls", []):
            print(f"CALL {call['name']}: {json.dumps(call.get('arguments', {}), ensure_ascii=False)[: args.chars * 2]}")
            print(f"  -> {str(call.get('observation', ''))[: args.chars]}")
    print(f"\nfinal reward file: {(trial_dir / 'reward.txt').read_text(encoding='utf-8').strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
