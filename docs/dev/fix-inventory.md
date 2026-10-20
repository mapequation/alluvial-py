# Fix inventory: TS engine/app defects and the Python emulations they cause

Round-2 phase 1 (read-only). Every TS row was re-checked against the web repo at master `d0abf3b`. TS paths are relative
to `packages/alluvial-diagram/src/` unless they start with `apps/web/`. Python paths are relative to `src/alluvial/`.
The sources are the port notes (`docs/dev/port-notes/*.md`), `design.md`, `STATUS.md`, `tools/ts-fixtures/README.md`,
the worklog and the CHANGELOG, plus a fresh read of the TS sources.

**Evidence tags.** `[src]` means read in the current TS source. `[note]` means verified by an earlier probe in the cited
port note. `[P-1]`, `[P-2]` and `[P-3]` are this phase's probes (§3). They ran the bit-exact Python engine with the
candidate fix patched in, which predicts the TS behaviour after the same fix (the engine is a literal port: 248 fixtures
are byte-identical and the differential fuzzer is clean).

**Recommendation key.** **FIX**: fix in TS and Python together, then regenerate the fixtures. **KEEP**: deliberate, or
harmless and documented. **LOW**: real but rare or cosmetic, so do it only if cheap.

## 1. Summary

| ID | Item | Rec |
|---|---|---|
| B1 | Batch `setModuleOrder`: one layout instead of one per adjacent swap (bit-identical, [P-1]) | **FIX** |
| B2 | Batch `setModuleLevel`: one layout instead of one per expand (same visible modules, last-ulp only, [P-2]) | **FIX** (owner: semantics) |
| E1 | `TreePath` trailing `:` keeps a phantom level | **FIX** |
| E2 | `TreePath.isAncestor` string-prefix bug (regroup collapses `10`, `11`, …) | **FIX** |
| E3 | `;` parsed only when it is the last character | LOW |
| E4 | `LeafNode.update()` destroys and re-creates single-leaf modules (the root of 5 colour quirks) | **FIX** |
| E5 | No-op recolours still run `update()` | **FIX** |
| E6 | Duplicate identifiers corrupt the streamline graph | **FIX** |
| E7 | Stale `index`/`margin` of hidden and custom-sorted modules | **FIX** |
| E8 | `verticalAlign: "top"` is declared but does nothing | LOW (remove) |
| E9 | NaN/missing flows load, so the sort order depends on V8's TimSort | **FIX** (reject at load) |
| E10 | The branch-sort comparator returns NaN for two `-Infinity` keys | LOW |
| E11 | The `highlightIndex`/`nodeId` sort keys are summed over sub-modules | LOW (owner) |
| E12 | First-leaf network getters (`haveMetadata`, …) skip or throw | LOW→FIX |
| E13 | Wrong variance and box/pdf bounds in `Network.metadata` | **FIX** (TS only) |
| E14 | `bipartiteStartId: null` makes a network "bipartite" | LOW |
| E15 | `Network.tree` throws on a visible `P` together with a visible `P:x` | **FIX** (the new save format can reach it) |
| E16 | Engine inefficiencies (Tree O(n²), `getNeighbor`, tree rebuilds, `console.time`) | LOW |
| E17 | `--` inside a network id corrupts the streamline ids | LOW |
| E18 | `moduleLevel` in input is not validated (0 → 1, negatives kept) | LOW |
| S1 | `colorMatchingModulesInAllNetworks` resets its colour counter for every network pair | **FIX** (owner) |
| S2 | Similarity colouring colours hidden left modules and seeds chains from them | LOW (owner) |
| S3 | `colorModuleIdsInAllNetworks`: no clear, and object key order | **FIX** (small) |
| S4 | `colorByLayer`/`colorByPhysicalId` do not clear first | LOW |
| S5 | `getSimilarModules` uses a plain object (key order, prototype keys) | **FIX** |
| S6 | `colorRealMetadata`: leaves at the data maximum get no colour | **FIX** (small) |
| S7 | `checkColors` dummy index 0 / no remapping of array palettes | **FIX** |
| S8 | `setStreamlineThreshold` re-runs the full layout | LOW |
| S9 | Out-of-palette index renders black | KEEP |
| H1 | `Module.move` boundary counts hidden modules | LOW→FIX |
| H2 | `moveSelectedModule` lays out without `calcFlow` | KEEP |
| H3 | `moveNetwork` loses the palette, names and order, and miswrites duplicates | **FIX** (TS only) |
| H4 | The Expand button is enabled for modules that `expand` refuses | **FIX** (UI) |
| H5 | `regroup` takes hidden siblings and jumps deeper siblings straight to the new level | KEEP |
| P1 | Unknown or uppercase extension: identifiers are left undefined | **FIX** |
| P2 | A zip is detected only by MIME type `application/zip` | **FIX** |
| P3 | JSON string paths go through `TreePath.toArray`, which drops `;` and gives NaN | **FIX** |
| P4 | Top-level JSON keys override `id`/`format`/`haveModules` | LOW |
| P5 | `mergeMultilayerFiles` forces identifier mode `"id"` | LOW |
| P6 | Multilayer layer order follows JS integer-key order | KEEP |
| P7 | `calcStatistics` quirks (NaN reset, first-node flags) | LOW |
| P8 | Stored `identifier`s pin the identifier mode on reload | KEEP |
| P9 | Dead 2019 diagram load/save code and sample | **FIX** (delete) |
| X1 | infomap-parser: `higherOrder` is never set | LOW (upstream) |
| X2 | infomap-parser: name slicing, tabs in `.clu`, quotes in names | LOW (upstream) |
| L1 | The web app has no "save diagram" at all | **FIX** |
| L2 | Web-app network files carry no version/format tag | **FIX** |
| L3 | Options, module names, custom order and scheme are lost on save→load | **FIX** |
| L4 | Old 2019 saved-diagram format in Python | **FIX** (drop) |
| L5 | Network ids and multilayer `layerId`/`originalId` are not written | LOW |
| U1 | The margin slider label shows half the real margin | **FIX** (trivial) |
| U2 | Visible-flow slider float noise | LOW |
| U3 | No module labels on middle networks | KEEP |
| U4 | `streamlineFraction = 0` makes the streamlines invisible | LOW |
| Y1-Y16 | Python-only emulations and inefficiencies (§10) | see §10 |

## 2. Batch operations for `module_order` and `module_level` (B1, B2)

### B1: `setModuleOrder`, one layout, bit-identical to today's move sequence

**Today.** The TS has no reorder op. Python's `DiagramStore.apply_module_order` (`engine/store.py:636-709`) and the
harness macro `runModuleOrder` (`tools/ts-fixtures/harness.ts:471`) issue one `moveSelectedModule("down")` per
adjacent swap. Each swap is `Module.move` (`Module.ts:294-319`), followed by `moveToIndex` and a full
`diagram.updateLayout` without `calcFlow` (`store/DiagramStore.ts:500-511`). The number of layouts equals the
number of inversions, so the cost grows quadratically with how far modules move. Measured on `science*_2y.stree` at
`module_level=2` (429 visible modules in network 0): reversing 40 modules takes 780 moves and **228 s**, while one
layout takes about 0.3 s.

**Proposed TS** (minimal, in the style of the existing code):

```ts
// alluvial/Network.ts
// `modules`: every visible module of this network exactly once, bottom to top.
setVisibleOrder(modules: Module[]): boolean {
  const visible = this.visibleChildren;
  if (modules.length !== visible.length || new Set(modules).size !== modules.length ||
      modules.some((m) => m.parent !== this || !m.isVisible))
    throw new Error("setVisibleOrder needs every visible module exactly once");
  if (modules.every((m, i) => m === visible[i])) return false;   // no-op keeps isCustomSorted
  this.children = [...modules, ...this.children.filter((m) => !m.isVisible)];
  this.isCustomSorted = true;
  return true;
}

// store/DiagramStore.ts
setModuleOrder(orders: [Network, Module[]][]) {
  let changed = false;
  for (const [network, modules] of orders) changed = network.setVisibleOrder(modules) || changed;
  if (changed) {
    this.diagram.updateLayout(this);   // like moveSelectedModule: flows are unchanged, no calcFlow
    this.toggleUpdate();
  }
  return changed;
}
```

**Python.** Add the same `Network.set_visible_order` and `DiagramStore.set_module_order`. `apply_module_order`
keeps its validation and its target composition (listed modules, `...`, and unlisted modules above), then calls
`set_module_order` once and records one op, `{op: "setModuleOrder", order: [[networkIndex, [moduleId, ...]], ...]}`.
The harness macro `moduleOrder` records the same op. Delete the move loop. `move_module` stays for single moves.

**Why it is exact, and what the per-step layouts leave behind.**

- A move never runs `calcFlow`. Flows, `network.flow` and the per-network threshold are therefore unchanged, so the
  visible set is constant.
- Pass 1 and pass 2 rewrite every field of every visible module, group, branch and streamline node from the order,
  the flows and the margins.
- `module.index` is not written while `isCustomSorted` is set (`Diagram.ts:197-208`). It is stale in both paths, and
  stale in the same way.
- Hidden modules are never laid out (`Diagram.ts:176-180, 322-325`). Their rectangles are identical in both paths.
- The only history-dependent states are these two:
  - **Branch order on equal finite sort keys.** Step 7 is a stable sort on the current pass-1 group `y`. `-Infinity`
    keys (dangling streamlines, or ones pointing at hidden modules) are tied in every layout, so their relative order
    never changes. A finite tie needs two opposite groups at exactly the same pass-1 `y` (zero-height groups, mostly
    with `zeroMargins`). An intermediate layout could have ordered such a pair differently.
  - **Stale margins of hidden modules that were once visible.** The 20 % cap multiplies every module's margin on every
    layout (`Diagram.ts:264-271`), so N layouts scale a stale margin N times. Such a margin is never drawn. E7(b)
    removes this effect.
- **[P-1]:** 10 datasets × 5 option sets × levels 1-3 × 4 random/reverse/`...` orders gave **550/550 cases with
  bit-identical full state**: visible and hidden modules, groups, branch orders, streamline nodes, flows and link paths.
  With the batch patched into the fixture tests, every `test_layout_reproduces_v4_fixture` for the `*order*`
  scenarios still passes. Only `test_v4_module_order_macro_issues_the_recorded_ops` fails, as expected.
- Variant: batch **with** `calcFlow` (`store.updateLayout()`) differed from the move sequence in last bits in 248 of
  the 550 cases, because the flows are re-summed in the new branch order. That variant is not recommended.

**Fixture impact.** Geometry and state stay byte-identical. Only `inputs.operations` changes (one `setModuleOrder`
instead of N `moveModule`) in the 10 v4 scenarios with a `moduleOrder` macro:
- `multilevel-tree__{colored__order, colored__order__roundTrip, colored__namesOrder__roundTrip, default__order, default__orderReverse, level2__order, level2Highlight__order, sortNodes__order}`
- `planted-ftree__{coloredSortHighlightIndex__order, flowThreshold40__orderHidden}`

`multilevel-tree__default__orderNoop` keeps no op. If the fixtures record `updateLayoutCalls`, that count drops.

**Risk.** Low. Owner decision: should an order equal to the current one still set `isCustomSorted`? As proposed it
does not, which matches today's "no moves" behaviour.

### B2: `setModuleLevel`, expand rounds without intermediate layouts

**Today.** `apply_module_level` (`engine/store.py:585-615`, harness `runModuleLevel` `harness.ts:448`) runs one
`store.expand` per module, and each one is `Module.expand` followed by `calcFlow` and a full layout. The order within a
round is the `network.children` order after the previous layout, and eligibility is re-checked before each expand
with the threshold of the last layout. Cost on science `module_level=2`: **7.7 s**.

**Proposed TS** (the eligibility rule is the existing one, factored into a `Module.canExpand` getter; see H4):

```ts
setModuleLevel(levels: number | number[]) {
  const ks = this.diagram.children.map((_, i) => (Array.isArray(levels) ? levels[i] : levels));
  let changed = false;
  this.diagram.children.forEach((network, i) => {
    for (;;) {
      const round = network.children.filter((m) => m.isVisible && m.moduleLevel < ks[i] && m.canExpand);
      if (!round.length) break;
      round.forEach((m) => m.expand());                   // leaf updates only, no layout
      changed = true;
      this.diagram.calcFlow();                            // new sub-modules get their flow
      network.updateFlowThreshold(this.flowThreshold);    // visibility for the next round
    }
  });
  if (changed) this.updateLayout();
}
```

**What the per-expand layouts provide that this drops.**
1. The re-sorted `children` before each expand. The batch expands in `children` order of the moment, so sub-modules
   are appended in a different order. That changes the hidden-module order and the order among equal-key visible
   modules.
2. Per-expand eligibility re-checks. The batch re-checks per round.
3. Branch re-sorts between expands. These change the `calcFlow` summation order and therefore the last bits.
4. Stale `index`/`margin` of hidden modules.

**[P-2]** (10 datasets × 5 option sets × k = 2-4, 140 cases): the visible module sets and their order were **identical
in all 140 cases**. The positions were bit-identical in 136 cases and differed by less than 1e-9 (last bits) in the 4
science cases.

A second variant expanded every module, hidden ones included, with no threshold refresh. It also kept the visible sets,
but differed by an ulp in 16 cases (`fuzz1347` and science). It does useless work and in principle moves the threshold, so it
is not recommended.

**Speed:** science k=2 drops from 7.7 s to 1.8 s.

**Fixture impact** ([P-3], last bits and hidden order). Every scenario with a `moduleLevel` macro changes:
- `debug5-stree__level3`, `fuzz1347__level4`, `mlayer-split__level2`, `prefix-tree__regroupPrefixDeep`
- `multilevel-tree__{level2, level2Colored, coloredLevel2, level2Highlight, level2SortNodeId, level3, level3Geometry, level3Justify40, level3Regroup, levelMixed}`
- v4 `multilevel-tree__{level2__order, level2Highlight__order, level2__names__roundTrip}`

**Risk.** Low to medium, because the semantics of the recorded fixtures change. **Owner decision.** Alternative: keep
the literal rounds (the cost is linear in the number of expanded modules, unlike B1).

## 3. Probe method

All probes are scratch scripts in the session scratchpad. Nothing was written to either repo. They load
`alluvial.layout._build_store` from `src/` and patch candidate fixes into the Python engine.

- **[P-1]** `order_probe.py`: legacy `apply_module_order` against the B1 batch, comparing a full state dump.
- **[P-2]** `level_probe.py`: legacy `apply_module_level` against batch variants, comparing visible sets, order and
  positions.
- **[P-3]** `fixpatch.py`: a pytest plugin (`-p fixpatch`, selected with `FIX=...`, no cache or bytecode written into
  the repo). It ran `tests/test_engine_fixtures.py`, `test_v3_fixtures.py` and `test_v4_fixtures.py` (329 tests)
  with each fix applied. The failing scenario ids are the fixtures that the same TS fix will change.
  - The baseline passes 329/329.
  - S1 was additionally checked on the a/b/c example of colors-render §6.1. Without the fix, all 5 modules get index 0.
    With it, `b.2` and `c.1` get `scheme[1]`.

## 4. Engine (`alluvial/*`, `utils/*`)

| ID | What happens (verified source) | User impact | TS fix | Python change (emulation deleted) | Fixtures that change | Risk | Rec |
|---|---|---|---|---|---|---|---|
| E1 | `TreePath` builds `pathArr` from the raw string (`utils/TreePath.ts:23`) but strips a trailing `:` only from `path` (`:40-43`), so `"1:1:1:"` becomes `[1,1,1,0]`. `calcStatistics` also counts the empty segment (`parsers/calc-statistics.ts:15-20`). [src][note] | `.stree` files of the debug5 kind get one extra expandable level. Expanding to it makes every leaf its own module, and `numLevels` is off by one. | In the non-`;` branch, strip the trailing `:` **before** `TreePath.toArray`, and drop an empty last segment in `calcStatistics`. | `tree_path.py:83-102` (and the module docstring `:5-7`), plus the stats in `io/text.py`. The phantom-level docs go. | [P-3] all 17 `debug5-stree__*`, v3 `debug5-stree__colored__roundTrip`, `fuzz1347__level4`, `fuzz1347__ops`, `fuzz2455__ops` | Low | **FIX** |
| E2 | `TreePath.isAncestor` is `c.startsWith(p)` with no separator (`utils/TreePath.ts:96-105`). It is used by `Module.siblings` (`Module.ts:184-193`). The same prefix flavour appears in the store's expand selection (`store/DiagramStore.ts:456-458`). [src][note] | Regrouping `1:2` also collapses `10:*`, `11:*`, … whenever a parent has 10 or more modules. | `return c.startsWith(p + ":")` (after the root and length checks). The selection uses `TreePath.isAncestor(moduleId, m.moduleId)`. | `tree_path.py:141-148`, `engine/module.py:210` docstring | [P-3] `multilevel-tree__expandRegroup` (+v3 `__roundTrip`), `multilevel-tree__level3Regroup`, `prefix-tree__regroupPrefix`, `prefix-tree__regroupPrefixDeep` (these then pin the fixed behaviour) | Low | **FIX** |
| E3 | `;` is honoured only when it is the last character (`utils/TreePath.ts:28`). `"1:2;3"` becomes `[1, NaN]`, which gives a module `"NaN"`. [src][note] | Hand-made or unusual stree paths only | Parse with `insignificantPathRexeg` whenever the string contains `;`. | `tree_path.py` | none | Low | LOW |
| E4 | `update() = remove(); add()` (`alluvial/LeafNode.ts:196-199`). `remove()` swap-removes a module that has emptied (`:217-223`) even when the leaf goes straight back into it (colour ops: `Module.setColor` `Module.ts:283-288`, `colorSelectedNodes`, `colorBy*`, metadata ops). The replacement is a **new** `Module`, appended with flow 0 and therefore invisible until `calcFlow`. [src][note] | This one cause produces five colour quirks: (a) live-iteration skip, where the last visible module of a network without hidden modules keeps its old colour (`store/DiagramStore.ts:597, 725, 783-788, 798-818, 826-844, 857-879, 892-917, 935-955`); (b) `colorMatchingModules` chains stop at a single-leaf module (`:568-587`); (c) `colorNodesInModule` does not propagate a single-leaf source (`:666-667`, `getLeafNodes()` after `setColor` is `[]`); (d) `colorMatchingModulesInAllNetworks` is not idempotent; (e) stale `Module` references in `B.links`. | `remove()`: `if (module?.isEmpty && module.moduleId !== this.moduleId) network?.removeChild(module);`. `update()` is the only caller. `expand`/`regroup` change `moduleLevel` before `update()`, so they still remove the old module. | `engine/leaf_node.py:183-196`. Delete the skip detection and warning in `apply_highlight` (`engine/store.py:744-782`), the skip-lemma docs (v2-highlight §2.2) and the hlskip caveats. `_visible_leaf_walk` may iterate plainly. | [P-3] `debug5-stree__expandHighlight`, `fuzz1347__ops`, `fuzz2455__ops`, `fuzz670__ops`, `hlskip-tree__{categoricalSkip, colorByPhysicalId, colorMatchingModulesSingle, colorMatchingModulesThrough, colorNodesInModuleSingle}`, `science-stree__nameColored` | Medium: the core mutation primitive. Run `StreamlineNode.test.ts` invariants plus a fuzz campaign. | **FIX** |
| E5 | `Module.setColor` runs `update()` on every leaf even when `highlightIndex` does not change (`Module.ts:283-288`). So do `clearColors` and repeated `colorModule`. [src][note] | Needless remove/re-add churn reorders streamline nodes, so tie orders and last bits change. Before E4 it also re-created modules. | Skip leaves whose `highlightIndex` already equals the target (in `setColor`, and as a guard in the store loops that assign then `update()`). | `engine/module.py:301-304` | [P-3] `planted-ftree__defaultColorChange`, `planted-ftree__highlightThenClear` (with E4: the union of both lists) | Low | **FIX** |
| E6 | `nodesByIdentifier` keeps the last duplicate (`alluvial/Network.ts:274-279`). In `add()` every duplicate looks up the same opposite leaf (`LeafNode.ts:134-141`) and re-attaches it (`:157-188`), so the second steals it. Same-group duplicates in network k that match a node in k-1 give `NULL--…` streamline ids and a leaf missing from its LEFT branch. A later `update()` re-steals through the cached opposite. [src][note] | Name mode on state networks (states share a physical name) and duplicate rows give a corrupted graph and undercounted flow. | Link only mutually registered leaves: `c = neighbor?.getLeafNode(id); opposite = c && this.network.getLeafNode(c.identifier) === this ? c : null`. Other duplicates stay dangling (deterministic, no stealing). The benign outcome is unchanged, because the registered (last) duplicate links. Add a load-time warning listing duplicate identifiers. | `engine/leaf_node.py:128-150`. `Network.built_leaf_nodes` remains only as the writers' input-order list. The reader warning stays. | [P-3] `dupname-tree__highlight`, `fuzz1347__level4`, `states-json__name`, `states-tree__{name, nameColored, nameColorSelectedNodes}`, v3 `states-ftree__colored__name__roundTrip` (orders and last bits; the corrupt cases are fixed) | Medium: fuzz with duplicates | **FIX** |
| E7 | (a) `module.index` is written only when `!isCustomSorted`, and only for visible modules (`Diagram.ts:197-208`), so it goes stale after moves. (b) The 20 % cap multiplies the margin of **every** module, hidden ones included, on every layout (`:264-271`). Hidden modules keep their last rectangle and margin. [src][note] | Nothing is drawn wrong. The dumps and fixtures carry stale numbers, and this state is why B1/B2 needed proofs. | (a) After the partition, always run `visibleModules.forEach((m, i) => (m.index = i))`. (b) Set `invisibleModules.forEach((m) => (m.margin = 0))` in the network callback (`:193-210`). | `engine/diagram.py:110-116, 165-175` | [P-3] (a) 15 scenarios: `multilevel-tree__{move, moveDown, moveExpand, moveSetOption}`, v3 `multilevel-tree__moveDown__roundTrip`, the 10 v4 `*order*`. (b) none. | Low | **FIX** |
| E8 | `VerticalAlign` includes `"top"` (`Diagram.ts:12`), but only `"justify"` is handled (`:277`), so `"top"` behaves as `"bottom"`. [src] | None in the UI, which offers bottom/justify only (`apps/web/src/components/Sidebar/Layout.tsx:164-167`). | Remove `"top"` from the type (or implement it). | Python already rejects it. A restored state with `"top"` warns. | none | Low | LOW |
| E9 | Flows are not validated. `Number("nan")` passes the parser and a JSON node without `flow` gives `undefined`, so NaN propagates (`parsers/parse-files.ts:77-82` has no check). NaN keys make the comparators inconsistent (`utils/Tree.ts:47-51`, `Network.ts:252-254`, `Diagram.ts:309-312`), and the order then depends on V8's TimSort. [src][note] | Garbage geometry (all `y` NaN) instead of an error | In `parseAcceptedFiles`, after `setIdentifiers`, reject a file with any node whose `flow` is not a finite number (`invalid-format`). | Readers reject non-finite, missing and `null` flows (`io/json_reader.py:134-137`, `io/text.py`). **Delete** the V8 TimSort port (`engine/_utils.py:208-575`, `js_sort`, the NaN path of `sort_by_number` `:577-593`) and `tests/test_engine_jssort.py`. | `nan-tree__default`, `nan-tree__colored`, `nan-multilevel__expand` become reader-rejection tests. The fuzzer stops generating NaN flows. | Low | **FIX** |
| E10 | The branch sort is `a.pos - b.pos` with `-Infinity` keys (`Diagram.ts:309-312`, `StreamlineNode.ts:45-58`), so `-Inf - -Inf = NaN`. V8 treats NaN as "not less", which is consistent and therefore stable, but only by accident. [src][note] | none | `(a, b) => (a.pos === b.pos ? 0 : a.pos - b.pos)` | none (Python key sort) | none | Low | LOW |
| E11 | `Tree` sums the sort key over sub-modules (`utils/Tree.ts:38`) for every key, including `highlightIndex` (`-index`) and `nodeId` (mean id) (`Diagram.ts:401-404`). [src][note] | With expanded modules, a parent of 3 sub-modules with mean id ≈ 100 sorts as 300, and colour sorting mixes indices. | Give `Tree` an aggregator: sum for flow/nodes, max (or mean) for `highlightIndex`/`nodeId`. | `engine/tree.py` | `multilevel-tree__level2SortNodeId` and other sortNodeId/highlightIndex scenarios with levels (not probed) | Low | LOW (owner) |
| E12 | `isMultilayer`, `isHigherOrder` and `haveMetadata` read only the first leaf, and throw on an empty network (`.value.layerId` of undefined) (`Network.ts:88-94, 108-110`). [src][note] | Metadata colouring skips a whole network if its first leaf has no metadata. | Use `?.value?.`, and `haveMetadata` = some leaf has metadata. | Delete the parity `TypeError` in `_have_metadata` (`engine/store.py:71-78`). | `planted-ftree__categoricalNoMetaFirst` (its purpose; not probed) | Low | LOW→FIX |
| E13 | `Network.metadata` "variance" is `E[X²]·N/(N-1) − mean²` ("Placeholder", `Network.ts:146, 163-167`), and `pdfBounds` uses the variance as if it were the standard deviation (`:169-176`). [src] | Wrong statistics in the Real-metadata panel (UI only) | Proper sample variance and standard deviation | not ported | none | Low | **FIX** (TS only) |
| E14 | `bipartiteStartId !== undefined` keeps `null` (`Network.ts:75-77`), so `isBipartite` is true and the toggle hides every node (`:100-106`). [src][note] | Hand-made JSON only | `!= null` | Remove the documented divergence. | none | Low | LOW |
| E15 | `Network.tree` throws `"Module added to non-leaf TreeNode"` when a visible `P` and a visible `P:x` coexist (`Network.ts:216-246, 417-420`). The React default `hierarchicalModules = "shadow"` crashes. It is reachable through per-node `moduleLevel` in loaded files (the web-app save format, L1) and through `moveNetwork` with duplicates (H3). [src][note] | Crash on load of an inconsistent file | (a) In `tree`, when the node for the module's own path already exists as a non-leaf, add the module to that node (the outline encloses `P` and its sub-modules). (b) Validate `moduleLevel` consistency at load: lift `P`'s leaves to the level of their siblings, with a warning. | `engine/network.py:278`. Remove the catch-and-warn path in `geometry.py:558-565`. | none (add a scenario) | Low | **FIX** |
| E16 | Inefficiencies: linear `find` per path segment and a `concat` flatten (`utils/Tree.ts:29-31, 58-66`, O(n²)); `getNeighbor` uses `findIndex` per leaf and side (`Network.ts:301-321` from `LeafNode.ts:135`); `Module.maxModuleLevel` scans every leaf ("FIXME optimize", `Module.ts:171-178`); `Network.tree` is rebuilt on every access (`Network.ts:212-246`, read per render in `react/ModulesWrapper.tsx:26`); `console.time` in hot paths (`Diagram.ts:122, 127, 141, 374`, `store/DiagramStore.ts:218, 233, 524, 556, 605, 655`), which is console noise for library users since #45. The cap comment says 50 % while the code uses 0.2 (`Diagram.ts:258`). [src] | Slower large diagrams, console noise | Map lookup in `Tree`; push-based flatten; cache the network index; memoise `tree` per layout (`updateFlag`); remove or guard `console.time`. | `engine/tree.py` the same (optional) | none | Low | LOW |
| E17 | Streamline ids are split on `--` (`StreamlineNode.ts:21`), and a JSON top-level `id` can contain `--`. [src] | Broken links for such ids | Reject `--` in `Diagram.addNetwork` (`Diagram.ts:105-113`). | Already rejected | none | Low | LOW |
| E18 | `moduleLevel` from input: `node.moduleLevel && Number.isInteger(...)` (`LeafNode.ts:56-59`). 0 becomes 1, and a negative value is kept, which gives the full path and `insignificant`. [src][note] | Hand-made files | Accept integers ≥ 1 only. | same | none | Low | LOW |

## 5. Store operations (`store/DiagramStore.ts`)

| ID | What happens | User impact | TS fix | Python change | Fixtures | Risk | Rec |
|---|---|---|---|---|---|---|---|
| S1 | `let highlightIndex = 0` sits **inside** the network-pair loop (`:621`), so chains that start in network ≥ 1 reuse `scheme[0], scheme[1], …`. [src][note] | Unrelated modules get the same colour (the a/b/c example: all 5 modules have index 0). | Hoist the counter above the loop (`:609`). | `engine/store.py:242` | [P-3] **none of the 329**; add a scenario (a/b/c) | Low (visible colours change only for such inputs) | **FIX** (owner) |
| S2 | Similarity colouring iterates **all** left modules (`:613`). The single-network branch also colours hidden modules (`:597`). Hidden modules consume scheme colours and can seed chains into visible modules. [src][note] | Gaps in the visible palette, and occasionally an odd chain | Iterate `visibleChildren` | `engine/store.py:224-237` | likely many `*__colored` (not probed) | Medium (colours change) | LOW (owner) |
| S3 | `colorModuleIdsInAllNetworks` does not clear first (`:735-793`): the registry grows and hidden modules keep old colours. The multilayer branch groups modules in a plain object (`:763-779`), so integer-like module ids iterate in numeric order before the stable flow sort. [src][note] | Stale colours after mixed ops; tie order by id | Call `clearColors(false)` first; use a `Map`. | Delete the `js_own_keys_order` use (`engine/store.py:317-328`). | Map: [P-3] none. Clear: `planted-ftree__colorOpsMixed` and fuzz ops (not probed). | Low | **FIX** (small) |
| S4 | `colorByLayer` and `colorByPhysicalId` do not clear (`:795-847`). [src] | Stale colours after mixed ops | Call `clearColors(false)` first. | `engine/store.py:468-489` | fuzz ops only (not probed) | Low | LOW |
| S5 | `getSimilarModules` builds `{[identifier]: flow}` (`Module.ts:333-337`). `Object.keys` puts integer-like ids first (numeric), which sets the `js_div` summation order. Prototype keys (`constructor`, `__proto__`) give NaN or lost entries in name mode, and duplicates within a module are last-write. [src][note] | Name-mode identifiers like "constructor" break matching | `Map<string, number>` (insertion order). Summing duplicates instead of last-write is a separate owner choice. | Delete `js_own_keys_order` in `engine/module.py:355-358`. | [P-3] **none** (similarities are not dumped; only exact ties could move) | Low | **FIX** |
| S6 | `colorRealMetadata` bins are half-open `[x0, x1)` (`:908-913`), and the UI's d3 bins end at the data maximum, so the max-valued leaves get no colour. [src][note] | Visible uncoloured nodes | Make the last bin inclusive. | `engine/store.py:507-525` (not public) | `planted-ftree__realMetadata` (not probed) | Low | **FIX** |
| S7 | `checkColors` registers array-form palettes with a dummy index `0` (`:185-193`, `:190`) and never remaps node indices to the merged palette. A later `colors: true` file maps an already-seen colour to 0. [src][note] | Wrong colours when files list colours in different orders or mix forms | Per file, map local index → merged index (`node.highlightIndex = merged.get(file.colors[node.highlightIndex])`) and store real indices. | `engine/store.py:155-184` | [P-3] `jscolors-abc__default`, v3 `jscolors-abc__default__roundTrip` | Low | **FIX** |
| S8 | `setStreamlineThreshold` calls `updateLayout()` (`:274-277`), but the layout does not read it (only `getLinks` does). [src][note] | A wasted layout, plus order churn in the last bits | `toggleUpdate()` only | `set_option` path | `planted-ftree__setOptions` if it sets it (not probed) | Low | LOW |
| S9 | An index past the palette gives `undefined`, which draws black (`utils/highlight-color.ts:14-17`, `:314-323`). [src] | Only with inconsistent files (S7) | none | Python cycles the palette and warns (deliberate) | none | – | KEEP |

## 6. Hierarchy, moves and network ops

| ID | What happens | User impact | TS fix | Python change | Fixtures | Risk | Rec |
|---|---|---|---|---|---|---|---|
| H1 | `Module.move` checks its boundary against **all** children (`Module.ts:302-311`). Moving the top visible module up swaps it with a hidden one. The move "succeeds" and freezes the order (`isCustomSorted`), but nothing changes visibly. [src][note] | The `w` key on the top module silently freezes the order. | Boundary on `visibleChildren`: warn and return `false`. | `engine/module.py` move | `planted-ftree__moveHidden` (its purpose; not probed) | Low | LOW→FIX |
| H2 | `moveSelectedModule` lays out without `calcFlow` (`:500-511`). [src][note] | none (flows are unchanged) | keep (B1 relies on it) | `move_module` keeps it | – | – | KEEP |
| H3 | `moveNetwork` (`:517-557`) rebuilds through `setNetworks`, so `checkColors` empties the palette and every coloured leaf renders black. `Module.name`, the custom order and `isCustomSorted` are lost. The write-back `network.getLeafNode(node.identifier)` (`:541-545`) gives every duplicate the registered leaf's level and colour, which can create E15 states. [src][note] | Moving a network left or right destroys colours and names. | Save `highlightColors` and restore them after the rebuild (or set `file.colors`); copy `Module.name` by `moduleId`; write back per node by input index (keep the leaves in input order, as Python's `built_leaf_nodes`); optionally re-apply the order with B1. | not ported (deferred API) | none; add TS unit tests | Low | **FIX** (TS only) |
| H4 | The Expand button is enabled when `!isLeafModule` (deepest leaf, `apps/web/src/components/Sidebar/Module.tsx:75-76`; `Module.ts:136-138, 171-178`), but `expand` refuses a module whose **shallowest** leaf is too shallow (`Module.ts:221-230`). [src][note] | The button shakes instead of working. | `Module.canExpand` getter (the refusal rule), used by the button and by B2 | `_expandable` (`engine/store.py:924-929`) uses the same rule | none | Low | **FIX** (UI) |
| H5 | `regroup` takes hidden siblings and sets every sibling leaf to the new level (`Module.ts:255-279`). [src][note] | intended | – | – | – | – | KEEP |

## 7. Parsers and IO (`parsers/*`, `apps/web`)

| ID | What happens | User impact | TS fix | Python change | Fixtures | Risk | Rec |
|---|---|---|---|---|---|---|---|
| P1 | `format = fileExtension(name)` is not validated (`parsers/parse-files.ts:42-47`). `x.TREE` parses, `setIdentifiers` does nothing (`parsers/set-identifiers.ts:30-54`), and every node gets identifier `undefined`, so all nodes "match" (a massive E6). [src][note] | Corrupt diagram from an uppercase extension | Lower-case the extension and check it against the supported formats; otherwise report `invalid-format`. | Python dispatches on the suffix (check case-insensitivity). | none | Low | **FIX** |
| P2 | A zip is recognised only by `file.type === "application/zip"` (`parsers/parse-files.ts:100`). Chrome on Windows reports `application/x-zip-compressed`. [src][note] | The saved `.zip` (L1) fails to load on Windows. | Also accept the `.zip` extension and the `x-zip-compressed` MIME type. | n/a | none | Low | **FIX** |
| P3 | JSON string paths are converted with `TreePath.toArray` ("TODO: remove", `parsers/set-identifiers.ts:39-42`). `"1:2;3;"` becomes `[1, NaN]` and stree insignificance is lost. [src][note] | Saved stree diagrams lose their insignificant groups or get a "NaN" module. | Keep string paths. `LeafNode`/`TreePath`/`calcStatistics` accept strings. | The JSON reader keeps string paths. The web-app writer may then write raw paths with `;` (`io/saved_diagram.py:401-404`). | v3 `webAppReload` of the stree round trips (`debug5-stree__colored__roundTrip`, `insig-stree__*__roundTrip`) become exact. | Low | **FIX** |
| P4 | `createFile` spreads the JSON contents after `id: id()` (`parsers/parse-files.ts:151-163`), so a top-level `id`, `format` or `haveModules` overrides the defaults. Loading the same file twice then throws on a duplicate id (`Diagram.ts:108-110`). [src][note] | Hand-made files | Ignore `id`/`format` from the contents (or whitelist keys). | Python writers omit `id`. | none | Low | LOW |
| P5 | `mergeMultilayerFiles` re-identifies in mode `"id"` (`parsers/multilayer-utils.ts:37`). [src][note] | Name mode is lost after a merge. | Pass the store identifier. | not ported | none | Low | LOW |
| P6 | Layer order comes from JS object integer keys (`parsers/multilayer-utils.ts:50, 80`), which is ascending for Infomap ids. [src][note] | fine | – | `io/multilayer.py` keeps it | – | – | KEEP |
| P7 | `calcStatistics`: `!flowDistribution[top]` resets on 0 or NaN (`parsers/calc-statistics.ts:22-25`); `isMultilayer`/`isStateNetwork` come from the first node (`:32-33`); an empty node list throws (rejected by accident). [src][note] | Statistics only | Use `?? 0`, use `some()`, add an explicit empty-file error. | `io/` stats | none | Low | LOW |
| P8 | For JSON, `node.identifier ?? id(node)` (`parsers/set-identifiers.ts:38`): stored identifiers ignore the load dialog's identifier mode. [src][note] | Saved files keep their matching, which is right for round trips. | Document it. | same | – | – | KEEP |
| P9 | Dead 2019 diagram code: `createFilesFromDiagramObject` ("TODO remove", `parsers/from-diagram.ts`, still exported `parsers/index.ts:6`); `apps/web/src/io/save-diagram.js`, which is imported nowhere and throws because `getModuleNames` was removed; and `apps/web/public/data/science-1998-2001-2007.json`, which is unused. [src] | none | Delete them. The removed export is an API change of the package. | see L4 | the v3 `saved`/`reload` blocks go (L4) | Low | **FIX** |
| X1 | External `@mapequation/infomap-parser` 1.0.2 (not in this repo): `/^# higher order/` has no capture group, so `higherOrder` is never set (`node_modules/@mapequation/infomap-parser/dist/index.js:566`). [src] | Dead data (the engine does not read it) | Upstream fix | `io/text.py` keeps `False` | none | – | LOW |
| X2 | Same package: an unquoted name is sliced `name[1:-1]`; `split(" ")` breaks `.clu` files that use tabs; a `"` inside a name shifts the columns. [note] | Hand-made files (Infomap always quotes) | Upstream fix | `io/text.py` mirrors it while TS uses the package | none | – | LOW |

## 8. Save and load (new format only)

Today's web app loads one Infomap-JSON file per network, dropped together or as a `.zip`. Each file carries `colors`
and per-node `highlightIndex`, `moduleLevel` and `identifier` (v3-webapp-json §4). The **app cannot save** anything
except SVG (`apps/web/src/components/Sidebar/Export.tsx`). The only writers are the harness (`webAppFiles`,
`tools/ts-fixtures/harness.ts:1265`) and Python `webapp_files` (`io/saved_diagram.py:383-419`).

| ID | What happens | TS fix | Python change | Fixtures | Risk | Rec |
|---|---|---|---|---|---|---|
| L1 | No save in the app | Move the writer into the package (`serializeNetworks(store)` → `[{name, text}]`, the harness logic). Add "Save diagram (.zip)" to the Export panel (JSZip is already a dependency), with P2 and P3 fixed. | `webapp_files` stays byte-identical to the package writer (generate `webAppFiles` fixtures from it, not from a harness copy). | the v3/v4 `webAppFiles` blocks, if field order changes | Low | **FIX** |
| L2 | No version or format tag. A saved file is indistinguishable from plain Infomap JSON, and Infomap's own top-level `version` (`"v2.15.1"`) is already a mapped key (`io/json_reader.py:31`), so it cannot double as the format tag. | A namespaced key, e.g. `"alluvial": {"format": 1, "generator": "alluvial-diagram 1.x" \| "alluvial-py 0.x"}`. It is spread onto the NetworkFile but inert in `createFile`. Warn on an unknown future `format`. | The writer emits it and the reader checks it. | all `webAppFiles` blocks | Low | **FIX** |
| L3 | Lost on save→load: layout/display options, `Module.name`, the custom module order (`isCustomSorted`), the scheme name, stree insignificance (P3) | Carry them in the namespaced key: `options` (a subset of `OPTION_KEYS`), `moduleNames {moduleId: name}`, `moduleOrder [visible ids bottom→top]` (re-applied with B1 after the build), `scheme`. Restore them in a store helper after `setNetworks`. | Read and write the same. Drop the loss warnings (`layout.py:486-494`, `_warn_webapp_losses`). | new round-trip scenarios | Medium (design: `saveload-plan.md`) | **FIX** |
| L4 | Old 2019 format (`{version: "0.3.0", timestamp, state, networks}`): the current TS cannot load it (`parsers/parse-files.ts` rejects it) and the writer is dead (P9). | Delete it (P9). | Drop `SavedDiagram`, `from_saved_diagram`, `diagram_json`, `SAVE_VERSION`, `save_diagram(format="diagram")`, the `read()` branches (`io/__init__.py:201, 370`), `restore_state`, `_restore_module_names`, the `;`→NaN warning, the harness `saveDiagram`/`getModuleNames` shim (`harness.ts:1202-1240`), the v3 `saved`/`reload` blocks and `webapp-science-trim__load*`. Give a clear error for an old file ("use alluvial 0.4"). | v3 suite shrinks to `webAppFiles`/`webAppReload` + `checkColors` + schemes | Low (requested by owner) | **FIX** |
| L5 | Network ids are random on load; split layers do not write `layerId`/`originalId` (v3 Q8), so multilayer colour ops are unavailable after a reload. | Optional: write them inside the namespaced key and restore them. | same | none | Low | LOW |

## 9. Web app UI and React

| ID | What happens | Fix | Rec |
|---|---|---|---|
| U1 | The margin slider label is `2 ** (value - 1)` (`apps/web/src/components/Sidebar/Layout.tsx:59`), half the real top-level margin `2 ** value`. | `2 ** value` | **FIX** |
| U2 | The visible-flow slider computes `flowThreshold = 1 - value/100` (`Layout.tsx:66-70`), e.g. `0.0050000000000000044`. | Round to 1e-6 | LOW |
| U3 | Middle networks get no module labels (`Module.ts:100-106`; `react/Module.tsx:135`). | deliberate | KEEP |
| U4 | With `streamlineFraction = 0` the link bbox has zero width, so the `objectBoundingBox` gradient is not rendered. | Use a solid fill when `x0 == x1`. | LOW |

## 10. Python-only emulations and inefficiencies

| ID | What and where | Exists because | Action after the TS fix | Rec |
|---|---|---|---|---|
| Y1 | `module_order` moves: one full layout per adjacent swap (`engine/store.py:636-709`); 780 moves take 228 s | No TS reorder op | B1 (bit-identical, [P-1]) | **FIX** |
| Y2 | `module_level`: one layout per expand (`engine/store.py:585-615`); 7.7 s on science k=2 | No TS level op | B2 | **FIX** (owner) |
| Y3 | V8 TimSort port (`engine/_utils.py:208-575`, `js_sort`, the NaN branch of `sort_by_number`, `tests/test_engine_jssort.py`) | NaN flows (E9) | Delete it | **FIX** |
| Y4 | Live-walk skip detection and warning (`engine/store.py:744-782`) | E4 | Delete it | **FIX** |
| Y5 | `js_own_keys_order` in `engine/module.py:355-358` and `engine/store.py:317-328` | S5, S3 | Delete those uses. Keep `_jscompat.js_own_keys_order_items` for byte-identical JSON of metadata objects (`_jscompat.py:284`). | **FIX** |
| Y6 | Parity `TypeError` in `_have_metadata` (`engine/store.py:71-78`) | E12 | Delete it | LOW→FIX |
| Y7 | Prefix bug and phantom level (`tree_path.py:5-7, 83-148`; `engine/module.py:210`) | E1, E2 | Fix them | **FIX** |
| Y8 | `check_colors` dummy 0 (`engine/store.py:155-184`) | S7 | Fix it | **FIX** |
| Y9 | `Network.tree` `RuntimeError` and the geometry catch-and-warn (`engine/network.py:278`, `geometry.py:558-565`) | E15 | Delete it | **FIX** |
| Y10 | Old-format reader and writer (`io/saved_diagram.py`) | L4 | Delete it | **FIX** |
| Y11 | fdlibm `log2` port (`engine/_utils.py:87-147`) | Bit-exact `js_div` similarity, not a TS defect | Keep it | KEEP |
| Y12 | JS number/JSON semantics (`_jscompat.py`, `js_json_stringify`) for byte-identical files | Writer parity | Keep it | KEEP |
| Y13 | `"flow": null` read as 0 (`io/json_reader.py:134`) | `JSON.stringify(NaN)` | Reject, as E9 does | **FIX** |
| Y14 | Python 3.10 support: `requires-python = ">=3.10"`, the 3.10 classifier and ruff `target-version = "py310"` (`pyproject.toml:13, 22, 74`); the infomap-extra comment (`:35-36, 42`); CI matrix and lowest-deps job on 3.10 (`.github/workflows/tests.yml:29, 44-52`) | Owner request | `>=3.11`, `py311`, drop the job (`infomap>=2.14` then installs everywhere) | **FIX** |
| Y15 | `move_module` lays out without `calc_flow` (`engine/store.py:558-564`) | H2 | Keep it | KEEP |
| Y16 | Out-of-palette indices cycle the palette and warn (TS draws black) | S9 | Keep it (deliberate divergence) | KEEP |

## 11. Owner decisions surfaced by this inventory

1. **B2 semantics.** Replace the recorded per-expand `module_level` rounds with the one-layout batch? It is 4× faster
   on science and gives the same visible modules ([P-2]), but all `moduleLevel` fixtures change in the last bits and
   in the hidden-module order.
2. **S1, and optionally S2.** Change similarity colours for chains that start after network 0 (S1 changes no existing
   fixture), and stop hidden modules from taking scheme colours (S2 likely changes many `*__colored` fixtures)?
3. **E11.** Aggregate `highlightIndex`/`nodeId` sort keys with max (or mean) instead of sum when modules are
   expanded?
4. **B1.** Should a `setModuleOrder` equal to the current order set `isCustomSorted`? As proposed it does not.
5. **L2 and L3.** Name and shape of the namespaced key (`"alluvial": {format, generator, options, moduleNames,
   moduleOrder, scheme}`), and whether the app restores options on load.
6. **L4.** A hard error for old saved-diagram files in Python ("use 0.4") or a one-release deprecation. P9 removes a
   package export from the TS library (a breaking change since #45).
