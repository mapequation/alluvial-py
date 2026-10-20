"""Saved diagrams ("alluvial network files", formatVersion 1; docs/dev/saveload-plan.md §7.3).

1. Python-save == TS-save: ``serialize_diagram`` on the replayed store gives the fixture's ``savedFiles`` (the TS
   ``serializeDiagram`` texts) byte for byte. TS therefore opens exactly what Python writes, so the fixtures'
   ``savedReload`` is also the TS load of Python's files (Python-save -> TS-load).
2. TS-save -> Python-load: ``read`` of the TS files as a directory, a zip and a shuffled list of paths, then
   ``open_networks``, equals ``savedReload`` bit for bit (dump, restored options, scheme, warnings).
3. Reload vs original: the same module order, names, colours, levels, options and scheme, and the same geometry up to
   float summation order.
4. The fuzz round trips (``tests/test_fuzz_parity.py``) do 1 and 2 for random cases.
5. A saved file is still plain Infomap JSON, with Infomap's own keys kept.
6. The 2019 saved-diagram format is rejected.
"""

from __future__ import annotations

import copy
import json
import random
import zipfile
from pathlib import Path
from typing import Any

import pytest
from conftest import DATA_DIR, FIXTURES_DIR, assert_matches, load_fixture
from test_engine_fixtures import Trace, dump_store
from test_v3_fixtures import ROUND_TRIP_IGNORED, SAVE, replay_v3

import alluvial
from alluvial.engine import DiagramStore
from alluvial.io import read, serialize_diagram
from alluvial.io.alluvial_format import ALLUVIAL_FORMAT, read_alluvial_metadata
from alluvial.layout import LayoutOptions

ROUND_TRIP_PATHS = sorted(p for d in ("v3", "v4") for p in (FIXTURES_DIR / d).glob("*__roundTrip.json"))
IDS = [f"{p.parent.name}/{p.stem}" for p in ROUND_TRIP_PATHS]

pytestmark = [
    pytest.mark.filterwarnings("ignore:.*identifier.*shared:UserWarning"),
]


def _texts(blocks: list[dict[str, str]]) -> list[tuple[str, str]]:
    return [(t["name"], t["text"]) for t in blocks]


@pytest.fixture(scope="module", params=ROUND_TRIP_PATHS, ids=IDS)
def fx(request: pytest.FixtureRequest) -> dict[str, Any]:
    return load_fixture(request.param)


def test_python_save_equals_ts_save(fx: dict[str, Any]) -> None:
    store, *_ = replay_v3(fx)
    assert serialize_diagram(store, **SAVE) == _texts(fx["savedFiles"])


def _open(files: list[Any]) -> tuple[DiagramStore, Trace, list[str]]:
    trace = Trace()
    store = DiagramStore(LayoutOptions(), trace=trace)
    return store, trace, store.open_networks(files)


@pytest.mark.parametrize("how", ["dir", "zip", "shuffled"])
def test_ts_save_python_load(fx: dict[str, Any], how: str, tmp_path: Path) -> None:
    texts = _texts(fx.get("savedReloadFiles", fx["savedFiles"]))
    expected = fx["savedReload"]["restored"]["openWarnings"]
    if how == "shuffled" and any(
        w.startswith(("the files", "incomplete")) or "formatVersion" in w for w in expected
    ):
        pytest.skip("not one complete save: the files load in the given order")
    if how == "zip":
        source: Any = tmp_path / "diagram.zip"
        with zipfile.ZipFile(source, "w") as zf:
            for name, text in texts:
                zf.writestr(name, text)
    else:
        for name, text in texts:
            (tmp_path / name).write_text(text, encoding="utf-8")
        source = tmp_path
        if how == "shuffled":
            paths = [tmp_path / name for name, _ in texts]
            random.Random(len(paths)).shuffle(paths)
            source = paths
    files = read(source)
    web = fx["savedReload"]
    store, trace, warnings = _open(files)
    res = assert_matches(dump_store(store, trace, web["inputs"], files), web, ignore=ROUND_TRIP_IGNORED)
    assert res.non_bitwise == 0
    assert store.get_options() == web["restored"]["options"]
    assert store.selected_scheme_name == web["restored"]["colorScheme"]
    assert warnings == web["restored"]["openWarnings"]


def _modules(dump: dict[str, Any]) -> list[list[tuple[Any, ...]]]:
    return [
        [
            (
                m["moduleId"],
                m["visible"],
                m["highlightIndex"],
                m["label"]["customName"] if m["label"] else None,
            )
            for m in n["modules"]
        ]
        for n in dump["networks"]
    ]


def test_reload_equals_original(fx: dict[str, Any]) -> None:
    if "savedReloadFiles" in fx:
        pytest.skip("the saved files were edited before the reload")
    web = fx["savedReload"]
    assert web["highlightColors"] == fx["highlightColors"]
    assert [n["name"] for n in web["networks"]] == [n["name"] for n in fx["networks"]]
    assert [n["isCustomSorted"] for n in web["networks"]] == [n["isCustomSorted"] for n in fx["networks"]]
    assert _modules(web) == _modules(fx)
    assert web["restored"]["options"] == fx["savedStore"]["options"]
    assert web["restored"]["colorScheme"] == fx["savedStore"]["colorScheme"]
    assert web["restored"]["openWarnings"] == []
    for n_web, n_fx in zip(web["networks"], fx["networks"], strict=True):
        for m_web, m_fx in zip(n_web["modules"], n_fx["modules"], strict=True):
            if m_fx["visible"]:
                assert m_web["y"] == pytest.approx(m_fx["y"], abs=1e-9)
                assert m_web["height"] == pytest.approx(m_fx["height"], abs=1e-9)


def test_hidden_order_survives_lowering_the_threshold() -> None:
    """``moduleOrder`` lists the hidden modules too: lowering the flow threshold after the reload shows them in the
    same order as in the original session."""
    fx = load_fixture(FIXTURES_DIR / "v3" / "multilevel-tree__flowThreshold40__orderHidden__roundTrip.json")
    store, *_ = replay_v3(fx)
    reloaded, _, warnings = _open(read([*_save_dir(store)]))
    assert warnings == []
    hidden = [[m.module_id for m in n.children if not m.is_visible] for n in store.diagram.children]
    assert any(hidden)
    for s in (store, reloaded):
        s.set_option("flowThreshold", 0)
    assert [[m.module_id for m in n.children] for n in reloaded.diagram.children] == [
        [m.module_id for m in n.children] for n in store.diagram.children
    ]


def _save_dir(store: DiagramStore) -> list[Path]:
    import tempfile

    out = Path(tempfile.mkdtemp())
    paths = []
    for name, text in serialize_diagram(store, generator="test"):
        (out / name).write_text(text, encoding="utf-8")
        paths.append(out / name)
    return paths


def test_saved_file_is_infomap_json() -> None:
    """Infomap's own keys are passed through unchanged, and the file still reads as plain Infomap JSON."""
    fx = load_fixture(FIXTURES_DIR / "v3" / "planted-json__default__passthrough__roundTrip.json")
    for i, t in enumerate(fx["savedFiles"]):
        saved = json.loads(t["text"])
        original = json.loads((DATA_DIR / f"planted_t{i}.json").read_text(encoding="utf-8"))
        for key in (
            "version",
            "args",
            "startedAt",
            "completedIn",
            "codelength",
            "directed",
            "flowModel",
            "modules",
        ):
            assert saved[key] == original[key], key
        assert saved["alluvial"]["format"] == ALLUVIAL_FORMAT
        plain = read({k: v for k, v in saved.items() if k != "alluvial"})
        assert [n.path for n in plain.nodes] == [n["path"] for n in saved["nodes"]]
    # Infomap output itself has no block
    nf = read(DATA_DIR / "planted_t0.json")
    assert nf.alluvial is None
    assert read_alluvial_metadata([nf]).networks == [None]


def test_restore_state_false_ignores_the_block(tmp_path: Path) -> None:
    out = alluvial.save_diagram(
        [DATA_DIR / f"multilevel_t{i}.tree" for i in range(3)],
        tmp_path / "d.zip",
        height=300,
        scheme="Paired",
    )
    assert alluvial.layout([out]).height == 300
    assert alluvial.layout([out], restore_state=False).height == 600


def test_restore_warnings_are_issued(tmp_path: Path) -> None:
    paths = [DATA_DIR / f"multilevel_t{i}.tree" for i in range(3)]
    folder = alluvial.save_diagram(paths, tmp_path / "d", loose=True, height=300)
    first = sorted(folder.iterdir())[:2]
    with pytest.warns(UserWarning, match=r"saved diagram: incomplete save: 2 of 3 networks"):
        geom = alluvial.layout(first)
    assert geom.height == 600  # the options are not restored


def test_2019_format_is_rejected() -> None:
    saved = {"version": "0.3.0", "timestamp": 0, "state": {}, "networks": [{"id": "a", "nodes": []}]}
    with pytest.raises(ValueError, match="2019 saved-diagram format is no longer supported"):
        read(saved)


def test_bipartite_nodes_hidden(tmp_path: Path) -> None:
    paths = [DATA_DIR / f"bipartite_t{i}.json" for i in range(2)]
    shown = alluvial.layout(paths)
    hidden = alluvial.layout(paths, show_bipartite_nodes=False)
    assert [n.flow for n in hidden.networks] != [n.flow for n in shown.networks]
    out = alluvial.save_diagram(paths, tmp_path / "b.zip", show_bipartite_nodes=False)
    assert alluvial.layout([out]).networks[0].flow == hidden.networks[0].flow
    assert alluvial.layout([out], show_bipartite_nodes=True).networks[0].flow == shown.networks[0].flow


def test_open_networks_consumes_the_saved_blocks(tmp_path: Path) -> None:
    """TS ``openNetworks`` (WP9 review): the saved blocks are removed from the files once read, so opening the same
    files again (the web app's Create diagram after a Load networks edit) keeps later changes and does not warn
    about different saves when a plain network is added."""
    fx = load_fixture(ROUND_TRIP_PATHS[0])
    assert not fx["savedReload"]["restored"]["openWarnings"]
    for name, text in _texts(fx["savedFiles"]):
        (tmp_path / name).write_text(text, encoding="utf-8")
    files = read(tmp_path)
    assert all(f.alluvial is not None for f in files)
    store, _, warnings = _open(files)
    assert warnings == []
    assert all(f.alluvial is None for f in files)

    height = store.get_options()["height"]
    store.set_option("height", height + 100)
    store.set_selected_scheme("Paired")
    assert store.open_networks(store.networks) == []
    assert store.get_options()["height"] == height + 100
    assert store.selected_scheme_name == "Paired"

    plain = copy.deepcopy(store.networks[0])
    plain.id = "plain"
    assert store.open_networks([*store.networks, plain]) == []
    assert store.get_options()["height"] == height + 100
