"""The command surface's allowlist, and the only function that reads a target.

Split out of ``http_api`` when that module reached its line cap, along the seam
the two already had: everything here decides WHICH route a request names, and
nothing here knows what any of them does. It touches no store, no registry, no
clock and no session, so a reader asking "what paths exist" reads one file, and
a reader asking "what happens on this one" never has to walk past the table.

The table is an allowlist and not a pattern. A path that no row names is
``route_not_found``; a path a row names under another method is
``method_not_allowed``; and the two are told apart before either is answered, so
a probe cannot learn which routes exist by watching the refusal change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .api_contracts import ApiRefusal
from .task_contracts import MAX_TASK_ID

#: Every route this build serves, method and path, in one place. The panel, the
#: spec's canonical table and the freeze tests all read this tuple, so a route
#: that is not written here is a route that does not exist.
COMMAND_ROUTES = (
    ("GET", "/command/session"),
    ("GET", "/command/runs/<run_id>"),
    ("GET", "/command/runs/<run_id>/controls"),
    ("POST", "/command/runs/<run_id>/proposals"),
    ("POST", "/command/runs/<run_id>/actions"),
    ("POST", "/command/runs/<run_id>/decisions"),
    ("POST", "/command/runs/<run_id>/graph"),
    ("POST", "/command/templates"),
    ("POST", "/command/runs/<run_id>/graph/from-template"),
    ("POST", "/command/runs/<run_id>/artifacts"),
    ("GET", "/command/workflows"),
    ("GET", "/command/workflows/<workflow_id>"),
    ("GET", "/command/workflows/<workflow_id>/revisions/<revision>"),
    ("POST", "/command/workflows/<workflow_id>/draft"),
    ("POST", "/command/workflows/<workflow_id>/revisions"),
    ("GET", "/command/runs"),
    ("POST", "/command/runs"),
    ("GET", "/command/tasks"),
    ("POST", "/command/tasks"),
    ("GET", "/command/tasks/<task_id>"),
    ("GET", "/command/quotas"),
    ("GET", "/command/runs/<run_id>/automation"),
    ("POST", "/command/runs/<run_id>/automation/preview"),
    ("POST", "/command/runs/<run_id>/automation/authorize"),
    ("POST", "/command/runs/<run_id>/automation/control"),
)

_RUN_ROUTE = re.compile(
    r"/command/runs/([A-Za-z0-9][A-Za-z0-9._-]{0,127})"
    # The longer tail is spelled FIRST: alternation is leftmost-first, and a
    # `graph` that matched before `graph/from-template` would send every
    # materialization to the route that speaks a different document.
    r"(?:/(automation/preview|automation/authorize|automation/control|automation|controls|proposals|actions|decisions|graph/from-template|artifacts|graph))?\Z")
_WORKFLOW_ROUTE = re.compile(
    r"/command/workflows/(?P<workflow_id>[A-Za-z0-9][A-Za-z0-9._-]{0,127})"
    # The revision number is a tail of the `revisions` tail rather than a fourth
    # alternative, for `_RUN_ROUTE`'s reason one level down: alternation is
    # leftmost-first, so `revisions` spelled beside `revisions/<n>` would swallow
    # every read of one revision into the route that publishes them. Spelled
    # this way there is nothing to order -- the number is either there or it is
    # not, and the tail it belongs to is decided by name.
    r"(?:/(?P<tail>draft|revisions)(?:/(?P<revision>[0-9]{1,9}))?)?\Z")
#: A task id is bounded at `MAX_TASK_ID`, and this grammar admits exactly the
#: names the task store can address -- as `_RUN_ROUTE` admits exactly what
#: `run_path` admits -- so a name past the bound is a path no row names rather
#: than a task the store is then asked about and cannot hold.
_TASK_ROUTE = re.compile(
    rf"/command/tasks/([A-Za-z0-9][A-Za-z0-9._-]{{0,{MAX_TASK_ID - 1}}})\Z")
_SESSION_PATH = "/command/session"
_QUOTAS_PATH = "/command/quotas"
_WORKFLOWS_PATH = "/command/workflows"
#: The one run route that names no run: the list, and the door that opens one.
_RUNS_PATH = "/command/runs"
#: The task route that names no task, under both verbs for the run list's
#: reason: listing tasks and creating one are the same noun asked two ways.
_TASKS_PATH = "/command/tasks"
#: The one command route that belongs to no run. A template outlives the run
#: that first materialized it, so a run id in its path would be a lie about
#: what it is.
_TEMPLATES_PATH = "/command/templates"


@dataclass(frozen=True)
class Route:
    """One named route, plus whichever identities its path carried."""

    name: str
    run_id: str | None = None
    workflow_id: str | None = None
    revision: int | None = None
    task_id: str | None = None


def target_path(target: str) -> str:
    """Accept an exact origin-form path; command routes have no query surface."""
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ApiRefusal.fixed("route_not_found")
    return parsed.path


def match_route(method: str, path: str) -> Route:
    """Name the one route this method and path reach, or refuse which way it failed.

    Args:
        method: The request method, verbatim.
        path: An origin-form path, already stripped of query and fragment by
            :func:`target_path`.

    Returns:
        The named route, carrying the run, workflow, revision and task its
        path spelled.

    Raises:
        ApiRefusal: ``route_not_found`` when no row names the path at all;
            ``method_not_allowed`` when a row names it under another method.
    """
    if method not in {"GET", "POST"}:
        raise ApiRefusal.fixed(
            "method_not_allowed" if _known(path) else "route_not_found")
    if path in {_SESSION_PATH, _QUOTAS_PATH}:
        if method != "GET":
            raise ApiRefusal.fixed("method_not_allowed")
        return Route("session" if path == _SESSION_PATH else "quotas")
    if path == _TEMPLATES_PATH:
        if method != "POST":
            raise ApiRefusal.fixed("method_not_allowed")
        return Route("templates")
    if path == _WORKFLOWS_PATH:
        if method != "GET":
            raise ApiRefusal.fixed("method_not_allowed")
        return Route("workflows")
    if path == _RUNS_PATH:
        # The one path this table admits under BOTH methods, because listing
        # runs and opening one are the same noun asked two ways.
        return Route("runs")
    task = _task_route(method, path)
    if task is not None:
        return task
    workflow = _WORKFLOW_ROUTE.fullmatch(path)
    if workflow is not None:
        return _workflow_route(method, workflow)
    matched = _RUN_ROUTE.fullmatch(path)
    if matched is None:
        raise ApiRefusal.fixed("route_not_found")
    run_id, tail = matched.groups()
    name = (tail or "run").replace("/", "_").replace("-", "_")
    expected = "GET" if name in {"run", "controls", "automation"} else "POST"
    if method != expected:
        raise ApiRefusal.fixed("method_not_allowed")
    return Route(name, run_id)


def _known(path: str) -> bool:
    """Whether some row names this path under any method at all."""
    return (path in {_SESSION_PATH, _QUOTAS_PATH, _TEMPLATES_PATH, _WORKFLOWS_PATH,
                     _RUNS_PATH, _TASKS_PATH}
            or _RUN_ROUTE.fullmatch(path) is not None
            or _WORKFLOW_ROUTE.fullmatch(path) is not None
            or _TASK_ROUTE.fullmatch(path) is not None)


def _task_route(method: str, path: str) -> Route | None:
    """Name one of the three task routes, or ``None`` when the path is not one.

    ``/command/tasks`` is the second path the table admits under BOTH verbs,
    for the run list's reason. The read of one task is GET only, and a name
    past the task bound matched nothing above, so it is no route at all.
    """
    if path == _TASKS_PATH:
        return Route("tasks")
    matched = _TASK_ROUTE.fullmatch(path)
    if matched is None:
        return None
    if method != "GET":
        raise ApiRefusal.fixed("method_not_allowed")
    return Route("task", task_id=matched.group(1))


def _workflow_route(method: str, matched: "re.Match[str]") -> Route:
    """Name one of the four workflow routes, or refuse the shape outright.

    A tail that carries a number it has no use for is a path this table does not
    contain, not a path with an ignored suffix: `.../draft/3` would otherwise be
    answered as `.../draft`, which is a route the allowlist never advertised.
    """
    workflow_id = matched.group("workflow_id")
    tail, revision = matched.group("tail"), matched.group("revision")
    if tail is None:
        expected, name = "GET", "workflow"
    elif tail == "draft":
        if revision is not None:
            raise ApiRefusal.fixed("route_not_found")
        expected, name = "POST", "workflow_draft"
    elif revision is None:
        expected, name = "POST", "workflow_revisions"
    else:
        expected, name = "GET", "workflow_revision"
    if method != expected:
        raise ApiRefusal.fixed("method_not_allowed")
    if name != "workflow_revision":
        return Route(name, workflow_id=workflow_id)
    # A revision is a counting number and the grammar above already refused a
    # sign, a decimal point and anything wider than nine digits; a leading zero
    # is a second spelling of one number and is refused here.
    if revision != str(int(revision)):
        raise ApiRefusal.fixed("route_not_found")
    number = int(revision)
    if number < 1:
        raise ApiRefusal.fixed("route_not_found")
    return Route(name, workflow_id=workflow_id, revision=number)
