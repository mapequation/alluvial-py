"""Run the doctest examples of the public modules: the API reference renders them, so they stay a single source of
truth that cannot go stale."""

from __future__ import annotations

import doctest
import importlib
import sys

import pytest

# The modules that define the objects of ``alluvial.__all__`` (doctest.testmod only collects the objects a module
# defines itself).
MODULES = [
    "alluvial.geometry",
    "alluvial.io",
    "alluvial.io._partition",
    "alluvial.io.multilayer",
    "alluvial.io.types",
    "alluvial.layout",
    "alluvial.mpl",
]


def test_modules_cover_all():
    import alluvial

    defined_in = {
        getattr(alluvial, name).__module__ for name in alluvial.__all__ if callable(getattr(alluvial, name))
    }
    assert defined_in <= set(MODULES)


@pytest.mark.parametrize("name", MODULES)
def test_doctests(name, tmp_path, monkeypatch):
    if name in ("alluvial.mpl", "alluvial.io._partition"):
        pytest.importorskip("matplotlib" if name == "alluvial.mpl" else "pandas")  # plots / from_dataframe
    if name == "alluvial.mpl":
        import matplotlib

        matplotlib.use("Agg")
    monkeypatch.chdir(tmp_path)  # examples that write files write them here
    module = importlib.import_module(name)
    try:
        result = doctest.testmod(module, optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE)
    finally:
        if "matplotlib.pyplot" in sys.modules:
            import matplotlib.pyplot as plt

            plt.close("all")
    assert result.attempted > 0
    assert result.failed == 0
