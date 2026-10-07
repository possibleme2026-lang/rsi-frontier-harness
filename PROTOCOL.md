# Measurement protocol

Every number in `RESULTS.md` comes from one of the commands below, run from
`rsi-frontier-harness/` with the pinned interpreter.

```powershell
$py = "D:\codebase\agentharness\.venv-rsi\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"
```

## 0. Preconditions

```powershell
& $py -m rsih doctor          # endpoint key, task coverage, model ping
& $py -m pytest tests -q      # unit tests: genome, gate arithmetic, report, tasks
& $py tools/pull_images.py    # 21 terminal-bench images
& $py tools/pull_deepswe.py --family datacurve   # 9 swE-bench-202605 images
& $py tools/audit_verifiers.py                   # verifier contract per task
```

`doctor` must report `30 / 30` runnable tasks before any suite number is quoted.

## 1. Baseline sweep (a genome, no evolution)

```powershell
& $py -m rsih run --run-id gen0-probe --genome gen0 --concurrency 3
& $py -m rsih report --run gen0-probe-g0-gen0 --label "RSIH gen0"
```

`run_trials` writes `runs/<run-id>-<genome>-<tag>/`; `report` adds `report/REPORT.md`
plus `report/chart.svg`. Every trial directory keeps its own `episode.json`,
`llm-calls.jsonl`, `trajectory.jsonl`, `verifier.log` and `reward.*`, so a reported
number can always be walked back to the container output that produced it.

## 2. Evolution run

```powershell
& $py -m rsih evolve --run-id rsi-r2 --genome gen1 `
    --generations 2 --proposals 1 --concurrency 2 `
    --tasks largest-eigenval,kv-store-grpc,log-summary-date-ranges,vulnerable-secret,modernize-scientific-stack,merge-diff-arc-agi-task
```

The run directory holds `ledger.json` (one entry per proposal: hypothesis, per-task
results, gate verdict, cost) and `genomes/` for every genome actually evaluated.
A run is only quotable if no ledger entry was retried for an `infra_invalid` reason
that was not resolved.

## 3. Holdout

Holdout tasks are never shown to the analyst and never used for acceptance:

```powershell
& $py -m rsih run --run-id holdout-seed  --genome gen1   --concurrency 2 --tasks extract-elf,db-wal-recovery,constraints-scheduling,sqlite-db-truncate,gcode-to-text,chess-best-move,regex-log
& $py -m rsih run --run-id holdout-final --genome <winner> --concurrency 2 --tasks extract-elf,db-wal-recovery,constraints-scheduling,sqlite-db-truncate,gcode-to-text,chess-best-move,regex-log
& $py -m rsih report --run holdout-final-<...> --label "holdout winner"
```

The holdout verdict is the only pass-rate comparison that can support a claim about
self-improvement, because the seed was selected on the evolve set.

## 4. Full-suite runs and the step budget

The step cap is a genome field, and the harness can instead take its step budget from
the envelope each task publishes. `steps_from_declared_budget` with
`step_budget_reference_s = R` gives a task declaring `D` seconds
`max_steps * clamp(D / R, 1, 4)` steps. `R = 1800` (the default) is the largest budget
any terminal-bench task declares, so it leaves that half byte-for-byte unchanged;
`R = 600` gives the 900 s tasks 90 steps, the 1200 s tasks 120, the 1800 s task 180 and
the 5400 s DeepSWE tasks the 4× ceiling.

```powershell
# a whole-suite number on one genome, with every task at its own declared budget
$env:RSIH_AGENT_TIMEOUT_CAP = "2100"
& $py -m rsih run --run-id gen4-full --genome gen4 --concurrency 3
& $py tools/coverage.py runs/gen4-full --label "RSIH gen4"
& $py tools/cost_rollup.py runs/gen4-full
```

`tools/task_stability.py <task>` prints every trial recorded for one task across runs,
which is how a pass that does not reproduce gets found rather than averaged away.

## 5. Cost anatomy

```powershell
& $py tools/cost_anatomy.py runs/gen0-probe-g0-gen0
& $py tools/baseline_family.py all
& $py tools/baseline_matrix.py --run runs/gen0-probe-g0-gen0
& $py tools/deepswe_table.py runs/deepswe-9
& $py tools/published_provenance.py     # what the baseline file actually contains
```

## 5b. What was measured here and what was not

Only the `rsih` rows in any table are measurements from this repository. The published
harness rows are read from `_ref-frontier-eval/results/eval-data.json`, which is the
benchmark authors' own result file: they ran Kimi K3 through twelve configurations on a
Runta runtime, and the configurations themselves are not part of the clone ("internal
infrastructure, credentials, runtime identifiers, private evidence, solutions, and
deployment configuration are not included"). They were **not re-run here and cannot be**.
`tools/published_provenance.py` prints the file's `generated_at`, its model field and its
per-harness cell/pass/cost totals so the provenance can be checked rather than trusted.

## 6. Rate limits

The endpoint rate-limits per client IP. Two rules keep that from becoming a result:

- `RSIH_MAX_INFLIGHT` (default 2) and `RSIH_REQUEST_INTERVAL` (default 0.5 s) are
  enforced process-wide, so concurrency in the runner buys container parallelism, not
  a faster path to a 429.
- An episode that ends in `model_error` is recorded as `infra_invalid` and retried by
  `run_trials`, never scored. `runs/_discarded-*` hold runs from before that rule
  existed and are not quoted anywhere.

## 7. Known deviations from the published run

Kept in one place, because each of them changes what a number means:

1. terminal-bench verifiers come from `terminal-bench-2` main, not the gated 2.1 tag.
2. Containers run on the default Docker bridge, so a verifier may reach package hosts;
   the published run applied a runtime-wide allowlist. `kv-store-grpc` depends on this.
3. No `--storage-opt` quota.
4. The 3 h DeepSWE agent budget is capped locally (`RSIH_AGENT_TIMEOUT_CAP`, recorded
   per trial), so long-horizon numbers are a lower bound. The per-trial record
   distinguishes the declared budget from the capped one.
5. DeepSWE's explicit submit step is replaced by the harness auto-committing the tree.
6. The model is DeepSeek-V4.1-Flash at the declared rate card, not the baselines'
   Kimi K3, so cost-per-pass is a cross-price comparison and is labelled as such.
7. Which step budget a genome uses is a design choice, not a property of the eval, so
   every result states the genome's policy rather than assuming one. A run with
   `max_steps = 60` and no policy is the strictest configuration measured here.
