"""c3 2 colours (web app 1.16, #47) and their save (#57) against the TS dumps in ``tests/data/ts_c3_schemes.json``
(``generate.mjs --make-data``): the d3 interpolators c3 takes as hue sources, every C3 scheme in every tone at several
offsets, c3's ``hierarchy()`` with the options of every scheme, and the Python API around them (``tone``,
``offset``, ``colors="hierarchy"``, saving and restoring the tone and offset).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tomllib
import warnings
from importlib.metadata import version
from pathlib import Path
from typing import Any

import c3
import pytest
from conftest import TESTS_DIR

import alluvial
from alluvial._d3_interpolators import interpolator, scheme_interpolators
from alluvial._palette import (
    DEFAULT_SCHEME,
    DEFAULT_TONE,
    SCHEMES,
    TONES,
    default_scheme_offset,
    hierarchy_options,
    scheme_colors,
    scheme_is_hue_source,
)
from alluvial.engine import DiagramStore
from alluvial.layout import LayoutOptions, _build_store, _layout_arguments

ROOT = TESTS_DIR.parent
REF = json.loads((TESTS_DIR / "data" / "ts_c3_schemes.json").read_text(encoding="utf-8"))
MULTILEVEL = [TESTS_DIR / "data" / f"multilevel_t{t}.tree" for t in range(3)]


def _sha256(colors: Any) -> str:
    return hashlib.sha256(json.dumps(list(colors), separators=(",", ":")).encode()).hexdigest()


# --- the c3 version ----------------------------------------------------------------------------------------------


def test_c3_colors_is_pinned_to_the_installed_version() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pins = [d for d in pyproject["project"]["dependencies"] if d.startswith("c3-colors")]
    assert pins == [f"c3-colors=={version('c3-colors')}"]


@pytest.mark.skipif(not os.environ.get("ALLUVIAL_TS_ROOT"), reason="set ALLUVIAL_TS_ROOT to the TS checkout")
def test_c3_colors_matches_the_ts_lockfile() -> None:
    # the Python port of c3 must be the version the web app's library resolves (pnpm-lock.yaml)
    lock = (Path(os.environ["ALLUVIAL_TS_ROOT"]) / "pnpm-lock.yaml").read_text(encoding="utf-8")
    versions = set(re.findall(r"^\s+'@mapequation/c3@([^']+)':", lock, flags=re.M))
    assert versions == {version("c3-colors")}


# --- schemes -----------------------------------------------------------------------------------------------------


def test_tones_hue_sources_and_default_offsets() -> None:
    assert list(TONES) == REF["tones"]
    assert REF["defaultTone"] == DEFAULT_TONE
    assert [name for name in SCHEMES if scheme_is_hue_source(name)] == REF["hueSources"]
    assert {name: default_scheme_offset(name) for name in SCHEMES} == REF["defaultOffsets"]


def test_d3_interpolators_match_ts() -> None:
    ts = REF["interpolatorSamples"]["t"]
    samples = REF["interpolatorSamples"]["samples"]
    assert set(samples) == set(scheme_interpolators().values())
    for name, expected in samples.items():
        f = interpolator(name)
        assert [f(t) for t in ts] == expected, name


def test_c3_schemes_match_ts() -> None:
    # every C3 scheme in every tone at REF["c3Offsets"], byte for byte (sha256 of JSON.stringify)
    assert len(REF["c3Schemes"]) == 5 * len(TONES) * len(REF["c3Offsets"])
    for case in REF["c3Schemes"]:
        colors = scheme_colors(case["scheme"], case["tone"], case["offset"])
        label = (case["scheme"], case["tone"], case["offset"])
        assert list(colors[:8]) == case["first"], label
        assert len(colors) == case["length"], label
        assert _sha256(colors) == case["sha256"], label


def test_c3_default_tone_equals_the_dumped_schemes() -> None:
    # the default tone and offset return SCHEMES; c3-colors computes the same colours
    for name in ("C3 Oklch", "C3 Turbo", "C3 Rainbow", "C3 Sinebow", "C3 Viridis"):
        assert scheme_colors(name) is SCHEMES[name]
        assert scheme_colors(name, DEFAULT_TONE, default_scheme_offset(name)) == SCHEMES[name]


def test_hierarchy_matches_ts() -> None:
    modules = REF["hierarchyModules"]
    for case in REF["hierarchy"]:
        color = c3.hierarchy(modules, **hierarchy_options(case["scheme"], case["tone"], case["offset"]))
        got = [[":".join(map(str, m["path"])), m["color"]] for m in color.modules]
        assert got == case["colors"], (case["scheme"], case["tone"], case["offset"])


@pytest.mark.xfail(
    strict=True,
    reason="c3-colors 2.0.1 hierarchy() colours a module with 119 sub-modules unlike @mapequation/c3 2.0.1 "
    "(sibling colours swap: last-bit math.hypot/libm vs V8 differences decide near-ties in placeChildren); "
    "needs a c3-colors release",
)
@pytest.mark.parametrize("scheme", ["C3 Sinebow", "C3 Oklch"])
def test_hierarchy_wide_module_matches_ts(scheme: str) -> None:
    (case,) = [c for c in REF["hierarchyWide"] if c["scheme"] == scheme]
    color = c3.hierarchy(
        REF["hierarchyWideModules"], **hierarchy_options(scheme, case["tone"], case["offset"])
    )
    got = [[":".join(map(str, m["path"])), m["color"]] for m in color.modules]
    assert got == case["colors"]


def test_scheme_colors_validation() -> None:
    with pytest.raises(ValueError, match="unknown c3 tone"):
        scheme_colors("C3 Oklch", "neon")
    with pytest.raises(TypeError, match="offset"):
        scheme_colors("C3 Oklch", "strong", "90")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite"):
        scheme_colors("C3 Oklch", "strong", math.inf)
    with pytest.raises(ValueError, match="unknown color scheme"):
        scheme_colors("C3 Nope")
    # the other schemes ignore the tone and offset
    assert scheme_colors("Paired", "pastel", 90) is SCHEMES["Paired"]


# --- store -------------------------------------------------------------------------------------------------------


def test_store_setters_follow_ts() -> None:
    store = DiagramStore(LayoutOptions(), scheme="C3 Oklch", tone="pastel", offset=10)
    assert store.selected_scheme == list(scheme_colors("C3 Oklch", "pastel", 10))
    store.set_selected_tone("dark")
    assert store.selected_scheme == list(scheme_colors("C3 Oklch", "dark", 10))
    store.set_selected_offset(-20.5)
    assert store.selected_scheme == list(scheme_colors("C3 Oklch", "dark", -20.5))
    # another scheme resets the offset (c3's default differs between hue sources) and keeps the tone
    store.set_selected_scheme("C3 Turbo")
    assert (store.selected_tone, store.selected_offset) == ("dark", None)
    assert store.selected_scheme == list(scheme_colors("C3 Turbo", "dark"))
    # a list scheme keeps its colours whatever the tone
    store.set_selected_scheme(["#111111", "#222222"])
    store.set_selected_tone("vivid")
    assert store.selected_scheme == ["#111111", "#222222"]
    with pytest.raises(ValueError, match="unknown c3 tone"):
        store.set_selected_tone("neon")


# --- layout API --------------------------------------------------------------------------------------------------


def _store(networks: Any = MULTILEVEL, **kwargs: Any) -> Any:
    store, _ = _build_store(networks, **_layout_arguments(dict(kwargs)))
    return store


def test_layout_tone_offset_and_hierarchy() -> None:
    geom = alluvial.layout(MULTILEVEL, scheme="C3 Oklch", tone="pastel", offset=120, colors="module_id")
    assert set(geom.palette) <= set(scheme_colors("C3 Oklch", "pastel", 120))
    hierarchy = alluvial.layout(MULTILEVEL, colors="hierarchy", module_level=2)
    top = alluvial.layout(MULTILEVEL, colors="hierarchy")
    assert len(hierarchy.palette) > len(top.palette) > 0
    # a list scheme gives c3 seeds
    seeded = alluvial.layout(
        MULTILEVEL, colors="hierarchy", scheme=["#ff0000", "#00ff00", "#0000ff", "#888888"]
    )
    assert seeded.palette[:4] == ("#ff0000", "#00ff00", "#0000ff", "#888888")


def test_layout_tone_offset_validation() -> None:
    with pytest.raises(ValueError, match="unknown c3 tone"):
        alluvial.layout(MULTILEVEL, tone="neon")
    with pytest.raises(TypeError, match="offset"):
        alluvial.layout(MULTILEVEL, offset="90")
    with pytest.raises(TypeError, match="offset"):
        alluvial.layout(MULTILEVEL, offset=True)
    with pytest.raises(ValueError, match="finite"):
        alluvial.layout(MULTILEVEL, offset=math.nan)
    with pytest.raises(ValueError, match="colors must be one of"):
        alluvial.layout(MULTILEVEL, colors="hierarchies")


def _diagram_blocks(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(f.read_text(encoding="utf-8"))["alluvial"]["diagram"] for f in sorted(path.glob("*.json"))
    ]


def test_save_writes_tone_and_offset(tmp_path: Path) -> None:
    out = alluvial.save_diagram(
        MULTILEVEL, tmp_path / "a", loose=True, scheme="C3 Oklch", tone="soft", offset=12.5
    )
    blocks = _diagram_blocks(out)
    assert [list(b) for b in blocks] == [
        ["saveId", "position", "numNetworks", "colorScheme", "colorTone", "colorOffset", "options"]
    ] * 3
    assert {(b["colorScheme"], b["colorTone"], b["colorOffset"]) for b in blocks} == {
        ("C3 Oklch", "soft", 12.5)
    }
    default = _diagram_blocks(alluvial.save_diagram(MULTILEVEL, tmp_path / "b", loose=True))
    assert {(b["colorTone"], b["colorOffset"]) for b in default} == {(DEFAULT_TONE, None)}


def test_read_restores_tone_and_offset(tmp_path: Path) -> None:
    out = alluvial.save_diagram(
        MULTILEVEL, tmp_path / "d.zip", scheme="C3 Oklch", tone="soft", offset=12.5, colors="hierarchy"
    )
    store = _store([out])
    assert (store.selected_scheme_name, store.selected_tone, store.selected_offset) == (
        "C3 Oklch",
        "soft",
        12.5,
    )
    # explicit keywords win; another scheme drops the stored offset, the stored tone stays
    store = _store([out], tone="dark", offset=3)
    assert (store.selected_tone, store.selected_offset) == ("dark", 3)
    store = _store([out], scheme="C3 Turbo")
    assert (store.selected_scheme_name, store.selected_tone, store.selected_offset) == (
        "C3 Turbo",
        "soft",
        None,
    )
    store = _store([out], restore_state=False)
    assert (store.selected_scheme_name, store.selected_tone, store.selected_offset) == (
        DEFAULT_SCHEME,
        DEFAULT_TONE,
        None,
    )
    # the saved colours come back as they were
    assert (
        alluvial.layout([out]).palette
        == alluvial.layout(
            MULTILEVEL, scheme="C3 Oklch", tone="soft", offset=12.5, colors="hierarchy"
        ).palette
    )


def test_invalid_saved_tone_and_offset_warn(tmp_path: Path) -> None:
    folder = alluvial.save_diagram(
        MULTILEVEL, tmp_path / "d", loose=True, scheme="C3 Oklch", tone="soft", offset=7
    )
    for f in folder.glob("*.json"):
        value = json.loads(f.read_text(encoding="utf-8"))
        value["alluvial"]["diagram"]["colorTone"] = "neon"
        value["alluvial"]["diagram"]["colorOffset"] = "90"
        f.write_text(json.dumps(value), encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        store = _store([folder])
    messages = [str(w.message) for w in caught]
    assert "saved diagram: ignoring the saved color tone (unknown tone)" in messages
    assert "saved diagram: ignoring the saved color offset (invalid value)" in messages
    assert (store.selected_scheme_name, store.selected_tone, store.selected_offset) == (
        "C3 Oklch",
        DEFAULT_TONE,
        None,
    )
