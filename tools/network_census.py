"""How many episodes reached the network, and what did they go and fetch?

The two-phase network policy only matters if episodes were actually using the route.  This
scans every stored episode for commands that can leave the host, and classifies what they
were pointed at -- the important distinction being an upstream fix commit or the benchmark's
own hidden tests, versus an ordinary package install.

Counts are per episode, over every run kept in the repository, so this is a census rather
than a single comparison.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NETWORK_COMMAND = re.compile(
    r"\b(curl|wget|git\s+clone|git\s+fetch|git\s+remote\s+add|pip\s+install|pip3\s+install|"
    r"npm\s+(install|i|ci)|yarn\s+add|pnpm\s+(add|install)|uv\s+pip\s+install|apt-get\s+install)\b"
)

#: Where the bytes were pointed.  Ordered: the first match wins.
TARGETS = (
    ("hidden tests", re.compile(r"datacurve|deep-swe|deep_swe|test\.patch|gold\.patch|solution\.patch", re.I)),
    ("upstream fix / history", re.compile(
        r"github\.com|raw\.githubusercontent\.com|codeload\.github|gitlab\.com|bitbucket\.org", re.I)),
    ("another team's results", re.compile(r"results|leaderboard|eval-", re.I)),
    ("package install", re.compile(
        r"pypi|pypi\.org|files\.pythonhosted|registry\.npmjs|npmjs\.org|nodejs\.org|"
        r"crates\.io|apt|deb\.debian|archive\.ubuntu", re.I)),
)


def classify(command: str) -> str:
    for label, pattern in TARGETS:
        if pattern.search(command):
            return label
    return "unclassified network use"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", type=int, default=0, help="print N example commands")
    args = parser.parse_args()

    episodes = 0
    with_network: list[dict] = []
    by_target: collections.Counter = collections.Counter()
    by_genome: collections.Counter = collections.Counter()
    by_task: collections.Counter = collections.Counter()

    for run in sorted(p for p in (ROOT / "runs").iterdir() if p.is_dir()):
        for path in run.glob("trials/*/episode.json"):
            try:
                episode = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            episodes += 1
            hits = []
            for step in episode.get("steps") or []:
                for call in step.get("tool_calls") or []:
                    command = str((call.get("arguments") or {}).get("command") or "")
                    if command and NETWORK_COMMAND.search(command):
                        hits.append(command)
            if not hits:
                continue
            targets = collections.Counter(classify(command) for command in hits)
            label = targets.most_common(1)[0][0]
            by_target.update(targets)
            by_genome[episode.get("genome_id") or "?"] += 1
            by_task[path.parent.name] += 1
            with_network.append({"run": run.name, "task": path.parent.name, "hits": hits, "label": label})

    print(f"episodes scanned                          : {episodes}")
    print(f"episodes that ran a network command       : {len(with_network)}"
          f"  ({100.0 * len(with_network) / max(1, episodes):.1f}%)")
    print()
    if with_network:
        print(f"{'what it was aimed at':<28} {'episodes':>9}  commands")
        for label, count in by_target.most_common():
            episodes_for = sum(1 for e in with_network if e["label"] == label)
            print(f"{label:<28} {episodes_for:>9}  {count}")
        print()
        print("cells that did it (top 15):")
        for task, count in by_task.most_common(15):
            print(f"  {task:<50} {count} episode(s)")
        print()
        print("by genome:")
        for genome, count in by_genome.most_common(10):
            print(f"  {genome:<20} {count} episode(s)")
    else:
        print("No stored episode ran a network command.")

    if args.examples:
        print()
        for entry in with_network[: args.examples]:
            print(f"[{entry['run']} / {entry['task']}] {entry['label']}")
            for command in entry["hits"][:3]:
                print(f"    {command[:180]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
