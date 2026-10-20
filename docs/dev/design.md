# alluvial (Python): v1 design

Status: decided on 2026-10-10 by the coordinating agent while the owner slept. The owner should review it. Anything marked
**[decision]** settles an open question from `docs/dev/port-notes/README.md`. v1 to v4 and the 0.5 fix round are
implemented; see "Status (0.5.0)" at the end for what is done and the decisions the owner still has to make. Later
sections and the 0.5 notes in them supersede earlier ones.

## Goal

The goal is to make matplotlib alluvial diagrams of Infomap partitions for scientific papers, with geometry identical to the
web app (`../web/alluvial`, `@mapequation/alluvial-diagram` 1.15.0, MIT).

**v1 scope.** v1 covers:
- top-level (two-level) modules
- flow-proportional streamlines
- consistent module colours across networks
- module ordering as in the web app
- state networks
- readers for `infomap.Infomap` objects and `.tree/.ftree/.stree/.clu` files
- a thin matplotlib renderer taking `ax=`

**Later versions.** v2 adds hierarchical sub-modules (expand/regroup, `module_level`) and a public highlight-groups API (user node sets).

## Architecture

```
input (paths | infomap.Infomap | NetworkFile)
   │  alluvial.io           pure Python: parsers + Infomap reader → NetworkFile (mirrors parsers/types.ts)
   ▼
alluvial.engine             faithful port of src/alluvial/*.ts: a mutable object tree, the colour ops, updateLayout
   │                        (no matplotlib; never imported by users directly)
   ▼
alluvial.geometry           frozen dataclasses: the ONLY contract between layout and rendering
   │  alluvial.layout()     public, pure: networks + options → AlluvialGeometry   (no matplotlib import)
   ▼
alluvial.mpl                draw(geometry, ax=None, …) and plot(networks, ax=None, …) = layout + draw
```

- **[decision] The engine is a faithful port, not a re-implementation.** It has one Python module per TS class, the same
  class names, and snake_case method names. It keeps the same iteration and mutation order (swap-remove, detach before
  create, colour-after-build). Every module docstring names the TS file it ports. The geometry's tie orders depend on the
  mutation sequence, so a clean-room rewrite would drift from the web app. That is the risk this package must avoid. The
  clean, Pythonic surface is `layout()`/`geometry`/`plot()`, not the engine.
- `alluvial.layout`, `alluvial.geometry`, `alluvial.io` and `alluvial.engine` must never import matplotlib. A test enforces this.
  infomap is imported lazily, only in the Infomap reader.

## Package layout **[decision]** (resolves port-notes README Q7)

```
pyproject.toml                 hatchling; name "alluvial"; requires-python >=3.11; deps: matplotlib>=3.7, numpy
                               extras: infomap = ["infomap>=2.14"], dev = ["pytest", "infomap", "ruff"]
src/alluvial/
  __init__.py                  re-exports: layout, plot, draw, read, LayoutOptions, AlluvialGeometry, NetworkFile, __version__
  _jscompat.py                 JS semantics: number→string (Number#toString), left-to-right float sum (NOT builtin sum —
                               3.12+ compensates), JS division/NaN rules, stable sort helpers, JS object key-order emulation
  tree_path.py                 port of utils/TreePath.ts
  palette.py                   the web app's schemes (data/color-schemes.json), c3 tone/offset (c3-colors),
                               d3 hsl().brighter(k) port, default (unhighlighted) colour
  _d3_interpolators.py         the d3 interpolators c3 takes as hue sources (data/d3-interpolators.json)
  io/
    __init__.py                read(source, *, name=None, identifier="id", states=None) -> NetworkFile
    types.py                   NetworkFile, Node (dataclasses mirroring parsers/types.ts)
    text.py                    port of @mapequation/infomap-parser for tree/ftree/stree/clu
    identifiers.py             set_identifiers, create_file, calc_statistics
    infomap_reader.py          infomap.Infomap -> NetworkFile (lazy `import infomap`)
  engine/
    depth.py side.py alluvial_node.py leaf_node.py streamline_node.py streamline_link.py branch.py
    highlight_group.py module.py network.py diagram.py tree.py   (utils/Tree.ts path-tree sort)
    store.py                   the minimal DiagramStore slice: set_networks (highlightColors reset, calcFlow, updateLayout),
                               colour ops (colorMatchingModulesInAllNetworks, colorModuleIdsInAllNetworks,
                               colorNodesInModulesInAllNetworks, colorModule, clearColors), and a replay(operations) used by tests
  geometry.py                  AlluvialGeometry, NetworkGeometry, ModuleGeometry, GroupGeometry, StreamlineGeometry, Label,
                               build_geometry(store/diagram, options) -> AlluvialGeometry, to_dict()
  layout.py                    LayoutOptions dataclass + layout(networks, *, names=None, identifier="id", colors="similarity",
                               **options) -> AlluvialGeometry
  mpl.py                       draw(...), plot(...)
tests/
  conftest.py                  fixture loader (json with -Infinity), numeric comparison helper, v1/v2 scenario split
  test_engine_fixtures.py      replays every v1 fixture through io+engine and compares everything (structure, orders, rects,
                               links, labels, highlight indices, highlightColors)
  test_io_*.py                 parser parity against fixture leaves/file stats; Infomap-object reader == written files
  test_geometry.py             build_geometry vs fixtures; to_dict round trip; no-matplotlib-import test
  test_mpl.py                  Agg smoke tests: ax=, subplots, savefig png/pdf/svg, artist counts, y orientation
tools/ts-fixtures/             (exists) node harness: `node tools/ts-fixtures/generate.mjs [--check]`
```

## Coordinates **[decision]**

The geometry uses the TS/SVG coordinates exactly: x points right, y points down, the units are layout px, and the diagram spans
`[0, width] × [0, height]`. That keeps it fixture-comparable. `mpl.draw` maps `y ↦ height − y`, so the axes keep their normal
orientation and the picture matches the web app, with the largest module at the bottom. `draw` turns the axis off by default,
sets the limits to include the labels, and does not force the aspect ratio.

## Geometry contract (`alluvial.geometry`, frozen dataclasses)

- `AlluvialGeometry`: `width`, `height`, `networks: tuple[NetworkGeometry]`, `streamlines: tuple[StreamlineGeometry]` (in draw
  order, i.e. `getLinks` order per network pair), `palette: tuple[str]` (the `highlightColors` in effect), `options`.
- `NetworkGeometry`: `id`, `name`, `index`, `x`, `y`, `width`, `height`, `flow`, `name_label: Label`, `modules`. The modules
  are the visible ones in layout order; invisible modules are omitted.
- `ModuleGeometry`: `id` (path string), `path: tuple[int]`, `network_index`, `flow`, `x`, `y`, `width`, `height`,
  `highlight_index`, `groups: tuple[GroupGeometry]`, `label: Label | None`, `largest_leaf_names: tuple[str]`.
- `GroupGeometry`: `highlight_index`, `insignificant`, `x`, `y`, `width`, `height`, `flow`. A module with no colouring has one
  group with `highlight_index = -1`.
- `StreamlineGeometry`: `id`, `left: (network_index, module_id, highlight_index)`, `right: (...)`, `x0, y0, h0, x1, y1, h1`,
  `avg_height`, `highlight_index`, `left_highlight_index`, `right_highlight_index`, plus
  `path() -> list[(code, (x, y))]`. The codes are MOVETO, CURVE4 and LINETO, as module constants that match matplotlib's
  numeric Path codes without importing matplotlib. The control points are the same as in the TS `path` string (cpx = (x0+x1)/2,
  1e-6 snapping). `svg_path()` returns the JS-formatted string, for parity tests.
- `Label`: `text`, `x`, `y`, `anchor` (`"start"|"end"|"middle"`).

## Public API (v1)

```python
geom = alluvial.layout(networks, *, names=None, identifier="id", colors="similarity",
                       height=600, module_width=80, streamline_fraction=2, streamline_threshold=1,
                       flow_threshold=5e-3, margin_exponent=4, zero_margins=False,
                       module_size="flow", sort_modules_by="flow")
ax = alluvial.draw(geom, ax=None, *, palette=None, default_color=None, module_labels=True, network_labels=True,
                   fontsize=8, max_label_names=..., streamline_alpha=..., edgecolor=..., linewidth=...)
ax = alluvial.plot(networks, ax=None, **layout_and_draw_kwargs)   # e.g. alluvial.plot([im_2020, im_2021])
nf = alluvial.read(source, *, name=None, identifier="id", states=None)
```

- `networks` items can be a path (str or PathLike; the format comes from the suffix), an `infomap.Infomap` that has already
  run, or a `NetworkFile`. `names` defaults to the file basename, or `"network {i}"` for objects. The network id is the file
  stem, or `net{i}`. Duplicate ids and ids that contain `--` raise ValueError.
- **[decision] Colours:** `colors="similarity"` (default) runs `colorMatchingModulesInAllNetworks`, `"module_id"` runs
  `colorModuleIdsInAllNetworks`, `"nodes"` runs `colorNodesInModulesInAllNetworks` (each node coloured by its module in the
  first network), and `None` leaves everything gray as when the web app loads a file. The ops are applied after the build,
  exactly as the store does it, and mirror the TS quirks for parity (no "clean" mode in v1). (port-notes Q1, Q2)
- **[decision]** Unhighlighted modules use the TS default colour. When a highlight index exceeds the palette, `draw` cycles the
  palette and emits a warning (TS would draw black). `palette=` accepts a list of colours or a matplotlib colormap name; a
  colormap is sampled to the needed number of colours.
- **[decision]** `streamline_threshold` lives in the layout options. It is in px, defaults to 1 and does not scale with
  `height`; it filters links exactly like `getLinks`. (Q4)
- **[decision]** `vertical_align` takes `"bottom"` (default) or `"justify"`; TS `"top"` (a no-op there; removed from TS in fix round WP11, E8) is rejected. `flow_threshold` must be in [0, 1), otherwise
  ValueError. `sort_modules_by` is one of `"flow"`, `"nodes"` or `"node_id"`, mapped to the TS keys. `margin_exponent` may be
  a float. (Q5)
- **[decision]** Labels follow TS: module labels sit only on the first network (left, anchor end) and the last network (right,
  anchor start). Network names go below each network. The text is the largest leaf names, aggregated to physical names for
  state networks. Fonts are matplotlib defaults and the font size is in points. (Q6)
- **[decision]** Duplicate identifiers inside a network: the readers emit a `UserWarning`, and the engine accepts them and runs
  the TS algorithm. Since fix round WP5 (E6) both engines link only the registered (last) duplicate across networks; the
  others stay dangling (no stealing, no `NULL--` ids). (Q3)
- **[decision]** Similarity uses `engine/_utils.js_log2`, a port of fdlibm `e_log2.c` (with the FMA that clang emits for
  arm64 node), because `math.log2` differed from V8 by 1 ulp on 1.6% of inputs and the differential fuzzer traced
  divergences to it. On x86-64 V8 (no FMA) about 1 in 300k inputs still differ. (Q8)

## State networks

The Infomap reader defaults to `states=None`, which means auto: it takes state nodes when the Infomap object is a state or
memory network, mirroring `write_tree(states=True)` / `.stree`. Identifiers follow `set_identifiers` (`"id"` gives
`stateId ?? id`, `"name"` gives the name). For state networks, labels aggregate to physical names (`aggregateStateNames`).

- Multilayer state ids are assigned by Infomap in input order, so matching multilayer networks across differently built
  runs with `identifier="id"` is unreliable (TS parity; documented, no warning).
- `identifier="name"` matches physical nodes by name (falling back to the physical id), with a duplicate-identifier
  warning.
- There is no `identifier="physical"`: TS only has a physical-id mode through multilayer expand
  (`"multilayer-expanded"`), which is v2.
- Reading Infomap objects needs infomap >= 2.14 (the `Result` API); older versions raise a `TypeError` naming the
  bound and the `write_tree` workaround. Files written by older versions read fine.

## Testing

- Every v1 fixture (all except `*__expand*` / regroup, which are v2) must pass the engine replay.
  - Floats compare to `abs ≤ 1e-9` (px), and the test also counts non-bitwise-identical values. The target is exact equality.
  - Orders (module order, group order, streamline-node order, link draw order) must match exactly.
  - Path strings compare numerically token by token.
- The parsers match the TS parse for every dataset. The Infomap reader on `make_datasets.build_infomap(stem)` equals reading
  the written files.
- The matplotlib tests run headless (Agg).
- Dev env: `uv venv --python 3.14` (conda py314 python) into `.venv`, `uv pip install -e ".[dev]"`, `.venv/bin/pytest`.

## v2 (after v1 is verified)

- `module_level` / `expand=` / `regroup=` (port `Module.expand`/`regroup`, `Network.tree` outlines; keep the TreePath quirks for
  parity, documented).
- `highlight=` node sets (a public highlight-groups API), with legends.
- Multilayer splitting (`multilayer-utils.ts`), JSON (saved web-app diagram) input, and a custom module order.

## Changes after review (renderer and API, 2026-10-10)

A review at paper sizes (3.4 in single-column and 7 in double-column, PDF) found that `draw(geom, ax)` was unusable in a
fixed-size axes. The labels kept their point size, the fixed-point limit fit diverged once the labels were wider than the
axes, and the diagram collapsed to a sliver. Label lines of neighbouring modules also overprinted each other, and
network names overlapped. Each gradient streamline was embedded in the PDF as a bbox-sized raster (517 KB for the science
example). The following decisions replace the matching parts of "Coordinates" and "Public API" for `draw`/`plot`. The
layout, the geometry contract and the TS parity are unchanged, and a test asserts that no draw option changes the
layout-px geometry.

- **Point-based text, data-based shapes.** Shapes stay in layout px (data units). Every text size, gap and margin is
  in points: the label gap is `label_pad=3` pt from the module edge, replacing the TS 20 px, and the network names sit
  0.4 em under the diagram with `va="top"`, replacing the TS 20 px + baseline. Font sizes therefore print exactly at
  any axes size.
- **Draw-time fitting.** An invisible `_Fitter` artist with zorder `-inf` and `in_layout=False` refits at every draw.
  It picks the label lines, truncates labels and names, places the network names, and sets the limits so that the
  diagram fills the axes and every text stays inside it. Texts are `in_layout=False`. This keeps constrained layout,
  `bbox_inches="tight"` and `fig.set_size_inches` correct. The fit only sets limits when they change, so redraws are
  stable. The axes aspect is never forced: the diagram stretches to the axes, and text does not.
- **Label fit rule.** The web app's multi-line rule (`ceil(h / 1.8 em)`, odd) is applied with the module height in
  points at the current scale, capped by the names in the geometry and `max_label_lines`. That parameter replaces
  `max_label_names`, which was never released. `avoid_label_overlap=True` (the default) places labels in descending
  module flow. A label that would overlap one already placed loses lines, then its whole label. `False` reproduces the
  web app's overprinting.
- **Truncation.** `max_label_width="auto"` (the default) truncates label lines with an ellipsis, so that each label
  column stays within 25% of the axes width. A number is a cap in points, and `None` turns truncation off. A figure that
  `draw` creates itself (1 pt per px) is not truncated. Network names are truncated to the distance between network
  centres. Text is measured with the renderer in use, because Agg hinting makes text up to about 7% wider than the
  outline metrics. If the labels still leave less than 5% of the axes for the diagram, `draw` warns.
- **Font sizes default to rcParams.** `fontsize=None` means `"small"` and `network_fontsize=None` means `"medium"`, so
  setting `font.size` for the paper scales everything. At matplotlib defaults this gives 8.3 and 10 pt, close to the TS
  8 and 10. Module labels use `parse_math=False`, because node names may contain `$`.
- **Seams.** Modules get a hairline in their own face colour by default (`edgecolor="face"`, `linewidth=0.3`).
  It hides the antialiasing seams between stacked groups and at streamline ends. `linewidth=0` gives the exact TS
  rectangles.
- **Vector gradients.** Gradient strips use `interpolation="none"`, so PDF and SVG embed each one as a 256 × 1 image.
  The science example's PDF went from 517 KB to 122 KB. `rasterized=True` rasterizes the modules and streamlines into
  one merged image and keeps the text vector.
- **Artists and styling.** `draw` still returns the Axes. `alluvial.get_artists(ax)` returns an `AlluvialArtists` with
  `modules`, `streamlines`, `module_labels`, `network_labels` and `geometry`. Every artist has a `gid`, which SVG keeps
  as the element id. The new keyword dicts `module_kw`, `streamline_kw`, `label_kw` and `network_label_kw` sit next to
  `text_kw`. `palette=` also accepts a `Colormap` object. `plot` raises `TypeError` for a keyword that neither `layout`
  nor `draw` takes, instead of the opaque `LayoutOptions` error.
- **Label name candidates.** `ModuleGeometry.largest_leaf_names` (and `label.text`) keep the web app's lines-per-module
  cap at layout px for parity. The new `ModuleGeometry.name_candidates` (labelled modules only) holds those names
  followed by the next largest, up to `geometry.NAME_CANDIDATES` = 25; `draw` picks lines from it, so a tall axes or a
  small font shows more names. It defaults to `()` and `from_dict` accepts dicts without it. Fixture comparisons
  ignore it (the TS fixtures have no such field).

## Packaging (since 0.1.0; current requirements)

- Requires Python >= 3.11, matplotlib >= 3.7 and numpy >= 1.23.2 (the first numpy with Python 3.11 wheels). `draw()`
  caps the initial size of its own figure so that very tall layouts stay under the Agg size limit of older matplotlib
  (2**16 px per side). Tested with the lowest direct dependencies on 3.11 (including the tutorial notebook, which
  needs ipykernel >= 6.3.1) and with current releases on 3.11, 3.12, 3.13 and 3.14. (Python 3.10 was supported up
  to 0.4.0.)
- `infomap>=2.14` for the object reader; the `dev` extra pins `infomap>=2.15.1`, which the infomap tests need.
- The wheel ships only `src/alluvial` (with `data/color-schemes.json`, `data/d3-interpolators.json` and `py.typed`). The sdist adds the tests,
  their data, `tools/ts-fixtures/make_datasets.py` and `docs/dev/port-notes/data`, so its tests run standalone.
- CI: `.github/workflows/tests.yml` (ruff, pytest on 3.11-3.14 on ubuntu and macos, build plus wheel smoke test).
  The fixture regeneration check needs the web repo and is not run in CI; the fuzz test (`-m fuzz`) skips there.

## v2 design (decided 2026-10-10, coordinating agent)

v2 keeps the v1 rules: a faithful port, TS fixtures for every engine feature, and the geometry as the only contract.

- **Hierarchy.** Port `Module.expand`/`regroup`/`move`, `Network.moveToIndex` and the store's `expand`/`regroup`, plus the
  `Network.tree` hierarchy outlines and the way the web app draws them.
  - Public API: `layout(..., module_level=1)`. It is an int, or a per-network sequence. Level k shows every module at depth k
    where the path is deep enough, using the deepest module otherwise.
  - It is implemented as a **deterministic sequence of store `expand` ops**, so TS parity is testable: per network, repeat
    "expand the visible modules whose level is below k, in current layout order" until nothing changes. The harness must
    run the identical op sequence through the TS store for the fixtures.
  - For explicit control there is `expand=[(network, module_id), ...]` (applied in order, then `module_level`).
  - The geometry gains hierarchy outlines (parent-module rects per network) and `ModuleGeometry.level`. `draw` draws the
    outlines like the web app (`hierarchy=True`).
- **Highlight groups.** `layout(..., highlight=...)` takes either a mapping `{label: iterable of node identifiers}` or a
  callable `(node) -> label | None`.
  - It is applied after the build through the store's node colouring path (`setColor` → `update()`, as the TS does for
    selected nodes). Each label gets one highlight index, in mapping order.
  - `highlight` and `colors` are mutually exclusive (ValueError). With `highlight`, the unmatched nodes stay gray.
  - The labels go into the geometry (`highlight_labels`), and `draw(..., legend=True)` / `alluvial.legend(ax)` adds a
    matplotlib legend.
- **More colour ops (parity).** Colouring by layer, by physical id and by metadata, if the TS store has them, via
  `colors="layer" | "physical_id"`.
- **IO.**
  - Multilayer splitting (`multilayer-utils.ts`): `read(..., split_layers=True)` returns one NetworkFile per layer, with the
    TS "multilayer-expanded" identifier. Done (`io/multilayer.py`).
  - Infomap JSON (`-o json`) input. Done (`io/json_reader.py`). The saved web-app diagram JSON waits for v3 (decided: it
    is not cheap; such a file gets its own error message).
- **Small v1 follow-ups.**
  - Network ids are auto-disambiguated when file stems collide (`out`, `out_2`, ...), with no error. An explicit
    `ids=` override is accepted.
  - The README snippets must run when pasted.

## v2 implementation decisions (2026-10-10)

These settle the open questions of the v2 port notes (v2-hierarchy §14, v2-highlight §11, v2-io §9) as implemented.
The TS parity rule is unchanged: `tests/test_layout_v2.py` checks that `layout()` with public arguments reproduces
every v2 fixture whose op sequence they can express (37 of 69), bit for bit and equal to the replayed store's geometry.

```python
geom = alluvial.layout(networks, *, names=None, ids=None, identifier="id", split_layers=False,
                       colors="similarity", module_level=1, expand=None, highlight=None, highlight_colors=None,
                       **layout_options)
ax = alluvial.draw(geom, ax=None, *, ..., hierarchy=True, legend=False, label_colors="auto", hierarchy_kw=None, ...)
leg = alluvial.legend(ax, *, other=None, **legend_kwargs)
```

- **Order of the store steps:** build, `expand`, `module_level`, then the colouring (`colors` or `highlight`). So
  colouring happens after expanding (hierarchy Q2, highlight Q3): sub-modules are matched and coloured as modules
  of their own. The other order is fixture-covered but not exposed.
- **`module_level`** only expands (never regroups), visible modules only (hierarchy Q6), as specified in
  v2-hierarchy §10.1. Since fix round WP8 (B2) it is one TS `setModuleLevel` op: expand rounds without intermediate
  layouts and one layout at the end (same visible modules; hidden order and last bits differ from per-expand layouts). Regroup, move and a custom module order are not public in v2 (hierarchy Q7).
- **Parity quirks kept** (hierarchy Q1): ~~the `isAncestor` prefix bug and the trailing-colon level~~ (both fixed in
  TS and Python in fix round WP3: E1, E2). ~~A state that makes
  `Network.tree` throw gives no outlines plus a warning (hierarchy Q5).~~ Fix round WP7 (E15a): `Network.tree` no
  longer throws for a visible `P` with a visible `P:x`; one outline encloses both, and the warning is gone.
- **`highlight`** uses the real `colorCategoricalMetadata` (highlight Q1(a)). The labels of both forms are computed
  on the input nodes (network order, then node order) and carried to the leaves in a private metadata key on copied
  nodes; the caller's `NetworkFile`s are never changed. An identifier under two labels raises `ValueError` (Q2).
  Callable labels are in first-appearance order (Q6), must be hashable and distinct as strings. Identifiers that
  match no node warn with a count; labels with the default colour (drawn gray) or a shared colour warn. (The
  live-walk skip and its warning are gone since fix round WP5, E4.) `highlight` and an explicit `colors` raise `ValueError`;
  `highlight_colors` without `highlight` too. `highlight_colors` takes colour strings (stored as given, so any
  matplotlib colour name works at draw time) or RGB tuples in [0, 1] (stored as `#rrggbb`). Named web colour schemes
  are not ported (Q7). `alluvial.NodeInfo` is the callable's frozen view: network index and id, identifier, id,
  state and layer id, name, flow, `path` (`"1:2:3"`) and read-only metadata.
- **Legend** (highlight Q5): one swatch per label with a highlight index >= 0, in label order, in the palette that
  `draw` uses; `other=` adds a default-colour entry. No entry for insignificant members. By default the legend is a
  frameless row centred above the diagram inside the axes, and the fitter reserves its height (and, for a figure
  `draw` made itself, its width); the number of columns is chosen when it is created to fit the axes width. With
  `loc` or `bbox_to_anchor` it is a plain matplotlib legend and nothing is reserved.
- **Label-line colours** (highlight §5.3): `label_colors="auto"` (default) colours lines only when the geometry has
  highlight labels, because with the similarity colours every line would just repeat its module's colour at lower
  contrast. Out-of-palette and gray names are black (TS tspans). An explicit `color` in `label_kw`/`text_kw` wins.
- **`colors="layer"` / `"physical_id"`** raise `ValueError` unless some network is multilayer / higher-order
  (highlight Q8).
- **Hierarchy rendering** (hierarchy Q3, Q4): `hierarchy=True` means `"shadow"`, the web default, and is a no-op for a
  flat diagram. Shadows are opaque `#a4a4b0` (the web composite over white) at a z-order under the streamlines.
  Outlines are dotted rounded boxes (`#b6b69f`, alpha 0.5, 1.2 pt stroke, dots every 2.5 linewidths) between the
  streamlines and the modules. Offsets stay in layout px (data units), as in the web app; the outline corner
  rounding gets a mutation aspect at every fit so corners are round on screen. The fitter treats the boxes' overhang
  as part of the diagram: right-hand labels move out past the shadows, left-hand ones past outlines, and the network
  names go below the lowest shadow.
- **Multilayer** (io Q2, Q3): `layout(split_layers=True | [flags per input])` splits inputs and flattens them in
  order; `names` and `ids` then apply to the split networks. `identifier="name"` with splitting warns (it does not
  apply). `layout` also accepts Infomap JSON dicts (default name `"network {i}"`, id `net{i}`, unless the dict has
  them). A single dict, like a single path, raises `TypeError`.
- **Network ids:** the first network keeps its id; later duplicates become `<id>_<k>` with the smallest `k >= 2` not
  used by any network. `ids=[...]` must be unique strings. An id containing `--` (it would break streamline ids) still
  raises, now pointing at `ids=`. `names` may be numbers (converted with `str`).
- **Tooling:** `ruff format` excludes `docs/dev/port-notes/*.md` (TS-aligned pseudocode); README snippets run in
  `tests/test_readme.py`.

## v3 design (decided 2026-10-10, coordinating agent)

> **0.5 (fix round WP2):** the 2019 saved-diagram format is removed (owner decision, fix-plan.md "Owner answers").
> `read` rejects it with a `ValueError` pointing to alluvial 0.4; `save_diagram(networks, path, **layout_kwargs)`
> writes only the web-app files; `SavedDiagram`, `diagram_json` and the state restore are gone. The 2019 parts of the
> v3/v4 sections below are kept as history; "Status (0.5.0)" at the end is current.
>
> **0.5 (fix round WP9):** saved diagrams use "alluvial network files" formatVersion 1 (saveload-plan.md §4), written
> and restored by the same code in TS (`serializeDiagram`, `openNetworks`) and Python (`serialize_diagram`,
> `DiagramStore.open_networks`), byte- and bit-exact (fixtures + fuzz, also a direct Python-save -> TS-open).
> `save_diagram(networks, path, *, loose=False, **layout_kwargs)` writes a zip by default (loose files with
> `loose=True`, one `.json` for one network); `layout(restore_state=True)` restores options, scheme, module orders and
> names, with explicit keywords winning silently; `read` takes a directory or a list of paths and sorts one save into
> saved order. The store keeps the TS display options (`display_options`) and `show_bipartite_nodes` (E19).
> `open_networks`/`openNetworks` consume the blocks (remove them from the files once read), so opening the same file
> objects again keeps the current state; `layout()` reads the blocks without changing the caller's files.

- **Web-app bridge.** v3 reads saved web-app diagram JSON (the "save diagram" output of the web app, e.g.
  `apps/web/public/data/science-1998-2001-2007.json`) and reproduces what the web app shows after loading it. It also
  **writes** that format from Python, so a figure made in a pipeline can be opened and fine-tuned in the web app.
  - Parity: a TS fixture loads each saved JSON, and a round trip goes Python write → TS load → same geometry.
  - The writer is a port of the TS save code, run on the engine store, never re-derived from the geometry.
  - Public API: `alluvial.read(path)` recognises a saved diagram and returns the list of networks plus their stored state.
    `layout()`/`plot()` accept it directly. `alluvial.save_diagram(networks, path, **layout_kwargs)` writes JSON the web app
    can load.
- **JSON `colors` input** (`checkColors`) is ported, so Infomap or diagram JSON that carries colours renders as in the web
  app.
- **Colour schemes.** The TS schemes (`schemes/*`, `setSelectedScheme`) are ported, so `layout(..., scheme="...")` picks
  them by name. A list or colormap `palette=` in `draw` still overrides.
- **Small follow-ups.**
  - Fix the warning stacklevels when `layout()` is called through `plot()`.
  - Warn on an empty diagram (all flows ≤ 0), keeping the geometry unchanged.
  - Use the non-deprecated infomap arguments in examples and the tutorial.

## v3 implementation decisions (2026-10-10, provisional; owner to confirm)

These settle the open questions of [`v3-webapp-json.md`](port-notes/v3-webapp-json.md) §10 as implemented. Parity:
`tests/test_v3_fixtures.py` replays all 30 v3 fixtures bit for bit, and for the 16 `roundTrip` ones checks that the
Python `diagram_json`/`webapp_files` texts equal the TS `saved`/`webAppFiles` byte for byte and that the Python loads
of them equal the TS `reload`/`webAppReload`. The fuzzer does the same for every case TS runs (`ts-roundtrip.json`):
v1 and v2 seeds 0-5999 and 20000-24999 pass with round trips (about 95 % of the cases reach them; when TS throws in a
reload dump, `Network.tree` on a module shown with one of its sub-modules, Python raises too, with the reloads built
from the case's ctor options as in the harness).

```python
saved = alluvial.read("diagram.json")                       # SavedDiagram (a list of NetworkFile) + .state etc.
geom = alluvial.layout(saved, restore_state=True, scheme=None, ...)
alluvial.save_diagram(networks, path, *, format="diagram", version=None, timestamp=None, **layout_kwargs)
```

- **Q1, writer target:** both. `format="diagram"` (default) is the port of `saveDiagram` (`io/saved_diagram.py`
  `diagram_json`, on the engine store after the `layout` steps); `format="webapp"` writes the §4 files (directory or
  `.zip`) that today's web app opens, and warns about what they cannot carry (options, stree insignificance, custom
  order). `layout()` is split into `_build_store` + `build_geometry` so that both share the store steps.
- **Q2, state on read:** restored by default (`restore_state=True`), as the 2019-2021 app did and exactly as the
  harness's `restoreState`: layout options (explicit keywords win; an unsupported value such as `verticalAlign:
  "top"` warns and keeps the default), `defaultHighlightColor`, the display settings (`fontSize` also sets the
  geometry's label line count), then `setHighlightColors(state.highlightColors)` after the build. `duration` is not
  restored. `restore_state=False` is today's converter (empty palette).
- **Q3, `;` paths in a saved diagram:** reproduced like TS (`split(":").map(Number)` -> a module `NaN`), with a
  warning; the fixtures pin this behaviour.
- **Q4:** `version` `"0.3.0"`, `timestamp` = now in ms, both injectable; no `generator` key (it would break byte
  equality with TS).
- **Q5/Q6:** `moduleNames` is always `[]` (no module-name API); the harness shims `getModuleNames = () => []`.
- **Q7:** the 3.5 MB sample stays opt-in (`ALLUVIAL_LARGE_FIXTURES`, `test_v3_large_fixture`).
- **Q8:** the web-app files carry no top-level `layerId`/`originalId` (as the harness writer).
- **Colours:** `DiagramStore.set_networks` runs `check_colors` (since fix round WP6, S7: merged palette, each list
  palette remapped per file, no dummy 0); `layout` copies the files with input colours first, so the caller's
  `NetworkFile` is not changed. When the input carries colours (a saved
  diagram, or JSON with `colors`), the default `colors` is `None` (keep them); an explicit `colors=` recolours.
  `scheme=` takes a web-app scheme name (data dumped from TS, `src/alluvial/data/color-schemes.json`) or a list, and
  gives the default `highlight_colors`. At write time, palette entries that are not hex/`rgb()`/CSS names (matplotlib
  `"tab:blue"`) are written as `#rrggbb`.
- ~~**JSON `"flow": null`** is read as 0~~ (fix round WP4, E9/Y13): both engines reject a NaN, infinite, missing or
  `null` flow at load (`io.identifiers.validate_network_nodes`, TS `parsers/validate-nodes.ts`, also called by
  `Network.create`). The V8 TimSort emulation that reproduced TS's order for NaN sort keys is deleted.
- **Hand-made saved diagrams (parity review, 0.3.0).** The reader follows the `...network` spread: a stored network
  `name` that is a number is shown as its JS string, and a missing, `null` or boolean `name` as nothing (`""`; the
  spread does not copy `File.name`, a prototype getter), not as the id; a number network `id` works as its string.
  A number node `path` is a top-level module (`TreePath.toArray(2) = [2]`), in Infomap JSON too. The geometry,
  palette and file name then equal TS (verified with a scratch TS harness). **Documented divergence, writers only:**
  Python cannot tell JSON `null` from a missing key or keep a number where it stores a string, so re-saving such a
  file writes `"name": "1998"`/`""`, `"id": "5"`, `"flow": 0` and omits `"codelength": null` and a node
  `"name": null`, where TS writes the stored values back (same class as JSON `layerId: null`, v2-io §2.8). Saved
  `state` values that are `null` are skipped (the harness's `restoreState` would assign them).
- **`save_diagram` input (decided with the API wiring, 0.3.0):** it takes the networks and `layout`'s keywords, not
  an `AlluvialGeometry` (and not a `layout(..., return_store=True)`-style handle). The geometry contract stays
  geometry only: it has no node paths, identifiers or expansion levels, and the writers must read the engine store
  (v3 design). `layout` is deterministic, so `layout(x, **kw)` and `save_diagram(x, path, **kw)` describe the same
  diagram; passing a geometry raises a `TypeError` that says so. Considered and rejected: attaching the store to the
  geometry (breaks the frozen, serialisable contract and its equality), and a separate `Diagram` result type (a
  second public result type for one use).
- **Module names (0.3.0, provisional):** with `restore_state=True`, the saved `moduleNames`
  (`${networkId}_module${moduleId}` keys) become the modules' custom names after all store steps, as the 2019-2021
  app's id-keyed `Module.customNames` did; entries for modules that do not exist are ignored, and the 2019
  fallback that showed a module's named descendants is not ported. `ModuleGeometry.name` (new, default `""`) carries
  `Module.name`; `ModuleGeometry.label` keeps the leaf names (TS parity), and `draw` shows the name instead, in
  black, as `Module.tsx` does (`module.name || <LargestLeafNames>`). The writers still emit `moduleNames: []` (Q5),
  so a read → save round trip drops the names; writing them would break byte equality with the harness (which
  shims `getModuleNames = () => []`, as TS has no module-name getter any more).
- **Warnings (0.3.0):** every package warning computes its `stacklevel` (`alluvial._warnings.user_stacklevel`: the
  first frame outside the package), so warnings point at the caller's line whether it called `layout`, `plot`,
  `read` or `save_diagram`. A diagram where no node flow is positive (zero or negative; NaN is rejected since WP4) warns and keeps the
  geometry.
- **infomap API in examples/tutorial (0.3.0):** infomap 2.15 marks the relax-rate keywords on `Infomap()`/`run()`
  and the result accessors on `Infomap` (`num_top_modules`, `num_levels`, `codelength`) as pending deprecations.
  `examples/multilayer.py` passes `"--multilayer-relax-rate 0.05"` to `run` (works on infomap 2.14 and 2.15; the
  first choice, `run(options=infomap.Options(...))`, is 2.15 only and failed on 2.14, which `pyproject` allows;
  same codelength and figure, byte-identical on both); the tutorial drops the default relax rate and reads the partition facts with `alluvial.read(im)`.
- Not done: reading a web-app `.zip` in Python.

## v4 design (decided 2026-10-10, coordinating agent): paper polish

- **Module names.** `layout(..., module_names=...)` takes either a mapping `{(network, module_id): name}` (network given by
  index or id) or a callable `(ModuleInfo) -> str | None`.
  - It is applied through the ported store op `setModuleName`, so a fixture can replay it as a TS op sequence.
  - `draw` shows the name in place of the leaf names, as the web app's Module.tsx does.
  - Saved diagrams write the names in `moduleNames` when any are set. When none are set they write `[]`, which keeps the
    v3 fixtures byte-identical.
- **Module order.** `layout(..., module_order={network: [module_id, ...]})` puts the listed modules at the given positions.
  The list runs bottom to top, matching the layout index. Unlisted modules keep their relative order above or below.
  - It is implemented as a deterministic sequence of TS `moveModule` ops (an engine helper), so the web app reproduces
    it with the same moves. (Fix round WP7, B1: one TS `setModuleOrder` op with one layout, bit-identical to the
    moves; v4-names-order §3 erratum.)
  - The harness records it as a macro, like `moduleLevel`.
  - `module_order` and `sort_modules_by` coexist: the sort sets the start, the moves define the result.
- **IO.** Read the web app's `.zip` bundle of per-network JSON files with the stdlib `zipfile`.
- No new heuristics that the web app cannot reproduce (no automatic crossing minimisation). It can be proposed to the
  owner as a future TS + Python feature.

## v4 implementation (2026-10-10)

Spec: [`v4-names-order.md`](port-notes/v4-names-order.md). Parity: 14 new TS fixtures in `tests/fixtures/v4/`
(`tests/test_v4_fixtures.py`), each replayed bit for bit, reproduced through public `layout()` arguments, and, for
the 4 round trips, through `save_diagram` in both formats byte for byte. Existing fixtures are byte-identical
(`generate.mjs --check`); `provenance.txt` gained `fixtures_v4`.

```python
geom = alluvial.layout(
    networks,
    module_order={0: ["3", ...], "net2": [..., "1"]},
    module_names={(0, "3"): "Physics"} or (lambda m: ...),
)  # m: alluvial.ModuleInfo
files = alluvial.read("diagram-webapp.zip")  # list[NetworkFile]
```

- **Step order:** build, `expand`, `module_level`, colouring/`highlight`, `module_order`, restored names, `module_names`.
- **`module_order`:** bottom to top; unlisted visible modules keep their relative order above, or where an `...`
  stands. Engine helper `DiagramStore.apply_module_order` issues ~~`moveModule("down")` ops only past visible modules
  (minimal adjacent swaps, networks in ascending index)~~ one `setModuleOrder` op with the full visible target of
  every network whose order changes (fix round WP7, B1); the harness macro `moduleOrder` runs the same in TS.
  Hidden modules cannot be placed (error).
- **`module_names`:** mapping or callable; `DiagramStore.apply_module_names` issues `setModuleName` ops.
- **Supersedes v3 Q5/Q6:** `save_diagram`/`diagram_json` write `moduleNames` from `Module.name` (v4 shim
  `[module.id, {name, flow}]` per named module of `network.children`), `[]` when a network has none, so unnamed
  diagrams are unchanged. The v3 fixture `multilevel-tree__colored__names__roundTrip` keeps the v3 shim
  (`diagram_json(module_names=False)` in its test). Web-app files carry neither names nor order (warned).
- **Zip:** `read()` of a `.zip` mirrors the app's `readAcceptedFiles` (archive order, network suffixes only, id =
  entry base name); `layout` accepts the zip path as an input. Supersedes "Not done: reading a web-app `.zip`".
- **Example:** `examples/names_order.py` → `docs/img/names_order.png` (science 2001-2007, fields named by a
  callable, one order for all years); README "Module names and order".
- **Fuzzing:** `gen.py --v4` mixes the `moduleOrder`/`moduleNames` macros and `setModuleName` into the v2 op
  sequences (round trips save `moduleNames`); v4 seeds 0-9999 pass (tools/ts-fixtures/README.md).
- **Not done:** the 2019 fallback that labelled a module
  with its named sub-modules. ~~A faster `module_order`~~ (done in fix round WP7, B1: one layout, proven
  bit-identical; reversing 40 of 429 science modules takes 0.11 s instead of 85 s).

## Status (0.6.0, 2026-10-21)

0.6 adds c3 2 (TS #47) and the saved tone and offset (TS #57) on top of the 0.5 status below. **Port base: TS
`master` `60fa1bf` (#58)**, recorded as `ts_repo_head` in `tests/fixtures/provenance.txt`; 297 fixtures (205 v1/v2,
77 v3, 15 v4) replay bit for bit, `generate.mjs --check` is byte-identical, and the fuzzer has a c3 mode.

- Colours: `alluvial.palette` ports `schemes/index.ts` (`TONES`, `schemeColors`, `hierarchyOptions`, ...), with
  `c3-colors==2.0.1` for the C3 schemes and `hierarchy()`; `DiagramStore` ports the tone/offset fields and setters
  and `colorModuleHierarchyInAllNetworks`; the saved diagram block gains `colorTone`/`colorOffset`
  (`io/alluvial_format.py`, TS `parsers/alluvial-format.ts`).
- #58 moved the TS diagram classes' arrays and maps behind getters; no ported behaviour changes.
- Known divergence (c3-colors, not the port): `hierarchy()` of a module with many sub-modules (about 40 or more)
  swaps a few sibling colours; strict xfail tests, owner decides on a c3-colors release.
- Syncing: `git -C <web> log <ts_repo_head>..master -- packages/alluvial-diagram/src` lists the engine commits to
  port (the web repo's `CLAUDE.md`, "Python port"); then `ALLUVIAL_TS_ROOT=<checkout> node
  tools/ts-fixtures/generate.mjs --check`, and regenerate after porting (`STATUS.md`, "How to sync with TS master").

## Status (0.5.0, 2026-10-10)

Replaces the 0.2.0, 0.3.0 and 0.4.0 status sections. The owner report is [`STATUS.md`](STATUS.md); the fix round is
planned in [`fix-plan.md`](fix-plan.md) and logged per work package in `CHANGELOG.md`.

**Implemented, checked bit for bit against the TS store** of the `py-parity-fixes` worktree: 259 fixtures (205
v1/v2, 39 v3, 15 v4; `generate.mjs --check` byte-identical) and the differential fuzzer (v1/v2/v4 with round trips
and Python-save -> TS-open).
- v1: readers (tree/ftree/stree/clu, Infomap objects and `Result`), engine, `colors`, geometry, matplotlib renderer.
- v2: `module_level`, `expand`, hierarchy shadows/outlines, `highlight` + legend, layer/physical-id colours,
  multilayer `split_layers`, Infomap JSON input.
- v3/v4: `scheme`, JSON `colors`, `module_names`, `module_order`, `read` of a `.zip`, a directory or a list of paths.
- 0.5 fix round (TS and Python together): tree paths (E1-E3, P3), load validation (NaN flows rejected; the V8
  TimSort emulation is gone), leaf mutation and colour operations (E4-E6, S1, S3, S5-S7, E12), layout state and
  `setModuleOrder` (one layout for `module_order`, B1), batched `module_level` (B2), and the saved-diagram format
  "alluvial network files" formatVersion 1 (`serialize_diagram`/`open_networks`, the TS `serializeDiagram`/
  `openNetworks`), with `show_bipartite_nodes` (E19). The 2019 format and Python 3.10 are dropped.

**Known divergences (hand-made input only).** JSON `layerId: null` reads as missing; an out-of-palette colour index
draws black in TS and cycles with a warning in Python (S9/Y16, kept); on x86-64 V8 (no FMA) about 1 in 300k `log2`
inputs differ in the last bit. When TS throws, Python raises too, but not necessarily the same message.

**Known in both engines.** A reload equals the original up to float summation order (about 1e-13 px): highlight
groups built by a colour operation sum their flows in another order than groups built at load. Labels of nodes with
exactly equal flow can therefore list in another order after a recolour or a reload (found while writing
`docs/capabilities.ipynb`; not fixed in this round).

**Deferred.** Regroup, `resetLayout`, `moveNetwork`, `mergeMultilayerFiles` and selection side effects as public
API (ported and fixture-covered in the engine); the LOW items of fix-plan §4.1; the 2019 label fallback for named
sub-modules.

**Owner decisions (ranked; defaults as implemented).**
1. Release metadata: PyPI name `alluvial` (free on 2026-10-10), placeholder `authors`, MIT. Nothing published.
2. TS package version (left at 1.15.0 in the worktree; the API change is breaking).
3. Default `colors="similarity"` (the web app loads gray) with no "clean" mode.
4. Duplicate identifiers warn; a `highlight` identifier under two labels raises.
5. `module_order` semantics: unlisted modules above the listed ones unless `...` places them.
