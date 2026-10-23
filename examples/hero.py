"""The hero figure: neuroscience emerging from neurology, psychology and molecular biology, 2001-2007.

Run with ``python examples/hero.py``; writes ``docs/img/hero.png`` and ``docs/img/hero.svg``. Needs infomap
(``pip install infomap``).

A take on Rosvall & Bergstrom's alluvial diagram of neuroscience emerging in the citation network (PLoS ONE 5,
e8694, 2010), with synthetic data that tells its story. Four yearly citation networks between journals have planted
fields; by 2005 Neurology, most of Psychology and a part of Molecular & cell biology have merged into Neuroscience,
and in 2007 Urology splits off Nephrology. ``infomap.run`` finds the fields of each year, the modules are named by
field and stacked in a fixed order, and the merging journals are highlighted (everything else stays gray).
"""

import random
from collections import Counter, defaultdict
from pathlib import Path

import infomap
import matplotlib.pyplot as plt

import alluvial

ROOT = Path(__file__).resolve().parents[1]
years = [2001, 2003, 2005, 2007]
rng = random.Random(2010)

# The journals of each field in 2001; journals are numbered 0, 1, 2, ... field by field.
SIZES = {
    "Molecular & cell biology": 240,
    "Medicine": 90,
    "Oncology": 32,
    "Infectious diseases": 20,
    "Psychiatry": 26,
    "Neurology": 26,
    "Psychology": 30,
    "Nephrology": 24,
}
# Bottom to top in the diagram.
ORDER = [
    "Molecular & cell biology",
    "Medicine",
    "Neuroscience",
    "Oncology",
    "Infectious diseases",
    "Psychiatry",
    "Neurology",
    "Psychology",
    "Nephrology",
    "Urology",
]

field_2001 = [field for field, size in SIZES.items() for _ in range(size)]
journals = defaultdict(list)
for journal, field in enumerate(field_2001):
    journals[field].append(journal)
molecular_part = set(journals["Molecular & cell biology"][-50:])  # the molecular neuroscience journals


def fields_in(year: int) -> dict[int, str]:
    """``{journal: field}`` of one year, with a few journals drifting to another field."""
    fields = dict(enumerate(field_2001))
    if year >= 2005:
        merging = journals["Neurology"] + journals["Psychology"][:18] + sorted(molecular_part)
        fields.update(dict.fromkeys(merging, "Neuroscience"))
    if year >= 2007:
        fields.update(dict.fromkeys(journals["Psychiatry"][:4], "Neuroscience"))
        fields.update(dict.fromkeys(journals["Nephrology"][-10:], "Urology"))
    names = sorted(set(fields.values()))
    for journal in rng.sample(sorted(fields), k=len(fields) // 60):
        fields[journal] = rng.choice([name for name in names if name != fields[journal]])
    return fields


def citations(fields: dict[int, str]) -> list[tuple[int, int]]:
    """Links of a planted-partition network: about 16 links within a journal's field and 1 to another."""
    members = defaultdict(list)
    for journal, field in fields.items():
        members[field].append(journal)
    links = set()
    for journal, field in fields.items():
        group = members[field]
        others = rng.sample(group, min(8, len(group)))
        if rng.random() < 0.5:
            others.append(rng.randrange(len(fields)))
        links.update((min(journal, other), max(journal, other)) for other in others if other != journal)
    return sorted(links)


planted = [fields_in(year) for year in years]
results = [infomap.run(citations(fields), seed=1, two_level=True, num_trials=5) for fields in planted]

# Name each module by the planted field of most of its journals.
field_of = {}  # {(network index, module id): field}
for i, (result, fields) in enumerate(zip(results, planted)):
    votes = defaultdict(Counter)
    for journal, module in result.modules().items():
        votes[str(module)][fields[journal]] += 1
    field_of.update({(i, module): count.most_common(1)[0][0] for module, count in votes.items()})
for i, year in enumerate(years):
    found = sorted(field for (j, _), field in field_of.items() if j == i)
    assert found == sorted(set(planted[i].values())), (year, found)  # one module per field


def story(node: alluvial.NodeInfo) -> str | None:
    """The highlight group of a journal in one year: the merging fields before 2005, Neuroscience after."""
    field = field_of[node.network_index, node.path.split(":")[0]]
    if field == "Neuroscience":
        return field
    if years[node.network_index] < 2005:
        if field in ("Neurology", "Psychology"):
            return field
        if field == "Molecular & cell biology" and node.id in molecular_part:
            return "Molecular neuroscience"
    return None


colors = {
    "Neurology": "#2c7bb6",
    "Psychology": "#66bd63",
    "Molecular neuroscience": "#ff7f00",
    "Neuroscience": "#e31a1c",
}
order = defaultdict(list)  # {network index: module ids, bottom to top}
for i, module in sorted(field_of, key=lambda key: ORDER.index(field_of[key])):
    order[i].append(module)

with plt.rc_context({"font.size": 7, "svg.hashsalt": "hero"}):  # svg.hashsalt: reproducible SVG ids
    fig, ax = plt.subplots(figsize=(7, 2.8), layout="constrained")
    alluvial.plot(
        results,
        ax=ax,
        names=years,
        highlight=story,
        highlight_colors=colors,
        module_names=field_of,
        module_order=order,
        max_label_lines=2,
    )
    fig.savefig(ROOT / "docs" / "img" / "hero.png", dpi=200)
    fig.savefig(ROOT / "docs" / "img" / "hero.svg", metadata={"Date": None})
