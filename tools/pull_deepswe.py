"""Pull the images the frozen suite needs, from the frozen task definitions.

Kept separate from the runner so image acquisition (slow, network-bound, resumable)
is never entangled with measurement.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.bench.tasks import load_tasks  # noqa: E402


def pull(image: str) -> tuple[str, bool, str]:
    present = subprocess.run(
        ["docker", "image", "inspect", image], capture_output=True, text=True
    ).returncode == 0
    if present:
        return image, True, "present"
    result = subprocess.run(["docker", "pull", image], capture_output=True, text=True, timeout=3600)
    tail = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()[-1:]
    return image, result.returncode == 0, tail[0] if tail else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", default=None, help="only this suite prefix, e.g. datacurve")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    tasks = [t for t in load_tasks(None) if args.family is None or t.suite == args.family]
    images = [t.docker_image for t in tasks if t.docker_image]
    print(f"{len(images)} image(s) for {len(tasks)} task(s), {args.workers} worker(s)")
    failures = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for image, ok, note in pool.map(pull, images):
            print(f"  [{'ok' if ok else 'FAIL'}] {image} :: {note}", flush=True)
            failures += 0 if ok else 1
    print(f"missing after run: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
