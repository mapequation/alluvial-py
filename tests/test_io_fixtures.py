"""Parser parity: every dataset parsed by alluvial.io reproduces the TS fixture's per-network file stats and leaves."""

from __future__ import annotations

import warnings
from functools import cache

import pytest
from conftest import TESTS_DIR, V1_SCENARIOS, load_fixture

from alluvial.io import NetworkFile, read
from alluvial.tree_path import TreePath


@cache
def _read(rel_path: str, identifier: str) -> NetworkFile:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return read(TESTS_DIR / rel_path, identifier=identifier)


def _leaf_rows(nf: NetworkFile) -> list[list]:
    rows = []
    for n in nf.nodes:
        tp = TreePath(n.path)
        rows.append(
            [n.identifier, n.id, n.state_id, tp.ancestor_at_level_as_string(1), 1, not tp.is_significant(0)]
        )
    return sorted(rows, key=repr)


def _without_highlight(rows: list[list]) -> list[list]:
    return sorted(([*r[:5], r[6]] for r in rows), key=repr)


@pytest.mark.parametrize("name", V1_SCENARIOS)
def test_parsed_files_match_fixture(name: str) -> None:
    fx = load_fixture(name)
    identifier = fx["inputs"]["identifier"]
    assert len(fx["networks"]) == len(fx["inputs"]["files"])
    for i, (rel, net) in enumerate(zip(fx["inputs"]["files"], fx["networks"], strict=True)):
        nf = _read(rel, identifier)
        assert nf.id == fx["inputs"]["networkIds"][i]
        assert nf.name == fx["inputs"]["networkNames"][i]
        assert nf.format == fx["inputs"]["formats"][i]
        actual_file = {
            "path": rel,
            "format": nf.format,
            "numTopModules": nf.num_top_modules,
            "numLevels": nf.num_levels,
            "isStateNetwork": nf.is_state_network,
            "directed": nf.directed,
            "codelength": nf.codelength,
            "numNodes": len(nf.nodes),
        }
        assert actual_file == net["file"]
        identifiers = [n.identifier for n in nf.nodes]
        unique = len(set(identifiers)) == len(identifiers)
        assert unique == net["identifiersUnique"]
        file_rows = _leaf_rows(nf)
        engine_rows = _without_highlight(net["leaves"])
        if unique or len(file_rows) == len(engine_rows):
            assert file_rows == engine_rows
        else:
            # With duplicate identifiers the engine may drop leaves (TS parity): every engine
            # leaf must still be one of the parsed file nodes.
            remaining = [repr(r) for r in file_rows]
            for row in engine_rows:
                remaining.remove(repr(row))
