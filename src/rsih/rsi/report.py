"""Normalisation and report.

A run becomes a *candidate* record with the same field names as
``_ref-frontier-eval/results/eval-data.json``, so it can be placed beside the
published baselines without hand-repairing numbers.  The metric definitions follow
the benchmark's own accounting:

* ``pass_rate`` = passes / valid cells
* ``effective_cost_per_pass`` = sum of known first-cold costs / passes
  (failures included, invalid cells with known costs included)
* ``median_cost_per_task`` = median of the per-task first-cold costs
* cache hit rate is token-weighted ``cached / input`` over successes

Nothing is inferred: a metric with incomplete coverage is reported with its
coverage and left ``None`` where the benchmark leaves it null.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from ..llm.pricing import rate_card

CANDIDATE_ORANGE = "#f47b35"
BASELINE_GRAY = "#8b8b8b"


@dataclass
class Candidate:
    label: str
    run_id: str
    genome: dict
    model: str
    expected: int
    valid: int
    passes: int
    infra_invalid: int
    pass_rate: float | None
    success_rate_expected: float | None
    valid_coverage: float
    effective_cost_per_pass: float | None
    effective_cost_coverage: float
    median_cost_per_task: float | None
    cost_coverage: float
    total_cost_usd: float | None
    cache_hit_rate_normalized: float | None
    cache_coverage: float
    mean_turns: float | None
    median_turns: float | None
    mean_input_tokens: float | None
    mean_output_tokens: float | None
    median_duration_seconds: float | None
    task_details: list[dict]
    valid_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _trial_files(run_dir: Path) -> list[dict]:
    trials_dir = run_dir / "trials"
    if not trials_dir.is_dir():
        return []
    records = []
    for path in sorted(trials_dir.glob("*/trial.json")):
        records.append(json.loads(path.read_text(encoding="utf-8")))
    return records


def load_run(run_dir: Path, label: str | None = None) -> Candidate:
    run_dir = Path(run_dir)
    trials = _trial_files(run_dir)
    if not trials:
        raise FileNotFoundError(f"no trials under {run_dir}")
    meta = {}
    run_meta = run_dir / "run.json"
    if run_meta.is_file():
        meta = json.loads(run_meta.read_text(encoding="utf-8"))
    genome = meta.get("genome") or {}

    valid = [t for t in trials if t["status"] in ("success", "failure")]
    passes = [t for t in valid if t["status"] == "success"]
    infra = [t for t in trials if t["status"] == "infra_invalid"]
    known = [t for t in valid if t.get("cost_first_cold_usd") is not None]

    total_cost = sum(t["cost_first_cold_usd"] for t in known) if known else None
    effective = (total_cost / len(passes)) if (passes and total_cost is not None) else None
    median_cost = median([t["cost_first_cold_usd"] for t in known]) if known else None

    success_usage = [
        (t.get("usage") or {}) for t in passes if (t.get("usage") or {}).get("prompt_tokens")
    ]
    total_prompt = sum(u.get("prompt_tokens") or 0 for u in success_usage)
    total_cached = sum(u.get("cached_tokens") or 0 for u in success_usage)
    cache_rate = (total_cached / total_prompt) if total_prompt else None
    cache_coverage = (len(success_usage) / len(passes)) if passes else 0.0

    def mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    task_details = [
        {
            "id": t["id"],
            "title": t["id"].split("/")[-1].replace("-", " "),
            "status": t["status"],
            "success": t["status"] == "success",
            "turns": t.get("turns"),
            "input_tokens": (t.get("usage") or {}).get("prompt_tokens"),
            "output_tokens": (t.get("usage") or {}).get("completion_tokens"),
            "cached_tokens": (t.get("usage") or {}).get("cached_tokens"),
            "cost_first_cold_usd": t.get("cost_first_cold_usd"),
            "duration_seconds": t.get("duration_seconds"),
            "cache_hit_rate_normalized": (
                ((t.get("usage") or {}).get("cached_tokens") or 0)
                / ((t.get("usage") or {}).get("prompt_tokens") or 1)
                if (t.get("usage") or {}).get("prompt_tokens")
                else None
            ),
        }
        for t in trials
    ]

    return Candidate(
        label=label or meta.get("label") or run_dir.name,
        run_id=meta.get("run_id", run_dir.name),
        genome=genome,
        model=meta.get("model", "unknown"),
        expected=len(trials),
        valid=len(valid),
        passes=len(passes),
        infra_invalid=len(infra),
        pass_rate=(len(passes) / len(valid)) if valid else None,
        success_rate_expected=(len(passes) / len(trials)) if trials else None,
        valid_coverage=(len(valid) / len(trials)) if trials else 0.0,
        effective_cost_per_pass=effective,
        effective_cost_coverage=(len(known) / len(trials)) if trials else 0.0,
        median_cost_per_task=median_cost,
        cost_coverage=(len(known) / len(valid)) if valid else 0.0,
        total_cost_usd=total_cost,
        cache_hit_rate_normalized=cache_rate,
        cache_coverage=cache_coverage,
        mean_turns=mean([t.get("turns") or 0 for t in valid]) if valid else None,
        median_turns=median([t.get("turns") or 0 for t in valid]) if valid else None,
        mean_input_tokens=mean([(t.get("usage") or {}).get("prompt_tokens") or 0 for t in valid])
        if valid
        else None,
        mean_output_tokens=mean([(t.get("usage") or {}).get("completion_tokens") or 0 for t in valid])
        if valid
        else None,
        median_duration_seconds=median([t.get("duration_seconds") or 0 for t in valid]) if valid else None,
        task_details=task_details,
        valid_ids=tuple(t["id"] for t in valid),
    )


# --------------------------------------------------------------------- baselines


def load_baselines(eval_repo: Path) -> tuple[dict, list[dict]]:
    data = json.loads((Path(eval_repo) / "results" / "eval-data.json").read_text(encoding="utf-8"))
    baselines = []
    for harness in data["harnesses"]:
        details = {d["id"]: d for d in harness.get("task_details", [])}
        costs = [d["cost_first_cold_usd"] for d in harness.get("task_details", []) if d.get("cost_first_cold_usd") is not None]
        baselines.append(
            {
                "name": harness["name"],
                "pass_rate": harness["pass_rate"],
                "effective_cost_per_pass": harness["effective_cost_per_pass"],
                "median_cost_per_task": median(costs) if costs else None,
                "cache_hit_rate_normalized": harness.get("cache_hit_rate_normalized"),
                "mean_turns": harness.get("mean_turns"),
                "mean_input_tokens": harness.get("mean_input_tokens"),
                "mean_output_tokens": harness.get("mean_output_tokens"),
                "median_duration_seconds": harness.get("median_duration_seconds"),
                "task_details": details,
            }
        )
    return data["overview"], baselines


def subset_overlap(candidate: Candidate, baseline: dict, ids: set[str] | None = None) -> dict:
    """Metrics restricted to the tasks compared like for like.

    Comparing a 21-task candidate against a 30-task baseline aggregate would be a
    category error, so each baseline is recomputed on the shared task ids.  The
    shared set is the candidate's *valid* cells: a task the candidate could not
    score (infra-invalid) must not silently count in someone else's denominator.
    """
    ids = ids if ids is not None else set(candidate.valid_ids)
    details = [d for d in baseline.get("task_details", {}).values() if d["id"] in ids]
    if not details:
        return {"n": 0}
    successes = [d for d in details if d.get("success")]
    costs = [d["cost_first_cold_usd"] for d in details if d.get("cost_first_cold_usd") is not None]
    total = sum(costs) if costs else None
    return {
        "n": len(details),
        "passes": len(successes),
        "pass_rate": len(successes) / len(details),
        "median_cost_per_task": median(costs) if costs else None,
        "effective_cost_per_pass": (total / len(successes)) if (successes and total is not None) else None,
        "cache_hit_rate_normalized": _weighted_cache(details),
        "mean_turns": (sum(d.get("turns") or 0 for d in details) / len(details)) if details else None,
        "mean_input_tokens": (sum(d.get("input_tokens") or 0 for d in details) / len(details)) if details else None,
        "mean_output_tokens": (sum(d.get("output_tokens") or 0 for d in details) / len(details)) if details else None,
    }


def _weighted_cache(details: list[dict]) -> float | None:
    rates = [d["cache_hit_rate_normalized"] for d in details if d.get("cache_hit_rate_normalized") is not None]
    return sum(rates) / len(rates) if rates else None


# ------------------------------------------------------------------------ chart


def _log_scale(value: float, lo: float, hi: float, x0: float, x1: float) -> float:
    value = max(value, lo)
    return x0 + (math.log10(value) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * (x1 - x0)


def chart_svg(candidate: Candidate, baselines: list[dict], path: Path) -> Path:
    width, height = 1040, 520
    left, right, top, bottom = 80, 30, 60, 70
    x0, x1 = left, width - right
    y0, y1 = height - bottom, top
    points = [b for b in baselines if b.get("median_cost_per_task")]
    if candidate.median_cost_per_task:
        points.append(
            {
                "name": candidate.label,
                "median_cost_per_task": candidate.median_cost_per_task,
                "pass_rate": candidate.pass_rate or 0.0,
                "candidate": True,
            }
        )
    if not points:
        raise ValueError("no priced points to plot")
    costs = [p["median_cost_per_task"] for p in points]
    lo = min(min(costs), 0.05)
    hi = max(max(costs), lo * 2)
    lo = 10 ** math.floor(math.log10(lo))
    hi = 10 ** math.ceil(math.log10(hi))

    def px(point: dict) -> tuple[float, float]:
        x = _log_scale(point["median_cost_per_task"], lo, hi, x0, x1)
        y = y1 + (1 - (point.get("pass_rate") or 0)) * (y0 - y1)
        return x, y

    # Pareto frontier (lower cost, higher pass rate is better).
    frontier: list[dict] = []
    for p in sorted(points, key=lambda p: p["median_cost_per_task"]):
        if all(p["pass_rate"] >= q["pass_rate"] for q in points if q["median_cost_per_task"] <= p["median_cost_per_task"]):
            frontier.append(p)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        f'<rect width="{width}" height="{height}" fill="#000"/>',
        '<g font-family="ui-monospace, SFMono-Regular, Menlo, monospace">',
    ]
    for tick in [0.0, 0.25, 0.5, 0.75, 1.0]:
        y = y1 + (1 - tick) * (y0 - y1)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#333" stroke-dasharray="3 5"/>')
        parts.append(f'<text x="{x0 - 12}" y="{y + 4:.1f}" fill="#8b8b8b" font-size="12" text-anchor="end">{tick:.0%}</text>')
    cost_tick = 10 ** math.floor(math.log10(lo))
    ticks = []
    while cost_tick <= hi:
        ticks.append(cost_tick)
        cost_tick *= 5
        ticks.append(cost_tick)
        cost_tick *= 2
    for tick in ticks:
        if tick < lo or tick > hi:
            continue
        x = _log_scale(tick, lo, hi, x0, x1)
        parts.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y1}" stroke="#222"/>')
        label = f"${tick:g}"
        parts.append(f'<text x="{x:.1f}" y="{y0 + 20}" fill="#8b8b8b" font-size="12" text-anchor="middle">{label}</text>')
    parts.append(f'<text x="{(x0 + x1) / 2:.0f}" y="{height - 18}" fill="#d8d8d8" font-size="13" text-anchor="middle">Median cost per task</text>')
    parts.append(f'<text x="18" y="{(y0 + y1) / 2:.0f}" fill="#d8d8d8" font-size="13" text-anchor="middle" transform="rotate(-90 18 {(y0 + y1) / 2:.0f})">Pass rate</text>')

    if len(frontier) > 1:
        coords = " ".join(f"{px(p)[0]:.1f},{px(p)[1]:.1f}" for p in frontier)
        parts.append(f'<polyline points="{coords}" fill="none" stroke="{CANDIDATE_ORANGE}" stroke-width="1.5" stroke-dasharray="6 4" opacity="0.8"/>')

    for point in points:
        x, y = px(point)
        if point.get("candidate"):
            continue
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="none" stroke="{BASELINE_GRAY}" stroke-width="1.6"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y - 12:.1f}" fill="{BASELINE_GRAY}" font-size="11" text-anchor="middle">'
            f'{point["name"]} {point["pass_rate"]:.0%} ${point["median_cost_per_task"]:.2f}</text>'
        )

    star = []
    for index in range(10):
        angle = -math.pi / 2 + index * math.pi / 5
        radius = 15 if index % 2 == 0 else 6
        star.append(f"{math.cos(angle) * radius:.1f},{math.sin(angle) * radius:.1f}")
    for point in points:
        if not point.get("candidate"):
            continue
        x, y = px(point)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="22" fill="none" stroke="{CANDIDATE_ORANGE}" stroke-width="1" opacity="0.55"/>')
        parts.append(
            f'<polygon points="{" ".join(star)}" fill="{CANDIDATE_ORANGE}" transform="translate({x:.1f},{y:.1f})"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y - 30:.1f}" fill="{CANDIDATE_ORANGE}" font-size="13" text-anchor="middle">'
            f'{point["name"]} {point["pass_rate"]:.0%} ${point["median_cost_per_task"]:.2f}</text>'
        )
    parts.append("</g></svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


# ----------------------------------------------------------------------- report


def build_report(run_dir: Path, eval_repo: Path, label: str | None = None) -> dict:
    run_dir = Path(run_dir)
    candidate = load_run(run_dir, label)
    overview, baselines = load_baselines(eval_repo)
    rows = []
    for baseline in baselines:
        overlap = subset_overlap(candidate, baseline, set(candidate.valid_ids))
        rows.append({"name": baseline["name"], "full": baseline, "shared": overlap})
    rows.sort(key=lambda r: (-(r["shared"].get("pass_rate") or 0), r["shared"].get("median_cost_per_task") or 9e9))

    report_dir = run_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "candidate.json").write_text(
        json.dumps(candidate.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    chart_points = [
        {
            "name": row["name"],
            "median_cost_per_task": (row["shared"].get("median_cost_per_task") or 0) or None,
            "pass_rate": row["shared"].get("pass_rate") or 0.0,
        }
        for row in rows
        if row["shared"].get("median_cost_per_task")
    ]
    chart_svg(candidate, chart_points, report_dir / "chart.svg")

    lines = [
        f"# FrontierHarness Eval - {candidate.label}",
        "",
        f"- Model: `{candidate.model}` (not the benchmark's Kimi K3, so the run is **not leaderboard-comparable**)",
        f"- Genome: `{candidate.genome.get('id')}` fingerprint `{candidate.genome.get('fingerprint')}`",
        f"- Task set: {candidate.expected} task(s); {candidate.valid} valid, {candidate.infra_invalid} infra-invalid",
        f"- Pass rate: **{_pct(candidate.pass_rate)}** ({candidate.passes}/{candidate.valid} valid, "
        f"{candidate.passes}/{candidate.expected} expected)",
        f"- Median cost per task: **{_usd(candidate.median_cost_per_task)}** "
        f"(cost coverage {candidate.cost_coverage:.0%})",
        f"- Effective cost per pass: **{_usd(candidate.effective_cost_per_pass)}** "
        f"(coverage {candidate.effective_cost_coverage:.0%})",
        f"- Cache hit rate (token-weighted, successes): **{_pct(candidate.cache_hit_rate_normalized)}** "
        f"(coverage {candidate.cache_coverage:.0%})",
        f"- Mean turns: {_num(candidate.mean_turns)}  Median wall time: {_num(candidate.median_duration_seconds)}s",
        "",
        "## Baselines recomputed on the same task ids",
        "",
        "| Harness | Shared tasks | Pass rate | Median cost/task | Cost per pass | Cache hit |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        f"| **{candidate.label}** | {len(candidate.valid_ids)} | **{_pct(candidate.pass_rate)}** | "
        f"**{_usd(candidate.median_cost_per_task)}** | **{_usd(candidate.effective_cost_per_pass)}** | "
        f"{_pct(candidate.cache_hit_rate_normalized)} |",
    ]
    for row in rows:
        shared = row["shared"]
        lines.append(
            f"| {row['name']} | {shared.get('n')} | {_pct(shared.get('pass_rate'))} | "
            f"{_usd(shared.get('median_cost_per_task'))} | {_usd(shared.get('effective_cost_per_pass'))} | "
            f"{_pct(shared.get('cache_hit_rate_normalized'))} |"
        )
    lines += [
        "",
        "Baseline costs are the published Kimi K3 numbers; the candidate's cost uses the declared "
        "rate card in `pricing.json`. Cost comparisons are therefore between *harnesses at their own "
        "model price*, which is the decision an operator actually faces, and the token columns below "
        "are price-independent.",
        "",
        "## Price-independent comparison (published aggregates)",
        "",
        "Cost mixes two things: how much transcript a harness needs, and what its model "
        "charges per token. These columns isolate the first. Published baselines are over "
        "all 30 frozen tasks; the candidate is over the tasks it could run.",
        "",
        "| Harness | Mean input tokens/task | Mean output tokens/task | Mean turns |",
        "| --- | ---: | ---: | ---: |",
        f"| **{candidate.label}** | {_int(candidate.mean_input_tokens)} | "
        f"{_int(candidate.mean_output_tokens)} | {_num(candidate.mean_turns)} |",
    ]
    for row in rows:
        full = row["full"]
        lines.append(
            f"| {row['name']} | {_int(full.get('mean_input_tokens'))} | "
            f"{_int(full.get('mean_output_tokens'))} | {_num(full.get('mean_turns'))} |"
        )
    lines += [
        "",
        "## Task detail",
        "",
        "| Task | Status | Turns | Cost | Wall time | Cache hit |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for detail in sorted(candidate.task_details, key=lambda d: (d["status"] != "success", d["id"])):
        lines.append(
            f"| {detail['id']} | {detail['status']} | {detail['turns']} | "
            f"{_usd(detail['cost_first_cold_usd'])} | {_num(detail['duration_seconds'])}s | "
            f"{_pct(detail['cache_hit_rate_normalized'])} |"
        )
    lines += [
        "",
        "## Provenance",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Frozen benchmark checkout: `{eval_repo}`",
        "- Verifier: the benchmark's own `tests/test.sh` -> `/logs/verifier/reward.txt`",
        "- Baseline prices: `_ref-frontier-eval/skills/frontierharness-eval/scripts/pricing.json` (kimi-k3-2026-08-20)",
        f"- Candidate price card: {_card_source(candidate.model)}",
        "",
    ]
    (report_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return {
        "candidate": candidate.as_dict(),
        "baselines": rows,
        "report": str(report_dir / "REPORT.md"),
        "chart": str(report_dir / "chart.svg"),
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _usd(value: float | None) -> str:
    return "n/a" if value is None else f"${value:.4f}"


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def _int(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.0f}"


def _card_source(model: str) -> str:
    try:
        return rate_card(model).source
    except KeyError:
        return f"no declared rate card for {model!r}"
