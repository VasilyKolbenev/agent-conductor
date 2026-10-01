"""The printing bodies of the hub-side commands of `conduct` (spec 4.1.12).

`conduct tools pin`, `conduct projects add` and `conduct hub` live here. Each body turns
what a library decided into the stream contract of the CLI: a result on stdout, or ONE refusal
line on stderr, and an exit code. The libraries (`tool_pins`, `hub.server`, ...) raise and never
print. `hub_command` imports the hub only when it runs, so `tools pin` and `init` do not load it.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from conductor import tool_pins
from conductor.hub import home


def tools_pin(tool: str, path: str) -> int:
    """`conduct tools pin <tool> --path <abs>`: one JSON line on stdout, or one refusal line.

    Args:
        tool: `git` or `gh`.
        path: The absolute path of the executable to pin.

    Returns:
        0 after a pin was written, 1 for any refusal.
    """
    try:
        pin = tool_pins.pin_tool(tool, path)
    except tool_pins.ToolPinError as error:
        return _refused("tools pin", error.code, error.detail)
    except home.ConductHomeInvalid as error:
        return _refused("tools pin", error.code, str(error))
    print(json.dumps({"tool": pin.tool, "path": pin.path, "version": pin.version},
                     sort_keys=True, ensure_ascii=False))
    return 0


def _refused(command: str, code: str, detail: str) -> int:
    print(f"conduct {command}: refused {code}: {' '.join(str(detail).split())}", file=sys.stderr)
    return 1


def projects_add(directory: str, *, name: str | None = None,
                 legacy_writers_stopped: bool = False, source: str = "folder",
                 repo: str | None = None) -> int:
    """Print one completed step per line, then the local folder's registration result."""
    from conductor.hub import projects_add as addition

    def completed(step: str) -> None:
        print(json.dumps({"step": step}, ensure_ascii=False), flush=True)

    try:
        result = addition.add_folder(directory, name=name,
            legacy_writers_stopped=legacy_writers_stopped, progress=completed,
            source=source, repo=repo)
    except addition.AddRefused as error:
        return _refused("projects add", error.code, error.detail)
    print(json.dumps({"result": result}, sort_keys=True, ensure_ascii=False), flush=True)
    print(f"conduct projects add: registered {result['name']} at {result['root']}", file=sys.stderr)
    return 0


class _Refusal(Exception):
    """A start the hub refuses: printed as ONE line and exit 1."""

    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


def hub_command(port: int, *, stop: threading.Event | None = None) -> int:
    """`conduct hub [--port N]`: serve the hub page and run one child per project (4.1).

    Prints the address of the hub on stdout when it serves; a second hub prints the first one's
    address and exits 0; a refusal is ONE stderr line and exit 1. It runs until Ctrl+C (or `stop`
    is set, which is how a test ends it): then every child is asked to drain, the hub says who it
    waits for, and a second Ctrl+C leaves at once while the children finish alone.

    Args:
        port: The loopback port; 0 lets the OS choose.
        stop: An event that ends the hub as Ctrl+C does; `None` for the command itself.

    Returns:
        0 after a serve (or when a hub already runs), 1 for any refusal.
    """
    if stop is None:
        from conductor import server_drain
        server_drain.enable_ctrl_c()
    try:
        return _run_hub(port, stop or threading.Event())
    except _Refusal as refusal:
        return _refused("hub", refusal.code, refusal.detail)


def _hub_home() -> Path:
    """The hub's folder, judged before it is made (4.1.2 rule 1)."""
    try:
        home.require_placement(home.conduct_home_path())
        return home.conduct_home()
    except (home.ConductHomeInvalid, home.ConductHomeOverlapsLogin) as error:
        raise _Refusal(getattr(error, "code", "conduct_home_invalid"), str(error)) from error
    except OSError as error:
        raise _Refusal("conduct_home_invalid", f"the folder could not be made: {error}") from error


def _run_hub(port: int, stopper: threading.Event) -> int:
    from conductor.hub import instance, state
    folder = _hub_home()
    try:
        hub = instance.HubInstance.acquire(folder)
    except instance.HubAlreadyRunning as running:
        if running.url:
            print(running.url, flush=True)
        print("conduct hub: a hub is already running; this one did not start", file=sys.stderr)
        return 0
    try:
        try:
            state.load(folder)
        except state.HubStateError as error:
            raise _Refusal(error.code, error.detail) from error
        return _serve_hub(hub, folder, port, stopper)
    finally:
        hub.close()


class _Parts:
    """What a running hub is made of, once its port is known."""

    def __init__(self, service, supervisor, reader) -> None:
        self.service, self.supervisor, self.reader = service, supervisor, reader


def _assemble(hub, folder: Path, srv, origin: str) -> _Parts:
    from conductor.hub import reader, service, snapshots, spawn, state, summary, supervisor
    store = state.HubStateStore(folder, hub)
    sup = supervisor.Supervisor(folder, store, spawn.Spawner(folder, hub_origin=origin),
                                hub_port=srv.server_port)
    snaps, ledger = snapshots.SnapshotStore(folder), summary.ObservedLedger()
    watching = reader.ChildReader(folder, sup, store, snaps, ledger, srv.bus, hub_origin=origin)
    return _Parts(service.HubService(folder, sup, store, snaps, watching, ledger, srv.bus), sup,
                  watching)


def _serve_hub(hub, folder: Path, port: int, stopper: threading.Event) -> int:
    from conductor.hub import server
    try:
        srv = server.HubServer(port)
    except server.HubBindError as error:
        raise _Refusal("hub_bind_failed", f"port {port} could not be bound: {error}") from error
    origin = f"http://127.0.0.1:{srv.server_port}"
    parts = _assemble(hub, folder, srv, origin)
    parts.service.start()
    srv.attach(parts.service)
    hub.publish(srv.server_port)
    parts.supervisor.restart()
    loop = server.HubLoop(parts.service)
    loop.start()
    web = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.2},
                           name="hub-http", daemon=True)
    web.start()
    print(f"{origin}/", flush=True)
    try:
        while not stopper.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    _shut_down(srv, web, loop, parts, folder)
    return 0


def _shut_down(srv, web: threading.Thread, loop, parts: _Parts, folder: Path) -> None:
    """Stop serving, ask every child to drain, wait for them, and let go (4.1.7)."""
    loop.stop()
    srv.shutdown()
    parts.reader.close()
    parts.supervisor.drain_all()
    _await_children(parts.supervisor, folder)
    loop.join(5)
    web.join(5)
    srv.server_close()


def exit_report(rows: list[tuple[str, datetime | None, bool]]) -> str:
    """The line the hub writes while it waits for its children: each with its deadline, or done."""
    if not rows:
        return "conduct hub: no child to wait for"
    said = []
    for name, deadline, done in rows:
        if done:
            said.append(f"{name} done")
        elif deadline is not None:
            said.append(f"{name} until {deadline.astimezone(timezone.utc):%H:%M} UTC")
        else:
            said.append(name)
    return "conduct hub: waiting for the children to stop: " + ", ".join(said)


def _await_children(sup, folder: Path) -> None:
    from conductor.hub import registry
    try:
        names = {p.project_id: p.name for p in registry.load(folder).projects}
    except registry.RegistryError:
        names = {}
    last = None
    try:
        while True:
            report = sup.children_report()
            if all(one.done for one in report):
                return
            line = exit_report([(names.get(one.project_id, one.project_id[:8]),
                                 one.drain_deadline, one.done) for one in report])
            if line != last:
                print(line, file=sys.stderr, flush=True)
                last = line
            time.sleep(0.5)
    except KeyboardInterrupt:
        return                       # a second Ctrl+C: leave now; the children finish alone
