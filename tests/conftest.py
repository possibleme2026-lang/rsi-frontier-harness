from __future__ import annotations

from pathlib import Path

import pytest

from rsih.config import settings


@pytest.fixture(scope="session")
def eval_repo() -> Path:
    path = settings().eval_repo
    if not (path / "results" / "eval-data.json").is_file():
        pytest.skip("published FrontierHarness checkout not present")
    return path


@pytest.fixture(scope="session")
def tb2_repo() -> Path:
    path = settings().tb2_repo
    if not path.is_dir():
        pytest.skip("terminal-bench-2 checkout not present")
    return path
