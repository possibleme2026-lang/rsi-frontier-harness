"""Print the near-miss cells: a failure whose verifier report shows it nearly passed.

The RSI gate scores pass/fail, so a task sitting at 70 of 72 required tests reads exactly
like a task with no patch at all.  Before changing the gate, look at what it was hiding.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    rows = []
    for run in sorted((ROOT / "runs").glob("smoke-*")):
        pass
    for run in sorted(p for p in (ROOT / "runs").iterdir() if p.is_dir()):
        for path in run.glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            detail = trial.get("verifier_detail") or {}
            if not detail:
                raw = path.parent / "reward.json"
                if raw.is_file():
                    try:
                        detail = json.loads(raw.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        detail = {}
            if detail.get("f2p") is None:
                continue
            rows.append(
                {
                    "run": run.name,
                    "genome": trial.get("genome_id"),
                    "task": trial["id"].split("/")[-1],
                    "f2p": detail["f2p"],
                    "p2p": detail.get("p2p"),
                    "status": trial["status"],
                    "turns": trial.get("turns"),
                    "exit": trial.get("exit_reason"),
                    "bytes": trial.get("submitted_bytes"),
                    "patch": detail.get("f2p_passed"),
                    "patch_total": detail.get("f2p_total"),
                }
            )

    print(f"{'run':<22}{'genome':<16}{'task':<40}{'f2p':>7}{'p2p':>7}  status")
    for row in sorted(rows, key=lambda r: (r["task"], r["run"])):
        note = f"  {row['patch']}/{row['patch_total']}" if row["patch"] is not None else ""
        print(
            f"{row['run']:<22}{str(row['genome']):<16}{row['task'][:38]:<40}"
            f"{row['f2p']:>7.3f}{(row['p2p'] if row['p2p'] is not None else -1):>7.3f}"
            f"  {row['status']:<8}{note} turns={row['turns']} exit={row['exit']} bytes={row['bytes']}"
        )

    partial = [r for r in rows if r["status"] == "failure" and r["f2p"] > 0]
    print()
    print(f"failures with partial credit: {len(partial)}")
    print(f"of which above 0.9          : {sum(1 for r in partial if r['f2p'] > 0.9)}")
    print(f"of which p2p stayed green   : {sum(1 for r in partial if r['p2p'] == 1.0)}")
    zero = [r for r in rows if r["status"] == "failure" and r["f2p"] == 0]
    print(f"failures with no credit     : {len(zero)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
