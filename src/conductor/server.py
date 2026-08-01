"""Loopback HTTP server for the Conduct panel: merge broker, routes, SSE.

`build(root, port)` returns a `ThreadingHTTPServer` bound to 127.0.0.1 that
serves the packaged panel at `/`, the merged state at `/state.json`, raw lane
files at `/lane/<author>.json`, and a Server-Sent-Events stream at `/events`.
A `Watcher` daemon thread polls `conductor/` every `POLL_INTERVAL` seconds and
re-merges every `TICK_INTERVAL` seconds regardless — lanes go stale by TIME,
not only by file change. Startup is fail-closed (missing conductor/ or a
broken map raise `store.StoreError`); *runtime* map breakage keeps serving
the last-good map with a warning.
"""
from __future__ import annotations

import copy
import importlib.resources
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from conductor import merge, store

POLL_INTERVAL = 0.5   # seconds between conductor/ fingerprint polls
TICK_INTERVAL = 60.0  # seconds between unconditional re-merges (staleness tick)
SSE_WAIT = 1.0        # seconds an SSE loop waits before re-checking shutdown


class Broker:
    """Holds the latest merged state and raw lane bytes under a lock.

    Handlers read pre-serialized, immutable bytes — no handler ever
    serializes a dict that the watcher thread is concurrently replacing;
    the broker replaces whole references under its lock instead.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.Lock()          # reader-facing swap only
        self._refresh_lock = threading.Lock()  # serializes whole refreshes
        self._comparable: dict | None = None   # last state minus generated_at
        self._state_bytes = b"{}"
        self._lane_bytes: dict[str, bytes] = {}
        self._map_data: dict | None = None     # last-good map, pinned on breakage

    def refresh(self) -> bool:
        """Re-load conductor/ and re-merge; report whether the state changed.

        The whole load→merge→compare→publish sequence runs under a refresh
        lock so concurrent callers cannot publish out of order; readers only
        contend on the inner swap lock, never on file I/O.

        Returns:
            True when the merged state differs from the previous one, with
            `generated_at` ignored (it changes on every merge).

        Raises:
            StoreError: If conductor/ vanished at runtime (the watcher
                swallows this and keeps serving the last-good state).
        """
        with self._refresh_lock:
            loaded = store.load(self._root)
            state = self._merge_loaded(loaded)
            comparable = copy.deepcopy(state)
            comparable.pop("generated_at", None)
            lane_bytes = _read_lane_bytes(store.conductor_dir(self._root))
            with self._lock:
                changed = comparable != self._comparable
                self._comparable = comparable
                self._state_bytes = json.dumps(state,
                                               ensure_ascii=False).encode("utf-8")
                self._lane_bytes = lane_bytes
            return changed

    def state_bytes(self) -> bytes:
        """Return the latest state.json payload as UTF-8 JSON bytes."""
        with self._lock:
            return self._state_bytes

    def lane_bytes(self, author: str) -> bytes | None:
        """Return the raw stored bytes for one lane, or None when absent."""
        with self._lock:
            return self._lane_bytes.get(author)

    def _merge_loaded(self, loaded: store.Loaded) -> dict:
        """Merge a snapshot, pinning the last-good map across runtime breakage."""
        map_data, map_error = loaded.map_data, loaded.map_error
        extra = list(loaded.warnings)
        if map_error is not None and self._map_data is not None:
            map_data = self._map_data      # design: keep serving the last-good map
            map_error = None
            extra.append(f"{loaded.map_error} — serving the last-good map")
        elif map_data is not None:
            self._map_data = map_data
        return merge.merge(map_data, map_error, loaded.lanes, loaded.events,
                           loaded.skipped_events, datetime.now(timezone.utc),
                           extra_warnings=extra)


def _read_lane_bytes(cdir: Path) -> dict[str, bytes]:
    """Snapshot raw lanes/*.json bytes keyed by author (valid stems only)."""
    lanes_dir = cdir / "lanes"
    out: dict[str, bytes] = {}
    if not lanes_dir.is_dir():
        return out
    for path in sorted(lanes_dir.glob("*.json")):
        if not store.AUTHOR_RE.fullmatch(path.stem):
            continue
        try:
            out[path.stem] = path.read_bytes()
        except OSError:
            continue          # vanished mid-scan; next refresh (change or tick) catches up
    return out


def _fingerprint(cdir: Path) -> tuple[tuple[str, int, int], ...]:
    """Stat every file under conductor/ into (name, mtime_ns, size) triples."""
    entries: list[tuple[str, int, int]] = []
    try:
        paths = sorted(p for p in cdir.rglob("*") if p.is_file())
    except OSError:                        # conductor/ vanished mid-walk
        return ()
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((str(path.relative_to(cdir)), stat.st_mtime_ns, stat.st_size))
    return tuple(entries)


class _Clients:
    """Registry of per-SSE-client wake events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: set[threading.Event] = set()

    def register(self) -> threading.Event:
        """Add one client; return the event its SSE loop waits on."""
        event = threading.Event()
        with self._lock:
            self._events.add(event)
        return event

    def unregister(self, event: threading.Event) -> None:
        """Drop one client's wake event (idempotent)."""
        with self._lock:
            self._events.discard(event)

    def wake_all(self) -> None:
        """Set every registered client's wake event."""
        with self._lock:
            events = list(self._events)
        for event in events:
            event.set()


class Watcher(threading.Thread):
    """Daemon thread: poll conductor/, re-merge on change or staleness tick.

    Every `POLL_INTERVAL` seconds the directory fingerprint is compared;
    every `TICK_INTERVAL` seconds a re-merge runs regardless, because lanes
    go stale purely by time. A refresh that reports change wakes all SSE
    clients.
    """

    def __init__(self, broker: Broker, cdir: Path, clients: _Clients) -> None:
        super().__init__(name="conduct-watcher", daemon=True)
        self._broker = broker
        self._cdir = cdir
        self._clients = clients
        self._stop = threading.Event()
        self._fingerprint = _fingerprint(cdir)
        self._last_merge = time.monotonic()

    def stop(self) -> None:
        """Ask the thread to exit; it wakes within POLL_INTERVAL."""
        self._stop.set()

    def run(self) -> None:
        """Poll until stopped; refresh on fingerprint change or tick."""
        while not self._stop.wait(POLL_INTERVAL):
            current = _fingerprint(self._cdir)
            tick_due = time.monotonic() - self._last_merge >= TICK_INTERVAL
            if current == self._fingerprint and not tick_due:
                continue
            self._fingerprint = current
            self._last_merge = time.monotonic()
            try:
                changed = self._broker.refresh()
            except store.StoreError:       # conductor/ vanished; keep last-good
                continue
            if changed:
                self._clients.wake_all()


class Handler(BaseHTTPRequestHandler):
    """Routes: `/` panel, `/state.json`, `/lane/<author>.json`, `/events`."""

    server: ConductServer                  # narrowed for type checkers

    def do_GET(self) -> None:              # required BaseHTTPRequestHandler name
        """Dispatch a GET to the matching `_serve_*` method, else 404."""
        path = urlsplit(self.path).path
        if path == "/":
            self._serve_panel()
        elif path == "/state.json":
            self._serve_state()
        elif path == "/events":
            self._serve_events()
        elif path.startswith("/lane/"):
            self._serve_lane(path)
        else:
            self._send_404()

    def log_message(self, format: str, *args: object) -> None:
        """Silence per-request stderr logs (they would pollute CLI and tests)."""

    def _send_body(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_404(self) -> None:
        self._send_body(404, "text/plain; charset=utf-8", b"not found\n")

    def _serve_panel(self) -> None:
        panel = importlib.resources.files("conductor") / "panel" / "index.html"
        self._send_body(200, "text/html; charset=utf-8", panel.read_bytes())

    def _serve_state(self) -> None:
        self._send_body(200, "application/json; charset=utf-8",
                        self.server.broker.state_bytes())

    def _serve_lane(self, path: str) -> None:
        # Security-load-bearing: parse the segment, regex it, then look up the
        # broker's cache — URL input never touches a filesystem path.
        name = path[len("/lane/"):]
        if not name.endswith(".json"):
            self._send_404()
            return
        author = name[: -len(".json")]
        if not store.AUTHOR_RE.fullmatch(author):   # excludes / \ . % .. by charset
            self._send_404()
            return
        body = self.server.broker.lane_bytes(author)
        if body is None:
            self._send_404()
            return
        self._send_body(200, "application/json; charset=utf-8", body)

    def _serve_events(self) -> None:
        """Stream SSE: one frame on connect, then one per broker change."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        wake = self.server.clients.register()
        try:
            self._send_frame()             # greeting: de-flakes registration race
            while not self.server.shutting_down:
                if not wake.wait(timeout=SSE_WAIT):
                    continue               # timeout — re-check shutdown
                wake.clear()
                if self.server.shutting_down:
                    break
                self._send_frame()
        except OSError:                    # incl. ConnectionAborted/Reset/BrokenPipe
            pass                           # client vanished: this loop only
        finally:
            self.server.clients.unregister(wake)

    def _send_frame(self) -> None:
        self.wfile.write(b'data: {"kind":"state"}\n\n')
        self.wfile.flush()


class ConductServer(ThreadingHTTPServer):
    """ThreadingHTTPServer wiring the broker, watcher and SSE registry."""

    daemon_threads = True  # SSE handler threads must never block process exit
    # On Windows, SO_REUSEADDR lets a second bind HIJACK a live port instead
    # of failing EADDRINUSE — keep it off there so `up` on a busy port exits
    # 1 (design: startup failure). POSIX keeps it for TIME_WAIT-free restarts.
    allow_reuse_address = os.name != "nt"

    def __init__(self, address: tuple[str, int], root: Path, cdir: Path) -> None:
        # Attributes first: a failed bind makes socketserver call our
        # server_close() before __init__ finishes.
        self.shutting_down = False
        self.broker = Broker(root)
        self.clients = _Clients()
        self.watcher = Watcher(self.broker, cdir, self.clients)
        super().__init__(address, Handler)  # binds; EADDRINUSE raises here
        self.broker.refresh()               # initial state before serving
        self.watcher.start()

    def shutdown(self) -> None:
        """Stop serve_forever and wake all SSE loops so they exit promptly."""
        self.shutting_down = True
        self.clients.wake_all()
        super().shutdown()

    def server_close(self) -> None:
        """Stop and join the watcher, wake SSE loops, close the socket."""
        self.shutting_down = True
        self.clients.wake_all()
        self.watcher.stop()
        if self.watcher.is_alive():        # never started on a failed bind
            self.watcher.join(timeout=POLL_INTERVAL * 2)
        super().server_close()

    def handle_error(self, request: object, client_address: object) -> None:
        """Silence client aborts (panel refreshes, closed tabs); keep the rest.

        A vanished client raises ConnectionError past the handler into
        ThreadingMixIn — the default prints a 40-dash traceback to stderr.
        """
        if isinstance(sys.exc_info()[1], ConnectionError):  # sys.exception() is 3.12+
            return
        super().handle_error(request, client_address)


def build(root: Path | str, port: int) -> ConductServer:
    """Build the loopback panel server (fail-closed startup).

    Args:
        root: The project root (the directory that contains `conductor/`).
        port: TCP port to bind on 127.0.0.1; 0 lets the OS assign one.

    Returns:
        A `ConductServer` ready for `serve_forever()`; its watcher thread
        is already running. Bound to 127.0.0.1 only, never 0.0.0.0.

    Raises:
        StoreError: If `root` has no conductor/ directory, or map.toml is
            broken at startup. Runtime map breakage instead degrades to the
            last-good map plus a warning in `state.json`.
        OSError: If the port cannot be bound.
    """
    cdir = store.conductor_dir(root)
    loaded = store.load(root)
    if loaded.map_error is not None:
        raise store.StoreError(f"refusing to start: {loaded.map_error}")
    return ConductServer(("127.0.0.1", port), Path(root), cdir)
