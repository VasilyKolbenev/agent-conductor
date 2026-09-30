"""The seed record of a task's work folder, read strictly (spec 9.1.5).

A task's work folder is seeded once from a commit of the project, and the seed step writes what it
did in one record, `<data_root>/seeds/<task_id>/work-001.json`: the tree it copied from, the counts,
the paths it did not copy and why. The materials of a run are judged against this record (a link to
a project document must name a file the seed copied, at the blob the seed copied), so the reader is
closed at every key and every type: a record that reads loosely is a base the check would trust.
The route is walked with the `lstat` rules the other stores use, because a record reached through a
link is bytes somebody else owns.

The record is written once, exclusively and all-or-nothing (`write_seed`): a name that is taken is
`SeedExists` whatever the other record says, and a record its own reader could not hold is refused
before a byte is written. A server in `view` mode starts no git, so it leaves a request instead,
`work-001.request.json` (9.1.6): a small closed record of the conditions the owner chose, written
and read the same way (`write_request`, `read_request`) and never read as a seed. The state of a
seed is not stored: `seed_state` reads it off the disk layout, the staging folder first, then the
task's own folder (9.1.4).
"""
from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

from ..ownership import data_root, write_guard
from ..ownership_errors import OwnerRefused
from .containment import first_directory_violation, lstat_or_none, portal_violation
from .contract_values import ContractError, _id, _timestamp
from .path_admission import admit_file
from .product_names import SEED_STAGING_DIR
from .run_store import _exclusive_bytes, _fsync_dir
from .store_errors import StoreError
from .task_contracts import _bounded_id
from .template_store import RouteNotOwned, _leaf_violation
from .work_layout import work_parts

SEEDS_DIR = "seeds"
#: Every task has exactly one work item (spec 9.1.1), and this is its name.
WORK_ITEM_ID = "work-001"
SCHEMA_VERSION = 1
SOURCES = ("git", "empty")
OBJECT_FORMATS = ("sha1", "sha256")
#: Why a path of the base was not copied (spec 9.1.3); the instruction files have their own list.
SKIP_REASONS = ("symlink", "submodule", "unportable_name", "path_budget")
WARNING_CODES = ("lfs_pointer",)
#: A record is a few hundred rows at most; a file past this is not one.
MAX_RECORD_BYTES = 1 << 20
MAX_PATH_CHARS = 4096

_OID = {"sha1": re.compile(r"[0-9a-f]{40}\Z"), "sha256": re.compile(r"[0-9a-f]{64}\Z")}
_STAGING = re.compile(r"s-(?:[0-9a-f]{8}|[0-9a-f]{64})\Z")
_FIELDS = frozenset({
    "schema_version", "task_id", "work_scope", "work_item_id", "source", "base_commit",
    "base_tree", "object_format", "base_ref", "file_count", "total_bytes",
    "include_agent_instructions", "staging", "skipped", "agent_instructions_skipped",
    "warnings", "staged_at"})
_BASE_FIELDS = ("base_commit", "base_tree", "object_format", "base_ref")


class CorruptSeed(StoreError):
    """A seed record that is unreadable, or is not exactly the schema, or names another place."""


class SeedExists(StoreError):
    """A record or a request already stands under this task and work item, whatever it says."""


class SeedRecordTooLarge(StoreError):
    """A record its own reader would refuse for its size; nothing was written."""


class Skip(NamedTuple):
    """One path of the base the seed did not copy, and why."""

    path: str
    reason: str


class SeedWarning(NamedTuple):
    """One path the seed copied that deserves a word."""

    path: str
    code: str


@dataclass(frozen=True)
class SeedRecord:
    """What the seed step did for one work item of one task: see the module text."""

    task_id: str
    work_scope: str
    work_item_id: str
    source: str
    base_commit: str | None
    base_tree: str | None
    object_format: str | None
    base_ref: str | None
    file_count: int
    total_bytes: int
    include_agent_instructions: bool
    staging: str
    skipped: tuple[Skip, ...]
    agent_instructions_skipped: tuple[str, ...]
    warnings: tuple[SeedWarning, ...]
    staged_at: str

    def not_copied(self) -> frozenset[str]:
        """Every path of the base the seed left out: its skips and the instruction files."""
        return frozenset({row.path for row in self.skipped} | set(self.agent_instructions_skipped))

    def as_dict(self) -> dict[str, Any]:
        """The stored shape, keys in the order of spec 9.1.5."""
        return {
            "schema_version": SCHEMA_VERSION, "task_id": self.task_id,
            "work_scope": self.work_scope, "work_item_id": self.work_item_id,
            "source": self.source, "base_commit": self.base_commit, "base_tree": self.base_tree,
            "object_format": self.object_format, "base_ref": self.base_ref,
            "file_count": self.file_count, "total_bytes": self.total_bytes,
            "include_agent_instructions": self.include_agent_instructions,
            "staging": self.staging,
            "skipped": [{"path": row.path, "reason": row.reason} for row in self.skipped],
            "agent_instructions_skipped": list(self.agent_instructions_skipped),
            "warnings": [{"path": row.path, "code": row.code} for row in self.warnings],
            "staged_at": self.staged_at}

    @classmethod
    def from_dict(cls, value: object) -> "SeedRecord":
        """Admit one stored record: closed at every key, exact at every type.

        Raises:
            ContractError: The document is not an object, carries another set of keys than the
                schema, or holds a value the schema does not allow.
        """
        if not isinstance(value, Mapping):
            raise ContractError("a seed record must be a JSON object")
        if set(value) != _FIELDS:
            raise ContractError(f"a seed record carries exactly {sorted(_FIELDS)}")
        if type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION:
            raise ContractError(f"a seed record speaks schema version {SCHEMA_VERSION}")
        source = _member("source", value["source"], SOURCES)
        return cls(
            task_id=_bounded_id("task_id", value["task_id"]),
            work_scope=_bounded_id("work_scope", value["work_scope"]),
            work_item_id=_id("work_item_id", value["work_item_id"]), source=source,
            **_base(source, value),
            file_count=_count("file_count", value["file_count"]),
            total_bytes=_count("total_bytes", value["total_bytes"]),
            include_agent_instructions=_flag(
                "include_agent_instructions", value["include_agent_instructions"]),
            staging=_grammar("staging", value["staging"], _STAGING),
            skipped=_skips(value["skipped"]),
            agent_instructions_skipped=_instruction_paths(value["agent_instructions_skipped"]),
            warnings=_warnings(value["warnings"]),
            staged_at=_timestamp("staged_at", value["staged_at"]))


def read_seed(project_root: str | os.PathLike[str], task_id: str,
              work_item_id: str = WORK_ITEM_ID) -> SeedRecord | None:
    """The seed record of one work item of one task, or ``None`` when none stands.

    Args:
        project_root: The project folder.
        task_id: A task id the task store can address.
        work_item_id: The work item; every task has `WORK_ITEM_ID`.

    Returns:
        The record, or ``None`` when the seed step has written none (the request a `view` server
        writes is another file and is not a record).

    Raises:
        StoreError: `task_id` or `work_item_id` names nothing the store can address.
        RouteNotOwned: The route to the record reaches bytes this build cannot account for.
        CorruptSeed: The record is unreadable, is not exactly the schema, or is another task's.
    """
    seeds, path, task, item = _stored_place(project_root, task_id, work_item_id, ".json")
    _hold_route(seeds, path)
    if not os.path.lexists(path):
        return None
    record = _parsed(path)
    if (record.task_id, record.work_item_id) != (task, item):
        raise CorruptSeed("a seed record names another task or work item than its place")
    return record


def _stored_place(project_root: str | os.PathLike[str], task_id: str, work_item_id: str,
                  suffix: str) -> tuple[Path, Path, str, str]:
    """The seed folder, the file of one stored document and the two ids, the ids judged first."""
    try:
        task, item = _bounded_id("task_id", task_id), _id("work_item_id", work_item_id)
    except ContractError as error:
        raise StoreError(str(error)) from error
    seeds = data_root(Path(project_root).resolve()) / SEEDS_DIR
    return seeds, seeds / task / f"{item}{suffix}", task, item


def _hold_route(seeds: Path, path: Path) -> None:
    violation = (first_directory_violation((seeds.parent, seeds, path.parent))
                 or _leaf_violation(path))
    if violation is not None:
        raise RouteNotOwned("the seed store has a component this build cannot account for")


def _parsed(path: Path) -> SeedRecord:
    document = _document(path, "a seed record")
    try:
        return SeedRecord.from_dict(document)
    except ContractError as error:
        raise CorruptSeed(f"a seed record violates its schema: {error}") from error


def _document(path: Path, what: str) -> Any:
    """The JSON of one stored file, bounded, UTF-8, with no key twice and no constant."""
    try:
        if path.stat().st_size > MAX_RECORD_BYTES:
            raise CorruptSeed(f"{what} is larger than any record can be")
        return json.loads(path.read_bytes().decode("utf-8"),
                          object_pairs_hook=_one_of_each, parse_constant=_no_constant)
    except (OSError, ValueError) as error:  # UnicodeError and JSONDecodeError are ValueErrors
        raise CorruptSeed(f"{what} is unreadable: {error}") from error


def _one_of_each(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a key is written twice")
    return dict(pairs)


def _no_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def _base(source: str, value: Mapping[str, Any]) -> dict[str, Any]:
    """The four base fields: all null for an empty seed, all present and consistent for git."""
    if source == "empty":
        if any(value[name] is not None for name in _BASE_FIELDS):
            raise ContractError("an empty seed has no base")
        return {name: None for name in _BASE_FIELDS}
    fmt = _member("object_format", value["object_format"], OBJECT_FORMATS)
    return {"base_commit": _grammar("base_commit", value["base_commit"], _OID[fmt]),
            "base_tree": _grammar("base_tree", value["base_tree"], _OID[fmt]),
            "object_format": fmt, "base_ref": _path("base_ref", value["base_ref"])}


def _member(name: str, value: object, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ContractError(f"{name} must be one of {', '.join(allowed)}")
    return value


def _grammar(name: str, value: object, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.match(value) is None:
        raise ContractError(f"{name} is not well formed")
    return value


def _count(name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise ContractError(f"{name} must be a whole number, zero or more")
    return value


def _flag(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise ContractError(f"{name} must be true or false")
    return value


def _path(name: str, value: object) -> str:
    """One line of text a path can be: no NUL, no line break, bounded."""
    if (not isinstance(value, str) or not value or len(value) > MAX_PATH_CHARS
            or set(value) & {"\x00", "\n", "\r"}):
        raise ContractError(f"{name} holds a path that is not one line of text")
    return value


def _list(name: str, value: object) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{name} must be a list")
    return value


def _rows(name: str, value: object, keys: set[str]) -> list[Mapping[str, Any]]:
    rows = _list(name, value)
    if any(not isinstance(row, Mapping) or set(row) != keys for row in rows):
        raise ContractError(f"every row of {name} carries exactly {sorted(keys)}")
    return rows


def _skips(value: object) -> tuple[Skip, ...]:
    return tuple(Skip(_path("skipped", row["path"]),
                      _member("skipped", row["reason"], SKIP_REASONS))
                 for row in _rows("skipped", value, {"path", "reason"}))


def _instruction_paths(value: object) -> tuple[str, ...]:
    return tuple(_path("agent_instructions_skipped", row)
                 for row in _list("agent_instructions_skipped", value))


def _warnings(value: object) -> tuple[SeedWarning, ...]:
    return tuple(SeedWarning(_path("warnings", row["path"]),
                             _member("warnings", row["code"], WARNING_CODES))
                 for row in _rows("warnings", value, {"path", "code"}))


# -- the request a view process leaves, and the writers (9.1.6, 9.1.5) ------------------------

REQUEST_SUFFIX = ".request.json"
_REQUEST_FIELDS = ("schema_version", "task_id", "work_item_id", "include_agent_instructions",
                   "requested_at")


@dataclass(frozen=True)
class SeedRequest:
    """What the owner chose for a seed that a server in `view` mode could not make (9.1.6)."""

    task_id: str
    work_item_id: str
    include_agent_instructions: bool
    requested_at: str

    def as_dict(self) -> dict[str, Any]:
        """The stored shape, keys in the order of spec 9.1.6."""
        return {"schema_version": SCHEMA_VERSION, "task_id": self.task_id,
                "work_item_id": self.work_item_id,
                "include_agent_instructions": self.include_agent_instructions,
                "requested_at": self.requested_at}

    @classmethod
    def from_dict(cls, value: object) -> "SeedRequest":
        """Admit one stored request: closed at every key, exact at every type.

        Raises:
            ContractError: Not an object, another set of keys, or a value the schema refuses.
        """
        if not isinstance(value, Mapping) or set(value) != set(_REQUEST_FIELDS):
            raise ContractError(f"a seed request carries exactly {list(_REQUEST_FIELDS)}")
        if type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION:
            raise ContractError(f"a seed request speaks schema version {SCHEMA_VERSION}")
        return cls(task_id=_bounded_id("task_id", value["task_id"]),
                   work_item_id=_id("work_item_id", value["work_item_id"]),
                   include_agent_instructions=_flag(
                       "include_agent_instructions", value["include_agent_instructions"]),
                   requested_at=_timestamp("requested_at", value["requested_at"]))


def write_seed(project_root: str | os.PathLike[str], record: SeedRecord) -> None:
    """Write the record of a seed, once.

    Raises:
        TypeError: `record` is not a `SeedRecord`.
        SeedExists: A record already stands for this task and work item; nothing was changed.
        SeedRecordTooLarge: The record is larger than its reader admits.
        RouteNotOwned: The route to the record reaches bytes this build cannot account for.
        WindowsPathError: The file or its private temporary file could not be made on Windows.
        StoreError: The record could not be written, or the project has no live owner.
    """
    if type(record) is not SeedRecord:
        raise TypeError("write_seed takes exactly a SeedRecord")
    _write_once(project_root, record.task_id, record.work_item_id, ".json", record.as_dict(),
                "seed record")


def write_request(project_root: str | os.PathLike[str], request: SeedRequest) -> None:
    """Write the request of a seed, once; the errors are those of `write_seed`."""
    if type(request) is not SeedRequest:
        raise TypeError("write_request takes exactly a SeedRequest")
    _write_once(project_root, request.task_id, request.work_item_id, REQUEST_SUFFIX,
                request.as_dict(), "seed request")


def read_request(project_root: str | os.PathLike[str], task_id: str,
                 work_item_id: str = WORK_ITEM_ID) -> SeedRequest | None:
    """The request a `view` server left for one work item of one task, or None.

    Raises:
        StoreError: `task_id` or `work_item_id` names nothing the store can address.
        RouteNotOwned: The route to the request reaches bytes this build cannot account for.
        CorruptSeed: The request is unreadable, not exactly the schema, or another task's.
    """
    seeds, path, task, item = _stored_place(project_root, task_id, work_item_id, REQUEST_SUFFIX)
    _hold_route(seeds, path)
    if not os.path.lexists(path):
        return None
    document = _document(path, "a seed request")
    try:
        request = SeedRequest.from_dict(document)
    except ContractError as error:
        raise CorruptSeed(f"a seed request violates its schema: {error}") from error
    if (request.task_id, request.work_item_id) != (task, item):
        raise CorruptSeed("a seed request names another task or work item than its place")
    return request


def seed_state(project_root: str | os.PathLike[str], record: SeedRecord) -> str:
    """`staged`, `seeded` or `seed_lost`, read off the disk and stored nowhere (9.1.4).

    The staging folder standing means the move is still owed (`staged`, even if the task's folder
    has appeared: the move says `work_not_empty` then); the staging gone and the task's folder
    standing is `seeded`; neither is `seed_lost`. A file or a link where a folder belongs is not
    a folder.
    """
    root = Path(project_root).resolve()
    if _is_folder(root / SEED_STAGING_DIR / record.staging):
        return "staged"
    if _is_folder(root.joinpath(*work_parts(record.work_item_id, record.work_scope))):
        return "seeded"
    return "seed_lost"


def read_seed_view(project_root: str | os.PathLike[str], task_id: str) -> dict[str, Any] | None:
    """What the preparation of a task says of its seed (9.1.5): the record with its state, else
    the request as `requested`, else None.

    A record or a request that cannot be read reads as none: one bad file must not hide the task
    from the page that would let its owner see what is wrong (the route that asks for a seed
    answers a store error for it).
    """
    try:
        record = read_seed(project_root, task_id)
        if record is not None:
            return {**record.as_dict(), "state": seed_state(project_root, record)}
        request = read_request(project_root, task_id)
    except (CorruptSeed, RouteNotOwned):
        return None
    return None if request is None else {**request.as_dict(), "state": "requested"}


def _is_folder(path: Path) -> bool:
    found = lstat_or_none(path)
    return (found is not None and portal_violation(path, found) is None
            and stat.S_ISDIR(found.st_mode))


def _write_once(project_root: str | os.PathLike[str], task_id: str, work_item_id: str,
                suffix: str, document: dict[str, Any], label: str) -> None:
    """Publish one document at its place, exclusively and whole, or say a record stands."""
    payload = json.dumps(document, ensure_ascii=True, separators=(",", ":"),
                         allow_nan=False).encode("ascii") + b"\n"
    if len(payload) > MAX_RECORD_BYTES:
        raise SeedRecordTooLarge(f"a {label} larger than {MAX_RECORD_BYTES} bytes cannot be read")
    root = Path(project_root).resolve()
    seeds, path, _task, _item = _stored_place(root, task_id, work_item_id, suffix)
    try:
        with write_guard(root):
            admit_file(path, label)
            _hold_route(seeds, path)
            path.parent.mkdir(parents=True, exist_ok=True)
            _hold_route(seeds, path)
            try:
                _exclusive_bytes(path, payload)
            except FileExistsError:
                raise SeedExists(f"a {label} already stands for this work item") from None
            _fsync_dir(path.parent)
    except OwnerRefused as error:
        raise StoreError(str(error)) from error
    except OSError as error:
        raise StoreError(f"cannot write the {label}: {error.strerror}") from None
