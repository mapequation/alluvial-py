"""Quickstart: an alluvial diagram of two Infomap partitions of an evolving network (the README's first snippet).

Run with ``python examples/quickstart.py``; writes ``docs/img/quickstart.png``.
Needs ``pip install "alluvial[infomap]"``.
"""

import random
from pathlib import Path

import infomap

import alluvial


def run_infomap(groups, seed):
    """Infomap on a random graph with dense groups of nodes."""
    rng = random.Random(seed)
    group_of = {n: g for g, members in enumerate(groups) for n in members}
    im = infomap.Infomap(two_level=True, seed=123, silent=True)
    for u in group_of:
        for v in group_of:
            if u < v and rng.random() < (0.4 if group_of[u] == group_of[v] else 0.02):
                im.add_link(u, v)
    im.run()
    return im


im_2020 = run_infomap([range(15), range(15, 30), range(30, 45), range(45, 60)], seed=2020)
im_2021 = run_infomap([range(20), range(20, 45), range(45, 60)], seed=2021)  # groups merge

ax = alluvial.plot([im_2020, im_2021], names=["2020", "2021"])
ax.figure.savefig(Path(__file__).resolve().parents[1] / "docs" / "img" / "quickstart.png", dpi=150)
