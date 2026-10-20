# Port note: input parsing and identifiers

Status: spec for the Python port (`alluvial` package). This note is meant to be complete enough
that you can implement the readers without reading the TypeScript (TS).
Revision 2: adversarially re-checked against the source and re-run (see "Changes in revision 2" at the end).

Sources (paths relative to the alluvial web repo root `web/alluvial/`; read-only):

| Abbrev. | Path |
|---|---|
| `IP` | `node_modules/@mapequation/infomap-parser/src/index.ts` (v1.0.2). The app runs `dist/index.js` / `dist/index.es.js`. `dist` matches `src` for every function used here (checked: `dist/index.es.js:100-124,164-166,225-251,271-305,329-333,397-474,506-578`). |
| `P/` | `packages/alluvial-diagram/src/parsers/` |
| `A/` | `packages/alluvial-diagram/src/alluvial/` |
| `U/` | `packages/alluvial-diagram/src/utils/` |
| `S/` | `packages/alluvial-diagram/src/store/` |
| `W/` | `apps/web/src/` |
| `IT` | `node_modules/@mapequation/infomap/` (typings only) |
| `IC` | Infomap C++ source of the installed Python package: `../infomap/Infomap/src/` (editable dev checkout, git `c9ce210b`, reports `2.15.1`) |
| `IPY` | its Python package `.../Infomap/interfaces/python/src/infomap/` |

All claims marked **[verified]** were checked by running the real TS code (transpiled read-only, see §11.5)
or the Python `infomap` 2.15.1 package.

---

## 0. Big picture: execution order from file to engine

```
user drops files                                   W/components/LoadNetworks/LoadNetworks.tsx:61-84
 (react-dropzone accepts .tree .ftree .stree .clu .net .json .zip   LoadNetworks.tsx:27-41)
 └─ parseAcceptedFiles(files, current, acceptedFormats, store.identifier)    P/parse-files.ts:25-86
     ├─ readAcceptedFiles: unzip *.zip, read text                            P/parse-files.ts:88-144
     └─ for each file (in order):
         format = extension(file.name) = file.name.split(".").pop()        P/parse-files.ts:42, IP:26-28
         json → JSON.parse | net → {network, haveModules:false} | else → parse(text, undefined, true, false)
         setIdentifiers(parsed.nodes, format, identifier)                   P/parse-files.ts:78
         createFile(file, format, parsed)  (+ calcStatistics)               P/parse-files.ts:79,146-171
         any exception → error entry, file skipped                         P/parse-files.ts:52-82
 (optional UI steps: identifier toggle W/.../NodeIdentifier.tsx:19-36,
  multilayer expand/merge W/.../Item/Item.tsx:107-115, run Infomap on .net W/.../Item/Item.tsx:56-97)
 └─ store.setNetworks(files)                                                S/DiagramStore.ts:217-234
     ├─ checkColors(files)          (v2: input colors → highlightIndex)    S/DiagramStore.ts:180-210
     └─ new Diagram(files)                                                  A/Diagram.ts:97-103
         └─ addNetwork(file): duplicate file.id → throw                     A/Diagram.ts:105-113
             └─ new Network(diagram, file).addNodes(file.nodes)             A/Network.ts:54-86, 273-283
                 ├─ LeafNode(node) for every node (in order); nodesByIdentifier.set(identifier, leaf)
                 └─ leaf.add() for every node (in order) → Module / HighlightGroup / Branch / StreamlineNode
```

The example data button uses a different path: `fetchScienceData()` (P/fetch-example-data.ts:6-29) parses
`science{2001,2003,2005,2007}_2y.stree` with `parse(text, undefined, true, false)`, `setIdentifiers(nodes, "stree", "name")`,
and `createFile(new File([], name), "stree", {name: "<year>", ...parsed})`, so the network names are `"2001"`, … .

The Python port replaces the browser plumbing (dropzone, zip, FileReader, `.net` + in-browser Infomap,
localforage) with plain readers. It must produce the same `NetworkFile` content. In particular it
must keep **node order** (see §8.3) and the **identifier strings** (§5).

---

## 1. Data structures

### 1.1 `Format` (P/types.ts:3-10)

`"json" | "clu" | "tree" | "ftree" | "stree" | "multilayer-expanded" | "net"`.
The format is **the text after the last `.` of the file name, case-sensitive** (P/parse-files.ts:42, IP:26-28).
`"a.TREE"` gives `"TREE"`, and a name without a dot gives the whole name (`"atree"`). Only `""` (name ending in `.`)
is rejected as "No format found" **[verified]**. `parse()` does **not** use the format, because it is called with
`type = undefined` (P/parse-files.ts:65), so the parser picks tree or clu from the header (§2.3). Only `setIdentifiers`
uses `format` (§5). For an unknown format string (`"TREE"`, `"atree"`), `setIdentifiers` is a no-op, so **every node has
`identifier === undefined`** and the file still loads **[verified]**. In the engine all such nodes then share one map key.
The Python port should take the format from an explicit argument or the lower-cased extension, and treat this TS
behaviour as a quirk that is not reproduced.

### 1.2 `Node` (P/types.ts:12-23)

| field | type | set by | read by engine (A/LeafNode.ts:42-61) |
|---|---|---|---|
| `id` | number | parser (`node_id` column) | `nodeId` |
| `flow` | number | parser | `_flow` (geometry!) |
| `stateId?` | number | parser (`state_id`) | `stateId` (`!= null` else null), identifier |
| `layerId?` | number | parser (`layer_id`) | `layerId` (`!= null` else null), multilayer expand |
| `name?` | string | parser (tree/ftree/stree), setIdentifiers (clu) | `name` (labels) |
| `identifier?` | string | setIdentifiers | **cross-network identity** |
| `path` | `string \| number[]` | parser (raw string), setIdentifiers (clu: module id string; json: array) | `new TreePath(path)` |
| `moduleId?` | number | parser (clu `module` column) | not read (only via `path`) |
| `highlightIndex?` | number | JSON input / checkColors / store write-back (S/DiagramStore.ts:537-545) | `highlightIndex` if `!= null && Number.isInteger`, else `-1` |
| `moduleLevel?` | number | JSON input / store write-back | `moduleLevel` if truthy and integer, else `1` |
| (`metadata?`) | object | JSON input only (not in the type) | `metadata` if `!= null`, else null (v2, UI only) |

Extra keys from JSON input (for example `modules` and `mec` from Infomap JSON) are carried along and ignored.
The leaf's base-class `id` is the raw `node.path` (A/LeafNode.ts:43); nothing in the layout reads it.

### 1.3 `NetworkFile` (P/types.ts:25-56)

The fields the engine reads are in **bold** (A/Network.ts:54-86, A/Diagram.ts:105-113). Everything else
is only shown in the UI.

| field | origin | engine use |
|---|---|---|
| **`id`** | `id()` = `"_" + Math.random().toString(36).substring(2, 11)` (U/id.ts:2-12, P/parse-files.ts:159). **A top-level JSON `id` overrides it** | network id. It must be unique (A/Diagram.ts:108-110) |
| **`name`** | `file.name` (the filename with its extension) unless the contents carry `name` (P/parse-files.ts:156,162) | network label |
| **`nodes`** | parser | the leaves |
| **`codelength`** | header `# codelength X bits`, or JSON `codelength` (full precision) | `Network.codelength = codelength ?? 0` (A/Network.ts:70); shown only (W/.../Sidebar/Module.tsx:116, NetworkInfo.tsx:33) |
| **`directed`** | ftree: the line right after the node section is `*Links directed`; JSON: top-level `directed` | `?? false` (A/Network.ts:72). Only feeds `createLinkMap` |
| **`modules`** | ftree `*Links <path> …` records, or JSON `modules` (no `links`) | `infomapModulesByPath`, `moduleLinks` (A/Network.ts:79-85) → `Module.enterFlow/exitFlow/links` (A/Module.ts:31-42). **Dead data**: nothing else reads these three fields (grep) |
| **`layerId`**, **`originalId`** | multilayer expand (§7) | stored |
| **`bipartiteStartId`** | header `# bipartite start id N` | `toggleShowBipartiteNodes` (A/Network.ts:100-106) |
| `format`, `filename`, `size`, `lastModified`, `haveModules` | createFile. **All of them can be overridden by top-level keys of a JSON file** (`...contents` is spread last) **[verified]** | none (but `haveModules: false` skips `calcStatistics`) |
| `version`, `args`, `startedAt`, `completedIn`, `relativeCodelengthSavings`, `flowModel`, `higherOrder`, `stateLevel`, `cluLevel` | header (§2.4) or JSON | none |
| `numLevels`, `numTopModules`, `flowDistribution`, `isMultilayer`, `isStateNetwork`, `isExpanded`, `numLayers` | calcStatistics (§6) | none (UI: W/components/LoadNetworks/Item/*.tsx) |
| `network`, `numTrials`, `twoLevel` | `.net` workflow | none |
| `layers?` | JSON input only | expand naming (§7) |
| `colors?` | JSON input only (not typed) | `checkColors` (v2) |

### 1.4 `Module` record from ftree (IT/index.d.ts:22-34, built at IP:268-285)

`{ path: number[] ([0] for root), enterFlow, exitFlow, numEdges, numChildren, links: {source, target, flow}[] }`
(`links` is `[]` because the app passes `parseLinks = true`). Missing columns become `undefined` (JS destructuring).
The typed `codelength` field is never set by the text parser. Infomap JSON modules carry `codelength` but no `links`.

---

## 2. `@mapequation/infomap-parser` (IP), exact behaviour

### 2.1 Line splitting (IP:30-33)

`lines(text) = text.split(/\r?\n/)`. A trailing newline gives a final `""` element. Lines are **not**
trimmed anywhere. A lone `\r` (classic Mac) is not a separator.
BOM: Node's `readFileSync(..., "utf8")` keeps a leading U+FEFF, and TS then rejects the file (`Invalid node line: ﻿# v…`)
**[verified]**. The browser's `FileReader.readAsText` strips a UTF-8 BOM (Encoding standard "decode"), so the app accepts it.
Python: read with `encoding="utf-8-sig"`.

### 2.2 `parseNodeHeader(lines)` (IP:340-445)

1. Scan the leading lines while they start with `#`. Stop at the first line that does not
   (IP:372-375). The first line that matches `/^#\s*(path|node_id|state_id)/` gives the header:
   `line.slice(1).trim().split(" ")` (IP:365,377-379). This also accepts `#path flow name node_id`
   without a space, as in the science `.stree` files. Note `split(" ")`: double spaces give `""` tokens, which shifts the
   columns. For example `# path flow  name node_id` has 5 columns, so every 4-token row is skipped, and the file is rejected
   as empty **[verified]**.
2. Fallback if no header comment is found: take the **first non-`#` line**. Note that an empty line counts here
   (`""` → clu branch → 1 field → throws `Invalid node line: `) **[verified]**.
   - If it contains `"`, it is a tree line. Tokenize it with `/[^\s"']+|"([^"]*)"/g` and require every token except
     token 0 (path) and token 2 (name) to be numeric. Token 0 split on `:` must also be numeric
     (`!isNaN(Number(x))`, so `""` is numeric and `1:1:1:` passes). **A headerless `.stree` whose first row has a `;`
     (`1;1;`, `1:2;3;`) fails this check and throws** **[verified]**. Then by token count:
     4 → `[path, flow, name, node_id]`, 5 → `[path, flow, name, state_id, node_id]`,
     6 → `[path, flow, name, state_id, node_id, layer_id]`. Any other count throws (IP:396-423).
   - Otherwise it is a clu line: `line.split(" ")`, all tokens numeric, then by count
     3 → `[node_id, module, flow]`, 4 → `[state_id, module, flow, node_id]`,
     5 → `[state_id, module, flow, node_id, layer_id]`. Any other count throws (IP:424-439).
   - The fallback inspects only that one line (IP:441 `break`). If every line starts with `#`, it throws `"Could not parse node header"`.

### 2.3 Dispatch `parse(text, type=undefined, parseLinks=true, strictHeader=false)` (IP:44-78; call site P/parse-files.ts:65)

```
h = parseNodeHeader(lines)
if "module" in h:                       # clu
    if h[0] == "node_id":  return parseClu(...)
    if h[0] == "state_id": return parseClu(...)
elif "path" in h:                       # tree / ftree / stree
    if h[-2] == "name" or h[-2] == "state_id" or h[-1] == "layer_id":
        return parseTree(...)           # the same function for all three variants
throw "File must be either a tree or a clu file"
```

Token → key map (IP:80-88): `node_id→id, module→moduleId, flow→flow, name→name, state_id→stateId, layer_id→layerId, path→path`.
The `.net` + in-browser Infomap path calls `parseTree(tree, undefined, true, true)`, i.e. with a **strict** header
(W/.../Item/Item.tsx:68). That is not ported.

### 2.4 `parseHeader(lines, strict=false)` (IP:447-578)

With `strict=false`, nothing throws, and the `file.length < 8` check is skipped (IP:465).

- `lines[0]` matches `/^# (v\d+\.\d+\.\d+)/` → `version` (for example `"v2.15.1"`) (IP:469-475)
- `lines[1]` matches `/^# (.+)/` → `args` (IP:477-483). Note: the science `.stree` line 1 is `#path …`, which has no space, so `args` stays unset.
- For `i = 2 …` while the line starts with `#` (IP:485-490), check each regex in this order. The first hit `continue`s.
  Lines 0 and 1 are not required to be comments: the loop always starts at index 2.

| regex | key | value |
|---|---|---|
| `/^# started at (.+)/` | `startedAt` | string |
| `/^# completed in (.+) s/` | `completedIn` | `Number` |
| `/^# partitioned into (\d+) levels with (\d+) top modules/` | `numLevels`, `numTopModules` | `Number` (later **overwritten** by calcStatistics, §6) |
| `/^# codelength (.+) bits/` | `codelength` | `Number` |
| `/^# relative codelength savings (.+)%/` | `relativeCodelengthSavings` | `Number(x) / 100` (JS division: `float(x) / 100` in Python is bit-identical) |
| `/^# flow model (.+)/` | `flowModel` | string |
| `/^# module level (\d+)/` | `cluLevel` | `Number`. `# module level -1` (written by `write_clu(depth_level=-1)`) does **not** match, so `cluLevel` stays unset **[verified]** |
| `/^# higher order/` | `higherOrder` | **bug: no capture group, so `?.[1]` is `undefined` and it is never set** (IP:540-544) |
| `/^# (state\|physical) level/` | `stateLevel` | `=== "state"` |
| `/^# bipartite start id (\d+)/` | `bipartiteStartId` | `Number` |

- Afterwards, `higherOrder` is set to `false` if it is unset. For text files it is therefore **always `false`** (IP:559-561) **[verified]**.
  (Infomap JSON carries the real flag, e.g. `true` for memory networks, and it passes through unchanged.)
- Truthiness checks are on the captured *strings*, so `"0"` is accepted.
- Unmatched lines are ignored: `# trials 2 of 2`, `# seed 123`, `# path flow …`, `# node_id module flow`, `# lossy …`.

### 2.5 Node section iterator (IP:304-318)

Iterate all lines from index 0. Skip lines that start with `#` or are empty (`""`). **Stop** at the first line that starts with `*`.
Yield `(i, line)` otherwise. (The header block is skipped because it is all `#`.) Whitespace-only lines are yielded,
and then dropped by the per-format length check (`" ".match(...)` is `null`; `" ".split(" ")` has 2 fields).

### 2.6 `parseClu` (IP:90-156)

For each node-section line:
`fields = line.split(" ").map(Number)`. If `fields.length < header.length`, skip the line silently.
Otherwise `node[map[h[k]]] = fields[k]` for each header column. Columns beyond the header are ignored.
Throw if `id`, `moduleId` or `flow` is `undefined`. Because of the length check, this only happens when the header lacks one of these columns. NaN passes.
The result is `{...header, nodes}`. Clu nodes have **no `path`/`name`** until setIdentifiers (§5).
Pitfalls that come from `split(" ")` **[verified]**: tabs → one token → the line is skipped. Leading space → `""` → `Number("") = 0`
→ columns shift (` 1 1 0.5` gives `id 0, moduleId 1, flow 1`). A trailing space adds an ignored extra field.

### 2.7 `parseTree` (IP:158-302)

Node lines (IP:194-243):
```
lineNo = 0
for (i, line) in nodeSection(lines):
    lineNo = i                                   # set BEFORE the length check
    tok = re.findall(r'[^\s"\']+|"[^"]*"', line) # JS /[^\s"']+|"([^"]*)"/g returns whole matches
    if len(tok) < len(h): continue               # (also when there is no match at all)
    for j, col in enumerate(h):
        path            -> node.path = tok[j]            # raw string, NOT split ("1:2;3;" stays as is)
        name            -> node.name = tok[j][1:-1]      # strips first+last char, quoted or not
        node_id         -> node.id = Number(tok[j])
        state_id|layer_id|flow -> node[key] = Number(tok[j])
        other           -> console.warn, ignored
    require path, flow, name, id not undefined (NaN passes) else throw
```
Name quirks **[verified]**: an unquoted name token `abc` becomes `"b"`. `""` becomes `""`. `'` is never part of a token, so an
unquoted `'x'` gives the token `x` and the name `""`. A `'` inside double quotes is fine (`"it's"`). A name containing `"`
shifts the columns (`"a"b"` → tokens `"a"`, `b`, then the next column; `id` becomes NaN). Infomap writes names raw
between quotes (IC/io/Output.cpp:216), so a name with `"` cannot round-trip. Tabs work as separators in tree files.
Use `[0-9]`/`re.ASCII` semantics in Python where JS uses `\d`; JS `\s` also matches U+FEFF, which Python's `\s` does not.

Link section (ftree; IP:245-301):
```
lineNo += 1                                   # index after the last *yielded* node-section line
if len(lines) <= lineNo + 1: return {...header, nodes}          # .tree: no 'directed', no 'modules' keys
linkHeader = lines[lineNo]
directed = linkHeader.startswith("*Links") and (parts := linkHeader.strip().split(" "))
           and len(parts) > 1 and parts[1] == "directed"
modules = []; module = None
if linkHeader.startswith("*Links"):
    for line in lines[lineNo+1:] (skipping empty lines):
        if line.startswith("*Links"):
            parts = line.split(" ")
            mid = parts[1]                    # bare "*Links" → JS undefined.split → TypeError → file rejected
            path = [0] if mid == "root" else [Number(x) for x in mid.split(":")]
            enterFlow, exitFlow, numEdges, numChildren = pad([Number(x) for x in parts[2:]], 4, None)
            module = {path, enterFlow, exitFlow, numEdges, numChildren, links: []}
            modules.append(module); continue
        if module is None: continue          # e.g. the "#*Links path enterFlow ..." comment line
        source, target, flow = pad([Number(x) for x in line.split(" ")], 3, None)
        module.links.append({source, target, flow})
return {...header, directed, nodes, modules}
```
`pad(xs, n, None)` = `(xs + [None] * n)[:n]`: JS array destructuring yields `undefined` for missing entries and ignores extra ones
(Python unpacking would raise) **[verified]**.
Infomap 2.15.1 ftree layout **[verified]** (IC/io/Output.cpp:231-253): the line after the last node is `*Links undirected` or
`*Links directed` (the word is chosen by `isUndirectedFlow()`, so flow model `undirdir` writes `undirected`),
then the comment `#*Links path enterFlow exitFlow numEdges numChildren`, then `*Links root …` and one
`*Links <module path> …` block per module, each followed by `source target flow` lines (child indices, 1-based; IC/io/OutputView.cpp:168).
Edge cases **[verified]**: a `.tree` ending in `\n\n` gets `directed:false, modules:[]`. A blank line between nodes and `*Links`
gives `directed:false, modules: []`.

### 2.8 Header and column variants (Infomap 2.15.1 output) **[verified]**

| file | node header | resulting node keys |
|---|---|---|
| first-order `.tree`/`.ftree` | `# path flow name node_id` | path, flow, name, id |
| `states=True` on a first-order net | `# path flow name state_id node_id` (state_id == node_id) | + stateId |
| memory `_states.tree` | `# path flow name state_id node_id` | + stateId |
| multilayer `_states.tree` | `# path flow name state_id node_id layer_id` | + stateId, layerId (state ids start at **0**) |
| physical tree of memory/multilayer | `# path flow name node_id` | **the same node_id can appear several times** (overlap) |
| first-order `.clu` | `# module level 1` + `# node_id module flow` | id, moduleId, flow |
| states `.clu` | `# state_id module flow node_id [layer_id]` | stateId, moduleId, flow, id [, layerId] |
| `debug5_*.stree` (sample data, Infomap v1.7.3) | `# path flow name node_id`, paths like `1:1:1:` / `1:2;3;` / `2:1;1;` | path kept raw |
| `science*_2y.stree` (sample data) | `#path flow name node_id` (no space; line 0 is `# output/…`, so no version/args) and paths like `1:1:1`, `1:1;10;`, `1;1;63;`, `1;1:235;` (no trailing `:`) | path kept raw |

The science files have **2457–3029 rows per file whose first separator is `;`** (insignificant at module level 1), so the
`;` handling of §3 matters for v1 geometry on the sample data. Every `;` path in the sample data ends in `;`.

The name column is always the **physical** node name (or the node id when unnamed). State names are never written
(IC/io/OutputView.cpp:206-213).

Infomap header lines (IC/io/Output.cpp:98-161): `# v2.15.1`, `# ./Infomap <args>`, `# started at …`, `# completed in … s`,
`# trials N of M`, `# seed S[ offset K]`, `# partitioned into L levels with T top modules`, `# codelength C bits`,
`# relative codelength savings R%`, `# flow model M`, then optionally `# higher order` and `# state level|physical level`
(both iff the network has memory), `# bipartite start id N` (iff bipartite), lossy lines, and for clu `# module level k`.
**All floats are written as `%g` = 6 significant digits** (header: fmt `{:g}`; rows: ostream precision 6) for flows,
codelength, and savings×100. This matters for §11. Bipartite **feature nodes are omitted from `.tree` and `.clu` when
`hide_bipartite_nodes` is set, but always kept in `.ftree`** (IC/io/Output.cpp:184,492,502; OutputView.cpp:185-191) **[verified]**.

---

## 3. `TreePath` (U/TreePath.ts), the only path semantics the engine uses

> **Erratum (0.5, fix round WP3: E1, E2, E3, P3).** TS and Python now share fixed semantics; the table rows for `"1:1:1:"`, `"1:"` and `"1:2;3"` below
> describe the old behaviour. (1) A path that **contains** `;` (anywhere, not only last) is parsed with the regex, so
> `"1:2;3"` gives `1:2`, `[1,2]`, `[F,T]` (the bare trailing `3` is not matched) instead of `[1,NaN]`. (2) Otherwise one
> trailing `:` is stripped **before** splitting: `"1:1:1:"` gives `[1,1,1]`, level 3 (no phantom `0`), and `"1:"` gives
> `[1]`, level 1. Array paths are kept as given. (3) `isAncestor(p, c)` is `len(p) < len(c) and c.startswith(p + ":")`,
> so `"1"` is no longer an ancestor of `"10:3"`. (4) `calcStatistics` drops an empty last segment of a string path, so
> `numLevels` of `"1:1:1:"` is 3. (5) Infomap-JSON string paths that contain `;` stay strings (`setIdentifiers` no longer
> runs them through `toArray`); other string paths still become arrays.

Constructor (U/TreePath.ts:17-52):
```
if path is list: s = ":".join(str(x) for x in path); arr = path          # same list object
else:            s = str(path);      arr = [JSNumber(x) for x in s.split(":")]
if s.endswith(";"):                                  # stree: insignificance markers
    arr, insig = [], []
    for m in re.finditer(r"([0-9]+)([:;])+", s):     # group 2 = the LAST repeated char (same in JS and Python)
        arr.append(int(m[1])); insig.append(m[2] == ";")
    s = ":".join(map(str, arr))
else:
    if s.endswith(":"): s = s[:-1]                   # arr was computed BEFORE stripping!
    insig = [False] * len(arr)
ancestor[0] = "root"; ancestor[l] = ":".join(arr[:l]) for 1 <= l < len(arr)
```
- `level` = `len(arr)` (0 for `"root"`) (U/TreePath.ts:54-56).
- `ancestorAtLevelAsString(l)` = `ancestor.get(l) || s`. This falls back to the full path string when `l >= len(arr)`
  (and if the ancestor string is `""`) (U/TreePath.ts:198-200).
- `isSignificant(l)` = `False` if `l < 0 or l >= len(insig)`, else `not insig[l]` (U/TreePath.ts:206-212).
- Static `toArray(p)` = `[JSNumber(x) for x in str(p).split(":")]` (U/TreePath.ts:157-159). The instance `toArray()` uses the
  **stripped** string `s`, so it can differ from `arr` (`"1:"`: `arr = [1, 0]`, `toArray() = [1]`).

Verified values **[verified]**:

| input | `toString` | `arr` | `insig` | level | anc(1) | anc(2) | sig(0) | sig(1) |
|---|---|---|---|---|---|---|---|---|
| `"1:1:1:"` | `1:1:1` | `[1,1,1,0]` (phantom 0) | all F | **4** | `1` | `1:1` | T | T |
| `"1:2;3;"` | `1:2:3` | `[1,2,3]` | `[F,T,T]` | 3 | `1` | `1:2` | T | F |
| `"1;2;"` | `1:2` | `[1,2]` | `[T,T]` | 2 | `1` | `1:2` | **F** | F |
| `"1;1:235;"` | `1:1:235` | `[1,1,235]` | `[T,F,T]` | 3 | `1` | `1:1` | **F** | T |
| `"1:1"` | `1:1` | `[1,1]` | `[F,F]` | 2 | `1` | `1:1` | T | T |
| `"01:2"` | `01:2` (not normalised) | `[1,2]` | `[F,F]` | 2 | `1` | `01:2` (fallback) | T | T |
| `"1:"` | `1` | `[1,0]` | `[F,F]` | 2 | `1` | `1` (fallback) | T | T |
| `"3"` (clu) | `3` | `[3]` | `[F]` | 1 | `3` (fallback) | `3` | T | F |
| `""` | `` | `[0]` | `[F]` | 1 | `` (fallback) | `` | T | F |
| `"1:2;3"` (`;` not last) | `1:2;3` | `[1,NaN]` | `[F,F]` | 2 | `1` | `1:2;3` | T | T |
| `[1,2]` (json) | `1:2` | `[1,2]` | `[F,F]` | 2 | `1` | `1:2` | T | T |

Engine use (A/LeafNode.ts):
- `moduleId = treePath.ancestorAtLevelAsString(moduleLevel)` (A/LeafNode.ts:79-81). In v1 (`moduleLevel = 1`), this is the
  first path component re-serialized from a number (`"01:2"` → `"1"`). For a single-component path (clu), it is the
  path string itself.
- `insignificant = not treePath.isSignificant(moduleLevel - 1)` (A/LeafNode.ts:63-65). In v1, a node is insignificant
  **only** if its first separator is `;` (for example `1;2;`, `1;1:235;`). Insignificant nodes go to a separate HighlightGroup
  (A/LeafNode.ts:125-127), which is covered by the layout notes.
- The phantom trailing `0` from `x:y:z:` only affected `level` (v2 expand/regroup) and `numLevels` (§6). Gone since fix
  round WP3 (erratum above).

---

## 4. JSON input (P/parse-files.ts:51-57, P/set-identifiers.ts:36-43)

`parseAcceptedFiles` expects **one network per JSON file with a top-level `nodes` array**. This is Infomap's JSON
output (`-o json`, `result.write_json`). Its shape **[verified]**:
`{version, args, startedAt, completedIn, codelength (full precision), seed, trials, numTrials, numLevels, numTopModules, numModules, relativeCodelengthSavings (fraction, full precision), directed, flowModel, higherOrder (real flag), [stateLevel], nodes:[{path:[1,1], [modules:[1]], name (always a string), flow (6 sig. digits), mec, [stateId], [layerId], id}], modules:[{path, enterFlow, exitFlow, numEdges, numChildren, codelength}]}`.
Physical-level JSON of a memory network has no per-node `modules` key. JSON flows are rounded by
`round(v * 10^(5 - floor(log10|v|))) / 10^(…)` (IC/io/Output.cpp:31-44), which is not guaranteed to be bit-identical to `float(f"{v:g}")`.
All top-level keys are spread into the NetworkFile (P/parse-files.ts:162), **after** the defaults, so `name`, `id`, `format`,
`haveModules`, `filename`, `size`, `lastModified` in the JSON win **[verified]**. JSON `modules` have no `links`, so `moduleLinks` is empty.
A JSON with `nodes: []` is rejected (§6). `JSON.parse` failure → `invalid-json`; `null` → "Could not parse file".

- The legacy diagram-save format (`{version, timestamp, state, networks:[{id, name, codelength, numLevels, numTopModules, moduleNames, nodes}]}`;
  written by W/io/save-diagram.js, for example `apps/web/public/data/science-1998-2001-2007.json`) is **rejected** by the current loader:
  `setIdentifiers(undefined, …)` throws `TypeError` → "invalid-format" **[verified]**. The converter
  `createFilesFromDiagramObject` (P/from-diagram.ts:5-32) is marked `TODO remove` and has no callers (grep).
  Its semantics are: per network, `setIdentifiers(nodes, "json")`, `size = file.size * n / totNodes`, then
  `{...file, lastModified, size, filename, haveModules:true, format:"json", ...calcStatistics(nodes), ...network}`.
  Its node fields are `{path:"1:9:443", flow, name, id, identifier, insignificant, highlightIndex, moduleLevel}`. `insignificant` is
  ignored by LeafNode (it recomputes it from the path), while `highlightIndex`/`moduleLevel` are honoured (§8.2).
- `colors` (v2, S/DiagramStore.ts:180-210), applied over all networks in order on every `setNetworks`. The store's
  `highlightColors` is then **replaced** by the collected list (first-seen order, deduped). It becomes `[]` when no file
  has `colors`, which discards the scheme copy made in the constructor (S/DiagramStore.ts:137,209,292-294).
  `colors: string[]` → colours collected, and nodes keep their own `highlightIndex`.
  `colors: true` → each node with a `color` string gets `highlightIndex` = the index of the colour in the global list.
  Bug: if that colour was first collected from a `colors: string[]` file, its stored index is the dummy `0` (line 190), so the node gets 0.
  (Fixed in fix round WP6, S7: real indices, and each list palette is remapped to the merged one; colors-render §2.5.)
- `metadata` per node: v2/UI only (A/Network.ts:108-150).

---

## 5. Identifiers: `setIdentifiers(nodes, format, identifier="id")` (P/set-identifiers.ts:9-55)

`Identifier = "id" | "name"` (A/LeafNode.ts:11). The app default is `"id"` (S/DiagramStore.ts:76). The example data
uses `"name"` (P/fetch-example-data.ts:17), and so do the app tests (W/test/data-flow.test.ts:21).
**Python default: `identifier="id"`** for every reader. This is the store default, and it is what the fixtures' `default` variants use.
`name` is opt-in (fixture variants `name`, `nameColored`). It matters for similarity colouring: the science example
only matches across years with `"name"` (colours note §6.1).

```
stateOrNodeId(n) = n.stateId if n.stateId is not None else n.id   # `!= null`: stateId 0 is kept
idfn(n) = js_num_str(stateOrNodeId(n))                       if identifier == "id"
          n.name if n.name is not None else js_num_str(stateOrNodeId(n))   if identifier == "name"
          None (undefined)                                   otherwise

format == "multilayer-expanded": n.identifier = js_num_str(n.id)    # physical id, ignores the mode
format == "json":   n.identifier = n.identifier if n.identifier is not None else idfn(n)
                    if path is not a list: n.path = TreePath.toArray(n.path)   # "1:2;3;" -> [1, NaN]; 3 -> [3]
format in ("tree","ftree","stree"): n.identifier = idfn(n)
format == "clu":    n.path = js_num_str(n.moduleId); n.identifier = js_num_str(stateOrNodeId(n)); n.name = js_num_str(n.id)
                                                      # ignores the mode; overwrites name
other ("net", "TREE", ...): nothing                   # identifier stays undefined (§1.1)
```
`js_num_str` is JS `Number.prototype.toString`: an integer-valued number prints without `.0` (`12` → `"12"`), `NaN` → `"NaN"`,
`-0` → `"0"`, `1e21` → `"1e+21"`, `1e-7` → `"1e-7"` (Python `repr` gives `"1e-07"`). Parse ids as `int` when integral.
A JSON `path` that is missing makes `TreePath.toArray(undefined)` throw → file rejected.

Re-application when the user toggles the mode (W/components/LoadNetworks/NodeIdentifier.tsx:19-36):
files with `isExpanded` are skipped. A `"net"` file that has modules is re-run as `"ftree"`. Everything else is re-run with its own `format`.
**Quirks**: for `json`, the existing `identifier` wins, so toggling has no effect; for `clu`, the mode is ignored anyway.
`mergeMultilayerFiles` always uses mode `"id"` (P/multilayer-utils.ts:37). That is a bug if the user picked `"name"` **[verified]**.

Identity semantics (all exact, case-sensitive string equality):
- `Network.addNodes` (A/Network.ts:273-283) first builds `nodesByIdentifier` with `Map.set` for every node in order. **The last
  node with a given identifier wins**, but **all** nodes are added to the tree afterwards (`leaf.add()` in order).
- `Network.getLeafNode(identifier)` (A/Network.ts:323-325) is used by `LeafNode.add` to find the same node in the
  neighbour network (A/LeafNode.ts:133-141). The neighbour is the network at index ±1 in `diagram.children` (A/Network.ts:301-321).
  While network *k* is added, network *k+1* does not exist yet. Linking order is covered in the streamline note.
- Duplicates occur in practice: physical trees of memory/multilayer networks (the same `node_id` in several modules), and
  `"name"` mode with non-unique names (the UI tooltip says names must be unique: NodeIdentifier.tsx:38-48).

---

## 6. `createFile` + `calcStatistics` (P/parse-files.ts:146-171, P/calc-statistics.ts:1-45)

Merge order (later keys override earlier ones):
`{...File own props, filename: name, name, lastModified, size, id: id(), haveModules: true, format, ...contents}`.
(A browser `File` has no own enumerable props; zip entries are plain `{name, size, lastModified}` objects.)
Then, if `haveModules` (truthy), `Object.assign(file, calcStatistics(file.nodes))`, which **overwrites** the header's `numLevels`/`numTopModules`.

```
calcStatistics(nodes):
  flowDistribution = {}  (JS object: array-index keys iterate ascending, then others like "NaN" in insertion order)
  layerIds = set(); top = set(); numLevels = 0
  for n in nodes (in order):
      parts = n.path if list else (n.path.split(":") if n.path is not None else [])   # raw string, NOT TreePath
      t = JSNumber(parts[0])                       # parts == [] -> Number(undefined) = NaN
      top.add(t); numLevels = max(numLevels, len(parts))
      acc = flowDistribution.get(t)
      if not acc or isnan(acc): acc = 0            # JS `!x`: undefined, 0 AND NaN reset the sum to 0
      flowDistribution[t] = acc + (n.flow if n.flow is not None else 0)   # left-to-right float sum
      if n.layerId is not undefined: layerIds.add(n.layerId)
  isMultilayer   = nodes[0].layerId !== undefined          # nodes == [] → TypeError → file rejected
  isStateNetwork = nodes[0].stateId !== undefined
  return {flowDistribution, isMultilayer, isStateNetwork,
          isExpanded: False if isMultilayer else undefined,   # the key is assigned even when undefined
          numLayers: len(layerIds) or undefined, numTopModules: len(top), numLevels}
```
Quirks **[verified]**: `"1:1:1:"` counts 4 levels. `"1:2;3;"` splits into `["1","2;3;"]`, so it counts 2 levels with top `1`. `"1;2;"` gives top `NaN`.
JS `Set` and object keys treat all NaNs as one value (`numTopModules` counts NaN once): in Python use **one shared NaN object**
(`_NAN = float("nan")`), because distinct NaN objects are distinct set/dict members. Python `x or 0` does **not** reset NaN (NaN is truthy in Python).
Clu (after setIdentifiers) always gives `numLevels = 1`. An empty node list throws, so **an empty file is rejected**. None of these
values affect geometry.

---

## 7. Multilayer expand / merge (P/multilayer-utils.ts) (optional in v1, a load-time transform)

`expandMultilayerFile(file, files)` (lines 45-92), requires `file.isMultilayer` (else throws):
1. `setIdentifiers(file.nodes, "multilayer-expanded")`. This **mutates the shared node objects** so that `identifier = str(id)`.
2. `file.isExpanded = true`.
3. For each node in order, if this is the first time `layerId` is seen: `layer = shallow copy of file` (so it **inherits**
   `codelength`, `modules`, `directed`, `bipartiteStartId`, `filename`, `format`, …), `id = id()`, `originalId = file.id`, `layerId`,
   `nodes = []`, and `name = file.layers?.find(l => l.id === layerId)?.name ?? "Layer " + layerId` (strict `===`).
   Then append the node to its layer.
4. For each layer, apply `calcStatistics(layer.nodes)` and `isExpanded = true` (so each layer has `isMultilayer = true`, `numLayers = 1`).
5. Replace `file` in `files` with the layers in **`Object.values` order, which is ascending numeric `layerId`** (JS integer-key
   order, *not* first-seen order) **[verified: layer ids first seen as 3, 1 → "Layer 1", "Layer 3"]**.

`mergeMultilayerFiles(file, files)` (lines 6-43), requires `file.isMultilayer`: takes a shallow copy of `file`, `name = filename`,
`id = originalId`, `originalId = undefined`, `layerId = undefined`. `nodes` = the concatenation of all parts with `isMultilayer`
and the same `originalId` in `files` order. `calcStatistics` is applied, `isExpanded = false`.
`setIdentifiers(nodes, "tree")` uses mode `"id"`. The merged file is inserted at the first part's index.
**Expand → merge is not the identity**: node order becomes layer-major (rows `10,11,12,13` in layers `3,1,1,3` come back as
`11,12,10,13`), which can change module creation order and therefore tie-breaks (§8.3), and `"name"` identifiers become state ids **[verified]**.

---

## 8. From `NetworkFile` to engine objects (what the reader must feed)

### 8.1 Network (A/Network.ts:54-86, 273-283)
`name`, `codelength ?? 0`, `layerId`, `directed ?? false`, `originalId`, `bipartiteStartId` (default `NOT_BIPARTITE = -1`, A/Network.ts:36;
set whenever the key is not `undefined`).
If `modules` is set: `infomapModulesByPath[path.join(":")] = module`, and `moduleLinks = createLinkMap(modules, directed)` (A/Network.ts:456-483).
In `createLinkMap`, the prefix is `""` for the root (`path[0] == 0`), else `moduleId + ":"`. Each link adds
`source→target` and, when undirected, also `target→source`. Both only feed `Module.enterFlow/exitFlow/links` (A/Module.ts:31-42),
which nothing reads, so a v1 port may drop `modules`/`directed` without geometric effect. The fixtures do record them,
though: `modules[j].enterFlow/exitFlow` are non-zero for every `*-ftree` group (the Module ctor looks up
`infomapModulesByPath.get(moduleId)`, A/Module.ts:31-36), and `networks[i].file.directed` is `true/false` for ftree
and `null` otherwise. Either keep the ftree module records (cheap) or skip those fields in the parity tests.

### 8.2 LeafNode (A/LeafNode.ts:42-61)
`name = node.name`, `_flow = node.flow`, `nodeId = node.id`, `stateId = node.stateId if != null else null`, `layerId` likewise,
`metadata` likewise, `identifier = node.identifier`, `treePath = TreePath(node.path)` (throws on `undefined` path),
`highlightIndex = node.highlightIndex if (!= null and Number.isInteger) else -1` (`NOT_HIGHLIGHTED`, A/HighlightGroup.ts:7),
`moduleLevel = node.moduleLevel if (node.moduleLevel and Number.isInteger(node.moduleLevel)) else 1` (`0` → `1`).
`flow` getter returns 0 when `visible` is false (A/LeafNode.ts:67-69). `visible` is only toggled by the bipartite switch:
`visible = nodeId >= bipartiteStartId ? show : true` (A/Network.ts:100-106). The store default is `showBipartiteNodes = true`
(S/DiagramStore.ts:118), so there is no effect by default.

### 8.3 Order matters
`addNodes` processes nodes **in NetworkFile order** (A/Network.ts:276-282). `leaf.add()` creates a Module the first time its
`moduleId` is seen (A/LeafNode.ts:121-123), and `Module.index = parent.addChild(this) - 1` (A/Module.ts:29). So module
creation order, and therefore every stable-sort tie-break downstream, comes from **file row order**. The readers must therefore:
never sort, dedupe or dict-group nodes; keep file order (Infomap writes depth-first tree order); and keep the
Infomap object iteration order (§11).

---

## 9. Edge cases (summary; all **[verified]** unless noted)

| case | behaviour |
|---|---|
| empty file / no node rows | `calcStatistics` throws → file rejected (§6) |
| zero-flow nodes (for example bipartite feature nodes, written as `0`) | parsed normally. Flow is 0 in `flowDistribution` and geometry |
| dangling nodes | nothing special at parse time (flow is whatever Infomap wrote) |
| NaN / garbage numbers | pass the parser (only `undefined` is checked); NaN flows reset the `flowDistribution` sum (§6). **Fix round WP4 (E9):** `parseAcceptedFiles` then rejects a file with a non-finite or non-numeric flow (`invalid-format`, `validateNetworkNodes`; `.net` is skipped), and Python's `create_file` raises `ValueError` |
| header-less file | inferred from the first data line (§2.2); header-less `.stree` with `;` paths is rejected |
| CRLF | handled (§2.1). Tabs: ok in tree, break clu. BOM: rejected by Node, stripped by the browser |
| unquoted tree name | `name[1:-1]` (§2.7) |
| duplicate identifiers | last one wins in lookup, and every node is still added (§5). **Fix round WP5 (E6):** only the registered (last) duplicate links across networks, the others stay dangling, and `parseAcceptedFiles` returns a non-fatal `duplicate-identifiers` warning (`warning: true`) per file. Before: Usually all nodes are drawn, but **not always**: two same-group duplicates in network *k* that match a node in *k−1* produce `NULL--…` streamline ids, and can drop a leaf from its LEFT branch (streamlines note §3.3). Duplicates in different groups demote the earlier match to dangling. Fixtures `states-tree__name*` contain (benign, different-group) duplicates, so readers must not drop or merge them in parity mode |
| `stateId == 0` | kept (`!= null`); identifier `"0"` |
| `.clu` file with tree content | parser follows the header (tree), setIdentifiers follows the extension → `moduleId.toString()` on undefined → **rejected** |
| `.tree`/`.ftree`/`.stree` file with clu content | parsed as clu, identifiers set, **accepted at load** (no `path`, `flowDistribution {NaN: …}`, `numLevels 0`); it crashes later in `new Diagram` (`TreePath(undefined)`) |
| unknown/uppercase extension | loads with `identifier` undefined on every node (§1.1) |
| JSON top-level `id`/`name`/`format`/`haveModules` | override the defaults (§1.3); two files with the same `id` → `Diagram.addNetwork` throws |
| single network | no special parse handling |
| JSON without `nodes` | rejected |
| ftree line `*Links` without a module id | `undefined.split` → rejected (from source, not run) |

---

## 10. v1 / v2 split for this area

| item | version |
|---|---|
| tree/ftree/stree/clu node sections + header (§2), TreePath incl. `;`/trailing `:` (§3), identifiers (§5), stats (§6, optional) | **v1** |
| Infomap object reader (§11), Infomap JSON reader (§4) | **v1** |
| ftree `*Links` module records (`modules`, `directed`) | v1-optional (dead data in the engine) |
| bipartite toggle (§8.2) | v1-optional (default no-op) |
| multilayer expand/merge (§7) | v1-optional |
| input `moduleLevel` (hierarchy), `highlightIndex`/`colors` (highlight API), `metadata` | **v2** (still apply the §8.2 normalisation in v1; the colours note §2.5 treats `checkColors` as v1-optional). v1 colours come from the post-build colour ops, not from input fields |
| `.net` + in-browser Infomap, zip, localStorage (P/localstorage-utils.ts), legacy diagram JSON | not ported (open question for the legacy JSON) |

---

## 11. `infomap.Infomap` (Python 2.15.1) → `NetworkFile`

### 11.1 Python API facts **[verified]**
- `result = im.run()` returns `infomap.result.Result`. `im._result is result`. The old `im.get_tree()`, `im.tree` and
  `im.codelength` still work but emit `LegacySurfaceWarning` (a `DeprecationWarning` subclass, IPY/_options.py:36: "leaves in 3.0").
  Use the `Result`.
- `result.nodes(depth=1, *, states=False)` (IPY/result.py:770-807) yields **leaf** `TreeNode` snapshots in depth-first order,
  which is **identical to the row order Infomap writes** for both physical and state views (including multilayer, where the
  physical order differs from the state order). The default is `states=False` **even for memory networks**.
  `result.tree(depth, states=)` yields live, generation-guarded `InfomapIterator` objects for modules and leaves
  (`path=()` root, `(1,)`, …; `.is_leaf`, `.flow`, and `.data.enterFlow/.data.exitFlow` for modules).
- `TreeNode` fields (IPY/result.py:146-192): `path: tuple[int,...]` (1-based), `flow: float` (full precision), `node_id`, `state_id`
  (equals `node_id` in first-order nets; starts at 0 in multilayer), `layer_id` (0 unless multilayer), `name`
  (physical name; **an `int` node_id when unnamed**. The file writes it quoted, as `"3"`), `state_name`, `module_id` (module
  index at the requested `depth`; for `depth=1` it equals `path[0]`), `child_index`, `depth`, `modular_centrality`.
- `states=False` on a memory or multilayer net gives *physical* leaves. State nodes of one physical node in the same module are
  merged (summed flow); the same physical node repeats across modules. `states=True` on a first-order net still writes a
  `state_id` column. `result.modules()` raises `InfomapError` on higher-order nets without `states=True`.
- `result.have_memory` is True for memory and multilayer nets. `im.network.is_multilayer_network` is a **property** (bool).
  `im.bipartite_start_id` is 0 when not bipartite. `result.codelength` is in bits; `result.relative_codelength_savings` is a fraction
  (the file writes ×100 with `%`).
- Directedness of the ftree `*Links` line: `result._directed` (private, IPY/result.py:347) = `not im._core.isUndirectedFlow()`.
  **Do not use `printAsUndirected()`**: it differs for flow model `undirdir` (`printAsUndirected() == False`, but the ftree says
  `undirected`) (IC/io/Config.h:351-355) **[verified]**. There is no public accessor for the flow model.
- `hide_bipartite_nodes` (deprecated kwarg) is readable only privately as `im._core._im.hideBipartiteNodes`.
- Names: `result.names` gives `{node_id: name}` only for named nodes.

### 11.2 Field mapping (target = what the TS app yields for the file written by `result.write_tree/write_flow_tree/write_clu(path, states=s)`)

| NetworkFile | from Infomap object |
|---|---|
| node order | `for n in result.nodes(depth, states=s)` with `depth = 1` (tree/ftree) or the clu `depth_level` |
| row filter | tree/clu only: drop `n.node_id >= im.bipartite_start_id` when bipartite and `hideBipartiteNodes` is set |
| `path` (tree/ftree) | `":".join(map(str, n.path))` |
| `flow` | `float(f"{n.flow:g}")` (file parity). With `exact`, use `n.flow` |
| `name` (tree/ftree) | `str(n.name)` |
| `id` | `n.node_id` |
| `stateId` | `n.state_id` iff `s` is True (even for first-order nets) |
| `layerId` | `n.layer_id` iff `s and im.network.is_multilayer_network` |
| clu `moduleId` / `path` / `name` | `n.module_id` (at the clu `depth_level`) / `str(n.module_id)` / `str(n.node_id)` |
| `identifier` | as §5 (`clu`: always `str(stateId ?? id)`) |
| `codelength` | `float(f"{result.codelength:g}")` |
| `relativeCodelengthSavings` | `float(f"{100*result.relative_codelength_savings:g}") / 100` |
| `higherOrder` | `False` (TS bug, §2.4) |
| `stateLevel` | `bool(s)` iff `result.have_memory` (else absent) |
| `cluLevel` | the clu `depth_level` iff `>= 0` (`-1` does not match the regex) |
| `bipartiteStartId` | `im.bipartite_start_id` if non-zero |
| `directed` | ftree only: `result._directed` |
| `version` | `f"v{infomap.__version__}"` |
| stats | `calc_statistics(nodes)` (§6) |
| `modules` (ftree), `args`, `startedAt`, `completedIn`, `flowModel`, `name`/`filename`/`id`/`size`/`lastModified` | not reproduced (dead data, UI or bookkeeping only) |

Default for `s`: `result.have_memory`. This mirrors the app's own Infomap runner, which prefers `ftree_states || ftree`
(W/components/LoadNetworks/Item/Item.tsx:65) and avoids duplicate physical identifiers.

### 11.3 Reference implementation (executed; `tmp-scratch/im2nf.py`, deleted afterwards)

```python
"""Infomap (2.15.1) Result -> NetworkFile dict, matching what the TS app yields for the written file."""

import infomap


def _g(x: float) -> float:
    # Infomap text writers: C++ ostream precision 6 (rows) / fmt "{:g}" (header) == "%g".
    return float(f"{x:g}")


def network_file_from_infomap(
    result, im, *, fmt="tree", states=None, identifier="id", exact=False, clu_level=1
):
    """fmt: 'tree' | 'ftree' | 'clu'. states=None -> result.have_memory."""
    if states is None:
        states = result.have_memory
    multilayer = bool(states) and im.network.is_multilayer_network
    num = (lambda x: x) if exact else _g
    # .tree/.clu honour --hide-bipartite-nodes, .ftree never does (Output.cpp:184,492,502)
    hide = (
        fmt != "ftree" and im.bipartite_start_id > 0 and im._core._im.hideBipartiteNodes
    )  # private flag; see note
    depth = clu_level if fmt == "clu" else 1
    nodes = []
    for n in result.nodes(depth, states=states):  # depth-first == file row order
        if hide and n.node_id >= im.bipartite_start_id:
            continue
        if fmt == "clu":
            node = {"id": n.node_id, "moduleId": n.module_id, "flow": num(n.flow)}
            if states:
                node["stateId"] = n.state_id
            if multilayer:
                node["layerId"] = n.layer_id
            node["path"] = str(node["moduleId"])  # set-identifiers.ts:48-53
            node["identifier"] = str(node.get("stateId", node["id"]))
            node["name"] = str(node["id"])
        else:
            node = {
                "path": ":".join(map(str, n.path)),
                "flow": num(n.flow),
                "name": str(n.name),
                "id": n.node_id,
            }
            if states:
                node["stateId"] = n.state_id
            if multilayer:
                node["layerId"] = n.layer_id
            sid = str(node.get("stateId", node["id"]))
            node["identifier"] = sid if identifier == "id" else node["name"]
        nodes.append(node)

    nf = {
        "format": fmt,
        "haveModules": True,
        "nodes": nodes,
        "version": f"v{infomap.__version__}",
        "codelength": num(result.codelength),
        "relativeCodelengthSavings": (
            result.relative_codelength_savings
            if exact
            else _g(100 * result.relative_codelength_savings) / 100
        ),
        "higherOrder": False,
    }  # TS parser never sets it true
    if result.have_memory:
        nf["stateLevel"] = bool(states)
    if fmt == "clu" and clu_level >= 0:  # "# module level -1" fails /(\d+)/
        nf["cluLevel"] = clu_level
    if im.bipartite_start_id:
        nf["bipartiteStartId"] = im.bipartite_start_id
    if fmt == "ftree":
        nf["directed"] = result._directed  # == ftree "*Links directed" (private)
    nf.update(calc_statistics(nodes))
    return nf


def calc_statistics(nodes):
    """calc-statistics.ts:1-45."""
    flow_distribution, layer_ids, top_modules, num_levels = {}, set(), set(), 0
    for node in nodes:
        parts = node["path"] if isinstance(node["path"], list) else node["path"].split(":")
        top = _js_number(parts[0])
        top_modules.add(top)
        num_levels = max(num_levels, len(parts))
        acc = flow_distribution.get(top)
        if not acc or acc != acc:  # JS `!x`: undefined, 0 and NaN reset to 0
            acc = 0
        flow = node.get("flow")
        flow_distribution[top] = acc + (0 if flow is None else flow)
        if "layerId" in node:
            layer_ids.add(node["layerId"])
    is_multilayer = "layerId" in nodes[0]  # TS throws on empty nodes
    out = {
        "flowDistribution": flow_distribution,
        "isMultilayer": is_multilayer,
        "isStateNetwork": "stateId" in nodes[0],
        "numTopModules": len(top_modules),
        "numLevels": num_levels,
    }
    if is_multilayer:
        out["isExpanded"] = False
    if layer_ids:
        out["numLayers"] = len(layer_ids)
    return out


_NAN = float("nan")  # one shared object: set/dict dedupe it like JS Set/object keys do


def _js_number(s):
    """JS Number(token) for a path component: '' -> 0, junk -> NaN, integral -> int."""
    if isinstance(s, (int, float)):
        return s
    t = s.strip()
    if not t:
        return 0
    try:
        v = float(t)
    except ValueError:
        return _NAN
    return int(v) if v.is_integer() else (_NAN if v != v else v)
```
(`_js_number` here is only good enough for Infomap-written paths; the full `js_number` needs the §12 pitfall 2 rules.)

### 11.4 Tiny seeded example (executed from `tmp-scratch/`; output pasted verbatim)

```python
import json, os, subprocess, warnings

warnings.simplefilter("ignore")  # LegacySurfaceWarning from infomap internals
import infomap
from im2nf import network_file_from_infomap  # §11.3

im = infomap.Infomap(silent=True, seed=3, num_trials=2)  # memory (state) network
for state_id, node_id in [(1, 1), (2, 2), (3, 2), (4, 3), (5, 4), (6, 1)]:
    im.add_state_node(state_id, node_id)
im.add_links([(1, 2), (2, 1), (2, 6), (6, 1), (3, 4), (4, 5), (5, 3), (4, 3)])
im.set_name(2, "two")
result = im.run()

SKIP = {"name", "filename", "args", "startedAt", "completedIn", "flowModel", "modules"}
os.makedirs("out2", exist_ok=True)
for fmt, write in [("tree", result.write_tree), ("ftree", result.write_flow_tree), ("clu", result.write_clu)]:
    for states in (True, False):
        path = os.path.abspath(f"out2/example{'_states' if states else ''}.{fmt}")
        write(path, states=states)
        ts = json.loads(
            subprocess.run(["node", "run.mjs", "id", path], cwd="ts", capture_output=True, text=True).stdout
        )[0]
        py = network_file_from_infomap(result, im, fmt=fmt, states=states, identifier="id")
        ts["flowDistribution"] = {float(k): v for k, v in ts["flowDistribution"].items()}
        same = {k for k in ts if k not in SKIP} == set(py) and all(ts[k] == v for k, v in py.items())
        print(f"{os.path.basename(path):20s} equal={same}")

nf = network_file_from_infomap(result, im, fmt="tree")  # states=True by default (have_memory)
for n in nf["nodes"]:
    print(n)
print({k: v for k, v in nf.items() if k != "nodes"})
phys = network_file_from_infomap(result, im, fmt="tree", states=False)
print([(n["path"], n["identifier"], n["flow"]) for n in phys["nodes"]])
```
Output:
```
example_states.tree  equal=True
example.tree         equal=True
example_states.ftree equal=True
example.ftree        equal=True
example_states.clu   equal=True
example.clu          equal=True
{'path': '1:1', 'flow': 0.1875, 'name': '1', 'id': 1, 'stateId': 1, 'identifier': '1'}
{'path': '1:2', 'flow': 0.1875, 'name': 'two', 'id': 2, 'stateId': 2, 'identifier': '2'}
{'path': '1:3', 'flow': 0.125, 'name': '1', 'id': 1, 'stateId': 6, 'identifier': '6'}
{'path': '2:1', 'flow': 0.1875, 'name': 'two', 'id': 2, 'stateId': 3, 'identifier': '3'}
{'path': '2:2', 'flow': 0.1875, 'name': '3', 'id': 3, 'stateId': 4, 'identifier': '4'}
{'path': '2:3', 'flow': 0.125, 'name': '4', 'id': 4, 'stateId': 5, 'identifier': '5'}
{'format': 'tree', 'haveModules': True, 'version': 'v2.15.1', 'codelength': 1.25786, 'relativeCodelengthSavings': 0.331943, 'higherOrder': False, 'stateLevel': True, 'flowDistribution': {1: 0.5, 2: 0.5}, 'isMultilayer': False, 'isStateNetwork': True, 'numTopModules': 2, 'numLevels': 2}
[('1:1', '1', 0.3125), ('1:2', '2', 0.1875), ('2:1', '2', 0.1875), ('2:2', '3', 0.1875), ('2:3', '4', 0.125)]
```
The comparison checks that the key sets are equal (apart from `SKIP`) and that every value is equal. The physical view (last line)
contains node `2` twice (in modules 1 and 2) with identifier `"2"`, and node 1's two states are merged (0.1875 + 0.125).

Broader verification: 9 seeded nets (first-order undirected with names containing a space and `'` `seed=123`; the same directed;
the same with `flow_model="undirdir"`; 3-level hierarchical `seed=7`; the same with `two_level=True`; memory `seed=3`; multilayer `seed=5`;
bipartite start id 10 `seed=11` with `hide_bipartite_nodes` False/True) × `states ∈ {False, True}` × `{tree, ftree, clu}` × identifier
`{id, name}` = **108/108 equal** on every key except `name, filename, args, startedAt, completedIn, flowModel, modules`.
In addition, `write_clu(depth_level=2|3)` matches with `clu_level=2|3`, and `depth_level=-1` matches once `cluLevel` is omitted.

Precision: `exact=True` flows differ from the file values by up to half a unit in the 6th significant digit (≈5e-6 relative), and the file flows of one network
need not sum to 1 (for example 1.000001). That is far above a geometry tolerance, so **fixture-parity mode must use `%g` rounding**.
`exact=True` is fine for users who do not compare against TS.

### 11.5 Fixture harness (how the TS side was run without touching the web repo)
`node_modules/typescript` is v7.0.2 (native) and has no JS `transpileModule`. Vite 8.3.4's `transformWithOxc` works.
Run both scripts from `alluvial-py/tmp-scratch/ts/` with Node 24:
```js
// build.mjs — writes ./out/{parsers,utils}/*.js (ESM)
import fs from "node:fs"; import path from "node:path";
const REPO = "../web/alluvial";
const { transformWithOxc } = await import(REPO + "/node_modules/vite/dist/node/index.js");
for (const f of ["parsers/parse-files.ts","parsers/set-identifiers.ts","parsers/calc-statistics.ts",
                 "parsers/multilayer-utils.ts","utils/TreePath.ts","utils/id.ts"]) {
  let { code } = await transformWithOxc(fs.readFileSync(`${REPO}/packages/alluvial-diagram/src/${f}`, "utf8"), f, { lang: "ts" });
  code = code.replace(/^import \{ Identifier \} from "\.\.\/alluvial";\n/m, "")          // type-only import
             .replace(/from "(\.\.?\/[^"]+)"/g, (m, p) => `from "${p}.js"`)
             .replace('from "@mapequation/infomap-parser"', `from "${REPO}/node_modules/@mapequation/infomap-parser/dist/index.es.js"`)
             .replace('from "jszip"', `from "${REPO}/node_modules/jszip/lib/index.js"`);
  const out = path.join("out", f.replace(/\.ts$/, ".js"));
  fs.mkdirSync(path.dirname(out), { recursive: true }); fs.writeFileSync(out, code);
}
fs.writeFileSync("out/package.json", JSON.stringify({ type: "module" }));

// run.mjs — mirrors P/parse-files.ts:42-82. Usage: node run.mjs <id|name> <file>... → JSON array
const { parse, extension } = await import(REPO + "/node_modules/@mapequation/infomap-parser/dist/index.es.js");
const { setIdentifiers } = await import("./out/parsers/set-identifiers.js");
const { createFile } = await import("./out/parsers/parse-files.js");
// per file: fmt = extension(basename); parsed = fmt === "json" ? JSON.parse(text) : parse(text, undefined, true, false);
// setIdentifiers(parsed.nodes, fmt, identifier); nf = createFile({name, size: 0, lastModified: 0}, fmt, parsed);
// delete nf.id, nf.size, nf.lastModified; on exception push {error, name}
```
The scratch files were deleted after verification. Re-create them under `alluvial-py/tmp-scratch/` when
generating parser fixtures. JSON loses `NaN`/`undefined` (they become `null`/absent), so compare those cases in Node or by key presence.

---

## 12. Python port guidance

Suggested structure:
```
alluvial/io/
  _jsnum.py        js_number(token) (Number semantics), js_num_str(x) (Number#toString for ids)
  infomap_text.py  parse_node_header, parse_header, parse_clu, parse_tree (+ link section), parse(text)
  identifiers.py   set_identifiers(nodes, fmt, identifier="id")      # exact §5 rules, mutates in place
  network_file.py  NetworkFile / Node dataclasses (keep `path` raw: str | list[int]); create_file, calc_statistics
  readers.py       read_file(path, identifier="id", name=None, fmt=None) → NetworkFile   (fmt default: extension)
                   from_infomap(result, im, fmt="tree", states=None, identifier="id", exact=False, clu_level=1)
                   from_infomap_json(dict)
  multilayer.py    expand / merge (optional)
alluvial/tree_path.py  TreePath exactly as §3 (incl. phantom 0 and `;` regex semantics)
```

Pitfalls:
1. **Do not normalise paths at parse time.** Keep the raw string. `TreePath` does the `;`/`:` handling, and `calc_statistics`
   deliberately works on the raw string.
2. `js_number` ≠ `float`: `""`/whitespace→0, `" 12 "`→12, `"0x10"`→16, `"0b11"`→3, `"0o7"`→7, `"-0x10"`→NaN, `"1_0"`→NaN (Python accepts `1_0`),
   `"inf"`/`"nan"`→NaN, `"Infinity"`/`"-Infinity"`→±inf, `".5"`/`"5."`/`"+5"`/`"1e3"` as in Python. Use it for ids, flows and path
   components. Flow tokens written by Infomap parse identically with `float()`.
3. Identifier strings: `str(12.0)` is `"12.0"` in Python and `"12"` in JS. Store integral ids as `int`, and use `js_num_str` (§5) otherwise.
4. Use `is not None` (not truthiness) for `stateId`, because `0` is valid. Use truthiness *only* where TS does
   (`moduleLevel`: `0` → 1; the `flowDistribution` accumulator, where NaN also counts as falsy).
5. Keep row order. Never build nodes from `result.modules()` / `multilevel_modules()`: they are dicts and drop overlapping physical
   nodes. Use `result.nodes(states=...)`.
6. Duplicate identifiers: a plain dict assignment loop reproduces "last wins". Still add every node.
7. `higherOrder` is always False for text input. If you want the real flag, add a separate attribute; do not change parity fields.
8. Multilayer expansion order is ascending numeric `layerId`, not first-seen order; merge reorders rows layer-major.
9. For tests, compare Python readers on the *same files* the TS fixtures were built from. For the Infomap object reader,
   use `exact=False`.
10. `name` of a network defaults to the filename (incl. extension) in TS. For `from_infomap`, take it from a `name=` argument.
    The network **id** is random in TS (`U/id.ts`). It ends up in every module, group, streamline and link id string, so the
    fixtures pin it to the **file stem** (`inputs.networkIds`, e.g. `planted_t0`). File readers should default `network_id` to
    the stem and accept an override. `from_infomap` needs an explicit or generated deterministic id. Reject duplicate ids and
    ids containing `--` (streamlines note §2, Q4).
11. Read text with `encoding="utf-8-sig"` (browser parity for BOM files) and split with `re.split(r"\r?\n", text)`, not `splitlines()`
    (which also splits on `\r`, `\x0b`, `\x1c`, U+2028, …).
12. Regexes: use `[0-9]` (or `re.ASCII`) for JS `\d`. Pad destructured link-section fields with `None` (§2.7).
13. The ftree `directed` word is `isUndirectedFlow`-based (`undirdir` → `undirected`); use `result._directed`, not `printAsUndirected()`.
14. Bipartite: `.tree`/`.clu` written with `hide_bipartite_nodes` omit feature nodes; `.ftree` keeps them. The object reader must filter the same way.

---

## 13. Open questions

1. Reproduce TS input bugs bit-for-bit (`higherOrder` never true; unquoted-name slicing; JSON identifier toggle no-op;
   merge forcing `"id"` mode; unknown extension → no identifiers; JSON keys overriding `format`/`id`), or fix them and document the
   divergence? Only the phantom path level and the `;` handling can affect geometry (v2 levels / insignificant groups). The rest only
   affects UI or metadata (the unknown-extension case breaks linking, so the port should not reproduce it).
2. Default for `from_infomap(..., exact=)`: `False` (TS parity, flows rounded to 6 digits) or `True` (full precision)?
   This note recommends `False` by default plus an opt-in.
3. Should we support the legacy diagram-save JSON (`networks[]`, the `science-1998-2001-2007.json` sample)? The current
   app cannot load it. `createFilesFromDiagramObject` defines what it would mean.
4. Default network name for `from_infomap` (TS would show the filename, for example `example_states.tree`).
5. `directed`, `hideBipartiteNodes` and module enter/exit flows from an Infomap object need private API (`result._directed`,
   `im._core._im.hideBipartiteNodes`, `InfomapIterator.data`). Since `modules`/`directed` are dead data in the engine, drop them in v1?
   The bipartite hide flag does change the node set, so the reader needs it or an explicit `hide_bipartite=` argument.
6. Clu files written at `module level ≠ 1` (`write_clu(depth_level=k)`): TS treats the module id as a top-level path
   regardless of `cluLevel`. Should we keep that, or reject it?
7. Multilayer expand/merge: v1 or later?
8. The installed `infomap` is an editable dev checkout (git `c9ce210b`) that reports `2.15.1`. A PyPI 2.15.1 wheel may differ in
   header lines (`# trials`, `# seed` are ignored by the parser anyway) and in private attribute names. Re-run §11.4 against the
   pinned release before freezing fixtures.
9. JSON flow rounding (`jsonOutputNumber`, §4) versus `float(f"{v:g}")`: equal on every tested value but not proven bit-identical.
   Only matters if `from_infomap` should also emulate the JSON format.
10. Not run, derived from source or specs only: browser BOM stripping, react-dropzone's case-insensitive extension check, and the
    bare-`*Links` crash.

---

## Changes in revision 2

- Fixed: `directed` mapping (`printAsUndirected` → `result._directed`; differs for `undirdir`); bipartite hide filter added to the
  object reader; `.tree`-with-clu-content is accepted (not rejected); format is case-sensitive and dot-less names give the whole name;
  JSON keys override `id/format/haveModules/…`; colours replace (not append to) the palette; NaN semantics of `calcStatistics`
  (accumulator reset, NaN dedupe) and the reference implementation; `l.id === layerId`; `cluLevel` for `depth_level=-1`;
  `modules`/`directed` are dead data; science `.stree` path forms; clu module id via `n.module_id` at `depth_level`; line refs.
- Added: header-less `.stree` rejection, BOM, whitespace-only lines, `\d`/`\s` differences, link-field padding, TreePath rows for
  `1;1:235;`, `01:2`, `1:`, `""`, `1:2;3`, layer inheritance and merge reordering, JSON physical-node shape and flow rounding,
  example-data network names, `.net` strict header, Infomap header line list, `js_num_str` exponent forms.
