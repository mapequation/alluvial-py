"""Differential fuzzing: random inputs/options/colour ops run on the TS store and on the Python port, compared in full.

The cases come from ``tools/ts-fixtures/fuzz/gen.py`` (seeded). The TS side runs through
``node tools/ts-fixtures/generate.mjs --fuzz DIR``, which writes fixture-format JSON per case. The Python side replays
each case exactly like ``test_engine_fixtures`` and compares everything (structure, orders, floats bit-exactly).

By default 30 seeds run (``ALLUVIAL_FUZZ_SEEDS``, starting at ``ALLUVIAL_FUZZ_START``, default 0), once as v1 cases and
once as v2 cases (``gen.py --v2``: the same cases plus hierarchy/move/colour/metadata ops, the ``highlight`` macro,
node metadata, JSON inputs, split layers and odd hierarchies; refusable ops carry the TS ``result``). The ``moduleLevel``
and ``highlight`` macros are replayed through ``apply_module_level``/``apply_highlight``, which must issue the ops TS
recorded. A third set runs the v4 cases (``gen.py --v4``: the v2 cases plus the ``moduleOrder`` and ``moduleNames``
macros and ``setModuleName``, replayed through ``apply_module_order``/``apply_module_names``), and a fourth the c3 cases
(``gen.py --c3``: the v4 cases plus ctor scheme/tone/offset options and the c3 ops ``setSelectedScheme``,
``setSelectedTone``, ``setSelectedOffset`` and ``colorModuleHierarchyInAllNetworks``). Every case also round trips
through the web-app files. Run more with e.g.::

    ALLUVIAL_FUZZ_SEEDS=5000 .venv/bin/pytest -q tests/test_fuzz_parity.py -x
    ALLUVIAL_FUZZ_SEEDS=5000 .venv/bin/pytest -q tests/test_fuzz_parity.py -x -k v2
    ALLUVIAL_FUZZ_SEEDS=5000 .venv/bin/pytest -q tests/test_fuzz_parity.py -x -k v4
    ALLUVIAL_FUZZ_SEEDS=5000 .venv/bin/pytest -q tests/test_fuzz_parity.py -x -k c3

Deselect it with ``-m 'not fuzz'``. The test is skipped when ``node`` or the TS sources (``ALLUVIAL_TS_ROOT``) are unavailable.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from conftest import assert_matches
from test_engine_fixtures import IGNORED, Trace, dump_store, highlight_label_of
from test_v3_fixtures import ROUND_TRIP_IGNORED, SAVE, _check_round_trip, open_saved_texts, scheme_sha256

import alluvial
from alluvial.engine import DiagramStore
from alluvial.io import read, split_layers
from alluvial.io.alluvial_format import serialize_diagram
from alluvial.layout import LayoutOptions, _distinct_ids

REPO = Path(__file__).resolve().parents[1]
HARNESS = REPO / "tools" / "ts-fixtures"
TS_ROOT = Path(os.environ.get("ALLUVIAL_TS_ROOT", REPO.parent / "web" / "alluvial"))

START = int(os.environ.get("ALLUVIAL_FUZZ_START", "0"))
COUNT = int(os.environ.get("ALLUVIAL_FUZZ_SEEDS", "30"))
SEEDS = list(range(START, START + COUNT))


def _ts_src_sha256(src: Path) -> str:
    """Hash the TS sources exactly like ``provenance()`` in ``tools/ts-fixtures/generate.mjs``."""

    def walk(d: Path, prefix: str = "") -> list[str]:
        out = []
        for name in sorted(p.name for p in d.iterdir()):
            rel = f"{prefix}/{name}" if prefix else name
            if (d / name).is_dir():
                out += walk(d / name, rel)
            elif re.search(r"\.(ts|tsx)$", name) and not re.search(r"\.test\.tsx?$", name):
                out.append(rel)
        return out

    h = hashlib.sha256()
    for rel in walk(src):
        h.update(rel.encode() + b"\0")
        h.update((src / rel).read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _require_ts() -> str:
    """Return the node binary, or skip unless the TS checkout is the one the fixtures came from."""
    node = shutil.which("node")
    src = TS_ROOT / "packages" / "alluvial-diagram" / "src"
    if (
        node is None or not src.is_dir() or not (HARNESS / "generate.mjs").is_file()
    ):  # an sdist ships only fuzz/gen.py
        pytest.skip("node, the TS alluvial sources or the fixture harness are not available")
    m = re.search(
        r"^ts_src_sha256: ([0-9a-f]{64})", (REPO / "tests" / "fixtures" / "provenance.txt").read_text(), re.M
    )
    if m and _ts_src_sha256(src) != m.group(1):
        pytest.skip(
            f"the TS sources at {TS_ROOT} differ from the ones tests/fixtures were generated from "
            "(tests/fixtures/provenance.txt); point ALLUVIAL_TS_ROOT at the matching checkout"
        )
    return node


pytestmark = [pytest.mark.fuzz, pytest.mark.filterwarnings("ignore::UserWarning")]


def _int_as_js(s: str) -> int | float:
    v = int(s)
    return v if abs(v) <= 2**53 else float(v)


def _load_ts_json(text: str) -> Any:
    """A harness output, with integer literals beyond 2**53 read as doubles like ``JSON.parse`` (TS writes a huge
    float such as a restored ``colorOffset`` of -4.27e17 as ``-427299959682199200``)."""
    return json.loads(text, parse_int=_int_as_js)


def _load_gen():
    spec = importlib.util.spec_from_file_location("alluvial_fuzz_gen", HARNESS / "fuzz" / "gen.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_fuzz_dir(
    tmp_path_factory: pytest.TempPathFactory, v2: bool, v4: bool = False, c3: bool = False
) -> Path:
    node = _require_ts()
    out = tmp_path_factory.mktemp("fuzz-c3" if c3 else "fuzz-v4" if v4 else "fuzz-v2" if v2 else "fuzz")
    _load_gen().make_cases(SEEDS, out, v2=v2, v4=v4, c3=c3)
    subprocess.run([node, str(HARNESS / "generate.mjs"), "--fuzz", str(out)], check=True, capture_output=True)
    return out


@pytest.fixture(scope="module")
def fuzz_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _make_fuzz_dir(tmp_path_factory, v2=False)


@pytest.fixture(scope="module")
def fuzz_dir_v2(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _make_fuzz_dir(tmp_path_factory, v2=True)


@pytest.fixture(scope="module")
def fuzz_dir_v4(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _make_fuzz_dir(tmp_path_factory, v2=True, v4=True)


@pytest.fixture(scope="module")
def fuzz_dir_c3(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _make_fuzz_dir(tmp_path_factory, v2=True, v4=True, c3=True)


def _ctor_color(case: dict[str, Any]) -> dict[str, Any]:
    """The case's DiagramStore ctor colour options (gen.py --c3 ``color``) as ``DiagramStore`` keywords."""
    color = case.get("color") or {}
    names = {"colorScheme": "scheme", "colorTone": "tone", "colorOffset": "offset"}
    return {names[k]: v for k, v in color.items()}


# The store's label defaults (the harness dumps them as inputs.labelOptions).
LABEL_OPTIONS = {
    "fontSize": 8,
    "adaptiveFontSize": False,
    "multilineModuleNames": True,
    "aggregateStateNames": True,
    "showModuleNames": True,
}

MODULE_OPS = frozenset(
    {
        "colorModule",
        "expand",
        "regroup",
        "moveModule",
        "colorMatchingModules",
        "colorModuleIds",
        "colorNodesInModule",
        "setModuleName",
    }
)


def _resolve(store: DiagramStore, op: dict[str, Any]) -> dict[str, Any]:
    """Same as ``resolveOp`` in harness.ts: a raw networkIndex modulo the network count, a module op's raw
    moduleIndex modulo the module count, colorSelectedNodes' ``{networkIndex, leafIndex}`` (and the highlight macro's
    raw group entries) as identifiers, a moduleLevel levels list cycled to one k per network, and the v4
    ``moduleOrder``/``moduleNames`` macros' raw entries as module ids."""
    num_networks = len(store.diagram.children)

    def identifier(ref: dict[str, Any]) -> tuple[int, str] | None:
        ni = ref["networkIndex"] % num_networks
        leaves = list(store.diagram.children[ni].leaf_nodes())
        return (ni, leaves[ref["leafIndex"] % len(leaves)].identifier) if leaves else None

    if op["op"] in MODULE_OPS:
        ni = op["networkIndex"] % num_networks
        n = len(store.diagram.children[ni].children)
        if n == 0:
            raise IndexError("no modules")
        return {**op, "networkIndex": ni, "moduleIndex": op["moduleIndex"] % n}
    if op["op"] == "colorSelectedNodes":
        picked = (identifier(ref) for ref in op["nodes"])
        return {**op, "nodes": [{"networkIndex": ni, "identifier": i} for ni, i in filter(None, picked)]}
    if op["op"] == "moduleLevel" and isinstance(op["levels"], list):
        raw = op["levels"]
        return {**op, "levels": [raw[i % len(raw)] for i in range(num_networks)]}
    if op["op"] == "moduleOrder":
        seen_networks: set[int] = set()
        order = []
        for raw_network, spec in op["order"]:
            ni = raw_network % num_networks
            if ni in seen_networks:
                continue
            seen_networks.add(ni)
            visible = [m.module_id for m in store.diagram.children[ni].children if m.is_visible]
            if spec == "reverse":
                ids = visible[::-1]
            elif spec == "rotate":
                ids = [*visible[1:], *visible[:1]]
            else:
                ids = []
                for raw in spec:
                    module_id = "..." if raw == "..." else visible[raw % len(visible)] if visible else None
                    if module_id is not None and module_id not in ids:
                        ids.append(module_id)
            order.append([ni, ids])
        return {**op, "order": order}
    if op["op"] == "moduleNames":
        names = []
        for raw_network, raw_module, name in op["names"]:
            ni = raw_network % num_networks
            children = store.diagram.children[ni].children
            if children:
                names.append([ni, children[raw_module % len(children)].module_id, name])
        return {**op, "names": names}
    if op["op"] == "highlight":
        seen: set[str] = set()
        groups = []
        for label, refs in op["groups"]:
            identifiers = []
            for ref in refs:
                picked = identifier(ref)
                if picked is not None and picked[1] not in seen:
                    seen.add(picked[1])
                    identifiers.append(picked[1])
            groups.append([label, identifiers])
        return {**op, "groups": groups}
    return op


def _apply_raw(store: DiagramStore, op: dict[str, Any]) -> None:
    """A resolved raw op in the harness's lenient mode: a refused expand/regroup/move is not an error."""
    if op["op"] == "expand":
        store.expand(store.diagram.children[op["networkIndex"]].children[op["moduleIndex"]])
    elif op["op"] == "regroup":
        store.regroup(store.diagram.children[op["networkIndex"]].children[op["moduleIndex"]])
    elif op["op"] == "moveModule":
        module = store.diagram.children[op["networkIndex"]].children[op["moduleIndex"]]
        store.move_module(module, op["direction"])
    elif op["op"] == "moduleLevel":
        store.apply_module_level(op["levels"])
    elif op["op"] == "highlight":
        _apply_highlight(store, op)
    elif op["op"] == "moduleOrder":
        store.apply_module_order((ni, ids) for ni, ids in op["order"])
    elif op["op"] == "moduleNames":
        store.apply_module_names((ni, module_id, name) for ni, module_id, name in op["names"])
    else:
        store.apply(op)


def _apply_highlight(store: DiagramStore, op: dict[str, Any]) -> list[int]:
    """The harness's fuzz-mode ``highlight`` macro is ``layout(highlight=...)``'s ``apply_highlight``."""
    if len(op["colors"]) != len(op["groups"]):
        raise ValueError("highlight: one colour per label")
    return store.apply_highlight(highlight_label_of(op["groups"]), op["colors"])


def read_case_files(case: dict[str, Any]) -> list[Any]:
    """The case's input files (id = stem, name = basename), with ``nodeMetadata`` assigned to the parsed nodes and
    the ``split`` files replaced by their layers (in place, increasing index), as the harness does."""
    files = []
    metadata = case.get("nodeMetadata")
    split = set(case.get("split") or ())
    ids = _distinct_ids([Path(path).stem for path in case["files"]])  # the harness's loadFiles ids
    for i, path in enumerate(case["files"]):
        nf = read(path, identifier=case.get("identifier", "id"))
        nf.id = ids[i]
        nf.name = Path(path).name
        if metadata is not None:
            if len(metadata[i]) != len(nf.nodes):
                raise ValueError("nodeMetadata does not match the nodes")
            for node, md in zip(nf.nodes, metadata[i]):
                node.metadata = md
        files.extend(split_layers(nf) if i in split else [nf])
    return files


def replay_case(
    case: dict[str, Any], fx_inputs: dict[str, Any] | None = None
) -> tuple[DiagramStore, Trace, list[Any]]:
    """Replay a case in Python: the case's initial options, then either the resolved ops the TS harness recorded
    (``fx_inputs["operations"]``, with the ``moduleLevel`` and ``highlight`` macros of ``fx_inputs["macros"]`` run
    through ``apply_module_level``/``apply_highlight``, which must issue the recorded ops) or else the raw
    ``case["ops"]`` resolved like the harness does.

    The fixture's ``inputs.options`` hold the options at the end, after any ``setOption``; they are not the
    options the diagram was built with.
    """
    files = read_case_files(case)
    trace = Trace()
    store = DiagramStore(LayoutOptions.from_ts(case["options"]), trace=trace, **_ctor_color(case))
    store.set_networks(files)
    if fx_inputs is None:
        for op in case["ops"]:
            _apply_raw(store, _resolve(store, op))
        return store, trace, files
    ops = fx_inputs["operations"]
    # several macros can share an atOperation (a macro that issued no op, e.g. moduleLevel with nothing to expand)
    macros: dict[int, list[dict[str, Any]]] = {}
    for m in fx_inputs.get("macros", ()):
        macros.setdefault(m["atOperation"], []).append(m)
    assert ops[0]["op"] == "setNetworks"
    i = 1
    while i < len(ops) or macros.get(i):
        if macros.get(i):
            macro = macros[i].pop(0)
            op = macro["op"]
            issued = ops[i : i + macro["numOperations"]]
            if op["op"] == "moduleLevel":
                assert store.apply_module_level(op["levels"]) == issued
            elif op["op"] == "moduleOrder":
                assert store.apply_module_order((ni, ids) for ni, ids in op["order"]) == issued
            elif op["op"] == "moduleNames":
                assert store.apply_module_names((ni, m, name) for ni, m, name in op["names"]) == issued
            else:
                indices = _apply_highlight(store, op)
                assert indices == [store.get_highlight_index(c) for c in op["colors"]]
            i += macro["numOperations"]
        else:
            store.apply(ops[i])
            i += 1
    macros = {k: v for k, v in macros.items() if v}
    assert not macros, f"macros not replayed: {macros}"
    return store, trace, files


def _check_case(case_dir: Path) -> None:
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    fx = json.loads((case_dir / "ts.json").read_text(encoding="utf-8"))
    if "error" in fx:
        # TS can also throw in the harness dump (Network.tree on a module shown with one of its sub-modules; the
        # pass-2 height self-check after a one-sided colorMatchingModules, which runs no layout), so dump too.
        inputs = {"files": case["files"], "labelOptions": LABEL_OPTIONS, "split": case.get("split")}
        with pytest.raises(Exception):  # noqa: B017 - any error, as long as Python does not silently succeed
            store, trace, files = replay_case(case)
            dump_store(store, trace, inputs, files)
        return
    store, trace, files = replay_case(case, fx["inputs"])
    actual = dump_store(store, trace, fx["inputs"], files)
    res = assert_matches(actual, fx, ignore=IGNORED)
    assert res.non_bitwise == 0, f"{res.non_bitwise} floats differ from TS in the last bits"
    # assert_matches compares SVG paths numerically; the JS number formatting must match too.
    assert [link["path"] for n in actual["networks"] for link in n["links"]] == [
        link["path"] for n in fx["networks"] for link in n["links"]
    ]
    rt_path = case_dir / "ts-roundtrip.json"
    if rt_path.exists():
        _check_round_trip_case(store, _load_ts_json(rt_path.read_text(encoding="utf-8")), case.get("open"))


def _check_round_trip_case(store: DiagramStore, rt: dict[str, Any], open_spec: dict[str, Any] | None) -> None:
    """Saved-diagram round trips (harness ``fuzzRoundTrip``): the Python ``serialize_diagram`` texts equal TS's
    ``serializeDiagram`` texts byte for byte (so TS opens exactly what Python writes: Python-save -> TS-load), and
    the Python ``open_networks`` of them equals the TS ``openNetworks`` (TS-save -> Python-load). When TS throws in
    the round trip, Python must raise too.

    The reloads restore the saved (final) options, as the web app does. c3 cases open the saved files edited and with
    the store colour options of their ``open`` spec (gen.py ``c3_open``; TS writes the edited files as
    ``savedReloadFiles``)."""
    if "error" in rt:
        # TS can throw in the dumps of the reloaded stores (Network.tree), so dump them too
        with pytest.raises(Exception):  # noqa: B017
            texts = _load_gen().mutate_saved_texts(serialize_diagram(store, **SAVE), open_spec)
            w_store, w_trace, w_files, _ = open_saved_texts(texts, (open_spec or {}).get("reloadStore"))
            dump_store(
                w_store, w_trace, {"files": [n for n, _ in texts], "labelOptions": LABEL_OPTIONS}, w_files
            )
        return
    _check_round_trip(rt, store)


@pytest.mark.parametrize("seed", SEEDS)
def test_fuzz_parity(seed: int, fuzz_dir: Path) -> None:
    _check_case(fuzz_dir / f"seed-{seed:06d}")


@pytest.mark.parametrize("seed", SEEDS)
def test_fuzz_parity_v2(seed: int, fuzz_dir_v2: Path) -> None:
    _check_case(fuzz_dir_v2 / f"seed-{seed:06d}")


@pytest.mark.parametrize("seed", SEEDS)
def test_fuzz_parity_v4(seed: int, fuzz_dir_v4: Path) -> None:
    _check_case(fuzz_dir_v4 / f"seed-{seed:06d}")


@pytest.mark.parametrize("seed", SEEDS)
def test_fuzz_parity_c3(seed: int, fuzz_dir_c3: Path) -> None:
    _check_case(fuzz_dir_c3 / f"seed-{seed:06d}")


# --- Python-save -> TS-open, directly: Python writes each case's saved diagram (its own generator, a random save id),
# TS opens the files (generate.mjs --open), and Python's open of the same files must equal TS's bit for bit.


def _python_save_ts_open(fuzz_dir: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    gen = _load_gen()
    cases = []
    for seed in SEEDS:
        case_dir = fuzz_dir / f"seed-{seed:06d}"
        fx = json.loads((case_dir / "ts.json").read_text(encoding="utf-8"))
        if "error" in fx:
            continue
        case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        store, _, _ = replay_case(case, fx["inputs"])
        out = case_dir / "saved"
        out.mkdir(exist_ok=True)
        # c3 cases: the saved diagram blocks edited and the opening store's colour options (gen.py c3_open)
        spec = case.get("open") or {}
        texts = gen.mutate_saved_texts(serialize_diagram(store, generator="alluvial (Python) fuzz"), spec)
        for name, text in texts:
            (out / name).write_text(text, encoding="utf-8")
        if "reloadStore" in spec:
            (case_dir / "open.json").write_text(
                json.dumps({"reloadStore": spec["reloadStore"]}), encoding="utf-8"
            )
        cases.append((case_dir, spec.get("reloadStore")))
    subprocess.run(
        [node, str(HARNESS / "generate.mjs"), "--open", str(fuzz_dir)], check=True, capture_output=True
    )
    for case_dir, reload_store in cases:
        ts = _load_ts_json((case_dir / "ts-open.json").read_text(encoding="utf-8"))
        texts = [(p.name, p.read_text(encoding="utf-8")) for p in sorted((case_dir / "saved").glob("*.json"))]
        try:
            if "error" in ts:
                with pytest.raises(Exception):  # noqa: B017 - TS threw (Network.tree in the dump): Python must too
                    w_store, w_trace, w_files, _ = open_saved_texts(texts, reload_store)
                    dump_store(
                        w_store,
                        w_trace,
                        {"files": [n for n, _ in texts], "labelOptions": LABEL_OPTIONS},
                        w_files,
                    )
                continue
            w_store, w_trace, w_files, warnings = open_saved_texts(texts, reload_store)
            res = assert_matches(
                dump_store(w_store, w_trace, ts["inputs"], w_files), ts, ignore=ROUND_TRIP_IGNORED
            )
            assert res.non_bitwise == 0, f"{res.non_bitwise} floats differ from TS in the last bits"
            assert w_store.get_options() == ts["restored"]["options"]
            assert w_store.selected_scheme_name == ts["restored"]["colorScheme"]
            assert w_store.selected_tone == ts["restored"]["colorTone"]
            assert w_store.selected_offset == ts["restored"]["colorOffset"]
            assert scheme_sha256(w_store) == ts["restored"]["schemeSha256"]
            assert warnings == ts["restored"]["openWarnings"]
        except AssertionError as e:
            raise AssertionError(f"{case_dir.name}: {e}") from None


def test_fuzz_python_save_ts_open(fuzz_dir: Path) -> None:
    _python_save_ts_open(fuzz_dir)


def test_fuzz_python_save_ts_open_v2(fuzz_dir_v2: Path) -> None:
    _python_save_ts_open(fuzz_dir_v2)


def test_fuzz_python_save_ts_open_v4(fuzz_dir_v4: Path) -> None:
    _python_save_ts_open(fuzz_dir_v4)


def test_fuzz_python_save_ts_open_c3(fuzz_dir_c3: Path) -> None:
    _python_save_ts_open(fuzz_dir_c3)


# --- A zip written by alluvial.save_diagram (Python's zipfile, deflated), dropped on the web app's "Load networks" as
# is: TS opens it through parseAcceptedFiles (JSZip) + openNetworks, and Python's ``read`` of the same zip +
# ``open_networks`` must equal it bit for bit (dump, restored options, scheme, warnings).

DATA = REPO / "tests" / "data"
SAVE_DIAGRAM_ZIPS: dict[str, tuple[list[Path], dict[str, Any]]] = {
    "plain": ([DATA / f"multilevel_t{i}.tree" for i in range(3)], {}),
    "options": (
        [DATA / f"multilevel_t{i}.tree" for i in range(3)],
        {
            "height": 300,
            "scheme": "Paired",
            "colors": "module_id",
            "module_names": {(0, "1"): "First", (2, "2"): "Second"},
        },
    ),
    "levels": ([DATA / f"multilevel_t{i}.tree" for i in range(3)], {"module_level": 2}),
    "ordered": (
        [DATA / f"multilevel_t{i}.tree" for i in range(3)],
        {"module_order": {0: ["2", ...]}, "names": ["a", "b", "c"]},
    ),
    "split": ([DATA / "mlayer_states.tree"], {"split_layers": True}),
    "tone": (
        [DATA / f"multilevel_t{i}.tree" for i in range(3)],
        {"scheme": "C3 Oklch", "tone": "pastel", "offset": 33.5, "colors": "hierarchy", "module_level": 2},
    ),
}


def test_python_save_diagram_zip_opens_in_ts(tmp_path: Path) -> None:
    node = _require_ts()
    for name, (paths, kwargs) in SAVE_DIAGRAM_ZIPS.items():
        (tmp_path / name).mkdir()
        out = alluvial.save_diagram(paths, tmp_path / name / "saved.zip", **kwargs)
        assert out == tmp_path / name / "saved.zip"
    subprocess.run(
        [node, str(HARNESS / "generate.mjs"), "--open", str(tmp_path)], check=True, capture_output=True
    )
    for name in SAVE_DIAGRAM_ZIPS:
        ts = json.loads((tmp_path / name / "ts-open.json").read_text(encoding="utf-8"))
        assert "error" not in ts, f"{name}: {ts.get('error')}"
        files = read(tmp_path / name / "saved.zip")
        trace = Trace()
        store = DiagramStore(LayoutOptions(), trace=trace)
        warnings = store.open_networks(files)
        try:
            res = assert_matches(dump_store(store, trace, ts["inputs"], files), ts, ignore=ROUND_TRIP_IGNORED)
            assert res.non_bitwise == 0, f"{res.non_bitwise} floats differ from TS in the last bits"
            assert store.get_options() == ts["restored"]["options"]
            assert store.selected_scheme_name == ts["restored"]["colorScheme"]
            assert store.selected_tone == ts["restored"]["colorTone"]
            assert store.selected_offset == ts["restored"]["colorOffset"]
            assert scheme_sha256(store) == ts["restored"]["schemeSha256"]
            assert warnings == ts["restored"]["openWarnings"] == []
            # the public path restores the same options
            assert (
                alluvial.layout([tmp_path / name / "saved.zip"]).height == ts["restored"]["options"]["height"]
            )
        except AssertionError as e:
            raise AssertionError(f"{name}: {e}") from None
