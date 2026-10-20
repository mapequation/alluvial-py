"""Warnings attributed to the user's code: the first stack frame outside the ``alluvial`` package."""

from __future__ import annotations

import os
import sys

_PACKAGE_DIR = os.path.normcase(os.path.dirname(os.path.abspath(__file__))) + os.sep


def user_stacklevel() -> int:
    """The ``stacklevel`` for a ``warnings.warn`` call in the calling frame that points at the first frame outside
    this package (whether the user called ``layout``, ``plot``, ``read`` or ``save_diagram``)."""
    frame = sys._getframe(1)
    level = 1
    while frame is not None and os.path.normcase(os.path.abspath(frame.f_code.co_filename)).startswith(
        _PACKAGE_DIR
    ):
        frame = frame.f_back
        level += 1
    return level
