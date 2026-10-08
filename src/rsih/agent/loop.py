"""The agent loop.

Three properties are non-negotiable here, because the RSI loop depends on them:

* the message log is **append-only** unless compaction fires, so the provider's
  prefix cache can hit on every turn — cache reads are ~10x cheaper than fresh
  input, and on this benchmark they are the single largest cost lever;
* a model call that fails is recorded as a failure, never replaced by a retry
  that produced different text;
* every step records its own measured usage, so a cost number can be traced back
  to the calls that produced it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..bench.sandbox import DockerSandbox
from ..bench.tasks import Task
from ..llm.client import LLMClient, LLMError, ToolCall
from ..llm.pricing import CostLedger, Usage
from . import tools as tool_lib
from .genome import Genome

NUDGE_TEXT = (
    "You replied with prose but did not act. Nothing you write is executed. "
    "Use a tool now, or call submit if the task is genuinely finished."
)
SUBMIT_GUARD_TEXT = (
    "Submit rejected once: before finishing you must run the check the task implies "
    "and read its actual output. Do that now, then call submit again."
)
#: Shown when the agent tries to finish a diff-graded task without having changed a single
#: product file. The grader scores the diff, so this submit is a guaranteed zero: there is
#: nothing to lose by refusing it and one turn to gain. Measured, not assumed -- three of
#: seven repository failures submitted an empty diff and two more submitted only their own
#: scratch files, and both `meriyah` and `katex` read the softer artifact-gate notice four
#: times and submitted nothing anyway.
EMPTY_ARTIFACT_TEXT = (
    "Submit rejected: the graded artifact is a diff of this repository and yours is empty "
    "of any product file. Scratch files, notes and probe scripts are not graded. You will "
    "score zero for this submission. Write the change you believe is most likely correct "
    "into the product source now -- a partial implementation that compiles is worth more "
    "than a perfect plan -- then submit."
)
#: How many times an empty submit may be refused before it is accepted anyway. One refusal
#: recovers an agent that had not realised the diff was the deliverable; several would trap
#: an agent that genuinely cannot do the task into burning its remaining steps.
EMPTY_ARTIFACT_REJECTION_LIMIT = 2
#: Appended when the provider stopped the response because it hit the output limit. A
#: reasoning model that is cut off mid-thought can spend a whole turn producing neither
#: prose nor a tool call, which without this message is indistinguishable from the model
#: simply going quiet -- and ends the episode. The wording is the one mini-SWE-agent uses
#: for the same condition: name the cause, demand exactly one action.
TRUNCATION_TEXT = (
    "Your previous response reached the output token limit before you produced a tool "
    "call, so it was cut off. Work in smaller pieces and finish with exactly one tool "
    "call. Do not restate the plan; issue the next action."
)
#: Shown once the agent is into the last fifth of its step budget.
ENDGAME_TEXT = (
    "Budget notice: {left} of {cap} tool calls remain. Stop exploring. Make the change "
    "you believe is correct, verify it against the task's own requirement, and submit. "
    "If you already have a working state, do not rewrite it -- an unnecessary edit to "
    "working code is how a solved task becomes an unsolved one."
)
#: Shown when the graded artifact is still untouched.  The repository half of this suite
#: grades the diff, so an episode that has not written a product file cannot score no
#: matter how much it has learned; measured episodes ended exactly that way.
ARTIFACT_GATE_TEXT = (
    "Artifact check: you have not modified any project source file yet. Only the "
    "repository diff is graded, so everything you have run so far earns nothing on its "
    "own. Stop reading and stop probing error messages: write the first real "
    "implementation edit now, then iterate against it. If the repository generates a "
    "file from a grammar or schema source, edit the source and regenerate it."
)


@dataclass
class Step:
    index: int
    content: str
    reasoning_chars: int
    tool_calls: list[dict[str, Any]]
    usage: Usage
    latency_s: float
    prompt_tokens: int | None
    compacted: bool = False

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "content": self.content,
            "reasoning_chars": self.reasoning_chars,
            "tool_calls": self.tool_calls,
            "usage": self.usage.as_dict(),
            "latency_s": round(self.latency_s, 3),
            "compacted_before": self.compacted,
        }


@dataclass
class Episode:
    task_id: str
    genome_id: str
    genome_fingerprint: str
    steps: list[Step] = field(default_factory=list)
    submitted: bool = False
    exit_reason: str = "unfinished"
    started_at: float = 0.0
    finished_at: float = 0.0
    ledger: CostLedger | None = None
    compactions: int = 0
    nudge_count: int = 0
    submit_rejections: int = 0
    model_retries: int = 0
    truncation_recoveries: int = 0
    artifact_warnings: int = 0
    #: Submits refused because the graded diff contained no product file. Counted apart from
    #: `submit_rejections` so a run can say whether the guard fired on evidence of an empty
    #: artifact rather than as an unconditional first-submit penalty.
    empty_artifact_rejections: int = 0
    error: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return max(0.0, self.finished_at - self.started_at)

    @property
    def turns(self) -> int:
        return len(self.steps)

    def as_dict(self, include_messages: bool = False) -> dict:
        data = {
            "task_id": self.task_id,
            "genome_id": self.genome_id,
            "genome_fingerprint": self.genome_fingerprint,
            "submitted": self.submitted,
            "exit_reason": self.exit_reason,
            "turns": self.turns,
            "duration_s": round(self.duration_s, 3),
            "compactions": self.compactions,
            "nudges": self.nudge_count,
            "submit_rejections": self.submit_rejections,
            "model_retries": self.model_retries,
            "truncation_recoveries": self.truncation_recoveries,
            "artifact_warnings": self.artifact_warnings,
            "empty_artifact_rejections": self.empty_artifact_rejections,
            "error": self.error,
            "ledger": self.ledger.as_dict() if self.ledger else None,
            "steps": [s.as_dict() for s in self.steps],
        }
        if include_messages:
            data["messages"] = self.messages
        return data


def _retry_schedule(attempts: int) -> list[float]:
    """Backoff before each extra attempt at an identical call.

    Deliberately longer than the client's own in-call backoff: by the time an LLMError
    reaches the loop the client has already tried short waits, so what is left is the
    quota-style outage that needs tens of seconds.  Returns [] when retries are off,
    which keeps the previous behaviour exactly.
    """
    if attempts <= 0:
        return []
    return [min(90.0, 15.0 * (1.8 ** i)) for i in range(attempts)]


def _gate_due(step_index: int, step_cap: int) -> bool:
    """Check the artifact every fifth of the budget, not every step.

    The check costs a container round trip, and a fifth is frequent enough to catch an
    episode that is spending its whole budget exploring while staying cheap.
    """
    interval = max(3, step_cap // 5)
    return (step_index + 1) % interval == 0


def _product_touched(sandbox: DockerSandbox, task: Task, genome: Genome) -> bool:
    """True when the repository diff contains at least one non-scratch, non-test file.

    Only meaningful for tasks whose deliverable is a diff, which is why the caller checks
    `_is_diff_graded` first: a task whose object *is* git history (rewriting it, pruning
    it) would be told to write source code it was never asked for.  Returns True on any
    doubt (no git, unreadable status), because the gate exists to add a message, and a
    false alarm would push an agent that is already editing to edit more.
    """
    changed = tool_lib.product_changes(sandbox, task.workdir)
    if changed is None:
        return True
    return any(tool_lib._is_product_path(path) for path in changed)


def _env_note(task: Task, genome: Genome, step_cap: int) -> str:
    note = (
        "# Environment\n"
        f"A Linux container, running as root. Working directory: {task.workdir}.\n"
        f"The task's time limit is {task.agent_timeout_s:.0f} seconds and you have at most "
        f"{step_cap} tool calls. Only the filesystem of this container counts.\n"
    )
    if _is_diff_graded(task):
        # Not a hint about the answer: a statement about the measurement, identical for
        # every task in the class.  Without it the agent has no way to know that the
        # repository's own tests are not the graded ones, and measured episodes were
        # spent looking for tests that were never in the container.
        note += (
            "How this task is scored: hidden behavioural tests, which are NOT in this "
            "container, are run elsewhere against the diff of this repository. The score "
            "is all-or-nothing -- every hidden test for the new behaviour must pass and "
            "the project's existing test suite must stay green. The task statement above "
            "is therefore the whole specification.\n"
        )
    return note


def _is_diff_graded(task: Task) -> bool:
    """True when the task's artifact is a repository diff rather than a file tree.

    Read off the task's own collect command instead of a task-id list, so a new task in
    the same family is classified correctly without anyone remembering to update a table.
    """
    collect = getattr(task, "collect_cmd", None) or ""
    return "git diff" in collect or "git -C" in collect


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        total += len(json.dumps(message, ensure_ascii=False))
    return total // 4


class AgentLoop:
    def __init__(
        self,
        client: LLMClient,
        *,
        log_path: Path | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        deadline_s: float | None = None,
    ):
        self.client = client
        self.log_path = log_path
        self.on_event = on_event
        self.deadline_s = deadline_s

    # ------------------------------------------------------------------ events
    def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event:
            self.on_event(event)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    # -------------------------------------------------------------- compaction
    def _compact(self, episode: Episode, genome: Genome, ledger: CostLedger) -> list[dict[str, Any]]:
        messages = episode.messages
        keep = max(2, genome.keep_recent_tool_results)
        # Walk backwards to a turn boundary, keeping the most recent tool results.
        tool_seen = 0
        boundary = len(messages)
        for index in range(len(messages) - 1, 1, -1):
            if messages[index].get("role") == "tool":
                tool_seen += 1
            if tool_seen >= keep and messages[index].get("role") == "assistant":
                boundary = index
                break
        if boundary <= 2:
            return messages

        dropped = messages[2:boundary]
        if genome.compaction == "summarize":
            note = self._summarize(dropped, ledger)
        else:
            names: list[str] = []
            for message in dropped:
                for call in message.get("tool_calls") or []:
                    names.append((call.get("function") or {}).get("name", "?"))
            counts = {name: names.count(name) for name in dict.fromkeys(names)}
            summary = ", ".join(f"{name}x{count}" for name, count in counts.items()) or "no tool calls"
            note = (
                f"[{len(dropped)} earlier messages omitted to stay inside the context budget. "
                f"Tools already used: {summary}. The working directory and any files you wrote "
                "persist; re-read anything you still need.]"
            )
        episode.compactions += 1
        self._emit({"event": "compaction", "dropped": len(dropped), "mode": genome.compaction})
        return messages[:2] + [{"role": "user", "content": note}] + messages[boundary:]

    def _summarize(self, dropped: list[dict[str, Any]], ledger: CostLedger) -> str:
        rendered = []
        for message in dropped[-40:]:
            role = message.get("role")
            if role == "assistant":
                for call in message.get("tool_calls") or []:
                    function = call.get("function") or {}
                    rendered.append(f"COMMAND: {function.get('arguments', '')[:400]}")
                if message.get("content"):
                    rendered.append(f"SAID: {message['content'][:300]}")
            elif role == "tool":
                rendered.append(f"OUTPUT: {str(message.get('content', ''))[:400]}")
        prompt = (
            "Summarise this agent transcript for the agent itself. Preserve: the goal, "
            "what has already been tried, exact paths and values that mattered, and what "
            "is still unknown. Be terse; no advice.\n\n" + "\n".join(rendered)
        )
        try:
            response = self.client.complete(
                [{"role": "user", "content": prompt}],
                max_tokens=700,
                label="compaction",
            )
            ledger.record(response.usage, label="compaction")
            summary = response.content.strip() or "(summary unavailable)"
        except LLMError as exc:
            summary = f"(summarise failed: {exc})"
        return f"[earlier work, summarised]\n{summary}"

    # -------------------------------------------------------------------- main
    def run(self, task: Task, sandbox: DockerSandbox, genome: Genome) -> Episode:
        ledger = CostLedger(card=self.client_card())
        episode = Episode(
            task_id=task.id,
            genome_id=genome.id,
            genome_fingerprint=genome.fingerprint(),
            started_at=time.time(),
            ledger=ledger,
        )
        step_cap = genome.effective_max_steps(task.agent_timeout_declared_s)
        diff_graded = _is_diff_graded(task)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": genome.system_prompt()},
            {"role": "user", "content": f"# Task\n{task.instruction.strip()}\n\n{_env_note(task, genome, step_cap)}"},
        ]
        episode.messages = messages
        schemas = tool_lib.schemas(genome.tools)
        nudges_left = genome.nudge_text_only
        submit_rejected = False
        empty_artifact_rejections = 0
        loop_started = time.time()

        for step_index in range(step_cap):
            if self.deadline_s and (time.time() - loop_started) > self.deadline_s:
                episode.exit_reason = "wall_clock_budget"
                break
            prompt_tokens = steps_last_prompt(episode)
            if prompt_tokens and prompt_tokens > genome.context_budget_tokens * 0.8:
                messages = self._compact(episode, genome, ledger)
                episode.messages = messages
                compacted = True
            else:
                compacted = False

            try:
                response = self.client.complete(
                    messages,
                    tools=schemas,
                    temperature=genome.temperature,
                    max_tokens=genome.max_output_tokens or None,
                    label=f"step{step_index}",
                )
            except LLMError as exc:
                # The client has already exhausted its own retries.  A gateway hiccup
                # here would discard every step taken so far, so re-issue the identical
                # call: nothing is appended between attempts, which keeps the prefix
                # cache hot and guarantees the agent cannot see a different history.
                response = None
                for wait_s in _retry_schedule(genome.retry_model_errors):
                    episode.model_retries += 1
                    self._emit(
                        {
                            "event": "model_retry",
                            "task": task.id,
                            "genome": genome.id,
                            "index": step_index,
                            "error": str(exc)[:200],
                            "sleep_s": wait_s,
                        }
                    )
                    time.sleep(wait_s)
                    if self.deadline_s and (time.time() - loop_started) > self.deadline_s:
                        break
                    try:
                        response = self.client.complete(
                            messages,
                            tools=schemas,
                            temperature=genome.temperature,
                            max_tokens=genome.max_output_tokens or None,
                            label=f"step{step_index}-retry",
                        )
                        break
                    except LLMError as retry_exc:
                        exc = retry_exc
                if response is None:
                    episode.error = str(exc)
                    episode.exit_reason = "model_error"
                    break
            ledger.record(response.usage, label=f"step{step_index}")

            call_records: list[dict[str, Any]] = []
            assistant_message: dict[str, Any] = {"role": "assistant", "content": response.content or ""}
            if response.tool_calls:
                assistant_message["tool_calls"] = [c.as_message_part() for c in response.tool_calls]
            messages.append(assistant_message)

            step = Step(
                index=step_index,
                content=response.content,
                reasoning_chars=len(response.reasoning),
                tool_calls=call_records,
                usage=response.usage,
                latency_s=response.latency_s,
                prompt_tokens=response.usage.prompt_tokens,
                compacted=compacted,
            )
            episode.steps.append(step)
            self._emit(
                {
                    "event": "step",
                    "task": task.id,
                    "genome": genome.id,
                    "index": step_index,
                    "content_chars": len(response.content),
                    "tools": [c.name for c in response.tool_calls],
                    "prompt_tokens": response.usage.prompt_tokens,
                    "cached_tokens": response.usage.cached_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                }
            )

            if not response.tool_calls:
                # A reasoning model stopped by the output limit is a different failure
                # from one that chose to answer in prose: the first was interrupted, the
                # second decided.  Telling them apart is what makes an output cap safe.
                if genome.truncation_recovery and response.finish_reason == "length":
                    episode.truncation_recoveries += 1
                    self._emit(
                        {
                            "event": "truncation_recovery",
                            "task": task.id,
                            "genome": genome.id,
                            "index": step_index,
                            "completion_tokens": response.usage.completion_tokens,
                        }
                    )
                    messages.append({"role": "user", "content": TRUNCATION_TEXT})
                    continue
                if nudges_left > 0:
                    nudges_left -= 1
                    episode.nudge_count += 1
                    messages.append({"role": "user", "content": NUDGE_TEXT})
                    continue
                episode.exit_reason = "text_only"
                break

            submitted_now = False
            for call in response.tool_calls:
                record = self._execute_call(call, sandbox, genome, task)
                call_records.append(record)
                if call.name == "submit" and genome.submit_guard == "one_shot_reject" and not submit_rejected:
                    submit_rejected = True
                    episode.submit_rejections += 1
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": SUBMIT_GUARD_TEXT}
                    )
                    continue
                if (
                    call.name == "submit"
                    and genome.submit_guard == "artifact_required"
                    and diff_graded
                    and empty_artifact_rejections < EMPTY_ARTIFACT_REJECTION_LIMIT
                    and step_cap - step_index - 1 > 0
                    and not _product_touched(sandbox, task, genome)
                ):
                    # A refusal here is free: the grader scores the diff, an empty diff is a
                    # certain zero, and the agent still has steps left to spend. Bounded so
                    # that an agent which genuinely cannot do the task is not trapped in a
                    # loop it cannot exit -- after the limit the submit is accepted and the
                    # episode ends with whatever it has.
                    empty_artifact_rejections += 1
                    episode.submit_rejections += 1
                    episode.empty_artifact_rejections += 1
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": EMPTY_ARTIFACT_TEXT}
                    )
                    continue
                if call.name == "submit":
                    submitted_now = True
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": "episode closed",
                        }
                    )
                    continue
                observation = record["observation"]
                gate_left = step_cap - step_index - 1
                if (
                    genome.artifact_gate
                    and diff_graded
                    and gate_left > 0
                    and _gate_due(step_index, step_cap)
                ):
                    if not _product_touched(sandbox, task, genome):
                        episode.artifact_warnings += 1
                        observation = f"{observation}\n\n{ARTIFACT_GATE_TEXT}"
                if genome.step_countdown:
                    left = gate_left
                    if left <= max(1, step_cap // 5):
                        observation = f"{observation}\n\n{ENDGAME_TEXT.format(left=left, cap=step_cap)}"
                    elif left > 0:
                        observation = f"{observation}\n\n[step {step_index + 1}/{step_cap}, {left} left]"
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": observation}
                )

            if submitted_now:
                episode.submitted = True
                episode.exit_reason = "submitted"
                break
        else:
            episode.exit_reason = "step_limit"

        episode.finished_at = time.time()
        episode.messages = messages
        return episode

    def _execute_call(
        self, call: ToolCall, sandbox: DockerSandbox, genome: Genome, task: Task
    ) -> dict[str, Any]:
        if call.parse_error:
            observation = f"ERROR: could not parse tool arguments: {call.parse_error}"
            execution = tool_lib.ToolExecution(call.name, {}, observation, None, 0.0, False)
        elif call.name == "submit":
            execution = tool_lib.ToolExecution(
                "submit", call.arguments, call.arguments.get("summary", ""), 0, 0.0, True
            )
        else:
            execution = tool_lib.execute(call.name, call.arguments, sandbox, genome)
        observation = tool_lib.format_observation(execution, genome)
        return {
            "name": call.name,
            "arguments": call.arguments,
            "observation": observation,
            "observation_chars": len(observation),
            "exit_code": execution.exit_code,
            "duration_s": round(execution.duration_s, 3),
        }

    def client_card(self):
        from ..llm.pricing import rate_card

        return rate_card(self.client.settings.model)


def steps_last_prompt(episode: Episode) -> int | None:
    for step in reversed(episode.steps):
        if step.prompt_tokens:
            return step.prompt_tokens
    return None


def run_episode(
    task: Task,
    sandbox: DockerSandbox,
    genome: Genome,
    client: LLMClient,
    *,
    log_path: Path | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    deadline_s: float | None = None,
) -> Episode:
    return AgentLoop(client, log_path=log_path, on_event=on_event, deadline_s=deadline_s).run(
        task, sandbox, genome
    )
