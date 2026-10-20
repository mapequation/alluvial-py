"""A two-panel, double-column (7 in) figure for a paper, saved as PDF and PNG.

Run with ``python examples/paper_figure.py``; writes ``examples/output/paper_figure.pdf`` and ``docs/img/paper_figure.png``.
Uses the bundled test data, so it needs no Infomap run.
"""

from pathlib import Path

import matplotlib.pyplot as plt

import alluvial

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data"
science = [DATA / f"science{year}_2y.stree" for year in (2001, 2003, 2005, 2007)]
planted = [DATA / f"planted_t{i}.ftree" for i in range(3)]

# Match the paper: its font family and size; every alluvial text size is in points.
with plt.rc_context({"font.family": "serif", "font.size": 8, "pdf.fonttype": 42}):
    fig, (a, b) = plt.subplots(1, 2, figsize=(7, 2.6), width_ratios=[1.4, 1], layout="constrained")
    alluvial.plot(science, ax=a, names=["2001", "2003", "2005", "2007"], max_label_lines=3)
    alluvial.plot(planted, ax=b, names=["$t_0$", "$t_1$", "$t_2$"], colors="module_id", palette="tab10")
    a.set_title("(a) Citation flow between journals", loc="left")
    b.set_title("(b) Planted partition", loc="left")

    out = ROOT / "examples" / "output"
    out.mkdir(exist_ok=True)
    fig.savefig(out / "paper_figure.pdf")
    fig.savefig(ROOT / "docs" / "img" / "paper_figure.png", dpi=200)
