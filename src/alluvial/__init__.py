"""Alluvial diagrams of Infomap partitions for matplotlib, with the web app's layout (mapequation.org/alluvial).

``draw``, ``plot``, ``legend`` and ``get_artists`` load matplotlib on first access, so ``import alluvial`` alone does not import it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import _palette
from .geometry import AlluvialGeometry, HighlightLabel
from .io import NetworkFile, from_dataframe, partition, read, split_layers
from .layout import LayoutOptions, ModuleInfo, NodeInfo, layout, save_diagram

if TYPE_CHECKING:
    from .mpl import draw, get_artists, legend, plot

__version__ = "0.7.0"

#: The names of the web app's color schemes, in the order of its scheme menu: the values of ``scheme=``.
SCHEMES: tuple[str, ...] = tuple(_palette.SCHEMES)

__all__ = [
    "SCHEMES",
    "AlluvialGeometry",
    "HighlightLabel",
    "LayoutOptions",
    "ModuleInfo",
    "NetworkFile",
    "NodeInfo",
    "__version__",
    "draw",
    "from_dataframe",
    "get_artists",
    "layout",
    "legend",
    "partition",
    "plot",
    "read",
    "save_diagram",
    "split_layers",
]


_MPL_NAMES = ("draw", "get_artists", "legend", "plot")


def __getattr__(name: str) -> Any:
    if name in _MPL_NAMES:
        from . import mpl

        return getattr(mpl, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_MPL_NAMES))
