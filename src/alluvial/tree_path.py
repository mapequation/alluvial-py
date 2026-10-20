"""Port of ``utils/TreePath.ts`` (alluvial-diagram 1.15.0 plus the fix round's E1/E2/E3).

Spec: docs/dev/port-notes/model.md §4 and parsers.md §3. Semantics:

- A path that contains ``;`` (stree insignificance) is parsed with ``([0-9]+)([:;])+``; the captured separator is
  the last of a run.
- Otherwise one trailing ``:`` (stree) is stripped before splitting, so ``"1:1:1:"`` is ``[1, 1, 1]``.
- ``ancestor_at_level_as_string`` falls back to the full path string when the level is not stored.
- ``is_ancestor`` tests the string prefix up to a ``:`` (``"1"`` is an ancestor of ``"1:3"``, not of ``"10:3"``).

Methods that exist both as static and instance methods in TS work both ways here:
``TreePath.is_root("root")`` and ``TreePath("1:2").is_root()``.
"""

from __future__ import annotations

import functools
import re
from typing import Any, Union

from ._jscompat import js_array_join, js_is_integer, js_number, js_number_to_string

__all__ = ["TreePath"]

Path = Union["TreePath", str, int, float, list]

_INSIGNIFICANT_RE = re.compile(r"([0-9]+)([:;])+")
_TREE_PATH_RE = re.compile(r"([0-9]+:)*[0-9]+")


class _hybridmethod:
    """Call as ``Class.f(path, ...)`` (TS static) or ``instance.f(...)`` (TS instance, ``path = this``)."""

    def __init__(self, func):
        self.func = func
        functools.update_wrapper(self, func)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self.func
        return functools.partial(self.func, obj)


def _to_string(path: Any) -> str:
    """JS ``path.toString()``."""
    if isinstance(path, TreePath):
        return path.path
    if isinstance(path, str):
        return path
    if isinstance(path, bool):
        return "true" if path else "false"
    if isinstance(path, (int, float)):
        return js_number_to_string(path)
    if isinstance(path, (list, tuple)):
        return js_array_join(path, ",")
    if path is None:
        raise TypeError("Cannot read properties of undefined (reading 'toString')")
    return str(path)


def _number(part: str) -> int | float:
    value = js_number(part)
    return int(value) if js_is_integer(value) else value


class TreePath:
    """A ``:``-separated module path such as ``"1:2:3"`` (TS ``TreePath``).

    Parameters
    ----------
    path : TreePath, str, int or list of int
        A path string (tree/ftree/clu ``"1:2:3"``, stree ``"1:2;3;"``), a number (clu module id) or a
        list of path components (JSON input). A list is kept as ``path_arr`` without copying.
    """

    __slots__ = ("ancestor_paths", "insignificant", "path", "path_arr")

    path: str
    path_arr: list
    insignificant: list[bool]
    ancestor_paths: dict[int, str]

    def __init__(self, path: Path) -> None:
        is_list = isinstance(path, list)
        string = js_array_join(path, ":") if is_list else _to_string(path)
        self.insignificant = []

        if ";" in string:
            self.path_arr = []
            for match in _INSIGNIFICANT_RE.finditer(string):
                self.path_arr.append(int(match.group(1)))
                self.insignificant.append(match.group(2) == ";")
            self.path = js_array_join(self.path_arr, ":")
        else:
            # strip the stree trailing ``:`` before splitting, so it adds no level
            self.path = string[:-1] if string.endswith(":") else string
            self.path_arr = path if is_list else TreePath.to_array(self.path)
            self.insignificant = [False] * len(self.path_arr)

        self.ancestor_paths = {0: "root"}
        for level in range(1, len(self.path_arr)):
            self.ancestor_paths[level] = js_array_join(self.path_arr[:level], ":")

    @property
    def level(self) -> int:
        return 0 if self.is_root() else len(self.path_arr)

    @property
    def rank(self) -> int | float:
        if TreePath.is_root(self):
            return 0
        return self.to_array()[-1]

    @staticmethod
    def from_array(path: list) -> TreePath:
        return TreePath.root() if not path else TreePath(js_array_join(path, ":"))

    @staticmethod
    def join(parent_path: Path, path: Path) -> TreePath:
        if TreePath.is_root(parent_path):
            return TreePath(path)
        return TreePath.from_array([_to_string(parent_path), _to_string(path)])

    @staticmethod
    def root() -> TreePath:
        return TreePath("root")

    @_hybridmethod
    def is_root(path: Path) -> bool:
        return _to_string(path) == "root"

    @_hybridmethod
    def equal(a: Path, b: Path) -> bool:
        return _to_string(a) == _to_string(b)

    @_hybridmethod
    def is_ancestor(parent: Path, child: Path) -> bool:
        if TreePath.is_root(parent):
            return True
        p = _to_string(parent)
        c = _to_string(child)
        if len(p) >= len(c):
            return False
        return c.startswith(p + ":")

    @staticmethod
    def level_of(path: Path) -> int:
        """TS static ``TreePath.level(path)``."""
        return 0 if TreePath.is_root(path) else len(TreePath.to_array(path))

    @_hybridmethod
    def ancestor_at_level(path: Path, level: int) -> TreePath:
        if level == 0:
            return TreePath.root()
        return TreePath.from_array(TreePath.to_array(path)[:level])

    @_hybridmethod
    def is_parent_of(parent: Path, child: Path) -> bool:
        p = TreePath.parent_path(child)
        if p is None:
            return False
        return TreePath.equal(parent, p)

    @_hybridmethod
    def parent_path(path: Path) -> TreePath | None:
        if not TreePath.is_tree_path(path):
            return None
        if len(TreePath.to_array(path)) == 1:
            return TreePath.root()
        p = _to_string(path)
        return TreePath(p[: p.rfind(":")])

    @_hybridmethod
    def to_array(path: Path) -> list:
        """``path.toString().split(":").map(Number)``; integral values are returned as ``int``."""
        return [_number(part) for part in _to_string(path).split(":")]

    @staticmethod
    def is_tree_path(path: Path) -> bool:
        return _TREE_PATH_RE.fullmatch(_to_string(path)) is not None

    def to_id(self) -> str:
        path = str(self)
        if TreePath.is_tree_path(path):
            path = path.replace(":", "-")
        return f"id-{path}"

    def ancestor_at_level_as_string(self, level: int) -> str:
        return self.ancestor_paths.get(level) or self.path

    def is_significant(self, level: int) -> bool:
        if level < 0 or level >= len(self.insignificant):
            return False
        return not self.insignificant[level]

    def __str__(self) -> str:
        return self.path

    def __repr__(self) -> str:
        return f"TreePath({self.path!r})"
