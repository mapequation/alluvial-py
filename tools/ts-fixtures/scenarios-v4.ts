// v4 scenarios (docs/dev/port-notes/v4-names-order.md §5): `module_order=` as the moduleOrder macro (recorded as
// one setModuleOrder op, fix round B1), `module_names=` as setModuleName ops, and round trips through the web-app files.
// Written to tests/fixtures/v4/ (README "v4 scenarios"). Every scenario keeps `layout()`'s
// step order (expand, module level, colouring or highlight, module order, names), so tests/test_v4_fixtures.py
// reproduces each one through public `layout()` arguments. Scenarios built from a v1/v2 one copy it (files,
// options, ops, metadata) under `${base}__${suffix}`.

import { SCENARIOS, type Op, type Scenario } from "./scenarios";

const COLOR_MATCHING: Op = { op: "colorMatchingModulesInAllNetworks" };
const ROUND_TRIP = "web-app files + reload";

const byName = new Map(SCENARIOS.map((s) => [s.name, s]));

function derive(base: string, suffix: string, extra: Partial<Scenario> & { description: string }): Scenario {
  const s = byName.get(base);
  if (!s) throw new Error(`v4: no base scenario ${base}`);
  const { description, ops = [], ...rest } = extra;
  return {
    ...s,
    name: `${base}__${suffix}`,
    variant: `${s.variant}__${suffix}`,
    description: `${s.description}; ${description}`,
    ...rest,
    ops: [...s.ops, ...ops], // the base ops first, then the v4 ones
    v3: true,
    v4: true,
  };
}

const order = (...entries: [number, string[]][]): Op => ({ op: "moduleOrder", order: entries });
const name = (networkIndex: number, moduleId: string, value: string): Op => ({
  op: "setModuleName",
  networkIndex,
  moduleId,
  name: value,
});

export const V4_SCENARIOS: Scenario[] = [
  // --- module order
  derive("multilevel-tree__default", "order", {
    ops: [order([0, ["3", "1"]], [2, ["...", "1"]])],
    description: 'moduleOrder: network 0 ["3", "1"] (the rest above), network 2 ["...", "1"] (1 on top)',
  }),
  derive("multilevel-tree__default", "orderReverse", {
    ops: [order([2, ["4", "3", "2", "1"]], [1, ["3", "2", "1"]])],
    description: "moduleOrder: networks 1 and 2 reversed (given in reverse network order; run in ascending order)",
  }),
  derive("multilevel-tree__default", "orderNoop", {
    ops: [order([0, ["1", "2"]], [1, ["..."]])],
    description: "moduleOrder that is already the layout order: no moves, no custom flag",
  }),
  derive("multilevel-tree__colored", "order", {
    ops: [order([0, ["4", "...", "2"]], [1, ["2", "3"]])],
    description: 'colorMatching, then moduleOrder network 0 ["4", "...", "2"], network 1 ["2", "3"]',
  }),
  derive("multilevel-tree__sortNodes", "order", {
    ops: [order([0, ["2"]], [2, ["...", "3", "1"]])],
    description: "sortModulesBy nodes sets the start, moduleOrder moves from there",
  }),
  derive("planted-ftree__coloredSortHighlightIndex", "order", {
    ops: [order([1, ["...", "1"]], [2, ["4", "3"]])],
    description: "sortModulesBy highlightIndex after colouring, then moduleOrder",
  }),
  derive("planted-ftree__flowThreshold40", "orderHidden", {
    ops: [order([0, ["3", "...", "2"]], [1, ["2", "4"]])],
    description:
      "flowThreshold 0.4 (hidden modules after the visible ones): moduleOrder moves only visible modules past visible ones",
  }),
  derive("multilevel-tree__level2", "order", {
    ops: [order([0, ["2:1", "1:3", "..."]], [2, ["4", "...", "1:1"]])],
    description: "moduleLevel 2, then moduleOrder with sub-module ids (breaks the path grouping)",
  }),
  derive("multilevel-tree__level2Highlight", "order", {
    ops: [order([1, ["3:3", "..."]])],
    description: "moduleLevel 2 + highlight, then moduleOrder",
  }),
  // --- names
  derive("multilevel-tree__colored", "names", {
    ops: [name(0, "1", "Alpha"), name(0, "4", "Delta"), name(2, "2", "Beta"), name(0, "1", "Alpha 2")],
    description: "colorMatching, setModuleName (one module renamed twice)",
  }),
  derive("multilevel-tree__colored", "namesOrder__roundTrip", {
    ops: [order([0, ["3", "1"]], [1, ["...", "1"]]), name(0, "3", "Gamma"), name(1, "1", "One"), name(2, "4", "Four")],
    roundTrip: true,
    description: `moduleOrder + setModuleName; ${ROUND_TRIP} (names and order are not in the files)`,
  }),
  derive("multilevel-tree__level2", "names__roundTrip", {
    ops: [name(0, "1:2", "Sub one-two"), name(1, "3:1", "Sub three-one"), name(2, "4", "Top four")],
    roundTrip: true,
    description: `moduleLevel 2 + names of sub-modules and a top module; ${ROUND_TRIP}`,
  }),
  derive("planted-ftree__flowThreshold40", "namesHidden__roundTrip", {
    ops: [name(1, "3", "Hidden three"), name(1, "4", "Visible four")],
    roundTrip: true,
    description: `flowThreshold 0.4, a hidden and a visible module named; ${ROUND_TRIP}`,
  }),
  // --- recolouring keeps a module's name and place (E4, fix-plan finding 10). Not a layout() step order (colour after
  // order and names), so tests/test_v4_fixtures.py replays it but does not rebuild it from layout() arguments.
  derive("hlskip-tree__default", "namesOrderRecolor", {
    ops: [
      order([0, ["2", "..."]], [1, ["3", "..."]]),
      name(0, "2", "Solo two"),
      name(1, "3", "Solo three"),
      { op: "colorModule", networkIndex: 0, moduleId: "2", color: "#ff0000" },
      { op: "colorModule", networkIndex: 1, moduleId: "3", color: "#0000ff" },
    ],
    description:
      "moduleOrder moves a single-leaf module up, setModuleName names it, colorModule recolours it: name and position are kept",
  }),
  derive("multilevel-tree__colored", "order__roundTrip", {
    ops: [order([0, ["4", "3", "2", "1"]])],
    roundTrip: true,
    description: `moduleOrder without names; ${ROUND_TRIP} (custom order lost)`,
  }),
];
