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


#: What a refused connection looks like in a command's observation. Counting an *attempt*
#: would say the isolation failed, because an agent that tries to curl still ran a curl; the
#: question is whether the bytes left the host, and that is answered by the observation.
#:
#: curl's own exit codes are here because `curl -s` prints nothing at all when it fails, so
#: the only evidence in the observation is the code: 5 cannot resolve proxy, 6 cannot resolve
#: host, 7 cannot connect, 28 timed out. An earlier version of this pattern missed them and
#: reported a correctly-isolated episode as one that had reached the network.
BLOCKED = re.compile(
    r"Temporary failure in name resolution|Could not resolve host|Name or service not known|"
    r"Network is unreachable|No route to host|Connection refused|Connection timed out|"
    r"Failed to establish a new connection|gaierror|\[Errno -2\]|\[Errno -3\]|\[Errno 101\]|"
    r"nodename nor servname|exit=(5|6|7|28)\b|http_code\W+000|\b000\b\s*\|?\s*exit=",
    re.I,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", type=int, default=0, help="print N example commands")
    parser.add_argument("--run", default=None, help="restrict to one run directory")
    args = parser.parse_args()

    runs = [ROOT / "runs" / args.run] if args.run else sorted(
        p for p in (ROOT / "runs").iterdir() if p.is_dir()
    )

    episodes = 0
    with_network: list[dict] = []
    by_target: collections.Counter = collections.Counter()
    by_genome: collections.Counter = collections.Counter()
    by_task: collections.Counter = collections.Counter()

    for run in runs:
        for path in run.glob("trials/*/episode.json"):
            try:
                episode = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            episodes += 1
            hits = []
            blocked = 0
            for step in episode.get("steps") or []:
                for call in step.get("tool_calls") or []:
                    command = str((call.get("arguments") or {}).get("command") or "")
                    if command and NETWORK_COMMAND.search(command):
                        hits.append(command)
                        if BLOCKED.search(str(call.get("observation") or "")):
                            blocked += 1
            if not hits:
                continue
            targets = collections.Counter(classify(command) for command in hits)
            label = targets.most_common(1)[0][0]
            by_target.update(targets)
            by_genome[episode.get("genome_id") or "?"] += 1
            by_task[path.parent.name] += 1
            with_network.append(
                {"run": run.name, "task": path.parent.name, "hits": hits, "label": label,
                 "blocked": blocked}
            )

    refused = [e for e in with_network if e["blocked"] == len(e["hits"])]
    print(f"episodes scanned                          : {episodes}")
    print(f"episodes that tried a network command     : {len(with_network)}"
          f"  ({100.0 * len(with_network) / max(1, episodes):.1f}%)")
    print()
    print("Of those commands, what the observation shows:")
    print(f"  explicit refusal (DNS/route/curl code)  : {sum(e['blocked'] for e in with_network)} commands")
    print(f"  episodes where every command refused    : {len(refused)}")
    print()
    print("A caveat this tool cannot resolve on its own: `curl -s` prints nothing at all when")
    print("it fails, so an episode whose only network command was a silent curl leaves no")
    print("evidence either way. Those are counted as attempts, not as successes. The direct")
    print("evidence that the agent phase has no route is tools/network_probe.py, which opens a")
    print("socket and reports what actually happened.")
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
