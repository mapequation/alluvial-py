"""Sub-modules: the same three multilevel partitions at module level 1 and 2, in a double-column (7 in) figure.

Run with ``python examples/hierarchy.py``; writes ``docs/img/hierarchy.png``. Uses the bundled test data.

``module_level=2`` expands every visible module that has sub-modules, as clicking modules in the web app does. The gray
boxes offset behind the sub-modules mark their parent module (the web app's "shadow" hierarchy); ``hierarchy="outline"``
draws dotted boxes around them instead.
"""

from pathlib import Path

import matplotlib.pyplot as plt

import alluvial

ROOT = Path(__file__).resolve().parents[1]
networks = [ROOT / "tests" / "data" / f"multilevel_t{i}.tree" for i in range(3)]
names = ["$t_0$", "$t_1$", "$t_2$"]

with plt.rc_context({"font.size": 8}):
    fig, (a, b) = plt.subplots(1, 2, figsize=(7, 3), layout="constrained")
    alluvial.plot(networks, ax=a, names=names)
    alluvial.plot(networks, ax=b, names=names, module_level=2)
    a.set_title("(a) Top modules", loc="left")
    b.set_title("(b) module_level=2", loc="left")
    fig.savefig(ROOT / "docs" / "img" / "hierarchy.png", dpi=200)
