import json
from pathlib import Path

import pytest

from alluvial._palette import (
    DEFAULT_HIGHLIGHT_COLOR,
    DEFAULT_SCHEME,
    DEFAULT_TONE,
    SCHEMES,
    brighter,
    make_fill,
    parse_color,
    to_rgb01,
)

DATA = Path(__file__).resolve().parents[1] / "docs" / "dev" / "port-notes" / "data"

TS_SCHEMES = Path(__file__).resolve().parent / "data" / "ts_color_schemes.json"


def test_defaults_come_from_the_ts_store():
    """The default scheme and tone have one source: the TS store, through the TS-derived data file."""
    data = json.loads(TS_SCHEMES.read_text())
    assert (data["default"], data["defaultTone"]) == (DEFAULT_SCHEME, DEFAULT_TONE)
    assert DEFAULT_SCHEME in SCHEMES


def test_layout_docstring_names_the_defaults():
    """The layout docstring names the default scheme and tone; it must follow the single source."""
    import alluvial

    doc = alluvial.layout.__doc__
    assert f'default ``"{DEFAULT_SCHEME}"``' in doc
    assert f'Default ``"{DEFAULT_TONE}"``' in doc


def test_c3_sinebow():
    C3_SINEBOW = SCHEMES["C3 Sinebow"]
    # c3 2 (web app 1.16): "C3 Sinebow" in the default tone, hex strings as TS writes them
    assert len(C3_SINEBOW) == 512
    assert list(C3_SINEBOW) == json.loads(TS_SCHEMES.read_text())["schemes"]["C3 Sinebow"]
    assert all(c.startswith("#") and len(c) == 7 for c in C3_SINEBOW)
    assert ["#{:02x}{:02x}{:02x}".format(*parse_color(c)) for c in C3_SINEBOW[:4]] == list(C3_SINEBOW[:4])


def test_brighter_reference():
    pairs = json.loads((DATA / "hsl-brighter-0.8-ref.json").read_text())
    assert len(pairs) == 549
    mismatches = [(c, ref, brighter(c, 0.8)) for c, ref in pairs if brighter(c, 0.8) != ref]
    assert mismatches == []


def test_brighter_values():
    assert brighter(DEFAULT_HIGHLIGHT_COLOR) == "rgb(231, 231, 223)"
    assert brighter("#000") == "rgb(0, 0, 0)"
    assert brighter("rgb(198, 59, 59)") == "rgb(217, 125, 125)"
    assert brighter(None) == "rgb(0, 0, 0)"


def test_parse_color():
    assert parse_color("#fff") == (255, 255, 255)
    assert parse_color(" rgb( 1 ,2,3 ) ") == (1, 2, 3)
    assert to_rgb01("#ff0000") == (1.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        parse_color("red")


def test_make_fill():
    fill = make_fill(DEFAULT_HIGHLIGHT_COLOR, ["#ff0000", "#00ff00"])
    assert fill(-1, False) == DEFAULT_HIGHLIGHT_COLOR
    assert fill(1, False) == "#00ff00"
    assert fill(2, False) is None
    assert fill(-2, False) is None
    assert fill(-1, True) == "rgb(231, 231, 223)"
    assert fill(5, True) == "rgb(0, 0, 0)"
