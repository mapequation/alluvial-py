"""Clear errors and warnings for inputs a researcher may feed ``alluvial.read`` (no infomap needed)."""

from __future__ import annotations

import sys
import types
import warnings
from pathlib import Path

import pytest

from alluvial.io import read, read_file
from alluvial.io.infomap_reader import _directed, _version_tuple

QUOTED_TREE = """# v2.15.1
# codelength 1.5 bits
# path flow name node_id
1:1 0.5 "say "hi"" 2
1:2 0.25 "it's fine" 3
2:1 0.25 "Göteborg å 日本" 4
"""


@pytest.mark.parametrize(
    ("suffix", "match"),
    [
        ("net", "input network"),
        ("json", "JSON"),
        ("csv", "CSV"),
        ("nwk", "Newick"),
        ("txt", "unsupported network file format"),
    ],
)
def test_unsupported_formats_have_clear_errors(tmp_path: Path, suffix: str, match: str) -> None:
    path = tmp_path / f"net.{suffix}"
    path.write_text('*Vertices 1\n1 "a"\n')
    with pytest.raises(ValueError, match=match) as info:
        read(path)
    if suffix != "txt":
        assert "write_tree" in str(info.value)


def test_quoted_name_in_tree_file_warns(tmp_path: Path) -> None:
    path = tmp_path / "q.tree"
    path.write_text(QUOTED_TREE, encoding="utf-8")
    with pytest.warns(UserWarning, match="double quote"):
        nf = read(path)
    # The TS parse is kept: the first row loses its id, the others (apostrophe, unicode) are intact.
    assert [n.identifier for n in nf.nodes] == ["NaN", "3", "4"]
    assert [n.name for n in nf.nodes][1:] == ["it's fine", "Göteborg å 日本"]


def test_clean_tree_file_does_not_warn(tmp_path: Path) -> None:
    path = tmp_path / "ok.tree"
    path.write_text(QUOTED_TREE.replace('"say "hi""', '"say hi"'), encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        read_file(path)


def test_old_infomap_object_is_rejected_with_version_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    # infomap < 2.14 has no Result API: no ``_result``, ``run()`` returns None.
    fake = types.ModuleType("infomap")
    fake.__version__ = "2.13.0"
    monkeypatch.setitem(sys.modules, "infomap", fake)
    Legacy = type(
        "Infomap", (), {"__module__": "infomap", "run": lambda self: None, "write_tree": lambda self: None}
    )
    with pytest.raises(TypeError, match=r"infomap 2\.13\.0 is too old.*>= 2\.14"):
        read(Legacy())


def test_directed_flag_across_infomap_versions() -> None:
    class Core:
        def __init__(self, undirected: bool) -> None:
            self.undirected = undirected

        def isUndirectedFlow(self) -> bool:
            return self.undirected

    result = types.SimpleNamespace(_directed=False)  # infomap 2.14: the raw --directed flag
    assert _directed(result, types.SimpleNamespace(_core=Core(False)), "2.14.0") is True
    assert _directed(result, types.SimpleNamespace(_core=Core(True)), "2.14.0") is False
    assert _directed(types.SimpleNamespace(_directed=True), None, "2.15.1") is True
    assert _version_tuple("2.15.1") == (2, 15, 1)
    assert _version_tuple("2.16.0rc1") == (2, 16, 0)
    assert _version_tuple("3.0.0.dev4+g1") == (3, 0, 0)
