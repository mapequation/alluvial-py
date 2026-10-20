# TS layout fixtures

These tools produce the reference geometry that the Python layout must reproduce
to float tolerance. They run the real TypeScript engine of the web app headlessly
in Node and write one JSON file per scenario to `tests/fixtures/`.

## Regenerate

Run from the repo root (`alluvial-py/`):

```sh
node tools/ts-fixtures/generate.mjs           # rewrite tests/fixtures/*.json + provenance.txt
node tools/ts-fixtures/generate.mjs --check   # regenerate to a temp dir, byte-compare, exit 1 on diff
node tools/ts-fixtures/generate.mjs --only planted-ftree   # only scenarios whose name contains the string
node tools/ts-fixtures/generate.mjs --out /some/dir        # write somewhere else
node tools/ts-fixtures/generate.mjs --fuzz /some/dir       # differential fuzzing, see below
node tools/ts-fixtures/generate.mjs --large --out /some/dir # also the `large` scenarios (not committed), see v2/v3
node tools/ts-fixtures/generate.mjs --make-data             # rewrite the TS-derived data: tests/data/ts_color_schemes.json,
                                                            # tests/data/ts_c3_schemes.json, src/alluvial/data/{color-schemes,d3-interpolators}.json
```

The default run and `--check` cover `tests/fixtures/*.json` (v1/v2), `tests/fixtures/v3/*.json` (v3) and `tests/fixtures/v4/*.json` (v4);
`--check` also regenerates the TS-derived v3 data files in memory and byte-compares them with `tests/data/`.

The input datasets in `tests/data/` are already committed. To recreate the
seeded ones (byte-identical with the PyPI Infomap 2.15.1 wheel in `.venv`; a dev
build of 2.15.1 writes an extra `# seed` header line and finds other multilevel
partitions):

```sh
.venv/bin/python tools/ts-fixtures/make_datasets.py
```

Requirements: Node >= 22 (tested with v24.21.0) and a checkout of the TS
monorepo (mapequation/alluvial) with its `node_modules` installed. The checkout defaults to
`../web/alluvial` next to this repo. Override it with
`ALLUVIAL_TS_ROOT=/path/to/alluvial`. Nothing is installed, built or written
in the TS repo. Vite's cache goes to `$TMPDIR/alluvial-ts-fixtures-vite-cache`.
A full run takes about 4 s. Each scenario runs twice (see Verification).

## How it works

| File | Role |
|---|---|
| `generate.mjs` | Launcher. Resolves `vite` (8.3.4) from the TS repo's `node_modules`. Starts an in-process Vite dev server with no config file, maps the alias `@alluvial-src` to `<TS>/packages/alluvial-diagram/src`, loads `harness.ts` through `ssrLoadModule`, writes `provenance.txt`, and implements `--check`. |
| `harness.ts` | Runs each scenario on the real `DiagramStore`/`Diagram` and serializes the result. |
| `scenarios.ts` | Dataset groups, variants and operations. |
| `make_datasets.py` | Seeded Infomap datasets. Writes `tests/data/datasets.json` with every parameter. |
| `scenarios-v3.ts` | v3 scenarios (round trips through the saved files: `serializeDiagram` + `openNetworks`, `checkColors`, colour schemes), see "v3 scenarios". |

- The harness imports the **TS sources** (`packages/alluvial-diagram/src`), not `dist/`.
  `dist/index.js` is stale: `src/store/DiagramStore.ts`, `src/utils/BipartiteGraph.ts`,
  `src/schemes/*`, `src/index.ts`, `src/react/Diagram.tsx` and `src/utils/save-svg.ts`
  are newer than it. Bare imports (`mobx`, `d3`, `@mapequation/infomap-parser`, `jszip`, ...)
  resolve from the TS repo's `node_modules`, because Node resolves them relative to the
  importing source file. TS transpilation follows the package `tsconfig.json`
  (`useDefineForClassFields: true`, ES2020), as in the app build.
- Loading uses the web app's own path. Each file becomes a `File` and goes through
  `parseAcceptedFiles(files, [], formats, store.identifier)` (`src/parsers/parse-files.ts`).
  That runs `@mapequation/infomap-parser` `parse(text, undefined, true, false)`,
  `setIdentifiers` and `createFile`. Node has no `FileReader`, so the harness adds a
  minimal shim. The random ids from `utils/id.ts` are then replaced with the file stem,
  e.g. `planted_t0`. Network names stay the file basename, e.g. `planted_t0.ftree`. The web app's ids are
  distinct, so a stem that an earlier input file already has becomes `<stem>_<k>` (smallest `k >= 2` not
  taken), the rule `layout()` applies before splitting. It matters only for split files, whose layers carry
  the file id as `originalId` (`mlayer-split-twice__colorModuleIds`).
- Each scenario uses a fresh `new DiagramStore(options)` and calls `store.setNetworks(files)`,
  which runs `calcFlow` and `updateLayout` once. Then it calls the listed store operations.
  The coloring operations are the real store methods, and each one ends with another
  `calcFlow` + `updateLayout`.
- `console.time`/`timeEnd` are silenced (since fix round WP11 the library no longer calls them). `console.warn` calls are captured in the fixture's `warnings`.
- **v2 inputs.** JSON files (Infomap `-o json`) take the same `parseAcceptedFiles` path; the stem override also
  replaces a JSON top-level `id`. A scenario's `nodeMetadata` (or its `highlight` macro) is assigned to the parsed
  input nodes (`file.nodes[j].metadata`) before the split and `setNetworks`. A scenario's `split` file indices are
  replaced, in increasing order, by `expandMultilayerFile(file, files)` (`src/parsers/multilayer-utils.ts`, the web
  app's "split layers"), and each layer gets the id `${file.id}_layer${String(layerId)}` (v2-io §2.4).
- **v2 macros.** `moduleLevel` and `highlight` are harness macros. They run real store ops and are recorded as the
  concrete ops they issued (see `inputs.operations` and `inputs.macros` below). Since fix round WP8 (B2) `moduleLevel`
  is one `store.setModuleLevel(levels)` (expand rounds without intermediate layouts, one layout at the end), recorded as
  `{op: "setModuleLevel", levels: [k per network]}`, or as no op when nothing expands.

### Instrumentation (read-only)

`Diagram.prototype.updateLayout` is wrapped. During each call, the diagram
instance's `forEachDepthFirstPreOrderWhile`/`forEachDepthFirstPostOrderWhile` are
shadowed so that the harness can take two snapshots. Neither one changes engine
state:

1. After pass 1 (the first top-level pre-order traversal, `Diagram.ts:176-249`):
   the pass-1 module margins (before the 20 % cap and justify), the pass-1
   module/group rects, and `module.index`.
2. Just before pass 2 (`Diagram.ts:322`): every streamline node's
   `oppositeStreamlinePosition`. This is the sort key used at `Diagram.ts:305-315`.
   It reads the opposite group's pass-1 `y`, which pass 2 then overwrites.

The fixture keeps the snapshots from the **last** `updateLayout` call.

### Values replicated by the harness (not engine state)

`usableHeight`, `maxTotalMargin` and the per-network totals are local variables
inside `updateLayout`. The harness recomputes them with the same expressions, in
the same evaluation order, from the pass-1 snapshot. It then **asserts** that
every visible module's final `height === size(module) * usableHeight`, with
exact float equality, so a replication error aborts the run. The label line
count `maxLines` is replicated from `react/Module.tsx:201-214`. The label names
come from the engine's `Module.getLargestLeafNodes`.

### Verification

- **Cross-check:** every scenario also runs on the plain engine, with the wrapper
  disabled. All network/module/streamline-node rects, margins, indices and link
  paths must be identical to the instrumented run, or generation fails.
- **Determinism:** `--check` regenerates everything and byte-compares. Two full
  regenerations were verified identical. `make_datasets.py` was also run twice
  with identical output. The only randomness in the engine is `utils/id.ts`,
  which is overridden.
- `provenance.txt` records the TS repo HEAD, whether `src/` is dirty, a sha256
  of `src/**/*.ts(x)` (tests excluded), the node, vite, mobx and parser
  versions, and the v1/v2, v3 and v4 fixture counts (the sha256 of the web app's `save-diagram.js` was dropped with
  the 2019 format in fix round WP2).
  `--check` prints a note when it differs.

## Datasets (`tests/data/`)

| Group | Files | Origin |
|---|---|---|
| `debug5-tree` | `debug5_{0,1}.tree` | copied from the TS repo's `apps/web/public/data/`; 5 nodes, 3-level paths |
| `debug5-stree` | `debug5_{0,1}.stree` | same data with `;` (insignificant) markers, but only below the top level (`1:2;3;`), so top-level groups are never insignificant; insignificant groups appear after `expand` (`debug5-stree__expand`) |
| `science-stree` | `science{2001,2003,2005,2007}_2y.stree` | web example, ~7k nodes per network, journal names |
| `planted-{ftree,tree,clu}` | `planted_t{0,1,2}.*` | (a) seeded planted partition, 3 slices, 100-130 nodes, nodes appear/disappear, groups split/merge |
| `states-{tree,ftree,clu}` | `states_t{0,1}.*` | (b) seeded state network, `states=True` outputs. `state_id = 10*node_id + topic`, so ids are stable across slices. Names `p<node_id>` are shared by all states of one physical node. |
| `multilevel-tree` | `multilevel_t{0,1,2}.tree` (+ `.ftree`) | (c) seeded hierarchical planted partition, 3- and 4-level trees, 3-4 top modules |
| `directed-{ftree,tree}` | `directed_t{0,1}.*` | (d) seeded directed weighted network, `*Links directed` |
| `planted-json`, `mixed-json-tree` (v2) | `planted_t{0,1,2}.json` | (e) `write_json` of the planted runs (`startedAt`/`completedIn` normalized) |
| `states-json` (v2) | `states_t{0,1}.json` | (e) `write_json(states=True)` of the state runs |
| `mlayer-unsplit`, `mlayer-split`, `mlayer-split-twice` (v2) | `mlayer_states.tree` | (f) seeded multilayer state network: 45 physical nodes (3 super x 3 sub x 5), 4 layers added in the order 3,1,4,2 (intra-layer links only), 157 state nodes, 6 top modules, 3-level paths, `layer_id` column |
| `mlayer-split-json` (v2) | `mlayer_states.json` | (f) the same run as JSON |
| `mlayer-split-flat` (v2) | + `mlayer_flat.tree` | (f) the links summed over layers, first order, same physical ids (a non-split neighbour) |
| `mlayer-named-json` (v2) | `mlayer_named.json` | (f) `mlayer_states.json` + `layers: [{id: 1, name: "Alpha"}, {id: 3, name: "Gamma"}, {id: "4", ...}]` (`"4"` does not match under `===`) |
| `prefix-tree` (v2) | `prefix_t{0,1}.tree` | (g) synthetic, seeded flows: 12 top modules (`"1"` is a string prefix of `"10"`-`"12"`); top module 1 has 11 sub-modules (`"1:1"` prefixes `"1:10"`, `"1:11"`) x 2 x 2-3 leaves (4-level paths), the others 2 x 2 leaves (3-level). Same node ids in both slices. |
| `hlskip-tree` (v2) | `hlskip_t{0,1,2}.tree` | (h) hand-written (v2-highlight §8.2): in t0/t1 a visible single-leaf module that is not last triggered the colour-walk skip before fix round WP5 (E4); the fixtures now pin the fixed walk |
| `abc-chain` (v1) | `abcchain_t{0,1,2}.tree` | (j) hand-written (colors-render §6.1): `a = {1: n1,n2}`, `b = {1: n1,n2; 2: n3,n4}`, `c = {1: n3,n4; 2: n1,n2}`; a similarity chain that starts in network 1 |

v3 inputs (none of them is in `datasets.json`):

| Group | Files | Origin |
|---|---|---|
| `jscolors-{a,b,abc}` (v3) | `jscolors_{a,b,c}.json` | hand-written 3-5 node Infomap-JSON files for `checkColors` (v3-webapp-json §5): `a` has `colors: ["#f00", "#0f0"]` and node `highlightIndex` 1, 1, 5 (out of range), -1, unset; `b` has `colors: true` and node `color` `#0f0`, `#00f`, `null` (+ `highlightIndex` 4), `#0f0`, unset (string paths); `c` has `colors: {...}` (ignored) and node colours (ignored). `a` also has a top-level `name: "A"` (overrides the file name). |
| `insig-stree` (v3) | `insig_t{0,1}.stree` | hand-written 9-node `.stree` pair with **top-level** `;` paths (`1;1;3;`, `2;1;3;`) and one lower one (`1:1;4;`), as in the science files. The web-app files write them cleaned, so the reload loses the insignificance. |
| — (v3 reference data) | `ts_color_schemes.json` (47 kB) | **TS-derived** (`--make-data`): `{source, default: "C3 Sinebow", names, groups, schemes}` = the key order of `COLOR_SCHEMES`, `SCHEME_GROUPS` and `COLOR_SCHEMES` itself (65 schemes since web app 1.16 added `C3 Oklch`; v3-webapp-json §6.1), in the fixture JSON layout. The C3 schemes are c3 2.0.1's, in the default tone (hex strings; the c3 1.x `rgb()` strings of `docs/dev/port-notes/data/c3-sinebow-512.json` are history). The package ships the same text as `src/alluvial/data/color-schemes.json`. |
| — (c3 reference data) | `ts_c3_schemes.json` (470 kB) | **TS-derived** (`--make-data`, #47): `TONES`, `DEFAULT_TONE`, the `schemeIsHueSource` schemes and `defaultSchemeOffset` of every scheme; every d3 interpolator c3 takes as a hue source sampled at 267 `t` (a 1/256 grid, outside [0, 1], awkward floats); `schemeColors(name, tone, offset)` of the 5 C3 schemes x 8 tones x offsets `[null, 0, -45.5, 90, 245, 400]` (first 8 colours + sha256 of `JSON.stringify`); and c3's `hierarchy()` of 50 synthetic modules with `hierarchyOptions` of every scheme (3 tone/offset cases for the hue sources); `hierarchyWide`: `hierarchy()` of a module with 119 sub-modules for C3 Sinebow and C3 Oklch (c3-colors 2.0.1 differs: strict xfail `test_hierarchy_wide_module_matches_ts`). `tests/test_c3_schemes.py`. `src/alluvial/data/d3-interpolators.json` holds the interpolators' colour data for the package (ColorBrewer ramps for `interpolateRgbBasis`, the viridis ramps). |

The v2 datasets are recorded under `v2_datasets` in `datasets.json` (the v1 reader tests iterate `datasets` only).
`make_datasets.build_infomap("mlayer_states")` / `("mlayer_flat")` rebuild the multilayer runs.

`make_datasets.build_infomap(stem)` (e.g. `"states_t0"`) rebuilds and runs the `infomap.Infomap`
object behind a seeded slice without writing anything. Its `write_tree` output equals the committed
file, so the Infomap-object reader can be tested against the file readers and these fixtures.

`tests/data/datasets.json` records each slice's graph seed, generator
parameters, Infomap kwargs and args line (`seed=123`, `num_trials=10`), the
result size, and the Infomap/Python versions. Infomap's wall-clock header lines
are normalized: `# started at 1970-01-01 00:00:00` and `# completed in 0 s`.

## Differential fuzzing (`fuzz/`)

`fuzz/gen.py` writes seeded random cases: 1-6 networks as `.tree`/`.ftree`/`.stree`/`.clu` text
(random module trees up to 5 levels, flows with zeros, ties, tiny and the odd NaN/Infinity token,
nodes appearing/disappearing, duplicate ids and names, names with spaces/quotes/unicode/tabs,
state ids and layer ids), random store options (all layout options, including edge values such as
`flowThreshold` 0 and 0.999999, non-integer `marginExponent`, heights 1e-8 to 1e22) and random
operation sequences (all colour ops, `colorModule`, `clearColors`, option setters after load).
`generate.mjs --fuzz DIR` runs every `DIR/<case>/case.json` on the TS store and writes
`DIR/<case>/ts.json` in the fixture format (or `{error, stack}` when TS throws). It does not touch
`tests/fixtures`.

```sh
.venv/bin/pytest -q tests/test_fuzz_parity.py                                   # 30 seeds
ALLUVIAL_FUZZ_START=0 ALLUVIAL_FUZZ_SEEDS=5000 .venv/bin/pytest -q tests/test_fuzz_parity.py
.venv/bin/python tools/ts-fixtures/fuzz/gen.py /tmp/cases --seeds 0:100      # cases only
```

The test replays each case in Python with the case's initial options and the operations the TS
harness recorded, and compares the full dump bit for bit (plus the SVG path strings exactly). When TS
throws, Python must raise too. A divergence found this way is minimised and added as a scenario below.

**v2 fuzzing** (`gen.py --v2`, `make_cases(seeds, out, v2=True)`): the same cases (files, options and v1 ops are
unchanged) plus v2 ops at random positions, drawn from a separate `random.Random(f"v2-{seed}")`: `expand`, `regroup`,
`moveModule`, `resetLayout`, `moduleLevel`, `colorSelectedNodes`, `colorMatchingModules`, `colorModuleIds`,
`colorNodesInModule`, `colorByLayer`, `colorByPhysicalId`, the three metadata ops and `setDefaultHighlightColor`,
and in half of the cases `nodeMetadata` (per file, aligned with the node rows; strings, numbers, `{}` and `null`).
Raw indices are resolved like `colorModule`'s; `colorSelectedNodes` entries `{networkIndex, leafIndex}` become
`{networkIndex, identifier}` (`[...network.leafNodes()][leafIndex % n]`). A refused `expand`/`regroup`/`moveModule` does
not abort the case: the recorded op gets `"result": false` (`true` when it succeeded), and Python must return the same
bool. `tests/test_fuzz_parity.py` runs both (`test_fuzz_parity` the v1 cases, `test_fuzz_parity_v2` the v2 cases;
`-k v2` for the v2 ones only). When TS throws, Python must raise on the raw ops or in the dump (the harness dump can
throw too: `Network.tree` on a module shown together with one of its sub-modules, and the pass-2 height self-check
after a one-sided `colorMatchingModules`, which runs no layout).

v2 cases also draw the **`highlight` macro** (raw groups `[label, [{networkIndex, leafIndex}]]`, resolved to identifiers,
an identifier keeping its first label; one colour per label). In fuzz mode the harness writes the labels onto the leaves
when the macro runs (any position, any number of macros, together with `nodeMetadata`), like the Python
`DiagramStore.apply_highlight` of `layout(highlight=...)`: every leaf built for a network (also one that duplicate
identifiers left in a streamline node detached from the tree) gets a fresh metadata object with its other keys kept.
Python replays both macros through `apply_module_level`/`apply_highlight` and checks the ops they issue. Raw network
indices are reduced modulo the network count and a `moduleLevel` list is cycled to one k per network, since split layers
add networks. The **v2 input profile** comes from its own `random.Random(f"v2in-{seed}")` (about half the cases get none
and keep the v1 files): Infomap JSON files (array or `"1:2"` paths, `modules` records, sometimes per-node `metadata`),
multilayer state networks with `split` (rarely a non-multilayer file, which must raise on both sides), deep (up to 10
levels), chain, flat or singleton hierarchies, and many duplicate identifiers.

Run (2026-10-10): v2 seeds 0-20000 and v1 seeds 0-5000 pass (about 6 % of the cases raise in TS, mostly on fuzzed
`.stree` path syntax; Python raises too). Divergences found: NaN outline rects (`nan-multilevel__expand`, removed in fix round WP4 with NaN flows), and the
`highlight` labels missing a detached duplicate-identifier leaf (`dupname-tree__highlight`, fixed in
`apply_highlight`). Earlier, seeds 0-15000 v2 passed without the highlight macro and the input profile.
Later (v3 parity review): v1 and v2 seeds 20000-24999 pass with round trips. v2 seed 21633 exposed a test bug: when TS
throws in a round-trip dump, the Python reloads were built with the case's final options (after `setOption`) instead
of its ctor options (the harness's `run.options`), so the `Network.tree` throw of a reload was missed; fixed in
`_check_round_trip_case`.
Release review (0.3.0): v1 and v2 seeds 6000-6999 pass (2000 cases). A first run had reported v1 seeds 6746 and 6907
diverging in `label.namesSingleLine`; neither reproduces on the current sources, alone or in the range.

**v4 fuzzing** (`gen.py --v4`, `make_cases(seeds, out, v4=True)`, implies v2): the v2 case unchanged plus v4 ops from
`random.Random(f"v4-{seed}")` at random positions. Ops: the **`moduleOrder` macro** (one `setModuleOrder` op since
fix round WP7) with
raw `[networkIndex, spec]` entries (`spec`: raw visible-module indices plus at most one `"..."`, or `"reverse"`/`"rotate"`
of all visible modules), resolved at its turn (network modulo the count, a repeated network dropped; index modulo the
visible modules of `network.children`, as ids, a repeated id dropped) and run by `runModuleOrder`; the **`moduleNames`
macro** with raw `[networkIndex, moduleIndex, name]` (index modulo all children, hidden ones included), run as one
`setModuleName` per entry recorded by `moduleId`; and plain `setModuleName` with a raw `moduleIndex`. Python replays the
macros through `apply_module_order`/`apply_module_names`, which must issue the recorded ops (`-k v4`).
**c3 fuzzing** (`gen.py --c3`, `make_cases(seeds, out, c3=True)`, implies v4; web app 1.16): the v4 case unchanged
plus, from `random.Random(f"c3-{seed}")`, sometimes a `color` block of ctor options (`colorScheme` from C3,
interpolated and list schemes, `colorTone`, `colorOffset` null/0/245/negative/fractional/1e6/random) that the harness
merges into the store options, and c3 ops at random positions: `setSelectedScheme`, `setSelectedTone`,
`setSelectedOffset`, `colorModuleHierarchyInAllNetworks` (half the time after a `moduleLevel`) and the scheme-driven
`colorMatchingModulesInAllNetworks`/`colorModuleIdsInAllNetworks`/`colorNodesInModulesInAllNetworks`. Every case
round trips through the saved files (tone and offset included; `restored` carries `colorTone`, `colorOffset` and
`schemeSha256`). On seeds 0-199: 90 % with a `color` block, 58 % reach a hierarchy colouring, 3 % raise in TS (fuzzed
`.stree` syntax) (`-k c3`).
The case's **`open` spec** (`c3_open`, from `random.Random(f"c3open-{seed}")`) says how the saved files are opened in
both directions: sometimes a `reloadStore` (the opening store's ctor scheme/tone/offset, which the restore rules of #57
depend on) and sometimes edits of the saved `colorScheme`/`colorTone`/`colorOffset` (valid; unknown or inherited-key
names; wrong JSON types; null; removed; odd literals such as `1e400`, `-0`, `1E2` and integers beyond 2**53; random
large/fractional offsets) in all files or some (`mutateFiles`). TS-save -> Python-open: the harness edits its saved
files (`mutateSavedTexts`; written as `savedReloadFiles`). Python-save -> TS-open: `gen.mutate_saved_texts` edits the
Python-saved files and `<case>/open.json` carries the `reloadStore` for `openMain`. setSelectedOffset also takes null.
TS outputs are read with integer literals beyond 2**53 as doubles (`_load_ts_json`; TS writes a restored offset of
-4.27e17 as `-427299959682199200`). Run (2026-10-21, TS 60fa1bf): v1, v2, v4 and c3 seeds 0-4999 and c3 seeds
5000-9999 pass, including both open directions. The harness's fuzz-mode `highlightLeaves` defines `metadata` as an own
property on the leaves since #58 (the field is private behind a getter). Regressions: `toneRestoreOddColor` (inherited
`toString` scheme, array tone, `1e400` offset) and `toneRestoreHugeOffset` (an integer offset literal beyond 2**53).

Run (2026-10-10): v4 seeds 0-9999 pass (on seeds 0-199: about 1.1 moves per `moduleOrder` and 2.6 names per `moduleNames` macro; 3 % of the cases raise in TS,
on fuzzed `.stree` syntax), plus v1 and v2 seeds 0-2999 as regression. No divergence found. A mutation check
(networks in descending order in `apply_module_order`, names stripped in `apply_module_names`) fails 35 of 300 v4 seeds.
Release review (0.4.0): v1, v2 and v4 seeds 10000-10999 pass (3000 cases), after `_module_at` was changed to
prefer `moduleId` over `moduleIndex` as the harness's `moduleAt` does.

**Saved-diagram round trips (fix round WP9).** For every case that TS runs without error, `fuzzMain` also writes
`<case>/ts-roundtrip.json`: the saved files of the final state (`savedFiles`, the engine's `serializeDiagram`) and
their open (`savedReload`: `parseAcceptedFiles` + `openNetworks`), exactly as for the v3 `roundTrip` fixtures
(`roundTripBlocks`), or `{error, stack}` when TS throws there. `tests/test_fuzz_parity.py` checks that the Python
`serialize_diagram` gives the same texts byte for byte (so TS opens exactly what Python writes) and that the Python
`open_networks` of them equals the TS open (so Python opens what TS saves like TS). In addition,
`test_fuzz_python_save_ts_open{,_v2,_v4}` write Python's own files for every case (its generator, a random save id) to
`<case>/saved/`, run `generate.mjs --open DIR` (harness `openMain`: TS opens each `<case>/saved/*.json` like the web
app, loose and as a zip, and writes `<case>/ts-open.json`) and compare TS's open with Python's bit for bit: a direct
Python-save -> TS-load. `test_python_save_diagram_zip_opens_in_ts` does the same for zips written by
`alluvial.save_diagram` (Python's `zipfile`, deflated): `openMain` opens `<case>/saved.zip` as one file dropped on
"Load networks" (`parseAcceptedFiles` unzips it with JSZip), and Python's `read` of the same zip must equal it.

The `large` scenarios (`science-stree__level2`, ~40 MB) are replayed by an opt-in test:

```sh
node tools/ts-fixtures/generate.mjs --large --only science-stree__level2 --out /tmp/large
ALLUVIAL_LARGE_FIXTURES=/tmp/large .venv/bin/pytest -q tests/test_engine_fixtures.py -k large
```

## Scenarios (`tests/fixtures/<group>__<variant>.json`, 205 files: 130 v1, 75 v2; v1 = no `features` list, as `tests/conftest.py` splits them)

- Primary groups `debug5-tree`, `debug5-stree`, `planted-ftree`, `states-tree`,
  `multilevel-tree`, `directed-ftree` get every variant in the table below.
- Secondary groups `planted-tree`, `planted-clu`, `states-ftree`, `states-clu`,
  `directed-tree` get `default` and `colored`.
- `science-stree` gets `default`, `name` and `nameColored`.

| Variant | Store options / operations |
|---|---|
| `default` | `DiagramStore` defaults: height 600, moduleWidth 80, streamlineFraction 2, streamlineThreshold 1, flowThreshold 0.005, marginExponent 4, zeroMargins false, verticalAlign "bottom", moduleSize "flow", sortModulesBy "flow", identifier "id" |
| `zeroMargins` | `zeroMargins: true` |
| `moduleSizeNodes` | `moduleSize: "nodes"` |
| `flowThreshold05` | `flowThreshold: 0.05` |
| `flowThreshold0` | `flowThreshold: 0` |
| `flowThreshold40` | `flowThreshold: 0.4`. Hides 1-4 modules per network, so it covers links to invisible modules, `-Infinity` sort-key ties and the invisible-module order on small data. At 0.005/0.05 the small datasets hide (almost) nothing. |
| `flowThreshold40Justify` | `flowThreshold: 0.4, verticalAlign: "justify"`. Covers justify with missing flow (`visibleFlow` 0.6-0.85), where margins absorb the hidden flow. |
| `sortNodes` | `sortModulesBy: "nodes"` |
| `sortNodeId` | `sortModulesBy: "nodeId"` |
| `geometry` | `height: 200, moduleWidth: 50, streamlineFraction: 1.5, marginExponent: 5`. Triggers the 20 % margin cap for groups with 3 or more visible modules per network. |
| `justify` | `verticalAlign: "justify"` |
| `colored` | `colorMatchingModulesInAllNetworks()` after `setNetworks` |
| `name` | `identifier: "name"` |
| `nameColored` | `identifier: "name"` + `colorMatchingModulesInAllNetworks()` |

Extra scenarios:

- `planted-ftree__colorModuleIds`: `colorModuleIdsInAllNetworks()`
- `planted-ftree__colorNodes`: `colorNodesInModulesInAllNetworks(undefined)`
- `planted-ftree__coloredSortHighlightIndex`: `sortModulesBy: "highlightIndex"` + `colorMatchingModulesInAllNetworks()`
- `planted-ftree__colorModule`: `colorModule(network 1 .children[0], "#ff0000")`
- `multilevel-tree__expand`: `store.expand(network 0 .children[0])`
- `multilevel-tree__expandColored`: `store.expand(network 1 .children[0])` + `colorMatchingModulesInAllNetworks()`
- `multilevel-tree__expandRegroup`: `store.expand(...)` then `store.regroup(network 0 .children[0])`
- `debug5-stree__expand`: `store.expand(network 0 .children[0])` then `store.expand(network 1 .children[0])`. This is the only small fixture with insignificant groups.
- `abc-chain__similarity` (fix round WP6, S1): `colorMatchingModulesInAllNetworks()`; one colour counter for all
  network pairs, so the chain `b.2` -> `c.1` gets `scheme[1]` (with the old per-pair counter all five modules got
  `scheme[0]`).

Coverage-gap and fuzz-regression scenarios:

- `planted-ftree-single__{default,colored,geometry,justify,colorModuleIds,colorNodes}`: a single network
  (the `networks.length < 2` branch of `colorMatchingModulesInAllNetworks`).
- `planted-ftree__setOptions`: option changes after load (store setters, one `updateLayout` each;
  `flowThreshold` 0.4 then 0 brings hidden modules back with stale values).
- `planted-ftree__colorOpsMixed`: colour ops in sequence, including `colorModule` with the default colour
  and `clearColors`.
- `{planted-ftree,debug5-tree}__height37` (height 37.5, `marginExponent` 3.5) and `__heightHuge`
  (height 1e6).
- `{planted-ftree,states-tree,multilevel-tree}__geometryJustify40`: the margin cap combined with justify
  and hidden modules.
- `zeroflow-tree__*`: zero-flow nodes in visible modules; the third network has only zero flows, so its
  module flow threshold is `Infinity`. `zeroflow-all__*`: every flow is zero (`maxNetworkFlow` 0, NaN sizes).
- (Removed in fix round WP4: `nan-tree__*` and `nan-multilevel__expand`. A NaN flow made the numeric sort
  comparators inconsistent, so the order depended on V8's TimSort, which Python emulated. Both engines now reject a
  NaN, infinite, missing or `null` flow at load (E9), so `tests/test_io_validation.py` and the TS
  `parse-files.test.ts` cover the rejection, and the fuzzer writes non-finite flow tokens in about 1 case in 200.)
- `fuzz2455__ops`, `fuzz670__ops`, `fuzz1347__ops`: fuzz cases kept verbatim (mixed formats, unicode names,
  identifier `"name"`, repeated colour ops, setters; `fuzz1347` has a finite streamline sort-key tie).
- `dupname-tree__highlight` (v2): hand-written `dupname_t{0,1}.tree`, identifier `"name"`, `highlight` label `c`.
  Network 1 has two leaves named `c` in module 2. Since fix round WP5 (E6) only the registered (last) one links to
  network 0 and the other stays dangling. Before, one of them sat in a streamline node that was detached from the tree
  (`network.leafNodes()` missed it) until the colour walk's `update()` re-attached it, with a `NULL--` streamline id. Input-node metadata labels it,
  so `layout(highlight=...)` must too (`Network.built_leaf_nodes`). Found by the v2 fuzzer through the
  `apply_highlight` property test.
- `dupname-tree__recolor` (v2, fix round WP5): the same data, `colorByPhysicalId` then `clearColors`, so every leaf runs
  `update()` (the old re-steal path). `tests/test_engine_fixtures.py::test_no_fixture_has_a_null_streamline_id` checks
  that no fixture has a `NULL--` streamline id.

The four `*__expand*` scenarios above are v2 (tagged `"features": ["hierarchy"]`; that line is the only change from
their v1-era bytes). `colorModule` is v1. `children[i]` always refers to the order after the previous layout.

### v2 scenarios

Every v2 fixture has a top-level `features` list (below); a v1 fixture has none. A replay needs every listed
feature. Specs: `docs/dev/port-notes/v2-hierarchy.md` §12, `v2-highlight.md` §8, `v2-io.md` §8. `S[i]` is
C3 Sinebow entry `i` (written out in the ops), `n/m` is `networkIndex/moduleIndex`, `"id"` a `moduleId`.

New v1-replayable baselines (no `features`): `hlskip-tree__default`, `prefix-tree__default`, `mlayer-unsplit__default`.

**Hierarchy** (`hierarchy`, `move`, `moduleId`)

The counts after `moduleLevel` are the expands of the pre-WP8 sequence (one layout each); since WP8 each macro records
one `setModuleLevel` op with a single layout.

| Scenario | Options / ops | Covers |
|---|---|---|
| `multilevel-tree__level2` | `moduleLevel 2` (10 expands) | the macro, sub-module creation, level-1 outlines |
| `multilevel-tree__level3` | `moduleLevel 3` (11) | nested outlines, refused module `4` (t2) |
| `multilevel-tree__levelMixed` | `moduleLevel [1,3,2]` (7) | per-network k |
| `multilevel-tree__level2Colored` / `__coloredLevel2` | `moduleLevel 2` then colour matching / the reverse | expand then colour; expanding coloured modules |
| `multilevel-tree__level3Geometry` | CORE `geometry` + `moduleLevel 3` | margin cap with deep `differenceIndex` |
| `multilevel-tree__level3Justify40` | `flowThreshold 0.4`, justify, `moduleLevel 3` | threshold moves between expands, the re-check |
| `multilevel-tree__level2SortNodeId` | `sortModulesBy "nodeId"`, `moduleLevel 2` | summed parent keys |
| `multilevel-tree__level3Regroup` | `moduleLevel 3`, `regroup {1, "1:1:1"}` | level-3 regroup |
| `debug5-stree__level3` | `moduleLevel 3` (4) | the trailing-`:` leaves stop at level 2 (E1, WP3; was 8 ops with leaf modules), insignificant groups, equal-flow ties |
| `fuzz1347__level4` | fuzz1347 options, `moduleLevel 4` (6) | mixed depths, zero flows/margins |
| `mlayer-split__level2` | split, `moduleLevel 2` (8) | hierarchy on split layers |
| `prefix-tree__regroupPrefix` | `flowThreshold 0`; expand `{0,"1"}`, `{0,"10"}`, `{0,"12"}`, `{1,"1"}`; regroup `{0,"1:2"}` | regroup at level 1: only `1:*` collapses (pins E2; before WP3 the `isAncestor` prefix bug also collapsed 10 and 12 and re-created 11) |
| `prefix-tree__regroupPrefixDeep` | `flowThreshold 0`; `moduleLevel [3,1]` (23); regroup `{0,"1:1:1"}` | regroup at level 2: only `1:1:*` collapses (pins E2; before WP3 also `1:10:*`, `1:11:*`) |
| `multilevel-tree__move` | `moveModule` up: 0/0, 0/1, 1/0 (last op a move) | `moveItem`, `isCustomSorted`, `index` in drawn order (stale before fix round WP7/E7a), no `calcFlow` after a move |
| `multilevel-tree__moveSetOption` | the moves, `setOption height 400`, colour matching | custom order survives setters and colour ops |
| `multilevel-tree__moveExpand` | up 0/0, up 1/0, expand `{1,"1"}` | expand resets only its own network |
| `multilevel-tree__moveReset` | the moves, `resetLayout` | `resetLayout` |
| `multilevel-tree__moveDown` | `moveModule` down 2/3, then 2/2 | the down direction |
| `planted-ftree__moveHidden` | `flowThreshold 0.4`, up 0/2 (topmost visible), `result: false` | refused at the top visible module, order not frozen (fix round WP7/H1; it used to swap with an invisible module) |
| `multilevel-tree__visibleAndSubmodule` | network 0 = `multilevel_mixed_t0.json` (leaves below `1:1` at `moduleLevel` 2), `flowThreshold 0` | a visible `1` with its visible sub-module `1:1` (default order: `1:1` first): one outline encloses both, no throw (fix round WP7/E15a) |
| `multilevel-tree__visibleAndSubmoduleOrder` | the same, then `moduleOrder [[0, ["1", "1:1", "..."]]]` | `1` first: its leaf tree node becomes a non-leaf node, same outline (E15a) |

`science-stree__level2` (`moduleLevel 2`, 24 expands) is marked `large` (~1000 mostly invisible modules per network,
39 MB): it is not committed and only generated with `--large --out DIR`.

**Colour ops** (`colorOps`, `colorBy`, `metadata`)

| Scenario | Ops | Covers |
|---|---|---|
| `hlskip-tree__colorSelectedNodes` | `colorSelectedNodes` `[(0,"3"),(0,"1")]` red; `[(0,"3")]` red; `[(0,"1")]` default | propagation, same-colour re-paint, erase |
| `planted-ftree__colorSelectedNodes` | ids 1-12 from n0 `S[0]`; 9-14 from n2 `S[1]`; 9-12 from n1 default | nodes absent elsewhere, overrides |
| `planted-ftree__colorSelectedNodesMixed` | one call, ids 9-11 from n0 and n1, `S[0]` | double propagation |
| `states-tree__nameColorSelectedNodes` | identifier `"name"`, 5 names from n0, `S[2]` | duplicate identifiers (last-wins `getLeafNode`) |
| `planted-ftree__colorMatchingModules` | `{1/0, S[0]}`, `{0/1, S[1], side 1}`, `{2/1, S[2], side -1}` | both- and one-sided chains |
| `hlskip-tree__colorMatchingModulesSingle` / `__colorMatchingModulesThrough` | `{1/1}` / `{2/1}`, red | chain on / through a single-leaf module (continues since WP5, E4) |
| `planted-ftree__colorModuleIdsSingle`, `hlskip-tree__colorModuleIdsSingle` | `colorModuleIds {0/1}` | source module id (stale object before WP5; the id was the same, so the fixture did not change) |
| `planted-ftree__colorNodesInModule`, `hlskip-tree__colorNodesInModuleSingle` | `colorNodesInModule` | propagation from a single-leaf module (none before WP5, E4) |
| `planted-ftree__defaultColorChange` | `setDefaultHighlightColor #ff0000`, `colorModule {0/0, #ff0000}` | the new default maps to -1 |
| `states-tree__colorByPhysicalId`, `mlayer-unsplit__colorByPhysicalId` | `colorByPhysicalId` | several states per physical id |
| `hlskip-tree__colorByPhysicalId` | `colorByPhysicalId` twice | every visible leaf coloured (before WP5 the walk skip left node 4 at -1 in t0, t1), non-clearing re-run |
| `planted-ftree__colorByLayerNoop` | `colorModule {0/0, red}`, `colorByLayer` | no layer ids: colours kept |
| `mlayer-unsplit__colorByLayer` | `colorByLayer` | 4 layers, 4 colours |
| `planted-ftree__categorical` | metadata `c` = a/b/c by `id % 3`, `7` if `id % 11 == 0`, missing if `id % 13 == 0`; `colorCategoricalMetadata("c", [b S0, a S1, zz S2, c default])` | index = map order, unused category, non-string skip |
| `planted-ftree__categoricalNoMetaFirst` | same, network 1's first leaf (tree order) has metadata `null` | `haveMetadata` network skip until fix round WP6; since E12 some leaf with metadata suffices, so network 1 is coloured |
| `hlskip-tree__categoricalSkip` | `hl` = a for ids 3, 4, b for id 1; `[a red, b blue]` | the highlight path (no skip since WP5, E4) |
| `planted-ftree__realMetadata` | `x = id / max id`; 4 equal bins `S[0..3]` | `x == 1` uncoloured until fix round WP6; since S6 the last bin includes `x1` |
| `planted-ftree__arrayMetadata` | metadata is a JSON array by `id % 5`: `null`, `["a"]`, `["b","b"]`, `[]`, `["a","b","c"]`; `colorCategoricalMetadata("0")` | `name in array` reads index keys; the first leaf's `null` skipped its whole network until fix round WP6 (E12) |
| `planted-ftree__arrayLength` | same arrays; `colorRealMetadata("length")`, bins `[k, k+1)` | an array's `length` is a number (`[]` gives 0); the first leaf's `null` skipped its whole network until fix round WP6 (E12) |
| `planted-ftree__realIntervals` | same `x`; breaks 0.25/0.5/0.75, colours `[S0, default, S1, S2]`, centres `[0.875, 0.125]` | registration order |

**Highlight** (`highlight`, `metadata`, `labelNameHighlight`): the `highlight` macro of `design.md`'s `highlight=`.

| Scenario | Ops | Covers |
|---|---|---|
| `planted-ftree__highlight` | labels alpha = ids 5-20, beta = 40-55, gamma = 85-100 + 121-125, `S[0..2]` | real data, label-name indices |
| `planted-ftree__highlightSortHighlightIndex` | same, `sortModulesBy "highlightIndex"` | |
| `planted-ftree-single__highlight` | same, one network | |
| `planted-ftree__highlightThenClear` | same, then `clearColors` | registry reset |
| `science-stree__nameHighlight` | identifier `"name"`, 5 + 5 journals | many invisible modules, aggregated names |
| `debug5-stree__expandHighlight` | expand 0/0, 1/0, labels A = 1, 82, 144, B = 171, 179 | insignificant highlighted groups |
| `multilevel-tree__expandThenHighlight` / `__highlightThenExpand` | expand 0/0 and labels x = 1-20, y = 50-70, both orders | op order matters |
| `multilevel-tree__level2Highlight` | `moduleLevel 2`, then the labels | the `layout(module_level=2, highlight=...)` path |

**IO** (`json`, `multilayerSplit`)

| Scenario | Files / ops | Covers |
|---|---|---|
| `planted-json__default` / `__colored` | `planted_t{0,1,2}.json` | JSON reader, array paths, JSON `modules` enter/exit flow |
| `states-json__default` / `__name` | `states_t{0,1}.json` | `stateId` identifiers, duplicate names |
| `mixed-json-tree__default` | `planted_t0.json`, `planted_t1.tree`, `planted_t2.ftree` | array and string paths side by side |
| `mlayer-split__default` / `__name` | split `mlayer_states.tree` | layer order 1-4 (input 3,1,4,2); `name` is ignored after a split |
| `mlayer-split__colorModuleIds` / `__colored` / `__flowThreshold40` | split + op/option | multilayer branch of `colorModuleIds`, similarity across layers, thin layers |
| `mlayer-split-json__colorModuleIds` | split `mlayer_states.json` | JSON multilayer split |
| `mlayer-split-twice__colorModuleIds` | `mlayer_states.tree` twice, both split (ids `mlayer_states`, `mlayer_states_2`) | distinct `originalId`s: the per-network branch, as in the web app with two loaded files |
| `mlayer-split-flat__colorModuleIds` | split + `mlayer_flat.tree` | non-multilayer branch, streamlines to the flat network |
| `mlayer-named-json__default` | split `mlayer_named.json` | layer names (`Alpha`, `Layer 2`, `Gamma`, `Layer 4`) |

Not generated: `jsoncolors__*` (JSON `colors` / `checkColors`, an open v2-io question), `setSelectedScheme`
scenarios (the harness supports the op; Python has only C3 Sinebow), and the saved web-app diagram JSON (v3).

Coloring note: the colored fixtures use the **color-after-build** path
(`Module.setColor` -> `LeafNode.update()` = swap-remove + re-add, see
`docs/dev/port-notes/layout.md` §7). To match them, the Python color ops must
mirror those mutation-order effects. Build-time `highlightIndex` gives different
tie orders. `states-tree__name*` has colliding identifiers: all states of one
physical node share a name. `identifiersUnique` is false there.

## v3 scenarios (`tests/fixtures/v3/<name>.json`, 73 files)

Spec: [`docs/dev/port-notes/v3-webapp-json.md`](../../docs/dev/port-notes/v3-webapp-json.md) §8. The v3 fixtures live in a
subdirectory so that the v1/v2 parametrization (`tests/conftest.py`: `FIXTURES_DIR.glob("*.json")`, not recursive)
does not pick them up; a v3 test module globs `tests/fixtures/v3/*.json` itself. Each one is a normal fixture (same
format, `formatVersion` 1, every v3 field written only when used) of the scenario's final state, plus the v3 blocks
below. Scenarios built from a v1/v2 scenario copy it (files, options, ops, metadata) and are named
`<base scenario>__<suffix>`. The `large` ones are generated only with `--large --out DIR` and land in `DIR/v3/`.

### What the harness runs (all TS code is the real code, read-only)

- The 2019 saved-diagram format (the web app's dead writer and the package's dead loader, the `saved`/`reload` blocks, the
  `savedDiagram`/`restoreState` scenario fields and the `webapp-science*` scenarios) was removed in the 0.5 fix round
  (docs/dev/fix-plan.md WP2); see the erratum in v3-webapp-json.md.
- **Web-app files writer (until WP9; replaced by `serializeDiagram`, see below)** (harness code, the v3-webapp-json §4/§7.2 reference writer; not app code): one
  Infomap-JSON text per network, in diagram order, named `` `${i padded to 2}_${network.name with [^A-Za-z0-9._-]
  -> _}.json` `` (e.g. `00_multilevel_t0.tree.json`), text = `JSON.stringify(value, null, 2)` without a trailing
  newline. Top level, in order: `name` (diagram network name), `codelength` (the file's, only if defined),
  `colors` (the whole `store.highlightColors`, also when empty), `nodes`. No top-level `id`, `layerId` or
  `originalId` (Q8). Nodes in **input order**: the leaf `Network.addNodes` built from each input node, by identity
  (the harness wraps `addNodes`, read-only), so duplicate identifiers are handled. Node keys, in order: `path` =
  `leaf.treePath.toString()` (always a string; `;` markers and a trailing `:` removed, arrays joined with `:`),
  `flow` = the raw leaf flow (`_flow`, not the hidden-bipartite 0), `name` (only if defined), `id` (`nodeId`),
  `stateId` and `layerId` (only if not null), `identifier`, `highlightIndex`, `moduleLevel`, `metadata` (only if a
  non-empty object).
- **Web-app files load** = the app's own path: `parseAcceptedFiles(files, [], formats, "id")` (stored identifiers
  win), ids = file name without `.json` (the app's are random), `setNetworks` on a fresh store with the scenario's
  ctor options. The harness loads the files once as loose `.json` Files and once as one zip (JSZip from the TS
  package, the `application/zip` branch of `readAcceptedFiles`; the Node `FileReader` shim gained
  `readAsArrayBuffer` for it) and fails unless both give the same geometry, palette and warnings.
- Cross-checks as for v1/v2 (instrumented vs plain run), plus: the plain run must save the same files.

**Fix round WP9 (saved diagrams, docs/dev/saveload-plan.md):** the round trips now use the engine's own writer and
loader (`serializeDiagram` with `generator`/`saveId` pinned to `"fixture"`, `parseAcceptedFiles`, `openNetworks` on a
default store); the harness-local `webAppFiles` writer, its `inputLeaves` wrapper and the id rewrite are gone. The
blocks are `savedStore` (the saved store options and scheme; Python sets the display options and
`showBipartiteNodes` from it before it writes), `savedFiles`, `savedReload` (with `restored`: options, scheme and
`openWarnings`) and, for a `restore` scenario, `savedReloadFiles` (the edited files that were opened; harness
`editSavedFiles`). The "lost" notes in the table below are history: names, order, insignificance (`;` path strings)
and options now survive, and the reload equals the original up to float summation order.

### Scenarios

| Fixture(s) | Input | What it pins |
|---|---|---|
| `multilevel-tree__{default,colored,expand,expandColored,expandRegroup,moveDown}__roundTrip` | `multilevel_t*.tree` | `webAppFiles` texts; colour ops: `webAppReload` keeps the palette (<= 1.1e-13); `moveDown`: custom order lost (`1 4 2 3` -> `1 2 3 4`) |
| `multilevel-tree__colored__names__roundTrip` | same | `setNetworkName` (kept in the files) + `setModuleName` (`label.customName` lost) |
| `debug5-stree__colored__roundTrip` | `debug5_*.stree` | `;` paths below the top level, written cleaned |
| `insig-stree__{colored,expandColored}__roundTrip` | `insig_t*.stree` | `webAppReload`: insignificance lost (no insignificant groups, group order and link count change) |
| `planted-json__colored__roundTrip` | `planted_t*.json` | JSON input with array paths, written as `:` strings |
| `states-ftree__colored__roundTrip`, `states-ftree__colored__name__roundTrip` | `states_t*.ftree` | state networks; with `identifier: "name"` (duplicate identifiers) the reload changes the streamlines (9 -> 8 links; the colour-after-build re-attachment is not reproduced by a fresh build) |
| `mlayer-split__colored__roundTrip` | `mlayer_states.tree`, split | split layers (`layerId` in the files) |
| `planted-ftree__highlight__roundTrip` | `planted_t*.ftree` + `highlight` macro | palette from `highlight` colours; metadata in the files (incl. the internal highlight key) |
| `jscolors-abc__default__roundTrip` | `jscolors_*.json` | input `colors` survive the files route |
| `science-stree__nameColored__roundTrip` (`large`, 23 MB) | `science*_2y.stree` | large round trip through the saved files |
| `multilevel-tree__options__roundTrip` (WP9) | `multilevel_t*.tree` | every saved option changed, `colorScheme` `Paired`, colouring, expand, `moduleOrder` (with `...`), module and network names: all restored |
| `multilevel-tree__restore{Shuffled,Partial,MixedSaves,FormatVersion2,BadBlock,BadOptions}__roundTrip` (WP9) | same | the saved files edited before the open: reversed (sorted back), the last file missing, another save id, `formatVersion` 2, `formatVersion` `"1"`, invalid options and an unknown scheme; the warnings and the partial restores |
| `multilevel-tree__flowThreshold40__orderHidden__roundTrip` (WP9) | same | `moduleOrder` lists the hidden modules too |
| `bipartite-json__hidden__roundTrip` (WP9) | `bipartite_t*.json` (hand-written) | `showBipartiteNodes: false` applied at build (E19) and restored |
| `planted-json__default__passthrough__roundTrip` (WP9) | `planted_t*.json` | Infomap's `version`, `args`, `directed`, `modules`, ... passed through |
| `mlayer-named-json__default__roundTrip` (WP9) | `mlayer_named.json`, split | named split layers; `layers` passed through |
| `jscolors-a__default` | `jscolors_a.json` | `colors` list: palette `["#f00", "#0f0"]`; index 5 out of range (black) |
| `jscolors-b__default` | `jscolors_b.json` | `colors: true`: palette `["#0f0", "#00f"]`, node indices 0, 1, 4 (kept), 0, -1 |
| `jscolors-abc__default` | a, b, c | b's `#0f0` nodes get index 1 (the dummy-0 bug gave 0 = `#f00` until fix round WP6, S7); c ignored; palette `["#f00", "#0f0", "#00f"]` |
| `jscolors-abc__colored` | a, b, c | `colorMatchingModulesInAllNetworks` replaces the input palette |
| `multilevel-tree__scheme{Paired,Set1,Tableau20,Mural,C3Turbo,Rainbow,Greys}` | `multilevel_t*.tree` | ctor `colorScheme` (recorded in `inputs.colorScheme`; `inputs.options` lists layout options only) + `colorMatchingModulesInAllNetworks`: hex vs `rgb()` strings, C3/Rainbow duplicates, Paired `["#a6cee3", "#b2df8a", "#33a02c"]` (index 1 skipped, colors-render §6.1) |
| `multilevel-tree__tone{Vivid,...,Muted}` (#47) | `multilevel_t*.tree` | ctor `colorTone` (C3 Sinebow in every c3 tone; `inputs.colorTone`) + colorMatching |
| `multilevel-tree__schemeC3Oklch*`, `__schemeC3Turbodark*`, `__schemeC3Viridissoft*`, `__schemeC3Rainbowvivid*` (#47) | same | ctor `colorScheme`/`colorTone`/`colorOffset` (`inputs.colorOffset`; 0, -90, 1000.5, 30, -1e-7, 359.99) + colorMatching |
| `multilevel-tree__toneSetters` (#47) | same | `setSelectedTone`, `setSelectedOffset`, colorModuleIds, `setSelectedScheme` (resets the offset, keeps the tone), colorMatching |
| `multilevel-tree__hierarchy{,Level2,Expand,OklchPastel,ViridisDeep,Spectral,Paired}`, `multilevel-tree__flowThreshold40__hierarchyHidden`, `{debug5,insig}-stree__hierarchy` (#47) | `multilevel_t*.tree`, `debug5_*.stree`, `insig_t*.stree` | `colorModuleHierarchyInAllNetworks` (c3 `hierarchy()`): top modules, after `moduleLevel` 2, after expands and a regroup, with hidden modules, C3 Oklch/interpolated hue sources in a tone and offset, a list scheme as seeds, `;` paths |
| `wide-tree__hierarchyLevel2` | `wide_t0.tree` (hand-made: module 1 with 119 sub-modules) | hierarchy colouring of a wide module; c3-colors 2.0.1 swaps some sibling colours, so `tests/test_v3_fixtures.py` marks it strict xfail (`C3_WIDE_XFAIL`) until a c3-colors release fixes it |
| `nanpath-json__hierarchyLevel2` | `nanpath_t0.json` (string paths `1:x:*`, `2:y:1`, `z:*`) | non-numeric path parts become NaN; TS c3 keys modules by the joined path, and the port's one shared NaN keeps its tuple keys equal |
| `multilevel-tree__tone{Offset,Default}__roundTrip` (#57) | `multilevel_t*.tree` | `colorTone`/`colorOffset` written (always; `"strong"`/null by default) and restored |
| `multilevel-tree__toneRestore{BadColor,NullColor,LegacyColor,OddColor,HugeOffset}__roundTrip` (#57) | same | the saved files edited before the open: unknown tone + offset `"90"` (two warnings), null tone (warning) + null offset, no tone/offset (a #55 save), scheme `"toString"` + tone `["strong"]` + offset literal `1e400` (three warnings), offset literal `-300000000000000000123` (a finite double, no warning) |
| `multilevel-tree__toneReload{SameScheme,OtherScheme,Override}__roundTrip` (#57) | same | opened by a store with its own scheme, tone and offset (`reloadStore`): a save without tone/offset keeps them for the same scheme, resets the offset for another scheme; a full save overrides them |
| `multilevel-tree__schemeSwitch` | same | colorMatching (C3 Sinebow), `setSelectedScheme("Set1")` (no recolour), `colorModuleIdsInAllNetworks` (clears first since fix round WP6, S3: palette `#e41a1c`, `#377eb8`, `#4daf4a`, `#984ea3`; before, it appended them to the Sinebow colours) |

Python replay notes: `setNetworkName {networkIndex, name}` and `setModuleName {networkIndex, moduleIndex|moduleId,
name}` are new ops (`store.setNetworkName(network.networkId, name)`, `store.setModuleName(module, name)`). The
parity targets are "Python write == `savedFiles` text" (same store state) and "Python open of that text ==
`savedReload`". Since WP9 "reload == original" holds too (up to float summation order; `tests/test_saveload.py`).

## v4 scenarios (`tests/fixtures/v4/<name>.json`, 15 files)

Spec: [`docs/dev/port-notes/v4-names-order.md`](../../docs/dev/port-notes/v4-names-order.md). Defined in
`scenarios-v4.ts` (`v3: true, v4: true`: the v3 dump and round-trip blocks, written to `DIR/v4/`). Every scenario
derives from a v1/v2 one (its ops first) and keeps `layout()`'s step order, so `tests/test_v4_fixtures.py`
reproduces each one through public `layout()`/`save_diagram()` arguments. The exception is
`hlskip-tree__default__namesOrderRecolor` (colour ops after order and names, `NOT_LAYOUT_ORDER` in the test), which is
replayed and dumped only.

- **Macro `moduleOrder {order: [[networkIndex, ids], ...]}`** (`runModuleOrder`): ids bottom to top, at most one
  `"..."` for the unlisted visible modules; networks in ascending index. The networks whose target visible order
  differs from the current one get it in one `store.setModuleOrder` (fix round WP7/B1: one layout without `calcFlow`,
  bit-identical to the former per-swap `moveSelectedModule("down")` sequence). Recorded as one
  `{op: "setModuleOrder", order: [[networkIndex, [moduleId, ...]], ...]}` op (none if nothing changes); the macro in
  `inputs.macros`.
| Fixture | What it pins |
|---|---|
| `multilevel-tree__default__{order,orderReverse,orderNoop}` | listed bottom, `...` on top, full reversal (networks given out of order), an order that needs no moves (no custom flag) |
| `multilevel-tree__colored__order`, `__sortNodes__order`, `planted-ftree__coloredSortHighlightIndex__order` | order after colouring; `sortModulesBy` nodes / highlightIndex set the start |
| `planted-ftree__flowThreshold40__orderHidden` | hidden modules after the visible ones are never moved or passed |
| `multilevel-tree__level2__order`, `__level2Highlight__order` | sub-module ids after `moduleLevel 2` (path grouping broken), with `highlight` |
| `multilevel-tree__colored__names` | `setModuleName` by id, a module renamed twice (`label.customName`) |
| `multilevel-tree__colored__namesOrder__roundTrip`, `__level2__names__roundTrip`, `planted-ftree__flowThreshold40__namesHidden__roundTrip` | names of sub-modules and a hidden module; `webAppReload` drops names and order |
| `hlskip-tree__default__namesOrderRecolor` | fix round WP5 (E4, plan finding 10): a single-leaf module moved up and named, then recoloured with `colorModule`, keeps its name and position |
| `multilevel-tree__colored__order__roundTrip` | v4 shim without names writes `moduleNames: []`; custom order lost in both reloads |

## JSON format (formatVersion 1)

v2 added fields only (each written only when used), so v1 fixtures are unchanged and the version stays 1. They are
marked *(v2)* below.

Conventions:

- Numbers are JS doubles in shortest round-trip form (`JSON.stringify`), at full
  precision with no rounding. Integers are written without `.0`; `json.load`
  gives `int`, so compare numerically.
- Non-finite numbers are written as the bare tokens `Infinity`, `-Infinity` and
  `NaN`. This is not strict JSON, but Python's `json.load` reads them natively.
  `-0` is written as `0`.
- Coordinates are SVG/TS coordinates: y points down, and the network spans
  `[0, height]`. Stacking starts at `y = height` (bottom) and goes up, so the
  first sorted module is at the bottom. Keep these numbers and invert the axis in
  the renderer.
- Missing values are `null`. Objects are never omitted.

### Top level

| Key | Type | Meaning |
|---|---|---|
| `formatVersion` | int | 1 |
| `features` *(v2)* | [str] | sorted v2 feature tags, only on v2 fixtures: `hierarchy` (expand/regroup/`moduleLevel`), `move` (`moveModule`/`setModuleOrder`/`resetLayout`), `moduleId` (ops address a module only by id), `colorOps`, `colorBy`, `metadata`, `highlight`, `labelNameHighlight`, `multilayerSplit`, `json`; *(v3)* `names` (`setNetworkName`/`setModuleName`), and on v3 fixtures only `roundTrip`, `colorScheme` (ctor option), `jsColors` (an input file has a top-level `colors` key). The `webAppReload` blocks carry their own tags (`json`, `jsColors`). |
| `scenario` | str | `<group>__<variant>` (= file stem) |
| `group`, `variant`, `description` | str | |
| `inputs` | object | see below |
| `diagram` | object | global layout values |
| `highlightColors` | [str] | `store.highlightColors` at the end. `highlightIndex` i maps to `highlightColors[i]`; `setNetworks` resets it to `[]`. |
| `defaultHighlightColor` | str | `#b6b69f` (color for `highlightIndex == -1`) |
| `warnings` | [str] | captured `console.warn` messages (empty in all current fixtures) |
| `networks` | [object] | in diagram order (left to right) |
| `savedStore` *(v3)* | object | `roundTrip` only: `{options, colorScheme, colorTone, colorOffset}` of the store that was saved (`getOptions()`) |
| `reloadStore` *(v3)* | object | `reloadStore` scenarios only: the ctor options (`colorScheme`, `colorTone`, `colorOffset`) of the store that opens the saved files |
| `savedFiles` *(v3)* | [{name, text}] | `roundTrip` only: `serializeDiagram` output (`generator`/`saveId` `"fixture"`), in diagram order |
| `savedReloadFiles` *(v3)* | [{name, text}] | `restore` scenarios only: the edited files that were opened |
| `savedReload` *(v3)* | object | `roundTrip` only: a complete fixture of the files opened with `parseAcceptedFiles` + `openNetworks` on a default store (or `reloadStore`); `inputs.files` = the file names, network ids = names without `.json`; `restored` = `{options, colorScheme, colorTone, colorOffset, schemeSha256, openWarnings}` (`schemeSha256`: sha256 of `JSON.stringify(store.selectedScheme)`) |

### `inputs`

| Key | Meaning |
|---|---|
| `files` | dataset paths relative to `tests/`, in network order |
| `formats` | parsed format per file (`tree`, `ftree`, `stree`, `clu`) |
| `networkIds` | network ids used, which are the file stems (a repeated stem gets `_<k>`; they appear inside module, group and streamline ids) |
| `networkNames` | network names, which are the file basenames |
| `identifier` | `"id"` (`stateId ?? id`) or `"name"` (`name ?? stateId ?? id`). `.clu` always uses the state/node id. See `parsers/set-identifiers.ts`. |
| `options` | the complete layout options the store passed to the last `Diagram.updateLayout`: `height`, `moduleWidth`, `streamlineFraction`, `streamlineThreshold`, `flowThreshold`, `marginExponent`, `zeroMargins`, `verticalAlign`, `moduleSize`, `sortModulesBy` |
| `initialOptions` | only when a `setOption` op changed them: the options the store was created with (replay starts from these) |
| `labelOptions` | `fontSize` 8, `adaptiveFontSize` false, `multilineModuleNames` true, `aggregateStateNames` true, `showModuleNames` true (store defaults used for labels) |
| `colorScheme` | `"C3 Sinebow"` (v3: the scheme at the end) |
| `colorTone`, `colorOffset` | *(v3, #47)* only when the scenario sets them: the ctor's `colorTone`/`colorOffset` |
| `operations` | executed store calls in order: `{"op": "setNetworks"}` followed by the scenario ops (`colorMatchingModulesInAllNetworks`, `colorModuleIdsInAllNetworks`, `colorNodesInModulesInAllNetworks`, `colorModule {networkIndex, moduleIndex, color}`, `expand`/`regroup {networkIndex, moduleIndex}`, `clearColors`, `setOption {key, value}` = the store setter `set<Key>(value)`). v2 ops are listed below. |
| `macros` *(v2)* | `[{atOperation, numOperations, op}]`: a harness macro (`moduleLevel`, `highlight`, v4 `moduleOrder`) and the slice `operations[atOperation : atOperation + numOperations]` of concrete ops it issued |
| `split`, `networkSources` *(v2)* | the split input-file indices, and per final network its index into `files`. With `split`, `formats`/`networkIds`/`networkNames` are per final network and no longer align with `files`. Replay: read each file, split the listed ones (in increasing index), flatten in order, then pin ids and names from `inputs`. |
| `labelNameHighlight` *(v2)* | `true` when `label.names[*]`/`namesSingleLine[*]` carry `highlightIndex` and `insignificant` |
| `nodeMetadata` *(v2)* | per input file (aligned with `files` and the parsed `file.nodes` order), the `metadata` object or `null` assigned to each node before split and `setNetworks`. The `highlight` macro writes `{"\u0000alluvial.highlight": "<label index>"}` or `{}`. |

v2 ops in `operations` (store method in parentheses; `moduleIndex` may be replaced by `moduleId`, resolved with
`network.getModule(moduleId)` at op time):

| Op | Store call |
|---|---|
| `expand`/`regroup {networkIndex, moduleIndex \| moduleId}` | `store.expand(m)` / `store.regroup(m)`. Issued by `moduleLevel` with both `moduleIndex` and `moduleId`. |
| `moveModule {networkIndex, moduleIndex \| moduleId, direction, result?}` | `setSelectedModule(m)`, `moveSelectedModule(direction)` (layout without `calcFlow`); a scenario's `result: false` expects the refusal |
| `setModuleOrder {order: [[networkIndex, [moduleId, ...]], ...]}` | `setModuleOrder([[network, modules], ...])` (fix round WP7/B1; issued by the `moduleOrder` macro) |
| `resetLayout` | `resetLayout()` |
| `colorSelectedNodes {nodes: [{networkIndex, identifier}], color}` | `colorSelectedNodes(nodes, color)`, nodes = `getLeafNode(identifier)` |
| `colorMatchingModules {networkIndex, moduleIndex, color, side?}` | `colorMatchingModules(m, color, side)` (`side` -1 left, 1 right) |
| `colorModuleIds`/`colorNodesInModule {networkIndex, moduleIndex, color}` | `colorModuleIds(m, color)` / `colorNodesInModule(m, color)` |
| `colorByLayer`, `colorByPhysicalId` | the store methods |
| `colorCategoricalMetadata {name, colors: [[value, colour], ...]}` | `colorCategoricalMetadata(name, new Map(colors))` |
| `colorRealMetadata {name, bins: [{x0, x1, color}]}` | `colorRealMetadata(name, bins)` |
| `colorRealIntervals {name, breaks, colors, centers}` | `colorRealIntervals(name, null, v => colors[#breaks <= v], centers)` |
| `setDefaultHighlightColor {color}`, `setSelectedScheme {name}` | the store setters |

Harness macros (only in `macros`): `moduleLevel {levels}` (an int, or one per network) runs v2-hierarchy §10.1: per
network left to right, rounds of "expand every visible module with `moduleLevel < k` whose leaves are all at least two
levels deeper, in the `children` order at the start of the round, re-checked just before each expand", until a round
finds none. `highlight {groups: [[label, identifiers]], colors}` sets `nodeMetadata` as above and runs
`colorCategoricalMetadata("\u0000alluvial.highlight", Map(String(k) -> colors[k]))`.

### `diagram`

| Key | Meaning |
|---|---|
| `x`, `y`, `width`, `height` | diagram rect. `width = totalWidth`; x and y are always 0. |
| `flow` | always 0: `calcFlow` never sets the root's flow |
| `numNetworks` | |
| `maxNetworkFlow` | `max(network.flow)`, the size normaliser for `moduleSize: "flow"` |
| `streamlineWidth`, `networkWidth`, `totalWidth` | `streamlineFraction*moduleWidth`, `moduleWidth+streamlineWidth`, `networkWidth*numNetworks - streamlineWidth` |
| `totalMargins` | per network, the sum of pass-1 (uncapped) margins of visible modules, summed in pass-1 order *(replicated)* |
| `maxTotalMargin` | `max(totalMargins)` *(replicated)* |
| `marginFractionOfHeight`, `maxMarginFractionOfHeight` | `maxTotalMargin/height` and `zeroMargins ? 0 : 0.2` |
| `marginCapped` | true if the margin cap branch ran |
| `moduleMarginScale`, `scaledTotalMargin` | `(0.2*height)/maxTotalMargin` and `maxTotalMargin*moduleMarginScale`, or `null` when not capped |
| `usableHeight` | `height - maxTotalMargin`, or `height - scaledTotalMargin` when capped *(replicated, verified exactly)* |
| `visibleFlows`, `visibleModuleCounts` | per network: the sum of pass-1 `size(module)` and the number of visible modules (used by justify) |
| `updateLayoutCalls` | number of `Diagram.updateLayout` calls in the scenario. The snapshots are from the last one. |
| `usableHeightCheckedModules` | how many modules passed the exact height assertion |

### `networks[i]`

| Key | Meaning |
|---|---|
| `networkId`, `name`, `index` | |
| `file` | `{path, format, numTopModules, numLevels, isStateNetwork, directed, codelength, numNodes}` from the parsed `NetworkFile`; with `split` *(v2)* also `layerId` and `originalId` (both `null` for a network that was not split), and `path` is the source file |
| `x`, `y`, `width`, `height` | network rect: `{x, y: 0, width: moduleWidth, height}`. `x` is built by repeated `x += networkWidth` from 0 (`Diagram.ts:365`), not `i*networkWidth`. The two agree for the integer widths in these fixtures, but can differ in the last ulp otherwise. |
| `flow`, `numLeafNodes` | after `calcFlow` |
| `moduleFlowThreshold` | `network.flowThreshold`, the module-flow cut set by `updateFlowThreshold(flowThreshold)` (`Network.ts:250-266`). Can be `Infinity`. |
| `isCustomSorted`, `isHigherOrder` | `isHigherOrder` is `null` when the TS getter throws (a network whose leaves were all removed by colour ops with duplicate identifiers) |
| `namePosition` | `{x, y}` of the network label (`Network.ts:201-206`: `x + width/2`, `height + 20`). React draws it with `textAnchor="middle"` and `dy=networkFontSize` (10). |
| `totalMargin`, `visibleFlow`, `numVisibleModules` | this network's entries of the diagram arrays *(replicated)* |
| `numModules` | |
| `modules` | **all** modules in final `network.children` order: visible modules sorted first, then invisible ones in their existing order. This order is the ordering result. |
| `numLinksAboveZero` | `getLinks(0).length` |
| `links` | `network.getLinks(streamlineThreshold)` in draw order. Links go to the network on the right, so the last network has `[]`. |
| `hierarchy` | `network.hierarchicalChildren` (BFS, used by React when `hierarchicalModules != "none"`). Items: `{type: "module", moduleId}` or `{type: "tree", path, moduleLevel, isLeaf, maxModuleLevel, x, y, width, height}`. Leaf tree nodes are not listed. The `tree` items are the hierarchy outline rects (v2: `NetworkGeometry.outlines`); the list order is the web draw order. |
| `identifiersUnique` | false if two leaves share an identifier |
| `leafColumns` | `["identifier","nodeId","stateId","moduleId","moduleLevel","highlightIndex","insignificant"]` |
| `leaves` | one row per leaf node (visited via `network.leafNodes()`), sorted by `(stateId ?? nodeId, identifier)`. This is the per-network identifier -> highlightIndex map after all operations. |

### `modules[j]`

| Key | Meaning |
|---|---|
| `moduleId`, `id`, `path` | `"3"` / `"1:2"`, `"<networkId>_module<moduleId>"`, `[3]` |
| `moduleLevel`, `maxModuleLevel` | |
| `index` | `module.index` (pass-1 sort index for visible modules; creation index otherwise) |
| `flow`, `numLeafNodes`, `enterFlow`, `exitFlow` | `enterFlow`/`exitFlow` come from `.ftree` module headers, else 0 |
| `meanNodeId` | `Module.meanNodeId`: mean leaf `nodeId` (physical id for state nodes), or -1 without leaves. It is the module order key for `sortModulesBy: "nodeId"` (descending, like the other keys). |
| `visible` | `flow >= network.flowThreshold && flow > 0` |
| `highlightIndex` | the module's largest group's highlightIndex |
| `margin` | final margin below this module (after cap/justify). The last visible module has 0. |
| `x`, `y`, `width`, `height` | final rect from pass 2. Invisible modules keep whatever the engine holds, which is zeros for never-laid-out modules. |
| `pass1` | `{margin, index, x, y, width, height}` at the end of pass 1 (uncapped margin, `height`-based sizes), or `null` for invisible modules |
| `label.shown` | `visible && showModuleNames && textAnchor != null`. Only the first and last networks get name labels. |
| `label.textAnchor` | `"end"` (first network), `"start"` (last network), or `null` |
| `label.namePosition`, `label.idPosition` | `{x, y}` from `Module.ts:82-114` |
| `label.customName` | `module.name` (always `""` here) |
| `label.maxLines` | `ceil(height/(fontSize*1.8))`, decremented by 1 if even; 0 means no label |
| `label.names` | `getLargestLeafNodes(maxLines, aggregateStateNames)` in engine order, as `[{name, nodeId, stateId, flow}]`. With aggregation, `flow` is summed per physical node. React shows `names[mid-1..0]` upward from the centre line and `names[mid..]` downward, where `mid = ceil(len/2)`. |
| `label.namesSingleLine` | `getLargestLeafNodes(5, aggregateStateNames)` (text used when `multilineModuleNames` is false) |
| `label.names[*].highlightIndex`, `.insignificant` *(v2, `labelNameHighlight` only)* | the name's colour index, and `insignificant`, which is `null` for aggregated copies (`{...leaf}` has no getter) |
| `groups` | in final `module.children` order: not insignificant first, then by highlightIndex |

### `groups[k]`

`{id, highlightIndex, insignificant, flow, numLeafNodes, x, y, width, height, pass1, branches}`.
`pass1` is the pass-1 rect, or `null`. `branches` is `[left, right]`, each
`{side, flow, numLeafNodes, x, y, width, height, streamlineNodes}` (`numLeafNodes` sizes the branch
when `moduleSize` is `"nodes"`). `streamlineNodes` is in
final `branch.children` order, which is the stable sort by `sortKey` applied to
insertion/swap-remove order. Each streamline node is:

| Key | Meaning |
|---|---|
| `id` | `currentId`: `"<source>--<target>"`, or just `"<source>"` when dangling. `source` = `<networkId>_module<moduleId>_group[i]<highlightIndex>_<side>` |
| `sourceId`, `targetId`, `dangling` | `targetId` is `null` when dangling |
| `flow`, `numLeafNodes` | |
| `x`, `y`, `width`, `height` | final rect |
| `sortKey` | `oppositeStreamlinePosition` just before pass 2: `-(opposite group's pass-1 y)`, or `-Infinity` when there is no visible opposite |
| `linked` | has a `StreamlineLink` |
| `opposite` | `{networkId, id, moduleId}` of the linked streamline node, or `null` |

### `links[l]`

| Key | Meaning |
|---|---|
| `id` | `link.id` = the left streamline node's `currentId` |
| `left`, `right` | `{networkId, moduleId, groupHighlightIndex, groupInsignificant, streamlineNodeId}` |
| `x0`, `y0`, `h0` | left streamline node: `x + width`, `y`, `height` |
| `x1`, `y1`, `h1` | right streamline node: `x`, `y`, `height` |
| `avgHeight` | `(h0 + h1) / 2` (`getLinks` keeps links with `avgHeight > streamlineThreshold`) |
| `highlightIndex`, `leftHighlightIndex`, `rightHighlightIndex` | `max(left, right)`, plus the two group indices |
| `path` | the SVG path string from `StreamlineLink.ts:118-135`. First `y0 = y0 < 1e-6 ? 0 : y0` (same for `y1`), then `y2 = y0+h0`, `y3 = y1+h1`, `cpx = (x0+x1)/2`, and the string is `M x0,y2 C cpx,y2,cpx,y3,x1,y3 L x1,y1 C cpx,y1,cpx,y0,x0,y0 Z`, written without spaces. Numbers use JS `Number#toString`, which differs from Python `repr`: JS writes `5`, `1e-7`, `1e+21`, Python writes `5.0`, `1e-07`, `1e+21`. Compare numerically or port the JS formatting. |

Link order: `getLinks` sorts ascending by `highlightIndex`, then descending by
`avgHeight`. The input to that sort is the left network's visible modules in
`children` order, then groups, then right-branch streamline nodes. Links to
invisible right modules are skipped.

## Coverage notes

- The 20 % margin cap triggers in the `*__geometry*` fixtures whose networks have 3 or more visible modules,
  and in `*__height37`.
- Top-level insignificant groups occur only in `science-stree__*` (30 groups). Small insignificant
  groups occur only in `debug5-stree__expand`.
- Within a branch every streamline node points to a different opposite group, so sort-key ties are
  always `-Infinity` (dangling, or opposite module invisible). The TS comparator then returns
  `-Infinity - -Infinity = NaN`. V8's sort treats that as "not less", which is effectively equal (stable)
  in the binary-insertion path used for short arrays. Take the fixture order as authoritative. Ties occur
  in `science-stree__*` and the `flowThreshold40*` variants. A finite tie (two opposite groups at the same
  pass-1 y) occurs in `fuzz1347__ops`. NaN keys no longer occur: NaN flows are rejected at load (WP4).
- Multi-group modules (highlight groups): `planted-ftree__colorNodes` (up to 3 groups) and `science-stree__*`.
- v2: the visible-leaf-walk skip (v2-highlight §2.2) fires in `hlskip-tree__{colorByPhysicalId,categoricalSkip}`;
  the fixed `isAncestor` (E2, WP3) in `prefix-tree__regroupPrefix*`; stale `module.index` and `network.flow` summed before
  a move in `multilevel-tree__move`. Small insignificant groups also occur in `debug5-stree__{level3,expandHighlight}`.
  Hierarchy outline (`tree`) items occur in every `hierarchy` fixture except `multilevel-tree__expandRegroup`
  (regrouped back to level 1).
- `Infinity` module flow thresholds: `zeroflow-*` (a network with only zero flows).
- `name` equals `default` wherever names map 1:1 to ids. `states-tree__name*` has colliding identifiers,
  and `science-stree__name*` differs from `default`.

## Loading in Python

```python
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
fx = json.loads((FIXTURES / "planted-ftree__default.json").read_text())  # Infinity ok
data_paths = [Path(__file__).parent / p for p in fx["inputs"]["files"]]
```

v3 fixtures are in `tests/fixtures/v3/` (not in `ALL_SCENARIOS`); load them by path, e.g.
`load_fixture(FIXTURES_DIR / "v3" / "multilevel-tree__colored__roundTrip.json")`. `fx["reload"]` and
`fx["savedReload"]` are complete fixtures and can go through the same comparison helpers. Large v3 fixtures from
`generate.mjs --large --out DIR` are in `DIR/v3/`.
