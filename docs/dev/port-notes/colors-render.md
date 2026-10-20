# Port note: Colors, labels and rendering

Topic owner: coloring operations (`DiagramStore`), module similarity (Jensen–Shannon),
palettes, the fill-color function (including the "insignificant = brighter" rule), and how the
React/SVG components draw modules, streamlines, labels and network names.

Citation prefix: unless a path says otherwise, `src/…` means
`web/alluvial/packages/alluvial-diagram/src/…` (TS repo, read-only). `apps/web/…` means
`web/alluvial/apps/web/…`. `node_modules/…` means `web/alluvial/node_modules/…`.

Companion data, generated from the TS sources and stored next to this note:

| File | Content |
|---|---|
| `docs/dev/port-notes/data/c3-sinebow-512.json` | The default palette `COLOR_SCHEMES["C3 Sinebow"]`: 512 strings, exactly as TS produces them (`"rgb(198, 59, 59)"`, …) |
| `docs/dev/port-notes/data/hsl-brighter-0.8-ref.json` | 549 `[input, d3.hsl(input).brighter(0.8).toString()]` pairs (default gray, black, white, all 512 Sinebow colors, Category10, Tableau10, Set3). Use it as a unit-test oracle for `brighter()` |

---

## 0. Summary and v1/v2 split

* **Color lives on leaf nodes only.** Each `LeafNode` has an integer `highlightIndex`
  (`-1` = `NOT_HIGHLIGHTED`). A module is split into `HighlightGroup`s keyed by
  `(highlightIndex, insignificant)`. Colors are strings in a store-level registry,
  `highlightColors[highlightIndex]`. Gray `#b6b69f` is used for `-1`.
  (`src/alluvial/LeafNode.ts:52-55`, `src/alluvial/Module.ts:204-210`, `src/alluvial/HighlightGroup.ts:7`,
  `src/store/DiagramStore.ts:91-92`)
* **Coloring changes geometry.** Coloring moves leaf nodes between highlight groups through
  `LeafNode.update()`, which re-attaches them to streamline nodes keyed by highlight index.
  Every coloring op ends with `updateLayout()`, which re-runs `calcFlow` and the full layout
  (`src/store/DiagramStore.ts:485-491`). Layout fixtures must therefore record which coloring op, if any, was applied.
* **Nothing is colored on load.** A diagram built from `.tree`, `.ftree`, `.stree` or `.clu` files is all gray. Coloring only
  happens when the user clicks a "Paint …" button (`apps/web/src/components/Sidebar/Colors.tsx:70-225`), presses `p` to paint the
  selected module (`:26-27`), or when the input JSON carries `colors` or per-node `highlightIndex` (`checkColors`, §2.5;
  `src/alluvial/LeafNode.ts:52-55`).
* "Consistent module colors across networks" in the web app is **"By similarity → Paint all"**,
  which is `colorMatchingModulesInAllNetworks()` (`apps/web/src/components/Sidebar/Colors.tsx:111-114`).

| Piece | v1 | v2 / later |
|---|---|---|
| Registry: `defaultHighlightColor`, `highlightColors`, `getHighlightIndex`, `clearColors` | **required** | |
| Fill function `highlightColor()` incl. `brighter(0.8)` for insignificant | **required** | |
| Default palette C3 Sinebow (512 colors, data file) | **required** | the other 63 schemes |
| `Module.getSimilarModules` + `js_div` | **required** | |
| `colorMatchingModulesInAllNetworks` | **required** (the v1 feature) | |
| `colorModuleIdsInAllNetworks`, `colorNodesInModulesInAllNetworks` | recommended (cheap, same primitives) | |
| `colorByLayer`, `colorByPhysicalId` | | v2 (multilayer/state extras) |
| Metadata coloring (`colorCategoricalMetadata`, `colorRealMetadata`, `colorRealIntervals`) | | v2 |
| Single-module ops (`colorModule`, `colorMatchingModules`, `colorModuleIds`, `colorNodesInModule`, `colorSelectedNodes`) | `colorModule` only, as the primitive | v2 "highlight groups API" |
| Renderer: group rects, gradient streamlines, labels (single/multi-line, state aggregation), network names | **required** | |
| Module-id labels, adaptive font size, title case, drop shadow | optional | |
| Hierarchical shadow/outline super-modules, expand/regroup | | v2 |

---

## 1. Color data model

### 1.1 Leaf node

* `highlightIndex: int`. It is set from the input node if `Number.isInteger(node.highlightIndex)`, otherwise
  `-1` (`src/alluvial/LeafNode.ts:52-55`). It is mutable.
* `insignificant: bool` (getter) is `not treePath.isSignificant(moduleLevel - 1)` (`src/alluvial/LeafNode.ts:63-65`).
  * `TreePath` records insignificance **only** when the path *string* ends in `';'`. In that case it
    parses every `(\d+)([:;])+` match and marks level `L` as insignificant iff the separator after path element
    `L` is `';'` (`src/utils/TreePath.ts:3, 26-38`). Paths given as arrays, or strings not ending in `';'`, are all
    significant (`src/utils/TreePath.ts:39-45`).
  * `isSignificant(level)` returns **False for an out-of-range level**, so the node counts as *insignificant*
    (`src/utils/TreePath.ts:206-212`). In v1 `moduleLevel = 1` gives level 0, which is always in range.
  * Example: `debug5_0.stree` line `1:2;3; 0.2 "node 3" 144` has `insignificant = [False, True, True]`. At module level 1 the node is
    significant.
* `flow` getter returns `_flow` if `visible`, else 0 (`src/alluvial/LeafNode.ts:67-69`). `visible` is the bipartite toggle, so it is effectively always True in v1.

### 1.2 Highlight group

* One per distinct `(highlightIndex, insignificant)` within a module. It is created on demand in
  `LeafNode.add()` via `module.getGroup(hi, insig) ?? new HighlightGroup(module, hi, insig)`
  (`src/alluvial/LeafNode.ts:125-127`). New groups are **appended** to `module.children`
  (`src/alluvial/HighlightGroup.ts:28`).
* `isHighlighted = highlightIndex != -1` (`src/alluvial/HighlightGroup.ts:33-35`).
* In layout pass 1, group order within a module is re-sorted as
  `(insignificant asc [False first], highlightIndex asc)` (`src/alluvial/Diagram.ts:215-221`). Only **visible**
  modules are sorted, because the pass-1 walk filters out invisible modules (`src/alluvial/Diagram.ts:176-180`). The sort is total
  because the key is unique per module. Group 0 is stacked at the **bottom** of the module and later groups
  above it. Pass 1 does this at `src/alluvial/Diagram.ts:237-246`, and the geometry that is actually drawn comes from pass 2
  (`src/alluvial/Diagram.ts:348-354`), which keeps the pass-1 order. The result is gray at the bottom, then colors by ascending
  index, then insignificant groups on top. Note that `-1` sorts before every color.

### 1.3 Module

* `isHighlighted = any(group.isHighlighted for group in children)` (`src/alluvial/Module.ts:144-146`).
* `highlightIndex = largestGroup.highlightIndex`, where `largestGroup` is
  `reduce(max by group.flow, strict '>')` with initial `{flow: -inf, highlightIndex: -1}`
  (`src/alluvial/Module.ts:148-150, 195-202`). Ties keep the **first** group. A module with no groups returns
  the dummy, so its `highlightIndex` is `-1`. `group.flow` is a **cached** value (`_flow` backing field,
  `src/alluvial/AlluvialNode.ts:92-100`) that only `calcFlow()` updates (`src/alluvial/Diagram.ts:121-128`). Groups
  created since the last `calcFlow` have flow 0. If all of them are new, the first one wins.
* `removeChild` (swap-remove, `src/alluvial/AlluvialNode.ts:149-158`) does **not** reset the removed child's `parent`.
  A detached module or group therefore still resolves `getAncestor(...)` and `.parent`. This matters for the stale objects of Q3 (§4).
* `isVisible = flow >= network.flowThreshold and flow > 0` (`src/alluvial/Module.ts:124-126`). `flow` is cached too,
  so **a Module object created since the last `calcFlow` is invisible** (flow 0). This matters in §4.
* `setColor(hi)`: `for node in self.getLeafNodes(): node.highlightIndex = hi; node.update()`
  (`src/alluvial/Module.ts:283-288`). `getLeafNodes()` returns a snapshot list. `removeColors()` is `setColor(-1)` (`src/alluvial/Module.ts:290-292`).

### 1.4 Store-level color state (`src/store/DiagramStore.ts`)

| Field | Default | Line |
|---|---|---|
| `defaultHighlightColor` | `"#b6b69f"` | 91 |
| `highlightColors: list[str]` | `[...selectedScheme]` in ctor (137), but **replaced by `[]` (or input colors) on every `setNetworks`** via `checkColors` (209, 220) | 92, 137 |
| `selectedScheme` / `selectedSchemeName` | `COLOR_SCHEMES["C3 Sinebow"]` / `"C3 Sinebow"` | 120-121 |

After loading ordinary files, `highlightColors == []`. Each coloring op then appends colors in
**first-use order**, so index `k` means "the k-th distinct color string used".

---

## 2. Registry operations and the fill function

### 2.1 `getHighlightIndex(color) -> int` (`src/store/DiagramStore.ts:296-312`)

```python
def get_highlight_index(state, color: str) -> int:
    if color == state.default_highlight_color:  # exact string compare
        return -1
    if color in state.highlight_colors:  # exact string compare
        return state.highlight_colors.index(color)  # FIRST occurrence
    state.highlight_colors.append(color)
    return len(state.highlight_colors) - 1
```

Equality is on **strings**. Two scheme entries with the same string share one index (see the duplicates
in §3). Keep colors as strings in the registry. Converting `"rgb(r, g, b)"` to hex is a bijection, so
either form gives identical indices as long as you use one form consistently.

### 2.2 `clearColors(updateLayout=True)` (`src/store/DiagramStore.ts:960-977`)

```python
for network in diagram.children:
    mods = [m for m in network.children if any(g.is_highlighted for g in m.children)]  # snapshot
    for m in mods:
        m.remove_colors()  # setColor(-1) -> LeafNode.update() per node (mutates tree, see §4)
state.highlight_colors = []
if update_layout:
    update_layout()
```

### 2.3 Fill function `highlightColor(default, colors)` (`src/utils/highlight-color.ts:9-25`)

```python
def make_fill(default: str, colors: list[str]):
    def fill(highlight_index: int, insignificant: bool) -> str | None:
        color = (
            default
            if highlight_index == -1
            else (colors[highlight_index] if 0 <= highlight_index < len(colors) else None)
        )  # JS: undefined
        if insignificant:
            return brighter(color, 0.8)
        return color

    return fill
```

Callers:

* group rects: `make_fill(defaultHighlightColor, highlightColors)` (`src/react/Diagram.tsx:54-55`, `src/react/Module.tsx:92`)
* streamline gradient stops: same function (`src/react/LinearGradients.tsx:18-21, 43-53`)
* multi-line label tspans: `make_fill("#000", highlightColors)` (`src/react/Module.tsx:74, 233, 247`)

Edge case: an index outside the registry gives `undefined` in TS. This includes any negative index other than `-1`. React then omits the
attribute:

* group rects fall back to the SVG default fill, black
* gradient stops fall back to the default `stop-color`, black
* multi-line label tspans inherit the `<text>` fill (`#000`)

With `insignificant`, `d3.hsl(undefined).brighter(0.8).toString()` returns the valid string `"rgb(0, 0, 0)"`
(verified in node), so that case is black too. This only happens when input nodes carry `highlightIndex` without matching colors.
For example, `apps/web/public/data/science-1998-2001-2007.json` has per-node `highlightIndex` values 1, 3, 5, 6, … and no `colors` key.
Python should **warn and use the default gray**. That is a deliberate deviation; record it in tests.

### 2.4 Exact port of `d3.hsl(c).brighter(0.8).toString()` (d3-color 3.1.0)

Source: `node_modules/d3-color/src/color.js:5-6` (`brighter = 1/0.7`), `:308-332` (rgb→hsl),
`:346-349` (brighter multiplies `l` by `(1/0.7)**k`), `:354-366` and `:391-396` (hsl→rgb), `:283-296`
(`rgb(r, g, b)` formatting, `Math.round` and clamp to [0, 255]). Python code verified bit-for-bit against
node on all 549 reference colors (0 mismatches):

```python
import math, re


def js_round(x):
    return math.floor(x + 0.5)  # JS Math.round, NOT Python round()


def parse(c):  # "#rgb", "#rrggbb", "rgb(r, g, b)"; extend via matplotlib.colors.to_rgb()*255 if needed
    c = c.strip()
    if c.startswith("#"):
        h = c[1:]
        h = "".join(ch * 2 for ch in h) if len(h) == 3 else h
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    return tuple(
        int(v) for v in re.fullmatch(r"rgb\(\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*\)", c).groups()
    )


def rgb_to_hsl(r, g, b):
    r, g, b = r / 255, g / 255, b / 255
    mn, mx = min(r, g, b), max(r, g, b)
    h, s, l = math.nan, mx - mn, (mx + mn) / 2
    if s:
        if r == mx:
            h = (g - b) / s + (6 if g < b else 0)
        elif g == mx:
            h = (b - r) / s + 2
        else:
            h = (r - g) / s + 4
        s /= (mx + mn) if l < 0.5 else (2 - mx - mn)
        h *= 60
    else:
        s = 0.0 if 0 < l < 1 else h  # NaN for black/white
    return h, s, l


def _h2c(h, m1, m2):
    return (
        m1 + (m2 - m1) * h / 60
        if h < 60
        else m2
        if h < 180
        else m1 + (m2 - m1) * (240 - h) / 60
        if h < 240
        else m1
    ) * 255


def hsl_to_rgb(h, s, l):
    if math.isnan(h):  # all JS comparisons with NaN are false -> m1 branch
        s = 0.0
    m2 = l + (l if l < 0.5 else 1 - l) * s
    m1 = 2 * l - m2
    if math.isnan(h):
        return (m1 * 255,) * 3
    h = math.fmod(h, 360) + (360 if h < 0 else 0)
    return (
        _h2c(h - 240 if h >= 240 else h + 120, m1, m2),
        _h2c(h, m1, m2),
        _h2c(h + 240 if h < 120 else h - 120, m1, m2),
    )


def clampi(v):
    return 0 if math.isnan(v) else max(0, min(255, js_round(v)))


def brighter(c, k=0.8):
    h, s, l = rgb_to_hsl(*parse(c))
    r, g, b = hsl_to_rgb(h, s, l * (1 / 0.7) ** k)  # l may exceed 1 -> clamped per channel
    return f"rgb({clampi(r)}, {clampi(g)}, {clampi(b)})"
```

Reference values: `brighter("#b6b69f") == "rgb(231, 231, 223)"` (insignificant gray),
`brighter("#000") == "rgb(0, 0, 0)"`, and `brighter("rgb(198, 59, 59)") == "rgb(217, 125, 125)"`. All three, and the whole
reference file, were re-checked against `d3-color` 3.1.0 in node, and the Python above was re-run against the file (549/549).

Not covered by the `parse()` above: d3 also accepts CSS named colors, `hsl(...)`, `rgba(...)` and `#rgba`/`#rrggbbaa`.
If the input opacity is below 1, d3 keeps it and prints `"rgba(r, g, b, a)"`. For example,
`brighter("rgba(10,20,30,0.5)") == "rgba(13, 27, 40, 0.5)"`. Palettes and the default gray never carry alpha, so v1 can reject such
inputs or accept them via `matplotlib.colors.to_rgba` (non-parity).

### 2.5 Colors supplied in input (`checkColors`, `src/store/DiagramStore.ts:180-210`) — v1 optional

> **Erratum (0.5, fix round WP6: S7).** The dummy index is gone in TS and Python. The files' palettes are merged (first
> occurrence wins); a `colors` list is local to its file, and each node's `highlightIndex` into it is remapped to the
> merged index (an index outside the file's list, `-1` or past the end, is kept). Each list-palette file's `colors`
> then becomes the merged palette, so a second `setNetworks` on the same files is the identity. A `colors: true` node
> gets the real index of its colour. `moveNetwork` gives every file the store palette before it rebuilds (since WP10 as
> part of its in-memory save and `openNetworks` restore, v2-hierarchy §6.5 erratum). The code below is the old algorithm.

This runs on raw network objects before `new Diagram(networks)` (`:220-224`):

```python
colors, color_idx = [], {}
for net in networks:
    if isinstance(net.get("colors"), list):  # top-level palette; nodes already carry highlightIndex
        for c in net["colors"]:
            if c not in color_idx:
                colors.append(c)
                color_idx[c] = 0  # value unused ("dummyIndex")
    elif net.get("colors") is True:  # per-node "color" strings
        for node in net["nodes"]:
            if node.get("color") is not None:
                if node["color"] not in color_idx:
                    colors.append(node["color"])
                    node["highlightIndex"] = color_idx[node["color"]] = len(colors) - 1
                else:
                    node["highlightIndex"] = color_idx[node["color"]]
state.highlight_colors = colors  # [] for ordinary files
```

With the array form, each network's node indices are used as-is against the **merged** list. The merge is only
consistent if all networks list colors in the same order. The dummy value is **not** always unused. If an earlier network
used the array form and a later one uses `colors: true` with a node color that is already in the map, that node gets
`highlightIndex = 0` (the dummy) instead of the color's real index (`src/store/DiagramStore.ts:190-191, 201-202`).
Mixed inputs are therefore broken in TS. Python should not reproduce this.

Neither of the app's own inputs uses this path. Tree, ftree, stree and clu parses have no `colors`. The bundled diagram JSON has none either (see §2.3).
The `createFilesFromDiagramObject` loader is unused, and `apps/web/src/io/save-diagram.js` is not imported anywhere. For Python v1, a cleaner API is to accept a
`{identifier: color}` or `{module_id: color}` mapping and route it through `get_highlight_index`
plus `setColor`.

---

## 3. Palettes

* Default scheme: `"C3 Sinebow" = c3.colors(512, {scheme: "Sinebow", saturation: 0.55, saturationEnd: 0.8,
  lightness: 0.5, lightnessEnd: 0.9, midpoint: 4.5, steepness: 1})` (`src/schemes/index.ts:118-125, 164`).
  The algorithm is `@mapequation/c3` 1.1.1 (`node_modules/@mapequation/c3/lib/c3.js:60-89, 91-115, 136-148`): Cantor-like
  interval splitting of [0, 1], `d3.interpolateSinebow(start)` per stop, then HSL s/l re-set by a sigmoid of
  "cantor depth", output via `hsl.toString()` → `"rgb(r, g, b)"`.
* **Do not re-implement c3 for v1.** Load `data/c3-sinebow-512.json` verbatim. Its first 24 entries in hex are:
  `#c63b3b #3dc8c8 #87cb43 #8b49cf #d3b051 #5779d6 #5dd97f #dc64bc #df996d #71b6e1 #85e376 #d57ae4
  #d7e67f #9284e8 #88e9c4 #eb8db1 #eca592 #94daed #b3ed96 #d299ee #efe99b #9da3ef #9ff0c3 #f0a1cd`.
* The palette has only **490 unique strings among 512**. The first repeat is index 390, which equals index 326.
  22 repeats in total. Through `getHighlightIndex`, a repeated color maps to the earlier index. This is
  irrelevant below 390 modules, but it is part of the exact semantics.
* Indexing is always `scheme[i % len(scheme)]`.
* `COLOR_SCHEMES` has **64** entries, so there are 63 besides C3 Sinebow. The groups are: 10 d3 categorical, 6 seaborn, 3 matplotlib tab20, 4 C3,
  Mural, 2 seaborn uniform (Flare, Crest), and 38 sampled interpolators (9 diverging, 12 + 9 sequential-multi, 6 sequential-single, 2 cyclical).
* Other schemes (`src/schemes/index.ts:138-214`): d3 categorical lists (Category10, Tableau10, Set1-3, …),
  seaborn and matplotlib tab20 lists (`src/schemes/seaborn-schemes.ts`, `src/schemes/matplotlib-schemes.ts`),
  the 50-color `Mural` (`:65-116`), and 21-step samples `interpolator(i/20)` of d3 continuous scales (`:127-137`).
  These are v2. Python can accept any `list[str]` as a scheme.

Regenerate the data file. The script is run from a scratch directory and writes nothing into the TS repo:

```js
// gen.mjs — node gen.mjs > c3-sinebow-512.json
const NM = "/…/web/alluvial/node_modules/";
const c3 = await import(NM + "@mapequation/c3/lib/index.js");
console.log(JSON.stringify(c3.colors(512, { scheme: "Sinebow", saturation: 0.55, saturationEnd: 0.8,
  lightness: 0.5, lightnessEnd: 0.9, midpoint: 4.5, steepness: 1 })));
```

---

## 4. The mutation primitive and its observable side effects

> **Erratum (0.5, fix round WP5: E4, E5).** Q1-Q4 below are fixed in TS and Python. `LeafNode.remove()` keeps an
> emptied module when the leaf goes straight back into it (`module.moduleId === leaf.moduleId`), so a recolour never
> re-creates, swap-removes or appends a module (no Q1). `network.children` is stable during a colour op (no Q2), module
> references stay valid (no Q3) and flows stay cached (no Q4). `Module.setColor` and the store loops that assign
> `highlightIndex` and call `update()` skip leaves whose index already equals the target (E5), so a no-op recolour
> touches nothing. Consequences: §6.1 is idempotent, `colorMatchingModules` chains run through single-leaf modules,
> `colorNodesInModule` propagates from a single-leaf module, and the verified Q2 example below now gives
> m1=0, m3=1, m2=2, m4=3. `expand`/`regroup` change `moduleLevel` (hence `moduleId`) before `update()`, so they
> still remove the old module. The text below describes the pre-0.5 behaviour.

All coloring goes through `node.highlightIndex = k; node.update()` (`src/alluvial/LeafNode.ts:196-199`),
which is `remove()` followed by `add()`.

`remove()` (`src/alluvial/LeafNode.ts:205-230`):

* It detaches the node from its left and right streamline nodes. Emptied streamline nodes are deleted and their
  opposite becomes dangling. That bookkeeping belongs to the streamline note.
* If the node's group is now empty, the group is removed from the module.
* If the module is now empty, the module is removed from the network.

Both removals use **swap-remove**, `children[i] = children[-1]; children.pop()`
(`src/alluvial/AlluvialNode.ts:149-158`). `Network.removeChild` also deletes `modulesById[moduleId]`
(`src/alluvial/Network.ts:291-295`).

`add()` (`src/alluvial/LeafNode.ts:120-192`) does three things:

* It looks up `network.getModule(moduleId)`. If none exists it creates `new Module(network, moduleId, moduleLevel)`, which is
  **appended** to `network.children` with cached flow 0.
* It gets or creates the group, which is appended.
* It re-attaches the node to streamline nodes.

Consequences that the Python port must reproduce for parity. They fall out automatically if the Python tree
mirrors TS `update()` exactly. Each one was verified by running the bundled TS (see §11).

* **Q1 – single-leaf modules are re-created.** `setColor` on a module with exactly one leaf node
  removes the module, which moves the *last* module of `network.children` into its slot, and appends a
  **new Module object** at the end. The old object keeps `children == []`. The new one has flow 0 and is
  `isVisible == False` until the next `calcFlow`. `update()` is unconditional (`src/alluvial/LeafNode.ts:196-199`), so this
  happens whenever **any** op calls `update()` on the only leaf of a module. That includes a recolor with the *same* index,
  e.g. `colorModule` twice with one color, or `colorNodesInModule` touching a node whose color does not change. Multi-leaf modules
  survive `setColor`: the module still holds its other leaves while the first leaf is re-added.
* **Q2 – live-array iteration skips.** These ops iterate `network.children` with `forEach` while
  coloring:
  * the single-network branch of §6.1
  * `colorModuleIdsInAllNetworks` (§6.2, non-multilayer branch)
  * `colorByLayer` and `colorByPhysicalId` (§6.4)
  * the three metadata ops (§6.5)
  * `colorModuleIds` (§6.6)

  When Q1 fires at index `k`, the module formerly at the end is never visited (it is now at `k`), and the re-created module is visited again at the end.
  In practice this skips a **visible** module only when the network has no invisible modules. After a layout,
  `children == [...visible, ...invisible]` (`src/alluvial/Diagram.ts:210`), so normally the skipped tail module is invisible, and
  later swaps move invisible re-created modules (flow 0) around. In the single-network branch of §6.1, the re-created module is visited again
  and recolored with `scheme[n0 - 1]`. Only the last re-created module can sit at index `n0 - 1`.
  JS `forEach` snapshots the length at the start and reads `arr[i]` live. Because swap-remove plus append keeps the length,
  a Python `for i in range(n0): m = children[i]` reproduces it.
  Example (verified): one network, modules in order `[m1(2 leaves), m3(2), m2(1 leaf), m4(1 leaf)]`.
  After `colorMatchingModulesInAllNetworks` the indices are m1=0, m3=1, m2=**3**, m4=**-1 (never colored)**, and
  `highlightColors` = scheme[0..3].
* **Q3 – stale object references.** Ops that hold Module references across mutations (`B.links` in §6.1,
  `module.getLeafNodes()` after `module.setColor` in §6.3) see an emptied object after Q1.
  Its `isHighlighted` is False and its `getLeafNodes()` is `[]`.
* **Q4 – cached flow 0 makes re-created modules invisible** until `updateLayout()` runs `calcFlow`.
  Visibility filters inside the same op (`getSimilarModules`, `isVisible` checks) therefore skip them.

---

## 5. Module similarity (`Module.getSimilarModules`, `src/alluvial/Module.ts:321-366`)

> **Erratum (0.5, fix round WP6: S5).** The node distribution is a `Map` in TS and a plain dict in Python: identifiers
> keep insertion order (no JS object key order, `js_key_order` below no longer applies), and identifiers such as
> `constructor` or `__proto__` work.

```python
def get_similar_modules(self, side, num_modules=5, threshold=1e-6) -> list[(Module, float)]:
    this_nodes = node_distribution(self)  # dict identifier -> flow
    results = []  # (module, similarity)
    for module in connected_modules(self, side):  # order matters for ties
        if not module.is_visible:  # cached flow (Q4)
            continue
        other_nodes = node_distribution(module)
        ids = list(dict.fromkeys(js_key_order(this_nodes) + js_key_order(other_nodes)))  # union, Set order
        p = [this_nodes.get(i, 0.0) for i in ids]
        q = [other_nodes.get(i, 0.0) for i in ids]
        sim = 1 - js_div(p, q, normalize=True)
        if sim > threshold:  # NaN fails -> skipped
            results.append((module, sim))
    # PriorityQueue(num_modules, (a,b) => b.sim - a.sim) == stable top-k, first-inserted wins ties
    return sorted(results, key=lambda t: t[1], reverse=True)[:num_modules]
```

* `node_distribution(m)`: `for leaf in m.leafNodes(): d[leaf.identifier] = leaf.flow`. The **last
  write wins** for duplicate identifiers, which happens in name mode or when several states share an identifier. Leaf order
  follows `leafNodes()`: groups → `group.left` streamline nodes → leaves (`src/alluvial/HighlightGroup.ts:57-59`,
  `src/alluvial/AlluvialNode.ts:164-172`). `leaf.flow` is the visible flow (§1.1).
* `js_key_order(d)`: JS `Object.keys` order (`src/alluvial/Module.ts:333-337`). Keys that are canonical array
  indices (`str(int(k)) == k`, `0 <= int(k) <= 2**32 - 2`) come first in ascending numeric order, then the other keys
  in insertion order. In id mode, identifiers are `str(stateId ?? id)` (`src/parsers/set-identifiers.ts:9-20`),
  so the result is plain ascending numeric order. This only affects float summation order in `js_div`, and so only
  exact ties.
* `connected_modules(self, side)` (`src/alluvial/Module.ts:384-401`) iterates `for group in module.children`, then
  `for sn in (group.left if side == LEFT else group.right).children`, taking
  `m = sn.opposite.getAncestor(MODULE)`. It skips `sn.opposite is None` (dangling) and yields each `m.moduleId` once
  (first occurrence). Branch children order is whatever the last layout's in-place sort left
  (`src/alluvial/Diagram.ts:305-314`, see the layout note), modified by later mutations.
* PriorityQueue semantics (`src/utils/PriorityQueue.ts:24-35, 49-51`): it pushes while `len < n`, re-sorting stably.
  Once full, it accepts only if `cmp(value, last) < 0`, i.e. a strictly greater key. This is exactly
  `sorted(items, key, reverse=True)[:n]` in Python, because reverse sorting is stable. NaN never occurs because of the `>` threshold.
* Only invisible **candidate** modules are skipped. `self` is never checked for visibility.

`js_div` (`src/utils/entropy.ts:3-5, 18-53`, `src/utils/math.ts:1-8`). Keep the float op order:

```python
def _log2(x):
    return math.log2(x) if (x > 0 and math.isfinite(x)) else 0.0  # NaN/0/inf -> 0


def normalize(v):
    s = 0.0
    for x in v:
        s += x  # left-to-right reduce from 0
    return [x / s for x in v]  # s == 0 -> NaN (Python: guard ZeroDivisionError -> nan)


def kl_div(p, q):
    acc = 0.0
    for pi, qi in zip(p, q):
        acc += pi * _log2(pi / qi if qi != 0 else math.nan)  # JS 0/0=NaN, x/0=inf
    return acc


def js_div(p, q, normalize_=True):
    if normalize_:
        p, q = normalize(p), normalize(q)
    mix = [0.5 * (a + b) for a, b in zip(p, q)]
    jsd = 0.5 * (kl_div(p, mix) + kl_div(q, mix))
    if jsd < 0:
        raise ValueError("JSD should be non-negative")  # TS throws (entropy.ts:48-50)
    return min(max(jsd, 0.0), 1.0)  # JS clamp: NaN propagates -> similarity NaN -> rejected
```

Python's `min`/`max` propagate NaN only when NaN is the *first* argument, as written above. JS `Math.min`/`Math.max` always propagate it.
Do not reorder the arguments, or add an explicit `if jsd != jsd: return jsd`. A module whose leaves all have flow 0 yields NaN and is never matched. JS `x/0` gives `inf`
(log2 → 0 via the guard), and `0/0` gives NaN (→ 0). Python division by zero raises, so special-case it as shown.
`Math.log2` (V8/fdlibm) and `math.log2` (libm) can differ by 1 ulp. That only matters for exact ties.

---

## 6. Coloring operations (execution order, exact)

Every op ends with `update_layout()` = `diagram.calc_flow(); diagram.update_layout(opts)`
(`src/store/DiagramStore.ts:485-491`), unless noted. `scheme = state.selected_scheme`, `L = len(scheme)`.

### 6.0 `colorModule(module, color, updateLayout=True)` (`src/store/DiagramStore.ts:559-566`)

`module.set_color(get_highlight_index(color))`, then lay out if requested.

### 6.1 `colorMatchingModulesInAllNetworks()` — **v1 core** (`src/store/DiagramStore.ts:589-657`)

> **Erratum (0.5, fix round WP6: S1).** The counter is declared once, above the network-pair loop, in TS and Python
> (owner decision). The "counter reset per pair" below is the old behaviour: in the a/b/c example `b.2` and `c.1` now
> get `scheme[1]` (fixture `abc-chain__similarity`).

```python
def color_matching_modules_in_all_networks(diagram, state):
    networks = diagram.children
    if len(networks) == 0:
        return  # no layout either
    clear_colors(diagram, state, update_layout=False)  # Q1/Q4 can fire here on re-runs!
    if len(networks) < 2:
        ch = networks[0].children
        n0 = len(ch)
        for i in range(n0):  # JS forEach over LIVE array, incl. invisible modules (Q2)
            color_module(ch[i], scheme[i % L], update_layout=False)
        update_layout()
        return
    for i in range(len(networks) - 1):
        left_network = networks[i]
        links = {}  # BipartiteGraph: dict left -> dict right -> weight
        for module in list(left_network.children):  # ALL modules incl. invisible, current children order
            for match, sim in module.get_similar_modules(RIGHT, 1):  # at most one
                links.setdefault(module, {})[match] = sim
        counter = 0  # !!! reset per network pair (TS: `let highlightIndex = 0` inside loop)
        for left in links:  # == B.left: insertion order of left modules with a match
            if left.is_highlighted:  # colored as a "right" in pair i-1
                color = state.highlight_colors[left.highlight_index]
            else:
                right0 = next(iter(links[left]))  # the single match
                # reduce(... module.isHighlighted && max.flow < module.flow ...) with init flow=-inf:
                if right0.is_highlighted:  # flow >= 0 > -inf always
                    color = state.highlight_colors[right0.highlight_index]
                else:
                    color = scheme[counter % L]
                color_module(left, color, update_layout=False)
                counter += 1
            for right in links[left]:
                if not right.is_highlighted:
                    color_module(right, color, update_layout=False)
    update_layout()
```

Notes and edge cases, all from the cited lines:

* `BipartiteGraph` (`src/utils/BipartiteGraph.ts:16-31`) is two insertion-ordered Maps. `B.left` yields nodes
  with side 0 in first-insertion order. Left and right modules are from different networks, so no node changes
  side. A Python dict reproduces this.
* Left modules **without** a match (no visible connected module, or similarity ≤ 1e-6, or NaN) are not in `B`
  and stay as they are: gray in network 0, or whatever pair `i-1` gave them.
* **Many-to-one merges share color.** If left modules A and B both best-match right X, then A gets a new color and X takes it.
  B then sees `X.isHighlighted` and adopts X's color. B does not increment `counter` only if it is itself already
  highlighted; otherwise `counter` still increments even when the color was adopted.
  Exception (Q1/Q3): if X is single-leaf, it was re-created when A colored it. The `links` key is the stale object, so
  `isHighlighted == False`, B gets `scheme[counter % L]`, and `color_module(stale X)` is a no-op. It still calls
  `get_highlight_index(color)`, which is a no-op here because B already registered the color. This exception is **unreachable when identifiers are
  unique per network** (id mode): X's only identifier lives in exactly one left module, so only one left module can connect to X.
  It needs duplicate identifiers, as in name mode or multilayer-expanded.
* **Counter reset per pair.** Modules in network `i ≥ 1` that were not matched in pair `i-1` get
  `scheme[0], scheme[1], …` again and collide with colors already used. Verified (re-run):
  * `a = {1: n1,n2}`
  * `b = {1: n1,n2; 2: n3,n4}`
  * `c = {1: n3,n4; 2: n1,n2}`

  All **five** modules get index 0, and `highlightColors == [scheme[0]]`. `b.1` keeps its color without incrementing, then `b.2` takes
  `scheme[0]`.
* Real data, verified by re-running the bundled TS. Visible module indices per network, in layout order:
  * `science2001/03/05/07_2y.stree` with **id** identifiers (`setIdentifiers(..., "id")`): 6 distinct colors,
    `[0,0,0,1,2] [0,3,4,1,2] [0,4,0,1,2] [0,-1,5,-1,2]`. A second run gives the same result here.
  * The same files loaded the way the web app's **"Load example"** does it, i.e. **name** identifiers and network names `"2001"`…`"2007"`
    (`src/parsers/fetch-example-data.ts:17, 24-27`): 5 colors, `[0,1,2,3,4]` in all four networks.
  * `debug5_0/1.stree` (id): `[0,1] [1,0]`.

  Use these as smoke checks. The id-mode science result looks scrambled because state ids are not aligned across those files.
* **Not idempotent.** On a second press, `clearColors` re-creates the previously colored single-leaf modules (Q1),
  which become invisible (Q4) and can no longer be matched as right modules. Verified (re-run):
  `a = b = {1: n1,n2; 2: n3}` gives `1:0 2:1` in both networks on the first run, and `1:0 2:-1` on the second.
  Fixtures must call it **once on a freshly built diagram**.
* The single-network branch colors invisible modules too, and invisible ones come last, so visible
  modules get `scheme[i]` by layout position `i`. Q1/Q2 break this for single-leaf modules (example in §4: `m2` ends with
  `scheme[3]`, and `m4` is skipped because that network has no invisible modules).
* The order of `left_network.children` at that moment is the order after the last layout
  (`[...visibleSorted, ...invisible]`, `src/alluvial/Diagram.ts:210`), as perturbed by `clearColors` (re-runs) and by
  pair `i-1` coloring (Q1 swaps, appended re-created modules).

### 6.2 `colorModuleIdsInAllNetworks()` — v1 recommended (`src/store/DiagramStore.ts:735-793`)

This op does **not** clear first, so the registry keeps growing.

> **Erratum (0.5, fix round WP6: S3).** It now starts with `clearColors(false)` in TS and Python, and the multilayer
> branch groups modules in a `Map` (insertion order, no `js_key_order`).

```python
id_color = {}  # moduleId -> color, insertion ordered


def set_module_color(m):
    if m.module_id in id_color:
        color = id_color[m.module_id]
    else:
        color = scheme[len(id_color) % L]
        id_color[m.module_id] = color
    m.set_color(get_highlight_index(color))


first = networks[0].original_id if networks else None
if all(
    n.layer_id is not None and n.original_id == first for n in networks
):  # expanded multilayer; [] -> True
    by_id = {}  # JS object! key order = js_key_order (§5)
    for n in networks:
        for m in list(n.children):  # copy is fine: no mutation in this loop
            if m.is_visible:
                e = by_id.setdefault(m.module_id, {"flow": 0.0, "modules": []})
                e["flow"] += m.flow
                e["modules"].append(m)
    groups = [by_id[k] for k in js_key_order(by_id)]
    groups.sort(key=lambda e: e["flow"], reverse=True)  # stable
    for e in groups:
        for m in e["modules"]:
            set_module_color(m)
else:
    for n in networks:
        ch = n.children
        n0 = len(ch)
        for i in range(n0):  # live forEach (Q2)
            if ch[i].is_visible:
                set_module_color(ch[i])  # re-created modules are invisible (Q4)
update_layout()
```

This is only "consistent across networks" when module ids are aligned, as in multilayer or `--clu`-seeded runs.

### 6.3 `colorNodesInModulesInAllNetworks(networkId?)` — v1 recommended (`src/store/DiagramStore.ts:659-699`)

```python
clear_colors(update_layout=False)
src = diagram.get_network(
    network_id or networks[0].network_id
)  # UI passes selectedModule.networkId (Colors.tsx:143)
for i, module in enumerate([m for m in src.children if m.is_visible]):  # snapshot copy
    color = scheme[i % L]
    hi = get_highlight_index(color)
    module.set_color(hi)
    for net in networks:
        if net.network_id == module.network_id:
            continue
        leaves = module.get_leaf_nodes()  # AFTER set_color: [] if module was single-leaf (Q1/Q3)!
        touched = []
        for leaf in leaves:
            other = net.get_leaf_node(leaf.identifier)  # nodesByIdentifier map (Network.ts:323-325)
            if other:
                other.highlight_index = hi
                touched.append(other)
        for other in touched:
            other.update()  # set all, then update all
update_layout()
```

Verified: a single-leaf source module's nodes are **not** colored in the other networks.

### 6.4 `colorByLayer()` / `colorByPhysicalId()` — v2 (`src/store/DiagramStore.ts:795-847`)

These do not clear. The loop is `for net: for m in net.children (live forEach, Q2): if m.is_visible: for leaf in m.get_leaf_nodes()`.
The key is `leaf.layerId` (skipped if None) or `leaf.nodeId`. A new key gets `scheme[len(map) % L]`. Then
`leaf.highlight_index = get_highlight_index(color); leaf.update()`.

### 6.5 Metadata — v2 (`src/store/DiagramStore.ts:849-958`)

Each op calls `clearColors(false)`, then pre-registers the colors in the given order to fix index order (`:852-855`,
`:887-890`, `:930-933`). It then walks visible modules of networks with `haveMetadata` (since fix round WP6, E12: some
leaf has metadata, not only the first) and recolors leaves:

* categorical: string value in the map
* real: first bin with `x0 <= v < x1`; since fix round WP6 (S6) the last bin also takes `v == x1`
* intervals: `getColor(v)`

### 6.6 Single-target ops — v2 highlight API

These are:

* `colorMatchingModules(module, color, side?)`, which recurses greedily left and right along `getSimilarModules(side)[0]`
  and lays out only at the top call (`:568-587`). It does not check whether the match is already colored. Because of Q1/Q3, the chain
  **stops at the first single-leaf module**: after `setColor` the object is stale with no groups, so its `connectedModules` is empty.
  A chain started on a single-leaf module colors only that module.
* `colorModuleIds(module, color)` (`:717-733`)
* `colorNodesInModule` (`:659-680`)
* `colorSelectedNodes(nodes, color)` (`:701-715`)
* `getHighlightColor` (`:314-323`, not used in rendering)

---

## 7. Rendering spec (SVG → matplotlib)

### 7.1 Coordinates and canvas

* Layout coordinates are **SVG pixels, y pointing down**. Diagram bbox is `[0, diagram.width] × [0, height]`. Modules
  stack upward from `y = height` (`src/alluvial/Diagram.ts:364, 369`, layout note). In matplotlib, use data units =
  px and `ax.invert_yaxis()`, then draw TS coordinates verbatim.
* Recommended scale: 1 px = 1 pt, so `figsize = (W/72, H/72)` and font sizes in px equal matplotlib points.
  `dpi` then sets raster resolution only.
* The web view translates the diagram by `x = max((viewW - diagram.width)/2, minMargin) + offsetX` and
  `y = max((viewH - diagram.height)/(2 if centerVertically else 3), minMargin) + offsetY`, with defaults `minMargin = 100`,
  `centerVertically = False` and offsets 0 (`src/react/Diagram.tsx:42-51, 102-107`). The web app passes `offsetX = -drawerWidth/2`
  (`apps/web/src/components/App.tsx:88-92`). None of this matters for static output.
* SVG export (`src/utils/save-svg.ts:17-90`) starts from `diagram.width + 10` by `diagram.height + 10`. If **any** `.label`
  element exists (network name, module name or module id), it adds `2*(maxLabelWidth + 20)` to the width and `80` to the height, and shifts the content by
  `maxLabelWidth + 15` in x. There is no y shift. `maxLabelWidth` is the largest `getBBox().width` over all label `<text>`s and their tspans,
  so it includes network names. In diagram coordinates the export window with labels is therefore
  `x ∈ [-(maxLabelW + 15), diagram.width + maxLabelW + 35]` and `y ∈ [0, height + 90]`. Without labels it is `[0, W + 10] × [0, H + 10]`.
  In matplotlib, set these limits (y inverted), or use `bbox_inches="tight"`.
* Background: white rect `#fff` (`src/react/Diagram.tsx:127`).

### 7.2 Draw order (z-order), from `src/react/Diagram.tsx:135-138` and `src/react/Network.tsx:29-64`

```
for network in diagram.children:                         # left to right
    network name label                                   (if showNetworkNames)
    for module in modules_to_draw(network):              # v1: network.visibleChildren order (see below)
        group rects, in module.children order            # bottom group first
        module-id label                                  (if showModuleId)
        module name label                                (if showModuleNames and textAnchor != null)
    for link in network.getLinks(streamlineThreshold):   # right-side streamlines of this network
        streamline path
selected-module outline                                  (UI only; skip in Python)
```

* `modules_to_draw`: with the default `hierarchicalModules = "shadow"`, `network.hierarchicalChildren` is used
  (`src/react/ModulesWrapper.tsx:23-26`). In v1 (all modules at level 1) the breadth-first walk
  (`src/alluvial/Network.ts:212-245, 402-415`) yields exactly the visible modules in `network.children` order and
  no super-module shapes. This is the same as `visibleChildren` (`:208-210`).
* Matplotlib: assign a strictly increasing `zorder` per artist in this sequence, or add artists in this order with equal zorder.
  Mixing `imshow` (gradients) with patches makes explicit zorder safer.

### 7.3 Modules

* Each highlight group is one rect at `group.layout` = `(x, y, width=moduleWidth, height)`, with fill
  `fill(group.highlightIndex, group.insignificant)` (§2.3), **no stroke** (CSS `g.module {stroke-width: 0}`,
  `src/react/Diagram.css:9-12`) and full opacity (`src/react/Module.tsx:85-96`).
* Hover stroke `#128bc2` (`src/react/Diagram.css:14-17`) and the double-click shake animation are UI only.
* Drop shadow (`dropShadow`, default False, `src/store/DiagramStore.ts:109`; filters `src/react/DropShadows.tsx:5-39`):
  `feDropShadow dx = dy = 1.5 + 0.2*moduleLevel, stdDeviation = 1 + 0.1*moduleLevel, floodOpacity 0.5` (black flood).
  In v1 these values are `1.7 / 1.1`. The filter sits on the `<g>` that wraps all group rects of a module (`src/react/Module.tsx:81-97`), so the shadow is
  cast by the whole module outline, not per group. Filters exist only for levels 1–3 (`maxDropShadowModuleLevel = 3`,
  `src/react/Diagram.tsx:100, 125`), so deeper modules reference a missing filter. This is optional. A matplotlib approximation is
  `patheffects.SimplePatchShadow(offset=(dx, -dy), alpha=0.5, shadow_rgbFace='k')` on one module-sized patch drawn under the groups (no blur).

### 7.4 Streamlines

* Set: `network.getLinks(streamlineThreshold)` (`src/alluvial/Network.ts:343-362`, `src/react/Network.tsx:25`):
  * Walk visible modules in `children` order, then groups, then `group.right` streamline nodes.
  * Skip nodes whose opposite module is invisible or that have no link (`src/alluvial/Module.ts:368-382`).
  * Keep `avgHeight > streamlineThreshold`, where `avgHeight = (h0 + h1)/2` (`src/alluvial/StreamlineLink.ts:78-80`) and the
    default threshold is `1` px (`src/store/DiagramStore.ts:87`).
  * **Stable sort** by `link.highlightIndex` ascending, then `avgHeight` descending. Link index is
    `max(leftGroup.highlightIndex, rightGroup.highlightIndex)` (`src/alluvial/StreamlineLink.ts:42-44`). The effect is that gray streamlines
    are drawn first (underneath) and thick before thin.
* Geometry: `_path` (`src/alluvial/StreamlineLink.ts:118-136`). The streamline note owns the numbers. The matplotlib
  mapping is:
  `MOVETO(x0, y0+h0)`, `CURVE4(cpx, y0+h0)(cpx, y1+h1)(x1, y1+h1)`, `LINETO(x1, y1)`,
  `CURVE4(cpx, y1)(cpx, y0)(x0, y0)`, `CLOSEPOLY`, with `cpx = (x0+x1)/2`. Set `y0` or `y1` to 0 when it is < 1e-6, before computing
  `y0+h0` and `y1+h1`.
* Fill: a horizontal `linearGradient` (`src/react/LinearGradients.tsx:23-55, 64-75`, `src/react/Streamline.tsx:18`):
  * Default SVG gradient units = path bounding box, and the path's x-extent is exactly `[x0, x1]`.
  * Left color `cL = fill(leftHI, leftInsig)`, right color `cR = fill(rightHI, rightInsig)`. Both come from the
    groups owning the two streamline nodes (`src/alluvial/StreamlineLink.ts:26-40`). A missing side defaults to `-1`/False.
  * With `t = (x - x0)/(x1 - x0)`, the color is `cL` for `t <= 0.15`, `cR` for `t >= 0.85`, and linear interpolation in
    **gamma-encoded sRGB** in between (SVG default `color-interpolation: sRGB`).
* Opacity: element `opacity = streamlineOpacity` (default 0.8, `src/store/DiagramStore.ts:88`;
  `src/react/Streamline.tsx:20`) on the whole path. There is no stroke.
* Matplotlib recipe:
  * If `cL == cR`, use `PathPatch(path, facecolor=cL, edgecolor='none', lw=0, alpha=0.8)`.
  * Otherwise add an invisible `PathPatch` as a clip path. Then `imshow` a 1×N RGBA strip (N≈256) with
    `extent=(x0, x1, ymax, ymin)`, `aspect='auto'`, `interpolation='bilinear'` and `alpha=0.8`, followed by
    `im.set_clip_path(patch)`.
  * Gradient only where colors differ. In the default gray diagram, everything is solid except insignificant ends.

### 7.5 Module name labels (`src/react/Module.tsx:135-164, 169-254`; `src/alluvial/Module.ts:45-106`)

* Shown only if `showModuleNames` (default True) **and** the module's network is the first or the last network:
  * first network (`isFirstChild`, also when there is a single network): anchor `"end"` at `x = module.x - 20`
  * last network: anchor `"start"` at `x = module.x + moduleWidth + 20`
  * middle networks: no label (`textAnchor` null)

  In every case `y = module.y + module.height/2`, and the vertical alignment is `dominant-baseline: middle`
  (`src/alluvial/Module.ts:82-106`, `src/alluvial/AlluvialNode.ts:112-122`). The 20 is `width 15 + padding 5`.
* Text: `module.name` if it is non-empty, which happens only after a user rename (`src/store/DiagramStore.ts:402-405`; Module ctor
  never sets it, `src/alluvial/Module.ts:18-43`). Otherwise the largest leaf names (below).
* Font size: `fs = 1 + js_round(min(fontSize, module.height))` if `adaptiveFontSize` else `fontSize`.
  Defaults are `fontSize = 8`, `adaptiveFontSize = False` (`src/react/Module.tsx:63-68`, `src/store/DiagramStore.ts:110-112`).
* Color: `#000`, or `#f00` if the module is selected (UI only). In multi-line mode, each line's tspan overrides this
  with `fill_text(node.highlightIndex, node.insignificant)` = `make_fill("#000", highlightColors)`, so
  gray-default nodes are black and colored nodes take their color (`src/react/Module.tsx:74, 147, 233, 247`).
* `getLargestLeafNodes(n, aggregate)` (`src/alluvial/Module.ts:45-72`):
  * `aggregate=False`: candidates are `module.leafNodes()` in iteration order (§5).
  * `aggregate=True` (default `aggregateStateNames=True`, `src/store/DiagramStore.ts:102`): candidates are a dict keyed by
    `nodeId` in first-seen order. Each value is a **shallow copy of the first-seen leaf** with `flow = 0.0`, then
    `flow += leaf.flow` for every leaf with that nodeId, in iteration order. The JS object spread copies own fields only, so
    the copy keeps `name`, `nodeId`, `stateId`, `highlightIndex` (of the first state) but **`insignificant` is
    undefined (falsy)**. Aggregated labels are never brightened. Verified by re-run (`Object.hasOwn(copy, "insignificant") === false`).
    Aggregation runs for **every** network, not only state networks. With the default `aggregateStateNames = True`, label colors are
    therefore never brightened anywhere. A label line is gray-default → black, or colored → the plain palette color.
  * Top-n = `sorted(candidates, key=flow, reverse=True)[:n]`, which is stable: on equal flow the earlier candidate wins (§5 PriorityQueue).
* Name per node: `node.name`. For `.clu` input the parser sets `name = str(node.id)` (`src/parsers/set-identifiers.ts:48-53`), so
  labels show node ids. With `titleCaseModuleNames` (default False) the name is `titleCase(name.lower())` from
  `title-case@4.3.2` (small-word list etc., `node_modules/title-case/dist/index.js`). This is optional for v1. `str.title()` is
  **not** equivalent.
* Single-line (`multilineModuleNames=False`): `", ".join(names of top 5)`, one text element.
* Multi-line (default True, `src/store/DiagramStore.ts:100`; `src/react/Module.tsx:197-253`):

  ```python
  line_h = fs * 1.8
  max_lines = math.ceil(module.height / line_h)
  if max_lines == 0: no label
  if max_lines % 2 == 0: max_lines -= 1
  names = largest_leaf_nodes(max_lines, aggregate)
  mid = math.ceil(len(names) / 2)
  # tspans: names[mid-1] at dy=0, names[mid-2..0] each -1.2em, then names[mid] at +mid*1.2em, then +1.2em each.
  # Net effect: line k (0-based, largest first, top to bottom) at y_k = center_y + (k - (mid - 1)) * 1.2 * fs
  ```

  All lines share the anchor x (every tspan has `x=0` inside the translated group) and the `em` unit equals `fs` px. With an
  **even** number of names, which can only happen when there are fewer names than `max_lines`, the block is not centered: the line
  `names[mid-1]` sits on the center line and the extra line hangs below. With an odd count it is centered.
* Vertical alignment: `dominant-baseline="middle"` is set on the `<text>`. SVG 2 makes it inherited, so the tspans use it too. The
  `middle` baseline lies half the x-height above the alphabetic baseline. For a glyph-independent match in matplotlib, draw each line with
  `va='baseline'` at `y_k + 0.5 * x_height(fs)`. `va='center'` centers each string's own ink box, so lines with and without descenders would jitter.
  Use `ha={'end':'right','start':'left'}[anchor]`, `fontsize=fs`, and `color=` per line.

### 7.6 Module id label (optional; `showModuleId` default False, `src/react/Module.tsx:109-133`)

Position `(module.x + moduleWidth/2, module.y + module.height/2)` (`src/alluvial/Module.ts:108-114`). There is no
`dominant-baseline`, so the **alphabetic** baseline sits at `y + fs/3` (`dy`). In matplotlib, use `va='baseline'` at `y + fs/3` in y-down data
coordinates. Anchor middle, `fontWeight 600`, fill black (the default, since no fill is set), with a white halo `stroke hsla(0,0%,100%,0.8)`,
`strokeWidth = max(fs/5, 1)`, round joins, painted under the fill. Text is `module.moduleId`.
Matplotlib: `path_effects=[patheffects.withStroke(linewidth=max(fs/5, 1), foreground=(1, 1, 1, 0.8))]`. The stroke is centered on
the glyph outline in both SVG and matplotlib, and 1 px = 1 pt per §7.1.

### 7.7 Network names (`src/react/Network.tsx:33-52`; `src/alluvial/Network.ts:201-206`)

When `showNetworkNames` (default True) is set, `network.name` is drawn anchored middle at
`x = network.x + network.width/2` (`network.width = moduleWidth`, `src/alluvial/Diagram.ts:364`). The alphabetic baseline is at
`y = height + 20 + networkFontSize`: position `height + 15 + 5`, plus `dy = networkFontSize`. `networkFontSize` defaults to 10 and
is not adaptive. The name defaults to the **full file name incl. extension** (`src/parsers/parse-files.ts:155-156`), e.g.
`science2001_2y.stree` (verified). `createFile` spreads `...contents` **after** `name`, so a parsed object that carries its own `name`
overrides it. Text-format parses only have `nodes` and `higherOrder`, but JSON input and the web example loader do carry one: the loader passes
`{name: "2001", ...}` (`src/parsers/fetch-example-data.ts:24-27`). In matplotlib use `va='baseline'`.

### 7.8 Fonts and text color

* The library sets no `font-family`. In the web app, SVG text inherits
  `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, … sans-serif` at **font-weight 300**
  (`apps/web/src/index.css:1-10`). An exported SVG has no font-family, so viewers fall back to their default (often serif).
* Recommendation: matplotlib `family="sans-serif"`, `fontweight="light"` (configurable). The module id label uses weight 600.

### 7.9 Selected module (UI only)

On load, the web app selects the largest module of the first network (`src/store/DiagramStore.ts:228-231`) and draws a
1 px `#f00` outline (`src/react/SelectedModule.tsx:12-21`). Its label is red in single-line mode only. The export
clears the selection first (`apps/web/src/components/Sidebar/Export.tsx:14`), so Python should not draw it.

### 7.10 Hierarchical super-modules (v2; `src/react/HierarchicalModule.tsx`, `src/react/ModulesWrapper.tsx:36-56`)

These are drawn for non-leaf `TreeNode`s of `network.tree` (a breadth-first walk). The bbox is the union of their sub-modules
(`src/alluvial/Network.ts:433-453`). In the BFS order (`src/alluvial/Network.ts:402-415`) a super-module is yielded before the modules
nested in it, so its shape is painted underneath them. Modules of shallower subtrees can still come earlier.

* `"shadow"` (default): a rect at the TreeNode layout, translated by `(o, o)` with
  `o = hierarchicalModuleOffset(5) * (maxModuleLevel - moduleLevel)`, fill `defaultHighlightColor`, opacity 0.5. It is wrapped in
  `isolation: isolate; mix-blend-mode: difference`, which matplotlib cannot blend, so approximate it with an offset rect at alpha 0.5
  drawn before the modules.
* `"outline"`: the rect is grown by `o = 1 + 2.5*(maxModuleLevel - moduleLevel)` on every side, with `rx = o`, no fill, stroke
  `defaultHighlightColor`, width 2, dasharray `1,4`, round caps, and opacity 0.5.

---

## 8. Defaults relevant to this topic (`src/store/DiagramStore.ts:81-121`)

| Option | Default | | Option | Default |
|---|---|---|---|---|
| `defaultHighlightColor` | `#b6b69f` | | `showModuleNames` | `True` |
| scheme | `C3 Sinebow` (512) | | `multilineModuleNames` | `True` |
| `streamlineOpacity` | `0.8` | | `aggregateStateNames` | `True` |
| `streamlineThreshold` | `1` (px, strict `>`) | | `titleCaseModuleNames` | `False` |
| `fontSize` | `8` | | `showModuleId` | `False` |
| `networkFontSize` | `10` | | `showNetworkNames` | `True` |
| `adaptiveFontSize` | `False` | | `dropShadow` | `False` |
| `hierarchicalModules` | `"shadow"` | | `hierarchicalModuleOffset` / `Opacity` | `5` / `0.5` |
| gradient stops | `15%` / `85%` | | brighter factor (insignificant) | `0.8` |

The geometry defaults the renderer also needs belong to the layout note: `height 600`, `moduleWidth 80`, `streamlineFraction 2`,
`flowThreshold 5e-3` and `marginExponent 4` (`src/store/DiagramStore.ts:81-89`). The web app uses the package defaults unchanged
(`apps/web/src/store/Store.ts:4-6`).

---

## 9. Recommendation for v1 "consistent module colors across networks"

1. **Engine default: no coloring.** All nodes keep `highlightIndex = -1` and are drawn in `#b6b69f`. This matches the
   web app's load state, so layout fixtures are independent of coloring.
2. **Plot-level default: `colors="similarity"`.** It runs an exact port of `colorMatchingModulesInAllNetworks` (§6.1)
   **once on the freshly built diagram** with C3 Sinebow, then re-runs layout. This is what a web-app user gets from
   "By similarity → Paint all", so outputs can be compared one-to-one against TS fixtures. The function itself must
   still call `clear_colors` first, for parity.
3. Offer `colors="module_id"` (§6.2), `colors="nodes"` (§6.3, source network 0), `colors=None`, and
   `colors={module or identifier: color}` (custom, routed through `get_highlight_index` and `set_color`).
4. Port the quirks Q1–Q4 faithfully by mirroring `LeafNode.update()` (swap-remove, append, cached flow). Do **not**
   special-case them. Expose a non-parity "clean" mode only after the open question below is answered.
5. The op mutates the tree and changes geometry (groups and streamline nodes split by color), and it is **not idempotent** (§6.1).
   `plot()` must therefore not re-run it on a diagram that is already colored. Record the applied op on the `Diagram`, e.g.
   `diagram.coloring = "similarity"`, and skip it or raise when it is requested again. Alternatively, color a freshly built diagram.
6. Matching quality depends on the identifier mode. Similarity coloring of the science example is only meaningful with name
   identifiers (§6.1 smoke checks; open question 10).

---

## 10. Python port guidance

Suggested modules:

```
alluvial/colors/
    palettes.py      # load data/c3-sinebow-512.json -> C3_SINEBOW (strings, TS form); DEFAULT_GRAY="#b6b69f"
    css.py           # parse(), js_round(), brighter() (§2.4), to_mpl_rgba()
    registry.py      # ColorState(default_highlight_color, highlight_colors, scheme); get_highlight_index; make_fill
    similarity.py    # js_key_order, normalize, kl_div, js_div, get_similar_modules (or a Module method)
    ops.py           # clear_colors, color_module, color_matching_modules_in_all_networks,
                     # color_module_ids_in_all_networks, color_nodes_in_modules_in_all_networks  (+v2 ops)
alluvial/render/mpl.py
    draw(diagram, ax=None, *, state, opts) -> Axes   # §7, z-order §7.2, gradients §7.4, labels §7.5-7.7
```

* `ColorState` is the Python counterpart of the color fields of `DiagramStore`. Keep it on the `Diagram` object
  (or alongside it) because every op needs both. Every op calls `diagram.calc_flow(); diagram.update_layout(opts)` at the end,
  as in TS.
* Colour fixtures exist: `tests/fixtures/*__colored.json`, `*__nameColored.json` and the `planted-ftree__color*` extras,
  generated by `tools/ts-fixtures/` with exactly `store.setNetworks(files); store.<op>()`. They contain `highlightColors`,
  per-module `highlightIndex`, per-group `[highlightIndex, insignificant, rects]`, per-link left/right indices and
  insignificance, and the path. They also contain the per-network `leaves` table (identifier → highlightIndex), which is
  the most direct check of the op itself. Smoke values from §6.1 reproduce in them: debug5 `[0,1] [1,0]`, and science
  name mode `[0,1,2,3,4]` ×4.

Pitfalls:

1. **Rounding**: JS `Math.round` rounds half up (`floor(x+0.5)`), unlike Python `round` (banker's rounding). This affects `brighter`
   channels and adaptive font size.
2. **NaN**: JS `Math.min`/`Math.max` always propagate NaN. Python's `min`/`max` do so only when NaN is the first argument, and Python raises on `/0`. Mirror `js_div` exactly (§5).
3. **Iteration over mutating lists**: `forEach` snapshots the length, while `for…of` and Python `for` re-check it. Both read live elements.
   Use index loops with a captured `n0` where TS uses `forEach` over `network.children` (§4 Q2).
4. **Ordering**: `Map`, `Set` and object literals are insertion ordered (use `dict`), except that JS objects put
   integer-like keys first in ascending order (`js_key_order`, §5 and §6.2). `Array.prototype.sort` is stable, and so is
   Python's `sorted(..., reverse=True)`. Comparator `b - a` maps to `key, reverse=True`.
5. **Cached flows**: `Module.flow` and `HighlightGroup.flow` are only refreshed by `calc_flow()`. Do not turn them into
   computed properties, or Q4 and `largestGroup` behavior will change.
6. **Object identity**: keep the stale-object semantics (Q3). `links` keys are object identities. Use plain object
   `__hash__`/`__eq__` (identity), not `module_id`.
7. **Aggregated label copies** must drop `insignificant`. Treat it as False.
8. **Color strings**: keep TS strings in the registry for exact equality semantics, and convert to RGBA only in the renderer
   (`matplotlib.colors.to_rgba` accepts `#hex`. For `rgb(r, g, b)` use `parse()/255`).
9. **y axis**: TS geometry is y-down. Invert the axis rather than flipping coordinates, so fixture numbers stay identical.
10. **Gradients**: implement them only for `cL != cR`. Interpolate in sRGB (gamma-encoded) 0–255 space, between stops 0.15 and 0.85.

---

## 11. How the claims were verified

The TS store was bundled **outside the TS repo** with rolldown's JS API. The input is `src/store/DiagramStore.ts`, plus a
scratch entry re-exporting `parse` from `@mapequation/infomap-parser`, `setIdentifiers` and `createFile`. The bundle was
written to a scratch directory and run with node 24. `git status` in the TS repo was unchanged afterwards.

```js
const { build } = await import("/…/web/alluvial/node_modules/rolldown/dist/index.mjs");
await build({ input: "/scratch/entry.ts", platform: "node", write: true,
              output: { file: "/scratch/full.bundle.mjs", format: "esm" } });
// then: const B = await import("/scratch/full.bundle.mjs");
// const parsed = B.parse(text, undefined, true, false); B.setIdentifiers(parsed.nodes, "stree", "id");
// const file = B.createFile({ name, size: 0, lastModified: 0 }, "stree", parsed);
// const s = new B.DiagramStore(); s.setNetworks([...files]); s.colorMatchingModulesInAllNetworks();
```

Verified results: Q1/Q2 single-network skip (§4), Q3 in `colorNodesInModulesInAllNetworks` (§6.3), the counter reset
and the many-to-one merge (§6.1), non-idempotence (§6.1), aggregated labels with `insignificant === undefined` (§7.5),
the science/debug5 smoke results (§6.1), and `brighter()` (549/549 matches).

An adversarial review re-derived every claim from the cited sources and re-ran the following with a fresh rolldown bundle in a scratch directory.
`git status` in the TS repo was unchanged afterwards.

* `c3-sinebow-512.json` equals the `c3.colors(...)` output: 512 entries, 490 unique, first repeat 390 = 326, 22 repeats.
* `hsl-brighter-0.8-ref.json` matches `d3-color` 3.1.0, and the §2.4 Python matches it 549/549.
* `d3.hsl(undefined).brighter(0.8) == "rgb(0, 0, 0)"`.
* The Q2 example, the counter-reset example and the non-idempotence example.
* `colorNodesInModulesInAllNetworks` with a single-leaf source, and `colorModuleIdsInAllNetworks` on the same input.
* The science id-mode and name-mode results, and the debug5 result.
* The aggregated label copy.
* The default network name.

---

## 12. Open questions

1. **Fix or mirror the TS quirks by default?** The counter reset per pair (colors reused across unrelated chains),
   Q1–Q3 (single-leaf modules skipped or left gray) and non-idempotent re-runs look like bugs. This note recommends mirroring them
   for parity. Should the TS be fixed upstream, and should Python offer `strict=False`, e.g. a global counter, no re-creation
   of single-leaf modules, and recomputing flow before matching?
2. Should the high-level `plot()` default to similarity coloring (recommended) or gray (web-app load state)?
3. Default palette: keep C3 Sinebow for web parity, or default to a matplotlib-native qualitative map?
4. ~~Insignificance from `infomap.Infomap` objects~~ **Resolved: there is no source.** In infomap 2.15.1, no attribute of `Infomap`,
   `InfoNode` or `InfomapIterator`, and no line of the module source, contains "signif" or "boot". Readers of `Infomap` objects must
   set every node significant. Only file readers can carry it: path strings ending in `';'` (§1.1). The JSON path in TS loses it as well,
   because `setIdentifiers` converts string paths to arrays for `json` (`src/parsers/set-identifiers.ts:36-43`).
   Still open: does any current Infomap writer emit `';'` paths? The repo's `debug5_*.stree` files do, but only at deeper levels, so at module level 1 they are
   significant.
5. Font: mimic the in-app look (system sans-serif, weight 300) or the exported-SVG look (renderer default font)?
6. Out-of-range `highlightIndex` (input indices without colors): TS renders black, and this note proposes gray plus a warning. Is that acceptable?
7. `title-case@4.3.2` port: is it needed in v1, or can `titleCaseModuleNames` be deferred?
8. In `getSimilarModules`, duplicate identifiers within one module (name mode, or multilayer with physical ids) take the last write
   and are not summed. Keep this, or sum flows?
9. Label baseline: the `x_height` used to emulate `dominant-baseline: middle` (§7.5) depends on the font. Measure it from the matplotlib
   font, or use a constant such as `0.5*fs`? This was not checked against a browser rendering, and neither was the claim that the
   browsers in use treat `dominant-baseline` as inherited by tspans.
10. ~~Default identifier mode for the Python readers~~ **Resolved** (parsers note §5): `identifier="id"`, the store
    default and the fixtures' `default` variants. `"name"` is opt-in. Coloring results differ completely between the two
    (§6.1 smoke checks), so the docs for `colors="similarity"` should point users with stable node names to `"name"`.
11. Mixed `colors` array/`true` inputs (§2.5) are broken in TS. Is it acceptable that Python fixes them silently, since it is unreachable from the app's own files?
