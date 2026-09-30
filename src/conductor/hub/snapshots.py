"""The one snapshot rule of the hub, and `limits.json` by the same rule (spec 4.1.9).

`snapshots/<project_id>.json` holds the last whole, good pass over one child:
`{"schema_version": 1, "project_id", "taken_at", "tasks", "task_queue", "auto_continue",
"quotas"}`, the answers of the reads as they were, with no word added. One rule, and no other:

- only the hub writes it, whole and atomically, and the caller offers a pass only after every
  read of it was answered (`Cycle.complete`);
- it is written only when its content changed (the moment it was taken is not content) and not
  more than once in 5 s for a project;
- it keeps at most the 200 newest tasks and at most 512 KiB: over the size, `attention.journal`
  falls out first (the wait then reads "noticed at", because `waitingSince` finds no record),
  and one that is still too big is not written, so the last good one stands;
- it outlives the stop of its project; nothing here removes one, and the registry is never
  written on the way;
- a broken one is absent (`data: "none"`) and a read does not repair it: the next good pass
  replaces it.

`limits.json` is the quotas answer of the ACTIVE project under the same rule, in the exact form
`HubLimitsView` (the reader of a `view` child) admits.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from conductor import atomic_replace, ownership_records
from conductor.command.quota_snapshot_view import LIMITS_FILE, HubLimitsView

SCHEMA_VERSION = 1
MAX_TASKS = 200
MAX_BYTES = 512 * 1024
MIN_INTERVAL_SECONDS = 5
FOLDER = "snapshots"
_ID = re.compile(r"[0-9a-f]{32}")
_INSTANT = "%Y-%m-%dT%H:%M:%SZ"
_FILE_KEYS = frozenset({"schema_version", "project_id", "taken_at", "tasks", "task_queue",
                        "auto_continue", "quotas"})
_ROW_KEYS = frozenset({"task", "run", "automation", "attention"})


@dataclass(frozen=True)
class Snapshot:
    """A project's last whole pass, as read back."""

    project_id: str
    taken_at: str
    tasks: list[dict[str, Any]]
    task_queue: dict[str, Any] | None
    auto_continue: dict[str, Any] | None
    quotas: dict[str, Any] | None


@dataclass(frozen=True)
class LimitsSnapshot:
    """The last quotas answer of the active project, and when and whose it was."""

    project_id: str
    taken_at: str
    quotas: dict[str, Any]


def _project_id(value: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("a project id is 32 lowercase hex characters")
    return value


def _instant(value: str) -> str:
    try:
        datetime.strptime(value, _INSTANT)
    except (TypeError, ValueError):
        raise ValueError("a moment is a UTC time like 2026-09-30T10:00:00Z") from None
    return value


def _digest(content: dict[str, Any]) -> str:
    return hashlib.sha256(ownership_records.canonical(content)).hexdigest()


def _newest(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The 200 newest tasks by the creation of the task record, kept in their own order."""
    if len(tasks) <= MAX_TASKS:
        return list(tasks)

    def age(index: int) -> tuple[str, int]:
        created = tasks[index].get("task", {}).get("created_at")
        return (created if isinstance(created, str) else "", index)

    keep = set(sorted(range(len(tasks)), key=age)[-MAX_TASKS:])
    return [row for index, row in enumerate(tasks) if index in keep]


def _without_journals(content: dict[str, Any]) -> dict[str, Any]:
    trimmed = copy.deepcopy(content)
    for row in trimmed.get("tasks", []):
        seen = row.get("attention")
        if isinstance(seen, dict):
            seen["journal"] = []
    return trimmed


def _is_row(row: object) -> bool:
    return isinstance(row, dict) and set(row) == _ROW_KEYS and isinstance(row["task"], dict)


def _admitted(document: object, project_id: str) -> Snapshot | None:
    if not isinstance(document, dict) or set(document) != _FILE_KEYS:
        return None
    version = document["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        return None
    tasks = document["tasks"]
    optional = (document["task_queue"], document["auto_continue"], document["quotas"])
    try:
        _instant(document["taken_at"])
    except ValueError:
        return None
    if (document["project_id"] != project_id or not isinstance(tasks, list)
            or not all(_is_row(row) for row in tasks)
            or not all(value is None or isinstance(value, dict) for value in optional)):
        return None
    return Snapshot(project_id, document["taken_at"], tasks, *optional)


class SnapshotStore:
    """The hub's snapshots of its children, and its `limits.json`, under one rule."""

    def __init__(self, folder: Path | str, *,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._folder = Path(folder)
        self._clock = clock
        #: key -> (digest of what was offered, when it was written, (mtime_ns, size) of the file)
        self._state: dict[str, tuple[str | None, float | None, tuple[int, int] | None]] = {}

    # -- reading -------------------------------------------------------------------------------

    def get(self, project_id: str) -> Snapshot | None:
        """The last snapshot of a project, or `None` when there is none or it is not the form.

        A read writes nothing: a broken file stays as it is until the next good pass.
        """
        path = self._path(_project_id(project_id))
        document = self._load(path)
        return None if document is None else _admitted(document, project_id)

    def get_limits(self) -> LimitsSnapshot | None:
        """The last `limits.json`, or `None` when it is absent or not the form the hub writes."""
        answer = HubLimitsView(self._folder / LIMITS_FILE).payload((), "2026-01-01T00:00:00Z")
        stored = answer["hub_snapshot"]
        if stored is None:
            return None
        quotas = {key: answer[key] for key in ("as_of", "max_age_seconds", "providers",
                                                "snapshots")}
        return LimitsSnapshot(stored["project_id"], stored["taken_at"], quotas)

    # -- writing -------------------------------------------------------------------------------

    def put(self, project_id: str, *, taken_at: str, tasks: list[dict[str, Any]],
            task_queue: dict[str, Any] | None, auto_continue: dict[str, Any] | None,
            quotas: dict[str, Any] | None) -> str:
        """Offer a whole good pass; `written`, `unchanged`, `too_soon`, `too_large`, `unwritable`.

        Raises:
            ValueError: `project_id` or `taken_at` is not the grammar.
        """
        _project_id(project_id)
        _instant(taken_at)
        content = {"project_id": project_id, "tasks": _newest(tasks), "task_queue": task_queue,
                   "auto_continue": auto_continue, "quotas": quotas}
        return self._publish(f"project:{project_id}", self._path(project_id), content, taken_at,
                             _without_journals)

    def put_limits(self, project_id: str, *, taken_at: str, quotas: dict[str, Any]) -> str:
        """Offer the quotas answer of the ACTIVE project by the same rule; the same results."""
        _project_id(project_id)
        _instant(taken_at)
        return self._publish("limits", self._folder / LIMITS_FILE,
                             {"project_id": project_id, "quotas": quotas}, taken_at, None)

    # -- the rule ------------------------------------------------------------------------------

    def _path(self, project_id: str) -> Path:
        return self._folder / FOLDER / f"{project_id}.json"

    @staticmethod
    def _load(path: Path) -> Any:
        try:
            if path.stat().st_size > MAX_BYTES:
                return None
            return json.loads(path.read_bytes().decode("utf-8"), parse_constant=_refuse)
        except (OSError, ValueError):
            return None

    @staticmethod
    def _signature(path: Path) -> tuple[int, int] | None:
        try:
            found = path.stat()
        except OSError:
            return None
        return found.st_mtime_ns, found.st_size

    def _known(self, key: str, path: Path) -> tuple[str | None, float | None]:
        """The digest of what the file holds and when it was last written; read again if changed."""
        held = self._state.get(key)
        signature = self._signature(path)
        if held is not None and held[2] == signature:
            return held[0], held[1]
        document = self._load(path)
        if isinstance(document, dict):
            document = {k: v for k, v in document.items()
                        if k not in ("taken_at", "schema_version")}
        digest = _digest(document) if isinstance(document, dict) else None
        return digest, (held[1] if held is not None else None)

    def _publish(self, key: str, path: Path, content: dict[str, Any], taken_at: str,
                 shrink: Callable[[dict[str, Any]], dict[str, Any]] | None) -> str:
        offered = _digest(content)
        digest, written_at = self._known(key, path)
        if digest == offered:
            return "unchanged"
        now = self._clock()
        if written_at is not None and now - written_at < MIN_INTERVAL_SECONDS:
            return "too_soon"
        payload = self._encode(content, taken_at)
        if len(payload) > MAX_BYTES and shrink is not None:
            payload = self._encode(shrink(content), taken_at)
        if len(payload) > MAX_BYTES:
            return "too_large"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_replace.replace_bytes(path, payload)
        except OSError:
            return "unwritable"
        self._state[key] = (offered, now, self._signature(path))
        return "written"

    @staticmethod
    def _encode(content: dict[str, Any], taken_at: str) -> bytes:
        document = {"schema_version": SCHEMA_VERSION, "taken_at": taken_at, **content}
        return ownership_records.canonical(document)


def _refuse(constant: str) -> Any:
    raise ValueError(f"{constant} is not JSON")
