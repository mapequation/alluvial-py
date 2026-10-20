"""Error messages and warnings for common mistakes with the public API."""

from __future__ import annotations

import importlib.util
import warnings

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest
from conftest import DATA_DIR

import alluvial

PLANTED = [DATA_DIR / f"planted_t{i}.ftree" for i in range(2)]
MULTILEVEL = [DATA_DIR / f"multilevel_t{i}.tree" for i in range(2)]
STATES = DATA_DIR / "mlayer_states.tree"

needs_infomap = pytest.mark.skipif(importlib.util.find_spec("infomap") is None, reason="needs infomap")


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _no_warnings(f):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return f()


@needs_infomap
def test_unrun_infomap_says_run_first():
    import infomap

    im = infomap.Infomap(silent=True)
    im.add_link(1, 2)
    with pytest.raises(ValueError, match=r"has not been run; call im\.run\(\) first"):
        alluvial.plot([im])


def test_missing_file_is_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError, match="no such network file") as info:
        alluvial.layout([PLANTED[0], tmp_path / "missing"])  # no suffix: not reported as a format error
    assert info.value.filename == str(tmp_path / "missing")


def test_directory_without_network_files(tmp_path):
    # a directory reads its network files (a saved diagram's loose files); an empty one is an error
    with pytest.raises(ValueError, match=r"holds no network files"):
        alluvial.layout([tmp_path])


def test_read_checks_the_path_before_the_format(tmp_path):
    with pytest.raises(FileNotFoundError, match="no such network file"):
        alluvial.read(tmp_path / "missing")
    with pytest.raises(ValueError, match=r"holds no network files"):
        alluvial.read(tmp_path)


def test_module_level_accepts_numpy_integers():
    import numpy as np

    assert alluvial.layout(MULTILEVEL, module_level=np.int64(2)) == alluvial.layout(
        MULTILEVEL, module_level=2
    )
    assert alluvial.layout(MULTILEVEL, module_level=[np.int64(1), np.int32(2)]) == alluvial.layout(
        MULTILEVEL, module_level=[1, 2]
    )


def test_expand_without_sub_modules_says_so():
    with pytest.raises(
        ValueError, match=r"cannot expand module '1'.*it has no sub-modules.*Module can't be expanded"
    ):
        alluvial.layout(PLANTED, expand=[(0, "1")])


def test_empty_networks():
    with pytest.raises(ValueError, match="networks is empty"):
        alluvial.plot([])


def test_geometry_and_networks_swapped():
    geom = alluvial.layout(PLANTED)
    with pytest.raises(TypeError, match=r"alluvial\.plot\(networks"):
        alluvial.draw(PLANTED)
    with pytest.raises(TypeError, match=r"already laid out; draw it with alluvial\.draw"):
        alluvial.plot(geom)


def test_draw_rejects_figure_and_axes_array():
    geom = alluvial.layout(PLANTED)
    with pytest.raises(TypeError, match=r"ax must be a matplotlib Axes, got Figure"):
        alluvial.draw(geom, plt.figure())
    _, axs = plt.subplots(1, 2)
    with pytest.raises(TypeError, match=r"axs\[0\]"):
        alluvial.draw(geom, axs)


def test_unknown_keywords_suggest_the_right_one():
    with pytest.raises(TypeError, match=r"'heigth' \(did you mean 'height'\?\)"):
        alluvial.layout(PLANTED, heigth=300)
    with pytest.raises(TypeError, match=r"drawing options such as ax="):
        alluvial.layout(PLANTED, ax=None)
    with pytest.raises(TypeError, match=r"'fontsze' \(did you mean 'fontsize'\?\)"):
        alluvial.plot(PLANTED, fontsze=6)


def test_mixed_state_and_node_networks_warn():
    with pytest.warns(UserWarning, match=r"match their nodes by state id.*identifier='name'"):
        alluvial.layout([STATES, PLANTED[0]])


def test_state_networks_matched_by_name_or_split_do_not_warn_about_mixing():
    for kwargs in ({"identifier": "name"}, {"split_layers": [True, False]}):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            alluvial.layout([STATES, DATA_DIR / "mlayer_flat.tree"], **kwargs)
        assert not [w for w in caught if "state id" in str(w.message)], kwargs


def test_highlight_names_with_id_matching_hint_identifier():
    with pytest.warns(UserWarning, match=r"1 of 2 identifiers match no node.*'nobody'.*identifier='name'"):
        alluvial.layout(PLANTED, highlight={"a": [1, "nobody"]})


def test_highlight_callable_matching_nothing_warns():
    with pytest.warns(UserWarning, match="returned None for every node"):
        alluvial.layout(PLANTED, highlight=lambda node: None)


def test_module_level_deeper_than_tree_warns():
    with pytest.warns(UserWarning, match=r"module_level is deeper.*'planted_t0\.ftree'.*two-level partition"):
        alluvial.layout(PLANTED, module_level=2)
    with pytest.warns(UserWarning, match=r"deepest level 2"):
        alluvial.layout(MULTILEVEL, module_level=3)
    _no_warnings(lambda: alluvial.layout(MULTILEVEL, module_level=2))
    _no_warnings(lambda: alluvial.layout([PLANTED[0], MULTILEVEL[0]], module_level=[1, 2]))


def test_hatch_hint_in_draw_docstring():
    assert '"hatch": "//", "edgecolor"' in alluvial.draw.__doc__
