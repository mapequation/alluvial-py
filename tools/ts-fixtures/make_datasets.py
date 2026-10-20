#!/usr/bin/env python
"""Generate the seeded Infomap datasets used by the alluvial-py tests.

Run from anywhere, with the project venv (PyPI ``infomap`` 2.15.1 wheel):

    .venv/bin/python tools/ts-fixtures/make_datasets.py

The datasets were regenerated with that wheel on 2026-10-10. Earlier they came from a dev build of Infomap
2.15.1, which writes an extra ``# seed`` header line and finds different partitions for ``multilevel_t*``, so
the Infomap-object reader tests could not compare against them. Run with the wheel to reproduce the files.

Writes into ``tests/data/`` (relative to the repo root) and records every
generator parameter, seed and Infomap argument string in
``tests/data/datasets.json``.

Determinism
-----------
* Graphs come from ``random.Random(seed)`` with fixed seeds (stdlib Mersenne
  Twister, stable across CPython versions for ``random()``).
* Infomap is run with a fixed ``seed`` and ``num_trials``.
* Infomap writes a wall-clock ``# started at`` and ``# completed in`` header
  line. Both are replaced with fixed placeholders, so re-running this script
  reproduces the files byte for byte (given the Infomap 2.15.1 PyPI wheel). The TS parser is
  called with ``strictHeader=false`` and ignores those lines for layout.

Datasets
--------
(a) ``planted_t{0,1,2}``: three undirected time slices of a planted partition
    (~100-130 nodes), with nodes disappearing/appearing and groups
    splitting/merging. Written as .ftree, .tree and .clu (two-level).
(b) ``states_t{0,1}``: an undirected state (memory) network. Physical nodes
    in two overlapping topics get one state node per topic. Written with
    ``states=True`` as .tree, .ftree and .clu
    (``# path flow name state_id node_id`` / ``# state_id module flow node_id``).
(c) ``multilevel_t{0,1,2}``: hierarchical planted partition (4 super groups x
    3 sub groups x 9 nodes), multilevel Infomap, giving 3-level trees
    (``a:b:c``). Written as .tree and .ftree.
(d) ``directed_t{0,1}``: directed planted network, ``directed=True``,
    two-level. Written as .ftree (with ``*Links directed``) and .tree.

v2 datasets (recorded under ``v2_datasets`` in ``datasets.json``, so the v1 reader tests that iterate
``datasets`` are unaffected):

(e) ``planted_t{0,1,2}.json`` / ``states_t{0,1}.json``: ``write_json`` of the runs in (a) and (b)
    (``startedAt``/``completedIn`` normalized like the text headers).
(f) ``mlayer_states.{tree,json}``: a seeded multilayer network (3 super x 3 sub x 5 physical nodes, four
    layers added in the order 3, 1, 4, 2, intra-layer links only), multilevel Infomap, ``states=True``.
    ``mlayer_flat.tree``: the same links aggregated over layers, first order (same physical node ids).
    ``mlayer_named.json``: ``mlayer_states.json`` plus a hand-made ``layers`` list (one id given as a
    string, so it does not match under the TS strict ``===``).
(g) ``prefix_t{0,1}.tree``: synthetic (no Infomap) 12-top-module trees, so ``"1"`` is a string prefix of
    ``"10"``-``"12"`` and ``"1:1"`` of ``"1:10"``/``"1:11"`` (the TS ``isAncestor`` prefix bug, fixed in fix round WP3/E2). Seeded flows.
(h) ``hlskip_t{0,1,2}.tree``: hand-written (literal text below), triggers the visible-leaf-walk skip of
    the TS metadata/layer/physical-id colour ops.
(i) ``dupname_t{0,1}.tree``: hand-written (literal text below), a duplicate name in one module of t1; with
    ``identifier="name"`` one of its leaves sits in a streamline node detached from the tree (minimised v2 fuzz case).
(j) ``abcchain_t{0,1,2}.tree``: hand-written (literal text below), the a/b/c similarity chain of colors-render.md
    §6.1: a similarity chain that starts in network 1 (``b.2`` -> ``c.1``) shares the colour counter of pair 0 (S1).
(k) ``multilevel_mixed_t0.json``: derived from ``multilevel_t0.tree`` (no Infomap run): a minimal JSON ``nodes`` list
    (string paths) where the leaves below ``1:1`` carry ``"moduleLevel": 2`` and every other leaf the default 1, so
    the visible module ``1`` is shown together with its visible sub-module ``1:1`` (``Network.tree``, fix round E15a).
(l) ``bipartite_t{0,1}.json``: hand-written (literal values below), Infomap JSON with ``bipartiteStartId`` 5: nodes
    5-8 are the second node type, which ``showBipartiteNodes: false`` hides (fix round WP9/E19); module 3 of t0 holds
    only such nodes.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

import infomap

EXPECTED_INFOMAP = "2.15.1"

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "data"

STARTED_RE = re.compile(r"^# started at .*$", re.M)
COMPLETED_RE = re.compile(r"^# completed in .* s$", re.M)


def normalize_header(path: Path) -> None:
    text = path.read_text()
    text = STARTED_RE.sub("# started at 1970-01-01 00:00:00", text)
    text = COMPLETED_RE.sub("# completed in 0 s", text)
    path.write_text(text)


STARTED_JSON_RE = re.compile(r'"startedAt":"[^"]*"')
COMPLETED_JSON_RE = re.compile(r'"completedIn":[-+0-9.eE]+')


def normalize_json(path: Path) -> None:
    text = path.read_text()
    text = STARTED_JSON_RE.sub('"startedAt":"1970-01-01 00:00:00"', text)
    text = COMPLETED_JSON_RE.sub('"completedIn":0', text)
    path.write_text(text)


def write_outputs(im: infomap.Infomap, stem: str, kinds: list[str], states: bool) -> list[str]:
    files = []
    for kind in kinds:
        path = OUT / f"{stem}.{kind}"
        if kind == "tree":
            im.write_tree(str(path), states=states)
        elif kind == "ftree":
            im.write_flow_tree(str(path), states=states)
        elif kind == "json":
            im.write_json(str(path), states=states)
            normalize_json(path)
            files.append(path.name)
            continue
        elif kind == "clu":
            # depth_level=1: top modules, matches the TS clu path = moduleId
            im.write_clu(str(path), states=states, depth_level=1)
        else:  # pragma: no cover
            raise ValueError(kind)
        normalize_header(path)
        files.append(path.name)
    return files


def first_args_line(path: Path) -> str:
    # The second header line of every output file holds the effective args.
    for line in path.read_text().splitlines()[:3]:
        if line.startswith("# ./Infomap"):
            return line[2:]
    return ""


# ---------------------------------------------------------------------------
# (a) planted partition time slices
# ---------------------------------------------------------------------------

PLANTED_SLICES = [
    # Each slice: group label -> list of global entity ids (1-based node ids).
    # t0: four groups of 30, entities 111-120 not yet present.
    {
        "A": list(range(1, 31)),
        "B": list(range(31, 61)),
        "C": list(range(61, 91)),
        "D": list(range(91, 111)),
    },
    # t1: A loses 1-8, C splits (76-90 joins D), 111-120 appear in D.
    {
        "A": list(range(9, 31)),
        "B": list(range(31, 61)),
        "C": list(range(61, 76)),
        "D": list(range(76, 121)),
    },
    # t2: A and B merge, new group E (121-135) appears, D loses 101-110.
    {
        "AB": list(range(9, 61)),
        "C": list(range(61, 76)),
        "D": list(range(76, 101)) + list(range(111, 121)),
        "E": list(range(121, 136)),
    },
]
PLANTED_P_IN = 0.3
PLANTED_P_OUT = 0.01
PLANTED_GRAPH_SEEDS = [1001, 1002, 1003]
PLANTED_INFOMAP = dict(two_level=True, num_trials=10, seed=123, silent=True)


def planted_edges(rng: random.Random, groups: dict[str, list[int]], p_in: float, p_out: float):
    group_of = {n: g for g, ns in groups.items() for n in ns}
    nodes = sorted(group_of)
    edges = []
    for i, u in enumerate(nodes):
        for v in nodes[i + 1 :]:
            p = p_in if group_of[u] == group_of[v] else p_out
            if rng.random() < p:
                edges.append((u, v))
    return nodes, edges


def build_planted(t: int):
    groups, gseed = PLANTED_SLICES[t], PLANTED_GRAPH_SEEDS[t]
    rng = random.Random(gseed)
    nodes, edges = planted_edges(rng, groups, PLANTED_P_IN, PLANTED_P_OUT)
    im = infomap.Infomap(**PLANTED_INFOMAP)
    for n in nodes:
        im.add_node(n, name=f"v{n}")
    for u, v in edges:
        im.add_link(u, v)
    res = im.run()
    return im, res, {"nodes": nodes, "edges": edges}


def make_planted(manifest: dict, v2: dict) -> None:
    for t, (groups, gseed) in enumerate(zip(PLANTED_SLICES, PLANTED_GRAPH_SEEDS)):
        im, res, graph = build_planted(t)
        nodes, edges = graph["nodes"], graph["edges"]
        stem = f"planted_t{t}"
        files = write_outputs(im, stem, ["ftree", "tree", "clu"], states=False)
        v2[f"{stem}.json"] = {
            "kind": f"write_json of {stem} (same run)",
            "files": write_outputs(im, stem, ["json"], False),
        }
        manifest[stem] = {
            "kind": "planted partition time slice (undirected, unweighted)",
            "files": files,
            "graph_seed": gseed,
            "p_in": PLANTED_P_IN,
            "p_out": PLANTED_P_OUT,
            "groups": {g: [min(ns), max(ns), len(ns)] for g, ns in groups.items()},
            "num_nodes": len(nodes),
            "num_links": len(edges),
            "node_names": "v<node_id>",
            "infomap_kwargs": PLANTED_INFOMAP,
            "infomap_args": first_args_line(OUT / files[0]),
            "num_top_modules": res.num_top_modules,
            "max_depth": res.max_depth,
            "codelength": res.codelength,
        }


# ---------------------------------------------------------------------------
# (b) state (memory) network slices
# ---------------------------------------------------------------------------

# Physical nodes 1..36 in three topics. Overlapping physical nodes get one
# state node per topic: state_id = 10 * node_id + topic (stable across slices).
STATES_SLICES = [
    {"topics": {0: list(range(1, 15)), 1: list(range(11, 27)), 2: list(range(25, 37))}, "drop": []},
    {"topics": {0: list(range(1, 13)), 1: list(range(9, 25)), 2: list(range(23, 37))}, "drop": [5, 30]},
]
STATES_P_IN = 0.35
STATES_P_OUT = 0.02
STATES_GRAPH_SEEDS = [2001, 2002]
STATES_INFOMAP = dict(two_level=True, num_trials=10, seed=123, silent=True)


def build_states(t: int):
    spec, gseed = STATES_SLICES[t], STATES_GRAPH_SEEDS[t]
    rng = random.Random(gseed)
    drop = set(spec["drop"])
    states = []  # (state_id, node_id, topic)
    for topic, phys in spec["topics"].items():
        for p in phys:
            if p in drop:
                continue
            states.append((10 * p + topic, p, topic))
    states.sort()
    edges = []
    for i, (s, p, tp) in enumerate(states):
        for s2, p2, tp2 in states[i + 1 :]:
            if p == p2:
                continue
            prob = STATES_P_IN if tp == tp2 else STATES_P_OUT
            if rng.random() < prob:
                edges.append((s, s2))
    im = infomap.Infomap(**STATES_INFOMAP)
    for s, p, _ in states:
        im.add_state_node(s, p)
    for p in sorted({p for _, p, _ in states}):
        im.set_name(p, f"p{p}")
    for u, v in edges:
        im.add_link(u, v)
    res = im.run()
    return im, res, {"states": states, "edges": edges}


def make_states(manifest: dict, v2: dict) -> None:
    for t, (spec, gseed) in enumerate(zip(STATES_SLICES, STATES_GRAPH_SEEDS)):
        im, res, graph = build_states(t)
        states, edges = graph["states"], graph["edges"]
        stem = f"states_t{t}"
        files = write_outputs(im, stem, ["tree", "ftree", "clu"], states=True)
        v2[f"{stem}.json"] = {
            "kind": f"write_json(states=True) of {stem} (same run)",
            "files": write_outputs(im, stem, ["json"], True),
        }
        manifest[stem] = {
            "kind": "state network slice (undirected, states=True outputs)",
            "files": files,
            "graph_seed": gseed,
            "p_in": STATES_P_IN,
            "p_out": STATES_P_OUT,
            "topics": {str(k): [min(v), max(v)] for k, v in spec["topics"].items()},
            "dropped_physical_nodes": spec["drop"],
            "state_id_formula": "10 * node_id + topic",
            "node_names": "p<node_id> (physical name shared by its state nodes)",
            "num_state_nodes": len(states),
            "num_links": len(edges),
            "infomap_kwargs": STATES_INFOMAP,
            "infomap_args": first_args_line(OUT / files[0]),
            "num_top_modules": res.num_top_modules,
            "max_depth": res.max_depth,
            "codelength": res.codelength,
        }


# ---------------------------------------------------------------------------
# (c) multilevel hierarchical slices
# ---------------------------------------------------------------------------

ML_SUPER, ML_SUB, ML_SIZE = 4, 3, 9
ML_P_SUB = 0.7
ML_P_SUPER = 0.08
ML_P_OUT = 0.004
ML_GRAPH_SEEDS = [3001, 3002, 3003]
ML_DROP_FRACTION = 0.08
ML_INFOMAP = dict(num_trials=10, seed=123, silent=True)  # multilevel (default)


def build_multilevel(t: int):
    n_total = ML_SUPER * ML_SUB * ML_SIZE
    rng = random.Random(ML_GRAPH_SEEDS[t])
    # node id -> (super, sub); in t2 sub group (0, 2) moves to super 1
    labels = {}
    for n in range(1, n_total + 1):
        k = (n - 1) // ML_SIZE
        sup, sub = divmod(k, ML_SUB)
        if t == 2 and (sup, sub) == (0, 2):
            sup = 1
            sub = ML_SUB  # new sub group index inside super 1
        labels[n] = (sup, sub)
    present = [n for n in range(1, n_total + 1) if rng.random() >= ML_DROP_FRACTION]
    edges = []
    for i, u in enumerate(present):
        for v in present[i + 1 :]:
            (su, bu), (sv, bv) = labels[u], labels[v]
            if su == sv and bu == bv:
                p = ML_P_SUB
            elif su == sv:
                p = ML_P_SUPER
            else:
                p = ML_P_OUT
            if rng.random() < p:
                edges.append((u, v))
    im = infomap.Infomap(**ML_INFOMAP)
    for n in present:
        im.add_node(n, name=f"m{n}")
    for u, v in edges:
        im.add_link(u, v)
    res = im.run()
    return im, res, {"present": present, "edges": edges}


def make_multilevel(manifest: dict) -> None:
    for t, gseed in enumerate(ML_GRAPH_SEEDS):
        im, res, graph = build_multilevel(t)
        present, edges = graph["present"], graph["edges"]
        stem = f"multilevel_t{t}"
        files = write_outputs(im, stem, ["tree", "ftree"], states=False)
        manifest[stem] = {
            "kind": "hierarchical planted partition slice (undirected, multilevel)",
            "files": files,
            "graph_seed": gseed,
            "super_groups": ML_SUPER,
            "sub_groups_per_super": ML_SUB,
            "nodes_per_sub_group": ML_SIZE,
            "p_sub": ML_P_SUB,
            "p_super": ML_P_SUPER,
            "p_out": ML_P_OUT,
            "drop_fraction": ML_DROP_FRACTION,
            "t2_moves_sub_group": "(super 0, sub 2) -> super 1" if t == 2 else None,
            "node_names": "m<node_id>",
            "num_nodes": len(present),
            "num_links": len(edges),
            "infomap_kwargs": ML_INFOMAP,
            "infomap_args": first_args_line(OUT / files[0]),
            "num_top_modules": res.num_top_modules,
            "max_depth": res.max_depth,
            "codelength": res.codelength,
        }
        if res.max_depth < 3:
            print(f"warning: {stem} has max_depth {res.max_depth} < 3", file=sys.stderr)


# ---------------------------------------------------------------------------
# (d) directed slices
# ---------------------------------------------------------------------------

DIR_GROUPS = [
    {"A": list(range(1, 26)), "B": list(range(26, 51)), "C": list(range(51, 76))},
    {"A": list(range(1, 31)), "B": list(range(31, 51)), "C": list(range(51, 81))},
]
DIR_P_IN = 0.15
DIR_P_OUT = 0.012
DIR_GRAPH_SEEDS = [4001, 4002]
DIR_INFOMAP = dict(directed=True, two_level=True, num_trials=10, seed=123, silent=True)


def build_directed(t: int):
    groups, gseed = DIR_GROUPS[t], DIR_GRAPH_SEEDS[t]
    rng = random.Random(gseed)
    group_of = {n: g for g, ns in groups.items() for n in ns}
    nodes = sorted(group_of)
    edges = []
    # a directed cycle inside each group keeps flow circulating
    for ns in groups.values():
        for a, b in zip(ns, ns[1:] + ns[:1]):
            edges.append((a, b, 1.0))
    for u in nodes:
        for v in nodes:
            if u == v:
                continue
            p = DIR_P_IN if group_of[u] == group_of[v] else DIR_P_OUT
            if rng.random() < p:
                edges.append((u, v, 1.0 + rng.random()))
    im = infomap.Infomap(**DIR_INFOMAP)
    for n in nodes:
        im.add_node(n, name=f"d{n}")
    for u, v, w in edges:
        im.add_link(u, v, w)
    res = im.run()
    return im, res, {"nodes": nodes, "edges": edges}


def make_directed(manifest: dict) -> None:
    for t, (groups, gseed) in enumerate(zip(DIR_GROUPS, DIR_GRAPH_SEEDS)):
        im, res, graph = build_directed(t)
        nodes, edges = graph["nodes"], graph["edges"]
        stem = f"directed_t{t}"
        files = write_outputs(im, stem, ["ftree", "tree"], states=False)
        manifest[stem] = {
            "kind": "directed planted slice (weighted, directed flow model)",
            "files": files,
            "graph_seed": gseed,
            "p_in": DIR_P_IN,
            "p_out": DIR_P_OUT,
            "groups": {g: [min(ns), max(ns), len(ns)] for g, ns in groups.items()},
            "weights": "cycle links 1.0, random links 1 + U(0,1)",
            "node_names": "d<node_id>",
            "num_nodes": len(nodes),
            "num_links": len(edges),
            "infomap_kwargs": DIR_INFOMAP,
            "infomap_args": first_args_line(OUT / files[0]),
            "num_top_modules": res.num_top_modules,
            "max_depth": res.max_depth,
            "codelength": res.codelength,
        }


# ---------------------------------------------------------------------------
# (f) multilayer state network (v2: layer splitting, colorByLayer)
# ---------------------------------------------------------------------------

MLAYER_SUPER, MLAYER_SUB, MLAYER_SIZE = 3, 3, 5
MLAYER_LAYERS = [3, 1, 4, 2]  # order in which the layers' links are added
MLAYER_P_SUB = 0.8
MLAYER_P_SUPER = 0.1
MLAYER_P_OUT = 0.002
MLAYER_DROP_FRACTION = 0.12
MLAYER_GRAPH_SEED = 5001
MLAYER_INFOMAP = dict(num_trials=5, seed=123, silent=True)  # multilevel, default multilayer relax rate
MLAYER_LAYER_NAMES = [
    {"id": 1, "name": "Alpha"},
    {"id": 3, "name": "Gamma"},
    {"id": "4", "name": "not matched"},
]


def mlayer_links():
    n_total = MLAYER_SUPER * MLAYER_SUB * MLAYER_SIZE
    rng = random.Random(MLAYER_GRAPH_SEED)
    labels = {n: divmod((n - 1) // MLAYER_SIZE, MLAYER_SUB) for n in range(1, n_total + 1)}
    links = []  # (layer, u, v, weight)
    for layer in MLAYER_LAYERS:
        present = [n for n in range(1, n_total + 1) if rng.random() >= MLAYER_DROP_FRACTION]

        def label(n, layer=layer):
            sup, sub = labels[n]
            if layer == 4 and (sup, sub) == (1, 1):  # in layer 4 sub group (1, 1) joins super group 0
                return (0, MLAYER_SUB)
            return (sup, sub)

        for i, u in enumerate(present):
            for v in present[i + 1 :]:
                (su, bu), (sv, bv) = label(u), label(v)
                p = MLAYER_P_SUB if (su, bu) == (sv, bv) else MLAYER_P_SUPER if su == sv else MLAYER_P_OUT
                if rng.random() < p:
                    links.append((layer, u, v, 1 + round(rng.random(), 3)))
    return n_total, links


def build_mlayer(flat: bool = False):
    n_total, links = mlayer_links()
    im = infomap.Infomap(**MLAYER_INFOMAP)
    if flat:
        weights: dict = {}
        for _layer, u, v, w in links:
            weights[(u, v)] = weights.get((u, v), 0) + w
        nodes = sorted({n for _l, u, v, _w in links for n in (u, v)})
        for n in nodes:
            im.add_node(n, name=f"p{n}")
        for (u, v), w in weights.items():
            im.add_link(u, v, w)
    else:
        for layer, u, v, w in links:
            im.add_multilayer_intra_link(layer, u, v, w)
        for n in range(1, n_total + 1):
            im.set_name(n, f"p{n}")
    res = im.run()
    return im, res, links


def make_mlayer(v2: dict) -> None:
    im, res, links = build_mlayer()
    files = write_outputs(im, "mlayer_states", ["tree", "json"], states=True)
    common = {
        "graph_seed": MLAYER_GRAPH_SEED,
        "groups": f"{MLAYER_SUPER} super x {MLAYER_SUB} sub x {MLAYER_SIZE} physical nodes",
        "p_sub": MLAYER_P_SUB,
        "p_super": MLAYER_P_SUPER,
        "p_out": MLAYER_P_OUT,
        "drop_fraction_per_layer": MLAYER_DROP_FRACTION,
        "num_links": len(links),
        "node_names": "p<node_id>",
        "infomap_kwargs": MLAYER_INFOMAP,
    }
    v2["mlayer_states"] = {
        "kind": "multilayer state network, intra-layer links only, layers added in the order 3, 1, 4, 2 (states=True)",
        "files": files,
        "layers_added": MLAYER_LAYERS,
        **common,
        "num_state_nodes": im.num_nodes,
        "infomap_args": first_args_line(OUT / files[0]),
        "num_top_modules": res.num_top_modules,
        "max_depth": res.max_depth,
        "codelength": res.codelength,
    }
    doc = json.loads((OUT / "mlayer_states.json").read_text())
    doc["layers"] = MLAYER_LAYER_NAMES
    (OUT / "mlayer_named.json").write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
    v2["mlayer_named"] = {
        "kind": 'mlayer_states.json plus a hand-made `layers` list (layer id "4" is a string: no strict match)',
        "files": ["mlayer_named.json"],
        "layers": MLAYER_LAYER_NAMES,
    }
    im, res, _ = build_mlayer(flat=True)
    files = write_outputs(im, "mlayer_flat", ["tree"], states=False)
    v2["mlayer_flat"] = {
        "kind": "mlayer_states links summed over layers, first order (same physical node ids)",
        "files": files,
        **common,
        "num_nodes": im.num_nodes,
        "infomap_args": first_args_line(OUT / files[0]),
        "num_top_modules": res.num_top_modules,
        "max_depth": res.max_depth,
        "codelength": res.codelength,
    }


# ---------------------------------------------------------------------------
# (g) prefix trees (synthetic, no Infomap; v2: the isAncestor prefix bug, fixed in WP3/E2)
# ---------------------------------------------------------------------------

PREFIX_SEEDS = [6001, 6002]
PREFIX_TOP = 12  # top modules 1..12: "1" is a string prefix of "10", "11", "12"
PREFIX_SUB_OF_1 = 11  # sub-modules 1:1..1:11: "1:1" is a prefix of "1:10", "1:11"


def prefix_rows(t: int) -> list[tuple[str, float, int]]:
    """(path, raw weight, node id) rows of prefix_t<t>. Node ids are assigned in path order and are the
    same in both slices; slice 1 only redraws the weights."""
    rng = random.Random(PREFIX_SEEDS[t])
    shape = random.Random(PREFIX_SEEDS[0])  # same tree shape in both slices
    rows = []
    node_id = 0
    for top in range(1, PREFIX_TOP + 1):
        if top == 1:
            for sub in range(1, PREFIX_SUB_OF_1 + 1):
                for subsub in (1, 2):
                    for leaf in range(1, 2 + shape.randint(1, 2)):
                        node_id += 1
                        rows.append((f"{top}:{sub}:{subsub}:{leaf}", 0.5 + rng.random(), node_id))
        else:
            for sub in (1, 2):
                for leaf in (1, 2):
                    node_id += 1
                    rows.append((f"{top}:{sub}:{leaf}", 0.5 + rng.random(), node_id))
    return rows


def make_prefix(v2: dict) -> None:
    for t in range(len(PREFIX_SEEDS)):
        rows = prefix_rows(t)
        total = sum(w for _p, w, _n in rows)
        flows = [f"{w / total:.6g}" for _p, w, _n in rows]
        if len(set(flows)) != len(flows):
            raise RuntimeError("prefix tree: tied leaf flows")
        stem = f"prefix_t{t}"
        lines = [
            "# synthetic (tools/ts-fixtures/make_datasets.py): 12 top modules, string-prefix module ids",
            "# path flow name node_id",
        ]
        lines += [f'{p} {f} "x{n}" {n}' for (p, _w, n), f in zip(rows, flows)]
        (OUT / f"{stem}.tree").write_text("\n".join(lines) + "\n")
        v2[stem] = {
            "kind": "synthetic prefix tree (no Infomap): top module 1 has 11 sub-modules x 2 sub-sub-modules x 2-3 "
            "leaves (4-level paths), top modules 2-12 have 2 sub-modules x 2 leaves (3-level paths)",
            "files": [f"{stem}.tree"],
            "weight_seed": PREFIX_SEEDS[t],
            "shape_seed": PREFIX_SEEDS[0],
            "flows": "(0.5 + U(0,1)) normalized to sum 1, 6 significant digits, no ties",
            "node_names": "x<node_id>",
            "num_nodes": len(rows),
            "num_top_modules": PREFIX_TOP,
            "max_depth": 4,
        }


# ---------------------------------------------------------------------------
# (h) hand-written skip dataset (v2-highlight.md §8.2)
# ---------------------------------------------------------------------------

HLSKIP = {
    # t0, t1: all modules visible, module 2 is single-leaf and not last, module 3 (last) is single-leaf too
    "hlskip_t0": [("1:1", 0.3, 1), ("1:2", 0.3, 2), ("2:1", 0.25, 3), ("3:1", 0.15, 4)],
    "hlskip_t1": [("1:1", 0.3, 1), ("1:2", 0.3, 2), ("2:1", 0.25, 3), ("3:1", 0.15, 4)],
    # t2: only multi-leaf modules
    "hlskip_t2": [("1:1", 0.3, 1), ("1:2", 0.3, 3), ("2:1", 0.2, 2), ("2:2", 0.2, 4)],
}


def make_hlskip(v2: dict) -> None:
    for stem, rows in HLSKIP.items():
        lines = [
            "# hand-written (v2-highlight.md §8.2): a visible single-leaf module that is not last triggers the colour-op skip",
            "# path flow name node_id",
        ]
        lines += [f'{p} {f:g} "n{n}" {n}' for p, f, n in rows]
        (OUT / f"{stem}.tree").write_text("\n".join(lines) + "\n")
    v2["hlskip"] = {
        "kind": "hand-written, see HLSKIP in make_datasets.py",
        "files": [f"{stem}.tree" for stem in HLSKIP],
    }


# ---------------------------------------------------------------------------
# (i) hand-written duplicate-name dataset (minimised v2 fuzz case, dupname-tree__highlight)
# ---------------------------------------------------------------------------

DUPNAME = {
    "dupname_t0": [("1:1", 1, "c", 17)],
    "dupname_t1": [("2:1", 0.335, "c", 2), ("2:3", 0.143, "a", 8), ("2:4", 0.804, "c", 17)],
}


def make_dupname(v2: dict) -> None:
    for stem, rows in DUPNAME.items():
        lines = [
            "# hand-written (minimised v2 fuzz case): duplicate name c, read with identifier name",
            "# path flow name node_id",
        ]
        lines += [f'{p} {f:g} "{name}" {n}' for p, f, name, n in rows]
        (OUT / f"{stem}.tree").write_text("\n".join(lines) + "\n")
    v2["dupname"] = {
        "kind": "hand-written, see DUPNAME in make_datasets.py",
        "files": [f"{stem}.tree" for stem in DUPNAME],
    }


# ---------------------------------------------------------------------------
# (j) hand-written similarity-chain dataset (colors-render.md §6.1, abc-chain__similarity, fix round WP6/S1)
# ---------------------------------------------------------------------------

ABCCHAIN = {
    "abcchain_t0": [("1:1", 0.5, 1), ("1:2", 0.5, 2)],
    "abcchain_t1": [("1:1", 0.25, 1), ("1:2", 0.25, 2), ("2:1", 0.25, 3), ("2:2", 0.25, 4)],
    "abcchain_t2": [("1:1", 0.25, 3), ("1:2", 0.25, 4), ("2:1", 0.25, 1), ("2:2", 0.25, 2)],
}


def make_abcchain(v2: dict) -> None:
    for stem, rows in ABCCHAIN.items():
        lines = [
            "# hand-written (colors-render.md §6.1): a similarity chain that starts in network 1",
            "# path flow name node_id",
        ]
        lines += [f'{p} {f:g} "n{n}" {n}' for p, f, n in rows]
        (OUT / f"{stem}.tree").write_text("\n".join(lines) + "\n")
    v2["abcchain"] = {
        "kind": "hand-written, see ABCCHAIN in make_datasets.py",
        "files": [f"{stem}.tree" for stem in ABCCHAIN],
    }


def make_mixedlevel(v2: dict) -> None:
    nodes = []
    for line in (OUT / "multilevel_t0.tree").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        path, flow, rest = line.split(" ", 2)
        name, node_id = rest.rsplit(" ", 1)
        node = {"path": path, "flow": float(flow), "name": json.loads(name), "id": int(node_id)}
        if path.startswith("1:1:"):
            node["moduleLevel"] = 2
        nodes.append(node)
    (OUT / "multilevel_mixed_t0.json").write_text(json.dumps({"nodes": nodes}, separators=(",", ":")) + "\n")
    v2["multilevel_mixed"] = {
        "kind": "derived from multilevel_t0.tree, see make_mixedlevel in make_datasets.py",
        "files": ["multilevel_mixed_t0.json"],
    }


# ---------------------------------------------------------------------------
# (l) hand-written bipartite JSON (fix round WP9/E19, bipartite-json__hidden__roundTrip)
# ---------------------------------------------------------------------------

BIPARTITE = {
    "bipartite_t0": [
        ([1, 1], 0.2, 1),
        ([1, 2], 0.1, 5),
        ([1, 3], 0.1, 2),
        ([2, 1], 0.2, 3),
        ([2, 2], 0.1, 6),
        ([2, 3], 0.1, 4),
        ([3, 1], 0.1, 7),
        ([3, 2], 0.1, 8),
    ],
    "bipartite_t1": [
        ([1, 1], 0.2, 3),
        ([1, 2], 0.1, 6),
        ([1, 3], 0.1, 1),
        ([2, 1], 0.2, 2),
        ([2, 2], 0.1, 5),
        ([2, 3], 0.1, 4),
        ([2, 4], 0.1, 7),
        ([3, 1], 0.1, 8),
    ],
}


def make_bipartite(v2: dict) -> None:
    for stem, rows in BIPARTITE.items():
        value = {
            "codelength": 1.5,
            "bipartiteStartId": 5,
            "nodes": [{"path": p, "flow": f, "name": f"n{n}", "id": n} for p, f, n in rows],
        }
        (OUT / f"{stem}.json").write_text(json.dumps(value, separators=(",", ":")) + "\n")
    v2["bipartite"] = {
        "kind": "hand-written, see BIPARTITE in make_datasets.py",
        "files": [f"{stem}.json" for stem in BIPARTITE],
    }


BUILDERS = {
    "planted": build_planted,
    "states": build_states,
    "multilevel": build_multilevel,
    "directed": build_directed,
}


def build_infomap(stem: str) -> infomap.Infomap:
    """Rebuild and run the Infomap object behind ``tests/data/<stem>.*``.

    For testing the ``infomap.Infomap`` reader against the file readers and
    the TS fixtures, e.g. ``build_infomap("states_t0")``. Nothing is written.
    The result matches the committed files given Infomap 2.15.1.
    """
    if stem in ("mlayer_states", "mlayer_flat"):
        return build_mlayer(flat=stem == "mlayer_flat")[0]
    m = re.fullmatch(r"(planted|states|multilevel|directed)_t(\d+)", stem)
    if not m:
        raise ValueError(f"unknown seeded dataset {stem!r}")
    im, _res, _graph = BUILDERS[m.group(1)](int(m.group(2)))
    return im


def main() -> None:
    if infomap.__version__ != EXPECTED_INFOMAP:
        print(
            f"warning: infomap {infomap.__version__} != {EXPECTED_INFOMAP}; "
            "outputs may differ from the committed datasets",
            file=sys.stderr,
        )
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict = {}
    v2: dict = {}
    make_planted(manifest, v2)
    make_states(manifest, v2)
    make_multilevel(manifest)
    make_directed(manifest)
    make_mlayer(v2)
    make_prefix(v2)
    make_hlskip(v2)
    make_dupname(v2)
    make_abcchain(v2)
    make_mixedlevel(v2)
    make_bipartite(v2)
    doc = {
        "generator": "tools/ts-fixtures/make_datasets.py",
        "infomap_version": infomap.__version__,
        "python": sys.version.split()[0],
        "header_normalization": {
            "# started at": "1970-01-01 00:00:00",
            "# completed in": "0 s",
        },
        "copied_from_web_app": {
            "source": "apps/web/public/data/ in the TS alluvial repo",
            "files": [
                "debug5_0.tree",
                "debug5_1.tree",
                "debug5_0.stree",
                "debug5_1.stree",
                "science2001_2y.stree",
                "science2003_2y.stree",
                "science2005_2y.stree",
                "science2007_2y.stree",
            ],
        },
        "datasets": manifest,
        "v2_datasets": v2,
    }
    (OUT / "datasets.json").write_text(json.dumps(doc, indent=2) + "\n")
    for stem, info in {**manifest, **v2}.items():
        print(
            f"{stem}: files={info['files']} top_modules={info.get('num_top_modules')} "
            f"max_depth={info.get('max_depth')}"
        )


if __name__ == "__main__":
    main()
