"""Named modules in a custom order: four years of a citation network, each module labelled by its field.

Run with ``python examples/names_order.py``; writes ``docs/img/names_order.png``. Uses the bundled test data.

``module_names`` replaces a module's node-name label by a name of your choice (here a function of the module's
largest journals); ``module_order`` stacks the modules bottom to top in the given order. Both are web-app
operations (the module name field and "move up/down"), so ``save_diagram`` writes a diagram that shows the same.
"""

from pathlib import Path

import matplotlib.pyplot as plt

import alluvial

ROOT = Path(__file__).resolve().parents[1]
years = [2001, 2003, 2005, 2007]
networks = [ROOT / "tests" / "data" / f"science{year}_2y.stree" for year in years]

# A field per landmark journal; a module is named after the first landmark among its ten largest journals.
FIELDS = {
    "J BIOL CHEM": "Life sciences",
    "PHYS REV LETT": "Physics",
    "J GEOPHYS RES": "Earth sciences",
    "IEEE T INFORM THEORY": "Engineering",
    "AM ECON REV": "Economics",
}


def field(module: alluvial.ModuleInfo) -> str | None:
    largest = module.node_names[:10]
    return next((name for journal, name in FIELDS.items() if journal in largest), None)


# Bottom to top, the same in every year: physics at the bottom, the life sciences on top.
order = ["2", "4", "3", "5", "1"]

with plt.rc_context({"font.size": 8}):
    fig, ax = plt.subplots(figsize=(3.4, 2.6), layout="constrained")
    # identifier="name": these state networks match journals by name across the years.
    alluvial.plot(
        networks,
        ax=ax,
        identifier="name",
        names=years,
        module_names=field,
        module_order={i: order for i in range(len(years))},
    )
    fig.savefig(ROOT / "docs" / "img" / "names_order.png", dpi=300)
