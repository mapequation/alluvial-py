"""Sphinx configuration for the alluvial documentation (https://mapequation.github.io/alluvial-py)."""

from docutils import nodes
from docutils.statemachine import StringList
from sphinx.util.docutils import SphinxDirective

import alluvial
from alluvial import _palette

project = "alluvial"
author = "mapequation"
copyright = "mapequation"
version = release = alluvial.__version__

extensions = [
    "myst_nb",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
]

exclude_patterns = ["_build", "dev/**", "tutorial_output", "**.ipynb_checkpoints"]

# The notebooks are executed (and run by tests/test_tutorial.py and tests/test_capabilities_notebook.py);
# render their stored outputs.
nb_execution_mode = "off"
# Anchors for "#1-inputs"-style links to headings (the capabilities table of contents).
myst_heading_anchors = 3

autodoc_member_order = "bysource"
autodoc_typehints = "description"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable", None),
    "matplotlib": ("https://matplotlib.org/stable", None),
}

html_theme = "pydata_sphinx_theme"
html_title = f"alluvial {release}"
html_theme_options = {
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/mapequation/alluvial-py",
            "icon": "fa-brands fa-github",
        },
    ],
}


class ColorSchemes(SphinxDirective):
    """``.. alluvial-schemes::``: the scheme names of ``alluvial.SCHEMES`` by group, and the c3 tones, generated
    from the package so the list cannot go stale (names only, never color values)."""

    def run(self) -> list[nodes.Node]:
        groups: dict[str, list[str]] = {}
        group_of = {name: group for group, names in _palette.SCHEME_GROUPS.items() for name in names}
        if set(group_of) != set(alluvial.SCHEMES):
            raise self.error("alluvial.SCHEMES and the scheme groups disagree")
        for name in alluvial.SCHEMES:
            groups.setdefault(group_of[name], []).append(name)
        lines = [
            ".. list-table::",
            "   :header-rows: 1",
            "   :widths: auto",
            "",
            "   * - Group",
            "     - Schemes",
        ]
        for group, names in groups.items():
            lines += [f"   * - {group}", "     - " + ", ".join(f"``{name}``" for name in names)]
        tones = ", ".join(
            f"``{tone}``" + (" (default)" if tone == _palette.DEFAULT_TONE else "") for tone in _palette.TONES
        )
        lines += ["", f"The c3 tones (``tone=``): {tones}."]
        container = nodes.container()
        self.state.nested_parse(StringList(lines, source="conf.py"), self.content_offset, container)
        return container.children


def setup(app):
    app.add_directive("alluvial-schemes", ColorSchemes)
