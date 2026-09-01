"""Structural containment checks shared by preview, Confirm, and process runners.

The checks follow no link: callers receive facts established with ``os.lstat``
and decide how their own public boundary phrases a refusal.  Passing proves the
route only at the instant it was read.  It is deliberately not an OS sandbox:
a concurrent component swap (check-then-act) and NTFS alternate data streams
are outside this structural door, while a ``RunStore`` project root is already
resolved from the operator's ``--dir`` choice.
"""
from __future__ import annotations

import os
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

JUNCTION_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)
STORE_OWNED_FILES = frozenset({"run.json", "config.json", "records.jsonl"})
RECEIPTS_DIR, RECEIPT_SUFFIX = "decisions", ".json"


class RouteViolationCode(str, Enum):
    """Closed structural reasons a writable route is not locally contained."""

    SYMLINK = "symlink"
    JUNCTION = "junction"
    REPARSE_POINT = "reparse_point"
    HARD_LINK = "hard_link"
    IRREGULAR_FILE = "irregular_file"
    MISSING = "missing"
    UNREADABLE = "unreadable"
    NOT_DIRECTORY = "not_directory"
    OUTSIDE_ROOT = "outside_root"
    ROOT_NOT_DESCENDANT = "root_not_descendant"
    PARENT_TRAVERSAL = "parent_traversal"


@dataclass(frozen=True)
class RouteViolation:
    """One typed structural fact; public callers never need to parse its rendering."""

    code: RouteViolationCode
    path: Path
    project_root: Path | None = None
    reparse_tag: int | None = None
    link_count: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", RouteViolationCode(self.code))
        object.__setattr__(self, "path", Path(self.path))
        if self.project_root is not None:
            object.__setattr__(self, "project_root", Path(self.project_root))
        if self.code is RouteViolationCode.REPARSE_POINT:
            if (not isinstance(self.reparse_tag, int)
                    or isinstance(self.reparse_tag, bool) or self.reparse_tag == 0):
                raise ValueError("a reparse-point violation requires its non-zero tag")
        elif self.reparse_tag is not None:
            raise ValueError("only a reparse-point violation carries a tag")
        if self.code is RouteViolationCode.HARD_LINK:
            if (not isinstance(self.link_count, int)
                    or isinstance(self.link_count, bool) or self.link_count < 2):
                raise ValueError("a hard-link violation requires a link count above one")
        elif self.link_count is not None:
            raise ValueError("only a hard-link violation carries a link count")
        rooted = {
            RouteViolationCode.OUTSIDE_ROOT,
            RouteViolationCode.ROOT_NOT_DESCENDANT,
            RouteViolationCode.PARENT_TRAVERSAL,
        }
        if (self.code in rooted) != (self.project_root is not None):
            raise ValueError("only cwd authority violations carry the project root")


class StoreRoute(Protocol):
    """The path-only part of RunStore needed by this module."""

    project_root: Path
    runs_root: Path

    def run_path(self, run_id: str) -> Path: ...


def _portal_code(found: os.stat_result) -> RouteViolationCode | None:
    """Classify one lstat result without following the name it describes."""
    if stat.S_ISLNK(found.st_mode):
        return RouteViolationCode.SYMLINK
    tag = getattr(found, "st_reparse_tag", 0)
    if tag == JUNCTION_TAG:
        return RouteViolationCode.JUNCTION
    if tag:
        return RouteViolationCode.REPARSE_POINT
    return None


def portal_violation(path: Path, found: os.stat_result) -> RouteViolation | None:
    """Return a typed portal fact for one lstat result, else ``None``."""
    code = _portal_code(found)
    if code is None:
        return None
    tag = (
        getattr(found, "st_reparse_tag", 0)
        if code is RouteViolationCode.REPARSE_POINT else None)
    return RouteViolation(code=code, path=path, reparse_tag=tag)


def detected_portal(found: os.stat_result) -> str | None:
    """Compatibility rendering for the historical stat-only portal detector."""
    violation = portal_violation(Path("."), found)
    if violation is None:
        return None
    return _portal_name(violation)


def lstat_or_none(path: Path) -> os.stat_result | None:
    """Read one name without following it; ``None`` leaves its state unestablished.

    Absence and an unreadable name are deliberately not guessed apart here.
    Creation/replay owns their diagnostic and must still fail if it cannot act.
    """
    try:
        return os.lstat(path)
    except OSError:
        return None


def _required_lstat(path: Path) -> tuple[os.stat_result | None, RouteViolation | None]:
    """Read a required component, distinguishing absence from unreadability."""
    try:
        return os.lstat(path), None
    except FileNotFoundError:
        return None, RouteViolation(RouteViolationCode.MISSING, path)
    except OSError:
        return None, RouteViolation(RouteViolationCode.UNREADABLE, path)


def _optional_lstat(path: Path) -> tuple[os.stat_result | None, RouteViolation | None]:
    """Read a create-optional name; only inability to judge is a violation."""
    try:
        return os.lstat(path), None
    except FileNotFoundError:
        return None, None
    except OSError:
        return None, RouteViolation(RouteViolationCode.UNREADABLE, path)


def _portal_name(violation: RouteViolation) -> str:
    """Render only the historical human name of a typed portal kind."""
    if violation.code is RouteViolationCode.SYMLINK:
        return "a symbolic link"
    if violation.code is RouteViolationCode.JUNCTION:
        return "a directory junction"
    if violation.code is RouteViolationCode.REPARSE_POINT:
        return f"a reparse point (tag {violation.reparse_tag:#010x})"
    raise ValueError(f"{violation.code.value!r} is not a portal code")


def render_route_violation(violation: RouteViolation) -> str:
    """Render one typed fact with the established CLI wording."""
    path = str(violation.path)
    if violation.code in {
            RouteViolationCode.SYMLINK,
            RouteViolationCode.JUNCTION,
            RouteViolationCode.REPARSE_POINT}:
        return (
            f"route: {path!r} is {_portal_name(violation)}: "
            "a name whose content lies elsewhere")
    if violation.code is RouteViolationCode.HARD_LINK:
        return (
            f"route: {path!r} carries {violation.link_count} hard links: "
            "its bytes stand at another name as well")
    if violation.code is RouteViolationCode.IRREGULAR_FILE:
        return f"route: {path!r} is not a regular file where the store writes one"
    if violation.code in {RouteViolationCode.MISSING, RouteViolationCode.UNREADABLE}:
        return f"route: {path!r} does not exist or cannot be read"
    if violation.code is RouteViolationCode.NOT_DIRECTORY:
        return f"route: {path!r} is not a directory"
    raise ValueError(f"{violation.code.value!r} requires the cwd renderer")


def render_route_violations(violations: Iterable[RouteViolation]) -> tuple[str, ...]:
    """Render typed run-route facts for compatibility with established refusals."""
    return tuple(render_route_violation(violation) for violation in violations)


def render_legacy_run_route_violations(
        violations: Iterable[RouteViolation], run_path: Path) -> tuple[str, ...]:
    """Preserve the old store-owned timing for typed non-file objects.

    The typed API sees a non-directory route component and a non-regular receipt.
    Existing command callers continue to let their create/replay operation own
    those refusals, as before ROUTE-1.
    """
    receipts = run_path / RECEIPTS_DIR
    return render_route_violations(
        row for row in violations
        if row.code is not RouteViolationCode.NOT_DIRECTORY
        and not (
            row.code is RouteViolationCode.IRREGULAR_FILE
            and row.path.parent == receipts
            and row.path.suffix == RECEIPT_SUFFIX))


def first_directory_violation(paths: Iterable[Path]) -> RouteViolation | None:
    """Find the first unreadable, non-directory, or portal route component.

    A missing component remains admissible because create_run may own its
    creation. An existing component whose structure cannot be established is
    never guessed safe and the walk stops before looking below it.
    """
    route = tuple(paths)
    for path in route:
        found, failure = _optional_lstat(path)
        if failure is not None:
            return failure
        if found is None:
            continue
        violation = portal_violation(path, found)
        if violation is not None:
            return violation
        if not stat.S_ISDIR(found.st_mode):
            return RouteViolation(RouteViolationCode.NOT_DIRECTORY, path)
    return None


def owned_file_violations(run_path: Path) -> tuple[RouteViolation, ...]:
    """Judge every present store-owned file as regular, local, and singly named.

    A second hard link makes the same bytes reachable through a name outside the
    inspected tree.  Writing or publishing at the owned name can then affect, or
    replace only one view of, state the caller cannot account for.  The relation
    is uniform over the three top-level files and receipt-shaped decision files.
    """
    receipts = run_path / RECEIPTS_DIR
    try:
        entries = sorted(receipts.iterdir())
    except FileNotFoundError:
        entries = []
    except OSError:
        return (RouteViolation(RouteViolationCode.UNREADABLE, receipts),)
    violations: list[RouteViolation] = []
    paths = (*(run_path / name for name in sorted(STORE_OWNED_FILES)), *entries)
    for path in paths:
        found, failure = _optional_lstat(path)
        if failure is not None:
            violations.append(failure)
            continue
        if found is None:
            continue
        portal = portal_violation(path, found)
        if portal is not None:
            violations.append(portal)
            continue
        if path.parent == receipts and path.suffix != RECEIPT_SUFFIX:
            continue
        if not stat.S_ISREG(found.st_mode):
            violations.append(RouteViolation(RouteViolationCode.IRREGULAR_FILE, path))
        elif found.st_nlink != 1:
            violations.append(RouteViolation(
                RouteViolationCode.HARD_LINK, path, link_count=found.st_nlink))
    return tuple(violations)


def run_route_violations(store: StoreRoute, run_id: str) -> tuple[RouteViolation, ...]:
    """Inspect the structural route; an empty result is not run authorization.

    A caller must still create or replay the run through ``RunStore``. Legacy
    command callers render selected typed facts through their compatibility
    boundary so the existing store refusal remains authoritative.
    """
    run_path = store.run_path(run_id)
    first = first_directory_violation((
        store.project_root / "conductor", store.runs_root, run_path,
    ))
    if first is None:
        found, failure = _optional_lstat(run_path)
        if failure is not None:
            return (failure,)
        if found is not None and stat.S_ISDIR(found.st_mode):
            first = first_directory_violation((run_path / RECEIPTS_DIR,))
    return (first,) if first is not None else owned_file_violations(run_path)


def unowned_paths(run_path: Path, *, all_reparse: bool = False) -> tuple[str, ...]:
    """Name objects below a run that RunStore neither reads nor writes.

    Plain empty directories carry no bytes and remain admissible.  Portals are
    named by their local entry and never traversed; receipt-shaped files are
    owned only directly beneath ``decisions``.
    """
    receipts = run_path / RECEIPTS_DIR
    unowned: list[str] = []
    stack = [run_path]
    while stack:
        entries = sorted(stack.pop().iterdir())
        for path in entries:
            found = lstat_or_none(path)
            if found is None:
                raise OSError(f"cannot lstat run object {str(path)!r}")
            name = path.relative_to(run_path).as_posix()
            tag = getattr(found, "st_reparse_tag", 0)
            is_portal = stat.S_ISLNK(found.st_mode) or tag == JUNCTION_TAG
            if is_portal or (all_reparse and tag):
                unowned.append(name)
            elif stat.S_ISDIR(found.st_mode):
                stack.append(path)
            elif path.parent == run_path and path.name in STORE_OWNED_FILES:
                continue
            elif (path.parent == receipts and path.suffix == RECEIPT_SUFFIX
                  and stat.S_ISREG(found.st_mode)):
                continue
            else:
                unowned.append(name)
    return tuple(sorted(unowned))


def _walk_directory_route(
        root: Path, relative: Path) -> tuple[Path, RouteViolation | None]:
    """Walk a known-relative route without following components."""
    walked = root
    for part in relative.parts:
        walked = walked / part
        found, failure = _required_lstat(walked)
        if failure is not None:
            return walked, failure
        assert found is not None
        portal = portal_violation(walked, found)
        if portal is not None:
            return walked, portal
        if not stat.S_ISDIR(found.st_mode):
            return walked, RouteViolation(RouteViolationCode.NOT_DIRECTORY, walked)
    return walked, None


def assess_cwd_route(
        root: Path, raw_cwd: str | os.PathLike[str]) -> tuple[Path, RouteViolation | None]:
    """Assess a cwd as a strict descendant of an already-resolved authority root."""
    candidate = Path(raw_cwd)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return candidate, RouteViolation(
            RouteViolationCode.OUTSIDE_ROOT, candidate, project_root=root)
    if not relative.parts:
        return candidate, RouteViolation(
            RouteViolationCode.ROOT_NOT_DESCENDANT, candidate, project_root=root)
    if os.pardir in relative.parts:
        return candidate, RouteViolation(
            RouteViolationCode.PARENT_TRAVERSAL, candidate, project_root=root)
    return _walk_directory_route(root, relative)


def render_cwd_violation(violation: RouteViolation) -> str:
    """Render one cwd assessment with the runner's established public wording."""
    path = str(violation.path)
    root = str(violation.project_root) if violation.project_root is not None else None
    if violation.code is RouteViolationCode.OUTSIDE_ROOT:
        return f"cwd {path!r} is not beneath the project root {root!r}"
    if violation.code is RouteViolationCode.ROOT_NOT_DESCENDANT:
        return (
            "cwd must be strictly beneath the project root, not the root itself: "
            f"{root!r}")
    if violation.code is RouteViolationCode.PARENT_TRAVERSAL:
        return f"cwd {path!r} escapes the project root through '..'"
    fact = render_route_violation(violation).removeprefix("route: ")
    return f"cwd route component {fact}"


def contained_directory(root: Path, relative: Path) -> tuple[Path, str | None]:
    """Compatibility wrapper returning the historical rendered route fact.

    ``root`` is the caller's already-resolved authority root.  ``relative`` must
    contain only a strict descendant route; no component is resolved or followed.
    """
    walked, violation = _walk_directory_route(root, relative)
    rendered = render_route_violation(violation) if violation is not None else None
    return walked, rendered


# -- what a PLAN may demand of the route its work runs on ---------------------

#: The sandbox routes this build can actually provide, and there is one.
#:
#: A `sandbox` resource on a step is a DEMAND the plan makes of whatever machine
#: runs it. Until this vocabulary existed the demand was recorded and spent by
#: nobody, so a plan could name any route-shaped word and the run would proceed
#: exactly as if it had named none -- which is the lie this closes.
#:
#: `project-root` names the boundary the walk above is ANCHORED to, and not the
#: directory a child stands in. The child's cwd is `work/<work_item_id>`, chosen
#: from the capability's own argument; what `project-root` promises is that this
#: route is walked from the project root with `os.lstat` and refused if it
#: leaves -- a symlink, a junction, a reparse point, a hard link, a `..`
#: segment, or anything not strictly beneath it. That promise is what
#: `assess_cwd_route` already enforces on every spawn, and naming it is how a
#: plan says it wants it.
#:
#: It is NOT an operating-system sandbox, and this module's own docstring says
#: why: the walk establishes facts with `os.lstat` at the instant it reads them,
#: so a concurrent component swap and NTFS alternate data streams are outside
#: it. There is no privilege drop and no filesystem jail anywhere in this build.
#: A word added here must name a route this product really provides.
SANDBOX_ROUTES = frozenset({"project-root"})

#: The one resource kind this build spends. The other five are recorded on the
#: step, materialized into a run's plan, and consumed by nothing -- which is a
#: true and deliberately narrow claim, held by a census test rather than by this
#: comment. Only THIS kind is judged against a closed vocabulary; a `model`,
#: `tool`, `skill`, `session` or `filesystem` row may name anything id-shaped
#: and is refused by nobody, because refusing a name this build has no
#: behaviour for would be inventing a promise about it.
SANDBOX_KIND = "sandbox"


def unprovidable_sandboxes(resources: Iterable[object]) -> tuple[str, ...]:
    """The sandbox routes one step demands that this build cannot provide.

    A pure reading over a step's declared attachments, in the order the step
    declared them. Rows of every other kind are passed over -- see
    `SANDBOX_KIND` -- and so is a row whose shape this function cannot read,
    because the node contract already refused those at the door and a second
    opinion here could only disagree with it.

    Args:
        resources: One step's `GraphResource` rows.

    Returns:
        Each demanded route this build does not provide, first mention only.
    """
    found: list[str] = []
    for row in resources:
        kind = getattr(row, "kind", None)
        name = getattr(row, "name", None)
        if kind != SANDBOX_KIND or type(name) is not str:
            continue
        if name not in SANDBOX_ROUTES and name not in found:
            found.append(name)
    return tuple(found)
