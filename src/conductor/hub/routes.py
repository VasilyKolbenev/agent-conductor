"""`HUB_ROUTES`: the one table of the hub's paths (spec 4.6.3), and the reader of a target.

Every row is a method, a path template, the exact key sets a body may have and the refusals the row
names (the transport refusals act on all rows and are not repeated). A path that no row names is
`route_not_found`, a path a row names under another method is `method_not_allowed`, and a path
parameter outside its grammar names no route at all. There is no query: a target with one is not a
route. `GET /hub/<name>` is the only row with no fixed path: it is a route only for a name the
literal allowlist `HUB_ASSETS` holds.

This module touches no store, no socket and no clock: it decides WHICH route a request names.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import NamedTuple

from conductor.hub.assets import HUB_ASSETS
from conductor.hub.refusals import HubRefusal

#: The grammar of each path parameter (4.6.3). `login_key` is a login, not a harness name (L27).
PARAM_GRAMMAR: Mapping[str, str] = MappingProxyType({
    "project_id": r"[0-9a-f]{32}",
    "operation_id": r"operation-[0-9a-f]{32}",
    "pick_id": r"pick-[0-9a-f]{32}",
    "login_key": r"[0-9a-f]{64}",
    "tool": r"gh|git",
    "owner": r"[A-Za-z0-9-]{1,39}",
})
#: Keys that name a place on disk: refused at any depth before the route is judged (L5).
FORBIDDEN_KEYS = frozenset({"root", "path", "dir"})
ASSET_PATH = "/hub/<name>"
_EMPTY: frozenset[str] = frozenset()


class HubRoute(NamedTuple):
    """One row: `bodies` are the exact key sets a body may have (none for a GET)."""

    method: str
    path: str
    bodies: tuple[frozenset[str], ...]
    refusals: tuple[str, ...]


def _row(method: str, path: str, bodies: Iterable[Iterable[str]] = (),
         refusals: tuple[str, ...] = ()) -> HubRoute:
    return HubRoute(method, path, tuple(frozenset(keys) for keys in bodies), refusals)


_GH = ("gh_not_pinned", "gh_changed", "gh_not_logged_in", "gh_unreachable", "gh_failed")
_NONE = ((),)
HUB_ROUTES: tuple[HubRoute, ...] = (
    _row("GET", "/"),
    _row("GET", ASSET_PATH, refusals=("route_not_found",)),
    _row("GET", "/hub/session"),
    _row("GET", "/hub/events"),
    _row("GET", "/hub/projects"),
    _row("GET", "/hub/limits"),
    _row("GET", "/hub/setup"),
    _row("GET", "/hub/operations/<operation_id>", refusals=("operation_not_found",)),
    _row("GET", "/hub/dialogs/<pick_id>", refusals=("pick_not_found",)),
    _row("GET", "/hub/github/status"),
    _row("GET", "/hub/github/repos", refusals=_GH),
    _row("GET", "/hub/github/repos/<owner>", refusals=_GH),
    _row("POST", "/hub/dialogs/folder", [("purpose",)], ("dialog_busy", "dialog_unavailable")),
    _row("POST", "/hub/dialogs/<pick_id>/cancel", _NONE, ("pick_not_found",)),
    _row("POST", "/hub/projects",
         [("source", "pick_id", "name", "legacy_writers_stopped"),
          ("source", "repo", "folder", "name"), ("source", "folder", "name")],
         ("name_invalid", "folder_invalid", "windows_name_unsafe", "repo_invalid", "pick_invalid",
          "legacy_writers_unconfirmed", "folder_exists", "projects_home_invalid",
          "git_not_pinned", "git_changed", "gh_not_pinned", "gh_changed",
          "review_harness_missing", "operation_busy", "registry_busy", "registry_invalid")),
    _row("POST", "/hub/setup/projects-home", [("pick_id",), ("default",)],
         ("pick_invalid", "projects_home_invalid", "windows_path_too_long")),
    _row("POST", "/hub/tools/<tool>/pin", [("candidate_id",)],
         ("candidate_not_found", "git_changed", "gh_changed", "git_too_old",
          "tool_version_unreadable")),
    _row("POST", "/hub/projects/<project_id>/activate", _NONE,
         ("project_not_found", "already_active", "active_not_closed", "project_unavailable",
          "recovery_required", "project_busy", "hub_in_kill_on_close_job")),
    _row("POST", "/hub/projects/<project_id>/view", _NONE,
         ("project_not_found", "already_active", "project_running", "project_unavailable",
          "recovery_required", "project_busy", "hub_in_kill_on_close_job")),
    _row("POST", "/hub/projects/<project_id>/stop", _NONE,
         ("project_not_found", "project_not_running", "project_busy")),
    _row("POST", "/hub/projects/<project_id>/recover", _NONE,
         ("project_not_found", "project_running", "recover_not_needed", "project_busy")),
    _row("POST", "/hub/projects/<project_id>/providers", _NONE,
         ("project_not_found", "profile_absent", "profile_invalid", "project_busy")),
    _row("POST", "/hub/projects/<project_id>/forget", _NONE,
         ("project_not_found", "project_running")),
    _row("POST", "/hub/logins/<login_key>/recover", _NONE,
         ("login_not_found", "recover_not_needed")),
    _row("POST", "/hub/operations/<operation_id>/cancel", _NONE,
         ("operation_not_found", "operation_not_cancellable")),
    _row("POST", "/hub/queue/order", [("order",)], ("project_queue_changed",)),
)


@dataclass(frozen=True)
class Matched:
    """The row a request names and the path parameters read from its target."""

    route: HubRoute
    params: Mapping[str, str]


def _pattern(path: str) -> re.Pattern[str]:
    parts = re.split(r"<([a-z_]+)>", path)
    literal = "".join(
        re.escape(part) if number % 2 == 0 else f"(?P<{part}>{PARAM_GRAMMAR[part]})"
        for number, part in enumerate(parts))
    return re.compile(literal)


_PATTERNS = {row.path: _pattern(row.path) for row in HUB_ROUTES if row.path != ASSET_PATH}


def _params(row: HubRoute, target: str) -> dict[str, str] | None:
    if row.path == ASSET_PATH:
        return {"name": target[len("/hub/"):]} if target in HUB_ASSETS else None
    found = _PATTERNS[row.path].fullmatch(target)
    return None if found is None else found.groupdict()


def match(method: str, target: str) -> Matched:
    """The row a method and a target name.

    Args:
        method: The HTTP method, as sent.
        target: The request target, path and (refused) query as sent.

    Raises:
        HubRefusal: `route_not_found` (no row names the path, a parameter is outside its
            grammar, or the target has a query or a fragment) or `method_not_allowed` (a row
            names the path, under other methods only).
    """
    if not isinstance(target, str) or "?" in target or "#" in target:
        raise HubRefusal("route_not_found")
    named = [(row, found) for row in HUB_ROUTES
             if (found := _params(row, target)) is not None]
    if not named:
        raise HubRefusal("route_not_found")
    for row, found in named:
        if row.method == method:
            return Matched(row, MappingProxyType(found))
    raise HubRefusal("method_not_allowed")


def _names_a_place(value: object) -> bool:
    if isinstance(value, dict):
        return any(key in FORBIDDEN_KEYS or _names_a_place(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_names_a_place(item) for item in value)
    return False


def check_body(row: HubRoute, body: Mapping[str, object]) -> frozenset[str]:
    """Hold a decoded body to the key sets of its row; return the key set it matched.

    A key that names a place on disk (`root`, `path`, `dir`) at any depth is refused first, as the
    spec orders (L5); then the keys must be exactly one of the row's sets (L6).

    Raises:
        HubRefusal: `contract_invalid`.
    """
    if _names_a_place(body):
        raise HubRefusal("contract_invalid", {"reason": "a place on disk"})
    keys = frozenset(body)
    if keys not in (set(row.bodies) or {_EMPTY}):
        raise HubRefusal("contract_invalid", {"reason": "the keys of the body"})
    return keys
