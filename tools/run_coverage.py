"""Which runs cover which suite cells, under which genome fingerprint.

Before comparing two configurations it has to be established that both were actually run on
the cell in question, and earlier experiments were spread over many run directories with
overlapping coverage.  This prints the coverage grid so a comparison can be assembled from
the runs that really contain the configuration, instead of from the run that happens to be
named after it.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    rows = []
    for run_dir in sorted((ROOT / "runs").iterdir()):
        if not run_dir.is_dir():
            continue
        by_fp: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for path in run_dir.glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if trial["status"] not in ("success", "failure"):
                continue
            suite = trial["id"].split("/")[0]
            by_fp[trial.get("genome_fingerprint") or "?"][suite] += 1
            by_fp[trial.get("genome_fingerprint") or "?"]["pass"] += trial["status"] == "success"
        for fingerprint, counts in by_fp.items():
            rows.append((run_dir.name, fingerprint, dict(counts)))

    print(f"{'run':<34}{'fingerprint':>18}{'tb':>5}{'ds':>5}{'pass':>6}  genomes")
    for run, fingerprint, counts in rows:
        genomes = set()
        for path in (ROOT / "runs" / run).glob("trials/*/trial.json"):
            trial = json.loads(path.read_text(encoding="utf-8"))
            if (trial.get("genome_fingerprint") or "?") == fingerprint:
                genomes.add(trial.get("genome_id"))
        print(
            f"{run:<34}{fingerprint:>18}{counts.get('terminal-bench', 0):>5}"
            f"{counts.get('datacurve', 0):>5}{counts.get('pass', 0):>6}"
            f"  {', '.join(sorted(genomes))}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
