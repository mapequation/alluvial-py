"""Sphinx configuration for the alluvial documentation (https://mapequation.github.io/alluvial-py)."""

import alluvial

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
