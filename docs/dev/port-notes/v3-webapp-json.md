# Port note (v3): saved web-app diagram JSON, `checkColors`, colour schemes

Status: v3 spec for the Python port, in support of the "v3 design" in [`docs/dev/design.md`](../design.md). It extends
[`v2-io.md`](v2-io.md) §4-§5, which stay valid; this note corrects one point there (§1: the web app no longer saves
diagrams at all) and adds the save side, the round trips, a second load route, and the schemes.
Everything marked **[verified]** was run on 2026-10-10 against TS HEAD `d0abf3b` (2026-10-09, clean `src/`): the real TS
sources were loaded read-only through Vite SSR (the `tools/ts-fixtures/generate.mjs` setup, run from a scratch directory,
with `apps/web/src/io/save-diagram.js` imported as is and only its `file-saver` sink stubbed). History claims come from
`git log`/`git show` in the TS repo. Nothing was written under the TS repo.

> **Erratum (0.5, fix round WP2).** The 2019 saved-diagram format is removed from both code bases: TS deleted
> `parsers/from-diagram.ts` (`createFilesFromDiagramObject`), `apps/web/src/io/save-diagram.js` and the bundled
> `science-1998-2001-2007.json`; Python deleted `SavedDiagram`, `from_saved_diagram`, `diagram_json`, `saved_state`
> and the `state`/`moduleNames` restore. `alluvial.read` of JSON with top-level `networks` and no `nodes` raises
> `ValueError("the 2019 saved-diagram format is no longer supported; use alluvial 0.4 to convert")`. §2, §3.2-§3.5,
> §7.1 and the `saved`/`reload`/`webapp-science-trim` parts of §8 are history. `save_diagram(networks, path,
> **layout_kwargs)` writes only the §4 web-app files (directory or `.zip`); `io/saved_diagram.py` keeps only
> `webapp_files` until the new format replaces it (fix-plan.md WP9).
>
> **Erratum (0.5, fix round WP9).** The §4 web-app files are superseded by the saved-diagram format "alluvial network
> files" formatVersion 1 (saveload-plan.md §4; TS `parsers/alluvial-format.ts`, Python `io/alluvial_format.py`).
> The writer is now the engine's `serializeDiagram` (no harness copy): paths are Infomap's arrays or, with an
> insignificant level, stree `;` strings (insignificance is kept); Infomap's top-level keys, `modules` and `layers`
> pass through; `colors` is omitted when empty; node `metadata` comes before `identifier`; and an `alluvial` block
> stores the options, scheme, module names and custom order (`openNetworks` restores them once and removes the
> blocks from the files; E19 hides bipartite nodes at build). The §4 "lost on reload" lists, the trailing-colon quirk (removed in WP3) and §3.4 "never reload ==
> original" are history: a reload now equals the original up to float summation order. The fixtures' `webAppFiles`/
> `webAppReload` blocks are now `savedStore`/`savedFiles`/`savedReload` (tools/ts-fixtures/README.md).

Sources (relative to `web/alluvial/`, read-only), same abbreviations as v2-io:

| Abbrev. | Path |
|---|---|
| `P/` | `packages/alluvial-diagram/src/parsers/` |
| `A/` | `packages/alluvial-diagram/src/alluvial/` |
| `S` | `packages/alluvial-diagram/src/store/DiagramStore.ts` |
| `C/` | `packages/alluvial-diagram/src/schemes/` |
| `R/` | `packages/alluvial-diagram/src/react/` |
| `W/` | `apps/web/src/` |
| `git:<sha>` | a commit of the TS repo (history before the 2026 monorepo split used `src/` paths) |

---

## 0. Summary

| Question | Answer |
|---|---|
| (a) How does the web app save a diagram? | **It does not, today.** `W/io/save-diagram.js` (`saveDiagram`) is dead code: nothing imports it since the Save button was commented out in `git:5d8f62e` (2021-11-09), and it throws `TypeError: network.getModuleNames is not a function` on the current engine (removed in `git:7e446e1`, 2022-01-18). With that one method shimmed it still produces the 2019 format (§2) **[verified]**. |
| (b) How does it load one? | **It does not, today.** The UI path rejects the file (`invalid-format`, "Cannot read properties of undefined (reading 'forEach')") **[verified]**. The only remaining loader is the dead converter `P/from-diagram.ts` (`createFilesFromDiagramObject`, `// TODO remove`, exported, not called since `git:b0f5081`, 2022-11-30). It restores nodes (`highlightIndex`, `moduleLevel`, `identifier`), network ids, names and codelengths; it ignores `state`, `moduleNames`, `version` and `insignificant`, and `checkColors` empties the palette, so every saved colour renders black (§3). |
| What the current app *can* load with colours and expansion | One Infomap-JSON-shaped file per network (dropped together or in one `.zip`) carrying top-level `colors` (the palette) and per-node `highlightIndex`/`moduleLevel`/`identifier`. It reproduces networks, names, palette, colours and expanded modules, with geometry equal to ≤ 3e-13 px for every probed scenario except stree inputs with `;` paths **[verified]** (§4). |
| Lost by every route into the current app | custom module order (`isCustomSorted`), module names, layout/display options, the selected scheme name, stree insignificance (`;` paths) (§3.4, §4.4). |
| (c) `checkColors` | v2-io §4 re-verified through the full `parseAcceptedFiles` → `setNetworks` path, including the dummy-0 mis-colouring (§5). |
| (d) Colour schemes | 64 named lists in `C/index.ts` (d3 7.9.0, d3-scale-chromatic 3.1.0, `@mapequation/c3` 1.1.1); default `"C3 Sinebow"`. A scheme only feeds later colour ops; `highlightColors` is the registry of colour strings in first-use order and is emptied by every `setNetworks`/`clearColors` (§6). |

Consequence for the v3 design: "Python write → TS load → same geometry" has **no live TS target in the web app's own
save/load code**; the TS references are the dead `saveDiagram` + `createFilesFromDiagramObject` pair (harness-only), and
the live Infomap-JSON route (§4). Which one `save_diagram` targets is a decision (§10 Q1).

---

## 1. History (why both directions are dead)

| Date | Commit | Change |
|---|---|---|
| 2019-06-10 | `git:31b6a0b`, `git:0f119d8` | "Export diagram to json" / "Load networks from json". `saveDiagram(version, networks, alluvialRoot, state)` in `src/io/export.js`. |
| 2019-06-12 | `git:6c34023` | Load custom module names from a saved diagram (`Module.customNames`). |
| 2019-10/11 | `git:601c7b7`, `git:f8e4ade` | `public/data/science-1998-2001-2007.json` (saved 2019-11-06, `version "0.3.0"`) becomes the example data. |
| 2021-11-09 | `git:5d8f62e` | mobx refactor: the Save click is commented out (`//dispatch({ type: "saveDiagram" })`). |
| 2021-12-15 | `git:6574dc2` | The last caller (`AlluvialDiagram.jsx`) is deleted. |
| 2022-01-18 | `git:7e446e1` | `Network.getModuleNames` removed (module names move to `Module.name` / `setModuleName`). |
| 2022-04-21 | `git:e5fe247` | `saveDiagram` moved verbatim to `src/io/save-diagram.js` (now `W/io/save-diagram.js`). |
| 2022-11-30 | `git:b0f5081` | Diagram-JSON loading removed from `parseAcceptedFiles`; the example becomes the four `science*_2y.stree` files (`P/fetch-example-data.ts`). The science JSON stays in `apps/web/public/data/`, unused. |

The app's About text points users who miss the old version to `mapequation.org/alluvial/old` (`W/components/Documentation.tsx`);
that deployment (not verified here) is the only place where §2's files were loaded with `state` and module names (§3.3).

---

## 2. Save: `saveDiagram` (`W/io/save-diagram.js:3-71`)

### 2.1 Algorithm

```
saveDiagram(version, networks, root, state = {}):
    filename = ",".join(n.name for n in networks) + ".json"           # file names, not diagram names
    for network in networks:                                            # the NetworkFile list, in diagram order
        net = root.getNetwork(network.id)                               # A/Diagram.ts:115; missing -> console.error, nodes []
        emit {
          id:          network.id,
          name:        net.name || network.name,                        # diagram name wins (setNetworkName), "" falls back
          codelength:  network.codelength,                              # FILE value; undefined -> key omitted
          moduleNames: net.getModuleNames(),                            # TypeError today (§2.3)
          nodes: [ {path: leaf.id, flow: leaf.flow, name: leaf.name, id: leaf.nodeId, identifier: leaf.identifier,
                    insignificant: leaf.insignificant, highlightIndex: leaf.highlightIndex, moduleLevel: leaf.moduleLevel}
                   for leaf in net.leafNodes() ] }
    JSON.stringify({version, timestamp: +new Date(), state, networks: [...]}, null, 2)   # 2-space indent
```

Field sources **[verified]** on `multilevel_t*`, `planted_t*.json`, `states_t*.ftree`, `science200{1,3}_2y.stree` and the
split `mlayer_states.json`:

| Field | Source | Notes |
|---|---|---|
| `path` | `LeafNode.id` = the node's `path` **as given to the engine** (`A/LeafNode.ts:43`, `A/AlluvialNode.ts:104-110`) | text formats: the raw string, including stree `;`/trailing `:` (`"1;1;63;"`); JSON input: the **array** `[2, 1]`, written over several lines by the 2-space indent |
| `flow` | `LeafNode.flow` getter = `visible ? _flow : 0` (`A/LeafNode.ts:67-69`) | raw input flow; 0 only for bipartite nodes hidden by `showBipartiteNodes` |
| `name` | `LeafNode.name` | key omitted when `undefined` (JSON nodes without `name`) |
| `id` | `LeafNode.nodeId` (physical id) | `stateId`, `layerId`, `metadata` are **not** written |
| `identifier` | `LeafNode.identifier` | what made the match across networks; it survives reload (JSON mode keeps stored identifiers) |
| `insignificant` | getter, `!treePath.isSignificant(moduleLevel - 1)` | `true` only for stree `;` paths; informational, never read back |
| `highlightIndex`, `moduleLevel` | leaf fields | the colour and expand state |

Order: `nodes` follow `network.leafNodes()` (module → group → branch → streamline node, i.e. layout order), **not** file
order (`same order as file: false` on `multilevel`). Key order is exactly as listed. `networks` keep diagram order.

### 2.2 `state` (written by the caller, never by `saveDiagram`)

The 2019-2021 caller (`git:6574dc2~1:src/components/Diagram/AlluvialDiagram.jsx`, the `saveDiagramBit` branch) passed
`process.env.REACT_APP_VERSION` and:

```
state = {height, duration, marginExponent, moduleWidth, moduleFlowThreshold, streamlineFraction, streamlineOpacity,
         streamlineThreshold, verticalAlign, showModuleId, showModuleNames, showNetworkNames, dropShadow, fontSize,
         defaultHighlightColor, highlightColors, moduleSize, sortModulesBy, modulesVisibleInFilter}
```

(the 2019 sample predates `moduleSize`, `sortModulesBy`, `modulesVisibleInFilter`). Mapping to today's store options
(`S:28-57`): every key has the same name except `moduleFlowThreshold` → `flowThreshold`; `duration` was ms (400) and is
now seconds (0.2), presentation only; `highlightColors` is not an option (it is restored with `setHighlightColors` after
`setNetworks`); `modulesVisibleInFilter` belongs to the dropped module filter. No current store setting is missing from
the list except `zeroMargins`, `multilineModuleNames`, `aggregateStateNames`, `titleCaseModuleNames`,
`hierarchicalModules*`, `networkFontSize`, `adaptiveFontSize`, `showBipartiteNodes`, `identifier` and the scheme name.

### 2.3 `moduleNames`

`getModuleNames` no longer exists, so there is no current definition. The 2019-2021 one (`git:5d8f62e~1:src/alluvial/Network.ts:78-83`):

```
getModuleNames() = [[key, {name, flow}] for key, value in Module.customNames (a static Map) if key.startsWith(network.id)]
```

Keys are full module ids `${networkId}_module${moduleId}`; `flow` was the module flow when it was named. `startsWith`
is a prefix test, so a network id that prefixes another (`net1`, `net10`) would collect the other's names.
For a harness, shim `Network.prototype.getModuleNames` (see §8.1): with `() => []` the output is exactly what a
fixed `saveDiagram` would write for a diagram without names.

### 2.4 The bundled sample deviates from §2.1

`science-1998-2001-2007.json` (3.5 MB) is minified (not 2-space indented) and its networks carry two extra keys,
`numLevels` and `numTopModules` (between `codelength` and `moduleNames`, or after `name`), so it was post-processed after
saving. Node key order matches §2.1. All paths are strings without `;`; every `insignificant` is false. Facts in
v2-io §5.1 and §5.3 (ids, counts, `state`, the Paired palette, 3/1/3 module names) are unchanged **[verified]**.

---

## 3. Load

### 3.1 Current UI path: rejected **[verified]**

`parseAcceptedFiles` (`P/parse-files.ts:51-82`) parses the `.json`, then `setIdentifiers(parsedFile.nodes, "json", …)`
throws because there is no top-level `nodes`, and the file is reported as `invalid-format`
"Cannot read properties of undefined (reading 'forEach')". 0 files are produced.

### 3.2 Dead converter: `createFilesFromDiagramObject(json, file)` + `setNetworks` (`P/from-diagram.ts:6-32`)

v2-io §5.2 has the code. What survives, field by field **[verified]**:

| Stored | Restored? | How / why |
|---|---|---|
| network order, `id`, `name`, `codelength` | yes | `...network` is spread last over the file object; the Network ctor reads them (`A/Network.ts:54-86`) |
| extra network keys (`numLevels`, `numTopModules`, `colors`, `layerId`, `originalId`, `directed`, `modules`, …) | yes, if the engine reads them | same spread; `colors` reaches `checkColors` (§5) |
| node `path` | yes, converted | `setIdentifiers(…, "json")` turns strings into **arrays** with `TreePath.toArray` = `split(":").map(Number)` (`P/set-identifiers.ts:36-43`, `utils/TreePath.ts:157-159`) |
| node `identifier` | yes | stored identifier wins (`node.identifier ?? id(node)`); the identifier mode is irrelevant |
| node `highlightIndex`, `moduleLevel` | yes | `A/LeafNode.ts:51-58` (integers only; otherwise −1 / 1) |
| node `flow`, `name`, `id` | yes | |
| node `insignificant` | **no** | recomputed from the TreePath; array paths are never insignificant |
| `moduleNames` | **no** | carried on the NetworkFile, read by nothing; `Module.name` stays `""` |
| `state` (options, `highlightColors`, `defaultHighlightColor`) | **no** | nothing reads it; `checkColors` sets `highlightColors = []` (no network has `colors`) |
| `version` | **no** | the 2019 loader set `identifier = name` for `version < 0.3.0`; this one does not |
| custom module order | not stored | `isCustomSorted` is not saved; layout re-sorts by `sortModulesBy` |
| `stateId`, `layerId`, `metadata` | not stored | `Network.isHigherOrder` turns false for state networks, so the UI hides "aggregate state names" and "colour by physical id" (`W/components/Sidebar/Layout.tsx:185`, `Colors.tsx:205`) and labels cannot show state ids (`R/Module.tsx:227-242`); layer and metadata colouring are unavailable |

With `highlightColors = []`, every group index ≥ 0 makes `getHighlightColor` return `undefined` (`S:314-323`) and the
group renders **black** (streamlines §6.4, colors-render §1.4); −1 stays `defaultHighlightColor`.

### 3.3 The 2019-2021 loader (for reference; not reproducible from this repo's current code)

`LoadNetworks.jsx` (`git:5d8f62e~1`) accepted a single diagram `.json` (no other files), applied
`setIdentifiersInJsonFormat` (`version < 0.3.0` → `identifier = name`), and passed the whole JSON as React state:
`Layout` spread `json.state` over its defaults (so options **and** `highlightColors` were restored), and
`Root.addNetwork` merged each network's `moduleNames` into `Module.customNames`. A module without its own name showed the
names of its named descendants (`subModuleNames`: keys starting with its id, sorted by ascending stored flow). That
engine was different (pre-mobx), so its geometry is not a parity target.

### 3.4 Round trips through the dead pair **[verified]**

Store state → `saveDiagram` (with `getModuleNames = () => []`) → `createFilesFromDiagramObject` → fresh `DiagramStore(same options).setNetworks`:

| Scenario | Modules, groups, streamline ids | Palette | Other |
|---|---|---|---|
| `multilevel_t*` plain | same sets and orders; module `y`/`height` differ in the last bits (≤ 3e-13 px) | — | leaf order changed, so `calcFlow` sums in another order |
| colored (`colorMatchingModulesInAllNetworks`), expanded, expanded+colored, `json-input` coloured, `mlayer` split coloured | exactly equal | lost (`[]` → black) | |
| regroup after expand; one `colorModule` | same orders, last-bit differences | lost | expand state is per leaf, so regroup round-trips |
| custom move (`moveSelectedModule("down")`) | **order lost**: `1 3 2` → `1 2 3`, `y` changes by ~30 px | — | `isCustomSorted` false after reload |
| `setNetworkName` | name kept | | `setModuleName`: lost (`moduleNames: []`) |
| `states_t*.ftree`, identifier `"name"`, coloured | **streamline count changes (29 → 26)** | lost | duplicate identifiers: which leaf a name maps to depends on node order, which the save changes; `isHigherOrder` true → false |
| `science200{1,3}_2y.stree` (5486 `;` paths) | **an extra module `NaN`** in each network (6 visible instead of 5) | lost | `"1;1;63;".split(":")` → `[NaN]` |
| re-save of a reloaded diagram | | | `path` becomes an array (`[2, 1]`), so the file is not a fixed point |

So even within TS, save → load is bit-exact only up to float summation order, and structurally exact only without
duplicate identifiers, stree `;` paths and custom order. The parity target for Python is therefore
"Python load of file F == TS load of file F" (and "Python write == TS write" for the same store state), not
"reloaded == original".

### 3.5 The bundled sample in the current engine **[verified]**

`createFilesFromDiagramObject` + `DiagramStore({height 750, marginExponent 4, moduleWidth 110, flowThreshold 0.005,
streamlineFraction 2.9, streamlineThreshold 0.7, verticalAlign "bottom", defaultHighlightColor "#b6b69f"})`: 91 ms;
120/111/80 modules (40/42/38 visible); visible group indices `{-1,1,7}`, `{-1,1,3,6}`, `{-1,1,3,5,7}`; `highlightColors []`.
After `setHighlightColors(state.highlightColors)`: index 1 = `#1f78b4`, 7 = `#ff7f00` (d3 `schemePaired`). Module names:
`2`/`3` exist and are visible in 1998/2007 and `3` in 2001; module `1` ("Life sciences") does not exist as a `Module`
(all its leaves are at `moduleLevel` 2). Every `Module.name` is `""`.

---

## 4. The route the current app loads: Infomap-JSON files with colours

### 4.1 Format (one file per network)

```
{ "name": <network name>,                 # top-level keys are spread over the NetworkFile (createFile, P/parse-files.ts:146-170)
  "codelength": <number>,                 # optional
  "colors": [<css colour>, ...],          # the full highlightColors, identical in every file (§5)
  "nodes": [ {"path": "1:2:3" | [1,2,3], "flow": <raw flow>, "name": ..., "id": <physical id>,
              "stateId": ..., "layerId": ...,      # only when present (isHigherOrder, layers, labels)
              "identifier": <string>, "highlightIndex": <int>, "moduleLevel": <int>,
              "metadata": {...}}, ... ] }          # optional
```

Delivery: N `.json` files dropped together, or one `.zip` with the files as entries in network order (JSZip keeps
central-directory order; zero-padded names such as `00_<name>.json` keep it obvious and avoid integer-like keys).
The user can still drag files to reorder in the load dialog (`W/components/LoadNetworks/LoadNetworks.tsx:192-206`).

### 4.2 Verified behaviour

A TS reference writer (store → files above; nodes in **original file order**, `highlightIndex`/`moduleLevel` copied
from `network.getLeafNode(identifier)`, `path` = `leaf.treePath.toString()`, `flow` = `leaf._flow`) zipped with JSZip
and loaded with `parseAcceptedFiles([zip], [], formats, "id")` → `setNetworks` **[verified]**:

| Scenario | Module sets and group orders | max abs diff (y, height, group height) | `highlightColors` | streamline ids |
|---|---|---|---|---|
| `multilevel` plain, file order | equal | **0** (bit-exact) | equal | equal |
| `multilevel` plain, `leafNodes()` order | equal | 2.8e-14 | equal | equal |
| expanded+coloured (string or array paths), coloured + `colorModule`, `planted` JSON coloured, `states` ftree coloured, `mlayer` split coloured | equal | ≤ 2.8e-13 | equal | equal |
| `science` stree coloured | **group order differs in 10 modules** | 20.3 px | equal | differ |

Names come from the JSON `name` (`Layer 1`, … for split layers). The residual 1e-13 noise is the known effect of
build-time `highlightIndex` (groups are created in another order than by `setColor` → `update()`; README "Cross-note
decisions"). The stree difference is the lost insignificance: JSON cannot express it (strings are split on `:` and
arrays have no `;`), so the writer must write the cleaned path (`TreePath.toString()` or the number array), never the
raw `leaf.id` (§3.4 `NaN`).

### 4.3 Caveats

- `readAcceptedFiles` treats a file as a zip only when `file.type === "application/zip"` (`P/parse-files.ts:100`). Browsers
  that report `application/x-zip-compressed` (Chrome on Windows) send it to the infomap parser as text, which fails.
  Loose `.json` files avoid this. Not verified in a browser.
- A top-level `id` would override the random file id (`createFile` spreads contents after `id: id()`); loading the same
  files twice would then give duplicate network ids. Omit `id`.
- Any top-level key lands on the NetworkFile: `nodes`, `name`, `id`, `format`, `size`, `haveModules`, `colors`,
  `layerId`, `originalId`, `bipartiteStartId`, `directed`, `modules` change behaviour; anything else is inert. Python-only
  data (options, module names, scheme name, custom order) can ride in one namespaced key (e.g. `"alluvialPy": {...}`)
  for a Python → Python round trip.
- `checkColors` runs on every `setNetworks`, also inside `moveNetwork` (`S:517-557`), which re-applies the **file's** `colors`
  after writing the leaves' current indices back. That is correct until the user runs a colour op; after one, the indices
  refer to the new registry but the restored list is the file's (code reading, not run). Colour ops clear the palette first
  (`clearColors`), as for any input.

### 4.4 What this route cannot carry

custom module order, module names, layout and display options, the scheme name, stree insignificance, and the
"aggregated state names" decision when `stateId` is omitted. Duplicate identifiers make the result depend on node order;
writing nodes in original file order (as Python has them) keeps it identical to the original build.

---

## 5. `checkColors` (`S:180-210`), re-verified through `parseAcceptedFiles` **[verified]**

> **Erratum (0.5, fix round WP6: S7).** The dummy-0 bug below is fixed in TS and Python: B's `#0f0` nodes get index 1
> (fixtures `jscolors-abc__default` and `__roundTrip`). A list palette is local to its file and is remapped to the merged
> palette; colors-render §2.5 erratum.

Algorithm: v2-io §4 (unchanged). Through the real JSON path:

- `createFile` keeps any `colors` value on the NetworkFile (`["#f00","#0f0"]`, `true`, `{a: …}` all kept).
- A = `{colors: ["#f00","#0f0"]}`, nodes with `highlightIndex` 1/5/−1; B = `{colors: true}`, node `color` `#0f0`/`#00f`/`null`
  (with `highlightIndex 4`); C = `{colors: {…}}` with node `color` → `highlightColors ["#f00","#0f0","#00f"]`; B's node
  indices `{0, 2, 4}`; C ignored (indices stay unset → −1). A's 5 and B's 4 are out of range → `undefined` (black).
- **Dummy-0 bug:** B's `#0f0` was registered by A's list with index 0, so B's `#0f0` nodes get index 0 = `#f00`
  (wrong colour, no warning).
- A second `setNetworks` on the same files gives the same palette (nodes were mutated in place); `colorMatchingModulesInAllNetworks`
  then replaces it with the scheme (`rgb(198, 59, 59)`, …).
- The same list on every file → exactly that list (dedup keeps first occurrences). This is what §4 relies on; it is
  exact as long as the list has no duplicate strings, which holds for any registry built by colour ops (`getHighlightIndex`
  dedups, `S:296-312`).
- Infomap itself never writes `colors` or `color`; only hand-made, third-party, or §4 files carry them.

---

## 6. Colour schemes (`C/index.ts`, `C/seaborn-schemes.ts`, `C/matplotlib-schemes.ts`)

### 6.1 Definitions **[verified]** (dump of `COLOR_SCHEMES`: 64 entries, 62 kB as JSON)

| Group (`SCHEME_GROUPS`, `C/index.ts:220-284`) | Names, length, string format |
|---|---|
| ColorBrewer (d3 categorical) | Accent 8, Category10 10, Dark2 8, Paired 12, Pastel1 9, Pastel2 8, Set1 9, Set2 8, Set3 12, Tableau10 10 — hex |
| Seaborn | Deep, Muted, Pastel, Bright, Dark, Colorblind — 10 each, hex (literal lists) |
| Matplotlib | Tableau20, Tableau20b, Tableau20c — 20 each, hex (literal lists) |
| C3 | C3 Turbo, C3 Rainbow, C3 Sinebow, C3 Viridis — 512 each, `"rgb(r, g, b)"`; `c3.colors(512, {scheme, saturation 0.55, saturationEnd 0.8, lightness 0.5, lightnessEnd 0.9, midpoint 4.5, steepness 1})` (`C/index.ts:118-125`); duplicate strings 74/28/22/80 |
| Natural | Mural 50, hex (literal) |
| Uniform | Flare, Crest — 21 each, hex (literal seaborn) |
| Diverging, Sequential Multi, Sequential Single, Cyclical | 37 d3 interpolators sampled at `i/20`, i = 0..20 (`scheme()`, `C/index.ts:127-136`) — 21 each; `"rgb(r, g, b)"` except Viridis/Magma/Inferno/Plasma (hex); Rainbow and Sinebow have 1 duplicate (t = 0 and 1 coincide) |

`SCHEME_GROUPS` covers all 64 names but in a different order than `COLOR_SCHEMES` (Cividis…Plasma are listed under
"Sequential Multi"); the dropdown (`W/components/Sidebar/ColorSchemeSelect.tsx`) uses the group order. `C3 Sinebow` equals
`docs/dev/port-notes/data/c3-sinebow-512.json` byte for byte.

### 6.2 Store behaviour

- Default: `selectedScheme = COLOR_SCHEMES["C3 Sinebow"]` (`S:120-121`); the web app uses the package defaults
  (`W/store/Store.ts:4-6`). The ctor option `colorScheme` picks another one (`S:123-137`).
- The ctor copies the scheme into `highlightColors`, but `setNetworks` → `checkColors` replaces it (with `[]` unless a
  file has `colors`). So the scheme never reaches the palette directly.
- `setSelectedScheme(name)` (`S:236-239`) only swaps the list; it does not recolour or touch `highlightColors`.
  Later ops use it: `colorMatchingModulesInAllNetworks` (`scheme[i % L]`, colors-render §6), `colorNodesInModulesInAllNetworks`,
  `colorModuleIdsInAllNetworks`, `colorByLayer`, `colorByPhysicalId` (v2-highlight §2), and the UI for real-valued metadata
  (`W/components/Sidebar/Metadata/Real.tsx:93-130`). Manual paint picks a colour from the first 21 swatches
  (`W/components/Sidebar/Colors.tsx:57`; keys `2`…`0` = `scheme[0..8]`, `1` = default colour) and calls `colorModule`.
- `highlightColors` is derived, never chosen: each op calls `clearColors` (→ `[]`) where it does, then
  `getHighlightIndex(colour)` appends unseen strings (`S:296-312`). Example **[verified]**: ctor `colorScheme: "Paired"`
  → 12 entries; after `setNetworks` → `[]`; after `colorMatchingModulesInAllNetworks` → `["#a6cee3","#b2df8a","#33a02c"]`
  (index 1 skipped by the counter quirk, colors-render §6.1); `setSelectedScheme("Set1")` → unchanged; then
  `colorModuleIdsInAllNetworks` → the three Paired entries plus `#e41a1c`, `#377eb8`, `#4daf4a`, `#984ea3` (that op does
  not clear first).
- Duplicate strings within a scheme (C3, Rainbow, Sinebow) share one registry index, so two "different" modules can end
  up in the same highlight group.

---

## 7. What a Python writer must emit

### 7.1 Diagram JSON (`saveDiagram` port; loadable by the dead converter, the harness and possibly `/alluvial/old`)

Byte-identical to `saveDiagram` on the same store state, apart from `timestamp` (and `version`, §10 Q4):

- Top level, in order: `version`, `timestamp` (int ms), `state`, `networks`; `JSON.stringify(…, null, 2)` formatting:
  2-space indent, item separator `,` + newline, key separator `": "`, empty arrays as `[]`, empty objects as `{}`, raw
  UTF-8 (no `\uXXXX` for non-ASCII), JS escapes for control characters, JS number formatting (`_jscompat` number-to-string;
  `1e-7`, never `1e-07`; integral floats without `.0`; NaN/±Infinity → `null`), keys whose value is `undefined` omitted.
  Python `json.dumps(obj, indent=2, ensure_ascii=False)` matches this layout except for number formatting, so numbers
  must be pre-rendered.
- Per network: `id`, `name` (diagram name, else file name), `codelength` (file value; omit if absent), `moduleNames`, `nodes`.
- Per node, in `leafNodes()` order: `path` (the leaf's raw path: string, or list for JSON input), `flow` (0 if hidden),
  `name` (omit if None), `id`, `identifier`, `insignificant`, `highlightIndex`, `moduleLevel`.
- `state`: the §2.2 keys with the web names, plus `highlightColors` (the registry) and `defaultHighlightColor`.
  Colours must be CSS strings: Python `highlight_colors` accepts any matplotlib colour (`"tab:blue"`), which the web app
  cannot parse; convert with `matplotlib.colors.to_hex` at write time.
- To be loadable *with colours* by the dead converter too, add a per-network `colors` list (the full palette); `checkColors`
  then restores it (§5) and the 2019 loader ignores the key.

### 7.2 Web-app files (§4; loadable by the current app)

One JSON per network as in §4.1, nodes in **original file order** (the reader's `Node` order), `path` cleaned (no `;`),
`flow` raw, `stateId`/`layerId`/`metadata` when present, `identifier` as resolved by the reader, `highlightIndex` and
`moduleLevel` from the engine leaf, `colors` = full registry on every file, no top-level `id`. Then a `.zip` or a
directory of files. Warn when something cannot be carried: a network with `isCustomSorted`, stree insignificance,
non-default options.

---

## 8. Proposed fixture scenarios

All new; existing fixtures and `inputs` formats stay byte-identical (new optional `inputs` fields only).

### 8.1 Harness additions (`tools/ts-fixtures/harness.ts`)

- Import `saveDiagram` from `apps/web/src/io/save-diagram.js` through a second alias, with `file-saver` aliased to a
  capturing stub and `Network.prototype.getModuleNames = () => []` installed **only for the save op** (record it in
  `provenance.txt`). Pin `timestamp` (e.g. stub `Date` inside the op, or overwrite the parsed field) and `version`.
- New op `save` → the fixture gets `saved` (the exact text). New input kind `inputs.savedDiagram` (a file in `tests/data/`)
  loaded with `createFilesFromDiagramObject` + `setNetworks`, plus an optional `restoreState` flag that maps `state` to
  ctor options (§2.2) and calls `setHighlightColors(state.highlightColors)` after the build (this is not TS behaviour; it
  is what v3 decides `read` does, so it must be named in the fixture).
- New op `writeWebAppFiles` (the §4 reference writer, ~30 lines, in the harness) → `webAppFiles` texts; a scenario that loads
  them back through `parseAcceptedFiles` (as files, once as a JSZip zip).
- New op `setSelectedScheme(name)` and ctor option `colorScheme`.
- A one-off data dump `COLOR_SCHEMES` → `src/alluvial/data/schemes.json` (+ a test that compares names, order and values).

### 8.2 Scenarios

| Name | Input | Ops | Checks |
|---|---|---|---|
| `webapp-science1998__load` (`large`, opt-in like `science-stree__level2`) | `apps/web/public/data/science-1998-2001-2007.json` | `savedDiagram`, no `restoreState` | `read()` of the sample = TS converter build (311 modules, v2-io §5.4) |
| `webapp-science1998__loadState` (`large`) | same | `restoreState` | options + palette applied; group colours = Paired |
| `saved-multilevel__load` | small file produced by `save` below, committed to `tests/data/` | `savedDiagram` | committed loader fixture without the 3.5 MB file |
| `multilevel__save`, `__colored__save`, `__expanded__save`, `__expandedColored__save`, `__regroup__save`, `__moveModule__save`, `__networkName__save` | `multilevel_t*` | existing op sequences + `save` | Python writer text == `saved`; Python load of `saved` == TS load (`reload` block) |
| `planted-json__colored__save` | `planted_t*.json` | colour + `save` | array `path`s in the writer |
| `states-ftree__name__colored__save` | `states_t*.ftree`, `"name"` | colour + `save` | duplicate identifiers: reload changes streamlines in TS too (§3.4) |
| `science-stree__colored__save` | `science200{1,3}_2y.stree` | colour + `save` | raw `;` paths; reload gives module `NaN` in TS (pins the quirk; see Q3) |
| `mlayer-split__colored__save` | `mlayer_states.json`, split | colour + `save` | split layers |
| `highlight__save` | an existing `highlight` macro scenario | + `save` | palette from `highlight_colors` |
| `<same groups>__webapp` (multilevel coloured/expanded, planted JSON, states id, mlayer split, science stree) | as above | + `writeWebAppFiles` + reload | writer text equality; reload geometry; the science one pins the lost insignificance |
| `jscolors__array`, `jscolors__true`, `jscolors__dummy0`, `jscolors__thenColorMatching` | `planted_t*.json` + hand-set `colors`/`color`/`highlightIndex` (§5) | load (+ op) | the deferred `jscolors__*` of v2 |
| `scheme-<Name>__colorMatching` for Paired, Set1, Tableau20, Mural, C3 Turbo, Rainbow, Greys | `multilevel_t*` | ctor `colorScheme` + `colorMatchingModulesInAllNetworks` | hex vs rgb strings, duplicates, short schemes wrapping |
| `scheme-switch__colorModuleIds` | `multilevel_t*` | colorMatching, `setSelectedScheme("Set1")`, `colorModuleIdsInAllNetworks` | scheme switch is not a recolour (§6.2) |

---

## 9. Python port guidance

1. **Schemes first** (no IO dependency): ship `src/alluvial/data/schemes.json` dumped from TS (not re-derived from d3/c3
   in Python), `alluvial.SCHEMES` (read-only name → tuple) and `layout(..., scheme="Paired")` → `DiagramStore(scheme=…)`
   (the store already takes a list, `engine/store.py:112`, `set_selected_scheme`). Unknown name → `ValueError` listing
   close matches. `highlight_colors` keeps priority for `highlight=`; `draw(palette=…)` still overrides at draw time.
2. **`check_colors`** in `DiagramStore.set_networks` before the build, mutating the reader's own `Node` copies, exactly
   v2-io §4 (dummy 0 included); `Node.color`, `NetworkFile.colors`. `layout(colors=...)` default with input colours is
   v2-io Q4; with §4 files it must be "keep the input colours", otherwise reading a Python-written file recolours it.
3. **Reader** (`read(path)` dispatch: top-level `networks` and no `nodes`): port `createFilesFromDiagramObject` literally
   (`setIdentifiers(…, "json")` per network, key spread semantics, `size` irrelevant). Reject what TS turns into garbage
   instead of reproducing it: a string path containing `;` (TS: module `NaN`) → `ValueError` naming the network, or
   clean it with the TreePath rules (Q3). Return the networks plus a `SavedDiagram` side record (`version`, `state`,
   per-network `moduleNames`) for v3's state restore; which parts `layout()` applies by default is Q2.
4. **Writers** read the engine store, never the geometry: `leaf.highlight_index`, `leaf.module_level`, `leaf.identifier`,
   the leaf path, `network.name`, `store.highlight_colors`. Diagram JSON (§7.1) iterates `network.leaf_nodes()`;
   web-app files (§7.2) iterate the input nodes and look leaves up by identity (not by identifier, to survive duplicates).
   Use the existing JS number formatter; never `repr(float)`.
5. **Tests**: writer texts equal the harness's `saved`/`webAppFiles` byte for byte (with pinned timestamp/version); reload
   geometry equals the TS reload. Do not assert reloaded == original (§3.4, §4.2).
6. **Warnings**, not errors, for what the target cannot carry (custom order, module names, insignificance, options in
   §4 files), and for out-of-range indices in a loaded file (they render black in the web app; Python draws them with the
   out-of-range colour rule already ported).
7. Follow-ups from v2 that this enables: `read()` no longer raises for a saved diagram (`io/json_reader.py:93-97`);
   the `README` snippet list gains a save/load example.

---

## 10. Open questions

1. **Which file does `save_diagram` write?** (a) The `saveDiagram` format (§7.1): faithful port with a TS reference, but
   the current web app cannot open it (only the dead converter and possibly `/alluvial/old` can). (b) The §4 web-app files:
   opens in today's app with colours and expansion, TS reference is a harness writer (not app code), no module names/order.
   (c) Both, e.g. `format="webapp"` (default) and `"diagram"`. (b)/(c) change the v3 design's "port of the TS save code".
2. **Restoring `state` on read.** The current TS restores nothing; the 2019 app restored everything. Apply options and
   palette by default (matches what the file's author saw), or only on request (`read(..., state=True)`), or never?
3. **Stree `;` paths in a saved diagram:** reject, clean (TreePath rules, loses nothing TS keeps), or reproduce `NaN`?
   The writer side is settled: write cleaned paths in §4 files; §7.1 must write raw ones to match `saveDiagram`.
4. **`version`/`timestamp`:** write `"0.3.0"` (the only known format; ≥ 0.3.0 keeps the 2019 loader from overwriting
   identifiers) or the alluvial-py version? Add a `generator` key? Timestamp is wall-clock; make it injectable for tests.
5. **Module names:** Python has no module-name API. Write `moduleNames: []` always, or add `module_names=` to `layout`
   (would need the label/geometry contract change in v2-io §5.5)?
6. **`getModuleNames` shim in fixtures:** `() => []` (current behaviour of a fixed method for unnamed diagrams) vs a
   re-implementation of the 2019 prefix filter over `Module.name`. The latter invents semantics; recommended: `[]`.
7. **Large sample:** keep `webapp-science1998__*` opt-in (read from the TS checkout), or commit a gzipped copy (~0.5 MB)?
8. Should the §4 writer also write `layerId`/`originalId` at the top level for split layers (enables the app's
   "colour by layer"/module-id ops across layers, but the load dialog may then offer to merge/split again)?
