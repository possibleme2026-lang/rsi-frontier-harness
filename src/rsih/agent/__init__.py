"""The harness: genome, prompt blocks, tools, loop.

Lazy imports again, to keep ``rsih.bench`` and ``rsih.agent`` from closing an
import cycle through their package initialisers.
"""

from __future__ import annotations

from typing import Any

__all__ = ["Genome", "GenomeLibrary", "default_genome", "Episode", "Step", "run_episode"]


def __getattr__(name: str) -> Any:  # pragma: no cover - trivial dispatch
    if name in {"Genome", "GenomeLibrary", "default_genome"}:
        from . import genome

        return getattr(genome, name)
    if name in {"Episode", "Step", "run_episode"}:
        from . import loop

        return getattr(loop, name)
    raise AttributeError(name)
