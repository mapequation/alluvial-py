# Port note (v2): highlight and colour operations

Topic owner: every `DiagramStore` colour/highlight operation that v1 did not port, the colour-registry management
around them, how insignificant groups interact with colouring, how the web app's colour UI maps onto
`highlightIndex`, and how design.md's `layout(..., highlight=...)` maps onto these operations with exact TS parity.

Citation prefix: `src/…` is `web/alluvial/packages/alluvial-diagram/src/…` (read-only), `apps/web/…` is
`web/alluvial/apps/web/src/…`. `S:` is short for `src/store/DiagramStore.ts`. Python paths are relative to `alluvial-py/`.

Prerequisite reading: [`colors-render.md`](colors-render.md) §1 (data model), §2.1-2.3 (registry, `clearColors`, fill),
§4 (the mutation primitive and its quirks Q1-Q4) and §6 (the v1 ops). This note does not repeat them. It extends them.

> **Erratum (0.5, fix round WP5: E4, E5).** The single-leaf re-creation (colors-render Q1) is fixed in TS and Python:
> `LeafNode.remove()` keeps an emptied module when the leaf goes straight back into it (same `moduleId`), and the
> colour ops skip leaves whose `highlightIndex` already equals the target. Colour ops therefore never add, remove or
> reorder modules. The live-walk skip of §2.2, the chain stop of `colorMatchingModules` (§3), the missing propagation
> of `colorNodesInModule` from a single-leaf module and the `highlight=` "stay gray" warning (§7.4) are gone. The
> `hlskip-tree__*` fixtures now pin the fixed behaviour (every labelled node coloured, chains run through single-leaf
> modules). `_visible_leaf_walk` is a plain loop. The text below describes the pre-0.5 behaviour.

---

## 0. Summary

* All colouring goes through one primitive: `leaf.highlightIndex = k; leaf.update()` (remove plus re-add, colors-render §4).
  The v2 ops differ only in **which leaves** they visit, **in what order**, whether they **clear first**, and how they
  **register colours** (`getHighlightIndex`, first-use order).
* Five of the v2 ops (`colorByLayer`, `colorByPhysicalId` and the three metadata ops) share one walk, the **visible-module
  leaf walk** (§2). It iterates `network.children` live, so a single-leaf module that gets re-created (Q1) can hide one
  visible module from the walk (until fix round WP5, §2.2).
* `colorSelectedNodes` (the node-list "paint selected nodes" action) walks a **node list**, not modules. It has no skip,
  but it propagates every node to the other networks by identifier (`getLeafNode`, last registration wins).
* **Recommendation for `highlight=`** (§7): implement it as the real TS op `colorCategoricalMetadata(KEY, Map(label → colour))`
  after writing each leaf's label into `leaf.metadata[KEY]`. This is exactly what the web app does when a user loads
  networks whose nodes carry a categorical metadata field and presses "Paint current colors". It gives each label one
  highlight index in mapping order, and it covers both the mapping form and the callable form with one code path.
  It inherited the §2.2 skip, which Python detected and warned about, until fix round WP5 removed both. The alternatives and their trade-offs are in Open question 1.
* The web app has **no legend**. Highlight indices are just "the k-th distinct colour string painted since the last
  clear". A legend is a Python addition and needs the label → index map recorded at op time (§7.5).

---

## 1. What the Python port already has, and what is missing

**Update 2026-10-10: everything in the "Missing" table below is implemented** (`engine/store.py`, `geometry.py`,
`layout(highlight=..., highlight_colors=...)`, `mpl.draw(legend=..., label_colors=...)`, `alluvial.legend`), and every
§8 fixture replays bit-exactly. `checkColors` (JSON `colors`) is still not ported. The tables keep the pre-v2 state
for reference.

Present in `src/alluvial/engine` (v1, fixture-verified):

| TS | Python | Notes |
|---|---|---|
| `getHighlightIndex` (S:296-312) | `DiagramStore.get_highlight_index` | appends in place; TS assigns a copied array (`[...colors]`), which has no observable effect |
| `colorModule` (S:559-566) | `color_module` | |
| `colorMatchingModulesInAllNetworks` (S:589-657) | `color_matching_modules_in_all_networks` | |
| `colorNodesInModule` (S:659-680) | `color_nodes_in_module` | ported as the helper of the next row; no fixture calls it directly |
| `colorNodesInModulesInAllNetworks` (S:682-699) | `color_nodes_in_modules_in_all_networks` | |
| `colorModuleIdsInAllNetworks` (S:735-793) | `color_module_ids_in_all_networks` | |
| `clearColors` (S:960-977) | `clear_colors` | |
| ctor `highlightColors = [...selectedScheme]` (S:137) | `__init__` copies the scheme | 512 entries until `set_networks` resets the list to `[]` |
| `Module.setColor/removeColors`, `LeafNode.update`, `Network.getLeafNode`, `haveMetadata`, `isMultilayer`, `isHigherOrder` | `engine/module.py`, `leaf_node.py`, `network.py` | `LeafNode.metadata`, `layer_id`, `node_id`, `network_id` are stored |
| `sortModulesBy: "highlightIndex"` (`src/alluvial/Diagram.ts:401-402`) | `sort_modules_by="highlight_index"` | fixture `planted-ftree__coloredSortHighlightIndex` |
| `getLargestLeafNodes(n, aggregate)` | `Module.get_largest_leaf_nodes` | the aggregated copies carry `highlight_index` but no `insignificant`, as in TS |

Missing (this note specifies them):

| TS | Section | Needed for |
|---|---|---|
| `colorSelectedNodes(nodes, color)` (S:701-715) | §3.1 | parity of the node-list UI; alternative highlight vehicle |
| `colorMatchingModules(module, color, side?)` (S:568-587) | §3.2 | single-module "by similarity" |
| `colorModuleIds(module, color)` (S:717-733) | §3.3 | single-module "by module id" |
| `colorByLayer()` (S:795-821), `colorByPhysicalId()` (S:823-847) | §3.4 | design.md `colors="layer" \| "physical_id"` |
| `colorCategoricalMetadata(name, colors)` (S:849-882) | §3.5 | metadata colouring; **the `highlight=` vehicle** |
| `colorRealMetadata(name, bins)` (S:884-920), `colorRealIntervals(name, data, getColor, centers)` (S:922-958) | §3.6 | metadata colouring (numeric) |
| `setHighlightColors` (S:292-294), `setDefaultHighlightColor` (S:288-290), `setSelectedScheme` (S:236-239), `getHighlightColor` (S:314-323), `checkColors` (S:180-210) | §4 | registry management |
| `DiagramStore.apply` records for all of the above | §8 | fixture replay |
| geometry: label-name highlight indices, `highlight_labels`; `draw(legend=)` | §5.3, §7.5 | rendering highlighted label lines; legend |

`checkColors` (input `colors` / per-node `color`) is specified in colors-render §2.5. It matters only for JSON input, which is
the v2 IO note's topic.

---

## 2. The visible-module leaf walk (shared by five ops)

### 2.1 Definition

`colorByLayer` (S:798-817), `colorByPhysicalId` (S:826-843), `colorCategoricalMetadata` (S:857-878),
`colorRealMetadata` (S:892-916) and `colorRealIntervals` (S:935-954) all iterate like this:

```python
def visible_leaf_walk(diagram, network_filter, visit):
    for network in diagram.children:  # networks are never removed by colouring
        if not network_filter(network):  # metadata ops: network.have_metadata; layer/physical: always True
            continue
        ch = network.children
        n0 = len(ch)  # JS forEach: length fixed at the start, ch[i] read live
        for i in range(n0):
            module = ch[i]
            if not module.is_visible:  # cached flow (Q4): re-created modules are invisible
                continue
            for leaf in module.get_leaf_nodes():  # snapshot list, getLeafNodes order (groups -> left sn -> leaves)
                visit(leaf)  # may do leaf.highlight_index = k; leaf.update()
```

`for (… of network)` iterators and `forEach` behave the same here, because swap-remove plus append keeps the length
constant (colors-render §4 Q2). A Python `for module in ch:` would also match (the list iterator reads `len` on every step),
but write `range(n0)` to make the intent explicit.

Inside one module, every leaf in the snapshot is visited even if the module object gets emptied. That cannot happen for
a multi-leaf module, because each leaf is re-added (to the same module, found again through `modulesById`) before the next one is removed.

### 2.2 The skip lemma (removed)

Before fix round WP5, a recolour re-created a single-leaf module (colors-render Q1), which swap-removed it while the walk
iterated `network.children` live, so the walk could skip the last visible module of a network without invisible
modules. E4 keeps the module, so `network.children` does not change during a walk and nothing is skipped. The lemma, its
verification (`p7`) and the Python detection are deleted. The `hlskip-tree` dataset (§8.2) stays as a regression test.

---

## 3. The operations, exactly

Every op ends with `store.updateLayout()` (S:485-491: returns early on an empty diagram, otherwise `calcFlow` + `updateLayout`),
unless noted. `scheme = selectedScheme`, `L = len(scheme)`. "Registers" means a `getHighlightIndex` call (first-use order,
exact string equality, the default colour maps to -1 without registering).

### 3.1 `colorSelectedNodes(nodes, color)` (S:701-715)

```python
def color_selected_nodes(self, nodes, color):
    hi = self.get_highlight_index(color)  # registers even when nodes == []
    for node in nodes:  # caller's order; no de-duplication
        node.highlight_index = hi
        node.update()
        for network in self.diagram.children:  # every network except the node's own
            if network.network_id == node.network_id:
                continue
            other = network.get_leaf_node(node.identifier)  # nodesByIdentifier: LAST registered leaf wins
            if other is None:
                continue
            other.highlight_index = hi
            other.update()  # immediately, not batched (unlike colorNodesInModule)
    self.update_layout()
```

* It does **not** clear, and it does **not** check visibility. It colours leaves of invisible modules too.
* Each node is updated, then its matches in the other networks, before the next node. That is unlike `colorNodesInModule`, which
  sets all the indices first and then updates them.
* If `nodes` holds leaves from several networks that share an identifier, the matching leaves are updated several times.
  Verified (`p1`, "both2"): the indices are the same, but there are extra remove/re-add cycles, which change the leaf and
  streamline-node order inside groups, and so the tie orders.
* Duplicate identifiers inside one network: only the leaf that `getLeafNode` returns is propagated to (verified, `p1` "dupB":
  the last node with identifier `x` in network B is coloured, the first is not). The selected leaf itself is
  always coloured, even when it is not the registered one.
* `color == defaultHighlightColor` gives `hi = -1`. That un-highlights the nodes, but still runs `update()` (Q1 can fire).
* Web app caller: `apps/web/src/components/NodeList/NodeList.tsx:107-111, 218-235`. The list is
  `selectedModule.getLeafNodes()` (memoised when the module is selected), filtered to the selected rows **in data order**
  (TanStack `getSelectedRowModel().flatRows`, which ignores the table sort).

### 3.2 `colorMatchingModules(module, color, side=None)` (S:568-587)

```python
def color_matching_modules(self, module, color, side=None):
    hi = self.get_highlight_index(color)
    module.set_color(hi)
    if side is None or side == LEFT:  # TS `!side || side === LEFT`; LEFT = -1, RIGHT = 1 (src/alluvial/Side.ts:3-4)
        left = module.get_similar_modules(LEFT)  # default numModules 5, threshold 1e-6; uses only [0]
        if left:
            self.color_matching_modules(left[0].module, color, LEFT)
    if side is None or side == RIGHT:
        right = module.get_similar_modules(RIGHT)
        if right:
            self.color_matching_modules(right[0].module, color, RIGHT)
    if side is None:
        self.update_layout()
```

* It never checks whether the match is already coloured, and it overwrites it. The recursion is one-directional per branch, so it terminates.
* **The chain stops at the first single-leaf module.** `set_color` re-creates that module (Q1), and the argument object is now stale
  with no groups, so its `getSimilarModules` is empty. A chain started on a single-leaf module colours only that module.
  Verified (`p5` "chainB2", `p8` "chain t1[1]"). A chain through one: `p8` "chain t2[1]" colours
  `hlskip_t2` module 2 and its best left match `hlskip_t1` module 3 (single leaf), then stops, so `hlskip_t0` stays gray.
* `getSimilarModules` skips invisible candidates (cached flow). The modules re-created earlier in the same chain are invisible.
* `get_similar_modules(side)` with the default `num_modules=5` returns the same element 0 as `num_modules=1`, because the top-k is
  stable. Call it with the default anyway, for literal parity.

### 3.3 `colorModuleIds(module, color)` (S:717-733)

```python
def color_module_ids(self, module, color):
    hi = self.get_highlight_index(color)
    module.set_color(hi)
    module_id = module.module_id  # read AFTER set_color; the stale object keeps its moduleId
    for network in [n for n in self.diagram.children if n.network_id != module.network_id]:
        ch = network.children
        for i in range(len(ch)):  # live forEach
            m = ch[i]
            if m.is_visible and m.module_id == module_id:
                m.set_color(hi)
    self.update_layout()
```

* Module ids are unique per network (`modulesById`), so at most one module per network matches. The live-iteration skip
  (§2.2) has no observable effect: the only module that a re-creation could hide is a different id.
* `module.network_id` of a stale object is still correct (the field is set at construction).
* Verified (`p5` "modIds", `p8` "modIds").

### 3.4 `colorByLayer()` / `colorByPhysicalId()` (S:795-821, 823-847)

```python
def _color_by_key(self, key):  # key(leaf) -> hashable or None (skip)
    key_color = {}  # JS Map, insertion order, SameValueZero keys
    def visit(leaf):
        k = key(leaf)
        if k is None:
            return  # colorByLayer: `node.layerId == null` (S:802)
        if k not in key_color:
            key_color[k] = self.selected_scheme[len(key_color) % L]
        leaf.highlight_index = self.get_highlight_index(key_color[k])
        leaf.update()  # unconditional, even if the index is unchanged
    visible_leaf_walk(self.diagram, lambda n: True, visit)
    self.update_layout()

color_by_layer = lambda self: self._color_by_key(lambda l: l.layer_id)
color_by_physical_id = lambda self: self._color_by_key(lambda l: l.node_id)  # never None
```

* They do **not** clear. Leaves that are not visited keep their colour, and the registry keeps growing.
  `colorByLayer` on a network without layer ids changes no index but still re-lays out (verified, `p2` "byLayerNone").
* The key → colour map is local to one call. The registry is not: a second call re-registers the same strings, so the indices stay the same.
* The colour index follows first-seen order in walk order (network → visible module in children order → `getLeafNodes` order),
  across networks.
* (Before fix round WP5) the §2.2 skip applied. Verified (`p2` "byPhys", and `p8` "phys"): network `A = 1{1,2} 2{3} 3{4}` (no invisible modules)
  leaves node 4 at `-1` in A, while B colours node 4 (`scheme[3]`). A second call gives the same result. When A has an invisible tail module, node 4 is coloured
  (`p2` "byPhysInv").
* Key equality: JS `Map` uses SameValueZero, so `NaN` equals `NaN` and `0` equals `-0`. A Python dict treats two different `float('nan')`
  objects as different keys. Normalise NaN keys to one sentinel if NaN ids can occur (the fuzzer emits NaN tokens only for flows).
* Web-app gating (UI only): "By layer id" is shown if any network `isMultilayer`, and "By physical id" if any `isHigherOrder`
  (`apps/web/components/Sidebar/Colors.tsx:181-226`). The store ops themselves have no guard.

### 3.5 `colorCategoricalMetadata(name, colors)` (S:849-882)

```python
def color_categorical_metadata(self, name, colors):  # colors: dict value -> colour string (JS Map order)
    self.clear_colors(False)  # registry -> [], all highlighted modules -> -1 (Q1 can fire here)
    for c in colors.values():  # pre-register in map order (the "FIXME" at S:852-855)
        self.get_highlight_index(c)  # a default-colour entry registers nothing
    def visit(leaf):
        md = leaf.metadata
        if md is None or name not in md or not isinstance(md[name], str):  # S:864-869
            return
        v = md[name]
        if v in colors:
            leaf.highlight_index = self.get_highlight_index(colors[v])  # already registered
            leaf.update()  # also for a default-colour category (index -1)
    visible_leaf_walk(self.diagram, lambda n: n.have_metadata, visit)
    self.update_layout()
```

* `network.haveMetadata` is `leafNodes().next().value.metadata != null` (`src/alluvial/Network.ts:108-110`). That is the **first leaf in
  tree order at call time**. If that leaf has no metadata, the whole network is skipped (verified, `p3` "noMetaB"). On a network
  with no leaves, TS throws a `TypeError` (`undefined.metadata`). The Python `Network.have_metadata` returns False there, so the metadata
  ops must raise explicitly (`TypeError`) to keep fuzz parity. **Erratum (fix round WP6, E12):** `haveMetadata` is now true when
  **some** leaf has metadata, and False for a network without leaves, in TS and Python; nothing raises.
* `!node.metadata` is a null check: `{}` is truthy in JS. Use `md is None` in Python, not `not md`. `name in md` in JS also sees
  prototype keys (`"toString"`), but those fail the `typeof === "string"` test, so plain dict membership is equivalent.
* **Index order equals map order**, including categories that match no leaf (verified, `p3` "order": `Map([b, a, zz])` gives
  `highlightColors == [blue, red, green]` with `green` unused). Two categories with the same colour string share one index
  (`p3` "shared"). A category mapped to the default colour gets `-1` and is still `update()`d (`p3` "default").
* (Before fix round WP5) the §2.2 skip applied. Verified (`p3` "cat", `p8` "cat"): on `hlskip`, node 4, labelled `"a"`, stays `-1` in every network without
  invisible modules.
* Web app caller: `apps/web/components/Sidebar/Metadata/Categorical.tsx:20-22, 51`. The map starts as
  `category → defaultHighlightColor` in `data.counts` order (count descending, `src/alluvial/Network.ts:192-195`). Clicking a bar
  sets that category's colour (Map position unchanged). So in the web app, the index order is the count order of the
  categories the user coloured.

### 3.6 `colorRealMetadata(name, bins)`, `colorRealIntervals(name, data, getColor, centers)` (S:884-920, 922-958)

These are the same as §3.5 (clear, pre-register, `have_metadata` filter, visible-leaf walk), except:

* the value test is `typeof === "number"`. In Python: `isinstance(v, (int, float)) and not isinstance(v, bool)`. NaN passes the test and then matches nothing.
* `colorRealMetadata`: pre-registers `bin.color` for each bin in order. A leaf takes the **first** bin with `x0 <= v < x1`, then
  `break`s. It is not updated if no bin matches. The UI's d3 bins make the last bin's `x1` the data max, so leaves **at the max
  get no colour**, unless a later bin covers them. Verified (`p6` "real": with a third overlapping bin `[0.5, 2)`, `v = 1` falls to it).
  **Erratum (fix round WP6, S6):** the last bin also takes `v == x1`, so the maximum gets the last colour.
* `colorRealIntervals`: pre-registers `getColor(c)` for `c in centers`. Every numeric leaf is then updated with
  `getHighlightIndex(getColor(v))`. A colour not produced by any centre is appended in walk order. `getColor` returning the default
  gives `-1`. `data` is unused. Verified (`p6` "intervals").
* UI callers: `apps/web/components/Sidebar/Metadata/Real.tsx:96-132` (quantize scale over `selectedScheme`, quartile intervals).

### 3.7 Ops already ported, for reference

`colorModule`, `colorNodesInModule`, `colorNodesInModulesInAllNetworks`, `colorModuleIdsInAllNetworks`,
`colorMatchingModulesInAllNetworks` and `clearColors` are in colors-render §6 and `engine/store.py`. Two v2-relevant
facts were re-verified:

* `colorNodesInModule` on a single-leaf module colours **only** that module. After `set_color` the object is stale, so
  `getLeafNodes()` is empty and nothing propagates (`p5` "nodesInSingle", `p8` "nodesIn single").
* `clearColors` touches only modules with a highlighted group, including insignificant ones. Leaves that are already `-1` are not updated.
  The registry becomes `[]`, so the next op numbers colours from 0 again.

---

## 4. Registry management

| TS | Semantics | Python |
|---|---|---|
| ctor (S:137) | `highlightColors = [...selectedScheme]` (512) | done |
| `setNetworks` → `checkColors` (S:180-210, 217-234) | `highlightColors = []`, or the input colours (colors-render §2.5) | done for `[]`; input colours are an IO-note topic |
| `getHighlightIndex(c)` (S:296-312) | default → -1; `includes` then `indexOf` (the same for strings and `undefined`); else append | done |
| `setHighlightColors(list)` (S:292-294) | replaces the registry. **It touches no leaf and runs no layout.** Existing indices now point at the new strings | add (trivial). Public use: recolour without changing the geometry. `draw(palette=)` already covers that at render time |
| `setDefaultHighlightColor(c)` (S:288-290) | changes the `-1` colour and the default test in `getHighlightIndex`. No layout | add; affects later `get_highlight_index` calls only |
| `setSelectedScheme(name)` (S:236-239) | changes the scheme for **later** ops. It does not recolour or reset the registry | add, accepting a list of strings. Named schemes need the 63 other `COLOR_SCHEMES` (colors-render §3, v2 optional) |
| `getHighlightColor(i, default?)` (S:314-323) | `i is None or i > len-1` → `None`; `i == -1` → `default ?? defaultHighlightColor`; else `highlightColors[i]`. **`i < -1` returns `None`** (JS negative index). Verified (`p5` "ghc") | add. UI only: node-list names (`apps/web/components/NodeList/Name.tsx:15`, default `"#000"`) |

"Custom colours" are any strings passed to `colorModule`, `colorSelectedNodes`, `colorMatchingModules` or the metadata maps. The registry
compares strings, so `"red"` and `"#ff0000"` get two indices. Python must keep the registry as the given strings. Normalising them (to hex, say)
would merge indices that TS keeps apart. Convert colours only when drawing.

---

## 5. Insignificant groups and colouring

### 5.1 Group keys and order

* A module's groups are keyed by `(highlightIndex, insignificant)` (`src/alluvial/Module.ts:204-210`). `insignificant` comes from the
  leaf's tree path at `moduleLevel - 1` (colors-render §1.1). Colouring changes only `highlightIndex`, so an insignificant leaf
  moves between insignificant groups: `i-1` → `i0` and so on.
* Pass-1 order (`src/alluvial/Diagram.ts:215-221`): significant first, then by index. Example (`p4`, a module with significant `1` and insignificant
  `2`, `5`, after colouring `2` and `1`): `[0, i-1, i0]`, with group ids `A_module1_group0`, `A_module1_groupi-1` and `A_module1_groupi0`.
* `clearColors` → `removeColors` sets insignificant leaves back to `-1`. They merge into the `i-1` group (`p4` "clear").
* `Module.highlightIndex` is the largest group by **cached** flow, with a strict `>`. Ties keep the first group in current children
  order, which after a layout is the `-1` group. Verified (`p4` "tie": two groups of flow 0.5 give module index `-1`). This index feeds
  `sortModulesBy: "highlightIndex"` (key `-highlightIndex`, descending, so gray sorts first, at the bottom) and `ModuleGeometry.highlight_index`.
* Streamline ends use the group's own `(highlightIndex, insignificant)` (`src/alluvial/StreamlineLink.ts:26-44`). The link's draw-order key
  is `max(left, right)`, and `getLinks` sorts ascending (`src/alluvial/Network.ts:343-351`). Highlighted streamlines are therefore drawn after gray ones,
  and higher indices are drawn on top.

### 5.2 Fill

The fill is `highlightColor(default, highlightColors)({highlightIndex, insignificant})` (`src/utils/highlight-color.ts:9-25`).
Insignificant groups and streamline ends get `d3.hsl(c).brighter(0.8)` of the label colour (Python: `palette.brighter`). A
legend should show the plain colour. The brighter variant means "insignificant member of that label", and the web app has no legend
entry for it (Open question 5).

### 5.3 Label-line colours (missing in the Python geometry)

The multi-line module labels colour each name with `highlightColor("#000", highlightColors)(node)`
(`src/react/Module.tsx:74, 233, 247`). Gray (`-1`) names are black, and highlighted names take the label colour. With the default
`aggregateStateNames = true`, the names are aggregated copies (`{...leaf, flow: 0}`), which keep the **first-seen state's**
`highlightIndex` and have **no** `insignificant` own property, so they are never brightened (colors-render §7.5). That is the main
visual cue of a highlight in the web app's labels. The Python `ModuleGeometry` carries only name strings, and `mpl.draw` draws them black.
Add `name_highlight_indices: tuple[int, ...]` (aligned with `name_candidates`, falling back to `largest_leaf_names`) and
`name_insignificant` (always False when aggregated). Then colour the label lines in `draw`. The fixtures do not record
per-name indices yet (§8.1).

---

## 6. How the web app's colour UI maps to `highlightIndex`

The web app has no legend. Every control below calls a store op with a **colour string**. The index is whatever
`getHighlightIndex` returns at paint time, so it is the order in which distinct colours were first painted since the last
clear or load.

| UI | Store call | Index effect |
|---|---|---|
| Swatches: the default colour plus `selectedScheme[0..20]` (`apps/web/components/Sidebar/Colors.tsx:49-66`); keys `1` = default, `2`-`9`, `0` = `scheme[0..8]` (`:20-35`) | sets the sidebar's current `color` only | none until painted |
| "Paint" / key `p` (`:26-27, 70-78`) | `colorModule(selectedModule, color)` | registers `color` |
| "Clear all" (`:79-86`) | `clearColors()` | registry `[]` |
| By similarity: "Paint modules" / "Paint all" (`:102-117`) | `colorMatchingModules(selectedModule, color)` / `colorMatchingModulesInAllNetworks()` | |
| By node assignments (`:131-146`) | `colorNodesInModule(selectedModule, color)` / `colorNodesInModulesInAllNetworks(selectedModule?.networkId)` | |
| By module id (`:160-175`) | `colorModuleIds(selectedModule, color)` / `colorModuleIdsInAllNetworks()` | |
| By layer id / By physical id (`:181-226`) | `colorByLayer()` / `colorByPhysicalId()` | |
| Node list swatches (`apps/web/components/NodeList/NodeList.tsx:218-235`) | `colorSelectedNodes(selectedRows, colour)` | |
| Metadata → Categorical "Paint current colors" (`.../Metadata/Categorical.tsx:51`) | `colorCategoricalMetadata(name, map)` | the map order sets the index order |
| Metadata → Real (`.../Metadata/Real.tsx:96-132, 173-179`) | `colorRealMetadata(name, hist)` / `colorRealIntervals(...)` | the bin or centre order sets the index order |
| Colour scheme select (`.../Sidebar/ColorSchemeSelect.tsx`) | `setSelectedScheme(name)` | affects later ops only |

Other readers of `highlightIndex` (display only): group and streamline fills (§5.2), label tspans (§5.3), the module tooltip bar plot
(`apps/web/components/Diagram/Tooltip/ModuleTooltip.jsx:34-40`, which uses `fillColor({highlightIndex})` and never brightens), and the
node-list name colour (`getHighlightColor(hi, "#000")`).

---

## 7. design.md `highlight=` → store ops (recommended mapping)

### 7.1 Vehicle

This is the recommendation (alternatives in Open question 1). `layout(..., highlight=H)` runs after `set_networks` and after the hierarchy ops
(`module_level` / `expand`, Open question 3), as the **only** colour op. It is mutually exclusive with `colors=`, as design.md says.

```python
KEY = "\x00alluvial.highlight"  # private metadata key; cannot collide with user metadata names


def apply_highlight(store, labels, colors, label_of_leaf):
    # labels: list of distinct label objects in index order; colors: list[str] aligned with labels
    # label_of_leaf(leaf) -> label index or None
    for network in store.diagram.children:  # order irrelevant: metadata is read only by colour ops
        for leaf in network.leaf_nodes():
            k = label_of_leaf(leaf)
            md = dict(leaf.metadata) if leaf.metadata is not None else {}
            md.pop(KEY, None)
            if k is not None:
                md[KEY] = str(k)  # TS requires typeof "string"; str(k) keeps distinct labels distinct
            leaf.metadata = md  # EVERY leaf gets a dict -> have_metadata is True for every non-empty network
    store.color_categorical_metadata(KEY, {str(k): colors[k] for k in range(len(labels))})
```

This is TS-exact by construction. It is `S:849-882` on a diagram whose leaves carry `metadata`, which is the state the web app
reaches when it loads nodes with a `metadata` field (`src/alluvial/LeafNode.ts:49`: `this.metadata = node.metadata`). Writing the dict onto the
leaves after the build gives the same result as putting it on the input nodes before the build (verified, `p3` "input" == "cat"), because nothing
but the metadata ops reads `metadata`.

### 7.2 The two input forms

* **Mapping** `{label: iterable of identifiers}`:
  * `labels = list(mapping)`, in mapping order.
  * Identifiers are compared with `leaf.identifier`, which is a string. Normalise the user's values:
    * a `str` as-is
    * an `int` or `float` (not `bool`) through `_jscompat` number→string (the same as `set_identifiers`, so `3` → `"3"`)
    * anything else: `TypeError`
  * `label_of_leaf(leaf)` is the index of the label whose set contains `leaf.identifier`. **Every** leaf with that identifier is labelled,
    in every network, including duplicates within a network. This differs from `colorSelectedNodes`, which picks the last registered leaf.
  * An identifier listed under two labels raises `ValueError` (Open question 2).
  * Identifiers found in no network raise a `UserWarning` with the count.
* **Callable** `f(node) -> label | None`:
  * It is evaluated once per leaf, before the op.
  * The order is network order, then input-node order (`NetworkFile.nodes`; map leaves back by building an id → leaf
    list during the build, or evaluate on the `NetworkFile` nodes and inject before the build, which is equivalent).
  * `labels` are the distinct non-None results in **first-appearance order**. They must be hashable.
  * `node` is a frozen public view, `alluvial.NodeInfo(network_index, network_id, identifier, id, state_id, layer_id, name, flow,
    path, metadata)`. Expose no engine objects.

### 7.3 Colours

* `colors[k]` is `highlight_colors[k]` if the user passes it (a list aligned with the labels, or a dict label → colour). Otherwise it is
  `store.selected_scheme[k % L]`, the C3 Sinebow strings, as the web app's swatches would give.
* Index of label k: `store.get_highlight_index(colors[k])`, recorded right after pre-registration. It equals `k` unless one of these holds:
  * two labels share a colour string: they share an index
  * a colour equals the default `#b6b69f`: the index is `-1`, so the label is drawn gray
  * there are more than 390 default-scheme labels: Sinebow index 390 equals 326 (colors-render §3), so they share
  * there are more than 512 default-scheme labels: the palette wraps around

  Warn in the first three cases. Never "fix" the registry.

### 7.4 Effects the user can see (all TS behaviour)

* Labels apply only to leaves of **visible** modules. Leaves in modules under `flow_threshold` stay `-1`. This is invisible in the
  picture: those modules are not drawn, and `getLinks` drops every link whose left or right module is invisible (streamlines §6).
  It shows only in `leaves` dumps and in later ops that read leaf indices.
* (Before fix round WP5: the §2.2 skip could leave the last module of a network without its labels, and Python warned.
  Both are gone.)
* Highlighting splits modules into coloured groups and re-orders streamlines (draw order by index, §5.1). The module order changes only with
  `sort_modules_by="highlight_index"`.
* Re-running is not needed. `layout()` always builds a fresh store.

### 7.5 Geometry and legend

* `AlluvialGeometry.highlight_labels: tuple[HighlightLabel, ...]` with `HighlightLabel(label: str, highlight_index: int, color: str)`,
  in label order. `label` is `str(label)` so the geometry stays serialisable. `color` is the registry string.
  * Labels that matched no visible leaf stay in the tuple: they are registered in TS too.
  * For `colors=` ops and for no colouring, the tuple is `()`.
* `palette` stays `tuple(store.highlight_colors)`. Pre-registration makes `palette[i]` the colour of every label whose index is `i`.
* `draw(..., legend=True)` / `alluvial.legend(ax)`: one patch per entry with `highlight_index >= 0`, in label order, coloured with the
  palette that `draw` uses (so `palette=` overrides apply), plus an optional "other" patch in the default colour.
* `to_dict` / `from_dict` round-trip `highlight_labels` and default it to `()` for v1 dicts.

### 7.6 Worked example (TS-verified, `p8` "cat")

`hlskip` dataset (§8.2), `highlight={"a": [3, 4], "b": [1]}`:
* `highlightColors == ["#ff0000", "#0000ff"]` (`highlight_colors=["#ff0000", "#0000ff"]`)
* leaves `t0`, `t1` and `t2`: `1=1 2=-1 3=0 4=0` (since fix round WP5; before, node 4 stayed -1 in t0 and t1
  because of the §2.2 skip)

---

## 8. Fixtures

### 8.1 Harness additions (existing fixtures stay byte-identical)

* **New `Op` kinds** in `scenarios.ts`, dispatched in `harness.ts` `applyOp`, recorded verbatim in `inputs.operations`:
  * `colorSelectedNodes {nodes: [{networkIndex, identifier}], color}`. Each entry resolves to
    `store.diagram.children[networkIndex].getLeafNode(identifier)` at op time, and the harness throws if it is missing.
  * `colorMatchingModules {networkIndex, moduleIndex, color, side?: -1 | 1}`
  * `colorModuleIds {networkIndex, moduleIndex, color}`
  * `colorNodesInModule {networkIndex, moduleIndex, color}`
  * `colorByLayer`, `colorByPhysicalId`
  * `colorCategoricalMetadata {name, colors: [[value, color], ...]}`, passed as a `new Map(colors)`
  * `colorRealMetadata {name, bins: [{x0, x1, color}]}`
  * `colorRealIntervals {name, breaks: [t1..tn-1], colors: [c0..cn-1], centers: [...]}`. The harness builds
    `getColor = v => colors[count of breaks <= v]` and passes `data = null`.
  * `setDefaultHighlightColor {color}`; `setSelectedScheme {name}` (only if Python ports the named schemes)

  `moduleIndex` refers to `children` order after the previous op, as today. `resolveOp` reduces it modulo the module count for fuzz.
* **`inputs.nodeMetadata`** (optional): one array per network, aligned with the parsed `file.nodes` order, of `object | null`. The harness
  assigns `file.nodes[i].metadata = nodeMetadata[n][i]` after `parseAcceptedFiles` and before `setNetworks`. The Python replay does
  the same on `NetworkFile.nodes`. Scenarios without it are unchanged.
* **`labelNameHighlight: true`** (per-scenario flag, off by default): add `highlightIndex` and `insignificant` (`null` when not an own
  property, i.e. aggregated) to every `label.names[*]` and `label.namesSingleLine[*]` record. It is opt-in, so the 132 existing files
  do not change. If the owner prefers one format, turn it on for all scenarios and regenerate all of them in one commit. That diff is
  additive only and needs `formatVersion` 2.
* The fuzzer (`fuzz/gen.py`) can then draw the new ops. `colorSelectedNodes` picks random `(networkIndex, identifier)` pairs, and the metadata ops
  need `nodeMetadata` with mixed string/number/missing values. The datasets and the harness must not change for the existing scenarios.

### 8.2 New dataset

`tests/data/hlskip_t{0,1,2}.tree` is hand-written, three networks. Node `i` is named `n<i>`. Rows are `path flow "name" node_id`:

```
# hlskip_t0.tree and hlskip_t1.tree (identical partitions)      # hlskip_t2.tree
1:1 0.3 "n1" 1                                                   1:1 0.3 "n1" 1
1:2 0.3 "n2" 2                                                   1:2 0.3 "n3" 3
2:1 0.25 "n3" 3                                                  2:1 0.2 "n2" 2
3:1 0.15 "n4" 4                                                  2:2 0.2 "n4" 4
```

In t0 and t1, all modules are visible, module 2 has a single leaf and is not last, and module 3 is last. So the §2.2 skip fires. Module 3 is
single-leaf as well, which covers the "last module is itself single-leaf" case after a swap. t2 has only multi-leaf modules.
Probes `p8` used exactly this data, as `NetworkFile`-like objects with array paths. Re-check the results with the real parser
when the scenarios are added. An optional `tests/data/mlayer_t{0,1}.stree` adds multilayer state networks with a `layer_id` column, for
`colorByLayer`. It can be hand-written (`# path flow name state_id node_id layer_id`), or seeded through `make_datasets.py`.

### 8.3 Proposed v2 scenarios (`<group>__<variant>`)

The colours are literal strings. `S[i]` means the C3 Sinebow string at index `i` (written out in the scenario). `n/m` means
`networkIndex/moduleIndex`.

| Scenario | Ops after `setNetworks` | Covers |
|---|---|---|
| `hlskip-tree__default` | none | v1 layout of the new dataset (must pass the v1 replay) |
| `hlskip-tree__colorSelectedNodes` | `colorSelectedNodes {[(0,"3"),(0,"1")], "#ff0000"}`; `colorSelectedNodes {[(0,"3")], "#ff0000"}`; `colorSelectedNodes {[(0,"1")], "#b6b69f"}` | propagation, same-colour re-paint (Q1 re-creation), erase with default |
| `planted-ftree__colorSelectedNodes` | `colorSelectedNodes` of the identifiers of `planted_t0` file nodes 0-11 from network 0, `S[0]`; then file nodes 0-5 of `planted_t2` from network 2, `S[1]`; then the first 4 of the first set from network 1, `"#b6b69f"` | real data, nodes absent in some networks, overrides |
| `planted-ftree__colorSelectedNodesMixed` | one call with `[(0,id), (1,id)]` for 3 shared ids, `S[0]` | double propagation (repeat updates) |
| `states-tree__nameColorSelectedNodes` | identifier `"name"`; `colorSelectedNodes` of 5 names from network 0, `S[2]` | duplicate identifiers: last-wins `getLeafNode` |
| `planted-ftree__colorMatchingModules` | `colorMatchingModules {1/0, S[0]}`; `colorMatchingModules {0/1, S[1], side: 1}`; `colorMatchingModules {2/1, S[2], side: -1}` | both-sided and one-sided chains, overwrite |
| `hlskip-tree__colorMatchingModulesSingle` | `colorMatchingModules {1/1, "#ff0000"}` | chain started on a single-leaf module colours only it |
| `hlskip-tree__colorMatchingModulesThrough` | `colorMatchingModules {2/1, "#ff0000"}` | chain stops after a single-leaf module (`p8` "chain t2[1]") |
| `planted-ftree__colorModuleIdsSingle` | `colorModuleIds {0/1, S[3]}` | |
| `hlskip-tree__colorModuleIdsSingle` | `colorModuleIds {0/1, "#ff0000"}` | stale source module's `moduleId` |
| `planted-ftree__colorNodesInModule` | `colorNodesInModule {1/0, S[0]}`; `colorNodesInModule {0/2, S[1]}` | |
| `hlskip-tree__colorNodesInModuleSingle` | `colorNodesInModule {0/1, "#ff0000"}` | no propagation from a single-leaf module |
| `states-tree__colorByPhysicalId` | `colorByPhysicalId` | several states per physical id |
| `hlskip-tree__colorByPhysicalId` | `colorByPhysicalId`; `colorByPhysicalId` | §2.2 skip, non-clearing re-run |
| `planted-ftree__colorByLayerNoop` | `colorModule {0/0, "#ff0000"}`; `colorByLayer` | no layer ids: colours kept, relayout |
| `mlayer-stree__colorByLayer` (optional dataset) | `colorByLayer` | layer colouring |
| `planted-ftree__categorical` | `nodeMetadata`: `{"c": ["a","b","c"][id % 3]}` for most nodes, `{"c": 7}` for some, `{}` for some; `colorCategoricalMetadata {"c", [["b",S[0]],["a",S[1]],["zz",S[2]],["c","#b6b69f"]]}` | index order equals map order, unused category, non-string skip, default category |
| `planted-ftree__categoricalNoMetaFirst` | as above, but network 1's first leaf in tree order (not file order) gets `metadata: null` | `haveMetadata` network skip |
| `hlskip-tree__categoricalSkip` | `nodeMetadata` labels `{"hl": "a"}` for ids 3 and 4, `{"hl": "b"}` for id 1, `{}` otherwise; `colorCategoricalMetadata {"hl", [["a","#ff0000"],["b","#0000ff"]]}` | **the `highlight=` path** with the §2.2 skip (§7.6) |
| `planted-ftree__highlight` | `nodeMetadata` from a 3-label mapping over identifiers (as §7.2 would build it, key `"\u0000alluvial.highlight"`, values `"0"`, `"1"`, `"2"`); `colorCategoricalMetadata` with `S[0..2]`; `labelNameHighlight: true` | `highlight=` on real data, label-name colours |
| `planted-ftree__highlightSortHighlightIndex` | the same, with `sortModulesBy: "highlightIndex"` | |
| `planted-ftree-single__highlight` | the same, single network | |
| `science-stree__nameHighlight` | identifier `"name"`; `highlight` of about 10 journal names in 2 labels; `labelNameHighlight: true` | many invisible modules, aggregated label names |
| `debug5-stree__expandHighlight` | `expand 0/0`; `expand 1/0`; highlight of 2 labels over all 5 nodes | insignificant highlighted groups (`i0`, `i1`), group order |
| `multilevel-tree__expandThenHighlight` / `__highlightThenExpand` | `expand 0/0` then highlight, and the reverse | op order matters (Open question 3) |
| `planted-ftree__highlightThenClear` | highlight; `clearColors` | registry reset, insignificant-free clear |
| `planted-ftree__realMetadata` | `nodeMetadata` `{"x": id / maxId}`; `colorRealMetadata {"x", 4 equal bins over [0, 1] with S[0..3]}` | `x == 1` uncoloured (last bin `<`) |
| `planted-ftree__realIntervals` | the same metadata; `colorRealIntervals {"x", breaks [0.25, 0.5, 0.75], colors [S[0], "#b6b69f", S[1], S[2]], centers [0.875, 0.125]}` | registration order: centres first, then the walk |
| `planted-ftree__defaultColorChange` | `setDefaultHighlightColor {"#ff0000"}`; `colorModule {0/0, "#ff0000"}` | the new default maps to -1 |

`setSelectedScheme` scenarios wait until Python has the named schemes.

---

## 9. Python port guidance

1. **Store methods** (`engine/store.py`, snake_case, TS order and mutation order as above):
   * `color_selected_nodes(nodes, color)`
   * `color_matching_modules(module, color, side=None)`
   * `color_module_ids(module, color)`
   * `color_by_layer()`, `color_by_physical_id()`
   * `color_categorical_metadata(name, colors: Mapping[str, str])`
   * `color_real_metadata(name, bins: Sequence[HistogramBin])`
   * `color_real_intervals(name, data, get_color, centers)`
   * `set_highlight_colors(colors)`, `set_default_highlight_color(color)`, `set_selected_scheme(scheme: Sequence[str])`
   * `get_highlight_color(index, default=None)`

   Put the walk in one private helper (§2.1), and do **not** snapshot `network.children`: the skip is part of parity.
2. **`apply()`** handles the §8.1 op records. `replay()` applies `inputs.nodeMetadata` to the `NetworkFile` nodes before `set_networks`. Copy the
   files and never mutate the caller's `NetworkFile`s.
3. **Value tests:** `md is None` (not falsiness), `isinstance(v, str)`, a numeric test that excludes `bool`, and a NaN-safe key map for
   `color_by_*`. ~~The metadata ops raise `TypeError` on a network with no leaves, because TS `haveMetadata` throws there.~~ (Fix round
   WP6, E12: no longer; such a network is skipped.)
4. **`layout(..., highlight=None, highlight_colors=None)`**:
   * Validate that it is exclusive with `colors`. `colors` defaults to `"similarity"`, so treat an explicit `colors=` plus `highlight=`
     as an error, and `highlight=` alone as `colors=None`.
   * Build the labels (§7.2) and run `apply_highlight` (§7.1) after the hierarchy ops.
   * Record `HighlightLabel`s from the indices returned by pre-registration.
   * Run the §7.4 skip detection.
   * Add `colors="layer" | "physical_id"` → `color_by_layer` / `color_by_physical_id` (design.md "more colour ops").
5. **Geometry and renderer:**
   * `highlight_labels`, `ModuleGeometry.name_highlight_indices` / `name_insignificant` (§5.3)
   * label lines coloured with `make_fill("#000", palette)`, brightened only when `insignificant` is True
   * `draw(legend=False)` and `alluvial.legend(ax, **kw)` using `get_artists(ax).geometry.highlight_labels`

   Text colour for an out-of-range index: black, as TS does for tspans. Group fills keep the v1 cycle-and-warn rule.
6. **Tests:**
   * the §8.3 fixtures through `test_engine_fixtures.py`
   * unit tests for the §7.2 normalisation (int ids → `"3"`), overlap `ValueError`, unknown-identifier warning, `str(k)` keys,
     label colour collisions (shared index, default → -1), and the §7.4 warning on `hlskip`
   * a property test: for random mappings, `layout(highlight=...)` equals a replay of `colorCategoricalMetadata` with the derived `nodeMetadata`
   * no-matplotlib-import still holds for `layout`

---

## 10. How the claims were verified

The probes ran the real TS sources (`src/store/DiagramStore.ts` and the engine). They were transpiled by an in-process Vite server that has the same alias set-up as
`tools/ts-fixtures/generate.mjs` (`resolve.alias["@alluvial-src"]`). The runner and the probes are in the session scratchpad. Nothing was written under
`web/alluvial`. Networks were built as `NetworkFile`-like objects (array paths, `identifier = String(id)`), not parsed files. Probes:

* `p1` `colorSelectedNodes`: propagation, re-paint, erase, multi-network selection, duplicate identifiers, empty selection
* `p2` `colorByPhysicalId` / `colorByLayer`: skip, re-run, invisible tail, layer keys, no-layer no-op
* `p3` `colorCategoricalMetadata`: index order, unused or shared or default colours, `haveMetadata` skip, metadata on input vs leaves
* `p4` insignificant groups, clear, `largestGroup` tie
* `p5` single-target ops and `getHighlightColor`
* `p6` real and interval metadata
* `p7` the skip lemma on a 4-module network
* `p8` the `hlskip` dataset

The results quoted in §2-§7 are the probes' outputs. For `p1` "selA", `p2` "byPhys" and `p3` "cat", a scratch Python implementation of
§3.1, §3.4 and §3.5 on top of the existing `alluvial.engine` reproduced the TS group/leaf dumps exactly. The note's pseudo-code is that implementation.
The `hlskip` files in §8.2 were not yet run through the real parser and the fixture harness. `colorRealIntervals` was probed with a
step `getColor`, not the UI's d3 quantize scale.

---

## 11. Open questions

1. **The `highlight=` vehicle (structural; owner decision).**
   * (a) **Recommended:** the real `colorCategoricalMetadata` with injected metadata (§7). It is a real web-app op and both forms share one path,
     but the user-visible §2.2 skip can leave the last module of a network without invisible modules gray. Python detects that and warns.
   * (b) The same walk over a **snapshot** of `network.children`, as a Python-only op mirrored by a harness-defined TS op built from
     TS primitives (`getHighlightIndex`, `LeafNode.update`, `updateLayout`). It has no skip and is still fixture-exact, but it has no web-app equivalent. It is the
     first "clean mode", against the v1 decision to mirror quirks.
   * (c) The mapping form through `colorSelectedNodes`, one call per label (the design's "as TS does for selected nodes"). It has no skip and also colours
     leaves of invisible modules, but propagation is last-wins per identifier, and it cannot express the callable form. The two forms would then
     have different quirks.
2. **An identifier under several labels:** `ValueError` (recommended), first label wins, or last label wins (what sequential `colorSelectedNodes` would do).
3. **Op order with hierarchy:** colour after the `module_level` / `expand` ops (recommended: it walks the displayed modules, and similarity ops
   need the final modules), or before. They differ in tie orders and in which leaves are visible (`multilevel-tree__expandThenHighlight` vs
   `__highlightThenExpand`). This must be fixed together with the hierarchy note.
4. **Fixture format:** an opt-in `labelNameHighlight` flag (recommended, which keeps 132 files byte-identical) vs per-name indices
   for all scenarios (`formatVersion` 2, one regeneration).
5. **The legend for insignificant members:** plain label colour only (recommended), or an extra "(insignificant)" entry in `brighter(0.8)`.
6. **Callable label order:** first appearance (recommended), or an explicit `highlight_order=`.
7. **Named colour schemes** (`setSelectedScheme`): port the 63 other `COLOR_SCHEMES` (needs a data file like `c3-sinebow-512.json`),
   or accept only lists and matplotlib colormaps at the Python level.
8. Should `colors="layer"` be offered when no network `is_multilayer` (TS: a relayout no-op), or raise? Should `"physical_id"` be offered when no network is higher-order?
   The web app hides the buttons. Raising is the recommended answer.
