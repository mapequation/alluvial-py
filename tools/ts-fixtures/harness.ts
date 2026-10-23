// Headless fixture harness: runs the real TS alluvial engine (DiagramStore +
// Diagram from packages/alluvial-diagram/src) on the scenarios in
// scenarios.ts and dumps the resulting geometry as JSON.
//
// Loaded by generate.mjs through Vite's SSR loader. "@alluvial-src" is an
// alias for <ALLUVIAL_TS_ROOT>/packages/alluvial-diagram/src.
//
// The engine is not modified. Diagram.prototype.updateLayout is wrapped only
// to take read-only snapshots between its passes (pass-1 positions and the
// streamline-node sort keys), which are otherwise overwritten.

import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { basename, join, resolve } from "node:path";

import Diagram from "@alluvial-src/alluvial/Diagram";
import type HighlightGroup from "@alluvial-src/alluvial/HighlightGroup";
import type Module from "@alluvial-src/alluvial/Module";
import Network from "@alluvial-src/alluvial/Network";
import LeafNode from "@alluvial-src/alluvial/LeafNode";
import type StreamlineNode from "@alluvial-src/alluvial/StreamlineNode";
import type StreamlineLink from "@alluvial-src/alluvial/StreamlineLink";
import { MODULE } from "@alluvial-src/alluvial/Depth";
import { expandMultilayerFile } from "@alluvial-src/parsers/multilayer-utils";
import { parseAcceptedFiles } from "@alluvial-src/parsers/parse-files";
import { serializeDiagram } from "@alluvial-src/parsers/alluvial-format";
import {
  COLOR_SCHEMES,
  DEFAULT_TONE,
  defaultSchemeOffset,
  hierarchyOptions,
  SCHEME_GROUPS,
  schemeColors,
  schemeIsHueSource,
  TONES,
  type SchemeName,
  type ToneName,
} from "@alluvial-src/schemes";
import { DiagramStore } from "@alluvial-src/store/DiagramStore";

import { V3_SCENARIOS } from "./scenarios-v3";
import { V4_SCENARIOS } from "./scenarios-v4";

import {
  HIGHLIGHT_KEY,
  SCENARIOS,
  type HighlightGroups,
  type ModuleRef,
  type Op,
  type Scenario,
  type StoreOptions,
} from "./scenarios";

export const FIXTURE_FORMAT_VERSION = 1;

// ---------------------------------------------------------------------------
// Environment shims (Node has File/Blob but no FileReader)
// ---------------------------------------------------------------------------

class FileReaderShim {
  result: string | null = null;
  onload: (() => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  // v3: JSZip.loadAsync(File) reads blobs as array buffers
  readAsArrayBuffer(blob: Blob) {
    blob.arrayBuffer().then(
      (buffer) => {
        (this as any).result = buffer;
        this.onload?.();
      },
      (e) => this.onerror?.(e)
    );
  }
  readAsText(blob: Blob) {
    blob.text().then(
      (text) => {
        this.result = text;
        this.onload?.();
      },
      (e) => this.onerror?.(e)
    );
  }
}
if (!(globalThis as any).FileReader) (globalThis as any).FileReader = FileReaderShim;

// The engine logs timings with console.time; keep stdout clean.
console.time = () => {};
console.timeEnd = () => {};

let warnings: string[] = [];
const origWarn = console.warn;
console.warn = (...args: unknown[]) => {
  warnings.push(args.map(String).join(" "));
};

// ---------------------------------------------------------------------------
// Instrumentation: snapshots inside Diagram.updateLayout (read-only)
// ---------------------------------------------------------------------------

type Rect = { x: number; y: number; width: number; height: number };
type Trace = {
  calls: number;
  pass1Modules: Map<Module, Rect & { margin: number; index: number }>;
  pass1Groups: Map<HighlightGroup, Rect>;
  sortKeys: Map<StreamlineNode, number>;
};

const traces = new WeakMap<Diagram, Trace>();

const rect = (n: Rect): Rect => ({ x: n.x, y: n.y, width: n.width, height: n.height });

function snapshotPass1(diagram: Diagram, trace: Trace) {
  trace.pass1Modules = new Map();
  trace.pass1Groups = new Map();
  for (const network of diagram.children) {
    for (const module of network.children) {
      if (!module.isVisible) continue;
      trace.pass1Modules.set(module, { ...rect(module), margin: module.margin, index: module.index });
      for (const group of module.children) trace.pass1Groups.set(group, rect(group));
    }
  }
}

function snapshotSortKeys(diagram: Diagram, trace: Trace) {
  trace.sortKeys = new Map();
  for (const network of diagram.children)
    for (const module of network.children)
      for (const group of module.children)
        for (const branch of group.children)
          for (const sn of branch.children) trace.sortKeys.set(sn, sn.oppositeStreamlinePosition);
}

// Set to false to run the plain engine (used by the uninstrumented cross-check).
let tracing = true;

const origUpdateLayout = Diagram.prototype.updateLayout;
Diagram.prototype.updateLayout = function (this: Diagram, opts: any) {
  if (!tracing) return origUpdateLayout.call(this, opts);
  const self = this as any;
  const proto = Object.getPrototypeOf(this);
  const trace: Trace = traces.get(this) ?? {
    calls: 0,
    pass1Modules: new Map(),
    pass1Groups: new Map(),
    sortKeys: new Map(),
  };
  trace.calls++;
  traces.set(this, trace);
  let preOrderCalls = 0;
  // updateLayout calls, on the diagram itself: pass 1 (pre-order), [margin
  // cap], [justify], branch sort (all pre-order), then pass 2 (post-order).
  self.forEachDepthFirstPreOrderWhile = function (predicate: any, callback: any) {
    const result = proto.forEachDepthFirstPreOrderWhile.call(this, predicate, callback);
    if (preOrderCalls++ === 0) snapshotPass1(self, trace);
    return result;
  };
  self.forEachDepthFirstPostOrderWhile = function (predicate: any, callback: any) {
    snapshotSortKeys(self, trace);
    return proto.forEachDepthFirstPostOrderWhile.call(this, predicate, callback);
  };
  try {
    return origUpdateLayout.call(this, opts);
  } finally {
    delete self.forEachDepthFirstPreOrderWhile;
    delete self.forEachDepthFirstPostOrderWhile;
  }
};

// ---------------------------------------------------------------------------
// Loading (same path as the web app: parseAcceptedFiles -> setNetworks)
// ---------------------------------------------------------------------------

const ACCEPTED_FORMATS = ["tree", "ftree", "stree", "clu", "json", "net", "zip"];

async function loadFiles(testsDir: string, files: string[], identifier: "id" | "name") {
  const accepted = files.map((rel) => {
    const text = readFileSync(resolve(testsDir, rel), "utf8");
    return new File([text], basename(rel), { lastModified: 0 });
  });
  const [parsed, allErrors] = await parseAcceptedFiles(accepted, [], ACCEPTED_FORMATS, identifier);
  // Non-fatal parse warnings (duplicate identifiers) load the file; only real errors abort.
  const errors = allErrors.filter((e) => !e.warning);
  if (errors.length) {
    throw new Error(`parse errors: ${JSON.stringify(errors.map((e) => e.errors))}`);
  }
  // parseAcceptedFiles assigns random ids (utils/id.ts); make them stable: the file stem. The web app's ids are
  // distinct, so a stem used by an earlier file becomes `${stem}_${k}` (smallest k >= 2 not taken), as layout()
  // does. It matters for split files: a layer's originalId is its file's id (colorModuleIdsInAllNetworks).
  const stems = files.map((rel) => basename(rel).replace(/\.[^.]+$/, ""));
  const taken = new Set(stems);
  const seen = new Set<string>();
  parsed.forEach((file, i) => {
    let id = stems[i];
    if (seen.has(id)) {
      let k = 2;
      while (taken.has(`${stems[i]}_${k}`)) k++;
      id = `${stems[i]}_${k}`;
      taken.add(id);
    }
    seen.add(id);
    file.id = id;
  });
  return parsed;
}

// v2 split (v2-io.md §8.2): each listed input file is replaced by its layers (expandMultilayerFile, in
// increasing file index), and each layer gets the deterministic id `${file.id}_layer${String(layerId)}`.
// v2 metadata (v2-highlight.md §8.1): scenario.nodeMetadata, or the `highlight` macro's labels, are assigned
// to the parsed input nodes before the split and setNetworks.
type Prepared = {
  files: any[]; // final network files, in diagram order
  inputFiles: any[]; // parsed input files, in scenario.files order
  sources: number[]; // per final network: index into scenario.files
  nodeMetadata?: (Record<string, unknown> | null)[][];
};

function highlightMetadata(inputFiles: any[], groups: HighlightGroups) {
  const labelOf = new Map<string, number>();
  groups.forEach(([, identifiers], k) => {
    for (const identifier of identifiers) {
      if (labelOf.has(identifier)) throw new Error(`highlight: ${identifier} listed under two labels`);
      labelOf.set(identifier, k);
    }
  });
  return inputFiles.map((file) =>
    file.nodes.map((node: any) => {
      const k = labelOf.get(node.identifier);
      return k === undefined ? {} : { [HIGHLIGHT_KEY]: String(k) };
    })
  );
}

// Fuzz mode (any op position, any number of highlight macros, together with nodeMetadata): the macro's labels
// are written onto the leaves when the macro runs, like the Python `DiagramStore.apply_highlight`
// (`layout(highlight=...)`): every leaf gets a fresh object with its other metadata keys kept, the highlight key
// removed and, if the leaf's identifier is listed under label k, set to String(k). An identifier listed twice keeps
// its first label (resolveOp drops the later ones, so the recorded groups have none).
// Every LeafNode built for a network (Network.addNodes calls add() on each; update() re-adds, hence a Set). With
// duplicate identifiers a leaf can sit in a streamline node detached from the tree, so network.leafNodes() misses
// it; input-node metadata reaches it, and so must the leaf-time labels (Python: Network.built_leaf_nodes).
const builtLeaves = new WeakMap<object, Set<LeafNode>>();
const origLeafAdd = LeafNode.prototype.add;
LeafNode.prototype.add = function (this: LeafNode, ...args: any[]) {
  const network = (this as any).network;
  let leaves = builtLeaves.get(network);
  if (!leaves) builtLeaves.set(network, (leaves = new Set()));
  leaves.add(this);
  return (origLeafAdd as any).apply(this, args);
};

function highlightLeaves(store: DiagramStore, groups: HighlightGroups) {
  const labelOf = new Map<string, number>();
  groups.forEach(([, identifiers], k) => {
    for (const identifier of identifiers) if (!labelOf.has(identifier)) labelOf.set(identifier, k);
  });
  for (const network of store.diagram.children) {
    for (const leaf of builtLeaves.get(network) ?? []) {
      const md: Record<string, unknown> = { ...((leaf.metadata as Record<string, unknown> | null) ?? {}) };
      delete md[HIGHLIGHT_KEY];
      const k = labelOf.get(leaf.identifier);
      if (k !== undefined) md[HIGHLIGHT_KEY] = String(k);
      // #58 keeps the metadata in a private field behind a getter: an own property shadows it (every reader goes
      // through the getter)
      Object.defineProperty(leaf, "metadata", { value: md, writable: true, configurable: true, enumerable: true });
    }
  }
}

async function prepareFiles(
  testsDir: string,
  scenario: Scenario,
  identifier: "id" | "name",
  highlightOnLeaves = false
): Promise<Prepared> {
  let files: any[] = await loadFiles(testsDir, scenario.files, identifier);
  const inputFiles = [...files];

  let nodeMetadata: Prepared["nodeMetadata"];
  const highlight = highlightOnLeaves
    ? undefined
    : (scenario.ops.find((op) => op.op === "highlight") as Extract<Op, { op: "highlight" }> | undefined);
  if (scenario.nodeMetadata && highlight) throw new Error(`${scenario.name}: nodeMetadata and highlight`);
  if (scenario.nodeMetadata) {
    nodeMetadata = await scenario.nodeMetadata({
      files: inputFiles,
      firstLeafNodeIndex: async (fileIndex) => {
        // Probe: the same files on a throwaway store; the first leaf in tree order after setNetworks.
        if (scenario.split) throw new Error("firstLeafNodeIndex with split");
        const saved = warnings;
        const probe = new DiagramStore(scenario.options);
        probe.setNetworks(await loadFiles(testsDir, scenario.files, identifier));
        warnings = saved;
        const leaf = probe.diagram.children[fileIndex].leafNodes().next().value;
        const index = inputFiles[fileIndex].nodes.findIndex((n: any) => n.identifier === leaf.identifier);
        if (index < 0) throw new Error("first leaf not found");
        return index;
      },
    });
  } else if (highlight) {
    nodeMetadata = highlightMetadata(inputFiles, highlight.groups);
  }
  if (nodeMetadata) {
    if (nodeMetadata.length !== inputFiles.length) throw new Error(`${scenario.name}: nodeMetadata length`);
    inputFiles.forEach((file, i) => {
      if (nodeMetadata![i].length !== file.nodes.length)
        throw new Error(`${scenario.name}: nodeMetadata[${i}] has ${nodeMetadata![i].length} != ${file.nodes.length} nodes`);
      file.nodes.forEach((node: any, j: number) => (node.metadata = nodeMetadata![i][j]));
    });
  }

  const sources = files.map((_, i) => i);
  for (const fileIndex of [...(scenario.split ?? [])].sort((a, b) => a - b)) {
    const file = inputFiles[fileIndex];
    const at = files.indexOf(file);
    const before = files.length;
    files = expandMultilayerFile(file, files);
    const layers = files.slice(at, at + files.length - before + 1);
    for (const layer of layers) layer.id = `${file.id}_layer${String(layer.layerId)}`;
    sources.splice(at, 1, ...layers.map(() => fileIndex));
  }
  return { files, inputFiles, sources, nodeMetadata };
}

function moduleAt(store: DiagramStore, ref: ModuleRef): Module {
  const network = store.diagram.children[ref.networkIndex];
  if (!network) throw new Error(`no network ${ref.networkIndex}`);
  if (ref.moduleId != null) {
    const module = network.getModule(ref.moduleId);
    if (!module) throw new Error(`no module ${ref.moduleId} in network ${ref.networkIndex}`);
    return module;
  }
  const module = network.children[ref.moduleIndex as number];
  if (!module) throw new Error(`no module ${ref.networkIndex}/${ref.moduleIndex}`);
  return module;
}

// Applies one non-macro op. Returns the success flag of the refusable ops (expand, regroup, moveModule);
// a refusal throws unless `lenient` (fuzz mode).
function applyOp(store: DiagramStore, op: Op, lenient = false): boolean | undefined {
  const refused = (what: string) => {
    // A scenario op may expect the refusal ({..., result: false}, e.g. planted-ftree__moveHidden).
    if (lenient || (op as { result?: boolean }).result === false) return false;
    throw new Error(`${op.op} refused for ${what}`);
  };
  switch (op.op) {
    case "colorMatchingModulesInAllNetworks":
      store.colorMatchingModulesInAllNetworks();
      return;
    case "colorModuleIdsInAllNetworks":
      store.colorModuleIdsInAllNetworks();
      return;
    case "colorNodesInModulesInAllNetworks":
      store.colorNodesInModulesInAllNetworks(
        op.networkIndex == null ? undefined : store.diagram.children[op.networkIndex].networkId
      );
      return;
    case "colorModule":
      store.colorModule(moduleAt(store, op), op.color);
      return;
    case "expand": {
      const module = moduleAt(store, op);
      return store.expand(module) || refused(module.id);
    }
    case "regroup": {
      const module = moduleAt(store, op);
      return store.regroup(module) || refused(module.id);
    }
    case "setOption": {
      const setter = `set${op.key[0].toUpperCase()}${op.key.slice(1)}`;
      if (typeof (store as any)[setter] !== "function") throw new Error(`no store setter ${setter}`);
      (store as any)[setter](op.value);
      return;
    }
    case "clearColors":
      store.clearColors();
      return;
    case "setModuleLevel":
      store.setModuleLevel(op.levels);
      return;
    case "setModuleOrder": {
      store.setModuleOrder(
        op.order.map(([networkIndex, ids]) => {
          const network = store.diagram.children[networkIndex];
          if (!network) throw new Error(`setModuleOrder: no network ${networkIndex}`);
          return [network, ids.map((moduleId) => moduleAt(store, { networkIndex, moduleId }))];
        })
      );
      return;
    }
    case "moveModule": {
      const module = moduleAt(store, op);
      store.setSelectedModule(module);
      return store.moveSelectedModule(op.direction) || refused(module.id);
    }
    case "resetLayout":
      store.resetLayout();
      return;
    case "colorSelectedNodes": {
      const nodes = op.nodes.map(({ networkIndex, identifier }) => {
        const leaf = store.diagram.children[networkIndex]?.getLeafNode(identifier);
        if (!leaf) throw new Error(`no leaf ${identifier} in network ${networkIndex}`);
        return leaf;
      });
      store.colorSelectedNodes(nodes, op.color);
      return;
    }
    case "colorMatchingModules":
      store.colorMatchingModules(moduleAt(store, op), op.color, op.side as any);
      return;
    case "colorModuleIds":
      store.colorModuleIds(moduleAt(store, op), op.color);
      return;
    case "colorNodesInModule":
      store.colorNodesInModule(moduleAt(store, op), op.color);
      return;
    case "colorByLayer":
      store.colorByLayer();
      return;
    case "colorByPhysicalId":
      store.colorByPhysicalId();
      return;
    case "colorCategoricalMetadata":
      store.colorCategoricalMetadata(op.name, new Map(op.colors));
      return;
    case "colorRealMetadata":
      store.colorRealMetadata(op.name, op.bins);
      return;
    case "colorRealIntervals": {
      const { breaks, colors } = op;
      const getColor = (v: number) => colors[breaks.filter((b) => b <= v).length];
      store.colorRealIntervals(op.name, null as any, getColor, op.centers);
      return;
    }
    case "setDefaultHighlightColor":
      store.setDefaultHighlightColor(op.color);
      return;
    case "setSelectedScheme":
      store.setSelectedScheme(op.name as any);
      return;
    case "setSelectedTone":
      store.setSelectedTone(op.tone as any);
      return;
    case "setSelectedOffset":
      store.setSelectedOffset(op.offset);
      return;
    case "colorModuleHierarchyInAllNetworks":
      store.colorModuleHierarchyInAllNetworks();
      return;
    case "setNetworkName": {
      const network = store.diagram.children[op.networkIndex];
      if (!network) throw new Error(`no network ${op.networkIndex}`);
      store.setNetworkName(network.networkId, op.name);
      return;
    }
    case "setModuleName":
      store.setModuleName(moduleAt(store, op), op.name);
      return;
    case "moduleLevel":
    case "moduleOrder":
    case "moduleNames":
    case "highlight":
      throw new Error(`macro ${op.op} must go through runOps`);
  }
}

// --- module_level=k (v2-hierarchy.md §10.1, fix round B2): one store.setModuleLevel, recorded as
// {op: "setModuleLevel", levels: [k per network]} when it expanded something (no op otherwise).
function moduleLevelLevels(store: DiagramStore, levels: number | number[]) {
  const n = store.diagram.children.length;
  const ks = typeof levels === "number" ? new Array(n).fill(levels) : levels;
  if (ks.length !== n || !ks.every((k) => Number.isInteger(k) && k >= 1))
    throw new Error(`moduleLevel: bad levels ${JSON.stringify(levels)} for ${n} networks`);
  return ks as number[];
}

function runModuleLevel(store: DiagramStore, levels: number | number[], operations: unknown[]) {
  const ks = moduleLevelLevels(store, levels);
  if (store.setModuleLevel(ks)) operations.push({ op: "setModuleLevel", levels: ks });
}

// --- module_order (v4-names-order.md §3, fix round B1): per network (ascending index) the target visible order
// (the listed ids, "..." = the unlisted visible modules in their children order; without "..." they go above). The
// networks whose target differs from their current visible order get it in ONE store.setModuleOrder (frozen, one
// layout without calcFlow), recorded as {op: "setModuleOrder", order: [[networkIndex, [moduleId, ...]], ...]}.
// A target equal to the current order issues no op and does not freeze.
function runModuleOrder(store: DiagramStore, order: [number, string[]][], operations: unknown[]) {
  const sorted = [...order].sort((a, b) => a[0] - b[0]);
  const orders: [Network, Module[]][] = [];
  const recorded: [number, string[]][] = [];
  for (const [networkIndex, ids] of sorted) {
    const network = store.diagram.children[networkIndex];
    if (!network) throw new Error(`moduleOrder: no network ${networkIndex}`);
    if (ids.filter((id) => id === "...").length > 1) throw new Error("moduleOrder: more than one ...");
    if (new Set(ids).size !== ids.length) throw new Error(`moduleOrder: duplicate ids ${JSON.stringify(ids)}`);
    const listed: (Module | null)[] = ids.map((id) => {
      if (id === "...") return null;
      const module = network.getModule(id);
      if (!module) throw new Error(`moduleOrder: no module ${id} in network ${networkIndex}`);
      if (!module.isVisible) throw new Error(`moduleOrder: module ${id} in network ${networkIndex} is not visible`);
      return module;
    });
    const rest = network.children.filter((m) => m.isVisible && !listed.includes(m));
    const k = listed.indexOf(null);
    const target = (k >= 0 ? [...listed.slice(0, k), ...rest, ...listed.slice(k + 1)] : [...listed, ...rest]) as Module[];
    const visible = network.children.filter((m) => m.isVisible);
    if (target.every((module, i) => module === visible[i])) continue;
    orders.push([network, target]);
    recorded.push([networkIndex, target.map((module) => module.moduleId)]);
  }
  if (orders.length === 0) return;
  store.setModuleOrder(orders);
  operations.push({ op: "setModuleOrder", order: recorded });
}

// --- module_names (fuzz, v4-names-order.md §2): one setModuleName per entry, in order, by module id.
function runModuleNames(store: DiagramStore, names: [number, string, string][], operations: unknown[]) {
  for (const [networkIndex, moduleId, name] of names) {
    const network = store.diagram.children[networkIndex];
    if (!network) throw new Error(`moduleNames: no network ${networkIndex}`);
    const module = network.getModule(moduleId);
    if (!module) throw new Error(`moduleNames: no module ${moduleId} in network ${networkIndex}`);
    store.setModuleName(module, name);
    operations.push({ op: "setModuleName", networkIndex, moduleId, name });
  }
}

type Macro = { atOperation: number; numOperations: number; op: Op };
type Recording = { operations: any[]; macros: Macro[] };

// Runs the scenario ops. Plain ops are recorded verbatim (fuzz: resolved, plus `result` for refusable ops);
// macros are recorded as the concrete ops they issued, and themselves in `macros`.
function runOps(
  store: DiagramStore,
  ops: Op[],
  rec: Recording,
  {
    lenient = false,
    resolve,
    highlightOnLeaves = false,
  }: { lenient?: boolean; resolve?: (store: DiagramStore, op: Op) => Op; highlightOnLeaves?: boolean } = {}
) {
  for (const raw of ops) {
    const op = resolve ? resolve(store, raw) : raw;
    const atOperation = rec.operations.length;
    if (op.op === "moduleLevel") {
      runModuleLevel(store, op.levels, rec.operations);
      rec.macros.push({ atOperation, numOperations: rec.operations.length - atOperation, op });
    } else if (op.op === "moduleOrder") {
      runModuleOrder(store, op.order, rec.operations);
      rec.macros.push({ atOperation, numOperations: rec.operations.length - atOperation, op });
    } else if (op.op === "moduleNames") {
      runModuleNames(store, op.names, rec.operations);
      rec.macros.push({ atOperation, numOperations: rec.operations.length - atOperation, op });
    } else if (op.op === "highlight") {
      const concrete: Op = {
        op: "colorCategoricalMetadata",
        name: HIGHLIGHT_KEY,
        colors: op.colors.map((color, k) => [String(k), color] as [string, string]),
      };
      if (op.colors.length !== op.groups.length) throw new Error("highlight: one colour per label");
      if (highlightOnLeaves) highlightLeaves(store, op.groups);
      applyOp(store, concrete);
      rec.operations.push(concrete);
      rec.macros.push({ atOperation, numOperations: 1, op });
    } else {
      const result = applyOp(store, op, lenient);
      const expected = (op as { result?: boolean }).result;
      if (!lenient && expected !== undefined && expected !== result) {
        throw new Error(`${op.op} returned ${result}, expected ${expected}`);
      }
      rec.operations.push(lenient && typeof result === "boolean" ? { ...op, result } : op);
    }
  }
}

// v2 feature tags of a fixture (top-level `features`, omitted when empty, so v1 fixtures are unchanged).
// A fixture needs every tagged feature to replay.
const OP_FEATURES: Partial<Record<Op["op"], string>> = {
  expand: "hierarchy",
  regroup: "hierarchy",
  moduleLevel: "hierarchy",
  setModuleLevel: "hierarchy",
  moveModule: "move",
  moduleOrder: "move",
  setModuleOrder: "move",
  moduleNames: "names",
  resetLayout: "move",
  colorSelectedNodes: "colorOps",
  colorMatchingModules: "colorOps",
  colorModuleIds: "colorOps",
  colorNodesInModule: "colorOps",
  setDefaultHighlightColor: "colorOps",
  setSelectedScheme: "colorOps",
  setSelectedTone: "c3Tone",
  setSelectedOffset: "c3Tone",
  colorModuleHierarchyInAllNetworks: "hierarchyColor",
  colorByLayer: "colorBy",
  colorByPhysicalId: "colorBy",
  colorCategoricalMetadata: "metadata",
  colorRealMetadata: "metadata",
  colorRealIntervals: "metadata",
  highlight: "highlight",
  setNetworkName: "names",
  setModuleName: "names",
};

function scenarioFeatures(scenario: Scenario, inputFiles: any[], ops: Op[]) {
  const features = new Set<string>();
  for (const op of ops) {
    const f = OP_FEATURES[op.op];
    if (f) features.add(f);
    // modules addressed only by id (moduleLevel's expands carry both)
    if ((op as any).moduleId != null && (op as any).moduleIndex == null) features.add("moduleId");
  }
  if (scenario.nodeMetadata) features.add("metadata");
  if (scenario.labelNameHighlight) features.add("labelNameHighlight");
  if (scenario.split?.length) features.add("multilayerSplit");
  if (inputFiles.some((f) => f.format === "json")) features.add("json");
  // v3 (only v3 scenarios carry these fields)
  if (scenario.v3) {
    if (scenario.roundTrip) features.add("roundTrip");
    if (scenario.options.colorScheme !== undefined) features.add("colorScheme");
    if (scenario.options.colorTone !== undefined || scenario.options.colorOffset !== undefined) features.add("c3Tone");
    if (scenario.reloadStore) features.add("reloadStore");
    if (inputFiles.some((f) => f.colors !== undefined)) features.add("jsColors");
  }
  return [...features].sort();
}

// ---------------------------------------------------------------------------
// Dump
// ---------------------------------------------------------------------------

function nodeSizeFn(network: Network, maxNetworkFlow: number, moduleSize: string) {
  // Same expressions as getNodeSizeByPropForNetwork (alluvial/Diagram.ts:378-390)
  const { numLeafNodes } = network;
  if (moduleSize === "flow") return (n: { flow: number }) => n.flow / maxNetworkFlow;
  if (moduleSize === "nodes") return (n: { numLeafNodes: number }) => n.numLeafNodes / numLeafNodes;
  throw new Error(moduleSize);
}

function labelNames(module: Module, n: number, aggregate: boolean, highlight = false) {
  return module.getLargestLeafNodes(n, aggregate).map((node: any) => ({
    name: node.name,
    nodeId: node.nodeId,
    stateId: node.stateId ?? null,
    flow: node.flow,
    // v2 labelNameHighlight: the aggregated copies ({...leaf, flow: 0}) have no `insignificant` (a getter)
    highlightIndex: highlight ? node.highlightIndex ?? null : undefined,
    insignificant: highlight ? ("insignificant" in node ? node.insignificant : null) : undefined,
  }));
}

function layoutOptions(store: DiagramStore) {
  return {
    height: store.height,
    moduleWidth: store.moduleWidth,
    streamlineFraction: store.streamlineFraction,
    streamlineThreshold: store.streamlineThreshold,
    flowThreshold: store.flowThreshold,
    marginExponent: store.marginExponent,
    zeroMargins: store.zeroMargins,
    verticalAlign: store.verticalAlign,
    moduleSize: store.moduleSize,
    sortModulesBy: store.sortModulesBy,
  };
}

// The store options at construction, before any setOption op (fresh store, same options).
function initialLayoutOptions(options: StoreOptions) {
  return layoutOptions(new DiagramStore(options as any));
}

// options: the ctor options (scenario.options)
type Run = Prepared & Recording & { store: DiagramStore; options: StoreOptions };

function dumpScenario(run: Run, scenario: Scenario) {
  const { store, files, sources } = run;
  const split = !!scenario.split?.length;
  const diagram = store.diagram;
  const trace = traces.get(diagram)!;
  const opts = layoutOptions(store);
  const initialOpts = initialLayoutOptions(run.options);
  const { height, moduleWidth, streamlineFraction, zeroMargins } = opts;

  // --- Globals. Same expressions/evaluation order as Diagram.updateLayout.
  const numNetworks = diagram.children.length;
  const streamlineWidth = streamlineFraction * moduleWidth;
  const networkWidth = moduleWidth + streamlineWidth;
  const totalWidth = networkWidth * numNetworks - streamlineWidth;
  const maxNetworkFlow = Math.max(...diagram.children.map((n) => n.flow));

  const totalMargins: number[] = [];
  const visibleFlows: number[] = [];
  const visibleModuleCounts: number[] = [];
  diagram.children.forEach((network, i) => {
    const size = nodeSizeFn(network, maxNetworkFlow, opts.moduleSize);
    totalMargins[i] = 0;
    visibleFlows[i] = 0;
    visibleModuleCounts[i] = 0;
    for (const module of network.children) {
      if (!module.isVisible) continue;
      const p1 = trace.pass1Modules.get(module);
      if (!p1) throw new Error(`no pass-1 snapshot for ${module.id}`);
      totalMargins[i] += p1.margin;
      visibleFlows[i] += size(module as any);
      visibleModuleCounts[i]++;
    }
  });
  const maxTotalMargin = Math.max(...totalMargins);
  let usableHeight = height - maxTotalMargin;
  const maxMarginFractionOfHeight = zeroMargins ? 0 : 0.2;
  const marginFractionOfHeight = maxTotalMargin / height;
  let marginCapped = false;
  let moduleMarginScale: number | null = null;
  let scaledTotalMargin: number | null = null;
  if (marginFractionOfHeight > maxMarginFractionOfHeight) {
    marginCapped = true;
    moduleMarginScale = zeroMargins ? 0 : (maxMarginFractionOfHeight * height) / maxTotalMargin;
    scaledTotalMargin = maxTotalMargin * moduleMarginScale;
    usableHeight = height - scaledTotalMargin;
  }

  // Self-check: the engine's pass-2 heights must equal size * usableHeight
  // exactly, which validates the replicated usableHeight.
  let checked = 0;
  for (const network of diagram.children) {
    const size = nodeSizeFn(network, maxNetworkFlow, opts.moduleSize);
    for (const module of network.children) {
      if (!module.isVisible) continue;
      const expected = size(module as any) * usableHeight;
      if (module.height !== expected && !(Number.isNaN(module.height) && Number.isNaN(expected))) {
        throw new Error(
          `${scenario.name}: usableHeight check failed for ${module.id}: ${module.height} !== ${expected}`
        );
      }
      checked++;
    }
  }

  const networks = diagram.children.map((network, networkIndex) => {
    const file = files.find((f) => f.id === network.networkId);
    const leaves = [...network.leafNodes()]
      .map((leaf) => ({ leaf, key: leaf.stateId ?? leaf.nodeId }))
      .sort((a, b) =>
        a.key !== b.key
          ? a.key - b.key
          : a.leaf.identifier < b.leaf.identifier
          ? -1
          : a.leaf.identifier > b.leaf.identifier
          ? 1
          : 0
      )
      .map(({ leaf }) => [
        leaf.identifier,
        leaf.nodeId,
        leaf.stateId ?? null,
        leaf.moduleId,
        leaf.moduleLevel,
        leaf.highlightIndex,
        leaf.insignificant,
      ]);
    const identifiers = new Set(leaves.map((row) => row[0]));

    const links = network.getLinks(store.streamlineThreshold).map((link) => dumpLink(link));

    const hierarchy = network.hierarchicalChildren.map((node: any) =>
      "isLeaf" in node
        ? {
            type: "tree",
            path: node.path,
            moduleLevel: node.moduleLevel,
            isLeaf: node.isLeaf,
            maxModuleLevel: node.maxModuleLevel,
            ...rect(node),
          }
        : { type: "module", moduleId: node.moduleId }
    );

    return {
      networkId: network.networkId,
      name: network.name,
      index: networkIndex,
      file: {
        path: scenario.files[sources[networkIndex]],
        format: file?.format ?? null,
        numTopModules: file?.numTopModules ?? null,
        numLevels: file?.numLevels ?? null,
        isStateNetwork: file?.isStateNetwork ?? null,
        directed: file?.directed ?? null,
        codelength: file?.codelength ?? null,
        numNodes: file?.nodes.length ?? null,
        // v2 split only
        layerId: split ? file?.layerId ?? null : undefined,
        originalId: split ? file?.originalId ?? null : undefined,
      },
      ...rect(network),
      flow: network.flow,
      numLeafNodes: network.numLeafNodes,
      moduleFlowThreshold: network.flowThreshold,
      isCustomSorted: network.isCustomSorted,
      // Throws (TypeError on leafNodes().next().value) when a network has lost all its leaves, which the colour
      // ops can do with duplicate identifiers (fuzz seed 13214); null then.
      isHigherOrder: (() => {
        try {
          return network.isHigherOrder;
        } catch {
          return null;
        }
      })(),
      namePosition: network.namePosition,
      totalMargin: totalMargins[networkIndex],
      visibleFlow: visibleFlows[networkIndex],
      numVisibleModules: visibleModuleCounts[networkIndex],
      numModules: network.children.length,
      modules: network.children.map((module) => dumpModule(store, trace, module, !!scenario.labelNameHighlight)),
      numLinksAboveZero: network.getLinks(0).length,
      links,
      hierarchy,
      identifiersUnique: identifiers.size === leaves.length,
      leafColumns: [
        "identifier",
        "nodeId",
        "stateId",
        "moduleId",
        "moduleLevel",
        "highlightIndex",
        "insignificant",
      ],
      leaves,
    };
  });

  // the scenario ops (macros) and the concrete ops they issued
  const features = scenarioFeatures(scenario, run.inputFiles, [...scenario.ops, ...run.operations]);
  return {
    formatVersion: FIXTURE_FORMAT_VERSION,
    scenario: scenario.name,
    group: scenario.group,
    variant: scenario.variant,
    description: scenario.description,
    features: features.length ? features : undefined,
    inputs: {
      files: scenario.files,
      formats: files.map((f) => f.format),
      networkIds: files.map((f) => f.id),
      networkNames: files.map((f) => f.name),
      identifier: store.identifier,
      options: opts,
      // Only when a setOption op changed them: the options the diagram was built with.
      initialOptions: JSON.stringify(initialOpts) === JSON.stringify(opts) ? undefined : initialOpts,
      labelOptions: {
        fontSize: store.fontSize,
        adaptiveFontSize: store.adaptiveFontSize,
        multilineModuleNames: store.multilineModuleNames,
        aggregateStateNames: store.aggregateStateNames,
        showModuleNames: store.showModuleNames,
      },
      colorScheme: store.selectedSchemeName,
      // the ctor's c3 tone and offset, when the scenario sets them
      colorTone: scenario.options.colorTone,
      colorOffset: scenario.options.colorOffset,
      operations: run.operations,
      // --- v2, each only when used
      macros: run.macros.length ? run.macros : undefined,
      split: split ? scenario.split : undefined,
      networkSources: split ? sources : undefined,
      labelNameHighlight: scenario.labelNameHighlight ? true : undefined,
      nodeMetadata: run.nodeMetadata,
    },
    diagram: {
      ...rect(diagram),
      flow: diagram.flow,
      numNetworks,
      maxNetworkFlow,
      streamlineWidth,
      networkWidth,
      totalWidth,
      totalMargins,
      maxTotalMargin,
      marginFractionOfHeight,
      maxMarginFractionOfHeight,
      marginCapped,
      moduleMarginScale,
      scaledTotalMargin,
      usableHeight,
      visibleFlows,
      visibleModuleCounts,
      updateLayoutCalls: trace.calls,
      usableHeightCheckedModules: checked,
    },
    highlightColors: [...store.highlightColors],
    defaultHighlightColor: store.defaultHighlightColor,
    warnings: [...warnings],
    networks,
  };
}

function dumpModule(store: DiagramStore, trace: Trace, module: Module, nameHighlight: boolean) {
  const p1 = trace.pass1Modules.get(module);
  const visible = module.isVisible;
  // Label line count: replicated from react/Module.tsx:201-214 (LargestLeafNames)
  const heightPerLine = store.fontSize * 1.8;
  let maxLines = Math.ceil(module.height / heightPerLine);
  if (maxLines !== 0 && maxLines % 2 === 0) maxLines--;
  const aggregate = store.aggregateStateNames;
  return {
    moduleId: module.moduleId,
    id: module.id,
    path: module.path,
    moduleLevel: module.moduleLevel,
    maxModuleLevel: module.maxModuleLevel,
    index: module.index,
    flow: module.flow,
    numLeafNodes: module.numLeafNodes,
    meanNodeId: module.meanNodeId,
    enterFlow: module.enterFlow,
    exitFlow: module.exitFlow,
    visible,
    highlightIndex: module.highlightIndex,
    margin: module.margin,
    ...rect(module),
    pass1: p1 ? { margin: p1.margin, index: p1.index, ...rect(p1) } : null,
    label: {
      shown: visible && store.showModuleNames && module.textAnchor != null,
      textAnchor: module.textAnchor,
      namePosition: module.namePosition,
      idPosition: module.idPosition,
      customName: module.name,
      maxLines,
      names: maxLines > 0 ? labelNames(module, maxLines, aggregate, nameHighlight) : [],
      namesSingleLine: labelNames(module, 5, aggregate, nameHighlight),
    },
    groups: module.children.map((group) => {
      const g1 = trace.pass1Groups.get(group);
      return {
        id: group.id,
        highlightIndex: group.highlightIndex,
        insignificant: group.insignificant,
        flow: group.flow,
        numLeafNodes: group.numLeafNodes,
        ...rect(group),
        pass1: g1 ? rect(g1) : null,
        branches: group.children.map((branch) => ({
          side: branch.isLeft ? "left" : "right",
          flow: branch.flow,
          numLeafNodes: branch.numLeafNodes,
          ...rect(branch),
          streamlineNodes: branch.children.map((sn) => {
            const opposite = sn.opposite;
            const sortKey = trace.sortKeys.get(sn);
            return {
              id: sn.currentId,
              sourceId: sn.sourceId,
              targetId: sn.targetId,
              dangling: sn.isDangling,
              flow: sn.flow,
              numLeafNodes: sn.numLeafNodes,
              ...rect(sn),
              sortKey: sortKey === undefined ? null : sortKey,
              linked: sn.link != null,
              opposite: opposite
                ? {
                    networkId: opposite.networkId,
                    id: opposite.currentId,
                    moduleId: (opposite.getAncestor(MODULE) as Module | null)?.moduleId ?? null,
                  }
                : null,
            };
          }),
        })),
      };
    }),
  };
}

function dumpLink(link: StreamlineLink) {
  const end = (sn: StreamlineNode) => {
    const group = sn.parent?.parent as HighlightGroup | undefined;
    return {
      networkId: sn.networkId,
      moduleId: (sn.getAncestor(MODULE) as Module | null)?.moduleId ?? null,
      groupHighlightIndex: group?.highlightIndex ?? null,
      groupInsignificant: group?.insignificant ?? null,
      streamlineNodeId: sn.currentId,
    };
  };
  return {
    id: link.id,
    left: end(link.left),
    right: end(link.right),
    x0: link.x0,
    y0: link.y0,
    h0: link.h0,
    x1: link.x1,
    y1: link.y1,
    h1: link.h1,
    avgHeight: link.avgHeight,
    highlightIndex: link.highlightIndex,
    leftHighlightIndex: link.leftHighlightIndex,
    rightHighlightIndex: link.rightHighlightIndex,
    path: link.path,
  };
}

function geometrySignature(diagram: Diagram) {
  const parts: unknown[] = [];
  for (const network of diagram.children) {
    parts.push(network.networkId, rect(network));
    for (const module of network.children) {
      parts.push(module.moduleId, module.margin, module.index, rect(module));
      for (const group of module.children)
        for (const branch of group.children)
          for (const sn of branch.children) parts.push(sn.currentId, rect(sn));
    }
    for (const link of network.getLinks(0)) parts.push(link.id, link.path);
  }
  return JSON.stringify(parts);
}

// JSON with full double precision (JSON.stringify emits the shortest
// round-trip repr). Non-finite numbers are written as the bare tokens
// Infinity / -Infinity / NaN, which Python's json module reads natively.
// Layout: objects one key per line (1-space indent), except small flat objects
// (<= 6 primitive values) and arrays of primitives, which stay on one line,
// so the files stay diff-able but small.
function scalar(v: unknown): string {
  if (typeof v === "number" && !Number.isFinite(v)) return String(v);
  // `undefined` array entries (e.g. highlightColors after getHighlightIndex(undefined)) -> null, as JSON.stringify
  if (v === undefined) return "null";
  return JSON.stringify(v);
}

const isPrimitive = (v: unknown) => v === null || typeof v !== "object";

function format(value: unknown, indent: string): string {
  if (isPrimitive(value)) return scalar(value);
  const inner = indent + " ";
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    if (value.every(isPrimitive)) return `[${value.map(scalar).join(",")}]`;
    return `[\n${value.map((v) => inner + format(v, inner)).join(",\n")}\n${indent}]`;
  }
  const entries = Object.entries(value as object).filter(([, v]) => v !== undefined);
  if (entries.length === 0) return "{}";
  if (entries.length <= 6 && entries.every(([, v]) => isPrimitive(v)))
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}: ${scalar(v)}`).join(", ")}}`;
  return `{\n${entries
    .map(([k, v]) => `${inner}${JSON.stringify(k)}: ${format(v, inner)}`)
    .join(",\n")}\n${indent}}`;
}

function toJson(value: unknown) {
  return format(value, "") + "\n";
}

async function runScenario(
  testsDir: string,
  scenario: Scenario,
  opts: {
    lenient?: boolean;
    resolve?: (store: DiagramStore, op: Op) => Op;
    rec?: Recording;
    highlightOnLeaves?: boolean;
  } = {}
): Promise<Run> {
  const rec = opts.rec ?? { operations: [{ op: "setNetworks" }], macros: [] };
  const store = new DiagramStore(scenario.options as any);
  const prepared = await prepareFiles(testsDir, scenario, store.identifier, opts.highlightOnLeaves);
  store.setNetworks(prepared.files);
  runOps(store, scenario.ops, rec, opts);
  return { store, options: scenario.options, ...prepared, ...rec };
}

export async function main({
  repoRoot,
  tsRoot,
  outDir,
  v3Dir,
  v4Dir,
  only,
  large = false,
}: {
  repoRoot: string;
  tsRoot: string;
  outDir: string;
  v3Dir: string;
  v4Dir: string;
  only: string | null;
  large?: boolean;
}) {
  const testsDir = join(repoRoot, "tests");
  // the TS package's own jszip (the one parse-files.ts unzips with)
  JSZip = createRequire(join(tsRoot, "packages/alluvial-diagram/src/parsers/parse-files.ts"))("jszip");
  mkdirSync(outDir, { recursive: true });
  const written: string[] = [];

  for (const scenario of [...SCENARIOS, ...V3_SCENARIOS, ...V4_SCENARIOS]) {
    if (only && !scenario.name.includes(only)) continue;
    if (scenario.large && !large) continue;
    warnings = [];
    const run = await runScenario(testsDir, scenario);
    const { store } = run;
    const fixture: Record<string, unknown> = dumpScenario(run, scenario);
    const roundTrip = scenario.roundTrip ? await roundTripBlocks(run, scenario) : null;

    // Cross-check: the same scenario on the plain (unwrapped) engine must give
    // identical geometry, proving the snapshots are read-only.
    tracing = false;
    const plain = await runScenario(testsDir, scenario);
    if (roundTrip && JSON.stringify(savedFiles(plain.store)) !== JSON.stringify(roundTrip.savedFiles))
      throw new Error(`${scenario.name}: plain run saves other files`);
    tracing = true;
    const a = geometrySignature(store.diagram);
    const b = geometrySignature(plain.store.diagram);
    if (a !== b) throw new Error(`${scenario.name}: instrumented run differs from plain run`);
    if (roundTrip) Object.assign(fixture, roundTrip);
    const dir = scenario.v4 ? v4Dir : scenario.v3 ? v3Dir : outDir;
    mkdirSync(dir, { recursive: true });
    const path = join(dir, `${scenario.name}.json`);
    writeFileSync(path, toJson(fixture));
    written.push(path);
  }

  console.warn = origWarn;
  return written;
}

// ---------------------------------------------------------------------------
// v3: saved diagrams (docs/dev/saveload-plan.md §4, §7): the engine's own writer and loader
// ---------------------------------------------------------------------------

// The engine's writer (serializeDiagram) with the generator and the save id pinned, so the texts are reproducible.
const SAVE = { generator: "fixture", saveId: "fixture" };

function savedFiles(store: DiagramStore) {
  return serializeDiagram(store, SAVE);
}

// The edits of a `restore` scenario: the saved files as the user might load them (docs/dev/saveload-plan.md §4.4,
// §4.5). The texts are re-stringified like the writer's.
function editSavedFiles(texts: { name: string; text: string }[], restore: NonNullable<Scenario["restore"]>) {
  const edit = (t: { name: string; text: string }, fn: (value: any) => void) => {
    const value = JSON.parse(t.text);
    fn(value);
    return { name: t.name, text: JSON.stringify(value, null, 2) };
  };
  switch (restore) {
    case "shuffled": // loose files dropped in reverse order: loaded in saved order
      return [...texts].reverse();
    case "partial": // the last network's file is missing
      return texts.slice(0, -1);
    case "mixedSaves": // the first file is from another save
      return texts.map((t, i) => (i === 0 ? edit(t, (v) => (v.alluvial.diagram.saveId = "other")) : t));
    case "formatVersion2": // saved by a newer version
      return texts.map((t) => edit(t, (v) => (v.alluvial.formatVersion = 2)));
    case "badBlock": // the first file's block has no valid formatVersion
      return texts.map((t, i) => (i === 0 ? edit(t, (v) => (v.alluvial.formatVersion = "1")) : t));
    case "badOptions": // invalid option values and an unknown scheme
      return texts.map((t) =>
        edit(t, (v) => {
          v.alluvial.diagram.options.height = -1;
          v.alluvial.diagram.options.verticalAlign = "top";
          v.alluvial.diagram.colorScheme = "No such scheme";
        })
      );
    case "badColor": // an unknown tone and an offset that is no finite number
      return texts.map((t) =>
        edit(t, (v) => {
          v.alluvial.diagram.colorTone = "neon";
          v.alluvial.diagram.colorOffset = "90";
        })
      );
    case "nullColor": // a null tone (unknown) and a null offset (c3's default)
      return texts.map((t) =>
        edit(t, (v) => {
          v.alluvial.diagram.colorTone = null;
          v.alluvial.diagram.colorOffset = null;
        })
      );
    case "oddColor": // an inherited Object key, an array tone and an offset literal JSON.parse reads as Infinity
      return texts.map((t) => {
        const { name, text } = edit(t, (v) => {
          v.alluvial.diagram.colorScheme = "toString";
          v.alluvial.diagram.colorTone = ["strong"];
          v.alluvial.diagram.colorOffset = "@@OFFSET@@";
        });
        return { name, text: text.replace('"@@OFFSET@@"', "1e400") };
      });
    case "hugeOffset": // an integer literal beyond 2**53 (JSON.parse: the nearest double, finite)
      return texts.map((t) => {
        const { name, text } = edit(t, (v) => (v.alluvial.diagram.colorOffset = "@@OFFSET@@"));
        return { name, text: text.replace('"@@OFFSET@@"', "-300000000000000000123") };
      });
    case "legacyColor": // saved before #57: no tone or offset
      return texts.map((t) =>
        edit(t, (v) => {
          delete v.alluvial.diagram.colorTone;
          delete v.alluvial.diagram.colorOffset;
        })
      );
  }
}

// The web app's open path for saved files: parseAcceptedFiles (identifier "id"; stored identifiers win; one saved
// diagram is sorted by position), ids = file name without ".json" (the app's are random), then openNetworks on a
// fresh default store (the files carry the options).
async function openSavedFiles(
  texts: { name: string; text: string }[],
  zip: boolean,
  reloadStore: Scenario["reloadStore"] = undefined
) {
  let accepted: File[];
  if (zip) {
    const archive = new JSZip();
    for (const { name, text } of texts) archive.file(name, text, { date: new Date(0) });
    const bytes = await archive.generateAsync({ type: "uint8array" });
    accepted = [new File([bytes], "diagram.zip", { type: "application/zip", lastModified: 0 })];
  } else {
    accepted = texts.map(({ name, text }) => new File([text], name, { type: "application/json", lastModified: 0 }));
  }
  return openAccepted(accepted, texts.length, reloadStore);
}

// A zip written by someone else (Python's save_diagram), dropped on "Load networks" as is.
async function openSavedZip(bytes: Uint8Array) {
  return openAccepted([new File([bytes], "diagram.zip", { type: "application/zip", lastModified: 0 })]);
}

async function openAccepted(accepted: File[], expected?: number, reloadStore: Scenario["reloadStore"] = undefined) {
  const [parsed, allErrors] = await parseAcceptedFiles(accepted, [], ACCEPTED_FORMATS, "id");
  const errors = allErrors.filter((e) => !e.warning);
  if (errors.length) throw new Error(`saved files: parse errors ${JSON.stringify(errors.map((e) => e.errors))}`);
  if (expected !== undefined && parsed.length !== expected)
    throw new Error(`saved files: ${parsed.length} of ${expected} parsed`);
  if (!parsed.length) throw new Error("saved files: nothing parsed");
  parsed.forEach((file: any) => (file.id = String(file.filename).replace(/\.json$/, "")));
  const store = new DiagramStore((reloadStore ?? {}) as any);
  const openWarnings = store.openNetworks(parsed);
  return { store, files: parsed, openWarnings };
}

let JSZip: any;

// The restored store state that the dump does not cover: every saved option, the scheme with its c3 tone and offset
// (and a hash of its colours) and openNetworks' warnings.
function restoredState(store: DiagramStore, openWarnings: string[]) {
  return {
    options: store.getOptions(),
    colorScheme: store.selectedSchemeName,
    colorTone: store.selectedTone,
    colorOffset: store.selectedOffset,
    schemeSha256: createHash("sha256").update(JSON.stringify(store.selectedScheme)).digest("hex"),
    openWarnings,
  };
}

// The dump of an opened saved diagram (as a fixture's `savedReload`), with the restored state.
function reloadBlock(
  loose: { store: DiagramStore; files: any[]; openWarnings: string[] },
  scenario: Pick<Scenario, "name" | "group" | "variant">
) {
  const reloadScenario: Scenario = {
    name: `${scenario.name}/savedReload`,
    group: scenario.group,
    variant: `${scenario.variant}/savedReload`,
    files: loose.files.map((f: any) => f.filename),
    options: {},
    ops: [],
    description: "the `savedFiles` of this fixture: parseAcceptedFiles (loose files; a zip of them gives the same) + openNetworks",
    v3: true,
  };
  const savedReload: Record<string, unknown> = dumpScenario(
    {
      store: loose.store,
      options: {},
      files: loose.files,
      inputFiles: loose.files,
      sources: loose.files.map((_: unknown, i: number) => i),
      operations: [{ op: "openNetworks" }],
      macros: [],
    },
    reloadScenario
  );
  savedReload.restored = restoredState(loose.store, loose.openWarnings);
  return savedReload;
}

// `savedFiles` + `savedReload` of a finished run (scenario.roundTrip). `savedStore`: the saved store state that the
// dump does not cover (Python sets the display options from it before it writes). With `scenario.restore`, the
// edited files that were loaded are in `savedReloadFiles`.
async function roundTripBlocks(
  run: Run,
  scenario: Scenario,
  edit?: (texts: { name: string; text: string }[]) => { name: string; text: string }[]
) {
  const outer = warnings;
  const texts = savedFiles(run.store);
  const loaded = scenario.restore ? editSavedFiles(texts, scenario.restore) : edit ? edit(texts) : texts;
  // loaded as loose files and as one zip (must agree), dumped once
  warnings = [];
  const loose = await openSavedFiles(loaded, false, scenario.reloadStore);
  const looseWarnings = [...warnings];
  warnings = [];
  const zipped = await openSavedFiles(loaded, true, scenario.reloadStore);
  if (
    geometrySignature(loose.store.diagram) !== geometrySignature(zipped.store.diagram) ||
    JSON.stringify(loose.store.highlightColors) !== JSON.stringify(zipped.store.highlightColors) ||
    JSON.stringify(restoredState(loose.store, loose.openWarnings)) !==
      JSON.stringify(restoredState(zipped.store, zipped.openWarnings)) ||
    JSON.stringify(looseWarnings) !== JSON.stringify(warnings)
  )
    throw new Error(`${scenario.name}: saved files open differently from a zip`);
  warnings = looseWarnings;
  const savedReload = reloadBlock(loose, scenario);
  warnings = outer;
  return {
    savedStore: {
      options: run.store.getOptions(),
      colorScheme: run.store.selectedSchemeName,
      colorTone: run.store.selectedTone,
      colorOffset: run.store.selectedOffset,
    },
    ...(scenario.reloadStore ? { reloadStore: scenario.reloadStore } : {}),
    savedFiles: texts,
    ...(scenario.restore || (edit && loaded !== texts) ? { savedReloadFiles: loaded } : {}),
    savedReload,
  };
}

// --- TS-derived data (generate.mjs --make-data writes them; --check verifies them). Paths are relative to the
// alluvial-py repo root: the reference dumps in tests/data and the scheme data the package ships (src/alluvial/data).

// Where interpolators are sampled: a grid, the ends, outside [0, 1] and awkward floats
const INTERPOLATOR_TS = [
  ...Array.from({ length: 257 }, (_, i) => i / 256),
  -0.25, -1e-9, 1e-9, 0.1 + 0.2, 1 / 3, 2 / 3, 0.999999, 1 - 1e-12, 1.25, 7.5,
];
// The C3 scheme offsets dumped for every scheme and tone (null: c3's default)
const C3_OFFSETS = [null, 0, -45.5, 90, 245, 400];

// Modules for hierarchy(): one per node, like colorModuleHierarchyInAllNetworks
function hierarchyModules() {
  let seed = 12345;
  const rand = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
  const modules: { path: number[]; flow: number }[] = [];
  for (let top = 1; top <= 9; ++top) {
    const children = 1 + Math.floor(rand() * 4);
    for (let child = 1; child <= children; ++child) {
      const grandChildren = top % 3 === 0 ? 1 + Math.floor(rand() * 3) : 0;
      if (grandChildren === 0) modules.push({ path: [top, child], flow: rand() / top });
      for (let g = 1; g <= grandChildren; ++g) modules.push({ path: [top, child, g], flow: rand() / top });
    }
  }
  modules.push({ path: [10], flow: 0.001 });
  return modules;
}

export async function makeData({ d3, c3, d3Version }: { d3: any; c3: any; d3Version: string }) {
  const saved = warnings;
  warnings = [];
  const names = Object.keys(COLOR_SCHEMES) as SchemeName[];
  // ts_color_schemes.json (and the package's copy, src/alluvial/data/color-schemes.json): COLOR_SCHEMES (in its
  // key order) and SCHEME_GROUPS, with the scheme and tone a new store starts with. The package reads its defaults
  // from here, so they have one source: the TS store.
  const defaults = new DiagramStore();
  const schemes = toJson({
    source: "packages/alluvial-diagram/src/schemes/index.ts (COLOR_SCHEMES, SCHEME_GROUPS)",
    default: defaults.selectedSchemeName,
    defaultTone: defaults.selectedTone,
    names,
    groups: SCHEME_GROUPS,
    schemes: COLOR_SCHEMES,
  });

  // The d3 interpolators c3 takes as hue sources: the interpolated schemes, and Viridis of "C3 Viridis"
  const d3Name = new Map<unknown, string>();
  for (const key of Object.keys(d3).sort()) if (key.startsWith("interpolate")) d3Name.set(d3[key], key);
  const interpolators: Record<string, unknown> = {};
  const hueOf: Record<string, string> = {};
  const addInterpolator = (fn: any) => {
    const name = d3Name.get(fn);
    if (!name) throw new Error("hue source is not a d3 interpolator");
    if (name in interpolators) return name;
    const key = name.slice("interpolate".length);
    const basis = d3[`scheme${key}`];
    if (Array.isArray(basis) && Array.isArray(basis[basis.length - 1])) {
      // ramp(scheme) = interpolateRgbBasis(scheme[scheme.length - 1])
      interpolators[name] = { kind: "basis", colors: basis[basis.length - 1] };
    } else if (["Viridis", "Magma", "Inferno", "Plasma"].includes(key)) {
      // ramp(range) = t => range[floor(t * n)], n = 256: read back at the bin centres
      const range = Array.from({ length: 256 }, (_, i) => fn((i + 0.5) / 256));
      interpolators[name] = { kind: "ramp", colors: range };
    } else {
      interpolators[name] = { kind: "formula" };
    }
    return name;
  };
  for (const name of names) {
    const { hue } = hierarchyOptions(name, DEFAULT_TONE);
    if (typeof hue === "function") hueOf[name] = addInterpolator(hue);
  }
  addInterpolator(d3.interpolateViridis); // "C3 Viridis": c3's getScheme("Viridis")
  const interpolatorData = toJson({
    source: `d3 ${d3Version} interpolators (d3-scale-chromatic), dumped from the TS repo's node_modules`,
    schemes: hueOf,
    interpolators,
  });

  const sha256 = (colors: string[]) => createHash("sha256").update(JSON.stringify(colors)).digest("hex");
  const c3Names = names.filter((name) => typeof hierarchyOptions(name, DEFAULT_TONE).hue === "string");
  const c3Schemes = [];
  for (const name of c3Names)
    for (const tone of TONES)
      for (const offset of C3_OFFSETS) {
        const colors = schemeColors(name, tone, offset) as string[];
        c3Schemes.push({ scheme: name, tone, offset, length: colors.length, first: colors.slice(0, 8), sha256: sha256(colors) });
      }

  const modules = hierarchyModules();
  const HIERARCHY_CASES: [ToneName, number | null][] = [
    [DEFAULT_TONE, null],
    ["pastel", 100],
    ["deep", -30],
  ];
  const hierarchy = [];
  for (const name of names)
    for (const [tone, offset] of schemeIsHueSource(name) ? HIERARCHY_CASES : HIERARCHY_CASES.slice(0, 1)) {
      const color = c3.hierarchy(modules, hierarchyOptions(name, tone, offset));
      hierarchy.push({
        scheme: name,
        tone,
        offset,
        colors: color.modules.map((m: { path: number[]; color: string }) => [m.path.join(":"), m.color]),
      });
    }

  // A module with 119 sub-modules (flow 1/j) and one more top module: c3-colors 2.0.1 colours these differently in
  // c3's own default tone, "strong" (xfail test_hierarchy_wide_module_matches_ts); pinned to that tone, since in
  // the store's default tone ("vivid") this module happens to come out the same
  const wideTone: ToneName = "strong";
  const wideModules = [
    ...Array.from({ length: 119 }, (_, i) => ({ path: [1, i + 1], flow: 1 / (i + 1) })),
    { path: [2], flow: 1 },
  ];
  const hierarchyWide = ["C3 Sinebow", "C3 Oklch"].map((name) => {
    const color = c3.hierarchy(wideModules, hierarchyOptions(name as SchemeName, wideTone, null));
    return {
      scheme: name,
      tone: wideTone,
      offset: null,
      colors: color.modules.map((m: { path: number[]; color: string }) => [m.path.join(":"), m.color]),
    };
  });

  const samples: Record<string, string[]> = {};
  for (const name of Object.keys(interpolators)) samples[name] = INTERPOLATOR_TS.map((t) => d3[name](t));

  const reference = toJson({
    source:
      "packages/alluvial-diagram/src/schemes/index.ts (TONES, DEFAULT_TONE, schemeIsHueSource, defaultSchemeOffset, " +
      "schemeColors, hierarchyOptions) with @mapequation/c3 hierarchy()",
    tones: TONES,
    defaultTone: DEFAULT_TONE,
    hueSources: names.filter(schemeIsHueSource),
    defaultOffsets: Object.fromEntries(names.map((name) => [name, defaultSchemeOffset(name)])),
    interpolatorSamples: { t: INTERPOLATOR_TS, samples },
    c3Offsets: C3_OFFSETS,
    c3Schemes,
    hierarchyModules: modules,
    hierarchy,
    hierarchyWideModules: wideModules,
    hierarchyWide,
  });
  warnings = saved;
  return [
    { rel: "tests/data/ts_color_schemes.json", text: schemes },
    { rel: "src/alluvial/data/color-schemes.json", text: schemes },
    { rel: "src/alluvial/data/d3-interpolators.json", text: interpolatorData },
    { rel: "tests/data/ts_c3_schemes.json", text: reference },
  ];
}

// ---------------------------------------------------------------------------
// Differential fuzzing (generate.mjs --fuzz DIR): run every DIR/<case>/case.json
// (written by fuzz/gen.py) and write DIR/<case>/ts.json next to it.
// ---------------------------------------------------------------------------

type FuzzCase = {
  name: string;
  seed?: number;
  files: string[]; // absolute paths
  identifier?: "id" | "name";
  options: StoreOptions;
  ops: Op[];
  // v2 (gen.py --v2): per file, aligned with its node rows
  nodeMetadata?: (Record<string, unknown> | null)[][];
  // v2: input file indices split into layers (expandMultilayerFile)
  split?: number[];
  // c3 (gen.py --c3): DiagramStore ctor colour options
  color?: Pick<StoreOptions, "colorScheme" | "colorTone" | "colorOffset">;
  // c3: how the saved files are opened in both round trips (gen.py c3_open; see mutateSavedTexts)
  open?: OpenSpec;
};

type OpenSpec = {
  reloadStore?: Scenario["reloadStore"];
  mutations?: { key: "colorScheme" | "colorTone" | "colorOffset"; value: unknown }[];
  mutateFiles?: number[];
};

// The saved files with the diagram blocks edited by an OpenSpec (same as gen.py mutate_saved_texts): file i (in
// saved order) is edited when there is no mutateFiles or some j in it has j % n == i; a value {delete: true} removes
// the key, {raw: text} writes text as the JSON literal (numbers JSON.parse reads as non-finite or -0), anything else
// is set as is. The texts are re-stringified with JSON.stringify(value, null, 2).
function mutateSavedTexts(texts: { name: string; text: string }[], spec: OpenSpec | undefined) {
  if (!spec?.mutations?.length) return texts;
  const n = texts.length;
  return texts.map((t, i) => {
    if (spec.mutateFiles && !spec.mutateFiles.some((j) => j % n === i)) return t;
    const value = JSON.parse(t.text);
    const diagram = value.alluvial.diagram;
    const raws: string[] = [];
    for (const { key, value: v } of spec.mutations!) {
      if (isPlainObject(v) && (v as any).delete === true) delete diagram[key];
      else if (isPlainObject(v) && typeof (v as any).raw === "string") {
        diagram[key] = `@@RAW${raws.length}@@`;
        raws.push((v as any).raw);
      } else diagram[key] = v;
    }
    let text = JSON.stringify(value, null, 2);
    raws.forEach((raw, k) => (text = text.replace(`"@@RAW${k}@@"`, raw)));
    return { name: t.name, text };
  });
}

function isPlainObject(v: unknown) {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

const MODULE_OPS = new Set([
  "colorModule",
  "expand",
  "regroup",
  "moveModule",
  "colorMatchingModules",
  "colorModuleIds",
  "colorNodesInModule",
  "setModuleName",
]);

// Raw op from gen.py -> concrete op on the current store state. A raw networkIndex is reduced modulo the number of
// networks, a module op's raw moduleIndex modulo the number of modules at that point. colorSelectedNodes' raw
// {networkIndex, leafIndex} picks [...network.leafNodes()][leafIndex % n] and is recorded as
// {networkIndex, identifier}; so do the highlight macro's raw groups [label, [{networkIndex, leafIndex}]].
// A moduleLevel levels list is cycled to one k per network. v4: the moduleOrder macro's raw [networkIndex, spec]
// (spec: raw visible-module indices and "...", or "reverse"/"rotate") becomes [networkIndex, ids] (a repeated network
// or id dropped); the moduleNames macro's raw [networkIndex, moduleIndex, name] becomes [networkIndex, moduleId, name]
// (moduleIndex modulo all children).
function resolveOp(store: DiagramStore, op: Op): Op {
  // networkIndex modulo the network count (split layers add networks the generator does not know of)
  const numNetworks = store.diagram.children.length;
  const net = (networkIndex: number) => networkIndex % numNetworks;
  if (MODULE_OPS.has(op.op)) {
    const ref = op as ModuleRef;
    const networkIndex = net(ref.networkIndex);
    const n = store.diagram.children[networkIndex]?.children.length ?? 0;
    if (n === 0) throw new Error(`no modules in network ${networkIndex}`);
    return { ...op, networkIndex, moduleIndex: (ref.moduleIndex as number) % n } as Op;
  }
  if (op.op === "colorSelectedNodes") {
    const nodes = (op.nodes as any[]).flatMap(({ networkIndex, leafIndex }) => {
      const leaves = [...store.diagram.children[net(networkIndex)].leafNodes()];
      return leaves.length
        ? [{ networkIndex: net(networkIndex), identifier: leaves[leafIndex % leaves.length].identifier }]
        : [];
    });
    return { ...op, nodes };
  }
  if (op.op === "moduleLevel" && Array.isArray(op.levels)) {
    // one k per final network, cycling the raw list
    const raw = op.levels;
    return { ...op, levels: store.diagram.children.map((_, i) => raw[i % raw.length]) };
  }
  if (op.op === "moduleOrder") {
    const seenNetworks = new Set<number>();
    const order: [number, string[]][] = [];
    for (const [rawNetwork, spec] of op.order as [number, any][]) {
      const networkIndex = net(rawNetwork);
      if (seenNetworks.has(networkIndex)) continue;
      seenNetworks.add(networkIndex);
      const visible = store.diagram.children[networkIndex].children.filter((m) => m.isVisible).map((m) => m.moduleId);
      let ids: string[];
      if (spec === "reverse") ids = [...visible].reverse();
      else if (spec === "rotate") ids = visible.length ? [...visible.slice(1), visible[0]] : [];
      else {
        ids = [];
        for (const raw of spec as (number | string)[]) {
          const id = raw === "..." ? "..." : visible.length ? visible[(raw as number) % visible.length] : null;
          if (id != null && !ids.includes(id)) ids.push(id);
        }
      }
      order.push([networkIndex, ids]);
    }
    return { ...op, order };
  }
  if (op.op === "moduleNames") {
    const names: [number, string, string][] = [];
    for (const [rawNetwork, rawModule, name] of op.names as [number, number, string][]) {
      const networkIndex = net(rawNetwork);
      const children = store.diagram.children[networkIndex].children;
      if (children.length) names.push([networkIndex, children[rawModule % children.length].moduleId, name]);
    }
    return { ...op, names };
  }
  if (op.op === "highlight") {
    // raw groups [label, [{networkIndex, leafIndex}]] -> [label, identifiers]; an identifier keeps its first label
    const seen = new Set<string>();
    const groups = (op.groups as any[]).map(([label, refs]) => {
      const identifiers: string[] = [];
      for (const { networkIndex, leafIndex } of refs) {
        const leaves = [...store.diagram.children[net(networkIndex)].leafNodes()];
        if (!leaves.length) continue;
        const identifier = leaves[leafIndex % leaves.length].identifier;
        if (seen.has(identifier)) continue;
        seen.add(identifier);
        identifiers.push(identifier);
      }
      return [label, identifiers];
    }) as HighlightGroups;
    return { ...op, groups };
  }
  return op;
}

// v3 round trips of a fuzz case that TS ran: `savedFiles` + `savedReload`, as for the roundTrip fixtures (roundTripBlocks), written to <case>/ts-roundtrip.json; when TS
// throws in the round trip, {error, stack} instead. The scenario dump in ts.json is unchanged.
async function fuzzRoundTrip(run: Run, scenario: Scenario, open?: OpenSpec) {
  const outer = warnings;
  try {
    return await roundTripBlocks(
      run,
      open?.reloadStore ? { ...scenario, reloadStore: open.reloadStore } : scenario,
      (texts) => mutateSavedTexts(texts, open)
    );
  } catch (e) {
    return {
      error: String((e as Error)?.message ?? e),
      stack: String((e as Error)?.stack ?? "").split("\n").slice(0, 8),
    };
  } finally {
    warnings = outer;
  }
}

// Python-save -> TS-open (generate.mjs --open DIR): every DIR/<case>/saved/*.json (files written by alluvial-py's
// serialize_diagram, loaded in file-name order) is opened like the web app does (parseAcceptedFiles + openNetworks,
// loose files and a zip must agree) and dumped to DIR/<case>/ts-open.json; {error, stack} when TS throws.
export async function openMain({ caseDir, tsRoot }: { caseDir: string; tsRoot?: string }) {
  if (tsRoot) {
    JSZip = createRequire(join(tsRoot, "packages/alluvial-diagram/src/parsers/parse-files.ts"))("jszip");
  }
  const names = readdirSync(caseDir)
    .filter((d) => existsSync(join(caseDir, d, "saved")) || existsSync(join(caseDir, d, "saved.zip")))
    .sort();
  let errors = 0;
  for (const dir of names) {
    const savedZip = join(caseDir, dir, "saved.zip");
    if (existsSync(savedZip)) {
      // <case>/saved.zip: a zip written outside TS (Python's save_diagram), opened through the app's loader
      warnings = [];
      let out: unknown;
      try {
        out = reloadBlock(await openSavedZip(readFileSync(savedZip)), { name: dir, group: "open", variant: dir });
      } catch (e) {
        errors++;
        out = { error: String((e as Error)?.message ?? e), stack: String((e as Error)?.stack ?? "").split("\n").slice(0, 8) };
      }
      writeFileSync(join(caseDir, dir, "ts-open.json"), toJson(out));
      continue;
    }
    const savedDir = join(caseDir, dir, "saved");
    const texts = readdirSync(savedDir)
      .filter((f) => f.endsWith(".json"))
      .sort()
      .map((name) => ({ name, text: readFileSync(join(savedDir, name), "utf8") }));
    // <case>/open.json (Python's c3 fuzz cases): {reloadStore}, the opening store's ctor colour options
    const openPath = join(caseDir, dir, "open.json");
    const reloadStore = existsSync(openPath) ? JSON.parse(readFileSync(openPath, "utf8")).reloadStore : undefined;
    warnings = [];
    let out: unknown;
    try {
      const loose = await openSavedFiles(texts, false, reloadStore);
      const looseWarnings = [...warnings];
      warnings = [];
      const zipped = await openSavedFiles(texts, true, reloadStore);
      if (
        geometrySignature(loose.store.diagram) !== geometrySignature(zipped.store.diagram) ||
        JSON.stringify(restoredState(loose.store, loose.openWarnings)) !==
          JSON.stringify(restoredState(zipped.store, zipped.openWarnings))
      )
        throw new Error(`${dir}: saved files open differently from a zip`);
      warnings = looseWarnings;
      out = reloadBlock(loose, { name: dir, group: "open", variant: dir });
    } catch (e) {
      errors++;
      out = {
        error: String((e as Error)?.message ?? e),
        stack: String((e as Error)?.stack ?? "").split("\n").slice(0, 8),
      };
    }
    writeFileSync(join(caseDir, dir, "ts-open.json"), toJson(out));
  }
  console.warn = origWarn;
  return { cases: names.length, errors };
}

export async function fuzzMain({ caseDir, tsRoot }: { caseDir: string; tsRoot?: string }) {
  if (tsRoot) {
    JSZip = createRequire(join(tsRoot, "packages/alluvial-diagram/src/parsers/parse-files.ts"))("jszip");
  }
  const names = readdirSync(caseDir)
    .filter((d) => existsSync(join(caseDir, d, "case.json")))
    .sort();
  let errors = 0;
  for (const dir of names) {
    const c: FuzzCase = JSON.parse(readFileSync(join(caseDir, dir, "case.json"), "utf8"));
    const options: StoreOptions = { ...c.options, ...c.color, identifier: c.identifier ?? "id" };
    const scenario: Scenario = {
      name: c.name,
      group: "fuzz",
      variant: c.name,
      files: c.files,
      options,
      ops: c.ops,
      description: `fuzz seed ${c.seed ?? "?"}`,
      nodeMetadata: c.nodeMetadata ? async () => c.nodeMetadata! : undefined,
      split: c.split,
    };
    warnings = [];
    const rec: Recording = { operations: [{ op: "setNetworks" }], macros: [] };
    let out: unknown;
    try {
      const run = await runScenario(caseDir, scenario, {
        lenient: true,
        resolve: resolveOp,
        rec,
        highlightOnLeaves: true,
      });
      out = dumpScenario(run, scenario);
      if (JSZip) writeFileSync(join(caseDir, dir, "ts-roundtrip.json"), toJson(await fuzzRoundTrip(run, scenario, c.open)));
    } catch (e) {
      errors++;
      out = {
        scenario: c.name,
        error: String((e as Error)?.message ?? e),
        stack: String((e as Error)?.stack ?? "").split("\n").slice(0, 8),
        opsApplied: rec.operations.slice(1),
      };
    }
    writeFileSync(join(caseDir, dir, "ts.json"), toJson(out));
  }
  console.warn = origWarn;
  return { cases: names.length, errors };
}
