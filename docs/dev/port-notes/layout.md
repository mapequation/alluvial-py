# Port note: Layout algorithm

Spec for porting `Diagram.updateLayout` (and everything it calls) from the TypeScript
alluvial engine to the Python package `alluvial`. A Python implementer should be able to
write the layout from this note alone and reproduce the TS geometry to float tolerance
(ideally bit-for-bit).

> **Erratum (0.5, fix round WP7: E7, E10).** (a) Pass 1 writes `index` for the visible modules in drawn order also
> when `isCustomSorted` is set (no stale `index`), and sets the `margin` of every invisible module to 0 before the
> cap, so a stale margin is no longer rescaled on every call (their rects stay stale). (b) The branch sort comparator
> is tie-safe (`a === b ? 0 : a - b`): two `-Infinity` keys compare equal explicitly instead of through `NaN`. Same
> order as before (and as the Python key sort); Step 5 and Step 7 below describe the old behaviour.

**Citation convention.** `file:line` paths are relative to
`packages/alluvial-diagram/src/` in the TS repo (`web/alluvial`), except paths starting
with `apps/`, which are relative to the TS repo root.

**Related notes (owned elsewhere).** Tree construction (`LeafNode.add/remove`, streamline-node
ids, linking, swap-remove) decides the *children orders* that the layout iterates. Getting
those orders right is a prerequisite for exact sums and tie-breaks here. Streamline paths
(`StreamlineLink`) and `getLinks` only read the geometry that this note produces.

---

## 1. Coordinate system and output

- Uses SVG coordinates. `y` grows downward and `y = height` is the **bottom** of the diagram.
  The layout stacks from the bottom up, so the first module in sort order is drawn lowest.
- Every node has a `Layout` record `{x, y, width, height}`, defaulting to all zeros
  (`alluvial/AlluvialNode.ts:4-35`). Here `y` is the **top** edge of the rectangle.
- The layout writes the following (verified by running the TS engine, see §10):
  - `Diagram`: `width`, `height`, `flowThreshold` (the fraction) (`alluvial/Diagram.ts:150-152`).
    `x`/`y` stay 0.
  - `Network`: layout, `flowThreshold` (absolute), `children` order (reassigned to a new array).
  - Visible `Module`: layout, `margin`, `index` (only when `!isCustomSorted`), `children`
    (group) order.
  - `HighlightGroup`, `Branch`, `StreamlineNode` of visible modules: layout.
  - Every `Branch` (including those in invisible modules): `children` order.
- Invisible modules and their subtrees get **no** new layout and no new `index`. They keep
  whatever they had before: all zeros on a fresh diagram, or stale values from a previous
  call. Their (stale) `margin` *is* multiplied by the cap scale in Step 5 (harmless, never read
  while invisible, but visible in a full-state dump).
- The order of `diagram.children` (networks) is never changed by the layout.

## 2. Data model the layout needs

Depth constants: ROOT 0, NETWORK 1, MODULE 2, HIGHLIGHT_GROUP 3, BRANCH 4, STREAMLINE_NODE 5,
LEAF_NODE 6 (`alluvial/Depth.ts:3-9`). Sides: LEFT = -1, RIGHT = 1 (`alluvial/Side.ts:3-4`).

| Class | Fields used by layout | Source |
|---|---|---|
| Diagram | `children: Network[]` (input order), `width`, `height`, `flowThreshold` (stores the *fraction*) | `alluvial/Diagram.ts:93-103,150-152` |
| Network | `children: Module[]`, `flow`, `flowThreshold` (absolute flow; init 0), `isCustomSorted` (init false), `numLeafNodes` | `alluvial/Network.ts:41-42,248-266` |
| Module | `path: number[]` (= `moduleId.split(":").map(Number)`), `moduleId`, `children: HighlightGroup[]`, `flow`, `margin` (init 0), `index` (init = creation index), `isVisible`, `highlightIndex`, `meanNodeId` | `alluvial/Module.ts:14-29,124-169` |
| HighlightGroup | `highlightIndex` (−1 = not highlighted), `insignificant: bool`, `children = [left Branch, right Branch]` (fixed order) | `alluvial/HighlightGroup.ts:7-31,37-43` |
| Branch | `side`, `isLeft`, `children: StreamlineNode[]` | `alluvial/Branch.ts:8-22` |
| StreamlineNode | `children: LeafNode[]`, `link`, `opposite`, `oppositeStreamlinePosition` | `alluvial/StreamlineNode.ts:10-65` |
| LeafNode | `flow` (0 when `visible == false`), `nodeId` | `alluvial/LeafNode.ts:67-69` |

### 2.1 Derived quantities (exact definitions)

- `flow` on every non-leaf node is a **stored** value written by `calcFlow` (§3). Do not
  recompute it lazily, because that can change the summation order.
- `childFlow(node) = reduce(children, (tot, c) => tot + c.flow, 0)`, a left-to-right sum
  starting at `0` (`alluvial/AlluvialNode.ts:135-137`).
  - Override: `HighlightGroup.childFlow = left.childFlow` (`alluvial/HighlightGroup.ts:53-55`).
    The right branch is ignored.
  - `LeafNode.childFlow = flow` (`alluvial/LeafNode.ts:83-85`).
- `numLeafNodes(node) = reduce(children, (n, c) => n + c.numLeafNodes, 0)`
  (`alluvial/AlluvialNode.ts:128-133`). Overrides:
  - `StreamlineNode.numLeafNodes = children.length` (`alluvial/StreamlineNode.ts:27-29`).
  - `HighlightGroup.numLeafNodes = left.numLeafNodes` (`alluvial/HighlightGroup.ts:49-51`).
  - Hence `Network.numLeafNodes` counts the leaves of **all** modules, visible or not,
    including leaves hidden by `visible = false`.
- `Module.isVisible = flow >= network.flowThreshold && flow > 0` (`alluvial/Module.ts:124-126,180-182`).
- `Module.highlightIndex = largestGroup.highlightIndex`. The largest group is found with
  `reduce` starting from `{flow: -Infinity, highlightIndex: -1}` and a strict `>`, so the
  **first** group with the maximum flow in the current `children` order wins
  (`alluvial/Module.ts:148-150,195-202`). When it is read as a sort key (Step 4, network
  callback) the module's groups have **not yet** been re-sorted in this pass (that happens
  later, in the module callback). "Current order" is therefore creation order on a fresh
  diagram, otherwise the order left by the previous layout. Ties between equal-flow groups
  are decided by that order.
- `Module.meanNodeId` is the mean of `nodeId` over `leafNodes()`, or `-1` if there are none
  (`alluvial/Module.ts:160-169`). Iteration order is groups → left branch → streamline nodes
  → leaves (`alluvial/HighlightGroup.ts:57-59`). The sum is exact for integer ids
  (< 2^53), so the order does not matter. `nodeId` is the parsed `node.id`
  (`alluvial/LeafNode.ts:46`). For state networks that is the **physical** id; `stateId` is a
  separate field and is not used here.
- `StreamlineNode.oppositeStreamlinePosition`
  (`alluvial/StreamlineNode.ts:45-58`):

  ```ts
  group = opposite?.getAncestor(HIGHLIGHT_GROUP)
  if (group && group.parent && group.parent.isVisible) return -group.y
  return -Infinity            // dangling, or opposite module is invisible
  ```

## 3. Call protocol and options

The store's `updateLayout()` (`store/DiagramStore.ts:485-490`) does the following:

```ts
if (diagram.children.length === 0) return;
diagram.calcFlow();
diagram.updateLayout(this);   // the store object itself is the LayoutOpts
```

`setNetworks` builds `new Diagram(networks)` and calls `updateLayout()` exactly once
(`store/DiagramStore.ts:217-234`). Before building, `checkColors` may write
`node.highlightIndex` into the input nodes from `node.color` (`store/DiagramStore.ts:180-205`),
so colours can enter at **build time**. Every layout option setter calls `updateLayout()` again
(`store/DiagramStore.ts:245-337`; `setStreamlineThreshold` too, although the layout ignores it).
Other callers:

- `setShowBipartiteNodes` flips `leaf.visible` and then calls `updateLayout()`
  (`store/DiagramStore.ts:415-424`).
- Every colouring operation mutates the tree via `Module.setColor` → `leaf.update()`
  (remove + re-add, `alluvial/Module.ts:283-288`, `alluvial/LeafNode.ts:196-199`) and then
  calls `updateLayout()` (`store/DiagramStore.ts:559-976`). See §7 for the order side effects.
- `moveSelectedModule` calls `diagram.updateLayout(store)` **without** `calcFlow`
  (`store/DiagramStore.ts:500-511`). Flows are unchanged by a move, so this is harmless.

`calcFlow` (`alluvial/Diagram.ts:121-128`) runs a post-order traversal over nodes with
`depth < LEAF_NODE` (leaves are skipped) and sets `node.flow = node.childFlow`. The order is:
streamline node, then branch, then group, then module, then network. It visits every module,
visible or not. The Diagram's own `flow` is not set.

### 3.1 LayoutOpts and defaults

The `LayoutOpts` interface is at `alluvial/Diagram.ts:17-28`. Defaults come from the
`DiagramStore` fields (`store/DiagramStore.ts:81-96`). `Diagram.updateLayout` itself has
destructuring fallbacks only for `verticalAlign = "bottom"`, `moduleSize = "flow"` and
`sortModulesBy = "flow"` (`alluvial/Diagram.ts:137-139`, applied only when the field is
`undefined`). The other six fields have **no** fallback when `Diagram.updateLayout` is
called directly: a missing numeric field gives `NaN` arithmetic (a missing `flowThreshold`
makes every threshold `Infinity`, so every module is invisible), and a missing `zeroMargins`
acts as `false`. The Python `LayoutOptions` should carry the store defaults for all nine
fields.

Invalid enum values: an unknown `moduleSize` throws `"Module size must be either 'flow' or
'nodes'."` and an unknown `sortModulesBy` throws (only for a network with
`isCustomSorted == false`) from inside the first network callback of pass 1
(`alluvial/Diagram.ts:183-201,388,406-408`). By then `diagram.width/height/flowThreshold`
and every `network.flowThreshold` have already been written. Any `verticalAlign` other than
`"justify"` behaves like `"bottom"` without error. Python should validate all three up front
and raise `ValueError` before mutating anything.

| Option | Type | Store default | Meaning |
|---|---|---|---|
| `height` | number | `600` | Total diagram height (px units) |
| `streamlineFraction` | number | `2` | Gap between networks as a fraction of `moduleWidth` |
| `moduleWidth` | number | `80` | Module bar width |
| `flowThreshold` | number | `5e-3` | Fraction of each network's flow to **hide**, smallest modules first |
| `verticalAlign` | `"bottom" \| "justify"` | `"bottom"` | `"top"` was declared but never implemented (it behaved like `"bottom"`); fix round WP11 (E8) removed it from the TS type |
| `marginExponent` | number | `4` | Margin is `2^(marginExponent - 2*differenceIndex)` |
| `zeroMargins` | bool | `false` | All margins 0 |
| `moduleSize` | `"flow" \| "nodes"` | `"flow"` | Height measure |
| `sortModulesBy` | `"flow" \| "nodes" \| "highlightIndex" \| "nodeId"` | `"flow"` | Module order. The key name is `"nodeId"` (there is no `"meanNodeId"`), but it sorts by `meanNodeId` |

Notes:

- `streamlineThreshold` (default `1`, `store/DiagramStore.ts:87`) is not part of
  `LayoutOpts`. It only filters drawn links (`avgHeight > threshold`, `alluvial/Network.ts:343-351`).
- The web UI sets `flowThreshold = 1 - value/100` for a "Visible flow" slider over 95–100,
  step 0.1 (`apps/web/src/components/Sidebar/Layout.tsx:70`). For example, 99.5 gives
  `0.0050000000000000044`, not `5e-3`.
- The UI slider for `marginExponent` runs over integers −1…6 (`apps/web/src/components/Sidebar/Layout.tsx:55-61`;
  no `step` prop, so the slider default step 1). Its value label showed `2 ** (value - 1)`,
  **half** the actual top-level margin `2 ** value`; fix round WP11 (U1) changed the label to `2 ** value`.
- The UI only toggles between `"bottom"` and `"justify"` (`apps/web/src/components/Sidebar/Layout.tsx:164-167`).
  The `sortModulesBy` options are at `:148`.

## 4. `Diagram.updateLayout`: execution order

Source: `alluvial/Diagram.ts:130-375`. Each step below must run in this order.

### Step 0: early exit

If there are no networks, return without changing anything (`:142-144`).

### Step 1: widths

`alluvial/Diagram.ts:146-152`:

```
streamlineWidth = streamlineFraction * moduleWidth
networkWidth    = moduleWidth + streamlineWidth
totalWidth      = networkWidth * numNetworks - streamlineWidth
diagram.width = totalWidth; diagram.height = height; diagram.flowThreshold = flowThreshold
```

The x of network `k` is built by **repeated addition** (`x = 0; x += networkWidth` once per
earlier network, at `:212` in pass 1 and `:365` in pass 2). It is never `k*networkWidth`.
All modules in a network share that x and the width `moduleWidth`.

### Step 2: visibility threshold per network

The loop is at `:154-156`. `Network.updateFlowThreshold` is at `alluvial/Network.ts:248-266`:

```
maxHiddenFlow = hiddenFlowFraction * network.flow
flows = [m.flow for m in network.children]   # ALL modules, numeric ascending sort
hiddenFlow = 0
network.flowThreshold = +Infinity
for f in flows:
    hiddenFlow += f
    if hiddenFlow > maxHiddenFlow:            # strict
        network.flowThreshold = f
        break
```

Consequences (checked against `alluvial/Diagram.test.ts:44-98` and the probe in §10):

- Module `m` is visible iff `m.flow >= threshold && m.flow > 0`. Every module with flow
  equal to the threshold flow stays visible.
- With `flowThreshold = 0`, the threshold is the smallest positive module flow, so every
  module with positive flow is visible. Zero-flow modules are never visible.
- If the running sum never exceeds `maxHiddenFlow` (fraction clearly > 1, or network flow
  0), the threshold is `Infinity` and **every** module is invisible.
- At fraction **exactly 1** the result depends on rounding: `network.flow` was summed in
  `children` order (in `calcFlow`), the running sum here in ascending order. Probe: three
  single-leaf modules with flows `.3, .2, .1` (creation order) give `network.flow = 0.6`, but
  the ascending sum is `0.6000000000000001 > 0.6`, so the threshold is `0.3` and the largest
  module stays **visible**. Python reproduces this only if both sums use the same orders. The
  UI cannot reach this (slider minimum 95 % visible → fraction ≤ 0.05).
- The sort is ascending numeric. The summation order is that sorted order (ties don't
  matter for the sum).

### Step 3: global normaliser and size/order functions

`maxNetworkFlow = Math.max(...networks.map(n => n.flow))` (`:161-163`). This is the
largest network flow across **all** networks, so smaller networks are drawn shorter.

Size function, set per network (`:378-390`):

```
"flow":  size(node) = node.flow / maxNetworkFlow
"nodes": size(node) = node.numLeafNodes / network.numLeafNodes   # network = the node's own network
```

- `network.numLeafNodes` is read once, when the size function is built (destructured at
  `alluvial/Diagram.ts:378-381`). It is an integer, so this has no float consequences.
- In `"nodes"` mode `maxNetworkFlow` is not used. Each network is normalised by its **own**
  leaf count (hidden bipartite leaves included), so every network's modules sum to 1 and
  networks of different size are drawn equally tall. Pass 2 uses `usableHeight`, so a network
  whose modules are all visible fills `usableHeight + its own margins`.
- `node` here is a module, group, branch or streamline node. `node.flow` is always the
  **stored** value from `calcFlow`.

Order key, used only for the module sort in pass 1 (`:392-410`):

```
"flow":           node.flow / maxNetworkFlow
"nodes":          node.numLeafNodes / network.numLeafNodes
"highlightIndex": -node.highlightIndex          (Module.highlightIndex, §2.1)
"nodeId":         node.meanNodeId
```

The tree sort is **descending** by key (§5). In effect:

- `flow` and `nodes`: largest first, so the largest module sits at the bottom.
- `highlightIndex`: ascending highlight index. Un-highlighted modules (−1) come first,
  at the bottom.
- `nodeId`: **largest** mean node id first, at the bottom. Verified in §10.

Keep the division by `maxNetworkFlow` in the key even though it is monotone. It can make
two near-equal flows tie, and ties then fall back to stable order.

### Step 4: pass 1 (pre-order). Sorts modules and computes provisional positions

Traversal: `forEachDepthFirstPreOrderWhile` (`alluvial/AlluvialNode.ts:209-218`) with the
predicate `depth < MODULE || (Module && isVisible) || HighlightGroup` (`:176-180`).

- The callback runs on a node **before** the node's own children are filtered. So the
  network callback reorders `children`, and the recursion then walks the new order. The
  same holds for the module callback and its group sort.
- Branches are excluded from this pass.
- The callback receives `(node, i, siblingsFiltered)`, where `siblingsFiltered` contains
  only the siblings that passed the predicate.

The state carried between callbacks is `x = 0`, `y = height`, `getNodeSize`, `networkIndex`,
`moduleHeight = 0`, `moduleMargin = 0`, plus the per-network arrays
`totalMargins[N] = 0`, `visibleFlows[N] = 0` and `visibleModules[N] = 0` (`:158-172`).

The equivalent Python for the whole pass (exact op order):

```python
x = 0
y = height
for i, network in enumerate(networks):  # all networks, input order
    # --- Network callback (:182-213)
    size = size_fn(network, max_network_flow, module_size)
    network_index = i
    visible = [m for m in network.children if m.is_visible]
    invisible = [m for m in network.children if not m.is_visible]
    if not network.is_custom_sorted:
        key = order_fn(network, max_network_flow, sort_modules_by)
        # highlightIndex key reads module.highlight_index NOW, i.e. with the module's
        # groups still in their pre-sort order (they are sorted below, per module).
        for idx, m in enumerate(path_tree_sort(visible, key)):  # §5
            m.index = idx
        visible.sort(key=lambda m: m.index)  # == tree order
    network.children = visible + invisible  # new list; invisible keep relative order
    if i > 0:
        x += network_width
    y = height

    mods = visible  # same list the TS recursion filters
    for j, module in enumerate(mods):
        # --- Module callback (:214-236)
        module.children.sort(key=lambda g: (g.insignificant, g.highlight_index))  # stable, in place
        if j + 1 < len(mods) and not zero_margins:
            margin = 2.0 ** (margin_exponent - 2 * difference_index(module.path, mods[j + 1].path))
        else:
            margin = 0
        node_size = size(module)
        module_height = node_size * height
        y -= module_height
        module.margin = margin
        module.layout = (x, y, module_width, module_height)
        module_margin = margin
        y -= margin
        total_margins[network_index] += margin
        visible_flows[network_index] += node_size
        visible_modules[network_index] += 1

        groups = module.children  # sorted above
        for k, group in enumerate(groups):
            # --- HighlightGroup callback (:237-247)
            if k == 0:
                y += module_height + module_margin  # RHS summed first, then added
            group_height = size(group) * height
            y -= group_height
            group.layout = (x, y, module_width, group_height)
            if k + 1 == len(groups):
                y -= module_margin
```

Details that matter:

- **Group order.** Groups are sorted by significant before insignificant, then by
  ascending `highlightIndex`. The comparator is
  `Number(a.insignificant) - Number(b.insignificant)`, falling back to
  `a.highlightIndex - b.highlightIndex` (`:215-221`). The sort is stable and in place, so
  the order persists. The first group goes to the bottom.
- **Margin** (`:222-227`). It uses the *next visible module in the new order*
  (`nodes[i+1]`). The last visible module in a network always gets margin 0.
  - `differenceIndex` (`utils/difference-index.ts:1-7`) is the first index where the paths
    differ, or `0` if one path is a prefix of the other or they are equal.
  - Top-level modules (path length 1, so v1) always give `differenceIndex = 0` and
    `margin = 2^marginExponent`, which is `16` by default.
  - In v2, siblings under the same parent give `2^(e-2)`, and so on.
- **Pass-1 height uses `height`, not `usableHeight`**, and the margins are not yet
  capped. Pass-1 `y` can therefore go negative (seen in §10). Pass-1 positions are
  provisional, but group `y` values feed the streamline-node sort (Step 7). They must be
  computed **exactly**, including the "rewind" `y += moduleHeight + moduleMargin` at the
  first group. That rewind does not necessarily restore the old `y` bit-for-bit.
- After the last group, `y` is re-derived from group heights, not module height:
  `y_after = y_before - Σ group heights - margin`, summed sequentially. The next module
  starts there.
- `isCustomSorted` is only set to true by `Module.move` (`alluvial/Module.ts:294-319`), a
  v2/optional feature. While it is true the visible order is the current `children` order
  and `index` is left stale. `expand`, `regroup` and `resetLayout` set it back to false
  (`alluvial/Module.ts:237,271`, `store/DiagramStore.ts:493-498`).

### Step 5: margin cap (20 % of height)

`:251-275`:

```python
max_total_margin = max(total_margins)  # unscaled; also used by justify
usable_height = height - max_total_margin
max_margin_fraction = 0 if zero_margins else 0.2
margin_fraction = max_total_margin / height
if margin_fraction > max_margin_fraction:
    scale = 0 if zero_margins else (max_margin_fraction * height) / max_total_margin
    for network in networks:
        for module in network.children:  # ALL modules, incl. invisible (harmless)
            module.margin *= scale
    scaled_total_margin = max_total_margin * scale
    usable_height = height - scaled_total_margin  # NOT exactly 0.8*height in floats
```

- The code comment said "below 50%", but the constant is `0.2` (`:254,258`); fix round WP11 (E16) corrected the comment.
- When `zeroMargins` is true every margin is 0, so `0 > 0` is false and the cap is skipped.
- `total_margins` and `max_total_margin` are never rescaled. Justify uses them unscaled.

### Step 6: justify (only when `verticalAlign == "justify"`)

`:277-303`. The pre-order traversal visits networks (index `i` over all networks) and their
visible modules (predicate `:285-287`):

```python
for i, network in enumerate(networks):
    total_margin = total_margins[i]
    num_margins = visible_modules[i] - 1
    visible_flow = visible_flows[i]
    missing_flow = 1 - visible_flow
    missing_margin = missing_flow * usable_height
    for module in [m for m in network.children if m.is_visible]:
        if module.margin > 0:
            module.margin *= max_total_margin / total_margin  # quotient first
            if num_margins > 0:
                module.margin += missing_margin / num_margins
```

- The effect is that every network with **at least two** visible modules fills the full
  `height` up to rounding (top module `y ≈ ±1e-15`, not exactly 0), including networks
  whose total flow is below `maxNetworkFlow`, because `missing_flow` is relative to the
  largest network. A network with one visible module gets no margin to stretch and stays
  bottom-aligned. Verified in §10.
- In `"nodes"` mode `visible_flows` holds leaf-count fractions, so `missing_flow` is the
  fraction of the network's own leaves that sit in invisible modules.
- The last module (margin 0) is untouched, so there is no division by zero for a network
  with one visible module.
- When `zeroMargins` is true nothing happens.
- `"bottom"` and `"top"` skip this step.

### Step 7: sort streamline nodes inside every branch

`:305-315`. A pre-order traversal with `depth <= BRANCH` visits **every** module, visible or
not:

```python
for network in networks:
    for module in network.children:
        for group in module.children:
            for branch in group.children:  # [left, right]
                branch.children.sort(key=lambda sn: sn.opposite_streamline_position)
```

- The sort is ascending by `-group.y` of the opposite group, using **pass-1** `y` values
  from Step 4. The opposite group that sits lowest on screen (largest `y`) comes first and
  is stacked first, at the bottom.
- `-Infinity` (dangling, or opposite module invisible) sorts first, so those streamline
  nodes sit at the **bottom** of the branch.
- Ties keep the current order (stable): insertion/swap-remove order on a fresh diagram,
  otherwise the order this sort left in the previous call.
- `isVisible` of the opposite module is evaluated live, with this call's thresholds. A
  visible opposite group always has a fresh pass-1 `y` from this call. `-group.y` is `-0.0`
  when `y == 0`; it compares equal to `0.0` in both languages.
- JS compares `-Infinity - -Infinity = NaN`. Per the ECMAScript `SortCompare` rule, a NaN
  comparator result counts as `+0`. That is equivalent to a key sort where `-inf == -inf`.
  This was verified on Node v24 with mixed finite and `-Infinity` arrays: the result is
  stable.
- This sort happens **after** `calcFlow`. Branch and streamline-node `flow` values were
  therefore summed in the *pre-sort* order, while pass-2 stacking uses the *post-sort*
  order.

### Step 8: pass 2 (post-order). Final positions

`:317-372`. The post-order traversal (`alluvial/AlluvialNode.ts:220-229`) uses the
predicate `depth !== MODULE || (Module && isVisible)`. It visits all networks, visible
modules, and all groups, branches, streamline nodes and leaves under them. Leaves do
nothing.

```python
x = 0
y = height
for network in networks:
    size = None  # TS: getNodeSize = null; set lazily (:328-338)
    for module in [m for m in network.children if m.is_visible]:
        for group in module.children:
            for branch in group.children:  # left first, then right
                for sn in branch.children:  # Step-7 order
                    if size is None:
                        size = size_fn(network, max_network_flow, module_size)
                    node_height = size(sn) * usable_height
                    y -= node_height
                    sn.layout = (x, y, module_width, node_height)
                branch_height = size(branch) * usable_height
                branch.layout = (x, y, module_width, branch_height)
                if branch.is_left:
                    y += branch_height  # rewind: right branch restacks from ~same base
            group.layout = (x, y, module_width, size(group) * usable_height)
        # module callback (after all its groups)
        module.layout = (x, y, module_width, size(module) * usable_height)
        y -= module.margin  # capped/justified margin
    network.layout = (x, 0, module_width, height)
    x += network_width
    y = height
```

The `module.layout` line runs once per module, after all of its groups. The TS guards
(`&& getNodeSize`) never fire for a visible module. A visible module has at least one
group, and every group's left branch holds at least one streamline node, because each leaf
is attached to one left and one right streamline node. Computing `size` at network start is
therefore equivalent.

Resulting invariants and quirks:

- A streamline node's `y` is the top of its slice. Streamline nodes in a branch stack
  bottom-up in branch order.
- A left branch's `y` is the top of its left stack. A right branch's `y` is the top of its
  right stack.
- A group's `y` is the top of its **right** stack, so a group's `y` equals its right
  branch's `y`.
- A module's `y` is the top of its last group's right stack. It is **not**
  `bottom - module.height`. Heights come from `module.flow`, positions from
  streamline-node sums. They agree only up to rounding.
- A branch's height uses `branch.flow`, which can differ from the sum of its streamline
  nodes in the last ulp (different summation orders). The right branch is never used for
  group or module flow.
- The network layout is `(x, 0, moduleWidth, height)`.
- The `node instanceof Diagram` branch (`:368-370`) is **dead code**: the visitor only
  calls back on descendants. The Diagram's layout is `x = y = 0` (defaults) plus
  `width = totalWidth` and `height` from Step 1, which gives the same result.

## 5. Path-tree module sort (`utils/Tree.ts`)

This is used only in Step 4. It builds a trie keyed on `module.path` segments
(`utils/Tree.ts:24-44`):

```python
class TNode: path, size = 0, nodes = []          # nodes: TNode | Module, insertion order
root = TNode(0)
for m in visible:                                # current children order
    parent = root
    for seg in m.path:                           # numbers
        node = first TNode in parent.nodes with node.path == seg, else new TNode(seg) appended
        node.size += key(m)                      # key called once per segment; accumulates from 0
        parent = node
    parent.nodes.append(m)
```

Sort and flatten (`utils/Tree.ts:46-66`). At every level, `nodes` is sorted stably and
**descending** by `size`, where a non-TNode item counts as size `0` (comparator
`sb - sa`). The sort recurses into TNodes. `flatten` is a pre-order concatenation that emits
modules in sorted order.

- v1 (all paths have length 1): the root holds one TNode per module with
  `size == key(module)` exactly. The result is the visible modules sorted stably by key,
  descending. Ties keep the current `network.children` order: creation order on a fresh
  diagram, otherwise the order left by the previous layout.
- v2: sub-modules of one parent stay contiguous. Parents are ordered by the sum of their
  children's keys, accumulated in insertion order.
- Segments are compared with numeric `===` (`module.path` is `moduleId.split(":").map(Number)`,
  `utils/TreePath.ts:157-159`; `moduleId` never contains `;` because `TreePath` normalises
  insignificant paths to `:`-joined form, `utils/TreePath.ts:26-38`). Use `int` segments in
  Python.
- A module item and TNodes only share a level if one module's path is a strict prefix of
  another's. That cannot happen in v1, and `expand` refuses it in v2 (`alluvial/Module.ts:221-230`).
  If it ever did, the module (size 0) would sort **before** TNodes with negative size, which
  is possible with the `highlightIndex` key (`-hi < 0`).
- Python equivalent: `nodes.sort(key=lambda n: n.size if isinstance(n, TNode) else 0, reverse=True)`.
  `reverse=True` keeps stability (verified). Finite `sb - sa` is sign-exact (IEEE with
  subnormals). For `±inf` ties JS gets NaN, which counts as 0, which matches equal keys.

## 6. Label positions

`Module` getters (`alluvial/Module.ts:74-114`), with `x1 = x` and `x2 = x + width`.
"First" and "last" refer to the module's **network** position in `diagram.children`
(`alluvial/AlluvialNode.ts:112-122`):

```
textOffset = 15 + 5   # = 20 (constant)
namePosition.x = x1 - 20          if network is first child      (checked first)
               = x2 + 20          elif network is last child
               = (x1 + x2) / 2    otherwise
namePosition.y = y + height / 2
textAnchor     = "end" | "start" | null   (same three cases)
idPosition     = ((x1 + x2) / 2, y + height / 2)
```

- With a single network both checks are true, and "first" wins: the label goes left with
  anchor `end` (verified, §10).
- Middle networks have `textAnchor = null`, and their module names are **not rendered**
  (`react/Module.tsx:135`).
- Module ids are shown only if `showModuleId` is set (default false). They use anchor
  `middle`, weight 600, `dy = actual/3` (the *actual* font size below, not the option),
  and a white halo `stroke = hsla(0,0%,100%,0.8)` with `strokeWidth = max(actual/5, 1)`
  (`react/Module.tsx:69-70,109-133`).
- Names are drawn only if `showModuleNames` (default true) and `textAnchor != null`, with
  `dominant-baseline: middle` (`react/Module.tsx:135-164`).
- Labels and positions use the **pass-2** module layout (`y`, `height = size*usableHeight`).

Font size (`react/Module.tsx:63-70`): `fontSize` defaults to 8 and `adaptiveFontSize` to
false.

```
adaptive = 1 + Math.round(min(fontSize, module.height))
actual   = adaptive if adaptiveFontSize else fontSize
```

`Math.round` rounds half up (toward +∞). In the name-text rules below, `fontSize` means
`actual`.

Name text (`react/Module.tsx:135-254`). If `module.name` is set it is used. Otherwise the
largest leaves are shown with `dominant-baseline: middle`, and with
`multilineModuleNames` (default true):

```
maxLines = ceil(module.height / (fontSize * 1.8)); if maxLines == 0: no text
if maxLines is even: maxLines -= 1
names = module.getLargestLeafNodes(maxLines, aggregateStateNames)   # descending flow
mid = ceil(len(names) / 2)
# Top-to-bottom visual order: names[0], names[1], ..., names[mid-1] (on the centre line), names[mid], ...
# The first half is emitted reversed with dy 0, then -1.2em each.
# The second half starts at dy = mid*1.2em, then +1.2em each (all x = 0, relative to namePosition).
```

The single-line variant joins the top 5 names with `", "`. `getLargestLeafNodes` is in
`alluvial/Module.ts:45-72` and `utils/PriorityQueue.ts`. On ties the earlier leaf wins,
because insertion requires a strictly larger flow and the internal sort is stable. The
result equals `sorted(leaves, key=lambda l: l.flow, reverse=True)[:n]` (stable), with leaves
in `module.leafNodes()` order (groups → left branch → streamline nodes → leaves) and
`leaf.flow` (0 for hidden leaves). With aggregation (`aggregateStateNames`, default true),
flows are summed per physical `nodeId` in first-seen order, and the entry keeps the first
leaf's `name`. `titleCaseModuleNames` (default false) title-cases the lower-cased name.

Network name (`alluvial/Network.ts:201-206`):
`x = network.x + network.width / 2` and `y = (network.height + 15) + 5`, which is
`height + 20`. It is rendered with anchor `middle` and `dy = networkFontSize` (default 10)
(`react/Network.tsx:33-52`).

SVG framing (only for SVG parity, not geometry): the content is translated by
`x = max((svgW - diagram.width)/2, minMargin) + offsetX` and
`y = max((svgH - diagram.height)/(centerVertically ? 2 : 3), minMargin) + offsetY`, with prop
defaults `minMargin = 100`, `offsetX = offsetY = 0`, `centerVertically = false`
(`react/Diagram.tsx:45-48,102-107`).

## 7. Iteration order, tie-breaking and persistence

- **Network order:** input order (`alluvial/Diagram.ts:100-102`).
- **Module order before the first layout:** creation order, i.e. the first leaf
  (in input node order) whose `moduleId` is new (`alluvial/Network.ts:273-283`,
  `alluvial/LeafNode.ts:120-123`). `Module.index` is initialised to the creation index
  (`alluvial/Module.ts:29`).
- **Group order before sorting:** creation order (`alluvial/LeafNode.ts:125-127`).
- **Branch children (streamline nodes):** insertion order, modified by swap-remove. Removal
  overwrites the slot with the last element and pops (`alluvial/AlluvialNode.ts:149-158`;
  used via `alluvial/LeafNode.ts:286` when a streamline node empties). This happens during
  the initial build too, when a leaf's opposite node is moved
  (`alluvial/LeafNode.ts:157-187`). It determines the stable tie order in Step 7 and the
  `calcFlow` summation order.
- **Leaves inside a streamline node:** swap-remove with index bookkeeping
  (`alluvial/StreamlineNode.ts:97-109`). This only affects summation order.
- **Recolouring mutates orders too (v1 colours).** `Module.setColor` runs `leaf.update()`
  (= `remove()` + `add()`) on every leaf (`alluvial/Module.ts:283-288`,
  `alluvial/LeafNode.ts:196-231`). That swap-removes emptied streamline nodes, emptied groups
  (`module.removeChild`) and emptied modules (`network.removeChild`, also swap-remove,
  `alluvial/Network.ts:291-295`), then re-creates/appends them. A single-leaf module is
  therefore **replaced by a new `Module` object appended at the end** of `network.children`
  (fresh `margin = 0`, zero layout, `index = len-1`). This changes stable tie order.
  Probe (TS, `height=100, moduleWidth=10, marginExponent=2, flowThreshold=0`): A with nodes
  `(4,"3:1",.4) (1,"1:1",.3) (3,"1:2",.1) (2,"2:1",.2)` lays out as modules `[3, 1, 2]`
  (3 and 1 tie at 0.4). After `getModule("3").setColor(0)` + `calcFlow` + `updateLayout` it is
  `[3, 1, 2]`. So "colour at build time" and "colour after build" are **not** equivalent
  in TS. **Decided by the fixture suite:** every coloured fixture (`*__colored`,
  `*__nameColored`, `planted-ftree__colorModuleIds/colorNodes/colorModule/coloredSortHighlightIndex`)
  uses the colour-after-build path (real store ops, `tools/ts-fixtures/README.md`). The Python
  colour ops must therefore port `Module.setColor` → `LeafNode.update()` literally (model note §5.3-5.4).
  Build-time `highlightIndex` (input records, `checkColors`) stays supported, but it is a different
  code path with different tie orders.
- **`updateLayout` mutates persistent state:** `network.children` (reassigned),
  `module.children` and `branch.children` (sorted in place), `module.index` and
  `module.margin`. A *second* `calcFlow` + `updateLayout` therefore sums in a different
  order and can differ in the last ulp. Network/module flows can also differ, which can
  even flip exact ties. The Python model must keep the same mutable lists with the same
  lifetime semantics if multi-call parity is wanted.
- **All sorts are stable comparator sorts.** JS `Array.prototype.sort` is stable, and NaN
  counts as 0. Python `list.sort(key=...)` with the keys given above reproduces them
  exactly.

## 8. Edge cases

| Case | Behaviour (source) |
|---|---|
| 0 networks | Return immediately. Nothing is written (`alluvial/Diagram.ts:144`) |
| 1 network | `totalWidth = networkWidth*1 - streamlineWidth`, which equals `moduleWidth` only up to rounding for non-integer inputs (use the same expression). Every streamline node is dangling (`-inf`), so branch order is unchanged. Labels go left with anchor `end` |
| Zero-flow module | Never visible (`flow > 0`). Keeps its old/zero layout |
| All networks have flow 0 | `maxNetworkFlow = 0`. No visible modules, so no division is ever evaluated. Network layouts are still written |
| `flowThreshold > 1` | Threshold is `Infinity`. All modules invisible. `max(total_margins) = 0`. Only network layouts are set |
| `flowThreshold == 1` | Rounding-dependent (Step 2): the largest module(s) may stay visible |
| Invisible module | Not sorted (stays after the visible ones in prior relative order) and not positioned. Its margin is still scaled by the cap. Its branches are still sorted (Step 7). Streamline nodes in visible neighbours that point at it get `-inf`, so they stack at the bottom and **still take height** |
| Dangling streamline node | At most one per branch (dangling id has no target). It gets `-inf` and goes to the bottom of its branch |
| Empty module or group | Cannot exist. They are removed when emptied (`alluvial/LeafNode.ts:217-223`) |
| Zero-flow leaf or group in a visible module | Zero-height rects. Ties in pass-1 `y` are resolved by stable order |
| Network with one visible module | `totalMargin = 0`. Justify doesn't touch it (margin 0) |
| `height == 0` | All heights are `size*0 = 0`. If `maxTotalMargin > 0`, JS gets `x/0 = Infinity > 0.2`, so the cap fires with `scale = (0.2*0)/maxTotalMargin = 0`: every margin becomes 0 and `usableHeight = 0`, so everything sits at `y = 0` (verified by probe). If `maxTotalMargin == 0`, `0/0 = NaN` and the cap is skipped. Python raises `ZeroDivisionError` in both cases, so reject `height <= 0` |
| Hidden (bipartite) leaves | `flow` reads as 0 but they still count in `numLeafNodes` (`"nodes"` mode) |

## 9. v1 vs v2

| Feature | Scope | Notes |
|---|---|---|
| Steps 0–8 with path length 1, `isCustomSorted = false` | **v1** | |
| `moduleSize` flow/nodes; `sortModulesBy` flow/nodes/nodeId | **v1** | |
| `sortModulesBy = "highlightIndex"` | **v1** | Colours are in v1 via `highlightIndex`. Only meaningful once colours exist |
| Group ordering (insignificant, highlightIndex) | **v1** | `.stree`/`.tree` paths ending in `;` produce insignificant groups. Colours give highlight groups |
| `verticalAlign` bottom/justify; `zeroMargins`; margin cap | **v1** | |
| Label positions (§6); renderer offsets | **v1** | Text content and multi-line placement belong to the renderer |
| Hierarchical modules: path length > 1, `differenceIndex` > 0, `expand`/`regroup` (`alluvial/Module.ts:212-281`) | **v2** | Layout code is identical; only paths and tree build change |
| `Network.tree` / `hierarchicalChildren` bounding boxes for shadow/outline super-modules (`alluvial/Network.ts:212-246,367-454`; render offsets `react/HierarchicalModule.tsx:12,51`) | **v2** | Computed from pass-2 module layouts. In v1, `hierarchicalChildren` equals `visibleChildren` order |
| `Module.move` / `isCustomSorted` manual order | v2 / optional | |
| Highlight-groups API (multiple groups per module) | **v2** | The layout already handles it. Only the API is missing |

v2 `TreeNode.updateLayout(module)` (`alluvial/Network.ts:433-453`) runs on each ancestor
TreeNode, from the leaf TreeNode's parent up to the root. The leaf TreeNode itself keeps
its defaults and is never yielded.

```
x = module.x; width = module.width; y = min(y, module.y)            # y starts +inf
if module.y > maxY: maxY = module.y; maxHeight = module.height;
                    height = max(height, |y - module.y| + module.height)
else:               height = max(height, |y - maxY| + maxHeight)
```

The outline offset is `1 + 2.5*(maxModuleLevel - moduleLevel)`. The shadow offset is
`hierarchicalModuleOffset (5) * (maxModuleLevel - moduleLevel)`.

## 10. Worked example: TS output, use as the first unit test

How it was produced: a vitest probe living in a scratch directory, run with the TS repo's
`node_modules/.bin/vitest --root <scratch>`. It imported `alluvial/Diagram.ts` by absolute
path. Nothing was written to the TS repo. The steps were `new Diagram(nets)`, `calcFlow()`,
`updateLayout(opts)`. Each node had `identifier = String(id)` and `name = String(id)`.

All numbers below were re-run (vitest probe, TS engine unchanged) and are printed with JS
`String(number)`, i.e. shortest round-trip repr, which equals Python `repr(float)`. Compare
exactly. The input `NetworkFile`s were minimal: `{id, name, nodes: [{id, path, flow, name,
identifier, highlightIndex?}]}`. "Module k" means `moduleId == "k"`, not node id.

### 10.1 Example 1 (base)

Options: `height=100, moduleWidth=10, streamlineFraction=2, flowThreshold=0,
marginExponent=2, zeroMargins=false, moduleSize="flow", sortModulesBy="flow",
verticalAlign="bottom"`.

Input (node id, path, flow), in input order:

- A: `(1,"1:1",.3) (2,"2:1",.2) (3,"1:2",.1) (4,"3:1",.4)` → modules 1 = {1,3}, 2 = {2},
  3 = {4}; creation order `[1, 2, 3]`.
- B: `(1,"2:1",.25) (2,"1:1",.25) (3,"1:2",.1) (5,"1:3",.1)` → modules 2 = {1},
  1 = {2,3,5}; creation order `[2, 1]`.

Results:

- Diagram width 40. Network layouts `(0,0,10,100)` and `(30,0,10,100)`. `A.flow = 1`,
  `B.flow = 0.7`. Module 1 of B has `flow = 0.44999999999999996`.
- Thresholds: A = 0.2, B = 0.25.
- Total margins A = 8, B = 4. No cap. `usableHeight = 92`.
- Module order: A `[1, 3, 2]` (1 and 3 tie at 0.4; creation order), B `[1, 2]`.
  `index` = position.
- Network A:
  - Module 1: `y = 63.2, h = 36.800000000000004`, margin 4. Its left branch
    `y = 63.199999999999996` (one dangling SN). Its right branch `y = 63.2` with SNs
    `[→B1 y 90.8 h 9.200000000000001, →B2 y 63.2 h 27.599999999999998]`.
  - Module 3: `y = 22.4, h = 36.800000000000004`, margin 4.
  - Module 2: `y = -3.552713678800501e-15, h = 18.400000000000002`, margin 0.
  - Module 1 name position `(-20, 81.60000000000001)`, anchor `end`.
- Network B:
  - Module 1: `y = 58.6, h = 41.4`, margin 4. Its left branch `y = 58.599999999999994`,
    SNs `[dangling y 90.8 h 9.200000000000001, →A1 y 81.6 h 9.200000000000001,
    →A2 y 58.599999999999994 h 23]`. Its right branch `y = 58.6` (one dangling SN).
  - Module 2: `y = 31.6, h = 23`, margin 0.
  - Name positions `(60, 79.3)` and `(60, 43.1)`, anchor `start`.
- Network name positions `(5, 120)` and `(35, 120)`.
- Same input with `verticalAlign="justify"`: A is unchanged (`missingFlow = 0`, ratio 1).
  B module 1 margin = `4*(8/4) + (0.30000000000000004*92)/1 = 35.60000000000001`; B module 2
  then has `y = -7.105427357601002e-15`, `h = 23`. B module 1 is unchanged.
- Same input with `height=0`: every `y` and `h` is 0, every margin 0, network names at
  `y = 20`.

### 10.2 Example 2 (cap, invisible module, multiple groups, sort modes)

Base options as in 10.1, but `marginExponent=4, flowThreshold=0.06`. Input:

- A: `(1,"1:1",.3,hi=0) (2,"2:1",.2) (3,"1:2",.1) (4,"3:1",.4) (6,"4:1",.05) (8,"1;3;",.05)`.
  Node 8's path ends in `;`, so it is insignificant. Module 1 has groups in creation order
  `[hi0, hi-1, insignificant hi-1]`.
- B: `(1,"2:1",.25) (2,"1:1",.25) (3,"1:2",.1) (5,"1:3",.1) (6,"1:4",.05) (8,"2:2",.05)`.

Results with `sortModulesBy="flow"`:

- `A.flow = 1.1`, `B.flow = 0.7999999999999999`, `maxNetworkFlow = 1.1`. Thresholds A = 0.2
  (module 4, flow 0.05, invisible), B = 0.3.
- Total margins A = 32, B = 16. `32/100 > 0.2`, so scale = 0.625, visible margins become 10,
  `usableHeight = 80`.
- A order `[1, 3, 2, 4]` (4 invisible, layout stays `(0,0,0,0)`, `index = 3` from creation).
  - Module 1: `y = 67.27272727272727, h = 32.72727272727273`, margin 10. Groups (sorted
    significant first, then highlightIndex) bottom-up:
    `hi-1 y 92.72727272727272 h 7.272727272727273`,
    `hi0 y 70.9090909090909 h 21.818181818181817`,
    `insignificant y 67.27272727272727 h 3.6363636363636367`.
  - Module 3: `y = 28.181818181818173, h = 29.090909090909093`.
  - Module 2: `y = 3.636363636363626, h = 14.545454545454547`, margin 0.
- B order `[1, 2]`.
  - Module 1: `y = 63.63636363636364, h = 36.36363636363636`, margin 10. Left branch SNs
    bottom-up: `[dangling y 92.72727272727272 h 7.272727272727273,
    →A4 (invisible, -inf) y 89.09090909090908 h 3.6363636363636367,
    →A1 y 81.81818181818181 h 7.272727272727273,
    →A2 y 63.63636363636363 h 18.18181818181818]`. The two `-inf` SNs keep their insertion
    order, and the SN linked to the invisible module still takes height.
  - Module 2: `y = 31.818181818181824, h = 21.818181818181817`. Left branch SNs
    `[→A1 hi0 y 35.45454545454546 h 18.18181818181818,
    →A1 insignificant y 31.818181818181824 h 3.6363636363636367]`.
- With `verticalAlign="justify"`: A margins `11.818181818181817` (×2), A module 2
  `y = -3.552713678800501e-15`. B module 1 margin `41.81818181818183`, B module 2
  `y = -3.552713678800501e-15`.
- With `moduleSize="nodes"`: A module 1 `y = 60.000000000000014, h = 40` (3 of 6 leaves × 80),
  module 3 `y = 36.666666666666686, h = 13.333333333333332`, module 2
  `y = 13.333333333333353`. B module 1 `y = 46.666666666666686, h = 53.33333333333333`,
  module 2 `y = 10.000000000000021, h = 26.666666666666664`.
- With `sortModulesBy="highlightIndex"`: A `[2, 3, 1, 4]`. Modules 2 and 3 have key
  `-(-1) = 1` and keep creation order, module 1 has key `-0` because its largest group is
  hi0. B `[2, 1]` (tie, creation order). A module 2 `y = 85.45454545454545`.
- With `sortModulesBy="nodeId"`: mean ids A: 1 → 4, 3 → 4, 2 → 2; B: 1 → 4, 2 → 4.5.
  A `[1, 3, 2, 4]` (tie, creation order), B `[2, 1]` (largest mean at the bottom).
  B module 2 `y = 78.18181818181817`.

## 11. Python port guidance

### Suggested structure

- `alluvial/layout.py` holds:
  - `@dataclass LayoutOptions`, with the §3.1 defaults plus `streamline_threshold=1.0`.
  - `calc_flow(diagram)`.
  - `update_layout(diagram, opts)`.
  - `_size_fn`, `_order_fn`, `_difference_index`, `_path_tree_sort`.

  Write explicit nested loops as in §4. Do not use a generic visitor: the TS visitors'
  "filter after callback" semantics are easy to get wrong.
- `alluvial/labels.py` holds the pure functions `module_name_position`,
  `module_text_anchor`, `module_id_position`, `network_name_position` and
  `multiline_offsets`.
- Model classes (owned by the tree-construction note) must carry the following, using
  mutable Python lists:
  - `children` with TS order semantics.
  - Stored `flow`, set only by `calc_flow`.
  - `layout` with `x, y, width, height`.
  - `Module.margin` and `Module.index`.
  - `Network.flow_threshold` and `Network.is_custom_sorted`.
- Keep TS (SVG, y-down) coordinates in the model and in fixtures. The matplotlib renderer
  flips them, either with `ax.invert_yaxis()` or by mapping `y' = height - y - h`.

### Pitfalls (each one breaks bit-exactness)

1. **Never use `sum()` for flows.** From Python 3.12 the built-in `sum()` over floats uses
   compensated summation (verified on py314: `sum([0.1]*10) == 1.0`, while the JS
   `reduce` gives `0.9999999999999999`).
   - Use `t = 0; for c in children: t += c.flow`.
   - Also avoid `math.fsum` and `numpy.sum` (pairwise summation).
2. **Keep every `y -= …`, `y += …` and `x += network_width`** as sequential updates.
   - Don't recompute positions algebraically: no `x = k*network_width`, no
     `module.y = bottom - h`.
   - Keep the pass-1 rewind `y += module_height + module_margin` with its parentheses.
3. **`a *= b / c`** means `a = a * (b / c)`. Don't rewrite it as `a * b / c`. This applies
   to justify.
4. **Margin power:** use `2.0 ** (e - 2*d)`. It is exact for integer `e`. For non-integer
   `marginExponent`, V8's `**` and C `pow` could in principle differ in the last ulp. Spot
   check (Node v24 vs py314): `2**3.7, 2**-1.3, 2**0.1, 2**4.4` agree bit-for-bit, but this is
   not a proof (open question).
5. **Rounding:** `Math.round` is round-half-up, but Python `round` is banker's rounding.
   Use `math.floor(v + 0.5)`. This matters for the adaptive font size.
6. **Sorting:** use `list.sort(key=…)`. `reverse=True` keeps stability. Group key
   `(insignificant, highlight_index)` relies on `False < True`, which matches
   `Number(bool)`. Branch key `opposite_streamline_position`: `float('-inf')` compares
   equal to itself, so ties stay stable just as with JS NaN→0.
7. **Zero division:** JS yields `Infinity`/`NaN` where Python raises. Every division in the
   layout is reachable only with non-zero denominators for valid inputs, except
   `max_total_margin / height` when `height == 0` (§8), so validate `height > 0`. The justify
   division `max_total_margin / total_margin` is safe because it only runs when
   `module.margin > 0`, which implies `total_margin > 0`.
8. **Visibility depends on per-network `flow_threshold`.** Compute it once per layout
   (Step 2) before any `is_visible` check. `is_visible` must be a live property: it is
   re-evaluated in every pass.
9. **Pass-1 vs pass-2 heights:** pass 1 uses `height` with uncapped margins. Pass 2 uses
   `usable_height` with capped/justified margins. Don't merge the passes.
10. **Branch flows vs streamline-node sums:** read `branch.flow` (from `calc_flow`, pre-sort
    order) for branch heights. Do not re-sum after Step 7.
11. **Fixture protocol** (`tools/ts-fixtures/README.md`, `tests/fixtures/*.json`): replay the
    store call sequence on **one** Python diagram object. That means: build from the files in
    `inputs.files` order, with `inputs.identifier`, network ids `inputs.networkIds` (file stems) and
    names `inputs.networkNames` (basenames). Then run `calc_flow` + `update_layout(inputs.options)`
    once (= `setNetworks`, which also resets `highlightColors` to `[]`). Then run each op in
    `inputs.operations[1:]` in order; each op ends with its own `calc_flow` + `update_layout`
    (`diagram.updateLayoutCalls` is 2 for the coloured fixtures). Orders persist between calls
    (§7), so multi-call parity is **required**, not optional. Coloured fixtures use the
    colour-after-build path (§7), so build-time `highlightIndex` does **not** reproduce them.
12. **Options as floats.** JS numbers are doubles. Python `int` arithmetic gives the same values
    for the small integer options used here, but `2 ** k` returns `int` for `k >= 0` and `float`
    otherwise. Coerce numeric options with `float()` once in `LayoutOptions` so outputs are
    uniformly `float` (JSON fixtures then round-trip identically).
13. **Validate enums up front** (`module_size`, `sort_modules_by`, `vertical_align`) and
    raise before mutating anything (TS throws halfway through, §3.1). Decide whether `"top"`
    is accepted (§12).

### Minimal test list

- §10 examples, compared exactly or within 1e-12.
- Threshold semantics: `alluvial/Diagram.test.ts:44-98`.
- Ties in module flow (stable creation order).
- Cap on and off; justify with networks of unequal total flow.
- `zeroMargins`.
- Single network.
- Invisible-neighbour streamline nodes stacked at the bottom.
- Multiple groups per module (insignificant + highlighted), §10.2.
- `moduleSize="nodes"`; `sortModulesBy` `highlightIndex` and `nodeId` ties (§10.2).
- `flowThreshold=1` rounding case (Step 2) and `flowThreshold > 1` (all invisible).
- `height=0` rejected; invalid enum values rejected without mutation.
- The full fixture suite `tests/fixtures/*.json` (105 scenarios), replayed per pitfall 11.

Spec check (2026-10-10): Steps 2-8 and `getLinks` as written in this note (and in the
streamlines note §5-7) were re-derived from the fixtures' own flows and final orders. The
check covered thresholds, visibility, pass-1 rects, margins, cap, justify, branch-key order,
pass-2 rects, link order and the exact path strings. It matches **all 105 fixtures with exact
float equality**. Module sort keys are monotone in every fixture. Ties occur only in the three
`*__sortNodes` fixtures, where creation order decides. So the remaining parity risk is in what
this note takes as given: the build/update orders (model note) and `calcFlow` summation order.

## 12. Open questions

1. ~~`verticalAlign: "top"` is declared (`alluvial/Diagram.ts:12`) but not implemented; it
   behaves like `"bottom"`. Should Python accept it with TS-identical behaviour, or reject
   it?~~ **Resolved:** Python rejects it, and fix round WP11 (E8) removed it from TS.
2. The option key is `"nodeId"` (sorting by mean node id, **descending**). Should the
   Python API keep the TS name, or expose `"mean_node_id"` with an alias?
3. ~~Do fixtures need to cover multi-call sequences?~~ **Resolved: yes.** Every coloured and
   expand fixture runs 2-3 `calcFlow` + `updateLayout` calls on one diagram, so mutated orders
   must persist across calls (pitfall 11). Option changes after load are still not covered.
4. Is non-integer `marginExponent` in scope? The UI only offers integers −1…6. If it is
   in scope, the parity of `Math.pow` vs C `pow` needs a fixture.
5. Middle-network module names are not drawn in TS (`textAnchor = null`). Should the
   matplotlib renderer match that, or offer centred labels?
6. Is manual module reordering (`Module.move` / `isCustomSorted`) in v1 or v2?
7. Should `streamlineThreshold` (default 1, in layout units) live in `LayoutOptions` or in
   the renderer/link API? Its meaning depends on `height`.
8. ~~Colour path~~ **Resolved:** the colour fixtures exercise the post-build path
   (`Module.setColor` → `leaf.update()`, §7). So the remove/re-add logic (model note §5.4) is
   v1 work. A design that assigns `highlightIndex` before building the tree cannot match
   them.
9. Should Python accept `flow_threshold >= 1`? TS behaviour at exactly 1 is rounding-dependent
   (Step 2). Rejecting `>= 1` (or clamping) diverges from TS only at an input the UI can't
   produce.
