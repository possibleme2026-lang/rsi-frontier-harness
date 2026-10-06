"""Run one task's verifier in a fresh container, with no agent involved.

This answers a question the trial record cannot: did the verifier fail because of the
agent's final filesystem state, or because the verifier's own setup is fragile under
this runtime?  A task whose verifier cannot score a *pristine* container must be
reported as infra-invalid rather than counted as a failure.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.bench.sandbox import DockerSandbox  # noqa: E402
from rsih.bench.tasks import load_tasks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    task = next(t for t in load_tasks(None, [args.task]) if t.available)
    sandbox = DockerSandbox(task, name=f"rsih-verify-{task.name}"[:60], network="bridge")
    sandbox.start()
    try:
        sandbox.exec_script("mkdir -p /logs/verifier && rm -rf /tests", timeout_s=60)
        sandbox.copy_tree(Path(task.tests_dir), "/tests")
        result = sandbox.exec_script("bash /tests/test.sh", timeout_s=task.verifier_timeout_s)
        print(result.output[-4000:])
        print(f"[exit {result.exit_code} in {result.duration_s:.0f}s]")
        reward = sandbox.exec_script(
            "cat /logs/verifier/reward.txt 2>/dev/null || echo __NO_REWARD__", timeout_s=60
        )
        print(f"reward: {reward.output.strip()}")
        return 0
    finally:
        if not args.keep:
            sandbox.remove()


if __name__ == "__main__":
    raise SystemExit(main())
