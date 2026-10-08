"""Does the agent phase really have no route off the host, and the verifier one?

A network policy that is only declared is worth nothing -- the whole reason this exists is
that three measured episodes reached github.com while their task declared
allow_internet=False.  So this starts a container the way the agent phase does, tries to
reach the network, then opens the network the way the verifier phase does and tries again.
It asserts on observed connectivity, not on the flags passed to docker.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.bench.sandbox import DockerSandbox  # noqa: E402
from rsih.bench.tasks import Task  # noqa: E402

PROBE = (
    "python3 - <<'EOF'\n"
    "import socket\n"
    "for host, port in (('github.com', 443), ('raw.githubusercontent.com', 443)):\n"
    "    try:\n"
    "        socket.create_connection((host, port), timeout=8).close()\n"
    "        print(f'{host}: REACHABLE')\n"
    "    except Exception as exc:\n"
    "        print(f'{host}: blocked ({type(exc).__name__})')\n"
    "EOF\n"
)


def main() -> int:
    task = Task(
        id="probe/network",
        suite="probe",
        name="network",
        instruction="",
        docker_image="python:3.12-slim",
        cpus=1.0,
        memory_mb=1024,
        storage_mb=2048,
        agent_timeout_s=120.0,
        verifier_timeout_s=120.0,
        allow_internet=False,
        workdir="/tmp",
        tests_dir=Path("/tmp"),
    )
    sandbox = DockerSandbox(task, name="rsih-net-probe")
    failures = 0
    try:
        sandbox.start()
        isolated = sandbox.exec_script(PROBE, timeout_s=90).output
        print("--- agent phase (expect blocked) ---")
        print(isolated.strip())
        if "REACHABLE" in isolated:
            print("FAIL: the agent phase can still reach the network")
            failures += 1

        sandbox.open_network()
        opened = sandbox.exec_script(PROBE, timeout_s=90).output
        print("--- verifier phase (expect reachable) ---")
        print(opened.strip())
        if "REACHABLE" not in opened:
            print("FAIL: the verifier phase has no network, so test.sh cannot install")
            failures += 1
    finally:
        sandbox.remove()

    print()
    print("PASS" if failures == 0 else f"{failures} check(s) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
