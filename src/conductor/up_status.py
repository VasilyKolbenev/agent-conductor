"""The child's status file: `<conduct-home>/run/<project_id>.json` (spec 4.1.4).

Only the server process of a hub child writes it, and every write replaces the
whole file (`atomic_replace`). It carries one state of the process at a time:
`starting`, `serving`, `stopping`, `stop_overdue`, `stopped`, `stop_uncertain` or
`refused`, with the code of a refusal and the drain deadline once one exists.
`process_started` stays `null` until `process_identity` lands; the key is here so
the record already has the spec's shape.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from conductor import atomic_replace

SCHEMA_VERSION = 1


def _instant(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
            "pid": self._pid, "process_started": None, "port": self._port,
            "mode": self._identity["mode"], "state": state, "code": code,
            "drain_deadline": self._deadline, "updated_at": _instant(self._clock())}
        payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_replace.replace_bytes(self.path, payload.encode("utf-8"))
