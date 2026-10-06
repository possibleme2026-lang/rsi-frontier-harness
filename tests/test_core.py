"""Unit tests for the parts of the system whose bugs would silently corrupt results.

No network and no Docker: everything here is either pure logic or a synthetic
artifact on disk.  The tests that matter most are the noise-floor decisions
(``test_paired_decision_*``) and the accounting (``test_cost_ledger_*``), because a
wrong answer there produces a confident wrong report.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rsih.agent.genome import ALL_TOOLS, Genome, GenomeLibrary, default_genome
from rsih.bench.sandbox import CWD_SENTINEL, EXIT_SENTINEL, DockerSandbox
from rsih.llm.pricing import CostLedger, RateCard, Usage, rate_card
from rsih.rsi.evolve import Outcome, paired_decision, split_tasks
from rsih.rsi.mutators import MUTATIONS, applicable, propose
from rsih.rsi.report import build_report, load_run

CARD = RateCard(fresh_input=0.28, cache_write=0.28, cache_read=0.028, output=0.42, source="test")


# --------------------------------------------------------------------- pricing


def test_rate_card_prices_cached_input_cheaper():
    card = CARD
    fresh = Usage(prompt_tokens=1_000_000, completion_tokens=0, cached_tokens=0)
    cached = Usage(prompt_tokens=1_000_000, completion_tokens=0, cached_tokens=1_000_000)
    assert card.price(fresh) == pytest.approx(0.28)
    assert card.price(cached) == pytest.approx(0.028)


def test_cost_ledger_refuses_partial_sum():
    ledger = CostLedger(card=CARD)
    ledger.record(Usage(prompt_tokens=1000, completion_tokens=100, cached_tokens=0))
    assert ledger.cost_usd() is not None
    ledger.record(Usage())  # a call with no usage payload
    assert not ledger.complete
    assert ledger.cost_usd() is None


def test_usage_add_keeps_missing_as_missing():
    assert Usage().add(Usage()).prompt_tokens is None
    assert Usage(prompt_tokens=5).add(Usage(prompt_tokens=7)).prompt_tokens == 12


def test_repo_rate_card_loads_declared_model():
    card = rate_card("DeepSeek-V4.1-Flash")
    assert card.fresh_input > card.cache_read
    with pytest.raises(KeyError):
        rate_card("no-such-model")


# ---------------------------------------------------------------------- genome


def test_genome_fingerprint_is_content_addressed():
    a = default_genome()
    b = default_genome()
    assert a.fingerprint() == b.fingerprint()
    c = a.derive("gen0x", mutation="test", extra_prompt="be careful")
    assert c.fingerprint() != a.fingerprint()


def test_genome_rejects_removing_the_submit_tool():
    with pytest.raises(ValueError):
        Genome(id="bad", blocks=default_genome().blocks, tools=("bash",))


def test_genome_rejects_unknown_block():
    with pytest.raises(ValueError):
        Genome(id="bad", blocks=("submit.contract", "nope.block"))


def test_genome_round_trip(tmp_path: Path):
    library = GenomeLibrary(tmp_path)
    genome = default_genome("genA").derive("genB", mutation="test", max_steps=42)
    library.save(genome)
    loaded = library.load("genB")
    assert loaded.fingerprint() == genome.fingerprint()
    assert loaded.max_steps == 42
    assert loaded.lineage[-1].endswith("test")


def test_system_prompt_includes_extra_text():
    genome = default_genome().derive("genX", mutation="patch", extra_prompt="- always read the file back")
    assert "always read the file back" in genome.system_prompt()


# -------------------------------------------------------------------- mutators


def test_every_mutation_is_applicable_somewhere_and_named():
    genome = default_genome()
    labels = applicable(genome)
    assert "prompt+=verify.self_check" in labels
    assert "tools+=files" not in labels  # already enabled in the seed
    child = propose(genome, "c1", "prompt+=verify.self_check")
    assert child is not None and "verify.self_check" in child.blocks
    assert child.lineage[-1] == "gen0:prompt+=verify.self_check"
    assert "submit.contract" in child.blocks


def test_mutation_returns_none_when_already_applied():
    genome = default_genome()
    assert propose(genome, "c1", "prompt+=verify.self_check") is not None
    once = propose(genome, "c1", "prompt+=verify.self_check")
    assert propose(once, "c2", "prompt+=verify.self_check") is None


def test_prompt_patch_mutation_is_recorded_verbatim():
    genome = default_genome()
    child = propose(genome, "c9", "llm.prompt_patch", extra_prompt="- check exit codes")
    assert child is not None and child.extra_prompt == "- check exit codes"
    assert propose(child, "c10", "llm.prompt_patch", extra_prompt="- check exit codes") is None


def test_mutation_catalogue_covers_all_labels():
    assert "llm.prompt_patch" not in MUTATIONS  # analyst-driven, not a descriptor edit
    assert all(m.component in {"prompt", "tools", "loop"} for m in MUTATIONS.values())


# --------------------------------------------------------------- noise floor


def _outcome(tmp_path: Path, genome: Genome, outcomes: dict[str, bool], cost: float = 1.0) -> Outcome:
    results = []
    for task_id, ok in outcomes.items():
        results.append(
            type(
                "R",
                (),
                {
                    "task_id": task_id,
                    "status": "success" if ok else "failure",
                    "cost_usd": cost / len(outcomes),
                    "turns": 1,
                },
            )()
        )
    return Outcome(genome=genome, run_id="t", run_dir=tmp_path, results=results)


def test_paired_decision_no_discordance_is_within_noise(tmp_path: Path):
    genome = default_genome()
    same = {f"t{i}": i % 2 == 0 for i in range(20)}
    incumbent = _outcome(tmp_path, genome, same)
    child = _outcome(tmp_path, genome, dict(same))
    decision = paired_decision(incumbent, child)
    assert not decision.accepted
    assert decision.reason == "rejected_within_noise"
    assert decision.floor == 0.0


def test_paired_decision_requires_beating_the_floor(tmp_path: Path):
    genome = default_genome()
    incumbent = _outcome(tmp_path, genome, {f"t{i}": False for i in range(20)})
    # One extra pass out of 20 does not clear z*sqrt(1)/20 = 0.1.
    child = _outcome(tmp_path, genome, {f"t{i}": i == 0 for i in range(20)})
    assert not paired_decision(incumbent, child).accepted
    # Ten extra passes do.
    child_big = _outcome(tmp_path, genome, {f"t{i}": i < 10 for i in range(20)})
    decision = paired_decision(incumbent, child_big)
    assert decision.accepted and decision.reason == "accepted_better"


def test_paired_decision_rejects_a_regression(tmp_path: Path):
    genome = default_genome()
    incumbent = _outcome(tmp_path, genome, {f"t{i}": True for i in range(20)})
    child = _outcome(tmp_path, genome, {f"t{i}": i % 2 == 0 for i in range(20)})
    decision = paired_decision(incumbent, child)
    assert not decision.accepted and decision.reason == "rejected_worse"


def test_paired_decision_adopts_a_cost_win_at_equal_pass_rate(tmp_path: Path):
    genome = default_genome()
    same = {f"t{i}": True for i in range(20)}
    incumbent = _outcome(tmp_path, genome, same, cost=1.0)
    child = _outcome(tmp_path, genome, dict(same), cost=0.5)
    decision = paired_decision(incumbent, child, cost_margin=0.85)
    assert decision.accepted and decision.reason == "accepted_cost"
    assert decision.cost_ratio == pytest.approx(0.5)


def test_paired_decision_refuses_cost_win_with_a_regression(tmp_path: Path):
    genome = default_genome()
    incumbent = _outcome(tmp_path, genome, {f"t{i}": True for i in range(20)}, cost=1.0)
    child = _outcome(tmp_path, genome, {f"t{i}": i > 0 for i in range(20)}, cost=0.1)
    assert not paired_decision(incumbent, child, cost_margin=0.85).accepted


def test_split_is_deterministic_and_disjoint():
    class T:
        def __init__(self, name: str):
            self.id = f"terminal-bench/{name}"
            self.short = name

    tasks = [T(f"task-{i}") for i in range(21)]
    train_a, holdout_a = split_tasks(tasks)
    train_b, holdout_b = split_tasks(tasks)
    assert [t.id for t in train_a] == [t.id for t in train_b]
    assert [t.id for t in holdout_a] == [t.id for t in holdout_b]
    assert not ({t.id for t in train_a} & {t.id for t in holdout_a})
    assert len(train_a) + len(holdout_a) == len(tasks)


# --------------------------------------------------------------------- sandbox


def test_sandbox_splits_sentinels_from_output():
    text = f"hello\n{CWD_SENTINEL}/app/sub\n{EXIT_SENTINEL}3\n"
    output, code, cwd = DockerSandbox._split(text, 0)
    assert code == 3
    assert cwd == "/app/sub"
    assert output.strip() == "hello"


def test_sandbox_split_tolerates_missing_sentinels():
    output, code, cwd = DockerSandbox._split("partial output", 124)
    assert code == 124 and cwd is None and output == "partial output"


# ---------------------------------------------------------------------- report


def _write_trial(run_dir: Path, task: str, status: str, cost: float, prompt: int, cached: int, turns: int):
    trial_dir = run_dir / "trials" / task
    trial_dir.mkdir(parents=True, exist_ok=True)
    (trial_dir / "trial.json").write_text(
        json.dumps(
            {
                "id": f"terminal-bench/{task}",
                "status": status,
                "success": status == "success",
                "turns": turns,
                "cost_usd": cost,
                "cost_first_cold_usd": cost,
                "duration_seconds": 100.0,
                "usage": {"prompt_tokens": prompt, "completion_tokens": 10, "cached_tokens": cached},
            }
        ),
        encoding="utf-8",
    )


def test_load_run_computes_benchmark_metrics(tmp_path: Path):
    run_dir = tmp_path / "run1"
    (run_dir).mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": "run1", "model": "m", "genome": {"id": "g0", "fingerprint": "abc"}}),
        encoding="utf-8",
    )
    _write_trial(run_dir, "a", "success", 0.10, 1000, 900, 5)
    _write_trial(run_dir, "b", "failure", 0.30, 1000, 0, 9)
    candidate = load_run(run_dir, label="Test Harness")
    assert candidate.passes == 1 and candidate.valid == 2
    assert candidate.pass_rate == pytest.approx(0.5)
    # cost per pass includes the failed task's cost
    assert candidate.effective_cost_per_pass == pytest.approx(0.40)
    assert candidate.median_cost_per_task == pytest.approx(0.20)
    # cache rate is token-weighted over successes only
    assert candidate.cache_hit_rate_normalized == pytest.approx(0.9)
    assert candidate.cache_coverage == pytest.approx(1.0)


def test_load_run_reports_null_when_costs_are_missing(tmp_path: Path):
    run_dir = tmp_path / "run2"
    run_dir.mkdir(parents=True, exist_ok=True)
    trial_dir = run_dir / "trials" / "a"
    trial_dir.mkdir(parents=True)
    (trial_dir / "trial.json").write_text(
        json.dumps({"id": "terminal-bench/a", "status": "success", "turns": 3, "cost_first_cold_usd": None}),
        encoding="utf-8",
    )
    candidate = load_run(run_dir)
    assert candidate.effective_cost_per_pass is None
    assert candidate.median_cost_per_task is None
    assert candidate.cost_coverage == 0.0


def test_build_report_writes_markdown_and_chart(tmp_path: Path, eval_repo: Path):
    run_dir = tmp_path / "run3"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_trial(run_dir, "regex-log", "success", 0.01, 1000, 800, 13)
    result = build_report(run_dir, eval_repo, label="RSIH gen0")
    report = Path(result["report"])
    chart = Path(result["chart"])
    assert report.is_file() and chart.is_file()
    body = report.read_text(encoding="utf-8")
    assert "Median cost per task" in body
    assert "not leaderboard-comparable" in body
    svg = chart.read_text(encoding="utf-8")
    assert "<svg" in svg and "polygon" in svg
    # the baseline table must be recomputed on the shared task id, not the 30-task aggregate
    regex_row = next(row for row in result["baselines"] if row["name"] == "codex")
    assert regex_row["shared"]["n"] == 1


# ------------------------------------------------------- verifier health triage


def test_verifier_setup_failure_is_not_an_agent_failure():
    """A reward of 0 written after the verifier's own install failed says nothing."""
    from rsih.bench.runner import verifier_setup_failure

    flaky = (
        "Err:1 http://deb.debian.org/debian bookworm InRelease\n"
        "  502  Bad Gateway [IP: 146.75.114.132 80]\n"
        "E: Unable to locate package curl\n"
        "/tests/test.sh: line 8: curl: command not found\n"
        "/tests/test.sh: line 19: uvx: command not found\n"
    )
    assert verifier_setup_failure(flaky)

    real = (
        "FAILED ../tests/test_outputs.py::test_speedup[5] - AssertionError: 0.000015 s\n"
        "========================= 5 failed, 22 passed in 0.66s =========================\n"
    )
    assert verifier_setup_failure(real) is None

    # the missing env file alone is a warning: uv still ran the suite
    mixed = "/tests/test.sh: line 9: /root/.local/bin/env: No such file or directory\n1 failed in 0.07s\n"
    assert verifier_setup_failure(mixed) is None
