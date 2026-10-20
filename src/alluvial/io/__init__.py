"""Readers: Infomap text output (tree/ftree/stree/clu), Infomap JSON and ``infomap.Infomap`` objects -> ``NetworkFile``.

Pure Python; ``infomap`` is imported lazily by the Infomap reader only. Spec: docs/dev/port-notes/parsers.md and
docs/dev/port-notes/v2-io.md (JSON, multilayer splitting).
"""

from __future__ import annotations

import errno
import math
import os
import warnings
from pathlib import Path
from typing import Any, Literal, overload

from .._warnings import user_stacklevel
from .alluvial_format import read_alluvial_metadata, serialize_diagram, sort_by_saved_position
from .identifiers import calc_statistics, create_file, set_identifiers, warn_duplicate_identifiers
from .infomap_reader import from_infomap, is_infomap
from .json_reader import _json_name, from_json_dict, read_json
from .multilayer import split_layers as _split_layers
from .text import ParseError, parse
from .types import InfomapModule, Link, NetworkFile, Node

__all__ = [
    "InfomapModule",
    "Link",
    "NetworkFile",
    "Node",
    "ParseError",
    "calc_statistics",
    "create_file",
    "from_infomap",
    "read",
    "read_alluvial_metadata",
    "read_dir",
    "read_file",
    "read_json",
    "read_zip",
    "serialize_diagram",
    "set_identifiers",
    "sort_by_saved_position",
    "split_layers",
]

split_layers = _split_layers

TEXT_FORMATS = ("tree", "ftree", "stree", "clu")
FORMATS = (*TEXT_FORMATS, "json")

_HOW_TO = (
    "write a partition with `infomap net.net out/ -o tree` (add `states` for state networks) or "
    "im.write_tree('net.tree'), or pass the infomap.Infomap object to alluvial.read"
)
_UNSUPPORTED = {
    "net": "is an Infomap input network (or an Infomap -o network/flow/states output) without modules; run Infomap "
    "on it first: " + _HOW_TO,
    "csv": "is Infomap's CSV output, which is not supported; " + _HOW_TO,
    "nwk": "is Newick, which is not supported; " + _HOW_TO,
    "newick": "is Newick, which is not supported; " + _HOW_TO,
    "zip": "is a zip archive of network files; read it with alluvial.read (one NetworkFile per network file)",
}


def _warn_unparsed_ids(nf: NetworkFile, path: Path) -> None:
    bad = [n for n in nf.nodes if isinstance(n.id, float) and math.isnan(n.id)]
    if bad:
        warnings.warn(
            f"{path.name}: {len(bad)} node row(s) have no readable node id (e.g. name {bad[0].name!r}). This happens "
            'when a node name contains a double quote ("), which Infomap writes unescaped; the web app misreads it '
            "the same way. Remove quotes from the node names, or read the infomap.Infomap object instead",
            UserWarning,
            stacklevel=user_stacklevel(),
        )


def read_file(
    path: str | os.PathLike[str],
    *,
    name: str | None = None,
    network_id: str | None = None,
    identifier: Literal["id", "name"] = "id",
    format: str | None = None,
) -> NetworkFile:
    """Read a ``.tree``/``.ftree``/``.stree``/``.clu`` or Infomap ``.json`` file like the web app does.

    Parameters
    ----------
    path : str or PathLike
        The file. Read as UTF-8 (a leading BOM is dropped, as in the browser).
    name : str, optional
        Network name. Defaults to the file basename (with extension); for JSON, to a top-level ``name`` first.
    network_id : str, optional
        Network id. Defaults to the file stem; for JSON, to a top-level string ``id`` first.
    identifier : {"id", "name"}, default "id"
        Node identity across networks (``set_identifiers``).
    format : str, optional
        One of ``"tree"``, ``"ftree"``, ``"stree"``, ``"clu"``, ``"json"`` (Infomap ``-o json`` output). Defaults
        to the lower-cased suffix.

    Returns
    -------
    NetworkFile

    Raises
    ------
    FileNotFoundError, IsADirectoryError
        If ``path`` does not exist or is a directory.
    ValueError
        For an unsupported format, a file the TS parser rejects (``ParseError``), content that does not match the
        format (tree content in a ``.clu`` file or vice versa), a file without nodes, a node whose flow is not a
        finite number (NaN, infinite, missing or JSON ``null``), invalid JSON, or JSON that is not Infomap output
        (an Infomap input network, a saved web-app diagram).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(errno.ENOENT, "no such network file", os.fspath(path))
    if p.is_dir():
        raise IsADirectoryError(
            errno.EISDIR,
            "a directory, not a network file; use alluvial.read(directory) to read all its network files "
            "(e.g. the loose files of save_diagram(..., loose=True))",
            os.fspath(path),
        )
    fmt = format if format is not None else p.suffix[1:].lower()
    if fmt in _UNSUPPORTED:
        raise ValueError(f"{p.name} {_UNSUPPORTED[fmt]}")
    if fmt not in FORMATS:
        raise ValueError(f"unsupported network file format {fmt!r} ({p.name}); expected one of {FORMATS}")
    if fmt == "json":
        return read_json(p, name=name, network_id=network_id, identifier=identifier)
    stat = p.stat()
    return _text_network(
        p.read_text(encoding="utf-8-sig"),
        fmt,
        id=p.stem if network_id is None else network_id,
        name=p.name if name is None else name,
        filename=p.name,
        size=stat.st_size,
        last_modified=int(stat.st_mtime * 1000),
        identifier=identifier,
    )


def _text_network(
    text: str, fmt: str, *, id: str, name: str, filename: str, size: int, last_modified: int, identifier: str
) -> NetworkFile:
    """A tree/ftree/stree/clu text -> ``NetworkFile`` (``parse`` + ``setIdentifiers`` + ``createFile``)."""
    kind, contents = parse(text)
    if (kind == "clu") != (fmt == "clu"):
        raise ParseError(f"{filename}: the content is a {kind} file, but the format is {fmt!r}")
    set_identifiers(contents["nodes"], fmt, identifier)
    nf = create_file(
        contents, format=fmt, id=id, name=name, filename=filename, size=size, last_modified=last_modified
    )
    _warn_unparsed_ids(nf, Path(filename))
    return nf


def read_zip(path: str | os.PathLike[str], *, identifier: Literal["id", "name"] = "id") -> list[NetworkFile]:
    """Read a zip of network files, as the web app's load dialog does with a dropped ``.zip``
    (``readAcceptedFiles``, v4-names-order.md §6): one ``NetworkFile`` per entry, in archive order.

    Entries with a network-file suffix (``.tree``, ``.ftree``, ``.stree``, ``.clu``, ``.json``) are read; directory
    entries and macOS ``__MACOSX/`` metadata are skipped silently, other entries with a warning (the web app
    reports them and loads the rest). The name is the JSON ``name`` or the entry name; the id is the JSON string
    ``id`` or the entry's base name without its suffix (the web app's ids are random). A web-app zip from
    ``save_diagram`` carries its palette (``colors``), colour indices and expansion levels.
    """
    import zipfile

    from .json_reader import _json_str, parse_json

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(errno.ENOENT, "no such zip file", os.fspath(path))
    try:
        archive = zipfile.ZipFile(p)
    except zipfile.BadZipFile as e:
        raise ValueError(f"{p.name} is not a readable zip file ({e})") from None
    files: list[NetworkFile] = []
    skipped: list[str] = []
    with archive:
        for info in archive.infolist():
            entry = info.filename
            base = entry.rsplit("/", 1)[-1]
            if info.is_dir() or entry.startswith("__MACOSX/") or base.startswith("._") or not base:
                continue
            stem, dot, suffix = base.rpartition(".")
            fmt = suffix.lower() if dot else ""
            if fmt not in FORMATS:
                skipped.append(entry)
                continue
            try:
                text = archive.read(info).decode("utf-8-sig")
            except UnicodeDecodeError as e:
                raise ValueError(f"{p.name}: {entry} is not UTF-8 text ({e})") from None
            last_modified = 0
            if fmt == "json":
                try:
                    data = parse_json(text)
                except ValueError as e:
                    raise ValueError(f"{p.name}: {entry} is not valid JSON ({e})") from None
                nf = from_json_dict(
                    data,
                    id=_json_str(data, "id") or stem,
                    name=_json_name(data, entry),
                    identifier=identifier,
                    filename=entry,
                    size=info.file_size,
                    last_modified=last_modified,
                    where=f"{p.name}: {entry}",
                )
            else:
                nf = _text_network(
                    text,
                    fmt,
                    id=stem,
                    name=entry,
                    filename=entry,
                    size=info.file_size,
                    last_modified=last_modified,
                    identifier=identifier,
                )
            files.append(nf)
    if skipped:
        warnings.warn(
            f"{p.name}: skipped {len(skipped)} entr{'y' if len(skipped) == 1 else 'ies'} that are not network "
            f"files ({', '.join(skipped[:3])}{', ...' if len(skipped) > 3 else ''})",
            UserWarning,
            stacklevel=user_stacklevel(),
        )
    if not files:
        raise ValueError(f"{p.name} holds no network files (.tree, .ftree, .stree, .clu or .json)")
    return sort_by_saved_position(files)


def read_dir(path: str | os.PathLike[str], *, identifier: Literal["id", "name"] = "id") -> list[NetworkFile]:
    """Read the network files of a directory (``.tree``, ``.ftree``, ``.stree``, ``.clu``, ``.json``; other files
    are ignored), in file-name order, or in saved order when they are the files of one saved diagram
    (``save_diagram(..., loose=True)`` or the files of the web app's zip)."""
    p = Path(path)
    paths = sorted(q for q in p.iterdir() if q.is_file() and q.suffix[1:].lower() in FORMATS)
    if not paths:
        raise ValueError(f"{p} holds no network files (.tree, .ftree, .stree, .clu or .json)")
    return sort_by_saved_position([read_file(q, identifier=identifier) for q in paths])


@overload
def read(
    source: str | os.PathLike[str] | Any,
    *,
    name: str | None = ...,
    identifier: Literal["id", "name"] = ...,
    states: bool | None = ...,
    network_id: str | None = ...,
    split_layers: Literal[False] = ...,
) -> NetworkFile: ...


@overload
def read(
    source: str | os.PathLike[str] | Any,
    *,
    name: str | None = ...,
    identifier: Literal["id", "name"] = ...,
    states: bool | None = ...,
    network_id: str | None = ...,
    split_layers: Literal[True],
) -> list[NetworkFile]: ...


def read(
    source: str | os.PathLike[str] | Any,
    *,
    name: str | None = None,
    identifier: Literal["id", "name"] = "id",
    states: bool | None = None,
    network_id: str | None = None,
    split_layers: bool = False,
) -> NetworkFile | list[NetworkFile]:
    """Read one network into a ``NetworkFile`` (or, with ``split_layers=True``, one per layer).

    Parameters
    ----------
    source : str, PathLike, dict, infomap.Infomap or NetworkFile
        A ``.tree``/``.ftree``/``.stree``/``.clu`` path (format from the suffix; Infomap's ``-o states`` files
        ``*_states.tree``/``.ftree``/``.clu`` included), an Infomap ``-o json`` file (``.json``) or its parsed
        ``dict``, an ``infomap.Infomap`` that has run, an infomap ``Result`` (from ``im.run()``,
        ``infomap.run(...)`` or ``Network.run()``; infomap >= 2.14), or a ``NetworkFile`` (returned unchanged
        unless split). A ``.zip`` of network files (the web app's zip upload, or ``save_diagram``), a directory of
        network files, or a list of paths gives a list, one ``NetworkFile`` per file, in archive (file-name, list)
        order, or in saved order when they are the files of one saved diagram.
    name : str, optional
        Network name. Defaults to the file basename, or ``"network"`` for objects. For JSON a top-level ``name``
        comes before these defaults.
    identifier : {"id", "name"}, default "id"
        Node identity across networks, as in the web app: ``"id"`` uses ``state_id`` if present else the node id,
        ``"name"`` the node name. See *State networks* below. Ignored with ``split_layers=True``.
    states : bool, optional
        Infomap objects only: read state nodes. ``None`` picks them for state/memory and multilayer networks
        (like ``write_tree(states=True)``); ``False`` reads the physical level (``write_tree(states=False)``).
    network_id : str, optional
        Network id. Defaults to the file stem for paths, or ``name`` (else ``"network"``) for objects. For JSON a
        top-level string ``id`` comes before these defaults.
    split_layers : bool, default False
        Split a multilayer state network into one network per layer, like the web app's "split layers"
        (``alluvial.io.split_layers``). Layers are ordered by layer id, named ``"Layer <k>"`` (or from a JSON
        ``layers`` list), get the ids ``"<network_id>_layer<k>"`` and match their nodes by **physical id**.

    Returns
    -------
    NetworkFile or list of NetworkFile
        A list (one per layer) if ``split_layers`` is true. Pass it on unpacked:
        ``layout([*read(path, split_layers=True)])``.

    Raises
    ------
    ValueError
        For an unsupported file (Infomap input ``.net``, ``.csv``, Newick, JSON that is not Infomap output, a
        saved diagram in the 2019 web-app format), a malformed file, a node whose flow is not a finite number, an
        Infomap object that has not been run, or ``split_layers=True`` on a network that is not a multilayer state
        network.
    TypeError
        For other sources, or an infomap older than 2.14.

    Warns
    -----
    UserWarning
        If several nodes share an identifier (the engine then matches the last one, as in TS; checked per layer
        after a split), if a tree file has node names with a double quote (Infomap writes them unescaped, so the
        id column is misread), or if ``identifier="name"`` is combined with ``split_layers=True``.

    Notes
    -----
    **State networks.** Networks are matched node by node through ``identifier``, exactly as in the web app.

    - ``identifier="id"`` matches *state* nodes by state id. That is right for memory networks whose state ids
      mean the same thing in every network (you assign them in the ``*States`` section or with
      ``add_state_node``). For multilayer networks Infomap assigns the state ids itself, in input order, so the
      same (layer, node) can get different state ids in two runs: do not match multilayer networks by ``"id"``
      unless they were built from identically ordered input.
    - ``identifier="name"`` matches by *physical* node name: Infomap writes the physical name (or the physical id
      when unnamed) for every state node. A physical node with several state nodes then gives duplicate
      identifiers (warned; matching uses the last one).
    - The physical level (``states=False`` or a ``write_tree(states=False)`` file) has one row per physical node
      and module; a node whose state nodes sit in several modules still appears more than once.
    - ``split_layers=True`` shows how one multilayer partition changes across its layers: each layer is a network,
      and its nodes are matched by physical node id (the identifier mode does not apply, as in the web app). A
      non-split network next to the layers matches them only if its identifiers are physical ids too, e.g. a
      first-order ``.tree`` read with ``identifier="id"``.
    """
    if identifier not in ("id", "name"):
        raise ValueError(f"identifier must be 'id' or 'name', got {identifier!r}")
    if split_layers and identifier == "name":
        warnings.warn(
            "identifier='name' is ignored with split_layers=True: split layers always match nodes by physical id, "
            "as in the web app",
            UserWarning,
            stacklevel=user_stacklevel(),
        )
    if isinstance(source, NetworkFile):
        nf = source
        if not split_layers:
            return nf
    elif isinstance(source, (list, tuple)) and all(isinstance(x, (str, os.PathLike)) for x in source):
        # several network files: the files of one saved diagram are sorted into saved order
        if not source:
            raise ValueError("read() got an empty list of paths")
        if name is not None or network_id is not None or split_layers or states is not None:
            raise ValueError(
                "name=, network_id=, states= and split_layers=True do not apply to a list of paths"
            )
        files = [read(path, identifier=identifier) for path in source]
        flat = [nf for item in files for nf in (item if isinstance(item, list) else [item])]
        return sort_by_saved_position(flat)
    elif isinstance(source, (str, os.PathLike)):
        if states is not None:
            raise ValueError("states= applies only to infomap.Infomap sources")
        if Path(source).is_dir():
            if name is not None or network_id is not None or split_layers:
                raise ValueError(
                    "name=, network_id= and split_layers=True do not apply to a directory of networks"
                )
            files = read_dir(source, identifier=identifier)
            for network in files:
                warn_duplicate_identifiers(network)
            return files
        if Path(source).suffix.lower() == ".zip":
            if name is not None or network_id is not None or split_layers:
                raise ValueError("name=, network_id= and split_layers=True do not apply to a zip of networks")
            files = read_zip(source, identifier=identifier)
            for network in files:
                warn_duplicate_identifiers(network)
            return files
        nf = read_file(source, name=name, network_id=network_id, identifier=identifier)
    elif isinstance(source, dict):
        if states is not None:
            raise ValueError("states= applies only to infomap.Infomap sources")
        json_id = source.get("id")
        resolved_name = name if name is not None else _json_name(source, "network")
        nf = from_json_dict(
            source,
            id=network_id
            if network_id is not None
            else (json_id if isinstance(json_id, str) and json_id else resolved_name or "network"),
            name=resolved_name,
            identifier=identifier,
        )
    elif is_infomap(source):
        nf = from_infomap(
            source,
            name="network" if name is None else name,
            network_id=network_id,
            identifier=identifier,
            states=states,
        )
    else:
        raise TypeError(
            f"cannot read a network from {type(source).__name__}; expected a path, an Infomap JSON dict, an "
            "infomap.Infomap or a NetworkFile"
        )
    if split_layers:
        layers = _split_layers(nf)
        for layer in layers:
            warn_duplicate_identifiers(layer)
        return layers
    warn_duplicate_identifiers(nf)
    return nf
