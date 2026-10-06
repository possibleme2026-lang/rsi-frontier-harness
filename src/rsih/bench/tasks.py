"""The task suite.

The suite is read from the published FrontierHarness Eval repository
(``_ref-frontier-eval``): the task ids come from ``benchmark.json``, the
instruction shown to the agent comes from that repository's ``tasks/<t>/instruction.md``,
and the resource envelope (image, vCPU, memory, timeouts) comes from that
repository's ``task.toml``.  Those are the frozen benchmark inputs.

The *verifier* is not published there.  Terminal-Bench task definitions with
their ``tests/`` directory come from the public ``terminal-bench-2`` repository,
downloaded once into ``_ref-tb2``.  Nine DeepSWE tasks in the frozen suite come
from a corpus that is not public; they are reported as unavailable rather than
guessed at.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings, settings as default_settings

DEFAULT_WORKDIR = "/app"


@dataclass(frozen=True)
class Task:
    id: str
    suite: str
    name: str
    instruction: str
    docker_image: str
    cpus: float
    memory_mb: int
    storage_mb: int
    agent_timeout_s: float
    verifier_timeout_s: float
    allow_internet: bool
    env: dict[str, str] = field(default_factory=dict)
    tests_dir: Path | None = None
    workdir: str = DEFAULT_WORKDIR
    unavailable_reason: str | None = None

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None

    @property
    def short(self) -> str:
        return self.name


def _load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _task_from_dir(eval_repo: Path, tb2_repo: Path, task_id: str) -> Task:
    suite, name = task_id.split("/", 1)
    toml_path = eval_repo / "tasks" / name / "task.toml"
    instruction_path = eval_repo / "tasks" / name / "instruction.md"

    if not toml_path.is_file() or not instruction_path.is_file():
        return Task(
            id=task_id,
            suite=suite,
            name=name,
            instruction="",
            docker_image="",
            cpus=0,
            memory_mb=0,
            storage_mb=0,
            agent_timeout_s=0,
            verifier_timeout_s=0,
            allow_internet=False,
            unavailable_reason=f"task definition missing under {eval_repo}",
        )

    data = _load_toml(toml_path)
    environment = data.get("environment", {})
    tests_dir = tb2_repo / name / "tests"
    reason = None
    if not tests_dir.is_dir():
        reason = (
            f"verifier (tests/) not published with the benchmark and not present in "
            f"the local terminal-bench-2 checkout at {tests_dir}"
        )

    return Task(
        id=task_id,
        suite=suite,
        name=name,
        instruction=instruction_path.read_text(encoding="utf-8"),
        docker_image=environment.get("docker_image", ""),
        cpus=float(environment.get("cpus", 1)),
        memory_mb=int(environment.get("memory_mb", 2048)),
        storage_mb=int(environment.get("storage_mb", 10240)),
        agent_timeout_s=float(data.get("agent", {}).get("timeout_sec", 900)),
        verifier_timeout_s=float(data.get("verifier", {}).get("timeout_sec", 900)),
        allow_internet=bool(environment.get("allow_internet", False)),
        env=dict(environment.get("env", {})),
        tests_dir=tests_dir if tests_dir.is_dir() else None,
        workdir=environment.get("workdir") or DEFAULT_WORKDIR,
        unavailable_reason=reason,
    )


def load_tasks(settings: Settings | None = None, task_ids: list[str] | None = None) -> list[Task]:
    settings = settings or default_settings()
    import json

    benchmark = json.loads((settings.eval_repo / "benchmark.json").read_text(encoding="utf-8"))
    known_ids = list(benchmark["task_ids"])
    if task_ids:
        # Accept either the fully qualified id or the bare task name, so
        # `--tasks regex-log` works without repeating the suite prefix.
        by_name = {task_id.split("/", 1)[1]: task_id for task_id in known_ids}
        ids = [t if t in known_ids else by_name.get(t, t) for t in task_ids]
    else:
        ids = known_ids
    unknown = [t for t in ids if t not in known_ids]
    if unknown:
        raise KeyError(f"task id(s) not in the frozen benchmark: {unknown}")
    return [_task_from_dir(settings.eval_repo, settings.tb2_repo, task_id) for task_id in ids]


def available_tasks(settings: Settings | None = None) -> tuple[list[Task], list[Task]]:
    tasks = load_tasks(settings)
    return (
        [t for t in tasks if t.available],
        [t for t in tasks if not t.available],
    )
