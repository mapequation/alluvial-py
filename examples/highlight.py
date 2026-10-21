"""Highlight groups: journals of two fields in a citation network, with a legend, at single-column width (3.4 in).

Run with ``python examples/highlight.py``; writes ``docs/img/highlight.png``. Uses the bundled test data.

``highlight`` colors the chosen nodes wherever they go (everything else stays gray), so their flow can be followed
across the networks. The label lines take the color of their node.
"""

from pathlib import Path

import matplotlib.pyplot as plt

import alluvial

ROOT = Path(__file__).resolve().parents[1]
years = [2001, 2003, 2005, 2007]
networks = [ROOT / "tests" / "data" / f"science{year}_2y.stree" for year in years]
fields = {
    "Biology": ["J BIOL CHEM", "CELL", "EMBO J", "GENE DEV", "MOL CELL BIOL", "P NATL ACAD SCI USA"],
    "Physics": ["PHYS REV LETT", "PHYS REV B", "ASTROPHYS J", "APPL PHYS LETT", "J CHEM PHYS"],
}

with plt.rc_context({"font.size": 8}):
    fig, ax = plt.subplots(figsize=(3.4, 2.8), layout="constrained")
    # identifier="name": these state networks match journals by name across the years.
    alluvial.plot(
        networks, ax=ax, identifier="name", highlight=fields, legend=True, names=years, max_label_lines=3
    )
    fig.savefig(ROOT / "docs" / "img" / "highlight.png", dpi=300)
