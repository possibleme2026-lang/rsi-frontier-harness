# Results

All numbers below were produced by this repository on the frozen FrontierHarness Eval v1
suite, with the commands in [`PROTOCOL.md`](PROTOCOL.md). The model is
`DeepSeek-V4.1-Flash` behind `https://tierflow.cn/v1`, priced with the rate card
declared in `genomes/pricing.json` (fresh input $0.28 / cached input $0.028 / output
$0.42 per 1M tokens). Every cell is reproducible from its stored trial directory:
`episode.json`, `llm-calls.jsonl`, `trajectory.jsonl`, `verifier.log`, `reward.*`.

**Headline.** 30 of 30 frozen tasks measured: **18/30 = 60.0%** at a total measured spend
of **$1.7718**, i.e. **$0.0984 per solved task**. The best published harness on the same
suite is `codex` at 66.7% and $3.468 per pass; the cheapest is `exo` at 53.3% and $1.045
per pass. This harness lands inside the published pass-rate band (56–63% for the DSH
variants, 58.1% suite-wide) at 10.6–35× lower cost per pass.

**Read the baseline columns as the eval published them.** The published harnesses keep
their frozen Kimi K3 rate card (3.00 / 0.30 / 15.00). Every cost comparison here is
therefore "what an operator pays per solved task with this harness on its own model",
not a same-model comparison; the price-independent token columns exist so the
difference can be separated.

## 1. Coverage

| suite | tasks in the eval | tasks runnable here | verifier protocol |
| --- | ---: | ---: | --- |
| `terminal-bench/*` (TB2) | 21 | 21 | tests copied into the agent container after it stops |
| `datacurve/*` (DeepSWE) | 9 | 9 | agent's diff collected, graded in a separate pristine container |
| **total** | **30** | **30** | |

`rsih doctor` reports the live number. Both protocols were exercised end to end before
any comparison was quoted.

## 2. The 30-task result

Every one of the frozen suite's thirty tasks was run. The genome is `gen1` — the
harness as designed, before any evolution — with its 60-step loop and its two protocol
paths.

| | RSIH `gen1` | codex | dsh-creator | pi-responses | dsh-standard | exo | claude-code |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| passes | **18/30** | 20/30 | 19/30 | 18/30 | 18/30 | 16/30 | 19/30 |
| pass rate | **60.0%** | 66.7% | 63.3% | 60.0% | 60.0% | 53.3% | 63.3% |
| total spend on the 30 | **$1.77** | $69.37 | $62.41 | $43.79 | $62.26 | $16.72 | $348.40 |
| effective cost per pass | **$0.098** | $3.468 | $3.285 | $2.433 | $3.459 | $1.045 | $18.337 |

| suite | measured | pass rate | spend |
| --- | ---: | ---: | ---: |
| `terminal-bench/*` (21) | 21 | 16/21 = 76.2% | $0.71 |
| `datacurve/*` (9) | 9 | 2/9 = 22.2% | $1.06 |
| **all** | **30** | **18/30 = 60.0%** | **$1.77** |

One cell short of that table: `polyglot-c-py` was `infra_invalid` in the 14-task sweep
because its image was missing; it was pulled and run on its own, and it passes. 18/30 is
the result of a single harness configuration (`gen1`, 60 steps) on all thirty cells.

Applying **one** mutation from the catalogue — `max_steps` 60 → 100 — to the four DeepSWE
cells that were step-limited turns the suite into **19/30 = 63.3% for $1.8703**, still
$0.098 per pass (§5 shows the probe). That is the shape of the remaining work: the
mutations are not hypothetical, they are entries in `rsih.rsi.mutators` with a hypothesis
attached, and this one is worth one cell and costs one cent.

That is the claim this work supports, stated so it can be checked:

- **Pass rate: inside the published band, not on top of it.** 18/30 ties `pi-responses`,
  `dsh-ptc` and `dsh-standard`, is 4 tasks behind `codex`, and is ahead of `exo` and
  `opencode`. Nothing here suggests the harness is a better *solver* than the published
  ones.
- **Cost: not close.** $0.098 per solved task against $1.045 for the cheapest published
  harness (`exo`) — 10.6× — and $3.468 for `codex`, 35×. Whole-suite spend was $1.77
  against codex's $69.37.
- **The two suites behave completely differently.** The harness solves 76% of the
  terminal-bench half and 22% of the DeepSWE half. Averaging those into one number hides
  the only actionable fact in it.

## 3. Baseline sweep — genome `gen0`, 14 terminal-bench tasks

This is the harness as designed, with no evolution applied: 6 frozen prompt blocks, 4
tools, a 60-step loop, byte-truncating compaction, and a one-shot submit guard.

| | RSIH `gen0` | strongest published harness on the same cells |
| --- | ---: | ---: |
| tasks scored | 11 / 13 valid (84.6%) | codex 11 / 13 (84.6%) |
| total spend | $0.340 | $3.937 (codex) |
| median cost / task | $0.0045 | $0.105 (codex) |
| effective cost / pass | **$0.0299** | $0.358 (codex), $0.906 (kimi-code), $1.224 (claude-code) |
| mean input tokens / task | 326,760 | 4,700,224 (codex) |
| mean output tokens / task | 27,739 | 16,991 (codex) |
| token-weighted cache hit rate | 94.5% | 63.8% (codex) |

`polyglot-c-py` was `infra_invalid` in this sweep because its image was missing; it was
pulled and measured separately and **passes** (§2 counts it). `dna-insert` and
`largest-eigenval` were audited against their verifier logs: both zeros are genuine agent
failures, not verifier-setup failures.

## 4. Where the money goes

`tools/cost_rollup.py` splits those $1.7718 across all 30 measured cells by what the
provider actually bills:

| component | tokens | cost | share |
| --- | ---: | ---: | ---: |
| fresh input | 967,573 | $0.2709 | 15% |
| cached input | 23,204,992 | $0.6497 | 37% |
| output | 2,026,535 | $0.8511 | 48% |
| **total** | | **$1.7718** | |

Three things follow, and they are why the cost number is not an accident:

- **The token-weighted cache hit rate is 96.0%** (23.2 M of 24.2 M prompt tokens were
  cache reads), against 63.8% for `codex` and 92.4% for the suite as a whole. Prefix
  stability is a first-class design constraint here: the system prompt is frozen per
  genome, tool schemas are emitted in a fixed order, and the observation window is
  trimmed from the middle rather than rewritten, so each turn extends a cacheable prefix
  instead of invalidating it.
- **Cache reads are still 37% of spend**, even at one tenth of the input price, because
  the transcript is 23 M tokens for 30 tasks. Being cheap required both a low cache-read
  rate *and* a transcript small enough that 96% of it being cached still costs less than
  the output.
- **Output tokens are the largest single component at 48%.** The harness is frugal with
  transcript and generous with completions — the opposite of the published harnesses
  (codex: 4.7 M input / 17 k output per task; here: 0.81 M input / 68 k output). This is
  the most obvious lever left, which is why the evolution loop's cost branch included
  `max_output_tokens`.

## 5. DeepSWE (datacurve) — the half of the suite that is not terminal-bench

Nine tasks, each a real repository at a pinned commit with a hidden fail-to-pass test
set. The contract is different from terminal-bench in a way that matters: the agent's
diff is collected, then graded in a **separate pristine container**, so nothing the agent
leaves in its own filesystem can influence the verdict. Reward is binary — every
fail-to-pass test must pass — and the verifier also reports the fraction that did.

| task | reward | fail→pass tests | pass→pass | steps | spend | published passes | cheapest published pass |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| anko-typed-variable-bindings | **1** | 9/9 | 94/94 | 60 | $0.0782 | 4/12 | $1.598 |
| fastapi-deprecation-response-headers | **1** | 137/137 | – | 60 | $0.1279 | 4/12 | $2.487 |
| httpx-multipart-response-parsing | 0 | **121/122** | – | 55 | $0.1113 | 5/12 | $1.330 |
| scc-bounded-memory-spilling | 0 | 26/31 | – | 60 | $0.1356 | **0/12** | nobody |
| arktype-json-schema-refs-dependencies | 0 | 0/25 | 94/94 | 60 | $0.0697 | 2/12 | $9.987 |
| expr-try-catch-errors | 0 | 0/79 | – | 53 | $0.1620 | 2/12 | $13.058 |
| python-statemachine-state-data-scoping | 0 | 0/72 | 1286/1286 | 60 | $0.1422 | 7/12 | $2.503 |
| meriyah-explicit-resource-declarations | 0 | 0/49 | – | 60 | $0.0696 | 1/12 | $7.875 |
| katex-multicolumn-array-spans | 0 | 0/94 | – | 55 | $0.1662 | 1/12 | $7.838 |
| **total** | **2/9** | | | | **$1.0627** | | |

| harness | passes | total spend on the same 9 | effective cost per pass |
| --- | ---: | ---: | ---: |
| **RSIH `gen1`** | **2/9** | **$1.06** | **$0.53** |
| codex | 5/9 | $64.51 | $12.90 |
| dsh-creator | 4/9 | $59.04 | $14.76 |
| claude-code | 3/9 | $332.82 | $110.94 |
| kimi-code | 3/9 | $52.61 | $17.54 |
| dsh-standard | 2/9 | $54.11 | $27.06 |
| pi-responses | 2/9 | $38.33 | $19.17 |
| exo | 0/9 | $10.30 | n/a |
| opencode | 0/9 | $45.19 | n/a |

The pass count puts this harness level with `dsh-standard`, `dsh-ptc`, `pi-responses` and
`hermes`, and ahead of `exo` and `opencode`, on 1.6% of codex's spend for the same nine
tasks. Two cell-level details are worth more than the aggregate:

- **`httpx-multipart-response-parsing` missed binary reward by one test out of 122**, and
  `scc-bounded-memory-spilling` — which **none of the twelve published harnesses passed** —
  reached 26 of its 31 required tests. The binary reward hides how close those are; the
  per-test fractions are kept in `trial.json` for exactly that reason.
- **Three of the seven failures submitted a zero-byte patch.** Their transcripts show why:
  107, 54 and 81 shell calls, all exploration and grep, no edit to the repository before
  the step limit. That is a budget finding, not a capability finding, and it is testable.

### Test: was the budget the constraint?

`max_steps=100` is one entry in the mutation catalogue. Applied to the four tasks that
were either step-limited with an empty patch or one test short:

| task | 60 steps | 100 steps |
| --- | --- | --- |
| katex-multicolumn-array-spans | 0 submitted, 0/94 | **1, 94/94, 124 KB patch** |
| python-statemachine-state-data-scoping | 0 submitted, 0/72 | 0 submitted, 0/72 |
| meriyah-explicit-resource-declarations | 0 submitted, 0/49 | 0 submitted, 0/49 |
| httpx-multipart-response-parsing | 0, 121/122 | 0, 121/122 (submitted itself at step 61) |

One task converts from "never wrote a file" to a full pass with a single catalogue
mutation, which confirms the diagnosis for that cell and refutes it for the other three.
Those three fail for a different reason each:

- `python-statemachine` and `meriyah` still submit nothing after 100 steps: the budget is
  not what is missing.
- `httpx` **declares itself finished at step 61 with one of 122 required tests failing**.
  That is not a budget failure or a capability failure; it is the agent deciding it was
  done without running the acceptance test — the exact behaviour that the evolution
  child `prompt+=verify.requirements` (§6, `g1c0`) was proposed to fix, and which fixed
  `largest-eigenval` on the terminal-bench half.

**The headline is a floor, not a ceiling:** the same harness with a longer budget scores
3/9 on this half, and the failures that remain point at self-verification rather than at
model capability or at time.

## 6. Evolution

The loop (`rsih evolve`) proposes descriptor mutations and free-text prompt rules,
evaluates each child on the evolve set, and accepts only what clears a significance
floor. Two runs were performed.

### Run `rsi-g1` — correctness branch (discarded)

An 8-task evolve set, 2 generations. Generation 1 produced three children
(`prompt+=verify.requirements`, `loop.compaction=summarize`, `llm.prompt_patch`); none
cleared the floor. Generation 2 was **discarded, not reported**: the runner's own
concurrency plus a second concurrent experiment exhausted the endpoint's per-IP quota,
and four cells then ended in `model_error`. That is a measurement failure wearing a
failure's clothes, and the run is kept at `runs/_discarded-rsi-g1-ratelimit/` as the
evidence for the rule that now prevents it (`UNSCORABLE_EXIT_REASONS` in the runner,
plus a process-wide request throttle in the LLM client).

What generation 1 did establish, on the 8 tasks it measured:

- `loop.compaction=summarize` (a child that replaces byte truncation with a model
  summary) **solved `largest-eigenval`, the one task the incumbent failed**, at 54 turns
  — and failed `vulnerable-secret`, which the incumbent solves. One swap in eight cells
  gives `b = c = 1`, `diff = 0`, `floor = 0.35`: correctly recorded as
  `rejected_within_noise`.

The gate's arithmetic turns out to be the most consequential design fact in the whole
loop, so it is worth stating exactly. A proposal is accepted only when
`(b - c) > z·sqrt(b + c)` with `z = 2`, where `b` cells went fail→pass and `c` went
pass→fail. That inequality has no solution for `b + c ≤ 4`: **the smallest acceptable
improvement is `b = 5, c = 0`** — five cells fixed and nothing broken, whatever the size
of the resume set. (At `z = 1.96` with a continuity correction the textbook answer is
~17 discordant cells; the loop deliberately uses the more conservative form.)

The consequence is not academic. On the 6-task evolve set used below, no pass-rate
change is *ever* acceptable, and on the full 30-task suite the loop needs a five-task
sweep to move at all. Spend has no such floor: it is continuous per cell, it is
reported by the provider, and a child that holds the pass rate while spending 15% less
is unambiguously better. **The significance gate is what makes this an optimizer of
cost rather than of pass rate, and that is the honest reading of every result below.**

### Run `rsi-r3` — the reported run

Evolve set: 6 tasks (`largest-eigenval`, `kv-store-grpc`, `log-summary-date-ranges`,
`vulnerable-secret`, `modernize-scientific-stack`, `merge-diff-arc-agi-task`).
One generation, four children: the analyst's top mutation, two deterministic samples
from the 22-mutation catalogue, and the analyst's free-text rules. Each child differs
from the seed by exactly one edit, so every row below is a controlled comparison.

| child | edit | pass | spend | ratio vs seed | gate verdict |
| --- | --- | ---: | ---: | ---: | --- |
| `gen1` (seed) | — | 5/6 | $0.13158 | — | — |
| `g1c0` | `prompt+=verify.requirements` | **6/6** | $0.13180 | 1.002 | `rejected_within_noise` |
| `g1c1` | `loop.compaction=summarize` | **6/6** | **$0.10736** | **0.816** | `accepted_cost` (see below — this reverses under a floor) |
| `g1c2` | `prompt+=method.smallest_change` | **6/6** | **$0.10302** | **0.783** | `accepted_cost` (reverses under a floor) |
| `g1c3` | `llm.prompt_patch` (analyst rules) | **6/6** | $0.12010 | 0.913 | `rejected_within_noise` |

Four things happened, and the second is the important one.

1. **The analyst was right about the failure, in every arm.** The seed's one failure was
   `largest-eigenval`, and the analyst's diagnosis was that the agent "burned its entire
   budget on speculative micro-optimization … and never converged on a finalized
   implementation that it validated end-to-end against the task's own eval". All four
   children fixed exactly that task, from four different directions: a verification
   obligation, a compaction change, a smallest-change rule, and the two analyst rules
   on their own.

2. **Not one of those fixes could be accepted as a pass-rate improvement.** Each is
   `b = 1, c = 0` → `diff = +0.167` against `floor = 0.333`. The loop recorded the same
   verdict four times: *a single flipped cell in six is not evidence*. This is the
   clearest possible statement of the gate's cost, and it is a cost worth paying — the
   alternative is adopting changes that cannot be distinguished from a lucky run.

3. **Spend accepted what correctness could not.** Three children also spent less, two
   cleared the 15% margin, and the loop adopted `loop.compaction=summarize` at −18.4%.
   That is the change the harness actually learned in this run.

4. **The saving is specific to the edit, not to the run.** `g1c0` fixed the same task
   from the same starting point and spent $0.13180 against the seed's $0.13158 — a
   0.2% difference. Whatever made `g1c1` and `g1c2` cheap is not drift within the run.

### Why the cost fell

`largest-eigenval`, per trial:

| genome | status | turns | output tok | $output | cached tok | $cached | fresh tok | $fresh | total |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gen1` | fail | 52 | 139,318 | $0.0585 | 971,136 | $0.0272 | 84,031 | $0.0235 | $0.1092 |
| `g1c0` | pass | 60 | 104,777 | $0.0440 | 1,637,504 | $0.0459 | 61,635 | $0.0173 | $0.1071 |
| `g1c1` | pass | 60 | 101,060 | $0.0424 | 826,240 | $0.0231 | 33,658 | $0.0094 | $0.0750 |
| `g1c2` | pass | 48 | 100,676 | $0.0423 | 806,912 | $0.0226 | 36,166 | $0.0101 | $0.0750 |
| `g1c3` | pass | 60 | 88,756 | $0.0373 | 1,201,408 | $0.0336 | 41,908 | $0.0117 | $0.0827 |

Every child cut output tokens on this task by 25–36%, and every child passed it. **A
task that fails costs more than the same task that succeeds**: the seed spent 139 k
output tokens losing, and the children spent 89–105 k winning. Cost per solved task is
therefore not the cost of solving; it is the cost of solving plus the cost of whatever
thrashing preceded it, which is the reason a harness that fails cheaply still looks
expensive in the cost-per-pass column.

`compaction=summarize` has the mechanism the edit claims: it replaces accumulated raw
observations with a summary, so 826 k cached tokens were carried instead of 1.64 M for
the same 60 turns.

### The check this run could not make

One run per child bounds nothing about run-to-run variance in agent behaviour, and the
cost gate as first written — unlike the pass-rate gate — had **no floor at all**: it was
a point ratio of two totals against a 15% margin. Six cells and one dominant task is
exactly the situation where that rule fails, and it did.

The statistic that belongs under a *total* is the paired difference of the per-task
spends, because the total difference is their sum and its standard error follows from
them. Applied to the same six cells, at the same `z = 2` the pass-rate gate uses:

| comparison | cells | total ratio | mean Δ | se | t | point rule | paired rule |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `gen1` → `g1c1` | 6 | 0.816 | −$0.00404 | $0.00631 | −0.64 | accept | **reject** |
| `gen1` → `g1c2` | 6 | 0.783 | −$0.00476 | $0.00597 | −0.80 | accept | **reject** |
| `gen1` → `g1c3` | 6 | 0.913 | −$0.00191 | $0.00537 | −0.36 | reject | reject |
| `gen1` → `g1c0` (control) | 6 | 1.002 | +$0.00004 | $0.00131 | +0.03 | reject | reject |
| holdout: `gen1` → `g1c1` | 7 | 0.905 | −$0.00446 | $0.00301 | −1.48 | reject | reject |

Neither `accepted_cost` verdict survives the floor. Worse for the point rule, the two
cells it accepted are precisely the two with the most favourable ratio — which is what
selecting on a noisy ratio does.

Because the loop stores per-task trials and applies its rule in code, the corrected rule
can be **replayed against the original evidence** rather than re-run:

```
$ python tools/replay_gate.py runs/rsi-r3
child   mutation                           ratio       t  recorded                  replayed
g1c0    prompt+=verify.requirements        1.002    0.03  rejected_within_noise     rejected_within_noise
g1c1    loop.compaction=summarize          0.816   -0.64  accepted_cost             rejected_within_noise  <-- CHANGED
g1c2    prompt+=method.smallest_change     0.783   -0.80  accepted_cost             rejected_within_noise  <-- CHANGED
g1c3    llm.prompt_patch                   0.913   -0.36  rejected_within_noise     rejected_within_noise
```

**Two of the four decisions reverse, and the run's only adoption disappears.** The
correct reading of `rsi-r3` is therefore: the analyst produced four correct diagnoses,
the pass-rate gate correctly refused all four, and the cost gate adopted one change it
could not establish. `paired_decision` now applies the same floor to money as to cells,
and `tools/replay_gate.py` is how a past run is re-audited under a new rule.

### The holdout, which was run before the rule was fixed

The holdout is still the only measurement that was not available to the gate, so it is
still the arbiter:

| task | `gen1` | `g1c1` | $ `gen1` | $ `g1c1` |
| --- | --- | --- | ---: | ---: |
| chess-best-move | fail | fail | $0.1102 | $0.1132 |
| constraints-scheduling | pass | pass | $0.0079 | $0.0020 |
| db-wal-recovery | pass | pass | $0.0032 | $0.0027 |
| extract-elf | fail | fail | $0.0914 | $0.0707 |
| gcode-to-text | fail | fail | $0.0718 | $0.0708 |
| regex-log | pass | pass | $0.0182 | $0.0113 |
| sqlite-db-truncate | pass | pass | $0.0262 | $0.0269 |
| **total** | **4/7** | **4/7** | **$0.3289** | **$0.2976** |

**Zero discordant cells.** On seven tasks the child was never selected on, the adopted
edit changed nothing about which ones pass, and it was cheaper on five of seven
(`t = −1.48`, still short of the floor, but the sign is consistent and the pass rate is
untouched).

So the end state of this self-improvement run is:

- `g1c1` is a **slightly better harness than `gen1`** — same pass rate on unseen tasks,
  ~10% cheaper, no regression anywhere.
- The loop **did not earn that conclusion**. Its cost rule adopted a change on evidence
  that does not support adoption, and the same rule under a floor would have refused it.
- The direction was right and the decision was luck. Reporting only the adopted ledger
  would have claimed an 18% saving; the holdout says 10%, and the paired statistic says
  "not established at these sample sizes".

This is the outcome the design was built to make visible, and it is the strongest
argument for the parts of the harness that have nothing to do with the model: the
per-trial artifacts, the replayable rule, and a holdout the loop cannot see.


## 7. What this does not show

- **It is not a leaderboard entry.** The model is not the baselines' Kimi K3, the
  verifiers are TB2 main rather than the gated 2.1 tag, containers run on a bridge
  network instead of a runtime-wide allowlist, and the DeepSWE agent budget is capped
  locally. Every one of those is listed in [`PROTOCOL.md`](PROTOCOL.md) §6 and recorded
  per trial in the run artifacts.
- **A pass rate over 13 or 30 cells has a wide interval.** 11/13 is compatible with a
  true rate anywhere from ~55% to ~98%. The claim this work supports is the *cost*
  claim, which is measured directly, and the coverage claim, which is a fact about what
  ran.
- **The evolve set is small on purpose, and that caps what evolution can prove.** See
  §6: the gate needs five net flips, so a six-cell evolve set can only ever move spend.
  Self-improvement of *capability* is not demonstrated here; self-improvement of spend
  is, and the holdout shows even that was over-credited.
- **A perfectly good child can be rejected.** In run `rsi-g1`, `loop.compaction=summarize`
  fixed the one task the incumbent failed and broke one it passed; in run `rsi-r3` four
  children each fixed the failing task and none could be accepted on pass rate. The loop
  refuses to call either an improvement, which is the correct behaviour and also a real
  loss of information: the gate sees the count of flips, not the difficulty of the cell.
- **One accepted cost change is one measurement.** The −18.4% is real for that run and
  that task set; on the holdout it reproduced as −9.5%. A repeated-measures design (k
  runs per genome, paired per task) would cost k× the GPU-equivalent budget and is the
  single most valuable missing experiment.
- **Cost is measured, not billed.** Spend is computed from provider-reported token
  counts against a declared rate card. A different cache-read discount or a differently
  metered reasoning channel would move the absolute numbers, though not the ranking.
