"""Seeded random inputs for the TS/Python differential fuzzer.

One *case* is a directory with 1-6 network files (``.tree``/``.ftree``/``.stree``/``.clu`` text) and a ``case.json``
with the store options and the operations to replay::

    {"name": "seed-000042", "seed": 42, "files": ["/abs/net0.tree", ...], "identifier": "id",
     "options": {...TS LayoutOpts names...}, "ops": [{"op": ...}, ...]}

``node tools/ts-fixtures/generate.mjs --fuzz DIR`` runs every case in ``DIR`` on the TS store and writes
``ts.json`` (fixture format, see ../README.md) next to ``case.json``; ``tests/test_fuzz_parity.py`` replays the
same case in Python and compares.

Operations, besides the store colour ops of ``scenarios.ts``:

- ``{"op": "setOption", "key": <TS option name>, "value": v}`` calls the store setter (``setHeight`` ...), which
  runs one ``updateLayout`` (an option change after load).
- ``{"op": "clearColors"}``.
- ``colorModule`` carries ``moduleIndex`` as a raw non-negative int; the TS harness reduces it modulo the number of
  modules at that point and records the resolved index in ``inputs.operations``, which Python replays.

v2 (``--v2`` / ``make_cases(..., v2=True)``): the same case (files, options, v1 ops are unchanged; the v2 parts come
from a separate ``random.Random(f"v2-{seed}")``) plus v2 ops inserted at random positions, and sometimes
``nodeMetadata`` (one list per file, aligned with its node rows; mixed string/number/missing values):

- ``expand``/``regroup``/``moveModule``/``colorMatchingModules``/``colorModuleIds``/``colorNodesInModule`` with a raw
  ``moduleIndex`` (resolved like ``colorModule``). A refused expand/regroup/move does not abort the case: the harness
  records ``"result": false`` (``true`` on success) in the resolved op.
- ``moduleLevel`` (k in 1-4, or one k per network): recorded as concrete ``expand`` ops plus ``inputs.macros``.
- ``colorSelectedNodes`` with raw ``{networkIndex, leafIndex}`` entries, recorded as ``{networkIndex, identifier}``.
- ``resetLayout``, ``colorByLayer``, ``colorByPhysicalId``, ``colorCategoricalMetadata``, ``colorRealMetadata``,
  ``colorRealIntervals``, ``setDefaultHighlightColor``.
- the ``highlight`` macro with raw groups ``[label, [{networkIndex, leafIndex}]]`` (resolved to identifiers; the
  harness writes the labels onto the leaves when it runs, like ``DiagramStore.apply_highlight``).
- raw network indices are reduced modulo the network count (split layers add networks), and a ``moduleLevel`` list
  is cycled to one k per network.

The v2 *input profile* (``_input_profile``, its own ``random.Random(f"v2in-{seed}")``) sometimes writes Infomap JSON
files, multilayer files split into layers (``"split": [file indices]``), deep/chain/flat/singleton hierarchies or many
duplicate identifiers.

v4 (``--v4`` / ``make_cases(..., v4=True)``, implies v2): the v2 case unchanged plus v4 ops from their own
``random.Random(f"v4-{seed}")`` inserted at random positions:

- the ``moduleOrder`` macro with raw ``order: [[networkIndex, spec], ...]``: ``spec`` is a list of raw visible-module
  indices and at most one ``"..."``, or ``"reverse"``/``"rotate"`` (all visible modules reversed/rotated by one). The
  harness resolves it at its turn: network indices modulo the network count (a repeated network is dropped), indices
  modulo the number of visible modules (``network.children.filter(m => m.isVisible)``, as module ids, a repeated id
  dropped), and runs ``runModuleOrder``; Python replays it through ``apply_module_order``.
- the ``moduleNames`` macro with raw ``names: [[networkIndex, moduleIndex, name], ...]`` (``moduleIndex`` modulo
  all of ``network.children``, hidden modules included, resolved to the module id at its turn): one
  ``setModuleName`` per entry, recorded by module id; Python replays it through ``apply_module_names``.
- plain ``setModuleName`` with a raw ``moduleIndex`` (resolved like ``colorModule``).

c3 (``--c3`` / ``make_cases(..., c3=True)``, implies v4; web app 1.16): the v4 case unchanged plus, from their own
``random.Random(f"c3-{seed}")``, sometimes a ``color`` block of DiagramStore ctor options (``colorScheme``,
``colorTone``, ``colorOffset``: any scheme, any c3 tone, offsets null/0/negative/fractional/large) and c3 ops inserted
at random positions: ``setSelectedScheme`` (C3, interpolated and list schemes), ``setSelectedTone``,
``setSelectedOffset`` (also null), ``colorModuleHierarchyInAllNetworks`` (often after a ``moduleLevel``) and the
scheme-driven colour ops (``colorMatchingModulesInAllNetworks``, ``colorModuleIdsInAllNetworks``,
``colorNodesInModulesInAllNetworks``). The saved-diagram round trip then also covers the saved tone and offset, and a
case's ``open`` spec (``c3_open``, from ``random.Random(f"c3open-{seed}")``) says how the saved files are opened in
both directions: the opening store's ctor colour options (``reloadStore``) and edits of the saved ``colorScheme``,
``colorTone`` and ``colorOffset`` (valid, invalid, odd JSON literals, removed; in all or some files), applied by
``mutate_saved_texts`` (Python-save -> TS-open) and ``mutateSavedTexts`` in harness.ts (TS-save -> Python-open).

Usage::

    python tools/ts-fixtures/fuzz/gen.py OUT_DIR --seeds 0:1000 [--v2 | --v4 | --c3]
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
from pathlib import Path

DEFAULT_HIGHLIGHT = "#b6b69f"
SCHEME_START = ["#fe8a7a", "#fe8d7a"]  # not exact scheme colours; just plausible hex colours

NAME_POOL = [
    "alpha",
    "beta gamma",
    "node 1",
    "O'Brien",
    "Zürich",
    "東京",
    "x  y",
    "a-b",
    "",
    " lead",
    "trail ",
    "Ωmega",
    "😀 face",
    "1",
    "1:2",
    "tab\there",
    "'single'",
]

OPTION_CHOICES: dict[str, list] = {
    "height": [600, 200, 1, 0.001, 37.5, 1e6, 123.456, 2000, 1e22, 1e-8],
    "moduleWidth": [80, 50, 1, 0.5, 333.3, 1e-7, 1e21],
    "streamlineFraction": [2, 1.5, 0, 0.25, 7],
    "streamlineThreshold": [1, 0, 0.5, 5, 50],
    "flowThreshold": [0.005, 0, 0.05, 0.4, 0.9, 0.999999, 0.5, 1e-9],
    "marginExponent": [4, 5, 0, 1, 2.5, 3.7, -1, 8, 0.5],
    "zeroMargins": [False, True],
    "verticalAlign": ["bottom", "justify"],
    "moduleSize": ["flow", "nodes"],
    "sortModulesBy": ["flow", "nodes", "nodeId", "highlightIndex"],
}


def _rand_option(rng: random.Random, key: str):
    if rng.random() < 0.75 or key in ("zeroMargins", "verticalAlign", "moduleSize", "sortModulesBy"):
        return rng.choice(OPTION_CHOICES[key])
    lo_hi = {
        "height": (0.01, 5000),
        "moduleWidth": (0.1, 300),
        "streamlineFraction": (0, 6),
        "streamlineThreshold": (0, 20),
        "flowThreshold": (0, 0.999),
        "marginExponent": (-3, 9),
    }[key]
    return rng.uniform(*lo_hi)


# Flow tokens that do not parse to a finite number. Both engines reject such a file at load (fix round E9), so a
# case with one only checks that rejection. Such tokens are written only in the 1 % of cases that draw
# ``_NON_FINITE_CASE`` (from their own RNG; then at a higher per-row rate, so about 1 case in 200 has one), the finite
# oddities ("-0.1", "-0") in every case. In an unflagged case a suppressed non-finite token falls through to the
# normal formatting, which may draw again (the zero spelling), so such a case is not drawn exactly as before the flag
# existed; before WP4 it held a non-finite token anyway, so no finite case is lost.
_NON_FINITE = frozenset({"NaN", "Infinity", "1e400", "abc"})
_NON_FINITE_CASE = False


def _fmt_flow(rng: random.Random, x: float, style: str) -> str:
    if rng.random() < (0.1 if _NON_FINITE_CASE else 0.004):
        token = rng.choice(["NaN", "-0.1", "Infinity", "1e400", "-0", "abc"])
        if _NON_FINITE_CASE or token not in _NON_FINITE:
            return token
    if x == 0:
        return rng.choice(["0", "0", "0.0", "0e0"])
    if style == "repr":
        return repr(x)
    if style == "g6":
        return f"{x:.6g}"
    if style == "g3":
        return f"{x:.3g}"
    return f"{x:.12e}"


def _flows(rng: random.Random, n: int) -> list[float]:
    kind = rng.choice(["uniform", "exp", "ties", "zeros", "tiny", "mixed", "equal"])
    if kind == "uniform":
        xs = [rng.random() for _ in range(n)]
    elif kind == "exp":
        xs = [rng.expovariate(1.0) ** 3 for _ in range(n)]
    elif kind == "ties":
        xs = [rng.choice([0.1, 0.2, 0.2, 0.3]) for _ in range(n)]
    elif kind == "zeros":
        xs = [rng.choice([0.0, 0.0, rng.random()]) for _ in range(n)]
    elif kind == "tiny":
        xs = [rng.choice([1e-12, 1e-300, 5e-324, rng.random() * 1e-9, rng.random()]) for _ in range(n)]
    elif kind == "equal":
        xs = [1.0] * n
    else:
        xs = [rng.choice([0.0, 1e-10, 0.25, rng.random(), 0.25]) for _ in range(n)]
    if rng.random() < 0.7:
        s = sum(xs)
        if s > 0:
            xs = [x / s for x in xs]
    return xs


class Universe:
    """Physical nodes shared by all networks of a case (so nodes can appear/disappear between networks)."""

    def __init__(self, rng: random.Random) -> None:
        self.size = rng.choice([1, 2, 3, 5, 8, 12, 20, 40, 100, 250, 3, 5, 8, 12])
        if rng.random() < 0.01:
            self.size = 1500
        base_ids = list(range(1, self.size + 1))
        if rng.random() < 0.3:
            base_ids = sorted(rng.sample(range(max(1000, 3 * self.size)), self.size))
        self.ids = base_ids
        name_mode = rng.choice(["v", "pool", "dupe", "mixed"])
        self.names = {}
        for i in self.ids:
            if name_mode == "v":
                self.names[i] = f"v{i}"
            elif name_mode == "pool":
                self.names[i] = rng.choice(NAME_POOL) + f"{i}"
            elif name_mode == "dupe":
                self.names[i] = rng.choice(["a", "b", "c"])
            else:
                self.names[i] = rng.choice(NAME_POOL + [f"n{i}"] * 5)


def _module_paths(rng: random.Random, n: int, shape: str | None = None) -> list[list[int]]:
    """Random hierarchical module paths (without the leaf index) for n nodes.

    ``shape`` (v2 input profile only; ``None`` keeps the v1 draws): ``"deep"`` (up to 10 levels), ``"chain"`` (one or
    two long single-child chains, so every expand creates one sub-module), ``"flat"`` (one top module) or
    ``"singletons"`` (every node alone in its own chain of modules).
    """
    if shape == "chain":
        depth = rng.randint(2, 8)
        tops = rng.sample(range(1, 9), rng.choice([1, 1, 2]))
        return [[rng.choice(tops)] + [1] * (depth - 1) for _ in range(n)]
    if shape == "flat":
        return [[rng.choice([1, 7])] for _ in range(n)]
    if shape == "singletons":
        depth = rng.randint(1, 4)
        # at most 120 chains: module_level on 1000+ chains means 1000s of expands, each with a full layout (minutes
        # in TS and Python alike)
        return [[i % 120 + 1] + [1] * (depth - 1) for i in range(n)]
    num_top = rng.choice([1, 1, 2, 3, 4, 6, 10])
    max_depth = rng.choice([1, 1, 2, 3, 5]) if shape != "deep" else rng.choice([6, 8, 10])
    top_ids = list(range(1, num_top + 1))
    if rng.random() < 0.15:
        top_ids = rng.sample(range(1, 50), num_top)
    out = []
    for _ in range(n):
        path = [rng.choice(top_ids)]
        depth = rng.randint(1, max_depth)
        for _ in range(depth - 1):
            path.append(rng.randint(1, 3))
        out.append(path)
    return out


def _header(rng: random.Random, kind: str, state: bool, num_top: int, directed: bool) -> list[str]:
    lines = []
    if rng.random() < 0.85:
        lines.append(rng.choice(["# v2.15.1", "# v1.7.3", "# v2.0.0"]))
        lines.append("# ./Infomap fuzz --two-level")
        if rng.random() < 0.7:
            lines.append(f"# partitioned into {rng.randint(2, 4)} levels with {num_top} top modules")
        if rng.random() < 0.7:
            lines.append(f"# codelength {rng.uniform(0, 10):.6g} bits")
        if rng.random() < 0.5:
            lines.append(f"# flow model {'directed' if directed else 'undirected'}")
        if state and rng.random() < 0.8:
            lines.append("# higher order")
            lines.append("# state level")
        if kind == "clu" and rng.random() < 0.6:
            lines.append("# module level 1")
    return lines


def _network_text(
    rng: random.Random,
    uni: Universe,
    fmt: str,
    state: bool,
    layers: bool = False,
    shape: str | None = None,
    dup_prob: float = 0.1,
    json_metadata: bool = False,
) -> str:
    # Which physical nodes are present
    k = rng.randint(1, uni.size)
    present = sorted(rng.sample(uni.ids, k))
    rows = []  # (node_id, state_id, layer_id)
    next_state = 1
    for node in present:
        nstates = rng.choice([1, 1, 2, 3]) if state else 1
        for _ in range(nstates):
            rows.append((node, next_state if state else None, rng.randint(1, 3) if layers else None))
            next_state += rng.choice([1, 1, 7])
    if rows and rng.random() < dup_prob:
        # duplicate identifier: repeat a node record (v2 profile "dupes": several)
        for _ in range(1 if dup_prob <= 0.1 else rng.randint(1, max(1, len(rows) // 3))):
            rows.append(rng.choice(rows))
    n = len(rows)
    paths = _module_paths(rng, n, shape)
    flows = _flows(rng, n)
    style = rng.choice(["repr", "g6", "g3", "e"])
    num_top = len({p[0] for p in paths})
    directed = rng.random() < 0.3
    header = _header(rng, "clu" if fmt == "clu" else "tree", state, num_top, directed)

    if fmt == "clu":
        cols = "state_id module flow node_id" if state else "node_id module flow"
        if layers:
            cols += " layer_id"
        if rng.random() < 0.8:
            header.append(f"# {cols}")
        body = []
        for (node, sid, lid), path, flow in zip(rows, paths, flows):
            f = _fmt_flow(rng, flow, style)
            line = f"{sid} {path[0]} {f} {node}" if state else f"{node} {path[0]} {f}"
            body.append(f"{line} {lid}" if layers else line)
        if rng.random() < 0.3:
            rng.shuffle(body)
        return "\n".join(header + body) + "\n"

    if fmt == "json":
        return _network_json(rng, uni, rows, paths, flows, state, layers, directed, json_metadata)

    cols = "path flow name state_id node_id" if state else "path flow name node_id"
    if layers:
        cols += " layer_id"
    if rng.random() < 0.8:
        header.append(f"# {cols}")
    # Leaf indices within each module, in record order
    counters: dict[tuple, int] = {}
    entries = []
    for (node, sid, lid), path, flow in zip(rows, paths, flows):
        key = tuple(path)
        counters[key] = counters.get(key, 0) + 1
        full = [*path, counters[key]]
        if fmt == "stree":
            seps = [
                rng.choice([":", ":", ";"]) if i > 0 or rng.random() < 0.1 else ":"
                for i in range(len(full) - 1)
            ]
            p = str(full[0]) + "".join(s + str(x) for s, x in zip(seps, full[1:]))
            if rng.random() < 0.5:
                p += rng.choice([":", ";"])
        else:
            p = ":".join(map(str, full))
        if rng.random() < 0.01:
            p = rng.choice(["0" + p, p.replace("1", "01"), p + ":", p.replace(":", "::", 1), "0:" + p])
        name = uni.names[node]
        f = _fmt_flow(rng, flow, style)
        line = f'{p} {f} "{name}" {sid} {node}' if state else f'{p} {f} "{name}" {node}'
        if layers:
            line += f" {lid}"
        entries.append((full, line))
    if rng.random() < 0.5:
        entries.sort(key=lambda e: e[0])
    elif rng.random() < 0.5:
        rng.shuffle(entries)
    body = [line for _, line in entries]
    text = header + body
    if fmt == "ftree":
        text.append(f"*Links {'directed' if directed else 'undirected'}")
        text.append("#*Links path enterFlow exitFlow numEdges numChildren")
        tops = sorted({e[0][0] for e in entries})
        text.append(f"*Links root 0 0 {rng.randint(0, 5)} {len(tops)}")
        for _ in range(rng.randint(0, 4)):
            if len(tops) > 1:
                a, b = rng.sample(range(1, len(tops) + 1), 2)
                text.append(f"{a} {b} {rng.random():.6g}")
        mods = sorted({tuple(e[0][:d]) for e in entries for d in range(1, len(e[0]))})
        for m in mods:
            if rng.random() < 0.8:
                enter, exit_ = rng.random() * 0.1, rng.random() * 0.1
                text.append(
                    f"*Links {':'.join(map(str, m))} {enter:.6g} {exit_:.6g} {rng.randint(0, 5)} {rng.randint(1, 5)}"
                )
                for _ in range(rng.randint(0, 3)):
                    text.append(f"{rng.randint(1, 4)} {rng.randint(1, 4)} {rng.random():.6g}")
    return "\n".join(text) + "\n"


def _network_json(rng, uni, rows, paths, flows, state, layers, directed, json_metadata) -> str:
    """Infomap ``-o json`` style (v2-io.md §3.2): array paths (sometimes ``"1:2:3"`` strings), JSON flows (repr, so
    bit-identical in JS), optional ``modules`` records with enter/exit flow and optional per-node ``metadata``."""
    counters: dict[tuple, int] = {}
    nodes = []
    for (node, sid, lid), path, flow in zip(rows, paths, flows):
        key = tuple(path)
        counters[key] = counters.get(key, 0) + 1
        full = [*path, counters[key]]
        rec: dict = {"path": full if rng.random() < 0.9 else ":".join(map(str, full))}
        rec["modules"] = full[:-1]
        rec["name"] = uni.names[node]
        rec["flow"] = 0 if flow == 0 and rng.random() < 0.5 else flow
        rec["mec"] = 0.0
        if json_metadata and rng.random() < 0.8:
            rec["metadata"] = _metadata_value(rng) or {}
        if state:
            rec["stateId"] = sid
            if layers:
                rec["layerId"] = lid
        rec["id"] = node
        nodes.append(rec)
    if rng.random() < 0.5:
        nodes.sort(key=lambda r: [int(x) for x in str(r["path"]).strip("[]").replace(":", ",").split(",")])
    elif rng.random() < 0.5:
        rng.shuffle(nodes)
    top = len({p[0] for p in paths})
    data: dict = {
        "version": "v2.15.1",
        "args": " --fuzz",
        "codelength": rng.uniform(0, 10),
        "numLevels": rng.randint(1, 4),
        "numTopModules": top,
        "directed": directed,
        "flowModel": "directed" if directed else "undirected",
        "higherOrder": state,
        "nodes": nodes,
    }
    if rng.random() < 0.7:
        mods = sorted({tuple(r_path[:d]) for r_path in paths for d in range(1, len(r_path) + 1)})
        records = [
            {"path": [0], "enterFlow": 0, "exitFlow": 0, "numEdges": 0, "numChildren": top, "codelength": 0}
        ]
        for m in mods:
            if rng.random() < 0.8:
                records.append(
                    {
                        "path": list(m),
                        "enterFlow": round(rng.random() * 0.1, 6),
                        "exitFlow": round(rng.random() * 0.1, 6),
                        "numEdges": rng.randint(0, 5),
                        "numChildren": rng.randint(1, 5),
                        "codelength": 0.0,
                    }
                )
        data["modules"] = records
    return json.dumps(data, ensure_ascii=rng.random() < 0.5)


def _ops(rng: random.Random, num_networks: int) -> list[dict]:
    ops: list[dict] = []
    for _ in range(rng.choice([0, 0, 1, 1, 1, 2, 3, 5, 8])):
        r = rng.random()
        if r < 0.3:
            ops.append({"op": "colorMatchingModulesInAllNetworks"})
        elif r < 0.42:
            ops.append({"op": "colorModuleIdsInAllNetworks"})
        elif r < 0.55:
            op = {"op": "colorNodesInModulesInAllNetworks"}
            if rng.random() < 0.5:
                op["networkIndex"] = rng.randrange(num_networks)
            ops.append(op)
        elif r < 0.7:
            ops.append(
                {
                    "op": "colorModule",
                    "networkIndex": rng.randrange(num_networks),
                    "moduleIndex": rng.randrange(1000),
                    "color": rng.choice([DEFAULT_HIGHLIGHT, "#ff0000", "#00ff00", "#0000ff", *SCHEME_START]),
                }
            )
        elif r < 0.75:
            ops.append({"op": "clearColors"})
        else:
            key = rng.choice(list(OPTION_CHOICES))
            ops.append({"op": "setOption", "key": key, "value": _rand_option(rng, key)})
    return ops


COLORS = [DEFAULT_HIGHLIGHT, "#ff0000", "#00ff00", "#0000ff", *SCHEME_START]


def _num_rows(text: str) -> int:
    """Node rows of a generated network file: non-comment lines before the first ``*`` section (JSON: ``nodes``)."""
    if text.startswith("{"):
        return len(json.loads(text)["nodes"])
    n = 0
    for line in text.splitlines():
        if line.startswith("*"):
            break
        if line and not line.startswith("#"):
            n += 1
    return n


def _metadata_value(rng: random.Random):
    r = rng.random()
    if r < 0.1:
        return None
    if r < 0.2:
        return {}
    md = {}
    if rng.random() < 0.8:
        md["c"] = rng.choice(["a", "b", "c", "zz", "a", 3, 1.5])
    if rng.random() < 0.6:
        md["x"] = rng.choice([0, 0.25, 1, 1.2, "0.5", round(rng.random(), 3)])
    return md


HIGHLIGHT_LABELS = ["alpha", "beta", "", "alpha", "γ", "1"]


def _highlight_op(rng: random.Random, num_networks: int) -> dict:
    """The ``highlight`` macro with raw groups ``[label, [{networkIndex, leafIndex}]]`` (resolved by the harness to
    identifiers; an identifier keeps its first label). One colour per label, duplicates and the default allowed."""
    n = rng.randint(1, 4)
    groups = [
        [
            rng.choice(HIGHLIGHT_LABELS),
            [
                {"networkIndex": rng.randrange(num_networks), "leafIndex": rng.randrange(1000)}
                for _ in range(rng.choice([0, 1, 2, 4, 8, 20]))
            ],
        ]
        for _ in range(n)
    ]
    return {"op": "highlight", "groups": groups, "colors": [rng.choice(COLORS) for _ in range(n)]}


def _v2_ops(rng: random.Random, num_networks: int) -> list[dict]:
    """``num_networks`` is the range raw network indices are drawn from (the harness reduces them modulo the
    network count, which split layers can raise)."""
    ops: list[dict] = []
    for _ in range(rng.choice([1, 1, 2, 3, 5])):
        if rng.random() < 0.12:
            ops.append(_highlight_op(rng, num_networks))
            continue
        r = rng.random()
        ni = rng.randrange(num_networks)
        if r < 0.15:
            index = rng.randrange(1000)
            if rng.random() < 0.6:
                ops.append({"op": "expand", "networkIndex": ni, "moduleIndex": index})
            if rng.random() < 0.5:  # often right after an expand, so that it can succeed
                ops.append(
                    {
                        "op": "regroup",
                        "networkIndex": ni,
                        "moduleIndex": rng.choice([index, rng.randrange(1000)]),
                    }
                )
        elif r < 0.25:
            op = {"op": "moveModule", "networkIndex": ni, "moduleIndex": rng.randrange(1000)}
            ops.append({**op, "direction": rng.choice(["up", "down"])})
        elif r < 0.28:
            ops.append({"op": "resetLayout"})
        elif r < 0.4:
            levels = (
                rng.randint(1, 4) if rng.random() < 0.7 else [rng.randint(1, 4) for _ in range(num_networks)]
            )
            ops.append({"op": "moduleLevel", "levels": levels})
        elif r < 0.5:
            nodes = [
                {"networkIndex": rng.randrange(num_networks), "leafIndex": rng.randrange(1000)}
                for _ in range(rng.randint(0, 4))
            ]
            ops.append({"op": "colorSelectedNodes", "nodes": nodes, "color": rng.choice(COLORS)})
        elif r < 0.6:
            kind = rng.choice(["colorMatchingModules", "colorModuleIds", "colorNodesInModule"])
            op = {
                "op": kind,
                "networkIndex": ni,
                "moduleIndex": rng.randrange(1000),
                "color": rng.choice(COLORS),
            }
            if kind == "colorMatchingModules" and rng.random() < 0.4:
                op["side"] = rng.choice([-1, 1])
            ops.append(op)
        elif r < 0.7:
            ops.append({"op": rng.choice(["colorByLayer", "colorByPhysicalId"])})
        elif r < 0.8:
            cats = rng.sample(["a", "b", "c", "zz"], rng.randint(1, 4))
            ops.append(
                {
                    "op": "colorCategoricalMetadata",
                    "name": "c",
                    "colors": [[c, rng.choice(COLORS)] for c in cats],
                }
            )
        elif r < 0.87:
            edges = sorted(rng.sample([0, 0.25, 0.5, 0.75, 1, 1.2], rng.randint(2, 4)))
            bins = [{"x0": a, "x1": b, "color": rng.choice(COLORS)} for a, b in itertools.pairwise(edges)]
            ops.append({"op": "colorRealMetadata", "name": "x", "bins": bins})
        elif r < 0.94:
            breaks = sorted(rng.sample([0.1, 0.25, 0.5, 0.75, 1], rng.randint(1, 3)))
            colors = [rng.choice(COLORS) for _ in range(len(breaks) + 1)]
            centers = [round(rng.random() * 1.2, 3) for _ in range(rng.randint(0, 3))]
            ops.append(
                {
                    "op": "colorRealIntervals",
                    "name": "x",
                    "breaks": breaks,
                    "colors": colors,
                    "centers": centers,
                }
            )
        else:
            ops.append({"op": "setDefaultHighlightColor", "color": rng.choice(COLORS)})
    return ops


MODULE_NAMES = ["Physics", "", "Physics", "a b", 'q"uote', "ünïcode ∑", "x" * 40, "0", " ", "tab\there"]


def _module_order_spec(rng: random.Random) -> list | str:
    r = rng.random()
    if r < 0.15:
        return rng.choice(["reverse", "rotate"])
    spec: list = [rng.randrange(1000) for _ in range(rng.choice([0, 1, 1, 2, 3, 5, 8]))]
    if rng.random() < 0.4:
        spec.insert(rng.randint(0, len(spec)), "...")
    return spec


def _v4_ops(rng: random.Random, num_networks: int) -> list[dict]:
    """``num_networks`` as for ``_v2_ops``."""
    ops: list[dict] = []
    for _ in range(rng.choice([1, 1, 2, 2, 3, 4])):
        r = rng.random()
        if r < 0.5:
            order = [
                [rng.randrange(num_networks), _module_order_spec(rng)]
                for _ in range(rng.choice([1, 1, 2, 3]))
            ]
            ops.append({"op": "moduleOrder", "order": order})
        elif r < 0.8:
            names = [
                [rng.randrange(num_networks), rng.randrange(1000), rng.choice(MODULE_NAMES)]
                for _ in range(rng.choice([1, 1, 2, 3, 6]))
            ]
            ops.append({"op": "moduleNames", "names": names})
        else:
            ni = rng.randrange(num_networks)
            ops.append(
                {
                    "op": "setModuleName",
                    "networkIndex": ni,
                    "moduleIndex": rng.randrange(1000),
                    "name": rng.choice(MODULE_NAMES),
                }
            )
    return ops


C3_SCHEMES = [
    "C3 Sinebow",
    "C3 Oklch",
    "C3 Turbo",
    "C3 Rainbow",
    "C3 Viridis",
    "Viridis",
    "Spectral",
    "Blues",
    "Cubehelix",
    "Warm",
    "Rainbow",
    "Paired",
    "Tableau20",
    "Mural",
]
C3_TONES = ["vivid", "bright", "strong", "deep", "dark", "soft", "pastel", "muted"]


def _c3_offset(rng: random.Random) -> float | None:
    return rng.choice(
        [
            None,
            0,
            245,
            -30,
            90.5,
            359.999,
            360,
            720.25,
            -1000,
            1e6,
            -0.5,
            1e-12,
            -3e17,
            rng.uniform(-400, 400),
        ]
    )


def _c3_color(rng: random.Random) -> dict:
    """DiagramStore ctor colour options (``colorScheme``, ``colorTone``, ``colorOffset``), each sometimes."""
    color: dict = {}
    if rng.random() < 0.6:
        color["colorScheme"] = rng.choice(C3_SCHEMES)
    if rng.random() < 0.6:
        color["colorTone"] = rng.choice(C3_TONES)
    if rng.random() < 0.5:
        color["colorOffset"] = _c3_offset(rng)
    return color


def _c3_ops(rng: random.Random, num_networks: int) -> list[dict]:
    """``num_networks`` as for ``_v2_ops``."""
    ops: list[dict] = []
    for _ in range(rng.choice([1, 2, 2, 3, 4])):
        r = rng.random()
        if r < 0.3:
            if rng.random() < 0.5:
                ops.append({"op": "moduleLevel", "levels": rng.randint(1, 4)})
            ops.append({"op": "colorModuleHierarchyInAllNetworks"})
        elif r < 0.45:
            ops.append({"op": "setSelectedScheme", "name": rng.choice(C3_SCHEMES)})
        elif r < 0.6:
            ops.append({"op": "setSelectedTone", "tone": rng.choice(C3_TONES)})
        elif r < 0.75:
            offset = _c3_offset(rng)
            # null: c3's default (the TS setter is typed number, but the app could pass the store's null back)
            ops.append({"op": "setSelectedOffset", "offset": offset})
        else:
            op = rng.choice(
                [
                    "colorMatchingModulesInAllNetworks",
                    "colorModuleIdsInAllNetworks",
                    "colorNodesInModulesInAllNetworks",
                ]
            )
            ops.append({"op": op})
    return ops


def _input_profile(seed: int, num_networks: int) -> dict:
    """v2 input variations, drawn from their own ``random.Random(f"v2in-{seed}")`` (about half the cases get none,
    and then the files are the v1 files): ``json`` (file indices written as Infomap JSON; ``json_metadata`` adds
    per-node ``metadata``), ``layers`` + ``split`` (multilayer state networks, some split into layers; rarely a
    non-multilayer file is split, which must raise on both sides), ``shapes`` (per file: deep, chain, flat or
    singleton hierarchies) and ``dup_prob`` (many duplicate identifiers)."""
    rng = random.Random(f"v2in-{seed}")
    profile: dict = {}
    if rng.random() < 0.2:
        profile["json"] = sorted(
            range(num_networks)
            if rng.random() < 0.5
            else rng.sample(range(num_networks), rng.randint(1, num_networks))
        )
        profile["json_metadata"] = rng.random() < 0.5
    if rng.random() < 0.15:
        profile["layers"] = rng.random() < 0.95
        profile["split"] = sorted(rng.sample(range(num_networks), rng.randint(1, num_networks)))
    if rng.random() < 0.2:
        shape = rng.choice(["deep", "chain", "flat", "singletons"])
        profile["shapes"] = {i: shape for i in range(num_networks) if rng.random() < 0.7}
    if rng.random() < 0.1:
        profile["dup_prob"] = 0.9
    return profile


def make_case(seed: int, out_dir: Path, v2: bool = False, v4: bool = False, c3: bool = False) -> dict:
    """Write case ``seed-NNNNNN`` under ``out_dir`` and return its ``case.json`` dict (``c3`` implies ``v4``, which
    implies ``v2``)."""
    v4 = v4 or c3
    v2 = v2 or v4
    global _NON_FINITE_CASE
    _NON_FINITE_CASE = random.Random(f"nonfinite-{seed}").random() < 0.01
    rng = random.Random(seed)
    name = f"seed-{seed:06d}"
    case_dir = Path(out_dir).resolve() / name
    case_dir.mkdir(parents=True, exist_ok=True)
    num_networks = rng.choice([1, 2, 2, 2, 3, 3, 4, 5, 6])
    uni = Universe(rng)
    profile = _input_profile(seed, num_networks) if v2 else {}
    state = rng.random() < 0.25 or profile.get("layers", False)
    layers = (state and rng.random() < 0.3) or profile.get("layers", False)
    same_fmt = rng.random() < 0.7
    fmt0 = rng.choice(["tree", "ftree", "stree", "clu"])
    files = []
    for i in range(num_networks):
        fmt = fmt0 if same_fmt else rng.choice(["tree", "ftree", "stree", "clu"])
        if i in profile.get("json", ()):
            fmt = "json"
        path = case_dir / f"net{i}.{fmt}"
        text = _network_text(
            rng,
            uni,
            fmt,
            state,
            layers,
            shape=profile.get("shapes", {}).get(i),
            dup_prob=profile.get("dup_prob", 0.1),
            json_metadata=profile.get("json_metadata", False),
        )
        path.write_text(text, encoding="utf-8")
        files.append(str(path))
    options = {k: _rand_option(rng, k) for k in OPTION_CHOICES if rng.random() < 0.4}
    case = {
        "name": name,
        "seed": seed,
        "files": files,
        "identifier": "name" if rng.random() < 0.25 else "id",
        "options": options,
        "ops": _ops(rng, num_networks),
    }
    if v2:
        if profile.get("split"):
            case["split"] = profile["split"]
        rng2 = random.Random(f"v2-{seed}")
        ops = case["ops"]
        for op in _v2_ops(rng2, num_networks * (3 if profile.get("split") else 1)):
            ops.insert(rng2.randint(0, len(ops)), op)
        if rng2.random() < 0.5:
            case["nodeMetadata"] = [
                [_metadata_value(rng2) for _ in range(_num_rows(Path(f).read_text(encoding="utf-8")))]
                for f in files
            ]
        case["v2"] = True
    if v4:
        rng4 = random.Random(f"v4-{seed}")
        ops = case["ops"]
        for op in _v4_ops(rng4, num_networks * (3 if profile.get("split") else 1)):
            ops.insert(rng4.randint(0, len(ops)), op)
        case["v4"] = True
    if c3:
        rng3 = random.Random(f"c3-{seed}")
        color = _c3_color(rng3)
        if color:
            case["color"] = color
        ops = case["ops"]
        for op in _c3_ops(rng3, num_networks * (3 if profile.get("split") else 1)):
            ops.insert(rng3.randint(0, len(ops)), op)
        case["c3"] = True
        open_spec = c3_open(seed, num_networks)
        if open_spec:
            case["open"] = open_spec
    (case_dir / "case.json").write_text(json.dumps(case, indent=1, ensure_ascii=False), encoding="utf-8")
    return case


# Saved diagram-block values for c3_open: {"delete": True} drops the key, {"raw": text} is a JSON literal written
# as is (numbers JSON.parse reads as non-finite or -0), anything else is written as JSON.
_DELETE = {"delete": True}
C3_OPEN_VALUES = {
    "colorScheme": [_DELETE, "c3 sinebow", "toString", "__proto__", 3, None, *C3_SCHEMES],
    "colorTone": [
        _DELETE,
        "Strong",
        "toString",
        "constructor",
        "__proto__",
        "",
        5,
        None,
        True,
        ["strong"],
        *C3_TONES,
    ],
    "colorOffset": [
        _DELETE,
        "90",
        True,
        False,
        [],
        {},
        None,
        [90],
        {"raw": "1e400"},
        {"raw": "-1e400"},
        {"raw": "1" + "0" * 400},
        {"raw": "-0"},
        {"raw": "-0.0"},
        {"raw": "1E2"},
        -1e-7,
        -5e-324,
        1e308,
        359.5,
        -720,
        0,
        12.25,
    ],
}


def c3_open(seed: int, num_files: int) -> dict:
    """How the c3 fuzz case's Python-saved files are opened (``test_fuzz_python_save_ts_open_c3``), from
    ``random.Random(f"c3open-{seed}")``: sometimes a ``reloadStore`` (the opening store's ctor scheme, tone and
    offset; the restore rules of #57 depend on it), and sometimes ``mutations`` of the saved diagram blocks
    (``colorScheme``, ``colorTone``, ``colorOffset`` set to valid, invalid or odd values, or removed) in all files
    or in ``mutateFiles`` (saved positions) only."""
    rng = random.Random(f"c3open-{seed}")
    out: dict = {}
    if rng.random() < 0.6:
        out["reloadStore"] = _c3_color(rng)
    if rng.random() < 0.6:
        mutations = [
            {"key": key, "value": _c3_open_value(rng, key, values)}
            for key, values in C3_OPEN_VALUES.items()
            if rng.random() < 0.6
        ]
        if mutations:
            out["mutations"] = mutations
            if num_files > 1 and rng.random() < 0.3:
                out["mutateFiles"] = sorted(rng.sample(range(num_files), rng.randint(1, num_files)))
    return out


def _c3_open_value(rng: random.Random, key: str, values: list):
    if key == "colorOffset" and rng.random() < 0.3:
        return rng.choice(
            [rng.uniform(-1e3, 1e3), rng.uniform(-1, 1), rng.uniform(-1e18, 1e18), rng.random() * 1e-300]
        )
    return rng.choice(values)


def mutate_saved_texts(texts: list[tuple[str, str]], spec: dict | None) -> list[tuple[str, str]]:
    """The saved files with the diagram blocks edited by a ``c3_open`` spec (same as ``mutateSavedTexts`` in
    harness.ts): file ``i`` (in saved order) is edited when there is no ``mutateFiles`` or some ``j`` in it has
    ``j % n == i``; ``{"delete": True}`` removes the key, ``{"raw": text}`` writes ``text`` as the JSON literal, anything
    else is set as is."""
    mutations = (spec or {}).get("mutations")
    if not mutations:
        return texts
    n = len(texts)
    files = spec.get("mutateFiles")
    out = []
    for i, (name, text) in enumerate(texts):
        if files is not None and not any(j % n == i for j in files):
            out.append((name, text))
            continue
        value = json.loads(text)
        diagram = value["alluvial"]["diagram"]
        raws: list[str] = []
        for m in mutations:
            key, v = m["key"], m["value"]
            if isinstance(v, dict) and v.get("delete") is True:
                diagram.pop(key, None)
            elif isinstance(v, dict) and isinstance(v.get("raw"), str):
                diagram[key] = f"@@RAW{len(raws)}@@"
                raws.append(v["raw"])
            else:
                diagram[key] = v
        new = json.dumps(value, indent=2, ensure_ascii=False)
        for k, raw in enumerate(raws):
            new = new.replace(f'"@@RAW{k}@@"', raw, 1)
        out.append((name, new))
    return out


def make_cases(seeds, out_dir: Path, v2: bool = False, v4: bool = False, c3: bool = False) -> list[dict]:
    return [make_case(s, Path(out_dir), v2, v4, c3) for s in seeds]


def _parse_seeds(spec: str) -> range:
    a, _, b = spec.partition(":")
    return range(int(a), int(b)) if b else range(int(a), int(a) + 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--seeds", default="0:30", help="START:STOP (half-open) or a single seed")
    ap.add_argument(
        "--v2", action="store_true", help="add v2 ops and node metadata (see the module docstring)"
    )
    ap.add_argument(
        "--v4", action="store_true", help="v2 plus module order/name macros (see the module docstring)"
    )
    ap.add_argument(
        "--c3",
        action="store_true",
        help="v4 plus c3 tone/offset/scheme/hierarchy ops (see the module docstring)",
    )
    args = ap.parse_args()
    cases = make_cases(_parse_seeds(args.seeds), args.out_dir, args.v2, args.v4, args.c3)
    print(f"wrote {len(cases)} cases to {args.out_dir}")
