"""Multilayer networks: one Infomap run on a four-layer network, drawn with one network per layer.

Run with ``python examples/multilayer.py``; writes ``docs/img/multilayer.png``. Needs ``pip install "alluvial[infomap]"``.

``split_layers=True`` splits the multilayer partition into its layers (as the web app does), so the diagram shows how
each node's module changes from layer to layer. Nodes are matched across layers by their physical id.
"""

import random
from pathlib import Path

import infomap
import matplotlib.pyplot as plt

import alluvial

# Four layers (say, years) over 40 nodes. Groups of 10 nodes; in layer 3 the first two groups merge, and in layer 4
# the third group splits up.
groups_by_layer = {
    1: [range(0, 10), range(10, 20), range(20, 30), range(30, 40)],
    2: [range(0, 10), range(10, 20), range(20, 30), range(30, 40)],
    3: [range(0, 20), range(20, 30), range(30, 40)],
    4: [range(0, 20), range(20, 25), range(25, 30), range(30, 40)],
}
rng = random.Random(7)
im = infomap.Infomap(silent=True, seed=7, num_trials=5)
for layer, groups in groups_by_layer.items():
    group_of = {n: g for g, members in enumerate(groups) for n in members}
    for u in range(40):
        for v in range(u + 1, 40):
            if rng.random() < (0.5 if group_of[u] == group_of[v] else 0.01):
                im.add_multilayer_intra_link(layer, u, v)
for n in range(40):
    im.set_name(n, f"n{n}")
# The relax rate as a CLI flag works with every infomap >= 2.14 (2.15 deprecates the keyword; run(options=) is 2.15+).
im.run("--multilayer-relax-rate 0.05")

with plt.rc_context({"font.size": 8}):
    fig, ax = plt.subplots(figsize=(3.4, 2.4), layout="constrained")
    alluvial.plot([im], ax=ax, split_layers=True, max_label_lines=2)
    fig.savefig(Path(__file__).resolve().parents[1] / "docs" / "img" / "multilayer.png", dpi=300)
