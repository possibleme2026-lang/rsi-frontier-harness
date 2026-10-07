"""Cost, tokens and time for a run, alongside another run's, cell by cell.

The pass count is one axis and the graded fraction is another; money and wall clock are
the third, and a change that wins a cell by tripling deliberation has not obviously won.
This prints all of them for two runs of the same cells so the tradeoff is visible rather
than buried in a total.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(run: str) -> dict[str, dict]:
    cells: dict[str, dict] = {}
    for path in sorted((ROOT / run).glob("trials/*/trial.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        detail = payload.get("verifier_detail") or {}
        if not detail:
            raw = path.parent / "reward.json"
            if raw.is_file():
                try:
                    detail = json.loads(raw.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    detail = {}
        payload["_detail"] = detail
        cells[payload["id"]] = payload
    return cells


def credit(cell: dict) -> float:
    if cell["status"] == "success":
        return 1.0
    if cell["status"] != "failure":
        return 0.0
    detail = cell["_detail"]
    f2p, p2p = detail.get("f2p"), detail.get("p2p")
    if f2p is None:
        return 0.0
    return min(0.99, max(0.0, float(f2p)) * (1.0 if p2p is None else max(0.0, min(1.0, float(p2p)))))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left")
    parser.add_argument("right")
    args = parser.parse_args()

    left, right = load(args.left), load(args.right)
    shared = sorted(set(left) & set(right))
    if not shared:
        print("no shared cells")
        return 1

    print(f"{'task':<42}{'credit':>16}{'cost':>18}{'completion':>20}{'minutes':>14}")
    totals = {k: [0.0] * 4 for k in ("l", "r")}
    for task in shared:
        a, b = left[task], right[task]
        la, lb = credit(a), credit(b)
        ca = (a.get("cost_usd") or 0.0)
        cb = (b.get("cost_usd") or 0.0)
        ta = (a.get("usage") or {}).get("completion_tokens") or 0
        tb = (b.get("usage") or {}).get("completion_tokens") or 0
        ma, mb = (a.get("duration_seconds") or 0.0) / 60, (b.get("duration_seconds") or 0.0) / 60
        print(
            f"{task.split('/')[-1][:40]:<42}"
            f"{la:>7.2f} ->{lb:>6.2f}"
            f"{ca:>7.3f} ->{cb:>6.3f}"
            f"{ta:>8} ->{tb:>7}"
            f"{ma:>6.1f} ->{mb:>5.1f}"
        )
        for index, value in enumerate((la, ca, ta, ma)):
            totals["l"][index] += value
        for index, value in enumerate((lb, cb, tb, mb)):
            totals["r"][index] += value

    print()
    print(f"{'TOTAL':<42}"
          f"{totals['l'][0]:>7.2f} ->{totals['r'][0]:>6.2f}"
          f"{totals['l'][1]:>7.3f} ->{totals['r'][1]:>6.3f}"
          f"{totals['l'][2]:>8.0f} ->{totals['r'][2]:>7.0f}"
          f"{totals['l'][3]:>6.1f} ->{totals['r'][3]:>5.1f}")
    lc, rc = totals["l"][0], totals["r"][0]
    print()
    print(f"credit              {lc:.3f} -> {rc:.3f}  ({rc - lc:+.3f})")
    print(f"spend               ${totals['l'][1]:.4f} -> ${totals['r'][1]:.4f}  "
          f"({totals['r'][1] / totals['l'][1] - 1:+.1%})")
    print(f"completion tokens   {totals['l'][2]:.0f} -> {totals['r'][2]:.0f}  "
          f"({totals['r'][2] / totals['l'][2] - 1:+.1%})")
    print(f"agent minutes       {totals['l'][3]:.1f} -> {totals['r'][3]:.1f}  "
          f"({totals['r'][3] / totals['l'][3] - 1:+.1%})")
    if rc:
        print(f"credit per dollar   {lc / totals['l'][1]:.2f} -> {rc / totals['r'][1]:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
