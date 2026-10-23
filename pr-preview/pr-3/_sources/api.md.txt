# API reference

```{eval-rst}
.. module:: alluvial
```

The page follows the tasks of the [capabilities tour](capabilities.ipynb): plot, lay out, read the inputs, save, and
pick colors. Every entry links to the tour sections that use it, and its examples run as tests, so they match the
current version. `draw`, `plot`, `legend` and `get_artists` load matplotlib on first access, so `import alluvial`
alone does not import it.

```{eval-rst}
.. data:: __version__

   The package version, a string such as ``"0.7.0"``: ``print(alluvial.__version__)``.
```

## Plotting

```{eval-rst}
.. autofunction:: alluvial.plot
```

Used in: [1.2 Infomap output files](capabilities.ipynb#12-infomap-output-files-tree-ftree-stree-clu) · [6.1 Axes, fonts and figure sizes](capabilities.ipynb#61-axes-fonts-and-figure-sizes) · [6.5 Saving figures](capabilities.ipynb#65-saving-figures-png-pdf-svg-and-rasterized)

```{eval-rst}
.. autofunction:: alluvial.draw
```

Used in: [2 Layout options](capabilities.ipynb#2-layout-options) · [3.1 Color modes](capabilities.ipynb#31-color-modes) · [6.2 Label options](capabilities.ipynb#62-label-options) · [6.3 Palettes, colormaps, gradients and styles](capabilities.ipynb#63-palettes-colormaps-gradients-and-styles)

```{eval-rst}
.. autofunction:: alluvial.legend
```

Used in: [3.4 Highlight groups and legends](capabilities.ipynb#34-highlight-groups-and-legends)

```{eval-rst}
.. autofunction:: alluvial.get_artists
```

Used in: [6.4 Restyling with get_artists](capabilities.ipynb#64-restyling-with-get_artists)

```{eval-rst}
.. autoclass:: alluvial.mpl.AlluvialArtists
```

Used in: [6.4 Restyling with get_artists](capabilities.ipynb#64-restyling-with-get_artists)

## Layout and geometry

```{eval-rst}
.. autofunction:: alluvial.layout
```

Used in: [1 Inputs](capabilities.ipynb#1-inputs) · [2 Layout options](capabilities.ipynb#2-layout-options) · [3.1 Color modes](capabilities.ipynb#31-color-modes) · [4 Hierarchy](capabilities.ipynb#4-hierarchy) · [7 Geometry access](capabilities.ipynb#7-geometry-access)

```{eval-rst}
.. autoclass:: alluvial.LayoutOptions
   :members:
```

Used in: [2 Layout options](capabilities.ipynb#2-layout-options)

```{eval-rst}
.. autoclass:: alluvial.AlluvialGeometry
   :members:
```

Used in: [7 Geometry access](capabilities.ipynb#7-geometry-access)

The geometry is a tree of frozen dataclasses: `AlluvialGeometry.networks` holds the `NetworkGeometry` of each
network, with its `ModuleGeometry` modules, their `GroupGeometry` highlight groups and `Label` labels, and the
`OutlineGeometry` boxes of the module hierarchy; `AlluvialGeometry.streamlines` holds the `StreamlineGeometry` between
adjacent networks. Each has `to_dict()`.

```{eval-rst}
.. autoclass:: alluvial.geometry.NetworkGeometry
.. autoclass:: alluvial.geometry.ModuleGeometry
.. autoclass:: alluvial.geometry.GroupGeometry
.. autoclass:: alluvial.geometry.Label
.. autoclass:: alluvial.geometry.OutlineGeometry
.. autoclass:: alluvial.geometry.StreamlineGeometry
   :members:
```

Used in: [7 Geometry access](capabilities.ipynb#7-geometry-access)

## Inputs

```{eval-rst}
.. autofunction:: alluvial.partition
```

Used in: [1.1 Dicts, partition() and DataFrames](capabilities.ipynb#11-dicts-partition-and-dataframes)

```{eval-rst}
.. autofunction:: alluvial.from_dataframe
```

Used in: [1.1 Dicts, partition() and DataFrames](capabilities.ipynb#11-dicts-partition-and-dataframes)

```{eval-rst}
.. autofunction:: alluvial.read
```

Used in: [1.2 Infomap output files](capabilities.ipynb#12-infomap-output-files-tree-ftree-stree-clu) · [1.3 Infomap JSON](capabilities.ipynb#13-infomap-json) · [1.4 Infomap results and objects](capabilities.ipynb#14-infomap-results-and-objects) · [1.7 The web app's zip, directories and lists of files](capabilities.ipynb#17-the-web-apps-zip-directories-and-lists-of-files)

```{eval-rst}
.. autofunction:: alluvial.split_layers
```

Used in: [1.6 Multilayer networks and split_layers](capabilities.ipynb#16-multilayer-networks-and-split_layers)

```{eval-rst}
.. autoclass:: alluvial.NetworkFile(id, name, format, nodes, ...)
```

Used in: [1.8 NetworkFile, names, ids and identifiers](capabilities.ipynb#18-networkfile-names-ids-and-identifiers)

```{eval-rst}
.. autoclass:: alluvial.NodeInfo
```

Used in: [3.4 Highlight groups and legends](capabilities.ipynb#34-highlight-groups-and-legends)

```{eval-rst}
.. autoclass:: alluvial.ModuleInfo
```

Used in: [5 Module names and order](capabilities.ipynb#5-module-names-and-order)

```{eval-rst}
.. autoclass:: alluvial.HighlightLabel
```

Used in: [3.4 Highlight groups and legends](capabilities.ipynb#34-highlight-groups-and-legends)

## Saving

```{eval-rst}
.. autofunction:: alluvial.save_diagram
```

Used in: [8 Save and load](capabilities.ipynb#8-save-and-load)

## Colors

```{eval-rst}
.. autodata:: alluvial.SCHEMES
   :no-value:
```

Used in: [3.2 Color schemes](capabilities.ipynb#32-color-schemes) · [3.3 Tones and offsets](capabilities.ipynb#33-tones-and-offsets)

Pass a name as `scheme=` to `layout`, `plot` or `save_diagram`, or pass a list of colors instead. The C3 schemes are
computed with [c3](https://mapequation.github.io/c3), which shows what they and its tones look like; `tone=` and
`offset=` apply to them. The other schemes are those of the web app's scheme menu. To draw with any matplotlib
colormap instead, pass `palette=` to `draw` or `plot`.

```{eval-rst}
.. alluvial-schemes::
```
