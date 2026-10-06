"""Re-decide an existing evolution ledger from its own artifacts.

The measurements a ledger records are per-task trials; the *rule* applied to them is
code.  When the rule changes, the honest thing is not to re-run the experiment and
quietly publish the new verdict - it is to replay the same evidence through both rules
and show which decisions move.  That is what this does, using a stored run's trial
directories directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.rsi.evolve import Outcome, paired_cost_t, paired_decision  # noqa: E402


def load_outcome(run_dir: Path, genome_id: str) -> Outcome:
    from rsih.agent.genome import GenomeLibrary
    from rsih.bench.runner import TrialResult

    trials = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(run_dir.glob("trials/*/trial.json"))
    ]
    # A cell that was retried leaves two trial directories behind.  They are two
    # attempts at one cell, not two cells: scoring both would double-count the task in
    # every total.  Keep the resolved attempt.
    by_task: dict[str, dict] = {}
    for trial in trials:
        previous = by_task.get(trial["id"])
        if previous is None or previous["status"] == "infra_invalid":
            by_task[trial["id"]] = trial
    trials = list(by_task.values())
    library = GenomeLibrary(ROOT / "genomes")
    try:
        genome = library.load(genome_id)
    except FileNotFoundError:
        genome = library.load("gen1")
    results = [TrialResult.from_dict(t) for t in trials]
    return Outcome(genome=genome, run_id=run_dir.name, run_dir=run_dir, results=results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", help="runs/<evolve-run-id>")
    parser.add_argument("--z", type=float, default=2.0)
    parser.add_argument("--margin", type=float, default=0.85)
    args = parser.parse_args()

    root = Path(args.run_root)
    ledger = root / "ledger.jsonl"
    entries = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]

    evaluations = {e["run_id"]: e for e in entries if e.get("event") == "evaluation"}
    print(f"{'child':<8}{'mutation':<32}{'ratio':>8}{'t':>8}  {'recorded':<26}{'replayed'}")
    changed = 0
    for entry in entries:
        if entry.get("event") != "proposal":
            continue
        child_summary = entry["child_summary"]
        incumbent_summary = entry["incumbent_summary"]
        child_dir = root.parent / child_summary["run_id"]
        incumbent_dir = root.parent / incumbent_summary["run_id"]
        if not child_dir.is_dir() or not incumbent_dir.is_dir():
            print(f"{entry['child']:<8}(trial directories missing, skipped)")
            continue
        incumbent = load_outcome(incumbent_dir, incumbent_summary["genome_id"])
        child = load_outcome(child_dir, child_summary["genome_id"])
        recorded = entry["decision"]["reason"]
        replay = paired_decision(incumbent, child, z=args.z, cost_margin=args.margin)
        t = paired_cost_t(incumbent, child)
        mark = "  <-- CHANGED" if replay.reason != recorded else ""
        changed += replay.reason != recorded
        print(
            f"{entry['child']:<8}{entry['mutation']:<32}{replay.cost_ratio or 0:>8.3f}"
            f"{(t if t is not None else float('nan')):>8.2f}  {recorded:<26}{replay.reason}{mark}"
        )
    print(f"\n{changed} decision(s) change under the paired cost floor at z={args.z:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
