"""Pull every task image that the frozen suite needs, in parallel.

Kept as a script rather than inlined shell because the pull is the slowest part of
setting the benchmark up and it needs to be resumable: an image already present is
skipped without touching the network.
"""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.bench.tasks import load_tasks  # noqa: E402


def present(image: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0


def pull(image: str) -> tuple[str, bool, str, float]:
    started = time.time()
    if present(image):
        return image, True, "present", 0.0
    result = subprocess.run(["docker", "pull", image], capture_output=True, text=True, timeout=3600)
    tail = (result.stdout or result.stderr or "").strip().splitlines()
    return image, result.returncode == 0, tail[-1] if tail else "", time.time() - started


def main() -> int:
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    tasks = [t for t in load_tasks() if t.available]
    images = sorted({t.docker_image for t in tasks})
    print(f"pulling {len(images)} image(s) with {workers} worker(s)", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(pull, image) for image in images]
        for future in concurrent.futures.as_completed(futures):
            image, ok, note, seconds = future.result()
            print(f"  [{'ok' if ok else 'FAIL'}] {image:<56} {seconds:6.1f}s {note[:60]}", flush=True)
    missing = [i for i in images if not present(i)]
    print(json.dumps({"images": len(images), "missing": missing}, indent=2))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
