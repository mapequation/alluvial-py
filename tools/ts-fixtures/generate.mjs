#!/usr/bin/env node
// Regenerate the TS layout fixtures for alluvial-py.
//
//   node tools/ts-fixtures/generate.mjs            # write tests/fixtures/*.json
//   node tools/ts-fixtures/generate.mjs --check    # regenerate into a temp dir
//                                                  # and byte-compare to tests/fixtures
//   node tools/ts-fixtures/generate.mjs --only planted   # scenarios whose name contains "planted"
//   node tools/ts-fixtures/generate.mjs --out DIR  # write somewhere else
//   node tools/ts-fixtures/generate.mjs --large --out DIR  # also the scenarios marked `large` (too big to
//                                                  # commit, e.g. science-stree__level2); requires --out
//   node tools/ts-fixtures/generate.mjs --make-data # (re)write the TS-derived data: the reference dumps in
//                                                  # tests/data and the scheme data in src/alluvial/data
//                                                  # (--check verifies them)
//   node tools/ts-fixtures/generate.mjs --fuzz DIR # run the differential-fuzz cases in DIR
//                                                  # (DIR/<case>/case.json from fuzz/gen.py) and
//                                                  # write DIR/<case>/ts.json; fixtures untouched
//   node tools/ts-fixtures/generate.mjs --open DIR # open the saved diagrams DIR/<case>/saved/*.json
//                                                  # (or the zip DIR/<case>/saved.zip as one dropped file)
//                                                  # (written by alluvial-py) like the web app and
//                                                  # write DIR/<case>/ts-open.json (Python-save -> TS-open)
//
// The TS sources are loaded straight from the alluvial monorepo
// (packages/alluvial-diagram/src, NOT the possibly stale dist/) through Vite's
// SSR module loader, using the monorepo's own node_modules. Nothing is
// written to the TS repo. Override its location with ALLUVIAL_TS_ROOT.

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import {
  existsSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");
const TS_ROOT = resolve(
  process.env.ALLUVIAL_TS_ROOT ?? join(REPO, "..", "web", "alluvial")
);
const TS_PKG = join(TS_ROOT, "packages", "alluvial-diagram");
const TS_SRC = join(TS_PKG, "src");

function parseArgs(argv) {
  const args = { check: false, only: null, out: null, fuzz: null, open: null, large: false, makeData: false };
  for (let i = 0; i < argv.length; ++i) {
    const a = argv[i];
    if (a === "--check") args.check = true;
    else if (a === "--only") args.only = argv[++i];
    else if (a === "--out") args.out = resolve(argv[++i]);
    else if (a === "--fuzz") args.fuzz = resolve(argv[++i]);
    else if (a === "--open") args.open = resolve(argv[++i]);
    else if (a === "--large") args.large = true;
    else if (a === "--make-data") args.makeData = true;
    else throw new Error(`Unknown argument ${a}`);
  }
  return args;
}

async function loadVite() {
  if (!existsSync(join(TS_SRC, "alluvial", "Diagram.ts"))) {
    throw new Error(`TS sources not found under ${TS_SRC} (set ALLUVIAL_TS_ROOT)`);
  }
  // vite, mobx and @mapequation/infomap-parser are the engine package's dependencies, not the TS root's; pnpm only
  // links a package's own dependencies into its node_modules
  const require = createRequire(join(TS_PKG, "package.json"));
  const vitePath = require.resolve("vite");
  return import(pathToFileURL(vitePath).href);
}

function listSources(dir, prefix = "") {
  const out = [];
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name);
    const rel = prefix ? `${prefix}/${name}` : name;
    if (statSync(full).isDirectory()) out.push(...listSources(full, rel));
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(rel);
  }
  return out;
}

// Provenance of the TS engine the fixtures were generated from. Read-only
// git calls (GIT_OPTIONAL_LOCKS=0 keeps `git status` from touching the index).
function provenance(fixtureCount, v3Count, v4Count) {
  const git = (...args) => {
    try {
      return execFileSync("git", ["-C", TS_ROOT, ...args], {
        encoding: "utf8",
        env: { ...process.env, GIT_OPTIONAL_LOCKS: "0" },
        stdio: ["ignore", "pipe", "ignore"],
      }).trim();
    } catch {
      return "unavailable";
    }
  };
  const hash = createHash("sha256");
  for (const rel of listSources(TS_SRC)) {
    hash.update(rel + "\0");
    hash.update(readFileSync(join(TS_SRC, rel)));
    hash.update("\0");
  }
  // vite, mobx and @mapequation/infomap-parser are the engine package's dependencies, not the TS root's; pnpm only
  // links a package's own dependencies into its node_modules
  const require = createRequire(join(TS_PKG, "package.json"));
  const version = (pkg) => {
    try {
      return JSON.parse(readFileSync(require.resolve(`${pkg}/package.json`), "utf8")).version;
    } catch {
      return "unknown";
    }
  };
  const dirty = git("status", "--porcelain", "--", "packages/alluvial-diagram/src");
  return [
    "# Provenance of tests/fixtures (written by tools/ts-fixtures/generate.mjs)",
    `ts_repo_head: ${git("rev-parse", "HEAD")}`,
    `ts_src_dirty: ${dirty === "unavailable" ? "unknown" : dirty ? "yes" : "no"}`,
    `ts_src_sha256: ${hash.digest("hex")}  (packages/alluvial-diagram/src/**/*.ts(x), excluding tests)`,
    `node: ${process.version}`,
    `vite: ${version("vite")}`,
    `mobx: ${version("mobx")}`,
    `@mapequation/infomap-parser: ${version("@mapequation/infomap-parser")}`,
    `fixtures: ${fixtureCount}`,
    `fixtures_v3: ${v3Count}`,
    `fixtures_v4: ${v4Count}`,
    "",
  ].join("\n");
}

function compareDirs(expectedDir, actualDir, prefix = "") {
  const list = (dir) => (existsSync(dir) ? readdirSync(dir).filter((f) => f.endsWith(".json")).sort() : []);
  const exp = list(expectedDir);
  const act = list(actualDir);
  const problems = [];
  for (const name of new Set([...exp, ...act])) {
    const f = prefix + name;
    if (!exp.includes(name)) problems.push(`new (not committed): ${f}`);
    else if (!act.includes(name)) problems.push(`missing (not regenerated): ${f}`);
    else if (!readFileSync(join(expectedDir, name)).equals(readFileSync(join(actualDir, name))))
      problems.push(`differs: ${f}`);
  }
  return problems;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.fuzz) return fuzz(args.fuzz);
  if (args.open) return openSaved(args.open);
  if (args.large && (args.check || !args.out)) throw new Error("--large needs --out DIR (large fixtures are not committed)");
  const fixturesDir = join(REPO, "tests", "fixtures");
  const outDir = args.check
    ? mkdtempSync(join(tmpdir(), "alluvial-ts-fixtures-"))
    : args.out ?? fixturesDir;
  // v3 scenarios (tools/ts-fixtures/README.md "v3 scenarios") go to a subdirectory, so the v1/v2 test
  // parametrization (tests/fixtures/*.json, not recursive) does not pick them up.
  const v3Dir = join(outDir, "v3");
  // v4 scenarios (module names and order) likewise go to tests/fixtures/v4
  const v4Dir = join(outDir, "v4");
  const dataProblems = [];

  const server = await createServer();

  try {
    const harness = await server.ssrLoadModule(join(HERE, "harness.ts"));
    // v3 TS-derived data files in tests/data (written with --make-data, verified by --check)
    if (args.makeData || (args.check && !args.only)) {
      // The TS package's own d3 and c3 (the interpolators and hierarchy() the data samples)
      const tsRequire = createRequire(join(TS_SRC, "schemes", "index.ts"));
      const d3 = await import(pathToFileURL(tsRequire.resolve("d3")).href);
      const c3 = await import(pathToFileURL(tsRequire.resolve("@mapequation/c3")).href);
      const d3Version = JSON.parse(
        readFileSync(join(dirname(tsRequire.resolve("d3")), "..", "package.json"), "utf8")
      ).version;
      const files = await harness.makeData({ d3, c3, d3Version });
      for (const { rel, text } of files) {
        const path = join(REPO, rel);
        if (args.makeData) {
          writeFileSync(path, text);
          console.log(`wrote ${rel}`);
        } else if (!existsSync(path)) dataProblems.push(`missing data file: ${rel}`);
        else if (readFileSync(path, "utf8") !== text) dataProblems.push(`differs: ${rel}`);
      }
    }
    const written = await harness.main({
      repoRoot: REPO,
      tsRoot: TS_ROOT,
      outDir,
      v3Dir,
      v4Dir,
      only: args.only,
      large: args.large,
    });
    const v3Count = written.filter((p) => p.startsWith(v3Dir + "/")).length;
    const v4Count = written.filter((p) => p.startsWith(v4Dir + "/")).length;
    console.log(`wrote ${written.length} fixtures to ${outDir} (${v3Count} v3 in ${v3Dir}, ${v4Count} v4 in ${v4Dir})`);
    const prov = provenance(written.length - v3Count - v4Count, v3Count, v4Count);
    if (args.check) {
      const committed = join(fixturesDir, "provenance.txt");
      const old = existsSync(committed) ? readFileSync(committed, "utf8") : "";
      if (!args.only && old !== prov) {
        console.log("note: provenance differs from tests/fixtures/provenance.txt:\n" + prov);
      }
    } else if (!args.only) {
      writeFileSync(join(outDir, "provenance.txt"), prov);
      // Drop fixtures of scenarios that no longer exist
      const keep = new Set(written);
      for (const dir of [outDir, v3Dir, v4Dir]) {
        if (!existsSync(dir)) continue;
        for (const f of readdirSync(dir)) {
          if (f.endsWith(".json") && !keep.has(join(dir, f))) {
            rmSync(join(dir, f));
            console.log(`removed stale fixture ${join(dir, f)}`);
          }
        }
      }
    }
  } finally {
    await server.close();
  }

  if (args.check) {
    const problems = [
      ...compareDirs(fixturesDir, outDir),
      ...compareDirs(join(fixturesDir, "v3"), v3Dir, "v3/"),
      ...compareDirs(join(fixturesDir, "v4"), v4Dir, "v4/"),
    ];
    if (args.only) {
      // Only compare what was regenerated
      const kept = problems.filter((p) => !p.startsWith("missing"));
      problems.length = 0;
      problems.push(...kept);
    }
    problems.push(...dataProblems);
    if (problems.length) {
      console.error(`fixtures differ from ${fixturesDir}:\n  ${problems.join("\n  ")}`);
      console.error(`(regenerated copies kept in ${outDir})`);
      process.exit(1);
    }
    rmSync(outDir, { recursive: true, force: true });
    console.log("check OK: regenerated fixtures are byte-identical");
  }
}

async function createServer() {
  const vite = await loadVite();
  return vite.createServer({
    configFile: false,
    root: HERE,
    // Keep Vite's cache out of both repos (dep optimization is off anyway).
    cacheDir: join(tmpdir(), "alluvial-ts-fixtures-vite-cache"),
    logLevel: "warn",
    appType: "custom",
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    optimizeDeps: { noDiscovery: true, include: [] },
    resolve: {
      alias: [
        { find: "@alluvial-src", replacement: TS_SRC },
      ],
    },
  });
}

async function fuzz(caseDir) {
  const server = await createServer();
  try {
    const harness = await server.ssrLoadModule(join(HERE, "harness.ts"));
    const { cases, errors } = await harness.fuzzMain({ caseDir, tsRoot: TS_ROOT });
    console.log(`ran ${cases} fuzz cases in ${caseDir} (${errors} raised in TS)`);
  } finally {
    await server.close();
  }
}

async function openSaved(caseDir) {
  const server = await createServer();
  try {
    const harness = await server.ssrLoadModule(join(HERE, "harness.ts"));
    const { cases, errors } = await harness.openMain({ caseDir, tsRoot: TS_ROOT });
    console.log(`opened ${cases} saved diagrams in ${caseDir} (${errors} raised in TS)`);
  } finally {
    await server.close();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
