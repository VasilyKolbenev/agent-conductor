"""The partition of the panel directory over studio*, desk* and hub* files.

The Studio's guards used to hold one prefix of the packaged directory to one
list. The desk and the hub page arrive beside it, and each has its own registry
of the files that are SERVED: `DESK_ASSETS` (the project server, in
`conductor/server_assets.py`) and `HUB_ASSETS` (the hub, in
`conductor/hub/assets.py`, written by another lane). This module is the one
statement of how the three relate, as pure functions over name sets, so the same
relation is asserted over the real directory in `test_studio_source.py` and
over synthetic trees in `test_desk_source.py`.

The hub registry does not exist until its lane writes it, and the partition has
to accept it the day it appears without an edit here. The rule is narrow on
purpose: exactly one failure reads as "not written yet" -- the import of
`conductor.hub.assets` (or of its parent package) not being found. While it is
absent, no `hub*` file may be packaged, so a hub page cannot arrive with no
registry to account for it. Once the module exists, `HUB_ASSETS` is read as a
mapping shaped like `PANEL_ASSETS` (`route -> (content_type, name)`); a module
that exists without it, or with another shape, fails loudly rather than being
skipped.

The hub's entry page is the one `hub*` file that is not a registry row. Spec
4.6.3 has `GET /` answer `hub.html` and `/hub/<name>` answer only `HUB_ASSETS`,
which is the import closure of `hub.js`, and a page nothing imports is not in a
closure. It is the same arrangement as `ENTRY_PAGE` beside `PANEL_ASSETS` on
the project server, so the partition gives it a slot of its own: once the
registry exists the entry page must be packaged and must not be a row.
"""
from __future__ import annotations

import importlib
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Callable

#: The files the desk and the hub page share (spec 4.1.10). Each is a `desk*`
#: file, so the desk registry accounts for it, and each is served by the hub too.
SHARED_MODULES = frozenset({"desk-hash.js", "desk-status.js", "desk-status-copy.js",
                            "desk-time.js"})
PREFIXES = ("studio", "desk", "hub")
SUFFIXES = (".js", ".css", ".html")
HUB_REGISTRY_MODULE = "conductor.hub.assets"
#: The document the hub answers `GET /` with (spec 4.6.3): packaged, and never a
#: `HUB_ASSETS` row.
HUB_ENTRY_PAGE = "hub.html"


def packaged_names(panel: Path) -> frozenset[str]:
    """Every studio*, desk* or hub* page file in `panel`, by name.

    Args:
        panel: The packaged `panel/` directory.

    Returns:
        The names of the files with a `.js`, `.css` or `.html` suffix.
    """
    return frozenset(entry.name for entry in panel.iterdir()
                     if entry.name.startswith(PREFIXES) and entry.name.endswith(SUFFIXES))


def hub_registry_names(
        importer: Callable[[str], ModuleType] = importlib.import_module,
) -> frozenset[str] | None:
    """The names `HUB_ASSETS` serves, or None while that registry is not written.

    Args:
        importer: How the registry module is imported; a test hands its own.

    Returns:
        The packaged names of the registry's rows, or None when the registry
        module (or the package holding it) does not exist yet.

    Raises:
        ModuleNotFoundError: The registry module imports something that is missing.
        AttributeError: The module exists and carries no `HUB_ASSETS`.
        AssertionError: `HUB_ASSETS` is not shaped like `PANEL_ASSETS`.
    """
    try:
        module = importer(HUB_REGISTRY_MODULE)
    except ModuleNotFoundError as error:
        if error.name not in ("conductor.hub", HUB_REGISTRY_MODULE):
            raise
        return None
    registry = module.HUB_ASSETS
    assert isinstance(registry, Mapping) and all(
        isinstance(row, tuple) and len(row) == 2 for row in registry.values()), (
        "HUB_ASSETS must map route -> (content_type, name), like PANEL_ASSETS")
    return frozenset(name for _, name in registry.values())


def _entry_page_faults(packaged: frozenset[str], hub: frozenset[str]) -> list[str]:
    faults = []
    if HUB_ENTRY_PAGE not in packaged:
        faults.append(f"hub entry page not packaged: {HUB_ENTRY_PAGE}")
    if HUB_ENTRY_PAGE in hub:
        faults.append(f"hub entry page listed in HUB_ASSETS: {HUB_ENTRY_PAGE}")
    return faults


def _hub_faults(packaged: frozenset[str], hub: frozenset[str] | None) -> list[str]:
    hub_files = {name for name in packaged if name.startswith("hub")}
    if hub is None:
        return [f"hub file packaged while no hub registry exists: {name}"
                for name in sorted(hub_files)]
    faults = [f"hub file in no HUB_ASSETS row: {name}"
              for name in sorted(hub_files - hub - {HUB_ENTRY_PAGE})]
    faults += [f"HUB_ASSETS row names no packaged file: {name}"
               for name in sorted(hub - packaged)]
    faults += [f"HUB_ASSETS row is neither a hub file nor a shared module: {name}"
               for name in sorted(hub)
               if not name.startswith("hub") and name not in SHARED_MODULES]
    faults += [f"shared module missing from HUB_ASSETS: {name}"
               for name in sorted((SHARED_MODULES & packaged) - hub)]
    return faults + _entry_page_faults(packaged, hub)


def partition_faults(*, packaged: frozenset[str], modules: frozenset[str],
                     desk: frozenset[str], hub: frozenset[str] | None) -> list[str]:
    """Every file or registry row the partition cannot account for.

    Args:
        packaged: Output of `packaged_names`.
        modules: The js modules the source guards iterate (`MODULES`).
        desk: The packaged names `DESK_ASSETS` serves.
        hub: The packaged names `HUB_ASSETS` serves; None while it is unwritten.

    Returns:
        One sentence per fault; empty when every file is accounted for.
    """
    scripts = {name for name in packaged
               if name.endswith(".js") and name.startswith(("studio", "desk"))}
    desk_files = {name for name in packaged if name.startswith("desk")}
    faults = [f"js module guarded by no MODULES row: {name}"
              for name in sorted(scripts - modules)]
    faults += [f"MODULES names no packaged file: {name}"
               for name in sorted(modules - packaged)]
    faults += [f"desk file in no DESK_ASSETS row: {name}"
               for name in sorted(desk_files - desk)]
    faults += [f"DESK_ASSETS row names no packaged file: {name}"
               for name in sorted(desk - packaged)]
    faults += [f"hub file in DESK_ASSETS: {name}"
               for name in sorted(name for name in desk if name.startswith("hub"))]
    return faults + _hub_faults(packaged, hub)
