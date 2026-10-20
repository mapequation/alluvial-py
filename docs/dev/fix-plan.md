# Fix plan: TS + Python parity fixes, the new save/load format, Python 3.11+

Round 2, phase 2 (review + plan; read-only). Inputs: [`fix-inventory.md`](fix-inventory.md) (row ids E*, S*, H*,
P*, X*, L*, U*, Y*, B1/B2) and [`saveload-plan.md`](saveload-plan.md) (§ numbers below refer to it). Both were checked
against the TS sources at `d0abf3b`. TS paths are relative to `packages/alluvial-diagram/src/` unless they start with
`apps/web/`; Python paths are relative to `src/alluvial/`.

Owner requests this plan serves: (1) fix the discovered problems in both engines with exact parity (regenerated
fixtures), the slow `module_order` first; (2) drop the 2019 saved-diagram format, make the new save/load path work
and carry a version tag; (3) drop Python 3.10; (4) a capabilities tutorial notebook at the end.

---

## 1. Review findings (corrections to the two input docs)

These change what the work packages below do. Each one was checked in the TS source.

1. **B1 primitive vs. the saved `moduleOrder` (conflict).** The B1 `setVisibleOrder` throws unless it gets exactly the
   visible modules, but saveload §4.3 stores and restores **all** of `network.children`, hidden modules included.
   Every layout re-partitions `children` into `[...visible, ...hidden]` and keeps each part's relative order
   (`Diagram.ts:190-210`). With `isCustomSorted` set, the hidden order decides where modules appear when the threshold
   is lowered later. **Resolution:** a single primitive, `Network.setModuleOrder(modules)`, sets
   `children = [...listed, ...unlisted in current order]`. The listed modules must be distinct modules of this network.
   It never throws for missing modules, and the layout re-partitions as usual. When the caller lists exactly the
   visible modules, this is B1 (same children after the next layout, so the [P-1] proof still holds). The restore lists
   all children and skips unknown ids with a warning. Python `apply_module_order` keeps its own validation and
   always passes a complete visible list.
2. **`isCustomSorted` when the order does not change (B1 owner question, resolved).** If the primitive set the flag
   only when the order changed, a file saved with a custom order that happens to equal the natural sort would come back
   unfrozen. **Resolution:** `setModuleOrder` always sets `isCustomSorted = true` for the networks it gets, and lays
   out only if some `children` order changed. Python's `module_order=` API keeps today's behaviour: a target equal to
   the current order issues no op and does not freeze, so `multilevel-tree__default__orderNoop` is unchanged. The restore
   always calls the primitive when a `moduleOrder` is present. (After E7(a), a frozen order and an unfrozen order with
   the same `children` give the same layout.)
3. **`openNetworks` must not use the option setters, and must not end with `updateLayout()`.**
   - Every store setter (`setHeight`, `setFlowThreshold`, …; `DiagramStore.ts:247-285`) runs `updateLayout()`. That is a
     no-op only while no diagram is loaded. When the web app opens a file over an existing diagram, each setter would
     lay out the **old** diagram. Assign the fields directly inside one `action`.
   - The trailing `updateLayout()` in saveload §4.5/§5.1 is wrong. It runs `calcFlow`, which re-sums the flows in the
     new branch order: the "batch with calcFlow" variant of [P-1] differs in the last bits in 248/550 cases. Module
     names need only `toggleUpdate()`.
   - Exact sequence, the same in TS and Python: assign options and the scheme → `setNetworks` (one calcFlow + layout) →
     apply the deferred options (finding 4) → `setModuleOrder` for every network with a `moduleOrder` (at most one layout,
     no calcFlow) → set module names → `toggleUpdate()`. A save without custom order therefore loads bit-identical to a
     plain `setNetworks` of the same files.
4. **New TS defect E19: `showBipartiteNodes = false` is only applied by its setter.** `setShowBipartiteNodes`
   (`DiagramStore.ts:415-421`) calls `network.toggleShowBipartiteNodes`, but `setNetworks` and the constructor option
   do not. A store created with `showBipartiteNodes: false` therefore shows the bipartite nodes while the checkbox says
   hidden, and `moveNetwork` re-shows them. A saved `showBipartiteNodes: false` would hit the same bug.
   **Fix:** `setNetworks` toggles every network to `this.showBipartiteNodes` before its first layout (no extra
   layout). Python ports `toggleShowBipartiteNodes` together with the option (saveload Q5: port, decided).
5. **The S7 remap breaks today's `moveNetwork` unless H3 lands too.** `moveNetwork` writes the **store** indices back
   into `file.nodes` and calls `setNetworks(files)` again with the original `file.colors`. With S7's local→merged
   remap, those indices would be remapped through the file's old palette. Order: S7 (WP6) adds a guard in the same
   package, `file.colors = [...this.highlightColors]` before the rebuild in `moveNetwork`. With that, the remap is the
   identity. H3 (WP10) later replaces the whole write-back. For S7, local indices outside the file's palette (`-1`, or
   past the end, as in `jscolors-a`) stay unchanged, as today.
6. **Where the E9 flow check goes.**
   - A `.net` file has no nodes until `apps/web/src/components/LoadNetworks/Item/Item.tsx:~75` runs Infomap, so
     `parseAcceptedFiles` must skip `format === "net"`.
   - `fetchScienceData` and library callers that pass `NetworkFile`s to `setNetworks` bypass the parser. Put the check
     in a shared `validateNetworkNodes(nodes)` (parsers) that both `parseAcceptedFiles` (friendly `invalid-format`
     error) and `Network.create` (throws) call.
   - The fixture harness and the fuzzer go through `parseAcceptedFiles`, so both sides record the rejection.
7. **Deleting the 2019 code breaks the fixture tools.**
   - `harness.ts:26,30` imports `createFilesFromDiagramObject` and `@alluvial-web/io/save-diagram.js`.
   - `generate.mjs` writes `ts_web_save_diagram_sha256` of that file into `provenance.txt`.
   - The TS deletion, the harness and generator edits, and the fixture regeneration are therefore one package (WP2).
     Doing WP2 **first** also stops every later fix (E1, E4, …) from churning the `saved`/`reload` blocks and the
     Python 2019 code that is about to be deleted.
8. **E3 goes with E1.** Both are in the same branch of the `TreePath` constructor (`utils/TreePath.ts:17-50`). The
   clean rule is "parse with the `;` regex whenever the string contains `;`; otherwise strip one trailing `:` before
   `toArray`". E3 changes no fixture. Do it in WP3 rather than leaving a half-fixed constructor.
9. **E15: do part (a) only.** Our own saves cannot produce a visible `P` together with a visible `P:x`. `expand` and
   `regroup` move every sibling leaf, and the writer stores the leaf levels as they are. Part (b), lifting levels at
   load, changes the layout of hand-made files and adds a parity surface. Make `Network.tree` tolerant (a), delete the
   Python catch-and-warn, and move (b) to LOW.
10. **E4 also fixes name and order loss.** Today a single-leaf module that is recoloured is destroyed and re-created
    (appended, flow 0). That loses its `Module.name` and its place in a custom order. The new format saves names and
    order, so this matters. WP5 adds a scenario for it: name and custom order, then recolour that module.
11. **Fixture regeneration ownership.**
    - `tests/test_fuzz_parity.py:44` and `generate.mjs:41` default to the **master** checkout. Every command below
      sets `ALLUVIAL_TS_ROOT` to the worktree.
    - alluvial-py has no commits, so review each regeneration against a snapshot of `tests/fixtures` (§3).
12. **App tests run against the built package.** `apps/web` imports `@mapequation/alluvial-diagram` through the
    workspace link, which resolves to `dist/` (no Vite alias). Run `npm run build:lib` before the app tests and the
    app typecheck. The fixture harness reads the TS `src/` directly and needs only `node_modules` (`npm ci`).
13. **Format naming conflict, resolved in favour of saveload §4.3.** The inventory sketched `"alluvial": {"format": 1}`.
    Use `{"format": "alluvial-network", "formatVersion": 1, "generator", "diagram": {...}, "network": {...}}`. Infomap's
    own top-level `version` stays untouched.
14. **L4 (owner question, resolved by the request).** "No need to support old json format": reading a 2019 file
    raises a `ValueError` with a pointer to alluvial 0.4. There is no deprecation release.
15. **B2 is a new store op.** `setModuleLevel` is used only by Python and the harness. The web app keeps per-click
    `expand`. Export it from the package and give it a unit test, so that it does not become harness-only logic.

---

## 2. Work packages (strictly in this order)

Nearly every package touches `store/DiagramStore.ts` ↔ `engine/store.py` and regenerates fixtures, so the packages
run **one after another**: there are no parallel tracks. Each package ends green: TS tests, `generate.mjs --check`
against the worktree, and the full Python suite. Run a fuzz smoke test when the engine changes. Do not start a package
on a red tree.

Notation: **TS** = files in the worktree, **Py** = files in alluvial-py, **Fx** = fixtures expected to change (predicted
by [P-3]; any other change is a bug or must be explained), **T** = tests to add or update, **AC** = acceptance criteria.

### WP0: Setup and baseline (no code changes)

- Create the worktree and install (§3). Do not touch `.claude/worktrees/package-boundary`.
- Baseline: `npm test` (after `npm run build:lib`) passes in the worktree. `ALLUVIAL_TS_ROOT=$WT generate.mjs --check`
  is byte-identical, apart from the `ts_repo_head`/worktree path lines in provenance, if any. `.venv/bin/pytest -q` gives
  1806 passed / 8 skipped.
- Snapshot `tests/fixtures` into the scratchpad as `fixtures.WP0`.
- **AC:** all three are green. If the baseline is not clean, stop and report.

### WP1: Drop Python 3.10 (Python only)

- **Py:** `pyproject.toml` (`requires-python = ">=3.11"`, remove the 3.10 classifier, ruff `target-version = "py311"`,
  simplify the infomap extra and its comment at `:35-42`); `.github/workflows/tests.yml` (matrix, and the lowest-deps
  job moves to 3.11); `README.md:18, 348`; `docs/dev/design.md:49, 230`; `tests/test_engine_jssort.py:52` (the file
  goes in WP4 anyway).
- Apply only the edits that `ruff check` flags for py311. No modernisation sweep beyond that.
- **T/AC:** `ruff check src tests` is clean and the suite is green. Smoke-test a wheel install on 3.11 if a 3.11 interpreter
  is available (otherwise note that it was not checked).

### WP2: Remove the 2019 saved-diagram format (P9, L4, Y10)

- **TS:**
  - Delete `parsers/from-diagram.ts` and its export (`parsers/index.ts:6`), `apps/web/src/io/save-diagram.js`, and
    `apps/web/public/data/science-1998-2001-2007.json`.
  - Keep `file-saver` (the WP9 button needs it).
- **Harness (alluvial-py `tools/ts-fixtures`):**
  - `harness.ts`: remove the imports at `:26, :30`, `saveDiagramText`, the `getModuleNames` shims, the
    `saved`/`savedFilename`/`reload` blocks, and the v4 `saveModuleNames` shim.
  - `scenarios-v3.ts`: remove `webapp-science-trim__*`.
  - `generate.mjs`: remove the `@alluvial-web` alias and the `ts_web_save_diagram_sha256` provenance line, and stop
    `--make-data` from writing `webapp_science_trim.json`.
  - Fuzz: the round trip keeps only `webAppFiles`/`webAppReload`, which WP9 replaces.
- **Py:**
  - `io/saved_diagram.py`: delete everything 2019 (`SavedDiagram`, `is_saved_diagram`, `from_saved_diagram`,
    `saved_state`, `STATE_KEYS`, `_LAYOUT_STATE_KEYS`, `SAVE_VERSION`, `diagram_json`, the `;`→NaN warning) and keep
    `webapp_files` until WP9.
  - `io/__init__.py`: remove the exports and the `read()` branches (`:201, :370`). JSON with top-level `networks` and no
    `nodes` raises `ValueError("the 2019 saved-diagram format is no longer supported; use alluvial 0.4 to convert")`.
  - `layout.py`: `save_diagram` loses `format`, `version` and `timestamp`; it writes the web-app files (today's
    `"webapp"`). Remove `restore_state` handling for `SavedDiagram` and `_restore_module_names`. Keep the
    `restore_state` parameter for WP9.
  - Delete `tests/data/webapp_science_trim.json`, `tests/fixtures/v3/webapp-science-trim__*.json` and
    `tests/test_api_v3.py`'s 2019 tests. The `saved`/`reload` assertions go from `test_v3_fixtures.py` and
    `test_fuzz_parity.py`.
- **Fx:** every v3 `*__roundTrip` and v4 `*__roundTrip` (blocks removed), and the 2 `webapp-science-trim` fixtures (deleted).
  Every other fixture stays byte-identical.
- **T:** `read()` of a 2019-shaped dict raises with the new message.
- **AC:** the TS `npm run build` and tests pass, so nothing else imported the deleted files. `--check` is clean. The
  Python suite is green. `grep -rn "createFilesFromDiagramObject\|saveDiagram\|SavedDiagram\|diagram_json"` finds
  nothing in either repo outside CHANGELOG.

### WP3: Tree paths (E1, E2, E3, P3; Y7)

- **TS:**
  - `utils/TreePath.ts`: constructor per finding 8; `isAncestor` returns `c.startsWith(p + ":")`.
  - `parsers/calc-statistics.ts:15-20`: drop an empty last segment.
  - `store/DiagramStore.ts:456-458`: the expand selection uses `TreePath.isAncestor`.
  - `parsers/set-identifiers.ts:39-42`: keep string paths that contain `;` as strings. `LeafNode` already passes
    them to `TreePath` (`LeafNode.ts:51`). Other strings still go through `toArray`.
- **Py:** `tree_path.py:5-7, 83-148`, `io/text.py` (statistics), `io/identifiers.py` (P3), and the `engine/module.py:210`
  docstring. Remove the phantom-level and prefix-quirk docs (STATUS quirk 3, the port notes).
- **Fx ([P-3]):**
  - E1: all 17 `debug5-stree__*`, v3 `debug5-stree__colored__roundTrip`, `fuzz1347__level4`, `fuzz1347__ops`,
    `fuzz2455__ops`.
  - E2: `multilevel-tree__expandRegroup` (and v3 `__roundTrip`), `multilevel-tree__level3Regroup`,
    `prefix-tree__regroupPrefix`, `prefix-tree__regroupPrefixDeep`.
  - E3 and P3: none.
- **T:**
  - `tests/test_tree_path.py`: trailing `:`, `"1:2;3"`, `"1;2:3;"`, and the `1` vs `10` ancestor case.
  - TS unit test for `TreePath` (new `utils/TreePath.test.ts`).
  - A JSON input with a `"1;1;3;"` path loads with no NaN module, in both engines.
- **AC:** the fixture diff equals the Fx list, and `prefix-tree__regroupPrefix*` now regroup only `1:*`. Fuzz smoke:
  v1 and v2, 1000 seeds each. Fuzzed `.stree` path syntax still raises on both sides or on neither.

### WP4: Load validation (E9, P1, P2, E14, E18; Y3, Y13)

- **TS:**
  - `parsers/parse-files.ts`: P1 lower-cases the extension and rejects unknown formats as `invalid-format`. P2 detects
    a zip by the `.zip` extension or by the MIME types `application/zip`, `application/x-zip-compressed` and
    `application/x-zip`, and skips `__MACOSX/`, `._*` and directory entries.
  - E9: a new `validateNetworkNodes` (finding 6) rejects a node whose `flow` is not a finite number. It is called from
    `parseAcceptedFiles` (skipped for `.net`) and from `Network.create`.
  - `alluvial/Network.ts:75-77`: `bipartiteStartId != null` (E14).
  - `alluvial/LeafNode.ts:56-59`: `moduleLevel` is used only if it is an integer ≥ 1, otherwise 1 (E18).
- **Py:**
  - Readers reject non-finite, missing and `null` flows (`io/json_reader.py:134-137`, `io/text.py`), and the stated
    `moduleLevel` rule applies.
  - Delete the V8 TimSort port (`engine/_utils.py:208-575`, `js_sort`, the NaN branch of `sort_by_number` `:577-593`)
    and `tests/test_engine_jssort.py`.
  - Remove the E14 divergence note.
  - Case-insensitive suffix dispatch in `io/__init__.py`.
- **Fx:** `nan-tree__default`, `nan-tree__colored` and `nan-multilevel__expand` become rejection records (or are removed
  and replaced by reader tests). Nothing else changes.
- **Fuzz:** `fuzz/gen.py` emits NaN/Infinity tokens rarely (for example 1 case in 200), so the rejection path stays
  covered without wasting cases.
- **T:**
  - TS `parse-files.test.ts`: `x.TREE`, a `.zip` sent as `x-zip-compressed`, a NaN flow, a `.net` file (accepted).
  - Python reader tests for the same inputs.
- **AC:** no `js_sort` reference remains, the suite is green, and v1/v2 fuzz with 1000 seeds each is clean.

### WP5: Leaf mutation (E4, E5, E6; Y4)

- **TS:**
  - `alluvial/LeafNode.ts:212-223`: `remove()` keeps an emptied module when `module.moduleId === this.moduleId` (E4).
  - `alluvial/LeafNode.ts:128-141`: link only mutually registered leaves (E6). The opposite is taken only when
    `this.network.getLeafNode(this.identifier) === this`, and an unregistered duplicate stays dangling.
    `parseAcceptedFiles` warns once per file with duplicate identifiers (non-fatal `ErrorType`).
  - `alluvial/Module.ts:283-288` and the store loops that assign then `update()`: skip leaves whose `highlightIndex`
    already equals the target (E5).
- **Py:**
  - `engine/leaf_node.py:128-150, 183-196` and `engine/module.py:301-304`.
  - Delete the skip detection and its warning in `apply_highlight` (`engine/store.py:744-782`). `_visible_leaf_walk`
    becomes a plain loop.
  - Remove the hlskip and skip-lemma docs (v2-highlight §2.2).
- **Fx ([P-3]; union):**
  - E4/E5: `debug5-stree__expandHighlight`, `fuzz1347__ops`, `fuzz2455__ops`, `fuzz670__ops`, the 5 `hlskip-tree__*`,
    `science-stree__nameColored`, `planted-ftree__defaultColorChange`, `planted-ftree__highlightThenClear`.
  - E6: `dupname-tree__highlight`, `fuzz1347__level4`, `states-json__name`, `states-tree__{name, nameColored,
    nameColorSelectedNodes}`, v3 `states-ftree__colored__name__roundTrip`.
- **T:**
  - `StreamlineNode.test.ts` invariants after recolouring a single-leaf module.
  - A new v4 scenario for finding 10 (rename and custom order, then recolour that single-leaf module: name and position
    are kept).
  - A duplicate-identifier scenario that checks that no `NULL--` streamline id remains.
- **AC:** the fixture diff equals Fx plus the new scenarios. **Fuzz campaign** (this package is the riskiest): v1
  0-4999, v2 0-9999 and v4 0-4999 are clean.

### WP6: Colour operations (S1, S3, S5, S6, S7, E12; Y5, Y6, Y8)

- **TS (`store/DiagramStore.ts` unless noted):**
  - S1: hoist `highlightIndex` above the network-pair loop (`:609/:621`).
  - S3: `clearColors(false)` first and a `Map` (`:735-793`).
  - S5: `Module.getSimilarModules` uses a `Map` (`Module.ts:333-337`).
  - S6: the last bin is inclusive (`:908-913`).
  - S7: `checkColors` stores real indices and remaps each file's local index to the merged one (`:180-210`), with the
    `moveNetwork` guard from finding 5.
  - E12: `Network.ts:88-94, 108-110` use optional chaining, and `haveMetadata` is true when some leaf has metadata.
- **Py:**
  - `engine/store.py` (`:155-184`, `:242`, `:317-328`, `:507-525`, `_have_metadata` `:71-78`) and `engine/module.py:355-358`.
  - Keep `_jscompat.js_own_keys_order_items` for metadata JSON (Y5).
- **Fx:**
  - S7: `jscolors-abc__default` and v3 `jscolors-abc__default__roundTrip`.
  - S3 clear: `planted-ftree__colorOpsMixed`, plus the fuzz-derived `*__ops` scenarios (not probed; review each diff).
  - S6: `planted-ftree__realMetadata` (not probed).
  - E12: `planted-ftree__categoricalNoMetaFirst`.
  - S1 and S5: none.
- **T:**
  - A new scenario `abc-chain__similarity` (colors-render §6.1: after the fix, `b.2`/`c.1` get `scheme[1]`).
  - TS unit tests for `checkColors` with mixed array/`true` palettes, and for `moveNetwork` after a recolour (palette
    kept).
- **AC:** every fixture diff is in Fx and explained. Fuzz v2 with 2000 seeds is clean.

### WP7: Layout state and fast module order (E7, E10, E15a, H1, B1; Y1, Y9)

- **TS:**
  - `alluvial/Diagram.ts:190-210`: always re-index the visible modules (E7a), and zero the margin of hidden modules
    (E7b).
  - `alluvial/Diagram.ts:309-312`: a tie-safe comparator (E10).
  - `alluvial/Network.ts`:
    - `setModuleOrder(modules)`, per findings 1-2; it returns whether `children` changed.
    - `tree` adds a module to an existing non-leaf node (E15a, `:216-246`).
  - `alluvial/Module.ts:302-311`: the move boundary uses `visibleChildren` (H1).
  - `store/DiagramStore.ts`: `setModuleOrder(orders: [Network, Module[]][])`. It sets the flag on every listed network
    and, if any order changed, runs one `diagram.updateLayout(this)` (no calcFlow) and `toggleUpdate()`.
- **Harness:** the `moduleOrder` macro (`harness.ts:471`) records one
  `{op: "setModuleOrder", order: [[networkIndex, [moduleId, ...]], ...]}` instead of N `moveModule`. The fuzz v4 case
  runner uses it.
- **Py:**
  - `engine/diagram.py:110-116, 165-175` and `engine/network.py` (`set_module_order`, `tree` without the
    `RuntimeError` at `:278`).
  - `engine/module.py`: the move boundary.
  - `engine/store.py:636-709`: `apply_module_order` validates as today, builds the full visible target, skips a no-op,
    and otherwise calls `set_module_order` once. Delete the move loop.
  - `geometry.py:558-565`: drop the catch-and-warn.
- **Fx:**
  - E7a: `multilevel-tree__{move, moveDown, moveExpand, moveSetOption}`, v3 `multilevel-tree__moveDown__roundTrip`,
    and the 10 v4 `*order*` (these also get the new op).
  - H1: `planted-ftree__moveHidden`.
  - E7b and E10: none.
  - B1 itself changes no geometry ([P-1]).
- **T:**
  - Scenario `multilevel-tree__visibleAndSubmodule` (E15a, via per-node `moduleLevel` JSON input).
  - Python timing test: reversing 40 modules on science at `module_level=2` runs well under 5 s (today 228 s). Mark it
    `slow` if it needs the large data.
  - TS unit tests for `Network.setModuleOrder`: an unknown module is skipped, hidden modules are listed, and an
    unchanged order sets the flag without a layout.
- **AC:** the v4 order scenarios keep byte-identical `dump`s (only `inputs.operations` and E7a `index` fields differ).
  Re-run the [P-1] equivalence probe against the new primitive (550 cases). Fuzz v4 0-4999 is clean.

### WP8: Batched module levels and the Expand button (B2, H4; Y2). Owner gate: skip if the owner says no

- **TS:**
  - `alluvial/Module.ts`: a `canExpand` getter that carries the refusal rule of `expand` (`:221-230`). `expand()`
    uses it.
  - `store/DiagramStore.ts`: `setModuleLevel(levels)` as in inventory §2 B2: rounds over the visible, expandable modules
    below the level, `calcFlow` and `updateFlowThreshold` between rounds, one `updateLayout()` at the end. Export it.
  - `apps/web/src/components/Sidebar/Module.tsx:75-76`: the button is disabled unless `module.canExpand`.
- **Harness:** `runModuleLevel` (`harness.ts:448`) records one `{op: "setModuleLevel", levels}`.
- **Py:** `engine/store.py:585-615` (`apply_module_level` calls `set_module_level` once) and `_expandable` (`:924-929`)
  becomes `Module.can_expand`.
- **Fx ([P-3]):** every `moduleLevel` scenario changes in the last bits and in the hidden-module order:
  - `debug5-stree__level3`, `fuzz1347__level4`, `mlayer-split__level2`, `prefix-tree__regroupPrefixDeep`
  - the 10 `multilevel-tree__level*`
  - the 3 v4 `level2*`
  The visible module sets and their order must not change. Check this with a small diff script over the old and new
  dumps.
- **T:** TS unit test for `setModuleLevel` (idempotent, and `canExpand` is respected). App test: the button is disabled for
  a module that `expand` refuses. Python timing: science `module_level=2` < 3 s (today 7.7 s).
- **AC:** the visible sets match the WP7 fixtures in every changed scenario, and fuzz v2 0-4999 is clean.

### WP9: Save/load format v1 (L1, L2, L3, E19, showBipartiteNodes in Python)

Implements saveload §4-§7 with the corrections of findings 1-4 and 13.
- **TS engine:**
  - `parsers/alluvial-format.ts` (new):
    - constants, types, `serializeDiagram(store, {generator, saveId?})`;
    - `readAlluvialMetadata(files)` (§4.4/§4.5 validation, returns warnings), `sortBySavedPosition(files)`, `zipFiles`.
  - `parsers/types.ts`: `alluvial?` and the pass-through keys.
  - `alluvial/Network.ts`: keep the leaves built from the input nodes in input order (`inputLeafNodes`) for the writer
    and for WP10.
  - `store/DiagramStore.ts`: `getOptions()`, `openNetworks(files)` per finding 3, and E19 in `setNetworks`.
  - `parsers/parse-files.ts`: `sortBySavedPosition` on each new batch.
  - Exports in `parsers/index.ts`/`index.ts`.
- **TS app:**
  - `apps/web/src/components/Sidebar/Export.tsx`: a "Download diagram (.zip)" button.
  - `apps/web/src/components/LoadNetworks/LoadNetworks.tsx:103`: `openNetworks` with warnings shown as a toast.
  - `Documentation.tsx`: one paragraph.
  - A generator string from the package version.
- **Harness:** delete the harness-local `webAppFiles` writer and the `loadWebAppFiles` id rewrite. The round-trip
  scenarios record `savedFiles` from `serializeDiagram` (with `generator: "fixture"` and `saveId: "fixture"`) and
  `savedReload` (`parseAcceptedFiles` on the loose files **and** on a JSZip zip, asserted equal, then `openNetworks`).
  Add the saveload §7.2 scenarios.
- **Py:**
  - `io/alluvial_format.py` (new): `serialize_diagram`, the metadata dataclass and its validation. It replaces
    `io/saved_diagram.py`, which is deleted.
  - `io/json_reader.py`: all pass-through keys, raw `modules`/`layers`, the `alluvial` block.
  - `io/__init__.py`: `read(dir | [paths] | zip)` sorts by saved position.
  - `layout.py`:
    - `save_diagram(networks, path, **layout_kwargs)` writes a zip, a directory, or a single `.json` for one network.
    - `layout(restore_state=True)` applies the block per finding 3, with explicit keyword arguments winning silently
      (saveload Q6).
    - Delete `_warn_webapp_losses`.
    - Unmodelled display options are kept on the geometry and written back.
  - `engine/network.py`/`engine/store.py`: `show_bipartite_nodes`, i.e. the toggle and the option applied at build (E19).
- **Fx:** all round-trip fixtures get new `savedFiles`/`savedReload` blocks in place of `webAppFiles`/`webAppReload`,
  plus the new scenarios. Engine `dump`s of existing scenarios are unchanged; check this with a diff that excludes the
  round-trip blocks.
- **T:**
  - saveload §7.3 items 1-6, in a new `tests/test_saveload.py`.
  - TS `alluvial-format.test.ts`: key order, path encoding, block validation, position sort, and a round trip through
    `parseAcceptedFiles` + `openNetworks`.
  - The fuzz round trip switches to Python-save → TS-load (`openNetworks`).
- **AC:**
  - Python's `serialize_diagram` equals `savedFiles` byte for byte in every round-trip fixture.
  - Python's load of `savedFiles` (directory and zip) equals `savedReload` bit for bit.
  - Reload vs original is structurally equal (order, names, palette, levels, options, scheme). The geometry of a
    custom-ordered network is within the saveload §4.5 tolerance.
  - A saved file still loads as plain Infomap JSON (block ignored).
  - Fuzz v4 0-4999 with round trips is clean.

### WP10: `moveNetwork` keeps its state (H3, TS only)

- **TS:** `store/DiagramStore.ts:517-557`:
  - Rebuild from the in-memory serialisation (`serializeDiagram` data, without text) and restore with the `openNetworks`
    sequence. Names, the custom order, the current palette and the bipartite toggle then survive.
  - Write the leaves back per input node through `inputLeafNodes`, not through `getLeafNode(identifier)`.
  - Remove the WP6 guard (now covered).
- **Harness/Py:** none. Python has no `moveNetwork` API (deferred). Add a TS-only fixture scenario only if the harness
  already exposes `moveNetwork`; otherwise the unit tests are enough.
- **T:** `DiagramStore.test.ts`: recolour, name, custom order, `moveNetwork` left and back. Palette, names, order and
  per-leaf colours stay equal, and duplicates keep their own level and colour.
- **AC:** the TS tests pass and `--check` is clean (no fixture change).

### WP11: TS-only hygiene and UI (U1, E13, E16 `console.time`, E8)

- **TS:**
  - `apps/web/src/components/Sidebar/Layout.tsx:59`: `2 ** value` (U1).
  - `alluvial/Network.ts:146-176`: sample variance and standard deviation (E13).
  - Remove the `console.time`/`timeEnd` calls from the library (`Diagram.ts`, `DiagramStore.ts`) and fix the cap comment
    (E16, logging only).
  - Remove `"top"` from `VerticalAlign` (E8).
- **AC:** the TS tests, typecheck and build pass. `--check` is clean, since the provenance source hash changes but no
  fixture does.

### WP12: Docs, version, capabilities notebook

- **Py:**
  - Version `0.5.0` (`__init__.py:19`, `pyproject.toml`).
  - `CHANGELOG.md` (breaking: 2019 format removed, `save_diagram` signature, Python ≥ 3.11, op changes; fixes listed by
    id).
  - `README.md` (save/load section), `docs/dev/STATUS.md` (remove owner decisions 3, 4 and 5 and the quirk list; new
    counts), `docs/dev/design.md`, the port-notes errata, and `tools/ts-fixtures/README.md` (ops, blocks, scenarios).
- **Notebook:** `docs/tutorial.ipynb` becomes a capabilities tour that exercises every public feature:
  - inputs: tree, ftree, stree, clu, JSON, zip, Infomap object;
  - all layout options;
  - `module_level`/`expand`, `module_order` (with timing), `module_names`;
  - all colour modes and schemes, `highlight`, `split_layers`, `show_bipartite_nodes`;
  - `save_diagram` → `read` → `layout` round trip with an equality check;
  - `plot`/`draw`/legend/hierarchy;
  - the error messages (2019 file, NaN flow).
  Install with `pip install -e . --no-deps` into the `py314` conda env and execute it with `jupyter nbconvert --execute`.
  `tests/test_tutorial.py` keeps it under test.
- **TS:** the package `README.md` gets a format section (`formatVersion` 1 contract) and a CHANGELOG entry. The package
  version bump is left to the owner (Q2).
- **AC:** the notebook executes without errors or warnings in py314, `test_tutorial.py` and `test_readme.py` pass, and
  `ruff` is clean.

### WP13: Final verification (§3.3)

---

## 3. How to run

### 3.1 Worktree (once, WP0)

```sh
cd ../web/alluvial
git worktree add .claude/worktrees/py-parity-fixes -b py-parity-fixes master    # master = d0abf3b
cd .claude/worktrees/py-parity-fixes && npm ci
export WT=../web/alluvial/.claude/worktrees/py-parity-fixes
```

Changes stay uncommitted on `py-parity-fixes`. Commit only when the owner asks.

### 3.2 Per package

```sh
# TS (in $WT)
npx tsc -p packages/alluvial-diagram/tsconfig.json                  # typecheck the library (noEmit)
npm run build:lib                                                    # vite build + tsc -p tsconfig.build.json -> dist/
npm test                                                             # vitest: package, then app (app uses dist/)
npm run build:app                                                    # app typecheck (tsc -b) + vite build
# optional UI check: (cd apps/web && npx playwright test)

# Fixtures (in alluvial-py); snapshot first, the repo has no commits
cp -R tests/fixtures "$SCRATCH/fixtures.WPn"
ALLUVIAL_TS_ROOT=$WT node tools/ts-fixtures/generate.mjs             # regenerate
diff -rq "$SCRATCH/fixtures.WPn" tests/fixtures                      # must equal the package's Fx list
ALLUVIAL_TS_ROOT=$WT node tools/ts-fixtures/generate.mjs --check     # determinism

# Python
.venv/bin/pytest -q
.venv/bin/ruff check src tests
ALLUVIAL_TS_ROOT=$WT ALLUVIAL_FUZZ_START=0 ALLUVIAL_FUZZ_SEEDS=1000 .venv/bin/pytest -q tests/test_fuzz_parity.py   # smoke
```

### 3.3 Final verification (WP13)

1. In `$WT`: `npx tsc -p packages/alluvial-diagram/tsconfig.json`, `npm run build`, `npm test`. All green.
2. `ALLUVIAL_TS_ROOT=$WT node tools/ts-fixtures/generate.mjs --check` is byte-identical, and `provenance.txt` names
   the worktree source hash.
3. `.venv/bin/pytest -q` (full suite) and `ruff check`. Compare the counts with the 1806 baseline and explain the
   difference: tests deleted in WP2/WP4, tests added.
4. Differential fuzz with `ALLUVIAL_TS_ROOT=$WT`: v1 seeds 0-6999, v2 0-24999, v4 0-10999 (the 0.4.0 coverage;
   run in the background with `-x`, `-k v2` and `-k v4`) and the round-trip mode. There must be no divergence.
5. Large fixtures: `generate.mjs --large --out $SCRATCH/large`. Replay the science scenarios, and run the
   `module_order`/`module_level` timings on science.
6. Build the wheel and sdist with `uv build`. Run the tests from the sdist on 3.11 (if available) and on py314.
7. Execute the notebook in py314, and run a manual web-app smoke test: `npm run dev` → load the planted files → colour,
   rename, reorder → Download diagram → reload the zip → same picture. Load the same zip from Python.

---

## 4. Not in this round

### 4.1 LOW (real, but rare, cosmetic or upstream; do it only on request)

| ID | Reason |
|---|---|
| S2 hidden modules take similarity colours | Changes many `*__colored` fixtures. Visible colours shift for everyone, so the owner should decide on a colour change of this size. |
| S4 `colorByLayer`/`colorByPhysicalId` do not clear first | It could be intended layering. It only affects fuzz op mixes, and it can be added to WP6 at near-zero cost on request. |
| S8 `setStreamlineThreshold` runs a layout | Wasted work only. Removing it changes last bits in option scenarios for no user gain. |
| E11 summed `highlightIndex`/`nodeId` sort keys | Owner semantics (max vs. mean). Changes the sort of expanded diagrams. |
| E15b moduleLevel consistency lift at load | Finding 9. Our saves cannot produce the state. |
| E16 `Tree` O(n²), `getNeighbor`, `maxModuleLevel`, `tree` memoisation | Performance only. No parity effect, but a broad change to the core. |
| E17 `--` in network ids | Python already rejects them. TS ids are random, and the writer does not write ids. |
| P4 top-level `id`/`format` override | Hand-made files only. Our writer never writes `id`. |
| P5 multilayer merge forces `"id"` | Merge is not ported, so this is a web-app nicety. |
| P7 `calcStatistics` quirks | Affects only the displayed statistics. |
| L5 network ids and `layerId`/`originalId` not saved | A split diagram reloads as plain per-layer networks (colour by layer unavailable). It can be added inside the `alluvial.network` block later without a format bump. |
| Saveload Q4: per-network module-name map | E4 fixes the colour-induced loss. Losing a name on expand or regroup affects only in-session TS, and the writer saves what exists. |
| U2 slider float noise, U4 invisible streamlines at fraction 0 | Cosmetic. |
| X1, X2 `@mapequation/infomap-parser` | Upstream package. Python mirrors it. File an upstream issue. |

### 4.2 KEEP (deliberate)

| ID | Reason |
|---|---|
| H2 / Y15 moves lay out without `calcFlow` | Flows are unchanged. B1 and the restore rely on it. |
| H5 `regroup` takes hidden siblings | Intended hierarchy semantics. |
| P6 layer order from integer keys | Ascending Infomap layer ids are what users expect. |
| P8 stored identifiers win on reload | Needed for exact round trips. |
| S9 / Y16 out-of-palette index | TS draws black; Python cycles and warns. This is a documented divergence that affects only inconsistent hand-made files. |
| U3 no labels on middle networks | Design choice. |
| Y11 fdlibm `log2`, Y12 JS number/JSON semantics | Needed for bit-exact similarities and byte-identical files. They are not emulations of TS defects. |

---

## 5. Owner decisions (the defaults are what this plan does)

1. **B2:** switch `module_level` to the one-layout batch (WP8)? Default: yes. The visible result stays the same, and
   the last bits and hidden order of 17 fixtures change.
2. **TS package semver:** removing `createFilesFromDiagramObject` breaks the published API, and `setModuleOrder`,
   `setModuleLevel`, `serializeDiagram` and `openNetworks` are added. Default: leave the version unbumped in the
   worktree and let the owner choose major vs. minor at release.
3. **S1** changes the colours of similarity chains that start after network 0. Default: fix (WP6).
4. **Insignificant stree paths** are written as `"1;1;63;"` strings. Today's deployed app shows a `NaN` module for
   them until the WP3 fix is deployed. Default: strings.
5. **Web-app save delivery:** zip only. Default: yes; loose files stay a Python option.

### Owner answers (2026-10-10)

1. B2 batched module levels: **yes**, do WP8.
2. TS API: **remove** `createFilesFromDiagramObject` and the 2019 code now. The version bump is decided at release.
3. S1 similarity colour fix: **fix** it in TS and Python.
4. Save delivery: **zip only** in the web app (Python keeps loose files as an option). Stree `;` paths are written as
   strings.
5. Not asked, plan defaults apply: Python `layout()` kwargs override stored options silently; module names are kept per
   network across expand and regroup; `showBipartiteNodes` is ported.
