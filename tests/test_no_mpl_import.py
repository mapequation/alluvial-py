import subprocess
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

CODE = f"""
import sys
import alluvial
import alluvial.layout, alluvial.geometry, alluvial.io, alluvial.io.types, alluvial.engine
import alluvial.palette, alluvial.tree_path, alluvial._jscompat
from alluvial import layout, read, LayoutOptions, AlluvialGeometry, NetworkFile, NodeInfo, split_layers, __version__
ml = [r"{DATA}/multilevel_t{{i}}.tree".format(i=i) for i in range(3)]
layout(ml, module_level=2, expand=[(1, "1"), (1, "1:1")], highlight={{"a": [1, 2]}}, highlight_colors=["red"])
layout(ml, highlight=lambda n: n.path[0])
layout([r"{DATA}/mlayer_states.tree"], split_layers=True, colors="layer")
bad = sorted(m for m in sys.modules if m == "matplotlib" or m.startswith("matplotlib."))
assert not bad, bad
assert "infomap" not in sys.modules
"""


def test_core_modules_do_not_import_matplotlib():
    subprocess.run([sys.executable, "-c", CODE], check=True)


def test_draw_and_plot_are_lazy_reexports():
    code = (
        "import alluvial, alluvial.mpl; assert alluvial.plot is alluvial.mpl.plot; "
        "assert alluvial.legend is alluvial.mpl.legend; print(alluvial.draw.__name__)"
    )
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert out.stdout.strip() == "draw"
