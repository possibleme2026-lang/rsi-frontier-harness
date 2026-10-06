"""Docker sandbox for one trial.

The sandbox is a single long-lived container started from the frozen task image.
Commands are executed through ``docker exec`` with the script fed on stdin, which
avoids every shell-quoting hazard: the agent may put newlines, quotes and unicode
in a command and the bytes that reach the container are exactly the bytes the
model emitted.

Network policy: the FrontierHarness run applied a runtime-wide allowlist that
also admitted the package hosts its verifiers need.  Locally we start the
container on the default bridge network so that ``tests/test.sh`` (which installs
``uv`` and ``pytest``) can run at all; this deviation is recorded in every trial
record rather than being left implicit.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .tasks import Task

CWD_SENTINEL = "<<<RSIH_CWD>>>"
EXIT_SENTINEL = "<<<RSIH_EXIT>>>"


class SandboxError(RuntimeError):
    pass


@dataclass
class ExecResult:
    command: str
    exit_code: int | None
    output: str
    duration_s: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _run(argv: list[str], *, timeout: float | None = None, input_text: str | None = None) -> subprocess.CompletedProcess:
    """Run a command with byte-exact stdin.

    ``subprocess`` in text mode rewrites ``\\n`` to the platform separator, which
    corrupts a script sent to a Linux shell from Windows (the shell then sees
    ``$'\\r'``).  Everything therefore travels as bytes and is decoded here.
    """
    proc = subprocess.run(
        argv,
        input=input_text.encode("utf-8") if input_text is not None else None,
        capture_output=True,
        timeout=timeout,
    )
    return subprocess.CompletedProcess(
        argv,
        proc.returncode,
        (proc.stdout or b"").decode("utf-8", errors="replace"),
        (proc.stderr or b"").decode("utf-8", errors="replace"),
    )


class DockerSandbox:
    def __init__(
        self,
        task: Task,
        name: str,
        *,
        workdir: str | None = None,
        network: str = "bridge",
        container_engine: str = "docker",
    ):
        self.task = task
        self.name = name
        self.workdir = workdir or task.workdir
        self.network = network
        self.engine = container_engine
        self._has_timeout: bool | None = None
        self.started_at: float | None = None
        self.network_policy_note = (
            "container started on the default bridge network; the task metadata declares "
            f"allow_internet={task.allow_internet}. The published run applied a runtime-wide "
            "allowlist that also admitted verifier package hosts, which cannot be reproduced "
            "exactly with a local Docker bridge."
        )

    # -------------------------------------------------------------- lifecycle

    def exists(self) -> bool:
        result = _run([self.engine, "inspect", "-f", "{{.Id}}", self.name])
        return result.returncode == 0

    def start(self) -> None:
        if self.exists():
            self.remove()
        argv = [
            self.engine,
            "run",
            "-d",
            "--name",
            self.name,
            "--cpus",
            str(self.task.cpus),
            "--memory",
            f"{self.task.memory_mb}m",
            "--memory-swap",
            f"{self.task.memory_mb}m",
            "--network",
            self.network,
            "-w",
            self.workdir,
        ]
        for key, value in self.task.env.items():
            argv += ["-e", f"{key}={value}"]
        argv += [self.task.docker_image, "sleep", "infinity"]
        result = _run(argv, timeout=300)
        if result.returncode != 0:
            raise SandboxError(f"could not start {self.name}: {result.stderr.strip()[:400]}")
        self.started_at = time.time()
        probe = self._exec_raw("command -v timeout >/dev/null 2>&1 && echo yes || echo no", timeout_s=60)
        self._has_timeout = probe.output.strip().endswith("yes")

    def remove(self, *, force: bool = True) -> None:
        argv = [self.engine, "rm", "-f", self.name] if force else [self.engine, "rm", self.name]
        _run(argv, timeout=180)

    # ------------------------------------------------------------------ exec

    def _exec_raw(self, script: str, *, timeout_s: float, workdir: str | None = None) -> ExecResult:
        wrapped = (
            # stderr belongs in the agent's observation, and it belongs in order.
            "exec 2>&1\n"
            'export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:$PATH"\n'
            f"{script}\n"
            "__rsih_code=$?\n"
            f"printf '\\n{CWD_SENTINEL}%s\\n{EXIT_SENTINEL}%s\\n' \"$PWD\" \"$__rsih_code\"\n"
        )
        argv = [
            self.engine,
            "exec",
            "-i",
            "-w",
            workdir or self.workdir,
            self.name,
        ]
        if self._has_timeout:
            argv += ["timeout", "-k", "5", str(max(1, int(timeout_s)))]
        argv += ["bash", "-s"]

        started = time.time()
        timed_out = False
        try:
            proc = _run(argv, timeout=timeout_s + 30, input_text=wrapped)
            stdout, code, stderr = proc.stdout, proc.returncode, proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            code = None
        duration = time.time() - started

        output, exit_code, cwd = self._split(stdout, code)
        if stderr.strip():
            output = f"{output}\n[harness] {stderr.strip()}"
        if cwd:
            self.workdir = cwd
        return ExecResult(
            command=script,
            exit_code=exit_code,
            output=output,
            duration_s=duration,
            timed_out=timed_out,
        )

    @staticmethod
    def _split(stdout: str, fallback_code: int | None) -> tuple[str, int | None, str | None]:
        cwd = None
        exit_code = fallback_code
        text = stdout
        if EXIT_SENTINEL in text:
            head, _, tail = text.rpartition(EXIT_SENTINEL)
            first_line, _, _ = tail.partition("\n")
            try:
                exit_code = int(first_line.strip())
            except ValueError:
                exit_code = fallback_code
            text = head
        if CWD_SENTINEL in text:
            head, _, tail = text.rpartition(CWD_SENTINEL)
            first_line, _, _ = tail.partition("\n")
            cwd = first_line.strip()
            text = head
        return text, exit_code, cwd

    def exec_script(
        self, script: str, *, timeout_s: float = 120.0, workdir: str | None = None
    ) -> ExecResult:
        if self._has_timeout is None:
            raise SandboxError("sandbox not started")
        return self._exec_raw(script, timeout_s=timeout_s, workdir=workdir)

    # ------------------------------------------------------------------ files

    def copy_tree(self, local: Path, remote: str) -> None:
        target = f"{self.name}:{remote}"
        Path(local).exists() or (_ for _ in ()).throw(SandboxError(f"missing {local}"))
        result = _run([self.engine, "cp", f"{local}{os_sep()}.", target], timeout=300)
        if result.returncode != 0:
            raise SandboxError(f"docker cp failed: {result.stderr.strip()[:300]}")

    def write_text(self, remote_path: str, text: str) -> None:
        import base64

        payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
        script = (
            f"mkdir -p \"$(dirname '{remote_path}')\"\n"
            f"printf '%s' '{payload}' | base64 -d > '{remote_path}'\n"
        )
        result = self._exec_raw(script, timeout_s=120)
        if not result.ok:
            raise SandboxError(f"write_text failed: {result.output[-300:]}")

    def read_text(self, remote_path: str, *, max_bytes: int = 400_000) -> str | None:
        import base64

        result = self._exec_raw(
            f"test -f '{remote_path}' && base64 -w0 '{remote_path}' || echo __MISSING__",
            timeout_s=120,
        )
        text = result.output.strip()
        if text.endswith("__MISSING__") or not text:
            return None
        try:
            raw = base64.b64decode(text.split("\n")[-1])
        except Exception:  # noqa: BLE001
            return None
        return raw[:max_bytes].decode("utf-8", errors="replace")


def os_sep() -> str:
    return "\\" if shutil.os.name == "nt" else "/"
