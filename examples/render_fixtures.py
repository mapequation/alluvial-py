"""Render TS fixture geometries to examples/output/*.png (no layout engine needed).

Usage: ``python examples/render_fixtures.py [fixture-name ...]`` from the repository root.
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from conftest import load_fixture
from helpers_geometry import geometry_from_fixture

import alluvial

DEFAULT = ["science-stree__nameColored", "planted-ftree__colored", "states-tree__default"]

out = ROOT / "examples" / "output"
out.mkdir(parents=True, exist_ok=True)
for name in sys.argv[1:] or DEFAULT:
    ax = alluvial.draw(geometry_from_fixture(load_fixture(name)))
    ax.figure.savefig(out / f"{name}.png", dpi=150)
    plt.close(ax.figure)
    print(out / f"{name}.png")
