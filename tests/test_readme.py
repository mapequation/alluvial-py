"""Every Python snippet in README.md runs when pasted (from the root of a source checkout)."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SNIPPETS = re.findall(r"```python\n(.*?)```", README.read_text(encoding="utf-8"), flags=re.S)


def test_readme_has_snippets() -> None:
    assert len(SNIPPETS) >= 6


@pytest.mark.parametrize("index", range(len(SNIPPETS)))
def test_readme_snippet_runs(index: int, tmp_path: Path) -> None:
    code = SNIPPETS[index]
    if "import infomap" in code and importlib.util.find_spec("infomap") is None:
        pytest.skip("needs infomap")
    # A fresh process in a scratch folder that looks like a checkout root (files the snippet saves land there).
    (tmp_path / "tests").symlink_to(ROOT / "tests", target_is_directory=True)
    env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONWARNINGS": "ignore"}
    run = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300
    )
    assert run.returncode == 0, run.stderr[-2000:]
