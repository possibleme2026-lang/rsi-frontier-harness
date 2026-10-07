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

**Measured result** ([`RESULTS.md`](RESULTS.md), all 30 frozen tasks, commands in
[`PROTOCOL.md`](PROTOCOL.md)):

| | rsih `gen1` | codex | pi-responses | exo | suite aggregate |
| --- | ---: | ---: | ---: | ---: | ---: |
| pass rate | **60.0%** (18/30) | 66.7% | 60.0% | 53.3% | 58.1% |
| spend on all 30 tasks | **$1.77** | $69.37 | $43.79 | $16.72 | — |
| effective cost per pass | **$0.098** | $3.468 | $2.433 | $1.045 | $1.220 |
| token-weighted cache hit rate | **96.0%** | 63.8% | — | — | 92.4% |

Same pass rate as the best published harnesses at **1/25th the cost per solved task**, and
inside the published band rather than above it — the claim is the efficiency frontier, not
a higher score. The self-improvement loop's one measured change and the holdout that
overruled it are in §6 of `RESULTS.md`; the parts of that story that are negative are
reported with the same prominence as the parts that are not.

Three later configurations were built specifically to close the four-task gap to `codex`
by giving the agent more of the budget each task actually declares — 64 extra cell-runs
in total. All three scored at or below the 60-step harness, and the one that matched its
18/30 did so for **20% more money** ($2.12 vs $1.77). §2.1 of `RESULTS.md` has the
per-call records that explain why: unbounded deliberation eats the wall clock, and
bounding it per response truncates the tool calls away. That negative result is why the
number above is quoted for the configuration it was measured on.

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

**Cost wins are held to the same pass rate *and* the same floor.** A candidate that cuts
measured cost by at least 15% is adopted at an unchanged pass rate (`accepted_cost`) —
but only if it is not worse beyond the same floor, only if its cost is *known for every
cell*, and only if the paired per-task spend difference clears `z` standard errors of
itself. A harness cannot become cheap by failing to record its usage, and it cannot
become cheap by getting lucky on the one expensive task: that second rule was added
after a measured run showed the point-ratio version adopting a change the holdout
reproduced at half the size. [`RESULTS.md`](RESULTS.md) §6 has the numbers, and
`tools/replay_gate.py` re-decides an old ledger under the new rule from its own trials.

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

The frozen suite has 30 tasks and two corpus families, and they do not share a
verification protocol:

| family | tasks | verifier |
| --- | ---: | --- |
| `terminal-bench/*` | 21 | `tests/` copied into the agent's container after the agent stops |
| `datacurve/*` (DeepSWE) | 9 | the agent's diff is collected as a patch and graded in a **separate, pristine** container |

The Terminal-Bench verifiers are not published with the eval; they come from the public
`terminal-bench-2` checkout. The DeepSWE corpus is public
([`datacurve-ai/deep-swe`](https://github.com/datacurve-ai/deep-swe)) and its nine eval
tasks are run from it directly. Nothing is guessed at: a task whose definition or
verifier is absent is loaded as `unavailable` and reported as such, never as a pass
and never as a zero.

Deviations, recorded in every trial record:

* **Tests come from the main branch of `terminal-bench-2`, not the gated
  `terminal-bench-2-1` artifact.** The verifiers are the published ones for these task
  names; where a task's verifier differs between the two, this run used the available one.
* **Containers run on the default Docker bridge network.** Every task metadata declares
  `no-network`, but the Terminal-Bench verifiers install `uv`/`pytest` at test time, and
  the DeepSWE grader needs its test runner, so a network-less container cannot be scored
  at all. Published runs applied a runtime-wide allowlist that also admitted package
  hosts; a local bridge is the closest reproducible approximation. An agent container is
  therefore *less* constrained than the published protocol, which is disclosed wherever
  it could matter (for example `kv-store-grpc` needs `pip install grpcio`).
* **A verifier that fails to set itself up is not scored as a task failure.** Mirror
  502s and DNS failures happen; when the verifier's own install fails before any test
  runs, the cell is `infra_invalid` and is retried, not counted as a zero.
* **DeepSWE's 3-hour agent budget is capped** (`RSIH_AGENT_TIMEOUT_CAP`, default 40
  minutes) and the cap is recorded per trial, because the comparison is on cost per pass
  and a 9-task budget of 27 hours is not a harness anyone can use.
* **DeepSWE grading needs a commit.** The task's collect hook is `git diff <base> HEAD`,
  so the runner commits a dirty tree after the agent stops, standing in for the
  submit step the benchmark's own runtime performs.
* **The model is `DeepSeek-V4.1-Flash`, not the benchmark's Kimi K3.** The run is
  therefore **not leaderboard-comparable** by construction — the point is harness
  efficiency at a fixed model, so the report compares token counts (price-independent)
  and every harness at its own model price.

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

## 8. The genome, in full

A genome is a frozen dataclass. Its fingerprint is the sha256 of its JSON, so two
harnesses with the same behaviour have the same name and two with different behaviour
never share one.

| field | default | what a mutation can do to it |
| --- | --- | --- |
| `blocks` | `role.engineer, method.loop, tools.bash, errors.recover, budget.brevity, submit.contract` | add/remove named instruction blocks |
| `tools` | `bash, read_file, write_file, submit` | shrink or grow the tool schema |
| `max_steps` | 60 | ±20 |
| `steps_from_declared_budget` | `false` | take the step budget from the task's declared envelope |
| `step_budget_reference_s` | 1800 | the declared budget `max_steps` is exactly enough for |
| `obs_head_chars` / `obs_tail_chars` | 4000 / 3000 | ±2000 |
| `temperature` | 0.0 | 0.2 |
| `context_budget_tokens` | 96000 | — |
| `compaction` | `truncate` | `summarize`, `none` |
| `keep_recent_tool_results` | 12 | +8 |
| `nudge_text_only` | 2 | 0 |
| `bash_timeout_s` | 240 | — |
| `submit_guard` | `none` | `one_shot_reject` |
| `max_output_tokens` | 0 (provider default) | 4096, 2048 |
| `extra_prompt` | `""` | free text written by the failure analyst |

22 descriptor mutations are available, grouped by the component they touch: prompt blocks
(8), tools (2), loop parameters (11), and the analyst's free-text patch, which is not a
descriptor mutation and is always tried alongside one. Each mutation carries the
hypothesis it tests, and every proposal is logged with that hypothesis next to its
measured outcome.

The two step-budget fields are the one place the harness takes a budget from the task
rather than from a constant: with the policy on, a task declaring `D` seconds gets
`max_steps * clamp(D / step_budget_reference_s, 1, 4)` steps. Its default reference is
the largest declared budget in the terminal-bench half, which makes the policy *inert
there by construction* — that is a property the test suite pins, because a result
measured with the policy off has to carry over to a run with it on. `RESULTS.md` §2.1
reports what happened when the reference was lowered: the extra budget made the harness
worse, for reasons that are visible in the per-call records.

## 9. Failure taxonomy

Not every zero is a result. The runner classifies each cell before it reaches a metric:

| verdict | meaning |
| --- | --- |
| `success` | the task's own verifier wrote a reward of 1 |
| `failure` | the verifier ran its tests and they did not all pass |
| `infra_invalid` | no usable reward: image unavailable, sandbox error, or **the verifier's own setup failed before any test ran** |
| `unavailable` | the task definition or verifier is not present locally |
| `accepted` / `rejected_within_noise` / `rejected_worse` / `accepted_cost` | the four verdicts a proposal can receive from the gate |

The `infra_invalid` row is the one that protects the pass rate. Every task image ships
without a test runner, so every verifier installs one first; when that install hits a
mirror 502 or a DNS failure the script still writes `reward.txt = 0`, which is
indistinguishable from an agent failure unless the log is read. The runner reads it,
re-classifies the cell, and retries it.

## 10. Results

See [`RESULTS.md`](RESULTS.md) for the measured numbers and the ledger excerpt.
