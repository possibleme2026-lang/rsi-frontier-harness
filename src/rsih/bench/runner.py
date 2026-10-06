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
from .tasks import Task

TRIAL_STATUSES = ("success", "failure", "infra_invalid")


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

    def ensure_image(self, image: str) -> tuple[bool, str]:
        if image_present(image):
            return True, "present"
        if not self.pull_missing:
            return False, "missing (pull disabled)"
        result = subprocess.run(
            ["docker", "pull", image], capture_output=True, text=True, timeout=3600
        )
        return result.returncode == 0, (result.stdout or result.stderr).strip().splitlines()[-1:][0] if result.returncode else "pulled"

    def run_task(self, task: Task, genome: Genome) -> TrialResult:
        artifacts = self.run_dir / "trials" / _slug(task.name)
        artifacts.mkdir(parents=True, exist_ok=True)
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

        ok, note = self.ensure_image(task.docker_image)
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

        sandbox = DockerSandbox(task, name=f"rsih-{_slug(self.run_id)}-{_slug(task.name)}"[:60], network=self.network)
        episode: Episode | None = None
        verifier_output = ""
        reward: float | None = None
        status = "infra_invalid"
        error: str | None = None
        verifier_ran = False
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
            # Verifier: the tests are copied in only after the agent is done, so the
            # agent never sees them.
            sandbox.exec_script("mkdir -p /logs/verifier && rm -rf /tests", timeout_s=60)
            sandbox.copy_tree(Path(task.tests_dir), "/tests")
            result = sandbox.exec_script(
                "bash /tests/test.sh", timeout_s=task.verifier_timeout_s
            )
            verifier_ran = True
            verifier_output = result.output
            (artifacts / "verifier.log").write_text(verifier_output, encoding="utf-8")
            reward = self._read_reward(sandbox, artifacts)
            if reward is None:
                status = "infra_invalid"
                error = "verifier produced no reward file"
            else:
                status = "success" if reward >= 1 else "failure"
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
                "verifier_ran": verifier_ran,
                "allow_internet_declared": task.allow_internet,
                "network_policy_note": sandbox.network_policy_note,
                "compactions": episode.compactions if episode else 0,
                "submit_rejections": episode.submit_rejections if episode else 0,
                "reward_source": "tests/test.sh -> /logs/verifier/reward.txt",
                "tests_source": str(task.tests_dir),
            },
        )
        if episode:
            (artifacts / "episode.json").write_text(
                json.dumps(episode.as_dict(include_messages=True), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        (artifacts / "trial.json").write_text(
            json.dumps(result.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return result

    @staticmethod
    def _read_reward(sandbox: DockerSandbox, artifacts: Path) -> float | None:
        result = sandbox.exec_script(
            "test -f /logs/verifier/reward.txt && cat /logs/verifier/reward.txt || echo __NO_REWARD__",
            timeout_s=60,
        )
        text = result.output.strip().splitlines()[-1] if result.output.strip() else ""
        (artifacts / "reward.txt").write_text(text, encoding="utf-8")
        if "__NO_REWARD__" in text or not text:
            return None
        try:
            return float(text.strip())
        except ValueError:
            return None

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
