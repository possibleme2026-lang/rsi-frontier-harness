"""Would the dense gate decide differently from the pass-count gate, on real runs?

The pass-count gate needs a net swing of several cells before it accepts anything, and on
a six-task evolve split that is rare enough that the loop mostly learns nothing.  This
replays both gates over runs that were actually paid for, so the change is justified by
measurement rather than by the argument that a denser signal must be better.

It also prints the per-task credit table, because a gate is only as honest as the numbers
it reads: the interesting question is whether the dense gate ever *fights* the pass gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.agent.genome import GenomeLibrary  # noqa: E402
from rsih.bench.runner import TrialResult  # noqa: E402
from rsih.rsi.evolve import Outcome, paired_capability_t, paired_decision  # noqa: E402

PAIRS = [
    ("gen1 (deepswe-9)", "runs/deepswe-9", "gen6", "runs/gen6-full"),
    ("gen1 (deepswe-9)", "runs/deepswe-9", "gen4", "runs/gen4-full"),
    ("gen1 (deepswe-9)", "runs/deepswe-9", "gen5", "runs/gen5-full"),
]

#: Runs that exist but whose verifier detail has to come from the sibling reward.json,
#: because they were paid for before the report was being copied into trial.json.
FALLBACK_DETAIL = True


def load(run: str, genome_id: str | None) -> Outcome:
    run_dir = ROOT / run
    results = []
    for path in sorted(run_dir.glob("trials/*/trial.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        detail = payload.get("verifier_detail") or {}
        if not detail and FALLBACK_DETAIL:
            raw = path.parent / "reward.json"
            if raw.is_file():
                try:
                    detail = json.loads(raw.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    detail = {}
        results.append(
            TrialResult(
                task_id=payload["id"],
                genome_id=payload.get("genome_id", ""),
                genome_fingerprint=payload.get("genome_fingerprint", ""),
                status=payload["status"],
                reward=payload.get("reward"),
                turns=int(payload.get("turns") or 0),
                duration_s=float(payload.get("duration_seconds") or 0.0),
                cost_usd=payload.get("cost_usd"),
                cost_first_cold_usd=payload.get("cost_first_cold_usd"),
                usage=payload.get("usage") or {},
                exit_reason=payload.get("exit_reason", ""),
                error=payload.get("error"),
                artifacts=path.parent,
                extra={"verifier_detail": detail},
            )
        )
    library = GenomeLibrary(ROOT / "genomes")
    try:
        genome = library.load(genome_id) if genome_id else None
    except Exception:  # noqa: BLE001 - the genome object is only a label here
        genome = None
    return Outcome(genome=genome, run_id=run, run_dir=run_dir, results=results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--z", type=float, default=2.0)
    parser.add_argument("--left", help="run directory to treat as the incumbent")
    parser.add_argument("--right", help="run directory to treat as the candidate")
    parser.add_argument("--left-genome", default=None)
    parser.add_argument("--right-genome", default=None)
    args = parser.parse_args()

    if args.left or args.right:
        if not (args.left and args.right):
            parser.error("--left and --right must be given together")
        pairs = [(args.left, args.left, args.right_genome or args.right, args.right)]
    else:
        pairs = PAIRS

    for label, left_run, right_genome, right_run in pairs:
        if not (ROOT / right_run).is_dir():
            if args.left:
                print(f"{right_run}: no such run")
            continue
        incumbent = load(left_run, None)
        child = load(right_run, right_genome)
        left_scores = incumbent.capability()
        right_scores = child.capability()
        shared = sorted(set(left_scores) & set(right_scores))
        if not shared:
            print(f"{label} vs {right_genome}: no shared cells")
            continue

        decision = paired_decision(incumbent, child, z=args.z)
        cap_t = paired_capability_t(incumbent, child)
        dense = sum(right_scores[t] for t in shared) - sum(left_scores[t] for t in shared)

        print(f"=== {label}  vs  {right_genome} ({len(shared)} shared cells)")
        for task in shared:
            mark = " " if left_scores[task] == right_scores[task] else "*"
            print(
                f"  {mark} {task.split('/')[-1][:40]:<42} "
                f"{left_scores[task]:>6.3f} -> {right_scores[task]:>6.3f}"
            )
        shared_pass_left = sum(1 for t in shared if left_scores[t] == 1.0)
        shared_pass_right = sum(1 for t in shared if right_scores[t] == 1.0)
        print(
            f"  passes on the shared cells {shared_pass_left} -> {shared_pass_right}   "
            f"credit {dense:+.3f}   capability_t="
            f"{cap_t if cap_t is None else round(cap_t, 2)}"
        )
        print(
            f"  gate: accepted={decision.accepted} reason={decision.reason} "
            f"diff={decision.diff:+.3f} floor={decision.floor:.3f}"
        )
        print()

    print(
        "Reading: 'accepted_capability' is a decision the pass-count gate could not make.\n"
        "A cell marked * moved on the graded fractions; a pass still counts as 1.0."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
