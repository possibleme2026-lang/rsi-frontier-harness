"""The failure analyst.

This is the part of the loop that reads its own failures.  It is given the failed
trials of the incumbent harness and must return (a) named descriptor edits that
touch existing components and (b) at most two imperative rules for the free-text
slot of the genome.

Two guard rails matter for the result to mean anything:

* the analyst sees the *instruction* and the *transcript*, not the verifier's
  internals, so it cannot reverse-engineer a test rather than a capability;
* the analyst is told that task-specific facts are contamination, and the ledger
  keeps the exact text it produced so an overfitted rule is visible later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..llm.client import LLMClient, LLMError
from .mutators import MUTATIONS

ANALYST_SYSTEM = """You diagnose why a coding agent failed terminal tasks, and you \
propose changes to the agent's own instructions.

You will receive, for each failed task: the task statement, the verifier outcome, and a \
transcript of the agent's tool calls and their observations.

Return JSON only, with this shape:
{
  "pattern": "one sentence naming the shared mechanism of failure",
  "rules": ["at most 2 imperative rules, each under 200 characters"],
  "mutations": ["up to 2 names from the allowed list"]
}

Rules must be general engineering discipline that would help on an unseen task. Facts \
tied to one task (file names, values, dataset names, magic constants) are contamination \
and must not appear. If the failures have no shared mechanism, return "rules": [].

Allowed mutation names:
"""


@dataclass
class Analysis:
    pattern: str = ""
    rules: list[str] = field(default_factory=list)
    mutations: list[str] = field(default_factory=list)
    raw: str = ""
    error: str | None = None

    @property
    def patch(self) -> str:
        return "\n".join(f"- {rule}" for rule in self.rules if rule.strip())


def _render_transcript(trial_dir: Path, max_steps: int = 8, obs_chars: int = 700) -> str:
    episode = trial_dir / "episode.json"
    if not episode.is_file():
        return "(no transcript recorded)"
    data = json.loads(episode.read_text(encoding="utf-8"))
    lines: list[str] = []
    for step in data.get("steps", [])[-max_steps:]:
        content = (step.get("content") or "").strip()
        if content:
            lines.append(f"AGENT SAID: {content[:300]}")
        for call in step.get("tool_calls", []):
            arguments = json.dumps(call.get("arguments", {}), ensure_ascii=False)
            lines.append(f"CALL {call.get('name')}: {arguments[:400]}")
            observation = str(call.get("observation", ""))
            lines.append(f"RESULT: {observation[:obs_chars]}")
    return "\n".join(lines) or "(empty transcript)"


def analyse(
    failures: list[dict],
    client: LLMClient,
    *,
    tasks_by_id: dict,
    runs_dir: Path,
    max_tasks: int = 5,
) -> Analysis:
    if not failures:
        return Analysis(pattern="no failures to analyse")

    sections = []
    for trial in failures[:max_tasks]:
        task = tasks_by_id.get(trial["id"])
        instruction = (task.instruction[:1200] if task else "(instruction unavailable)")
        trial_dir = runs_dir / "trials" / trial["id"].split("/")[-1]
        sections.append(
            f"### TASK {trial['id']} (status={trial['status']}, turns={trial.get('turns')})\n"
            f"{instruction}\n\nTRANSCRIPT:\n{_render_transcript(trial_dir)}"
        )

    user = (
        "Failed trials of the current harness:\n\n"
        + "\n\n".join(sections)
        + "\n\nDiagnose and return the JSON object."
    )
    try:
        response = client.complete(
            [
                {"role": "system", "content": ANALYST_SYSTEM + "\n".join(sorted(MUTATIONS))},
                {"role": "user", "content": user},
            ],
            max_tokens=1500,
            label="analyst",
        )
    except LLMError as exc:
        return Analysis(error=str(exc))

    text = response.content.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return Analysis(raw=text, error="analyst did not return JSON")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        return Analysis(raw=text, error=f"invalid JSON from analyst: {exc}")

    rules = [str(r).strip() for r in payload.get("rules", []) if str(r).strip()][:2]
    mutations = [m for m in payload.get("mutations", []) if m in MUTATIONS][:2]
    return Analysis(
        pattern=str(payload.get("pattern", "")),
        rules=rules,
        mutations=mutations,
        raw=text,
    )
