# Save/load plan: one saved-diagram format for the web app and Python

Status: plan, written 2026-10-10 against TS HEAD `d0abf3b` and alluvial-py 0.4.0. Read-only investigation; nothing in
either repo was changed. Builds on [`port-notes/v3-webapp-json.md`](port-notes/v3-webapp-json.md) (which has the history and
verified behaviour of today's routes) and [`port-notes/v4-names-order.md`](port-notes/v4-names-order.md). Companion plans:
`fix-inventory.md` / `fix-plan.md` (module_order speed, quirks). Section 8 lists where this plan depends on them.

Paths: `P/` = `packages/alluvial-diagram/src/parsers/`, `A/` = `packages/alluvial-diagram/src/alluvial/`,
`S` = `packages/alluvial-diagram/src/store/DiagramStore.ts`, `W/` = `apps/web/src/` (all in the web repo);
`py/` = `src/alluvial/` in this repo.

---

## 0. Summary

- **The web app has no save today.** The Export section (`W/components/Sidebar/Export.tsx`) only has "Download SVG".
  `W/io/save-diagram.js` (`saveDiagram`, the 2019 format) is dead code: nothing imports it, and it throws on today's
  engine (`network.getModuleNames` was removed in 2022).
- **The web app loads only per-network files.** Accepted: `tree, ftree, stree, clu, json, net, zip`
  (`W/components/LoadNetworks/LoadNetworks.tsx:27-41`). A `.json` must be Infomap-JSON-shaped (top-level `nodes`);
  a 2019 saved diagram (top-level `networks`) is rejected (`invalid-format`). A `.zip` is unpacked and its entries
  parsed as loose files (`P/parse-files.ts:88-140`). The only way to get colours and expansion back today is a top-level
  `colors` palette plus per-node `highlightIndex`/`moduleLevel` (`S:180-210` `checkColors`, `A/LeafNode.ts:51-58`). That
  is what Python's `save_diagram(format="webapp")` writes.
- **Lost by every route today:** layout and display options, colour scheme name, module names, custom module order,
  stree insignificance, Infomap's own top-level data (`modules`, `layers`, `directed`, `bipartiteStartId`, `version`,
  ...) when Python re-writes a file. There is no version tag of our own.
- **Proposal:** one format, **"alluvial network files" v1**. It has one Infomap-JSON file per network, and the files are
  delivered loose or in a `.zip`. Each file is a superset of `infomap -o json` output: Infomap's keys are passed through,
  and the file adds `name`, `colors` and three node keys (`identifier`, `highlightIndex`, `moduleLevel`), all of which
  today's app already reads. Everything else goes in one namespaced block, `"alluvial": {"format": "alluvial-network",
  "formatVersion": 1, ...}`. That block holds the options, scheme, network position, module names and module order.
  The TS engine gets a writer (`serializeDiagram`) and a restorer (`DiagramStore.openNetworks`). The web app gets a
  "Download diagram (.zip)" button. Python drops the 2019 format entirely and writes and reads exactly the same files
  (byte-identical text apart from `generator`).
- **Proof:** the TS fixture harness calls the real TS writer and loader (no harness-local copies). Python asserts that
  its writer output equals the TS text byte for byte, and that Python's load of the TS files equals the TS reload
  bit for bit. Both together prove TS-save → Python-load and Python-save → TS-load.

---

## 1. Today's web app, exactly

### 1.1 Save / export

| Entry point | What it does |
|---|---|
| `W/components/Sidebar/Export.tsx` | One button, "Download SVG": `saveSvg(#alluvialSvg, names.join("-") + ".svg")` (`packages/.../utils/save-svg.ts`). No PNG, no JSON, no zip. |
| `W/io/save-diagram.js` | `saveDiagram(version, networks, root, state)`: the 2019 single-JSON format (`{version, timestamp, state, networks:[{id,name,codelength,moduleNames,nodes}]}`). **Not imported anywhere**; it throws `TypeError: network.getModuleNames is not a function` on the current engine. |
| `P/from-diagram.ts` | `createFilesFromDiagramObject` (the 2019 loader, `// TODO remove`): exported from the package, called by nothing. |
| `apps/web/public/data/science-1998-2001-2007.json` | 3.5 MB 2019-format sample, unused since `git:b0f5081` (2022). |

### 1.2 Load (`LoadNetworks.tsx` → `parseAcceptedFiles` → `store.setNetworks`)

1. react-dropzone with `accept` = `.tree .ftree .stree .clu .net` (text/plain), `.json`, `.zip`.
2. `readAcceptedFiles` (`P/parse-files.ts:88`): a file is a zip only if `file.type === "application/zip"`. Chrome on Windows
   reports `application/x-zip-compressed`, so there the zip goes to the text parser and fails (code reading; not run in a
   browser). Zip entries are read in central-directory order. Entries with other extensions produce an "Unsupported file
   format" error each, and the rest still load.
3. Per file: `.json` → `JSON.parse`; `.net` → unpartitioned (Infomap must run in the app); others → `infomap-parser`.
4. `setIdentifiers(nodes, format, store.identifier)` (`P/set-identifiers.ts`). For JSON a stored `node.identifier`
   wins, and **string paths are split with `TreePath.toArray` (`split(":").map(Number)`)**, so an stree-style
   `"1;1;63;"` path becomes `[NaN]`.
5. `createFile` (`P/parse-files.ts:146`) spreads **every top-level JSON key** over the `NetworkFile` after
   `id: id()`. A top-level `id` therefore overrides the random id, and unknown keys (for example `alluvial`) are carried
   inertly.
6. The user may reorder files by dragging, split or merge multilayer files, or switch the identifier
   (`NodeIdentifier.tsx` re-runs `setIdentifiers`; stored identifiers still win for JSON).
7. "Create Diagram" → `store.setNetworks(files)` (`S:217`) → `checkColors` (top-level `colors` array, or `colors: true`
   with node `color`) → `new Diagram(files)` → `updateLayout`.

What a JSON file can set today: `name`, `codelength`, `colors`, `directed`, `bipartiteStartId`, `modules`
(module enter/exit flow and links), `layers` (layer names on split), per node `path, flow, name, id, stateId, layerId,
identifier, highlightIndex, moduleLevel, metadata, color`. Module `name` in Infomap's `modules` is **not** read
(`A/Module.ts:31-36` copies only enter/exit flow).

### 1.3 What is lost on a save → load round trip (today, through the only working route)

| State | Stored in the store as | Survives today? |
|---|---|---|
| network order | `diagram.children` | only by zip-entry order or the drop order of loose files (browser-dependent); no index in the file |
| network names | `Network.name` (`setNetworkName`) | yes, if the writer writes top-level `name` (no writer exists in TS) |
| palette | `highlightColors` | yes, via `colors` (identical list in every file) |
| colours | leaf `highlightIndex` | yes |
| expanded modules | leaf `moduleLevel` | yes |
| module names | `Module.name` (`setModuleName`, `S:402`) | **no**. Nothing writes or reads them. They are also lost in-session by `moveNetwork` (rebuild) and by regroup (`Module` objects are recreated). |
| custom module order | `network.children` order + `isCustomSorted` | **no** |
| layout options | `height, moduleWidth, streamlineFraction, streamlineThreshold, flowThreshold, marginExponent, zeroMargins, verticalAlign, moduleSize, sortModulesBy, showBipartiteNodes` | **no** |
| display options | `streamlineOpacity, defaultHighlightColor, showModuleId, showModuleNames, multilineModuleNames, showNetworkNames, aggregateStateNames, titleCaseModuleNames, hierarchicalModules, hierarchicalModuleOffset, hierarchicalModuleOpacity, dropShadow, fontSize, networkFontSize, adaptiveFontSize` | **no** |
| colour scheme | `selectedSchemeName` | **no** |
| stree insignificance | `TreePath.insignificant` (affects highlight groups → geometry) | **no**. JSON cannot express it; a `;` string path becomes module `NaN`. |
| Infomap top-level data | `modules`, `layers`, `directed`, `bipartiteStartId`, `version`, `args`, ... on the NetworkFile | **no** (Python's writer drops them) |
| format/version info | none | **no version tag exists** |

There is also an in-session bug in the same code path: `moveNetwork` (`S:517-557`) rebuilds via `setNetworks` and
re-applies the **file's** `colors` after the user may have recoloured. Leaf indices then point into the wrong palette
(v3-webapp-json §4.3). It also drops module names and the custom order.

## 2. Today's Python

- `py/io/saved_diagram.py`: `is_saved_diagram`, `from_saved_diagram` (port of `createFilesFromDiagramObject`),
  `SavedDiagram` (list + `version/timestamp/state/module_names`), `saved_state`, `STATE_KEYS`, `diagram_json`
  (byte-identical port of `saveDiagram` with a `getModuleNames` shim), and `webapp_files` (per-network Infomap JSON
  with `colors`; the harness's reference writer, not a TS function).
- `py/layout.py:403` `save_diagram(networks, path, *, format="diagram"|"webapp", version, timestamp, **layout_kwargs)`.
  `"diagram"` writes the 2019 JSON (options, palette, names; no order). `"webapp"` writes `NN_<name>.json` to a directory
  or a `.zip` and warns about what it drops (options, names, order, insignificance) (`_warn_webapp_losses`).
- `py/io/__init__.py` `read()`: a 2019 file gives a `SavedDiagram`, a `.zip` gives `list[NetworkFile]` (`read_zip`), and
  Infomap JSON gives a `NetworkFile`. `layout(..., restore_state=True)` restores a `SavedDiagram`'s state and names.
  For webapp files, input `colors` are kept as the default colouring.
- `py/io/json_reader.py` keeps a fixed set of top-level keys (`_FILE_KEYS`: version, args, startedAt, completedIn,
  codelength, relativeCodelengthSavings, flowModel, higherOrder, stateLevel, bipartiteStartId, directed, layers,
  numTrials, colors) and parses `modules`. Other keys are dropped, so a read → save cannot pass them through.
- Tests and fixtures for the 2019 format: `tests/test_v3_fixtures.py` (the `saved`/`reload` blocks),
  `tests/test_api_v3.py`, the `saved`/`reload`/`saveDiagram` blocks in the 18 `tests/fixtures/v3/*__roundTrip.json`
  and 4 `tests/fixtures/v4/*__roundTrip.json`, `tests/fixtures/v3/webapp-science-trim__load{,State}.json`,
  `tests/data/webapp_science_trim.json`, and the fuzz round trip in `tests/test_fuzz_parity.py`. On the harness side
  (`tools/ts-fixtures/harness.ts`): the `saveDiagramText` + `getModuleNames` shim, `scenarios-v3.ts`, and the v4
  `saveModuleNames` shim.

---

## 3. Decisions taken in this plan (owner can override; see §9)

1. **Per-network files, not one diagram file.** Each file stays a loadable Infomap JSON. Today's production app and
   any Infomap-JSON consumer open it, and the app's existing loader (drop, zip, reorder, multilayer) is reused unchanged.
2. **Write what the app already reads at the top level** (`name`, `colors`, node `identifier/highlightIndex/moduleLevel`).
   Everything new goes in one namespaced `alluvial` block that older readers ignore.
3. **Do not touch Infomap's `version` key.** It is Infomap's version (`"v2.15.1"`). Our version tag is
   `alluvial.formatVersion` (an integer).
4. **Network-level state lives in the file of that network; diagram-level state is repeated in every file** and tied
   together by a `saveId`. Any subset of files still loads.
5. **The 2019 format is removed from both code bases.** Reading a 2019 file gives a clear error.

---

## 4. Format contract: alluvial network files, formatVersion 1

### 4.1 One file per network

Top-level keys, **in this order**, with absent keys omitted (fixed so that TS and Python write identical text):

| Key | Value | Read by |
|---|---|---|
| Infomap pass-through: `version`, `args`, `startedAt`, `completedIn`, `codelength`, `relativeCodelengthSavings`, `directed`, `flowModel`, `higherOrder`, `stateLevel`, `bipartiteStartId` | copied from the input file when present (only JSON inputs have most of them; tree inputs have none) | engine reads `codelength`, `directed`, `bipartiteStartId` |
| `name` | the diagram's network name (after `setNetworkName`) | engine (`Network.name`) |
| `colors` | the full `highlightColors` registry as CSS strings, identical in every file of a save; omitted when empty | `checkColors` |
| `nodes` | see below, in **input order** | engine |
| `modules` | Infomap's `modules` list, passed through unchanged when the input had one | engine (enter/exit flow, links) |
| `layers` | Infomap's multilayer `layers` list, passed through | split layers (names) |
| `alluvial` | the metadata block (§4.3) | new readers only |

Not written: top-level `id` (it would override the app's random id and collide when the same files are loaded twice),
`numLevels`/`numTopModules`/`numModules` (recomputed by `calcStatistics` on load; writing them would make the TS and Python
texts depend on two computations), `numTrials`, and the `NetworkFile` bookkeeping (`filename`, `size`, `format`,
`haveModules`, `flowDistribution`, ...).

Node keys, in this order: `path`, `flow` (raw input flow, `_flow`, not the bipartite-hidden 0), `name` (if defined),
`id` (physical id), `stateId` and `layerId` (if not null), `metadata` (if a non-empty object), `identifier`,
`highlightIndex`, `moduleLevel`. Infomap's per-node `modules` and `mec` are dropped (no reader uses them, and `modules`
would contradict an edited path).

`path` encoding:
- an **array of integers** (Infomap's own form) when no level is insignificant;
- the stree string with `;` markers when any level is insignificant: `segments.map((n, i) => n + (insig[i] ? ";" : ":")).join("")`,
  for example `"1;1;63;"` or `"1:1;63;"`. Probed with the real `TreePath` (scratch copy, node 24): `new TreePath(rebuilt)`
  restores the same array and insignificance flags for these forms. This needs the TS reader fix in §5.1 step 1, which
  stops `setIdentifiers` from splitting such strings into `[NaN]`.
- stree paths with a trailing `:` are written cleaned (array). The trailing-colon extra level (STATUS quirk 3) is
  therefore not reproduced on reload. If `fix-plan.md` removes that quirk in both engines, the reload is exact.

### 4.2 Delivery

- **Zip (default):** `<diagram name>.zip`, entries `NN_<safe network name>.json` (`NN` zero-padded diagram position;
  `safe` = `[^A-Za-z0-9._-]` → `_`, as today's `webapp_files`). Entries in position order, no directories.
- **Loose files:** the same entries written to a directory (Python), or a single `.json` when the diagram has one
  network.
- **Text:** `JSON.stringify(value, null, 2)` with no trailing newline (Python already has `js_json_stringify` for this).
  Zip bytes are not compared across TS and Python (the compressors differ); entry names, order and texts are.

### 4.3 The `alluvial` block

```jsonc
"alluvial": {
  "format": "alluvial-network",          // magic: identifies the block
  "formatVersion": 1,                    // integer; see §4.4
  "generator": "@mapequation/alluvial-diagram 1.16.0",   // or "alluvial (Python) 0.5.0"; informational
  "diagram": {                           // identical in every file of one save
    "saveId": "k3x9q2m1",                // random per save; ties the files together
    "position": 0,                       // this network's index in the diagram
    "numNetworks": 3,
    "colorScheme": "C3 Sinebow",         // selectedSchemeName
    "options": {                         // every OPTION_KEYS entry except identifier/duration, TS names and values,
      "height": 600, "moduleWidth": 80, ...   // in OPTION_KEYS order (S:28-57)
    }
  },
  "network": {
    "moduleNames": {"1": "Physics", "2:1": "Optics"},   // module id -> name; only non-empty names; children order
    "moduleOrder": ["3", "1", "2", "4"]                 // only when isCustomSorted: all module ids in network.children
  }                                                     // order (visible, then hidden), bottom to top
}
```

Rules:
- `options` excludes `identifier` (identifiers are stored per node) and `duration` (animation only). It includes the
  display-only keys so the web app restores its look. Python passes keys it does not model through unchanged (§6.2).
- `moduleNames` keys are module ids as the engine has them at save time (`"2:1"` for an expanded sub-module). The
  `moduleLevel` stored on the leaves recreates exactly those modules on load.
- `moduleOrder` lists **all** of `network.children`, hidden modules included. With `isCustomSorted` the layout skips the
  sort, so the hidden order matters as soon as `flowThreshold` is lowered.
- No timestamp. The zip entries carry dates, and a timestamp would only add noise to the byte-equality tests.

### 4.4 Versioning

- No `alluvial` block, or a `format` other than `"alluvial-network"`: plain Infomap JSON (today's behaviour,
  including `colors` / `highlightIndex` / `moduleLevel` if present).
- `formatVersion` 1: full restore (§4.5).
- `formatVersion` > 1: load nodes, names and colours (the top-level part is stable by contract), ignore the block,
  and warn "saved by a newer version (formatVersion N); options, module names and order were not restored".
- A non-integer or missing `formatVersion` in an `alluvial-network` block counts as invalid: same as the line above,
  with a different message.
- Bump the integer only for an incompatible change to the block. New optional keys inside the block do not bump it,
  and readers ignore unknown keys.

### 4.5 Restore semantics (identical in TS and Python)

Given the files chosen for the diagram (after any user reordering), in their final order:

1. **Diagram block** applies only when every file has a valid v1 block with the same `saveId`, and the positions are a
   permutation of `0..numNetworks-1` with `numNetworks` equal to the file count. Otherwise the diagram block is skipped
   with one warning ("files from different saves" / "incomplete save: k of n networks"). Per-network blocks still apply.
2. **Order:** the web app sorts each newly dropped batch by `position` when (1) holds for that batch, so loose files
   dropped in any order load in saved order. Python's `read` of a directory or a list of paths does the same. The user can
   still drag to reorder afterwards; nothing re-sorts later.
3. **Options and scheme** are set on the store **before** the build (no extra layouts), then `setNetworks` runs
   (`checkColors` restores the palette from `colors`).
4. **Module order** per network: the `setModuleOrder` primitive (§8), then **one** layout. Ids that no longer exist are
   skipped and the remaining modules keep the order they have. Each skipped id warns.
5. **Module names** per network: `setModuleName` for each id that exists. A missing id warns.

Equality contract: "TS load of F == Python load of F" bit for bit (the parity target), and "reload == original" for
everything in §1.3 structurally (order, names, colours, levels, options, scheme, network names). Geometry of the
reload is equal up to float summation order (≤ 3e-13 px, v3-webapp-json §4.2). A custom-ordered network is equal
**if** `setModuleOrder` reproduces the move sequence's layout (open; §8).

### 4.6 Compatibility matrix

| File | Today's production app | New web app | Python (new) |
|---|---|---|---|
| `infomap -o json` output | loads | loads (no block) | loads |
| `.tree/.ftree/.stree/.clu` | loads | loads | loads |
| new files, no insignificant paths | loads with names, palette, colours, expansion; ignores the block | full restore | full restore |
| new files with stree `;` paths | the affected nodes become module `NaN` (as with any `;` JSON path today) | full restore | full restore |
| today's `save_diagram(format="webapp")` output | loads | loads as plain Infomap JSON with colours | same |
| 2019 saved diagram | rejected | rejected, with a clearer message (optional) | `ValueError`: "the 2019 saved-diagram format is no longer supported" |

---

## 5. TS changes (web repo, in the `py-parity-fixes` worktree)

### 5.1 Engine (`packages/alluvial-diagram`)

1. `P/set-identifiers.ts` (json branch): keep a string path that ends in `;` as a string (the `TreePath` constructor
   parses it), and only `TreePath.toArray` other strings. This is the one-line fix for the `NaN` module. Python mirror:
   `py/io/identifiers.py`. Regenerating the fixtures must leave all existing fixtures unchanged (no current JSON input has
   `;` paths).
2. New `P/alluvial-format.ts`:
   - `export const ALLUVIAL_FORMAT = "alluvial-network"`, `ALLUVIAL_FORMAT_VERSION = 1`, and the types
     `AlluvialMetadata`, `AlluvialDiagramMetadata`, `AlluvialNetworkMetadata`.
   - `serializeDiagram(store, {generator, saveId?}): {name: string; text: string}[]`, as specified in §4.1-§4.3. It
     iterates `store.networks` (the files) for input-order nodes and looks each leaf up through the network's built
     leaves **by identity**, not by identifier (needed for duplicate identifiers; the harness already does this with
     `inputLeaves`, so the engine needs the same: `Network` keeps the `LeafNode` built from each input node, in input
     order). The pass-through keys come from the `NetworkFile`.
   - `readAlluvialMetadata(files): {diagram?: AlluvialDiagramMetadata; networks: (AlluvialNetworkMetadata|undefined)[]; warnings: string[]}`,
     which applies the §4.4/§4.5 validation.
   - `sortBySavedPosition(files)`, used by `parseAcceptedFiles` on each new batch.
   - `zipFiles(entries): Promise<Blob>` (JSZip is already a dependency).
3. `P/types.ts`: `NetworkFile.alluvial?: AlluvialMetadata`, plus the pass-through keys that are not yet typed
   (`version`, `args`, `startedAt`, `completedIn`, `relativeCodelengthSavings`, `flowModel`, `higherOrder`,
   `stateLevel`).
4. `S` (`DiagramStore`):
   - `openNetworks(files)` = §4.5 steps 3-5: apply options and scheme to fields without layouts, then `setNetworks(files)`,
     then `setModuleOrder` and module names, then one `updateLayout`. It returns the warnings.
   - `getOptions()`: the `OPTION_KEYS` values (used by the writer).
   - Fix `moveNetwork`: rebuild from `serializeDiagram`-equivalent in-memory data so that names, custom order and the
     **current** palette survive (today it syncs only names, `highlightIndex` and `moduleLevel`, and re-applies stale
     file `colors`). Concretely: also sync `file.colors = [...highlightColors]`, carry module names and `moduleOrder`,
     and run `openNetworks`-style restore after `setNetworks`.
   - Module names that survive regroup and expand (optional, see §9 Q4): keep `Network.moduleNames: Map<moduleId, string>`
     as the source of truth, with `Module.name` as a getter and setter over it.
5. Delete `P/from-diagram.ts` (`createFilesFromDiagramObject`) and its export in `P/index.ts`. This removes a public
   export (semver; §9 Q3).
6. Export the new functions from `P/index.ts` / `src/index.ts`. Unit tests next to them (`alluvial-format.test.ts`):
   writer key order, path encoding, block validation, sort, and a round trip through `parseAcceptedFiles` + `openNetworks`.

### 5.2 Web app (`apps/web`)

1. `W/components/Sidebar/Export.tsx`: add a "Download diagram" button (ZIP icon) next to "Download SVG". It calls
   `serializeDiagram(store, {generator: "@mapequation/alluvial-diagram " + version})` → `zipFiles` →
   `FileSaver.saveAs(blob, names.join("-") + ".zip")`. Tooltip or help text: "Network files with colours, names,
   order and settings. Open them again with Load networks." Optionally add a second item, "Download network JSON files",
   for loose files (one save prompt per file is clumsy, so the zip should be the main path).
2. `W/components/LoadNetworks/LoadNetworks.tsx` `createDiagram`: call `store.openNetworks(files)` instead of
   `store.setNetworks(files)`, and show the returned warnings through `onError` (or as a non-error toast).
3. `P/parse-files.ts` `readAcceptedFiles`: detect a zip by **extension or MIME type** (`.zip`, `application/zip`,
   `application/x-zip-compressed`, `application/x-zip`), and skip `__MACOSX/`, `._*` and directory entries silently
   (Python's `read_zip` already does).
4. Delete `W/io/save-diagram.js` and `apps/web/public/data/science-1998-2001-2007.json`. Drop `file-saver` only if
   nothing else uses it (the new button does).
5. `W/components/Documentation.tsx`: describe "Download diagram" and the format (one paragraph, linking to the format
   section of the package README).
6. Version string: use the package's `version` (vite `define` or `import pkg from "../package.json"`) for `generator`.

---

## 6. Python changes

### 6.1 Remove (2019 format)

- `py/io/saved_diagram.py`: delete `SavedDiagram`, `is_saved_diagram`, `from_saved_diagram`, `saved_state`,
  `STATE_KEYS`, `_LAYOUT_STATE_KEYS`, `SAVE_VERSION`, `diagram_json` and the `getModuleNames`-shaped `module_names` writer.
  Move `webapp_files` into a new `py/io/alluvial_format.py` and upgrade it (§6.2). Remove the module or reduce it to
  nothing.
- `py/io/__init__.py`: drop those exports. `read()` on JSON with top-level `networks` and no `nodes` raises `ValueError`
  ("2019 saved-diagram format (web app before 2022) is no longer supported; ...").
- `py/layout.py`: `save_diagram` loses `format`, `version` and `timestamp`. Remove `_warn_webapp_losses` (nothing is
  lost any more except the trailing-colon quirk; warn only for that, if it is kept). `layout(restore_state=)` keeps its
  name but now means "apply the `alluvial` block" (§6.2).
- Tests and fixtures: listed in §2, last bullet. Remove `tests/data/webapp_science_trim.json` and the two
  `webapp-science-trim__*` fixtures. Remove the `saveDiagram`, `saved`, `savedFilename` and `reload` blocks from the
  round-trip fixtures (by regeneration, §7). Update `README.md`, `docs/tutorial.ipynb`, `CHANGELOG.md` (breaking:
  0.5.0), `docs/dev/STATUS.md` (owner decision 4 goes away) and `design.md`.

### 6.2 Add or upgrade (new format)

- `py/io/json_reader.py`: keep **all** Infomap pass-through keys of §4.1 (add the missing ones to `_FILE_KEYS`) and the
  raw `modules`/`layers` lists for re-writing, parse the `alluvial` block into `NetworkFile.alluvial`
  (`AlluvialMetadata` dataclass: `format_version`, `generator`, `save_id`, `position`, `num_networks`, `color_scheme`,
  `options: dict` (TS names, raw), `module_names: dict[str, str]`, `module_order: list[str] | None`), and validate it per
  §4.4 with warnings. Path: accept stree strings with `;` (same rule as the TS fix).
- `read(dir)` and `read([paths])`: read `*.json` and sort by `position` per §4.5 step 2. `read(zip)`: unchanged except
  for the sort being applied when the files form one save (entries are already in order).
- `py/io/alluvial_format.py`: `serialize_diagram(store, generator=...) -> list[tuple[str, str]]`, a line-for-line port
  of `serializeDiagram` (same key order, path encoding and option order). It uses `js_json_stringify`. Colours are
  converted with `_css_colors`.
- `save_diagram(networks, path, **layout_kwargs)`: a `.zip` path gives a zip, a directory gives loose files, and a
  `.json` path is allowed only for one network. `generator = f"alluvial (Python) {__version__}"`.
- `layout(...)` with `restore_state=True` (default) and a valid block runs §4.5. The options map TS → Python names
  (`moduleWidth`→`module_width`, ..., `sortModulesBy` values `highlightIndex`→`highlight_index`, `nodeId`→`node_id`).
  **Explicit `layout` keyword arguments win** over stored options, and explicit `module_order`/`module_names` win over
  stored ones (the current rule for `SavedDiagram`). `colorScheme` maps to `scheme=`.
- Options Python does not model: the display keys are kept on the `AlluvialGeometry` (for example
  `geometry.saved_options`) so that `save_diagram(read(f))` writes them back unchanged. `showBipartiteNodes: false`
  changes the layout, and Python has no such option. Either port `toggleShowBipartiteNodes` (preferred; it is
  fixture-able) or warn that the file's bipartite nodes are shown. See §9 Q5.
- `draw()` may use `showModuleNames`, `showNetworkNames` and `defaultHighlightColor` from the restored options as
  defaults (optional; Python's draw options are separate today).

---

## 7. Tests and fixtures that prove losslessness

### 7.1 Harness (`tools/ts-fixtures/harness.ts`)

- Remove `saveDiagramText`, the `getModuleNames` shims, the harness-local `webAppFiles` writer and `loadWebAppFiles`'s
  id rewrite. Import `serializeDiagram`, `parseAcceptedFiles`, `DiagramStore.openNetworks` from the **engine** (the real
  code under test).
- New round-trip blocks per scenario (`roundTrip: true`): `savedFiles: [{name, text}]` from `serializeDiagram` with
  `generator: "<fixture>"` and `saveId: "fixture"` pinned, and `savedReload`: the full dump after `parseAcceptedFiles`
  (loose files **and** a JSZip zip; assert both identical) + `openNetworks`, with ids = entry name without `.json`
  (as today).
- Fixture `formatVersion` of the fixture files bumps (the blocks change). `generate.mjs --check` stays the guard.

### 7.2 Scenarios

Re-use all 18 v3 and 4 v4 round-trip scenarios (multilevel plain, coloured, expanded, expand+regroup, moveDown,
names, names+order, network name, planted JSON, states ftree id/name, mlayer split, insig-stree, debug5-stree,
highlight, jscolors, flowThreshold40 hidden names). Add:

| Scenario | Proves |
|---|---|
| `multilevel-tree__options__roundTrip` | every `OPTION_KEYS` value non-default + `colorScheme: "Paired"` restored; no extra layout |
| `insig-stree__colored__roundTrip`, `science-stree__colored__roundTrip` (`large`) | `;` path encoding; reload groups equal (today: 20 px off, module `NaN`) |
| `planted-json__passthrough` | Infomap `version`, `args`, `modules`, `directed` kept byte for byte; file still loads as plain Infomap JSON |
| `mlayer-named__split__roundTrip` | `layers` names and per-layer files |
| `bipartite__hidden__roundTrip` | `showBipartiteNodes: false` (if ported) |
| `multilevel-tree__order__flowThreshold__roundTrip` | hidden modules in `moduleOrder`; lowering the threshold after reload gives the same order as before |
| `multilevel-tree__moveNetwork__afterColor` | the `moveNetwork` fix: names, order and current palette survive (TS-only behaviour change; Python has no `moveNetwork` API, so the engine replay covers it) |
| `restore__mixedSaves`, `restore__partial`, `restore__formatVersion2`, `restore__badBlock` | §4.4/§4.5 warnings and partial restore (unit level in both, plus one fixture each for the geometry) |
| `restore__shuffledLooseFiles` | position sort |

### 7.3 Python tests (`tests/test_saveload.py`, replacing the 2019 parts of `test_v3_fixtures.py` / `test_api_v3.py`)

1. **Python-save == TS-save:** for every round-trip fixture, `serialize_diagram` on the replayed store gives
   `savedFiles` byte for byte (names, order and texts; `generator`/`saveId` pinned the same way). Since the texts are
   identical, TS loading Python's files is the same as TS loading its own, so **Python-save → TS-load** is proved by
   `savedReload`.
2. **TS-save → Python-load:** `layout(read(<savedFiles as dir>))` and `layout(read(<zip>))` equal `savedReload` bit for
   bit (geometry, palette, names, order flags, options).
3. **Reload vs original (structural):** module order per network, names, `highlight_colors`, leaf
   levels/indices, options and scheme are equal. Geometry is within 1e-12 except the scenarios documented in §4.5.
4. **Direct cross-runtime check:** the fuzz harness (`tests/test_fuzz_parity.py` + `ts-roundtrip.json`) writes
   Python's files for random cases and asks TS to load them (`openNetworks`) and dump. This catches anything the
   fixture set misses (duplicate identifiers, odd names, unicode, out-of-range indices).
5. **Infomap compatibility:** a saved file still parses with Python's plain Infomap-JSON path (block ignored) and keeps
   Infomap's keys. `read()` of `infomap -o json` output (`tests/data/planted_t0.json`) is unchanged.
6. **2019 rejection:** `read()` of a 2019-shaped dict raises with the new message.

---

## 8. Sequencing and dependencies

1. TS: `set-identifiers` `;` fix → `alluvial-format.ts` writer/reader + `openNetworks` + `moveNetwork` fix → web app
   button and loader → engine unit tests.
2. Harness: switch to the engine functions, add scenarios, regenerate (`ALLUVIAL_TS_ROOT` = worktree).
3. Python: remove the 2019 code, then port the writer, reader and restore. Tests per §7.3, then fuzz.
4. Docs: README, tutorial notebook (save → read → layout section), CHANGELOG, STATUS.

Dependencies on `fix-plan.md`:
- **`setModuleOrder` primitive.** The restore needs "put `network.children` in this order, set `isCustomSorted`, lay out
  once". This is the same primitive as the fast `module_order` fix. If the fix plan proves (or redefines) the one-layout
  order as canonical, the restore and `layout(module_order=...)` share it and a reload equals the original exactly. If it
  keeps the move-by-move semantics, the restore still uses the direct primitive (both runtimes identically, so parity
  holds), but reload geometry of a custom-ordered network may differ from the original session in streamline branch
  order. Document that.
- **Trailing-colon stree level and `checkColors` dummy-0:** independent. The writer is unaffected, because every file of
  a save carries the same `colors` list, so dummy-0 cannot trigger between our own files.

---

## 9. Open questions for the owner

1. **Default delivery:** a zip only from the web app's button (proposed), or also a "download loose JSON files"
   option?
2. **Insignificant stree paths** are written as `"1;1;63;"` strings (exact in the new app and Python, module `NaN` in
   today's production app until it is deployed). The alternative is integer arrays (old app fine, insignificance lost,
   geometry off for stree inputs). Proposed: strings.
3. **Removing `createFilesFromDiagramObject`** from the published `@mapequation/alluvial-diagram` exports: remove now
   (minor bump, it is marked `TODO remove` and unused), or deprecate for one release?
4. **Module names across regroup and expand** (TS loses a name when its `Module` object is recreated): fix with a
   per-network name map in both engines (proposed), or leave as is and only persist what exists at save time?
5. **`showBipartiteNodes` in Python:** port the toggle (proposed; it is a layout option the web app saves), or warn
   and ignore?
6. **Python `layout()` precedence:** explicit keyword arguments override stored options (proposed). Should a stored
   option that is overridden warn, or stay silent?
