"""Replay the v3 fixtures (``tests/fixtures/v3``): ``checkColors``, colour schemes and saved diagrams, all against
the real TS code (tools/ts-fixtures/README.md "v3 scenarios").

- Every fixture's final store state is dumped and compared bit for bit (as ``test_engine_fixtures``).
- ``roundTrip`` fixtures: the Python ``serialize_diagram`` texts equal the TS ``serializeDiagram`` texts
  (``savedFiles``) byte for byte, so TS loads exactly what Python writes (Python-save -> TS-load); and the Python
  ``open_networks`` of the loaded files equals the TS ``openNetworks`` (``savedReload``) bit for bit, with the same
  restored options, scheme and warnings (TS-save -> Python-load).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES_DIR, TESTS_DIR, assert_matches, load_fixture
from test_engine_fixtures import IGNORED, Trace, dump_store, read_fixture_inputs

from alluvial._palette import DEFAULT_SCHEME
from alluvial.engine import DiagramStore
from alluvial.io.alluvial_format import (
    DISPLAY_OPTION_DEFAULTS,
    serialize_diagram,
    sort_by_saved_position,
)
from alluvial.io.json_reader import _json_name, from_json_dict, parse_json
from alluvial.layout import LayoutOptions

V3_DIR = FIXTURES_DIR / "v3"
V3_SCENARIOS = sorted(p.stem for p in V3_DIR.glob("*.json"))
ROUND_TRIPS = [s for s in V3_SCENARIOS if s.endswith("__roundTrip")]

V3_IGNORED = IGNORED | {
    "savedStore",
    "savedFiles",
    "savedReloadFiles",
    "savedReload",
    "restored",
    "reloadStore",
}
ROUND_TRIP_IGNORED = IGNORED | {"restored"}

#: The fixture harness pins these (tools/ts-fixtures/harness.ts ``SAVE``).
SAVE = {"generator": "fixture", "save_id": "fixture"}

pytestmark = [
    pytest.mark.filterwarnings("ignore:.*identifier.*shared:UserWarning"),
    pytest.mark.filterwarnings("ignore:.*contain ';':UserWarning"),
]


def _load(name_or_path: str | Path) -> dict[str, Any]:
    p = Path(name_or_path)
    return load_fixture(p if p.suffix == ".json" else V3_DIR / f"{name_or_path}.json")


def _ctor_scheme(inputs: dict[str, Any]) -> str:
    # inputs.colorScheme is the scheme at the end; a setSelectedScheme op means the ctor used the default
    if any(op["op"] == "setSelectedScheme" for op in inputs["operations"]):
        return DEFAULT_SCHEME
    return inputs.get("colorScheme", DEFAULT_SCHEME)


def _ctor_color(options: dict[str, Any]) -> dict[str, Any]:
    """The ctor's c3 tone and offset (TS ``colorTone``/``colorOffset``), when given."""
    kwargs: dict[str, Any] = {}
    if "colorTone" in options:
        kwargs["tone"] = options["colorTone"]
    if "colorOffset" in options:
        kwargs["offset"] = options["colorOffset"]
    return kwargs


def replay_v3(fx: dict[str, Any]) -> tuple[DiagramStore, Trace, list[Any], dict[str, Any]]:
    """Replay a v3 fixture. Returns the store, trace, files and the ``inputs`` to dump with."""
    inputs = dict(fx["inputs"])
    trace = Trace()
    kwargs: dict[str, Any] = {"scheme": _ctor_scheme(inputs), "trace": trace, **_ctor_color(inputs)}
    saved = fx.get("savedStore")
    if saved is not None:
        # the store options that the dump does not cover (display options, showBipartiteNodes)
        options = saved["options"]
        kwargs["display_options"] = {k: options[k] for k in DISPLAY_OPTION_DEFAULTS}
        kwargs["show_bipartite_nodes"] = options["showBipartiteNodes"]
        kwargs["default_highlight_color"] = options["defaultHighlightColor"]
    files = read_fixture_inputs(inputs)
    store = DiagramStore(LayoutOptions.from_ts(inputs.get("initialOptions", inputs["options"])), **kwargs)
    store.replay(files, inputs["operations"])
    return store, trace, files, inputs


def _check_dump(
    store: DiagramStore, trace: Trace, inputs: dict[str, Any], files: list[Any], fx: dict[str, Any]
):
    actual = dump_store(store, trace, inputs, files)
    res = assert_matches(actual, fx, ignore=V3_IGNORED)
    assert res.non_bitwise == 0, f"{res.non_bitwise} floats differ from TS in the last bits"


# c3-colors 2.0.1 diverges from @mapequation/c3 2.0.1 in hierarchy() for a module with many sub-modules (seen
# from about 40): last-bit differences of math.hypot/libm against V8's Math.hypot/trig shift the radius, and the
# farthest-point sampling in placeChildren then breaks near-ties the other way, so some sibling colours swap.
# Not patched around here: the fix belongs in a c3-colors release (tests/test_c3_schemes.py has the c3-level case).
C3_WIDE_XFAIL = pytest.mark.xfail(
    strict=True,
    reason="c3-colors 2.0.1 hierarchy() colours wide modules (119 sub-modules) unlike @mapequation/c3 2.0.1",
)
C3_WIDE_SCENARIOS = {"wide-tree__hierarchyLevel2"}


@pytest.mark.parametrize(
    "name", [pytest.param(s, marks=C3_WIDE_XFAIL) if s in C3_WIDE_SCENARIOS else s for s in V3_SCENARIOS]
)
def test_v3_fixture(name: str) -> None:
    fx = _load(name)
    store, trace, files, inputs = replay_v3(fx)
    _check_dump(store, trace, inputs, files, fx)


def open_saved_texts(
    texts: list[tuple[str, str]], reload_store: dict[str, Any] | None = None
) -> tuple[DiagramStore, Trace, list[Any], list[str]]:
    """The web app's open path for saved files: Infomap JSON (stored identifiers win), id = file name without
    ``.json``, the files of one save sorted by position, then ``open_networks`` on a default store (or one with the
    fixture's ``reloadStore`` scheme, tone and offset)."""
    files = []
    for name, text in texts:
        data = parse_json(text)
        network_id = name.removesuffix(".json")
        files.append(
            from_json_dict(data, id=network_id, name=_json_name(data, name), identifier="id", filename=name)
        )
    files = sort_by_saved_position(files)
    trace = Trace()
    kwargs: dict[str, Any] = _ctor_color(reload_store or {})
    if reload_store and "colorScheme" in reload_store:
        kwargs["scheme"] = reload_store["colorScheme"]
    store = DiagramStore(LayoutOptions(), trace=trace, **kwargs)
    warnings = store.open_networks(files)
    return store, trace, files, warnings


def scheme_sha256(store: DiagramStore) -> str:
    """The harness's ``schemeSha256``: sha256 of ``JSON.stringify(store.selectedScheme)``."""
    return hashlib.sha256(json.dumps(store.selected_scheme, separators=(",", ":")).encode()).hexdigest()


def check_saved_reload(fx: dict[str, Any], texts: list[tuple[str, str]]) -> None:
    """Python's open of ``texts`` equals the TS ``savedReload`` (dump, restored options, scheme, warnings)."""
    web = fx["savedReload"]
    w_store, w_trace, w_files, warnings = open_saved_texts(texts, fx.get("reloadStore"))
    actual = dump_store(w_store, w_trace, web["inputs"], w_files)
    res = assert_matches(actual, web, ignore=ROUND_TRIP_IGNORED)
    assert res.non_bitwise == 0, f"{res.non_bitwise} floats differ from TS in the last bits"
    restored = web["restored"]
    assert w_store.get_options() == restored["options"]
    assert w_store.selected_scheme_name == restored["colorScheme"]
    assert w_store.selected_tone == restored["colorTone"]
    # the fixture JSON writes a huge offset as an integer literal; JSON.parse reads the nearest double
    offset = restored["colorOffset"]
    assert w_store.selected_offset == (
        float(offset) if isinstance(offset, int) and abs(offset) > 2**53 else offset
    )
    assert scheme_sha256(w_store) == restored["schemeSha256"]
    assert warnings == restored["openWarnings"]


def _check_round_trip(fx: dict[str, Any], store: DiagramStore) -> None:
    texts = serialize_diagram(store, **SAVE)
    assert texts == [(t["name"], t["text"]) for t in fx["savedFiles"]]
    loaded = fx.get("savedReloadFiles", fx["savedFiles"])
    check_saved_reload(fx, [(t["name"], t["text"]) for t in loaded])


@pytest.mark.parametrize("name", ROUND_TRIPS)
def test_v3_round_trip(name: str) -> None:
    fx = _load(name)
    store, _, _, _ = replay_v3(fx)
    _check_round_trip(fx, store)


def test_schemes_match_ts_dump() -> None:
    from alluvial._palette import DEFAULT_SCHEME, DEFAULT_TONE, SCHEME_GROUPS, SCHEMES

    data = json.loads((TESTS_DIR / "data" / "ts_color_schemes.json").read_text(encoding="utf-8"))
    assert list(SCHEMES) == data["names"]
    assert {k: list(v) for k, v in SCHEMES.items()} == data["schemes"]
    assert {k: list(v) for k, v in SCHEME_GROUPS.items()} == data["groups"]
    assert (data["default"], data["defaultTone"]) == (DEFAULT_SCHEME, DEFAULT_TONE)


# Opt-in: the large v3 fixtures (generate.mjs --large --out DIR writes them to DIR/v3/).
LARGE_DIR = os.environ.get("ALLUVIAL_LARGE_FIXTURES")
LARGE_V3 = sorted((Path(LARGE_DIR) / "v3").glob("*.json")) if LARGE_DIR else []


@pytest.mark.skipif(not LARGE_V3, reason="set ALLUVIAL_LARGE_FIXTURES=DIR (generate.mjs --large --out DIR)")
@pytest.mark.parametrize("path", LARGE_V3, ids=[p.stem for p in LARGE_V3])
def test_v3_large_fixture(path: Path) -> None:
    fx = load_fixture(path)
    store, trace, files, inputs = replay_v3(fx)
    _check_dump(store, trace, inputs, files, fx)
    if "savedFiles" in fx:
        _check_round_trip(fx, store)
