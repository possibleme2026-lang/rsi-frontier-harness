"""Tool surface.

The tool set is deliberately tiny.  On this benchmark the cost of a turn is
dominated by the transcript that precedes it, and a large tool schema is paid for
on *every* turn of *every* task, so a tool has to earn its place by removing more
transcript than it adds.  ``bash`` is the only general actuator; ``read_file`` and
``write_file`` exist because their shell equivalents (heredocs, ``cat`` with
escapes) are the two places where models lose tokens to quoting accidents.
"""

from __future__ import annotations

import re
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


def product_changes(sandbox: DockerSandbox, workdir: str = "/app") -> list[str] | None:
    """Files changed in the repository, or None when this is not a git worktree.

    The graded artifact on the repository suites is the git diff itself, and several
    measured episodes spent their entire budget probing while the diff stayed empty --
    one of them ending with a patch that contained nothing but its own scratch files.
    Knowing *whether* the product has been touched is therefore worth a cheap check.

    A file is treated as non-product when its path looks like scratch or test material:
    those are the paths an agent writes while exploring, and they do not earn reward.
    """
    result = sandbox.exec_script(
        f"cd {_sh_quote(workdir)} 2>/dev/null && "
        "git status --porcelain --untracked-files=all 2>/dev/null",
        timeout_s=30.0,
    )
    if result.exit_code != 0:
        return None
    changed: list[str] = []
    for line in (result.output or "").splitlines():
        path = line[3:].strip() if len(line) > 3 else ""
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path.strip('"'):
            changed.append(path.strip('"'))
    return changed


def _is_product_path(path: str) -> bool:
    lowered = path.lower()
    parts = lowered.split("/")
    name = parts[-1]
    if any(part in _SCRATCH_DIRS for part in parts[:-1]):
        return False
    if name.startswith("scratch") or name.endswith("_test.go"):
        return False
    if lowered.startswith("tests/") or "/tests/" in lowered or "/test/" in lowered:
        return False
    if name.startswith("test_") or ".test." in name or ".spec." in name:
        return False
    return True


_SCRATCH_DIRS = frozenset({"scratch", "scratchpad", "tmp", "temp", "__pycache__", ".git"})



#: Tokens we may safely interpolate into the probe shell command.
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.+-]+$")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_.+-]+")
_SHELL_BUILTINS = frozenset(
    {
        "cd", "echo", "export", "if", "then", "else", "fi", "for", "do", "done", "while",
        "case", "esac", "set", "unset", "source", "true", "false", "test", "return",
        "function", "local", "read", "exit", "shift", "trap", "sudo", "env", "time",
        "and", "or", "not", "null", "while", "until", "in", "the", "a", "an",
    }
)
_MISSING_COMMAND_RE = re.compile(
    r"command not found|not found:|No such file or directory|"
    r"executable file not found|is not recognized as",
    re.IGNORECASE,
)


def _looks_like_missing_command(output: str, exit_code: int | None) -> bool:
    """Only enrich when the shell says a *binary* is missing, not a normal file error.

    `No such file or directory` is how a missing data file reads too, so the exit code
    has to agree: 126/127 are the shell's own "cannot execute" codes.
    """
    if exit_code not in (126, 127, None):
        return False
    if "command not found" in output.lower():
        return True
    return exit_code == 127 and bool(_MISSING_COMMAND_RE.search(output))


def command_not_found_hint(sandbox: DockerSandbox, command: str) -> str | None:
    """If the shell could not find a binary, say what it is actually called.

    A missing or not-in-PATH executable is the largest single measured command-failure
    category on this benchmark, and the answer is already inside the container: the
    spelling the OS would have accepted.  This runs one cheap `compgen` for the tokens of
    the failed command and returns the near matches, so the model corrects the name
    instead of concluding the tool is absent and inventing around it.
    """
    tokens = [
        token
        for token in _TOKEN_RE.findall(command)
        if token not in _SHELL_BUILTINS and not token.startswith("-")
    ]
    if not tokens:
        return None
    probe = " ; ".join(
        f"echo '-- {token}:'; compgen -c | grep -ix '{token}' | head -3 ; "
        f"compgen -c | grep -i '^{token}' | sort -u | head -8"
        for token in tokens[:3]
        if _SAFE_TOKEN.match(token)
    )
    if not probe:
        return None
    try:
        found = sandbox.exec_script(probe, timeout_s=20.0)
    except Exception:  # noqa: BLE001 - a hint is never worth failing the step over
        return None
    lines = [line.strip() for line in (found.output or "").splitlines() if line.strip()]
    if not lines:
        return None
    body = "\n".join(lines[:24])
    return (
        "A command was not found. Installed commands with a similar name:\n"
        f"{body}\n"
        "Use one of these, or check the tool is installed before relying on it."
    )


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
        observation = result.output or ""
        if result.timed_out:
            observation += f"\n[timeout after {genome.bash_timeout_s:.0f}s]"
        if genome.command_not_found_hint and _looks_like_missing_command(observation, result.exit_code):
            hint = command_not_found_hint(sandbox, command)
            if hint:
                observation += f"\n\n{hint}"
        return ToolExecution(
            name,
            arguments,
            observation,
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
