# Port note: v2 hierarchy (expand, regroup, move, outlines, `module_level`)

Spec for porting the TS module-hierarchy features: `Module.expand`/`regroup`/`move`, `Network.moveToIndex` and
`isCustomSorted`, the store ops and how the web UI triggers them, `Network.tree` / `TreeNode` outlines and how React draws
them. It also defines the deterministic op sequence behind `layout(..., module_level=k)` (design.md, "v2 design") and the
v2 fixture scenarios.

TS citations are relative to `packages/alluvial-diagram/src/` unless they start with `apps/web/`. Python citations are
relative to `src/alluvial/`. Everything not owned here (swap-remove, `LeafNode.add/update`, `calcFlow`, the layout passes)
is specified in [`model.md`](model.md) and [`layout.md`](layout.md). This note only says how the hierarchy features use it.

> **Erratum (0.5, fix round WP3: E1, E2).** Both "parity quirks" of this note are fixed in TS and Python: the stree
> trailing `:` no longer adds a phantom level (§3.4: the `"1:1:1:"` leaves of `debug5` now stop at level 2, like the
> `.tree` files), and `isAncestor` needs a `:` after the parent path (§4.2: regrouping `"1:2"` collapses only `1:*`; the
> store's expand selection uses `isAncestor` too). The `prefix-tree__regroupPrefix*` fixtures now pin the fixed
> behaviour. See model.md §4 erratum.

> **Erratum (0.5, fix round WP8: B2, H4).** §10.1 is replaced by one store op, `setModuleLevel(levels)` (TS
> `DiagramStore.setModuleLevel`, Python `DiagramStore.set_module_level`). Per network, rounds of "expand every visible
> module below its level with `Module.canExpand` (the refusal rule of `expand`, factored into a getter), in `children`
> order", each followed by `calcFlow` and the network's `updateFlowThreshold` but **no layout**, until a round finds
> none; then one `updateLayout()` if something was expanded. `apply_module_level` calls it once and returns
> `[{"op": "setModuleLevel", "levels": [k per network]}]` (or `[]`); the harness `moduleLevel` macro records the same
> op. The visible module sets and their order are unchanged (17 fixtures checked); hidden-module order and last bits
> changed. Science `module_level=2`: 2.5 s → 0.67 s in Python (one layout instead of 25), 523 → 157 ms in TS. The web
> app's Expand button is disabled unless `module.canExpand` (it used `isLeafModule`, which looks at the deepest leaf
> only). §10.1 below and the macro description in §11 are kept as the record of the old per-expand sequence.

> **Erratum (0.5, fix round WP7: E7, E10, E15a, H1).** (a) Pass 1 now writes `module.index` for the visible modules
> in drawn order also when `isCustomSorted` is set, and zeroes the margin of hidden modules (§5.3: `index` no longer
> goes stale; a hidden module's margin is no longer scaled by the 20 % cap on every layout). (b) The branch sort is
> tie-safe (`a === b ? 0 : a - b`; two `-Infinity` keys compare equal instead of `NaN`; no visible change, Python
> already sorted by key). (c) `Module.move` checks its boundary against the **visible** children (§5.1): moving the
> top visible module up is refused with the usual warning and no longer freezes the order (`planted-ftree__moveHidden`
> now pins the refusal). (d) `Network.tree` no longer throws for a visible `P` together with a visible `P:x` (§8.4):
> `P` joins the non-leaf node of its own path, and if `P` came first its leaf node becomes a non-leaf node, so in
> either order one outline encloses `P` and its sub-modules. The Python `RuntimeError` and the geometry
> catch-and-warn are gone; scenarios `multilevel-tree__visibleAndSubmodule{,Order}`.

## 0. Verification (2026-10-10)

The TS sources were loaded through Vite SSR exactly as `tools/ts-fixtures/generate.mjs` does (scratch dir only, nothing
written under the web repo). The probes and their results:

- **Python prototype vs the 4 existing v2 fixtures.** `Module.expand`/`regroup` and `DiagramStore.expand`/`regroup` were
  monkeypatched onto the current engine exactly as in §2-§4 and §10. `debug5-stree__expand`,
  `multilevel-tree__expand`, `multilevel-tree__expandColored` and `multilevel-tree__expandRegroup` all match with 0
  non-bitwise floats. That includes the `hierarchy` outline rects that the existing `Network.tree` port produces.
- **`module_level` algorithm (§10), TS vs Python prototype.** The cases were multilevel k=2, 3 and `[1,3,2]`, debug5-stree k=3,
  science-stree k=2 (24 expands, 4 networks of about 1k modules) and fuzz1347 k=4. The op lists are identical, and so are
  every module's `(id, level, visible, y, height, margin)`, every outline `(path, level, max, x, y, w, h)` and `network.flow`.
- **Move, custom sort and the regroup prefix bug, TS vs Python prototype.** The sequences were expand ×4 + regroup (prefix bug)
  + moves + `setHeight` + move, and moves + colour + `setHeight` + expand + moves + `resetLayout` with `flowThreshold`
  0.4. The return values, every module's `(id, level, visible, index, y, margin)`, `isCustomSorted` and `network.flow` are
  identical.
- **Order sensitivity.** The same `module_level` run in three op orders gives the same leaf levels and the same visible sets.
  The invisible-module order differs on science, the last bits of `y` differ on science, and the visible order on
  debug5-stree k=3 differs through an equal-flow tie. So the op order must be specified exactly (§10.2).
- **Edge cases.** The `isAncestor` prefix bug collapses unrelated modules (§4.2). Modules `P` and `P:x` shown at the same
  time make `hierarchicalChildren` throw (§8.4). `moveNetwork` drops `highlightColors` (§6.5).

## 1. Status of the Python port (updated 2026-10-10: v2 implemented)

| Piece | TS | Python today |
|---|---|---|
| `TreePath` incl. `isAncestor` (prefix bug), `parentPath`, `ancestorAtLevel`, trailing-`:` phantom level | `utils/TreePath.ts` | **done** (`tree_path.py`; model §4) |
| `LeafNode.moduleLevel` (mutable), live `insignificant`, `moduleId`, `update()` | `alluvial/LeafNode.ts:56-81,196-231` | **done** (`engine/leaf_node.py:69-97,175`) |
| `Module.maxModuleLevel`, `hasSubmodules`, `isTopModule`, `isLeafModule`, `parentIndex` | `alluvial/Module.ts:128-142,171-178` | **done** (`engine/module.py:138-180`) |
| `Network.tree`, `TreeNode`, `hierarchicalChildren` | `alluvial/Network.ts:212-246,367-454` | **done** and correct on all v2 cases probed (`engine/network.py:111-131,216-293`) |
| `Network.isCustomSorted` honoured by pass 1 | `alluvial/Diagram.ts:197-210` | **done** (`engine/diagram.py:110`) |
| `Module.expand` / `regroup` / private `siblings` / `move` | `alluvial/Module.ts:184-193,212-319` | **done** (`engine/module.py`) |
| `Network.moveToIndex` + `moveItem` | `alluvial/Network.ts:339-341`, `utils/array.ts:2-11` | **done** (`engine/network.py`, `engine/_utils.move_item`) |
| Store `expand`, `regroup`, `moveSelectedModule`, `resetLayout` | `store/DiagramStore.ts:450-511` | **done** (`engine/store.py`: `expand`, `regroup`, `move_module`, `reset_layout`) |
| `apply` ops `moveModule`, `resetLayout`, `moduleId` addressing | (harness) | **done** |
| `module_level=`, `expand=` in `layout()` | (§10) | **done** (`DiagramStore.apply_module_level` / `apply_expand_list`, called by `layout.py`) |
| Geometry: `ModuleGeometry.level`/`max_level`/`order`, `NetworkGeometry.outlines` | (§11) | **done** (`geometry.py`) |
| Renderer `hierarchy=` (shadow/outline) | `react/ModulesWrapper.tsx`, `react/HierarchicalModule.tsx` | **done** (`mpl.draw(hierarchy=...)`, §13.4; decisions in design.md "v2 implementation") |
| Tests | | **done**: all v2 fixtures replay bit-exactly (`tests/test_engine_fixtures.py`), the macro ops match (`test_engine_fixture_macros`), `layout()` reproduces every fixture its arguments can express (`tests/test_layout_v2.py`), renderer in `tests/test_mpl_v2.py` |
| Not ported (not needed) | `moveNetwork`, `selectedModule` and its selection side effects, `DropShadows` | none |

The fixture dump (`tests/test_engine_fixtures.py:285-296`) already writes `hierarchy` in the harness format, so the v2
fixtures need no new dump code. The only exception is the new op records (§12).

## 2. TreePath pieces the hierarchy uses

All of them are in model §4 and already ported. The quirks that matter here:

- **`isAncestor(parent, child)`** (`utils/TreePath.ts:96-105`): root → true. Otherwise `len(p) < len(c) and
  c.startswith(p)` on the **strings**, with no separator check. Verified: `isAncestor("1","10:2") == true`,
  `isAncestor("1:2","1:20") == true`, `isAncestor("1","1") == false`. Only `Module.siblings` (regroup) uses it.
- **Trailing `:`** (`:40-43`): `"1:1:1:"` keeps `pathArr = [1,1,1,0]`, so `level == 4` and
  `ancestorAtLevelAsString(3) == "1:1:1"` (the leaf's own path). `.stree` files from Infomap ≥ 1 write such paths
  (`debug5_*.stree`). The science `.stree` files do not. Effect: one extra expandable level, and expanding to it makes
  every leaf its own module (§3.4).
- **`ancestorAtLevelAsString(level)`** (`:198-200`): for `level >= len(pathArr)` it returns the full cleaned path. So a
  `moduleLevel` at or beyond the path depth gives `moduleId == leaf path` (input-only; `expand` never gets there, §3.1).
- **`ancestorAtLevel(path, level)`** (static, `:111-114`) returns a `TreePath`. `TreePath.parentPath` (`:132-143`) is only
  used for the store's selection after a regroup (no geometry effect).
- **`String.startsWith`** is also used in `DiagramStore.expand` (`:456-458`) to pick the selected sub-module. It has the
  same prefix flavour, but it only affects the selection (verified: expanding `"1"` selects `"11"` when that is the largest
  `"1…"` module).

## 3. `Module.expand()` (`alluvial/Module.ts:212-245`)

### 3.1 Algorithm

```python
def expand(self) -> bool:
    leaf_nodes = self.get_leaf_nodes()                   # snapshot list, leafNodes() order (groups → branch → leaves)
    if not leaf_nodes:
        warn("No leaf nodes found"); return False        # console.warn, :214-217
    new_module_level = self.module_level + 1
    if any(node.level <= new_module_level for node in leaf_nodes):   # :221-223, node.level = TreePath.level
        warn(f"Module can't be expanded to level {new_module_level} "
             f"because some nodes are at level {new_module_level - 1}")
        return False
    network = self.parent                                 # :232-235 throws if None (unreachable)
    network.is_custom_sorted = False                      # :237, set BEFORE any mutation
    for node in leaf_nodes:                               # :239-242
        node.module_level = new_module_level
        node.update()                                     # remove() + add(), model §5.4
    return True
```

- **Eligibility is all-or-nothing per module.** If *any* leaf has `level <= moduleLevel + 1`, the module is refused,
  even when other leaves are much deeper. Examples: fuzz1347 module `3` has leaf depths {2,3,4} and stays at level 1;
  multilevel_t2 module `4` has depth-2 leaves only. "Deepest module otherwise" (design.md) therefore holds per module,
  not per leaf.
- **The sidebar's Expand button is enabled when `!isLeafModule`** (`apps/web/src/components/Sidebar/Module.tsx:74-77`).
  `isLeafModule` uses `maxModuleLevel = max(level - 1)` (the *deepest* leaf), but the refusal uses the *shallowest* leaf.
  So the button can be enabled for a module that `expand` refuses (the UI then plays the shake animation, `react/Module.tsx:43-61`).
- **No visibility check.** `expand` works on invisible modules. Only the UI limits users to visible ones.

### 3.2 Mutation order and its effects

The effects are all the existing `LeafNode.update()` machinery (model §5.3-§5.4, streamlines §3.3). Nothing new:

1. The leaves are processed in snapshot order. Each `update()` removes the leaf from its group, branch and streamline
   node (swap-removes) and re-adds it under `module_id = ancestorAtLevelAsString(new_level)`.
2. The **first** leaf for each new sub-module id creates `Module(network, sub_id, new_level)`, which is **appended** to
   `network.children` (`Module.ts:29`, `LeafNode.ts:120-124`). So the sub-modules are appended in order of first
   appearance in the snapshot.
3. When the last leaf leaves the old module, the old module is removed from `network.children` by **swap-remove**
   (`AlluvialNode.ts:149-158`): the last child (normally the most recently created sub-module) takes its slot.
4. The store then runs `calcFlow` + `updateLayout` (§6.1). Pass 1 re-sorts the visible modules (`isCustomSorted` was
   cleared) with the path `Tree` (§7.1) and moves the invisible ones behind them **in their current order**. That order
   is the swap-remove result and is visible in fixtures (`modules` lists all modules).
5. `HighlightGroup.insignificant` is fixed when a group is created, from the leaf's live `insignificant`
   (`isSignificant(moduleLevel - 1)`, `LeafNode.ts:63-65`). `"1:2;3;"` re-added at level 2 goes into an insignificant
   group (`debug5-stree__expand`).
6. `highlightIndex` is kept per leaf, so the sub-modules inherit their parent's colours. Group order inside a module is
   re-sorted every layout (`Diagram.ts:215-221`).

### 3.3 Equal-flow ties and op order

The Tree sort is stable. Sub-modules with equal sort keys keep their `network.children` order, which is the creation order
from step 2 plus the swap-remove of step 3. So two expand orders can give different visible orders (verified:
debug5_1 at k=3, `1:1:1` vs `1:2:1`, both flow 0.2). This is why §10 fixes the order.

### 3.4 Trailing-colon example (verified, `debug5_*.stree`, §10 with k=3)

The ops are `[expand n0 "1", expand n0 "2", expand n0 "1:1", expand n0 "2:1", expand n1 "2", expand n1 "1", expand n1 "1:1",
expand n1 "1:2"]`. Final modules of `debug5_0` in children order: `1:1:1@3 1:1:2@3 1:2@2 2:2@2 2:1:1@3`. Modules
`1:1:1`, `1:1:2` and `2:1:1` are single leaves (`"1:1:1:"` level 4 allows level 3). `1:2` and `2:2` hold `"1:2;3;"` /
`"2:2;2;"` (level 3), so they are refused at level 3. The same files as `.tree` stop at level 2.

## 4. `Module.regroup()` (`alluvial/Module.ts:247-281`) and `siblings` (`:184-193`)

### 4.1 Algorithm

```python
def _siblings(self) -> list[Module]:
    modules = self.parent.children                                    # current order (after the last layout)
    level = self.module_level - 1
    if level < 1:
        return modules                                                # unreachable from regroup (refused at level 1)
    parent_path = TreePath.ancestor_at_level(self.module_id, level)   # TreePath of the first `level` segments
    return [m for m in modules if TreePath.is_ancestor(parent_path, m.module_id)]   # string-prefix bug kept

def regroup(self) -> bool:
    if self.module_level <= 1:
        warn(f"Module with id {self.module_id} is already at module level {self.module_level}"); return False
    leaf_nodes = [leaf for m in self._siblings() for leaf in m.get_leaf_nodes()]   # module order, then leaf order
    if not leaf_nodes:
        warn("No leaf nodes found"); return False
    self.parent.is_custom_sorted = False
    new_module_level = self.module_level - 1
    for node in leaf_nodes:
        node.module_level = new_module_level
        node.update()
    return True
```

- The snapshot is built completely before any mutation. Siblings are taken from `network.children`, **including
  invisible modules** (they are regrouped too).
- `new_module_level` is applied to **all** sibling leaves, whatever their current level. A sibling at a deeper level (for
  example `1:2:5:x` when regrouping `1:3`) jumps straight to `new_module_level`. A sibling already at `new_module_level`
  (only reachable through the prefix bug, e.g. `"10"` when regrouping `"1:2"`) keeps its level, but its leaves still
  run `update()`, so it is re-created with the swap-remove reshuffle of model §10.3.
- A matched module is never *raised*. Every id with the prefix `"a:b"` has at least two segments.

### 4.2 The prefix bug (verified)

Synthetic network with 11 top modules, each `t:s:l`. The calls are `expand "1"`, `expand "10"`, `expand "11"`, then
`regroup "1:2"`. `parent_path = "1"` matches `1:1`, `1:2`, `10:1`, `10:2`, `11:1`, `11:2`, so **all three** top modules
collapse back to level 1. Children before the regroup:
`2@1 3@1 11:1@2 11:2@2 5@1 1:1@2 1:2@2 7@1 6@1 4@1 8@1 10:2@2 10:1@2 9@1`; after:
`2@1 3@1 11@1 5@1 1@1 7@1 6@1 4@1 8@1 10@1 9@1`. One level down, regrouping `1:2:x` also collapses `1:20:*`, `1:21:*` and so on.
This only happens with ≥ 10 modules under one parent. ~~Keep it for parity (decided in model Q3; see Open questions).~~
Fixed in fix round WP3 (E2): only `1:1` and `1:2` collapse.

## 5. `Module.move`, `Network.moveToIndex`, `isCustomSorted`

### 5.1 `move(direction)` (`alluvial/Module.ts:294-319`)

```python
def move(self, direction: str) -> bool:            # "up" | "down"
    index = self.parent_index                       # identity index in network.children (ALL modules)
    network = self.parent
    boundary = len(network.children) - 1 if direction == "up" else 0
    if index == boundary:
        warn(f"Can't move module {direction} because it is already at the "
             f"{'bottom' if direction == 'down' else 'top'}")
        return False
    network.is_custom_sorted = True                 # :316, set BEFORE the move
    network.move_to_index(index, index + (-1 if direction == "down" else 1))
    return True
```

- **Up means a higher index.** Stacking starts at the bottom (`y = height`), so `children[0]` is the bottom module and
  "up" is visually up.
- The boundary is about **all** children, not the visible ones. Moving the topmost *visible* module up swaps it with the
  first invisible module. That succeeds and sets `isCustomSorted`, but pass 1 puts the visible ones first again
  (stable partition, `Diagram.ts:210`), so nothing visible changes.

### 5.2 `moveToIndex` / `moveItem` (`alluvial/Network.ts:339-341`, `utils/array.ts:2-11`)

```python
def move_item(arr: list, from_index: int, to_index: int) -> None:
    start = len(arr) + from_index if from_index < 0 else from_index
    if 0 <= start < len(arr):
        end = len(arr) + to_index if to_index < 0 else to_index
        item = arr.pop(from_index)        # JS splice(fromIndex, 1); note: raw from_index, not start
        arr.insert(end, item)             # JS splice(endIndex, 0, item); end > len appends, like splice
```

`move` only passes in-range neighbours, so the negative-index branches are never used. Port them anyway. Note that
`splice(-1, 1)` and `pop(-1)` agree, and that `insert` with a negative `end` cannot happen after the normalisation.

### 5.3 Who sets and clears `isCustomSorted`

| Call | Effect on `isCustomSorted` |
|---|---|
| `Network` ctor (`Network.ts:41`) | `False` |
| `Module.move` (succeeded) | that network → `True` |
| `Module.expand` / `regroup` (succeeded) | **that network only** → `False` (other networks keep their custom order) |
| `DiagramStore.resetLayout` (`DiagramStore.ts:493-498`) | all networks → `False`, then `updateLayout()` |
| colour ops, option setters, failed ops | unchanged (verified: custom order survives `setHeight` and `colorMatchingModulesInAllNetworks`) |
| `moveNetwork` / `setNetworks` | new diagram → `False` |

When `isCustomSorted` is true, pass 1 skips the Tree sort, so **`module.index` is not updated and goes stale**. It keeps
the value of the last sorted layout (verified: after moving `children[0]` up, `index` reads `1,0,2,…`). The fixture
field `modules[j].index` checks this. The `children = visible + invisible` partition still runs.

### 5.4 Layout after a move

`DiagramStore.moveSelectedModule` (`:500-511`) calls **`diagram.updateLayout(this)` without `calcFlow`**. Every other op
goes through `store.updateLayout()` (`:485-491`, `calcFlow` first). `network.flow` (the sum of `children` flows in
children order) is therefore *not* re-summed after a move, and keeps the pre-move summation order until the next op that
runs `calcFlow`. Port this literally. A fixture whose last op is a move covers it (§12).

## 6. Store ops and the web UI

### 6.1 Store methods (`store/DiagramStore.ts`)

| Method | Lines | Behaviour (geometry-relevant part) |
|---|---|---|
| `expand(module)` | 450-467 | `ok = module.expand()`; if not `ok` return `False` (no layout). Else `updateLayout()` (= `calcFlow` + `diagram.updateLayout`), then select the largest visible module whose id `startsWith(moduleId)` (selection only). |
| `regroup(module)` | 469-483 | `ok = module.regroup()`; if not `ok` return `False`. Else `updateLayout()`, then select `parent.getModule(parentPath(moduleId))` (selection only). |
| `moveSelectedModule(dir)` | 500-511 | no-op without a selection; `didMove = selectedModule.move(dir)`; if moved: `diagram.updateLayout(this)` (**no calcFlow**). |
| `resetLayout()` | 493-498 | all `isCustomSorted = False`; `updateLayout()`. |
| `moveNetwork(dir)` | 517-557 | rebuilds the diagram (§6.5). |
| `selectModule(dir)` | 430-448 | selection only (up/down within `visibleChildren`, left/right via `getSimilarModules(side, 1)`). |
| `setHierarchicalModules`, `…Offset`, `…Opacity` | 364-376 | render options only, no layout. Defaults `"shadow"`, `5`, `0.5` (`:105-107`). |

`updateLayout` returns early for an empty diagram (`:487`). The Python store already mirrors that.

### 6.2 UI triggers (what a web user can do)

- **Double-click a module**: `store.expand(module)`. **Shift + double-click**: `store.regroup(module)`
  (`react/Module.tsx:41-61`; on failure the module shakes). Only *drawn* (visible) modules can be clicked.
- **Keys** (`react/Diagram.tsx:72-96`, inactive in edit mode): `e` expand and `c` regroup the selected module; `w`/`s`
  `moveSelectedModule("up"/"down")`; `a`/`d` `moveNetwork("left"/"right")`; the arrow keys change the selection.
- **Sidebar** (`apps/web/src/components/Sidebar/Module.tsx`): Move up/down, Move network left/right, Expand (disabled when
  `isLeafModule`), Contract = regroup (disabled when `isTopModule`). Layout panel (`…/Sidebar/Layout.tsx:22,105-135`):
  "Reset layout" (`resetLayout`), hierarchical mode select, opacity slider (0-1, step 0.1, disabled for `"none"`),
  offset slider (1-10, step 1, enabled only for `"shadow"`).
- After `setNetworks` the largest module of the leftmost network is selected (`:228-231`). That has no geometry effect.

### 6.3 What a user's expansions produce

Each click is exactly one `store.expand(module)`. So any click sequence is an op list of the form §12 records, and
`module_level=k` (§10) is one particular click order: per network left to right, level by level, each level bottom to
top in the stacking order of the moment. Under a different click order the probes gave the same leaf levels and visible
sets, but a different invisible order, last-bit `y` values, and visible order on equal-flow ties (§0).

### 6.4 Selection

The selection never changes geometry. The Python store does not need `selected_module`. `move_module(module, direction)`
takes the module directly. The harness selects it first (§12.1).

### 6.5 `moveNetwork` (not ported; for reference)

> **Erratum (0.5, fix round WP10: H3, TS only).** `moveNetwork` no longer uses `getLeafNode(identifier)` or a bare
> `setNetworks`. It serialises the diagram in memory as a save (`serializeDiagramData`, the data of the WP9 writer),
> writes each node's `highlightIndex`/`moduleLevel` back **per input node** (`Network.inputLeafNodes`, so duplicates
> keep their own), sets each file's `colors` to the store palette and its `alluvial` block, reorders the files and
> restores them with `openNetworks`. The palette, the per-leaf colours, network and module names, custom module orders
> (`isCustomSorted`), the options, the scheme and the bipartite toggle survive the move. Python still has no
> `moveNetwork`. The text below describes the old behaviour.

`moveNetwork` writes `file.name`, and per node the `highlightIndex`/`moduleLevel` of `network.getLeafNode(identifier)`
(last-wins on duplicate identifiers), back into the `NetworkFile`s. It then splices the files and calls
`setNetworks(files, false)`. The expansion state is rebuilt by the `LeafNode` ctor (`LeafNode.ts:56-60`) at build time.
That is a different mutation order from replaying the expands, so the ties and the invisible order can differ.
`setNetworks` → `checkColors` resets `highlightColors` to `[]` unless the files carry `colors` (verified: 3 → 0 colours,
while the leaves keep their `highlightIndex`). That is a TS bug. In Python, reordering the inputs and re-applying
`module_level`/`expand=` is the equivalent.

## 7. Layout with mixed module levels

Nothing in `Diagram.updateLayout` knows about levels. Levels enter only through `module.path` (= `TreePath.toArray(moduleId)`)
and through which modules exist. The Python layout already handles all of this (the v2 fixtures pass).

### 7.1 Sort (pass 1, `Diagram.ts:197-207`, `utils/Tree.ts:24-66`)

- `Tree(visibleModules, key)` nests the modules by path segment. Every ancestor `TreeNode` gets
  `size += key(module)` for each visible descendant module. Siblings are sorted **descending by size, stably**. A module
  item itself compares as 0, and it is pushed into the `TreeNode` of its last segment, so its rank is that node's size.
  Flatten is depth-first. Result: **sub-modules of one parent are always contiguous**, and parents compete with their
  summed key.
- The keys (`Diagram.ts:392-405`): `flow → flow/maxFlow`, `nodes → numLeafNodes/numLeafNodes(network)`,
  `highlightIndex → -highlightIndex`, `nodeId → meanNodeId`. For `highlightIndex` and `nodeId` the parent key is a
  **sum** over the visible sub-modules (e.g. an expanded module with three sub-modules of mean id ≈ 100 sorts as 300). That
  quirk is level-dependent and covered by a proposed fixture (§12).
- Only *visible* modules enter the Tree. Hidden sub-modules contribute nothing to their parent's size.

### 7.2 Margins (`Diagram.ts:222-226`, `utils/difference-index.ts:1-7`)

`margin = 2 ** (marginExponent - 2 * differenceIndex(path_i, path_next))` between consecutive *visible* modules in the
sorted order (0 after the last one). `differenceIndex` is the first index where the arrays differ, and **0 if one is a
prefix of the other or they are equal**. With the default exponent 4:

| neighbours | differenceIndex | margin |
|---|---|---|
| different top modules (`1:2` / `2`, `2` / `3:1`) | 0 | 16 |
| same top, different level-2 (`1:1` / `1:2:3`) | 1 | 4 |
| same level-2 (`1:1:1` / `1:1:2`) | 2 | 1 |
| same level-3 | 3 | 0.25 |

So expanding adds many small margins and lowers `totalMargin`, unless the 20 % cap (layout §5) scales them. The
`geometry` option set (exponent 5) gives 32/8/2/0.5.

### 7.3 Visibility and threshold

`Network.updateFlowThreshold` (layout §2) runs over **all** module flows. Splitting a module adds smaller flows and can
move the threshold, so other modules (including untouched ones and other sub-modules) can appear or disappear after an
expand. `Module.isVisible` reads the threshold set by the *last* layout. That is why §10 re-checks visibility before each
op.

### 7.4 Labels

There is nothing level-specific. Every visible module gets a label in the first and last network (layout §6). Sub-modules
are smaller, so labels get crowded. `mpl.draw`'s `avoid_label_overlap` handles that. Module ids (`showModuleId`) would show
`1:2:3`.

## 8. `Network.tree`, `TreeNode`, `hierarchicalChildren`

### 8.1 Construction (`alluvial/Network.ts:216-246`)

The getter **rebuilds the tree on every access**, and so does `hierarchicalChildren` (`:212-214`).

```python
root = TreeNode()                                       # path "root", module_level 1, is_leaf False, no parent
for module in network.children:                         # current order = visible (sorted) then invisible
    if not module.is_visible: continue
    parent = root
    path = TreePath(module.path)                        # module.path is a number list → joined with ":"
    for level in range(1, module.module_level + 1):
        key = path.ancestor_at_level_as_string(level)   # full path when level >= len(path)
        if not parent.has(key):
            parent = parent.create_child(key, level, is_leaf=(level == module.module_level))
        else:
            parent = parent.get(key)
    parent.add_child(module)                            # raises unless parent.is_leaf and parent.parent
```

- **`is_leaf` is decided by the module that creates the node.** A node created as an ancestor is non-leaf forever.
- `TreeNode(path, module_level, is_leaf, parent)` (`:367-396`): `children = []`, `childPathMap = {}`,
  `maxModuleLevel = 1`, `y = +inf`, `maxY = -inf`, `maxHeight = -inf`, `x = width = height = 0` (from `Layout`). With a
  parent it appends itself to `parent.children`, registers itself in `parent.childPathMap`, and calls
  `updateMaxModuleLevel(module_level)` **on itself**. That raises its own max and then every ancestor's (root included).
  So `maxModuleLevel` is the maximum level in the node's subtree, **local** to it: sibling outlines in one network can
  have different maxima (verified: debug5_1 at k=3 has `T(2) max 2` and `T(1) max 3`).
- `add_child(module)` (`:417-424`) calls `self.parent.update_layout(module)` and then appends the module. **The leaf
  `TreeNode` itself never gets a layout.** That is harmless, because leaf nodes are not yielded.
- `update_layout(module)` (`:433-453`), recursive up to the root:

```python
self.x = module.x; self.width = module.width           # last module wins (same column)
self.y = min(self.y, module.y)
if module.y > self._max_y:
    self._max_y = module.y; self._max_height = module.height
    self.height = max(self.height, abs(self.y - module.y) + module.height)
else:
    self.height = max(self.height, abs(self.y - self._max_y) + self._max_height)
parent.update_layout(module) if parent
```

The rect is the union of the visible descendant modules, from the top of the topmost one to the bottom of the
lowest one. It includes the inner margins and is computed with exactly these float operations. Do not replace it with
`max(y + h) - min(y)`, because the last bits can differ. Already ported verbatim (`engine/network.py:281-293`).

### 8.2 BFS order (`TreeNode.visitBreadthFirst`, `:402-415`)

```python
queue = root.children        # NOTE: the root's own list is consumed (shift/push mutate it); fine, the tree is throwaway
while queue:
    node = queue.pop(0)
    if isinstance(node, TreeNode):
        if not node.is_leaf: yield node
        queue.extend(node.children)
    else:
        yield node           # a Module
```

The root is never yielded, and neither are leaf `TreeNode`s. A level-L outline sits at tree depth L, and a level-L
module sits at depth L+1. So the output is ordered by depth and interleaves **level-(L+1) outlines with level-L modules**.
Verified example (multilevel_t2, k=3):
`T(1) T(2) T(3) | 4 | 1:1 1:2 1:3 1:4 1:5 2:1 2:2 2:3 3:1 3:2 3:3` (module `4` is level 1, depth 2, so it comes
right after the level-1 outlines). With nested outlines (multilevel_t1, k=3):
`T(1,max3) T(2) T(3) T(1:1,L2,max3) 1:2 1:3 1:4 2:1 … 3:3 1:1:1 1:1:2 1:1:3`. In v1 (all level 1) every `TreeNode`
is a leaf, so `hierarchicalChildren == visibleChildren` in order.

### 8.3 Fixture field

`networks[i].hierarchy` (`tools/ts-fixtures/README.md`) is this BFS list. Each item is
`{type: "module", moduleId}` or `{type: "tree", path, moduleLevel, isLeaf (always false), maxModuleLevel, x, y, width,
height}`, with the raw `TreeNode` rect (no render offset).

### 8.4 Mixed `P` / `P:x` makes the tree throw (verified)

If module `P` (level 1) and some `P:x` (level 2) are both visible, the Tree sort puts `P:x` before `P` (§7.1: the `TreeNode`
for `P:x` has size > 0, while the module `P` compares as 0). `P:x` then creates `T(P)` as non-leaf, and `P.add_child`
throws `"Module added to non-leaf TreeNode"`. Verified in both creation orders. The React diagram (default
`hierarchicalModules = "shadow"`) would crash. **No sequence of expand/regroup from a uniform start reaches this state**:
expand moves all of a module's leaves, and regroup lowers every prefix match. It needs input `moduleLevel`s (saved web-app
JSON, `moveNetwork` with duplicate identifiers). The Python port raises the same `RuntimeError`. Geometry building must not
call `tree` blindly for such inputs (Open question 5).

## 9. How React draws the hierarchy

### 9.1 Draw order (`react/Network.tsx:29-64`, `react/Diagram.tsx:135-137`)

Per network `<g class="network">`, in diagram order: gradients, the network name, then `ModulesWrapper`, then the network's
streamlines (`getLinks` order). So network *i+1*'s outlines are painted **over** network *i*'s streamlines, and under its own.

`ModulesWrapper` (`react/ModulesWrapper.tsx:23-57`): with mode `"none"` it draws `visibleChildren` as modules. Otherwise
it iterates `hierarchicalChildren` in BFS order. A Module is drawn as a module (group rects, labels). A `TreeNode` is
drawn as a `ShadowModule` (mode `"shadow"`, the **default**) or an `OutlineModule` (mode `"outline"`). The keys and ids are
`path`. That makes the z-order: level-1 outlines, then level-1 modules interleaved with level-2 outlines, and so on.

### 9.2 `OutlineModule` (`react/HierarchicalModule.tsx:5-38`)

```text
offset = 1 + 2.5 * (maxModuleLevel - moduleLevel)          # ≥ 3.5 (a non-leaf node always has max ≥ level + 1)
rect x = x - offset, y = y - offset, width = width + 2*offset, height = height + 2*offset
rx = offset (ry defaults to rx), fill none, stroke = defaultHighlightColor "#b6b69f",
strokeWidth 2, strokeDasharray "1,4", strokeLinecap round, strokeLinejoin round, opacity = hierarchicalModuleOpacity (0.5)
```

With round caps the 1-px dashes on a 2-px stroke become dots of diameter about 2, every 5 px. The outer outline of a
3-level subtree is 6 px out, the inner one 3.5 px. The outline sticks out by `offset` on every side, so its left edge lies
over the previous network's incoming streamlines (drawn earlier) and its right edge under this network's outgoing
streamlines.

### 9.3 `ShadowModule` (`react/HierarchicalModule.tsx:40-79`)

```text
offsetBy = hierarchicalModuleOffset (5) * (maxModuleLevel - moduleLevel)      # ≥ 5
<g style="isolation: isolate; mix-blend-mode: difference">
  <g transform=translate(offsetBy, offsetBy)>                                  # down-right in SVG (y down)
    <rect x y width height = TreeNode rect, fill = defaultHighlightColor "#b6b69f", opacity = 0.5/>
```

The rect is the raw union rect shifted right and **down** by `offsetBy`. It is painted before the deeper modules, so it
peeks out to the right (under the outgoing streamlines) and below the parent's bottom module (into the margin). Blend:
`Co = 0.5·Cb + 0.5·|Cb − Cs|`, with `Cs = (182,182,159)/255`. Over the white background this gives `(164,164,175.5)` ≈
`#a4a4b0`. Over a module colour `Cb` it gives a partial inversion. That happens only where a shadow overlaps an
earlier-painted module, i.e. when the margin below a parent is smaller than `offsetBy` (the margin cap, `geometry`
options, deep levels).

### 9.4 Module drop shadow (not part of the hierarchy, off by default)

With `store.dropShadow` (default `False`, `DiagramStore.ts:109`), each module's group container gets
`filter: url(#shadow<moduleLevel>)` (`react/Module.tsx:37,83`, `react/DropShadows.tsx:31-38`). The filters exist for
levels 1-3 only (`Diagram.tsx:100`, `feDropShadow dx = dy = 1.5 + 0.2·level, stdDeviation 1 + 0.1·level, floodOpacity 0.5`).
A level-4 module references a missing filter (in current browsers: no filter). Not worth porting.

## 10. `module_level=k`: the deterministic op sequence

### 10.1 Definition

`levels`: an int `k` for every network, or a sequence with exactly one int per network (in diagram order). Each value
must be an int ≥ 1 (`bool` excluded). `1` means no ops.

```python
def eligible(module, k) -> bool:          # == "store.expand(module) would succeed and a user could click it"
    if not module.is_visible or module.module_level >= k:
        return False
    leaves = module.get_leaf_nodes()
    return bool(leaves) and not any(leaf.level <= module.module_level + 1 for leaf in leaves)

def apply_module_level(store, levels) -> list[dict]:
    ops = []
    for ni in range(len(store.diagram.children)):          # networks left to right; each runs to its fixpoint
        k = levels[ni]
        while True:                                       # one "round" per iteration
            network = store.diagram.children[ni]
            snapshot = [m for m in network.children if eligible(m, k)]   # current children order (after last layout)
            if not snapshot:
                break
            for module in snapshot:
                if not eligible(module, k):               # re-check: an earlier expand in this round may have moved
                    continue                              # the flow threshold and hidden it
                index = identity_index(network.children, module)   # recorded for the fixture/replay
                ops.append({"op": "expand", "networkIndex": ni, "moduleIndex": index, "moduleId": module.module_id})
                assert store.expand(module)               # module.expand() + calc_flow + update_layout
    return ops
```

The exact properties:

- **Visible only, re-checked before every op** (`is_visible` with the threshold of the last layout). Invisible modules are
  never expanded, the way a web user cannot click them. A module that becomes visible later is picked up in the next
  round. At the fixpoint every visible module is either at level ≥ k or not expandable.
- **Within a round:** the snapshot order is the `network.children` order of the moment, i.e. the sorted visible order
  (bottom to top), since only visible modules qualify. Each expand re-sorts `children`, so `moduleIndex` is looked up just
  before each op. Snapshot modules are never removed by another module's expand (expand only moves the expanded module's
  leaves into new ids under its own path), so identity lookups are safe.
- **Networks are independent fixpoints, run left to right.** The flow threshold is per network. Across networks the order
  still matters for bits and ties (a leaf `update()` touches the neighbour's streamline nodes), so it is fixed.
- **No refused ops are issued**, so there are no `console.warn`s and the fixture `warnings` stay empty.
- `k` beyond the deepest level just stops at the fixpoint. A lower level than the current one (input `moduleLevel` > k) is
  not regrouped. `module_level` only expands.

Verified counts (TS = Python): multilevel k=2: 10 ops, k=3: 11, `[1,3,2]`: 7; debug5-stree k=3: 8; science-stree k=2:
24 (23-36 level-1 modules stay per network; all but at most one are invisible, and the visible ones are not expandable), k=3: 55; fuzz1347 k=4: 2;
planted-* and states-* (2-level trees): 0 for every k.

### 10.2 Why this order (and not the others)

Probed alternatives: re-scanning after every op ("first eligible"), and each round in reverse order. Both give the same
leaf levels and visible sets on all datasets, but a different invisible order (science), last-bit `y` (science
reverse) and the visible order of an equal-flow tie (debug5-stree reverse). The rounds definition matches the design text
("expand the visible modules whose level is below k, in current layout order, until nothing changes"), and a user who
expands level by level, bottom to top, would get the same op list. Any fixed definition is testable. This one is now pinned
by the harness (§12).

### 10.3 `expand=[(network, module_id), ...]`

Applied first, in order, each as one `store.expand(module)`. `network` is an index (int) or a network id (str).
`module = network.get_module(module_id)` is looked up **at that time**, so `[(0, "1"), (0, "1:2")]` works. Visibility is
not required (the TS allows it). A missing module or a refused expand raises `ValueError` with the TS warning text.
Then `module_level`. Colour ops run after both (Open question 2).

## 11. Geometry fields (proposal)

The contract stays fixture-comparable: raw TS values, TS coordinates (y down), layout px.

- `ModuleGeometry.level: int = 1` (`module.module_level`). The default keeps `from_dict` of v1 geometry working.
  Optional: `ModuleGeometry.max_level: int = 1` (`module.max_module_level`, i.e. "has sub-modules"). It costs one pass
  over the leaves per module, which is fine.
- `NetworkGeometry.outlines: tuple[OutlineGeometry, ...] = ()`: the non-leaf `TreeNode`s of `network.hierarchical_children`
  in BFS order.

```python
@dataclass(frozen=True)
class OutlineGeometry(_ToDict):
    path: str            # TreeNode.path, e.g. "1" or "1:2"
    level: int           # TreeNode.module_level
    max_level: int       # TreeNode.max_module_level (subtree max, see §8.1)
    x: float; y: float; width: float; height: float    # raw union rect (§8.1), no render offset
    order: int           # index in hierarchical_children (BFS), for the web z-order
```

- `ModuleGeometry.order: int | None = None`: the index in `hierarchical_children` (visible modules). Together with
  `OutlineGeometry.order` this reproduces the web interleaving (§8.2). If the renderer does not need the exact
  interleaving (§13.4), drop both `order` fields.
- In v1 geometry: `outlines == ()`, `level == 1`, and `order` is the visible index.
- Fixture mapping for the geometry tests: `hierarchy` items of `type == "tree"` ↔ `outlines` (`path`, `moduleLevel`,
  `maxModuleLevel`, rect); `modules[j].moduleLevel` ↔ `level`.
- No geometry field for `isCustomSorted` is needed (the order is already in `modules`).

## 12. Fixture scenarios (proposal)

### 12.1 Harness additions (`tools/ts-fixtures/scenarios.ts`, `harness.ts`)

Existing fixtures stay **byte-identical**. Existing scenario ops and the dump format are unchanged. New op shapes only appear
in new scenarios.

- **Module addressing:** `expand`, `regroup`, `colorModule` and the new `moveModule` accept `moduleId` *instead of*
  `moduleIndex`, resolved with `network.getModule(moduleId)` at op time (throw if missing). Hand-written scenarios stay
  readable after the indices shift.
- `{op: "moveModule", networkIndex, moduleIndex | moduleId, direction: "up" | "down"}` →
  `store.setSelectedModule(m); if (!store.moveSelectedModule(direction)) throw`.
- `{op: "resetLayout"}` → `store.resetLayout()`.
- **Macro** `{op: "moduleLevel", levels: number | number[]}`: the harness runs §10.1 **in TS** and records the concrete
  ops it issued, `{op: "expand", networkIndex, moduleIndex, moduleId}`, in `inputs.operations`. The macro itself goes into a
  new `inputs.macros: [{atOperation, op}]` field, which is only written when present, so old fixtures don't change. Python
  tests both: (a) replaying `inputs.operations` gives the dump (bit parity), and (b) `apply_module_level` on the
  pre-macro state issues exactly the recorded ops (algorithm parity, compare the dicts incl. `moduleId`).
- The Python `DiagramStore.apply` gets `moveModule`, `resetLayout` and `moduleId` resolution. Ops carrying `moduleId` look
  it up instead of using the index.

### 12.2 New dataset

`prefix-tree`: `make_datasets.py` writes seeded `prefix_t{0,1}.tree`. There are 12 top modules, so `"1"` prefixes `"10"`,
`"11"` and `"12"`. Top module 1 has 11 sub-modules (`"1:1"` prefixes `"1:10"`, `"1:11"`), each with 2 sub-sub-modules of
2-3 leaves (4-level paths). The other top modules have 2 sub-modules × 2 leaves (3-level paths). The flows are seeded
random with no exact ties. Both slices share the node ids, so streamlines exist.

### 12.3 Scenario list

| Scenario | Options | Ops | Covers |
|---|---|---|---|
| `multilevel-tree__level2` | default | `moduleLevel 2` (10 expands) | the macro, sub-module creation and swap-remove, level-1 outlines |
| `multilevel-tree__level3` | default | `moduleLevel 3` (11) | nested outlines (`T(1) max 3`, `T(1:1)`), per-subtree `maxModuleLevel`, refused module `4` (t2), margins 16/4/1 |
| `multilevel-tree__levelMixed` | default | `moduleLevel [1,3,2]` (7) | per-network k, untouched network 0 |
| `multilevel-tree__level2Colored` | default | `moduleLevel 2`, `colorMatchingModulesInAllNetworks` | the recommended `plot()` path (expand, then colour) |
| `multilevel-tree__coloredLevel2` | default | `colorMatchingModulesInAllNetworks`, `moduleLevel 2` | expanding coloured modules (groups re-created, inherited colours) |
| `multilevel-tree__level3Geometry` | CORE `geometry` | `moduleLevel 3` | margin cap with deep `differenceIndex` (32/8/2) |
| `multilevel-tree__level3Justify40` | `flowThreshold 0.4`, `verticalAlign "justify"` | `moduleLevel 3` | threshold moves between ops, hidden modules below k, the re-check in §10.1 |
| `multilevel-tree__level2SortNodeId` | `sortModulesBy "nodeId"` | `moduleLevel 2` | summed parent keys (§7.1) |
| `debug5-stree__level3` | default | `moduleLevel 3` (8) | trailing-`:` leaf modules, insignificant groups at level 2, equal-flow ties (order-sensitive) |
| `science-stree__level2` | default | `moduleLevel 2` (24) | scale, hidden unexpandable modules, invisible order (about 2.4 MB, like the other science fixtures; Python replay about 4 s) |
| `fuzz1347__level4` | group options | `moduleLevel 4` (2) | mixed-depth refusal, zero flows, zero margins |
| `multilevel-tree__level3Regroup` | default | `moduleLevel 3`, `regroup {n1, "1:1:1"}` | level-3 regroup (siblings by prefix `"1:1"`, no bug), back to `T(1) max 2` |
| `prefix-tree__regroupPrefix` | `flowThreshold 0` | `expand 1`, `expand 10`, `expand 12` (n0), `expand 1` (n1), `regroup {n0, "1:2"}` | the `isAncestor` prefix bug at level 1 (collapsed 10 and 12 too; the unexpanded `11` was re-created at level 1). Since WP3 (E2): only `1:*` collapses |
| `prefix-tree__regroupPrefixDeep` | `flowThreshold 0` | `moduleLevel [3,1]`, `regroup {n0, "1:1:1"}` | the prefix bug at level 2 (`"1:1"` also collapsed `1:10:*`, `1:11:*`). Since WP3 (E2): only `1:1:*` collapses |
| `multilevel-tree__move` | default | `moveModule {n0, idx0, up}`, `moveModule {n0, idx1, up}`, `moveModule {n1, idx0, up}` (last op is a move) | `moveItem`, `isCustomSorted`, stale `index`, **no calcFlow after a move** |
| `multilevel-tree__moveSetOption` | default | the moves above, then `setOption height 400`, `colorMatchingModulesInAllNetworks` | custom order survives setters and colour ops |
| `multilevel-tree__moveExpand` | default | `moveModule {n0, idx0, up}`, `moveModule {n1, idx0, up}`, `expand {n1, "1"}` | expand resets only its own network |
| `multilevel-tree__moveReset` | default | the `__move` moves, then `resetLayout` | `resetLayout` |
| `planted-ftree__moveHidden` | `flowThreshold 0.4` | `moveModule` of the topmost visible module `up`, expected `result: false` (fix round H1; it used to swap with the first invisible one) | visible boundary: refused, order not frozen |

Unit tests rather than fixtures: refused ops return `False` and change nothing (`expand` of a 2-level module, `regroup` at
level 1, `move` down at index 0 and up at the last index); `planted-*` / `states-*` `module_level=3` issues no ops;
`move_item` with negative indices; the §8.4 `RuntimeError`.

**Fuzz:** add `expand`, `regroup`, `moveModule`, `resetLayout` and `moduleLevel` (k in 1-4) to `fuzz/gen.py::_ops`. A
refused expand, regroup or move must not abort the case. The fuzz harness records `{..., "result": bool}` in the resolved
ops instead of throwing, and Python asserts the same bool.

## 13. Python port guidance

### 13.1 Engine (all literal ports, verified by the prototype in §0)

- `engine/module.py`: `expand`, `regroup`, `_siblings`, `move` as in §3.1, §4.1 and §5.1. Use
  `warnings.warn(..., stacklevel=2)` for the TS `console.warn`s, with the same text. Import `TreePath` from
  `..tree_path` (`ancestor_at_level` returns a `TreePath`, and `is_ancestor` accepts `TreePath | str`). Drop the "v2 not
  implemented" docstring lines.
- `engine/network.py`: `move_to_index(from_index, to_index)` → `move_item(self.children, …)`. Put `move_item` in
  `engine/_utils.py`.
- `engine/store.py`:

```python
def expand(self, module):
    if not module.expand(): return False
    self.update_layout(); return True                  # calc_flow + layout
def regroup(self, module):
    if not module.regroup(): return False
    self.update_layout(); return True
def move_module(self, module, direction):              # TS moveSelectedModule with the module passed in
    if not module.move(direction): return False
    self.diagram.update_layout(self.options, self.trace)   # NO calc_flow (§5.4); keep update_layout_calls in sync
    self.update_layout_calls += 1
    return True
def reset_layout(self):
    for network in self.diagram.children: network.is_custom_sorted = False
    self.update_layout()
```

- `apply`: add `moveModule`, `resetLayout`, `moduleId` resolution (`network.get_module`). Make a failed
  expand/regroup/move in a replay an error (the harness throws there too).
- `apply_module_level(store, levels) -> list[dict]` (§10.1) and `apply_expand_list` (§10.3). Put them next to the store,
  not in `layout.py`, so the tests can call them directly.

### 13.2 `layout()` (`layout.py:158`)

The order: `set_networks` → `expand=` → `module_level=` → the colour op → `build_geometry`. Validate `module_level` before
building (int ≥ 1, or a sequence of length `num_networks`; `bool` rejected). `module_level=1` (the default) and
`expand=None` must leave v1 geometry identical (test against all v1 fixtures).

### 13.3 Geometry

Fill `ModuleGeometry.level` and `NetworkGeometry.outlines` (§11) from `network.hierarchical_children`. Call it once per
network: the tree is rebuilt on every access, so do not call `.tree` per module. Guard against §8.4: catch the
`RuntimeError`, emit `outlines=()` and a warning (or raise, see Open question 5).

### 13.4 Renderer (`mpl.draw(..., hierarchy=...)`)

- Modes: `"shadow"` (the web default), `"outline"`, `None`. `hierarchy=True` means `"shadow"`. The renderer default is
  Open question 3.
- Shapes are in data units (layout px), like the modules: the shadow shift `offset·(max_level − level)` (default
  `offset=5`) and the outline grow `1 + 2.5·(max_level − level)`. In matplotlib (y flipped, `y ↦ height − y`) the shadow
  moves **right and down** on screen: data `(x + o, height − (y + h) − o)`.
- Shadow: an opaque `Rectangle` in `#a4a4b0` (the white-background composite of §9.3), or `#b6b69f`-derived
  `(73,73,96)/255` at `alpha=0.5`. Both match the web over white. `mix-blend-mode: difference` cannot be done in Agg/PDF
  vector output, so document the deviation over coloured backdrops.
- Outline: a rounded rect (corner radius = outline offset, in data units; with a non-square data aspect use a
  `FancyBboxPatch(boxstyle=f"round,pad=0,rounding_size={o}")` and accept the slight distortion), `fill=False`, edge
  `#b6b69f`, `alpha=0.5`, dotted: `linestyle=(0, (0.01, 2.5))`, `capstyle="round"`, `linewidth` in points (Open question 4).
- Z-order. The web interleaving matters only where shadows overlap modules. Recommended: shadows at `Z_STREAMLINE − 0.5`
  (under the outgoing streamlines, as in the web; over the white background only), outlines at
  `(Z_STREAMLINE + Z_MODULE)/2`. Within each kind draw in BFS order (`OutlineGeometry.order`). Add `outlines` to
  `AlluvialArtists`, with gids `"outline-<network_id>-<path>"`.
- Do not port `dropShadow`.

### 13.5 Tests

Done (2026-10-10); kept as the record of what the tests cover.

- Move `V2_SCENARIOS` into the regular `test_engine_fixture`. Delete `test_v2_operations_not_implemented`. Update
  `test_conftest_helpers.py` (the count and the v2 list), and the README sentence "`colorModule`, the `expand*` scenarios
  … are for v2".
- For macro fixtures, add the algorithm-parity test of §12.1(b).
- Geometry tests: `outlines` vs fixture `hierarchy` (§11). Also check that `module_level=1` reproduces every v1 fixture.

### 13.6 Pitfalls

1. Expand/regroup must snapshot `get_leaf_nodes()` **before** mutating. Iterating the live generator while `update()`
   moves leaves skips leaves.
2. Regroup's sibling filter runs over `network.children` (all modules, current order), not `visible_children`.
3. ~~Keep the `isAncestor` string-prefix semantics.~~ Since fix round WP3 (E2) `isAncestor` checks `parent + ":"` in
   both engines, and `prefix-tree__regroupPrefix*` pin that.
4. ~~`TreePath.level` counts the trailing-`:` phantom element.~~ Since fix round WP3 (E1) it does not, in both engines.
5. `move` uses the identity index (`parent_index`) over **all** children, and the boundary is `len(children) - 1`.
6. `move_module` must not call `calc_flow`. `expand`/`regroup` must not lay out on failure.
7. Look up `moduleIndex` by identity just before each op in `apply_module_level`. Use `eligible()` both for the snapshot
   and for the re-check.
8. `Network.tree` raises on §8.4 states. Never call it inside the layout.

## 14. Open questions

1. **Prefix bug and trailing `:`** (model Q3, README Q10): resolved, both fixed in TS and Python (fix round WP3).
   Was: this note assumes parity (keep both). If a "clean" mode is
   wanted, add it as an explicit option later, and keep the parity default so that the fixtures hold.
2. **Colour vs expand order in `layout()`/`plot()`**: expand first and then colour (sub-modules matched across networks,
   distinct colours), or colour first (sub-modules inherit their parent's colour, which pairs with the outlines)?
   Recommended: expand first. Both are fixture-covered (§12.3).
3. **Renderer default for `hierarchy`**: the web default is `"shadow"`, but over a white background a shadow is just a
   grey offset box, and in print the dotted `"outline"` may read better. Proposal: `hierarchy="shadow"` when any outline
   exists, which is a no-op for v1 geometry.
4. **Outline stroke units**: the web uses 2 layout px. Treat it as a stroke in points (consistent with `linewidth=0.3` for
   modules, e.g. 1 pt), or as data px? The offsets stay in data units either way.
5. **States that crash `Network.tree`** (§8.4, only from input `moduleLevel`s): raise like TS, or emit no outlines plus a
   warning? Only relevant once JSON input with `moduleLevel` is supported.
6. **Invisible modules in `module_level`**: visible-only follows the design and web-user parity. An "all modules"
   variant would make hidden modules uniform too (they can become visible after option changes). Not needed for v2.
7. **A custom module order API** (design.md "IO"): it can only be built from adjacent `move` ops (with the invisible-boundary
   quirk of §5.1). Is a `move=[(network, module_id, "up"|"down"), ...]` list enough for v2?
