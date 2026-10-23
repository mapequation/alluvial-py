# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). 0.6.0 is the first release on PyPI; 0.1.0 to 0.5.0 were development
milestones and were not published.

## [0.7.0] - 2026-10-23

Upgrading from 0.6:

- The default `colors` is `"module_id"`, not `"similarity"`. Pass `colors="similarity"` to keep the 0.6 colors.
- The default color scheme is `"C3 Oklch"` in the `"vivid"` tone, as in the web app (was `"C3 Sinebow"`, `"strong"`).
  Pass `scheme="C3 Sinebow", tone="strong"` to keep the 0.6 colors.
- `alluvial.palette` is private. `alluvial.SCHEMES` is now a tuple of scheme names. For the colors of a scheme, use
  [c3](https://mapequation.github.io/c3) directly.
- `plot()` without `ax` sizes the figure by its content: a small diagram is about 2 inches tall, not 8.

### Added

- Plain dicts as networks: `alluvial.plot([{"Ann": 1, "Bo": 1, "Cy": 2}, {"Ann": 1, "Bo": 2, "Cy": "2:1"}])`. A
  module is an int, a tree path like `"2:1"` or a tuple.
- `alluvial.partition(modules, flows=None, *, name=None)` for one network with optional flows (normalized to sum to 1)
  and a name. Module paths make sub-modules: a node's path is its module's path plus its position in the module,
  as in Infomap's `.tree` files.
- pandas DataFrames in long format: `alluvial.plot(df)` with the columns `network`, `node`, `module` and an optional
  `flow`, or `alluvial.from_dataframe(df, network=..., node=..., module=..., flow=...)` for other column names. pandas
  stays optional.
- Without flows, modules are sized and sorted by node count (`module_size` and `sort_modules_by` default to `"nodes"`
  unless set).
- `color_network` chooses the network for `colors="nodes"`, as the web app's selected network does. The default is the
  first network.
- Every public function and class has a usage example in its docstring, run as a doctest, and the API reference links
  to the capabilities sections that use it.
- Pull requests get a preview of the docs site.
- Port base: TS `master` `effb609` (web app and `@mapequation/alluvial-diagram` 1.17.0, with #64). Since 0.6.0 the
  engine changed in #60 (types only) and #64 (the default colors); the fixtures are regenerated from it.

### Changed

- The default `colors` is `"module_id"`.
- The default color scheme is `"C3 Oklch"` in the `"vivid"` tone, the web app's new default (TS #64). The default
  scheme and tone have one source: the TS store, through `data/color-schemes.json` (`generate.mjs --make-data`
  writes `default` and `defaultTone` from a new `DiagramStore`). `_palette.DEFAULT_SCHEME` and `DEFAULT_TONE` read
  it, and the engine store and `layout()` use them.
- The examples use Infomap's functional API, `infomap.run(...)`, whose `Result` alluvial reads (as it did before).
  `infomap.Infomap` objects that have run still work.
- `alluvial.palette` is private (`alluvial._palette`), and `alluvial.SCHEMES` is a tuple of names.
- The default figure size follows the content: the height grows with the number of modules in the tallest network
  (2 to 6 inches), and the width with the number of networks and the labels.
- `hierarchy="outline"` draws solid dark gray outlines instead of dots. `hierarchy_kw` still restyles them.
- The docs, docstrings and messages use American spelling, like the API.
- The landing page and README lead with what the package does and show a version of the neuroscience alluvial diagram
  from Wikipedia (`examples/hero.py`): synthetic yearly citation networks, partitioned with `infomap.run`, in which
  Neurology, Psychology and part of Molecular & cell biology merge into Neuroscience.

### Fixed

- The README images show on PyPI (absolute URLs) and use the current colors.

## [0.6.0] - 2026-10-21

c3 2 in the web app (TS #47, web app 1.16) and the saved tone and offset (TS #57), ported against TS `master`.
Port base: TS `master` `60fa1bf` (#58); `tests/fixtures/provenance.txt` records it (`ts_repo_head`). #59 (`4a46b90`,
license credit only) does not touch the engine.

Upgrading from 0.5:

- New dependency `c3-colors==2.0.1` (the Python port of `@mapequation/c3`, pinned to the TS lockfile's version).
- The C3 schemes (the default `"C3 Sinebow"` included) are c3 2's (web app 1.16): other colors, hex strings instead
  of `rgb()`. Colorings with the default scheme change color, not geometry. `alluvial.palette.C3_SINEBOW` follows,
  and the package data `c3-sinebow-512.json` is gone (`SCHEMES["C3 Sinebow"]`).

### Added

- **First release on PyPI** (`pip install alluvial`), from <https://github.com/mapequation/alluvial-py>, with a docs
  site at <https://mapequation.github.io/alluvial-py> (Sphinx: the tutorial and capabilities notebooks and the API
  reference). CI tests Linux and macOS on Python 3.11 to 3.14 and the lowest direct dependencies, runs the fixture
  check and the fuzz tests against the TS engine at the provenance commit, and checks TS `master` weekly for drift.
  A GitHub release `vX.Y.Z` publishes to PyPI with trusted publishing.
- **c3 2: tone, offset and coloring by module hierarchy (TS #47, web app 1.16), saved with the diagram (TS #57).**
  Ported against the merged TS `master` (`61b5390`; `packages/alluvial-diagram` identical to PR #57's `9dd2954`);
  re-checked against `60fa1bf` (#58). The C3 schemes are computed by `c3-colors` 2.0.1, the Python port of
  `@mapequation/c3`, pinned to the TS lockfile's version (`tests/test_c3_schemes.py` checks the pin, and the TS
  `pnpm-lock.yaml` when `ALLUVIAL_TS_ROOT` is set).
  - `alluvial.palette`: `TONES`, `DEFAULT_TONE`, `scheme_colors(name, tone, offset)`, `scheme_is_hue_source`,
    `default_scheme_offset`, `hierarchy_options` (TS `schemeColors`, `schemeIsHueSource`, `defaultSchemeOffset`,
    `hierarchyOptions`), the new scheme `"C3 Oklch"` (65 schemes), and the d3 interpolators c3 takes as hue sources
    (`alluvial._d3_interpolators`, exact ports of d3-scale-chromatic 3.1 with their color data in
    `data/d3-interpolators.json`).
  - `DiagramStore(tone=, offset=)`, `selected_tone`/`selected_offset`, `set_selected_tone`, `set_selected_offset`,
    `set_selected_scheme` resetting the offset, and `color_module_hierarchy_in_all_networks` (TS
    `colorModuleHierarchyInAllNetworks`, same mutation order; a list scheme is taken as c3 seeds).
  - `layout(..., tone=, offset=, colors="hierarchy")` (validated: `ValueError` for an unknown tone, `TypeError`/
    `ValueError` for an offset that is no finite number); `save_diagram` writes them.
  - Saved diagrams: the diagram block is `{saveId, position, numNetworks, colorScheme, colorTone, colorOffset,
    options}`, both keys always written (`colorOffset` null for c3's default). Reading warns "ignoring the saved
    color tone (unknown tone)" / "ignoring the saved color offset (invalid value)"; `open_networks` restores as TS
    `openNetworks` (another saved scheme resets the offset; a saved tone/offset applies when present). In `layout`,
    explicit `tone`/`offset` win, and an explicit other `scheme` drops the stored offset.
  - Fixtures: regenerated against that TS tree. Every fixture whose colors come from a C3 scheme changes color
    strings only (no geometry); saved files gain `colorTone`/`colorOffset`. 34 new v3 scenarios (every tone, offsets,
    C3 Oklch, hierarchy coloring, saved tone/offset and their restore rules, `reloadStore`), the TS-derived
    `tests/data/ts_c3_schemes.json` (every C3 scheme x tone x 6 offsets, interpolator samples, `hierarchy()` of
    every scheme), and a c3 fuzz mode (`gen.py --c3`, `-k c3`).

### Changed

- Package metadata: authors mapequation, and the license reads "Copyright (c) 2019-2026 The mapequation authors"
  like the web app's (TS #59). The fixture tools look for the TS checkout at `../web/alluvial` next to this repo
  unless `ALLUVIAL_TS_ROOT` is set. The science `module_level=2` test counts layouts instead of timing them
  (`test_module_level_on_science_is_one_layout`), so slow CI runners pass.
- **TS #58 (`60fa1bf`)**: the TS diagram classes keep their arrays and maps in private fields behind getters, and
  `TreePath` is refactored. Each getter returns the container that used to be the public field, so nothing the port
  mirrors changes: the fixtures regenerated against `60fa1bf` are byte-identical (`ts_repo_head` in
  `provenance.txt` moves from `61b5390` to `60fa1bf`). The fuzz harness's `highlightLeaves` assigned
  `LeafNode.metadata`, which is now a getter, and threw on every highlight macro; it defines `metadata` as an own
  property instead (every TS reader goes through the getter, so this is faithful).
- **Fuzzer:** c3 cases carry an `open` spec (`C3_OPEN_VALUES` in `tools/ts-fixtures/fuzz/gen.py`): the saved
  `colorScheme`/`colorTone`/`colorOffset` are edited (valid, invalid, null, removed, odd literals) before the open, in
  both directions (TS-save -> Python-open and Python-save -> TS-open), optionally opened by a store with its own
  scheme, tone and offset. `setSelectedOffset` ops can be null; offsets include -0.5, 1e-12 and -3e17. TS writes such
  huge floats as integer literals (`-427299959682199200`), so the fuzz test reads TS output with integers beyond
  2**53 as doubles, like `JSON.parse`. v1, v2, v4 and c3 seeds 0-4999 pass, c3 also 5000-9999.
- **Fixtures:** 297 (205 v1/v2, 77 v3, 15 v4). New v3 scenarios: `multilevel-tree__toneRestore{OddColor,HugeOffset}__
  roundTrip`, `nanpath-json__hierarchyLevel2` (string paths with a non-numeric part, which become NaN: TS c3 keys
  modules by the joined path, and the port's one shared NaN keeps its tuple keys equal, so the colors match) and
  `wide-tree__hierarchyLevel2` (see Known issues). `tests/data/ts_c3_schemes.json` gains `hierarchyWide`.

### Known issues

- **c3-colors 2.0.1 vs `@mapequation/c3` 2.0.1:** `hierarchy()` colors a module with many sub-modules (about 40 or
  more) differently: some sibling colors swap (for 119 sub-modules, 8 of 121 colors with C3 Sinebow, 2 with C3
  Oklch). Last-bit differences between Python's `math.hypot`/libm and V8's `Math.hypot`/trig shift the radii, and
  the farthest-point sampling in c3's `placeChildren` breaks near-ties the other way. `colors="hierarchy"`
  (`color_module_hierarchy_in_all_networks`) inherits it. Not patched around in the port: strict xfail tests
  (`tests/test_c3_schemes.py::test_hierarchy_wide_module_matches_ts`, `tests/test_v3_fixtures.py`
  `wide-tree__hierarchyLevel2`) wait for a c3-colors release.

## [0.5.0] - not published

Fix round against the TypeScript worktree `py-parity-fixes` (branched from `d0abf3b`); see
`docs/dev/fix-plan.md`. Per work package (WP), the fixture and behavior changes are listed below.

Upgrading from 0.4 (breaking):

- Python >= 3.11 (WP1).
- The 2019 saved-diagram format is no longer read (`ValueError`; use alluvial 0.4 to convert) and
  `alluvial.SavedDiagram`/`alluvial.io.diagram_json` are gone (WP2).
- `save_diagram(networks, path, *, loose=False, **layout_kwargs)` writes "alluvial network files" formatVersion 1
  (a zip by default, loose files with `loose=True`, one `.json` for one network); `format`, `version` and
  `timestamp` are gone (WP2, WP9). Files saved by 0.4 with `format="webapp"` still read as plain Infomap JSON.
- A node with a non-finite or missing flow raises `ValueError` at load (WP4).
- Engine results change where TS was fixed: stree files lose a phantom level, regrouping `1:2` no longer collapses
  `10:*`, recoloring no longer moves modules, similarity chains that start after the first network get their own
  colors, and `module_level` expands in one batch (WP3-WP8). Diagrams of plain inputs without these cases are
  unchanged.

### Changed

- **WP1, breaking:** Python 3.10 is no longer supported (`requires-python = ">=3.11"`; the 3.10 classifier, the
  ruff `py310` target and the 3.10 CI jobs are gone; the lowest-direct-dependencies CI job runs on 3.11). The numpy
  floor rises from 1.21 to 1.23.2, the first release with Python 3.11 wheels (1.21 does not build on 3.11). The `dev`
  extra installs infomap on every Python and needs `infomap>=2.15.1` (2.15.0 writes another version header and hides
  bipartite nodes differently, so 20 infomap tests failed with the lowest dependencies). The `infomap` extra stays
  `infomap>=2.14`. No engine or output change; fixtures unchanged (WP0 baseline: `generate.mjs --check` against the
  worktree is byte-identical, 1806 passed / 8 skipped).
- **WP1, tests:** the two opt-in large-fixture parametrizations pass their ids as a list instead of a function, so
  collection works with pytest 7.0 (the lowest-dependencies job) when no large fixtures are configured.

### Removed

- **WP2, breaking: the 2019 saved-diagram format** (one JSON with top-level `networks`, the web app's `saveDiagram`
  before 2022; P9, L4, Y10). `alluvial.read` of such a file, dict or zip entry raises
  `ValueError("the 2019 saved-diagram format is no longer supported; use alluvial 0.4 to convert")`. Gone:
  `alluvial.SavedDiagram`, `alluvial.io.SavedDiagram`, `alluvial.io.diagram_json`, and in `io/saved_diagram.py`
  `is_saved_diagram`, `from_saved_diagram`, `saved_state`, `diagram_filename`, `STATE_KEYS`, `SAVE_VERSION` and the
  `;`->NaN warning (the module keeps only `webapp_files` until the new format lands). `layout` no longer accepts a
  `SavedDiagram` or restores its `state`/`moduleNames`; `restore_state` stays as a reserved no-op keyword.
- **WP2, breaking: `save_diagram(networks, path, **layout_kwargs)`** loses `format`, `version` and `timestamp` and
  always writes the web-app files (formerly `format="webapp"`) to a directory or a `.zip`; a `.json` path raises
  `ValueError`. The warning now reads `save_diagram: the web-app files do not store ...`.
- **WP2, fixtures and tools:** the `saveDiagram`, `savedFilename`, `saved` and `reload` blocks are gone from the 16 v3
  and 4 v4 `*__roundTrip` fixtures (their `description` changed accordingly, and the 4 v4 ones lose the
  `saveModuleNames` feature); `v3/webapp-science-trim__load` and `__loadState` and `tests/data/webapp_science_trim.json`
  are deleted (v3 fixtures: 30 -> 28). Every other fixture is byte-identical. `provenance.txt` loses
  `ts_web_save_diagram_sha256`. The harness no longer imports TS's `createFilesFromDiagramObject` or the web app's
  `save-diagram.js` (the `@alluvial-web` alias and the `file-saver` stub are deleted), `--make-data` writes only
  `ts_color_schemes.json`, and the fuzz round trip checks only the web-app files (`saveModuleNames` dropped from
  `fuzz/gen.py`).
- **WP2, tests:** the 2019 tests are deleted (10 in all: 6 in `test_api_v3.py`, 3 in `test_v3_fixtures.py`, 1 each in
  `test_v4_fixtures.py` and `test_api_v4.py`, minus 1 new: `test_read_rejects_the_2019_saved_diagram`); the suite
  goes from 1806 to 1796 passed. README, the tutorial's save cell and the v3/v4 port notes (errata) are updated.
- **WP2, verification:** `generate.mjs --check` clean; 1796 passed / 8 skipped; ruff clean. Differential fuzz seeds
  0-999 in v1/v2/v4 against the worktree: 2991 pass, 9 diverge (v1 249/566/603, v2 and v4 566/603/863), all in
  `label.namesSingleLine` of a module holding a node with a non-numeric flow token (`NaN`, `abc`). The same 9 fail with
  a pre-WP0 copy of the code and harness, so they are not caused by WP2; they are E9 (NaN flows load), which WP4
  fixes by rejecting such flows at load.

- **WP4: the V8 TimSort emulation** (`engine._utils.js_sort`, the `_TimSort` port and the NaN branch of
  `sort_by_number`; Y3) and `tests/test_engine_jssort.py`. It reproduced V8's order for NaN sort keys, which no
  longer occur because NaN flows are rejected at load (below). `sort_by_number` is now a plain stable key sort.

### Fixed

- **WP3: tree paths, in TS and Python together (E1, E2, E3, P3; Y7).** `TreePath` strips the stree trailing `:` before
  splitting, so `"1:1:1:"` has 3 levels, not 4 with a phantom `0` (stree files no longer get an extra expandable level
  that made every leaf its own module); `read` statistics (`num_levels`) agree. `TreePath.is_ancestor` needs a `:` after
  the parent path, so regrouping `1:2` no longer collapses `10:*`, `11:*`, ... (any parent with 10 or more modules;
  TS's expand selection had the same prefix test). A path with `;` anywhere (not only last) is parsed as an
  insignificant path, so `"1:2;3"` no longer gives `[1, NaN]` (it gives `1:2`; the bare trailing number is not
  matched). Infomap-JSON string paths that contain `;` (e.g. `"1;1;3;"`) stay strings and load with their
  insignificant levels instead of a `NaN` module. The "parity quirks kept" notes (STATUS quirk 3, design.md, the
  `tree_path`/`module` docstrings, errata in port notes model §4, parsers §3, v2-hierarchy) are updated.
- **WP3, fixtures:** changed: the 17 `debug5-stree__*`, `v3/debug5-stree__colored__roundTrip`, `fuzz1347__level4`,
  `fuzz1347__ops`, `fuzz2455__ops` (E1: `numLevels` and the leaves' `maxModuleLevel` one lower, fewer expandable levels:
  `debug5-stree__level3` issues 4 expands instead of 8 and stops at level 2, like the `.tree` files), and
  `prefix-tree__regroupPrefix`/`__regroupPrefixDeep` (E2: they now collapse only `1:*`/`1:1:*` and pin the fix; their
  `description` is updated). `provenance.txt` has the new TS source hash. Every other fixture is byte-identical. The
  plan's prediction also named `multilevel-tree__expandRegroup` (+ v3 round trip) and `multilevel-tree__level3Regroup`;
  they are unchanged because no sibling id there shares a digit prefix (at most 4 modules per parent). E3 and P3
  change no fixture (the fuzzer writes no `;` JSON string paths).
- **WP3, tests:** `test_tree_path.py` (trailing `:`, `"1:2;3"`, `"1;2:3;"`, `[1, 2, 3]`, `1` vs `10` ancestors),
  `test_io_v2.py` (a `;` JSON string path stays a string; `"1;1;3;"` loads with modules `1`, `2` and no `NaN`),
  `test_io_text.py` (`num_levels` 3). TS: new `utils/TreePath.test.ts`, two cases in `parsers/parse-files.test.ts`.
  Suite 1796 -> 1802 passed / 8 skipped.
- **WP3, verification:** TS `tsc`, `build:lib`, `npm test` (package 20, app 6), `build:app` pass; `generate.mjs
  --check` clean (node 25.8.1, as before; node 24.21.0 writes identical fixtures apart from the `node:` line). Python
  1802 passed / 8 skipped with `ALLUVIAL_TS_ROOT` at the worktree; ruff clean. Differential fuzz, seeds 0-999 in
  v1/v2/v4: with node 24.21.0 all 3000 pass; with node 25.8.1 the same 9 pre-existing E9 cases as in WP2 diverge
  (`label.namesSingleLine` of modules with a NaN flow; WP4 rejects such flows), everything else passes. So those 9
  depend on the node version, not on WP2/WP3.
- **WP4: load validation, in TS and Python together (E9, P1, P2, E14, E18; Y3, Y13).** A node whose flow is NaN,
  infinite (`Infinity`, `1e400`), garbage (`abc`), missing or JSON `null` is rejected at load: `read` raises
  `ValueError` ("node N has no finite flow (...)", from the new `alluvial.io.identifiers.validate_network_nodes`,
  called by `create_file`), and the engine's `Network.create` raises for `NetworkFile`s built by hand, as TS's
  `Network.create` now throws and `parseAcceptedFiles` reports `invalid-format`. Before, such a flow loaded and gave
  NaN geometry and a V8-specific module order; JSON `"flow": null` was read as 0 (Y13). A JSON `moduleLevel` that is
  not an integer >= 1 (negatives included) now means level 1 in both engines (E18); `bipartiteStartId: null` is
  absent in TS too (E14; Python already read it so, the divergence note is gone). TS now reads upper-case
  extensions and recognizes zips by `.zip` or the `x-zip-compressed`/`x-zip` MIME types, skipping `__MACOSX/`,
  `._*` and directory entries (P1, P2); Python already dispatched case-insensitively and skipped those entries
  (now tested). The empty-diagram warning reads "every node flow is zero or negative, ...".
- **WP4, fixtures:** removed `nan-tree__default`, `nan-tree__colored` and `nan-multilevel__expand` (and their
  scenarios; `tests/data/nan_t1.tree` is deleted, `nan_t0.tree` stays as rejection input). `provenance.txt` has the
  new TS source hash and `fixtures: 201`. Every other fixture is byte-identical. The fuzzer (`fuzz/gen.py`) writes
  the non-finite flow tokens (`NaN`, `Infinity`, `1e400`, `abc`) only in the 1 % of cases flagged by
  `random.Random(f"nonfinite-{seed}")` (then at a higher per-row rate), about 1 case in 200; unflagged cases are
  generated exactly as before, with the finite oddities (`-0.1`, `-0`) kept.
- **WP4, tests:** new `tests/test_io_validation.py` (39: non-finite text flows in tree/ftree/stree/clu, JSON
  `null`/string/bool/missing flows, finite oddities, `nan_t0.tree`, the engine check, upper-case suffixes, `.net`,
  unknown suffixes, zip metadata entries and a zip with a NaN flow, `moduleLevel`, `bipartiteStartId: null`);
  `test_geometry.py`'s NaN-height test now asserts the rejection; scenario counts in `test_conftest_helpers.py`
  (201: 129 v1, 72 v2). Suite 1802 -> 1822 passed / 8 skipped (+39 new, -14 parametrizations of the removed
  fixtures, -5 jssort tests). TS: `parsers/parse-files.test.ts` (P1, P2, E9, `.net`) and new
  `alluvial/Network.test.ts` (E9 in `Network.create`, E14, E18).
- **WP4, verification:** TS `tsc`, `build:lib`, `npm test` (package 54, app 6), `build:app` pass; fixtures
  regenerated with node 25.8.1 and `generate.mjs --check` is byte-identical. Python 1822 passed / 8 skipped with
  `ALLUVIAL_TS_ROOT` at the worktree; ruff check and format clean. Differential fuzz: seeds 0-4999 in v1, v2 and v4
  (15000 cases, node 24.21.0) and seeds 0-999 in all three modes with node 25.8.1 all pass, so the 9 node-25 E9
  divergences noted under WP2/WP3 are gone (those cases are now rejected by both engines).
- **WP5: leaf mutation, in TS and Python together (E4, E5, E6; Y4).** Recoloring keeps every module in place: an
  emptied module is removed only when its leaf moves to another module (`LeafNode._remove`), so a single-leaf module
  keeps its object, name, position and flow (before, it was re-created at the end with flow 0). With it go five color
  quirks: the visible-leaf walks (`colors="layer"`/`"physical_id"`, metadata coloring, `highlight=`) no longer skip a
  module, so no labeled node stays gray and the "stay gray" warning is gone; `colorMatchingModules` chains run through
  single-leaf modules; `colorNodesInModule` propagates from one; `colorMatchingModulesInAllNetworks` is idempotent.
  Color ops skip leaves whose highlight index does not change (E5). Duplicate identifiers link only the registered
  (last) leaf across networks, the others stay dangling (E6): no stolen leaves, no `NULL--` streamline ids, and the
  flow of every duplicate is drawn. The web app warns once per file with duplicate identifiers (non-fatal); Python
  keeps its reader warning. `DiagramStore.apply_highlight` no longer detects the walk skip, and `_visible_leaf_walk`
  is a plain loop (Y4).
- **WP5, fixtures:** changed (orders, last bits, the fixed colors and links): `debug5-stree__expandHighlight`,
  `dupname-tree__highlight`, `fuzz1347__ops`, `fuzz2455__ops`, `fuzz670__ops`, `hlskip-tree__{categoricalSkip,
  colorByPhysicalId, colorMatchingModulesSingle, colorMatchingModulesThrough, colorNodesInModuleSingle}` (new
  descriptions), `planted-ftree__{defaultColorChange, highlightThenClear}`, `science-stree__nameColored`,
  `states-json__name`, `states-tree__{name, nameColored, nameColorSelectedNodes}` and
  `v3/states-ftree__colored__name__roundTrip`, as the plan predicted. Also changed, not predicted:
  `planted-ftree__{categorical, categoricalNoMetaFirst, realIntervals}` (last bits and label tie order only; their
  default-color category or interval is now a no-op for leaves already at -1, the E5 guard in the store loops, which
  the plan's probe applied only to `Module.setColor`). Predicted but unchanged: `fuzz1347__level4` (its duplicates
  `9` and `2` take the benign path; the probe ran before WP3, whose phantom-level fix changed what `moduleLevel 4`
  expands. Confirmed in review: a regeneration with only the E6 guard reverted leaves `fuzz1347__level4`
  byte-identical and changes exactly the E6 files listed above).
  New: `dupname-tree__recolor` (every duplicate runs `update()`) and `v4/hlskip-tree__default__namesOrderRecolor`
  (a single-leaf module moved, named, then recolored keeps its name and place). `provenance.txt`: new source hash,
  `fixtures: 202`, `fixtures_v4: 15`, node 24.21.0. The harness ignores the new non-fatal parse warnings.
- **WP5, tests:** the five tests that pinned the old behavior now pin the fix (`test_engine_model.py`: duplicate
  links, single-network coloring of every module, idempotent matching; `test_engine_v2.py` and `test_layout_v2.py`:
  no gray node and no warning on `hlskip`). New: `test_recolor_single_leaf_module_keeps_name_order_and_flow` and
  `test_no_fixture_has_a_null_streamline_id`; the new v4 scenario is replayed but not rebuilt from `layout()`
  arguments (`NOT_LAYOUT_ORDER`, color after order and names). The obsolete "stay gray" warning filters are gone.
  Suite 1822 -> 1830 passed, 8 -> 9 skipped. TS: `StreamlineNode.test.ts` (single-leaf recolor, no-op recolor,
  duplicate identifiers) and `parse-files.test.ts` (the duplicate warning).
- **WP5, verification:** TS `tsc`, `build:lib`, `npm test` (package 58, app 6), `build:app` pass; `generate.mjs --check`
  byte-identical with node 24.21.0 and 25.8.1. Python 1830 passed / 9 skipped with `ALLUVIAL_TS_ROOT` at the
  worktree; ruff check and format clean. Differential fuzz campaign (node 24.21.0): v1 seeds 0-4999, v2 0-9999 and
  v4 0-4999 all pass (20000 cases).
- **WP6: color operations, in TS and Python together (S1, S3, S5, S6, S7, E12; Y5, Y6, Y8).**
  - `colors="similarity"` (`colorMatchingModulesInAllNetworks`, S1): one color counter for all network pairs. A
    similarity chain that starts in network 1 or later no longer reuses `scheme[0], scheme[1], …` and so no longer
    takes the color of an unrelated chain (owner decision 3). Chains that start in network 0 keep their colors.
  - `colors="module_id"` (`colorModuleIdsInAllNetworks`, S3) clears first, like the other color ops: the registry
    restarts and hidden modules lose stale colors. Expanded-multilayer groups are taken in insertion order (no JS
    object key order; Y5).
  - Module similarity (S5): the node distribution keeps insertion order for every identifier (TS `Map`, no JS object
    key order; Y5), and name-mode identifiers such as `constructor` or `__proto__` match in TS too.
    `_jscompat.js_own_keys_order_items` stays for byte-identical metadata JSON.
  - Real-valued metadata bins (S6): the last bin includes its upper edge, so the leaves with the maximum value get
    the last color (before: no color).
  - Input palettes (`check_colors`, S7; Y8): the files' palettes are merged (first occurrence wins). A `colors` list is
    local to its file: each node's `highlight_index` into it is remapped to the merged index (an index outside the
    file's list, `-1` or past the end, is kept), and the file's `colors` becomes the merged palette, so a second
    `set_networks` on the same files is the identity. `colors: true` nodes get the real index of their color (before:
    the dummy index 0 when the color came from an earlier list). `layout()` copies every file with input colors
    before `check_colors`, so the caller's files are not changed. TS `moveNetwork` gives every file the store palette
    before it rebuilds (fix-plan finding 5).
  - `have_metadata` (E12; Y6) is true when some leaf has metadata (before: only the first leaf in tree order was
    checked), so the metadata color ops no longer skip such a network. A network without leaves no longer raises
    `TypeError`; `is_multilayer`/`is_higher_order` read the first leaf safely in TS too.
- **WP6, fixtures:** changed: `v3/jscolors-abc__default` and `v3/jscolors-abc__default__roundTrip` (S7: b's `#0f0`
  nodes get index 1, not the dummy 0); `planted-ftree__categoricalNoMetaFirst`, and also, not predicted,
  `planted-ftree__{arrayLength, arrayMetadata}` (E12: their first leaf has `metadata: null`, so a whole network was
  skipped; now colored); `planted-ftree__realMetadata` (S6: the maximum-valued leaves get the last bin's color);
  `fuzz2455__ops` and, not predicted, `v3/multilevel-tree__schemeSwitch` (S3: `colorModuleIdsInAllNetworks` after
  another color op now starts from an empty registry; in fuzz2455 a hidden module loses a stale color, in
  schemeSwitch the registry has the 4 Set1 colors instead of 3 Sinebow + 4 Set1). Each attribution was checked by
  regenerating with only that fix reverted in the TS worktree (the fixture then equals the WP5 one). Predicted but
  unchanged: `planted-ftree__colorOpsMixed` (its `colorModuleIdsInAllNetworks` follows `colorNodesInModulesInAllNetworks`,
  which registered the same scheme colors from index 0, and every colored module is visible, so clearing first gives
  the same indices). S1 and S5 change no committed fixture, as predicted. New: `abc-chain__similarity` (v1; hand-written
  `abcchain_t{0,1,2}.tree`, `make_datasets.py` (j), `datasets.json` `v2_datasets.abcchain`): `b.2` and `c.1` get
  `scheme[1]`; with the old counter all five modules got `scheme[0]` (checked the same way). `provenance.txt`: new
  source hash, `fixtures: 203`.
- **WP6, tests:** `test_color_matching_counter_reset_per_pair` becomes `test_color_matching_counter_shared_by_all_pairs`;
  `test_metadata_ops_throw_on_a_network_without_leaves` becomes `test_metadata_ops_skip_a_network_without_leaves`. New:
  `check_colors` remap and idempotence, `layout()` leaves list-palette inputs unchanged, `color_module_ids_in_all_networks`
  clears first, similarity with `constructor`/`__proto__` identifiers (`test_engine_model.py`), the inclusive last bin
  and `have_metadata` with a first leaf without metadata (`test_engine_v2.py`); scenario count 202 -> 203. TS:
  `DiagramStore.test.ts` (`checkColors` with mixed palettes and on the same files twice; `moveNetwork` after a recolor).
- **WP6, verification:** TS `tsc`, `build:lib`, `npm test` (package 61, app 6), `build:app` pass; `generate.mjs --check`
  byte-identical (node 24.21.0). Python 1842 passed / 9 skipped with `ALLUVIAL_TS_ROOT` at the worktree (1830 + 7 new
  tests + the new scenario's parametrizations); ruff check and format clean. Differential fuzz: v2 seeds 0-1999, v1 and
  v4 seeds 0-999 all pass.
- **WP7: layout state and fast module order, in TS and Python together (E7, E10, E15a, H1, B1; Y1, Y9).**
  - `module_order=` (B1; Y1) issues one TS `setModuleOrder` op (one layout without `calc_flow`) instead of one
    `moveModule("down")` per adjacent swap (one layout each). The result is bit-identical. Probe [P-1], re-run
    against the new primitive, gave 550/550 cases with identical full state, hidden modules included. On
    `science*_2y.stree` at `module_level=2`, reversing 40 of the 429 visible modules of network 0 takes ~0.1 s
    instead of 85 s (780 layouts, measured in WP7 on the same machine; the inventory had 228 s; 766x, identical full state). `apply_module_order` validates as before and skips networks whose target equals
    the current visible order (no op, not frozen). It passes the full visible target of the other networks to the
    new `DiagramStore.set_module_order` and returns
    `[{"op": "setModuleOrder", "order": [[networkIndex, [moduleId, ...]], ...]}]` (or `[]`). `Network.set_module_order`
    puts the listed modules first and the unlisted ones after them in their current order. It skips foreign modules
    and repeats, always freezes the order, and the caller lays out.
  - Pass 1 (E7): the visible modules get `index` in drawn order also for a custom order (no stale `index`), and hidden
    modules get margin 0 (a stale margin is no longer rescaled by the cap on every layout). Nothing drawn changes.
    E10 (tie-safe TS branch comparator) changes no output; Python already sorted by key.
  - `Module.move` (H1): moving the top visible module up is refused with the usual warning. It used to swap with a
    hidden module and freeze the order without any visible change.
  - `Network.tree` (E15a; Y9): a visible module shown together with one of its visible sub-modules (input
    `moduleLevel`s) no longer raises. The parent joins the non-leaf node of its path (or its leaf node becomes a
    non-leaf node when it comes first), so one outline encloses both. `build_geometry` no longer catches the
    `RuntimeError` and no longer warns "no hierarchy outlines".
- **WP7, fixtures:** the E7a fixtures changed, as predicted: `multilevel-tree__{move, moveDown, moveExpand,
  moveSetOption}` and `v3/multilevel-tree__moveDown__roundTrip`, only in `modules[].index` and `pass1.index`. The 10
  predicted v4 `*order*` fixtures changed, plus `v4/hlskip-tree__default__namesOrderRecolor`, which WP5 added after the
  prediction. In these 11, `inputs.operations` has one `setModuleOrder` op instead of the `moveModule` ops, and
  `macros[].numOperations`, `diagram.updateLayoutCalls` and the E7a `index` fields differ. The rest of every dump is
  byte-identical (AC). `v4/multilevel-tree__default__orderNoop` is unchanged. In `planted-ftree__moveHidden` (H1), the
  op carries `result: false`; `isCustomSorted` is false, the warning is recorded and there is one layout fewer.
  New: `multilevel-tree__visibleAndSubmodule` (plan) and
  `multilevel-tree__visibleAndSubmoduleOrder` (also covers the "parent first" order). Both are v2 (`json`), with
  network 0 from the new derived `multilevel_mixed_t0.json` (`make_datasets.py` (k), `datasets.json`
  `v2_datasets.multilevel_mixed`). E7b and E10 change no fixture. `provenance.txt`: new source hash, `fixtures: 205`.
  The harness can now expect a refusal in a scenario op (`result: false`) and replays `setModuleOrder`.
- **WP7, tests:** `test_mixed_parent_and_submodule_warns_without_outlines` becomes
  `test_mixed_parent_and_submodule_has_an_enclosing_outline` (both orders). New in `test_api_v4.py`: one
  `setModuleOrder` op and one layout for two networks, with no-op networks skipped; `set_module_order` with hidden,
  foreign and repeated modules; and the science timing test (`module_level=2`, reverse 40 of 429 modules, under 5 s;
  not marked slow, the data is committed, ~4 s in all). The macro replay test checks that `apply_module_order` issues
  the recorded op. The scenario split is now 205 (75 v2).
- **WP7, verification:** TS `tsc`, `build:lib`, `npm test` (package 67, app 6), `build:app` pass; `generate.mjs
  --check` byte-identical. Python 1857 passed / 9 skipped with `ALLUVIAL_TS_ROOT` at the worktree (1842 + 3 new
  `test_api_v4.py` tests + the two new scenarios' parametrizations); ruff check and format clean. [P-1] re-run
  (550 cases, legacy move loop vs `set_module_order`): identical full state in all. Differential fuzz: v4 seeds
  0-4999, v1 and v2 seeds 0-999 all pass.
- **WP8: batched module levels and the Expand rule, in TS and Python together (B2, H4; Y2).**
  - `module_level=` (B2; Y2) is one TS `setModuleLevel(levels)` op instead of one `expand` per module (each with
    `calc_flow` and a full layout). Per network it runs rounds of "expand every visible module below the level that
    can expand, in `children` order", each followed by `calc_flow` and the network's `update_flow_threshold` but no
    layout, until a round finds none; then one `update_layout` if something was expanded. The new
    `DiagramStore.set_module_level` returns whether something was expanded. `apply_module_level` validates as
    before, calls it once and returns `[{"op": "setModuleLevel", "levels": [k per network]}]` (or `[]`), and
    `DiagramStore.apply` replays `setModuleLevel`. The visible modules and their order are unchanged; the order of
    hidden modules and the last bits of some coordinates and flows differ from the per-expand sequence (owner
    decision, fix-plan §5). On `science*_2y.stree`, `module_level=2` takes 0.67 s instead of 2.5 s (2 layouts
    instead of 25; 3.7x; the inventory had 7.7 s before WP3-WP7), `module_level=3` 0.87 s instead of 6.0 s (6.8x),
    with identical visible modules. TS on the same data: 157 ms instead of 523 ms (k=2), 248 ms instead of 940 ms
    (k=3).
  - `Module.can_expand` (H4) is the refusal rule of `expand` as a property (leaf nodes exist and all lie deeper than
    the next level). `expand` and `set_module_level` use it; the module-level helper `_expandable` is gone. The web
    app's Expand button uses the TS `canExpand` (it used `isLeafModule`, which looks only at the deepest leaf, so a
    module with a shallow leaf had an enabled button that `expand` refused).
- **WP8, fixtures:** exactly the 17 predicted `moduleLevel` fixtures changed: `debug5-stree__level3`,
  `fuzz1347__level4`, `mlayer-split__level2`, `prefix-tree__regroupPrefixDeep`, the 10
  `multilevel-tree__{level2, level2Colored, coloredLevel2, level2Highlight, level2SortNodeId, level3, level3Geometry,
  level3Justify40, level3Regroup, levelMixed}` and v4 `multilevel-tree__{level2__order, level2Highlight__order,
  level2__names__roundTrip}`. In all of them `inputs.operations` has one `setModuleLevel` op instead of the
  `expand` ops, and `macros` (`numOperations`, and the `atOperation` of later macros) and
  `diagram.updateLayoutCalls` differ. A diff script over the WP7 and WP8 dumps confirms the AC: the visible module
  ids and their order, and the module sets, are identical in all 17. Only ties can reorder (review): the label names
  of equal-flow nodes (network 2, module 3:2 lists m101, m107, m105 instead of m101, m105, m107 in
  `multilevel-tree__level3Geometry` and v4 `multilevel-tree__{level2, level2Highlight}__order`), and in
  `multilevel-tree__level3Justify40` the streamline nodes with equal sort key (-Infinity) inside modules 1:3
  (network 0) and 2:2 (network 1), whose dangling and linked streamlines swap y (13-46 px; the drawn links differ
  only in the last bits). `multilevel-tree__level3Justify40` also has a different hidden-module order;
  13 scenarios differ in the last bits (relative difference at most 1.6e-15; `hierarchy` rectangles of network 1 in
  7 of them); `debug5-stree__level3`, `fuzz1347__level4`, `prefix-tree__regroupPrefixDeep` and
  `multilevel-tree__level2Colored` differ only in the recorded ops and layout counts. `provenance.txt`: new source
  hash. The harness `moduleLevel` macro (also used by the v2/v4 fuzzers) records the same op, and `applyOp` replays
  `setModuleLevel`.
- **WP8, tests:** `test_module_level_is_idempotent_and_only_expands` checks the single op and the single layout. New:
  `test_can_expand_carries_the_expand_refusal_rule` and `test_set_module_level_expands_in_rounds_with_one_layout`
  (a mixed-depth tree written to `tmp_path`), and `test_module_level_on_science_is_fast` (science `module_level=2`
  through `layout`'s store build in under 3 s, ~0.9 s here; visible counts 429/386/352/471; renamed in 0.6.0).
- **WP8, verification:** TS `tsc --noEmit` (package), `build:lib`, `npm test` (package 71, app 8; +4 and +2), `build:app`
  pass; `generate.mjs --check` byte-identical. Python 1860 passed / 9 skipped with `ALLUVIAL_TS_ROOT` at the worktree
  (1857 + 3 new tests); ruff check and format clean. Differential fuzz: v2 seeds 0-4999 (AC), v4 and v1 seeds 0-999
  all pass. Visible-set diff script over the WP7 and WP8 dumps: identical visible ids and order in all 17.
- **WP10, TS only (H3):** `DiagramStore.moveNetwork` keeps its state. It serializes the diagram in memory as a save
  (`serializeDiagramData`, the data step of `serializeDiagram`, now exported), writes each node's color and module
  level back per input node (`Network.inputLeafNodes`, so duplicate identifiers keep their own instead of the
  registered leaf's), reorders the files and restores them with `openNetworks`. The palette, per-leaf colors, network
  and module names, custom module orders, options, scheme and bipartite toggle survive a move (before, names and the
  custom order were lost and duplicates were miswritten). Python has no `moveNetwork`; no Python or fixture change.
- **WP11, TS only (U1, E13, E16, E8):** the web app's margin slider label shows the real top-level margin `2 ** value`
  (U1); `Network.metadata` real entries have the sample variance, a new `standardDeviation` and `pdfBounds` at
  mean ± 1, 2 standard deviations (E13; not ported to Python); the library no longer calls `console.time`/`timeEnd`
  and the margin-cap comment says 20 % (E16, logging only); `VerticalAlign` drops the unimplemented `"top"` (E8;
  Python already rejected it, `layout()` docstring updated). Port-note errata: v2-hierarchy §6.5, colors-render §5,
  layout (option table, slider label, cap comment, Q1), README; `design.md` and `tools/ts-fixtures/README.md` notes.
- **WP10/WP11, fixtures:** none change; `provenance.txt` gets the new TS source hash. The harness's scenario option
  type drops `verticalAlign: "top"` (unused).
- **WP10/WP11, verification:** TS `tsc --noEmit` (package), `build:lib`, `npm test` (package 89 = 84 + 5
  new: 2 `moveNetwork`, 1 no-`console.time`, 2 metadata statistics; app 8) and `build:app` pass; `generate.mjs`
  regenerated (only `provenance.txt` changes) and `--check` byte-identical. Python 2039 passed / 19 skipped with
  `ALLUVIAL_TS_ROOT` at the worktree (1946 + the default 93 fuzz cases, unchanged); ruff check and format clean.
  Differential fuzz with round trips and the direct Python-save -> TS-open: v1, v2, v4 seeds 0-599 (1803 passed).
- **Review fixes (after WP0-WP11), TS and Python together where both have the code:**
  - `DiagramStore.open_networks` (TS `openNetworks`) consumes the saved blocks: it sets `file.alluvial = None`
    (TS: deletes it) on every file once read. Before, opening the same files again (the web app's Create diagram in
    the Load networks dialog passes `store.networks`) re-applied the save and undid later option, scheme, order and
    name changes, and adding a plain network to an opened save warned about different saves. Test:
    `test_open_networks_consumes_the_saved_blocks`.
  - TS only: `moveNetwork` reorders `store.networks` in place (the Load networks dialog keeps that array; WP10 had
    replaced it), and `setModuleLevel` moves a selection that it expanded to the largest visible sub-module, like
    `expand` (before, the selection stayed on a detached module). The Load networks dialog warns about shared
    identifiers when the identifier is switched there, not only on drop (`duplicateIdentifiers` and
    `duplicateIdentifiersMessage` are exported from the TS package).
  - `validate_network_nodes` accepts NumPy scalar flows (`numbers.Real`, as `layout` does; bools stay rejected) and
    rejects an `int` too large for a float instead of raising `OverflowError`. `_jscompat.js_is_integer` (TS
    `Number.isInteger`) is true for an `int` of any size, so `check_colors` keeps a huge `highlight_index` instead of
    raising `OverflowError`; the store's private copy `_is_js_integer` is gone.
  - Dev extra: `ipykernel>=6.3.1` (was `>=6`). 6.0.2-6.3.0 import `ipython_genutils` without requiring it, so the
    3.11 lowest-deps job skipped the tutorial notebook; with 6.3.1 it runs (checked on 3.11.7, lowest-direct).
  - Messages and docs: `read_file(directory)` points to `alluvial.read(directory)`; the `build_geometry` docstring
    describes the E15a outline; rewrapped `read()` Raises and the design.md packaging bullet; the port-notes README
    marks the settled v2 quirks; `tools/ts-fixtures/README.md` scenario counts re-derived (205: 130 v1, 75 v2); the
    harness drops the stale `restoreState` comment and the unused `makeData` `tsRoot` parameter; the fuzz generator
    comment no longer claims unflagged cases draw exactly as before.
  - Fixtures: none change (the harness opens fresh parsed files and never reads a block after `openNetworks`);
    `provenance.txt` gets the new TS source hash.

### Added

- **WP9: the saved-diagram format "alluvial network files", formatVersion 1, in TS and Python together (L1, L2, L3,
  E19; saveload-plan.md §4-§7).** A saved diagram is one Infomap-JSON file per network (`NN_<network name>.json`), in
  a zip or loose. Each file carries Infomap's own top-level keys unchanged (`version`, `args`, `startedAt`,
  `completedIn`, `codelength`, `relativeCodelengthSavings`, `directed`, `flowModel`, `higherOrder`, `stateLevel`,
  `bipartiteStartId`, then `modules` and `layers`), the network `name`, the palette `colors` (omitted when empty),
  the nodes in input order (`path`, `flow`, `name`, `id`, `stateId`, `layerId`, `metadata`, `identifier`,
  `highlightIndex`, `moduleLevel`), and an `alluvial` block: `format` `"alluvial-network"`, `formatVersion` 1,
  `generator`, `diagram` (`saveId`, `position`, `numNetworks`, `colorScheme`, all 26 saved store `options` in the TS
  order) and `network` (`moduleNames`, and `moduleOrder` with every module, hidden ones included, when the order is
  custom). A path is Infomap's integer array, or the stree string (`"1;1;63;"`) when a level is insignificant
  (owner decision: strings). Other Infomap-JSON readers ignore the block, so a saved file is still plain Infomap JSON.
  - `alluvial.io.serialize_diagram(store, generator=..., save_id=None)` is a line-for-line port of the TS
    `serializeDiagram` (same names, key order, path encoding and `JSON.stringify(value, null, 2)` text).
    `alluvial.io.read_alluvial_metadata(files)` and `sort_by_saved_position(files)` port the TS block checks: the
    network part applies per file; the diagram part (options and scheme) only when every file has a valid v1 block
    of one save and the positions are a permutation of `0..n-1` for `n` files; a newer `formatVersion`, an invalid
    block, files from different saves, an incomplete save, an invalid option value or an unknown scheme give a
    warning (same text as TS) and the rest still loads.
  - `DiagramStore.open_networks(files)` ports the TS `openNetworks` (fix-plan finding 3): assign the saved options and
    scheme (no layout), `set_networks` (one `calc_flow` + layout), `set_module_order` for every saved order (at most
    one layout, no `calc_flow`), then the module names. A save without a custom order therefore reloads exactly like a
    plain build of the same files. New store fields and methods: `show_bipartite_nodes`, `display_options` (the 14
    TS display options the layout does not use, kept so that a save writes them back; replaces `settings` and
    `SETTINGS_DEFAULTS`), `get_options()`, `restore_options()`, `set_show_bipartite_nodes()`.
  - `showBipartiteNodes` (E19, ported): `set_networks` applies `show_bipartite_nodes` to every bipartite network
    before the first layout (the TS store applied it only in its setter, so a store built with the option off showed
    the nodes). `layout(..., show_bipartite_nodes=False)` hides the second node type.
  - `save_diagram(networks, path, *, loose=False, **layout_kwargs)` writes this format: a zip by default (`.zip` is
    appended to a path with another suffix), loose files in a directory with `loose=True`, or one `.json` file for a
    one-network diagram. Nothing is lost any more, so the "do not store" warning (`_warn_webapp_losses`) is gone.
    `generator` is `"alluvial (Python) <version>"`.
  - `layout(..., restore_state=True)` restores a saved diagram as the web app opens it: options, scheme, module
    orders and module names. Explicit keywords win silently (owner default): layout options, `scheme` and
    `show_bipartite_nodes` replace the stored values, `module_order`/`module_names` replace the stored orders/names.
    The restore warnings are issued as `UserWarning("saved diagram: ...")`. Saved files keep their colors by default
    (`colors=None`), even when the palette is empty. The restored `fontSize` and `aggregateStateNames` are used for the
    labels.
  - `read` takes a directory (its network files in name order) or a list of paths, and sorts the files of one saved
    diagram into saved order; a zip is sorted the same way. `layout` takes a directory like a zip. `read_dir` is new.
  - `NetworkFile.raw_modules` (the JSON `modules` list as read) and `NetworkFile.alluvial` (the block as read) are
    new; JSON `alluvial` is read. `io/saved_diagram.py` (`webapp_files`) is deleted; `io/alluvial_format.py` replaces it.
- **WP9, TS** (worktree `CHANGES-py-parity.md`): `parsers/alluvial-format.ts` (`serializeDiagram`,
  `readAlluvialMetadata`, `sortBySavedPosition`, `zipFiles`, `SAVED_OPTION_KEYS`, `PASS_THROUGH_KEYS`),
  `TreePath.toSavedPath`, `Network.inputLeafNodes`, `LeafNode.inputFlow`, `DiagramStore.getOptions`/`openNetworks`,
  E19 in `setNetworks`, `parseAcceptedFiles` sorts each batch by saved position, and the web app's "Download diagram
  (.zip)" button (zip only, owner decision) and `openNetworks` with a warning toast on load.
- **WP9, fixtures:** the round-trip blocks are renamed and now come from the engine's own writer and loader:
  `webAppFiles`/`webAppReload` become `savedStore` (the saved store options and scheme), `savedFiles`
  (`serializeDiagram` with `generator` and `saveId` pinned to `"fixture"`) and `savedReload` (the dump after
  `parseAcceptedFiles` + `openNetworks` on a default store, loose files and a zip asserted equal, plus `restored`:
  options, scheme and `openWarnings`); a `restore` scenario also has `savedReloadFiles` (the edited files it loaded).
  The harness-local `webAppFiles` writer, its `inputLeaves` wrapper and the `loadWebAppFiles` id rewrite are gone.
  The 20 existing round-trip fixtures (16 v3, 4 v4) changed only in these blocks and in the description text ("saved
  files + reload"); a diff that drops them and `description` shows every engine dump unchanged. 11 new v3 fixtures:
  `multilevel-tree__options__roundTrip` (every saved option changed, `Paired`, coloring, expand, order, names, a
  network name), `multilevel-tree__restore{Shuffled,Partial,MixedSaves,FormatVersion2,BadBlock,BadOptions}__roundTrip`
  (the restore warnings and partial restores), `multilevel-tree__flowThreshold40__orderHidden__roundTrip` (hidden
  modules in `moduleOrder`), `bipartite-json__hidden__roundTrip` (E19), `planted-json__default__passthrough__roundTrip`
  (Infomap's keys) and `mlayer-named-json__default__roundTrip` (named split layers, `layers` passed through). New
  hand-written data `tests/data/bipartite_t{0,1}.json` (`make_datasets.py` (l), `datasets.json` `v2_datasets.bipartite`).
  `provenance.txt`: new source hash.
- **WP9, tests:** new `tests/test_saveload.py`: Python-save == TS-save for every round-trip fixture; TS-save ->
  Python-load through `read` of a directory, a zip and a shuffled list of paths; reload == original (order, names,
  colors, options, scheme, network names; geometry within 1e-9); hidden order after lowering the threshold;
  Infomap pass-through; `restore_state=False`; restore warnings; 2019 rejection; `show_bipartite_nodes`.
  `test_v3_fixtures`/`test_v4_fixtures` check `savedFiles` byte for byte and `savedReload` bit for bit (with the
  restored options, scheme and warnings); the v4 `save_diagram` test runs the public API as a zip and as loose files.
  The fuzz round trip (`ts-roundtrip.json`) now holds `savedFiles`/`savedReload`; new
  `test_fuzz_python_save_ts_open{,_v2,_v4}` write Python's own files (its generator, a random save id) for every
  case, let TS open them (`generate.mjs --open DIR`, new) and compare TS's open with Python's bit for bit (direct
  Python-save -> TS-load). API tests: a directory is now read (its old `IsADirectoryError` tests now expect "holds no
  network files" for an empty one).
- **WP9, verification:** TS `tsc --noEmit` (package), `build:lib`, `npm test` (package 84 = 71 + 13 new in
  `alluvial-format.test.ts`, app 8) and `build:app` pass; `generate.mjs` regenerated (11 new, 20 changed in the
  round-trip blocks only) and `--check` byte-identical. Python 1946 passed / 19 skipped, not fuzz (1860 at WP8, +86:
  `test_saveload.py`, the v4 zip/loose save test, the new v3 fixtures); ruff check and format clean. Differential
  fuzz with round trips and the direct Python-save -> TS-open: v1, v2, v4 seeds 0-999 (3003 passed) and v4 seeds
  0-4999 (AC, 5001 passed). Large `science-stree__nameColored__roundTrip` (`--large`) passes.

- **WP12: docs, version and the capabilities notebook.** Version 0.5.0 (`pyproject.toml`, `alluvial.__version__`;
  `save_diagram` therefore writes `generator` `"alluvial (Python) 0.5.0"`). New `docs/capabilities.ipynb`: a tested
  tour of every public feature in ten sections (inputs: tree/ftree/stree/clu, Infomap JSON path and dict,
  `infomap.Infomap` objects and their `Result`, state/memory and multilayer networks with `split_layers`, a zip,
  directories and lists of files, `NetworkFile`, names/ids/identifier, bipartite networks; every `LayoutOptions`
  field; all color modes, schemes, highlight groups by mapping and by function, legends; `module_level`, `expand`
  and the hierarchy styles; `module_names`/`module_order`; drawing on subplot axes, fonts from `rcParams`, every
  label option, palettes and colormaps, gradients, styles, `get_artists`, PNG/PDF/SVG and `rasterized`; the geometry
  without matplotlib, `to_dict`/`from_dict` and a renderer of one's own; `save_diagram` zip/loose/`.json` ->
  `read` -> `layout` with checks, opening in the web app; 18 typical mistakes with their messages and 3 warnings;
  timings on the science networks). Every step asserts what it shows; it runs in about 15 s and is executed in
  place in the py314 conda env with its outputs (16 figures). `tests/test_capabilities_notebook.py` checks the
  stored outputs (no errors, no warnings) and executes it (the kernel finds `tests/data` through `ALLUVIAL_DATA`).
  `docs/tutorial.ipynb` re-executed (its `module_order` note now says one layout). README: status 0.5.0, a
  capabilities list, the notebook, fixture counts. `layout`'s `module_order` docstring no longer says one layout
  per move. `docs/dev/STATUS.md` and the `design.md` status section rewritten for 0.5.0 (settled owner decisions
  removed, new counts); the port-notes index and `tools/ts-fixtures/README.md` (v3 count 39, provenance fields, the
  replaced writer) updated. TS: package README section "Saving and opening diagrams" (the formatVersion 1
  contract), a CHANGELOG entry; the TS version is not bumped (owner decision).
- **WP12, found while writing the notebook (not fixed, both engines, parity holds):** a reload equals the original
  up to float summation order (about 1e-13 px, as saveload-plan.md §4.5 states): highlight groups built by a color
  operation sum their flows in another order than the groups built at load from `highlightIndex` (a plain JSON of
  the same nodes without `highlightIndex` reloads bit for bit). Labels of nodes with exactly equal flow can then list
  in another order (e.g. `multilevel_t*.tree` saved and reopened, or the same diagram colored differently). The
  notebook compares a reload with the original up to rounding and without the node-name labels, and checks that
  saving a reloaded diagram again is bit-exact.
- **WP12, fixtures:** none change (no engine or harness change).
- **WP12, verification:** both notebooks execute without errors or warnings in py314 (capabilities 15 s, tutorial
  4 s); Python 2050 passed / 19 skipped with `ALLUVIAL_TS_ROOT` at the worktree (2048 before WP12, after the
  review fixes, + the 2 notebook tests); `test_readme.py`, `test_tutorial.py` and `test_capabilities_notebook.py`
  pass; ruff check and format clean.
- **WP13: final verification.** Fixed: the sdist shipped `tests/test_capabilities_notebook.py` without
  `docs/capabilities.ipynb`, so the test failed when run from the sdist (`pyproject.toml` sdist `include` now lists
  the notebook). Added `test_python_save_diagram_zip_opens_in_ts` (`tests/test_fuzz_parity.py`): zips written by
  `alluvial.save_diagram` (Python's `zipfile`, deflated; plain, options + names + `module_id` colors, `module_level=2`,
  `module_order`, split layers) are opened by TS through the web app's loader (`parseAcceptedFiles` unzips with
  JSZip, then `openNetworks`; harness `openMain` now also opens `<case>/saved.zip` as one dropped file) and must
  equal Python's `read` of the same zip bit for bit. TS-side: the new lines of the WP changes formatted with the repo's
  prettier style (formatting only); two stray debug outputs (`packages/alluvial-diagram/out3.txt`, `out4.txt`)
  deleted from the worktree.
  - Fixtures: none change; `provenance.txt` gets the new TS source hash (the formatting).
  - Verification: TS typecheck, build (lib + app) and tests (92 package + 9 app) green; `--check` byte-identical;
    Python 2051 passed / 19 skipped (py314 `.venv`, `ALLUVIAL_TS_ROOT` at the worktree); wheel + sdist tests in
    fresh venvs on 3.11, 3.12, 3.13 and 3.14 green (fuzz skipped there: no harness in the sdist); fuzz 3000 seeds
    each for v1, v2 and v4 including the round trips and Python-save -> TS-open; large science fixtures replayed;
    both notebooks execute in conda py314 without errors or warnings; a headless run of the built web app loads a
    Python zip (same group positions and fills as Python, bit for bit), recolors it and downloads a zip that
    Python reopens like TS (bit for bit; equal to the in-app picture up to float summation order, as documented).

## [0.4.0] - not published

Module names and order for paper figures, checked against 14 new TypeScript reference scenarios
(`tests/fixtures/v4`, bit for bit, plus byte-identical saved texts).

### Added

- `layout(..., module_names=...)`: `{(network, module_id): name}` or a function of the new `alluvial.ModuleInfo`;
  `draw` shows the names, as the web app does. Saved diagrams write them in `moduleNames`.
- `layout(..., module_order={network: [module_id, ...]})`: modules bottom to top, `...` for the unlisted ones,
  applied as the web app's "move down" steps.
- `alluvial.read` of a `.zip` of network files (the web app's zip upload or `save_diagram(format="webapp")`), and
  zip paths as `layout` inputs.
- `examples/names_order.py`.

- `module_order`/`module_names` also take a network by the name given with `names=` (as a string, when exactly
  one network has it); their "no network" errors list the names.

### Changed

- `save_diagram(format="webapp")` also warns that module names are not stored.
- `save_diagram(format="diagram")` warns when a custom module order would be lost (the saved diagram has no field
  for it; pass `module_order` again after `read`).
- Engine op replay: a module referenced by both `moduleId` and `moduleIndex` is looked up by id, as in the TS
  harness (no fixture changes).

## [0.3.0] - not published

The web-app bridge, checked against 30 new TypeScript reference scenarios (`tests/fixtures/v3`, bit for bit, plus
byte-identical saved texts) and save/load round trips in the differential fuzzer.

### Added

- `alluvial.read` loads a saved web-app diagram (a port of the web app's converter) and returns a `SavedDiagram`;
  `layout`/`plot` take it and restore its state (layout options, default color, label font size, palette), as the
  web app that saved it did (`restore_state=False` loads it like today's converter).
- `alluvial.save_diagram(networks, path, format="diagram" | "webapp", **layout_kwargs)`: the web app's
  `saveDiagram` JSON, byte-identical to TS for the same store state, or one Infomap-JSON file per network with the
  palette (`colors`) that today's web app opens (directory or `.zip`).
- JSON top-level `colors` and per-node `color` (`checkColors`, including its index-0 quirk); `layout` keeps input
  colors by default when the input carries them.
- The 64 named color schemes of the web app (`alluvial.palette.SCHEMES`, `SCHEME_GROUPS`, `get_scheme`) and
  `layout(..., scheme=...)`; the scheme also gives the default `highlight_colors`.
- Engine: `DiagramStore.check_colors`, `set_network_name`, `set_module_name`, display `settings`, schemes by name;
  `alluvial._jscompat.js_json_stringify`.
- Module names of a saved diagram (`moduleNames`) are restored as the modules' custom names (with
  `restore_state=True`), as the 2019-2021 web app did; `ModuleGeometry.name` carries them and `draw` shows a module's
  name instead of its leaf names, as the web app's renderer does. (`save_diagram` still writes `moduleNames: []`.)
- A warning when every node flow is zero, negative or not a number (an empty diagram).
- Tutorial section "Open in the web app".

### Changed

- Warnings point at the caller's line whether `layout`, `plot`, `read` or `save_diagram` was called (the stack level
  is computed, not fixed).
- `layout(..., colors=None)` is the default when the input carries colors (a saved diagram, or JSON with `colors`).
- JSON `"flow": null` is read as 0 (what JS arithmetic does with the `null` that `JSON.stringify` writes for NaN).
- Examples and the tutorial use only infomap API that 2.15 does not deprecate and 2.14 supports (the relax rate as
  the `--multilayer-relax-rate` flag of `Infomap.run`, partition facts via `alluvial.read(im)`).

### Fixed (v3 parity review)

- A saved diagram whose network `name` is a number shows it as text, and one without a `name` (or `null`) shows no
  name, as the web app does (it showed the network id); a number network `id` is accepted.
- A number node `path` in Infomap or saved-diagram JSON is a top-level module, as in the web app (it was rejected).

### Fixed (release review)

- `save_diagram` refuses a path that does not fit the format: a `.zip` with `format="diagram"` (it wrote JSON into
  the zip name) and a `.json` with `format="webapp"` (it made a directory of that name).
- `alluvial.read` of a `.zip` or of a directory says how to read web-app files (extract them, `*.json`).

## [0.2.0] - not published

The v2 features of the web app, each a port of the store operations it uses, checked against 73 new TypeScript
reference scenarios (204 in all, bit for bit) and an extended differential fuzzer.

### Added

- Sub-modules: `layout(..., module_level=2)` (an int, or one per network) expands every visible module that has
  sub-modules, as a deterministic sequence of the web app's `expand` operations; `expand=[(network, module_id), ...]`
  expands single modules first. `ModuleGeometry.level`, `max_level` and `order` and `NetworkGeometry.outlines`
  (`OutlineGeometry`) describe the hierarchy.
- `draw(..., hierarchy=True)` draws the parent modules like the web app: offset gray boxes (`"shadow"`, the default
  whenever the geometry has outlines) or dotted rounded boxes (`"outline"`); `hierarchy_kw` styles them. Labels and
  network names make room for them.
- Highlight groups: `layout(..., highlight={label: identifiers})` or `highlight=callable(NodeInfo) -> label | None`,
  with `highlight_colors`. It runs the web app's "color by metadata" operation; `AlluvialGeometry.highlight_labels`
  (`HighlightLabel`) keeps the labels, and `layout` warns where the web app's color walk leaves labeled nodes gray.
- Legends: `draw(..., legend=True)` and `alluvial.legend(ax, other=None, **kwargs)` add a legend of the highlight
  labels above the diagram, inside the axes (the fit makes room for it).
- Module label lines take their node's highlight color, as in the web app (`draw(label_colors="auto")`: for
  highlight diagrams; `True` always). `ModuleGeometry.name_highlight_indices` and `name_insignificant` carry it.
- More colorings: `colors="layer"` and `colors="physical_id"` for multilayer and state networks.
- Multilayer splitting: `layout(..., split_layers=True)` (or one flag per network) and
  `alluvial.read(..., split_layers=True)` / `alluvial.split_layers(nf)` give one network per layer, matched by
  physical id, as the web app does.
- Infomap JSON input (`-o json` files, or the parsed dict) for `read`, `layout` and `plot`.
- `layout(..., ids=[...])` sets the network ids.
- `AlluvialArtists.outlines` and `AlluvialArtists.legend`; outline artists have the gid `outline:<network>:<path>`.
- Examples `examples/hierarchy.py`, `examples/highlight.py` and `examples/multilayer.py`.
- A tutorial notebook, `docs/tutorial.ipynb` (executed with its outputs, and run by the tests): seeded Infomap runs on
  a small temporal network, colorings, sub-modules, highlight groups, multilayer networks, reading files, a PDF
  figure for a paper and restyling artists.
- Warnings for silent mistakes: state networks matched by state id next to networks matched by node id, a
  `module_level` deeper than a network's module tree, a `highlight` function that labels no node, and `highlight`
  identifiers that match no node (now with examples and a hint at `identifier=`).

### Changed

- Colliding network ids (files with the same stem in different folders, or `NetworkFile`s with the same id) are
  renamed `out`, `out_2`, ... instead of raising `ValueError`.
- `layout(names=...)` accepts non-string names such as years (converted with `str`).
- Every README snippet now runs when pasted from the root of a source checkout (tested).
- Clearer errors: `layout([])` raises `ValueError` instead of returning an empty geometry; a missing path raises
  `FileNotFoundError` (also without a suffix) and a folder `IsADirectoryError`; `draw` raises `TypeError` for
  networks instead of a geometry and for a figure or an array of axes; unknown keywords of `layout` and `plot`
  suggest the closest valid name.
- The `draw(module_kw=...)` docs note that a hatch needs an `edgecolor` (the edge is drawn in the face color).
- `alluvial.read()` checks that the path exists (`FileNotFoundError`) and is not a folder (`IsADirectoryError`)
  before looking at its suffix. `module_level` accepts numpy integers and arrays. An `expand=` module without
  sub-modules says so in the error, and a module that is not shown says whether its parent must be expanded first
  or it is already expanded. A JSON dict node with a NaN or infinite `flow` raises `ValueError` (it used to give an
  empty diagram). `legend` on a diagram whose highlight labels are all gray says so.
- `draw` and `savefig` are much faster for diagrams with thousands of labels (text metrics are cached across
  fits): for the science example with `module_level=2`, from about 18 s to 4 s for the first draw and from 8 s to
  0.4 s for a following `savefig`, with identical output.

### Fixed (parity with the web app)

- `layout(highlight=...)` also labels a leaf that duplicate identifiers leave in a streamline node outside the
  module tree; before, it could stay gray where the web app colors it (`Network.built_leaf_nodes`, fixture
  `dupname-tree__highlight`).
- Splitting two inputs with the same file stem (the same file twice, or `a/x.tree` and `b/x.tree`) gave
  `colors="module_id"` the single-multilayer-network colors. The second input now gets the id `x_2` before
  splitting (layers `x_2_layer1`, ...), so each file's layers keep their own original id, as with the web app's
  distinct file ids (fixture `mlayer-split-twice__colorModuleIds`). Their layer ids change from `x_layer1_2` to
  `x_2_layer1`.
- Node metadata that is not an object (from JSON input): an array is read by index and `length` as in the web app
  (fixtures `planted-ftree__arrayMetadata`, `__arrayLength`), and a string, number or `true` raises the web app's
  `TypeError` in the metadata color operations instead of being skipped.
- Infomap JSON: a top-level `name` that is `""` or a number is used as given (a number as its JavaScript string),
  as in the web app; a `null` entry in `layers` that the layer-name lookup reaches raises `ValueError` (the web app
  throws).

### Notes

- The saved web-app diagram JSON (`networks` without `nodes`) is not read yet; it gets its own error message.
- Hierarchy shadows are drawn opaque in their color over white; the web app's `mix-blend-mode: difference` has no
  vector equivalent, so where a shadow overlaps a module the module simply covers it.

## [0.1.0] - not published

First release.

### Added

- `alluvial.layout()`: a port of the layout engine of the mapequation.org alluvial web app
  (`@mapequation/alluvial-diagram` 1.15.0). Module order, sizes, margins, streamlines and colors match the web app;
  all 128 v1 reference scenarios generated from the TypeScript store match bit for bit, and a differential fuzzer
  (`tests/test_fuzz_parity.py`, `tools/ts-fixtures`) compares the two on random networks and operations.
- `LayoutOptions` with the web app's layout options (height, module width, flow and streamline thresholds, margins,
  vertical alignment, module size and sort order) and the web app's coloring (`colors="similarity"`, `"module_id"`
  or `"nodes"`).
- `AlluvialGeometry`: a frozen, renderer-independent geometry contract (modules, groups, streamlines as path codes or
  SVG paths, labels) with `to_dict()` / `from_dict()`. `ModuleGeometry.name_candidates` offers renderers more label
  names than the web app's lines-per-module rule allows.
- `alluvial.read()` for Infomap `.tree`, `.ftree`, `.clu` and `*_states.*` files and for `infomap.Infomap` objects
  or their `Result` (infomap >= 2.14), including state, multilayer and bipartite networks.
- matplotlib renderer: `alluvial.draw()`, `alluvial.plot()` and `alluvial.get_artists()`. Labels and limits are
  refitted at every draw (constrained layout, `bbox_inches="tight"` and resizing work), overlapping labels lose lines
  instead of colliding, long labels are truncated, gradient streamlines stay small in PDF/SVG, and every artist has
  a `gid`.
- The web app's color handling (`alluvial.palette`), including its 512-color `c3-sinebow` palette.

### Notes

- Requires Python >= 3.10 and matplotlib >= 3.7. Reading Infomap objects needs infomap >= 2.14, which requires
  Python >= 3.11; files written by any infomap version read on every supported Python.
- Hierarchical sub-modules (expand/regroup), highlight groups and Infomap JSON input are planned for a later version.
