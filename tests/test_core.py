"""Unit tests for the parts of the system whose bugs would silently corrupt results.

No network and no Docker: everything here is either pure logic or a synthetic
artifact on disk.  The tests that matter most are the noise-floor decisions
(``test_paired_decision_*``) and the accounting (``test_cost_ledger_*``), because a
wrong answer there produces a confident wrong report.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rsih.agent.genome import (
    ALL_TOOLS,
    REFERENCE_AGENT_SECONDS,
    STEP_BUDGET_CEILING,
    Genome,
    GenomeLibrary,
    default_genome,
)
from rsih.agent.loop import (
    ARTIFACT_GATE_TEXT,
    ENDGAME_TEXT,
    TRUNCATION_TEXT,
    AgentLoop,
    _gate_due,
    _retry_schedule,
)
from rsih.agent.tools import _is_product_path, _looks_like_missing_command
from rsih.bench.sandbox import CWD_SENTINEL, EXIT_SENTINEL, DockerSandbox
from rsih.llm.client import LLMError, LLMResponse, ToolCall
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


def test_step_budget_policy_is_inert_inside_terminal_bench():
    """The policy's blast radius is part of its definition, so pin it.

    Every terminal-bench cell in the frozen suite declares at most
    ``REFERENCE_AGENT_SECONDS``, so turning the policy on must leave all of them at the
    genome's literal cap -- otherwise a result measured with it off would not carry
    over to a run with it on.
    """
    genome = default_genome("genPolicy").derive("genPolicyOn", mutation="test",
                                                steps_from_declared_budget=True)
    assert genome.effective_max_steps(REFERENCE_AGENT_SECONDS) == genome.max_steps
    for declared in (60.0, 600.0, 900.0, 1200.0, 1800.0):
        assert genome.effective_max_steps(declared) == genome.max_steps
    # a long declared budget buys steps, multiplicatively and with a ceiling
    assert genome.effective_max_steps(REFERENCE_AGENT_SECONDS * 3) == genome.max_steps * 3
    assert (
        genome.effective_max_steps(REFERENCE_AGENT_SECONDS * 100)
        == genome.max_steps * int(STEP_BUDGET_CEILING)
    )
    # off by default, and unchanged for a genome that never opted in
    assert default_genome().effective_max_steps(5400.0) == default_genome().max_steps
    assert genome.effective_max_steps(None) == genome.max_steps


def test_step_budget_policy_changes_the_fingerprint():
    a = default_genome("genA")
    b = a.derive("genB", mutation="test", steps_from_declared_budget=True)
    assert a.fingerprint() != b.fingerprint()


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


# --------------------------------------------------- loop robustness the research forced
#
# Each of these covers a change that was made because a failure was *measured*: episodes
# that ended on a transient gateway error, episodes that were stopped mid-thought by the
# output cap, and episodes that spent their whole budget without editing the product.


def test_retry_schedule_is_off_by_default_and_bounded():
    assert _retry_schedule(0) == []
    waits = _retry_schedule(5)
    assert len(waits) == 5
    assert waits == sorted(waits), "backoff must not go backwards"
    assert waits[0] >= 1.0 and waits[-1] <= 90.0


def test_artifact_gate_fires_on_a_fifth_of_the_budget():
    for cap in (20, 60, 100):
        fired = [i for i in range(cap) if _gate_due(i, cap)]
        assert 4 <= len(fired) <= 6, (cap, fired)
        assert fired[-1] < cap, "the gate must not fire on the final step only"
    # a short episode still gets more than one chance
    assert _gate_due(2, 10)


def test_product_path_excludes_scratch_and_test_material():
    # the two measured scratch-only patches, verbatim from the audit
    assert not _is_product_path("ark/json-schema/scratch.ts")
    assert not _is_product_path("scratch/t1.ts")
    assert not _is_product_path("scratch_msg_test.go")
    # a checked-in test file is not the deliverable either
    assert not _is_product_path("tests/test_multipart_response.py")
    assert not _is_product_path("src/foo.test.ts")
    # but real product source is what the gate is looking for
    for path in (
        "fastapi/routing.py",
        "src/parser.ts",
        "processor/formatters.go",
        "statemachine/state_data.py",
        "parser/parser.go.y",
        "httpx/_multipart_response.py",
    ):
        assert _is_product_path(path), path


def test_missing_command_is_only_inferred_for_shell_exec_failures():
    assert _looks_like_missing_command("bash: foo: command not found\n", 127)
    assert _looks_like_missing_command("bash: foo: command not found\n", None)
    # a missing *data* file reads the same way but must not trigger a PATH hint
    assert not _looks_like_missing_command("cat: /app/data.csv: No such file or directory\n", 1)
    assert not _looks_like_missing_command("", 0)


class _StubSandbox:
    """Minimal stand-in: the loop only needs exec_script to answer the gate's query."""

    def __init__(self, status_output: str = "", exit_code: int = 0):
        self.status_output = status_output
        self.exit_code = exit_code
        self.commands: list[str] = []

    def exec_script(self, command: str, timeout_s: float = 60.0):
        from rsih.bench.sandbox import ExecResult

        self.commands.append(command)
        return ExecResult(command, self.exit_code, self.status_output, 0.01, False)


class _ScriptedClient:
    """Returns queued responses; raises for entries that are exceptions."""

    def __init__(self, responses: list, model: str = "DeepSeek-V4.1-Flash"):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []
        # the loop only reads `.model` (to pick the rate card), so a stand-in avoids
        # building the whole application settings object for a unit test
        self.settings = SimpleNamespace(model=model)

    def complete(self, messages, **kwargs):
        self.calls.append([dict(m) for m in messages])
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _reply(content: str = "", calls: list[ToolCall] | None = None, finish: str = "stop"):
    from rsih.llm.pricing import Usage

    return LLMResponse(
        content=content,
        reasoning="",
        tool_calls=calls or [],
        usage=Usage(prompt_tokens=100, completion_tokens=10, cached_tokens=50),
        latency_s=0.1,
        finish_reason=finish,
        raw={},
    )


def _bash_call(command: str = "ls", call_id: str = "c1") -> ToolCall:
    return ToolCall(id=call_id, name="bash", arguments_raw="{}", arguments={"command": command})


def _task(tmp_path: Path):
    from rsih.bench.tasks import Task

    return Task(
        id="datacurve/example",
        suite="datacurve",
        name="example",
        instruction="Implement the feature.",
        docker_image="example:latest",
        cpus=2.0,
        memory_mb=8192,
        storage_mb=20480,
        agent_timeout_s=600.0,
        verifier_timeout_s=1800.0,
        allow_internet=False,
        workdir="/app",
        agent_timeout_declared_s=5400.0,
        collect_cmd="cd /app && git diff --binary abc HEAD > /tmp/model.patch",
        tests_dir=tmp_path,
    )


def test_episode_survives_a_transient_gateway_error(tmp_path: Path):
    """One 503 must not discard an episode that has already done work."""
    genome = default_genome("retry-on").derive(
        "retry-on", mutation="retry_model_errors=2", retry_model_errors=2
    )
    calls = ToolCall(id="s1", name="submit", arguments_raw="{}", arguments={"summary": "done"})
    client = _ScriptedClient([_reply("thinking", [_bash_call()]), LLMError("503"), _reply("", [calls])])
    loop = AgentLoop(client, deadline_s=60.0)
    episode = loop.run(_task(tmp_path), _StubSandbox(), genome)
    assert episode.exit_reason == "submitted"
    assert episode.model_retries == 1
    # the retry re-sent the identical history: nothing was appended in between
    assert len(client.calls[2]) == len(client.calls[1])


def test_episode_still_fails_when_the_error_persists(tmp_path: Path):
    genome = default_genome("retry-on").derive(
        "retry-on", mutation="retry_model_errors=1", retry_model_errors=1
    )
    client = _ScriptedClient([LLMError("boom"), LLMError("boom")])
    loop = AgentLoop(client, deadline_s=60.0)
    episode = loop.run(_task(tmp_path), _StubSandbox(), genome)
    assert episode.exit_reason == "model_error"
    assert episode.model_retries == 1


def test_a_truncated_turn_is_recovered_not_treated_as_silence(tmp_path: Path):
    """The gen5 failure mode: an output cap stops the model mid-thought."""
    genome = default_genome("cap").derive(
        "cap", mutation="truncation_recovery=True", truncation_recovery=True, max_output_tokens=2048
    )
    submit = ToolCall(id="s1", name="submit", arguments_raw="{}", arguments={"summary": "ok"})
    client = _ScriptedClient([
        _reply("I was in the middle of", finish="length"),  # no tool call, cut off
        _reply("", [_bash_call()]),
        _reply("", [submit]),
    ])
    loop = AgentLoop(client, deadline_s=60.0)
    episode = loop.run(_task(tmp_path), _StubSandbox(), genome)
    assert episode.truncation_recoveries == 1
    assert episode.exit_reason == "submitted"
    assert TRUNCATION_TEXT in client.calls[1][-1]["content"]


def test_prose_without_truncation_still_uses_the_plain_nudge(tmp_path: Path):
    genome = default_genome("cap").derive(
        "cap", mutation="truncation_recovery=True", truncation_recovery=True
    )
    submit = ToolCall(id="s1", name="submit", arguments_raw="{}", arguments={"summary": "ok"})
    client = _ScriptedClient([_reply("here is my plan"), _reply("", [submit])])
    loop = AgentLoop(client, deadline_s=60.0)
    episode = loop.run(_task(tmp_path), _StubSandbox(), genome)
    assert episode.truncation_recoveries == 0
    assert episode.nudge_count == 1


def test_artifact_gate_warns_while_the_product_is_untouched(tmp_path: Path):
    genome = default_genome("gate").derive(
        "gate", mutation="artifact_gate=True", artifact_gate=True, max_steps=10
    )
    submit = ToolCall(id="s1", name="submit", arguments_raw="{}", arguments={"summary": "ok"})
    responses = [_reply("", [_bash_call(f"echo {i}", f"c{i}")]) for i in range(4)]
    responses.append(_reply("", [submit]))
    sandbox = _StubSandbox(status_output="?? scratch/t1.ts\n")
    client = _ScriptedClient(responses)
    loop = AgentLoop(client, deadline_s=600.0)
    episode = loop.run(_task(tmp_path), sandbox, genome)
    assert episode.artifact_warnings >= 1
    injected = [
        m for call in client.calls for m in call
        if m.get("role") == "tool" and ARTIFACT_GATE_TEXT in (m.get("content") or "")
    ]
    assert injected, "the gate never reached the model"


def test_artifact_gate_stays_quiet_once_product_source_changes(tmp_path: Path):
    genome = default_genome("gate").derive(
        "gate", mutation="artifact_gate=True", artifact_gate=True, max_steps=10
    )
    submit = ToolCall(id="s1", name="submit", arguments_raw="{}", arguments={"summary": "ok"})
    responses = [_reply("", [_bash_call(f"echo {i}", f"c{i}")]) for i in range(4)]
    responses.append(_reply("", [submit]))
    sandbox = _StubSandbox(status_output=" M fastapi/routing.py\n?? scratch/t1.ts\n")
    client = _ScriptedClient(responses)
    loop = AgentLoop(client, deadline_s=600.0)
    episode = loop.run(_task(tmp_path), sandbox, genome)
    assert episode.artifact_warnings == 0


def test_diff_graded_note_tells_the_agent_the_tests_are_hidden(tmp_path: Path):
    from rsih.agent.loop import _env_note, _is_diff_graded

    task = _task(tmp_path)
    assert _is_diff_graded(task)
    note = _env_note(task, default_genome("g"), 60)
    assert "NOT in this container" in note
    assert "all-or-nothing" in note
    # a task whose artifact is a file tree must not get the repository wording
    from dataclasses import replace

    file_task = replace(task, collect_cmd="cp /app/out.txt /logs/artifacts/out.txt")
    assert not _is_diff_graded(file_task)
    assert "NOT in this container" not in _env_note(file_task, default_genome("g"), 60)


# ---------------------------------------------- judge capability, not only pass counts
#
# On a six-task evolve split the pass-count floor needs five net flips, so a mutation that
# moves every cell from "no patch" to "nearly passing" is invisible to it.  The repository
# suites report how far each patch got, and these tests pin down that the dense gate uses
# that signal without ever accepting a regression.


def _trial(task: str, status: str, f2p: float | None = None, p2p: float | None = None):
    from rsih.bench.runner import TrialResult

    return TrialResult(
        task_id=task,
        genome_id="g",
        genome_fingerprint="f",
        status=status,
        reward=1.0 if status == "success" else 0.0,
        turns=10,
        duration_s=1.0,
        cost_usd=0.01,
        cost_first_cold_usd=0.01,
        usage={},
        exit_reason="submitted",
        extra={"verifier_detail": ({"f2p": f2p, "p2p": p2p} if f2p is not None else {})},
    )


def _cap_outcome(results, run_id: str = "r"):
    from rsih.rsi.evolve import Outcome

    return Outcome(genome=default_genome("g"), run_id=run_id, run_dir=Path("."), results=results)


def test_capability_credit_is_dense_and_never_reaches_a_pass():
    outcome = _cap_outcome([
        _trial("t/pass", "success"),
        _trial("t/nearly", "failure", f2p=0.972, p2p=1.0),
        _trial("t/regressed", "failure", f2p=0.839, p2p=0.983),
        _trial("t/empty", "failure"),
    ])
    scores = outcome.capability()
    assert scores["t/pass"] == 1.0
    assert 0.97 < scores["t/nearly"] < 1.0, "a near miss must stay below a pass"
    # a regression in the existing suite must be penalised, not averaged away
    assert scores["t/regressed"] < 0.839
    assert scores["t/empty"] == 0.0


def test_dense_gate_accepts_progress_the_pass_count_cannot_see():
    """Six tasks, no pass flips, every cell moves from nothing to nearly passing."""
    left = _cap_outcome([_trial(f"t/{i}", "failure") for i in range(6)])
    right = _cap_outcome([_trial(f"t/{i}", "failure", f2p=0.8, p2p=1.0) for i in range(6)])
    binary = paired_decision(left, right)
    # There is no discordance at all: not one cell changed hands, so the pass-count
    # signal is a flat tie and its floor is zero.
    assert binary.diff == 0.0 and binary.floor == 0.0
    assert binary.child_wins == [] and binary.incumbent_wins == []
    # The dense signal is what turns that tie into an adoptable improvement.
    assert binary.accepted and binary.reason == "accepted_capability"
    assert binary.capability_t == float("inf")


def test_dense_gate_refuses_to_trade_a_pass_for_partial_credit():
    left = _cap_outcome([_trial("t/win", "success"), _trial("t/a", "failure"), _trial("t/b", "failure")])
    right = _cap_outcome([
        _trial("t/win", "failure", f2p=0.9, p2p=1.0),  # lost a pass
        _trial("t/a", "failure", f2p=0.9, p2p=1.0),
        _trial("t/b", "failure", f2p=0.9, p2p=1.0),
    ])
    decision = paired_decision(left, right)
    assert not decision.accepted
    assert decision.reason in ("rejected_within_noise", "rejected_worse")


def test_dense_gate_still_rejects_a_regression():
    left = _cap_outcome([_trial(f"t/{i}", "failure", f2p=0.5, p2p=1.0) for i in range(4)])
    right = _cap_outcome([_trial(f"t/{i}", "failure", f2p=0.1, p2p=1.0) for i in range(4)])
    decision = paired_decision(left, right)
    assert not decision.accepted
    assert decision.reason == "rejected_worse"



def test_artifact_gate_stays_quiet_when_the_deliverable_is_not_a_diff(tmp_path: Path):
    """A task whose object is git history must not be told to write source code."""
    from dataclasses import replace

    genome = default_genome("gate").derive(
        "gate", mutation="artifact_gate=True", artifact_gate=True, max_steps=10
    )
    submit = ToolCall(id="s1", name="submit", arguments_raw="{}", arguments={"summary": "ok"})
    responses = [_reply("", [_bash_call(f"echo {i}", f"c{i}")]) for i in range(4)]
    responses.append(_reply("", [submit]))
    # the worktree looks untouched, but this task is graded on container state
    sandbox = _StubSandbox(status_output="")
    client = _ScriptedClient(responses)
    loop = AgentLoop(client, deadline_s=600.0)
    task = replace(_task(tmp_path), collect_cmd=None)
    episode = loop.run(task, sandbox, genome)
    assert episode.artifact_warnings == 0
    assert not [c for c in sandbox.commands if "git status" in c], (
        "the gate should not even query a task that is not graded on a diff"
    )
