# rsih — a recursively self-improving harness for FrontierHarness Eval

**The model is fixed; the harness evolves.** `rsih` runs the published
[FrontierHarness Eval](https://github.com/frontier-harness-eval/eval) task suite with
`DeepSeek-V4.1-Flash`, and improves the *agent harness itself* — its instructions, its
tool surface, its context policy — from measured failures, accepting a change only when
the paired evidence clears a measured noise floor.

It exists because of the benchmark's own headline result: with the model, the tasks and
the runtime held constant, changing only the harness moved pass rate from 50.0% to 66.7%
and median cost per pass from \$1.05 to \$18.34 — a **17.5x cost spread at similar pass
rate**. The harness is not packaging. It is the largest single lever available to someone
who cannot change the model.

```
                ┌──────────────────────────── rsi loop ───────────────────────────┐
                │                                                                  │
   seed genome  │   evaluate on the evolve split ──► analyst reads the failures    │
   (gen0)  ─────┼──►                                            │                   │
                │                                               ▼                   │
                │        gated acceptance  ◄── paired measurement ◄── proposed child│
                │        (z·√(b+c)/n floor)                                            │
                └──────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                            holdout evaluation → report
```

---

## 1. What the system is

| layer | module | what it owns |
| --- | --- | --- |
| model endpoint | `rsih.llm` | OpenAI-compatible calls to `DeepSeek-V4.1-Flash`, measured usage, declared rate card |
| harness | `rsih.agent` | the **genome** (prompt blocks, tool set, loop policy), the tools, the loop |
| benchmark | `rsih.bench` | frozen task loading, Docker sandbox, one-trial execution, scoring |
| self-improvement | `rsih.rsi` | mutation catalogue, failure analyst, noise-floor gate, report |

The dependency direction is one-way: `rsih.agent` never imports `rsih.rsi`. A harness
that could only be run by the loop that improves it could not be measured.

## 2. The four things that are self-modified

RSI here is not a slogan; it is four concrete, separately measured changes.

1. **Instructions** — the genome is an ordered selection of named prompt blocks
   (`verify.self_check`, `method.plan`, `errors.offline`, …). 19 descriptor mutations can
   add or remove them, each carrying an explicit hypothesis about why the agent fails.
2. **Free-text guidance** — the *failure analyst* reads the incumbent's own failed
   transcripts and writes up to two imperative rules into the genome's `extra_prompt`
   slot. This is the open-ended part of the search space; the exact text is stored in the
   ledger next to the measurement it produced.
3. **Tool surface** — `bash` alone versus `bash + read_file + write_file`. A tool has to
   earn its place: a larger schema is paid for on every turn of every task.
4. **Context policy** — step budget, observation truncation, compaction mode, the submit
   guard. These change both pass rate and cost, and they are the only knobs that move cost
   without touching the model.

Every adopted change is a genome with a fingerprint. A result can never be attributed to
a harness that was quietly edited afterwards.

## 3. Why the loop cannot lie to itself

The dominant failure mode of a self-improving system is not failing to learn; it is
**believing it learned**. Three mechanisms prevent that here.

**A change must beat a measured noise floor.** Candidates are evaluated on the *same*
task set as the incumbent, so the comparison is paired. With `b` tasks the child won and
`c` tasks the incumbent won, the floor is

```
floor = z · √(b + c) / n          z = 2
```

and a candidate is adopted only if `diff = (b − c)/n > floor > 0`. A candidate that wins
one task out of twenty is `diff = 0.05`, `floor = 0.10` — rejected, and labelled
`rejected_within_noise`. The ledger distinguishes that from `rejected_worse`, because
"we could not tell" and "it was worse" are different findings.

**Cost wins are held to the same pass rate.** A candidate that cuts measured cost by at
least 15% is adopted at an unchanged pass rate (`accepted_cost`) — but only if it is not
worse beyond the same floor, and only if its cost is *known for every cell*. A harness
cannot become cheap by failing to record its usage.

**The loop never sees the holdout.** The runnable suite is split deterministically by
`sorted(sha256(task_id + seed))`; the loop tunes on one part and the final number is
reported on the other. The split is written to `split.json` beside the run so a reader can
re-derive it.

## 4. Why it is cheap

Cost on this benchmark is not dominated by the size of the model's answers; it is
dominated by how much *transcript* precedes every call.

| decision | effect |
| --- | --- |
| **Append-only transcript.** The message log is never rewritten between turns, so the provider's prefix cache hits on nearly every turn. | measured cache hit ≈ 83% on the first trial; cached input is priced at 10% of fresh input in the declared card |
| **Tiny tool surface.** One general actuator (`bash`) plus two file tools, no shell-substitution guessing. | schema text is paid on every turn |
| **Head/tail observation truncation** with an explicit omitted-character marker. | long logs stop displacing the signal |
| **Compaction only when the context budget is actually approached** (`truncate` or LLM `summarize`, genome-selected). | pays for summarisation only when the alternative is worse |
| **Step budget as a first-class parameter.** | a looping agent is the expensive failure mode |

## 5. Measurement protocol

One trial = one task, one container from the frozen task image, one genome.

1. the container starts from the benchmark's own image at the benchmark's own resource
   envelope (vCPU, memory, timeouts, `PATH`);
2. the agent works through `docker exec` with the script fed on **stdin as bytes** —
   quoting can never mangle a command, and `cd` persists across calls;
3. the verifier's `tests/` directory is copied in **only after the agent stops**, so the
   agent never sees it;
4. the benchmark's own `tests/test.sh` runs and writes `/logs/verifier/reward.txt`;
5. the trial record keeps the reward, the trajectory, the raw verifier log, per-call
   token usage, and the derived first-cold cost.

Nothing about the outcome is inferred. A missing verifier reward is `infra_invalid`, not a
failure; a task whose definition or verifier is not published is `unavailable`, not a
pass and not a zero.

## 6. Honest scope

The frozen suite has 30 tasks: 21 Terminal-Bench and 9 DeepSWE. The DeepSWE verifiers come
from a corpus that is not public, so **9 of 30 tasks cannot be run here and are reported as
unavailable rather than skipped silently**. Every number in this repository is over the
runnable subset, and the report says so.

Two further deviations are recorded in every trial record:

* the container runs on the default Docker bridge network. The task metadata declares
  `allow_internet=false`, but the benchmark's verifiers install `uv` and `pytest` at test
  time, so a network-less container cannot be scored at all. The published run applied a
  runtime-wide allowlist that also admitted verifier package hosts; a local Docker bridge
  is the closest reproducible approximation.
* the model is `DeepSeek-V4.1-Flash`, not the benchmark's Kimi K3. The run is therefore
  **not leaderboard-comparable** by construction — the point is harness efficiency at a
  fixed model, so the report compares token counts (price-independent) and each harness at
  its own model price.

## 7. Reproducing

```bash
# 0. prerequisites: Docker, Python >= 3.11, the two reference checkouts
#    _ref-frontier-eval  (github.com/frontier-harness-eval/eval)
#    _ref-tb2            (github.com/harbor-framework/terminal-bench-2, for tests/)
python -m venv .venv && .venv/bin/pip install -e .[dev]
cp .env.example .env      # then set TIERFLOW_API_KEY

python -m rsih doctor                       # endpoint, checkouts, task availability
python -m rsih tasks                        # what can actually be run
python -m rsih run --run-id smoke --tasks regex-log
python -m rsih evolve --run-id rsi-1 --generations 4 --proposals 3 --concurrency 3
python -m rsih report --run rsi-1 --label "RSIH 0.1"
```

Artifacts land in `runs/<run-id>/`: `ledger.jsonl` (every proposal and its decision),
`genomes/*.json`, `trials/<task>/{trial.json,episode.json,trajectory.jsonl,llm-calls.jsonl,verifier.log,reward.txt}`,
and `report/{REPORT.md,chart.svg,candidate.json}`.

## 8. Results

See [`RESULTS.md`](RESULTS.md) for the measured numbers and the ledger excerpt.
