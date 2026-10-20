import json
import math
import random
import shutil
import struct
import subprocess

import pytest

from alluvial._jscompat import (
    index_of_identity,
    is_array_index_key,
    js_array_join,
    js_clamp,
    js_divide,
    js_is_integer,
    js_max,
    js_min,
    js_num_str,
    js_number,
    js_number_to_string,
    js_own_keys_order,
    js_round,
    js_sum,
    js_truthy,
    stable_sort,
)


@pytest.mark.parametrize(
    "x, expected",
    [
        (80.0, "80"),
        (80, "80"),
        (-0.0, "0"),
        (0.1 + 0.2, "0.30000000000000004"),
        (1e-6, "0.000001"),
        (1e-7, "1e-7"),
        (1.5e-7, "1.5e-7"),
        (0.000001234, "0.000001234"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (1.5e21, "1.5e+21"),
        (123456789012345680000.0, "123456789012345680000"),
        (2.0**53, "9007199254740992"),
        (5e-324, "5e-324"),
        (1.7976931348623157e308, "1.7976931348623157e+308"),
        (-230.80000000000004, "-230.80000000000004"),
        (math.nan, "NaN"),
        (math.inf, "Infinity"),
        (-math.inf, "-Infinity"),
    ],
)
def test_number_to_string(x, expected):
    assert js_number_to_string(x) == expected
    assert js_num_str(x) == expected


def test_number_to_string_rejects_non_numbers():
    with pytest.raises(TypeError):
        js_number_to_string(True)
    with pytest.raises(TypeError):
        js_number_to_string("1")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_number_to_string_matches_node():
    rng = random.Random(1)
    values = [struct.unpack("<d", struct.pack("<Q", rng.getrandbits(64)))[0] for _ in range(1500)]
    values += [rng.uniform(-1000, 1000) for _ in range(500)]
    values += [10.0**e * m for e in range(-9, 23) for m in (1, 1.5, 9.999999999999998)]
    values = [v for v in values if math.isfinite(v)]
    out = subprocess.run(
        [
            "node",
            "-e",
            (
                "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>"
                "console.log(JSON.stringify(JSON.parse(s).map(String))))"
            ),
        ],
        input=json.dumps(values),
        capture_output=True,
        text=True,
        check=True,
    )
    expected = json.loads(out.stdout)
    assert [js_number_to_string(v) for v in values] == expected


@pytest.mark.parametrize(
    "s, expected",
    [
        ("", 0.0),
        ("  ", 0.0),
        (" 12 ", 12.0),
        ("\t12\n", 12.0),
        ("0x10", 16.0),
        ("0X1f", 31.0),
        ("0b11", 3.0),
        ("0o7", 7.0),
        ("-0x10", math.nan),
        ("1_0", math.nan),
        ("inf", math.nan),
        ("nan", math.nan),
        ("Infinity", math.inf),
        ("-Infinity", -math.inf),
        ("+Infinity", math.inf),
        (".5", 0.5),
        ("5.", 5.0),
        ("+5", 5.0),
        ("1e3", 1000.0),
        ("1e", math.nan),
        ("abc", math.nan),
        ("1:2", math.nan),
        ("\x1c1", math.nan),
        (" 1", 1.0),
        ("١", math.nan),
        (None, math.nan),
        (3, 3.0),
    ],
)
def test_js_number(s, expected):
    got = js_number(s)
    if math.isnan(expected):
        assert math.isnan(got)
    else:
        assert got == expected


def test_js_sum_is_left_to_right():
    assert js_sum([0.1] * 10) == 0.9999999999999999
    assert js_sum([]) == 0.0
    assert js_sum([1e100, 1.0, -1e100]) == 0.0


def test_js_divide():
    assert js_divide(1.0, 0.0) == math.inf
    assert js_divide(-1.0, 0.0) == -math.inf
    assert js_divide(1.0, -0.0) == -math.inf
    assert math.isnan(js_divide(0.0, 0.0))
    assert math.isnan(js_divide(math.nan, 0.0))
    assert js_divide(1.0, 4.0) == 0.25


def test_js_min_max():
    assert math.isnan(js_max(0.0, math.nan))
    assert math.isnan(js_max(math.nan, 0.0))
    assert math.isnan(js_min(1.0, math.nan, 2.0))
    assert math.copysign(1, js_max(-0.0, 0.0)) == 1
    assert math.copysign(1, js_max(0.0, -0.0)) == 1
    assert math.copysign(1, js_min(0.0, -0.0)) == -1
    assert js_max() == -math.inf
    assert js_min() == math.inf
    assert js_clamp(1.5, 0, 1) == 1
    assert math.isnan(js_clamp(math.nan, 0, 1))


@pytest.mark.parametrize(
    "x, expected",
    [(0.5, 1.0), (1.5, 2.0), (2.5, 3.0), (-2.5, -2.0), (-0.6, -1.0), (0.49999999999999994, 0.0), (3.0, 3.0)],
)
def test_js_round(x, expected):
    assert js_round(x) == expected


def test_js_round_non_finite():
    assert math.isnan(js_round(math.nan))
    assert js_round(math.inf) == math.inf


def test_js_is_integer_and_truthy():
    assert js_is_integer(3) and js_is_integer(3.0) and not js_is_integer(3.5)
    assert not js_is_integer(True) and not js_is_integer(math.inf) and not js_is_integer(math.nan)
    assert not js_is_integer("3")
    assert [js_truthy(v) for v in (None, False, 0, -0.0, math.nan, "", "0", 1, [], {})] == [
        False,
        False,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        True,
    ]


def test_js_array_join():
    assert js_array_join([1, 1.5, None, 2.0], ":") == "1:1.5::2"
    assert js_array_join([1, 2]) == "1,2"
    assert js_array_join([]) == ""


def test_own_keys_order():
    keys = ["b", "10", "a", "2", "01", "-1", "4294967295", "4294967294", "1.5"]
    assert js_own_keys_order(keys) == ["2", "10", "4294967294", "b", "a", "01", "-1", "4294967295", "1.5"]
    assert js_own_keys_order(["3", "1", "3", "x", "0"]) == ["0", "1", "3", "x"]
    assert is_array_index_key("0") and not is_array_index_key("") and not is_array_index_key("١")


def test_index_of_identity_and_stable_sort():
    class Eq:
        def __eq__(self, other):
            return True

    a, b = Eq(), Eq()
    assert index_of_identity([a, b], b) == 1
    assert index_of_identity([a], b) == -1
    items = [("a", 1), ("b", 2), ("c", 1), ("d", 2)]
    stable_sort(items, key=lambda t: t[1], descending=True)
    assert items == [("b", 2), ("d", 2), ("a", 1), ("c", 1)]
