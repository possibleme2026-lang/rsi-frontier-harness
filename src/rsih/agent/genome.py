"""The harness as a genome.

The harness is not a file that a human edits between runs.  It is a value: an
ordered list of named prompt blocks, an enabled tool set, and the numeric policy
of the loop (step budget, observation truncation, compaction, submit guard).
Two consequences follow, and both are load-bearing for the RSI loop:

* a change is *named* (``+verify.self_check``) rather than described, so the
  ledger can say which hypothesis was tested;
* a genome has a fingerprint, so a result can never be attributed to a harness
  that was quietly edited afterwards.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import prompts

ALL_TOOLS = ("bash", "read_file", "write_file", "submit")

COMPACTION_MODES = ("none", "truncate", "summarize")
SUBMIT_GUARDS = ("none", "one_shot_reject")


@dataclass(frozen=True)
class Genome:
    id: str
    blocks: tuple[str, ...]
    tools: tuple[str, ...] = ALL_TOOLS
    max_steps: int = 60
    obs_head_chars: int = 4000
    obs_tail_chars: int = 3000
    temperature: float = 0.0
    context_budget_tokens: int = 96_000
    compaction: str = "truncate"
    keep_recent_tool_results: int = 12
    nudge_text_only: int = 2
    bash_timeout_s: float = 240.0
    submit_guard: str = "none"
    #: hard cap on one model response, 0 = provider default. On a reasoning model
    #: this is the difference between a terse action and a page of deliberation that
    #: is billed as output and then never read again.
    max_output_tokens: int = 0
    #: free-text guidance appended after the named blocks. This is the open-ended
    #: part of the search space: the RSI loop may write anything here, and the
    #: ledger records the exact text together with what it measured.
    extra_prompt: str = ""
    #: ordered provenance: parent id, then one label per applied mutation
    lineage: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    # ------------------------------------------------------------- invariants
    def __post_init__(self) -> None:
        if self.compaction not in COMPACTION_MODES:
            raise ValueError(f"compaction must be one of {COMPACTION_MODES}")
        if self.submit_guard not in SUBMIT_GUARDS:
            raise ValueError(f"submit_guard must be one of {SUBMIT_GUARDS}")
        if "submit" not in self.tools:
            raise ValueError("the submit tool is the only way to end an episode; it cannot be disabled")
        if "bash" not in self.tools:
            raise ValueError("bash is the harness's only general actuator; it cannot be disabled")
        unknown = [t for t in self.tools if t not in ALL_TOOLS]
        if unknown:
            raise ValueError(f"unknown tool(s): {unknown}")
        for name in prompts.REQUIRED_BLOCKS:
            if name not in self.blocks:
                raise ValueError(f"required prompt block missing: {name}")
        unknown_blocks = [b for b in self.blocks if b not in prompts.BLOCKS]
        if unknown_blocks:
            raise ValueError(f"unknown prompt block(s): {unknown_blocks}")

    # -------------------------------------------------------------- rendering
    def system_prompt(self) -> str:
        return prompts.render(self.blocks, extra=self.extra_prompt or None)

    def fingerprint(self) -> str:
        payload = {
            "blocks": list(self.blocks),
            "tools": list(self.tools),
            "max_steps": self.max_steps,
            "obs_head_chars": self.obs_head_chars,
            "obs_tail_chars": self.obs_tail_chars,
            "temperature": self.temperature,
            "context_budget_tokens": self.context_budget_tokens,
            "compaction": self.compaction,
            "keep_recent_tool_results": self.keep_recent_tool_results,
            "nudge_text_only": self.nudge_text_only,
            "bash_timeout_s": self.bash_timeout_s,
            "submit_guard": self.submit_guard,
            "max_output_tokens": self.max_output_tokens,
            "extra_prompt": self.extra_prompt,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    # ------------------------------------------------------------------- i/o
    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "blocks": list(self.blocks),
            "tools": list(self.tools),
            "max_steps": self.max_steps,
            "obs_head_chars": self.obs_head_chars,
            "obs_tail_chars": self.obs_tail_chars,
            "temperature": self.temperature,
            "context_budget_tokens": self.context_budget_tokens,
            "compaction": self.compaction,
            "keep_recent_tool_results": self.keep_recent_tool_results,
            "nudge_text_only": self.nudge_text_only,
            "bash_timeout_s": self.bash_timeout_s,
            "submit_guard": self.submit_guard,
            "max_output_tokens": self.max_output_tokens,
            "extra_prompt": self.extra_prompt,
            "lineage": list(self.lineage),
            "notes": self.notes,
            "fingerprint": self.fingerprint(),
        }
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Genome":
        known = {
            "id",
            "blocks",
            "tools",
            "max_steps",
            "obs_head_chars",
            "obs_tail_chars",
            "temperature",
            "context_budget_tokens",
            "compaction",
            "keep_recent_tool_results",
            "nudge_text_only",
            "bash_timeout_s",
            "submit_guard",
            "max_output_tokens",
            "extra_prompt",
            "lineage",
            "notes",
        }
        payload = {k: v for k, v in data.items() if k in known}
        payload["blocks"] = tuple(payload.get("blocks", ()))
        payload["tools"] = tuple(payload.get("tools", ALL_TOOLS))
        payload["lineage"] = tuple(payload.get("lineage", ()))
        return cls(**payload)

    def derive(self, new_id: str, *, mutation: str, **changes) -> "Genome":
        """Return a child genome; ``mutation`` is recorded in the lineage."""
        child = replace(self, id=new_id, lineage=self.lineage + (f"{self.id}:{mutation}",), **changes)
        return child


def default_genome(genome_id: str = "gen0") -> Genome:
    """The hand-written seed.  Everything after it must beat it by measurement."""
    return Genome(
        id=genome_id,
        blocks=(
            "role.engineer",
            "method.loop",
            "tools.bash",
            "errors.recover",
            "budget.brevity",
            "submit.contract",
        ),
        tools=ALL_TOOLS,
        notes="seed harness: minimal bash loop, no self-verification block",
    )


class GenomeLibrary:
    """Genomes persisted as one JSON file each, so a run can name its harness."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, genome_id: str) -> Path:
        return self.root / f"{genome_id}.json"

    def save(self, genome: Genome) -> Path:
        path = self.path_for(genome.id)
        path.write_text(json.dumps(genome.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def load(self, genome_id: str) -> Genome:
        path = self.path_for(genome_id)
        if not path.is_file():
            raise FileNotFoundError(f"unknown genome {genome_id!r} at {path}")
        return Genome.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))
