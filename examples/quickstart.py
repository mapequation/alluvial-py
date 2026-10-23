"""Quickstart: an alluvial diagram of two partitions given as plain dicts (the README's first snippet).

Run with ``python examples/quickstart.py``; writes ``docs/img/quickstart.png``. Needs no Infomap.

Each network maps node names to modules; nodes are matched across networks by name. Without flows, every node
counts the same, so modules are sized and sorted by their number of nodes.
"""

from pathlib import Path

import alluvial

# Who works in which team, two years running.
teams_2020 = {"Ann": 1, "Bo": 1, "Cy": 1, "Di": 1, "Ed": 2, "Flo": 2, "Gus": 2, "Hal": 3, "Ivy": 3}
teams_2021 = {"Ann": 1, "Bo": 1, "Cy": 1, "Di": 2, "Ed": 2, "Flo": 2, "Gus": 2, "Hal": 2, "Ivy": 3}

ax = alluvial.plot([teams_2020, teams_2021], names=["2020", "2021"])
ax.figure.savefig(Path(__file__).resolve().parents[1] / "docs" / "img" / "quickstart.png", dpi=150)
