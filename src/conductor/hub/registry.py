"""The registry of projects: `<conduct-home>/registry.json` (spec 4.1.3, 8.2 step 7).

One file, canonical JSON, read strictly and written whole. Strict to read: an unknown key, a
key twice, JSON that is not JSON, a file over 256 KiB or a value outside its grammar is
`registry_invalid`, named by the file, and the file is then never rewritten over what its owner
must look at (the hub starts without projects, shows a banner, and leaves it). Every write is
a read, a change and an atomic replace under `registry.lock`, taken without waiting and retried
for about two seconds (`registry_busy`), so the hub and `conduct projects add` in another
process never lose each other's entries. Reading takes no lock.

The registry knows a project by values it is handed (the nonce, the root, the root's identity);
it opens no project folder. Who may be added is the admission of `projects add`, not this file.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from conductor import atomic_replace, ownership_records
from conductor.hub import home, lockfile

SCHEMA_VERSION = 1
FILE_NAME = "registry.json"
LOCK_NAME = "registry.lock"
MAX_BYTES = 256 * 1024
MAX_NAME = 64
#: The ports a project may be given, and the one that is never given: the standalone `up`'s.
PORT_FIRST, PORT_LAST, STANDALONE_PORT = 7701, 7799, 7777
SOURCES = ("folder", "github", "scratch")

#: The codes of the spec that this module raises (4.1.3, 8.2 step 7, 4.6.5).
SPEC_CODES = frozenset({"registry_invalid", "registry_busy", "ports_exhausted", "name_invalid",
                        "root_already_registered"})
#: A proposal: the spec has no name for a registry that cannot be written (the folder is not
#: writable). `tools_file_unwritable` is its analogue for the pins. It stays until ruled on.
PROPOSED_CODES = frozenset({"registry_unwritable"})

_ID = re.compile(r"[0-9a-f]{32}")
_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}")
_INSTANT = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
_TOP_KEYS = frozenset({"schema_version", "projects_home", "projects"})
_PROJECT_KEYS = frozenset({"project_id", "name", "root", "root_identity", "port", "source",
                           "repo", "added_at"})


class RegistryError(Exception):
    """A refusal of the registry: a closed code and one line of detail.

    Raises:
        ValueError: `code` is neither a code of the spec nor a proposed one; a new code is a
            decision for the spec, not something a raise site may introduce.
    """

    def __init__(self, code: str, detail: str) -> None:
        if code not in SPEC_CODES | PROPOSED_CODES:
            raise ValueError(f"{code!r} is neither a code of the spec nor a proposed one")
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class Project:
    """One registered project, as the file spells it (spec 4.1.3)."""

    project_id: str
    name: str
    root: str
    root_identity: tuple[int, int]
    port: int
    source: str
    repo: str | None
    added_at: str


@dataclass(frozen=True)
class Registry:
    """The whole file: the projects folder the owner chose (or `None`) and the projects."""

    projects_home: str | None
    projects: tuple[Project, ...] = ()

    def project(self, project_id: str) -> Project | None:
        """The entry with this nonce, or `None`."""
        return next((p for p in self.projects if p.project_id == project_id), None)

    def find_root(self, root: str, identity: Iterable[int]) -> Project | None:
        """The entry of this root, by its path (folded the way the OS folds it) or by identity."""
        wanted_key, wanted_identity = _root_key(root), tuple(identity)
        return next((p for p in self.projects if _root_key(p.root) == wanted_key
                     or p.root_identity == wanted_identity), None)


def _root_key(root: str) -> str:
    return os.path.normcase(os.path.normpath(root))


def _folder(folder: Path | str | None) -> Path:
    return home.conduct_home_path() if folder is None else Path(folder)


def registry_file(folder: Path | str | None = None) -> Path:
    """`<conduct-home>/registry.json`, or the same name in `folder`."""
    return _folder(folder) / FILE_NAME


# -- the grammar of a value -------------------------------------------------------------------


def name_problem(name: object) -> str | None:
    """Why `name` is not a signature (spec 4.1.3), or `None` when it is one.

    1 to 64 characters, none of them a control, format, private-use, surrogate or unassigned
    character or a line or paragraph separator, and no space at either edge. Letters, digits,
    marks, spaces and punctuation of any script pass, and so does any symbol.
    """
    if not isinstance(name, str):
        return "is not text"
    if not 1 <= len(name) <= MAX_NAME:
        return f"must have 1 to {MAX_NAME} characters"
    if name != name.strip():
        return "must not start or end with a space"
    for char in name:
        category = unicodedata.category(char)
        if category[0] == "C" or category in ("Zl", "Zp"):
            return f"holds the character U+{ord(char):04X}, which cannot be shown safely"
    return None


def _is_count(value: object) -> bool:
    return type(value) is int and value >= 0


def _project_problem(project: Project) -> str | None:
    """The first way one entry is outside its grammar, or `None`."""
    checks = (
        (_ID.fullmatch(project.project_id) if isinstance(project.project_id, str) else None,
         "project_id must be 32 lowercase hex characters"),
        (name_problem(project.name) is None, f"name {name_problem(project.name)}"),
        (isinstance(project.root, str) and project.root and "\0" not in project.root
         and os.path.isabs(project.root), "root must be an absolute path"),
        (isinstance(project.root_identity, tuple) and len(project.root_identity) == 2
         and all(_is_count(n) for n in project.root_identity),
         "root_identity must be two non-negative integers"),
        (type(project.port) is int and PORT_FIRST <= project.port <= PORT_LAST
         and project.port != STANDALONE_PORT,
         f"port must be {PORT_FIRST} to {PORT_LAST} without {STANDALONE_PORT}"),
        (project.source in SOURCES, f"source must be one of {', '.join(SOURCES)}"),
        (project.repo is None or (isinstance(project.repo, str)
                                  and _REPO.fullmatch(project.repo)),
         "repo must be owner/name or null"),
        (_is_instant(project.added_at), "added_at must be a UTC time like 2026-09-30T10:00:00Z"),
    )
    return next((message for holds, message in checks if not holds), None)


def _is_instant(value: object) -> bool:
    if not (isinstance(value, str) and _INSTANT.fullmatch(value)):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _registry_problem(current: Registry) -> str | None:
    """The first rule the whole registry breaks: a bad entry, a bad folder, a repeated value."""
    home_value = current.projects_home
    if home_value is not None and not (isinstance(home_value, str) and home_value
                                       and "\0" not in home_value and os.path.isabs(home_value)):
        return "projects_home must be null or an absolute path"
    seen: dict[str, set] = {"project_id": set(), "root": set(), "identity": set(),
                            "name": set(), "port": set()}
    for index, project in enumerate(current.projects):
        problem = _project_problem(project)
        if problem is not None:
            return f"projects[{index}]: {problem}"
        keys = {"project_id": project.project_id, "root": _root_key(project.root),
                "identity": project.root_identity, "name": project.name.casefold(),
                "port": project.port}
        for field, value in keys.items():
            if value in seen[field]:
                return f"two projects share the {field} {project_value(project, field)}"
            seen[field].add(value)
    return None


def project_value(project: Project, field: str) -> str:
    """How a repeated value reads in a refusal."""
    return {"project_id": project.project_id, "root": project.root, "port": str(project.port),
            "identity": str(list(project.root_identity)), "name": repr(project.name)}[field]


# -- reading: strict about the schema --------------------------------------------------------


def _invalid(detail: str) -> RegistryError:
    return RegistryError("registry_invalid", f"{FILE_NAME}: {detail}")


def _strict_json(text: str) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict:
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("a key appears twice")
        return dict(pairs)

    def refuse(constant: str) -> object:
        raise ValueError(f"{constant} is not JSON")

    return json.loads(text, object_pairs_hook=unique, parse_constant=refuse)


def _read_bytes(path: Path) -> bytes | None:
    try:
        size = path.stat().st_size
        if size > MAX_BYTES:
            raise _invalid(f"is larger than {MAX_BYTES // 1024} KiB")
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise _invalid(f"cannot be read: {error}") from error
    if len(data) > MAX_BYTES:
        raise _invalid(f"is larger than {MAX_BYTES // 1024} KiB")
    return data


def _project_from(entry: object, index: int) -> Project:
    if not isinstance(entry, dict) or set(entry) != _PROJECT_KEYS:
        raise _invalid(f"projects[{index}] must be an object with exactly the keys of a project")
    identity = entry["root_identity"]
    pair = tuple(identity) if isinstance(identity, list) else identity
    return Project(entry["project_id"], entry["name"], entry["root"], pair, entry["port"],
                   entry["source"], entry["repo"], entry["added_at"])


def _parse(data: bytes) -> Registry:
    try:
        document = _strict_json(data.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise _invalid(f"is not JSON the registry accepts: {error}") from error
    if not isinstance(document, dict) or set(document) != _TOP_KEYS:
        raise _invalid("must be an object with exactly schema_version, projects_home, projects")
    version = document["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise _invalid(f"schema_version must be the number {SCHEMA_VERSION}")
    listed = document["projects"]
    if not isinstance(listed, list):
        raise _invalid("projects must be a list")
    found = Registry(document["projects_home"],
                     tuple(_project_from(entry, number) for number, entry in enumerate(listed)))
    problem = _registry_problem(found)
    if problem is not None:
        raise _invalid(problem)
    return found


def load(folder: Path | str | None = None) -> Registry:
    """Read the registry; a missing file is an empty registry, and reading writes nothing.

    Raises:
        RegistryError: `registry_invalid`: the file exists and is not the schema.
    """
    data = _read_bytes(registry_file(folder))
    return Registry(None, ()) if data is None else _parse(data)


def digest(folder: Path | str | None = None) -> str | None:
    """The SHA-256 of the file's bytes, or `None` when there is no file: what a poller compares."""
    try:
        return hashlib.sha256(registry_file(folder).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise _invalid(f"cannot be read: {error}") from error


# -- writing: one read, one change, one atomic replace, under the lock -------------------------


def _document(current: Registry) -> dict:
    return {"schema_version": SCHEMA_VERSION, "projects_home": current.projects_home,
            "projects": [{"project_id": p.project_id, "name": p.name, "root": p.root,
                          "root_identity": list(p.root_identity), "port": p.port,
                          "source": p.source, "repo": p.repo, "added_at": p.added_at}
                         for p in current.projects]}


def _store(updated: Registry, folder: Path) -> None:
    problem = _registry_problem(updated)
    if problem is not None:
        raise _invalid(f"would not be the schema: {problem}")
    target = folder / FILE_NAME
    try:
        atomic_replace.replace_bytes(target, ownership_records.canonical(_document(updated)))
    except OSError as error:
        raise RegistryError("registry_unwritable",
                            f"{FILE_NAME} could not be written: {error}") from error


def mutate(change: Callable[[Registry], Registry], folder: Path | str | None = None, *,
           attempts: int = lockfile.ATTEMPTS, pause: float = lockfile.PAUSE_SECONDS) -> Registry:
    """Read the registry, apply `change` to it and publish the result, all under the lock.

    A `change` that returns what it was given writes nothing. The result is judged against the
    rules of the schema before it reaches the disk, and an invalid file on disk is never
    replaced.

    Args:
        change: A pure function of the registry read under the lock.
        folder: `<conduct-home>` unless a test says another.
        attempts: Tries of the lock.
        pause: Seconds between two tries.

    Returns:
        The registry as it stands after the call.

    Raises:
        RegistryError: `registry_busy`, `registry_invalid`, `registry_unwritable`, or whatever
            `change` refuses with.
    """
    where = _folder(folder)
    try:
        where.mkdir(mode=0o700, parents=True, exist_ok=True)
        with lockfile.held(where / LOCK_NAME, attempts=attempts, pause=pause):
            current = load(where)
            updated = change(current)
            if updated != current:
                _store(updated, where)
            return updated
    except lockfile.LockBusy as error:
        raise RegistryError("registry_busy", str(error)) from error
    except OSError as error:
        raise RegistryError("registry_unwritable",
                            f"{FILE_NAME} cannot be written in {where}: {error}") from error


def next_port(used: Iterable[int], hub_port: int | None) -> int:
    """The first port of 7701-7799 that is free: not used, not 7777, not the hub's own.

    Raises:
        RegistryError: `ports_exhausted`: all 98 are taken.
    """
    taken = {*used, STANDALONE_PORT}
    if hub_port is not None:
        taken.add(hub_port)
    free = next((port for port in range(PORT_FIRST, PORT_LAST + 1) if port not in taken), None)
    if free is None:
        raise RegistryError("ports_exhausted",
                            f"every port from {PORT_FIRST} to {PORT_LAST} is in use")
    return free


def _unique_name(wanted: str, taken: set[str]) -> str:
    """`wanted`, or `wanted 2`, `wanted 3`, ... the first not taken without regard to case."""
    if wanted.casefold() not in taken:
        return wanted
    for number in range(2, 10_000):
        suffix = f" {number}"
        candidate = wanted[:MAX_NAME - len(suffix)].rstrip() + suffix
        if candidate.casefold() not in taken:
            return candidate
    raise RegistryError("name_invalid", f"no free suffix was found for {wanted!r}")


def _already_there(current: Registry, project_id: str, root: str,
                   identity: tuple[int, int]) -> Project | None:
    """The entry this add repeats, `None` when it is new; a clash with another entry refuses."""
    by_id, by_root = current.project(project_id), current.find_root(root, identity)
    if by_id is None and by_root is None:
        return None
    if by_id is not None and by_id is by_root:
        return by_id
    held_by = by_root if by_root is not None else by_id
    raise RegistryError(
        "root_already_registered",
        f"the root {root} or the project {project_id} is already registered as "
        f"{held_by.name!r} at {held_by.root}")


def add_project(*, project_id: str, root: str, root_identity: Iterable[int],
                source: str = "folder", repo: str | None = None, name: str | None = None,
                now: str | None = None, hub_port: int | None = None,
                folder: Path | str | None = None, attempts: int = lockfile.ATTEMPTS,
                pause: float = lockfile.PAUSE_SECONDS) -> tuple[Project, str]:
    """Register a project, or recognise it: `(project, "new" | "existing")`.

    The port is the first free one, the name the wanted one (or the last folder of the root) with
    a suffix when it is taken, and the project folder is not touched. A repeat of the same root
    with the same nonce is `existing` and writes nothing.

    Raises:
        RegistryError: `name_invalid`, `root_already_registered` (the root, its identity or the
            nonce is held by another entry), `ports_exhausted`, `registry_busy`,
            `registry_invalid`, `registry_unwritable`.
        ValueError: A value of the new entry is outside its grammar; a fault of the caller.
    """
    identity = tuple(root_identity)
    made: list[tuple[Project, str]] = []

    def change(current: Registry) -> Registry:
        existing = _already_there(current, project_id, root, identity)
        if existing is not None:
            made.append((existing, "existing"))
            return current
        project = _new_project(current, project_id, root, identity, source, repo, name, now,
                               hub_port)
        made.append((project, "new"))
        return Registry(current.projects_home, (*current.projects, project))

    mutate(change, folder, attempts=attempts, pause=pause)
    return made[-1]


def _new_project(current: Registry, project_id: str, root: str, identity: tuple[int, int],
                 source: str, repo: str | None, name: str | None, now: str | None,
                 hub_port: int | None) -> Project:
    wanted = Path(root).name if name is None else name
    problem = name_problem(wanted)
    if problem is not None:
        raise RegistryError("name_invalid", f"the name {wanted!r} {problem}")
    taken = {p.name.casefold() for p in current.projects}
    port = next_port((p.port for p in current.projects), hub_port)
    project = Project(project_id, _unique_name(wanted, taken), root, identity, port, source,
                      repo, now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    problem = _project_problem(project)
    if problem is not None:
        raise ValueError(f"the new entry is outside its grammar: {problem}")
    return project


def remove_project(project_id: str, folder: Path | str | None = None) -> Registry:
    """Take an entry off the list ("Убрать из списка"); the project's files are not touched.

    An id that is not there writes nothing.
    """
    return mutate(lambda current: Registry(
        current.projects_home,
        tuple(p for p in current.projects if p.project_id != project_id)), folder)


def set_projects_home(value: str | None, folder: Path | str | None = None) -> Registry:
    """Keep the folder the owner chose for new projects; `None` puts back the default (8.4).

    Raises:
        RegistryError: `registry_invalid` when `value` is not an absolute path.
    """
    return mutate(lambda current: Registry(value, current.projects), folder)
