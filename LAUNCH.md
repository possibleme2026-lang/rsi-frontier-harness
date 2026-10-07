# Launch post

A thread for X/Twitter, and a single-post version. Every number here is one this
repository measured or read from the eval's own results file — the honest decomposition in
posts 3–4 is the point, not a footnote. Character counts are checked by
`tools/check_post.py`.

---

## Thread (English)

**1/8**

I built a coding agent from scratch and ran it on all 30 FrontierHarness Eval tasks.

18/30 solved. $1.77 total. $0.098 per solved task.

Codex got 20/30 for $69.37.

Then I re-priced my own tokens on their card, and the honest version is better than the
shiny one. 🧵

**2/8**

Same 30 tasks, same verifiers, one config, all 30 cells run. 🟢

60.0% pass rate — level with pi-responses, dsh-ptc and dsh-standard — at $0.098 per
solved task instead of $1.05–$18.34.

The x axis needed two extra decades to fit me.

**3/8**

Now the part every benchmark thread skips.

Those baselines ran Kimi K3 at $3/$15 per 1M. I ran DeepSeek-V4.1-Flash at $0.28/$0.42.

So I re-priced my own tokens on THEIR card: $2.24 per pass.

Still cheapest of the 12 — but only 1.09x ahead of pi-responses, 1.55x ahead of codex.

**4/8**

That means ~90% of the 35x is the model's price, not my harness.

What the harness actually buys:
· 0.81M input tokens/task vs codex's 4.70M
· and NOT cache magic — codex caches better (99.1% vs 96.0%)
· and I burn 4x more output tokens (79% of it is reasoning)

**5/8**

The agent is also self-improving: 22 catalogue mutations, an LLM analyst that reads
failures + cost records, and a gated hill-climb that only accepts a child if the
improvement beats z·√(b+c).

It accepted one change: 18% cheaper.

On the holdout that shrank to 9.5%, t = −0.64.

**6/8**

And when I replayed the gate against the new evidence, 2 of its 4 decisions flipped.

Capability never evolved: the pass floor needs 5 net flips on a 6-task split — unreachable
there. Cost evolved, and even that was over-attributed.

Negative results, same volume as the good ones.

**7/8**

The obvious next move was "give it more steps."

I tried it 3 ways, 64 extra cell-runs. All three scored at or below the 60-step harness,
and matching 18/30 cost 20% MORE.

Unbounded, it burns 138s thinking in one step. Capped, the cap eats its tool calls.

**8/8**

Receipts, including everything that didn't work: 30/30 cells, per-trial llm-calls.jsonl,
every dollar recomputed from raw token counts. 27 tests.

github.com/possibleme2026-lang/rsi-frontier-harness

One ask: re-price your tokens on the baseline's card before you tweet a multiple.

---

## Thread (中文)

**1/8**

我从零写了一个 coding agent，跑完 FrontierHarness Eval 全部 30 个任务。

18/30。总花费 $1.77。每次通过 $0.098。

codex 是 20/30，花了 $69.37。

然后我把自己的 token 按**他们的价目表**重算了一遍——诚实的版本比漂亮的那个更值钱。🧵

**2/8**

同一套 30 题、同一套验证器，单一配置，30 格全跑。🟢

通过率 60.0%，和 pi-responses、dsh-ptc、dsh-standard 持平，而每次通过成本是 $0.098 而不是
$1.05–$18.34。

那张图的 x 轴为了装下我，多延了两个数量级。

**3/8**

下面是每个榜单贴都会跳过的那部分。

那些基线用的是 Kimi K3，$3/$15 每 1M。我用的 DeepSeek-V4.1-Flash 是 $0.28/$0.42。

所以我把**自己实测的 token** 按**他们的卡**重算：$2.24 每次通过。

仍然是 12 个配置里最便宜——但只领先 pi-responses 1.09 倍、领先 codex 1.55 倍。

**4/8**

也就是说那个 35 倍里大约九成是模型价格，不是我的 harness。

harness 真正带来的：
· 每题 0.81M 输入 token，codex 是 4.70M
· 靠的不是缓存命中——codex 缓存比我还好（99.1% vs 96.0%）
· 而且我的输出 token 是它的 4 倍（其中 79% 是推理）

**5/8**

这个 agent 还会自我进化：22 个候选变异、一个读失败记录和成本账的 LLM 分析器、一个只有
提升超过 z·√(b+c) 才接受子代的爬山门。

它接受了一个改动：便宜 18%。

在 holdout 上缩到 9.5%，t = −0.64。

**6/8**

而当我把新证据回放进那道门时，4 个决策里有 2 个直接翻案。

能力始终没有进化——6 题进化集上的通过率门需要净翻转 5 题，那里根本够不到。成本进化了，
连这一条当时也是过度归因。

负面结论，和好消息一样大声。

**7/8**

最显然的下一步是"多给它点步数"。

我试了 3 种，多跑了 64 格。三种全部不高于 60 步的版本，而追平 18/30 要多花 20%。

不设限，它一步就能想 138 秒。设了限，限制会把工具调用一起吃掉。

**8/8**

全部证据，包括所有没成的：30/30 格、每格留着 llm-calls.jsonl、每一个美元都从原始 token
数重算、27 个测试。

github.com/possibleme2026-lang/rsi-frontier-harness

一个请求：在你发推某个倍数之前，先把你的 token 按基线的卡重算一遍。

---

## Single post

I ran a from-scratch coding agent on all 30 FrontierHarness Eval tasks.

18/30 solved for $1.77. Codex: 20/30 for $69.37.

Re-priced on the baselines' own card it's $2.24 per pass — cheapest, but only 1.55x ahead
of codex. ~90% of that 35x is the model's price. 🧵

---

## Long-form (needs X Premium, over 280)

I ran a from-scratch coding agent on all 30 FrontierHarness Eval tasks: 18/30 solved,
$1.77 total, $0.098 per solved task. Codex: 20/30 for $69.37.

Then I re-priced my measured tokens on the baselines' own rate card. $2.24 per pass —
cheapest of the 12, but only 1.55x ahead of codex. ~90% of the 35x is the model's price,
not the harness. The harness's real contribution is 0.81M input tokens per task against
codex's 4.70M, and it isn't cache magic: codex caches better than I do.

Three attempts to buy more score with more steps all failed. Capability never evolved; cost
did, and the holdout cut that claim in half. Everything is auditable and the failures are
documented as loudly as the wins.
