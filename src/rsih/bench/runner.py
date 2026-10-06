"""Trial runner: one task, one container, one genome, one measured outcome.

A trial is reproducible from its directory alone:

```
runs/<run-id>/trials/<task>/trial.json      # status + measured usage + cost
runs/<run-id>/trials/<task>/trajectory.jsonl # every model call and tool call
runs/<run-id>/trials/<task>/verifier.log     # raw verifier stdout/stderr
runs/<run-id>/trials/<task>/reward.txt       # the benchmark's own signal
```
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..agent.genome import Genome
from ..agent.loop import Episode, run_episode
from ..config import Settings, settings as default_settings
from ..llm.client import LLMClient, client_from_env
from .sandbox import DockerSandbox, SandboxError
from .tasks import VERIFIER_SEPARATE, Task

TRIAL_STATUSES = ("success", "failure", "infra_invalid")

#: Episode endings that are not a statement about the harness: the model endpoint
#: never gave the agent a usable turn, so the cell has to be retried, not scored.
UNSCORABLE_EXIT_REASONS = ("model_error", "not_started")

#: Evidence that the verifier never got its own test environment up.  These strings
#: are about the verifier's toolchain, not about the agent's work, so a zero reward
#: alongside them says nothing about the agent.
SETUP_FAILURE_PATTERNS = (
    r"Unable to locate package",
    r"Failed to fetch",
    r"502 {2}Bad Gateway",
    r"Could not resolve host",
    r"Temporary failure in name resolution",
    r"Connection timed out",
    r"release file .* is not valid yet",
    r"are not signed",
    r"uvx: command not found",
    r"uv: command not found",
    r"curl: command not found",
    r"pip: command not found",
    r"pytest: command not found",
)

#: Evidence that the verifier's tests actually executed, so the reward is meaningful.
TESTS_RAN_PATTERNS = (
    r"\d+ (?:passed|failed|error|skipped)",
    r"short test summary info",
    r"no tests ran",
    r"PASSED|FAILED",
    r"^\s*ok\s+\d+",
)


def verifier_setup_failure(log: str) -> str | None:
    """Return the matching setup-failure evidence, or None if the log is usable."""
    if any(re.search(pattern, log, re.MULTILINE) for pattern in TESTS_RAN_PATTERNS):
        return None
    for pattern in SETUP_FAILURE_PATTERNS:
        match = re.search(pattern, log, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


@dataclass
class TrialResult:
    task_id: str
    genome_id: str
    genome_fingerprint: str
    status: str
    reward: float | None
    turns: int
    duration_s: float
    cost_usd: float | None
    cost_first_cold_usd: float | None
    usage: dict
    exit_reason: str
    error: str | None = None
    artifacts: Path | None = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict, artifacts: Path | None = None) -> "TrialResult":
        """Rebuild a result from ``trial.json``.

        Evolution runs are long and the host is shared; a completed cell is not
        re-purchased after an interruption.  Only cells whose recorded fingerprint
        matches the genome being evaluated are reused, so a resumed run can never
        mix results from two harnesses.
        """
        return cls(
            task_id=payload["id"],
            genome_id=payload.get("genome_id", ""),
            genome_fingerprint=payload.get("genome_fingerprint", ""),
            status=payload["status"],
            reward=payload.get("reward"),
            turns=int(payload.get("turns") or 0),
            duration_s=float(payload.get("duration_seconds") or 0.0),
            cost_usd=payload.get("cost_usd"),
            cost_first_cold_usd=payload.get("cost_first_cold_usd"),
            usage=payload.get("usage") or {},
            exit_reason=payload.get("exit_reason", "resumed"),
            error=payload.get("error"),
            artifacts=artifacts,
            extra=payload.get("extra") or {},
        )

    def as_dict(self) -> dict:
        return {
            "id": self.task_id,
            "genome_id": self.genome_id,
            "genome_fingerprint": self.genome_fingerprint,
            "status": self.status,
            "success": self.status == "success",
            "reward": self.reward,
            "turns": self.turns,
            "duration_seconds": round(self.duration_s, 3),
            "cost_usd": self.cost_usd,
            "cost_first_cold_usd": self.cost_first_cold_usd,
            "usage": self.usage,
            "exit_reason": self.exit_reason,
            "error": self.error,
            **self.extra,
        }


def first_cold_cost(per_call: list[dict], card) -> float | None:
    """Re-price the first call's cache reads at the fresh-input rate.

    The benchmark's ``cost_first_cold_usd`` exists because a harness that warms
    the cache on turn one pays for that warm-up; charging it at the discounted
    cache rate would hide a real cost difference between harnesses.
    """
    if not per_call:
        return None
    total = 0.0
    adjusted = False
    for record in per_call:
        cost = record.get("cost_usd")
        if cost is None:
            return None
        prompt = record.get("prompt_tokens") or 0
        cached = record.get("cached_tokens") or 0
        if not adjusted and cached:
            cost += cached * (card.fresh_input - card.cache_read) / card.unit_tokens
            adjusted = True
        total += cost
    return total


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")


def image_present(image: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", image], capture_output=True, text=True
    )
    return result.returncode == 0


class TrialRunner:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: LLMClient | None = None,
        run_dir: Path | None = None,
        run_id: str = "adhoc",
        network: str = "bridge",
        keep_container: bool = False,
        pull_missing: bool = True,
    ):
        self.settings = settings or default_settings()
        self.run_dir = Path(run_dir) if run_dir else self.settings.runs_dir / run_id
        self.run_id = run_id
        self.network = network
        self.keep_container = keep_container
        self.pull_missing = pull_missing
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._client = client

    def client(self, log_path: Path) -> LLMClient:
        # A fresh client per trial keeps the per-call counter and the usage log
        # scoped to one episode.
        return self._client or client_from_env(log_path=log_path)

    def ensure_image(self, task: Task) -> tuple[str, str]:
        """Resolve the task's image, falling back to an equivalent reference.

        Returns the image actually used and a one-line note.  The eval's own
        ``task.toml`` is authoritative, but two DeepSWE entries there name an image
        without the corpus's version tag; a pull failure on the first reference is not
        an agent result, so the equivalent reference is tried rather than recorded as
        an infrastructure failure.
        """
        candidates = [task.docker_image, *task.docker_image_fallbacks]
        last = ""
        for index, image in enumerate(candidates):
            if image_present(image):
                note = "present" if index == 0 else f"fallback reference in use: {image}"
                return image, note
            if not self.pull_missing:
                return task.docker_image, "missing (pull disabled)"
            result = subprocess.run(
                ["docker", "pull", image], capture_output=True, text=True, timeout=3600
            )
            if result.returncode == 0:
                note = "pulled" if index == 0 else f"pulled fallback reference: {image}"
                return image, note
            last = (result.stdout or result.stderr).strip().splitlines()[-1:][0] if (
                result.stdout or result.stderr
            ).strip() else "pull failed"
        return task.docker_image, last

    def _collect_submission(
        self, task: Task, sandbox: DockerSandbox, artifacts: Path
    ) -> str | None:
        """Run the task's collect hook and return the submitted patch.

        DeepSWE's hook is ``git diff <base> HEAD``, so the agent's work only counts
        once it is committed.  An agent that edits without committing would be graded
        on a pristine tree - a submission-protocol failure, not a capability one - so
        a dirty tree is committed first.  This stands in for the "commit your work"
        step the benchmark's own agent runtime performs, and the trial records it.
        """
        assert task.collect_cmd
        status = sandbox.exec_script(
            f"cd {task.workdir} && git status --porcelain", timeout_s=120, workdir=task.workdir
        )
        dirty = bool(status.output.strip())
        if dirty:
            sandbox.exec_script(
                "cd {wd} && git config user.email rsih@local && git config user.name rsih && "
                "git add -A && git commit -q -m 'rsih: submitted work' || true".format(
                    wd=task.workdir
                ),
                timeout_s=300,
                workdir=task.workdir,
            )
        result = sandbox.exec_script(task.collect_cmd, timeout_s=600, workdir=task.workdir)
        if result.exit_code != 0:
            (artifacts / "collect.log").write_text(
                f"dirty_tree_at_submit={dirty}\ncollect_exit={result.exit_code}\n{result.output}",
                encoding="utf-8",
            )
            return None
        patch = sandbox.read_text(task.collect_path, max_bytes=16_000_000)
        if patch is None:
            return None
        (artifacts / "model.patch").write_text(patch, encoding="utf-8")
        (artifacts / "collect.log").write_text(
            f"dirty_tree_at_submit={dirty}\nsubmitted_bytes={len(patch)}\n{result.output}",
            encoding="utf-8",
        )
        return patch

    def _read_reward(
        self, sandbox: DockerSandbox, artifacts: Path, reward_path: str
    ) -> float | None:
        """Read the task's verdict from wherever that task's protocol writes it."""
        raw = sandbox.exec_script(
            f"cat {reward_path} 2>/dev/null || echo __NO_REWARD__", timeout_s=60
        ).output.strip()
        (artifacts / "reward.raw").write_text(raw, encoding="utf-8")
        if not raw or raw == "__NO_REWARD__":
            return None
        if reward_path.endswith(".json"):
            try:
                payload = json.loads(raw.splitlines()[0])
            except (ValueError, IndexError):
                return None
            value = payload.get("reward")
            if value is None:
                return None
            if value == -1:  # DeepSWE's crash sentinel: the verifier never finished
                return None
            return float(value)
        try:
            value = float(raw.splitlines()[0].strip())
        except ValueError:
            return None
        return None if value < 0 else value

    def _read_reward_report(
        self, sandbox: DockerSandbox, artifacts: Path, reward_path: str
    ) -> dict:
        """Keep the verifier's structured verdict, not just the binary reward.

        DeepSWE grades every fail-to-pass test and reports the fraction; the reward is
        binary, but "0 with 70/72 required tests passing" and "0 with 0/72" are
        different findings about the harness and the artifact keeps them apart.
        """
        if not reward_path.endswith(".json"):
            return {}
        raw = sandbox.exec_script(f"cat {reward_path} 2>/dev/null || true", timeout_s=60).output
        if not raw.strip():
            return {}
        (artifacts / "reward.json").write_text(raw, encoding="utf-8")
        try:
            payload = json.loads(raw.splitlines()[0])
        except (ValueError, IndexError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def run_task(
        self, task: Task, genome: Genome, *, attempt: int = 1, resume: bool = True
    ) -> TrialResult:
        suffix = "" if attempt == 1 else f"-attempt{attempt}"
        artifacts = self.run_dir / "trials" / f"{_slug(task.name)}{suffix}"
        artifacts.mkdir(parents=True, exist_ok=True)
        trial_path = artifacts / "trial.json"
        if resume and trial_path.is_file():
            previous = json.loads(trial_path.read_text(encoding="utf-8"))
            if previous.get("genome_fingerprint") == genome.fingerprint():
                return TrialResult.from_dict(previous, artifacts)
        trajectory = artifacts / "trajectory.jsonl"
        llm_log = artifacts / "llm-calls.jsonl"
        for stale in (trajectory, llm_log):
            if stale.exists():
                stale.unlink()

        started = time.time()
        if not task.available:
            return TrialResult(
                task_id=task.id,
                genome_id=genome.id,
                genome_fingerprint=genome.fingerprint(),
                status="infra_invalid",
                reward=None,
                turns=0,
                duration_s=0.0,
                cost_usd=None,
                cost_first_cold_usd=None,
                usage={},
                exit_reason="unavailable",
                error=task.unavailable_reason,
                artifacts=artifacts,
            )

        ok, note = self.ensure_image(task)
        if not ok:
            return TrialResult(
                task_id=task.id,
                genome_id=genome.id,
                genome_fingerprint=genome.fingerprint(),
                status="infra_invalid",
                reward=None,
                turns=0,
                duration_s=time.time() - started,
                cost_usd=None,
                cost_first_cold_usd=None,
                usage={},
                exit_reason="image_unavailable",
                error=f"{task.docker_image}: {note}",
                artifacts=artifacts,
            )

        image_note = note
        sandbox = DockerSandbox(
            task,
            name=f"rsih-{_slug(self.run_id)}-{_slug(task.name)}{suffix}"[:60],
            network=self.network,
        )
        episode: Episode | None = None
        verifier_output = ""
        reward: float | None = None
        status = "infra_invalid"
        error: str | None = None
        verifier_ran = False
        verdict_detail: dict = {}
        try:
            sandbox.start()
            client = self.client(llm_log)
            episode = run_episode(
                task,
                sandbox,
                genome,
                client,
                log_path=trajectory,
                deadline_s=task.agent_timeout_s,
            )
            # Two verifier protocols live in the frozen suite.  A Terminal-Bench task
            # copies its tests into the agent's container once the agent has stopped.
            # A DeepSWE task commits nothing itself: the harness collects the agent's
            # diff and grades it in a *separate*, pristine container, so the agent's
            # own filesystem (editor droppings, stray artifacts) cannot influence the
            # verdict.
            submitted = self._collect_submission(task, sandbox, artifacts) if task.collect_cmd else None
            verifier_sandbox = sandbox
            if task.verifier_mode == VERIFIER_SEPARATE:
                verifier_sandbox = DockerSandbox(
                    task,
                    name=f"rsih-vfy-{_slug(self.run_id)}-{_slug(task.name)}{suffix}"[:60],
                    network=self.network,
                )
                verifier_sandbox.start()
                if submitted is not None:
                    verifier_sandbox.write_text(task.collect_path, submitted)
            try:
                verifier_sandbox.exec_script("mkdir -p /logs/verifier && rm -rf /tests", timeout_s=60)
                verifier_sandbox.copy_tree(Path(task.tests_dir), "/tests")
                result = verifier_sandbox.exec_script(
                    "bash /tests/test.sh", timeout_s=task.verifier_timeout_s, workdir=task.workdir
                )
                verifier_ran = True
                verifier_output = result.output
                (artifacts / "verifier.log").write_text(verifier_output, encoding="utf-8")
                # Read the verdict while the container still exists: a separate
                # verifier environment is torn down as soon as its work is done.
                reward = self._read_reward(verifier_sandbox, artifacts, task.reward_path)
                verdict_detail = self._read_reward_report(
                    verifier_sandbox, artifacts, task.reward_path
                )
            finally:
                if verifier_sandbox is not sandbox and not self.keep_container:
                    verifier_sandbox.remove()
            if reward is None:
                status = "infra_invalid"
                error = (
                    "verifier produced no usable reward"
                    if verifier_ran
                    else "verifier did not run"
                )
            elif episode is not None and episode.exit_reason in UNSCORABLE_EXIT_REASONS:
                # The agent never finished its turn: the endpoint refused the call, so
                # the container holds whatever the agent had done when the quota ran
                # out. That is a measurement failure, not a capability result, and
                # scoring it as a zero would make the suite's difficulty depend on how
                # busy our own IP was.
                status = "infra_invalid"
                error = f"episode did not complete ({episode.exit_reason}): {episode.error or ''}".strip()
            elif reward >= 1:
                status = "success"
            else:
                # A zero reward is only evidence about the agent if the verifier got
                # as far as running its tests.  The task images ship no pytest, so
                # every verifier installs one first; when that install fails (a
                # mirror 502, a DNS hiccup) the script still writes 0, which would
                # otherwise be recorded as a failure the agent caused.
                flake = verifier_setup_failure(verifier_output)
                if flake:
                    status = "infra_invalid"
                    error = f"verifier setup failed before any test ran: {flake}"
                else:
                    status = "failure"
        except SandboxError as exc:
            status = "infra_invalid"
            error = f"sandbox error: {exc}"
        except Exception as exc:  # noqa: BLE001
            status = "infra_invalid"
            error = f"{type(exc).__name__}: {exc}"
        finally:
            if not self.keep_container:
                sandbox.remove()

        duration = time.time() - started
        ledger = episode.ledger if episode else None
        per_call = ledger.per_call if ledger else []
        card = ledger.card if ledger else None
        usage = ledger.usage.as_dict() if ledger else {}
        cost = ledger.cost_usd() if ledger else None
        first_cold = first_cold_cost(per_call, card) if card else None

        result = TrialResult(
            task_id=task.id,
            genome_id=genome.id,
            genome_fingerprint=genome.fingerprint(),
            status=status,
            reward=reward,
            turns=episode.turns if episode else 0,
            duration_s=duration,
            cost_usd=cost,
            cost_first_cold_usd=first_cold,
            usage=usage,
            exit_reason=episode.exit_reason if episode else "not_started",
            error=error or (episode.error if episode else None),
            artifacts=artifacts,
            extra={
                "image": task.docker_image,
                "image_resolution": image_note,
                "verifier_ran": verifier_ran,
                "verifier_mode": task.verifier_mode,
                "allow_internet_declared": task.allow_internet,
                "network_policy_note": sandbox.network_policy_note,
                "compactions": episode.compactions if episode else 0,
                "submit_rejections": episode.submit_rejections if episode else 0,
                "reward_source": f"tests/test.sh -> {task.reward_path}",
                "tests_source": str(task.tests_dir),
                "agent_timeout_s": task.agent_timeout_s,
                "agent_timeout_declared_s": task.agent_timeout_declared_s,
                "agent_timeout_capped": task.timeout_capped,
                "submitted_bytes": len(submitted) if submitted else 0,
                "verifier_detail": verdict_detail,
            },
        )
        if episode:
            (artifacts / "episode.json").write_text(
                json.dumps(episode.as_dict(include_messages=True), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        (artifacts / "trial.json").write_text(
            json.dumps(result.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8"        )
        return result

    def save_run_meta(self, payload: dict) -> None:
        path = self.run_dir / "run.json"
        existing = {}
        if path.is_file():
            existing = json.loads(path.read_text(encoding="utf-8"))
        existing.update(payload)
        existing["updated_at"] = time.time()
        path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def run_trials(
    tasks: list[Task],
    genome: Genome,
    *,
    run_id: str,
    settings: Settings | None = None,
    network: str = "bridge",
    keep_container: bool = False,
    on_result=None,
    concurrency: int = 1,
    infra_retries: int = 1,
) -> tuple[list[TrialResult], Path]:
    """Run one genome over a task list, sequentially or with bounded concurrency.

    Trials are independent: each owns its container, its LLM client and its
    artifact directory, so concurrency changes wall-clock time and nothing else.
    """
    runner = TrialRunner(
        settings=settings, run_id=run_id, network=network, keep_container=keep_container
    )
    runner.save_run_meta(
        {
            "run_id": run_id,
            "genome": genome.to_dict(),
            "model": (settings or default_settings()).model,
            "task_ids": [t.id for t in tasks],
            "concurrency": concurrency,
            "started_at": time.time(),
            "host": _host_fingerprint(),
        }
    )
    results: list[TrialResult] = []
    if concurrency and concurrency > 1 and len(tasks) > 1:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(runner.run_task, task, genome): task for task in tasks}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                results.append(result)
                runner.save_run_meta({"completed": [r.task_id for r in results]})
                if on_result:
                    on_result(result)
        order = {task.id: index for index, task in enumerate(tasks)}
        results.sort(key=lambda r: order[r.task_id])
    else:
        for task in tasks:
            result = runner.run_task(task, genome)
            results.append(result)
            runner.save_run_meta({"completed": [r.task_id for r in results]})
            if on_result:
                on_result(result)

    # A cell that could not be scored at all (verifier setup flake, image failure)
    # is retried once. The benchmark's own selection rule is "first valid attempt",
    # so an infra-invalid cell must not be recorded as a failure or dropped.
    for attempt in range(2, infra_retries + 2):
        retry_tasks = [
            task
            for task in tasks
            if next(r for r in results if r.task_id == task.id).status == "infra_invalid"
            and next(r for r in results if r.task_id == task.id).exit_reason != "unavailable"
        ]
        if not retry_tasks:
            break
        for task in retry_tasks:
            result = runner.run_task(task, genome, attempt=attempt)
            results = [result if r.task_id == task.id else r for r in results]
            runner.save_run_meta({"retried": [t.id for t in retry_tasks], "attempt": attempt})
            if on_result:
                on_result(result)

    passed = sum(1 for r in results if r.status == "success")
    valid = [r for r in results if r.status in ("success", "failure")]
    known_cost = [r.cost_usd for r in valid if r.cost_usd is not None]
    runner.save_run_meta(
        {
            "finished_at": time.time(),
            "passed": passed,
            "valid": len(valid),
            "expected": len(results),
            "pass_rate": passed / len(valid) if valid else None,
            "total_cost_usd": sum(known_cost) if known_cost else None,
        }
    )
    return results, runner.run_dir


def _host_fingerprint() -> dict:
    info: dict = {}
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        info["docker_server"] = result.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        info["docker_server"] = f"unavailable: {exc}"
    info["shutil_disk_free_gb"] = round(shutil.disk_usage(Path.cwd()).free / 1e9, 1)
    return info
