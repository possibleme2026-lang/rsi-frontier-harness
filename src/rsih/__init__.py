"""rsih - a recursively self-improving coding-agent harness.

The package is deliberately organised around three separable concerns:

* ``rsih.llm``   - the frozen model endpoint and its cost accounting
* ``rsih.bench`` - the FrontierHarness-compatible task suite and trial runner
* ``rsih.agent`` - the harness itself, expressed as an evolvable *genome*
* ``rsih.rsi``   - the self-improvement loop that mutates the genome using measured evidence

Nothing in ``rsih.agent`` may import ``rsih.rsi``: the harness has to be runnable
without the loop that improves it, otherwise no measurement could ever be trusted.
"""

__version__ = "0.1.0"
