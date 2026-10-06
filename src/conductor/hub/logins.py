"""The login folders the hub knows, and the state of the box each one has (spec 4.1.8, ADR-8).

A login folder is named only by the shared profile and by the `providers.json` of the registered
projects; the hub finds each one from those two sources and gives it the key its box carries
(`ownership_login.box_key`), so a click names a key and never a path. `harness` is the provider id
of the first row that names the folder, as data. A source that cannot be read hides only itself,
and a folder that is not a plain existing one is left out: this is a list for a person to act on,
never a gate. The state of a box is read from its `active.json` and from what the hub itself runs:
the word that offers no action (`in_use`) is the one given whenever the hub cannot tell.
"""
from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from conductor import ownership, ownership_login
from conductor.command import operator_config
from conductor.hub import registry
from conductor.ownership_errors import OwnerRefused

#: How long one scan of the sources is kept: the state of each box is read afresh every time.
TTL_SECONDS = 2.0
_UNREADABLE = (operator_config.OperatorConfigError, OwnerRefused, OSError, ValueError)


@dataclass(frozen=True)
class Login:
    """One login folder: its key, the provider id of the first row that names it, its users."""

    key: str
    harness: str
    used_by: tuple[str, ...]
    auth_home: str
    box: Path


def _sources(home: Path, projects: Sequence[registry.Project]) -> list[tuple[Path, str | None]]:
    """The provider files to read, the profile first: `(file, project id or None)`."""
    profile = home / operator_config.PROVIDER_CONFIG_FILENAME
    found: list[tuple[Path, str | None]] = [(profile, None)]
    for project in projects:
        try:
            data = ownership.data_root(Path(project.root))
        except _UNREADABLE:
            continue
        found.append((operator_config.provider_config_path(data), project.project_id))
    return found


def _boxes(path: Path) -> list[tuple[str, str, str, Path]]:
    """`(key, provider id, login folder, box)` of each row whose folder is a plain existing one."""
    try:
        rows = operator_config.load_provider_configs(path)
    except _UNREADABLE:
        return []
    found = []
    for row in rows:
        if not row.auth_home:
            continue
        try:
            auth_home, box, key = ownership_login.box_key(row.auth_home)
        except _UNREADABLE:
            continue
        found.append((key, row.provider_id, str(auth_home), box))
    return found


def scan(home: Path | str, projects: Sequence[registry.Project]) -> tuple[Login, ...]:
    """Every login folder the profile and the registered projects name, merged by box key.

    Args:
        home: The hub's folder (its shared profile is `home/providers.json`).
        projects: The registered projects, in registry order.

    Returns:
        One `Login` per box key, in the order the sources first named it; `used_by` lists the
        registered projects that name it, in registry order (the profile adds none).
    """
    first: dict[str, tuple[str, str, Path]] = {}
    users: dict[str, set[str]] = {}
    for path, project_id in _sources(Path(home), projects):
        for key, harness, auth_home, box in _boxes(path):
            first.setdefault(key, (harness, auth_home, box))
            users.setdefault(key, set())
            if project_id is not None:
                users[key].add(project_id)
    order = [project.project_id for project in projects]
    return tuple(
        Login(key, harness, tuple(one for one in order if one in users[key]), auth_home, box)
        for key, (harness, auth_home, box) in first.items())


def state_of(login: Login, *, active_running: bool, closing_owed: bool) -> str:
    """`free` (no lease record), `in_use` (the hub's active child works or still owes its closure,
    or the box cannot be read) or `unclosed` (a lease record and nobody the hub knows holds it)."""
    try:
        os.lstat(login.box / "active.json")
    except FileNotFoundError:
        return "free"
    except OSError:
        return "in_use"
    return "in_use" if active_running or closing_owed else "unclosed"


def public(login: Login, state: str) -> dict[str, object]:
    """The four keys `GET /hub/setup` shows for a login: no path, no provider name beyond data."""
    return {"login_key": login.key, "harness": login.harness, "used_by": list(login.used_by),
            "state": state}


class LoginView:
    """The logins as the page reads them, over the two things the hub knows about its children."""

    def __init__(self, home: Path | str, load_projects: Callable[[], Sequence[registry.Project]],
                 active_running: Callable[[], bool], closing_owed: Callable[[], bool], *,
                 clock: Callable[[], float] = time.monotonic, ttl: float = TTL_SECONDS) -> None:
        self._home, self._load_projects = Path(home), load_projects
        self._active_running, self._closing_owed = active_running, closing_owed
        self._clock, self._ttl = clock, ttl
        self._lock = threading.Lock()
        self._scanned: tuple[float, tuple[Login, ...]] | None = None

    def entries(self) -> list[dict[str, object]]:
        """The public form of every login; the sources are read at most once per `ttl`."""
        found = self._cached()
        if not found:
            return []
        running, owed = self._active_running(), self._closing_owed()
        return [public(login, state_of(login, active_running=running, closing_owed=owed))
                for login in found]

    def find(self, key: str) -> Login | None:
        """The login of a key, from a scan made now: a recovery is judged on the disk."""
        return next((login for login in scan(self._home, self._load_projects())
                     if login.key == key), None)

    def state(self, login: Login) -> str:
        """The state of one box now."""
        return state_of(login, active_running=self._active_running(),
                        closing_owed=self._closing_owed())

    def _cached(self) -> tuple[Login, ...]:
        with self._lock:
            now = self._clock()
            if self._scanned is None or now - self._scanned[0] >= self._ttl:
                self._scanned = (now, scan(self._home, self._load_projects()))
            return self._scanned[1]
