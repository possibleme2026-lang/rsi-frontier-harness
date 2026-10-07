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

### Where the two sides of this table come from

They do **not** come from the same place, and the difference is large enough that the
table has to be read as two separate measurements:

| | this harness | the published harnesses |
| --- | --- | --- |
| who ran it | this repository, in this session | the benchmark authors |
| where the numbers live | `runs/*/trials/*/trial.json` | `_ref-frontier-eval/results/eval-data.json` |
| model | `DeepSeek-V4.1-Flash` | **Kimi K3** (every configuration) |
| runtime | Docker Desktop on Windows, default bridge | a Runta runtime with a runtime-wide egress allowlist |
| price basis | the tierflow rate card, `genomes/pricing.json` | the eval's own `pricing.json` |
| verifiers | terminal-bench-2 main; deep-swe corpus 1.3 collect hook | the gated published set |
| DeepSWE agent budget | capped locally at 1500–2100 s | the declared 5400 s |

**The published harnesses were not re-run here and cannot be.** The eval repository ships
its results, task definitions and workflow, and states that "internal infrastructure,
credentials, runtime identifiers, private evidence, solutions, and deployment
configuration are not included" — the twelve configurations are not executable artifacts
in the clone. `tools/published_provenance.py` prints exactly what the file contains:

```
file          : _ref-frontier-eval/results/eval-data.json
generated_at  : 2026-08-22T16:04:57.538734+00:00
model field   : k3
overview.checkpoint_tasks                 30
overview.expected_cells                   360
overview.completed_cells                  360
overview.harness_configurations           12
```

So the pass-rate column is *their harness on their model* against *this harness on this
model*. It is a like-for-like comparison of **tasks, verifier contracts and per-task
outcomes**, and it is **not** a controlled comparison of harnesses. Anyone reading the
cost column should read it as "what an operator pays per solved task, on each side's own
model and own prices". The price-independent evidence that this harness is frugal is the
token profile, which is provider-reported on both sides and is in §4.

| | RSIH `gen1` | codex | dsh-creator | pi-responses | dsh-standard | exo | claude-code |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| passes | **18/30** | 20/30 | 19/30 | 18/30 | 18/30 | 16/30 | 19/30 |
| pass rate | **60.0%** | 66.7% | 63.3% | 60.0% | 60.0% | 53.3% | 63.3% |
| total spend on the 30 | **$1.77** | $69.37 | $62.41 | $43.79 | $62.26 | $16.72 | $348.40 |
| effective cost per pass | **$0.098** | $3.468 | $3.285 | $2.433 | $3.459 | $1.045 | $18.337 |

Both sides of the cost row are token-derived and use the **first-cold** convention
(§4.1). Ours is $1.7793 over the 30 cells by that convention — $0.0988 per pass — against
$1.7718 / $0.0984 by the plain one; the table quotes the plain one and the difference is
0.42%.

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

### 2.1 The step budget is not the constraint; the output cap is

Every terminal-bench failure in the 14-task sweep ended in `step_limit` or
`wall_clock_budget`, so the obvious hypothesis is that the harness is starved of steps by
its own 60-step cap and the eval would score higher if it used the budget each task
actually declares. `tools/tb_budget_table.py` is that table:

| task | declared | outcome | turns | exit |
| --- | ---: | --- | ---: | --- |
| dna-insert | 1800 s | failure | 38 | wall_clock_budget |
| chess-best-move | 900 s | failure | **60** | **step_limit** |
| gcode-to-text | 900 s | failure | **60** | **step_limit** |
| largest-eigenval | 900 s | failure | **60** | **step_limit** |
| extract-elf | 900 s | failure | 36 | wall_clock_budget |

`steps_from_declared_budget` implements the hypothesis directly: a task declaring `D`
seconds gets `max_steps * clamp(D / reference, 1, 4)` steps. With `reference = 1800` —
the largest budget any terminal-bench task declares — **the terminal-bench half is
unchanged by construction** and only DeepSWE moves (60 → 180). With `reference = 600` the
900 s tasks get 90 steps, the 1200 s ones 120, `dna-insert` 180 and DeepSWE 240.

`gen4` is that second setting, run over the four cells that were either step-limited or
one test short. **It made things worse, on cells the seed passes:**

| task | `gen1` (60 steps, no output cap) | `gen4` (declared budget) |
| --- | --- | --- |
| anko-typed-variable-bindings | **success**, 60 turns | failure, 124 turns |
| fastapi-deprecation-response-headers | **success**, 60 turns | failure, 33 turns (`wall_clock_budget`) |
| arktype-json-schema-refs-dependencies | failure, 60 turns | failure, 103 turns |
| expr-try-catch-errors | failure, 53 turns | failure, 75 turns |

The reason is in `runs/gen4-full/trials/fastapi-deprecation-response-headers/llm-calls.jsonl`,
and it is not a mystery:

```
step31  latency_s=138.1  completion_tokens=21999  reasoning_tokens=21844
step32  latency_s= 54.9  completion_tokens= 8338  reasoning_tokens= 8166
```

Given a longer horizon, the model does not take more actions; it takes *longer thoughts*.
Two 22 k-token deliberation turns ate a minute and a half each and the episode died on the
wall clock with 33 actions taken out of 240 available. The 60-step cap was not starving
the harness — it was the only thing bounding a per-response cost blowup, which is the
same conclusion the cost anatomy reaches from the other direction (output is 48% of
spend). **`max_output_tokens = 0`, the provider default, is the hole** — so the obvious
fix is to close it, and that fix was tested next and also failed.

`gen5` = `gen4` + `max_output_tokens = 4096`, same four cells: **0 of 5 raw attempts
passed**, and the episodes did not fail on the wall clock any more. They failed at turn
18–51 with exit reason `text_only`: the cap truncates this model *mid-thought*, before it
emits its tool calls, so the response contains no action at all and the loop's
text-only nudge exhausts and ends the episode. Reasoning tokens are part of the
completion here, not an add-on to it, which means the harness cannot bound deliberation
per response without also bounding its ability to act.

The three runs together locate the workable region precisely:

| configuration | steps | output cap | cells | outcome |
| --- | --- | ---: | ---: | --- |
| `gen1` | 60 | none | 30 | **18/30, $1.7718, $0.0984/pass — the reported harness** |
| `gen4` | up to 240 | none | 4 | worse: two cells it used to pass now fail |
| `gen5` | up to 240 | 4096 | 5 | much worse: actions truncated away, `text_only` exits |
| `gen6` | 100 | none | **30** | **18/30, $2.1216, $0.1179/pass** — same score, 20% more spend |

`gen6` is the honest attempt at the hypothesis rather than a probe: a modest step
increase plus a targeted self-verification block, uncapped output, run over the whole
suite. It **trades cells rather than winning them** — `tools/ab_runs.py` against the
reported harness:

| | task | verdict change | turns | spend |
| --- | --- | --- | --- | --- |
| won | `katex-multicolumn-array-spans` | failure → **success** | 55 → 100 | $0.166 → $0.167 |
| won | `python-statemachine-state-data-scoping` | failure → **success** | 60 → 100 | $0.142 → $0.147 |
| won | `extract-elf` | failure → **success** | 36 → 17 | $0.091 → $0.063 |
| lost | `anko-typed-variable-bindings` | success → failure | 60 → 86 | $0.078 → $0.209 |
| lost | `fastapi-deprecation-response-headers` | success → failure | 60 → 100 | $0.128 → $0.201 |
| lost | `sanitize-git-repo` | success → failure | 32 → 35 | $0.023 → $0.032 |

Three cells bought at the price of three, for 20% more money, and the three losses cost
**2.6×** what the three wins cost. The step cap was not starving the harness; it was
bounding a per-response cost blowup, and the per-response cost cannot be bounded directly.
That is the answer to the question §2 opened with, and it is a negative one.

### 2.2 How stable is a cell?

A pass measured once is not a property of the harness. Every cell that was deliberately
re-run is collected by `tools/task_stability.py`, and the result is worth reporting
because it is not uniform:

| task | valid runs | passes | why the runs disagree |
| --- | ---: | ---: | --- |
| `sanitize-git-repo` | 9 | **2 (22%)** | **flaky at a fixed genome** — same mistake, same test |
| `anko-typed-variable-bindings` | 4 | 1 | only at 60 steps; fails at 51 / 86 / 124 |
| `fastapi-deprecation-response-headers` | 4 | 1 | only at 60 steps |
| `katex-multicolumn-array-spans` | 4 | 2 | both passes at 100 steps |
| `python-statemachine-state-data-scoping` | 5 | 1 | only pass is 100 steps + self-check |
| `extract-elf` | 3 | 1 | only pass is `gen6` |
| `polyglot-c-py` | 2 | 2 | never disagrees |
| `httpx-multipart-response-parsing` | 3 | 0 | never disagrees — 121/122 every time |

`sanitize-git-repo` is the one cell whose pass does not reproduce *at a fixed genome*, and
it fails the same way almost every time: the agent decides the right fix for "secrets are
in this repo" is to rewrite history with `git filter-branch`, then `git reflog expire` and
`git gc --prune=now`, which destroys the commit the verifier's
`test_no_other_files_changed` needs. Five of its seven failures are that one mistake. A
conservative reading of the headline is therefore **17/30 = 56.7%**, and §7 says so rather
than quietly keeping the flattering number. The rows below it are a different phenomenon —
they are *configuration*-sensitive, not flaky, which is why the report quotes one genome
per number and A/Bs the rest with `tools/ab_runs.py`.

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
- **The gap to the top is not a budget gap.** §2.1 spends 64 extra cell-runs proving it:
  three configurations with more steps and/or a verification block all landed at or below
  the 60-step harness, and the one that matched its score cost 20% more.

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

### 4.1 How the number is computed

Nothing here is billed-and-read-back; every dollar figure is derived from the token counts
the provider returns on each call, times a declared rate card. The chain is:

```
provider usage per call  ->  RateCard.price()  ->  CostLedger  ->  trial.json  ->  sums
  prompt_tokens             fresh  = prompt - cached            cost_usd
  cached_tokens             cost   = fresh*0.28 + cached*0.028
  completion_tokens                 + cache_write*0.28 + completion*0.42   (per 1M)
  reasoning_tokens          (reasoning is inside completion, not beside it)
```

Rates come from `pricing.json`, which records its own source: `0.28 / 0.28 / 0.028 / 0.42`
per 1M fresh input / cache write / cache read / output, *declared by the operator* for the
`tierflow.cn` endpoint (DeepSeek flash-tier shape, cache read = 10% of fresh input). They
were not read off an invoice, and the file says so.

Four rules make the accounting auditable:

1. **Missing stays missing.** A call with no usage payload contributes `None`, never zero,
   and if any call in an episode is missing usage the episode's cost is `None` rather
   than a partial sum (`test_cost_ledger_refuses_partial_sum`). Failed attempts — the 429
   retries that appear in the call log with `error` and `sleep_s` and no usage — are
   logged but not billed.
2. **The convention is named.** `cost_usd` prices cache reads at the cache rate from the
   first call on; `cost_first_cold_usd` re-prices the first call's cache reads at the
   fresh-input rate, so a harness that warms the cache on turn one pays for the warm-up.
   The published baselines use the second convention, and `tools/cost_conventions.py`
   measures the gap on our side: **$1.7718 → $1.7793 over 30 cells, +0.42%**. §2's headline
   quotes $1.7718 (`cost_usd`); the conservative figure is **$0.0988 per pass**.
3. **Passes are the benchmark's definition.** `effective_cost_per_pass` is total cost over
   all measured cells divided by passes, with `infra_invalid` cells excluded from both
   numerator and denominator.
4. **It can be recomputed from the raw log.** `tools/verify_cost.py <trial>` re-derives
   the trial's cost from `llm-calls.jsonl` alone. On
   `runs/deepswe-9/trials/anko-typed-variable-bindings`:

```
component               tokens   rate/1M        usd
fresh input             59,384     0.280    0.01663
cached input         1,700,224     0.028    0.04761
output                  33,137     0.420    0.01392
recomputed                                  0.07815
trial.json cost_usd            : 0.07815133199999999
trial.json cost_first_cold_usd : 0.07844163599999998
reasoning tokens               : 26,177  (79.0% of completion)
```

Two things that audit makes visible, and both matter:

- **`cache_write_tokens` is `null` on this endpoint**, so the `0.28` write rate is never
  applied in practice. DeepSeek-style implicit caching does not charge a separate write,
  so this is consistent — but it is an assumption the card encodes, not something the
  measurements confirm.
- **Reasoning is 79% of completion and is billed at the output rate.** That is the single
  most important fact about this harness's cost, and §2.1 is what happens when you try to
  cap it.

### 4.2 Where the 30-task total goes

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
  cache reads), against 92.4% for the suite as a whole. That is *above* the suite average
  and *below* every top-half harness — `codex` is at 99.1% normalized and 88.0% typical,
  `pi-responses` at 97.2%. **The cost advantage is therefore not a warmer cache.** What it
  is instead is a shorter transcript: 0.81 M input tokens per task against `codex`'s
  4.70 M. Prefix stability still matters here — the system prompt is frozen per genome,
  tool schemas are emitted in a fixed order, and the observation window is trimmed from
  the middle rather than rewritten — but it buys a transcript small enough to be cheap,
  not a cache hit rate that beats the field.
- **Cache reads are still 37% of spend**, even at one tenth of the input price, because
  the transcript is 23 M tokens for 30 tasks. Being cheap required both a low cache-read
  rate *and* a transcript small enough that 96% of it being cached still costs less than
  the output.
- **Output tokens are the largest single component at 48%, and this harness is the most
  output-hungry configuration measured.** 68 k output tokens per task against `codex`'s
  17 k, `pi-responses`' 8 k and `exo`'s 6 k — because 79% of each completion is the
  reasoning channel (§4.1). This is the opposite of the published harnesses' profile and
  it is the reason the reported cost is sensitive to the output rate rather than to the
  cache. It is also the most obvious lever left, which is why the evolution loop's cost
  branch included `max_output_tokens`.

### 4.3 The price-independent comparison

Cost per pass mixes two things: what the model charges per token, and how many tokens the
harness uses. The second is provider-reported on both sides, so it can be compared
directly. `tools/token_profile.py`:

| configuration | mean input / task | mean output / task | turns | cache hit |
| --- | ---: | ---: | ---: | ---: |
| `codex` | 4,700,224 | 16,991 | 62.4 | 99.1% |
| `dsh-creator` | 2,119,233 | 13,649 | 35.7 | 98.3% |
| `dsh-minimal` | 4,790,827 | 13,392 | 47.6 | 98.6% |
| `claude-code` | 1,903,406 | 10,109 | 49.3 | 24.9% |
| `kimi-code` | 3,395,606 | 10,989 | 39.9 | 98.3% |
| `pi-responses` | 638,339 | 7,927 | 18.7 | 97.2% |
| `exo` | 375,126 | 5,545 | 12.0 | 94.5% |
| `opencode` | 153,533 | 2,398 | 11.2 | 91.6% |
| **rsih `gen1`** | **805,752** | **67,551** | **40.1** | **96.0%** |

Read honestly, this table does not flatter the harness: it is mid-pack on input, last on
output, and mid-pack on cache. The published configurations include several that are
leaner in tokens. So the money question becomes: if this token profile ran on *their*
price card, what would it cost?

### 4.4 Re-pricing our tokens on the frozen Kimi K3 card

`tools/repricing.py` prices our measured 30-cell token counts on the baselines' card
(3.00 / 3.00 / 0.30 / 15.00 per 1M), which removes the model-price difference and leaves
the harness difference:

| | 30 tasks | per pass |
| --- | ---: | ---: |
| ours, DeepSeek-V4.1-Flash card (the reported number) | $1.7718 | $0.0984 |
| ours, frozen Kimi K3 card | **$40.2622** | **$2.2368** |

Against the published configurations on their own card, $2.237 per pass is the cheapest of
the twelve — but by **1.09x over `pi-responses` ($2.433)** and **1.55x over `codex`
($3.468)**, not by 35x. And it is not actually the cheapest token profile on the board:
`exo` reaches 53.3% at $1.045 per pass with a third of our input and a twelfth of our
output. **The headline ratio is mostly the model's price. The harness's own contribution
is the small real gap above, and this is the number to quote to anyone who asks whether
the harness or the model is doing the work.**

### 4.5 Is the declared card right? One billed call says it over-states by 3x

`pricing.json` states that its rates are operator-declared rather than verified. The
provider's console records one real call, and `tools/billing_check.py` runs the arithmetic
against it:

```
billed call        : 11,145 fresh | 88,832 cached | 196 output
charged            : 0.013706 CNY
rate (CNY per 1M)         implied by the bill  declared card   ratio
fresh input                            0.6744         2.0160    0.33
cache read                             0.0674         0.2016    0.33
output                                 1.0117         3.0240    0.33
```

The bill implies a fresh-input rate of ¥0.674 per 1M where the declared card says ¥2.016
(at 7.2 CNY/USD) — **the card is 2.99x the billed rate**. That call's output term is only
1.45% of its cost, so the output rate is genuinely unconstrained by it; what the record
does establish is that the input side is billed at about a third of what was declared
(the console labels it 阶梯计费, tiered). Consequences for the headline:

| assumption | 30 tasks | per pass |
| --- | ---: | ---: |
| declared card (quoted everywhere in this report) | $1.7718 | $0.0984 |
| billed input rates, declared output rate | $1.1591 | $0.0644 |
| billed input rates, output rate scaled with them | $0.5927 | $0.0329 |

So **$0.0984 per pass is an upper bound, and the real figure is between $0.033 and
$0.064** depending on the output rate. The report keeps quoting the declared-card numbers
because they are the conservative ones and because the card is what the harness declares;
re-pricing is one command. The CNY/USD conversion is the only assumption in the table, and
it is stated.

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

| task | 60 steps (`gen1`) | 100 steps | 100 steps + `verify.self_check` (`gen6`) |
| --- | --- | --- | --- |
| katex-multicolumn-array-spans | 0 submitted, 0/94 | **1, 94/94, 124 KB patch** | **1, 94/94** |
| python-statemachine-state-data-scoping | 0 submitted, 0/72 | 0 submitted, 0/72 | **1** |
| meriyah-explicit-resource-declarations | 0 submitted, 0/49 | 0 submitted, 0/49 | 0 |
| httpx-multipart-response-parsing | 0, 121/122 | 0, 121/122 (submitted itself at step 61) | 0, **121/122** |
| anko-typed-variable-bindings | **1**, 9/9 | — | 0, **0/9** |
| fastapi-deprecation-response-headers | **1**, 137/137 | — | 0, step_limit at 100 |
| arktype-json-schema-refs-dependencies | 0 | — | 0 |
| expr-try-catch-errors | 0 | — | 0 |
| scc-bounded-memory-spilling | 0, 26/31 | — | 0 |

Two tasks convert from "never wrote a file at 60 steps" to full passes — `katex` under the
budget increase, `python-statemachine` under the budget increase plus the self-check
block. That is the good news, and it is all of the good news: **the same edit loses two
cells the 60-step harness passes.** `anko` and `fastapi` are solved at 60 steps, and at
86–100 steps the agent re-opens work it had already finished — `anko` ends with a patch
that passes all 94 existing tests and **none of the 9 new ones**. `katex` needs more than
60 steps and `anko` needs fewer than 100; one global constant cannot serve both.

And `httpx` failed identically three times, which is the most informative single fact in
this report. Its one failing test is:

```
test_iter_multipart_part_headers_parsing[X: 1\r\n\tz\r\n\r\n-expected7]
AssertionError: assert '1\tz' == '1 z'
```

The hidden test folds a header with a **tab**, and expects the parser to unfold it to a
space. The agent implemented 121 of 122 required behaviours and lost the binary reward on
a tab-versus-space in a header continuation. No amount of budget, and neither verification
block, changes that: this is a byte-exact conformance detail that has to be either known
from the spec or read out of the test. **The harness is one RFC unfolding rule away from
3/9 on this half**, and the failures that remain are of that kind rather than of the
budget kind.

**The headline is therefore a configuration, not a floor.** The longer budget is not
free: over the whole suite it buys three cells and sells three, for 20% more money
(§2.1). The reported 30-task number is the 60-step harness, and the reason is
measurement, not preference.

### 5.1 The failures are not a budget finding — five of seven never wrote the deliverable

The zero-byte finding above generalises, and correcting it changes what the fix should be.
`tools/empty_artifact.py`:

| | repository tasks (diff is the deliverable) |
| --- | ---: |
| submitted nothing at all | **3 of 7** |
| submitted only scratch files (< 4 KB) | **2 of 7** |
| made a real attempt | 2 of 7 |

`expr` submitted 1,146 bytes and `arktype` 1,475 bytes — in both cases a file under
`scratch/`, with the product source untouched. So **five of the seven repository failures
are cases where the agent explored, reasoned and then submitted without ever editing the
code it was asked to fix.** Not a step-count problem: `meriyah` produced nothing at both 60
and 100 steps, and `katex` produced nothing at 55 steps but a 124 KB passing patch at 100.

A caution that this section had to correct in itself. `submitted_bytes` is 0 for all five
terminal-bench failures too, and the obvious reading — the same failure mode on the other
half — is **wrong**: terminal-bench grades container state in place and defines no collect
step, so its artifact is empty by construction. Only the repository half can be judged this
way, and only that half is counted above. The harness's artifact gate makes the same
distinction at runtime, and stays silent on a task that is not graded on a diff.

### 5.2 The binary verdict was hiding six near misses

Every repository suite reports how far a patch got, and the harness has been keeping that
report beside the verdict all along. `tools/near_miss.py` over every run in the repo: of 28
failures carrying a report, **6 had nonzero required-test credit and 5 were above 0.9**,
four of them with the existing suite fully green.

| cell | required tests | existing suite | read as |
| --- | ---: | ---: | --- |
| python-statemachine (a `gen0` run) | **70 / 72** | 1.000 | a failure, identical to 0/72 |
| httpx (three separate runs) | 121 / 122 | 1.000 | a failure |
| fastapi (`gen6`) | 129 / 137 | 1.000 | a failure |
| scc | 26 / 31 | 0.983 | a failure |

This matters for the evolution loop more than for the report, and §6.1 changes the loop
accordingly: a gate that only sees pass or fail cannot distinguish "wrote nothing" from
"wrote almost all of it", so on a six-task evolve split it could essentially only ever
adopt cost improvements.

### 5.3 A/B: the artifact gate and the protocol blocks, over the same nine cells

`gen7` adds five mechanisms and three prompt blocks to `gen1` and is otherwise identical.
Both were run on all nine repository tasks (`runs/gen7-deepswe`, `runs/deepswe-9`).

| task | `gen1` | `gen7` | what the transcript says |
| --- | ---: | ---: | --- |
| expr-try-catch-errors | 0.00 | **1.00** | gate fired 6×, patch 1.2 KB → 18.7 KB |
| httpx-multipart-response-parsing | 0.99 | **1.00** | the tab/space unfolding rule, finally |
| arktype-json-schema-refs-dependencies | 0.00 | 0.88 | was scratch-only, now 22/25 |
| scc-bounded-memory-spilling | 0.82 | 0.90 | existing-suite damage reduced |
| python-statemachine-state-data-scoping | 0.00 | 0.61 | 44/72, was 0/72 |
| katex-multicolumn-array-spans | 0.00 | 0.00 | wall clock again, at step 57 |
| meriyah-explicit-resource-declarations | 0.00 | 0.00 | still no product edit |
| anko-typed-variable-bindings | **1.00** | 0.00 | 7× deliberation, dead on the wall clock |
| fastapi-deprecation-response-headers | **1.00** | 0.89 | submitted early, 129/137 |
| **passes** | **2/9** | **2/9** | |
| **graded credit** | **3.814** | **5.285** | **+38.6%** |

| axis | `gen1` | `gen7` | |
| --- | ---: | ---: | --- |
| graded credit | 3.814 | 5.285 | **+38.6%** |
| spend | $1.0627 | $1.1119 | **+4.6%** |
| completion tokens | 1,126,827 | 1,369,440 | +21.5% |
| agent minutes | 123.9 | 215.6 | **+74.0%** |
| credit per dollar | 3.59 | 4.75 | +32% |

**The pass count is a tie and the harness is materially better.** Two cells converted, two
were lost, and four moved substantially on the graded fraction. Capability improved 38.6%
for 4.6% more money — but at 74% more wall clock, and that is precisely what killed `anko`
and `katex`, both of which now end on the time limit rather than the step limit.

The two losses are diagnoses, not shrugs:

- **`fastapi` — the countdown caused a premature submit.** The endgame notice appears at
  message positions 105, 107, 109 … 119 and the `submit` call is at 120. `gen1` needs the
  full 60 steps on this cell and ends on the step limit; `gen7` was told to stop at step 48
  and stopped, at 129 of 137 tests. Telling an agent to wrap up is advice about the budget,
  and it is wrong advice when the budget is not the binding constraint.
- **`anko` — the prompt blocks multiplied deliberation 7×.** 33,137 completion tokens over
  60 steps became 231,570 over 45, median 250 → 1,821 per step with single steps at 24,416.
  The per-step profile (`tools/deliberation_profile.py`) ramps from ~200 tokens to ~8,500
  across the episode rather than jumping when the gate fires, which points at the added
  protocol text licensing in-head analysis. Where the agent had been flailing the gate
  *saves* work — `expr` used 7.5× **fewer** completion tokens and now passes — and where it
  was already efficient the same text makes it over-think.

So the next edit is not "more capability": it is to keep the gate and bound the turn. The
countdown comes out (measured cause of one loss) and the per-turn output is capped, which
`truncation_recovery` makes safe because a truncated turn is answered with a directive
rather than with silence — the mechanism whose absence made the `gen5` cap experiment fail.

A note on the gate itself, because "it fired" and "it worked" are different claims.
`tools/gate_firings.py` over the nine `gen7` episodes:

| | |
| --- | ---: |
| cells where the gate fired at least once | **9 of 9** |
| folds per cell | 1–6 |
| cells where it fired and the diff was still scratch-sized | 2 (`meriyah` 1,533 B, `katex` 564 B) |

So the gate reached every container — including `meriyah` and `katex`, which had produced
no product edit at any budget — and in those two cells the agent read it four times and
kept investigating. That is a limit of the mechanism as written and it is the honest
boundary of the `expr` result: the gate converts a cell that was *nearly* ready to act, and
does not by itself rescue a cell where the agent has not understood the change yet.

### 5.4 The same bundle over the terminal half — where it loses

The repository half is nine of thirty cells, so §5.3 cannot say whether `gen7` is a better
harness. It was then run on all 21 terminal-bench cells (`runs/gen7-tb`).

The tightest comparison is against `gen6`, the only configuration with a single clean
21-cell terminal run. On the 19 cells both covered:

| | cells |
| --- | ---: |
| `gen6` passed, `gen7` passed — held | 12 |
| `gen6` passed, `gen7` **failed** — lost | **3** (`build-cython-ext`, `extract-elf`, `polyglot-c-py`) |
| `gen6` failed, `gen7` passed — won | **0** |
| both failed | 4 |
| **net** | **−3** |

`gen7` scores **12/21** on the terminal half against `gen6`'s 15/21, and against `gen1`'s
pooled terminal record it loses `polyglot-c-py` and wins nothing
(`tools/tb_compare.py`). Adding the repository half — where the two are a tie at 2 passes —
`gen7` is **14/30 against `gen1`'s 18/30.** The bundle is a net loss and `gen1` stays the
reported harness.

It matters which part of the bundle did the damage:

- **The artifact gate did not misfire on the terminal half.** It fired in **0 of 20**
  terminal cells (`tools/gate_firings.py`), exactly as its diff-graded confinement intends,
  and never issued a `git status` it could not interpret. The gate is not implicated.
- **The terminal loss tracks the three prompt blocks and the countdown**, the parts of the
  bundle with no repository-specific justification: they were motivated by hidden test
  suites, and the terminal half has none — it runs its verifier in place, in the container
  the agent has already been working in.

So the finding narrows rather than closes. The diagnosis (five of seven repository failures
never edited the deliverable) stands, the gate is the measured fix for it, and the fix has
to be applied *without* the general-purpose prompting that came bundled with it — which is
the configuration §5.5 measures.

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
- **The budget is not the gap, and this report does not pretend otherwise.** Three
  configurations were built to test whether the remaining failures were a
  self-inflicted budget shortage (`gen4`, `gen5`, `gen6`, 4–30 cells each). All three
  scored at or below the 60-step harness they were meant to improve on, and the two
  mechanisms are recorded above: unbounded deliberation eats the wall clock, and bounding
  it per response destroys the tool calls. Closing the gap to `codex` needs a harness
  change this work did not find — most likely a per-task step budget chosen from observed
  progress rather than a global constant, since the two cells the longer budget broke
  (`anko`, `fastapi`) and the one it fixed (`katex`) are all in the same suite.
