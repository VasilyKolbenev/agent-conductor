"""Server-Sent-Events plumbing: signal frames, per-client mailboxes, the stream loop.

Extracted from `server.py` when that module neared its line cap. The mailboxes and
their registry keep the signal semantics exactly as they were; `serve_events` is the
body of the handler's `/events` arm, taking the handler it serves. This module
starts no thread and binds nothing: the server still owns the registry and the
shutdown flag the loop reads.
"""
from __future__ import annotations

import re
import threading
from typing import TYPE_CHECKING

from conductor.command.contracts import canonical_json

if TYPE_CHECKING:
    from conductor.server import Handler

SSE_WAIT = 1.0        # seconds an SSE loop waits before re-checking shutdown
MAX_PENDING_RUNS = 256
_COMMAND_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def _run_frame(run_id: str) -> bytes:
    """Serialize the sole additive command SSE signal shape."""
    if type(run_id) is not str or _COMMAND_RUN_ID.fullmatch(run_id) is None:
        raise ValueError("run signal requires a validated run id")
    return b"data: " + canonical_json(
        {"kind": "run", "run_id": run_id}).encode("utf-8") + b"\n\n"


class _Mailbox:
    """One bounded, lossless-between-drains SSE signal queue."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._state = False
        self._runs: dict[str, None] = {}

    def publish_state(self) -> None:
        with self._lock:
            self._state = True
            self._event.set()

    def publish_run(self, run_id: str) -> None:
        with self._lock:
            if len(self._runs) < MAX_PENDING_RUNS or run_id in self._runs:
                self._runs[run_id] = None
            else:
                self._state = True
            self._event.set()

    def wake(self) -> None:
        self._event.set()

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)

    def drain(self) -> tuple[bytes, ...]:
        with self._lock:
            frames = ([b'data: {"kind":"state"}\n\n'] if self._state else [])
            frames.extend(_run_frame(run_id) for run_id in self._runs)
            self._state = False
            self._runs.clear()
            self._event.clear()
            return tuple(frames)


class _Clients:
    """Registry of independent per-SSE-client bounded mailboxes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mailboxes: set[_Mailbox] = set()

    def register(self) -> _Mailbox:
        """Add one client; return its private signal mailbox."""
        mailbox = _Mailbox()
        with self._lock:
            self._mailboxes.add(mailbox)
        return mailbox

    def unregister(self, mailbox: _Mailbox) -> None:
        """Drop one client's mailbox (idempotent)."""
        with self._lock:
            self._mailboxes.discard(mailbox)

    def publish_state(self) -> None:
        """Coalesce one state signal independently for every client."""
        with self._lock:
            mailboxes = tuple(self._mailboxes)
        for mailbox in mailboxes:
            mailbox.publish_state()

    def publish_run(self, run_id: str) -> None:
        """Coalesce one identifier-only run signal for every client."""
        with self._lock:
            mailboxes = tuple(self._mailboxes)
        for mailbox in mailboxes:
            mailbox.publish_run(run_id)

    def wake_all(self) -> None:
        """Wake shutdown waiters without fabricating a frame."""
        with self._lock:
            mailboxes = tuple(self._mailboxes)
        for mailbox in mailboxes:
            mailbox.wake()


def serve_events(handler: Handler) -> None:
    """Stream SSE: one frame on connect, then one per broker change."""
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-store")
    # A stream has no length and never will, so the CLOSE is its frame and
    # this says so. Without it a client on a kept connection is entitled to
    # look for a second answer after this one, and there is no second
    # answer -- there is more of the first, until one side goes away.
    handler.send_header("Connection", "close")
    handler.close_connection = True
    handler.end_headers()
    mailbox = handler.server.clients.register()
    try:
        handler._send_frame(b'data: {"kind":"state"}\n\n')
        while not handler.server.shutting_down:
            if not mailbox.wait(timeout=SSE_WAIT):
                continue               # timeout — re-check shutdown
            if handler.server.shutting_down:
                break
            for frame in mailbox.drain():
                handler._send_frame(frame)
    except OSError:                    # incl. ConnectionAborted/Reset/BrokenPipe
        pass                           # client vanished: this loop only
    finally:
        handler.server.clients.unregister(mailbox)
