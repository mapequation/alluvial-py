"""Replay the v4 fixtures (``tests/fixtures/v4``): ``module_order`` (the ``moduleOrder`` macro, recorded as concrete
``moveModule`` ops), ``module_names`` (``setModuleName`` ops) and round trips through the web-app files
(tools/ts-fixtures/README.md "v4 scenarios", docs/dev/port-notes/v4-names-order.md).

- Every fixture's final store state is dumped and compared bit for bit, as the v3 fixtures.
- ``moduleOrder`` macros: ``DiagramStore.apply_module_order`` on the pre-macro state issues exactly the recorded ops.
- Every fixture is reproduced through public ``layout()`` arguments (``module_order``, ``module_names`` and the
  v2 keywords), and the round trips through ``save_diagram``.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES_DIR, TESTS_DIR, assert_matches, load_fixture
from helpers_geometry import geometry_from_fixture
from test_engine_fixtures import read_fixture_inputs
from test_geometry import _assert_geometry_equal
from test_v3_fixtures import _check_dump, _check_round_trip, replay_v3

from alluvial import layout, save_diagram
from alluvial.engine import DiagramStore
from alluvial.geometry import build_geometry
from alluvial.layout import LayoutOptions

V4_DIR = FIXTURES_DIR / "v4"
V4_SCENARIOS = sorted(p.stem for p in V4_DIR.glob("*.json"))
ROUND_TRIPS = [s for s in V4_SCENARIOS if s.endswith("__roundTrip")]
# Scenarios whose op order layout() cannot express (replayed and dumped, but not rebuilt from layout() arguments).
NOT_LAYOUT_ORDER = {"hlskip-tree__default__namesOrderRecolor"}

_COLOR_OPS = {
    "colorMatchingModulesInAllNetworks": "similarity",
    "colorModuleIdsInAllNetworks": "module_id",
    "colorNodesInModulesInAllNetworks": "nodes",
}


def _load(name: str) -> dict[str, Any]:
    return load_fixture(V4_DIR / f"{name}.json")


def test_v4_fixture_set() -> None:
    assert len(V4_SCENARIOS) >= 14
    assert len(ROUND_TRIPS) >= 4
    features = {f for s in V4_SCENARIOS for f in _load(s).get("features", ())}
    assert {"move", "names", "roundTrip", "hierarchy", "highlight"} <= features


@pytest.mark.parametrize("name", V4_SCENARIOS)
def test_v4_fixture(name: str) -> None:
    fx = _load(name)
    store, trace, files, inputs = replay_v3(fx)
    _check_dump(store, trace, inputs, files, fx)


@pytest.mark.parametrize("name", ROUND_TRIPS)
def test_v4_round_trip(name: str) -> None:
    fx = _load(name)
    store, _, _, _ = replay_v3(fx)
    _check_round_trip(fx, store)


@pytest.mark.parametrize("name", V4_SCENARIOS)
def test_v4_module_order_macro_issues_the_recorded_ops(name: str) -> None:
    fx = _load(name)
    inputs = fx["inputs"]
    ops = inputs["operations"]
    macros = [m for m in inputs.get("macros", ()) if m["op"]["op"] == "moduleOrder"]
    if not macros:
        pytest.skip("no moduleOrder macro")
    store = DiagramStore(LayoutOptions.from_ts(inputs["options"]))
    store.set_networks(read_fixture_inputs(inputs))
    done = 1
    for macro in macros:
        for op in ops[done : macro["atOperation"]]:
            store.apply(op)
        issued = store.apply_module_order((ni, ids) for ni, ids in macro["op"]["order"])
        end = macro["atOperation"] + macro["numOperations"]
        assert issued == ops[macro["atOperation"] : end]
        done = end


def layout_kwargs(fx: dict[str, Any]) -> dict[str, Any]:
    """The ``layout`` arguments that stand for a v4 fixture's ops (every v4 scenario but ``NOT_LAYOUT_ORDER`` keeps
    ``layout``'s order)."""
    inputs = fx["inputs"]
    ops = inputs["operations"]
    macros = {m["atOperation"]: m for m in inputs.get("macros", ())}
    kwargs: dict[str, Any] = {"identifier": inputs["identifier"], "colors": None}
    names: dict[tuple[int, str], str] = {}
    stage = 0  # 0: expand, 1: module level, 2: colour/highlight, 3: order, 4: names
    i = 1
    while i < len(ops):
        macro = macros.get(i)
        if macro is not None:
            op = macro["op"]
            if op["op"] == "moduleLevel" and stage <= 1:
                kwargs["module_level"] = op["levels"]
                stage = 2
            elif op["op"] == "highlight" and stage <= 2:
                kwargs["highlight"] = {label: ids for label, ids in op["groups"]}
                kwargs["highlight_colors"] = op["colors"]
                del kwargs["colors"]
                stage = 3
            elif op["op"] == "moduleOrder" and stage <= 3:
                kwargs["module_order"] = {
                    ni: [... if m == "..." else m for m in ids] for ni, ids in op["order"]
                }
                stage = 4
            else:
                raise AssertionError(f"not expressible: macro {op}")
            i += macro["numOperations"]
            continue
        op = ops[i]
        if op["op"] in _COLOR_OPS and stage <= 2:
            kwargs["colors"] = _COLOR_OPS[op["op"]]
            stage = 3
        elif op["op"] == "setModuleName":
            names.pop(
                (op["networkIndex"], op["moduleId"]), None
            )  # a rename moves to the end, as the op order
            names[(op["networkIndex"], op["moduleId"])] = op["name"]
            stage = 4
        else:
            raise AssertionError(f"not expressible: {op}")
        i += 1
    if names:
        kwargs["module_names"] = names
    return kwargs


def _paths(fx: dict[str, Any]) -> list[str]:
    return [str(TESTS_DIR / f) for f in fx["inputs"]["files"]]


@pytest.mark.parametrize("name", V4_SCENARIOS)
def test_layout_reproduces_v4_fixture(name: str) -> None:
    if name in NOT_LAYOUT_ORDER:
        pytest.skip("colour ops after module order and names: not a layout() step order")
    fx = _load(name)
    kwargs = layout_kwargs(fx)
    options = LayoutOptions.from_ts(fx["inputs"]["options"])
    geom = layout(_paths(fx), **kwargs, **vars(options))
    _assert_geometry_equal(dataclasses.replace(geom, highlight_labels=()), geometry_from_fixture(fx))
    store, _, _, _ = replay_v3(fx)
    expected = build_geometry(store.diagram, store.options, palette=tuple(store.highlight_colors))
    res = assert_matches(dataclasses.replace(geom, highlight_labels=()).to_dict(), expected.to_dict())
    assert res.non_bitwise == 0
    named = {(m.network_index, m.id): m.name for n in geom.networks for m in n.modules if m.name}
    assert named == {
        (i, m["moduleId"]): m["label"]["customName"]
        for i, n in enumerate(fx["networks"])
        for m in n["modules"]
        if m["visible"] and m["label"]["customName"]
    }


def _as_fixture_save(text: str) -> str:
    """A ``save_diagram`` text with the generator and the save id the fixture harness pins."""
    text = re.sub(r'"generator": "alluvial \(Python\) [^"]*"', '"generator": "fixture"', text, count=1)
    return re.sub(r'"saveId": "[0-9a-f]{8}"', '"saveId": "fixture"', text, count=1)


@pytest.mark.parametrize("name", ROUND_TRIPS)
@pytest.mark.parametrize("loose", [False, True])
def test_save_diagram_reproduces_v4_round_trip(name: str, loose: bool, tmp_path: Path) -> None:
    """The public ``save_diagram`` writes the TS ``serializeDiagram`` texts (zip by default, or loose files)."""
    import zipfile

    fx = _load(name)
    kwargs = layout_kwargs(fx)
    options = LayoutOptions.from_ts(fx["inputs"]["options"])
    with _no_warning():
        out = save_diagram(_paths(fx), tmp_path / "web", loose=loose, **kwargs, **vars(options))
    if loose:
        assert out == tmp_path / "web"
        saved = [(p.name, p.read_text(encoding="utf-8")) for p in sorted(out.iterdir())]
    else:
        assert out == tmp_path / "web.zip"
        with zipfile.ZipFile(out) as zf:
            saved = [(info.filename, zf.read(info).decode("utf-8")) for info in zf.infolist()]
    assert [(n, _as_fixture_save(t)) for n, t in saved] == [(t["name"], t["text"]) for t in fx["savedFiles"]]


class _no_warning:
    def __enter__(self) -> None:
        import warnings

        self._cm = warnings.catch_warnings()
        self._cm.__enter__()
        warnings.simplefilter("error")

    def __exit__(self, *exc: object) -> None:
        self._cm.__exit__(*exc)


# --- reading a saved diagram's zip (v4-names-order.md §6, saveload-plan.md §4.5) ---------------------------------


@pytest.mark.parametrize("name", ROUND_TRIPS)
def test_read_zip_equals_the_ts_open_of_the_saved_files(name: str, tmp_path: Path) -> None:
    """``read`` of a zip of ``savedFiles`` + ``open_networks`` gives what the web app opens (``savedReload``), and
    ``layout`` of the zip restores the same diagram."""
    import zipfile

    from test_engine_fixtures import Trace

    from alluvial import read
    from alluvial.io import serialize_diagram

    fx = _load(name)
    path = tmp_path / "web.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for t in fx["savedFiles"]:
            zf.writestr(t["name"], t["text"])
    files = read(path)
    assert isinstance(files, list)
    assert [f.id for f in files] == [t["name"].removesuffix(".json") for t in fx["savedFiles"]]
    web = fx["savedReload"]
    trace = Trace()
    store = DiagramStore(LayoutOptions(), trace=trace)
    assert store.open_networks(files) == web["restored"]["openWarnings"]
    _check_dump(store, trace, web["inputs"], files, web)
    assert serialize_diagram(store, generator="fixture", save_id="fixture") == [
        (t["name"], t["text"]) for t in fx["savedFiles"]
    ]
    expected = build_geometry(store.diagram, store.options, palette=tuple(store.highlight_colors))
    res = assert_matches(layout([path]).to_dict(), expected.to_dict())
    assert res.non_bitwise == 0
    assert layout([path]) == layout(read(path))


def test_read_zip_skips_and_rejects(tmp_path: Path) -> None:
    import zipfile

    from alluvial import read

    data = TESTS_DIR / "data"
    path = tmp_path / "mixed.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("nets/", "")
        zf.writestr("nets/a.tree", (data / "multilevel_t0.tree").read_text())
        zf.writestr("__MACOSX/nets/._a.tree", "junk")
        zf.writestr("nets/readme.txt", "hello")
        zf.writestr("nets/b.ftree", (data / "planted_t0.ftree").read_text())
    with pytest.warns(UserWarning, match=r"skipped 1 entry .*readme\.txt"):
        files = read(path)
    assert [(f.id, f.name, f.format) for f in files] == [
        ("a", "nets/a.tree", "tree"),
        ("b", "nets/b.ftree", "ftree"),
    ]

    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("x.txt", "x")
    with pytest.warns(UserWarning), pytest.raises(ValueError, match="holds no network files"):
        read(empty)
    bad = tmp_path / "bad.zip"
    bad.write_text("not a zip")
    with pytest.raises(ValueError, match="not a readable zip"):
        read(bad)
    with pytest.raises(ValueError, match="do not apply to a zip"):
        read(path, name="x")
