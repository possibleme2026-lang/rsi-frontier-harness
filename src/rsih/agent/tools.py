"""Tool surface.

The tool set is deliberately tiny.  On this benchmark the cost of a turn is
dominated by the transcript that precedes it, and a large tool schema is paid for
on *every* turn of *every* task, so a tool has to earn its place by removing more
transcript than it adds.  ``bash`` is the only general actuator; ``read_file`` and
``write_file`` exist because their shell equivalents (heredocs, ``cat`` with
escapes) are the two places where models lose tokens to quoting accidents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..bench.sandbox import DockerSandbox
from .genome import Genome


@dataclass
class ToolExecution:
    name: str
    arguments: dict[str, Any]
    observation: str
    exit_code: int | None = None
    duration_s: float = 0.0
    ok: bool = True


SCHEMAS: dict[str, dict] = {
    "bash": {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Run a bash command in the container. `cd` persists across calls; "
                "exported variables and background jobs do not. Returns the exit code "
                "and the combined stdout/stderr."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to run."}
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
    "read_file": {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a file with line numbers. Use start_line/end_line for large files. "
                "Cheaper and safer than reading through bash."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    "write_file": {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write exact text to a file, creating parent directories. Replaces the "
                "whole file. The content is transferred verbatim: no shell escaping."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    "submit": {
        "type": "function",
        "function": {
            "name": "submit",
            "description": "Declare the task complete and end the episode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "One sentence: what was changed and how it was checked.",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
}


def schemas(enabled: tuple[str, ...] | list[str]) -> list[dict]:
    return [SCHEMAS[name] for name in enabled if name in SCHEMAS]


def truncate(text: str, head: int, tail: int) -> tuple[str, bool]:
    """Keep the head and the tail; the middle of a long log is rarely the signal."""
    if head + tail <= 0 or len(text) <= head + tail + 200:
        return text, False
    omitted = len(text) - head - tail
    marker = f"\n... [{omitted} characters omitted] ...\n"
    return text[:head] + marker + text[-tail:], True


def format_observation(result: ToolExecution, genome: Genome) -> str:
    body, truncated = truncate(result.observation, genome.obs_head_chars, genome.obs_tail_chars)
    header = f"exit_code={result.exit_code}" if result.exit_code is not None else "exit_code=unknown"
    if result.duration_s >= 20:
        header += f" duration_s={result.duration_s:.0f}"
    if truncated:
        header += " output_truncated=true"
    return f"{header}\n{body}" if body else header


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def execute(
    name: str,
    arguments: dict[str, Any],
    sandbox: DockerSandbox,
    genome: Genome,
) -> ToolExecution:
    if name == "bash":
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            return ToolExecution(name, arguments, "ERROR: `command` must be a non-empty string", None, 0.0, False)
        result = sandbox.exec_script(command, timeout_s=genome.bash_timeout_s)
        note = " (command timed out in-container)" if result.timed_out else ""
        return ToolExecution(
            name,
            arguments,
            (result.output or "") + (f"\n[timeout after {genome.bash_timeout_s:.0f}s]" if result.timed_out else ""),
            result.exit_code,
            result.duration_s,
            result.exit_code == 0 and not result.timed_out,
        )

    if name == "read_file":
        path = arguments.get("path")
        if not isinstance(path, str) or not path:
            return ToolExecution(name, arguments, "ERROR: `path` is required", None, 0.0, False)
        start = arguments.get("start_line")
        end = arguments.get("end_line")
        span = ""
        if isinstance(start, int) or isinstance(end, int):
            low = start if isinstance(start, int) and start > 0 else 1
            high = end if isinstance(end, int) and end >= low else low + 400
            span = f"{low},{high}p"
        if span:
            script = f"if [ -f {_sh_quote(path)} ]; then sed -n {_sh_quote(span)} {_sh_quote(path)}; else echo 'ERROR: no such file'; exit 2; fi"
        else:
            script = f"if [ -f {_sh_quote(path)} ]; then cat -n {_sh_quote(path)}; else echo 'ERROR: no such file'; exit 2; fi"
        result = sandbox.exec_script(script, timeout_s=120)
        return ToolExecution(name, arguments, result.output or "", result.exit_code, result.duration_s, result.exit_code == 0)

    if name == "write_file":
        path = arguments.get("path")
        content = arguments.get("content")
        if not isinstance(path, str) or not path or not isinstance(content, str):
            return ToolExecution(name, arguments, "ERROR: `path` and `content` are required", None, 0.0, False)
        try:
            sandbox.write_text(path, content)
        except Exception as exc:  # noqa: BLE001
            return ToolExecution(name, arguments, f"ERROR: {exc}", None, 0.0, False)
        return ToolExecution(name, arguments, f"wrote {len(content)} bytes to {path}", 0, 0.0, True)

    return ToolExecution(name, arguments, f"ERROR: unknown tool {name!r}", None, 0.0, False)
