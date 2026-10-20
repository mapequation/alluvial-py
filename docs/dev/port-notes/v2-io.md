# Port note (v2): IO — multilayer splitting, Infomap JSON, saved-diagram JSON

Status: v2 spec for the Python port. It extends [`parsers.md`](parsers.md) (§4 JSON, §5 identifiers, §6 statistics,
§7 multilayer), which stays valid; this note does not repeat what is there unless a v2 detail depends on it.
Everything marked **[verified]** was run on 2026-10-10: the real TS sources were loaded read-only through Vite SSR
(the same setup as `tools/ts-fixtures/generate.mjs`, run from a scratch directory), and the Python side was the
current `src/alluvial` plus a scratch reference implementation (§7.3). Nothing was written under the TS repo.

Sources (relative to `web/alluvial/`, read-only):

| Abbrev. | Path |
|---|---|
| `P/` | `packages/alluvial-diagram/src/parsers/` |
| `A/` | `packages/alluvial-diagram/src/alluvial/` |
| `S/` | `packages/alluvial-diagram/src/store/DiagramStore.ts` |
| `R/` | `packages/alluvial-diagram/src/react/` |
| `W/` | `apps/web/src/` |
| `IC` | Infomap C++ dev checkout `../infomap/Infomap/src/` |

---

## 0. Summary

| Item | TS behaviour | Python today | v2 work | Engine work |
|---|---|---|---|---|
| Multilayer split (`expandMultilayerFile`) | UI button per multilayer file; one network per layer, nodes matched by **physical id** | not ported (`read` docstring says so) | `split_layers(nf)` + `read(..., split_layers=True)` (§2) | **none** (verified bit-exact, §2.6) |
| Multilayer merge (`mergeMultilayerFiles`) | UI button to undo a split | not ported | **do not port** (§2.7) | none |
| Infomap JSON (`-o json`) | `.json` → `JSON.parse` → `setIdentifiers(…, "json")` → `createFile` | rejected with a "not supported yet" error (`io/__init__.py:44`) | `read_file` for `.json` (§3) | none (verified) |
| JSON `colors` (`checkColors`) | input highlight colours, applied on every `setNetworks` | not ported (`set_networks` sets `highlight_colors = []`) | v2-optional, ~30 lines (§4) | `DiagramStore.set_networks` gains `check_colors` |
| Saved web-app diagram JSON | **rejected** by the current app; dead converter `createFilesFromDiagramObject` | rejected (same error as JSON) | **recommend v3** (§5), keep a clear error in v2 | none (verified bit-exact, §5.4) |

---

## 1. Shared facts

### 1.1 Where the UI calls the transforms

- `W/components/LoadNetworks/Item/Item.tsx:107-115`: the network icon toggles `files = file.isExpanded ? mergeMultilayerFiles(file, files) : expandMultilayerFile(file, files)`.
- `W/components/LoadNetworks/Item/components.tsx:70-84`: the toggle is enabled only if `file.isMultilayer && !(!file.isExpanded && file.numLayers === 1)`.
  So the UI never splits a multilayer file with a single layer, but `expandMultilayerFile` itself accepts one.
- `W/components/LoadNetworks/NodeIdentifier.tsx:19-36`: switching the identifier mode re-runs `setIdentifiers` on every file
  **except `isExpanded` ones**. Split layers therefore always keep the physical-id identifiers, whatever the mode.
- Order in the app: drop files (`parseAcceptedFiles` with the current mode) → optional split/merge → "Create diagram" →
  `store.setNetworks(files)` (`S:217-234`), which runs `checkColors` and then `new Diagram(files)`.

### 1.2 `NetworkFile` fields that the engine reads

Only `id`, `name`, `nodes`, `codelength`, `layerId`, `originalId`, `modules`, `directed`, `bipartiteStartId`
(`A/Network.ts:54-86`) and, per node, `path`, `flow`, `name`, `id`, `stateId`, `layerId`, `identifier`,
`highlightIndex`, `moduleLevel`, `metadata` (`A/LeafNode.ts:42-61`). Everything else is UI or statistics.
`layerId`/`originalId` are read by `colorModuleIdsInAllNetworks` (`S:756-781`), see §2.5.

---

## 2. Multilayer splitting (`P/multilayer-utils.ts`)

### 2.1 `expandMultilayerFile(file, files)` (lines 45-92), exact execution order

```
1. if not file.isMultilayer: throw Error("File is not multilayer")                       # :46-48
2. layers = {}  (plain JS object)                                                         # :50
3. setIdentifiers(file.nodes, "multilayer-expanded")                                      # :52
     → for every node, in order: node.identifier = node.id.toString()   (P/set-identifiers.ts:30-35)
     MUTATES the node objects, which stay shared between `file` and the layers
4. file.isExpanded = true                                                                 # :54   (before the copies!)
5. for node in file.nodes (file order):                                                   # :56-78
     key = String(node.layerId)                                   # JS property key, see 2.3
     if layers[key] is missing:
         layer = shallow copy of `file`   (Object.assign({}, file): every own key, incl.
                 isExpanded=true, format, filename, header fields, modules, layers, network, flowDistribution …)
         layer.id = id()                  # random "_xxxxxxxxx" (U/id.ts) → Python: deterministic, 2.4
         layer.originalId = file.id
         layer.lastModified = file.lastModified; layer.size = file.size   (no-ops, already copied)
         layer.layerId = node.layerId     # the FIRST node's value for that key
         layer.nodes = []
         layer.name = file.layers?.find(l => l.id === layerId)?.name ?? `Layer ${layerId}`
     layers[key].nodes.push(node)         # file order inside each layer
6. for layer in Object.values(layers):                                                    # :80-85
     Object.assign(layer, {...calcStatistics(layer.nodes), isExpanded: true})
     → flowDistribution, isMultilayer (= nodes[0].layerId !== undefined), isStateNetwork,
       numLayers (1, or undefined for the "undefined" layer), numTopModules, numLevels are recomputed;
       isExpanded from calcStatistics is overwritten with true
7. newFiles = [...files]; newFiles.splice(files.indexOf(file), 1, ...Object.values(layers))   # :87-91
```

`file.nodes` itself is not reordered. Layers do not get new `Node` objects: the identifier mutation in step 3 is visible
through the original file too (it has left the list).

### 2.2 Layer name

`file.layers?.find((l) => l.id === layerId)?.name ?? "Layer " + layerId` (`:68-74`):
- strict `===`: a JSON `layers: [{id: "0", …}]` does **not** name layer `0` **[verified]**;
- the first matching entry wins; a matching entry with `name` null/undefined falls back to the default;
- `"Layer " + layerId` uses JS `String(number)` (= `js_num_str`): `"Layer 1.5"`, `"Layer -1"`, `"Layer undefined"`.
- Only hand-made JSON has `layers` (Infomap writes no such key, `IC/io/Output.cpp:301-340`; the TS comment says "FIXME
  where is this used?").

### 2.3 Layer order and key collisions **[verified]**

`Object.values` order: keys that are canonical array indices (`"0"` … `"4294967294"`) ascending numerically, then all
other keys in insertion (first-seen) order. Example run: nodes with `layerId` 2, 0, −1, 1.5, (missing), 10 →
layers in the order `0, 2, 10, −1, 1.5, undefined`, named `Layer 0, Two (from layers), Layer 10, Layer -1, Layer 1.5, Layer undefined`.
For Infomap output (non-negative integer layer ids) this is simply ascending `layerId`.

The key is `String(layerId)`, so `-0` and `0` share a layer, and so do JSON `"1"` and `1` (the layer keeps the first
node's value). A missing `layerId` gives key `"undefined"`. This layer has `isMultilayer = false` and `numLayers = undefined`
from `calcStatistics` but `isExpanded = true`.

### 2.4 Network ids (Python)

TS ids are random. Python needs a deterministic id. It must be unique and must not contain `--` (streamline ids,
`streamlines.md` §2). Use

```
layer.id = f"{file.id}_layer{js_key(layer_id)}"     # js_key = String(x): js_num_str for numbers, "undefined" for None
```

The fixture harness must use the same rule (`${file.id}_layer${String(layerId)}`). Collisions with other network ids
(for example a file whose stem is `x_layer1`) go through the v2 auto-disambiguation (`_2` suffix), which must run
**after** splitting, over the final network list.

### 2.5 What the engine does with split layers

- Leaves are matched across neighbouring networks by the physical-id identifier. Streamlines connect the same physical
  node in adjacent layers, and layers sit in the §2.3 order. Any non-split neighbour matches only if its identifiers are
  also physical ids. A `.tree` read with `identifier="id"` uses `stateId ?? id`, so it does not match.
- `colorModuleIdsInAllNetworks` (`S:756-781`, Python `engine/store.py:177-217`) takes its **multilayer branch** only if every
  network has `layerId != null` and the same `originalId` as network 0. The branch sums the visible module flow per
  `moduleId` over the layers and colours in descending total flow. Splitting must therefore set `layer_id` and `original_id` on
  each layer. Python `engine/network.py:63-65` already reads both.
- `isMultilayer` on the `Network` (`A/Network.ts:88-90`) is per first leaf, UI only.
- `colorByLayer` (`S:795-821`) uses the **leaf** `layerId`. It is meant for unsplit multilayer networks; on split layers it
  gives one colour per network. It belongs to the v2 colour ops (colours note), not to IO.

### 2.6 Verification **[verified]**

A seeded multilayer net (40 physical nodes, layers added in the order 3, 1, 4, 2, 139 state nodes, 3 levels, 17 top
modules; Infomap 2.15.1 PyPI wheel, `seed=123`, `num_trials=5`) was written as `write_tree(states=True)` and
`write_json(states=True)`. For each of {tree, json} × {identifier `id`, `name`} × {no op, `colorModuleIdsInAllNetworks`,
`colorMatchingModulesInAllNetworks`, plus a non-split first-order network appended with `colorModuleIds`}, the TS
`parseAcceptedFiles → expandMultilayerFile → setNetworks → op` was compared with Python `read_file` / the JSON
reference reader → `split_layers` (§7.3) → `DiagramStore.set_networks` → op. **16/16 matched exactly**: every
module's id, visibility, x, y, width and height, every group's highlight index, y and height, every streamline-node id, and
`highlightColors`. `from_infomap(im, states=True)` + `split_layers` also matched the TS file path (with `colorModuleIds`).
So **no engine change is needed**; the Python `DiagramStore` already handles `layer_id`/`original_id`.

The identifier mode had no effect on the split layers (as expected, §1.1). The appended first-order network
used `stateId ?? id` / name identifiers, so it matched layer nodes only by coincidence of the strings.

### 2.7 `mergeMultilayerFiles` (lines 6-43): do not port

The merge exists only to undo a split in the UI. It is not an identity: rows come back layer-major (verified again:
state ids `3,4,5,6,7,8,0,1,2` for a file that was `0..8`), `setIdentifiers(…, "tree")` forces mode `"id"` (`:37`),
and `name = file.filename`. Python users simply do not split. If a merge is ever needed, parsers.md §7 has the spec.

### 2.8 Edge cases

| Case | TS | Python recommendation |
|---|---|---|
| not multilayer (`nodes[0].layerId` undefined), e.g. a physical-level tree of a multilayer net | throws `"File is not multilayer"` | `ValueError` with a hint (`states=True` / `-o states`) |
| one layer only | works (UI hides the button) | allow; returns `[layer]` |
| some nodes without `layerId` | an extra `"Layer undefined"` network, last | reproduce (only hand-made input) |
| JSON `layerId: null` | key `"null"`, name `"Layer null"`; `calcStatistics` counts `null` as a layer, `isMultilayer` true if node 0 | Python `None` cannot tell null from missing → `"Layer undefined"`. **Documented divergence**, only for hand-made JSON |
| duplicate (layer, physical id) rows | both added; last wins in lookup (parsers §5) | keep, warn per layer (`warn_duplicate_identifiers`) |
| split file also passed unsplit | node objects shared in TS | Python copies the nodes (`dataclasses.replace`) so the input `NetworkFile` is not mutated; verified to give identical geometry |

---

## 3. Infomap JSON (`-o json`, `write_json`)

### 3.1 TS path (`P/parse-files.ts:51-82, 146-171`)

```
format = extension (case-sensitive, after the last ".")                           # :42
parsed = JSON.parse(text)        # SyntaxError → error "invalid-json"                # :51-57
if !parsed → "Could not parse file"                                                  # :72-75 (null, 0, "", false)
setIdentifiers(parsed.nodes, "json", identifier)                                     # :78
   for each node: identifier = node.identifier ?? idfn(node)        (P/set-identifiers.ts:36-43)
                  if path is not an array: path = TreePath.toArray(path)   ("1:2" → [1,2]; "1:2;3;" → [1,NaN])
createFile(file, "json", parsed)                                                     # :79, :146-171
   {filename, name: file.name, lastModified, size, id: id(), haveModules: true, format: "json", ...parsed}
   if haveModules: Object.assign(file, calcStatistics(nodes))   # overwrites numLevels / numTopModules
any exception in setIdentifiers/createFile → "invalid-format", file skipped          # :80-82
```

No `@mapequation/infomap-parser` code is involved. It only contributes the `Header`/`Module` types
(`node_modules/@mapequation/infomap/index.d.ts`, v2.15.1). The web app's own Infomap run uses `output: "ftree"`
(`W/components/LoadNetworks/Item/Item.tsx:45-50`), so JSON reaches the app only by file upload.

### 3.2 What Infomap writes (`IC/io/Output.cpp:301-440`; PyPI 2.15.1 output **[verified]**)

Top level: `version, args, startedAt, completedIn, codelength (full precision), [seed, trialOffset, trials, numTrials:
dev checkout only], numLevels, numTopModules, numModules (array), relativeCodelengthSavings, directed, flowModel,
higherOrder, [stateLevel if memory], [bipartiteStartId if bipartite], nodes, modules`.

Node (in tree row order, bipartite feature nodes hidden as in `.tree`):
- physical level of a higher-order net: `{path, name, flow, mec, id}`;
- otherwise: `{path, modules, name, flow, mec, [metadata: {"0": "3", …} first-order only], [stateId, [layerId]] if states, id}`.
`path` is an int array, `name` is always a string, and `flow`/`mec` are rounded to 6 significant digits (`jsonOutputNumber`).

Module: `{path ([0] = root), enterFlow, exitFlow, numEdges, numChildren, codelength, [links: [{source, target, flow}]]}`.

### 3.3 Fields → `NetworkFile` / engine **[verified]**

- All top-level keys are spread **after** the defaults. A JSON `id`, `name`, `format`, `haveModules`, `filename`, `size` or
  `lastModified` overrides the default (verified: `{"id":"X","name":"N","format":"tree","haveModules":false}` gives
  id `X`, name `N`, format `tree`, and no statistics).
- `calcStatistics` on array paths: `parts = path` (array), top = `path[0]`. Verified values: `fo.json` →
  `flowDistribution {1: 0.5, 2: 0.5}`, `numLevels 2`; multilayer states JSON → `{1: 0.8888896000000001, 2: 0.1111112}`,
  `isMultilayer true`, `numLayers 3`. The existing Python `calc_statistics` already handles list paths and gives the same values.
- `modules` (JSON) **is read by the engine**: `A/Network.ts:79-85` keys them by `path.join(":")`, and `A/Module.ts:31-42` copies
  `enterFlow`/`exitFlow` (and `links` if present) into every module whose id matches. These are dead for geometry but appear in
  the fixture's `modules[j].enterFlow/exitFlow`, so the Python reader must map them into `InfomapModule`
  (`path`, `enter_flow`, `exit_flow`, `num_edges`, `num_children`, `links`); drop `codelength`. Split layers inherit the full module
  list (§2.1 step 5).
- A node's `identifier` key, if present and not null, wins over the mode (verified `"ID4"`). Infomap never writes it.
- `stateId` present → identifier `"id"` mode gives the state id. `layerId` present → multilayer → splittable (§2).
- `metadata` passes to `LeafNode.metadata` (UI and the v2 metadata colouring). Values are strings in Infomap output.
- Extra keys (`mec`, node `modules`, `numModules`, `seed`, `trials`, `flowModel`, …) are carried along and ignored.
- The leaf id is the path **array** (`A/LeafNode.ts:42`, `super(null, networkId, node.path)`). Nothing in the geometry uses it.

### 3.4 Rejections **[verified]** (`errors[].code`, message)

| Input | TS result |
|---|---|
| not JSON | `invalid-json` |
| `null` | `invalid-format` "Could not parse file" |
| `[]`, `{}`, `1` (no `nodes`) | `invalid-format` (`forEach` of undefined) |
| `{"nodes": {}}` | `invalid-format` (`nodes.forEach is not a function`) |
| `{"nodes": []}` | `invalid-format` (`calcStatistics` reads `nodes[0]`) |
| node without `path` | `invalid-format` (`TreePath.toArray(undefined)`) |
| node without `id`, mode `"id"` (or mode `"name"` without `name`) | `invalid-format` (`toString` of undefined) |
| Infomap **input** network JSON (`{nodes:[{id,name}], links|states|intra}`) | rejected (no `path`) |
| saved web-app diagram (`{version, timestamp, state, networks}`) | `invalid-format` (no `nodes`) |

`flow` is not validated. A missing `flow` loads and propagates `undefined` → NaN into module flows. (Fix round WP4, E9: `parseAcceptedFiles` now rejects a missing, `null`, non-numeric or non-finite flow as `invalid-format`; so does Python, which also stopped reading `null` as 0.)

### 3.5 JSON number semantics (Python `json` vs JS `JSON.parse`)

- `NaN`/`Infinity`/`-Infinity` tokens: JS rejects them (`invalid-json`), Python accepts them by default. Use `parse_constant` that raises.
- Integers beyond 2**53: JS rounds them to a double, so the identifier string differs (`12345678901234567891` → JS `"12345678901234567000"`).
  For parity use `parse_int=lambda s: int(s) if abs(int(s)) <= 2**53 else float(s)` and `js_num_str`.
- Floats: both parsers round correctly, so the flows are bit-identical to the TS values.
- `-0`: Python `json.loads("-0")` gives int `0`; JS gives `-0`. `js_num_str` prints both as `"0"`, so this is harmless.
- Duplicate keys: last wins in both. BOM: read with `encoding="utf-8-sig"` (browser FileReader strips it).
- JSON vs `.tree` from the same Infomap run: same row order and same 6-digit flows. The only TreePath difference is that array paths
  never carry `;` (insignificant) markers.

---

## 4. JSON `colors` → `checkColors` (`S:180-210`), v2-optional

Runs at the start of **every** `setNetworks` (`S:220`), over the files in order, before `new Diagram`:

```
colors = []; index = {}                      # Map: colour string → index
for net in networks:
    if Array.isArray(net.colors):            # colours listed, nodes carry highlightIndex already
        for c in net.colors: if c not in index: colors.append(c); index[c] = 0      # DUMMY 0 (bug)
    elif net.colors === true:                # colours on nodes
        for node in net.nodes:
            if node.color != null:           # null/undefined skipped; node keeps its own highlightIndex
                if c not in index: node.highlightIndex = len(colors); colors.append(c); index[c] = node.highlightIndex
                else:              node.highlightIndex = index[c]
store.setHighlightColors(colors)             # REPLACES highlightColors (also [] when no file has colors)
```

**[verified]**: A = `{colors: ["#f00","#0f0"]}` with node highlight indices 1 and 5, then B = `{colors: true}` with node
colours `#0f0`, `#00f` and `null` (with `highlightIndex 4`) → `highlightColors ["#f00","#0f0","#00f"]`, B's indices `[0, 2, 4]`.
The `#0f0` index is 0 because of the dummy-0 bug (fixed in fix round WP6, S7: now 1, and a list palette is remapped per
file; colors-render §2.5 erratum). A's index 5 is out of range, so `getHighlightColor` returns `undefined`
(`S:314-323`). A second `setNetworks` on the same files gives the same result (idempotent; the node objects were mutated).
A following `colorMatchingModulesInAllNetworks` **clears** the input colours (`clearColors` first).

Python: add `Node.color: str | None` and `NetworkFile.colors: list[str] | bool | None`, port `check_colors(files)` into
`DiagramStore.set_networks` before the build, mutating `node.highlight_index` (on the reader's own Node copies), then set
`highlight_colors`. With input colours, `layout(colors=...)` must not run a colour op (see Q4).

---

## 5. Saved web-app diagram JSON (`science-1998-2001-2007.json`)

### 5.1 Format (written by `W/io/save-diagram.js:3-71`)

```
{version: "0.3.0", timestamp, state: {…store options…},
 networks: [{id, name, codelength, moduleNames: [[moduleFullId, {name, flow}], …], nodes: [
     {path: "1:9:443", flow, name, id, identifier, insignificant, highlightIndex, moduleLevel}, …]}]}
```

- `nodes` are in `network.leafNodes()` order (module → group → branch → streamline node), **not** the original file
  order. `path` is the leaf id, which is the raw path string of the source file.
- `moduleNames` is `Map` entries (pairs). The key is the full module id `${networkId}_module${moduleId}`. `flow` is informational.
- The sample (3.5 MB) has 3 networks (`1998`, `2001`, `2007`, ids `_7peextn2u`, `_ttuk7fz7p`, `_k4c69rrhc`), with 6906/7170/7940 nodes.
  `moduleLevel` is 1 or 2, i.e. the stored expand state. `highlightIndex` values are −1, 1, 3, 5, 6 and 7. Every `insignificant` is false.
  `identifier == name` for every node (it was saved in "name" mode). There are 3/1/3 module names, for top-level modules.
- `state`: `height 750, duration 400, marginExponent 4, moduleWidth 110, moduleFlowThreshold 0.005, streamlineFraction 2.9,
  streamlineOpacity 0.7, streamlineThreshold 0.7, verticalAlign "bottom", showModuleId, showModuleNames, showNetworkNames,
  dropShadow, fontSize 10, defaultHighlightColor "#b6b69f", highlightColors [12 ColorBrewer Paired colours]`.

### 5.2 What loading it does in the current app **[verified]**

It is **rejected**: `parseAcceptedFiles` → `setIdentifiers(undefined, "json")` → `invalid-format` "Cannot read properties
of undefined (reading 'forEach')". `createFilesFromDiagramObject` (`P/from-diagram.ts:6-32`, marked `// TODO remove`,
exported from `P/index.ts` but called nowhere) is the only definition of its meaning:

```
totNodes = sum(len(n.nodes) for n in json.networks) or 1
for network in json.networks (in order):
    setIdentifiers(network.nodes, "json")      # mode default "id"; stored identifiers win; path strings → arrays (MUTATES json)
    yield {...file, lastModified, size: file.size * len(nodes) / totNodes, filename: file.name,
           haveModules: true, format: "json", ...calcStatistics(nodes), ...network}
    # network keys win: id, name, codelength, numLevels, numTopModules, moduleNames, nodes.
    # `name` is NOT defaulted from the file (commented out), so a network without `name` gets undefined.
```

Then `store.setNetworks(files)`. **[verified]** on the sample: it builds 120/111/80 modules (40/42/38 visible, mostly at
`moduleLevel` 2). Groups keep their stored highlight indices. But `checkColors` sets `highlightColors = []` (no `colors` key), so
every highlight index ≥ 0 has colour `undefined` (`S:314-323`). `moduleNames` are carried on the NetworkFile and
**ignored**: `Module.name` stays `""` (only `setModuleName`, `S:402-405`, sets it; `R/Module.tsx:152-162` renders
`module.name || largest leaf names`). `state` is not read by anything. The `insignificant` field is ignored (`LeafNode` recomputes
it from the TreePath, and array paths are never insignificant). A diagram saved from an `.stree` with `;` paths would come back
with `NaN` path components (`TreePath.toArray("1:2;3;") = [1, NaN]`).

### 5.3 Module names on the sample

Mapping `moduleNames` keys to modules after the build: in `1998` and `2007`, modules `2` ("Physical sciences") and `3` ("Social sciences")
exist and are visible at level 1. Module `1` ("Life sciences") is expanded, so its key matches nothing. In `2001`, module `3`
("Computing science") is visible, but `2001` is a middle network, so it has no labels anyway.

### 5.4 Engine parity of the Python port **[verified]**

Python `Node(path=…, highlight_index=…, module_level=…, identifier=…)` per node → `set_identifiers(nodes, "json")`
→ `NetworkFile(id, name, format="json", codelength)` → `DiagramStore(LayoutOptions(height=750, module_width=110,
streamline_fraction=2.9, margin_exponent=4, flow_threshold=0.005, streamline_threshold=0.7, vertical_align="bottom")).set_networks`
was compared with TS `createFilesFromDiagramObject` + `new DiagramStore(same options).setNetworks`. All **311 modules** matched
exactly (id, visibility, x, y, width, height, `moduleLevel`, each group's highlight index, y and height), and so did all **1034 streamline
node ids** (in order). The current engine needs nothing new: `LeafNode` already honours `highlight_index`/`module_level`
(`engine/leaf_node.py:65-70`).

### 5.5 Cost of supporting it in Python

| Piece | Size | Notes |
|---|---|---|
| reader `read_diagram(path) -> SavedDiagram` (networks + state) | ~80 lines | §5.2 semantics; validate ids (unique, no `--`) |
| state → `LayoutOptions` mapping | ~20 lines | `moduleFlowThreshold → flow_threshold`, and so on. **No TS parity target**: the current TS never reads `state` |
| palette restore (`state.highlightColors`, `defaultHighlightColor`) | ~20 lines + API | without it, the stored highlights render with the out-of-range colour. Needs a `layout` palette override, and `colors=None` |
| module names | ~30 lines + **geometry contract change** | `ModuleGeometry` label text = `module.name` when non-empty (single line, black, `R/Module.tsx:152-162`); `draw` must honour it |
| `layout()` entry point | ~40 lines | accept a `SavedDiagram` (one source → several networks + options + palette + names) |
| fixtures | harness loader path via `createFilesFromDiagramObject` + `setHighlightColors(state.highlightColors)` after `setNetworks` | 1-2 scenarios. The 3.5 MB sample is too big for `tests/data`, so a small saved diagram has to be synthesised |
| total | ~1 day incl. tests | engine: 0 |

**Recommendation: v3.** The engine part is free (§5.4), so deferring costs nothing in design. Everything that makes
the feature useful (options, palette, module names, a multi-network `layout` entry) is new public API with **no TS behaviour to
match**: the current web app cannot load the file, and the converter is marked for removal. Its palette and naming API
also overlaps with the v2 `highlight=` API and the label rules, which should land first. The format is undocumented and
has one 2019 sample (`version 0.3.0`). In v2, replace the generic JSON error with a specific one when the top level has
`networks` and no `nodes`: "a saved alluvial web-app diagram, which is not supported; load the original network files".

---

## 6. What the Python port has / lacks today

**Update 2026-10-10:** the JSON reader (`io/json_reader.py`, with the number guards), `split_layers` /
`read(..., split_layers=True)` (`io/multilayer.py`; `_js_key` lives there, privately, not in `_jscompat.py`) and
`layout(..., split_layers=...)` are implemented. Still missing: `check_colors`, `Node.color`, `NetworkFile.colors`
(the JSON `colors` input is ignored), and the saved web-app diagram (v3). The tables keep the pre-v2 state.

| Have | File |
|---|---|
| `set_identifiers` incl. `"json"` and `"multilayer-expanded"` | `src/alluvial/io/identifiers.py:33-63` |
| `calc_statistics` (list and string paths, NaN handling, JS key order) | `io/identifiers.py:82-122` |
| `create_file` with the contents-override semantics | `io/identifiers.py:125-154` |
| `Node.highlight_index/module_level/metadata`, `NetworkFile.layer_id/original_id/layers/bipartite_start_id/modules` | `io/types.py` |
| engine reads `layer_id`, `original_id`, `modules` (enter/exit flow, links), `highlight_index`, `module_level` | `engine/network.py:58-73`, `engine/leaf_node.py:55-70` |
| multilayer branch of `color_module_ids_in_all_networks` | `engine/store.py:177-217` |
| `TreePath` with list paths and `to_array` (`"1:2;3;" → [1, nan]`) | `tree_path.py` |

| Missing | Where |
|---|---|
| JSON reader (Infomap `-o json`) | `io/__init__.py:44` lists `json` as unsupported; `tests/test_io_robustness.py:28` asserts that message (update it) |
| `split_layers` / `read(..., split_layers=True)` | new `io/multilayer.py`; `read` docstring "not ported" note (`io/__init__.py`, "State networks") to update |
| `check_colors`, `Node.color`, `NetworkFile.colors` | `engine/store.py:61-65`, `io/types.py` |
| JSON number guards (`parse_constant`, `parse_int`) | JSON reader |
| a JS-key helper `js_key(x)` (`String(x)` for property keys) | `_jscompat.py` (`js_num_str` + `"undefined"`/`"null"`/bool) |

---

## 7. Python port guidance

### 7.1 API

- `alluvial.io.split_layers(nf: NetworkFile, *, id_format="{id}_layer{layer}") -> list[NetworkFile]`.
- `read(source, ..., split_layers=False)`: when `True`, returns `list[NetworkFile]` (paths and Infomap objects).
  Raise `ValueError` for a non-multilayer source. The `identifier` argument does not apply to the layers (they always use
  physical ids, §1.1). Say so in the docstring, and consider a warning if `identifier="name"` is passed explicitly (Q2).
- `layout(networks, ...)`: users unpack the layers (`layout([*read(p, split_layers=True)])`). Optionally flatten one level of
  nested lists (Q3).
- `read_file("x.json")` / `read("x.json")` → Infomap JSON reader. Dispatch on the parsed top level:
  dict with a list `nodes` → Infomap output; dict with `networks` and no `nodes` → saved-diagram error (§5.5);
  `nodes` without `path` plus `links`/`states`/`intra` → "Infomap input network" error (run Infomap first).
- Defaults: network id = explicit `network_id` > JSON top-level `id` > file stem; name = explicit `name` > JSON `name` >
  basename. JSON `format`/`haveModules`/`filename`/`size`/`lastModified` are not honoured. They do not affect geometry; document this.

### 7.2 Pitfalls

1. Split **after** reading with the normal identifiers, then overwrite them with `js_num_str(node.id)` on copies of the
   nodes. Never mutate the caller's `NetworkFile`.
2. Layer order is JS object key order (§2.3), not `sorted()` and not first-seen. Use `is_array_index_key(js_key(v))`.
3. Copy **every** file field into each layer (`dataclasses.replace`), including `modules`, then set `id`, `name`, `nodes`,
   `layer_id`, `original_id`, apply `calc_statistics`, and set `is_expanded = True` last.
4. Strict equality for `layers[].id` (no bool/str/number cross-matching; Python `True == 1` must not match).
5. JSON node keys are camelCase. Map `stateId, layerId, highlightIndex, moduleLevel` to snake_case and drop unknown keys. Keep `metadata`
   as is. Keep `path` as the list (do not join it into a string). `set_identifiers(nodes, "json", identifier)` converts string paths.
6. Map JSON `modules` into `InfomapModule` (fixtures expose `enterFlow`/`exitFlow`).
7. Reject what TS rejects (§3.4), with the same conditions. Missing `flow`: reject (a divergence from TS, which yields NaN geometry, until fix round WP4 made TS reject it too), see Q5.
8. Run `warn_duplicate_identifiers` per resulting network (per layer after a split).
9. Network-id disambiguation (v2 follow-up) runs over the final list, after splitting.

### 7.3 Reference implementation (scratch, verified against TS in §2.6/§3.3)

```python
def _js_key(v):                       # JS String(v) as a property key
    if v is None: return "undefined"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return js_num_str(v)
    return str(v)

def _strict_eq(a, b):                 # JS ===
    if isinstance(a, bool) or isinstance(b, bool): return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)): return a == b
    return type(a) is type(b) and a == b

def split_layers(nf, id_format="{id}_layer{layer}"):
    if not nf.is_multilayer:
        raise ValueError("not a multilayer network")
    nodes = [dataclasses.replace(n) for n in nf.nodes]
    set_identifiers(nodes, "multilayer-expanded")
    groups = {}                        # key -> (first layer_id, name, nodes)
    for n in nodes:
        k = _js_key(n.layer_id)
        if k not in groups:
            name = next((l.get("name") for l in (nf.layers or []) if _strict_eq(l.get("id"), n.layer_id)), None)
            groups[k] = (n.layer_id, name if name is not None else f"Layer {_js_key(n.layer_id)}", [])
        groups[k][2].append(n)
    order = sorted((k for k in groups if is_array_index_key(k)), key=int) + \
            [k for k in groups if not is_array_index_key(k)]
    out = []
    for k in order:
        lid, name, lnodes = groups[k]
        layer = dataclasses.replace(nf, id=id_format.format(id=nf.id, layer=_js_key(lid)), name=name,
                                    nodes=lnodes, layer_id=lid, original_id=nf.id)
        for key, value in calc_statistics(lnodes).items():
            setattr(layer, key, value)
        layer.is_expanded = True
        out.append(layer)
    return out
```

The JSON reader used for verification maps node keys `{id, flow, path, stateId, layerId, name, identifier, highlightIndex,
moduleLevel, metadata}` and file keys `{version, args, startedAt, completedIn, codelength, relativeCodelengthSavings,
flowModel, higherOrder, stateLevel, bipartiteStartId, directed, layers, id, name, numTrials}`. It then calls
`set_identifiers(nodes, "json", identifier)` and `create_file(contents, format="json", …)`. The production reader must add
`modules` → `InfomapModule` and the §3.5 number guards.

---

## 8. Proposed v2 fixture scenarios (IO)

### 8.1 New datasets (`make_datasets.py`, PyPI Infomap 2.15.1, seeded, committed to `tests/data/`)

| Files | Content |
|---|---|
| `mlayer_states.tree`, `mlayer_states.json` | one seeded multilayer run (≈40 physical nodes, 4 layers **added out of order** e.g. 3,1,4,2, 3 levels, names `p<id>`), `write_tree(states=True)` and `write_json(states=True)` |
| `mlayer_flat.tree` | Infomap on the same physical network aggregated over layers (first order, same node ids) → a non-split neighbour whose `"id"` identifiers match the layers' physical ids |
| `planted_t{0,1,2}.json` | `write_json` of the existing planted runs (same Infomap objects as the `.tree` files) |
| `states_t{0,1}.json` | `write_json(states=True)` of the existing state runs |
| `mlayer_named.json` (hand-edited) | `mlayer_states.json` + `layers: [{id: 1, name: "Alpha"}, {id: 3, name: "Gamma"}, {id: "4", name: "not matched"}]` |
| `jsoncolors_t{0,1}.json` (hand-made, only if §4 is ported) | t0 `colors: [...]` with node `highlightIndex` incl. one out of range; t1 `colors: true` with node `color` incl. a colour first listed by t0 (dummy-0 bug) and a `null` |

### 8.2 Harness changes

- `Scenario.split?: number[]`: file indices to split. After `loadFiles`, for each **original file object** in increasing index:
  `files = expandMultilayerFile(f, files)`, then set each layer's id to `${f.id}_layer${String(layer.layerId)}`.
- JSON files go through the existing `parseAcceptedFiles` path (`json` is already in `ACCEPTED_FORMATS`). The harness's
  stem override also replaces a JSON top-level `id`; note this in the README.
- `inputs.split` (list of file indices). `inputs.networkIds`/`networkNames` are then per **final** network (they no longer
  align with `inputs.files`). `networks[i].file.path` = the source file, plus new `file.layerId` and `file.originalId`
  (null when not split). Python replay: read each file, split the listed ones, flatten in order, then pin ids/names from
  `inputs`.
- Existing fixtures stay byte-identical. Only new files are added. The new keys are emitted only when a scenario uses them, or as `null`,
  which would change every fixture. **Emit them only for scenarios with `split`/JSON**, so that nothing is regenerated.

### 8.3 Scenarios

| Scenario | Files | Options / ops | Covers |
|---|---|---|---|
| `planted-json__default` | `planted_t{0,1,2}.json` | defaults | JSON reader, array paths, JSON `modules` → enter/exit flow |
| `planted-json__colored` | same | `colorMatchingModulesInAllNetworks` | JSON + colour op swap-remove orders |
| `states-json__default` | `states_t{0,1}.json` | defaults | `stateId` identifiers from JSON |
| `states-json__name` | same | `identifier: "name"` | name mode on JSON (duplicate names) |
| `mixed-json-tree__default` | `planted_t0.json`, `planted_t1.tree`, `planted_t2.ftree` | defaults | array and string paths in neighbouring networks |
| `mlayer-unsplit__default` | `mlayer_states.tree` | defaults | unsplit multilayer (v1 path, baseline) |
| `mlayer-split__default` | `mlayer_states.tree` | `split: [0]` | layer order 1,2,3,4 vs input 3,1,4,2; physical-id matching |
| `mlayer-split__name` | same | `split: [0]`, `identifier: "name"` | the mode is ignored after a split (must equal `__default` except `inputs`) |
| `mlayer-split__colorModuleIds` | same | `split: [0]` + `colorModuleIdsInAllNetworks` | multilayer branch of `colorModuleIds` |
| `mlayer-split__colored` | same | `split: [0]` + `colorMatchingModulesInAllNetworks` | similarity across layers |
| `mlayer-split__flowThreshold40` | same | `split: [0]`, `flowThreshold: 0.4` | hidden modules in thin layers |
| `mlayer-split-json__colorModuleIds` | `mlayer_states.json` | `split: [0]` + `colorModuleIdsInAllNetworks` | JSON multilayer split |
| `mlayer-split-flat__colorModuleIds` | `mlayer_states.tree`, `mlayer_flat.tree` | `split: [0]` + `colorModuleIdsInAllNetworks` | split layers + a normal network: non-multilayer branch, streamlines to the flat network |
| `mlayer-named-json__default` | `mlayer_named.json` | `split: [0]` | `layers` names, strict `===` |
| `jsoncolors__default` (if §4 ported) | `jsoncolors_t{0,1}.json` | defaults (no colour op) | `checkColors`, the dummy-0 bug, out-of-range index |
| `jsoncolors__colored` (if §4 ported) | same | `colorMatchingModulesInAllNetworks` | the colour op clears the input colours |

Hierarchy (`expand`) on split layers is covered by the v2 hierarchy note's scenarios if a 3-level multilayer dataset is used
there; it needs no IO-specific scenario.

IO-only Python unit tests (no harness): the §2.3 layer-order example with its expected order and names, the §3.4 rejection
table, the §3.5 number guards, `split_layers` not mutating its input, and `read(..., split_layers=True)` on a non-multilayer
file raising.

---

## 9. Open questions

1. **Saved-diagram JSON: v2 or v3?** This note recommends v3 (§5.5), with only a specific error message in v2. If v2: decide whether
   `state` options are applied by default and how the palette and module names enter `layout` (`SavedDiagram` object vs
   keyword arguments).
2. Should `read(..., split_layers=True, identifier="name")` warn, or should Python add a non-TS option to match layers by name?
   (TS always uses physical ids for layers; the name mode would match a physical node's states by name, which is equivalent unless
   names repeat.)
3. Should `layout()` flatten nested lists (`layout([read(p, split_layers=True), other])`), or should it require unpacking?
4. With JSON input colours (§4), what should `layout(colors=...)` default to? The default `"similarity"` clears them. Options: an
   `"auto"` default that picks `None` when any file has `colors`/non-negative `highlight_index`, or an explicit warning.
   This interacts with the v2 `highlight=` API (mutually exclusive with `colors`).
5. Missing `flow` in JSON nodes: reject (recommended) or reproduce the TS NaN propagation?
6. Layer id format `"{id}_layer{k}"`: is it acceptable as the public default (it appears in every module/streamline id in
   the geometry)? An alternative is `"{id}:{k}"`. `:` is safe for streamline ids, but it reads like a module path.
7. JSON `layerId: null` / `stateId: null` (hand-made only): accept the documented divergence (§2.8), or keep a sentinel to
   reproduce `"Layer null"`?
8. Is `check_colors` (§4) part of v2? It is cheap and has a fixture, but no Infomap tool writes `colors`. Its only producers
   are hand-made or third-party JSON.
