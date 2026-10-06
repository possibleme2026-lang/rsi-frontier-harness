"""Token accounting.

Every number this project reports about money is derived here from *measured*
token counts and a declared rate card.  Two rules keep that honest:

1. The rate card is data, not code.  ``pricing.json`` states its source; the
   FrontierHarness frozen Kimi K3 table is kept beside ours so a baseline can be
   re-priced from published token counts instead of being quoted from memory.
2. Missing measurements stay missing.  A call with no usage payload contributes
   ``None``, never zero; ``price()`` returns ``None`` rather than a partial sum.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..config import PROJECT_ROOT


@dataclass(frozen=True)
class RateCard:
    fresh_input: float
    cache_write: float
    cache_read: float
    output: float
    currency: str = "USD"
    unit_tokens: int = 1_000_000
    source: str = ""

    def price(self, usage: "Usage") -> float | None:
        if usage.prompt_tokens is None or usage.completion_tokens is None:
            return None
        cached = usage.cached_tokens or 0
        fresh = max(0, (usage.prompt_tokens or 0) - cached)
        write = usage.cache_write_tokens or 0
        total = (
            fresh * self.fresh_input
            + cached * self.cache_read
            + write * self.cache_write
            + (usage.completion_tokens or 0) * self.output
        )
        return total / self.unit_tokens


@dataclass
class Usage:
    """One model call's measured usage.  ``None`` means 'not reported'."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None

    def add(self, other: "Usage") -> "Usage":
        def plus(a: int | None, b: int | None) -> int | None:
            if a is None and b is None:
                return None
            return (a or 0) + (b or 0)

        return Usage(
            prompt_tokens=plus(self.prompt_tokens, other.prompt_tokens),
            completion_tokens=plus(self.completion_tokens, other.completion_tokens),
            cached_tokens=plus(self.cached_tokens, other.cached_tokens),
            cache_write_tokens=plus(self.cache_write_tokens, other.cache_write_tokens),
            reasoning_tokens=plus(self.reasoning_tokens, other.reasoning_tokens),
        )

    def as_dict(self) -> dict[str, int | None]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "reasoning_tokens": self.reasoning_tokens,
        }

    @property
    def cache_hit_rate(self) -> float | None:
        if not self.prompt_tokens:
            return None
        return (self.cached_tokens or 0) / self.prompt_tokens


@dataclass
class CostLedger:
    """Accumulates calls for one episode."""

    card: RateCard
    calls: int = 0
    usage: Usage = field(default_factory=Usage)
    missing_usage_calls: int = 0
    per_call: list[dict] = field(default_factory=list)

    def record(self, usage: Usage, *, label: str = "agent") -> float | None:
        self.calls += 1
        cost = self.card.price(usage)
        if usage.prompt_tokens is None and usage.completion_tokens is None:
            self.missing_usage_calls += 1
        self.usage = self.usage.add(usage)
        self.per_call.append(
            {"label": label, "cost_usd": cost, **usage.as_dict()}
        )
        return cost

    @property
    def complete(self) -> bool:
        return self.missing_usage_calls == 0

    def cost_usd(self) -> float | None:
        if not self.complete:
            return None
        return self.card.price(self.usage)

    def as_dict(self) -> dict:
        return {
            "model": self.card.source,
            "calls": self.calls,
            "usage": self.usage.as_dict(),
            "cache_hit_rate": self.usage.cache_hit_rate,
            "cost_usd": self.cost_usd(),
            "usage_complete": self.complete,
            "missing_usage_calls": self.missing_usage_calls,
            "rate_card": {
                "fresh_input": self.card.fresh_input,
                "cache_write": self.card.cache_write,
                "cache_read": self.card.cache_read,
                "output": self.card.output,
                "unit_tokens": self.card.unit_tokens,
                "currency": self.card.currency,
                "source": self.card.source,
            },
        }


def load_price_book(path: Path | None = None) -> dict:
    path = path or Path(os.environ.get("RSIH_PRICE_JSON", str(PROJECT_ROOT / "pricing.json")))
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rate_card(model: str, path: Path | None = None) -> RateCard:
    book = load_price_book(path)
    models = book["models"]
    if model in models:
        entry = models[model]
    else:
        lowered = model.lower()
        match = next((k for k in models if k.lower() == lowered), None)
        if match is None:
            raise KeyError(
                f"no rate card for model {model!r}; add it to pricing.json "
                f"(known: {sorted(models)})"
            )
        entry = models[match]
    return RateCard(
        fresh_input=entry["fresh_input"],
        cache_write=entry["cache_write"],
        cache_read=entry["cache_read"],
        output=entry["output"],
        currency=book.get("currency", "USD"),
        unit_tokens=book.get("unit_tokens", 1_000_000),
        source=f"{model} @ {entry.get('source', 'pricing.json')}",
    )


def baseline_rate_card(name: str, path: Path | None = None) -> RateCard:
    book = load_price_book(path)
    entry = book["baseline_models"][name]
    return RateCard(
        fresh_input=entry["fresh_input"],
        cache_write=entry["cache_write"],
        cache_read=entry["cache_read"],
        output=entry["output"],
        currency=book.get("currency", "USD"),
        unit_tokens=book.get("unit_tokens", 1_000_000),
        source=entry.get("source", name),
    )
