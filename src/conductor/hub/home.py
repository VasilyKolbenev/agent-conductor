"""Where the hub's folder is, that it exists, and where it may be: `<conduct-home>` (spec 4.1.2).

The folder is `~/.december-command` on every OS, and `CONDUCT_HOME` may replace it with an
ABSOLUTE path; a relative or empty override is refused instead of being resolved against the
working folder of whichever process reads it. `conduct_home_path` only computes the path and
creates nothing, so a child can judge `--status-file` against it before it does any IO;
`conduct_home` makes the folder. `require_placement` is the two rules of where it may lie:
not inside a project that is activated (or one it has become itself), and not inside a login
folder.
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

HOME_FOLDER = ".december-command"
OVERRIDE = "CONDUCT_HOME"
#: The names that make a folder a project: an activated one holds either (ownership_records).
PROJECT_MARKERS = (".conduct", "conductor.v3")


class ConductHomeInvalid(ValueError):
    """The folder the hub would use cannot be used: the override is not absolute, or it lies
    inside a project. The text says which."""

    code = "conduct_home_invalid"


class ConductHomeOverlapsLogin(ValueError):
    """A login folder is the hub's folder or one of its parents."""

    code = "conduct_home_overlaps_login"


def conduct_home_path() -> Path:
    """The folder the hub keeps its files in, without creating it.

    Returns:
        `CONDUCT_HOME` when it names an absolute path, else `~/.december-command`.

    Raises:
        ConductHomeInvalid: `CONDUCT_HOME` is set to a relative or empty path.
    """
    override = os.environ.get(OVERRIDE)
    if override is None:
        return Path.home() / HOME_FOLDER
    if not override or not os.path.isabs(override):
        raise ConductHomeInvalid(f"{OVERRIDE} must be an absolute path, not {override!r}")
    return Path(override)


def conduct_home() -> Path:
    """The hub's folder, made when it is not there yet.

    A new folder is private to the user where the OS has modes (0700); one that already
    exists is left exactly as it is, content and mode included.

    Returns:
        The path of the folder.

    Raises:
        ConductHomeInvalid: `CONDUCT_HOME` is set to a relative or empty path; nothing is made.
        OSError: The folder could not be made.
    """
    folder = conduct_home_path()
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder


def require_placement(folder: Path, login_homes: Iterable[Path | str] = ()) -> Path:
    """Judge where the hub's folder lies, before the hub puts anything in it (rules 1 and 2).

    Args:
        folder: The hub's folder; it need not exist yet.
        login_homes: The `auth_home` folders of the profile and of the registered projects.

    Returns:
        `folder`, when both rules allow it.

    Raises:
        ConductHomeInvalid: Rule 1. The folder, or a parent of it, holds `.conduct` or
            `conductor.v3`: it lies inside a project, or has become one, so the files of the
            hub would lie in a project's tree and `provider_write_guard` would refuse the
            profile. The text names the project folder and the marker.
        ConductHomeOverlapsLogin: Rule 2. A login folder is the hub's folder or one of its
            parents (a login folder the hub's folder lies beneath).
        ValueError: A login folder is not an absolute path; that is a fault of the caller.
    """
    resolved = folder.resolve()
    _refuse_a_project(resolved)
    for login in login_homes:
        _refuse_an_overlapping_login(resolved, login)
    return folder


def _refuse_a_project(resolved: Path) -> None:
    for place in (resolved, *resolved.parents):
        for marker in PROJECT_MARKERS:
            if os.path.lexists(place / marker):
                raise ConductHomeInvalid(
                    f"{resolved} lies inside the project {place}, which holds {marker}: the "
                    "hub's folder must be outside every project")


def _refuse_an_overlapping_login(resolved: Path, login: Path | str) -> None:
    if not os.path.isabs(login):
        raise ValueError(f"a login folder must be an absolute path, not {str(login)!r}")
    found = Path(login).resolve()
    same = os.path.normcase(str(found))
    if same in {os.path.normcase(str(place)) for place in (resolved, *resolved.parents)}:
        raise ConductHomeOverlapsLogin(
            f"the login folder {found} is the hub's folder {resolved} or contains it")
