import math

from conftest import V1_SCENARIOS, V2_SCENARIOS, compare, load_fixture


def test_scenario_split():
    assert len(V1_SCENARIOS) + len(V2_SCENARIOS) == 205
    # 130 v1 (128 + 3 new baselines - 2 nan-tree + abc-chain__similarity, WP6), 73 v2 (incl. 1 v2 fuzz regression);
    # NaN flows are rejected (WP4); WP5 adds dupname-tree__recolor; WP7 adds the two v2 (json)
    # multilevel-tree__visibleAndSubmodule* scenarios (E15a)
    assert len(V2_SCENARIOS) == 75
    assert all(load_fixture(s).get("features") for s in V2_SCENARIOS)
    assert not any(load_fixture(s).get("features") for s in V1_SCENARIOS)
    assert {
        "debug5-stree__expand",
        "multilevel-tree__expand",
        "multilevel-tree__expandColored",
        "multilevel-tree__expandRegroup",
    } <= set(V2_SCENARIOS)


def test_load_fixture_reads_infinity():
    fx = load_fixture("planted-ftree__flowThreshold40")
    keys = [
        s["sortKey"]
        for n in fx["networks"]
        for m in n["modules"]
        for g in m["groups"]
        for b in g["branches"]
        for s in b["streamlineNodes"]
    ]
    assert -math.inf in keys
    assert load_fixture("planted-ftree__default") is not load_fixture("planted-ftree__default")


def test_compare_basics():
    assert compare({"a": [1, 2.0, "x"]}, {"a": [1, 2, "x"]}).ok
    assert not compare({"a": 1}, {"a": 2}).ok
    assert not compare({"a": 1}, {"b": 1}).ok
    assert not compare([1, 2], [2, 1]).ok
    assert not compare([1], [1, 2]).ok
    assert not compare(True, 1).ok
    assert compare(None, None).ok and not compare(None, 0).ok
    assert compare(math.nan, math.nan).ok and compare(-math.inf, -math.inf).ok
    assert compare({"a": 1, "skip": 2}, {"a": 1}, ignore={"skip"}).ok


def test_compare_tolerance_and_bitwise_count():
    res = compare([0.1 + 0.2, 1.0], [0.3, 1.0])
    assert res.ok and res.non_bitwise == 1 and res.floats_compared == 2
    assert not compare(1.0, 1.0 + 1e-8).ok


def test_compare_svg_paths():
    a = "M80,600C160,600,160,291.84853872481835,240,291.84853872481835L240,145Z"
    b = "M80,600C160,600,160,291.8485387248184,240,291.84853872481835L240,145Z"
    res = compare(a, b)
    assert res.ok and res.non_bitwise == 1
    assert not compare(a, a.replace("L", "C")).ok
    assert not compare(a, a.replace("145", "146")).ok
    assert not compare("abc", "abd").ok
