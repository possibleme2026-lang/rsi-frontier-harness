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
            "error": self.error,
            "ledger": self.ledger.as_dict() if self.ledger else None,
            "steps": [s.as_dict() for s in self.steps],
        }
        if include_messages:
            data["messages"] = self.messages
        return data


def _env_note(task: Task, genome: Genome, step_cap: int) -> str:
    return (
        "# Environment\n"
        f"A Linux container, running as root. Working directory: {task.workdir}.\n"
        f"The task's time limit is {task.agent_timeout_s:.0f} seconds and you have at most "
        f"{step_cap} tool calls. Only the filesystem of this container counts.\n"
    )


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
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": genome.system_prompt()},
            {"role": "user", "content": f"# Task\n{task.instruction.strip()}\n\n{_env_note(task, genome, step_cap)}"},
        ]
        episode.messages = messages
        schemas = tool_lib.schemas(genome.tools)
        nudges_left = genome.nudge_text_only
        submit_rejected = False
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
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": record["observation"]}
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
