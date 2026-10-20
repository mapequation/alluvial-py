# Port note: data model and construction

Topic: the alluvial node tree (Diagram > Network > Module > HighlightGroup > Branch >
StreamlineNode > LeafNode), how it is built from parsed network files, how leaf nodes are
added/removed/updated, `Diagram.calcFlow`, `TreePath`, and the data used by
`Module.getSimilarModules`.

Not covered here (see sibling notes): `Diagram.updateLayout` geometry, module ordering
(`utils/Tree.ts`), streamline link geometry/`getLinks`, store coloring operations, label
placement, file parsers.

## 0. Conventions

* All TS citations are relative to
  `packages/alluvial-diagram/src/` in the alluvial web repo, e.g. `alluvial/LeafNode.ts:120`.
  Store citations: `store/DiagramStore.ts`.
* "JS sum" means a left-to-right fold starting at `0`: `xs.reduce((a, b) => a + b, 0)`.
* `LEFT = -1`, `RIGHT = 1` (`alluvial/Side.ts:3-4`).
* **Verified** marks behaviour confirmed by running the real TS engine. Method: the engine was
  transpiled with the repo's own `typescript` package into a scratch directory (no writes to the
  TS repo) and probed from Node:

  ```sh
  cd <ts-repo> && node node_modules/typescript/bin/tsc --outDir <scratch>/build \
    --module commonjs --target es2020 --useDefineForClassFields --esModuleInterop --skipLibCheck \
    --rootDir packages/alluvial-diagram/src packages/alluvial-diagram/src/alluvial/Diagram.ts \
    packages/alluvial-diagram/src/alluvial/index.ts packages/alluvial-diagram/src/utils/entropy.ts
  cd <scratch> && NODE_PATH=<ts-repo>/node_modules node probe.js   # require("./build/alluvial/Diagram.js").default
  ```

  You can reuse this to produce structural fixtures (section 12). To load the sample files in a
  probe the same way the app does, use `require("@mapequation/infomap-parser").parse(text,
  undefined, true, false)` (`parsers/parse-files.ts:65`) and then set
  `node.identifier = String(node.stateId ?? node.id)` (tree/stree id mode, section 3).
  Re-verified 2026-10-10: every example in section 10 reproduces exactly with this build.

## 1. Version split

| Feature | v1 | v2 |
|---|---|---|
| Tree construction (`Diagram`, `Network.addNodes`, `LeafNode.add`) | yes | |
| `TreePath` parsing, incl. `;` (insignificant) and trailing `:` (stree) | yes | |
| Insignificant highlight groups (science `.stree` samples have thousands of them) | yes | |
| `Diagram.calcFlow` | yes | |
| `LeafNode.update` / `remove` / `removeFromSide` (coloring calls `Module.setColor`, which calls them) | yes | |
| `Module.setColor`, `removeColors`, `isHighlighted`, `highlightIndex` | yes | |
| `Module.getSimilarModules` (JS similarity) | yes, used by color matching | |
| `Network.updateFlowThreshold`, `Module.isVisible` | yes, used by layout | |
| `Module.meanNodeId`, `numLeafNodes` | yes, used by sort/size options | |
| `Network.toggleShowBipartiteNodes`, `LeafNode.visible` | optional (cheap) | |
| Per-node `moduleLevel` > 1 from input | accept as data | |
| `Module.expand`, `regroup`, `siblings`, `maxModuleLevel`, `hasSubmodules` | | yes |
| `Network.tree` / `TreeNode` / `hierarchicalChildren` (rendering of parent modules) | | yes |
| Arbitrary per-node `highlightIndex` API (select nodes, metadata, layers) | | yes (engine is the same `update()` path) |
| `Module.move`, `Network.moveToIndex`, `isCustomSorted` | | yes |
| `Network.metadata`, `moduleLinks`, `Module.enterFlow/exitFlow/links` | | not needed for layout |

## 2. Tree shape, constants and the base class

### 2.1 Depth and Side

`alluvial/Depth.ts:3-9`: `ROOT=0, NETWORK=1, MODULE=2, HIGHLIGHT_GROUP=3, BRANCH=4,
STREAMLINE_NODE=5, LEAF_NODE=6`. Each class has a constant `depth` field with its value
(`Diagram.ts:94`, `Network.ts:39`, `Module.ts:13`, `HighlightGroup.ts:10`, `Branch.ts:12`,
`StreamlineNode.ts:11`, `LeafNode.ts:14`).

`alluvial/Side.ts`: `LEFT=-1`, `RIGHT=1`, `sideToString(side)` gives `"left"`/`"right"` (`:6`),
`opposite(side) = -side` (`:8`).

| Class | children | parent |
|---|---|---|
| Diagram | Network[] | none |
| Network | Module[] | Diagram |
| Module | HighlightGroup[] | Network |
| HighlightGroup | exactly `[Branch(LEFT), Branch(RIGHT)]`, fixed | Module |
| Branch | StreamlineNode[] | HighlightGroup |
| StreamlineNode | LeafNode[] | Branch |
| LeafNode | none | **`parent` is `null`** (`LeafNode.ts:43`). It has `leftParent`/`rightParent` (StreamlineNodes) instead |

**Every LeafNode belongs to two StreamlineNodes**: one in the LEFT branch and one in the RIGHT
branch of the same HighlightGroup. Both branches of a group hold the same set of leaves.

### 2.2 `Layout` and `AlluvialNode` (`alluvial/AlluvialNode.ts`)

`Layout` (`:4-35`): `x = y = width = height = 0`. The `layout` setter assigns all four (`:19-34`).

`AlluvialNode` extends `Layout` (`:81-230`):

* fields: `_flow = 0` (`:92`), `children = []` (`:102`), `parent`, `networkId`, `id = ""`
  (ctor `:104-110`). The constructor does **not** attach the node to its parent. Each subclass
  constructor does that explicitly.
* `flow` get/set reads and writes `_flow` (`:94-100`). For every class except LeafNode,
  **flow is a cached field**. It is 0 on a new node and changes only when `Diagram.calcFlow`
  runs (section 8). LeafNode overrides the getter (section 5.2).
* `isFirstChild` / `isLastChild` (`:112-122`): position of `this` in `parent.children`, found by
  identity.
* `isEmpty = children.length === 0` (`:124-126`).
* `numLeafNodes = Σ child.numLeafNodes` (`:128-133`). Overridden by StreamlineNode (it returns
  `children.length`) and HighlightGroup (it returns `left.numLeafNodes`), so each leaf is counted
  once. The base implementation on a LeafNode would return 0, but it is never called.
* `childFlow = JS sum of child.flow over children, in current children order` (`:135-137`).
* `getAncestor(depth)` (`:139-143`): returns `this` if `this.depth === depth`. Returns `null` if
  there is no parent or `this.depth < depth`. Otherwise it recurses on the parent.
  `leaf.getAncestor(x)` is `null` for every `x != LEAF_NODE`, because a leaf's parent is null.
* `addChild(node)`: `children.push(node)`. It **returns the new length** (`:145-147`).
* **`removeChild(node)` is a swap-remove** (`:149-158`):
  ```ts
  index = children.indexOf(node)            // identity
  if (index > -1) { children[index] = children[last]; children.pop() }
  return found
  ```
  Network, Module (for groups) and Branch (for streamline nodes) use it. StreamlineNode
  overrides it with an index-tracked variant (section 6.4).
* `leafNodes()` is a generator: `for child of children: yield* child.leafNodes()` (`:164-168`).
  HighlightGroup overrides it to yield only from `left` (`HighlightGroup.ts:57-59`). LeafNode
  yields itself (`LeafNode.ts:201-203`). The resulting **leaf order** is: groups in
  `module.children` order, then the LEFT branch's streamline nodes in branch order, then the
  leaves in streamline-node order. `getLeafNodes()` takes an array snapshot of this sequence
  (`:160-162`).
* Iteration (`for x of node`) goes over `children` (`:170-172`).
* Traversals:
  * `forEachDepthFirstPreOrder(cb)` (`:183-189`) calls `cb(child, i, children)` and then
    recurses. `forEachDepthFirstPostOrder` (`:191-197`) recurses first. Neither calls `cb` on
    the node it starts from.
  * `forEachDepthFirst{Pre,Post}OrderWhile(predicate, cb)` (`:209-229`) first builds
    `children.filter(predicate)` and then iterates that filtered array. **The index `i` and the
    array passed to `cb` refer to the filtered array.** The layout depends on this, e.g.
    `nodes[i + 1]` is the next *visible* module. A child that fails the predicate is skipped
    together with its whole subtree.
  * In both pre-order variants the callback on `child` runs **before** `child.children` is read
    for the recursion, so a callback that sorts or replaces `child.children` changes the order in
    which that subtree is visited. The layout relies on this. The non-`While` variants iterate
    the live `this.children` array; the `While` variants iterate a filtered copy.
* `Network.children` is **replaced by a new array** in the layout
  (`node.children = [...visibleModules, ...invisibleModules]`, `Diagram.ts:210`), and branch and
  group children are sorted in place. Never cache a `children` list reference across a layout.

## 3. Input records

`parsers/types.ts:12-23` `Node` and `:25-56` `NetworkFile`. The engine reads only these fields:

| field | used by | notes |
|---|---|---|
| `NetworkFile.id` (string) | `Network` ctor (`networkId` and `id`) | Must be unique (`Diagram.ts:108-110` throws). The app generates random `"_xxxxxxxxx"` ids (`utils/id.ts:2-12`, `parsers/parse-files.ts:159`), but `createFile` spreads the parsed contents **after** `id: id()` (`parse-files.ts:159-162`), so a parsed file's own `id` (JSON) wins. Ids end up inside id strings but never affect ordering or geometry. **Must not contain `"--"`** (section 6.1). |
| `name`, `codelength` (`?? 0`), `layerId`, `directed` (`?? false`), `originalId`, `bipartiteStartId`, `modules` | `Network.ts:54-86` | `name` is stored as given (may be undefined). `bipartiteStartId` is copied only if `!== undefined` (`:75-77`), so default -1, but **an explicit `null` is kept** and makes `isBipartite` true (verified; section 7.3). Fix round WP4 (E14): TS now copies it only if `!= null`, as Python always did. `modules` exists only for Infomap-JSON input (enterFlow/exitFlow/links, v2) |
| `nodes[]` | `Network.addNodes` | |
| `node.path` | `TreePath` | string such as `"1:2:3"`, `"1:1:1:"` (stree), `"1;1;63;"` / `"1:1;16;"` (stree), `"5"` (clu), or `number[]` (json: a string path is converted with `TreePath.toArray` at `parsers/set-identifiers.ts:40-42`, so a `;`-containing string path in JSON would become `[1, NaN]`-style garbage) |
| `node.flow` | leaf flow | number, taken as-is (`LeafNode.ts:45`). A missing flow is `undefined` in TS and turns every sum into NaN; require it in Python |
| `node.id` | `LeafNode.nodeId` | physical node id |
| `node.stateId`, `layerId`, `metadata` | LeafNode fields | `!= null` checks (`LeafNode.ts:47-49`): both `null` and `undefined` become `null` |
| `node.name` | `LeafNode.name` | copied as-is, no null check (`:44`) |
| `node.identifier` | cross-network identity key | set by `parsers/set-identifiers.ts`: id mode gives `String(stateId ?? id)` (`:9-11`, `:15-16`; `stateOrNodeId` uses `!= null`), name mode gives `name ?? String(stateId ?? id)` (`:17-18`), multilayer-expanded gives `String(id)` regardless of mode (`:30-35`), tree/ftree/stree use the mode (`:44-47`), clu gives `String(stateId ?? id)` **regardless of mode** and also overwrites `path = String(moduleId)` and `name = String(id)` (`:48-53`), json keeps an existing `identifier` (`:36-38`). Lookups use JS `Map` semantics, so the type matters (`5` ≠ `"5"`); the bundled JSON sample uses journal **names** as identifiers |
| `node.highlightIndex` | `LeafNode.highlightIndex` | optional. Comes from JSON exports, the store's `checkColors` (only when `network.colors === true`, from per-node `color`; `store/DiagramStore.ts:180-210`, assignment at `:196-204`), or the `moveNetwork` write-back (`:539-545`) |
| `node.moduleLevel` | `LeafNode.moduleLevel` | optional. The bundled `science-1998-2001-2007.json` has a **mix** of `moduleLevel: 1` and `2` in every network (e.g. 2764 × 1 and 4142 × 2 in the first), i.e. it was saved with some modules expanded. Also written back by `moveNetwork` |

The JSON `insignificant` field on nodes is **ignored**: insignificance is recomputed from the
path. JSON paths become arrays, so all JSON nodes are significant (section 4).

## 4. `TreePath` (`utils/TreePath.ts`)

> **Erratum (0.5, fix round WP3: E1, E2, E3, P3).** TS and Python now share fixed semantics; the "quirk" rows below
> describe the old behaviour. (1) A path that **contains** `;` (anywhere, not only last) is parsed with the regex, so
> `"1:2;3"` gives `1:2`, `[1,2]`, `[F,T]` (the bare trailing `3` is not matched) instead of `[1,NaN]`. (2) Otherwise one
> trailing `:` is stripped **before** splitting: `"1:1:1:"` gives `[1,1,1]`, level 3 (no phantom `0`), and `"1:"` gives
> `[1]`, level 1. Array paths are kept as given. (3) `isAncestor(p, c)` is `len(p) < len(c) and c.startswith(p + ":")`,
> so `"1"` is no longer an ancestor of `"10:3"`. (4) `calcStatistics` drops an empty last segment of a string path, so
> `numLevels` of `"1:1:1:"` is 3. (5) Infomap-JSON string paths that contain `;` stay strings (`setIdentifiers` no longer
> runs them through `toArray`); other string paths still become arrays.

State: `path: string`, `pathArr: number[]`, `insignificant: boolean[]`,
`ancestorPaths: Map<int, string>`.

Constructor (`:17-52`), step by step:

```python
INSIG_RE = re.compile(r"([0-9]+)([:;])+")  # :3 ; the group's LAST repetition is captured
# JS \d is ASCII-only; Python \d also matches
# Unicode digits, so spell it [0-9] (or re.ASCII)


def __init__(self, path):
    if isinstance(path, list):  # :18-20
        self.path = ":".join(js_num_str(x) for x in path)  # JS Array.join: 1 -> "1", 1.5 -> "1.5"
        self.path_arr = path  # same list object (aliasing harmless)
    else:  # :21-24
        self.path = str(path)
        self.path_arr = js_to_array(self.path)  # split(":") then JS Number() on each part
    last = self.path[-1:]  # :26
    if last == ";":  # :28-38
        self.path_arr, self.insignificant = [], []
        for m in INSIG_RE.finditer(self.path):
            self.path_arr.append(int(m.group(1)))
            self.insignificant.append(m.group(2) == ";")  # separator AFTER this element
        self.path = ":".join(map(str, self.path_arr))
    else:  # :39-46
        if last == ":":
            self.path = self.path[:-1]  # path_arr is NOT recomputed -> keeps trailing 0
        self.insignificant = [False] * len(self.path_arr)
    self.ancestor_paths = {0: "root"}  # :48-51
    for level in range(1, len(self.path_arr)):
        self.ancestor_paths[level] = ":".join(map(str, self.path_arr[:level]))
```

`js_to_array(s)` (`:157-159`) is `s.split(":").map(Number)`. JS `Number("") == 0`, so
`"1:1:1:"` becomes `[1, 1, 1, 0]`. `Number("root")` is NaN. For the inputs that actually occur
(ASCII digits only), `int(part) if part else 0` is enough. Degenerate inputs (verified): `""`
gives `path ""`, `pathArr [0]`, level 1 and module id `""`; `"1;;2;"` gives `[1,2]`, `[T,T]`
(the regex absorbs separator runs).

Methods used by the model:

* `level` (`:54-56`): 0 if `path == "root"`, else `len(path_arr)`. **Quirk:** a trailing-colon
  stree path gets one extra level.
* `ancestorAtLevelAsString(level)` (`:198-200`): `ancestor_paths.get(level) || path`. Level 0
  gives `"root"`. For `level >= len(path_arr)` the result falls back to the **full leaf path**.
* `isSignificant(level)` (`:206-212`): `False` if `level < 0` or
  `level >= len(insignificant)`, else `not insignificant[level]`.
* static `toArray`, `ancestorAtLevel(path, level)` (`:111-114`; level 0 gives the root
  TreePath, otherwise `TreePath(":".join(toArray(path)[:level]))`), `parentPath` (`:132-143`;
  returns null unless the path matches `^(\d+:)*\d+$`; a 1-element path gives root; otherwise the
  string is cut at the last `:`), `isAncestor(parent, child)` (`:96-105`: root is the ancestor
  of everything; otherwise `len(p) < len(c) and c.startswith(p)`, **a plain string prefix with no
  separator check, so `"1"` is an "ancestor" of `"10:3"`**; this only matters for v2 regroup).
  `rank`, `fromArray`, `join`, `equal`, `isParentOf`, `toId` are not needed for v1.

Verified examples (TS output):

| input | path | pathArr | insignificant | level | anc(1) | anc(2) | anc(5) | sig(0) | sig(1) |
|---|---|---|---|---|---|---|---|---|---|
| `"1:1:1:"` | `1:1:1` | `[1,1,1,0]` | `[F,F,F,F]` | **4** | `1` | `1:1` | `1:1:1` | T | T |
| `"1:2;3;"` | `1:2:3` | `[1,2,3]` | `[F,T,T]` | 3 | `1` | `1:2` | `1:2:3` | T | F |
| `"1;2;"` | `1:2` | `[1,2]` | `[T,T]` | 2 | `1` | `1:2` | `1:2` | F | F |
| `"5"` (clu) | `5` | `[5]` | `[F]` | 1 | `5` | `5` | `5` | T | F |
| `"1:2"` / `[1,2]` | `1:2` | `[1,2]` | `[F,F]` | 2 | `1` | `1:2` | `1:2` | T | T |

## 5. `LeafNode` (`alluvial/LeafNode.ts`)

### 5.1 Construction (`:42-61`). The constructor does not attach the node anywhere.

```python
def __init__(self, node, network):
    super().__init__(
        parent=None, network_id=network.network_id, id=node["path"]
    )  # id = raw path (str or list)
    self.name = node.get("name")  # may be None
    self._flow = node["flow"]
    self.node_id = node["id"]
    self.state_id = node.get("stateId") if node.get("stateId") is not None else None
    self.layer_id = node.get("layerId") if node.get("layerId") is not None else None
    self.metadata = node.get("metadata") if node.get("metadata") is not None else None
    self.identifier = node["identifier"]
    self.tree_path = TreePath(node["path"])
    hi = node.get("highlightIndex")
    self.highlight_index = hi if hi is not None and js_is_integer(hi) else NOT_HIGHLIGHTED  # -1
    ml = node.get("moduleLevel")
    self.module_level = ml if js_is_integer(ml) and ml >= 1 else 1  # 0/None/1.5/negatives -> 1 (WP4, E18)
    self.visible = True
    self.left_index = self.right_index = -1  # :26-27
    self.left_parent = self.right_parent = None  # :29-30
    self.opposite_nodes = {LEFT: None, RIGHT: None}  # :32-37
    self.network = network
```

`js_is_integer(x)`: true for finite numbers with an integral value (`1.0` counts). It is false for
booleans: exclude Python `bool` explicitly. Store integers as `int` so that id strings render as
`"1"`, not `"1.0"`.

### 5.2 Derived properties

* `insignificant = not tree_path.isSignificant(module_level - 1)` (`:63-65`). It is a **live
  getter**: it depends on the mutable `module_level`, so `expand`/`regroup` can move a leaf
  between significant and insignificant groups. `HighlightGroup.insignificant`, by contrast, is
  fixed at group creation. For v1
  (`module_level = 1`) this is `True` iff the separator after the first path element is `;`.
  Example: `"1;1;63;"` is insignificant, `"1:1;16;"` is significant. It is also `True` when
  `module_level - 1 >= len(path_arr)` (degenerate).
* `flow` getter: `_flow if visible else 0` (`:67-73`). This one is **live**, unlike every other
  node's flow. The setter writes `_flow`.
* `level = tree_path.level` (`:75-77`).
* `module_id = tree_path.ancestorAtLevelAsString(module_level)` (`:79-81`). For a `.tree` path
  `"1:2:3"` with level 1 this is `"1"`. For clu `"5"` it is `"5"`.
* `childFlow = flow` (`:83-85`, unused by calcFlow).
* `getParent/setParent(side)`, `getIndex/setIndex(side)` (index in that side's
  `StreamlineNode.children`), `getOpposite/setOpposite(side)` (`:87-118`).

### 5.3 `add()`, attaching to the tree (`:120-194`)

```python
def add(self):
    module = self.network.get_module(self.module_id) or Module(
        self.network, self.module_id, self.module_level
    )  # appended to network
    group = module.get_group(self.highlight_index, self.insignificant) or HighlightGroup(
        module, self.highlight_index, self.insignificant
    )  # appended to module
    for branch in group.children:  # [left, right] -> LEFT processed first
        side = branch.side
        opp = self.opposite_nodes[side]
        neighbor = self.network.get_neighbor(side)
        if opp is None:  # :138-141 sticky cache: looked up only while None
            opp = neighbor.get_leaf_node(self.identifier) if neighbor else None
            self.opposite_nodes[side] = opp
        sl_id = StreamlineNode.create_id(self, side, opp)
        sl = self.network.get_streamline_node(sl_id)
        if sl is None:
            sl = StreamlineNode(branch, sl_id)  # appended to branch.children
            self.network.set_streamline_node(sl.current_id, sl)
        if opp is not None:
            opp_side = -side
            opp_branch = opp._remove_from_side(opp_side)  # (1) detach opp FIRST (may swap-remove SLs)
            opp_sl_id = sl.opposite_id
            opp_sl = neighbor.get_streamline_node(opp_sl_id)
            if opp_sl is None:  # (2) THEN create the opposite SL
                opp_sl = StreamlineNode(opp_branch, opp_sl_id)  # appended to opp_branch
                neighbor.set_streamline_node(opp_sl.current_id, opp_sl)
                sl.link_to(opp_sl)  # link only when opp_sl is new
            opp_sl.add_child(opp)  # (3) opp re-appended at the END
            opp.set_parent(opp_sl, opp_side)
        sl.add_child(self)
        self.set_parent(sl, side)
```

Points that change ordering and that a Python port must reproduce:

1. The opposite leaf is **always** detached and re-appended, even when it ends up in the same
   streamline node. Each `add()` therefore moves the opposite leaf to the end of its streamline
   node's `children` (`:161`, `:186`). Leaf order affects the float summation order of flows.
2. The detach (1) happens **before** the new opposite streamline node is created (2). If the
   detach empties the old SL, that SL is swap-removed from `opp_branch` first, and the new SL is
   appended afterwards. Verified in section 10.2.
3. The opposite lookup goes through `neighbor.nodesByIdentifier`, where the last node per
   identifier wins (section 7.3). `opposite_nodes` is cached once found and never re-validated.
   A `None` result is looked up again on every `add()`. The cache is **one-directional**:
   `setOpposite` is only called on `this` (`:140`); `add()` never writes the opposite leaf's
   cache. Verified: after building `[A, B]` with a shared `x`, `B.x.getOpposite(LEFT)` is `A.x`
   but `A.x.getOpposite(RIGHT)` is `null`, so `A.x` looks `B` up again on its next `update()`.
4. `getNeighbor(RIGHT)` is `None` while a network is being built, because the next network does
   not exist yet. During construction, every new leaf's RIGHT streamline node is therefore
   dangling. It is re-linked when the next network's leaves pull the leaf over (section 9).
5. Own SL lookup (`:144-153`) happens **before** the opposite is detached (`:161`). With unique
   identifiers per network the detach cannot delete or re-key `sl`: the two SLs of a linked pair
   hold the same identifiers, apart from `self` itself while it is being re-added, so if `sl`
   still exists the opposite SL keeps at least one other leaf. With duplicate identifiers it
   can: `sl` is made dangling by the detach, then `sl.opposite_id` becomes `"NULL--<sl source id>"` and a
   corrupt SL with that id is created and linked (verified, section 10.6).
6. `module_id`, `highlight_index` and `insignificant` are read from the leaf's **current**
   fields. The store mutates `leaf.highlightIndex` / `leaf.moduleLevel` (public fields) and then
   calls `update()`. `remove()` locates the old group through `left_parent`, never through the
   fields, so a Python port must do the same.

### 5.4 `update()`, `remove()`, `removeFromSide()` (`:196-199`, `:205-231`, `:233-290`)

`update() = remove(); add()`. This is the only mutation path. Callers: `Module.setColor` /
`removeColors` (and through them the store's `colorModule`, `colorMatchingModules`,
`clearColors`, `colorMatchingModulesInAllNetworks`), `expand`/`regroup` (v2), and the store's
`colorNodesInModule` (`store/DiagramStore.ts:659-679`, which first sets `highlightIndex` on all
matching leaves of one network and then updates them one by one; this is safe because leaves of
the same network are never each other's opposites) and `colorSelectedNodes` (`:701-715`).
`clearColors` (`store/DiagramStore.ts:960-974`) calls `removeColors()` only on modules that have a
highlighted group, so unhighlighted modules keep their structure order.

```python
def _remove(self, remove_network=False):  # :205-231 ; called only with False
    group = self.left_parent.get_ancestor(HIGHLIGHT_GROUP) if self.left_parent else None
    self._remove_from_side(LEFT)
    self._remove_from_side(RIGHT)
    module = group.parent if group else None
    network = module.parent if module else None
    if group is not None and group.is_empty:  # both branches empty
        module.remove_child(group)  # swap-remove in module.children
    if module is not None and module.is_empty:
        network.remove_child(module)  # swap-remove + modules_by_id.pop(module_id)
    # remove_network=True branch (:225-230) is dead code: it also detaches the network and
    # clears opposite caches. Do not port it.


def _remove_from_side(self, side):  # :233-290 ; returns the Branch (or None)
    sl = self.get_parent(side)
    if sl is None:
        warn(f"Node {self.id} has no {side_str} parent")
        return None
    branch = sl.parent
    sl.remove_child(self)  # index-tracked swap-remove (6.4)
    self.set_parent(None, side)
    if sl.is_empty:
        opp_sl = sl.opposite  # via link; None if dangling
        if opp_sl is not None:
            neighbor = self.network.get_neighbor(side)
            neighbor.remove_streamline_node(opp_sl.current_id)  # old "X--Y" key
            opp_sl.make_dangling().remove_link()  # target_id=None; both .link=None
            existing = neighbor.get_streamline_node(opp_sl.current_id)  # now dangling id "X"
            if existing is not None:  # merge into the branch's existing dangling SL
                for node in opp_sl.children:  # in order
                    existing.add_child(node)  # appended, indices updated
                    node.set_parent(existing, -side)
                opp_sl.children.clear()
                if opp_sl.parent is not None:
                    opp_sl.parent.remove_child(opp_sl)  # swap-remove from its branch
            else:
                neighbor.set_streamline_node(opp_sl.current_id, opp_sl)  # stays in place, now dangling
        self.network.remove_streamline_node(sl.current_id)  # sl keeps its own linked id
        branch.remove_child(sl)  # swap-remove
    return branch
```

Consequences:

* A Module (or HighlightGroup) whose last leaf is removed is **destroyed**. `add()` then creates
  a **new object**, appended at the end of `network.children` (or `module.children`), with
  `index = len - 1`. For `setColor` this happens exactly for single-leaf modules. Verified:
  network order `1#0 2#1 3#2 4#3` becomes `1#0 4#3 3#2 2#3` after `module 2.setColor(3)`. The
  old object is gone, and `index` values become stale or duplicated. The layout reassigns
  `index` only for **visible** modules and only when `!network.isCustomSorted`
  (`Diagram.ts:197-207`); invisible modules keep a stale index. For a multi-leaf module the
  Module object survives `setColor` (its old group empties only after the new group exists),
  but all its groups are new objects with flow 0.
* New Module/HighlightGroup/StreamlineNode objects have `flow == 0` and `x = y = width =
  height = 0` until `calcFlow` / `updateLayout` run. The store calls `getSimilarModules`,
  `isHighlighted` and `highlightIndex` between `setColor` calls **without** recomputing flows
  (`store/DiagramStore.ts:609-652`). Python must keep flows cached to reproduce this.
* The invariants checked by `alluvial/StreamlineNode.test.ts:33-51` must hold after any
  sequence of operations **provided identifiers are unique per network**: streamline-node ids
  within a branch are unique, each branch has at most one dangling SL, and every SL in a branch
  is registered in its network's map under its `currentId`. (The test does not check the
  converse, i.e. that the map has no extra entries; the Python tests should check both.) With
  duplicate identifiers, `update()` breaks them (section 10.6).

## 6. `StreamlineNode` and `StreamlineLink`

### 6.1 Ids (`StreamlineNode.ts:67-89`)

```python
def part(leaf, side):  # side = side of the branch the SL sits in
    i = "i" if leaf.insignificant else ""
    return f"{leaf.network_id}_module{leaf.module_id}_group{i}{leaf.highlight_index}_{side_str(side)}"


def create_id(source, side, target=None):
    s = part(source, side)
    return s if target is None else s + "--" + part(target, -side)
```

Examples: `A_module1_group-1_right--B_module2_group-1_left` (linked),
`B_module3_groupi-1_left` (dangling, insignificant).

Constructor (`:17-25`): `AlluvialNode(parent=branch, network_id, id="")` (the node's `id` is the
**empty string**; identity is `current_id`). It is appended to `branch.children`, gets
`side = branch.side`, and `source, target = id.split("--")` (`target` is `None` if absent). JS
destructuring takes only the first two parts, so a network id containing `--` corrupts this.

* `current_id = f"{source}--{target}"` if linked, else `source` (`:31-35`).
* `opposite_id = f"{target if target is not None else 'NULL'}--{source}"` (`:37-39`).
* `is_dangling = target_id is None` (`:41-43`).
* `make_dangling()` sets `target_id = None` and returns self (`:111-115`). The SL keeps its
  `source_id`, so its new id is the dangling id of its own group and side.

### 6.2 Links (`StreamlineNode.ts:60-65`, `:117-130`; `StreamlineLink.ts:13-20`, `:102-105`)

* `link_to(opp)`: `reverse = (self.side == LEFT)`, then
  `self.link = opp.link = StreamlineLink(self, opp, reverse)`. With `reverse`, left and right are
  swapped. Result: **`link.left` is always the SL in the left network (a RIGHT-branch SL) and
  `link.right` is the SL in the right network (a LEFT-branch SL).**
* `opposite`: `link.right if link.left is self else link.left`, or `None` without a link.
* `remove_link()`: `link.remove()` sets both endpoints' `.link = None`.
* Invariant (unique identifiers only; see 10.6): an SL is non-dangling iff it has a link.
* `StreamlineLink.highlightIndex = max(left group hi, right group hi)` (`:42-44`). Geometry
  (`x0..h1`, `path`) is documented in the streamlines note.

### 6.3 `oppositeStreamlinePosition` (`StreamlineNode.ts:45-58`), used by the layout's branch sort

```python
g = self.opposite.get_ancestor(HIGHLIGHT_GROUP) if self.opposite else None
return -g.y if (g is not None and g.parent is not None and g.parent.is_visible) else -inf
```

All dangling SLs, and SLs whose opposite module is invisible, tie at `-inf`. Their relative order
after the stable sort is their **pre-sort branch order**, i.e. the construction/swap-remove
history. In JS the comparator `a - b` yields `NaN` for `-inf - -inf`, which the sort treats as
equal. A Python `key=` sort on `-inf` floats gives the same result.

### 6.4 Index-tracked children (`StreamlineNode.ts:91-109`)

```python
def add_child(self, leaf):
    self.children.append(leaf)
    leaf.set_index(len(self.children) - 1, self.side)
    return len(self.children)


def remove_child(self, leaf):
    i = leaf.get_index(self.side)
    found = -1 < i < len(self.children)  # does NOT check children[i] is leaf
    if found:
        self.children[i] = self.children[-1]
        self.children[i].set_index(i, self.side)
        leaf.set_index(-1, self.side)  # if i was last, this resets the same leaf: correct
        self.children.pop()
    return found
```

`num_leaf_nodes = len(children)` (`:27-29`).

## 7. Container classes

### 7.1 `Branch` (`alluvial/Branch.ts:8-23`)

`Branch(parent_group, side)`: `id = "left"` or `"right"`, `network_id = parent.network_id`, and
`is_left = side == LEFT`. The branch does not attach itself: `HighlightGroup` creates both as its
fixed `children`.

### 7.2 `HighlightGroup` (`alluvial/HighlightGroup.ts`)

* `NOT_HIGHLIGHTED = -1` (`:7`).
* Constructor (`:18-31`), defaults `highlight_index = -1`, `insignificant = False`:
  `id = f"{module.id}_group{'i' if insignificant else ''}{highlight_index}"`.
  It is appended to `module.children`. `children = [Branch(self, LEFT), Branch(self, RIGHT)]`
  (`:11-14`); branches are never removed. `highlight_index` and `insignificant` are read-only.
* `is_highlighted = highlight_index != -1` (`:33-35`). `left = children[0]`,
  `right = children[1]`.
* `is_empty = left.is_empty and right.is_empty` (`:45-47`).
* `num_leaf_nodes = left.num_leaf_nodes` (`:49-51`).
* **`child_flow = left.child_flow`** (`:53-55`): the JS sum over the left branch's SL flows.
  The right branch is ignored, even though its sum can differ in the last ulp.
* `leaf_nodes()` yields from `left` only (`:57-59`).
* A group is keyed inside its module by `(highlight_index, insignificant)`:
  `Module.getGroup` = first match in `children` order (`Module.ts:204-210`).

### 7.3 `Network` (`alluvial/Network.ts`)

Constructor (`:54-86`): `AlluvialNode(parent=diagram, network_id=file.id, id=file.id)`. It is
**appended to `diagram.children` immediately** (`:68`), before any node is added. Fields:
`name`, `is_custom_sorted = False` (`:41`), `flow_threshold = 0` (`:42`), `codelength`,
`layer_id`, `directed`, `original_id`, `bipartite_start_id` (`-1`), private maps
`nodes_by_identifier`, `modules_by_id`, `streamline_nodes_by_id` (`:48-50`).
`infomapModulesByPath` and `moduleLinks` are only built from `file.modules` (`:79-85`,
`:456-483`). They are v2 and not used by the layout.

* `add_nodes(nodes)` (`:273-283`):
  ```python
  self.nodes_by_identifier = {}
  leaves = []
  for n in nodes:  # 1) create all, register (later duplicate overwrites)
      leaf = LeafNode(n, self)
      self.nodes_by_identifier[leaf.identifier] = leaf
      leaves.append(leaf)
  for leaf in leaves:  # 2) attach in input order
      leaf.add()
  ```
* `add_child(module)`: append, then `modules_by_id[module.module_id] = module`, return the new
  length (`:285-289`). `remove_child(module)`: swap-remove, then **delete the map entry
  unconditionally** (`:291-295`).
* `get_module(id)`, `get_leaf_node(identifier)`, and `get/set/remove_streamline_node(id)` are
  plain map operations (`:297-337`).
* `get_neighbor(side)` (`:301-321`): looks up `root.children` by `network_id` and returns the
  entry at `idx + side` if it is in range, else `None`.
* `visible_children` = modules with `is_visible`, in `children` order (`:208-210`).
* `update_flow_threshold(hidden_fraction)` (`:250-266`), called at the start of each layout
  (layout note):
  ```python
  max_hidden = hidden_fraction * self.flow
  flows = sorted(m.flow for m in self.children)  # ascending; stable; JS (a,b)=>a-b
  hidden = 0.0
  self.flow_threshold = inf
  for f in flows:
      hidden += f
      if hidden > max_hidden:
          self.flow_threshold = f
          break
  ```
  If the cumulative sum never strictly exceeds `max_hidden` (e.g. fraction 1, or no modules),
  the threshold stays `inf` and every module is hidden. Zero-flow modules never set the threshold
  while `hidden == 0`.
* `toggle_show_bipartite_nodes(show)` (`:100-106`): no-op unless bipartite
  (`isBipartite = bipartite_start_id !== -1`, `:96-98`). Otherwise
  `leaf.visible = show if leaf.node_id >= bipartite_start_id else True`. Quirk: a file with
  `bipartiteStartId: null` stores `null` (ctor `:75-77` only skips `undefined`), so
  `isBipartite` is true and `node_id >= null` is `node_id >= 0` in JS (verified). In Python,
  map `None` to -1 unless parity with this quirk is wanted (open question 7).
* `Diagram.addNetwork` builds the network via `Network.create(parent, file)`
  (`:268-270`), which is just `new Network(parent, file)`.
* `isMultilayer` / `isHigherOrder` / `haveMetadata` (`:88-110`) inspect the first leaf. They
  **throw on an empty network** (`.next().value` is undefined). Guard this in Python. (Erratum, fix round WP6, E12: the
  TS getters use optional chaining, so an empty network is neither multilayer nor higher-order, and `haveMetadata` is
  true when some leaf has metadata.) Exact
  definitions, with `first = next(network.leaf_nodes())` in current order:
  `is_multilayer = first.layer_id is not None`,
  `is_higher_order = is_multilayer or first.state_id is not None`, and
  `have_metadata = first.metadata is not None`. Fixture field `networks[i].isHigherOrder` is
  true exactly for state-id inputs (`states-*`).
* `namePosition` (`:201-206`), `tree`/`TreeNode` (`:216-246`, `:367-454`, v2), `metadata`
  (`:112-199`), `getLinks`/`rightStreamlines` (`:343-362`, streamlines note), and `moveToIndex`
  (`:339-341`, v2 custom sort) are out of scope here.

### 7.4 `Module` (`alluvial/Module.ts`)

Constructor (`:24-43`):
`AlluvialNode(parent=network, network_id, id=f"{network_id}_module{module_id}")`. Then
`module_level`, `module_id`, `path = TreePath.toArray(module_id)` (a number list used by the
layout's margin `differenceIndex`), and `index = network.add_child(self) - 1`, which appends.
`enter_flow` and `exit_flow` default to 0 and `links` to `None`; they are filled from Infomap
module data if present. `margin = 0`, `name = ""`.

Getters:

* `is_visible = self.flow >= network.flow_threshold and self.flow > 0` (`:124-126`, `:180-182`).
  Before the first layout, `flow_threshold == 0`, so visible means `flow > 0`.
* `is_highlighted = any(g.is_highlighted for g in children)` (`:144-146`).
* `highlight_index = largest_group.highlight_index` (`:148-150`). `largest_group` (`:195-202`)
  is a reduce with initial value `{flow: -inf, highlightIndex: -1}` and a **strict `>`**, so the
  first group (in current `children` order) with the maximal *cached* flow wins. An empty module
  gives -1.
* `largest_node_id = max(-1, max(leaf.node_id))` (`:152-158`).
* `mean_node_id` (`:160-169`): JS sum of `leaf.node_id` in `leaf_nodes()` order, divided by `N`.
  Returns `-1` if `N == 0`.
* `max_module_level = max(module_level, max(leaf.level - 1))` (`:171-178`, v2). Because of the
  stree trailing-colon quirk, `"1:1:1:"` leaves report 3 where `.tree` leaves report 2.
* `has_submodules = module_level < max_module_level`; `is_top_module = module_level == 1`;
  `is_leaf_module = not has_submodules` (`:128-138`, v2).
* `parent_index = network.children.index(self)` by identity (`:140-142`).
* `x1 = x`, `x2 = x + width`, plus `namePosition`, `textAnchor` and `idPosition` (`:74-114`,
  labels note).

Mutators:

* `set_color(hi)` (`:283-288`): `for leaf in self.get_leaf_nodes(): leaf.highlight_index = hi;
  leaf.update()`. The loop runs over a snapshot in leaf order. `remove_colors() = set_color(-1)`
  (`:290-292`). Verified reshuffle: section 10.3.
* `expand()` / `regroup()` (`:212-281`, v2) take the same snapshot and run
  `leaf.module_level = new; leaf.update()`. `expand` refuses if any leaf has
  `level <= module_level + 1`. `regroup` refuses at level 1 and processes the leaves of all
  `siblings` (`:184-193`, which uses the prefix-buggy `isAncestor`). Both set
  `network.is_custom_sorted = False`.
* `move(direction)` (`:294-319`, v2): `moveItem` (`utils/array.ts:2-11`) by ±1 and
  `is_custom_sorted = True`.
* `get_largest_leaf_nodes(k=5, aggregate=False)` (`:45-72`, labels note): returns the top k by
  leaf flow via `PriorityQueue` (section 7.5). With `aggregate`, flows are summed per `node_id`
  in leaf order into copies first.

### 7.5 `getSimilarModules(side, numModules=5, threshold=1e-6)` (`Module.ts:321-366`)

This is the data and algorithm used by color matching (`store/DiagramStore.ts:568-587`,
`:613-618`). Exact procedure:

```python
def connected_modules(self, side):  # :384-401 generator
    seen = set()
    for group in self.children:  # current group order
        branch = group.left if side == LEFT else group.right
        for sl in branch.children:  # current branch order
            opp = sl.opposite
            m = opp.get_ancestor(MODULE) if opp else None  # opp.parent.parent.parent
            if m is not None and m.module_id not in seen:
                seen.add(m.module_id)
                yield m


def node_distribution(module):  # :330-338
    d = {}
    for leaf in module.leaf_nodes():  # leaf order (2.2)
        d[leaf.identifier] = leaf.flow  # live leaf flow; dup ids overwrite value, keep position
    keys = js_own_keys_order(list(d))  # !!! JS object key order, see below (fix round WP6, S5: a Map, insertion order)
    return d, keys


def get_similar_modules(self, side, num_modules=5, threshold=1e-6):
    queue = TopK(num_modules)  # PriorityQueue, desc similarity
    this_d, this_keys = node_distribution(self)
    for m in connected_modules(self, side):
        if not m.is_visible:
            continue  # cached m.flow vs network.flow_threshold
        other_d, other_keys = node_distribution(m)
        ids = list(dict.fromkeys(this_keys + other_keys))  # JS Set insertion order
        p = [this_d.get(k, 0) for k in ids]  # JS `?? 0` (a 0 flow stays 0)
        q = [other_d.get(k, 0) for k in ids]
        sim = 1 - js_div(p, q, normalize=True)
        if sim > threshold:  # NaN is never pushed
            queue.push({"module": m, "similarity": sim})
    return queue.to_list()
```

* **JS own-key order** (plain object `{}` at `:333`): keys that are canonical array indices
  (`"0"`, or ASCII digits without a leading zero, with value ≤ 4294967294) come first in
  ascending numeric order. All other keys follow in first-insertion order. Verified:
  `["b","10","a","2","01","-1","4294967295","4294967294","1.5"]` enumerates as
  `["2","10","4294967294","b","a","01","-1","4294967295","1.5"]`. In id mode, identifiers are
  numeric strings, so in practice the vector is **sorted by numeric identifier**. In name mode
  (and in the bundled JSON sample, whose identifiers are journal names) the order is first
  insertion, except for names that happen to be canonical numerals.
* **Prototype keys**: `nodes` is a plain `{}`, so `nodes[id]` reads inherited properties. An
  identifier such as `"constructor"`, `"toString"` or `"hasOwnProperty"` that is absent from one
  module reads the inherited function instead of `undefined`, `?? 0` keeps it, and the arithmetic
  gives NaN, so that module is skipped. `"__proto__"` as a key is never stored at all. Only
  reachable with name-mode identifiers (open question 8).
* `js_div(p, q, normalize=True)` (`utils/entropy.ts:31-53`, `utils/math.ts:1-8`):
  ```python
  def js_log2(x):
      return math.log2(x) if (x > 0 and math.isfinite(x)) else 0.0  # NaN -> 0


  def js_divide(a, b): ...  # IEEE: b == 0 -> nan if a == 0 or isnan(a) else copysign(inf, a) * copysign(1, b)
  def js_normalize(v):  # utils/math.ts:1-4
      s = 0.0
      for x in v:
          s += x  # JS sum
      return [js_divide(x, s) for x in v]  # s == 0 -> all NaN


  def kl(p, q):  # entropy.ts:18-29 (normalize=False path)
      acc = 0.0
      for pi, qi in zip(p, q):
          acc += pi * js_log2(js_divide(pi, qi))
      return acc


  def js_div(p, q, normalize=False):
      if len(p) != len(q):
          raise ValueError
      if normalize:
          p, q = js_normalize(p), js_normalize(q)
      mix = [0.5 * (a + b) for a, b in zip(p, q)]
      jsd = 0.5 * (kl(p, mix) + kl(q, mix))
      if jsd < 0:
          raise ValueError("JSD should be non-negative")  # TS throws too
      return jsd if math.isnan(jsd) else min(max(jsd, 0.0), 1.0)  # JS clamp keeps NaN
  ```
  `kl` uses `pi * log2(pi / mi)` exactly in that form; do not rewrite it as
  `pi * (log2(pi) - log2(mi))`, which differs in the last ulp. A tiny negative `jsd` from
  rounding would throw in TS as well; it has not been observed.
  Verified values: `js_div([1,0,0],[0,1,0],True) = 1`, `js_div([0,0],[1,1],True) = NaN`,
  `js_div([1,1],[1,1],True) = 0`. Note that Python `max(nan, 0)` returns nan but
  `max(0, nan)` returns 0, so write the NaN case explicitly.
* **PriorityQueue** (`utils/PriorityQueue.ts:24-35`, `:49-51`):
  ```python
  def push(self, v):
      if len(self.heap) < self.k:
          self.heap.append(v)
          self.heap.sort(key=lambda x: x["similarity"], reverse=True)  # stable
      elif v["similarity"] > self.heap[-1]["similarity"]:  # compare(v, last) < 0
          self.heap.append(v)
          self.heap.sort(key=..., reverse=True)
          if len(self.heap) > self.k:
              self.heap.pop()
  ```
  On ties, the earlier-inserted item ranks first. A newcomer that ties with the current last
  item is rejected.
* Edge cases: if `self` has zero total flow, every similarity is NaN and the result is `[]`. A
  connected module with zero leaf flow (but `is_visible` from a stale flow) gives NaN and is
  skipped. Dangling SLs and the first/last network contribute nothing. With a single network
  the result is `[]`.
* Result order depends on group order and branch order, i.e. on whether a layout has run
  (layout sorts groups and branch children). The store always calls this after at least one
  layout.

## 8. `Diagram` and `calcFlow` (`alluvial/Diagram.ts`)

* `Diagram(networks=[])` (`:97-103`): `AlluvialNode(None, network_id="", id="root")`, then
  `flow_threshold = 0` (`:95`; overwritten with the layout option by `updateLayout`,
  `:152`), then `for f in networks: self.add_network(f)` **in list
  order**. Network order is fixed after this; the store's `moveNetwork` rebuilds the whole
  diagram (`store/DiagramStore.ts:517-557`).
* `add_network(f)` (`:105-113`): raises if a network with `f.id` already exists. Otherwise
  `Network.create(self, f)` (= `Network(self, f)`, which appends itself) and then
  `.add_nodes(f.nodes)`. Networks can only be appended; there is no `removeNetwork` in use
  (`LeafNode.remove(true)` is dead code).
* `get_network(id)`: first match by `network_id` (`:115-119`).
* `calc_flow()` (`:121-128`) is a post-order traversal with predicate `depth < LEAF_NODE`, so
  the callback runs on every node except the leaves and the Diagram itself:
  ```python
  def calc_flow(self):
      def visit(node):
          for child in [c for c in node.children if c.depth < LEAF_NODE]:
              visit(child)
              child.flow = child.child_flow

      visit(self)


  # child_flow: StreamlineNode/Branch/Module/Network -> JS sum of children's flow in CURRENT order
  #             HighlightGroup -> left.child_flow
  ```
  * `StreamlineNode.flow` is the sum of `leaf.flow` (0 for invisible leaves) in leaf order.
  * `Branch.flow` is the sum of SL flows in branch order. The left and right branch flows can
    differ in the last ulp.
  * `HighlightGroup.flow` is the left-branch SL sum.
  * `Module.flow` is the sum of group flows. `Network.flow` is the sum of **all** module flows,
    visible or not.
  * `Diagram.flow` is never set and stays 0.
* The store runs `calcFlow()` and then `updateLayout()` on every relayout
  (`store/DiagramStore.ts:485-491`). The first call after construction therefore sums in
  **insertion order**. Later calls sum in the orders the previous layout left behind (sorted
  groups, sorted branch SLs, visible-first modules), so flows can change in the last ulp between
  relayouts. `moveSelectedModule` runs a layout **without** `calcFlow` (`:500-511`).
  Verified float sensitivity: module flow `0.1+0.2+0.3+0.15 = 0.7500000000000001`, but after
  re-grouping the same leaves as `(0.1+0.15+0.3)+0.2` it is `0.75` (section 10.3).

## 9. Construction walkthrough (what the tree looks like after `Diagram(files)`)

For network `k` (0-based), built after networks `0..k-1` are complete:

1. Modules are appended to `network.children` in order of first appearance of their
   `module_id` among the input nodes. Groups are appended to `module.children` in order of first
   appearance of `(highlight_index, insignificant)` within the module.
2. LEFT side of each leaf `b`:
   * If network `k-1` has a leaf `o` with the same identifier, `b` goes into the linked SL
     `k_…_left--(k-1)_…_right` (created on first use, appended to `b`'s left branch).
   * `o` is pulled out of its current RIGHT SL in network `k-1`. On first contact that is the
     dangling `(k-1)_…_right`. The dangling SL is swap-removed from its branch when it becomes
     empty.
   * `o` is then appended to the linked SL `(k-1)_…_right--k_…_left`, which is created and
     appended to `o`'s right branch if new, and linked.
   * Otherwise `b` goes into the dangling `k_…_left` of its group.
3. RIGHT side of each leaf in network `k`: always the dangling `k_…_right` of its group. It is
   fixed up when network `k+1` is added.
4. Therefore:
   * The LEFT branches of the first network and the RIGHT branches of the last network contain
     only dangling SLs. With a single network every SL is dangling and there are no links.
   * Each group's dangling LEFT SL (network 0) and dangling RIGHT SL (last network) hold the
     group's leaves in input order. LEFT SLs of network `k ≥ 1` are created in order of first
     use and hold their leaves in network-`k` input order.
   * RIGHT branches of non-last networks: linked SLs are **appended** in order of first contact
     from the next network, but this is **not** their final order. The dangling SL starts at
     slot 0; when it empties it is swap-removed, so the most recently appended linked SL jumps
     into its slot (10.2 ends as `[S_B3, S_B1, S_B2]`, not `[S_B1, S_B2, S_B3]`). A surviving
     dangling SL (leaves without a counterpart) stays wherever the swap-removes left it.
   * Leaves inside a linked RIGHT SL of network `k-1` are in the order in which network `k`'s
     leaves pulled them (network-`k` input order), because each pull re-appends at the end.
   * Leaves without a counterpart stay in the group's dangling SL on that side.
5. Duplicate identifiers inside network `k`: `nodes_by_identifier` keeps the last one. When two
   `k`-leaves both match the same `o`, `o` is stolen by the later one. If that empties `o`'s
   previous linked SL, the earlier `k`-leaf's left SL becomes dangling (verified in section
   10.4). Duplicates inside network `k-1`: only the last one is ever matched; the others stay
   dangling on the right.

## 10. Verified examples (use as unit tests)

Dump format: `NET id flow`, `MOD module_id index flow`, `GRP id flow`, then
`branch SL current_id flow [leaf identifiers in children order]`. Run after `calc_flow()`, with
no layout applied.

### 10.1 `debug5_0.tree` (A) + `debug5_1.tree` (B), sample data

Identifiers are node ids. A: `1:1:1 0.2 1`, `1:1:2 0.2 82`, `1:2:3 0.2 144`, `2:1:1 0.2 171`,
`2:2:2 0.2 179`. B: `1:1:1 0.2 1`, `1:2:1 0.2 82`, `2:1:1 0.2 144`, `2:1:2 0.2 171`,
`2:2:3 0.2 179`.

```
NET A flow=1
  MOD 1 index=0 flow=0.6000000000000001
    GRP A_module1_group-1 flow=0.6000000000000001
      left  SL A_module1_group-1_left                                 0.6000000000000001 [1,82,144]
      right SL A_module1_group-1_right--B_module1_group-1_left        0.4                [1,82]
      right SL A_module1_group-1_right--B_module2_group-1_left        0.2                [144]
  MOD 2 index=1 flow=0.4
    GRP A_module2_group-1 flow=0.4
      left  SL A_module2_group-1_left                                 0.4 [171,179]
      right SL A_module2_group-1_right--B_module2_group-1_left        0.4 [171,179]
NET B flow=1
  MOD 1 index=0 flow=0.4
    GRP B_module1_group-1 flow=0.4
      left  SL B_module1_group-1_left--A_module1_group-1_right        0.4 [1,82]
      right SL B_module1_group-1_right                                0.4 [1,82]
  MOD 2 index=1 flow=0.6000000000000001
    GRP B_module2_group-1 flow=0.6000000000000001
      left  SL B_module2_group-1_left--A_module1_group-1_right        0.2 [144]
      left  SL B_module2_group-1_left--A_module2_group-1_right        0.4 [171,179]
      right SL B_module2_group-1_right                                0.6000000000000001 [144,171,179]
```

The `.stree` versions give the identical structure. Note A module 1's RIGHT branch: the dangling
SL emptied while node 144 moved, *before* `…--B_module2…` was created, so the order is
`[B1-link, B2-link]` and not `[B2-link, B1-link]`.

### 10.2 Swap-remove reorder (synthetic)

A: `1:1 .1 #1`, `1:2 .2 #2`, `1:3 .3 #3`, `1:4 .15 #4`, `2:1 .25 #5`.
B: `1:1 .1 #1`, `2:1 .2 #2`, `3:1 .3 #3`, `2:2 .15 #4`, `3:2 .25 #6`.

```
A MOD 1 flow=0.7500000000000001, GRP A_module1_group-1
   left  A_module1_group-1_left                           [1,2,3,4]
   right A_module1_group-1_right--B_module3_group-1_left  [3]      <- swapped into slot 0
   right A_module1_group-1_right--B_module1_group-1_left  [1]
   right A_module1_group-1_right--B_module2_group-1_left  [2,4]
A MOD 2: right A_module2_group-1_right (dangling, #5 absent from B) [5]
B MOD 3 GRP B_module3_group-1
   left  B_module3_group-1_left--A_module1_group-1_right  [3]
   left  B_module3_group-1_left                           [6]      (dangling, #6 absent from A)
   right B_module3_group-1_right                          [3,6]
```

Trace for A module 1's right branch:

1. Start with `[D]`. Leaf #1 is moved, then `S_B1` is created: `[D, S_B1]`.
2. #2 is moved: `[D, S_B1, S_B2]`.
3. #3 is moved: `[D, S_B1, S_B2, S_B3]`.
4. #4 is moved and empties `D`, which is swap-removed: `[S_B3, S_B1, S_B2]`. `S_B2` already
   exists, so nothing is appended.

### 10.3 `update()` / `setColor()` reshuffle (continuing 10.2)

After `A.getLeafNode("2").highlightIndex = 0; .update()`, followed by `calcFlow`:

```
A MOD 1 flow=0.75
  GRP A_module1_group-1 flow=0.55   left [1,4,3]   right: …B_module3 [3] | …B_module1 [1] | …B_module2 [4]
  GRP A_module1_group0  flow=0.2    left [2]       right: A_module1_group0_right--B_module2_group-1_left [2]
B MOD 2 GRP B_module2_group-1  left: …--A_module1_group-1_right [4] | …--A_module1_group0_right [2]
```

Then `A.getModule("1").setColor(1)`, which updates the snapshot order `[1,4,3,2]`:

```
A MOD 1 flow=0.75 hi=1, single GRP A_module1_group1
  left  [1,4,3,2]
  right …--B_module1_group-1_left [1] | …--B_module2_group-1_left [4,2] | …--B_module3_group-1_left [3]
B MOD 2 left  B_module2_group-1_left--A_module1_group1_right [4,2]     (right stays [2,4])
B MOD 3 left  B_module3_group-1_left [6] | B_module3_group-1_left--A_module1_group1_right [3]
```

`A.getModule("1").getSimilarModules(RIGHT)` gives
`[(B_module2, 0.6617550740496512), (B_module3, 0.4646241078641882), (B_module1, 0.2961169789042666)]`.

> **Erratum (0.5, fix round WP5: E4, E6).** §10.3's re-creation of an emptied module no longer happens on a
> recolour: `remove()` keeps a module whose `moduleId` equals the leaf's (E4). §10.4 and §10.6: `add()` links only
> mutually registered leaves (`neighbor.getLeafNode(id)` is taken only when `this.network.getLeafNode(id) === this`),
> so the registered (last) duplicate links and the others stay dangling. §10.4's result is unchanged. In §10.6, B's
> first `y` stays dangling (`B_module1_group-1_left [y]`), A's `y` links to B module 2, and no `update()` produces a
> `NULL--…` id. `parseAcceptedFiles` warns once per file with duplicate identifiers (non-fatal); Python keeps its
> reader warning.

### 10.4 Duplicate identifier (synthetic)

A: `1:1 .5 x`, `2:1 .5 y`. B: `1:1 .3 x`, `2:1 .3 x`, `2:2 .4 y`. Result: B module 1's left SL
is the dangling `B_module1_group-1_left [x]`. A's `x` is linked to B module 2:
`A_module1_group-1_right--B_module2_group-1_left [x]`.

### 10.5 Scale check

`science2001_2y.stree` + `science2003_2y.stree` build in about 150 ms in Node. Network 2001 has
7170 leaves, 44 modules, 52 groups (10 insignificant), 261 SLs (52 dangling) and
`flow = 1.0000000077991007`. Network 2003 has 7323 leaves, 35 modules, 41 groups
(6 insignificant), 257 SLs (48 dangling) and `flow = 1.0000000675572005`. Each network's first
module has the groups `[…_group-1, …_groupi-1]`.

### 10.6 Duplicate identifier corrupts `update()` (synthetic)

A: `1:1 .5 x`, `1:2 .5 y`. B: `1:1 .3 x`, `1:2 .3 y`, `2:1 .4 y`. After construction, B module
1's left SL `B_module1_group-1_left--A_module1_group-1_right` holds `[x, y]`, but its partner
in A holds only `[x]` (the second B `y` stole A's `y`). Then `B.getLeafNode("x").update()`
gives:

```
A MOD 1: right A_module1_group-1_right--B_module2_group-1_left [y] | NULL--B_module1_group-1_left [x]
B MOD 1: left  B_module1_group-1_left [y,x]     (dangling id, but it still has a link)
```

The `NULL--…` SL and a linked SL under a dangling id both violate the section 5.4 invariants.
This is the reason to reject or de-duplicate identifiers in the Python readers (open question 2).

## 11. Edge cases summary

| Case | Behaviour |
|---|---|
| Single network | All SLs dangling, no links. `get_neighbor` returns None on both sides. `getSimilarModules` returns `[]` |
| First / last network | LEFT (first) and RIGHT (last) branches hold only dangling SLs |
| Leaf missing in neighbour | Stays in its group's dangling SL on that side. At most one dangling SL per branch |
| Zero-flow leaf | Kept in the structure and contributes 0. A module with total flow 0 is invisible (`flow > 0` required) |
| `visible = False` leaf (bipartite) | `flow` reads 0 everywhere. The structure is unchanged |
| Empty module / group | Removed (swap) when its last leaf leaves for another module. A module the leaf goes straight back into (recolour) is kept since fix round WP5 (E4); an emptied group is still removed and re-created |
| Empty network (`nodes == []`) | Network with no modules, `flow` 0. `isMultilayer`-style getters throw in TS. Layout divides by the max network flow (layout note) |
| Duplicate network id | `add_network` raises |
| Network id containing `--` | Corrupts SL id parsing. Reject in Python |
| Duplicate identifiers | Last wins in lookups. ~~Construction steals/dangles (9.5, 10.4); a later `update()` can corrupt the SL graph (`NULL--…` ids, 10.6)~~ Since fix round WP5 (E6) only the registered leaf links; other duplicates stay dangling (§10 erratum) |
| `bipartiteStartId: null` | ~~Kept as `null`, so `isBipartite` is true and `toggleShowBipartiteNodes` hides every node with `node_id >= 0` (7.3)~~ Fixed in WP4 (E14): read as absent (-1) in TS and Python |
| Missing `node.flow` | `undefined` in TS, so every sum becomes NaN. Require it. Fix round WP4 (E9): `Network.create` and the readers reject a missing, NaN or infinite flow in both engines |
| Identifier equal to an `Object.prototype` key (name mode) | `getSimilarModules` yields NaN for affected pairs (7.5) |
| `moduleLevel` ≥ path depth (`len(path_arr)`) | `module_id` falls back to the leaf's full (stripped) path, because `ancestor_paths` only has levels `< len(path_arr)`. `insignificant` is True if `module_level - 1 >= len(path_arr)`; at `module_level == len(path_arr)` it is the last element's separator. Negative `moduleLevel` is kept by the ctor and also gives the full path and `insignificant = True` |
| stree trailing `:` | ~~`path_arr` gets a trailing 0, so `level` is one higher~~ Fixed in WP3 (E1, §4 erratum) |
| JSON array paths | No `;` information, so every node is significant |
| Stale caches after `update()` | New nodes have flow 0, x/y 0 and a stale `Module.index` until `calc_flow` / layout (layout re-indexes visible modules only) |

## 12. Python port guidance

### Suggested structure

```
alluvial/
  model/
    constants.py      # Depth ints, LEFT/RIGHT, NOT_HIGHLIGHTED, side_str
    tree_path.py      # TreePath (section 4)
    nodes.py          # AlluvialNode, Diagram, Network, Module, HighlightGroup, Branch,
                      # StreamlineNode, StreamlineLink(minimal), LeafNode — one file avoids import cycles
    jscompat.py       # js_sum, js_divide, js_log2, js_is_integer, js_own_keys_order, TopK, js_div
  layout.py, ordering.py, ...   (other notes)
```

* Use plain classes with `__slots__`. Mirror the TS method names in snake_case so the citations
  stay traceable. Keep `depth` as a class attribute and use `isinstance` where TS uses
  `instanceof`.
* Port the **operations literally** (append, swap-remove, index tracking, detach before create)
  rather than deriving the final orders. The orders feed the stable sorts in the layout and the
  float summation order, so any shortcut will diverge on ties and in the last ulp.
* Add a `dump_structure(diagram)` helper that emits the section-10 format as JSON, and compare it
  with TS-generated dumps (section 0 explains how to produce them without touching the TS repo).
  Compare ids and orders exactly, and flows with `==` (0 ulp).

### Pitfalls

1. **`sum()` is compensated in Python ≥ 3.12.** Verified: `sum([0.1]*10) == 1.0` in py314,
   while JS reduce and `functools.reduce(operator.add, xs, 0)` give `0.9999999999999999`. Use
   an explicit left-to-right loop (`js_sum`) for every `childFlow`, `meanNodeId`, `normalize`,
   KL accumulator and threshold cumulative sum. Never use `math.fsum` or numpy reductions
   (pairwise) in the model.
2. **Identity, not equality.** `indexOf`, `findIndex(child === this)` and `Set`/`Map` of nodes
   are identity-based. Do not give nodes `__eq__` (no `@dataclass` with `eq=True`). `list.index`
   / `list.remove` / `in` call `__eq__`. Use an identity helper
   (`next(i for i, c in enumerate(xs) if c is x)`) to be explicit.
3. **Never `list.remove()` / `del xs[i]` for children.** Every removal is a swap-remove. Only
   `Network.moveToIndex` (v2) shifts elements.
4. **Flows are cached fields**, except `LeafNode.flow`. Do not turn them into computed
   properties. New nodes start at 0, and the coloring code relies on that staleness.
5. **Order inside `LeafNode.add()`**: neighbour lookup, then get/create own SL, then detach the
   opposite leaf (possibly swap-removing its old SL), then get/create the opposite SL plus link,
   then append the opposite leaf, then append self. LEFT before RIGHT.
6. **Network attaches before its nodes**, so `get_neighbor(RIGHT)` is None while building.
7. **Id strings**: `f"{network_id}_module{module_id}_group{'i' if insig else ''}{hi}_{side}"`.
   `hi` must be an int (`-1`, not `-1.0`). `module_id` is the TreePath string (`"1"`,
   `"1:2"`). The SL's own `id` is `""` and its key is `current_id`.
8. **JS value checks**: `!= null` covers both null and undefined, so use `is not None`.
   `moduleLevel` uses `Number.isInteger` and `>= 1` (fix round WP4, E18; before: JS truthiness, so negatives were
   kept); exclude `bool`. `??` keeps 0.
9. **JS object key order** in `getSimilarModules` (section 7.5). A Python dict keeps insertion
   order, which is wrong for numeric-string identifiers.
10. **`Math.log2` ≠ `math.log2` in the last ulp**: about 0.1–0.2 % of inputs differ by exactly
    1 ulp (measured 231 and 343 of 200,000 on two random input sets; never more than 1 ulp;
    V8 uses an fdlibm-derived log2). Similarity values
    therefore match only to about 1e-15. Use a tolerance in tests. If exact tie-breaking in
    color matching ever matters, port fdlibm `e_log2.c` (open question 4).
11. **NaN**: JS `Math.max(NaN, 0)` is NaN while Python's `max` depends on argument order.
    `NaN > threshold` is False in both. Python raises on `x / 0.0`, so use `js_divide`.
12. **TreePath regex** `(\d+)([:;])+`: group 2 is the last character of the separator run.
    Use `[0-9]` in Python (`\d` matches Unicode digits; JS `\d` does not).
    Trailing `:` strips the string but not `path_arr` (before fix round WP3; see the §4 erratum). `ancestorAtLevelAsString` falls back to
    the full path.
13. Recursion depth is at most 6, so recursive traversals are fine. Snapshot children
    (`list(...)`) wherever TS uses `filter` before iterating.

## 13. Open questions

1. ~~**Fixture procedure.**~~ **Resolved** (`tools/ts-fixtures/README.md`): the fixtures replicate
   the store exactly. That is `parseAcceptedFiles` → `setNetworks` (`checkColors`, construction,
   `calcFlow`, `updateLayout`), then the real store colour ops, which interleave `setColor` with
   stale flows and end with `calcFlow` + `updateLayout`. Tie orders therefore follow the
   "coloured afterwards via `setColor`" path (10.3). Section 5.3-5.4 is v1 work.
2. **Duplicate identifiers** within a network: replicate the TS steal/dangling behaviour (9.5),
   or raise or warn in the Python readers? Construction alone is deterministic and replicable,
   but any later `update()` (coloring) can corrupt the SL graph (10.6). **Constraint:** the
   fixtures `states-tree__name` and `states-tree__nameColored` contain duplicates (different
   groups, no corruption), and `nameColored` runs `update()` on them. So the engine must run
   the literal algorithm on duplicates, both for construction **and** for `update()`. The open
   part is the reader/API default: warn (recommended, keeps the parity tests simple) or raise
   with an opt-out.
3. (Resolved: both fixed in TS and Python in fix round WP3, §4 erratum.) **Quirks to keep for v2**: the `TreePath.isAncestor` string-prefix bug (`"1"` is treated as
   an ancestor of `"10:3"`, which affects `regroup` siblings) and the stree trailing-colon extra
   level (which affects `max_module_level` and `expand`). Replicate them for parity, or fix them
   and document the divergence?
4. **Exact `log2`**: is a ~1e-15 tolerance on similarities acceptable (it affects only
   near-exact ties in color matching)? The alternative is a pure-Python port of V8/fdlibm log2.
5. **JSON inputs with `moduleLevel > 1`** (the bundled science JSON mixes `moduleLevel` 1 and 2
   within each network): in v1, honor them (mixed-level modules without expand/regroup UI; the
   layout's margin `differenceIndex` then compares paths of different lengths) or force level 1?
6. **`LeafNode.id`** is the raw `path` (str or list) in TS. The Python port should probably store
   `str(TreePath)` for hashability. In the engine it is only used in the `removeFromSide` warning
   (`LeafNode.ts:240`) and as `node` in real-valued `Network.metadata` entries (`Network.ts:144`,
   v2). React components were not checked.
7. (Resolved in fix round WP4, E14: `null` is absent in TS too.) **`bipartiteStartId: null`**: replicate the TS quirk (network becomes "bipartite" with start
   id 0) or treat `None` as absent (-1)? Proposal: treat as absent and document.
8. **Identifiers that collide with `Object.prototype` keys** in `getSimilarModules` (7.5): replicate
   the NaN or ignore? Proposal: ignore (plain dict semantics) and document; only name-mode inputs
   with names like `"constructor"` are affected.
