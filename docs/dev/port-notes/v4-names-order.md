# Port note: v4 module names, module order and web-app zips

Spec of `layout(..., module_names=, module_order=)`, the `moduleNames` written by `save_diagram`, and `read()` of a
web-app `.zip` (design.md "v4 design"). TS citations are relative to `packages/alluvial-diagram/src/` (engine) or
`apps/web/src/` (web app). Python: `engine/store.py` (`apply_module_order`, `apply_module_names`), `layout.py`
(argument checks, `ModuleInfo`, step order), `io/saved_diagram.py` (`diagram_json(module_names=...)`),
`io/__init__.py` (`read_zip`). Fixtures: `tests/fixtures/v4/` (tools/ts-fixtures/README.md "v4 scenarios").

## 1. Step order in `layout`

build → `expand` → `module_level` → colouring (`colors` or `highlight`) → **`module_order`** → restored saved names
(`restore_state`) → **`module_names`**.

- The order runs after the colouring so that `sort_modules_by="highlight_index"` sorts by the final colours, and so
  that reordering never changes the colours (`colorMatchingModulesInAllNetworks` walks modules in `children` order).
- It runs after `expand`/`module_level` because a successful `expand` or `regroup` clears that network's
  `isCustomSorted` and re-sorts it (v2-hierarchy §5.3): an order applied before would be lost.
- Names have no layout effect (`setModuleName` is `module.name = name; toggleUpdate()`, `store/DiagramStore.ts:402`),
  so they go last; explicit names win over restored ones.

## 2. `module_names`

- Mapping `{(network, module_id): name}`: `network` an index or a network id, `module_id` a path string as shown at
  that time (`"1:2"` after `module_level=2`). Applied in mapping order, one `store.setModuleName(module, name)` each,
  the module looked up with `network.getModule(module_id)` at its turn. `""` clears a name.
- Callable `(ModuleInfo) -> str | None`: called once per module of every network (`network.children` order: visible
  then hidden; networks left to right), after the other steps; `None`/`""` leaves the module unnamed.
  `ModuleInfo`: `network_index, network_id, network_name, id, path, level, flow, visible, node_names` (leaf names
  by descending flow, unnamed leaves dropped).
- Errors (`ValueError`, prefixed `module_names:`): unknown network index/id; unknown module (with the
  `expand`-style hint "expand its parent module first" / "already expanded"); the same module named twice (e.g. by
  index and by id). `TypeError` for malformed keys or non-string names.
- `ModuleGeometry.name` carries the name; `label` keeps the leaf names (TS parity). `draw` shows the name, in black,
  instead of the leaf names, on the networks that have labels (first and last), as `react/Module.tsx` does
  (`module.name || <LargestLeafNames>`).
- `harness.ts`: plain `setModuleName {networkIndex, moduleId, name}` ops (no macro). `apply_module_names` returns
  the same records.

## 3. `module_order`: the deterministic move sequence

> **Erratum (0.5, fix round WP7: B1; Y1).** `module_order=` is no longer a move sequence. `apply_module_order` keeps
> the validation and the target of §3.2, skips networks whose target equals their current visible order (no op, not
> frozen), and passes the full visible target of the others to ONE `store.set_module_order` (TS
> `DiagramStore.setModuleOrder` → `Network.setModuleOrder` per network: `children = [...listed, ...unlisted in current
> order]`, always frozen; then one `diagram.updateLayout` without `calcFlow` if some order changed). It records one op,
> `{op: "setModuleOrder", order: [[networkIndex, [moduleId, ...]], ...]}` (networks ascending), which the harness
> macro (§3.3) records too. The result is bit-identical to the move sequence (fix-inventory.md B1, [P-1]; re-run in
> WP7 against the new primitive: 550/550 cases identical), because moves never run `calcFlow` and each layout rewrites
> every visible field from the order. On `science*_2y.stree` at `module_level=2`, reversing 40 of the 429 visible
> modules of network 0 takes 0.11 s instead of 85 s (780 moves; measured in WP7). The cost notes below are history.

### 3.1 TS move semantics it must respect (v2-hierarchy §5)

- `Module.move(direction)` swaps the module with its neighbour in `network.children` (**all** modules, visible then
  invisible after a layout); "up" = higher index = visually up. It sets `network.isCustomSorted = true` before the
  move and refuses (warns, returns false) at the boundary.
- `moveSelectedModule` lays out **without** `calcFlow`; with `isCustomSorted` pass 1 skips the sort, so
  `module.index` goes **stale** (keeps the last sorted value), and re-partitions `children = visible + invisible`.
- Moving the topmost visible module up swaps it with the first hidden one: it succeeds and sets the flag, but the
  partition undoes it visibly.
- Flows are not re-summed and the threshold is per network, so the visible set is constant during a move sequence.

### 3.2 Algorithm (`DiagramStore.apply_module_order`, `harness.ts` `runModuleOrder`)

Input: `(network_index, ids)` pairs; `ids` are module ids bottom to top with at most one `"..."` (Python `...`).

```
validate all networks first (unknown network, network given twice, >1 "...", unknown/duplicate/hidden module)
for network_index in ascending order:
    network = diagram.children[network_index]
    listed  = modules of ids (None for "...")
    rest    = [m for m in network.children if m.is_visible and m not in listed]     # current order
    target  = listed[:k] + rest + listed[k+1:]  if "..." at k  else  listed + rest
    for p, module in enumerate(target):                                                # from the bottom
        while (j := identity_index(network.children, module)) > p:
            record {op: "moveModule", networkIndex, moduleIndex: j, moduleId, direction: "down"}
            store.move_module(module, "down")      # swap j <-> j-1, layout without calc_flow
```

Properties:

- The result is exactly `target` at positions `0..n_visible-1` (asserted after each module).
- Every move is "down" past a visible module: positions `0..p-1` already hold `target[:p]`, and `module` sits at
  `j > p` inside the visible prefix. So no move is refused, none touches a hidden module, and no warning is issued.
- The number of moves is the number of inversions between the current visible order and `target` (minimal for
  adjacent swaps). An order that is already the layout order issues no moves and leaves `isCustomSorted` false.
- Positions are looked up by identity before every move, never through the stale `module.index`.
- Networks run in ascending index, whatever the mapping order: each move lays out the whole diagram, and the branch
  sort reads the previous layout's positions, so the op order is fixed for bit parity.
- Cost: one full `diagram.update_layout` per move, as in the web app. Measured on `science*_2y.stree` at
  `module_level=2` (429 visible modules in the first network): 0.08 s per move, so moving one module from the top
  to the bottom takes ~35 s and a full reversal hours. Skipping the intermediate layouts is not known to be
  bit-exact (the branch sort is stable on positions from the previous layout, and streamline nodes towards hidden
  modules keep stale positions), so it is not done; it would need a proof or a fuzz campaign first.
- `sort_modules_by` (and colours, for `"highlight_index"`) only decide the starting order and so the `"..."`/unlisted
  part; the first move freezes the network's order for later ops that do not expand/regroup/reset it.

Errors (`ValueError`, prefixed `module_order:`): unknown network index/id; a network given twice (by index and id);
more than one `...`; unknown module (with the expand hint); a module listed twice; a hidden module ("not shown (its
flow is below the flow threshold, or zero)"). `TypeError` for a non-mapping, non-list values, non-string ids.

### 3.3 Fixture macro

`{op: "moduleOrder", order: [[networkIndex, ids], ...]}` runs §3.2 **in TS** and records the issued `moveModule`
ops (with both `moduleIndex` and `moduleId`; replay uses `moduleIndex`) in `inputs.operations`, the macro itself in
`inputs.macros` (as `moduleLevel`). Python checks (a) replaying the ops gives the dump bit for bit, (b)
`apply_module_order` on the pre-macro state issues exactly the recorded ops, (c) `layout(..., module_order=...)`
gives the fixture geometry.

## 4. `moduleNames` in saved diagrams

> **Erratum (0.5, fix round WP2).** The 2019 saved diagram and its `moduleNames` are gone (v3-webapp-json.md
> erratum): no `diagram_json`, no `saveModuleNames` shim, no `saveDiagram`/`saved`/`reload` blocks in the v4
> round-trip fixtures, and `save_diagram` writes only the web-app files, which carry neither names nor order (it
> warns). The rest of this section is history; the new format (fix-plan.md WP9) stores names and order again.
>
> **Erratum (0.5, fix round WP9).** The saved-diagram format stores them: `alluvial.network.moduleNames` (module id ->
> non-empty name, in `children` order) and, for a custom order, `alluvial.network.moduleOrder` (every module id in
> `children` order, hidden ones included). `openNetworks`/`open_networks` (and `layout(restore_state=True)`) restore
> the order with one `setModuleOrder` and then the names; ids that do not exist are skipped with a warning; explicit
> `module_order=`/`module_names=` replace the stored ones. `save_diagram` no longer warns. `read` of a zip, a directory
> or a list of paths sorts the files of one save into saved order (§6).

TS has no `getModuleNames` since 2022 (v3-webapp-json §2.3); the harness shims it for the save call. v4 shim, used
by the `saveModuleNames` scenarios and by `diagram_json(module_names=True)` (the default, `save_diagram`):

```
network.children.filter(m => m.name !== "").map(m => [m.id, { name: m.name, flow: m.flow }])
```

- Keys are the module ids `${networkId}_module${moduleId}` (the 2019-2021 `Module.customNames` keys), in
  `network.children` order (visible then hidden; hidden named modules are written too); `flow` = `module.flow` at
  save time (the 2019 app stored the flow at naming time).
- A network without names writes `[]`, so a diagram without names is byte-identical to the v3 shim `() => []`.
- The v3 fixture `multilevel-tree__colored__names__roundTrip` names a module but pins the v3 shim (`moduleNames:
  []`); its `saveDiagram.moduleNames` provenance is `"() => []"`, and the test passes `module_names=False` for it.
- Reading: `layout(read(path))` with `restore_state=True` sets the names again by module id (v3 decisions), after
  `module_order`. Today's converter (`createFilesFromDiagramObject`) ignores `moduleNames` and the custom order, so
  `reload` blocks have neither.
- Web-app files (`format="webapp"`) carry neither names nor order (the app has no field for them); `save_diagram`
  warns.

## 5. Scenarios

See tools/ts-fixtures/README.md "v4 scenarios". All 14 keep `layout`'s step order, so each is reproduced through
public `layout()` arguments (`tests/test_v4_fixtures.py`); the round-trip ones also through `save_diagram` (both
formats, byte for byte). The move quirks themselves (custom flag cleared by expand, reset, the hidden swap) stay
covered by the v2 fixtures `multilevel-tree__move*`, `planted-ftree__moveHidden`.

## 6. Reading a zip (`read_zip`)

Mirrors `readAcceptedFiles` (`P/parse-files.ts:88-140`) for an `application/zip` file:

- Entries in archive (central-directory) order, as `Object.entries(JSZip.files)`. (JSZip's object would put
  integer-like entry names first; zips from `save_diagram` use `00_<name>.json`, so this does not arise.)
- Entries whose suffix is a network format (`tree`, `ftree`, `stree`, `clu`, `json`) are parsed like loose files.
  Directory entries, `__MACOSX/` and `._*` entries are skipped silently (the app would report errors for them);
  other suffixes are skipped with one warning (the app reports "Unsupported file format" and loads the rest).
- Name: the JSON `name` (spread over the file) or the entry name (full path inside the zip); id: the JSON string
  `id`, else the entry's base name without its suffix (the app's ids are random; the harness uses the file name
  without `.json`, so `read` of a zip of `webAppFiles` equals `webAppReload` bit for bit, tested).
- A saved diagram inside a zip, a non-UTF-8 entry, invalid JSON, a zip without network files or an unreadable zip
  raise `ValueError`. `read(zip)` returns `list[NetworkFile]`; `layout` also takes the zip path as one input and
  expands it (like a saved diagram).
