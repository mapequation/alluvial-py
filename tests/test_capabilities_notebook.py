"""docs/capabilities.ipynb (the tested tour of every public feature) runs from top to bottom without errors or
warnings, and the stored copy keeps its outputs. Its own cells assert the behaviour they show."""

from __future__ import annotations

from pathlib import Path

import pytest

nbformat = pytest.importorskip("nbformat")
nbclient = pytest.importorskip("nbclient", reason="needs nbconvert (nbclient) and ipykernel")
pytest.importorskip("ipykernel")
pytest.importorskip("infomap")

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "docs" / "capabilities.ipynb"


def _outputs(nb):
    return [o for c in nb.cells if c.cell_type == "code" for o in c.outputs]


def test_stored_notebook_has_outputs() -> None:
    nb = nbformat.read(NOTEBOOK, as_version=4)
    code = [c for c in nb.cells if c.cell_type == "code"]
    assert all(c.execution_count is not None for c in code), "execute the notebook before committing it"
    outputs = _outputs(nb)
    assert sum("image/png" in o.get("data", {}) for o in outputs) >= 15
    assert not [o for o in outputs if o.output_type == "error"]
    assert not [o for o in outputs if o.get("name") == "stderr"], "a stored cell printed a warning"


def test_notebook_executes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLUVIAL_DATA", str(ROOT / "tests" / "data"))  # the kernel runs in tmp_path
    nb = nbformat.read(NOTEBOOK, as_version=4)
    client = nbclient.NotebookClient(
        nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(tmp_path)}}
    )
    client.execute()  # raises CellExecutionError on the first failing cell (every section asserts)
    outputs = _outputs(nb)
    assert not [o.text for o in outputs if o.get("name") == "stderr"]  # no warnings escaped
    printed = "".join(o.get("text", "") for o in outputs)
    assert "the 2019 saved-diagram format is no longer supported" in printed  # the error section ran
    assert "visible modules at level 2" in printed  # the last section ran
    assert not list(tmp_path.iterdir())  # it writes only to its own temporary directory, and removes it
