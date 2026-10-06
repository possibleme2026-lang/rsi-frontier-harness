"""Benchmark plumbing: tasks, sandbox, trial runner.

Imports are lazy on purpose: ``rsih.agent`` needs ``rsih.bench.sandbox``, and the
runner needs ``rsih.agent``, so an eager ``__init__`` would close an import cycle
between the two packages.
"""

from __future__ import annotations

from typing import Any

__all__ = ["Task", "load_tasks", "available_tasks", "DockerSandbox", "ExecResult", "TrialRunner", "run_trials"]


def __getattr__(name: str) -> Any:  # pragma: no cover - trivial dispatch
    if name in {"Task", "load_tasks", "available_tasks"}:
        from . import tasks

        return getattr(tasks, name)
    if name in {"DockerSandbox", "ExecResult"}:
        from . import sandbox

        return getattr(sandbox, name)
    if name in {"TrialRunner", "run_trials"}:
        from . import runner

        return getattr(runner, name)
    raise AttributeError(name)
