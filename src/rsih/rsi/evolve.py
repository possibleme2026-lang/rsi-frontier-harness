"""The self-improvement loop.

The loop is a *gated* hill climb over harness genomes.  A candidate is adopted only
when the paired evidence from the same task set clears a measured noise floor:

    floor = z * sqrt(b + c) / n        (b, c = discordant pairs, z = 2)

That single rule is what separates a self-improving system from a system that
believes it improved itself.  Two outcomes get their own names in the ledger,
because they are different findings:

* ``rejected_within_noise`` - "we could not tell the difference"
* ``rejected_worse``        - "the candidate was worse"

A candidate that does not move the pass rate may still be adopted for *cost*
(``accepted_cost``), but only if it is not worse on pass rate beyond the same
floor and cuts measured cost by at least ``cost_margin``.  Cost is measured with
the same token accounting the report uses, so a cheap harness cannot be cheap by
having failed to record its usage.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..agent.genome import Genome, GenomeLibrary
from ..bench.runner import TrialResult, run_trials
from ..bench.tasks import Task
from ..config import Settings, settings as default_settings
from ..llm.client import LLMClient, client_from_env
from .analyst import Analysis, analyse
from .mutators import MUTATIONS, propose, sample_labels


# --------------------------------------------------------------------- outcomes


@dataclass
class Outcome:
    genome: Genome
    run_id: str
    run_dir: Path
    results: list[TrialResult]

    @property
    def valid(self) -> list[TrialResult]:
        return [r for r in self.results if r.status in ("success", "failure")]

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "success")

    @property
    def pass_rate(self) -> float | None:
        return self.passed / len(self.valid) if self.valid else None

    def outcomes(self) -> dict[str, bool]:
        return {r.task_id: r.status == "success" for r in self.results if r.status in ("success", "failure")}

    def cost(self) -> float | None:
        costs = [r.cost_usd for r in self.results if r.cost_usd is not None]
        if len(costs) != len(self.results) or not costs:
            return None
        return sum(costs)

    def cost_coverage(self) -> float:
        known = sum(1 for r in self.results if r.cost_usd is not None)
        return known / len(self.results) if self.results else 0.0

    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "genome_id": self.genome.id,
            "fingerprint": self.genome.fingerprint(),
            "passed": self.passed,
            "valid": len(self.valid),
            "expected": len(self.results),
            "pass_rate": self.pass_rate,
            "cost_usd": self.cost(),
            "cost_coverage": self.cost_coverage(),
            "turns": sum(r.turns for r in self.results),
        }


@dataclass
class Decision:
    accepted: bool
    reason: str
    diff: float
    floor: float
    discordant: int
    n: int
    child_wins: list[str] = field(default_factory=list)
    incumbent_wins: list[str] = field(default_factory=list)
    cost_ratio: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def paired_decision(
    incumbent: Outcome,
    child: Outcome,
    *,
    z: float = 2.0,
    cost_margin: float = 0.85,
) -> Decision:
    left = incumbent.outcomes()
    right = child.outcomes()
    shared = sorted(set(left) & set(right))
    if not shared:
        return Decision(False, "no_shared_cells", 0.0, 0.0, 0, 0)

    b = [t for t in shared if right[t] and not left[t]]  # child wins
    c = [t for t in shared if left[t] and not right[t]]  # incumbent wins
    n = len(shared)
    diff = (len(b) - len(c)) / n
    floor = z * ((len(b) + len(c)) ** 0.5) / n

    if diff > floor and diff > 0:
        return Decision(True, "accepted_better", diff, floor, len(b) + len(c), n, b, c)

    incumbent_cost = incumbent.cost()
    child_cost = child.cost()
    cost_ratio = None
    if incumbent_cost and child_cost is not None and incumbent_cost > 0:
        cost_ratio = child_cost / incumbent_cost
    if (
        cost_ratio is not None
        and cost_ratio <= cost_margin
        and diff >= -floor
        and len(child.valid) == len(incumbent.valid)
        and child.passed >= incumbent.passed - 0
    ):
        return Decision(True, "accepted_cost", diff, floor, len(b) + len(c), n, b, c, cost_ratio)

    reason = "rejected_worse" if diff < 0 else "rejected_within_noise"
    return Decision(False, reason, diff, floor, len(b) + len(c), n, b, c, cost_ratio)


# ---------------------------------------------------------------------- splits


def split_tasks(tasks: list[Task], *, holdout: float = 0.35, seed: str = "fh-v1") -> tuple[list[Task], list[Task]]:
    """Deterministic, disclosed split of the runnable suite.

    Tasks are ordered by a hash of (id, seed) and every k-th task becomes holdout.
    The RSI loop never sees holdout results, so the final number is not a fitted
    number; the split is printed with every run so a reader can re-derive it.
    """
    ordered = sorted(tasks, key=lambda t: hashlib.sha256(f"{seed}:{t.id}".encode()).hexdigest())
    holdout_count = max(1, round(len(ordered) * holdout))
    step = max(2, len(ordered) // holdout_count) if holdout_count else len(ordered)
    holdout_ids = {ordered[i].id for i in range(0, len(ordered), step)}
    train = [t for t in ordered if t.id not in holdout_ids]
    test = [t for t in ordered if t.id in holdout_ids]
    if not train:  # pathological small suite
        train, test = ordered[:1], ordered[1:]
    return train, test


# ------------------------------------------------------------------- the loop


@dataclass
class EvolutionConfig:
    generations: int = 4
    proposals_per_generation: int = 3
    z: float = 2.0
    cost_margin: float = 0.85
    concurrency: int = 3
    seed: int = 7
    analyst_tasks: int = 5


class EvolutionLoop:
    def __init__(
        self,
        tasks: list[Task],
        *,
        settings: Settings | None = None,
        config: EvolutionConfig | None = None,
        seed_genome: Genome | None = None,
        root_name: str | None = None,
    ):
        self.settings = settings or default_settings()
        self.tasks = tasks
        self.config = config or EvolutionConfig()
        self.rng = random.Random(self.config.seed)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.root = self.settings.runs_dir / (root_name or f"rsi-{stamp}")
        self.root.mkdir(parents=True, exist_ok=True)
        self.library = GenomeLibrary(self.root / "genomes")
        self.ledger_path = self.root / "ledger.jsonl"
        from ..agent.genome import default_genome

        self.incumbent = seed_genome or default_genome()
        self.library.save(self.incumbent)
        self.client: LLMClient | None = None

    # ------------------------------------------------------------- utilities
    def _log(self, record: dict) -> None:
        record["at"] = time.time()
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _trial_log(self) -> LLMClient:
        if self.client is None:
            self.client = client_from_env(log_path=self.root / "analyst-calls.jsonl")
        return self.client

    def evaluate(self, genome: Genome, tag: str) -> Outcome:
        run_id = f"{self.root.name}-{tag}"
        results, run_dir = run_trials(
            self.tasks,
            genome,
            run_id=run_id,
            settings=self.settings,
            concurrency=self.config.concurrency,
            on_result=lambda r: print(
                f"    [{'PASS' if r.status == 'success' else r.status[:4].upper()}] "
                f"{r.task_id:<46} turns={r.turns:<3} "
                f"cost=${r.cost_usd:.4f}" if r.cost_usd is not None
                else f"    [{r.status[:4].upper()}] {r.task_id} (no cost)",
                flush=True,
            ),
        )
        outcome = Outcome(genome=genome, run_id=run_id, run_dir=run_dir, results=results)
        self._log({"event": "evaluation", **outcome.summary()})
        return outcome

    def _proposals(self, analysis: Analysis, generation: int) -> list[tuple[str, str | None]]:
        """The analyst's best structural idea first, then sampled hypotheses.

        The analyst's free-text patch rides along on whichever child is evaluated
        next rather than being a separate arm: instruction text and a structural
        edit are two descriptions of the same hypothesis, and testing them apart
        would spend a whole evaluation to learn nothing about their interaction.
        """
        labels: list[tuple[str, str | None]] = []
        for label in analysis.mutations[:1]:
            labels.append((label, None))
        need = max(0, self.config.proposals_per_generation - len(labels))
        sampled = sample_labels(
            self.incumbent,
            need,
            self.rng,
            exclude={label for label, _ in labels},
        )
        for label in sampled:
            labels.append((label, None))
        if analysis.patch:
            labels.append(("llm.prompt_patch", analysis.patch))
        return labels

    def run(self) -> dict:
        print(f"RSI loop root: {self.root}")
        print(f"evolve set ({len(self.tasks)}): {[t.short for t in self.tasks]}")
        self._log(
            {
                "event": "start",
                "tasks": [t.id for t in self.tasks],
                "config": asdict(self.config),
                "seed_genome": self.incumbent.to_dict(),
            }
        )
        incumbent_outcome = self.evaluate(self.incumbent, f"g0-{self.incumbent.id}")
        print(f"  seed: {incumbent_outcome.passed}/{len(incumbent_outcome.valid)} passes\n")

        for generation in range(1, self.config.generations + 1):
            failures = [r.as_dict() for r in incumbent_outcome.results if r.status != "success"]
            analysis = analyse(
                failures,
                self._trial_log(),
                tasks_by_id={t.id: t for t in self.tasks},
                runs_dir=incumbent_outcome.run_dir,
                max_tasks=self.config.analyst_tasks,
            )
            print(f"generation {generation}: analyst pattern = {analysis.pattern!r}")
            if analysis.rules:
                for rule in analysis.rules:
                    print(f"  rule: {rule}")
            if analysis.mutations:
                print(f"  analyst mutations: {analysis.mutations}")

            best: tuple[Outcome, str, str | None] | None = None
            for index, (label, patch) in enumerate(self._proposals(analysis, generation)):
                child_id = f"g{generation}c{index}"
                child = propose(self.incumbent, child_id, label, extra_prompt=patch or analysis.patch)
                if child is None:
                    continue
                self.library.save(child)
                print(f"  evaluating {child_id}: {label}")
                outcome = self.evaluate(child, f"g{generation}-{child_id}")
                decision = paired_decision(
                    incumbent_outcome, outcome, z=self.config.z, cost_margin=self.config.cost_margin
                )
                self._log(
                    {
                        "event": "proposal",
                        "generation": generation,
                        "mutation": label,
                        "patch": patch or analysis.patch or "",
                        "parent": self.incumbent.id,
                        "child": child.id,
                        "child_summary": outcome.summary(),
                        "incumbent_summary": incumbent_outcome.summary(),
                        "decision": decision.as_dict(),
                    }
                )
                print(
                    f"    -> {outcome.passed}/{len(outcome.valid)} passes, "
                    f"diff={decision.diff:+.3f} floor={decision.floor:.3f} "
                    f"({decision.reason})"
                )
                if decision.accepted and (best is None or outcome.passed > best[0].passed):
                    best = (outcome, label, patch)

            if best is None:
                self._log({"event": "generation_end", "generation": generation, "accepted": None})
                print("  no candidate cleared the floor; incumbent stands\n")
                continue

            outcome, label, patch = best
            self.incumbent = outcome.genome
            incumbent_outcome = outcome
            self.library.save(self.incumbent)
            self._log(
                {
                    "event": "generation_end",
                    "generation": generation,
                    "accepted": self.incumbent.id,
                    "mutation": label,
                    "summary": outcome.summary(),
                }
            )
            print(f"  adopted {self.incumbent.id} ({label}): {outcome.passed}/{len(outcome.valid)}\n")

        summary = {
            "event": "end",
            "incumbent": self.incumbent.to_dict(),
            "incumbent_summary": incumbent_outcome.summary(),
            "ledger": str(self.ledger_path),
        }
        self._log(summary)
        (self.root / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return summary


def mutation_catalogue() -> dict[str, dict[str, str]]:
    return {
        name: {"component": m.component, "hypothesis": m.hypothesis} for name, m in MUTATIONS.items()
    }
