// v3 scenarios (docs/dev/port-notes/v3-webapp-json.md §8): round trips through the web-app files writer,
// `checkColors` inputs and colour schemes. Written to tests/fixtures/v3/ (README "v3
// scenarios"). The v1/v2 scenarios in scenarios.ts are untouched; v3 scenarios built from one of them copy it
// (files, options, ops, metadata) and add v3 fields, under the name `${base}__${suffix}`.

import { SCENARIOS, type Op, type Scenario } from "./scenarios";

const COLOR_MATCHING: Op = { op: "colorMatchingModulesInAllNetworks" };

const byName = new Map(SCENARIOS.map((s) => [s.name, s]));

function derive(base: string, suffix: string, extra: Partial<Scenario> & { description: string }): Scenario {
  const s = byName.get(base);
  if (!s) throw new Error(`v3: no base scenario ${base}`);
  const { description, ...rest } = extra;
  return {
    ...s,
    name: `${base}__${suffix}`,
    variant: `${s.variant}__${suffix}`,
    description: `${s.description}; ${description}`,
    ...rest,
    v3: true,
  };
}

function scenario(
  group: string,
  variant: string,
  files: string[],
  extra: Partial<Scenario> & { description: string }
): Scenario {
  return { name: `${group}__${variant}`, group, variant, files, options: {}, ops: [], ...extra, v3: true };
}

const ROUND_TRIP = "saved files + reload";
// hand-written .stree pair with top-level insignificant paths ("1;1;3;"); the saved files keep them as ";" strings
const INSIG = [0, 1].map((t) => `data/insig_t${t}.stree`);

// --- 1. Round trips: the base scenario, then `savedFiles` (the engine's serializeDiagram) + `savedReload`
// (parseAcceptedFiles of those files + openNetworks; docs/dev/saveload-plan.md §7).
const roundTripBases = [
  "multilevel-tree__default",
  "multilevel-tree__colored",
  "multilevel-tree__expand",
  "multilevel-tree__expandColored",
  "multilevel-tree__expandRegroup",
  "multilevel-tree__moveDown",
  "debug5-stree__colored",
  "planted-json__colored",
  "states-ftree__colored",
  "mlayer-split__colored",
  "planted-ftree__highlight",
];

const ROUND_TRIPS: Scenario[] = [
  ...roundTripBases.map((base) =>
    derive(base, "roundTrip", { roundTrip: true, description: ROUND_TRIP })
  ),
  derive("multilevel-tree__colored", "names__roundTrip", {
    ops: [
      COLOR_MATCHING,
      { op: "setNetworkName", networkIndex: 1, name: "Middle (renamed)" },
      { op: "setModuleName", networkIndex: 0, moduleIndex: 0, name: "Named module" },
    ],
    roundTrip: true,
    description: `setNetworkName + setModuleName; ${ROUND_TRIP} (network and module names kept)`,
  }),
  derive("states-ftree__colored", "name__roundTrip", {
    options: { identifier: "name" },
    roundTrip: true,
    description: `identifier="name" (duplicate identifiers); ${ROUND_TRIP}`,
  }),
  scenario("insig-stree", "colored__roundTrip", INSIG, {
    ops: [COLOR_MATCHING],
    roundTrip: true,
    description: `colorMatchingModulesInAllNetworks(); ${ROUND_TRIP} (";" paths keep the insignificance)`,
  }),
  scenario("insig-stree", "expandColored__roundTrip", INSIG, {
    ops: [{ op: "expand", networkIndex: 0, moduleId: "1" }, COLOR_MATCHING],
    roundTrip: true,
    description: `expand module 1 of network 0, colorMatchingModulesInAllNetworks(); ${ROUND_TRIP}`,
  }),
  derive("science-stree__nameColored", "roundTrip", {
    roundTrip: true,
    large: true,
    description: `${ROUND_TRIP} (large: --large only)`,
  }),
];

// --- 2. checkColors (v3-webapp-json.md §5): hand-written Infomap-JSON inputs with `colors`.
const JS_A = "data/jscolors_a.json"; // colors: ["#f00", "#0f0"], node highlightIndex 1/1/5/-1/unset
const JS_B = "data/jscolors_b.json"; // colors: true, node color "#0f0"/"#00f"/null(+highlightIndex 4)/"#0f0"/unset
const JS_C = "data/jscolors_c.json"; // colors: {...} (ignored), node colors ignored

const JSCOLORS: Scenario[] = [
  scenario("jscolors-a", "default", [JS_A], { description: "top-level colors list, nodes carry highlightIndex (5 is out of range)" }),
  scenario("jscolors-b", "default", [JS_B], { description: "colors: true, nodes carry color strings" }),
  scenario("jscolors-abc", "default", [JS_A, JS_B, JS_C], {
    description: "list + true + object: B's #0f0 gets A's dummy index 0 (#f00); C ignored",
  }),
  scenario("jscolors-abc", "colored", [JS_A, JS_B, JS_C], {
    ops: [COLOR_MATCHING],
    description: "as default, then colorMatchingModulesInAllNetworks() replaces the palette with the scheme",
  }),
  scenario("jscolors-abc", "default__roundTrip", [JS_A, JS_B, JS_C], {
    roundTrip: true,
    description: `as default; ${ROUND_TRIP} (the saved files keep the palette)`,
  }),
];

// --- 3. Colour schemes (v3-webapp-json.md §6): ctor colorScheme + colorMatchingModulesInAllNetworks.
const SCHEME_NAMES = ["Paired", "Set1", "Tableau20", "Mural", "C3 Turbo", "Rainbow", "Greys"];
const MULTILEVEL = byName.get("multilevel-tree__default")!.files;

const SCHEMES: Scenario[] = [
  ...SCHEME_NAMES.map((name) =>
    scenario("multilevel-tree", `scheme${name.replace(/ /g, "")}`, MULTILEVEL, {
      options: { colorScheme: name },
      ops: [COLOR_MATCHING],
      description: `colorScheme "${name}", then colorMatchingModulesInAllNetworks()`,
    })
  ),
  scenario("multilevel-tree", "schemeSwitch", MULTILEVEL, {
    ops: [COLOR_MATCHING, { op: "setSelectedScheme", name: "Set1" }, { op: "colorModuleIdsInAllNetworks" }],
    description:
      'colorMatching (default scheme), setSelectedScheme("Set1") (no recolour), colorModuleIdsInAllNetworks() (appends Set1 colours)',
  }),
];

// --- 4. Saved diagrams (docs/dev/saveload-plan.md §7.2): every option, the scheme, names, a custom order with hidden
// modules, bipartite nodes hidden (E19), Infomap's own keys, named split layers, and the restore warnings.
const order = (...entries: [number, string[]][]): Op => ({ op: "moduleOrder", order: entries });
const name = (networkIndex: number, moduleId: string, value: string): Op => ({
  op: "setModuleName",
  networkIndex,
  moduleId,
  name: value,
});

// every saved option away from its default (showBipartiteNodes has no effect on these trees)
const ALL_OPTIONS = {
  height: 432,
  marginExponent: 3,
  zeroMargins: true,
  moduleWidth: 60,
  streamlineFraction: 1.5,
  streamlineThreshold: 0.5,
  streamlineOpacity: 0.5,
  flowThreshold: 0.01,
  defaultHighlightColor: "#aaaaaa",
  verticalAlign: "justify",
  moduleSize: "nodes",
  sortModulesBy: "nodes",
  showModuleId: true,
  showModuleNames: false,
  multilineModuleNames: false,
  showNetworkNames: false,
  aggregateStateNames: false,
  titleCaseModuleNames: true,
  hierarchicalModules: "outline",
  hierarchicalModuleOffset: 3,
  hierarchicalModuleOpacity: 0.25,
  dropShadow: true,
  fontSize: 11,
  networkFontSize: 12,
  adaptiveFontSize: true,
  showBipartiteNodes: false,
  colorScheme: "Paired",
} as const;

const OPTIONS_OPS: Op[] = [
  COLOR_MATCHING,
  { op: "expand", networkIndex: 0, moduleId: "1" },
  order([0, ["2", "..."]], [2, ["...", "1"]]),
  name(0, "2", "Two"),
  name(1, "1", "Eins"),
  { op: "setNetworkName", networkIndex: 2, name: "Last network" },
];

const RESTORES = ["shuffled", "partial", "mixedSaves", "formatVersion2", "badBlock", "badOptions"] as const;

const SAVED: Scenario[] = [
  scenario("multilevel-tree", "options__roundTrip", MULTILEVEL, {
    options: ALL_OPTIONS,
    ops: OPTIONS_OPS,
    roundTrip: true,
    description: `every saved option changed, colorScheme "Paired", colorMatching, expand, moduleOrder, names; ${ROUND_TRIP}`,
  }),
  ...RESTORES.map((restore) =>
    scenario("multilevel-tree", `restore${restore[0].toUpperCase()}${restore.slice(1)}__roundTrip`, MULTILEVEL, {
      options: ALL_OPTIONS,
      ops: OPTIONS_OPS,
      roundTrip: true,
      restore,
      description: `as options__roundTrip; the saved files edited (${restore}) before the reload`,
    })
  ),
  derive("multilevel-tree__flowThreshold40", "orderHidden__roundTrip", {
    ops: [order([0, ["...", "1"]], [1, ["2", "..."]])],
    roundTrip: true,
    description: `moduleOrder with hidden modules; ${ROUND_TRIP} (moduleOrder lists the hidden modules too)`,
  }),
  scenario("bipartite-json", "hidden__roundTrip", [0, 1].map((t) => `data/bipartite_t${t}.json`), {
    options: { showBipartiteNodes: false },
    ops: [COLOR_MATCHING],
    roundTrip: true,
    description: `hand-written bipartite JSON, showBipartiteNodes false at build (E19), colorMatching; ${ROUND_TRIP}`,
  }),
  derive("planted-json__default", "passthrough__roundTrip", {
    roundTrip: true,
    description: `${ROUND_TRIP} (Infomap's version, args, directed, modules, ... passed through)`,
  }),
  derive("mlayer-named-json__default", "roundTrip", {
    roundTrip: true,
    description: `${ROUND_TRIP} (split layers named from \`layers\`, which is passed through)`,
  }),
];

// --- 5. c3 tone and offset (web app 1.16, #47) and their save (#57): the C3 schemes in every tone and at several
// offsets, C3 Oklch, the colouring by module hierarchy (colorModuleHierarchyInAllNetworks) with hue sources (C3,
// interpolated) and seeds (list schemes), the setters, and saved tone/offset round trips with the restore rules.
const HIERARCHY: Op = { op: "colorModuleHierarchyInAllNetworks" };
const LEVEL2: Op = { op: "moduleLevel", levels: 2 };
const TONE_NAMES = ["vivid", "bright", "strong", "deep", "dark", "soft", "pastel", "muted"];
const DEBUG5_STREE = [0, 1].map((t) => `data/debug5_${t}.stree`);

const C3_TONES: Scenario[] = [
  ...TONE_NAMES.map((tone) =>
    scenario("multilevel-tree", `tone${tone[0].toUpperCase()}${tone.slice(1)}`, MULTILEVEL, {
      options: { colorTone: tone },
      ops: [COLOR_MATCHING],
      description: `colorTone "${tone}" (the default scheme), then colorMatchingModulesInAllNetworks()`,
    })
  ),
  ...([
    ["C3 Oklch", undefined, undefined],
    ["C3 Oklch", "strong", 0],
    ["C3 Oklch", "deep", -90],
    ["C3 Oklch", "pastel", 1000.5],
    ["C3 Turbo", "dark", 30],
    ["C3 Viridis", "soft", -1e-7],
    ["C3 Rainbow", "vivid", 359.99],
  ] as [string, string | undefined, number | undefined][]).map(([colorScheme, colorTone, colorOffset]) =>
    scenario(
      "multilevel-tree",
      `scheme${colorScheme.replace(/ /g, "")}${colorTone ?? ""}${colorOffset === undefined ? "" : `Offset${String(colorOffset).replace(/[-.]/g, (c) => (c === "-" ? "m" : "p"))}`}`,
      MULTILEVEL,
      {
        options: { colorScheme, colorTone, colorOffset },
        ops: [COLOR_MATCHING],
        description: `colorScheme "${colorScheme}", colorTone ${colorTone ?? "default"}, colorOffset ${colorOffset ?? "default"}, then colorMatchingModulesInAllNetworks()`,
      }
    )
  ),
  scenario("multilevel-tree", "toneSetters", MULTILEVEL, {
    ops: [
      { op: "setSelectedTone", tone: "vivid" },
      { op: "setSelectedOffset", offset: -30 },
      { op: "colorModuleIdsInAllNetworks" },
      { op: "setSelectedScheme", name: "C3 Turbo" },
      COLOR_MATCHING,
    ],
    description:
      'setSelectedTone("vivid"), setSelectedOffset(-30), colorModuleIdsInAllNetworks(), setSelectedScheme("C3 Turbo") (resets the offset, keeps the tone), colorMatching',
  }),
];

const HIERARCHIES: Scenario[] = [
  scenario("multilevel-tree", "hierarchy", MULTILEVEL, {
    ops: [HIERARCHY],
    description: "colorModuleHierarchyInAllNetworks() (the default scheme, top modules only)",
  }),
  scenario("multilevel-tree", "hierarchyLevel2", MULTILEVEL, {
    ops: [LEVEL2, HIERARCHY],
    description: "moduleLevel 2, then colorModuleHierarchyInAllNetworks()",
  }),
  scenario("multilevel-tree", "hierarchyExpand", MULTILEVEL, {
    ops: [
      { op: "expand", networkIndex: 0, moduleId: "1" },
      { op: "expand", networkIndex: 1, moduleId: "2" },
      HIERARCHY,
      { op: "regroup", networkIndex: 0, moduleId: "1:1" },
      HIERARCHY,
    ],
    description:
      "expand 1 (network 0) and 2 (network 1), colorModuleHierarchyInAllNetworks(), regroup 1:1, colour again (the regrouped module is new)",
  }),
  derive("multilevel-tree__flowThreshold40", "hierarchyHidden", {
    ops: [LEVEL2, HIERARCHY],
    description: "moduleLevel 2, then colorModuleHierarchyInAllNetworks() (hidden modules stay gray)",
  }),
  scenario("multilevel-tree", "hierarchyOklchPastel", MULTILEVEL, {
    options: { colorScheme: "C3 Oklch", colorTone: "pastel", colorOffset: 120 },
    ops: [LEVEL2, HIERARCHY],
    description: 'C3 Oklch, tone "pastel", offset 120; moduleLevel 2, colorModuleHierarchyInAllNetworks()',
  }),
  scenario("multilevel-tree", "hierarchyViridisDeep", MULTILEVEL, {
    options: { colorScheme: "Viridis", colorTone: "deep", colorOffset: 45 },
    ops: [LEVEL2, HIERARCHY],
    description: 'interpolated Viridis as c3 hue source, tone "deep", offset 45; moduleLevel 2, hierarchy colouring',
  }),
  scenario("multilevel-tree", "hierarchySpectral", MULTILEVEL, {
    options: { colorScheme: "Spectral" },
    ops: [LEVEL2, HIERARCHY],
    description: "interpolated Spectral (diverging, rgbBasis) as c3 hue source; moduleLevel 2, hierarchy colouring",
  }),
  scenario("multilevel-tree", "hierarchyPaired", MULTILEVEL, {
    options: { colorScheme: "Paired", colorTone: "muted" },
    ops: [LEVEL2, HIERARCHY],
    description: "Paired (a list scheme: c3 seeds, the tone ignored); moduleLevel 2, hierarchy colouring",
  }),
  scenario("debug5-stree", "hierarchy", DEBUG5_STREE, {
    ops: [LEVEL2, HIERARCHY],
    description: "stree with insignificant (';') tree paths; moduleLevel 2, hierarchy colouring",
  }),
  scenario("insig-stree", "hierarchy", INSIG, {
    ops: [LEVEL2, HIERARCHY],
    description: "stree with top-level insignificant paths; moduleLevel 2, hierarchy colouring",
  }),
  // A module with 119 sub-modules: c3-colors 2.0.1 colours it differently from @mapequation/c3 2.0.1
  // (xfail in tests/test_v3_fixtures.py, C3_WIDE_XFAIL)
  // Pinned to C3 Sinebow in c3's "strong" tone, where the divergence is known
  scenario("wide-tree", "hierarchyLevel2", ["data/wide_t0.tree"], {
    options: { colorScheme: "C3 Sinebow", colorTone: "strong" },
    ops: [LEVEL2, HIERARCHY],
    description: "one module with 119 sub-modules; moduleLevel 2, hierarchy coloring (C3 Sinebow, strong)",
  }),
  // Non-numeric path parts ("1:x:1" -> [1, NaN, 1]): c3 keys modules by the joined path, so the NaN parts match
  scenario("nanpath-json", "hierarchyLevel2", ["data/nanpath_t0.json"], {
    ops: [LEVEL2, HIERARCHY],
    description: "string paths with a non-numeric part (1:x:*, 2:y:1, z:*); moduleLevel 2, hierarchy colouring",
  }),
];

const TONE_SAVE = {
  options: { colorScheme: "C3 Oklch", colorTone: "soft", colorOffset: 123.5 },
  ops: [LEVEL2, HIERARCHY],
};
const COLOR_RESTORES = ["badColor", "nullColor", "legacyColor", "oddColor", "hugeOffset"] as const;

const TONE_SAVED: Scenario[] = [
  scenario("multilevel-tree", "toneOffset__roundTrip", MULTILEVEL, {
    ...TONE_SAVE,
    roundTrip: true,
    description: `C3 Oklch, tone "soft", offset 123.5, moduleLevel 2, hierarchy colouring; ${ROUND_TRIP}`,
  }),
  scenario("multilevel-tree", "toneDefault__roundTrip", MULTILEVEL, {
    options: { colorScheme: "Set1" },
    ops: [COLOR_MATCHING],
    roundTrip: true,
    description: `Set1, default tone and offset (written as "strong" and null), colorMatching; ${ROUND_TRIP}`,
  }),
  ...COLOR_RESTORES.map((restore) =>
    scenario("multilevel-tree", `toneRestore${restore[0].toUpperCase()}${restore.slice(1)}__roundTrip`, MULTILEVEL, {
      ...TONE_SAVE,
      roundTrip: true,
      restore,
      description: `as toneOffset__roundTrip; the saved files edited (${restore}) before the reload`,
    })
  ),
  scenario("multilevel-tree", "toneReloadSameScheme__roundTrip", MULTILEVEL, {
    ...TONE_SAVE,
    roundTrip: true,
    restore: "legacyColor",
    reloadStore: { colorScheme: "C3 Oklch", colorTone: "dark", colorOffset: 10 },
    description: `as toneOffset__roundTrip, saved without tone and offset, opened by a store with the same scheme (tone "dark", offset 10 kept)`,
  }),
  scenario("multilevel-tree", "toneReloadOtherScheme__roundTrip", MULTILEVEL, {
    ...TONE_SAVE,
    roundTrip: true,
    restore: "legacyColor",
    reloadStore: { colorScheme: "C3 Turbo", colorTone: "dark", colorOffset: 10 },
    description: `as toneOffset__roundTrip, saved without tone and offset, opened by a store with another scheme (offset reset, tone "dark" kept)`,
  }),
  scenario("multilevel-tree", "toneReloadOverride__roundTrip", MULTILEVEL, {
    ...TONE_SAVE,
    roundTrip: true,
    reloadStore: { colorScheme: "C3 Oklch", colorTone: "dark", colorOffset: 10 },
    description: `as toneOffset__roundTrip, opened by a store with the same scheme (the saved tone and offset win)`,
  }),
];

export const V3_SCENARIOS: Scenario[] = [
  ...ROUND_TRIPS,
  ...JSCOLORS,
  ...SCHEMES,
  ...SAVED,
  ...C3_TONES,
  ...HIERARCHIES,
  ...TONE_SAVED,
];
