// Scenario definitions for the TS layout fixtures.
//
// A scenario = dataset group (2-4 network files, in diagram order)
//            + DiagramStore constructor options (identifier + layout options)
//            + a list of store operations applied after store.setNetworks().
//
// Every scenario starts from a fresh DiagramStore and freshly parsed files, so
// fixtures never depend on each other (the engine mutates orders in place).

export type StoreOptions = {
  identifier?: "id" | "name";
  height?: number;
  marginExponent?: number;
  zeroMargins?: boolean;
  moduleWidth?: number;
  streamlineFraction?: number;
  streamlineThreshold?: number;
  flowThreshold?: number;
  verticalAlign?: "bottom" | "justify";
  moduleSize?: "flow" | "nodes";
  sortModulesBy?: "flow" | "nodes" | "highlightIndex" | "nodeId";
  // v3: DiagramStore ctor option (a COLOR_SCHEMES name; default the store's selectedSchemeName)
  colorScheme?: string;
  // c3 tone and offset (web app 1.16, #47): DiagramStore ctor options colorTone (a TONES name; default "strong") and
  // colorOffset (degrees; default null, c3's default for the scheme)
  colorTone?: string;
  colorOffset?: number | null;
  // saved diagrams: the display options a saved file carries (DiagramStore OPTION_KEYS)
  streamlineOpacity?: number;
  defaultHighlightColor?: string;
  showModuleId?: boolean;
  showModuleNames?: boolean;
  multilineModuleNames?: boolean;
  showNetworkNames?: boolean;
  aggregateStateNames?: boolean;
  titleCaseModuleNames?: boolean;
  hierarchicalModules?: "none" | "outline" | "shadow";
  hierarchicalModuleOffset?: number;
  hierarchicalModuleOpacity?: number;
  dropShadow?: boolean;
  fontSize?: number;
  networkFontSize?: number;
  adaptiveFontSize?: boolean;
  showBipartiteNodes?: boolean;
};

// Module addressing: `moduleIndex` indexes network.children AFTER the previous layout (visible modules
// sorted first, then invisible ones). v2 ops may give `moduleId` instead, resolved with
// network.getModule(moduleId) at op time (the harness throws if it is missing).
export type ModuleRef = { networkIndex: number; moduleIndex?: number; moduleId?: string };

export type HighlightGroups = [label: string, identifiers: string[]][];

export type Op =
  | { op: "colorMatchingModulesInAllNetworks" }
  | { op: "colorModuleIdsInAllNetworks" }
  | { op: "colorNodesInModulesInAllNetworks"; networkIndex?: number }
  | ({ op: "colorModule"; color: string } & ModuleRef)
  | ({ op: "expand" } & ModuleRef)
  | ({ op: "regroup" } & ModuleRef)
  // Option change after load: calls the store setter (setHeight, setFlowThreshold, ...),
  // which runs one updateLayout on the same diagram.
  | { op: "setOption"; key: keyof Omit<StoreOptions, "identifier">; value: number | string | boolean }
  | { op: "clearColors" }
  // --- v2: hierarchy (docs/dev/port-notes/v2-hierarchy.md §5, §6, §10)
  // store.setSelectedModule(m); store.moveSelectedModule(direction) (layout without calcFlow)
  // `result: false` expects the refusal (the op is then not an error); see planted-ftree__moveHidden.
  | ({ op: "moveModule"; direction: "up" | "down"; result?: boolean } & ModuleRef)
  // Fix round B1: store.setModuleOrder([[network, modules], ...]) (Network.setModuleOrder per network, then one
  // layout without calcFlow if some order changed). Recorded by the moduleOrder macro.
  | { op: "setModuleOrder"; order: [number, string[]][] }
  | { op: "resetLayout" }
  // Fix round B2: store.setModuleLevel(levels) (expand rounds without intermediate layouts, one layout at the end
  // if something was expanded). Recorded by the moduleLevel macro, with one level per network.
  | { op: "setModuleLevel"; levels: number[] }
  // Macro: module_level=k (§10.1, fix round B2), run in TS. It is recorded as one concrete
  // {op: "setModuleLevel", levels: [k per network]} op in inputs.operations (none if nothing expands), and itself
  // in inputs.macros.
  | { op: "moduleLevel"; levels: number | number[] }
  // --- v2: colour ops (docs/dev/port-notes/v2-highlight.md §3, §4)
  // nodes resolve to store.diagram.children[networkIndex].getLeafNode(identifier) at op time
  | { op: "colorSelectedNodes"; nodes: { networkIndex: number; identifier: string }[]; color: string }
  | ({ op: "colorMatchingModules"; color: string; side?: -1 | 1 } & ModuleRef)
  | ({ op: "colorModuleIds"; color: string } & ModuleRef)
  | ({ op: "colorNodesInModule"; color: string } & ModuleRef)
  | { op: "colorByLayer" }
  | { op: "colorByPhysicalId" }
  // colors: [value, colour] pairs, passed as new Map(colors)
  | { op: "colorCategoricalMetadata"; name: string; colors: [string, string][] }
  | { op: "colorRealMetadata"; name: string; bins: { x0: number; x1: number; color: string }[] }
  // getColor = v => colors[number of breaks <= v]; data = null
  | { op: "colorRealIntervals"; name: string; breaks: number[]; colors: string[]; centers: number[] }
  | { op: "setDefaultHighlightColor"; color: string }
  | { op: "setSelectedScheme"; name: string }
  // c3 tone and offset (#47): store.setSelectedTone(tone), store.setSelectedOffset(offset), and the colouring by
  // module hierarchy store.colorModuleHierarchyInAllNetworks()
  | { op: "setSelectedTone"; tone: string }
  | { op: "setSelectedOffset"; offset: number }
  | { op: "colorModuleHierarchyInAllNetworks" }
  // Macro: design.md `highlight=` (v2-highlight.md §7.1). Before setNetworks every input node gets the metadata
  // {[HIGHLIGHT_KEY]: String(k)} if its identifier is listed in groups[k], else {} (recorded in
  // inputs.nodeMetadata). At its position it runs colorCategoricalMetadata(HIGHLIGHT_KEY, Map(String(k) -> colors[k])),
  // which is recorded in inputs.operations; the macro itself goes to inputs.macros.
  | { op: "highlight"; groups: HighlightGroups; colors: string[] }
  // --- v3: names (docs/dev/port-notes/v3-webapp-json.md §3.4); store.setNetworkName(network.networkId, name)
  | { op: "setNetworkName"; networkIndex: number; name: string }
  | ({ op: "setModuleName"; name: string } & ModuleRef)
  // --- v4 (docs/dev/port-notes/v4-names-order.md §3). Macro: `module_order=`, run in TS as at most one
  // setModuleOrder op (fix round B1; recorded in inputs.operations; the macro itself in inputs.macros).
  // order: [networkIndex, visible module ids bottom to top, at most one "..." for the unlisted ones][]
  | { op: "moduleOrder"; order: [number, string[]][] }
  // Macro (fuzz only, v4): `module_names=` as one setModuleName per [networkIndex, moduleId, name], the module
  // looked up with network.getModule at its turn (DiagramStore.apply_module_names); recorded by moduleId.
  | { op: "moduleNames"; names: [number, string, string][] };

export const HIGHLIGHT_KEY = "\u0000alluvial.highlight";

export type MetadataContext = {
  // parsed input files (before split), in `files` order
  files: { nodes: any[] }[];
  // index into files[fileIndex].nodes of the first leaf in tree order (network.leafNodes()) after setNetworks
  firstLeafNodeIndex: (fileIndex: number) => Promise<number>;
};

export type Scenario = {
  name: string;
  group: string;
  variant: string;
  files: string[]; // relative to tests/
  options: StoreOptions;
  ops: Op[];
  description: string;
  // --- v2 (each is written to the fixture only when set)
  // indices into `files` of multilayer files to split with expandMultilayerFile (v2-io.md §2)
  split?: number[];
  // per-input-file node metadata (aligned with the parsed file.nodes), assigned before split and setNetworks
  nodeMetadata?: (ctx: MetadataContext) => Promise<(Record<string, unknown> | null)[][]>;
  // add highlightIndex/insignificant to every label.names / label.namesSingleLine record
  labelNameHighlight?: boolean;
  // too large to commit: generated only with `generate.mjs --large --out DIR` (never by --check or the default run)
  large?: boolean;
  // --- v3 (scenarios-v3.ts; written to tests/fixtures/v3/)
  v3?: boolean;
  // after the ops: the engine's saved files (`savedFiles`, serializeDiagram) and their reload (`savedReload`,
  // parseAcceptedFiles + openNetworks)
  roundTrip?: boolean;
  // with roundTrip: edit the saved files before the reload (harness editSavedFiles; the edited files are in
  // `savedReloadFiles`)
  restore?:
    | "shuffled"
    | "partial"
    | "mixedSaves"
    | "formatVersion2"
    | "badBlock"
    | "badOptions"
    // #57: an unknown tone and an offset that is no number; null tone and offset; a save without them (#55)
    | "badColor"
    | "nullColor"
    | "legacyColor"
    // odd saved values (fuzz c3_open): an inherited Object key as scheme, an array tone, an offset literal that
    // JSON.parse reads as Infinity; an integer offset literal beyond 2**53 (a finite double)
    | "oddColor"
    | "hugeOffset";
  // with roundTrip: the ctor options of the store that opens the saved files (default: a default store), so the
  // restore can keep or reset the current scheme, tone and offset (written to the fixture as `reloadStore`)
  reloadStore?: Pick<StoreOptions, "colorScheme" | "colorTone" | "colorOffset">;
  // --- v4 (scenarios-v4.ts; written to tests/fixtures/v4/)
  v4?: boolean;
};

export const GROUPS: Record<string, { files: string[]; description: string; split?: number[] }> = {
  "debug5-tree": {
    files: ["data/debug5_0.tree", "data/debug5_1.tree"],
    description: "web app debug sample, 5 nodes, 3-level tree",
  },
  "debug5-stree": {
    files: ["data/debug5_0.stree", "data/debug5_1.stree"],
    description: "web app debug sample with insignificant (';') tree paths",
  },
  "science-stree": {
    files: [2001, 2003, 2005, 2007].map((y) => `data/science${y}_2y.stree`),
    description: "web app example (journal citation networks), ~7k nodes per network",
  },
  "planted-ftree": {
    files: [0, 1, 2].map((t) => `data/planted_t${t}.ftree`),
    description: "seeded planted-partition time slices, nodes appear/disappear (.ftree)",
  },
  "planted-tree": {
    files: [0, 1, 2].map((t) => `data/planted_t${t}.tree`),
    description: "same partitions as planted-ftree, .tree format",
  },
  "planted-clu": {
    files: [0, 1, 2].map((t) => `data/planted_t${t}.clu`),
    description: "same partitions as planted-ftree, .clu format (no names, module-only paths)",
  },
  "states-tree": {
    files: [0, 1].map((t) => `data/states_t${t}.tree`),
    description: "seeded state (memory) network, state-level .tree (state_id node_id)",
  },
  "states-ftree": {
    files: [0, 1].map((t) => `data/states_t${t}.ftree`),
    description: "seeded state network, state-level .ftree",
  },
  "states-clu": {
    files: [0, 1].map((t) => `data/states_t${t}.clu`),
    description: "seeded state network, state-level .clu (state_id module flow node_id)",
  },
  "multilevel-tree": {
    files: [0, 1, 2].map((t) => `data/multilevel_t${t}.tree`),
    description: "seeded hierarchical planted partition, 3-level trees",
  },
  "directed-ftree": {
    files: [0, 1].map((t) => `data/directed_t${t}.ftree`),
    description: "seeded directed weighted network (.ftree with *Links directed)",
  },
  "directed-tree": {
    files: [0, 1].map((t) => `data/directed_t${t}.tree`),
    description: "seeded directed weighted network, .tree format",
  },
  // Coverage gaps and minimised differential-fuzz cases (tools/ts-fixtures/fuzz)
  "planted-ftree-single": {
    files: ["data/planted_t0.ftree"],
    description: "a single network (planted_t0.ftree)",
  },
  "zeroflow-tree": {
    files: [0, 1, 2].map((t) => `data/zeroflow_t${t}.tree`),
    description:
      "hand-written: zero-flow nodes in visible modules (zero-height streamlines, finite sort-key ties); the third network has only zero flows (module flow threshold Infinity)",
  },
  "zeroflow-all": {
    files: [2, 3].map((t) => `data/zeroflow_t${t}.tree`),
    description: "hand-written: every flow is zero (maxNetworkFlow 0, NaN sizes and sort keys)",
  },
  "fuzz2455": {
    files: [
      "data/fuzz2455_net0.stree",
      "data/fuzz2455_net1.clu",
      "data/fuzz2455_net2.tree",
      "data/fuzz2455_net3.stree",
      "data/fuzz2455_net4.ftree",
    ],
    description: "fuzz seed 2455: five networks in four formats, unicode/quoted names, duplicate ids",
  },
  "fuzz670": {
    files: ["data/fuzz670_net0.ftree", "data/fuzz670_net1.clu", "data/fuzz670_net2.clu"],
    description: "fuzz seed 670: ftree + clu networks matched by name",
  },
  "fuzz1347": {
    files: [0, 1, 2, 3, 4].map((i) => `data/fuzz1347_net${i}.stree`),
    description:
      "fuzz seed 1347: five .stree networks with zero margins and zero flows; finite streamline sort-key ties (equal opposite y)",
  },
  // --- v2 datasets (make_datasets.py; tests/data/datasets.json "v2_datasets")
  "prefix-tree": {
    files: [0, 1].map((t) => `data/prefix_t${t}.tree`),
    description:
      'synthetic 12-top-module trees: "1" is a string prefix of "10"-"12", "1:1" of "1:10"/"1:11" (the isAncestor prefix bug, fixed in WP3/E2); 3- and 4-level paths',
  },
  "dupname-tree": {
    files: [0, 1].map((t) => `data/dupname_t${t}.tree`),
    description:
      "minimised v2 fuzz case: duplicate name c in one module of t1; with identifier name one c leaf sits in a streamline node detached from the tree",
  },
  "hlskip-tree": {
    files: [0, 1, 2].map((t) => `data/hlskip_t${t}.tree`),
    description:
      "hand-written: a visible single-leaf module that is not last (t0, t1) triggers the skip of the visible-leaf colour walk",
  },
  "abc-chain": {
    files: [0, 1, 2].map((t) => `data/abcchain_t${t}.tree`),
    description:
      "hand-written (colors-render §6.1): a = {1: n1,n2}, b = {1: n1,n2; 2: n3,n4}, c = {1: n3,n4; 2: n1,n2}; a similarity chain starts in network 1",
  },
  "planted-json": {
    files: [0, 1, 2].map((t) => `data/planted_t${t}.json`),
    description: "Infomap JSON (write_json) of the planted runs",
  },
  "states-json": {
    files: [0, 1].map((t) => `data/states_t${t}.json`),
    description: "Infomap JSON (write_json states=True) of the state-network runs",
  },
  "mixed-json-tree": {
    files: ["data/planted_t0.json", "data/planted_t1.tree", "data/planted_t2.ftree"],
    description: "JSON (array paths) next to .tree and .ftree networks",
  },
  "mlayer-unsplit": {
    files: ["data/mlayer_states.tree"],
    description: "seeded multilayer state network (layer_id column), one unsplit network",
  },
  "mlayer-split": {
    files: ["data/mlayer_states.tree"],
    split: [0],
    description: "the multilayer network split into its 4 layers (expandMultilayerFile; input layer order 3,1,4,2)",
  },
  "mlayer-split-twice": {
    files: ["data/mlayer_states.tree", "data/mlayer_states.tree"],
    split: [0, 1],
    description:
      "the multilayer network loaded twice and both split: two files with one stem (ids mlayer_states, mlayer_states_2)",
  },
  "mlayer-split-json": {
    files: ["data/mlayer_states.json"],
    split: [0],
    description: "the multilayer JSON split into its 4 layers",
  },
  "mlayer-split-flat": {
    files: ["data/mlayer_states.tree", "data/mlayer_flat.tree"],
    split: [0],
    description: "the 4 split layers followed by the first-order aggregate network (not split)",
  },
  "mlayer-named-json": {
    files: ["data/mlayer_named.json"],
    split: [0],
    description: 'multilayer JSON with a `layers` name list (ids 1 and 3 named; "4" as a string does not match)',
  },
};

const COLOR_MATCHING: Op = { op: "colorMatchingModulesInAllNetworks" };

type Variant = {
  // replaces the group's files (same group name, e.g. one network swapped for a hand-made variant)
  files?: string[];
  options?: StoreOptions;
  ops?: Op[];
  description: string;
  nodeMetadata?: Scenario["nodeMetadata"];
  labelNameHighlight?: boolean;
  large?: boolean;
};

const CORE: Record<string, Variant> = {
  default: { description: "DiagramStore defaults" },
  zeroMargins: { options: { zeroMargins: true }, description: "zeroMargins=true" },
  moduleSizeNodes: { options: { moduleSize: "nodes" }, description: 'moduleSize="nodes"' },
  flowThreshold05: { options: { flowThreshold: 0.05 }, description: "flowThreshold=0.05 (hide up to 5% flow)" },
  flowThreshold0: { options: { flowThreshold: 0 }, description: "flowThreshold=0 (all modules with flow > 0 visible)" },
  // The small datasets have few, similar-sized modules, so 0.005/0.05 hide
  // (almost) nothing. 0.4 hides several modules per network: links to
  // invisible modules, -Infinity sort-key ties, invisible module order, and
  // (with justify) the missing-flow margin redistribution.
  flowThreshold40: {
    options: { flowThreshold: 0.4 },
    description: "flowThreshold=0.4 (hides several modules per network)",
  },
  flowThreshold40Justify: {
    options: { flowThreshold: 0.4, verticalAlign: "justify" },
    description: 'flowThreshold=0.4, verticalAlign="justify" (justify with missing flow)',
  },
  sortNodes: { options: { sortModulesBy: "nodes" }, description: 'sortModulesBy="nodes"' },
  sortNodeId: { options: { sortModulesBy: "nodeId" }, description: 'sortModulesBy="nodeId" (mean leaf node id)' },
  geometry: {
    options: { height: 200, moduleWidth: 50, streamlineFraction: 1.5, marginExponent: 5 },
    description: "height=200 moduleWidth=50 streamlineFraction=1.5 marginExponent=5 (triggers the 20% margin cap)",
  },
  justify: { options: { verticalAlign: "justify" }, description: 'verticalAlign="justify"' },
  colored: { ops: [COLOR_MATCHING], description: "setNetworks, then colorMatchingModulesInAllNetworks()" },
};

const NAME: Record<string, Variant> = {
  name: { options: { identifier: "name" }, description: 'identifier="name"' },
  nameColored: {
    options: { identifier: "name" },
    ops: [COLOR_MATCHING],
    description: 'identifier="name", then colorMatchingModulesInAllNetworks()',
  },
};

const PRIMARY = [
  "debug5-tree",
  "debug5-stree",
  "planted-ftree",
  "states-tree",
  "multilevel-tree",
  "directed-ftree",
];
const SECONDARY = ["planted-tree", "planted-clu", "states-ftree", "states-clu", "directed-tree"];

const EXTRA: { group: string; variant: string; v: Variant }[] = [
  {
    group: "science-stree",
    variant: "default",
    v: CORE.default,
  },
  { group: "science-stree", variant: "name", v: NAME.name },
  { group: "science-stree", variant: "nameColored", v: NAME.nameColored },
  {
    group: "planted-ftree",
    variant: "colorModuleIds",
    v: { ops: [{ op: "colorModuleIdsInAllNetworks" }], description: "colorModuleIdsInAllNetworks()" },
  },
  {
    group: "planted-ftree",
    variant: "colorNodes",
    v: {
      ops: [{ op: "colorNodesInModulesInAllNetworks" }],
      description: "colorNodesInModulesInAllNetworks(undefined) (source = first network)",
    },
  },
  {
    group: "planted-ftree",
    variant: "coloredSortHighlightIndex",
    v: {
      options: { sortModulesBy: "highlightIndex" },
      ops: [COLOR_MATCHING],
      description: 'sortModulesBy="highlightIndex", then colorMatchingModulesInAllNetworks()',
    },
  },
  {
    group: "planted-ftree",
    variant: "colorModule",
    v: {
      ops: [{ op: "colorModule", networkIndex: 1, moduleIndex: 0, color: "#ff0000" }],
      description: 'colorModule(network 1 children[0], "#ff0000") (single-module highlight, v2)',
    },
  },
  {
    group: "multilevel-tree",
    variant: "expand",
    v: {
      ops: [{ op: "expand", networkIndex: 0, moduleIndex: 0 }],
      description: "store.expand(network 0 children[0]) (sub-modules, v2)",
    },
  },
  {
    group: "multilevel-tree",
    variant: "expandColored",
    v: {
      ops: [{ op: "expand", networkIndex: 1, moduleIndex: 0 }, COLOR_MATCHING],
      description: "store.expand(network 1 children[0]), then colorMatchingModulesInAllNetworks() (v2)",
    },
  },
  {
    // debug5 .stree paths only mark levels below the top as insignificant
    // ("1:2;3;"), so insignificant groups appear only after expanding.
    group: "debug5-stree",
    variant: "expand",
    v: {
      ops: [
        { op: "expand", networkIndex: 0, moduleIndex: 0 },
        { op: "expand", networkIndex: 1, moduleIndex: 0 },
      ],
      description:
        "store.expand(network 0 children[0]), then store.expand(network 1 children[0]) (insignificant groups, v2)",
    },
  },
  // --- coverage gaps (single network, option changes after load, other heights,
  // margin cap with justify + hidden modules, zero flows) and fuzz regressions
  ...["default", "colored", "geometry", "justify"].map((k) => ({ group: "planted-ftree-single", variant: k, v: CORE[k] })),
  {
    group: "planted-ftree-single",
    variant: "colorModuleIds",
    v: { ops: [{ op: "colorModuleIdsInAllNetworks" }], description: "colorModuleIdsInAllNetworks()" },
  },
  {
    group: "planted-ftree-single",
    variant: "colorNodes",
    v: { ops: [{ op: "colorNodesInModulesInAllNetworks" }], description: "colorNodesInModulesInAllNetworks(undefined)" },
  },
  {
    group: "planted-ftree",
    variant: "setOptions",
    v: {
      ops: [
        COLOR_MATCHING,
        { op: "setOption", key: "height", value: 1234.5 },
        { op: "setOption", key: "flowThreshold", value: 0.4 },
        { op: "setOption", key: "verticalAlign", value: "justify" },
        { op: "setOption", key: "sortModulesBy", value: "nodes" },
        { op: "setOption", key: "marginExponent", value: 2.5 },
        { op: "setOption", key: "flowThreshold", value: 0 },
      ],
      description:
        "colorMatchingModulesInAllNetworks(), then store setters (height, flowThreshold 0.4, justify, sortModulesBy, marginExponent 2.5, flowThreshold 0), one updateLayout each",
    },
  },
  {
    group: "planted-ftree",
    variant: "colorOpsMixed",
    v: {
      ops: [
        COLOR_MATCHING,
        { op: "colorModule", networkIndex: 0, moduleIndex: 1, color: "#ff0000" },
        { op: "colorModule", networkIndex: 0, moduleIndex: 1, color: "#b6b69f" },
        { op: "clearColors" },
        { op: "colorNodesInModulesInAllNetworks", networkIndex: 1 },
        { op: "colorModuleIdsInAllNetworks" },
        COLOR_MATCHING,
      ],
      description:
        "colour ops in sequence: matching, colorModule red, colorModule default colour, clearColors, colorNodes from network 1, moduleIds, matching",
    },
  },
  ...["planted-ftree", "debug5-tree"].flatMap((group) => [
    {
      group,
      variant: "height37",
      v: {
        options: { height: 37.5, marginExponent: 3.5 },
        description: "height=37.5 marginExponent=3.5 (non-integer margins, 20% margin cap)",
      },
    },
    {
      group,
      variant: "heightHuge",
      v: { options: { height: 1e6, moduleWidth: 333.3 }, description: "height=1e6 moduleWidth=333.3" },
    },
  ]),
  ...["planted-ftree", "states-tree", "multilevel-tree"].map((group) => ({
    group,
    variant: "geometryJustify40",
    v: {
      options: {
        height: 200,
        moduleWidth: 50,
        streamlineFraction: 1.5,
        marginExponent: 5,
        flowThreshold: 0.4,
        verticalAlign: "justify" as const,
      },
      description: "geometry options + flowThreshold=0.4 + justify (margin cap with justify and hidden modules)",
    },
  })),
  ...["default", "colored", "flowThreshold0", "justify", "sortNodeId"].map((k) => ({
    group: "zeroflow-tree",
    variant: k,
    v: CORE[k],
  })),
  ...["default", "colored"].map((k) => ({ group: "zeroflow-all", variant: k, v: CORE[k] })),
  {
    group: "fuzz2455",
    variant: "ops",
    v: {
      options: { streamlineThreshold: 50, flowThreshold: 0.4, moduleSize: "nodes", sortModulesBy: "nodeId" },
      ops: [
        { op: "colorModule", networkIndex: 2, moduleIndex: 1, color: "#ff0000" },
        { op: "setOption", key: "height", value: 48.694962191673014 },
        COLOR_MATCHING,
        { op: "colorNodesInModulesInAllNetworks" },
        { op: "colorModuleIdsInAllNetworks" },
      ],
      description: "fuzz seed 2455 options and operations (resolved colorModule index)",
    },
  },
  {
    group: "fuzz670",
    variant: "ops",
    v: {
      options: {
        identifier: "name",
        streamlineFraction: 0.25,
        flowThreshold: 0.5,
        marginExponent: 8,
        sortModulesBy: "highlightIndex",
      },
      ops: [
        COLOR_MATCHING,
        { op: "colorNodesInModulesInAllNetworks", networkIndex: 2 },
        { op: "colorModuleIdsInAllNetworks" },
        { op: "setOption", key: "moduleSize", value: "nodes" },
        COLOR_MATCHING,
        COLOR_MATCHING,
        { op: "colorModule", networkIndex: 1, moduleIndex: 0, color: "#0000ff" },
        COLOR_MATCHING,
      ],
      description: "fuzz seed 670 options and operations (identifier name, repeated colour ops)",
    },
  },
  {
    group: "fuzz1347",
    variant: "ops",
    v: {
      options: {
        moduleWidth: 333.3,
        flowThreshold: 0,
        marginExponent: 8.074328676568566,
        zeroMargins: true,
        verticalAlign: "justify",
      },
      ops: [{ op: "colorNodesInModulesInAllNetworks", networkIndex: 3 }],
      description: "fuzz seed 1347 options, then colorNodesInModulesInAllNetworks(network 3)",
    },
  },
  {
    group: "abc-chain",
    variant: "similarity",
    v: {
      ops: [COLOR_MATCHING],
      description:
        "colorMatchingModulesInAllNetworks(): one colour counter for all network pairs (fix round WP6/S1), so the chain b.2 -> c.1 gets scheme[1], not scheme[0] again",
    },
  },
  // Fix round E15a: network 0 is multilevel_mixed_t0.json (multilevel_t0 with "moduleLevel": 2 on the leaves below
  // 1:1), so module 1 is visible together with its sub-module 1:1. Network.tree adds 1 to the non-leaf node of 1
  // (default order: 1:1 first) or turns the leaf node of 1 into a non-leaf node (custom order: 1 first).
  {
    group: "multilevel-tree",
    variant: "visibleAndSubmodule",
    v: {
      files: ["data/multilevel_mixed_t0.json", "data/multilevel_t1.tree", "data/multilevel_t2.tree"],
      options: { flowThreshold: 0 },
      description:
        "network 0 from JSON with per-node moduleLevel: module 1 and its sub-module 1:1 both visible; the hierarchy outline of 1 encloses both (E15a, no throw)",
    },
  },
  {
    group: "multilevel-tree",
    variant: "visibleAndSubmoduleOrder",
    v: {
      files: ["data/multilevel_mixed_t0.json", "data/multilevel_t1.tree", "data/multilevel_t2.tree"],
      options: { flowThreshold: 0 },
      ops: [{ op: "moduleOrder", order: [[0, ["1", "1:1", "..."]]] }],
      description:
        "as visibleAndSubmodule, then module_order puts 1 below 1:1 in network 0, so the tree meets 1 first (its leaf node becomes a non-leaf node, E15a)",
    },
  },
  {
    group: "multilevel-tree",
    variant: "expandRegroup",
    v: {
      ops: [
        { op: "expand", networkIndex: 0, moduleIndex: 0 },
        { op: "regroup", networkIndex: 0, moduleIndex: 0 },
      ],
      description: "store.expand(network 0 children[0]), then store.regroup(network 0 children[0]) (v2)",
    },
  },
];

// ---------------------------------------------------------------------------
// v2 scenarios. Specs: docs/dev/port-notes/v2-hierarchy.md §12, v2-highlight.md §8, v2-io.md §8.
// Every fixture of a v2 scenario carries a top-level `features` list (derived in harness.ts).
// ---------------------------------------------------------------------------

// C3 Sinebow scheme entries 0-3 of c3 1.x (before web app 1.16), written out so the ops are literal colours.
const S = ["rgb(198, 59, 59)", "rgb(61, 200, 200)", "rgb(135, 203, 67)", "rgb(139, 73, 207)"];
const DEFAULT = "#b6b69f";
const ids = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => String(from + i));

const MOVES: Op[] = [
  { op: "moveModule", networkIndex: 0, moduleIndex: 0, direction: "up" },
  { op: "moveModule", networkIndex: 0, moduleIndex: 1, direction: "up" },
  { op: "moveModule", networkIndex: 1, moduleIndex: 0, direction: "up" },
];

const PLANTED_HIGHLIGHT: Op = {
  op: "highlight",
  groups: [
    ["alpha", ids(5, 20)],
    ["beta", ids(40, 55)],
    ["gamma", [...ids(85, 100), ...ids(121, 125)]],
  ],
  colors: [S[0], S[1], S[2]],
};

const MULTILEVEL_HIGHLIGHT: Op = {
  op: "highlight",
  groups: [
    ["x", ids(1, 20)],
    ["y", ids(50, 70)],
  ],
  colors: [S[0], S[1]],
};

// planted metadata: {c: "a"|"b"|"c"} by id % 3, a number for id % 11 == 0, no key for id % 13 == 0
const plantedCategorical = (node: any): Record<string, unknown> =>
  node.id % 13 === 0 ? {} : node.id % 11 === 0 ? { c: 7 } : { c: ["a", "b", "c"][node.id % 3] };
const CATEGORICAL_OP: Op = {
  op: "colorCategoricalMetadata",
  name: "c",
  colors: [
    ["b", S[0]],
    ["a", S[1]],
    ["zz", S[2]],
    ["c", DEFAULT],
  ],
};
// planted metadata {x: id / max id of that network} (x == 1 for the largest id)
const plantedReal = async ({ files }: { files: { nodes: any[] }[] }) =>
  files.map((file) => {
    const maxId = Math.max(...file.nodes.map((n) => n.id));
    return file.nodes.map((n) => ({ x: n.id / maxId }));
  });

// planted metadata that is a JSON array, not an object (`name in metadata` reads index keys and `length`):
// id % 5 -> null, ["a"], ["b", "b"], [], ["a", "b", "c"]
const plantedArray = async ({ files }: { files: { nodes: any[] }[] }) =>
  files.map((file) =>
    file.nodes.map((n) => [null, ["a"], ["b", "b"], [], ["a", "b", "c"]][n.id % 5] as any),
  );

const V2: { group: string; variant: string; v: Variant }[] = [
  // ----- hierarchy: module_level macro, expand/regroup, move (v2-hierarchy.md §12.3)
  ...(
    [
      ["level2", 2, {}, "moduleLevel 2: sub-module creation and swap-remove, level-1 outlines"],
      ["level3", 3, {}, "moduleLevel 3: nested outlines, refused module 4 (t2)"],
      ["levelMixed", [1, 3, 2], {}, "moduleLevel [1,3,2]: per-network k, network 0 untouched"],
      ["level3Geometry", 3, CORE.geometry.options, "geometry options + moduleLevel 3: margin cap with deep differenceIndex"],
      [
        "level3Justify40",
        3,
        { flowThreshold: 0.4, verticalAlign: "justify" },
        "flowThreshold 0.4 + justify + moduleLevel 3: threshold moves between expands, hidden modules below k",
      ],
      ["level2SortNodeId", 2, { sortModulesBy: "nodeId" }, 'sortModulesBy "nodeId" + moduleLevel 2: summed parent keys'],
    ] as [string, number | number[], StoreOptions, string][]
  ).map(([variant, levels, options, description]) => ({
    group: "multilevel-tree",
    variant,
    v: { options, ops: [{ op: "moduleLevel", levels } as Op], description },
  })),
  {
    group: "multilevel-tree",
    variant: "level2Colored",
    v: {
      ops: [{ op: "moduleLevel", levels: 2 }, COLOR_MATCHING],
      description: "moduleLevel 2, then colorMatchingModulesInAllNetworks() (expand, then colour)",
    },
  },
  {
    group: "multilevel-tree",
    variant: "coloredLevel2",
    v: {
      ops: [COLOR_MATCHING, { op: "moduleLevel", levels: 2 }],
      description: "colorMatchingModulesInAllNetworks(), then moduleLevel 2 (expanding coloured modules)",
    },
  },
  {
    group: "multilevel-tree",
    variant: "level3Regroup",
    v: {
      ops: [
        { op: "moduleLevel", levels: 3 },
        { op: "regroup", networkIndex: 1, moduleId: "1:1:1" },
      ],
      description: 'moduleLevel 3, then regroup(network 1 module "1:1:1") (level-3 regroup, siblings by prefix "1:1")',
    },
  },
  {
    group: "debug5-stree",
    variant: "level3",
    v: {
      ops: [{ op: "moduleLevel", levels: 3 }],
      description: "moduleLevel 3: the trailing-':' leaves stop at level 2 (no phantom level since E1), insignificant groups, equal-flow ties",
    },
  },
  {
    group: "science-stree",
    variant: "level2",
    v: {
      ops: [{ op: "moduleLevel", levels: 2 }],
      // ~1000 modules per network after the 24 expands, mostly invisible: a 39 MB fixture
      large: true,
      description: "moduleLevel 2 at scale: hidden unexpandable modules, invisible order (large: --large only)",
    },
  },
  {
    group: "fuzz1347",
    variant: "level4",
    v: {
      options: {
        moduleWidth: 333.3,
        flowThreshold: 0,
        marginExponent: 8.074328676568566,
        zeroMargins: true,
        verticalAlign: "justify",
      },
      ops: [{ op: "moduleLevel", levels: 4 }],
      description: "fuzz1347 options + moduleLevel 4: mixed-depth refusal, zero flows, zero margins",
    },
  },
  { group: "prefix-tree", variant: "default", v: CORE.default },
  {
    group: "prefix-tree",
    variant: "regroupPrefix",
    v: {
      options: { flowThreshold: 0 },
      ops: [
        { op: "expand", networkIndex: 0, moduleId: "1" },
        { op: "expand", networkIndex: 0, moduleId: "10" },
        { op: "expand", networkIndex: 0, moduleId: "12" },
        { op: "expand", networkIndex: 1, moduleId: "1" },
        { op: "regroup", networkIndex: 0, moduleId: "1:2" },
      ],
      description:
        'expand "1", "10", "12" (network 0) and "1" (network 1), then regroup "1:2" in network 0: collapses only 1:* (10:*, 12:* and 11 stay; the isAncestor prefix bug, fixed in E2, collapsed them)',
    },
  },
  {
    group: "prefix-tree",
    variant: "regroupPrefixDeep",
    v: {
      options: { flowThreshold: 0 },
      ops: [
        { op: "moduleLevel", levels: [3, 1] },
        { op: "regroup", networkIndex: 0, moduleId: "1:1:1" },
      ],
      description:
        'moduleLevel [3,1], then regroup "1:1:1" in network 0: collapses only 1:1:* (1:10:*, 1:11:* stay; the prefix bug, fixed in E2, collapsed them)',
    },
  },
  {
    group: "multilevel-tree",
    variant: "move",
    v: {
      ops: MOVES,
      description:
        "moveModule up: network 0 children[0] and [1], network 1 children[0] (custom order, stale index, no calcFlow after a move)",
    },
  },
  {
    group: "multilevel-tree",
    variant: "moveSetOption",
    v: {
      ops: [...MOVES, { op: "setOption", key: "height", value: 400 }, COLOR_MATCHING],
      description: "the __move moves, then setHeight(400) and colorMatchingModulesInAllNetworks() (custom order survives)",
    },
  },
  {
    group: "multilevel-tree",
    variant: "moveExpand",
    v: {
      ops: [
        { op: "moveModule", networkIndex: 0, moduleIndex: 0, direction: "up" },
        { op: "moveModule", networkIndex: 1, moduleIndex: 0, direction: "up" },
        { op: "expand", networkIndex: 1, moduleId: "1" },
      ],
      description: 'moveModule up in networks 0 and 1, then expand network 1 module "1" (resets only its own network)',
    },
  },
  {
    group: "multilevel-tree",
    variant: "moveReset",
    v: { ops: [...MOVES, { op: "resetLayout" }], description: "the __move moves, then resetLayout()" },
  },
  {
    group: "multilevel-tree",
    variant: "moveDown",
    v: {
      ops: [
        { op: "moveModule", networkIndex: 2, moduleIndex: 3, direction: "down" },
        { op: "moveModule", networkIndex: 2, moduleIndex: 2, direction: "down" },
      ],
      description: "moveModule down twice in network 2 (top module to the middle)",
    },
  },
  {
    group: "planted-ftree",
    variant: "moveHidden",
    v: {
      options: { flowThreshold: 0.4 },
      ops: [{ op: "moveModule", networkIndex: 0, moduleIndex: 2, direction: "up", result: false }],
      description:
        "flowThreshold 0.4: moveModule up of the topmost visible module of network 0 is refused (fix round H1: the boundary is the top visible module; it used to swap with the invisible one and freeze the order)",
    },
  },
  {
    group: "mlayer-split",
    variant: "level2",
    v: { ops: [{ op: "moduleLevel", levels: 2 }], description: "split layers, then moduleLevel 2" },
  },

  // ----- colour ops and highlight (v2-highlight.md §8.3)
  { group: "hlskip-tree", variant: "default", v: CORE.default },
  {
    group: "hlskip-tree",
    variant: "colorSelectedNodes",
    v: {
      ops: [
        {
          op: "colorSelectedNodes",
          nodes: [
            { networkIndex: 0, identifier: "3" },
            { networkIndex: 0, identifier: "1" },
          ],
          color: "#ff0000",
        },
        { op: "colorSelectedNodes", nodes: [{ networkIndex: 0, identifier: "3" }], color: "#ff0000" },
        { op: "colorSelectedNodes", nodes: [{ networkIndex: 0, identifier: "1" }], color: DEFAULT },
      ],
      description: "colorSelectedNodes: propagation, same-colour re-paint, erase with the default colour",
    },
  },
  {
    group: "planted-ftree",
    variant: "colorSelectedNodes",
    v: {
      ops: [
        { op: "colorSelectedNodes", nodes: ids(1, 12).map((identifier) => ({ networkIndex: 0, identifier })), color: S[0] },
        { op: "colorSelectedNodes", nodes: ids(9, 14).map((identifier) => ({ networkIndex: 2, identifier })), color: S[1] },
        { op: "colorSelectedNodes", nodes: ids(9, 12).map((identifier) => ({ networkIndex: 1, identifier })), color: DEFAULT },
      ],
      description:
        "colorSelectedNodes: planted_t0 nodes 1-12 from network 0 (1-8 absent elsewhere), t2 nodes 9-14 from network 2, then 9-12 from network 1 with the default colour",
    },
  },
  {
    group: "planted-ftree",
    variant: "colorSelectedNodesMixed",
    v: {
      ops: [
        {
          op: "colorSelectedNodes",
          nodes: ["9", "10", "11"].flatMap((identifier) => [
            { networkIndex: 0, identifier },
            { networkIndex: 1, identifier },
          ]),
          color: S[0],
        },
      ],
      description: "one colorSelectedNodes call with the same 3 identifiers from networks 0 and 1 (repeated updates)",
    },
  },
  {
    group: "states-tree",
    variant: "nameColorSelectedNodes",
    v: {
      options: { identifier: "name" },
      ops: [
        {
          op: "colorSelectedNodes",
          nodes: ["p1", "p2", "p6", "p12", "p13"].map((identifier) => ({ networkIndex: 0, identifier })),
          color: S[2],
        },
      ],
      description: 'identifier "name": colorSelectedNodes of 5 names (duplicate identifiers: last-wins getLeafNode)',
    },
  },
  {
    group: "planted-ftree",
    variant: "colorMatchingModules",
    v: {
      ops: [
        { op: "colorMatchingModules", networkIndex: 1, moduleIndex: 0, color: S[0] },
        { op: "colorMatchingModules", networkIndex: 0, moduleIndex: 1, color: S[1], side: 1 },
        { op: "colorMatchingModules", networkIndex: 2, moduleIndex: 1, color: S[2], side: -1 },
      ],
      description: "colorMatchingModules: both-sided, right-only and left-only chains, overwrites",
    },
  },
  {
    group: "hlskip-tree",
    variant: "colorMatchingModulesSingle",
    v: {
      ops: [{ op: "colorMatchingModules", networkIndex: 1, moduleIndex: 1, color: "#ff0000" }],
      description: "colorMatchingModules started on a single-leaf module: the chain continues from it (E4; before, it coloured only that module)",
    },
  },
  {
    group: "hlskip-tree",
    variant: "colorMatchingModulesThrough",
    v: {
      ops: [{ op: "colorMatchingModules", networkIndex: 2, moduleIndex: 1, color: "#ff0000" }],
      description: "colorMatchingModules chain runs through a single-leaf module (E4; before, it stopped there)",
    },
  },
  {
    group: "planted-ftree",
    variant: "colorModuleIdsSingle",
    v: {
      ops: [{ op: "colorModuleIds", networkIndex: 0, moduleIndex: 1, color: S[3] }],
      description: "colorModuleIds(network 0 children[1])",
    },
  },
  {
    group: "hlskip-tree",
    variant: "colorModuleIdsSingle",
    v: {
      ops: [{ op: "colorModuleIds", networkIndex: 0, moduleIndex: 1, color: "#ff0000" }],
      description: "colorModuleIds on a single-leaf module (stale source module's moduleId)",
    },
  },
  {
    group: "planted-ftree",
    variant: "colorNodesInModule",
    v: {
      ops: [
        { op: "colorNodesInModule", networkIndex: 1, moduleIndex: 0, color: S[0] },
        { op: "colorNodesInModule", networkIndex: 0, moduleIndex: 2, color: S[1] },
      ],
      description: "colorNodesInModule twice",
    },
  },
  {
    group: "hlskip-tree",
    variant: "colorNodesInModuleSingle",
    v: {
      ops: [{ op: "colorNodesInModule", networkIndex: 0, moduleIndex: 1, color: "#ff0000" }],
      description: "colorNodesInModule on a single-leaf module propagates to the other networks (E4; before, it did not)",
    },
  },
  {
    group: "states-tree",
    variant: "colorByPhysicalId",
    v: { ops: [{ op: "colorByPhysicalId" }], description: "colorByPhysicalId (several states per physical id)" },
  },
  {
    group: "hlskip-tree",
    variant: "colorByPhysicalId",
    v: {
      ops: [{ op: "colorByPhysicalId" }, { op: "colorByPhysicalId" }],
      description: "colorByPhysicalId twice: every visible leaf is coloured (E4 removed the visible-leaf-walk skip), non-clearing re-run",
    },
  },
  {
    group: "planted-ftree",
    variant: "colorByLayerNoop",
    v: {
      ops: [{ op: "colorModule", networkIndex: 0, moduleIndex: 0, color: "#ff0000" }, { op: "colorByLayer" }],
      description: "colorModule, then colorByLayer on networks without layer ids (colours kept, relayout)",
    },
  },
  {
    group: "mlayer-unsplit",
    variant: "colorByLayer",
    v: { ops: [{ op: "colorByLayer" }], description: "colorByLayer on the unsplit multilayer network" },
  },
  {
    group: "mlayer-unsplit",
    variant: "colorByPhysicalId",
    v: { ops: [{ op: "colorByPhysicalId" }], description: "colorByPhysicalId on the unsplit multilayer network" },
  },
  {
    group: "planted-ftree",
    variant: "categorical",
    v: {
      nodeMetadata: async ({ files }) => files.map((f) => f.nodes.map(plantedCategorical)),
      ops: [CATEGORICAL_OP],
      description:
        'metadata c = a/b/c (number 7 or missing for some), colorCategoricalMetadata("c", b, a, zz (unused), c (default))',
    },
  },
  {
    group: "planted-ftree",
    variant: "categoricalNoMetaFirst",
    v: {
      nodeMetadata: async ({ files, firstLeafNodeIndex }) => {
        const md: (Record<string, unknown> | null)[][] = files.map((f) => f.nodes.map(plantedCategorical));
        md[1][await firstLeafNodeIndex(1)] = null;
        return md;
      },
      ops: [CATEGORICAL_OP],
      description: "as __categorical, but network 1's first leaf in tree order has metadata null (network skipped)",
    },
  },
  {
    group: "hlskip-tree",
    variant: "categoricalSkip",
    v: {
      nodeMetadata: async ({ files }) =>
        files.map((f) =>
          f.nodes.map((n: any) => (n.id === 3 || n.id === 4 ? { hl: "a" } : n.id === 1 ? { hl: "b" } : {}))
        ),
      ops: [
        {
          op: "colorCategoricalMetadata",
          name: "hl",
          colors: [
            ["a", "#ff0000"],
            ["b", "#0000ff"],
          ],
        },
      ],
      description: "colorCategoricalMetadata on hlskip (the highlight= path): node 4 is coloured in every network (E4; before, the walk skip left it gray in t0, t1)",
    },
  },
  {
    group: "planted-ftree",
    variant: "highlight",
    v: {
      ops: [PLANTED_HIGHLIGHT],
      labelNameHighlight: true,
      description: "highlight macro: 3 labels over node ids, label-name highlight indices",
    },
  },
  {
    group: "planted-ftree",
    variant: "highlightSortHighlightIndex",
    v: {
      options: { sortModulesBy: "highlightIndex" },
      ops: [PLANTED_HIGHLIGHT],
      labelNameHighlight: true,
      description: 'sortModulesBy "highlightIndex" + highlight macro',
    },
  },
  {
    group: "planted-ftree-single",
    variant: "highlight",
    v: { ops: [PLANTED_HIGHLIGHT], labelNameHighlight: true, description: "highlight macro on a single network" },
  },
  {
    group: "planted-ftree",
    variant: "highlightThenClear",
    v: { ops: [PLANTED_HIGHLIGHT, { op: "clearColors" }], description: "highlight macro, then clearColors()" },
  },
  {
    group: "science-stree",
    variant: "nameHighlight",
    v: {
      options: { identifier: "name" },
      ops: [
        {
          op: "highlight",
          groups: [
            ["bio", ["J BIOL CHEM", "CELL", "EMBO J", "GENE DEV", "MOL CELL BIOL"]],
            ["phys", ["PHYS REV LETT", "PHYS REV B", "ASTROPHYS J", "APPL PHYS LETT", "J CHEM PHYS"]],
          ],
          colors: [S[0], S[1]],
        },
      ],
      labelNameHighlight: true,
      description: 'identifier "name": highlight of 10 journals in 2 labels (many invisible modules, aggregated names)',
    },
  },
  {
    group: "debug5-stree",
    variant: "expandHighlight",
    v: {
      ops: [
        { op: "expand", networkIndex: 0, moduleIndex: 0 },
        { op: "expand", networkIndex: 1, moduleIndex: 0 },
        {
          op: "highlight",
          groups: [
            ["A", ["1", "82", "144"]],
            ["B", ["171", "179"]],
          ],
          colors: [S[0], S[1]],
        },
      ],
      labelNameHighlight: true,
      description: "expand 0/0 and 1/0, then highlight all 5 nodes in 2 labels (insignificant highlighted groups)",
    },
  },
  {
    group: "multilevel-tree",
    variant: "expandThenHighlight",
    v: {
      ops: [{ op: "expand", networkIndex: 0, moduleIndex: 0 }, MULTILEVEL_HIGHLIGHT],
      description: "expand network 0 children[0], then highlight",
    },
  },
  {
    group: "multilevel-tree",
    variant: "highlightThenExpand",
    v: {
      ops: [MULTILEVEL_HIGHLIGHT, { op: "expand", networkIndex: 0, moduleIndex: 0 }],
      description: "highlight, then expand network 0 children[0] (op order matters)",
    },
  },
  {
    group: "multilevel-tree",
    variant: "level2Highlight",
    v: {
      ops: [{ op: "moduleLevel", levels: 2 }, MULTILEVEL_HIGHLIGHT],
      labelNameHighlight: true,
      description: "moduleLevel 2, then highlight (the layout(module_level=2, highlight=...) path)",
    },
  },
  {
    group: "planted-ftree",
    variant: "realMetadata",
    v: {
      nodeMetadata: plantedReal,
      ops: [
        {
          op: "colorRealMetadata",
          name: "x",
          bins: [0, 1, 2, 3].map((i) => ({ x0: i / 4, x1: (i + 1) / 4, color: S[i] })),
        },
      ],
      description: "metadata x = id / max id; colorRealMetadata with 4 equal bins over [0, 1] (x == 1 uncoloured)",
    },
  },
  {
    group: "planted-ftree",
    variant: "arrayMetadata",
    v: {
      nodeMetadata: plantedArray,
      ops: [{ op: "colorCategoricalMetadata", name: "0", colors: [["a", S[0]], ["b", S[1]]] }],
      description: 'array metadata (null, ["a"], ["b","b"], [], ["a","b","c"]); colorCategoricalMetadata("0") reads index 0',
    },
  },
  {
    group: "planted-ftree",
    variant: "arrayLength",
    v: {
      nodeMetadata: plantedArray,
      ops: [
        {
          op: "colorRealMetadata",
          name: "length",
          bins: [0, 1, 2, 3].map((i) => ({ x0: i, x1: i + 1, color: S[i] })),
        },
      ],
      description: "array metadata; colorRealMetadata(\"length\") reads the array length (0 for [], null skipped)",
    },
  },
  {
    group: "planted-ftree",
    variant: "realIntervals",
    v: {
      nodeMetadata: plantedReal,
      ops: [
        {
          op: "colorRealIntervals",
          name: "x",
          breaks: [0.25, 0.5, 0.75],
          colors: [S[0], DEFAULT, S[1], S[2]],
          centers: [0.875, 0.125],
        },
      ],
      description: "metadata x = id / max id; colorRealIntervals (registration order: centres first, then the walk)",
    },
  },
  {
    group: "planted-ftree",
    variant: "defaultColorChange",
    v: {
      ops: [
        { op: "setDefaultHighlightColor", color: "#ff0000" },
        { op: "colorModule", networkIndex: 0, moduleIndex: 0, color: "#ff0000" },
      ],
      description: 'setDefaultHighlightColor("#ff0000"), then colorModule with it (maps to -1)',
    },
  },

  // ----- IO: Infomap JSON and multilayer splitting (v2-io.md §8.3)
  { group: "planted-json", variant: "default", v: CORE.default },
  { group: "planted-json", variant: "colored", v: CORE.colored },
  { group: "states-json", variant: "default", v: CORE.default },
  { group: "states-json", variant: "name", v: NAME.name },
  { group: "mixed-json-tree", variant: "default", v: CORE.default },
  { group: "mlayer-unsplit", variant: "default", v: CORE.default },
  { group: "mlayer-split", variant: "default", v: CORE.default },
  {
    group: "mlayer-split",
    variant: "name",
    v: { ...NAME.name, description: 'identifier "name" (ignored by the split: equals __default except inputs)' },
  },
  {
    group: "mlayer-split",
    variant: "colorModuleIds",
    v: { ops: [{ op: "colorModuleIdsInAllNetworks" }], description: "colorModuleIdsInAllNetworks() (multilayer branch)" },
  },
  { group: "mlayer-split", variant: "colored", v: CORE.colored },
  { group: "mlayer-split", variant: "flowThreshold40", v: CORE.flowThreshold40 },
  {
    group: "mlayer-split-twice",
    variant: "colorModuleIds",
    v: {
      ops: [{ op: "colorModuleIdsInAllNetworks" }],
      description:
        "colorModuleIdsInAllNetworks() over the layers of two loaded files (distinct originalIds: per-network branch)",
    },
  },
  {
    group: "mlayer-split-json",
    variant: "colorModuleIds",
    v: { ops: [{ op: "colorModuleIdsInAllNetworks" }], description: "colorModuleIdsInAllNetworks() (multilayer branch)" },
  },
  {
    group: "mlayer-split-flat",
    variant: "colorModuleIds",
    v: {
      ops: [{ op: "colorModuleIdsInAllNetworks" }],
      description: "colorModuleIdsInAllNetworks() (non-multilayer branch: the flat network has no layer id)",
    },
  },
  { group: "mlayer-named-json", variant: "default", v: CORE.default },
  // --- v2 fuzz regressions
  {
    group: "dupname-tree",
    variant: "highlight",
    v: {
      options: { identifier: "name" },
      ops: [{ op: "highlight", groups: [["c", ["c"]]], colors: ["#00ff00"] }],
      description:
        "highlight name c: input-node metadata labels both c leaves of t1; only the registered (last) one links to t0, the other stays dangling (E6)",
    },
  },
  {
    group: "dupname-tree",
    variant: "recolor",
    v: {
      options: { identifier: "name" },
      ops: [{ op: "colorByPhysicalId" }, { op: "clearColors" }],
      description:
        "colorByPhysicalId splits the two c leaves of t1 into groups, clearColors joins them: every leaf runs update() (the old re-steal path); no NULL-prefixed streamline id remains (E6)",
    },
  },
];

function make(group: string, variant: string, v: Variant): Scenario {
  const scenario: Scenario = {
    name: `${group}__${variant}`,
    group,
    variant,
    files: v.files ?? GROUPS[group].files,
    options: v.options ?? {},
    ops: v.ops ?? [],
    description: v.description,
  };
  if (GROUPS[group].split) scenario.split = GROUPS[group].split;
  if (v.nodeMetadata) scenario.nodeMetadata = v.nodeMetadata;
  if (v.labelNameHighlight) scenario.labelNameHighlight = true;
  if (v.large) scenario.large = true;
  return scenario;
}

export const SCENARIOS: Scenario[] = [
  ...PRIMARY.flatMap((g) => [
    ...Object.entries(CORE).map(([k, v]) => make(g, k, v)),
    ...Object.entries(NAME).map(([k, v]) => make(g, k, v)),
  ]),
  ...SECONDARY.flatMap((g) => [make(g, "default", CORE.default), make(g, "colored", CORE.colored)]),
  ...EXTRA.map(({ group, variant, v }) => make(group, variant, v)),
  ...V2.map(({ group, variant, v }) => make(group, variant, v)),
];
