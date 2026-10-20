# alluvial

Alluvial diagrams of [Infomap](https://www.mapequation.org/infomap/) partitions for matplotlib, for scientific
papers. The layout is a faithful port of the engine behind the
[mapequation.org alluvial web app](https://www.mapequation.org/alluvial/) (`@mapequation/alluvial-diagram`
at TS `master` `60fa1bf`, web app 1.16), so module order, sizes, margins, streamlines and colours match the web app.

**Documentation:** <https://mapequation.github.io/alluvial-py>

> **Status: v0.6.0.** The layout reproduces every reference scenario generated from the TypeScript engine bit for
> bit, and a differential fuzzer checks it against the TS store. 0.6 adds c3 2's tones, offsets, the C3 Oklch
> scheme and colouring by module hierarchy, saved with the diagram. 0.5 fixed engine problems found in a joint review
> in both engines (tree paths, NaN flows, colour operations, fast `module_order`/`module_level`), replaced the
> saved-diagram format with "alluvial network files" that the web app and `alluvial` both write and read, and needs
> Python >= 3.11. See [`CHANGELOG.md`](CHANGELOG.md).

## Capabilities

- **Inputs:** Infomap's `.tree`, `.ftree`, `.stree` and `.clu` files (also the `*_states.*` versions), Infomap JSON
  (a `-o json` file or its dict), `infomap.Infomap` objects and their `Result` (state, memory and multilayer
  networks, with `split_layers` for one network per layer), a `.zip` or directory of network files (the web app's
  upload), and `alluvial.NetworkFile`s from `alluvial.read`.
- **Layout:** the web app's layout options (`height`, `module_width`, `streamline_fraction`, `streamline_threshold`,
  `flow_threshold`, `margin_exponent`, `zero_margins`, `vertical_align`, `module_size`, `sort_modules_by`),
  sub-modules (`module_level`, `expand`), custom `module_names` and `module_order`, and bipartite networks
  (`show_bipartite_nodes`).
- **Colours:** matching modules by similarity, by module id, by node, by layer, by physical node or by the module
  hierarchy; the web app's 65 colour schemes (with c3's tone and offset) or your own colours; highlight groups of nodes (a mapping or a function) with a legend.
- **Drawing:** `plot`/`draw` on any matplotlib axes, with fonts from `rcParams`, labels fitted at draw time,
  hierarchy shadows or outlines, palettes and colormaps, gradient streamlines, rasterizing, and every artist
  available for restyling (`get_artists`); vector PDF and SVG output.
- **Geometry:** `layout` returns frozen dataclasses (no matplotlib needed) with `to_dict()` for other renderers.
- **Save and load:** `save_diagram` writes the web app's "Download diagram" files (a zip or loose Infomap-JSON
  files), which the [web app](https://www.mapequation.org/alluvial/) opens for hand editing and `read`/`layout`
  load back with options, colours, order and names restored.

[`docs/capabilities.ipynb`](docs/capabilities.ipynb) is a tested tour of all of these: every step asserts what it
shows, and the test suite runs it.

## Install

```sh
pip install "alluvial[infomap]"
```

Requires Python >= 3.11 and matplotlib >= 3.7. `infomap` is optional and only needed to pass `infomap.Infomap`
objects (or their `Result`) directly; that needs infomap >= 2.14. Files written by any infomap version (`.tree`,
`.ftree`, `.clu`, `*_states.*`, `.json`) read without it.

## Usage

```python
import random

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
ax.figure.savefig("alluvial.png", dpi=150)
```

![Alluvial diagram of two Infomap partitions](https://raw.githubusercontent.com/mapequation/alluvial-py/main/docs/img/quickstart.png)

`examples/quickstart.py` makes the figure above. Networks go from left to right, and each one can be:

- a path to an Infomap output file (`.tree`, `.ftree`, `.stree`, `.clu` or `-o json` `.json`; the format comes from
  the suffix),
- an `infomap.Infomap` that has run (state and memory networks give state nodes, labelled by physical names),
- an Infomap JSON dict (`json.load` of a `-o json` file), or
- an `alluvial.NetworkFile` from `alluvial.read(...)`.

[`docs/tutorial.ipynb`](docs/tutorial.ipynb) walks through a complete analysis: seeded Infomap runs on a small
temporal network, the colourings, sub-modules, highlight groups with a legend, multilayer (state) networks, reading
Infomap files, a two-panel PDF figure and restyling single artists.
[`docs/capabilities.ipynb`](docs/capabilities.ipynb) covers every feature, each with checks.

The snippets below use the datasets bundled in `tests/data` of a source checkout; run them from its root.

### Figures for papers

Pass your own axes and the diagram fills it. Shapes scale with the axes, while every font size, gap and margin is in
points, so text prints at exactly the size you ask for. Labels and limits are fitted again at each draw, which keeps
`layout="constrained"`, `bbox_inches="tight"` and later resizing working. Labels never leave the axes. Long names are
truncated with an ellipsis, and where the labels of neighbouring modules would collide, the smaller module's label
loses lines or is hidden.

```python
import matplotlib.pyplot as plt

import alluvial

science = [f"tests/data/science{year}_2y.stree" for year in (2001, 2003, 2005, 2007)]
planted = [f"tests/data/planted_t{i}.ftree" for i in range(3)]

with plt.rc_context({"font.family": "serif", "font.size": 8, "pdf.fonttype": 42}):  # match the paper
    fig, (a, b) = plt.subplots(1, 2, figsize=(7, 2.6), width_ratios=[1.4, 1], layout="constrained")
    alluvial.plot(science, ax=a, names=[2001, 2003, 2005, 2007], max_label_lines=3)
    alluvial.plot(planted, ax=b, names=["$t_0$", "$t_1$", "$t_2$"], colors="module_id", palette="tab10")
    a.set_title("(a)", loc="left")
    fig.savefig("figure.pdf")
```

![A two-panel double-column figure](https://raw.githubusercontent.com/mapequation/alluvial-py/main/docs/img/paper_figure.png)

`examples/paper_figure.py` makes the figure above. The PDF stays vector: a two-colour streamline is a 256 × 1 gradient strip
clipped to its outline (`gradient=False` makes them solid). For very large diagrams, `rasterized=True` rasterizes the
shapes and keeps the text as vector.

### Sub-modules

Infomap finds hierarchies of modules. `module_level=2` shows the sub-modules of every visible module that has them
(one value, or one per network), exactly as clicking modules in the web app does. `expand=[(network, module_id), ...]`
expands single modules first. Gray boxes offset behind the sub-modules mark their parent module, like the web app's
hierarchy shadows; `hierarchy="outline"` draws dotted boxes around them instead, and `hierarchy=False` nothing.

```python
import alluvial

networks = [f"tests/data/multilevel_t{i}.tree" for i in range(3)]
ax = alluvial.plot(networks, module_level=2)
geom = alluvial.layout(networks, expand=[(1, "1"), (1, "1:1")])  # network index (or id), module path
```

![Top modules and module level 2](https://raw.githubusercontent.com/mapequation/alluvial-py/main/docs/img/hierarchy.png)

`examples/hierarchy.py` makes the figure above. Each `ModuleGeometry` has its `level`, and
`NetworkGeometry.outlines` holds the parent-module boxes.

### Highlight groups

`highlight` colours chosen nodes wherever they go and leaves everything else gray. Pass `{label: node identifiers}`
or a function of an `alluvial.NodeInfo` that returns a label or `None`. `legend=True` (or `alluvial.legend(ax)`) adds
a legend above the diagram, and the label lines take the colour of their node.

```python
import matplotlib.pyplot as plt

import alluvial

science = [f"tests/data/science{year}_2y.stree" for year in (2001, 2003, 2005, 2007)]
fields = {
    "Biology": ["J BIOL CHEM", "CELL", "EMBO J", "GENE DEV", "MOL CELL BIOL", "P NATL ACAD SCI USA"],
    "Physics": ["PHYS REV LETT", "PHYS REV B", "ASTROPHYS J", "APPL PHYS LETT", "J CHEM PHYS"],
}
fig, ax = plt.subplots(figsize=(3.4, 2.8), layout="constrained")
alluvial.plot(
    science, ax=ax, identifier="name", highlight=fields, legend=True, names=[2001, 2003, 2005, 2007]
)

# A function of an alluvial.NodeInfo works too; it returns a label or None:
geom = alluvial.layout(
    science, identifier="name", highlight=lambda node: "J ..." if node.name.startswith("J ") else None
)
```

![Highlighted journals with a legend](https://raw.githubusercontent.com/mapequation/alluvial-py/main/docs/img/highlight.png)

`examples/highlight.py` makes the figure above. Identifiers are matched like the networks' nodes (`identifier=`),
and numbers are allowed (`{"a": [1, 2, 3]}`). `highlight_colors` sets the colours (a list, or `{label: colour}`).
`highlight` replaces `colors`. The colouring is the web app's own "colour by metadata" operation, including one quirk:
in a network without hidden modules, the last module can miss its colour; `layout` then warns.

### Module names and order

`module_names` labels modules with names of your choice instead of their largest nodes, and `module_order` stacks
a network's modules in a given order. Both are web-app operations (the module name field and "move up/down"), so
the web app can show the same diagram.

```python
import alluvial

science = [f"tests/data/science{year}_2y.stree" for year in (2001, 2003, 2005, 2007)]
geom = alluvial.layout(
    science,
    identifier="name",
    module_names={(0, "1"): "Life sciences", (0, "2"): "Physics", (3, "1"): "Life sciences"},
    module_order={0: ["2", ...], 3: ["2", "4", "3", "5", "1"]},  # bottom to top
)
# A function of an alluvial.ModuleInfo names every module; it returns a name or None:
geom = alluvial.layout(
    science,
    identifier="name",
    module_names=lambda m: "Physics" if "PHYS REV LETT" in m.node_names[:5] else None,
)
```

![Four years of a citation network, modules named by field in a fixed order](https://raw.githubusercontent.com/mapequation/alluvial-py/main/docs/img/names_order.png)

`examples/names_order.py` makes the figure above.

- `module_names` takes `{(network, module_id): name}` (network index, id, or a name given with `names=` as a
  string; module ids as shown, e.g. `"1:2"` after `module_level=2`) or a function. As in the web app, names are
  drawn on the first and last network (`ModuleGeometry.name` holds them for every network).
- `module_order` takes `{network: [module_id, ...]}`, bottom to top. The unlisted visible modules keep their
  relative order above the listed ones; `...` stands for them, so `["2", ...]` puts module 2 at the bottom,
  `[..., "2"]` at the top. Hidden modules (below `flow_threshold`) cannot be placed. The order is applied after
  `colors`/`highlight`, so `sort_modules_by` sets the starting order.
- Unknown networks or modules, a module listed twice and hidden modules raise a `ValueError` that names them.

### Multilayer networks

`split_layers=True` draws a multilayer partition as one network per layer, matching nodes by their physical id, as
the web app does when it expands a multilayer file. Pass one flag per network to split only some.

```python
import alluvial

ax = alluvial.plot(["tests/data/mlayer_states.tree"], split_layers=True)
layers = alluvial.read("tests/data/mlayer_states.tree", split_layers=True)  # one NetworkFile per layer
```

![A four-layer partition, one network per layer](https://raw.githubusercontent.com/mapequation/alluvial-py/main/docs/img/multilayer.png)

`examples/multilayer.py` makes the figure above from an Infomap run on a multilayer network. `colors="layer"` and
`colors="physical_id"` colour multilayer and state networks by layer and by physical node.

### Colours

`colors` chooses what gets a colour (`"similarity"`, `"module_id"`, `"nodes"`, `"layer"`, `"physical_id"`,
`"hierarchy"` or None) and `scheme` the colours: one of the web app's 65 schemes by name (`alluvial.SCHEMES`) or a
list of colours. The C3 schemes (`"C3 Sinebow"`, the default, `"C3 Oklch"`, `"C3 Turbo"`, `"C3 Rainbow"`,
`"C3 Viridis"`) are computed by `c3-colors`, the Python port of the web app's c3, and take a `tone` and an `offset`.

```python
import alluvial

networks = [f"tests/data/multilevel_t{i}.tree" for i in range(3)]
geom = alluvial.layout(networks, scheme="C3 Oklch", tone="pastel", offset=120)
geom = alluvial.layout(networks, colors="hierarchy", module_level=2, scheme="Viridis", tone="deep")
colors = alluvial.palette.scheme_colors("C3 Sinebow", "soft", 90)  # the 512 colours of a scheme
```

- `tone` is one of `alluvial.palette.TONES` (`"vivid"`, `"bright"`, `"strong"`, the default, `"deep"`, `"dark"`,
  `"soft"`, `"pastel"`, `"muted"`). `offset` turns the hue source by that many degrees (None: the scheme's default,
  `alluvial.palette.default_scheme_offset`, 245 for `"C3 Oklch"` and 0 for the others). The other schemes are fixed
  lists, which tone and offset leave unchanged.
- `colors="hierarchy"` colours the modules by their place in the module hierarchy (c3's `hierarchy()`): sub-modules
  get colours close to their parent's, and the same module path gets the same colour in every network. The C3 schemes
  and the interpolated schemes (`"Viridis"`, `"Spectral"`, ...; `alluvial.palette.scheme_is_hue_source`) are its hue
  source, with the tone and offset; any other scheme, a colour list included, gives its seed colours and ignores the
  tone.
- `save_diagram` stores the scheme, tone and offset, and `layout` of the saved files restores them, as the web app
  does. A `tone` or `offset` you pass wins, and passing another `scheme` drops the saved offset.
- Known difference: c3-colors 2.0.1 colours a module with many sub-modules (about 40 or more) slightly differently
  from the web app's c3 2.0.1 with `colors="hierarchy"` (a few sibling colours swap). It waits for a c3-colors
  release; the reference fixtures and the differential fuzzer find no other colour difference.

### The web app: save and load

`save_diagram` lays out the networks like `layout` and saves the result for the
[web app](https://www.mapequation.org/alluvial), where it can be fine-tuned by hand. It takes the networks and the
same keywords as `layout`, not an `AlluvialGeometry`: the geometry holds only shapes, while the saved file needs the
engine's networks (node paths, identifiers, expansion levels). The layout is deterministic, so the same arguments
give the same diagram.

```python
import alluvial

networks = [f"tests/data/multilevel_t{i}.tree" for i in range(3)]
# The web app's "Download diagram" format (drop the zip on its "Load networks" dialog):
alluvial.save_diagram(networks, "diagram.zip", module_level=2, scheme="Paired")
files = alluvial.read("diagram.zip")  # one NetworkFile per saved network, in saved order
geom = alluvial.layout(files)  # the same diagram: colours, levels, options, order and names
```

- `save_diagram` writes "alluvial network files" (formatVersion 1), the format of the web app's "Download diagram":
  one Infomap-JSON file per network with the palette, each node's colour and module level, and an `alluvial` block
  with the options, the colour scheme with its c3 tone and offset, the module names and the custom module order. It writes a zip by default
  (`loose=True` writes the files to a directory). `alluvial.read` of the zip, of the directory or of a list of the
  files gives one `NetworkFile` per file in saved order, and `layout` restores the diagram from them (keywords you
  pass win over the stored values; `restore_state=False` ignores the block). The files are also plain Infomap JSON.
- The 2019 saved-diagram format (one JSON file with `networks`, written by the web app before 2022) is no longer
  read: `alluvial.read` raises a `ValueError`. alluvial 0.4 still reads it.
- JSON input with a top-level `colors` list (or `colors: true` with per-node `color`) is coloured as in the web app,
  and `layout` then keeps those colours unless `colors=` is given. Schemes, tones and offsets: see "Colours" above.

### API

```python
import alluvial

networks = [f"tests/data/planted_t{i}.ftree" for i in range(3)]
geom = alluvial.layout(
    networks,
    names=None,
    ids=None,
    identifier="id",
    split_layers=False,
    colors="similarity",  # "module_id", "nodes", "layer", "physical_id", "hierarchy" or None
    module_level=1,
    expand=None,
    highlight=None,
    highlight_colors=None,
    scheme=None,  # a web-app scheme name, e.g. "Paired", or a list of colours; default "C3 Sinebow"
    tone=None,  # a c3 tone of the C3 schemes and colors="hierarchy", e.g. "pastel"; default "strong"
    offset=None,  # degrees around the c3 hue source of the first colour; default c3's
    restore_state=True,  # restore what a saved diagram stores (options, scheme, tone, offset, orders, names)
    module_order=None,  # {network: [module_id, ...]}, bottom to top
    module_names=None,  # {(network, module_id): name} or a function of an alluvial.ModuleInfo
    height=600,
    module_width=80,
    streamline_fraction=2,
    streamline_threshold=1,
    flow_threshold=5e-3,
    margin_exponent=4,
    zero_margins=False,
    vertical_align="bottom",  # or "justify"
    module_size="flow",
    sort_modules_by="flow",
)
ax = alluvial.draw(
    geom,
    ax=None,
    palette=None,
    default_color=None,
    module_labels=True,
    network_labels=True,
    fontsize=None,
    network_fontsize=None,  # points or "small"/"medium"/...
    max_label_lines=None,
    max_label_width="auto",
    avoid_label_overlap=True,
    label_pad=3,
    streamline_alpha=0.8,
    gradient=True,
    edgecolor="face",
    linewidth=0.3,
    rasterized=False,
    hierarchy=True,  # "shadow", "outline" or False
    legend=False,
    label_colors="auto",
    module_kw=None,
    streamline_kw=None,
    hierarchy_kw=None,
    text_kw=None,
    label_kw=None,
    network_label_kw=None,
)
art = alluvial.get_artists(ax)  # .modules, .streamlines, .outlines, .module_labels, .network_labels, .legend
```

- `plot(networks, ax=None, **kwargs)` passes each keyword to `draw` or `layout`, whichever takes it. An unknown keyword
  raises `TypeError`.
- `colors`: `"similarity"` (default, the web app's "paint all by similarity"), `"module_id"`, `"nodes"` (colour
  nodes by their module in the first network), `"layer"`, `"physical_id"` (multilayer and state networks), or
  `None` (the input colours: gray, except for JSON with `colors`, where `None` is the default).
- `alluvial.save_diagram(networks, path, *, loose=False, **layout_kwargs)` saves the diagram for the web app as a zip
  (or loose files; see above).
- `identifier`: match nodes across networks by `"id"` (state id if present, else node id) or by `"name"`.
- Network ids default to the file stem (or `net0`, `net1`, ... for objects). Colliding ids are renamed `out`,
  `out_2`, ...; `ids=[...]` sets them.
- The steps run in the web app's store in a fixed order: build, `expand`, `module_level`, then `colors` or
  `highlight`. Each step is the store's own operation, so the geometry is the web app's to the last bit.
- `palette`: a list of colours, or a matplotlib colormap or its name. It defaults to the web app's palette. A
  qualitative map (`"tab10"`) is used as is, and a continuous one is sampled. For grayscale-safe prints, use a map
  whose lightness changes monotonically, such as `"cividis"` or `"viridis"`. Unhighlighted modules take
  `default_color`, and insignificant groups are drawn brighter.
- Font sizes follow `rcParams["font.size"]` by default: module labels are `"small"` and network names `"medium"`.
  `text_kw` styles all text, while `label_kw` and `network_label_kw` style one kind only. `module_kw`,
  `streamline_kw` and `hierarchy_kw` go to the shapes. Module labels are drawn literally, with no mathtext. Network
  names may use `$...$`.
- `label_colors="auto"` colours label lines by their node's highlight colour only for `highlight` diagrams; `True`
  always does (as the web app), `False` never.
- `max_label_width="auto"` caps each label column at a quarter of the axes width. Pass a number in points, or `None`
  to disable truncation. `avoid_label_overlap=False` and `linewidth=0` reproduce the web app exactly.
- `alluvial.legend(ax, other=None, **kwargs)` adds (or replaces) the highlight legend; `other="other"` adds a gray
  entry, and `loc=`/`bbox_to_anchor=` place it like any matplotlib legend.
- Every artist has a `gid`, such as `module:<network>:<module>:<group>`, `streamline:<id>` or
  `outline:<network>:<path>`, which SVG output keeps as the element id.
- Without `ax=`, `draw` makes its own figure at one layout px per point, sized to fit the labels.
- `draw` and `plot` never call `plt.show()` and never change global state. They return the axes.
- Common mistakes get a clear error or warning: an Infomap object that has not run, a missing file, passing networks
  to `draw` (use `plot`), state networks next to ordinary networks under `identifier="id"` (state ids would be
  compared with node ids), `highlight` identifiers that match no node, a `module_level` deeper than a
  network's module tree, and networks whose node flows are all zero (an empty diagram). Warnings point at your own
  line, also through `plot`.

See `docs/dev/design.md` for the binding design decisions.

## Development

```sh
uv sync --extra dev   # .venv with the package (editable) and the dev tools, from uv.lock; any Python >= 3.11
.venv/bin/pytest -q
```

The dev extra installs `pytest`, `infomap` and `ruff` (`.venv/bin/ruff check src tests`). infomap 2.15.1 installs
from a cp314 wheel, so no `--system-site-packages` fallback is needed.

Layout:

- `src/alluvial/`: `layout.py` (public `layout`, `LayoutOptions`, `NodeInfo`), `geometry.py` (frozen geometry
  contract), `io/` (readers, `NetworkFile`, `split_layers`), `engine/` (port of the TS engine; internal), `mpl.py`
  (`draw`, `plot`, `legend`, `get_artists`),
  `palette.py`, `tree_path.py`, `_jscompat.py` (JS number formatting and arithmetic semantics).
- `layout`, `geometry`, `io` and `engine` never import matplotlib (enforced by `tests/test_no_mpl_import.py`).
- `docs/dev/port-notes/`: detailed porting specs for each part of the TS engine.

### Test fixtures

`tests/fixtures/*.json` (205 scenarios, plus 77 in `v3/` and 15 in `v4/` with save/load round trips) are the
reference geometry, produced by running the real TypeScript engine headlessly in Node on the datasets in
`tests/data/`. Fixtures with a `features` list exercise v2 features. To regenerate or verify them (needs Node >= 22
and a checkout of the web app with `node_modules`; set `ALLUVIAL_TS_ROOT` if it is not at `../web/alluvial`):

```sh
node tools/ts-fixtures/generate.mjs           # rewrite tests/fixtures
node tools/ts-fixtures/generate.mjs --check   # regenerate to a temp dir and byte-compare
```

See `tools/ts-fixtures/README.md` for the fixture format and the scenario list.

The port follows the TS engine at the commit in `tests/fixtures/provenance.txt` (`ts_repo_head`, now `60fa1bf`). To
sync with a newer TS `master`, list the engine commits to port, port them, then regenerate and review:

```sh
git -C ../web/alluvial log <ts_repo_head>..master -- packages/alluvial-diagram/src
ALLUVIAL_TS_ROOT=../web/alluvial node tools/ts-fixtures/generate.mjs --check   # exit 0: nothing changed
ALLUVIAL_TS_ROOT=../web/alluvial node tools/ts-fixtures/generate.mjs           # regenerate, then review the diff
```

## License

MIT. The layout algorithm is ported from the alluvial web app by Anton Holmgren (MIT); see `LICENSE`.
