"""Pure new-work admission, separate from durable grammar and exact repeats.

Callers already hold the frozen registry schema and the actual store root. The
production factory builds its provider workspaces with this same project root;
transports repeat the check against their own workspace before any effect.
No mutable adapter callback, lookup of credentials, filesystem access or spawn.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .path_admission import admit_work_path
from .work_layout import work_parts


def admit_new_work(root: Path, schema: str | None, capability: str,
                   arguments: Mapping[str, Any]) -> None:
    """Consume registry-validated fields from the registered deep family.

    Both service and plan callers validate the entire frozen argument schema
    before this check. This is new-write admission, not a second schema parser;
    importing the adapter package here would make the core depend on its eager
    transport imports and reintroduce the store initialisation cycle.
    """
    if schema != "deep-arguments-v1" or capability not in ("dispatch", "review"):
        return
    item, scope = arguments["work_item_id"], arguments.get("work_scope")
    path = root.joinpath(*work_parts(item, scope))
    admit_work_path(path, item, scope)
