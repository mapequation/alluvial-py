"""The hero figure: neuroscience in the citation network 2001-2007, after the alluvial diagram on Wikipedia.

Run with ``python examples/hero.py``; writes ``docs/img/hero.png`` and ``docs/img/hero.svg``. Uses the bundled
test data.

A take on Rosvall & Bergstrom's figure of neuroscience emerging in the citation network (PLoS ONE 5, e8694,
2010), drawn from the journal citation networks bundled with the tests. It keeps the life-science fields of that
figure, builds one ``alluvial.partition`` per year from the journals' sub-modules and flows, names the modules by
field, stacks them in a fixed order and highlights the brain sciences of 2001 (everything else stays gray).
"""

import re
from pathlib import Path

import matplotlib.pyplot as plt

import alluvial

ROOT = Path(__file__).resolve().parents[1]
years = [2001, 2003, 2005, 2007]

# A field per landmark journal, listed bottom to top: a sub-module of the life sciences is that field
# when it contains the landmark journal.
FIELDS = {
    "J BIOL CHEM": "Molecular & cell biology",
    "NEW ENGL J MED": "Medicine",
    "J NEUROSCI": "Neuroscience",
    "CANCER RES": "Oncology",
    "AM J PSYCHIAT": "Psychiatry",
    "NEUROLOGY": "Neurology",
    "J INFECT DIS": "Infectious diseases",
    "J PERS SOC PSYCHOL": "Psychology",
    "KIDNEY INT": "Nephrology",
    "J UROLOGY": "Urology",
}
fields = list(FIELDS.values())


def field_partition(year: int) -> tuple[dict[str, int], dict[str, float]]:
    """``{journal: field number}`` and ``{journal: flow}`` of one year, for the journals of the fields above."""
    network = alluvial.read(ROOT / "tests" / "data" / f"science{year}_2y.stree", identifier="name")
    # The life sciences are top module 1; its sub-modules are the fields.
    sub_module = {node.name: tuple(re.split("[:;]", node.path)[:2]) for node in network.nodes}
    field_of = {sub_module[journal]: i for i, journal in enumerate(FIELDS, start=1)}
    modules = {name: field_of[sub] for name, sub in sub_module.items() if sub in field_of}
    flows = {node.name: node.flow for node in network.nodes if node.name in modules}
    return modules, flows


partitions = [field_partition(year) for year in years]
networks = [
    alluvial.partition(modules, flows, name=str(year)) for year, (modules, flows) in zip(years, partitions)
]

# The brain sciences in 2001, followed across the years; every other journal stays gray.
first = partitions[0][0]
brain = ["Neuroscience", "Neurology", "Psychology", "Psychiatry"]
groups = {
    field: [journal for journal, module in first.items() if fields[module - 1] == field] for field in brain
}

ids = [str(i) for i in range(1, len(fields) + 1)]
with plt.rc_context({"font.size": 7, "svg.hashsalt": "hero"}):  # svg.hashsalt: reproducible SVG ids
    fig, ax = plt.subplots(figsize=(7, 2.8), layout="constrained")
    alluvial.plot(
        networks,
        ax=ax,
        highlight=groups,
        highlight_colors=["#e31a1c", "#2c7bb6", "#66bd63", "#ff7f00"],
        module_names={(i, id_): field for i in range(len(years)) for id_, field in zip(ids, fields)},
        module_order={i: ids for i in range(len(years))},
        max_label_lines=2,
    )
    fig.savefig(ROOT / "docs" / "img" / "hero.png", dpi=200)
    fig.savefig(ROOT / "docs" / "img" / "hero.svg", metadata={"Date": None})
