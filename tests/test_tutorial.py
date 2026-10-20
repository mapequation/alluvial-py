"""docs/tutorial.ipynb runs from top to bottom, and the stored copy keeps its outputs."""

from __future__ import annotations

from pathlib import Path

import pytest

nbformat = pytest.importorskip("nbformat")
nbclient = pytest.importorskip("nbclient", reason="needs nbconvert (nbclient) and ipykernel")
pytest.importorskip("ipykernel")
pytest.importorskip("infomap")

NOTEBOOK = Path(__file__).resolve().parents[1] / "docs" / "tutorial.ipynb"


def test_stored_notebook_has_outputs() -> None:
    nb = nbformat.read(NOTEBOOK, as_version=4)
    code = [c for c in nb.cells if c.cell_type == "code"]
    assert all(c.execution_count is not None for c in code), "execute the notebook before committing it"
    images = [o for c in code for o in c.outputs if "image/png" in o.get("data", {})]
    assert len(images) >= 10
    assert not [o for c in code for o in c.outputs if o.output_type == "error"]


def test_notebook_executes(tmp_path: Path) -> None:
    nb = nbformat.read(NOTEBOOK, as_version=4)
    client = nbclient.NotebookClient(
        nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(tmp_path)}}
    )
    client.execute()  # raises CellExecutionError on the first failing cell
    assert (tmp_path / "tutorial_output" / "figure.pdf").stat().st_size > 1000
    printed = "".join(o.get("text", "") for c in nb.cells if c.cell_type == "code" for o in c.outputs)
    assert "module_level is deeper" in printed  # the "Common mistakes" cell shows the warnings
