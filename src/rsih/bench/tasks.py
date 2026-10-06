"""The task suite.

The suite is read from the published FrontierHarness Eval repository
(``_ref-frontier-eval``): the task ids come from ``benchmark.json``, the
instruction shown to the agent comes from that repository's ``tasks/<t>/instruction.md``,
and the resource envelope (image, vCPU, memory, timeouts) comes from that
repository's ``task.toml``.  Those are the frozen benchmark inputs.

The benchmark mixes two corpus families, and they do not share a verification
protocol:

* ``terminal-bench/*`` - the verifier is a ``tests/`` directory that is copied
  into the agent's own container after the agent stops (``in_place``).
* ``datacurve/*`` - the DeepSWE corpus.  The agent works in a git checkout and
  the harness collects its diff as a patch (``collect``); grading happens in a
  *separate* container from the same image, where the patch and the held-out
  tests are applied to a pristine checkout (``separate``).

Both are read from the task's own ``task.toml``, so the difference is data, not
a special case in the runner.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings, settings as default_settings

DEFAULT_WORKDIR = "/app"

#: How the task's verifier is staged relative to the agent's container.
VERIFIER_IN_PLACE = "in_place"
VERIFIER_SEPARATE = "separate"


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
    verifier_mode: str = VERIFIER_IN_PLACE
    #: command whose stdout is the submitted artifact (DeepSWE: ``git diff``)
    collect_cmd: str | None = None
    #: where that artifact must appear for the verifier to grade it
    collect_path: str = "/logs/artifacts/model.patch"
    #: where the task's own verifier writes its verdict
    reward_path: str = "/logs/verifier/reward.txt"
    #: declared wall-clock envelope, before any local cap
    agent_timeout_declared_s: float = 0.0
    #: images to try if ``docker_image`` cannot be pulled.  The frozen eval's
    #: ``task.toml`` for two DeepSWE tasks names an image without the corpus's
    #: ``-v1.1`` tag; the corpus copy of the same task carries the usable reference.
    docker_image_fallbacks: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None

    @property
    def short(self) -> str:
        return self.name

    @property
    def timeout_capped(self) -> bool:
        return self.agent_timeout_declared_s > self.agent_timeout_s


def _load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _missing(suite: str, name: str, task_id: str, reason: str) -> Task:
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
        unavailable_reason=reason,
    )


def _terminal_bench_task(eval_repo: Path, tb2_repo: Path, task_id: str, name: str) -> Task:
    toml_path = eval_repo / "tasks" / name / "task.toml"
    instruction_path = eval_repo / "tasks" / name / "instruction.md"
    if not toml_path.is_file() or not instruction_path.is_file():
        return _missing("terminal-bench", name, task_id, f"task definition missing under {eval_repo}")

    data = _load_toml(toml_path)
    environment = data.get("environment", {})
    tests_dir = tb2_repo / name / "tests"
    reason = None
    if not tests_dir.is_dir():
        reason = (
            f"verifier (tests/) not published with the benchmark and not present in "
            f"the local terminal-bench-2 checkout at {tests_dir}"
        )
    timeout = float(data.get("agent", {}).get("timeout_sec", 900))
    return Task(
        id=task_id,
        suite="terminal-bench",
        name=name,
        instruction=instruction_path.read_text(encoding="utf-8"),
        docker_image=environment.get("docker_image", ""),
        cpus=float(environment.get("cpus", 1)),
        memory_mb=int(environment.get("memory_mb", 2048)),
        storage_mb=int(environment.get("storage_mb", 10240)),
        agent_timeout_s=timeout,
        agent_timeout_declared_s=timeout,
        verifier_timeout_s=float(data.get("verifier", {}).get("timeout_sec", 900)),
        allow_internet=bool(environment.get("allow_internet", False)),
        env=dict(environment.get("env", {})),
        tests_dir=tests_dir if tests_dir.is_dir() else None,
        workdir=environment.get("workdir") or DEFAULT_WORKDIR,
        unavailable_reason=reason,
        verifier_mode=VERIFIER_IN_PLACE,
    )


def _deep_swe_task(
    eval_repo: Path, deepswe_repo: Path, task_id: str, name: str, cap_s: float
) -> Task:
    toml_path = eval_repo / "tasks" / name / "task.toml"
    instruction_path = eval_repo / "tasks" / name / "instruction.md"
    corpus_dir = deepswe_repo / "tasks" / name
    if not toml_path.is_file() or not instruction_path.is_file():
        return _missing("datacurve", name, task_id, f"task definition missing under {eval_repo}")
    if not corpus_dir.is_dir():
        return _missing(
            "datacurve",
            name,
            task_id,
            f"DeepSWE task directory not present in the local corpus checkout at {corpus_dir}",
        )

    data = _load_toml(toml_path)
    corpus = _load_toml(corpus_dir / "task.toml")
    environment = data.get("environment", {})
    verifier = data.get("verifier", {})
    corpus_verifier = corpus.get("verifier", {})
    tests_dir = corpus_dir / "tests"
    reason = None
    if not tests_dir.is_dir():
        reason = f"DeepSWE verifier (tests/) missing at {tests_dir}"
    declared = float(data.get("agent", {}).get("timeout_sec", 10800))
    # The corpus is the authority on the *verification protocol* (schema 1.3 adds the
    # collect hook and the separate verifier environment); the frozen eval is the
    # authority on the *envelope* it was run under.  Where they disagree on the
    # protocol, the protocol that can actually grade the task wins.
    collect = (corpus_verifier.get("collect") or [{}])[0].get("command") or (
        verifier.get("collect") or [{}]
    )[0].get("command")
    reward_path = "/logs/verifier/reward.json" if (tests_dir / "grader.py").is_file() else "/logs/verifier/reward.txt"
    timeout = min(declared, cap_s) if cap_s else declared
    corpus_image = corpus.get("environment", {}).get("docker_image", "")
    eval_image = environment.get("docker_image") or ""
    image = corpus_image or eval_image
    fallbacks = tuple(i for i in (eval_image,) if i and i != image)
    artifacts = corpus.get("artifacts") or data.get("artifacts") or ["/logs/artifacts/model.patch"]
    return Task(
        id=task_id,
        suite="datacurve",
        name=name,
        instruction=instruction_path.read_text(encoding="utf-8"),
        docker_image=image,
        cpus=float(environment.get("cpus", 2)),
        memory_mb=int(environment.get("memory_mb", 8192)),
        storage_mb=int(environment.get("storage_mb", 20480)),
        agent_timeout_s=timeout,
        agent_timeout_declared_s=declared,
        verifier_timeout_s=float(verifier.get("timeout_sec", 1800)),
        allow_internet=False,
        env=dict(environment.get("env", {})),
        tests_dir=tests_dir if tests_dir.is_dir() else None,
        workdir=environment.get("workdir") or DEFAULT_WORKDIR,
        unavailable_reason=reason,
        verifier_mode=VERIFIER_SEPARATE,
        collect_cmd=collect,
        collect_path=artifacts[0],
        reward_path=reward_path,
        docker_image_fallbacks=fallbacks,
    )


def _task_from_dir(settings: Settings, task_id: str) -> Task:
    suite, name = task_id.split("/", 1)
    if suite == "datacurve":
        return _deep_swe_task(
            settings.eval_repo, settings.deepswe_repo, task_id, name, settings.agent_timeout_cap_s
        )
    return _terminal_bench_task(settings.eval_repo, settings.tb2_repo, task_id, name)


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
    return [_task_from_dir(settings, task_id) for task_id in ids]


def available_tasks(settings: Settings | None = None) -> tuple[list[Task], list[Task]]:
    tasks = load_tasks(settings)
    return (
        [t for t in tasks if t.available],
        [t for t in tasks if not t.available],
    )
