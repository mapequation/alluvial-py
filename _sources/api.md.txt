# API reference

```{eval-rst}
.. module:: alluvial

``draw``, ``plot``, ``legend`` and ``get_artists`` load matplotlib on first access, so ``import alluvial`` alone
does not import it.

.. data:: __version__

   The package version, as a string.
```

## Plotting

```{eval-rst}
.. autofunction:: alluvial.plot
.. autofunction:: alluvial.draw
.. autofunction:: alluvial.legend
.. autofunction:: alluvial.get_artists
```

## Layout and geometry

```{eval-rst}
.. autofunction:: alluvial.layout
.. autoclass:: alluvial.LayoutOptions
   :members:
.. autoclass:: alluvial.AlluvialGeometry
   :members:
.. autoclass:: alluvial.HighlightLabel
   :members:
```

## Reading and saving

```{eval-rst}
.. autofunction:: alluvial.read
.. autofunction:: alluvial.split_layers
.. autofunction:: alluvial.save_diagram
```

## Data types

```{eval-rst}
.. autoclass:: alluvial.NetworkFile
   :members:
.. autoclass:: alluvial.ModuleInfo
   :members:
.. autoclass:: alluvial.NodeInfo
   :members:
```

## Colours and palettes

```{eval-rst}
.. data:: SCHEMES

   The web app's colour schemes: a read-only mapping from scheme name to its colours (the same object as
   :data:`alluvial.palette.SCHEMES`).

.. automodule:: alluvial.palette
   :members:
```
