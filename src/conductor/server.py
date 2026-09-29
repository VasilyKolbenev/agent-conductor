"""Loopback HTTP server for the Conduct panel: merge broker, routes, SSE.

`build(root, port)` returns a `ThreadingHTTPServer` bound to 127.0.0.1 that
serves the packaged Workflow Studio shell at `/` (the classic panel keeps its
own file name and is served at `/panel/index.html`), the merged state at
`/state.json`, the
bundled harness registry at `/harnesses.json`, raw lane files at
`/lane/<author>.json`, deterministic packets at `/handoff/<author>.md`, and a
Server-Sent-Events stream at `/events`.

Every one of those reads answers only the two exact `Host` values this process
minted for its bound port — `127.0.0.1:<port>` and `localhost:<port>` — and
refuses any other name before dispatch. Loopback binding keeps a stranger's
packet off the socket but says nothing about whose page sent it, and a page
that re-resolves its own name to loopback would otherwise read the whole
merged project from its own origin.

`/harnesses.json` is a *presentation* route and not part of Protocol v1. It
answers with `harnesses.as_payload()` — the same bytes for every project,
computed from the bundled registry and never from the merge — so the panel can
draw a harness as a product rather than as a slug. `state.json` is unchanged by
its existence, and a panel that never receives it stays fully usable with
neutral badges.

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
import secrets
import socketserver
import sys
import threading
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from conductor import harnesses, merge, project_identity, report, store
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.provider import ProviderConfig, ProviderConfigError
from conductor.command.api_contracts import ApiRefusal
from conductor.command.contracts import canonical_json
from conductor.command.coordinator import ExecutionCoordinator
from conductor.command.http_api import (
    PRODUCT_COMMAND_BUDGET,
    CommandApi,
)
from conductor.command.http_transport import (
    CommandSession, HttpRefusal, validate_command_host)
#: Re-exported deliberately: `IDLE_CONNECTION_SECONDS` is a fact about THIS
#: server that callers and guards read off it, and moving where it is
#: written did not move what it is about.
from conductor.http_framing import IDLE_CONNECTION_SECONDS, KeptConnection
from conductor.command.providers import ProviderResolution, resolve_providers
from conductor.command.run_store import RunStore
from conductor.command.runtime import Budget
from conductor.command.quota_service import QuotaService
from conductor.quota_collectors import QuotaCollector
#: Re-exported deliberately: tests and `scripts/installed_probe.py` read
#: `PANEL_ASSETS` off `server`, and moving where the table is written did not
#: move what it is about.
from conductor.server_assets import ENTRY_PAGE, PANEL_ASSETS
#: Re-exported deliberately: `_Mailbox`, `_run_frame` and `MAX_PENDING_RUNS` are
#: read off `server` by the run-event tests, and `SSE_WAIT` is the stream's wait
#: that callers of this server have always found here. `_Clients` and
#: `serve_events` are used below.
from conductor.server_events import (
    MAX_PENDING_RUNS, SSE_WAIT, _Clients, _Mailbox, _run_frame, serve_events)
from conductor.server_retirement import retire_resources, retire_workers

#: The `/harnesses.json` body, serialized once. The registry is frozen data
#: that no project can influence, so this is the same answer for every request
#: of every server — building it per request would only invite the impression
#: that something about it varies.
HARNESSES_JSON = json.dumps(harnesses.as_payload(),
                            ensure_ascii=False).encode("utf-8")

POLL_INTERVAL = 0.5   # seconds between conductor/ fingerprint polls
TICK_INTERVAL = 60.0  # seconds between unconditional re-merges (staleness tick)
#: Worker threads the server-owned coordinator mints. More than one so two runs
#: bound to two different provider instances really do execute at the same time;
#: bounded, because the coordinator's own queue capacity is what caps admission.
EXECUTION_WORKERS = 4


def _command_clock() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _command_id(kind: str) -> str:
    return f"{kind}-{secrets.token_hex(16)}"


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

    def project_name(self) -> str | None:
        """This project's name, off the LAST-GOOD map rather than the last read.

        A map broken by an edit in progress keeps answering with the name it
        had, for the same reason the merged state does: losing a project's
        identity to a syntax error is a worse answer than holding the one that
        was true a second ago. What counts as a name at all is
        `project_identity`'s single rule, not a second copy of it here.
        """
        return project_identity.project_name(self._map_data)

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
        # _stop_event, not _stop: threading.Thread has a private _stop()
        # method that join() calls on Python <= 3.12 — shadowing it with an
        # Event breaks join with TypeError: 'Event' object is not callable.
        self._stop_event = threading.Event()
        self._fingerprint = _fingerprint(cdir)
        self._last_merge = time.monotonic()

    def stop(self) -> None:
        """Ask the thread to exit; it wakes within POLL_INTERVAL."""
        self._stop_event.set()

    def run(self) -> None:
        """Poll until stopped; refresh on fingerprint change or tick."""
        while not self._stop_event.wait(POLL_INTERVAL):
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
                self._clients.publish_state()


class Handler(KeptConnection, BaseHTTPRequestHandler):
    """Legacy read routes plus the exact seven frozen command routes."""

    server: ConductServer                  # narrowed for type checkers

    def do_GET(self) -> None:              # required BaseHTTPRequestHandler name
        """Dispatch a GET to the matching `_serve_*` method, else 404."""
        path = urlsplit(self.path).path
        if path.startswith("/command"):
            self._serve_command("GET")     # keeps its own Host gate and refusal
            return
        if not self._read_host_is_allowed():
            return
        if path == "/":
            self._serve_panel()
        elif self.path in PANEL_ASSETS:
            self._serve_panel_asset(self.path)
        elif path == "/state.json":
            self._serve_state()
        elif path == "/harnesses.json":
            self._serve_harnesses()
        elif path == "/events":
            self._serve_events()
        elif path.startswith("/lane/"):
            self._serve_lane(path)
        elif path.startswith("/handoff/"):
            self._serve_handoff(path)
        else:
            self._send_404()

    def _read_host_is_allowed(self) -> bool:
        """Refuse a read whose Host this process never minted; say whether to go on.

        Binding to 127.0.0.1 keeps a stranger's packet off this socket, but it
        says nothing about whose PAGE sent it: a site the operator visits while
        `conduct up` runs can re-resolve its own name to loopback and then read
        every route here from its own origin. The panel, the merged state, the
        raw lanes, the handoff packets and the event stream are the whole
        project; none of them may answer a name this process did not hand out.

        The check is delegated, never re-derived. It is the same function, over
        the same ordered raw pairs, against the same session's two exact Host
        values that the command surface already spends -- so there is one
        allowlist to widen, not two, and a change of mind about loopback naming
        cannot reach one arm while the other keeps the old rule.

        The refusal is written in the legacy read arm's own plain prose rather
        than the command surface's JSON envelope. That arm answers HTML,
        markdown and raw lane bytes and has never spoken that vocabulary; the
        difference is also what makes it visible if this gate is ever moved
        ahead of the command branch, where it does not belong.

        Returns:
            True when dispatch may continue. False when the refusal has already
            been sent, and the caller must return without serving anything --
            in particular before the event stream, which commits a 200 as its
            first act and would leave no status line for a later refusal.
        """
        try:
            validate_command_host(self.headers.raw_items(),
                                  self.server.command_session.allowed_hosts)
        except HttpRefusal as refusal:
            self._send_body(refusal.status, "text/plain; charset=utf-8",
                            f"{refusal}\n".encode("utf-8"))
            return False
        return True

    def do_POST(self) -> None:             # required BaseHTTPRequestHandler name
        """Read one bounded command body; no legacy POST route exists."""
        if urlsplit(self.path).path.startswith("/command"):
            self._serve_command("POST", read_body=True)
        else:
            self._drain_refused_body()
            self._send_404()

    def do_HEAD(self) -> None:             # required BaseHTTPRequestHandler name
        self._serve_wrong_method("HEAD", head=True)

    def do_OPTIONS(self) -> None:          # required BaseHTTPRequestHandler name
        self._serve_wrong_method("OPTIONS")

    def do_TRACE(self) -> None:            # required BaseHTTPRequestHandler name
        self._serve_wrong_method("TRACE")

    def do_CONNECT(self) -> None:          # required BaseHTTPRequestHandler name
        self._serve_wrong_method("CONNECT")

    def do_PUT(self) -> None:              # required BaseHTTPRequestHandler name
        self._serve_wrong_method("PUT")

    def do_PATCH(self) -> None:            # required BaseHTTPRequestHandler name
        self._serve_wrong_method("PATCH")

    def do_DELETE(self) -> None:           # required BaseHTTPRequestHandler name
        self._serve_wrong_method("DELETE")

    def log_message(self, format: str, *args: object) -> None:
        """Silence per-request stderr logs (they would pollute CLI and tests)."""

    def send_error(
            self, code: int, message: str | None = None,
            explain: str | None = None) -> None:
        """Keep arbitrary command methods inside the frozen JSON refusal surface."""
        if (code == 501
                and urlsplit(getattr(self, "path", "")).path.startswith("/command")):
            self._serve_command(getattr(self, "command", ""))
            return
        super().send_error(code, message, explain)

    def _serve_wrong_method(self, method: str, *, head: bool = False) -> None:
        # Any body was already settled at the entrance (`parse_request`). Do not
        # drain again here: the headers still announce it, so a second drain
        # would read the NEXT request's bytes, or wait for bytes never sent.
        if urlsplit(self.path).path.startswith("/command"):
            self._serve_command(method, head=head)
        else:
            self._send_404(head=head)

    def _serve_command(
            self, method: str, *, read_body: bool = False,
            head: bool = False) -> None:
        """Bridge raw HTTP facts to CommandApi without normalizing headers."""
        pairs = tuple(self.headers.raw_items())
        body = b""
        if read_body:
            try:
                length = self.server.command_api.body_length(self.path, pairs)
            except (ApiRefusal, HttpRefusal):
                self.close_connection = True
            else:
                try:
                    body = self.rfile.read(length)
                except OSError:
                    body = b""
                if len(body) != length:
                    self.close_connection = True
        response = self.server.command_api.handle(method, self.path, pairs, body)
        encoded = canonical_json(response.payload).encode("utf-8")
        self._send_body(
            response.status, "application/json; charset=utf-8", encoded,
            write_body=not head)

    def _serve_panel(self) -> None:
        """Answer `GET /` with the Workflow Studio's shell.

        The front door is the Studio; the classic panel keeps its file name and
        is reached at `/panel/index.html` from the asset allowlist. Nothing
        about the classic panel's contents changed — only the route that gets
        to it — and the name here is a literal, as every panel resource name in
        this module is, so no request target can select the document served.
        """
        panel = importlib.resources.files("conductor") / "panel" / ENTRY_PAGE
        self._send_body(200, "text/html; charset=utf-8", panel.read_bytes())

    def _serve_panel_asset(self, target: str) -> None:
        content_type, name = PANEL_ASSETS[target]
        asset = importlib.resources.files("conductor") / "panel" / name
        self._send_body(200, content_type, asset.read_bytes())

    def _serve_state(self) -> None:
        self._send_body(200, "application/json; charset=utf-8",
                        self.server.broker.state_bytes())

    def _serve_harnesses(self) -> None:
        # Read-only presentation data. It never reaches the broker, so no
        # project's files can change a byte of it and no merge can be delayed
        # by it — which is the whole reason the registry is served beside the
        # state document instead of inside it.
        self._send_body(200, "application/json; charset=utf-8", HARNESSES_JSON)

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

    def _serve_handoff(self, path: str) -> None:
        """Render one current lane packet; URL input never becomes a path."""
        name = path[len("/handoff/"):]
        if not name.endswith(".md"):
            self._send_404()
            return
        author = name[:-len(".md")]
        if not store.AUTHOR_RE.fullmatch(author):
            self._send_404()
            return
        state = json.loads(self.server.broker.state_bytes())
        try:
            body = report.handoff(state, author).encode("utf-8")
        except KeyError:
            self._send_404()
            return
        self._send_body(200, "text/markdown; charset=utf-8", body)

    def _serve_events(self) -> None:
        """Stream SSE: one frame on connect, then one per broker change."""
        serve_events(self)

    def _send_frame(self, frame: bytes) -> None:
        self.wfile.write(frame)
        self.wfile.flush()


def _resolved_providers(
        registry: AdapterRegistry | None,
        providers: Sequence[ProviderConfig], root: Path,
        clock: Callable[[], str], ids: Callable[[str], str]) -> ProviderResolution:
    """Take an explicit registry OR the operator provider config, never both.

    An explicitly injected registry is a test/embedding seam and is used verbatim,
    with no descriptors; supplying provider config beside it is refused rather
    than silently ignored. The default resolves the provider config through the
    factory, which is empty by default, so the production server never pretends a
    real provider is available until real providers are configured and resolve to
    available.
    """
    if registry is not None:
        if providers:
            raise ProviderConfigError(
                "pass either an explicit adapter registry or provider config, not both")
        return ProviderResolution(registry=registry, contracts=())
    return resolve_providers(providers, root=root, clock=clock, ids=ids)


class ConductServer(ThreadingHTTPServer):
    """ThreadingHTTPServer wiring broker, watcher, SSE registry and execution worker."""

    daemon_threads = True  # SSE handler threads must never block process exit
    # On Windows, SO_REUSEADDR lets a second bind HIJACK a live port instead
    # of failing EADDRINUSE — keep it off there so `up` on a busy port exits
    # 1 (design: startup failure). POSIX keeps it for TIME_WAIT-free restarts.
    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        """Bind exactly as TCPServer does; name the server by its literal, not by DNS.

        HTTPServer.server_bind adds socket.getfqdn(host), a reverse lookup of a
        loopback literal that nothing here reads (review ruling: macOS start).
        """
        socketserver.TCPServer.server_bind(self)  # honours allow_reuse_address
        self.server_name, self.server_port = self.server_address[:2]

    def __init__(
            self, address: tuple[str, int], root: Path, cdir: Path, *,
            registry: AdapterRegistry | None = None,
            providers: Sequence[ProviderConfig] = (),
            budget: Budget = PRODUCT_COMMAND_BUDGET,
            clock: Callable[[], str] = _command_clock,
            ids: Callable[[str], str] = _command_id,
            token_factory: Callable[[int], str] = secrets.token_urlsafe) -> None:
        # Attributes first: a failed bind makes socketserver call our
        # server_close() before __init__ finishes.
        self.shutting_down = False
        self.project_owner = None
        self.policy_driver = None
        self.retirement_uncertain = False
        self.broker = Broker(root)
        self.clients = _Clients()
        self.watcher = Watcher(self.broker, cdir, self.clients)
        self.command_execution: ExecutionCoordinator | None = None
        self.command_quotas = QuotaService()
        self.quota_collector: QuotaCollector | None = None
        super().__init__(address, Handler)  # binds; EADDRINUSE raises here
        try:
            from .server_policy import acquire_server_owner
            acquire_server_owner(self, root)
            self._start_command(root, registry, providers, budget, clock, ids, token_factory)
            self.broker.refresh()               # initial state before serving
            self.watcher.start()
            self.quota_collector.start()
        except BaseException:
            self.server_close()
            raise

    def _start_command(self, root, registry, providers, budget, clock, ids, token_factory):
        from .server_command import start_command
        start_command(self, root, registry, providers, budget, clock, ids, token_factory)

    def shutdown(self) -> None:
        """Stop serve_forever, retire the owned worker, wake all SSE loops."""
        self.shutting_down = True
        self.clients.wake_all()
        try:
            self._retire_execution()
        finally:
            super().shutdown()

    def _retire_execution(self) -> None:
        """Retire this server's execution workers and quota collection lifetime."""
        retire_workers(self)

    def server_close(self) -> None:
        """Stop and join the watcher and worker, wake SSE loops, close the socket."""
        self.shutting_down = True
        self.clients.wake_all()
        retire_resources(self, super().server_close, POLL_INTERVAL)

    def handle_error(self, request: object, client_address: object) -> None:
        """Silence client aborts (panel refreshes, closed tabs); keep the rest.

        A vanished client raises ConnectionError past the handler into
        ThreadingMixIn — the default prints a 40-dash traceback to stderr.
        """
        if isinstance(sys.exc_info()[1], ConnectionError):  # sys.exception() is 3.12+
            return
        super().handle_error(request, client_address)


def build(
        root: Path | str, port: int, *,
        registry: AdapterRegistry | None = None,
        providers: Sequence[ProviderConfig] = (),
        budget: Budget = PRODUCT_COMMAND_BUDGET,
        clock: Callable[[], str] = _command_clock,
        ids: Callable[[str], str] = _command_id,
        token_factory: Callable[[int], str] = secrets.token_urlsafe,
) -> ConductServer:
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
    return ConductServer(
        ("127.0.0.1", port), Path(root), cdir, registry=registry,
        providers=providers, budget=budget, clock=clock, ids=ids,
        token_factory=token_factory)
