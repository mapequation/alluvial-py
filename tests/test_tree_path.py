import math

import pytest

from alluvial.tree_path import TreePath

F, T = False, True

# (input, path, path_arr, insignificant, level, anc(1), anc(2), anc(5), sig(0), sig(1)); model.md §4, parsers.md §3.
CASES = [
    ("1:1:1:", "1:1:1", [1, 1, 1], [F, F, F], 3, "1", "1:1", "1:1:1", T, T),  # E1: no phantom level
    ("1:2;3;", "1:2:3", [1, 2, 3], [F, T, T], 3, "1", "1:2", "1:2:3", T, F),
    ("1;2;", "1:2", [1, 2], [T, T], 2, "1", "1:2", "1:2", F, F),
    ("1;1:235;", "1:1:235", [1, 1, 235], [T, F, T], 3, "1", "1:1", "1:1:235", F, T),
    ("1;;2;", "1:2", [1, 2], [T, T], 2, "1", "1:2", "1:2", F, F),
    ("1;2:3;", "1:2:3", [1, 2, 3], [T, F, T], 3, "1", "1:2", "1:2:3", F, T),
    # E3: a `;` that is not last also selects the `;` parse; the bare trailing number is dropped
    ("1:2;3", "1:2", [1, 2], [F, T], 2, "1", "1:2", "1:2", T, F),
    ("5", "5", [5], [F], 1, "5", "5", "5", T, F),
    ("1:2", "1:2", [1, 2], [F, F], 2, "1", "1:2", "1:2", T, T),
    ([1, 2], "1:2", [1, 2], [F, F], 2, "1", "1:2", "1:2", T, T),
    ("01:2", "01:2", [1, 2], [F, F], 2, "1", "01:2", "01:2", T, T),
    ("1:", "1", [1], [F], 1, "1", "1", "1", T, F),
    ([1, 2, 3], "1:2:3", [1, 2, 3], [F, F, F], 3, "1", "1:2", "1:2:3", T, T),
    ("", "", [0], [F], 1, "", "", "", T, F),
    (3, "3", [3], [F], 1, "3", "3", "3", T, F),
]


@pytest.mark.parametrize("case", CASES, ids=[repr(c[0]) for c in CASES])
def test_constructor(case):
    inp, path, arr, insig, level, a1, a2, a5, s0, s1 = case
    tp = TreePath(inp)
    assert str(tp) == path
    assert tp.path_arr == arr
    assert all(isinstance(x, int) for x in tp.path_arr)
    assert tp.insignificant == insig
    assert tp.level == level
    assert tp.ancestor_at_level_as_string(0) == "root"
    assert tp.ancestor_at_level_as_string(1) == a1
    assert tp.ancestor_at_level_as_string(2) == a2
    assert tp.ancestor_at_level_as_string(5) == a5
    assert tp.is_significant(0) is s0
    assert tp.is_significant(1) is s1
    assert tp.is_significant(-1) is False


def test_list_is_aliased():
    arr = [1, 2]
    assert TreePath(arr).path_arr is arr


def test_semicolon_not_last():
    # E3: `;` anywhere selects the insignificant-path parse (TS used to give [1, NaN], module "NaN")
    tp = TreePath("1:2;3")
    assert not any(isinstance(x, float) and math.isnan(x) for x in tp.path_arr)
    assert TreePath("1;1;63;").path_arr == [1, 1, 63]
    assert TreePath("1:1;16;").insignificant == [F, T, T]


def test_trailing_colon_same_as_without():
    # E1: "1:1:1:" (stree) is the same path as "1:1:1"
    a, b = TreePath("1:1:1:"), TreePath("1:1:1")
    assert (a.path, a.path_arr, a.insignificant, a.level) == (b.path, b.path_arr, b.insignificant, b.level)


def test_is_ancestor_needs_separator():
    # E2: "1" is not an ancestor of "10:3"; "1:2" is not one of "1:20"
    assert TreePath.is_ancestor("1", "1:2")
    assert TreePath.is_ancestor("1", "1:20:3")
    assert not TreePath.is_ancestor("1", "10")
    assert not TreePath.is_ancestor("1", "10:3")
    assert not TreePath.is_ancestor("1:2", "1:20")
    assert TreePath("1:2").is_ancestor("1:2:7")
    assert not TreePath("1:1").is_ancestor("1:10:1")


def test_root():
    root = TreePath.root()
    assert root.is_root() and TreePath.is_root("root") and root.level == 0 and root.rank == 0
    assert math.isnan(root.path_arr[0])
    assert TreePath.level_of("root") == 0 and TreePath.level_of("1:2:3") == 3


def test_static_and_instance_methods():
    assert TreePath.to_array("1:1") == [1, 1]
    assert TreePath.to_array(1) == [1]
    assert math.isnan(TreePath.to_array("root")[0])
    assert TreePath("1:").to_array() == [1]
    assert TreePath.is_ancestor("root", "1")
    assert TreePath.is_ancestor("1", "1:2")
    assert not TreePath.is_ancestor("1", "10:3")
    assert not TreePath("1:2").is_ancestor("1:2")
    assert TreePath.parent_path("root") is None
    assert TreePath.parent_path(1).is_root()
    assert str(TreePath.parent_path("1:2:3")) == "1:2"
    assert TreePath("1:2:3").parent_path().path == "1:2"
    assert TreePath.is_parent_of("1", "1:2") and not TreePath.is_parent_of("1", "1:2:3")
    assert (
        TreePath.is_tree_path("1:2:3")
        and not TreePath.is_tree_path("1:2:")
        and not TreePath.is_tree_path("1:2\n")
    )
    assert not TreePath.is_tree_path("١")
    assert TreePath("1:2").to_id() == "id-1-2" and TreePath.root().to_id() == "id-root"
    assert TreePath("1:2:7").rank == 7
    assert str(TreePath.from_array([1, 2])) == "1:2" and TreePath.from_array([]).is_root()
    assert str(TreePath.join("root", "3")) == "3" and str(TreePath.join("1", "3")) == "1:3"
    assert TreePath("1:2:3").ancestor_at_level(0).is_root()
    assert str(TreePath.ancestor_at_level("1:2:3", 2)) == "1:2"
    assert TreePath.equal(TreePath("1:2"), "1:2") and TreePath("1:2").equal("1:2")
    assert str(TreePath(TreePath("1:2;3;"))) == "1:2:3"
