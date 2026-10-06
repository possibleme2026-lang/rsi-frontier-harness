"""Command line entry point.

``python -m rsih <command>`` (or the ``rsih`` console script).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .agent.genome import GenomeLibrary, default_genome
from .bench.runner import TrialRunner, run_trials
from .bench.sandbox import DockerSandbox
from .bench.tasks import available_tasks, load_tasks
from .config import PROJECT_ROOT, settings


def _cmd_doctor(args: argparse.Namespace) -> int:
    cfg = settings()
    print("rsih doctor")
    print(f"  project root      : {PROJECT_ROOT}")
    print(f"  workspace         : {cfg.workspace}")
    print(f"  eval repo         : {cfg.eval_repo} ({'ok' if cfg.eval_repo.is_dir() else 'MISSING'})")
    print(f"  terminal-bench-2  : {cfg.tb2_repo} ({'ok' if cfg.tb2_repo.is_dir() else 'MISSING'})")
    print(f"  runs dir          : {cfg.runs_dir}")
    print(f"  base url          : {cfg.base_url}")
    print(f"  model             : {cfg.model}")
    key = cfg.api_key
    print(f"  api key           : {'present (' + key[:6] + '...' + key[-4:] + ')' if key else 'MISSING'}")
    ready, blocked = available_tasks(cfg)
    print(f"  tasks runnable    : {len(ready)} / {len(ready) + len(blocked)}")
    for task in blocked[:5]:
        print(f"    - {task.id}: {task.unavailable_reason}")
    try:
        from .llm.client import client_from_env

        client = client_from_env()
        response = client.complete(
            [{"role": "user", "content": "Reply with the single word: ready"}],
            max_tokens=512,
            label="doctor",
        )
        print(f"  model ping        : ok ({(response.content or '').strip()[:40]!r})")
        print(f"  usage             : {response.usage.as_dict()}")
    except Exception as exc:  # noqa: BLE001
        print(f"  model ping        : FAILED {type(exc).__name__}: {exc}")
        return 1
    return 0


def _cmd_tasks(args: argparse.Namespace) -> int:
    cfg = settings()
    ready, blocked = available_tasks(cfg)
    print(f"{len(ready)} runnable task(s), {len(blocked)} unavailable")
    for task in load_tasks(cfg):
        flag = "ok " if task.available else "no "
        print(
            f"  {flag} {task.id:<48} image={task.docker_image:<52} "
            f"cpus={task.cpus:g} mem={task.memory_mb} net={task.allow_internet}"
        )
        if not task.available:
            print(f"      reason: {task.unavailable_reason}")
    return 0


def _load_genome(genome_id: str):
    library = GenomeLibrary(PROJECT_ROOT / "genomes")
    if genome_id == "gen0" and not library.path_for("gen0").is_file():
        genome = default_genome()
        library.save(genome)
        return genome
    try:
        return library.load(genome_id)
    except FileNotFoundError:
        genome = default_genome(genome_id)
        library.save(genome)
        return genome


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = settings()
    genome = _load_genome(args.genome)
    ids = [t.strip() for t in args.tasks.split(",")] if args.tasks else None
    tasks = load_tasks(cfg, ids)
    runnable = [t for t in tasks if t.available]
    skipped = [t for t in tasks if not t.available]
    for task in skipped:
        print(f"skip {task.id}: {task.unavailable_reason}")
    if not runnable:
        print("nothing to run")
        return 1
    print(f"run {args.run_id}: {len(runnable)} task(s), genome={genome.id} ({genome.fingerprint()})")
    started = time.time()

    def report(result):
        mark = {"success": "PASS", "failure": "FAIL", "infra_invalid": "INV "}[result.status]
        cost = f"${result.cost_usd:.4f}" if result.cost_usd is not None else "$?"
        print(
            f"  [{mark}] {result.task_id:<46} turns={result.turns:<3} "
            f"{result.duration_s:6.1f}s cost={cost} exit={result.exit_reason}"
        )

    results, run_dir = run_trials(
        runnable,
        genome,
        run_id=args.run_id,
        settings=cfg,
        network=args.network,
        keep_container=args.keep_container,
        on_result=report,
    )
    passed = sum(1 for r in results if r.status == "success")
    valid = sum(1 for r in results if r.status in ("success", "failure"))
    cost = sum(r.cost_usd or 0 for r in results)
    print(
        f"\npass {passed}/{valid} valid ({passed}/{len(results)} expected) in "
        f"{time.time() - started:.0f}s, measured cost ${cost:.4f}"
    )
    print(f"artifacts: {run_dir}")
    return 0


def _cmd_shell(args: argparse.Namespace) -> int:
    """Interactive one-shot: run a command inside a fresh task container."""
    cfg = settings()
    tasks = {t.name: t for t in load_tasks(cfg, [args.task])}
    task = tasks[args.task]
    sandbox = DockerSandbox(task, name=f"rsih-shell-{task.name}"[:60], network=args.network)
    sandbox.start()
    try:
        result = sandbox.exec_script(args.command or "pwd; ls -la", timeout_s=300)
        print(result.output)
        print(f"[exit {result.exit_code} in {result.duration_s:.1f}s]")
    finally:
        if not args.keep_container:
            sandbox.remove()
    return 0


def _cmd_evolve(args: argparse.Namespace) -> int:
    from .rsi.evolve import EvolutionConfig, EvolutionLoop, mutation_catalogue, split_tasks

    cfg = settings()
    ready, blocked = available_tasks(cfg)
    if args.tasks:
        tasks = load_tasks(cfg, [t.strip() for t in args.tasks.split(",")])
        tasks = [t for t in tasks if t.available]
        holdout: list = []
    else:
        tasks, holdout = split_tasks(ready, holdout=args.holdout)
    print(f"evolve set ({len(tasks)}): {[t.short for t in tasks]}")
    if holdout:
        print(f"holdout set ({len(holdout)}, never shown to the loop): {[t.short for t in holdout]}")
        (cfg.runs_dir / args.run_id).mkdir(parents=True, exist_ok=True)
        (cfg.runs_dir / args.run_id / "split.json").write_text(
            json.dumps(
                {"evolve": [t.id for t in tasks], "holdout": [t.id for t in holdout]}, indent=2
            ),
            encoding="utf-8",
        )
    if args.catalogue:
        print(json.dumps(mutation_catalogue(), indent=2))
        return 0
    config = EvolutionConfig(
        generations=args.generations,
        proposals_per_generation=args.proposals,
        concurrency=args.concurrency,
        seed=args.seed,
        analyst_tasks=args.analyst_tasks,
    )
    genome = _load_genome(args.genome)
    loop = EvolutionLoop(tasks, settings=cfg, config=config, seed_genome=genome, root_name=args.run_id)
    summary = loop.run()
    print(json.dumps(summary["incumbent_summary"], indent=2))
    print(f"ledger: {summary['ledger']}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from .rsi.report import build_report

    cfg = settings()
    run_dir = Path(args.run)
    if not run_dir.is_dir():
        run_dir = cfg.runs_dir / args.run
    result = build_report(run_dir, cfg.eval_repo, label=args.label)
    candidate = result["candidate"]
    print(
        f"{candidate['label']}: pass {candidate['passes']}/{candidate['valid']} "
        f"median cost/task {candidate['median_cost_per_task']} "
        f"cost/pass {candidate['effective_cost_per_pass']}"
    )
    print(f"report: {result['report']}")
    print(f"chart : {result['chart']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rsih", description="RSI self-evolving harness")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check endpoint, paths and task availability")
    doctor.set_defaults(func=_cmd_doctor)

    tasks_cmd = sub.add_parser("tasks", help="list tasks and their runnability")
    tasks_cmd.set_defaults(func=_cmd_tasks)

    run = sub.add_parser("run", help="run trials for a genome")
    run.add_argument("--run-id", required=True)
    run.add_argument("--tasks", default=None, help="comma-separated task ids")
    run.add_argument("--genome", default="gen0")
    run.add_argument("--network", default="bridge")
    run.add_argument("--keep-container", action="store_true")
    run.set_defaults(func=_cmd_run)

    shell = sub.add_parser("shell", help="open a task container and run one command")
    shell.add_argument("--task", required=True)
    shell.add_argument("--command", default=None)
    shell.add_argument("--network", default="bridge")
    shell.add_argument("--keep-container", action="store_true")
    shell.set_defaults(func=_cmd_shell)

    evolve = sub.add_parser("evolve", help="run the self-improvement loop")
    evolve.add_argument("--run-id", required=True)
    evolve.add_argument("--generations", type=int, default=4)
    evolve.add_argument("--proposals", type=int, default=3)
    evolve.add_argument("--concurrency", type=int, default=3)
    evolve.add_argument("--holdout", type=float, default=0.35)
    evolve.add_argument("--seed", type=int, default=7)
    evolve.add_argument("--analyst-tasks", type=int, default=5)
    evolve.add_argument("--genome", default="gen0")
    evolve.add_argument("--tasks", default=None, help="explicit evolve set; skips the split")
    evolve.add_argument("--catalogue", action="store_true", help="print the mutation catalogue and exit")
    evolve.set_defaults(func=_cmd_evolve)

    report = sub.add_parser("report", help="normalise a run and build the report")
    report.add_argument("--run", required=True, help="run id under runs/ or a path")
    report.add_argument("--label", default=None)
    report.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
