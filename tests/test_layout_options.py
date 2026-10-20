import shutil
from pathlib import Path

import pytest
from conftest import ALL_SCENARIOS, DATA_DIR, load_fixture

from alluvial.io import read
from alluvial.layout import LayoutOptions, layout

TS_DEFAULTS = {
    "height": 600,
    "moduleWidth": 80,
    "streamlineFraction": 2,
    "streamlineThreshold": 1,
    "flowThreshold": 0.005,
    "marginExponent": 4,
    "zeroMargins": False,
    "verticalAlign": "bottom",
    "moduleSize": "flow",
    "sortModulesBy": "flow",
}


def test_defaults_match_store():
    opts = LayoutOptions()
    assert opts.to_ts() == TS_DEFAULTS
    assert all(isinstance(getattr(opts, n), float) for n in ("height", "module_width", "margin_exponent"))


def test_from_ts_roundtrips_every_fixture():
    seen = set()
    for name in ALL_SCENARIOS:
        ts = load_fixture(name)["inputs"]["options"]
        opts = LayoutOptions.from_ts(ts)
        assert opts.to_ts() == ts
        seen.add(opts.sort_modules_by)
    assert seen == {"flow", "nodes", "node_id", "highlight_index"}


def test_coercion_and_mapping():
    opts = LayoutOptions(height=200, margin_exponent=4.5, sort_modules_by="node_id")
    assert opts.height == 200.0 and isinstance(opts.height, float)
    assert opts.to_ts()["sortModulesBy"] == "nodeId"
    assert "module_width" in LayoutOptions.field_names()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"height": 0},
        {"height": -1},
        {"height": float("inf")},
        {"module_width": 0},
        {"streamline_fraction": -1},
        {"streamline_threshold": -0.5},
        {"flow_threshold": 1},
        {"flow_threshold": -0.1},
        {"vertical_align": "top"},
        {"module_size": "size"},
        {"sort_modules_by": "nodeId"},
        {"margin_exponent": float("nan")},
    ],
)
def test_validation(kwargs):
    with pytest.raises(ValueError):
        LayoutOptions(**kwargs)


@pytest.mark.parametrize("kwargs", [{"flow_threshold": "0.1"}, {"height": True}, {"zero_margins": 1}])
def test_type_validation(kwargs):
    with pytest.raises(TypeError):
        LayoutOptions(**kwargs)


def test_from_ts_rejects_unknown():
    with pytest.raises(ValueError):
        LayoutOptions.from_ts({"height": 600, "colour": "red"})
    with pytest.raises(ValueError):
        LayoutOptions.from_ts({"sortModulesBy": "node_id"})


def test_layout_validates_before_stub():
    with pytest.raises(ValueError):
        layout([], flow_threshold=2)
    with pytest.raises(TypeError):
        layout([], not_an_option=1)


def test_numpy_scalars_are_numbers():
    np = pytest.importorskip("numpy")
    opts = LayoutOptions(height=np.int64(300), module_width=np.float32(40), margin_exponent=np.int32(3))
    assert (opts.height, opts.module_width, opts.margin_exponent) == (300.0, 40.0, 3.0)
    assert all(type(v) is float for v in (opts.height, opts.module_width, opts.margin_exponent))
    with pytest.raises(TypeError):
        LayoutOptions(height=np.bool_(True))


@pytest.mark.parametrize("networks", ["t0.tree", Path("t0.tree"), 3])
def test_layout_rejects_a_single_network(networks):
    with pytest.raises(TypeError, match="wrap a single network in a list"):
        layout(networks)


def test_layout_rejects_a_single_network_file():
    nf = read(DATA_DIR / "planted_t0.ftree")
    with pytest.raises(TypeError, match="wrap a single network in a list"):
        layout(nf)
    assert len(layout(iter([nf])).networks) == 1  # any iterable of networks works


def test_layout_rejects_unhashable_colors():
    with pytest.raises(ValueError, match="colors must be one of"):
        layout([], colors=["similarity"])


def test_duplicate_stems_are_disambiguated(tmp_path):
    for year in ("2020", "2021", "2022"):
        (tmp_path / year).mkdir()
        shutil.copy(DATA_DIR / "planted_t0.ftree", tmp_path / year / "out.ftree")
    shutil.copy(DATA_DIR / "planted_t0.ftree", tmp_path / "out_2.ftree")
    paths = [tmp_path / y / "out.ftree" for y in ("2020", "2021", "2022")] + [tmp_path / "out_2.ftree"]
    # The second "out" skips "out_2", which another network already uses.
    assert [n.id for n in layout(paths).networks] == ["out", "out_3", "out_4", "out_2"]
    assert [n.id for n in layout(paths, ids=list("abcd")).networks] == list("abcd")
    files = [read(p, network_id=p.parent.name) for p in paths[:2]]
    assert [n.id for n in layout(files).networks] == ["2020", "2021"]
    with pytest.raises(ValueError, match="duplicate network id 'x'"):
        layout(paths[:2], ids=["x", "x"])
    with pytest.raises(ValueError, match=r"must not contain '--'.*ids="):
        layout(paths[:2], ids=["a--b", "c"])
    with pytest.raises(ValueError, match="got 1 ids for 2 networks"):
        layout(paths[:2], ids=["a"])
