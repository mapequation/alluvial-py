# Port notes: index

These notes are specs for porting the TS alluvial layout engine (`web/alluvial`, read-only) to the
`alluvial` Python package. TS citations are relative to `packages/alluvial-diagram/src/` unless a note
says otherwise.

## Port base and syncing

The port follows TS `master` at `60fa1bf` (#58; `ts_repo_head` in `tests/fixtures/provenance.txt`). The engine
commits still to port are `git -C <web> log <ts_repo_head>..master -- packages/alluvial-diagram/src` (the web repo's
`CLAUDE.md`, "Python port"). After porting, `ALLUVIAL_TS_ROOT=<checkout> node tools/ts-fixtures/generate.mjs --check`
shows which fixtures differ, and `generate.mjs` without `--check` regenerates them. The colour code of TS #47/#57
(`schemes/index.ts`, the `DiagramStore` tone/offset and `colorModuleHierarchyInAllNetworks`) is ported in
`palette.py` and `engine/store.py` on top of `c3-colors`; these notes predate it, and `CHANGELOG.md` 0.6.0 describes it.

## Notes

- [`layout.md`](layout.md): `Diagram.updateLayout` end to end. It covers widths, the per-network flow threshold, pass 1 (path-tree module sort, groups, margins), the 20 % margin cap, justify, the branch sort, pass 2, label positions, edge cases and worked examples.
- [`model.md`](model.md): the node tree, `TreePath`, `LeafNode.add/remove/update` (swap-remove, detach before create), registries, `calcFlow` summation order, and the `getSimilarModules` data. Includes verified structure dumps.
- [`streamlines.md`](streamlines.md): streamline-node ids and links, build-time linking order, branch sort keys, pass-2 streamline geometry, `getLinks` filter and order, SVG path and JS number formatting, and the renderer rules for streamlines.
- [`parsers.md`](parsers.md): `@mapequation/infomap-parser` behaviour for tree/ftree/stree/clu (and JSON), `setIdentifiers`, `createFile`/`calcStatistics`, and the `infomap.Infomap` → `NetworkFile` reader.
- [`colors-render.md`](colors-render.md): the colour registry, the fill function with `d3.hsl().brighter(0.8)`, the C3 Sinebow palette, the store colour ops (`colorMatchingModulesInAllNetworks`, …) and their mutation quirks, and the React/SVG → matplotlib render spec.
- [`v2-highlight.md`](v2-highlight.md) (v2): the colour/highlight ops v1 did not port (`colorSelectedNodes`, `colorMatchingModules`, `colorModuleIds`, `colorByLayer`/`colorByPhysicalId`, the metadata ops), registry management, the live-iteration skip, insignificant groups, the web app's colour UI, the `highlight=` mapping, and the proposed v2 fixture scenarios.
- [`v2-hierarchy.md`](v2-hierarchy.md) (v2): `Module.expand`/`regroup`/`move`, `moveToIndex`/`isCustomSorted`, the store ops and web-UI triggers, `Network.tree` outlines and their React shadow/outline rendering, the `isAncestor` prefix bug, the deterministic `module_level=k` op sequence (since fix round WP8 one `setModuleLevel` op, top erratum), the geometry fields, the TS-only `moveNetwork` (since fix round WP10 an in-memory save and `openNetworks` restore, §6.5 erratum), and the proposed v2 fixture scenarios.
- [`v2-io.md`](v2-io.md) (v2): multilayer splitting (`expandMultilayerFile`: execution order, layer order and names, deterministic layer ids), the Infomap JSON load path and its rejections, JSON number semantics, `checkColors`, the saved web-app diagram format (recommended for v3), and the proposed v2 IO fixture scenarios.
- [`v3-webapp-json.md`](v3-webapp-json.md) (v3): the saved web-app diagram JSON. Both web-app directions are dead code today: `saveDiagram` (format, fields, `state`, `moduleNames`, history) and the `createFilesFromDiagramObject` loader (what it restores and ignores). It also covers save→load round trips, the Infomap-JSON-with-`colors` route that the current app does load, `checkColors` re-verified, the 64 colour schemes and how `highlightColors` derives from them, what a Python writer must emit, the proposed v3 fixture scenarios and the open decisions. Implemented in `io/saved_diagram.py` (now `io/alluvial_format.py`), `palette.py` (schemes) and `engine/store.py` (`check_colors`); decisions in `design.md` "v3 implementation decisions". **0.5:** the 2019 format is removed, and since fix round WP9 the web-app files are superseded by the saved-diagram format "alluvial network files" formatVersion 1 (`io/alluvial_format.py`, TS `parsers/alluvial-format.ts`; both errata at the top of the note; spec in [`../saveload-plan.md`](../saveload-plan.md) §4). **0.5 (fix round):** the 2019 format is removed (WP2) and saved diagrams are "alluvial network files" formatVersion 1 (WP9, [`../saveload-plan.md`](../saveload-plan.md) §4; `io/alluvial_format.py`); see the errata in the note.
- [`v4-names-order.md`](v4-names-order.md) (v4): `module_names` (the `setModuleName` op, `ModuleInfo`, labels), `module_order` as a deterministic sequence of `moveModule("down")` ops and why it respects the TS move quirks (stale `index`, hidden-module swaps, `isCustomSorted`; since fix round WP7 one `setModuleOrder` op, §3 erratum), the step order in `layout`, the `moduleNames` written by saved diagrams (v4 `getModuleNames` shim; since fix round WP9 the saved-diagram format stores names and order, §4 erratum), and `read()` of a web-app `.zip`. Implemented in `engine/store.py`, `layout.py`, `io/alluvial_format.py` (was `io/saved_diagram.py`) and `io/__init__.py`. **0.5 (fix round WP7, B1):** `module_order` is one `setModuleOrder` op with one layout, bit-identical to the move sequence; see the erratum.
- [`data/c3-sinebow-512.json`](data/c3-sinebow-512.json) and [`data/hsl-brighter-0.8-ref.json`](data/hsl-brighter-0.8-ref.json): the default palette, verbatim, and a 549-pair test oracle for `brighter()`.
- [`tools/ts-fixtures/README.md`](../../../tools/ts-fixtures/README.md): how `tests/fixtures/*.json` (205 scenarios: 130 v1, 75 v2; plus 77 v3 and 15 v4 in subdirectories) are generated from the real TS store, plus their JSON format, the v2 harness ops and macros, and coverage. The v2 scenarios proposed in the three v2 notes are generated (except `science-stree__level2`, which is too large to commit and is generated only with `--large`, and the optional `jsoncolors__*`/`setSelectedScheme` ones).

## Fixture replay, step by step (which note owns which step)

1. Read the files in `inputs.files` order with `inputs.identifier`. Use network id = file stem (`inputs.networkIds`) and name = basename. See parsers §2-§6, §12 pitfall 10.
   v2: assign `inputs.nodeMetadata[i][j]` to the parsed nodes, then split the files in `inputs.split` (v2-io §2); ids and names then come from `inputs.networkIds`/`networkNames` per final network.
2. Build the `Diagram`: model §5.3, §7.3, §9; streamlines §3.
3. Run `setNetworks`: `highlightColors = []`, then `calc_flow` (model §8), then `update_layout(inputs.options)` (layout §4, §5).
4. Run each op in `inputs.operations[1:]`, mutating through `setColor` → `update()` (colors §4, §6; model §5.4; streamlines §3.3). Each op ends with `calc_flow` + `update_layout` on the **same** objects (layout §7, pitfall 11).
5. Build links and paths (streamlines §6, §7) and labels (layout §6, colors §7.5).

Spec check (2026-10-10): steps 2-8 of the layout and `getLinks`, re-derived from each fixture's own flows and final orders, reproduced all 105 fixtures that existed then with exact float equality (layout §11); there are now 132, all matched bit-exactly by the port. The remaining parity risk is in the orders and flows themselves: build, `update()`, colour ops and `calcFlow` summation order. The notes specify these, but no fixture checks them independently of a full port.

## Cross-note decisions fixed by the fixture suite

- **Colours are applied after the build** via the real store ops. So `LeafNode.update/remove`, the dangling merge and the colour ops are **v1**. Build-time `highlightIndex` gives different tie orders and cannot reproduce the coloured fixtures (layout §7, streamlines §0, model Q1).
- **Multi-call persistence is required.** The coloured and expand fixtures run 2-3 layouts on one diagram (layout Q3, streamlines Q2).
- **The engine must accept duplicate identifiers** and run the literal TS algorithm. `states-tree__name*` have them (streamlines Q3, model Q2, parsers §9).
- **The default identifier is `"id"`** (parsers §5). Fixtures pin network ids to file stems.
- **`moduleSize="nodes"` is v1** (`*__moduleSizeNodes`).

## Fixture fields that need more than the layout note

| Field | Where it is specified |
|---|---|
| `networks[i].isHigherOrder` | model §7.3 (first leaf's `stateId`/`layerId`) |
| `networks[i].hierarchy` | layout §9. In v1 it lists the visible modules in `children` order; it differs only in the expand fixtures (v2) |
| `networks[i].file.*` | parsers §6 (`calcStatistics`), §2.7 (`directed`). `numNodes = len(nodes)` |
| `modules[j].enterFlow/exitFlow` | parsers §8.1. Non-zero only for ftree; requires keeping the ftree module records, otherwise skip the field |
| `modules[j].maxModuleLevel`, `leaves[*].moduleLevel/insignificant` | model §5.2, §7.4 |
| `modules[j].label.*` | layout §6, colors §7.5 (aggregated `getLargestLeafNodes`) |
| `modules[j].index`, `margin`, rects of invisible modules | layout §1, §8 (stale values persist; the cap rescales stale margins on every call). Fix round WP7 (E7): `index` follows the drawn order also for a custom order, and hidden modules get margin 0; their rects stay stale. |
| `highlightColors`, `leaves[*].highlightIndex` | colors §1.4, §2.1, §6 |
| `features` (v2 fixtures only; a v1 fixture has none) | `tools/ts-fixtures/README.md` "v2 scenarios" |
| `inputs.macros`, `moduleLevel`/`setModuleLevel`/`expand`/`regroup`/`moveModule`/`resetLayout` ops, `hierarchy` `tree` items as outlines | v2-hierarchy §10-§12 |
| `inputs.nodeMetadata`, `inputs.labelNameHighlight`, the v2 colour ops, the `highlight` macro | v2-highlight §3, §7, §8 |
| `inputs.split`, `inputs.networkSources`, `networks[i].file.layerId/originalId`, JSON inputs | v2-io §2, §3, §8 |

## Known open questions

Status (0.2.0, 2026-10-10): v1 and v2 are implemented. Questions 1-7 were settled provisionally in
[`docs/dev/design.md`](../design.md) (marked **[decision]**; v2 ones under "v2 implementation decisions"), 8 and 11
are resolved, and 9-10 are settled as listed below. What waits for v3 and the decisions the owner still has to
confirm are listed under "Status (0.2.0)" at the end of `design.md`. The text below keeps the questions as they
were asked.

Decisions (API or policy):
1. Should `plot()` default to similarity colouring (colors §9 recommends `colors="similarity"`) or to the gray web-app load state? (colors Q2)
2. Should the TS colouring quirks be mirrored by default (counter reset per pair, single-leaf re-creation, non-idempotence), and should there be a "clean" mode? (colors Q1) (Fix round WP5 fixed the single-leaf re-creation and the non-idempotence in TS and Python, colors-render §4 erratum; WP6 fixed the counter reset per pair, S1, colors-render §6.1 erratum.)
3. Reader policy for duplicate identifiers: warn (recommended) or raise with an opt-out. The engine must accept them either way. (model Q2, streamlines Q3) (Fix round WP5, E6: both engines link only the registered duplicate; both warn.)
4. Where `streamline_threshold` lives (`LayoutOptions` vs renderer), and whether it scales with `height`. (layout Q7, streamlines Q7)
5. Should `verticalAlign="top"` (behaves like bottom in TS) be accepted? (Rejected in Python; fix round WP11 removed it from TS, E8.) Should `flow_threshold >= 1` be accepted? Naming of `sortModulesBy="nodeId"`. Non-integer `marginExponent`. (layout Q1, Q2, Q4, Q9)
6. Labels: middle-network names, font family/weight, baseline emulation, `title-case` port, colour of out-of-range indices (black in TS vs gray plus warning). (layout Q5; colors Q5-Q7, Q9; streamlines Q5)
7. Package layout: the suggested structures conflict. Model §12 puts all nodes in one `model/nodes.py`. Streamlines §11 splits `model/streamline.py`, `leaf.py` and `layout/passes.py`. Layout §11 uses `layout.py`. Parsers §12 puts `tree_path.py` at the top level and `_jsnum.py` in `io/`. `js_num_str` (parsers §5) and `js_number_to_string` (streamlines §7) are the same function. This needs one decision before code is written; a single `jscompat` module for JS number/sum/divide/key-order helpers is recommended.

Parity details that are still unproven:
8. ~~`Math.log2` vs `math.log2` 1-ulp differences in similarity.~~ Resolved: `engine/_utils.js_log2` ports fdlibm `e_log2.c` (FMA as in arm64 node) and matches V8 on 3.3M inputs. (model Q4)
9. (Settled in `design.md` and parsers.md; JSON `layerId: null` is a documented divergence, v2-io §9; `flow`-less nodes are rejected by both since fix round WP4.) Readers: whether to reproduce TS input bugs, `exact=` default for `from_infomap`, its network name and id, use of private infomap API, clu level ≠ 1, multilayer expand/merge in v1, and PyPI vs dev-checkout infomap header lines. (parsers Q1-Q9)
10. (Fix round WP3 fixed the `isAncestor` prefix bug, the stree trailing colon and `;` string paths in TS and Python;
    see the model §4 erratum. WP4 fixed `bipartiteStartId: null` (absent in both, E14) and negative JSON `moduleLevel`
    (1 in both, E18), and both engines reject NaN, infinite, missing and `null` flows at load (E9), so the V8 TimSort
    emulation is gone.) v2 quirks to keep or fix: ~~the `isAncestor` string-prefix bug, the stree trailing-colon
    extra level~~ (fixed, WP3), ~~`bipartiteStartId: null`~~ (fixed, WP4), ~~JSON `moduleLevel > 1`~~ (kept as data,
    model §1 table; only non-integers and values < 1 are ignored since WP4). Still open: prototype-key identifiers.
    (model Q3, Q5, Q7, Q8)
11. ~~Gaps in fixture coverage~~ Resolved by the `planted-ftree-single__*`, `planted-ftree__setOptions`, `*__height37`/`*__heightHuge`, `zeroflow-*` and `fuzz1347__ops` scenarios plus the differential fuzzer (`tests/test_fuzz_parity.py`). Was: no finite zero-height-group sort tie (streamlines Q6), no `Infinity` module threshold, no option change after load, no single network, and no `height` other than 600/200. The worked examples in layout §10, model §10 and streamlines §10 are not in `tests/fixtures`; port them as unit tests.
