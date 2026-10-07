"""Descriptor mutations: each one is a named hypothesis, not a random tweak.

The mutation set is closed and inspectable, because a search whose moves cannot be
described cannot be audited.  Two families exist:

* **structural edits** - add/remove a named prompt block, change the tool set,
  change a loop parameter.  Cheap, safe, and each has a stated hypothesis.
* **free text** - ``extra_prompt``, written by the failure analyst
  (``analyst.py``) from the incumbent's own failed trajectories.  The text is
  stored verbatim in the ledger beside the measurement it produced, so an
  open-ended edit is still evidence.

Every mutation returns a *new* genome with a fresh id and a lineage entry.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Callable

from ..agent.genome import ALL_TOOLS, Genome
from ..agent import prompts


@dataclass(frozen=True)
class Mutation:
    label: str
    component: str
    hypothesis: str
    apply: Callable[[Genome, str], Genome | None]


def _with_block(genome: Genome, new_id: str, block: str, position: str = "before_submit") -> Genome | None:
    if block in genome.blocks:
        return None
    blocks = list(genome.blocks)
    if position == "before_submit":
        index = blocks.index("submit.contract") if "submit.contract" in blocks else len(blocks)
        blocks.insert(index, block)
    elif position == "after_role":
        index = 1 if blocks else 0
        blocks.insert(index, block)
    else:
        blocks.append(block)
    return genome.derive(new_id, mutation=f"+{block}", blocks=tuple(blocks))


def _drop_block(genome: Genome, new_id: str, block: str) -> Genome | None:
    if block not in genome.blocks or block in prompts.REQUIRED_BLOCKS:
        return None
    blocks = tuple(b for b in genome.blocks if b != block)
    return genome.derive(new_id, mutation=f"-{block}", blocks=blocks)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


MUTATIONS: dict[str, Mutation] = {
    # ------------------------------------------------------------ prompt blocks
    "prompt+=verify.self_check": Mutation(
        label="prompt+=verify.self_check",
        component="prompt",
        hypothesis="the agent submits without running the check the task implies",
        apply=lambda g, i: _with_block(g, i, "verify.self_check"),
    ),
    "prompt+=verify.requirements": Mutation(
        label="prompt+=verify.requirements",
        component="prompt",
        hypothesis="requirements are missed rather than mis-executed: exact paths/values/formats",
        apply=lambda g, i: _with_block(g, i, "verify.requirements"),
    ),
    "prompt+=method.plan": Mutation(
        label="prompt+=method.plan",
        component="prompt",
        hypothesis="the agent acts before inspecting the environment and wastes turns",
        apply=lambda g, i: _with_block(g, i, "method.plan", "after_role"),
    ),
    "prompt+=method.smallest_change": Mutation(
        label="prompt+=method.smallest_change",
        component="prompt",
        hypothesis="the agent over-edits and breaks something that already worked",
        apply=lambda g, i: _with_block(g, i, "method.smallest_change"),
    ),
    "prompt+=errors.offline": Mutation(
        label="prompt+=errors.offline",
        component="prompt",
        hypothesis="the agent burns turns fighting a missing package index",
        apply=lambda g, i: _with_block(g, i, "errors.offline"),
    ),
    "prompt+=budget.no_explore": Mutation(
        label="prompt+=budget.no_explore",
        component="prompt",
        hypothesis="exploration outside the working directory costs turns and finds nothing",
        apply=lambda g, i: _with_block(g, i, "budget.no_explore"),
    ),
    "prompt-=budget.brevity": Mutation(
        label="prompt-=budget.brevity",
        component="prompt",
        hypothesis="the brevity rule suppresses reasoning the task actually needs",
        apply=lambda g, i: _drop_block(g, i, "budget.brevity"),
    ),
    # ---------------------------------------------------------------- tool set
    "tools+=files": Mutation(
        label="tools+=files",
        component="tools",
        hypothesis="read_file/write_file remove heredoc and quoting failures",
        apply=lambda g, i: None
        if tuple(g.tools) == ALL_TOOLS
        else g.derive(i, mutation="tools+=files", tools=ALL_TOOLS),
    ),
    "tools-=files": Mutation(
        label="tools-=files",
        component="tools",
        hypothesis="the file tools cost more prefix than they save on this task mix",
        apply=lambda g, i: None
        if tuple(g.tools) == ("bash", "submit")
        else g.derive(i, mutation="tools-=files", tools=("bash", "submit")),
    ),
    # -------------------------------------------------------------- loop policy
    "loop.max_steps+=20": Mutation(
        label="loop.max_steps+=20",
        component="loop",
        hypothesis="hard tasks are being cut off before they finish",
        apply=lambda g, i: g.derive(i, mutation="max_steps+=20", max_steps=_clamp(g.max_steps + 20, 8, 160)),
    ),
    "loop.max_steps-=20": Mutation(
        label="loop.max_steps-=20",
        component="loop",
        hypothesis="the agent is looping instead of thinking; fewer steps forces closure",
        apply=lambda g, i: g.derive(i, mutation="max_steps-=20", max_steps=_clamp(g.max_steps - 20, 8, 160)),
    ),
    "loop.obs_head-=2000": Mutation(
        label="loop.obs_head-=2000",
        component="loop",
        hypothesis="long observations dominate input cost and displace the signal",
        apply=lambda g, i: g.derive(
            i, mutation="obs_head-=2000", obs_head_chars=_clamp(g.obs_head_chars - 2000, 1000, 20000)
        ),
    ),
    "loop.obs_head+=2000": Mutation(
        label="loop.obs_head+=2000",
        component="loop",
        hypothesis="truncated observations hide the error text the agent needs",
        apply=lambda g, i: g.derive(
            i, mutation="obs_head+=2000", obs_head_chars=_clamp(g.obs_head_chars + 2000, 1000, 20000)
        ),
    ),
    "loop.compaction=summarize": Mutation(
        label="loop.compaction=summarize",
        component="loop",
        hypothesis="truncation drops information the agent still needs on long tasks",
        apply=lambda g, i: None
        if g.compaction == "summarize"
        else g.derive(i, mutation="compaction=summarize", compaction="summarize"),
    ),
    "loop.compaction=none": Mutation(
        label="loop.compaction=none",
        component="loop",
        hypothesis="tasks finish before the context budget is reached, so compaction never fires",
        apply=lambda g, i: None
        if g.compaction == "none"
        else g.derive(i, mutation="compaction=none", compaction="none"),
    ),
    "loop.submit_guard=one_shot_reject": Mutation(
        label="loop.submit_guard=one_shot_reject",
        component="loop",
        hypothesis="a rejected first submit forces one verification pass",
        apply=lambda g, i: None
        if g.submit_guard == "one_shot_reject"
        else g.derive(i, mutation="submit_guard=one_shot_reject", submit_guard="one_shot_reject"),
    ),
    "loop.nudge_text_only=0": Mutation(
        label="loop.nudge_text_only=0",
        component="loop",
        hypothesis="nudging prose replies spends a turn on a model that will not recover",
        apply=lambda g, i: None
        if g.nudge_text_only == 0
        else g.derive(i, mutation="nudge_text_only=0", nudge_text_only=0),
    ),
    "loop.temperature=0.2": Mutation(
        label="loop.temperature=0.2",
        component="loop",
        hypothesis="a little sampling diversity escapes a repeated failed action",
        apply=lambda g, i: None
        if abs(g.temperature - 0.2) < 1e-9
        else g.derive(i, mutation="temperature=0.2", temperature=0.2),
    ),
    "loop.keep_recent+=8": Mutation(
        label="loop.keep_recent+=8",
        component="loop",
        hypothesis="compaction drops too much recent context on long tasks",
        apply=lambda g, i: g.derive(
            i,
            mutation="keep_recent+=8",
            keep_recent_tool_results=_clamp(g.keep_recent_tool_results + 8, 4, 64),
        ),
    ),
    "loop.max_output_tokens=4096": Mutation(
        label="loop.max_output_tokens=4096",
        component="loop",
        hypothesis=(
            "most of the spend is deliberation the agent never acts on; a cap of 4096 "
            "output tokens per turn should cut cost without changing the actions taken"
        ),
        apply=lambda g, i: None
        if g.max_output_tokens == 4096
        else g.derive(i, mutation="max_output_tokens=4096", max_output_tokens=4096),
    ),
    "loop.max_output_tokens=2048": Mutation(
        label="loop.max_output_tokens=2048",
        component="loop",
        hypothesis="as above, more aggressively: 2048 output tokens is still far more than an action needs",
        apply=lambda g, i: None
        if g.max_output_tokens == 2048
        else g.derive(i, mutation="max_output_tokens=2048", max_output_tokens=2048),
    ),
    "loop.max_output_tokens=0": Mutation(
        label="loop.max_output_tokens=0",
        component="loop",
        hypothesis="a cap was truncating the reasoning the hard tasks need",
        apply=lambda g, i: None
        if g.max_output_tokens == 0
        else g.derive(i, mutation="max_output_tokens=0", max_output_tokens=0),
    ),
    # ---------------------------------------------------- mechanism, not prose
    # These are switches on the loop itself rather than text in the prompt.  The
    # hypothesis behind each was measured before it was written down: episodes ended on
    # transient gateway errors, an output cap stopped turns mid-thought, missing
    # executables were the largest single command-failure class, and -- on the repository
    # suites -- most failures had not edited a single product file.
    "loop.artifact_gate=true": Mutation(
        label="loop.artifact_gate=true",
        component="loop",
        hypothesis=(
            "the graded artifact is a repository diff; an agent still probing after a "
            "fifth of its budget has produced nothing that can score, so telling it that "
            "in the grader's own terms should convert exploration into an edit"
        ),
        apply=lambda g, i: None
        if g.artifact_gate
        else g.derive(i, mutation="artifact_gate=true", artifact_gate=True),
    ),
    "loop.retry_model_errors=2": Mutation(
        label="loop.retry_model_errors=2",
        component="loop",
        hypothesis=(
            "one gateway hiccup currently discards the whole episode; re-issuing the "
            "identical call costs nothing extra when it succeeds and recovers the cell "
            "when it does not"
        ),
        apply=lambda g, i: None
        if g.retry_model_errors >= 2
        else g.derive(i, mutation="retry_model_errors=2", retry_model_errors=2),
    ),
    "loop.truncation_recovery=true": Mutation(
        label="loop.truncation_recovery=true",
        component="loop",
        hypothesis=(
            "an output cap is only safe with an explicit recovery turn; without it a "
            "model cut off mid-thought is indistinguishable from one that went quiet"
        ),
        apply=lambda g, i: None
        if g.truncation_recovery
        else g.derive(i, mutation="truncation_recovery=true", truncation_recovery=True),
    ),
    "loop.command_not_found_hint=true": Mutation(
        label="loop.command_not_found_hint=true",
        component="loop",
        hypothesis=(
            "missing or not-in-PATH executables are the largest measured command-failure "
            "class, and the correct spelling is already inside the container"
        ),
        apply=lambda g, i: None
        if g.command_not_found_hint
        else g.derive(i, mutation="command_not_found_hint=true", command_not_found_hint=True),
    ),
    "loop.step_countdown=true": Mutation(
        label="loop.step_countdown=true",
        component="loop",
        hypothesis=(
            "the step cap is stated once at the start and then never again; a running "
            "countdown plus an endgame instruction should stop an agent from rewriting "
            "work that was already correct"
        ),
        apply=lambda g, i: None
        if g.step_countdown
        else g.derive(i, mutation="step_countdown=true", step_countdown=True),
    ),
    "prompt+=protocol.spec_checklist": Mutation(
        label="prompt+=protocol.spec_checklist",
        component="prompt",
        hypothesis=(
            "every graded feature test is added by the grader and is absent from the "
            "container, so the statement is the whole specification and should be turned "
            "into an explicit requirement list"
        ),
        apply=lambda g, i: _with_block(g, i, "protocol.spec_checklist"),
    ),
    "prompt+=protocol.conformance": Mutation(
        label="prompt+=protocol.conformance",
        component="prompt",
        hypothesis=(
            "the parsing and wire-format tasks grade exact string or byte equality, and "
            "the near-miss cell failed on one continuation byte -- enumerating the format "
            "variants should close that class"
        ),
        apply=lambda g, i: _with_block(g, i, "protocol.conformance"),
    ),
    "prompt+=protocol.new_surface": Mutation(
        label="prompt+=protocol.new_surface",
        component="prompt",
        hypothesis=(
            "adding a flag without validating it turns a vacuously-passing 'invalid input "
            "is rejected' test into a regression; the p2p half of the grade is binary"
        ),
        apply=lambda g, i: _with_block(g, i, "protocol.new_surface"),
    ),
}


def applicable(genome: Genome, labels: list[str] | None = None) -> list[str]:
    names = labels or list(MUTATIONS)
    out = []
    for name in names:
        mutation = MUTATIONS.get(name)
        if mutation is None:
            raise KeyError(f"unknown mutation {name!r}")
        if mutation.apply(genome, "probe") is not None:
            out.append(name)
    return out


def propose(
    genome: Genome,
    child_id: str,
    label: str,
    *,
    extra_prompt: str | None = None,
) -> Genome | None:
    if label == "llm.prompt_patch":
        if not extra_prompt or extra_prompt.strip() == genome.extra_prompt.strip():
            return None
        return genome.derive(child_id, mutation="llm.prompt_patch", extra_prompt=extra_prompt.strip())
    mutation = MUTATIONS.get(label)
    if mutation is None:
        raise KeyError(f"unknown mutation {label!r}")
    child = mutation.apply(genome, child_id)
    if child is None:
        return None
    # Record the catalogue's label, not the edit's internal shorthand, so a ledger
    # entry always names a mutation a reader can look up.
    return replace(child, lineage=genome.lineage + (f"{genome.id}:{label}",))


def sample_labels(genome: Genome, count: int, rng: random.Random, *, exclude: set[str] | None = None) -> list[str]:
    exclude = exclude or set()
    pool = [name for name in applicable(genome) if name not in exclude]
    rng.shuffle(pool)
    return pool[:count]
