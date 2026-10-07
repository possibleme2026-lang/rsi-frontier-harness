"""Is there a continuous signal available to the RSI gate?

The gate compares pass counts and needs a net swing of several tasks before it will accept
anything, which on a six-task evolve split means capability can barely ever be adopted.
DeepSWE reports how far a patch got -- required tests passing, existing tests still green --
and that is a dense signal in exactly the dimension a harness mutation would move.  This
checks the signal was actually recorded rather than assuming it.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="*", default=None)
    args = parser.parse_args()

    run_dirs = [ROOT / r for r in args.runs] if args.runs else sorted(
        p for p in (ROOT / "runs").glob("*")
        if p.is_dir() and not p.name.startswith("_") and (p / "trials").is_dir()
    )

    scored = 0
    with_detail = 0
    rows = []
    for run in run_dirs:
        for path in run.glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if trial["status"] not in ("success", "failure"):
                continue
            scored += 1
            # Older runs predate the field being written, but the verifier's own report
            # is kept beside the trial, so fall back to reading it rather than reporting
            # a signal that exists as missing.
            detail = trial.get("verifier_detail") or {}
            if not detail:
                raw = path.parent / "reward.json"
                if raw.is_file():
                    try:
                        detail = json.loads(raw.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        detail = {}
            f2p, p2p = detail.get("f2p"), detail.get("p2p")
            if f2p is None and p2p is None:
                continue
            with_detail += 1
            rows.append(
                {
                    "run": run.name,
                    "task": trial.get("task_id") or trial["id"],
                    "status": trial["status"],
                    "f2p": f2p,
                    "p2p": p2p,
                    "partial": detail.get("partial"),
                }
            )

    print(f"scored trials                 : {scored}")
    print(f"trials carrying f2p/p2p detail: {with_detail}")
    print()

    print(f"{'task':<46}{'f2p':>8}{'p2p':>8}  verdict")
    for row in sorted(rows, key=lambda r: (r["task"], r["run"])):
        name = row["task"].split("/")[-1][:44]
        f2p = "n/a" if row["f2p"] is None else f"{row['f2p']:.3f}"
        p2p = "n/a" if row["p2p"] is None else f"{row['p2p']:.3f}"
        print(f"{name:<46}{f2p:>8}{p2p:>8}  {row['status']:<8} {row['run']}")

    failed = [r for r in rows if r["status"] == "failure" and r["f2p"] is not None]
    if failed:
        print()
        print("Failed trials that were nevertheless partly correct:")
        for row in sorted(failed, key=lambda r: -(r["f2p"] or 0))[:12]:
            name = row["task"].split("/")[-1][:44]
            p2p_note = "" if row["p2p"] == 1.0 else f"  (p2p {row['p2p']:.3f})"
            print(f"  {name:<46} f2p={row['f2p']:.3f}{p2p_note}")
        partial_only = [r for r in failed if (r["f2p"] or 0) > 0]
        print()
        print(f"failures with nonzero f2p     : {len(partial_only)}/{len(failed)}")
        if partial_only:
            print(f"median f2p among those        : "
                  f"{statistics.median([r['f2p'] for r in partial_only]):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

