"""The parent side of the drain witnesses.

It lays an activated project down with the repo's own helpers, launches
``tests/_drain_child.py`` (the real `conduct up` with fake dispatch), drives the
grant through the real HTTP door, and reads back only durable facts: the status
file, the ownership head, the login box names, the run journal and the exit code.

Every wait here is ``wait_until`` with an explicit bound that names what it was
waiting for, and the child's stderr rides along in the failure. Nothing sleeps
to "let something happen". The launch shape is the one the spec gives a hub
child (own process group, no job), and for the Ctrl+C witnesses a hidden console
of its own whose signal is proven on a plain sleeper first.
"""
from __future__ import annotations

import functools
import http.client
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import conductor
from conductor import ownership_login, ownership_records
from conductor import ownership_transition as transition
from conductor.command.command_routes import COMMAND_ROUTES
from conductor.command.coordinator import JOIN_TIMEOUT_SECONDS
from conductor.command.run_store import RunStore
from tests.test_policy_driver import ask as two_step_ask
from tests.test_policy_runtime import setup
from tests.test_store import good_lane, write_project

#: A rendezvous that must succeed, and a deadlock bound rather than a speed budget.
WAIT = 30.0
#: A window in which something must NOT happen; enlarging it only costs time.
PROBE = 1.0
#: A drain must outlast what `shutdown()` waits for a worker today, or it proves nothing
#: about waiting: the bound is the coordinator's own, plus a margin.
PAST_THE_OLD_JOIN = JOIN_TIMEOUT_SECONDS + 1.5
#: How long a worker lingers after an attempt's receipt (see `_drain_child`).
LINGER = 1.0
RUN_ID = "run"
CHILD = Path(__file__).resolve().with_name("_drain_child.py")
REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(conductor.__file__).resolve().parents[1]
_URL = re.compile(r"http://127\.0\.0\.1:(\d+)/")

_CONSOLE_STOP = """
import ctypes, sys, time
from ctypes import wintypes
k = ctypes.WinDLL('kernel32', use_last_error=True)
k.FreeConsole.restype = wintypes.BOOL
k.AttachConsole.argtypes = [wintypes.DWORD]
k.AttachConsole.restype = wintypes.BOOL
k.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wintypes.BOOL]
k.SetConsoleCtrlHandler.restype = wintypes.BOOL
k.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
k.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
k.FreeConsole()
if not k.AttachConsole(int(sys.argv[1])):
    raise ctypes.WinError(ctypes.get_last_error())
try:
    if not k.SetConsoleCtrlHandler(None, True) or not k.GenerateConsoleCtrlEvent(0, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    time.sleep(0.25)
finally:
    k.FreeConsole()
"""

_SLEEPER = """
import os, sys, time
if os.name == 'nt':
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wintypes.BOOL]
    k.SetConsoleCtrlHandler(None, False)
open(sys.argv[1], 'w').close()
time.sleep(60)
"""


def wait_until(predicate: Callable[[], object], timeout: float, what: str,
               child: DrainChild | None = None) -> None:
    """Poll until the predicate holds; fail naming `what` and the child's stderr."""
    deadline = time.monotonic() + timeout
    while True:
        if child is not None:
            child.raise_if_exited(what)
        if predicate():
            return
        if time.monotonic() >= deadline:
            tail = "" if child is None else f"\nchild stderr:\n{child.stderr_tail()}"
            raise AssertionError(f"timed out after {timeout}s waiting for {what}{tail}")
        time.sleep(0.02)


def stays_true(predicate: Callable[[], object], window: float, what: str) -> None:
    """Assert the predicate holds at every poll across the whole window."""
    deadline = time.monotonic() + window
    while time.monotonic() < deadline:
        assert predicate(), f"{what}: stopped holding inside the {window}s window"
        time.sleep(0.05)


def _launch_options(*, console: bool) -> dict:
    """A hub child has no console and its own group (spec 4.1.4); a Ctrl+C child a hidden one."""
    if os.name != "nt":
        return {"start_new_session": True}
    if console:
        flags = subprocess.CREATE_NEW_CONSOLE
    else:
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    hidden = subprocess.STARTUPINFO()
    hidden.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    hidden.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": flags, "startupinfo": hidden}


def _deliver_ctrl_c(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run([sys.executable, "-I", "-c", _CONSOLE_STOP, str(proc.pid)],
                       check=True, timeout=20, capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGINT)


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True, timeout=30)
    else:
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(timeout=30)


@functools.cache
def ctrl_c_proof(work: str) -> str | None:
    """None when a plain sleeper launched like the child dies of our Ctrl+C.

    Otherwise the measured reason, for the skip message. The sleeper clears any
    inherited "ignore Ctrl+C" itself, so what is proven is the delivery road
    (a hidden console of its own, a helper that attaches to it), not the product.
    """
    ready = Path(work) / "sleeper-ready"
    sleeper = subprocess.Popen(
        [sys.executable, "-c", _SLEEPER, str(ready)], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **_launch_options(console=True))
    try:
        wait_until(ready.exists, WAIT, "the Ctrl+C sleeper to start")
        _deliver_ctrl_c(sleeper)
        try:
            sleeper.wait(timeout=10)
        except subprocess.TimeoutExpired:
            return ("a plain sleeper in its own console survived the delivered Ctrl+C: "
                    "this environment cannot deliver the signal, so no witness can judge it")
        return None
    finally:
        _kill_tree(sleeper)


@dataclass
class DrainChild:
    """One launched `conduct up` and everything the witnesses ask of it."""

    project: DrainProject
    proc: subprocess.Popen
    hub: bool
    stderr_path: Path
    lines: list[str] = field(default_factory=list)
    token: str | None = None
    reader: threading.Thread | None = None

    def start_reader(self) -> None:
        def pump() -> None:
            for raw in iter(self.proc.stdout.readline, b""):
                self.lines.append(raw.decode("utf-8", "replace").strip())
        self.reader = threading.Thread(target=pump, daemon=True)
        self.reader.start()

    def stderr_tail(self) -> str:
        try:
            return self.stderr_path.read_text(encoding="utf-8", errors="replace")[-1500:]
        except OSError:
            return "(no stderr)"

    def raise_if_exited(self, what: str) -> None:
        code = self.proc.poll()
        if code is not None:
            raise AssertionError(
                f"the child exited with {code} while waiting for {what}\n"
                f"child stderr:\n{self.stderr_tail()}")

    @property
    def port(self) -> int | None:
        for line in list(self.lines):
            found = _URL.fullmatch(line)
            if found:
                return int(found.group(1))
        return None

    def status(self) -> dict | None:
        try:
            return json.loads(self.project.status_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def state(self) -> str | None:
        return (self.status() or {}).get("state")

    def wait_serving(self) -> None:
        wait_until(lambda: self.port is not None, WAIT, "the child to print its URL", self)
        if self.hub:
            self.wait_state("serving")

    def wait_state(self, state: str, timeout: float = WAIT) -> None:
        wait_until(lambda: self.state() == state, timeout,
                   f"the status file to say {state!r}", self)

    def http(self, method: str, path: str, body: dict | None = None):
        headers = {}
        encoded = None
        if method == "POST":
            encoded = json.dumps({} if body is None else body).encode("utf-8")
            headers = {"Origin": f"http://127.0.0.1:{self.port}",
                       "X-Conduct-CSRF": self._csrf(), "Content-Type": "application/json"}
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=encoded, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def _csrf(self) -> str:
        if self.token is None:
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            try:
                connection.request("GET", "/command/session")
                self.token = json.loads(connection.getresponse().read())["csrf_token"]
            finally:
                connection.close()
        return self.token

    def authorize(self, node_timeout: int | None = None) -> None:
        body = two_step_ask()
        if node_timeout is not None:
            body = {**body, "max_action_seconds": 2 * node_timeout,
                    "max_total_task_seconds": 8 * node_timeout,
                    "node_limits": [{"node_id": node, "timeout_seconds": node_timeout,
                                     "max_attempts": 2} for node in ("do", "next")]}
        base = f"/command/runs/{RUN_ID}/automation"
        status, preview = self.http("POST", f"{base}/preview", body)
        assert status == 200, preview
        status, grant = self.http("POST", f"{base}/authorize", {
            "authorization_id": "grant", "preview_digest": preview["preview_digest"],
            "authorized_by": "owner", "terms": preview["terms"], "supersedes": None})
        assert status == 201, grant

    def wait_attempt(self, number: int = 1) -> None:
        marker = self.project.control / f"entered-{number}"
        wait_until(marker.exists, WAIT, f"attempt {number} to enter its effect", self)

    def release(self, number: int = 1) -> None:
        (self.project.control / f"release-{number}").write_text("1", encoding="ascii")

    def close_stdin(self) -> None:
        self.proc.stdin.close()

    def send_ctrl_c(self) -> None:
        _deliver_ctrl_c(self.proc)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def wait_exit(self, timeout: float) -> int:
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise AssertionError(
                f"the child was still running {timeout}s after the stop request\n"
                f"child stderr:\n{self.stderr_tail()}") from None

    def finish(self) -> None:
        for number in range(1, 5):
            self.release(number)
        try:
            self.proc.stdin and self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _kill_tree(self.proc)
        self.reader.join(timeout=10)
        self.proc.stdout.close()


@dataclass
class DrainProject:
    """An activated two-step project, its login folder and its hub-style home."""

    base: Path
    root: Path
    login: Path
    control: Path
    home: Path
    project_id: str
    box: Path
    children: list[DrainChild] = field(default_factory=list)

    @classmethod
    def build(cls, base: Path) -> DrainProject:
        root = base / "project"
        root.mkdir()
        write_project(root, lanes={"claude": good_lane()})
        setup(root, two_steps=True, checker=True)
        transition.activate(root, legacy_writers_stopped=True)
        login, control, home = base / "login", base / "control", base / "home"
        for folder in (login, control, home / "run"):
            folder.mkdir(parents=True)
        return cls(base, root, login, control, home,
                   ownership_records.state(root)[1]["nonce"],
                   ownership_login._route(str(login))[1])

    @property
    def status_file(self) -> Path:
        return self.home / "run" / f"{self.project_id}.json"

    def start(self, *, hub: bool, auto_release: bool = False, fault: str | None = None,
              margin: float | None = None, ctrl_c: str = "none",
              settle_delay: float = LINGER) -> DrainChild:
        """Launch the child; `ctrl_c` is `none` (no console), `ignored` or `enabled` (its own)."""
        argv = [sys.executable, str(CHILD), "up", "--dir", str(self.root), "--port", "0"]
        if hub:
            argv += ["--project-id", self.project_id,
                     "--hub-origin", "http://127.0.0.1:7700",
                     "--status-file", str(self.status_file), "--stop-on-stdin-eof"]
        stderr_path = self.base / f"child-{len(self.children)}.err"
        with stderr_path.open("wb") as stderr:
            proc = subprocess.Popen(
                argv, cwd=self.home,
                env=self._environment(auto_release, fault, margin, ctrl_c, settle_delay),
                stdin=subprocess.PIPE if hub else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=stderr,
                **_launch_options(console=ctrl_c != "none"))
        child = DrainChild(self, proc, hub, stderr_path)
        child.start_reader()
        self.children.append(child)
        return child

    def _environment(self, auto_release, fault, margin, ctrl_c, settle_delay) -> dict[str, str]:
        env = dict(os.environ)
        env.update(PYTHONPATH=os.pathsep.join((str(SOURCE_ROOT), str(REPO_ROOT))),
                   PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
                   CONDUCT_HOME=str(self.home), DRAIN_ROOT=str(self.root),
                   DRAIN_CONTROL=str(self.control), DRAIN_LOGIN=str(self.login),
                   DRAIN_SETTLE_DELAY=str(settle_delay))
        for name in ("DRAIN_AUTO_RELEASE", "DRAIN_FAULT", "DRAIN_MARGIN", "DRAIN_CTRL_C"):
            env.pop(name, None)
        if auto_release:
            env["DRAIN_AUTO_RELEASE"] = "1"
        if fault is not None:
            env["DRAIN_FAULT"] = fault
        if margin is not None:
            env["DRAIN_MARGIN"] = str(margin)
        if ctrl_c != "none":
            env["DRAIN_CTRL_C"] = ctrl_c
        return env

    def require_ctrl_c(self) -> None:
        """Skip, with the measured reason, where the OS cannot deliver Ctrl+C."""
        reason = ctrl_c_proof(str(self.base))
        if reason is not None:
            pytest.skip(reason)

    def close(self) -> None:
        for child in self.children:
            child.finish()

    # -- durable facts, read without touching ownership --------------------

    def head_phase(self) -> str:
        return ownership_records.state(self.root)[1]["phase"]

    def lease_standing(self) -> bool:
        return os.path.lexists(self.box / "active.json")

    def closed_leases(self) -> list[str]:
        return sorted(path.name for path in self.box.glob("closed-*.json"))

    def _records(self):
        return RunStore(self.root).read(RUN_ID).records

    def proposal_nodes(self) -> list[str]:
        return [row.value.node_id for row in self._records() if row.kind == "action_proposal"]

    def request_nodes(self) -> list[str]:
        return [row.value.node_id for row in self._records() if row.kind == "action_request"]

    def results(self) -> list[str]:
        return [row.value.outcome for row in self._records() if row.kind == "action_result"]

    def wait_run_terminal(self, child: DrainChild) -> None:
        wait_until(lambda: any(row.kind == "run_terminal" for row in self._records()),
                   WAIT, "the run to record its terminal", child)


def post_paths() -> list[str]:
    """Every POST row of the frozen command table, with concrete identifiers."""
    filled = {"<run_id>": RUN_ID, "<workflow_id>": "custom", "<task_id>": "task",
              "<revision>": "1"}
    paths = []
    for method, path in COMMAND_ROUTES:
        if method == "POST":
            for name, value in filled.items():
                path = path.replace(name, value)
            paths.append(path)
    return paths
