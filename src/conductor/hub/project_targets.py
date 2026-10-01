"""Admission of the hub's parent directory and exclusively created project folders."""
from __future__ import annotations

import os
import re
import stat
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from conductor import ownership_native
from conductor.command import path_admission
from conductor.hub import home, projects_add, registry
from conductor.hub.refusals import HubRefusal

DEFAULT_NAME = "ConductProjects"
FOLDER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}\Z")


@dataclass(frozen=True)
class TargetTicket:
    path: Path
    hub: Path
    configured_home: str | None
    ancestors: tuple[tuple[Path, tuple[int, int]], ...]


def _ancestors(path):
    return tuple(reversed((path, *path.parents)))


def _identity(path):
    return ownership_native.identity(path)


def _within(path, parent):
    return path == parent or parent in path.parents


def admit_home(path, hub, *, missing_default=False):
    """Read only. A missing default's existing parent is checked before its first mkdir."""
    path, hub = Path(path), Path(hub)
    try:
        if not path.is_absolute():
            raise ValueError("absolute parent required")
        present = os.path.lexists(path)
        if not present and not missing_default:
            raise ValueError("chosen parent must exist")
        projects_add._plain_route(path if present else path.parent)
        path = path.resolve(strict=present)
        listed = registry.load(hub)
        if os.name == "nt" and len(str(path).encode("utf-16-le")) // 2 > 60:
            raise HubRefusal("windows_path_too_long")
        if path == Path(path.anchor) or path == Path.home().resolve():
            raise ValueError("broad parent")
        hub = hub.resolve()
        if _within(path, hub) or _within(hub, path):
            raise ValueError("hub overlap")
        for parent in (path, *path.parents):
            if any(os.path.lexists(parent / marker) for marker in home.PROJECT_MARKERS):
                raise ValueError("inside project")
        if any(_within(path, Path(project.root).resolve()) for project in listed.projects):
            raise ValueError("registered project")
        for login in projects_add._login_homes(listed):
            if _within(path, login) or _within(login, path):
                raise ValueError("login overlap")
        return path
    except HubRefusal:
        raise
    except (OSError, ValueError, registry.RegistryError, projects_add.AddRefused) as error:
        raise HubRefusal("projects_home_invalid") from error


def target(hub, folder):
    if type(folder) is not str or FOLDER.fullmatch(folder) is None:
        raise HubRefusal("folder_invalid")
    try:
        path_admission.admit_name(folder, "project folder")
    except path_admission.WindowsNameError as error:
        raise HubRefusal("windows_name_unsafe") from error
    try:
        configured = registry.load(hub).projects_home
    except registry.RegistryError as error:
        raise HubRefusal("registry_invalid") from error
    parent = admit_home(configured or Path.home() / DEFAULT_NAME, hub,
                        missing_default=configured is None)
    child = parent / folder
    if os.name == "nt" and len(str(child).encode("utf-16-le")) // 2 > 100:
        raise HubRefusal("windows_path_too_long")
    if os.path.lexists(child):
        raise HubRefusal("folder_exists")
    return child


def ticket(hub, folder):
    """Read-only admission fixed to the chosen parent and its existing ancestor chain."""
    path = target(hub, folder)
    try:
        configured = registry.load(hub).projects_home
        parent = path.parent if path.parent.exists() else path.parent.parent
        ancestors = tuple((part, _identity(part)) for part in _ancestors(parent))
        if path != target(hub, folder):
            raise HubRefusal("projects_home_invalid")
        return TargetTicket(path, Path(hub).resolve(), configured, ancestors)
    except (OSError, ownership_native.NativeOwnershipError, registry.RegistryError) as error:
        raise HubRefusal("projects_home_invalid") from error


def _held_parent(expected, stack):
    """Open the admitted chain before creating; Windows holds deny rename/delete."""
    if os.name == "nt":
        for part, identity in expected.ancestors:
            hold = ownership_native.NativeHold(part, directory=True)
            stack.callback(hold.close)
            if hold.identity != identity:
                raise HubRefusal("projects_home_invalid")
        parent = expected.path.parent
        made_home = False
        if parent != expected.ancestors[-1][0]:
            try:
                parent.mkdir(mode=0o700)
                made_home = True
            except FileExistsError:
                pass
            hold = ownership_native.NativeHold(parent, directory=True)
            stack.callback(hold.close)
        admit_home(parent, expected.hub)
        return None, made_home

    # Each component is opened relative to the preceding directory handle, so
    # a replacement name cannot redirect the final mkdir to a different inode.
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    chain = expected.ancestors
    fd = os.open(chain[0][0], flags)
    stack.callback(os.close, fd)
    found = os.fstat(fd)
    if (found.st_dev, found.st_ino) != chain[0][1]:
        raise HubRefusal("projects_home_invalid")
    for part, identity in chain[1:]:
        fd = os.open(part.name, flags, dir_fd=fd)
        stack.callback(os.close, fd)
        found = os.fstat(fd)
        if not stat.S_ISDIR(found.st_mode) or (found.st_dev, found.st_ino) != identity:
            raise HubRefusal("projects_home_invalid")
    parent = expected.path.parent
    made_home = False
    if parent != chain[-1][0]:
        try:
            os.mkdir(parent.name, mode=0o700, dir_fd=fd)
            made_home = True
        except FileExistsError:
            pass
        fd = os.open(parent.name, flags, dir_fd=fd)
        stack.callback(os.close, fd)
    admit_home(parent, expected.hub)
    if _identity(parent) != (os.fstat(fd).st_dev, os.fstat(fd).st_ino):
        raise HubRefusal("projects_home_invalid")
    return fd, made_home


def create(hub, folder, *, expected: TargetTicket | None = None):
    """The operation, after explicit Add, is the only caller allowed to create these paths."""
    expected = expected or ticket(hub, folder)
    path = expected.path
    if (Path(hub).resolve() != expected.hub or path.name != folder
            or path != target(hub, folder)):
        raise HubRefusal("projects_home_invalid")
    try:
        if registry.load(hub).projects_home != expected.configured_home:
            raise HubRefusal("projects_home_invalid")
        with ExitStack() as stack:
            parent_fd, made_home = _held_parent(expected, stack)
            if registry.load(hub).projects_home != expected.configured_home:
                raise HubRefusal("projects_home_invalid")
            if os.name == "nt":
                path.mkdir(mode=0o700)
            else:
                os.mkdir(path.name, mode=0o700, dir_fd=parent_fd)
            projects_add._plain_route(path)
        return path, made_home
    except FileExistsError as error:
        raise HubRefusal("folder_exists") from error
    except (OSError, ownership_native.NativeOwnershipError, projects_add.AddRefused) as error:
        raise HubRefusal("projects_home_invalid") from error
