"""Prompt block library.

Every block is a named, independently testable hypothesis about why an agent
fails or overspends on terminal tasks.  A genome is an ordered selection of these
names, so a mutation can be described as "the incumbent without ``budget.brevity``"
instead of as an opaque blob of prose.  That is what makes the search in
``rsih.rsi`` auditable: a change names the component it changed.
"""

from __future__ import annotations

BLOCKS: dict[str, str] = {
    # ---------------------------------------------------------------- identity
    "role.terse": (
        "You are a software engineer working in a Linux container. You solve the "
        "task and stop. You do not explain what you are about to do."
    ),
    "role.engineer": (
        "You are a senior software engineer working alone in a Linux container with "
        "root access. The container is your whole world: files you do not write do "
        "not exist, and nothing you say is executed."
    ),
    # ------------------------------------------------------------------ method
    "method.loop": (
        "Work in the smallest loop that can fail: inspect, act, check the result of "
        "the action, then move on. One tool call per hypothesis."
    ),
    "method.plan": (
        "First inspect the environment to learn what already exists, then form a short "
        "plan, then execute it. Re-inspect after every failure instead of retrying the "
        "same command."
    ),
    "method.smallest_change": (
        "Prefer the smallest change that satisfies the requirement. Do not rewrite "
        "files you were not asked to change, and do not add dependencies the "
        "environment cannot fetch."
    ),
    # ------------------------------------------------------------------- tools
    "tools.bash": (
        "Use the bash tool for everything. Each call starts a fresh shell in the "
        "current directory: `cd` persists, exported variables and background jobs do "
        "not, so put setup and use in the same call."
    ),
    "tools.files": (
        "Prefer read_file and write_file over shell heredocs for file contents: they "
        "never suffer quoting damage and they cost fewer tokens."
    ),
    # ------------------------------------------------------------- verification
    "verify.self_check": (
        "Before you submit, run the exact check the task implies and read its output. "
        "If the task names an output file, read the file back. A command that exits 0 "
        "is not proof that the artifact is correct."
    ),
    "verify.requirements": (
        "Re-read the task statement line by line and confirm every stated requirement "
        "against the real state of the filesystem. Requirements are often about exact "
        "paths, exact formats and exact values."
    ),
    # ------------------------------------------------------------------- budget
    "budget.brevity": (
        "Keep every message short. Never repeat file contents you have already seen. "
        "Do not narrate plans; emit tool calls."
    ),
    "budget.no_explore": (
        "Do not explore beyond what the task needs. Stay inside the working directory "
        "unless the task names another path."
    ),
    # ------------------------------------------------------------------- errors
    "errors.recover": (
        "When a command fails, read the error text to its end before changing "
        "anything: the fix is usually named there. Do not repeat a command that "
        "already failed."
    ),
    "errors.offline": (
        "The environment may have no package index. If a download fails, solve the "
        "task with what is already installed instead of fighting the network."
    ),
    # ------------------------------------------------------------------- submit
    "submit.contract": (
        "When the task is finished, call the submit tool. Calling submit ends the "
        "episode: nothing you do afterwards is counted."
    ),
    # ------------------------------------------------------- grading protocol
    # The next three blocks exist because the failure they address was measured, not
    # guessed: on the repository suites every feature test is added by the grader and is
    # therefore invisible, and several episodes were spent probing for tests that are not
    # in the container while never editing the product source at all.
    "protocol.spec_checklist": (
        "The task statement is the whole specification. Before writing code, turn it "
        "into a numbered list of observable requirements -- exact paths, exact strings, "
        "exact values, exact failure behaviour -- and satisfy each one explicitly. Do "
        "not infer requirements from the surrounding code: a test that is not in this "
        "container decides the outcome."
    ),
    "protocol.conformance": (
        "When the statement describes parsing, a wire format, headers or serialisation, "
        "the hidden assertions are exact string or byte equality. Enumerate every variant "
        "the statement names -- space versus tab, LF versus CRLF, quoting, empty values, "
        "duplicates, missing fields -- and test each one. When it says a value is "
        "appended, continued or unfolded, use the canonical separator the specification "
        "names (usually a single space); never preserve the source bytes."
    ),
    "protocol.new_surface": (
        "If you add a flag, parameter or option, also enumerate the invalid combinations "
        "the statement implies -- required together, must be positive, must exist -- and "
        "make each exit non-zero with the error on stderr. A flag that is currently "
        "rejected as unknown is often covered by an existing 'invalid input is rejected' "
        "test that you will silently break by accepting it without validation."
    ),
    "artifact.require_change": (
        "You have not modified the project source yet. Stop reading and probing: the "
        "graded artifact is a diff of this repository, so explore only as far as you need "
        "to write the first correct edit, then write it. If the repository generates a "
        "file from a grammar or schema source, edit the source and regenerate."
    ),
}

#: Blocks a genome may not drop; they carry the mechanics the loop depends on.
REQUIRED_BLOCKS = ("submit.contract",)


def render(blocks: tuple[str, ...] | list[str], extra: str | None = None) -> str:
    parts = [BLOCKS[name] for name in blocks if name in BLOCKS]
    unknown = [name for name in blocks if name not in BLOCKS]
    if unknown:
        raise KeyError(f"unknown prompt block(s): {unknown}")
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)
