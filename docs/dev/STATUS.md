# alluvial 0.6.0: status for the owner (2026-10-21)

## What exists

A Python package that draws alluvial diagrams of Infomap partitions with matplotlib. Its layout engine is a
line-by-line port of the web app's TS engine (`packages/alluvial-diagram` in the web repo), so module order, sizes,
margins, streamlines and colours are the web app's, bit for bit. 0.5 is the fix round done together with the TS
engine (worktree branch `py-parity-fixes`, uncommitted; `docs/dev/fix-plan.md`): both engines got the same fixes,
and the fixtures were regenerated from the fixed TS. 0.6 ports c3 2 (TS #47: tones, offsets, the C3 Oklch scheme,
colouring by module hierarchy) and the saved tone and offset (TS #57). **Port base: TS `master` `60fa1bf` (#58)**,
recorded as `ts_repo_head` in `tests/fixtures/provenance.txt`; #59 after it changes only the licence.

- **Input:** `.tree`/`.ftree`/`.stree`/`.clu`, Infomap JSON, `infomap.Infomap` objects and their `Result`, a `.zip`,
  a directory or a list of network files, and saved diagrams ("alluvial network files", restored as the web app
  opens them). The 2019 saved-diagram format is no longer read.
- **Layout:** `alluvial.layout(...)` -> `AlluvialGeometry` (frozen dataclasses): sub-module levels (`module_level`,
  `expand`), colouring (`colors`, `scheme`, `highlight` groups), multilayer `split_layers`, `show_bipartite_nodes`,
  module names (`module_names`) and a custom module order (`module_order`, one layout), all layout options.
- **Output:** `alluvial.plot`/`draw` (matplotlib, labels fitted at draw time, legends, hierarchy outlines) and
  `alluvial.save_diagram` (the web app's "Download diagram" files, formatVersion 1, byte-identical to TS's
  `serializeDiagram` apart from `generator`; a zip, loose files or one `.json`).
- **Docs:** `README.md`, `docs/tutorial.ipynb` (story), `docs/capabilities.ipynb` (every feature, with asserts; both
  executed and under test), `examples/*.py`, `CHANGELOG.md`; developer notes in `docs/dev/design.md` and
  `docs/dev/port-notes/`.

## How it is verified

| Check | Result |
|---|---|
| TS reference fixtures (`tests/fixtures`, made by the real TS store at `60fa1bf`) | 297 (205 v1/v2, 77 v3, 15 v4), all replayed bit for bit except one strict xfail (c3-colors, below); `generate.mjs --check` byte-identical |
| Saved files (`save_diagram`) | byte-identical to TS `serializeDiagram` for every round-trip fixture; TS opens Python's files and Python opens TS's with the same state, bit for bit |
| Differential fuzzer (random inputs and op sequences, TS vs Python, with round trips and Python-save -> TS-open) | 0.6: v1, v2, v4 and c3 (saved scheme/tone/offset edited before the open) seeds 0-4999 clean, c3 also 5000-9999 |
| Test suite | 0.6: 2187 passed, 26 skipped, 3 xfailed (c3-colors, strict) on 3.14 with `ALLUVIAL_TS_ROOT` at `60fa1bf`; 2186 passed, 27 skipped without it (the TS lockfile pin check needs the env var). 0.5: the wheel with the sdist tests passed on 3.11-3.14 |
| Docs | README snippets run fresh; both notebooks re-executed in py314 without errors or warnings; `ruff` clean |

**c3-colors 2.0.1** (the Python port of `@mapequation/c3`) colours a module with many sub-modules (about 40 or
more) differently with `colors="hierarchy"`: a few sibling colours swap (last-bit `hypot`/libm vs V8 differences
decide near-ties in c3's `placeChildren`). Not patched in the port; strict xfail tests wait for a c3-colors release
(owner decision).

Other known divergences are on hand-made input only: JSON `layerId: null` reads as missing, an out-of-palette colour index
draws black in TS and cycles (with a warning) in Python, and on x86-64 V8 (no FMA) about 1 `log2` in 300k differs in
the last bit.

## How to run and regenerate

```sh
.venv/bin/pytest -q                                              # full suite (about 2 min)
node tools/ts-fixtures/generate.mjs --check                      # fixtures still match the TS sources
node tools/ts-fixtures/generate.mjs                              # regenerate after a TS change (then review the diff)
ALLUVIAL_FUZZ_START=0 ALLUVIAL_FUZZ_SEEDS=1000 .venv/bin/pytest -q tests/test_fuzz_parity.py   # fuzz v1/v2/v4
uv build                                                         # wheel (package only) + sdist (with tests)
```

The fixture tools need node and the web repo checkout (`ALLUVIAL_TS_ROOT`, default `../web/alluvial`);
`tools/ts-fixtures/README.md` has the details, including the opt-in 40 MB `large` fixtures.
`tests/fixtures/provenance.txt` pins the TS commit (`ts_repo_head`) and source hash.

## How to sync with TS `master`

The web repo's `CLAUDE.md` ("Python port") asks TS PRs that change the engine to run the parity check and to leave
this repo to a session here. To catch up:

```sh
TS=../web/alluvial                                    # or a clean checkout of the commit to port
git -C $TS log <ts_repo_head>..master -- packages/alluvial-diagram/src   # the engine commits to port
ALLUVIAL_TS_ROOT=$TS node tools/ts-fixtures/generate.mjs --check          # exit 0: the port still matches
# port the commits, then:
ALLUVIAL_TS_ROOT=$TS node tools/ts-fixtures/generate.mjs [--make-data]    # regenerate; review the diff
ALLUVIAL_TS_ROOT=$TS .venv/bin/pytest -q                                # then the fuzzer (tools/ts-fixtures/README.md)
```

Keep `c3-colors` at the TS lockfile's `@mapequation/c3` version (`tests/test_c3_schemes.py` checks it).

## Open owner decisions (most important first; each default is what is implemented now)

1. **c3-colors release.** Fix the wide-module `hierarchy()` divergence in c3-colors (V8-compatible `hypot` and
   trig), then pin the new version on both sides and drop the xfails. *Default: keep 2.0.1 and the xfails.*
2. **Release process (settled).** Published to PyPI as `alluvial` from GitHub releases: a release tagged `vX.Y.Z`
   runs `.github/workflows/publish-python.yml` (tests, `uv build`, trusted publishing). Authors: mapequation.
3. **TS release.** The worktree removes `createFilesFromDiagramObject` (breaking) and adds `serializeDiagram`,
   `openNetworks`, `setModuleOrder` and `setModuleLevel`; its version is left at 1.15.0. *Default: choose major vs.
   minor at release (fix-plan Q2).* Python 0.5 files open in the new web app only once it is deployed.
4. **Default colouring.** `colors="similarity"` (the web app starts gray), with no "clean" mode (e.g. an unpaired
   sub-module stays gray). *Default: keep.*
5. **Duplicate identifiers** warn; a `highlight` identifier under two labels raises. *Default: keep.*
6. **`module_order` semantics.** Unlisted modules go above the listed ones unless `...` places them.
   *Default: keep.*

Settled in 0.5 (owner answers, fix-plan.md): the parity quirks of 0.4 (string-prefix `isAncestor`, the stree
trailing-colon level, `;` paths) are fixed in both engines; the 2019 format is dropped and `save_diagram` writes the
new format (zip by default, loose files optional); `module_order` and `module_level` are one layout each.

## Deferred ideas

- Public API for regroup, `resetLayout`, `moveNetwork`, `mergeMultilayerFiles` (regroup, moves and reset are already
  ported and fixture-covered in the engine).
- Automatic crossing minimisation, proposed as a joint TS + Python feature (the port adds no heuristics the web app
  cannot reproduce).
- The LOW and KEEP items of `fix-plan.md` §4 (e.g. S2 hidden modules taking similarity colours, E16 `Tree` O(n²)).
- Labels of nodes with exactly equal flow can list in another order after a recolour or a reload (both engines;
  see `CHANGELOG.md` WP12).
