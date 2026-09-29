"""Stop a server by draining it (spec 4.1.6): nothing new starts, what runs finishes.

A hub child stops when its stdin reaches end of file; a standalone `conduct up`
stops on Ctrl+C. Both set ONE event, and the main thread, which waits for it in
short slices so Ctrl+C can be heard on every OS, then calls `drain_and_close`
once. `serve_forever` runs in the thread `conduct-http` and the stdin watcher is
the thread `conduct-stdin`.

The eight steps, in the order the spec gives them: the server refuses every
command POST and the status file says `stopping`; the policy driver is told to
start nothing new (in memory: a written pause would forge a human decision); the
quota collector stops and its running poll finishes; the deadline is the latest
open attempt's reservation plus a margin, or ten seconds when none is open; the
drain waits for the execution workers; only then are the server and its owner
closed, and `stopped` is written; a deadline that passes is `stop_overdue`, a
state and not an exit; a retirement that cannot be proved is `stop_uncertain`,
exit 1, and the owner is not released, so no `closed` is ever written early.
"""
from __future__ import annotations

import os
import signal
import sys
import threading
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

#: Added to the end of the latest open attempt's reservation to make the deadline.
DRAIN_MARGIN_SECONDS = 60
#: The deadline of a drain that finds no open attempt, counted from now.
IDLE_DEADLINE_SECONDS = 10
#: How long the main thread waits at a time; a Ctrl+C is heard between two slices.
WAIT_SLICE_SECONDS = 0.5
_READ_BYTES = 4096


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Stopper:
    """The one event both ways of stopping set: end of file on stdin, and Ctrl+C."""

    def __init__(self) -> None:
        self.event = threading.Event()

    def watch_stdin(self, descriptor: int) -> None:
        """Start the `conduct-stdin` thread: it sets the event when stdin ends.

        The hub writes nothing into the pipe, so any bytes are ignored; end of
        file, or a descriptor that cannot be read, is the hub being gone. It reads
        the raw descriptor, not the buffered `sys.stdin`, so a daemon thread still
        blocked at interpreter exit holds no buffer lock.
        """
        watcher = threading.Thread(target=self._read_until_end, args=(descriptor,),
                                   name="conduct-stdin", daemon=True)
        watcher.start()

    def _read_until_end(self, descriptor: int) -> None:
        try:
            while os.read(descriptor, _READ_BYTES):
                pass
        except (OSError, ValueError):
            pass
        self.event.set()


class _Notice:
    """What a second Ctrl+C prints: how long the drain may take. Filled at step 4."""

    def __init__(self) -> None:
        self.deadline: datetime | None = None

    def report(self, signum, frame) -> None:
        when = ("the deadline is not set yet" if self.deadline is None else
                f"until {self.deadline.astimezone(timezone.utc):%H:%M:%S} UTC")
        print(f"conduct up: draining, {when}; Ctrl+C does not interrupt it", file=sys.stderr)


@contextmanager
def _absorbing_interrupts(notice: _Notice):
    """Answer Ctrl+C with the deadline instead of an exception, for the whole drain."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.signal(signal.SIGINT, notice.report)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT,
                      previous if previous is not None else signal.default_int_handler)


def serve_until_stopped(srv, status, stopper: Stopper, *,
                        clock: Callable[[], datetime] = _utcnow) -> int:
    """Serve on `conduct-http` until the stop event, then drain and close.

    Args:
        srv: The bound server.
        status: Where state changes are written (`up_status`).
        stopper: The event that end of file on stdin or Ctrl+C sets.
        clock: The current time; a parameter so a test can move it.

    Returns:
        0 for a proven stop, 1 for `stop_uncertain`.
    """
    http = threading.Thread(target=_serve_http, args=(srv, stopper), name="conduct-http",
                            daemon=True)
    http.start()
    try:
        while not stopper.event.wait(WAIT_SLICE_SECONDS):
            if not http.is_alive():
                break                       # a serve loop that ended by itself is a stop
    except KeyboardInterrupt:
        stopper.event.set()
    notice = _Notice()
    with _absorbing_interrupts(notice):
        return drain_and_close(srv, status, clock=clock, notice=notice)


def _serve_http(srv, stopper: Stopper) -> None:
    try:
        srv.serve_forever()
    finally:
        stopper.event.set()


def drain_and_close(srv, status, *, clock: Callable[[], datetime] = _utcnow,
                    notice: _Notice | None = None) -> int:
    """Steps 1-8 of the drain; see the module docstring.

    Returns:
        0 when the server and its owner were closed with proof, 1 otherwise.
    """
    srv.draining = True
    _report(status, "stopping")
    _hold_and_quiet(srv)
    deadline = drain_deadline(getattr(srv, "command_store", None), clock())
    if notice is not None:
        notice.deadline = deadline
    _report(status, "stopping", drain_deadline=deadline)
    _wait_for_idle(srv, status, deadline, clock)
    return _close(srv, status)


def _report(status, state: str, **fields) -> None:
    """Write a state change; a status file that cannot take it never stops the drain."""
    try:
        status.write(state, **fields)
    except OSError as error:
        print(f"conduct up: status file not written ({state}): {error}", file=sys.stderr)


def _attempt(srv, step: str, call: Callable[[], object]) -> None:
    """Run one step; an exception leaves the retirement unproven, and the drain goes on."""
    try:
        call()
    except Exception as error:
        srv.retirement_uncertain = True
        print(f"conduct up: stop uncertain: {step}: {error}", file=sys.stderr)


def _hold_and_quiet(srv) -> None:
    """Steps 2 and 3: no new work, no new quota poll. Absent in `view`, where there is none."""
    driver = getattr(srv, "policy_driver", None)
    if driver is not None:
        _attempt(srv, "hold_new_work", driver.hold_new_work)
    collector = getattr(srv, "quota_collector", None)
    if collector is not None:
        _attempt(srv, "quota_collector.stop", collector.stop)


def _wait_for_idle(srv, status, deadline: datetime, clock: Callable[[], datetime]) -> None:
    """Step 5, and step 7: past the deadline the state changes and the wait goes on."""
    execution = getattr(srv, "command_execution", None)
    overdue = False
    while execution is not None and not execution.wait_idle(WAIT_SLICE_SECONDS):
        if not overdue and clock() > deadline:
            overdue = True
            _report(status, "stop_overdue", drain_deadline=deadline)


def _close(srv, status) -> int:
    """Steps 6 and 8: close the server and release the owner, or say that it is unproven."""
    _attempt(srv, "shutdown", srv.shutdown)
    _attempt(srv, "server_close", srv.server_close)
    if getattr(srv, "retirement_uncertain", False):
        _report(status, "stop_uncertain")
        return 1
    _report(status, "stopped")
    return 0


def drain_deadline(store, now: datetime) -> datetime:
    """Step 4: the latest open attempt's reservation plus the margin, else `now` plus ten seconds.

    Args:
        store: The project's run store, or None.
        now: The current time.
    """
    ends = []
    for run_id in _run_ids(store):
        ends.extend(open_attempt_ends(_values(store, run_id)))
    if not ends:
        return now + timedelta(seconds=IDLE_DEADLINE_SECONDS)
    return max(ends) + timedelta(seconds=DRAIN_MARGIN_SECONDS)


def _run_ids(store) -> tuple[str, ...]:
    if store is None:
        return ()
    from conductor.command.studio_routes import run_ids     # deferred: a heavy package
    return run_ids(store)


def _values(store, run_id: str) -> tuple[object, ...]:
    """The record values of one run; a run that cannot be read counts no attempt."""
    from conductor.command.contract_values import ContractError
    from conductor.command.store_errors import StoreError
    try:
        return tuple(row.value for row in store.read(run_id).records)
    except (StoreError, ContractError):
        return ()


def open_attempt_ends(values: tuple[object, ...]) -> list[datetime]:
    """When each open attempt's reservation ends: requested_at plus what it reserved.

    An attempt is open while its ActionRequest has no result receipt. A step with
    an independent checker reserves its time twice; a request that names no plan
    node reserves its own timeout.
    """
    from conductor.command.contracts import ActionRequest, ActionResultReceipt
    from conductor.command.policy_history import request_reservation
    from conductor.command.contract_values import ContractError
    settled = {v.action_id for v in values if type(v) is ActionResultReceipt}
    definition = next((v for v in values if type(v).__name__ == "GraphDefinition"), None)
    ends = []
    for request in values:
        if type(request) is not ActionRequest or request.action_id in settled:
            continue
        try:
            reserved = request_reservation(request, definition)
        except (ContractError, AttributeError):
            reserved = request.timeout_seconds
        started = datetime.fromisoformat(request.requested_at.replace("Z", "+00:00"))
        ends.append(started + timedelta(seconds=reserved))
    return ends


def enable_ctrl_c(*, set_handler: Callable[[object, bool], object] | None = None,
                  windows: bool | None = None) -> None:
    """On Windows, stop ignoring Ctrl+C: a harness or a GUI child inherits "ignore".

    `SetConsoleCtrlHandler(NULL, FALSE)`, called by a standalone `up` at start. A
    hub child has no console and does not call it. Best effort: a process with no
    console has no Ctrl+C to enable.
    """
    if not (os.name == "nt" if windows is None else windows):
        return
    (set_handler or _set_console_ctrl_handler)(None, False)


def _set_console_ctrl_handler(handler, add: bool) -> None:
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wintypes.BOOL]
    kernel.SetConsoleCtrlHandler.restype = wintypes.BOOL
    kernel.SetConsoleCtrlHandler(handler, add)
