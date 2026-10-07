"""Ask the endpoint whether it can be told to think less.

Reasoning is 79% of completion tokens here and completion is 48% of spend, so this is the
largest single cost and latency lever in the whole system.  The earlier `max_output_tokens`
experiment failed because that cap truncates the tool call along with the thought; a
*reasoning effort* knob would be the surgical version of the same idea.

Provider-specific knobs are not discoverable from the API surface, so this probes the
usual spellings and reports what actually changed in the usage payload.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsih.llm.client import LLMClient  # noqa: E402

VARIANTS: list[tuple[str, dict | None]] = [
    ("baseline (nothing extra)", None),
    ('reasoning_effort="low"', {"reasoning_effort": "low"}),
    ('reasoning_effort="high"', {"reasoning_effort": "high"}),
    ('thinking={"type":"disabled"}', {"thinking": {"type": "disabled"}}),
    ("enable_thinking=False", {"enable_thinking": False}),
    ('reasoning={"effort":"low"}', {"reasoning": {"effort": "low"}}),
]

PROMPT = (
    "You are fixing a bug in a Python library. The function `parse_duration(text)` should "
    "accept strings like '1h30m', '90s', '2d3h', and must raise ValueError on anything else. "
    "A user reports that '1h30' is accepted and returns 5400 seconds, but it should be "
    "rejected. Before touching any file, work out exactly which branch of the parser lets a "
    "trailing number without a unit through, and state the minimal change. Then call the "
    "bash tool with: ls -la /tmp"
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    }
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reps", type=int, default=1)
    args = parser.parse_args()

    client = LLMClient()
    rows = []
    for label, extra in VARIANTS:
        for rep in range(args.reps):
            started = time.perf_counter()
            try:
                reply = client.complete(
                    [{"role": "user", "content": PROMPT}],
                    tools=TOOLS,
                    extra_body=extra,
                )
            except Exception as exc:  # noqa: BLE001 - the point is to report what broke
                rows.append((label, rep, None, None, None, None, f"{type(exc).__name__}: {exc}"))
                print(f"{label:<28} rep{rep}  ERROR {type(exc).__name__}: {str(exc)[:90]}")
                continue
            latency = time.perf_counter() - started
            usage = reply.usage
            rows.append(
                (
                    label,
                    rep,
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.reasoning_tokens,
                    latency,
                    f"tool_calls={len(reply.tool_calls)}",
                )
            )
            print(
                f"{label:<28} rep{rep}  prompt={usage.prompt_tokens:>6}  "
                f"completion={usage.completion_tokens:>6}  reasoning={usage.reasoning_tokens:>6}  "
                f"{latency:>6.1f}s  tool_calls={len(reply.tool_calls)}"
            )

    print("\nsummary")
    for label, _, _ in [(v[0], None, None) for v in VARIANTS]:
        group = [r for r in rows if r[0] == label]
        ok = [r for r in group if r[2] is not None]
        if not ok:
            print(f"  {label:<28} all attempts failed")
            continue
        reasoning = [r[4] or 0 for r in ok]
        completion = [r[3] or 0 for r in ok]
        latency = [r[5] for r in ok]
        print(
            f"  {label:<28} reasoning={sum(reasoning) // len(ok):>6}  "
            f"completion={sum(completion) // len(ok):>6}  "
            f"latency={sum(latency) / len(ok):>5.1f}s  n={len(ok)}"
        )
    out = ROOT / "assets" / "reasoning-probe.json"
    out.write_text(
        json.dumps([{"variant": r[0], "rep": r[1], "prompt_tokens": r[2],
                     "completion_tokens": r[3], "reasoning_tokens": r[4],
                     "latency_s": r[5], "note": r[6]} for r in rows], indent=2),
        encoding="utf-8",
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

