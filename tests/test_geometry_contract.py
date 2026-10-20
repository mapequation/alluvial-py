import math

from conftest import compare, load_fixture
from helpers_geometry import geometry_from_fixture

from alluvial.geometry import CLOSEPOLY, CURVE4, LINETO, MOVETO, AlluvialGeometry, StreamlineGeometry


def test_path_codes_match_matplotlib_values():
    assert (MOVETO, LINETO, CURVE4, CLOSEPOLY) == (1, 2, 4, 79)


def test_fixture_geometry_and_svg_paths(scenario):
    fx = load_fixture(scenario)
    geom = geometry_from_fixture(fx)
    expected_paths = [link["path"] for n in fx["networks"] for link in n["links"]]
    assert [s.svg_path() for s in geom.streamlines] == expected_paths
    assert len(geom.networks) == len(fx["networks"])
    for net, n in zip(geom.networks, fx["networks"]):
        assert [m.id for m in net.modules] == [m["moduleId"] for m in n["modules"] if m["visible"]]
    # Field-wise dataclass __eq__ treats NaN != NaN, so compare the dicts NaN-aware (no fixture has NaN geometry since NaN flows are rejected, WP4).
    assert compare(AlluvialGeometry.from_dict(geom.to_dict()).to_dict(), geom.to_dict()).ok


def test_streamline_path_points():
    s = StreamlineGeometry(
        id="a",
        left=(0, "1", -1),
        right=(1, "1", -1),
        x0=80.0,
        y0=5e-7,
        h0=10.0,
        x1=240.0,
        y1=20.0,
        h1=5.0,
        avg_height=7.5,
        highlight_index=-1,
        left_highlight_index=-1,
        right_highlight_index=-1,
    )
    path = s.path()
    assert [c for c, _ in path] == [MOVETO, CURVE4, CURVE4, CURVE4, LINETO, CURVE4, CURVE4, CURVE4, CLOSEPOLY]
    assert path[0][1] == (80.0, 10.0)  # y0 snapped to 0 before y2 = y0 + h0
    assert path[3][1] == (240.0, 25.0)
    assert path[4][1] == (240.0, 20.0)
    assert path[7][1] == (80.0, 0.0)
    assert path[1][1][0] == 160.0
    assert s.svg_path() == "M80,10C160,10,160,25,240,25L240,20C160,20,160,0,80,0Z"


def test_svg_path_example_from_notes():
    s = StreamlineGeometry(
        id="a",
        left=(0, "1", -1),
        right=(1, "1", -1),
        x0=80,
        y0=72.80000000000001,
        h0=142.0,
        x1=240,
        y1=230.80000000000004,
        h1=198.79999999999998,
        avg_height=0.0,
        highlight_index=-1,
        left_highlight_index=-1,
        right_highlight_index=-1,
    )
    assert s.svg_path().startswith("M80,214.8")
    assert (
        "L240,230.80000000000004C160,230.80000000000004,160,72.80000000000001,80,72.80000000000001Z"
        in s.svg_path()
    )
    assert math.isclose(s.path()[2][1][1], 429.6)
