# Port note: Streamline nodes and links

Status: spec for the Python port. You should be able to implement it without reading the TS source.

## Citation conventions

- The TS repo is `web/alluvial`, and it is read-only for this port.
- A bare `File.ts:N` is in `packages/alluvial-diagram/src/alluvial/`.
- Other TS paths are given relative to `packages/alluvial-diagram/src/`, e.g. `react/Network.tsx:25`, `store/DiagramStore.ts:87` and `utils/TreePath.ts:206`.
- Claims marked **[verified]** were checked by running the TS engine from a scratch directory (see "Appendix: probing the TS engine").

## 0. Scope and versioning

| Topic | v1 | v2 |
|---|---|---|
| StreamlineNode / StreamlineLink data model, ids, dangling nodes | yes | |
| Side linking during a **fresh build** (`LeafNode.add`, including its `removeFromSide` call on the neighbour leaf) | yes | |
| Flow sums of streamline nodes and branches (summation order) | yes | |
| Branch-internal sort (opposite position from pass 1) and pass-2 streamline-node heights and y | yes | |
| `Network.getLinks(threshold)`: filter and order | yes | |
| Link path geometry (two cubic Béziers, 1e-6 snapping), JS-compatible number formatting | yes | |
| Link colour inputs (left/right highlightIndex and insignificant) and the renderer's 1 px threshold, gradient, opacity and z-order | yes | |
| **Incremental** relinking (`LeafNode.update` → `remove` + `add`, dangling merge), used by `setColor` (v1 colours) and by `expand`/`regroup` (v2) | yes | (expand/regroup) |
| `transitionPath` (animation-only) | | optional/never |
| `moduleSize = "nodes"` sizing of streamline nodes | yes (fixtures `*__moduleSizeNodes`) | |
| Bipartite `LeafNode.visible` (flow reads 0) | optional | |

In v1, colours are applied **after** the build, through the store's colour ops (`Module.setColor` → `LeafNode.update()`), exactly as in the web app. The fixture suite uses this path (`tools/ts-fixtures/README.md`, coloured scenarios). Build-time per-node `highlightIndex` also exists: `checkColors`, and `moveNetwork` (`store/DiagramStore.ts:517-556`), which writes `highlightIndex`/`moduleLevel` back to the node records and calls `setNetworks`. It gives **different** leaf and streamline-node orders (§3.5), so it cannot replace the update path for fixture parity.

---

## 1. Data structures

### 1.1 Sides (`Side.ts:1-8`)

```
LEFT  = -1
RIGHT = +1
side_to_string(LEFT) = "left", side_to_string(RIGHT) = "right"
opposite(side) = -side
```

`Network.getNeighbor(side)` returns the network at index `networkIndex + side` in `diagram.children`, or `null` when that index is out of range (`Network.ts:301-321`). LEFT therefore means the previous network and RIGHT the next one. `networkIndex` is found by `networkId` equality, not identity (`Network.ts:305-307`).

### 1.2 Tree position

The depths are `Diagram(0) > Network(1) > Module(2) > HighlightGroup(3) > Branch(4) > StreamlineNode(5) > LeafNode(6)` (`Depth.ts:3-9`).

- Every `HighlightGroup` owns exactly two branches, created in its constructor in the fixed order `[Branch(LEFT), Branch(RIGHT)]` (`HighlightGroup.ts:11-14`). `group.left` is `children[0]` and `group.right` is `children[1]` (`HighlightGroup.ts:37-43`).
- `Branch.id` is `"left"` or `"right"` (`Branch.ts:15-18`).
- A `Branch`'s children are `StreamlineNode`s. A `StreamlineNode`'s children are `LeafNode`s.
- **A LeafNode has two parents**, one `StreamlineNode` in its group's LEFT branch and one in its RIGHT branch. They are stored on the leaf (`LeafNode.ts:29-30`). The generic `parent` field of a LeafNode is `null` (`LeafNode.ts:43`, `super(null, ...)`).

### 1.3 `StreamlineNode` (`StreamlineNode.ts:10-131`)

| Field | Meaning | Source |
|---|---|---|
| `parent: Branch` | owning branch | `:17-19` (the constructor also does `parent.addChild(this)`, i.e. **append**) |
| `side: Side` | `= parent.side`, fixed | `:13,20` |
| `sourceId: str` | id part for this end | `:14,21-22` |
| `targetId: str or None` | id part for the far end; `None` = dangling | `:15,24` |
| `link: StreamlineLink or None` | shared link object with the opposite node | `:12` |
| `children: list[LeafNode]` | leaves, in insertion order modified by swap-remove | `AlluvialNode.ts:102` |
| `x, y, width, height` | layout, initialised to 0 | `AlluvialNode.ts:4-8` |
| `flow` | `_flow`, set by `calcFlow` (§4) | `AlluvialNode.ts:92-100` |
| `id` | always `""`, **unused**; identity is `currentId` | `:18` |

The constructor parses `id.split("--")` into `[source, target]` and sets `targetId = target ?? null` (`:21-24`). Only the first two pieces are used (see Q4).

Derived properties:

```
currentId  = sourceId if targetId is None else f"{sourceId}--{targetId}"      # :31-35
oppositeId = f"{targetId if targetId is not None else 'NULL'}--{sourceId}"     # :37-39
isDangling = targetId is None                                                  # :41-43
opposite   = None if link is None else (link.right if link.left is self else link.left)  # :60-65
numLeafNodes = len(children)                                                   # :27-29
```

`oppositeStreamlinePosition` (`:45-58`) is the sort key used in §5.2:

```
def opposite_streamline_position(sn):
    opp = sn.opposite
    if opp is not None:
        group = opp.parent.parent            # getAncestor(HIGHLIGHT_GROUP)
        module = group.parent
        if module is not None and module.isVisible:
            return -group.y                  # group.y as set by layout PASS 1
    return -inf
```

`addChild(leaf)` (`:91-95`) appends the leaf and then records the leaf's index on this node's side:

```
children.append(leaf); leaf.set_index(len(children) - 1, self.side)
```

`removeChild(leaf)` (`:97-109`) is an **O(1) swap-remove using the leaf's stored index**:

```
i = leaf.get_index(self.side)
if 0 <= i < len(children):          # TS: index > -1 && index < length
    children[i] = children[-1]      # last element moves into the hole
    children[i].set_index(i, self.side)
    leaf.set_index(-1, self.side)   # if leaf was last: set to i, then -1, then popped -- correct
    children.pop()
    return True
return False
```

`removeChild` does **not** check that `children[i] is leaf`; it trusts the stored index. Leaves inside a StreamlineNode are never sorted in TS (only StreamlineNodes inside a Branch are, §5.2), so the indices stay valid. In Python, never reorder `StreamlineNode.children` except through `add_child`/`remove_child`, or the stored indices go stale and the wrong leaf is removed.

The remaining methods (`:111-130`):

- `makeDangling()`: `targetId = None`, returns self.
- `linkTo(opp)`: `reverse = (self.side == LEFT)`, then `self.link = opp.link = StreamlineLink(self, opp, reverse)`.
- `removeLink()`: if `link` is set, call `link.remove()`, which sets both ends' `link = None`.

### 1.4 Generic swap-remove (`AlluvialNode.ts:149-158`)

`Branch.removeChild` (StreamlineNode from Branch) and `Module.removeChild` (group from module) use the base class:

```
i = children.index_by_identity(node)     # JS indexOf uses ===, i.e. identity
if i > -1: children[i] = children[-1]; children.pop()
```

> **Pitfall:** Python `list.index` / `list.remove` use `==`. Dataclasses default to `eq=True`, which gives value equality. Use `eq=False` or an explicit identity search.

`Network.removeChild` uses the same swap-remove and also deletes from `modulesById` (`Network.ts:291-295`).

### 1.5 `LeafNode` side bookkeeping (`LeafNode.ts:26-37, 87-118`)

| Field | Default | Purpose |
|---|---|---|
| `leftParent`, `rightParent` | `None` | StreamlineNode on each side |
| `leftIndex`, `rightIndex` | `-1` | index in that parent's `children` (used by the O(1) swap-remove) |
| `oppositeNodes[LEFT]`, `oppositeNodes[RIGHT]` | `None` | cached matching leaf (same `identifier`) in the neighbour network |

Other leaf attributes used here:

- `identifier`: cross-network identity; see the identifiers note.
- `highlightIndex`: default `NOT_HIGHLIGHTED = -1` unless an integer is given (`LeafNode.ts:52-55`, `HighlightGroup.ts:7`). The test is `x != null && Number.isInteger(x)`, so `2.0` is accepted (it is the JS number 2), `1.5`, `"2"` and `true` give -1, and any negative integer is kept (e.g. `-2` gives a `group-2` id).
  - **Python pitfalls:** store it as `int`. A float `2.0` would print as `group2.0` in ids. Reject `bool` explicitly, because `isinstance(True, int)` is true in Python.
- `moduleLevel`: default 1 (`:56-59`). The test is `x && Number.isInteger(x)`, so a missing value, `0` or a non-integer gives 1. Fix round WP4 (E18): the test is now `Number.isInteger(x) && x >= 1`, so a negative level also gives 1 (before, it was kept and gave the full path and `insignificant`).
- `moduleId = treePath.ancestorAtLevelAsString(moduleLevel)` (`:79-81`), e.g. `"1"` at level 1 or `"1:2"` at level 2.
- `insignificant = not treePath.isSignificant(moduleLevel - 1)` (`:63-65`, `utils/TreePath.ts:206-212`).
- `flow` reads `_flow if visible else 0` (`:67-69`). `visible` is only toggled by the bipartite feature (`Network.ts:100-106`).

### 1.6 `Network` registries (`Network.ts:48-50, 273-283, 323-337`)

- `nodesByIdentifier: dict[str, LeafNode]` is rebuilt in `addNodes` **before** any `add()` call. Later duplicates overwrite earlier ones (see Q3).
- `streamlineNodesById: dict[str, StreamlineNode]` is keyed by `currentId` and is per network. It supports `get`, `set` and `delete` (a delete of a missing key is a no-op).

### 1.7 `StreamlineLink` (`StreamlineLink.ts:12-136`)

```
class StreamlineLink:
    def __init__(self, a, b, reverse=False):     # :13-20
        self.left  = b if reverse else a
        self.right = a if reverse else b
```

Because of `linkTo`'s `reverse = (self.side == LEFT)`, **`link.left` is always the end in the lower-index network** (it sits in that network's RIGHT branch), and `link.right` is the end in the higher-index network (in its LEFT branch). Both ends hold the same object. `remove()` sets `left.link = right.link = None` (`:102-105`).

### 1.8 Invariants (hold after every public operation)

These hold only when **identifiers are unique within each network**. With duplicates, TS breaks invariants 3 and 4 and can lose leaves from the tree (§3.3, Q3).

1. Every leaf belongs to exactly one StreamlineNode per side, inside **its own** group's branch for that side.
2. A branch contains **at most one dangling** node (its id is just `sourceString`) and no two nodes with the same `currentId`. Every node in a branch is registered in its network under its `currentId`. This is asserted by `StreamlineNode.test.ts:33-50`.
3. Each non-dangling node has `link` set, its `opposite` is non-dangling, and the opposite's `oppositeId == self.currentId`.
4. For a linked pair (A in network k's RIGHT branch, B in network k+1's LEFT branch), the leaves of A are exactly the identifier-matches of the leaves of B, so `len(A.children) == len(B.children)`. Their **orders may differ**.
5. StreamlineNodes, groups and modules are never empty after an operation completes. Empty ones are removed (§3.3, `LeafNode.ts:217-223`).

---

## 2. Streamline ids (`StreamlineNode.createId`, `StreamlineNode.ts:67-89`)

```
def side_string(leaf, side):
    i = "i" if leaf.insignificant else ""
    return f"{leaf.networkId}_module{leaf.moduleId}_group{i}{leaf.highlightIndex}_{side_to_string(side)}"

def create_id(source_leaf, side, target_leaf=None):
    s = side_string(source_leaf, side)
    if target_leaf is None:
        return s                                         # dangling id
    return s + "--" + side_string(target_leaf, opposite(side))
```

- The source string equals `f"{group.id}_{side}"`, because `Module.id = f"{networkId}_module{moduleId}"` (`Module.ts:25`) and `HighlightGroup.id = f"{module.id}_group{'i' if insig else ''}{hi}"` (`HighlightGroup.ts:23-27`).
- `highlightIndex` is printed as a JS integer, so the not-highlighted case is `group-1` (a single hyphen, which does not collide with `--`).
- Real examples **[verified]**: `A_module1_group-1_right--B_module2_group-1_left`, `A_module2_group-1_right` (dangling), and `B_module3_group2_left--A_module1_group1_right`.
- `link.id = link.left.currentId` (`StreamlineLink.ts:22-24`). It is used as the React key and the SVG element id (`react/Network.tsx:58`, `react/Streamline.tsx:16`).
- Network ids in the app are random `"_" + 9 base-36 chars` (`utils/id.ts:2-11`; `parsers/parse-files.ts:159`). The parsed file contents are spread **after** that `id` (`parsers/parse-files.ts:151-163`), so a saved JSON diagram keeps its stored ids (e.g. `"_7peextn2u"` in `apps/web/public/data/science-1998-2001-2007.json`). Fixtures must therefore pin network ids, and the Python port should take network ids from the caller or default to deterministic ones.
- Network ids must be unique. `Diagram.addNetwork` throws `Network with id … already exists` (`Diagram.ts:105-113`), and `getNeighbor` looks networks up by id (§1.1). The Python port should raise as well.

---

## 3. Linking algorithm

### 3.1 Build order (`Diagram.ts:97-113`, `Network.ts:68, 273-283`)

```
Diagram(networks):
    for nf in networks:                    # file order
        if any(n.networkId == nf.id for n in diagram.children): raise   # Diagram.ts:108-110
        net = Network(diagram, nf)         # appends net to diagram.children FIRST (Network.ts:68)
        net.addNodes(nf.nodes)

Network.addNodes(nodes):
    nodesByIdentifier = {}
    leaves = [LeafNode(n, self) for n in nodes]          # nodesByIdentifier filled here
    for leaf in leaves: leaf.add()                       # file order
```

When network k is being added, network k+1 does not exist yet, so `getNeighbor(RIGHT)` is `None`.

- For a leaf of network k, the **LEFT** side links to network k−1 (if the identifier exists there). The **RIGHT** side is always dangling at build time.
- When network k+1 is built later, its leaves pull the matching leaves of network k out of their dangling RIGHT nodes and into linked RIGHT nodes.

### 3.2 `LeafNode.add()` (`LeafNode.ts:120-194`) in exact step order

```
def add(self):
    module = self.network.getModule(self.moduleId) or Module(self.network, self.moduleId, self.moduleLevel)   # :121-123 (new module appended to network.children)
    group  = module.getGroup(self.highlightIndex, self.insignificant) \
             or HighlightGroup(module, self.highlightIndex, self.insignificant)                               # :125-127 (appended to module.children)
    for branch in group.children:            # [LEFT, RIGHT] -- LEFT first   # :132
        side = branch.side
        opp_leaf = self.getOpposite(side)                                     # cached?
        neighbor = self.network.getNeighbor(side)
        if opp_leaf is None:                                                  # :138-141
            opp_leaf = neighbor.getLeafNode(self.identifier) if neighbor else None
            self.setOpposite(opp_leaf, side)   # sets ONLY this leaf's cache, not opp_leaf's

        sn_id = create_id(self, side, opp_leaf)                               # :144
        sn = self.network.getStreamlineNode(sn_id)
        if sn is None:                                                        # :147-153
            sn = StreamlineNode(branch, sn_id)        # appended to branch.children
            self.network.setStreamlineNode(sn.currentId, sn)

        if opp_leaf is not None:                                              # :157-188
            opp_side = opposite(side)
            opp_branch = opp_leaf.removeFromSide(opp_side)   # §3.3; returns the branch it was in
            opp_sn_id = sn.oppositeId
            opp_sn = neighbor.getStreamlineNode(opp_sn_id)
            if opp_sn is None:
                opp_sn = StreamlineNode(opp_branch, opp_sn_id)  # appended to opp_branch.children
                neighbor.setStreamlineNode(opp_sn.currentId, opp_sn)
                sn.linkTo(opp_sn)          # link created ONLY when the opposite node is new
            opp_sn.addChild(opp_leaf)      # append
            opp_leaf.setParent(opp_sn, opp_side)

        sn.addChild(self)                  # append                           # :191-192
        self.setParent(sn, side)
```

Notes:

- **Truthiness:** TS uses `??` for module and group, `|| null` for the opposite leaf, and `!x` / `if (x)` for the streamline nodes. All of these operands are objects or `null`/`undefined`, so in Python write explicit `is None` tests. The pseudocode's `or` is only safe if no node class defines `__len__` or `__bool__`. An empty Module or Branch with `__len__` is falsy, and `get_module(...) or Module(...)` would then create a duplicate.
- `opp_branch` is the branch the opposite leaf was in. It is the correct branch for `opp_sn`, because the opposite leaf's module and group do not change here.
- In a fresh build the opposite leaf is always attached on `opp_side`, so `removeFromSide` never returns `None` there. In TS, if it ever did (the leaf has no parent on that side), `removeFromSide` logs a warning and returns `undefined` (`:239-242`). Constructing `StreamlineNode(undefined, …)` would then throw.
- The **opposite leaf is removed and re-appended** even when it is moved into a node that already exists. This changes child orders, so swap-remove effects accumulate.
- The opposite leaf's `oppositeNodes[opp_side]` cache is **not** set. Only the acting leaf's cache is set. This matters only for v2 `update()`, where a later lookup by identifier finds it anyway.

### 3.3 `LeafNode.removeFromSide(side)` (`LeafNode.ts:233-290`)

```
def removeFromSide(self, side):
    sn = self.getParent(side)
    if sn is None:
        warn(...); return None                                   # :239-242
    branch = sn.parent
    sn.removeChild(self)                    # index-based swap-remove (§1.3)
    self.setParent(None, side)
    if len(sn.children) == 0:                                    # :250
        opp = sn.opposite
        if opp is not None:                                      # :255-283
            neighbor = self.network.getNeighbor(side)
            neighbor.removeStreamlineNode(opp.currentId)         # old linked id
            opp.makeDangling().removeLink()                      # targetId=None; both links None
            existing = neighbor.getStreamlineNode(opp.currentId) # now the dangling id
            if existing is not None:                             # MERGE into existing dangling node
                for leaf in opp.children:                        # in opp's current order
                    existing.addChild(leaf)                      # append (sets index on existing.side)
                    leaf.setParent(existing, opposite(side))
                opp.children.clear()                             # TS: children.length = 0
                opp.parent.removeChild(opp)                      # identity swap-remove from its branch
            else:
                neighbor.setStreamlineNode(opp.currentId, opp)   # re-register under dangling id; keeps its slot
        self.network.removeStreamlineNode(sn.currentId)          # sn's targetId unchanged → its own key
        branch.removeChild(sn)                                   # identity swap-remove
    return branch
```

During a **fresh build with unique identifiers in every network**, this is only ever called on a leaf of network k−1 that is still in its build-time dangling RIGHT node. The `opp is not None` block therefore never runs during such a build (a dangling node has no link). It does run in `update()`, i.e. in the v1 colour ops. Only the following steps happen:

- the leaf is swap-removed from the dangling node;
- if the dangling node becomes empty, it is unregistered and swap-removed from its branch.

The merge path runs during `update()`, i.e. in the v1 colour ops (and v2 expand/regroup). It is exercised by `StreamlineNode.test.ts:103-127` and by the coloured fixtures.

**Duplicate identifiers in network k (fresh build) [verified].** If two leaves X1 and X2 of network k share an identifier that exists in network k−1 (leaf Y), both look up Y. X1 moves Y into a linked node O. X2's `add()` then calls `Y.removeFromSide(RIGHT)` a second time, from a **linked** node, so the `opp is not None` block runs during the build:

- **X1 and X2 in different groups:** O empties, X1's LEFT node is made dangling (re-registered, or merged into the branch's dangling node), and Y links to X2 instead. The result is consistent and "last wins". X1 behaves like an unmatched leaf.
- **X1 and X2 in the same group:** O empties and makes the shared node S (which X2 is about to join) dangling under X2's feet. `S.oppositeId` is now `"NULL--<S.sourceId>"`, so a bogus node with `sourceId = "NULL"` is created in network k−1 and linked to S. The emitted `link.id` is `NULL--B_module1_group-1_left`. If the branch already had a dangling node, S was merged into it and detached from the branch **before** `S.addChild(X2)`, so X2 is lost from its LEFT branch. In the probe, `B.flow` became `0.6` instead of `1.0`.

Duplicates in network k−1 alone (unique in k) are benign: `nodesByIdentifier` keeps the last one, and the earlier ones stay in the dangling RIGHT node. See Q3 for the Python policy.

### 3.4 Resulting order within a branch at build time (worked trace, **[verified]**)

Network A has leaves `a(1:1) b(1:2) c(2:1) d(2:2) e(3:1)`. Network B has leaves `c(1:1) a(1:2) b(2:1) f(2:2)`.

1. Building A creates one dangling node per branch, e.g. `A.m1.right = [D1(a,b)]` and `A.m2.right = [D2(c,d)]`.
2. B's leaf `c` (B.m1, LEFT): the opposite is A.c. A.c is removed from D2, giving `D2(d)`. `L(c)` is appended, giving `A.m2.right = [D2(d), L(c)]`.
3. B's leaf `a`: A.a leaves D1, giving `D1(b)`. The branch becomes `A.m1.right = [D1(b), L(a)]`.
4. B's leaf `b` (B.m2): A.b leaves D1, so D1 is empty. D1 is unregistered and swap-removed: `[D1, L(a)]` becomes `[L(a)]`. Then `L(b)` is appended, giving `[L(a), L(b)]`.

The pre-sort branch order is therefore **creation order distorted by swap-removes**. It matters only for:

- sort ties (§5.2);
- float summation order (§4);
- `getLinks` ties (§6).

**Port the algorithm literally. Don't compute final orders some other way.**

### 3.5 v1 (colours) and v2 (expand/regroup): `update()` / `remove()` (`LeafNode.ts:196-231`)

```
def update(self): self.remove(); self.add()

def remove(self, removeNetwork=False):
    group = self.leftParent.parent.parent if self.leftParent else None
    self.removeFromSide(LEFT); self.removeFromSide(RIGHT)
    module = group.parent if group else None; network = module.parent if module else None
    if group and group.isEmpty: module.removeChild(group)          # identity swap-remove
    if module and module.isEmpty: network.removeChild(module)      # swap-remove + modulesById delete
    if removeNetwork and network.isEmpty: ...                      # dead code: never called with True
```

Callers:

- `Module.expand` and `Module.regroup` set `moduleLevel` (`Module.ts:212-281`).
- `Module.setColor` sets `highlightIndex` (`Module.ts:283-288`).

All of them iterate `module.getLeafNodes()` (groups → left branch → its streamline nodes → leaves, using **current**, i.e. last-sorted, orders) and call `update()` on each leaf.

After a `setColor`, leaf orders differ from a fresh build with the same colours. For example, `B_module3_group2_right` holds leaves `dc` instead of `cd` **[verified]**. Geometry then agrees only to float tolerance, and tie-dependent orders (module order, `-inf` streamline nodes, `getLinks` ties) may differ. The coloured fixtures follow the `setColor` path, so port it literally (Q1, resolved).

---

## 4. Flow of streamline nodes and branches (`Diagram.ts:121-128`, `AlluvialNode.ts:135-137`, `HighlightGroup.ts:49-55`)

The store's `updateLayout()` runs `diagram.calcFlow()` and then `diagram.updateLayout(opts)` (`store/DiagramStore.ts:485-490`). Every store action goes through it, including the initial `setNetworks` (`:217-226`), except `moveSelectedModule` (`:500-511`), which calls `diagram.updateLayout` without `calcFlow`. Flows don't change when a module moves, so that path only matters for v2 re-layout parity (Q2). `calcFlow` is a post-order walk over every node with `depth < LEAF_NODE`, **including invisible modules**, that sets `node.flow = node.childFlow`:

```
StreamlineNode.flow = reduce(+, [leaf.flow for leaf in children], 0)   # children order, starting from 0
Branch.flow         = reduce(+, [sn.flow for sn in children], 0)       # branch children order
HighlightGroup.flow = group.left.childFlow                             # LEFT branch sum (re-reduced)
Module.flow         = reduce(+, [g.flow for g in groups], 0)
```

- `leaf.flow` is 0 for bipartite-hidden leaves (`LeafNode.ts:67-69`).
- `calcFlow` runs **before** the layout re-sorts branches. On the first layout the sums use build order. On later layouts they use the previous layout's sorted order.
- A Python port that replays the same call sequence (`calc_flow`, then `layout`, which sorts in place) reproduces the TS results bit-for-bit.

> **Pitfall:** Python ≥ 3.12 `sum()` uses compensated summation for floats, so `sum([0.1]*10) == 1.0`, while JS `reduce` gives `0.9999999999999999` **[verified on py314]**. Use an explicit left-to-right loop starting at `0.0`, or `functools.reduce(operator.add, xs, 0.0)`. Never use `sum()` or `math.fsum()` for flows.

---

## 5. Layout steps that touch streamlines (`Diagram.ts:130-375`)

Module-level layout (widths, visibility, margins, justify) belongs to the layout note. Only the parts that produce streamline-node geometry are specified here.

Constants from `Diagram.ts:146-148, 161-163`:

```
streamlineWidth = streamlineFraction * moduleWidth
networkWidth    = moduleWidth + streamlineWidth
maxNetworkFlow  = max(net.flow for net in diagram.children)
getNodeSize(n)  = n.flow / maxNetworkFlow                       # moduleSize "flow" (Diagram.ts:383-384)
                = n.numLeafNodes / network.numLeafNodes          # moduleSize "nodes" (Diagram.ts:385-386)
```

- For `"nodes"`, `network.numLeafNodes` is captured when the size function is created and counts all modules, visible or not.
- `usableHeight` is computed after pass 1 (`Diagram.ts:251-275`; see the layout note).

### 5.1 Pass 1 group positions used as sort keys (`Diagram.ts:176-249`)

Pass 1 is a pre-order walk over networks, **visible** modules in sorted order, and their groups in sorted order (significant first, then ascending `highlightIndex`; `Diagram.ts:215-221`). Within each module's band it stacks the groups **from the bottom up**, using `height` (not `usableHeight`) and **unscaled** margins (`Diagram.ts:237-247`):

```
# entering the module: y has already been decremented by moduleHeight and margin
if group_index == 0: y += moduleHeight + moduleMargin      # back to module bottom
groupHeight = getNodeSize(group) * height
y -= groupHeight
group.y = y                                                 # <- the value read by oppositeStreamlinePosition
if group_index == last: y -= moduleMargin
```

Groups of invisible modules are not visited, so their `y` is stale (initially 0). They are never read, because `oppositeStreamlinePosition` returns `-inf` for invisible modules. **All networks finish pass 1 before any branch is sorted.**

Pass-1 y values are not clipped to `[0, height]`. Pass 1 stacks full-`height` sizes plus unscaled margins, so a network can overflow the top. In the §10 fixture, B.m2's pass-1 group y is `-15.999999999999943` **[verified]**. Only their relative order matters.

> **Pitfall:** pass 2 overwrites `group.y`. Reading `oppositeStreamlinePosition` **after** `updateLayout` returns `-(pass-2 y)`, which is not the value the sort used. To test the sort key, capture it between pass 1 and the sort. The probe did this by wrapping the getter during `updateLayout`.

### 5.2 Branch sort (`Diagram.ts:305-315`)

```
for net in diagram.children:                      # pre-order, depth <= BRANCH
    for module in net.children:                   # ALL modules, visible and invisible
        for group in module.children:
            for branch in group.children:         # LEFT then RIGHT
                branch.children.sort(key=opposite_streamline_position)   # ascending, stable, IN PLACE
```

- The TS comparator is `a.pos - b.pos`, and `-inf - -inf` gives `NaN`. ECMAScript `SortCompare` maps `NaN` to `+0` (equal), and `Array.prototype.sort` is stable.
- A Python stable key sort with `-math.inf` keys gives identical results. This was checked against node on a mixed `-inf`/finite list **[verified]**.
- The comparator is consistent (no NaN except `-inf` vs `-inf`, which reads as equal; NaN flows are rejected at load since fix round WP4), so V8's TimSort and Python's `list.sort` produce the same unique stable order.
- The sort persists: it mutates `branch.children` and affects the next `calcFlow` and `getLinks`.

Meaning:

- Ascending `-oppositeGroup.y` is the same as descending opposite-group y. In SVG coordinates y grows downwards, so the opposite group lowest on screen comes first.
- First in the list means **bottom-most** after pass 2.
- **Dangling nodes and nodes whose opposite module is invisible (key `-inf`) come first, so they sit at the bottom of the branch**, in their current relative order **[verified]**. For example, `B_module1 left` = `[→A2(x), →A3(y), →A4(z)]`, all with key `-inf`, keep build order.

Distinct streamline nodes in one branch always point to distinct opposite groups, because the opposite group is encoded in `targetId`. Finite ties therefore only occur when two opposite groups have identical pass-1 `y`. That can happen with a zero-flow group, which gets the same `y` as its predecessor in the stack. Ties keep the current order.

### 5.3 Pass 2: streamline-node heights and positions (`Diagram.ts:317-372`)

Pass 2 is a **post-order** walk.

- The predicate `depth != MODULE or module.isVisible` skips invisible modules and **their entire subtree**. Their streamline nodes keep stale layout (initially `x=y=width=height=0` **[verified]**).
- `x` starts at 0 and `y` at `height`.
- `getNodeSize` is created lazily at the first StreamlineNode of each network (`:327-338`) and reset at each Network (`:363-367`).

```
x = 0.0; y = height
for net in diagram.children:
    for module in visible modules of net (in net.children order):
        for group in module.children:                 # pass-1 sorted order
            for branch in (group.left, group.right):
                for sn in branch.children:            # §5.2 sorted order
                    h = getNodeSize(sn) * usableHeight          # (flow / maxNetworkFlow) * usableHeight
                    y -= h                                       # :339-340
                    sn.x, sn.y, sn.width, sn.height = x, y, moduleWidth, h   # :341
                bh = getNodeSize(branch) * usableHeight          # :343
                branch.x, branch.y, branch.width, branch.height = x, y, moduleWidth, bh
                if branch.side == LEFT: y += bh                  # :345-347  reset to group bottom
            group.(x, y, width, height) = (x, y, moduleWidth, getNodeSize(group) * usableHeight)  # :348-354
        module.(x, y, width, height) = (x, y, moduleWidth, getNodeSize(module) * usableHeight)    # :355-361
        y -= module.margin                                       # :362
    net.(x, y, width, height) = (x, 0, moduleWidth, height)      # :364
    x += networkWidth; y = height                                # :365-366  (x accumulates by repeated +=)
```

Float details that the port must replicate exactly:

- The LEFT branch is reset with `y += bh`, using the branch's **reduce-sum** flow, not by restoring a saved y. As a result the RIGHT branch's first node starts from a value that can differ from the LEFT branch's start in the last ulp. For example, in the probe the left node has `y = 72.79999999999998` and the right node `y = 72.80000000000001` **[verified]**.
- The group, the module and the next stacking position all continue from the **RIGHT** branch's running `y`.
- `y` near the top can be a tiny positive or negative number such as `7.105427357601002e-15` **[verified]**. The path code snaps it (§7).
- Each network's x is `0 + networkWidth + networkWidth + …` by repeated addition, never `k * networkWidth`.

---

## 6. Links: `Network.getLinks(streamlineThreshold = 0)` (`Network.ts:343-362`, `Module.ts:368-382`)

```
def right_streamlines(net):
    for module in net.children:                      # after layout: [visible sorted..., invisible...]
        if not module.isVisible: continue            # left end hidden
        for group in module.children:                # pass-1 sorted order
            for sn in group.right.children:          # §5.2 sorted order
                opp = sn.opposite
                if opp is None: continue             # dangling (link is None)
                opp_module = opp.parent.parent.parent
                if not opp_module.isVisible: continue   # right end hidden
                if sn.link is not None: yield sn.link

def get_links(net, threshold=0.0):
    links = [l for l in right_streamlines(net) if l.avgHeight > threshold]   # STRICT >
    links.sort(key=lambda l: (l.highlightIndex, -l.avgHeight))              # stable
    return links
```

- The TS comparator is `hi_a != hi_b ? hi_a - hi_b : avg_b - avg_a`, which is equivalent to the stable key sort above.
- Each link is yielded once, from its left network. The last network yields none.
- Draw order equals list order: not-highlighted (`-1`) first, then ascending highlight index; within the same index, thicker first, so thinner links are drawn on top.
- **Ties on exact float equality are common**, e.g. equal-flow leaves. They fall back to the iteration order above, so module, group and branch orders must match TS exactly.
- Near-ties depend on the last ulp. In the probe, `170.4` sorts before `170.39999999999998` **[verified]**, so §4 and §5.3 float-order fidelity directly affects link order.

Link accessors (`StreamlineLink.ts:26-80`):

```
leftHighlightIndex  = link.left.parent.parent.highlightIndex      # group of left end  (default -1)
rightHighlightIndex = link.right.parent.parent.highlightIndex
leftInsignificant   = link.left.parent.parent.insignificant       # (default False)
rightInsignificant  = link.right.parent.parent.insignificant
highlightIndex      = max(leftHighlightIndex, rightHighlightIndex)  # sort key only
x0 = left.x + left.width        # right edge of left module column
x1 = right.x                    # left edge of right module column
y0 = left.y ; y1 = right.y
h0 = left.height ; h1 = right.height
xMid = (x0 + x1) / 2 ; yMid = (y0 + y1) / 2
avgHeight = (h0 + h1) / 2
```

The two ends usually have **different heights**: h0 comes from the leaves' flows in the left network and h1 from their flows in the right network. A streamline therefore tapers.

---

## 7. Path geometry (`StreamlineLink.ts:82-84, 107-135`)

```
def path(link):  # _path(self)
    x0, x1, y0, y1, h0, h1 = link.x0, link.x1, link.y0, link.y1, link.h0, link.h1
    T = 1e-6
    y0 = 0 if y0 < T else y0          # also maps negatives and -0.0 to 0
    y1 = 0 if y1 < T else y1
    y2 = y0 + h0                      # AFTER snapping
    y3 = y1 + h1
    cpx = (x0 + x1) / 2
    return ("M" + f(x0) + "," + f(y2) +
            "C" + f(cpx) + "," + f(y2) + "," + f(cpx) + "," + f(y3) + "," + f(x1) + "," + f(y3) +
            "L" + f(x1) + "," + f(y1) +
            "C" + f(cpx) + "," + f(y1) + "," + f(cpx) + "," + f(y0) + "," + f(x0) + "," + f(y0) +
            "Z")
```

Here `f` is JS `Number#toString` (see below). Shape:

- Move to the bottom-left `(x0, y0+h0)`.
- Cubic to the bottom-right `(x1, y1+h1)`, with both control points at `x = cpx` and the y of their own end.
- Line up to the top-right `(x1, y1)`.
- Cubic back to the top-left `(x0, y0)`, mirrored.
- Close.

Only the top edges `y0` and `y1` are snapped. `h0`, `h1`, `x` and the derived `y2`/`y3` are not.

Example **[verified]**: `M80,214.8C160,214.8,160,429.6,240,429.6L240,230.80000000000004C160,230.80000000000004,160,72.80000000000001,80,72.80000000000001Z`

**JS number formatting**: JS prints `80`, not `80.0`, and `1e-7`, not `1e-07`. The fixed/exponential thresholds also differ from Python's. The function below matched node's `String(x)` on 9,019 values, including random bit patterns, subnormals and the boundaries 1e-6, 1e-7 and 1e21 **[verified]**:

```python
import math


def js_number_to_string(x: float) -> str:
    """ECMAScript Number::toString(10)."""
    if x != x:
        return "NaN"
    if x == 0:
        return "0"  # also -0.0
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    sign = "-" if x < 0 else ""
    mant, _, exp = repr(abs(x)).partition("e")  # repr = shortest round-trip digits (same as JS)
    ip, _, fp = mant.partition(".")
    s = ip + fp
    z = len(s) - len(s.lstrip("0"))  # leading zeros
    digits = s.lstrip("0").rstrip("0")
    k = len(digits)
    n = len(ip) + int(exp or 0) - z  # x = 0.<digits> * 10**n
    if k <= n <= 21:
        out = digits + "0" * (n - k)
    elif 0 < n <= 21:
        out = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        out = digits[0] + ("." + digits[1:] if k > 1 else "") + "e" + ("+" if e >= 0 else "-") + str(abs(e))
    return sign + out
```

`transitionPath` (`StreamlineLink.ts:86-100`) is animation-only. It collapses the link to `x0 = x1 = xMid`, `y0' = yMid + h0/4`, `y1' = yMid + h1/4` and halved heights, where `yMid` uses the **unsnapped** y, then passes the result through the same `_path`. It is not needed for a static renderer.

---

## 8. Renderer behaviour (React; reference for the matplotlib renderer)

- **Threshold:** `links = network.getLinks(streamlineThreshold)`, where the store default is `streamlineThreshold = 1` (`react/Network.tsx:19-25`, `store/DiagramStore.ts:87`).
  - The unit is layout units (the default `height` is 600, `store/DiagramStore.ts:81`). It is not scaled by zoom.
  - The engine default is 0 (`Network.ts:343`).
  - Expose `streamline_threshold=1.0` in the renderer and `threshold=0.0` in the engine API.
  - The threshold is absolute, in the same units as `height`. TS does not rescale it when the user changes `height`. If the Python layout ever defaults to a normalised height (e.g. `1.0`), a threshold of `1.0` drops **every** link. Keep `height=600` as the default, or document the threshold as layout units (Q7).
  - Links whose `avgHeight` is at or below the threshold are simply not drawn. Their streamline nodes still take up space in the modules, so a thin empty band remains, as with invisible opposite modules.
- **Z-order:** for each network in order, draw its modules first and then its links in `getLinks` order (`react/Network.tsx:54-63`, `react/Diagram.tsx:135-137`). Links of network k are therefore drawn under the modules of network k+1, though they don't overlap in x.
- **Fill:** each link gets `url(#gradient_{L}{i?}_{R}{i?})` (`react/LinearGradients.tsx:7-15, 64-75`). This is an SVG `linearGradient` with default vector `x1=0%, x2=100%` in objectBoundingBox units, i.e. horizontal across the path's bbox, which spans exactly `[x0, x1]`. Its stops are:
  - `offset 15%` → `color(leftHighlightIndex, leftInsignificant)`
  - `offset 85%` → `color(rightHighlightIndex, rightInsignificant)`

  So the fill is solid left colour up to `x0 + 0.15*(x1-x0)`, a linear blend up to `x0 + 0.85*(x1-x0)`, and solid right colour after that (`:23-24, 40-55`). The blend interpolates the gamma-encoded **sRGB** components, because SVG's default `color-interpolation` is `sRGB` and no attribute overrides it. It is not a `linearRGB` (linear-light) blend.
  - Gradient `<defs>` are emitted per network for every distinct `(leftHighlightIndex, rightHighlightIndex)` pair among its links, times all four insignificance combinations (`react/LinearGradients.tsx:26-31`, `react/Network.tsx:31, 68-76`). Every `fill` url therefore resolves.
- **Colour function** (`utils/highlight-color.ts:9-24`): `-1` maps to `defaultHighlightColor` (store default `#b6b69f`, `store/DiagramStore.ts:91`). Any other index maps to `highlightColors[i]`. The field default is `[]` (`:92`), the constructor copies the scheme into it (`:137`), and every `setNetworks` resets it to `[]` via `checkColors` (`:209`), so after loading ordinary files it is `[]` (fixture field `highlightColors`). Files can bring their own palette: `checkColors` maps a network's `colors` array, or per-node `color` fields, to highlight indices before the build (`store/DiagramStore.ts:180-210`; colours note). If the group is insignificant, the colour becomes `d3.hsl(color).brighter(0.8)`, i.e. HSL lightness × `(1/0.7)**0.8`. Exact colour conversion belongs to the colours note.
- **Opacity:** element `opacity = streamlineOpacity`, default `0.8` (`store/DiagramStore.ts:88`, `react/Streamline.tsx:20`). There is no stroke; no CSS rule targets `.streamline` (`react/Diagram.css`).
- **Coordinates:** SVG y points down. The engine's y=0 is the top of the diagram and y=`height` the bottom (`index 0` module at the bottom). For matplotlib, either invert the y-axis or plot `height - y`.

---

## 9. Edge cases

| Case | Behaviour | Source |
|---|---|---|
| Single network | No neighbours, so every streamline node is dangling (one per branch) and `getLinks` returns `[]`. Nodes are still laid out. | `Network.ts:301-321`; §3 |
| Identifier missing in neighbour | The leaf goes to its branch's single dangling node, which sits at the bottom after the sort. | `LeafNode.ts:138-141`; §5.2 |
| Node present in k−1 and k+1 but not in k | No link skips network k; only adjacent networks link. | `LeafNode.ts:135-139` |
| Invisible left module | Skipped in pass 1 and pass 2 (stale layout), and its links are skipped. | `Network.ts:354-358`; `Diagram.ts:322-325` |
| Invisible right module | The neighbour's streamline node keeps its slot (bottom, `-inf` key) but no link is emitted, which leaves an empty band. | `StreamlineNode.ts:52-57`; `Module.ts:375-377` |
| Zero-flow leaf or streamline node | `h = 0`, `y` unchanged. A link with `avgHeight == 0` is dropped even at threshold 0 (strict `>`). | `Network.ts:345` |
| Zero-flow group in a visible module | Same pass-1 `y` as its predecessor, so finite sort ties are possible (stable). | §5.2 |
| Module with flow 0 | Invisible (`flow >= threshold and flow > 0`). | `Module.ts:124-126` |
| Empty streamline node, group or module | Never persists: removed on emptying (§3.3, `LeafNode.ts:217-223`). Empty branches don't occur because each leaf is in both branches. | |
| All networks zero flow | `maxNetworkFlow = 0` would divide by zero, but all modules are invisible, so nothing is laid out. Guard against it in Python. | `Diagram.ts:161-163` |
| `y` in the range −ε…1e-6 at the top | Snapped to 0 in the path only, not in `sn.y`. | `StreamlineLink.ts:119-121` |
| `highlightIndex >= len(highlightColors)`, or a negative index other than -1 | The colour function returns `undefined`, and the `<stop>` gets no `stop-color`, so it renders black (the SVG default). With `insignificant`, `d3.hsl(undefined).brighter(0.8).toString()` gives `"rgb(0, 0, 0)"`, which is also black. The store's `getHighlightColor` returns `undefined` for indices past the palette, and the gradients don't use it anyway. | `utils/highlight-color.ts:14-20`; `store/DiagramStore.ts:314-322` |
| Duplicate identifiers within a network | Since fix round WP5 (E6): only the registered (last) duplicate links, the others stay dangling. Before: benign in the left network ("last wins"). In the right network they demote earlier matches to dangling (different groups) or corrupt the tree (same group: `NULL--` ids, lost leaves). | §3.3, Q3 |
| Duplicate network ids | `Diagram.addNetwork` throws. | `Diagram.ts:108-110` |
| `streamlineFraction = 0` | `x0 == x1`, so the path's bbox has zero width. An `objectBoundingBox` gradient is then not rendered, so streamlines are invisible in TS. The matplotlib renderer should skip zero-width links. | `Diagram.ts:146-147`; SVG spec on zero-size bboxes |

---

## 10. Worked mini-fixture (**[verified]**, TS engine output)

Input: network ids `A`, `B` and `C`; `identifier == name`; `.tree`-style paths with all nodes significant and `highlightIndex = -1`:

```
A: a 1:1 0.3 | b 1:2 0.2 | c 2:1 0.25 | d 2:2 0.15 | e 3:1 0.1
B: c 1:1 0.35 | a 1:2 0.3 | b 2:1 0.2 | f 2:2 0.15
C: a 1:1 0.6 | f 1:2 0.4
opts: height 600, streamlineFraction 2, moduleWidth 80, flowThreshold 0,
      verticalAlign bottom, marginExponent 4, zeroMargins false, moduleSize flow, sortModulesBy flow
```

Branch contents after layout, listed bottom first. `key` is the **sort key** (`oppositeStreamlinePosition` captured during the sort, i.e. `-(pass-1 group y)`). `post` is the same getter read **after** `updateLayout`, i.e. `-(pass-2 group y)`. An earlier revision of this note mislabelled `post` values as the sort keys. Both are **[verified]**.

```
A.m1 right: [A_module1_group-1_right--B_module1_group-1_left y=429.6 h=170.4 leaves=a key=-210.00000000000006 post=-230.80000000000004]
            [A_module1_group-1_right--B_module2_group-1_left y=316 h=113.60000000000001 leaves=b key=15.999999999999943 post=-16]
A.m2 right: [A_module2_group-1_right (dangling) y=214.8 h=85.2 leaves=d key=-inf]
            [A_module2_group-1_right--B_module1_group-1_left y=72.80000000000001 h=142 leaves=c key=-210.00000000000006 post=-230.80000000000004]
A.m2 left : [A_module2_group-1_left y=72.79999999999998 h=227.20000000000002 leaves=cd]
A.m3 left : [A_module3_group-1_left y=7.105427357601002e-15 h=56.800000000000004 leaves=e]
B.m1 left : [..--A_module1_group-1_right y=429.6 h=170.4 leaves=a key=-300 post=-316]
            [..--A_module2_group-1_right y=230.80000000000004 h=198.79999999999998 leaves=c key=-44 post=-72.80000000000001]
B.m1 right: [B_module1_group-1_right (dangling) y=401.20000000000005 h=198.79999999999998 leaves=c key=-inf]
            [B_module1_group-1_right--C_module1_group-1_left y=230.80000000000004 h=170.4 leaves=a key=0 post=-32]
B.m2 left : [B_module2_group-1_left (dangling) y=129.60000000000002 h=85.2 leaves=f key=-inf]
            [B_module2_group-1_left--A_module1_group-1_right y=16.000000000000014 h=113.60000000000001 leaves=b key=-300]
C.m1 left : [C_module1_group-1_left--B_module1_group-1_right y=259.2 h=340.8 leaves=a key=-210.00000000000006]
            [C_module1_group-1_left--B_module2_group-1_right y=31.99999999999997 h=227.20000000000002 leaves=f key=15.999999999999943]
```

Pass-1 group y values (from `height = 600`, unscaled margins 16): A.m1 300, A.m2 44; B.m1 210.00000000000006, B.m2 −15.999999999999943; C.m1 0. A `key` of `0` prints as `0` because `-(0)` is `-0`.

`A.getLinks(0)`, in order:

```
A_module1_group-1_right--B_module1_group-1_left  avg=170.4
  M80,600C160,600,160,600,240,600L240,429.6C160,429.6,160,429.6,80,429.6Z
A_module2_group-1_right--B_module1_group-1_left  avg=170.39999999999998
  M80,214.8C160,214.8,160,429.6,240,429.6L240,230.80000000000004C160,230.80000000000004,160,72.80000000000001,80,72.80000000000001Z
A_module1_group-1_right--B_module2_group-1_left  avg=113.60000000000001
  M80,429.6C160,429.6,160,129.60000000000002,240,129.60000000000002L240,16.000000000000014C160,16.000000000000014,160,316,80,316Z
```

`B.getLinks(0)`:

```
B_module1_group-1_right--C_module1_group-1_left avg=255.60000000000002
  M320,401.20000000000005C400,401.20000000000005,400,600,480,600L480,259.2C400,259.2,400,230.80000000000004,320,230.80000000000004Z
B_module2_group-1_right--C_module1_group-1_left avg=156.20000000000002
  M320,101.2C400,101.2,400,259.2,480,259.2L480,31.99999999999997C400,31.99999999999997,400,16,320,16Z
```

A second probe with `flowThreshold 0.05`, A modules 2–4 invisible and highlight indices 0 and 1 confirmed the following:

- The invisible-opposite nodes in `B.m1 left` keep build order at the bottom.
- `link.highlightIndex = max(L, R)`, e.g. `L=1, R=-1 → 1`, and after `setColor(B.m3, 2)`, `L=-1, R=2 → 2`.
- Link order is `-1, 0, 1` (before recolouring) and `-1, 0, 2(99.0), 2(93.06)` after.

Turn both probes into proper JSON fixtures using the fixtures tooling.

---

## 11. Python port guidance

### Suggested structure

```
alluvial/
  model/
    sides.py         # LEFT=-1, RIGHT=1, side_to_string, opposite
    streamline.py    # StreamlineNode, StreamlineLink (geometry + path)
    leaf.py          # LeafNode incl. add(), _remove_from_side(), update()/remove() (v1: colour ops)
    ...              # network.py owns streamline_nodes_by_id, nodes_by_identifier, get_neighbor, get_links
  layout/
    flow.py          # calc_flow (naive left-to-right reduce!)
    passes.py        # pass1 (layout note), sort_branches(), pass2
  render/
    paths.py         # js_number_to_string, svg_path(link), mpl_path(link)
    mpl.py           # link drawing (gradient), z-order
```

### Implementation rules

1. **Port the linking algorithm literally**, including `append`, both swap-remove flavours, and the remove-then-re-append of the opposite leaf. Child orders feed float sums and tie-breaks.
2. Use `@dataclass(eq=False)` or plain classes for tree nodes so that `list.index`, `in` and `remove` compare by identity, matching JS `indexOf`.
3. Keep `left_index` and `right_index` on leaves and implement `StreamlineNode.remove_child` via the stored index, exactly as in §1.3. `Branch.remove_child` and `Module.remove_child` use identity search plus swap-remove.
4. Keep string ids (`currentId`, `oppositeId`, `createId`) byte-identical to TS, so that `link.id` can be compared with fixtures. Internally a tuple key is fine if you also render the string. Don't use `split("--")` on user-controlled network ids without validating them (Q4).
5. Flows: an explicit loop `t = 0.0; for c in children: t = t + c.flow`. **Never use `sum()`.**
6. Size: compute `(flow / max_network_flow) * usable_height` in that order. `y -= h` happens sequentially. Reset the LEFT branch with `y += branch_height`.
7. Sorting: `branch.children.sort(key=opposite_streamline_position)` with `-math.inf`, and `links.sort(key=lambda l: (l.highlight_index, -l.avg_height))`. Both are stable, both are in place, and both persist.
8. `get_links` must iterate `network.children` **after** layout has reordered them (`[visible sorted..., invisible...]`) and must recheck `is_visible` on both ends.
9. Path: snap `y0`/`y1` with `< 1e-6` **before** computing `y2`/`y3`. Build the string with `js_number_to_string`. In tests, prefer comparing parsed numeric tuples with tolerance, and also assert exact string equality where the fixture permits.
10. Matplotlib path: vertices `[(x0,y2),(cpx,y2),(cpx,y3),(x1,y3),(x1,y1),(cpx,y1),(cpx,y0),(x0,y0),(x0,y2)]` with codes `[MOVETO, CURVE4, CURVE4, CURVE4, LINETO, CURVE4, CURVE4, CURVE4, CLOSEPOLY]`. Here `y0`/`y1` are the **snapped** values and `y2`/`y3` are computed from them, exactly as in §7. Share one `link_geometry(link) -> (x0, x1, y0, y1, y2, y3, cpx)` helper between the SVG-string and matplotlib paths.
    - When the left and right colours are equal, draw a solid `PathPatch`.
    - Otherwise draw an `imshow` of a 1×N horizontal gradient (left colour on `[0, 0.15]`, a linear ramp to `0.85`, then the right colour) over `extent=(x0, x1, ymin, ymax)`, clipped by the `PathPatch`.
    - Use `alpha=0.8` and no edge colour.
    - Respect z-order: per network, modules first, then links in `get_links` order.
11. The renderer's default `streamline_threshold` is `1.0`; the engine's default is `0.0`.
12. In v1, port `update()`/`remove()`/merge literally (§3.3, §3.5). The v1 colour ops need them, and the coloured fixtures only reproduce through them. Use `StreamlineNode.test.ts:65-128` as port tests (no duplicate ids, at most one dangling per branch, registry consistency, dangling leaves restored after recolouring). Only `expand`/`regroup` (which set `moduleLevel` and then call the same `update()`) are v2.

### Pitfalls checklist

- Python `sum()` compensation (§4).
- Value-equality `list.index` on dataclasses.
- `repr(80.0) == "80.0"` versus JS `"80"`; `1e-07` versus `1e-7`.
- Forgetting that network k's RIGHT links are made **while building network k+1** (from the neighbour leaf's perspective, `opp_side = RIGHT`).
- Laying out streamline nodes of invisible modules. TS does not lay them out; their stale zeros must not be emitted.
- Using pass-2 y (or `usableHeight`) for the branch sort key. TS uses **pass-1** group y, computed with `height` and unscaled margins.
- Resetting y with a saved value instead of `y += branch_height`, which loses ulp parity.
- Computing network x as `k * network_width` instead of repeated `+=`.
- Python truthiness (`x or y`, `if not node`) on node classes that define `__len__`; use `is None` (§3.2).
- A float `highlightIndex` (`2.0`) in ids, or a `bool` accepted as an int (§1.5).
- Sorting or otherwise reordering `StreamlineNode.children` directly, which breaks the stored leaf indices (§1.3).
- Testing the branch-sort key by reading `opposite_streamline_position` after layout, which returns the pass-2 value (§5.1, §10).

---

## 12. Open questions

- **Q1 (fixture protocol for colours): resolved.** The fixtures replay the real store operations (`colorMatchingModulesInAllNetworks`, `colorModule`, … → incremental `update()`), see `tools/ts-fixtures/README.md`. Port `update()` in v1 (rule 12).
- **Q2 (re-layout parity): resolved, required.** The coloured fixtures run `calcFlow` + `updateLayout` twice on one diagram, so sorts must be in place and persist.
- **Q3: resolved in fix round WP5 (E6).** `LeafNode.add()` links only mutually registered leaves, in TS and Python:
  other duplicates stay dangling, nothing is stolen, and no `NULL--` id can appear. `parseAcceptedFiles` warns once per
  file (non-fatal); the Python reader warning stays. The original analysis follows.
- **Q3 (duplicate identifiers within a network):** `nodesByIdentifier` keeps the last one. TS behaviour is **verified broken** when two leaves of network k share an identifier found in network k−1 and sit in the same highlight group. The build then creates `NULL--…` streamline ids, and a leaf can drop out of its LEFT branch, so the network flow is undercounted (§3.3). Duplicates can occur in name mode, e.g. state networks whose states share a physical name.
  - Options: (a) raise on duplicates in the reader or the `Diagram` constructor; (b) aggregate duplicates into one leaf before the build; (c) replicate TS bug-for-bug.
  - **Constraint from the fixture suite:** `states-tree__name` and `states-tree__nameColored` have duplicate identifiers (`identifiersUnique: false`, all states of one physical node share the name). The duplicates there sit in different groups, so neither fixture has `NULL--` ids or lost leaves (`numLeafNodes == file.numNodes`). `nameColored` also runs `update()` on them. The **engine** must therefore accept duplicates and run the literal algorithm (c). Reject or aggregate only at the reader/API level, as an opt-in or behind a warning, so the parity tests can still build these inputs. The default reader policy is still open (README index).
  - The `parsers.md` edge-case row has been corrected to match §3.3.
- **Q4 (`--` in ids):** `StreamlineNode` parses its id with `split("--")` and keeps the first two pieces. A network id or module id containing `--` would corrupt `sourceId`/`targetId`. App ids are base-36, so this is safe there. Should the Python API validate user-supplied network ids, or use tuple keys and render strings only for output?
- **Q5 (colour of out-of-range highlight indices):** should the matplotlib renderer replicate the black fallback from §9, or use the store's default-colour fallback? This is a renderer-only decision.
- **Q6:** the zero-height-group finite tie (§5.2) is untested. Should a fixture cover it?
- **Q7 (threshold units):** `streamlineThreshold` is in absolute layout units (§8). If the Python API allows or defaults to a `height` other than 600, should the renderer default stay `1.0` (TS-faithful), or scale as `height / 600`? This must match whatever `layout.md` Q7 decides about where the option lives.

---

## Appendix: probing the TS engine without touching the repo

This is how the **[verified]** claims were produced. All files live in a scratch directory. Nothing was written into or installed in `web/alluvial`.

```js
// <scratch>/vitest.config.mjs
export default { root: import.meta.dirname, cacheDir: import.meta.dirname + "/.vite-cache",
  server: { fs: { allow: ["/"] } }, test: { include: ["*.test.ts"], watch: false } };
```

The test file imports `Diagram` and `Branch` by absolute path from `…/packages/alluvial-diagram/src/alluvial/` and constructs `new Diagram([{ id, name, nodes: [{id, name, identifier, path, flow, highlightIndex}], … }])`. It then calls `calcFlow()` and `updateLayout(opts)` and writes results with `fs.writeFileSync`, because console output is swallowed by the default reporter. Run it with `<web/alluvial>/node_modules/.bin/vitest run --config ./vitest.config.mjs`.

To capture the **sort keys** (pass-1 values), wrap the getter before calling `updateLayout`, and record only while it runs. The branch sort is the only caller during layout:

```ts
const desc = Object.getOwnPropertyDescriptor(StreamlineNode.prototype, "oppositeStreamlinePosition")!;
Object.defineProperty(StreamlineNode.prototype, "oppositeStreamlinePosition", {
  get() { const v = desc.get!.call(this); if (record) out.push(`${this.currentId} ${v}`); return v; },
});
```

The duplicate-identifier claims in §3.3 used A = `z(1:1, ident z) q(1:2)` with these variants of B:

- `x(1:1, z) y(1:2, z)`: same group, no dangling node; gives a `NULL--` link.
- `w(1:1) x(1:2, z) y(1:3, z)`: same group with a dangling node; `y` is lost and `B.flow = 0.6`.
- `x(1:1, z) y(2:1, z)`: different groups; last wins.
