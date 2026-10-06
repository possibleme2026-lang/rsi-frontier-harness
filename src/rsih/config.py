"""Runtime configuration: paths, endpoint, credentials.

The API key is never hard-coded in a tracked file.  It is read from the
environment, falling back to ``<project>/.env`` (git-ignored), which is how the
operator supplied it.  ``rsih doctor`` prints presence, never the value.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKSPACE = Path(r"D:\codebase\agentharness")


def load_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env reader (KEY=VALUE, ``#`` comments).  Missing file is fine."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


_DOTENV = load_dotenv(PROJECT_ROOT / ".env")


def _get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    return _DOTENV.get(name, default)


@dataclass(frozen=True)
class Settings:
    workspace: Path
    eval_repo: Path
    tb2_repo: Path
    runs_dir: Path
    base_url: str
    api_key: str | None
    model: str
    request_timeout_s: float
    max_retries: int

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


def settings() -> Settings:
    workspace = Path(_get("RSIH_WORKSPACE", str(DEFAULT_WORKSPACE)) or DEFAULT_WORKSPACE)
    return Settings(
        workspace=workspace,
        eval_repo=Path(_get("RSIH_EVAL_REPO", str(workspace / "_ref-frontier-eval"))),
        tb2_repo=Path(_get("RSIH_TB2_REPO", str(workspace / "_ref-tb2"))),
        runs_dir=Path(_get("RSIH_RUNS_DIR", str(PROJECT_ROOT / "runs"))),
        base_url=(_get("TIERFLOW_BASE_URL", "https://tierflow.cn/v1") or "").rstrip("/"),
        api_key=_get("TIERFLOW_API_KEY"),
        model=_get("RSIH_MODEL", "DeepSeek-V4.1-Flash") or "DeepSeek-V4.1-Flash",
        request_timeout_s=float(_get("RSIH_REQUEST_TIMEOUT", "600") or 600),
        max_retries=int(_get("RSIH_MAX_RETRIES", "4") or 4),
    )
