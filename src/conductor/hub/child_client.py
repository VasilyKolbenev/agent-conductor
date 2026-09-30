"""The hub's only door to a child: GET, from one table (spec 4.1.9, 4.5.6, L10).

`CHILD_READS` is the table of 4.5.6 verbatim: the routes the hub may read from a child in `active`
or in `view`, when, and why. `ChildClient` has one method, `get`, and it refuses any path outside
the table before a byte is sent; there is no other verb in this module and no token of the child's
to send (the hub holds no CSRF of a child). Every read carries the child's own `Host` and the
claim `X-Conduct-Project: <project id of the registry>`; a read is bounded at 10 s and 8 MiB, and
one that exceeds either is a failed read.

`read_cycle` is one pass of the summary over one child, in the order of 4.5.6: identity first (a
child that is another project, or another hub's, or in another mode, stops the pass with no data),
then the tasks, the runs, the automation of the newest run of each task, the run itself only for a
row that needs a person and changed since the last pass, the task queue and the continue-after flag
(a `404` on either is `null`, not an error) and the quotas. A read that fails beyond that is named
in `failures`: the pass is still read, but it is not complete, and an incomplete pass is never
"free" and never becomes a snapshot. `ChildEvents` follows a child's `/events` as a signal and
nothing more: no frame's content is read.
"""
from __future__ import annotations

import http.client
import json
import re
import socket
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, NamedTuple

TIMEOUT_SECONDS = 10.0
MAX_BYTES = 8 * 1024 * 1024
HEADER = "X-Conduct-Project"
PAUSE_FIRST, PAUSE_LAST = 1.0, 30.0
EVENTS_PATH = "/events"
_CHUNK = 64 * 1024
_POLL_SECONDS = 1.0
_MAX_EVENT_BYTES = 1024 * 1024
_RUN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"


class ChildRead(NamedTuple):
    """One row of the table: a method, a path, when it is read and why."""

    method: str
    path: str
    when: str
    why: str


CHILD_READS: tuple[ChildRead, ...] = (
    ChildRead("GET", "/command/project", "first in every cycle", "identity and mode"),
    ChildRead("GET", "/command/tasks", "every cycle", "the tasks of the column"),
    ChildRead("GET", "/command/runs", "every cycle", "the rows of the runs as they are"),
    ChildRead("GET", "/command/runs/<run_id>/automation", "the newest run of each task",
              "state, reason code and expiry of the grant"),
    ChildRead("GET", "/command/runs/<run_id>",
              "only a row with human_state required that changed since the last read",
              "the gate, the reasons and the journal for the time a person has waited"),
    ChildRead("GET", "/command/queue", "every cycle",
              "the task queue and the slot; a 404 is null"),
    ChildRead("GET", "/command/project/auto-continue", "every cycle",
              "the continue-after flag; a 404 is null"),
    ChildRead("GET", "/command/quotas", "every cycle", "the limits"),
    ChildRead("GET", EVENTS_PATH, "all the time, one stream per running child",
              "only a signal to read again"),
)
_GET_PATTERNS = tuple(re.compile(row.path.replace("<run_id>", _RUN))
                      for row in CHILD_READS if row.path != EVENTS_PATH)
_RUN_ID = re.compile(_RUN)


class ChildReadFailed(Exception):
    """A read that gave no answer: `reason` is `unreachable`, `timeout`, `too_large`, `not_json`."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class Answer:
    """What a child answered: its status and the decoded JSON (`None` for a refusal not in JSON)."""

    status: int
    body: Any


def _decode(raw: bytes, status: int) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as error:                   # incl. UnicodeDecodeError
        if status == 200:
            raise ChildReadFailed("not_json") from error
        return None


def _fetch(connection: http.client.HTTPConnection, path: str, port: int, project_id: str,
           deadline: float) -> Answer:
    connection.putrequest("GET", path, skip_host=True, skip_accept_encoding=True)
    connection.putheader("Host", f"127.0.0.1:{port}")
    connection.putheader(HEADER, project_id)
    connection.putheader("Accept", "application/json")
    connection.endheaders()
    response = connection.getresponse()
    raw = bytearray()
    while len(raw) <= MAX_BYTES:
        chunk = response.read(_CHUNK)
        if not chunk:
            break
        raw += chunk
        if time.monotonic() > deadline:
            raise TimeoutError("the child answered too slowly")
    if len(raw) > MAX_BYTES:
        raise ChildReadFailed("too_large")
    return Answer(response.status, _decode(bytes(raw), response.status))


class ChildClient:
    """One child, read by GET and by nothing else."""

    __slots__ = ("_port", "_project_id", "_timeout")

    def __init__(self, port: int, project_id: str, *, timeout: float = TIMEOUT_SECONDS) -> None:
        self._port, self._project_id, self._timeout = port, project_id, timeout

    @property
    def port(self) -> int:
        return self._port

    @property
    def project_id(self) -> str:
        return self._project_id

    def get(self, path: str) -> Answer:
        """Read one route of the table from the child.

        Raises:
            ValueError: `path` is not a route of `CHILD_READS` (nothing is sent).
            ChildReadFailed: The child did not answer in time, was not reachable, sent more than
                8 MiB, or answered 200 with something that is not JSON.
        """
        if not any(pattern.fullmatch(path) for pattern in _GET_PATTERNS):
            raise ValueError(f"{path!r} is not a read of the hub's table")
        deadline = time.monotonic() + self._timeout
        connection = http.client.HTTPConnection("127.0.0.1", self._port, timeout=self._timeout)
        try:
            return _fetch(connection, path, self._port, self._project_id, deadline)
        except TimeoutError as error:
            raise ChildReadFailed("timeout") from error
        except (OSError, http.client.HTTPException) as error:
            raise ChildReadFailed("unreachable") from error
        finally:
            connection.close()


# -- one cycle --------------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskRead:
    """One task of a cycle: its row, its newest run, that run's automation and its run read."""

    task: dict[str, Any]
    run: dict[str, Any] | None
    automation: dict[str, Any] | None
    detail: dict[str, Any] | None = None
    detail_failed: bool = False


@dataclass(frozen=True)
class Cycle:
    """The result of one pass over one child.

    `verdict` is `live`, `identity_mismatch`, `busy_elsewhere` or `unreadable`. `failures` names
    the reads that failed beyond a `404` of an optional one. `memory` is what the next pass needs
    to read a run only when its row changed: `run_id -> (row, run read)`.
    """

    verdict: str
    project: dict[str, Any] | None = None
    tasks: tuple[TaskRead, ...] = ()
    queue: dict[str, Any] | None = None
    auto_continue: dict[str, Any] | None = None
    quotas: dict[str, Any] | None = None
    failures: tuple[str, ...] = ()
    memory: Mapping[str, tuple[dict[str, Any], dict[str, Any] | None]] = field(
        default_factory=lambda: MappingProxyType({}))

    @property
    def complete(self) -> bool:
        """Whether every read of the pass was answered: the only pass a snapshot may come from."""
        return self.verdict == "live" and not self.failures


class _Failed(Exception):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)


def _get(client: ChildClient, path: str, name: str, *, optional: bool = False
         ) -> dict[str, Any] | None:
    try:
        answer = client.get(path)
    except ChildReadFailed as failed:
        raise _Failed(name) from failed
    if optional and answer.status == 404:
        return None
    if answer.status != 200 or not isinstance(answer.body, dict):
        raise _Failed(name)
    return answer.body


def _list(client: ChildClient, path: str, key: str) -> list[Any]:
    found = _get(client, path, key)
    value = None if found is None else found.get(key)
    if not isinstance(value, list):
        raise _Failed(key)
    return value


def _identity(client: ChildClient, hub_origin: str, mode: str) -> tuple[dict | None, str]:
    """`(the four keys, "live")`, or `(None, the verdict that stops the pass)`."""
    try:
        answer = client.get("/command/project")
    except ChildReadFailed as failed:
        raise _Failed("project") from failed
    if answer.status == 409:
        return None, "identity_mismatch"
    body = answer.body
    if answer.status != 200 or not isinstance(body, dict):
        raise _Failed("project")
    if body.get("project_id") != client.project_id:
        return None, "identity_mismatch"
    if body.get("hub_origin") != hub_origin or body.get("mode") != mode:
        return None, "busy_elsewhere"
    return body, "live"


def _newest(runs: list[Any]) -> dict[str, dict[str, Any]]:
    """The newest readable run of each task, by `created_at` then `run_id`."""
    newest: dict[str, dict[str, Any]] = {}
    for row in runs:
        if not isinstance(row, dict) or row.get("unreadable") or not isinstance(
                row.get("task_id"), str) or not isinstance(row.get("created_at"), str):
            continue
        held = newest.get(row["task_id"])
        if held is None or (row["created_at"], str(row.get("run_id"))) > (
                held["created_at"], str(held.get("run_id"))):
            newest[row["task_id"]] = row
    return newest


def _automation(client: ChildClient, run: dict[str, Any] | None,
                failures: list[str]) -> dict[str, Any] | None:
    run_id = None if run is None else run.get("run_id")
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        return None
    try:
        body = _get(client, f"/command/runs/{run_id}/automation", "automation")
    except _Failed:
        failures.append("automation")
        return None
    return {key: body.get(key) for key in ("state", "reason_code", "expires_at")}


def _detail(client: ChildClient, run: dict[str, Any] | None, previous: Mapping[str, Any]
            ) -> tuple[dict[str, Any] | None, bool]:
    """`(the run read, failed)`; read only for a row that needs a person and changed."""
    if run is None or run.get("unreadable") or run.get("human_state") != "required":
        return None, False
    run_id = run.get("run_id")
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        return None, True
    before = previous.get(run_id)
    if before is not None and before[0] == run and before[1] is not None:
        return before[1], False
    try:
        return _get(client, f"/command/runs/{run_id}", "run"), False
    except _Failed:
        return None, True


def _task_reads(client: ChildClient, tasks: list[Any], runs: list[Any],
                previous: Mapping[str, Any], failures: list[str]
                ) -> tuple[tuple[TaskRead, ...], dict[str, tuple]]:
    newest, reads, memory = _newest(runs), [], {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("task_id")
        run = newest.get(task_id) if isinstance(task_id, str) else None
        automation = _automation(client, run, failures)
        detail, failed = _detail(client, run, previous)
        if run is not None and run.get("human_state") == "required":
            memory[run["run_id"]] = (run, detail)
        reads.append(TaskRead(task, run, automation, detail, failed))
    return tuple(reads), memory


def _optional(client: ChildClient, path: str, name: str, failures: list[str]
              ) -> dict[str, Any] | None:
    try:
        return _get(client, path, name, optional=True)
    except _Failed:
        failures.append(name)
        return None


def read_cycle(client: ChildClient, *, hub_origin: str, mode: str,
               previous: Mapping[str, Any] | None = None) -> Cycle:
    """One pass of the reads of 4.5.6 over one child.

    Args:
        client: The child's client (its port and the registry's project id).
        hub_origin: This hub's own origin; a child with another one is `busy_elsewhere`.
        mode: The mode the hub started the child in; a child in another one is `busy_elsewhere`.
        previous: `Cycle.memory` of the last pass, so a run is read again only when its row changed.
    """
    failures: list[str] = []
    try:
        project, verdict = _identity(client, hub_origin, mode)
        if project is None:
            return Cycle(verdict)
        tasks = _list(client, "/command/tasks", "tasks")
        runs = _list(client, "/command/runs", "runs")
    except _Failed as failed:
        return Cycle("unreadable", failures=(failed.name,))
    reads, memory = _task_reads(client, tasks, runs, previous or {}, failures)
    queue = _optional(client, "/command/queue", "queue", failures)
    flag = _optional(client, "/command/project/auto-continue", "auto_continue", failures)
    try:
        quotas = _get(client, "/command/quotas", "quotas")
    except _Failed:
        quotas = None
        failures.append("quotas")
    return Cycle("live", project, reads, queue, flag, quotas,
                 tuple(dict.fromkeys(failures)), MappingProxyType(memory))


# -- the stream ---------------------------------------------------------------------------------


def next_pause(previous: float | None) -> float:
    """The pause before a reconnect: 1 s, then doubled up to 30 s (4.5.6)."""
    return PAUSE_FIRST if previous is None else min(PAUSE_LAST, previous * 2)


class ChildEvents:
    """A child's `/events` followed as a signal: any frame means "read again"; none is read."""

    def __init__(self, port: int, project_id: str, on_signal: Callable[[], object], *,
                 sleep: Callable[[float], object] | None = None,
                 timeout: float = TIMEOUT_SECONDS,
                 connect: Callable[..., socket.socket] = socket.create_connection) -> None:
        self._port, self._project_id, self._on_signal = port, project_id, on_signal
        self._sleep, self._timeout, self._connect = sleep, timeout, connect

    def follow(self, stop: threading.Event) -> None:
        """Connect, signal on every frame, and reconnect after a pause, until `stop` is set."""
        pause: float | None = None
        wait = stop.wait if self._sleep is None else self._sleep
        while not stop.is_set():
            got = self._once(stop)
            if stop.is_set():
                return
            pause = next_pause(None if got else pause)
            wait(pause)

    def _request(self) -> bytes:
        lines = (f"GET {EVENTS_PATH} HTTP/1.1", f"Host: 127.0.0.1:{self._port}",
                 f"{HEADER}: {self._project_id}", "Accept: text/event-stream",
                 "Connection: close", "", "")
        return "\r\n".join(lines).encode("ascii")

    def _once(self, stop: threading.Event) -> bool:
        """One connection; whether it delivered at least one frame."""
        try:
            sock = self._connect(("127.0.0.1", self._port), timeout=self._timeout)
        except OSError:
            return False
        try:
            sock.sendall(self._request())
            return self._read(sock, stop)
        except OSError:
            return False
        finally:
            sock.close()

    def _read(self, sock: socket.socket, stop: threading.Event) -> bool:
        sock.settimeout(_POLL_SECONDS)
        buffer, got, opened = b"", False, False
        while not stop.is_set():
            try:
                chunk = sock.recv(4096)
            except TimeoutError:
                continue
            if not chunk:
                return got
            buffer += chunk
            if len(buffer) > _MAX_EVENT_BYTES:
                return got
            if not opened:
                head, separator, buffer = buffer.partition(b"\r\n\r\n")
                if not separator:
                    buffer = head
                    continue
                if not head.startswith(b"HTTP/1.1 200"):
                    return got
                opened = True
            events = buffer.split(b"\n\n")
            buffer = events.pop()
            for event in events:
                if any(line.startswith(b"data:") for line in event.split(b"\n")):
                    got = True
                    self._on_signal()
        return got
