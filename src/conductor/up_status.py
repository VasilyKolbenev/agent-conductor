"""The child's status file: `<conduct-home>/run/<project_id>.json` (spec 4.1.4).

Only the server process of a hub child writes it, and every write replaces the
whole file (`atomic_replace`). It carries one state of the process at a time:
`starting`, `serving`, `stopping`, `stop_overdue`, `stopped`, `stop_uncertain` or
`refused`, with the code of a refusal and the drain deadline once one exists, and
the moment the process started (`process_identity`), which together with the pid
is the process's identity. `read_status` is what the hub reads it back with:
strict to the last key, typed, and `None` for a file that is not there.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from conductor import atomic_replace, process_identity, up_flags

SCHEMA_VERSION = 1
#: The closed list of the states of a child (4.1.4), in the order its life goes through them.
STATES = ("starting", "serving", "stopping", "stop_overdue", "stopped", "stop_uncertain",
          "refused")
MAX_BYTES = 64 * 1024
_KEYS = frozenset({"schema_version", "project_id", "pid", "process_started", "port", "mode",
                   "state", "code", "drain_deadline", "updated_at"})
_PROJECT_ID = re.compile(r"[0-9a-f]{32}")
_STARTED = re.compile(r"windows:\d+|linux:[0-9a-f-]{36}:\d+|darwin:\d+\.\d{6}")
_INSTANT = "%Y-%m-%dT%H:%M:%SZ"


def _instant(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(_INSTANT)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _started_of(pid: int) -> str | None:
    """When `pid` started, or `None`: a process that cannot be read records no start."""
    try:
        return process_identity.started_of(pid)
    except (process_identity.IdentityUnreadable, ValueError):
        return None


class NullStatus:
    """The status of a process started without `--status-file`: it records nothing."""

    def write(self, state: str, **fields: object) -> None:
        """Accept a state change and drop it."""


class StatusFile:
    """One process's status record, rewritten whole at every change of state."""

    def __init__(self, path: Path | str, project_id: str, mode: str, port: int, *,
                 clock: Callable[[], datetime] = _now, pid: int | None = None) -> None:
        self.path = Path(path)
        self._identity = {"project_id": project_id, "mode": mode}
        self._port = port
        self._deadline: str | None = None
        self._clock = clock
        self._pid = os.getpid() if pid is None else pid
        self._started = _started_of(self._pid)

    def write(self, state: str, *, code: str | None = None, port: int | None = None,
              drain_deadline: datetime | None = None) -> None:
        """Publish `state`; a port or deadline given once is kept by later writes.

        Args:
            state: The process state to record.
            code: The refusal code, for `refused` only.
            port: The bound port, once it is known.
            drain_deadline: The end of the drain, once step 4 has computed it.

        Raises:
            OSError: The record could not be published.
        """
        if port is not None:
            self._port = port
        if drain_deadline is not None:
            self._deadline = _instant(drain_deadline)
        record = {
            "schema_version": SCHEMA_VERSION, "project_id": self._identity["project_id"],
            "pid": self._pid, "process_started": self._started, "port": self._port,
            "mode": self._identity["mode"], "state": state, "code": code,
            "drain_deadline": self._deadline, "updated_at": _instant(self._clock())}
        payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_replace.replace_bytes(self.path, payload.encode("utf-8"))


# -- the reader ------------------------------------------------------------------------------


class StatusInvalid(ValueError):
    """A status file that is not the record: the text names the file and what is wrong."""


@dataclass(frozen=True)
class StatusRecord:
    """A status file, read back: times are aware UTC `datetime`s, the rest as written."""

    project_id: str
    pid: int
    process_started: str | None
    port: int
    mode: str
    state: str
    code: str | None
    drain_deadline: datetime | None
    updated_at: datetime


def _time(value: object, what: str, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    try:
        if not isinstance(value, str):
            raise ValueError("not text")
        return datetime.strptime(value, _INSTANT).replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(f"{what} must be a UTC time like 2026-09-29T12:00:00Z") from None


def _whole(value: object, low: int, high: int, what: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{what} must be a whole number from {low} to {high}")
    return value


def _shape(document: object) -> dict:
    if not isinstance(document, dict) or set(document) != _KEYS:
        raise ValueError("must be an object with exactly the keys of the status record")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ValueError(f"schema_version must be the number {SCHEMA_VERSION}")
    return document


def _record(document: dict) -> StatusRecord:
    project_id, started = document["project_id"], document["process_started"]
    if not (isinstance(project_id, str) and _PROJECT_ID.fullmatch(project_id)):
        raise ValueError("project_id must be 32 lowercase hex characters")
    if started is not None and not (isinstance(started, str) and _STARTED.fullmatch(started)):
        raise ValueError("process_started must be null or the spelling of an OS")
    state, code = document["state"], document["code"]
    if document["mode"] not in up_flags.MODES or state not in STATES:
        raise ValueError("mode or state is not one of the closed lists")
    if (state == "refused") != (code is not None) or (
            code is not None and code not in up_flags.START_CODES):
        raise ValueError("a code goes with `refused` and is one of the start codes")
    return StatusRecord(
        project_id, _whole(document["pid"], 1, 2**31 - 1, "pid"), started,
        _whole(document["port"], 0, 65535, "port"), document["mode"], state, code,
        _time(document["drain_deadline"], "drain_deadline", optional=True),
        _time(document["updated_at"], "updated_at"))


def _strict_json(text: str) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict:
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("a key appears twice")
        return dict(pairs)

    def refuse(constant: str) -> object:
        raise ValueError(f"{constant} is not JSON")

    return json.loads(text, object_pairs_hook=unique, parse_constant=refuse)


def read_status(path: Path | str) -> StatusRecord | None:
    """Read one status file; `None` when it is not there.

    Raises:
        StatusInvalid: The file is there and is not the record (or cannot be read); the file
            is left as it is.
    """
    target = Path(path)
    try:
        data = atomic_replace.read_bytes(target)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise StatusInvalid(f"{target.name} cannot be read: {error}") from error
    try:
        if len(data) > MAX_BYTES:
            raise ValueError(f"is larger than {MAX_BYTES // 1024} KiB")
        return _record(_shape(_strict_json(data.decode("utf-8"))))
    except (UnicodeError, ValueError) as error:
        raise StatusInvalid(f"{target.name} is not the status record: {error}") from error
