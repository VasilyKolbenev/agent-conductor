"""The throwaway box the Windows checks run in: layout, container, grants, one-step runner.

A ``Box`` owns a layout under a pytest tmp path and one AppContainer profile. It
grants the container rights ONLY on directories the attempt owns (its tmp, its home,
its vendor home, and the work copy as either writable or read-only) and never on the
source tree, which is exactly what makes the source unwritable. ``run`` performs an
operation's steps with a launch built one way for the confined run and, with
``confined=False``, the identical launch without the container attribute: the control.
"""
from __future__ import annotations

import http.server
import os
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests import os_boundary_windows as ac
from tests.os_boundary_layout import Layout, Operation, Step, make_layout, render, snapshot

_STEP_TIMEOUT = 90.0
_MOVE_REPLACE = (
    "Add-Type -Namespace H -Name N -MemberDefinition "
    "'[DllImport(\"kernel32.dll\",CharSet=CharSet.Unicode,SetLastError=true)] "
    "public static extern bool MoveFileExW(string a,string b,int f);'; "
    "Write-Output ('ok=' + [H.N]::MoveFileExW('@SRC_FILE@','@DST_FILE@',1))"
)
_NESTED = (
    "$i = New-Object Diagnostics.ProcessStartInfo; $i.FileName = '@POWERSHELL@'; "
    "$i.Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File @TMPD@\\inner.ps1'; "
    "$i.UseShellExecute = $false; [Diagnostics.Process]::Start($i).WaitForExit()"
)


@dataclass(frozen=True)
class StepResult:
    """One tool run: did the process start at all, how it ended, what it printed."""

    started: bool
    exit_code: int | None
    output: str


def base_environment(scratch: Path) -> dict[str, str]:
    """A minimal environment. LOCALAPPDATA is required by the container launch (measured)."""
    root = os.environ["SystemRoot"]
    return {"SystemRoot": root, "windir": root, "ComSpec": str(ac.CMD),
            "PATH": f"{ac.SYSTEM32};{root}", "LOCALAPPDATA": str(scratch),
            "TEMP": str(scratch), "TMP": str(scratch)}


def command_line(step: Step, tokens: dict[str, str]) -> str:
    """The raw command line for one step, identical for the confined run and its control."""
    body = render(step.body, tokens)
    if step.tool == "ps":
        return subprocess.list2cmdline([
            str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-Command", body])
    if step.tool == "cmd":
        return f'"{ac.CMD}" /d /s /c "{body}"'
    if step.tool == "icacls":
        return f'"{ac.ICACLS}" {body}'
    raise ValueError(f"no Windows tool named {step.tool!r}")


class Box:
    """A layout, its container, and the ways to run steps in it."""

    def __init__(self, layout: Layout, container: ac.Container) -> None:
        self.layout = layout
        self.container = container

    def snapshot(self, root_name: str):
        return snapshot(self.layout.root(root_name), acl=ac.acl_text)

    def tokens(self, root_name: str = "source") -> dict[str, str]:
        found = self.layout.tokens(root_name)
        found["POWERSHELL"] = str(ac.POWERSHELL)
        return found

    def launch(self, line: str, *, confined: bool, suspended: bool = False,
               capabilities=(), env: dict[str, str] | None = None):
        return ac.launch(
            line, sid=self.container.sid if confined else None, capabilities=capabilities,
            cwd=str(self.layout.tmp), env=env or base_environment(self.layout.tmp),
            suspended=suspended)

    def run_line(self, line: str, *, confined: bool = True, capabilities=(),
                 env: dict[str, str] | None = None) -> StepResult:
        try:
            proc = self.launch(line, confined=confined, capabilities=capabilities, env=env)
        except OSError as error:
            return StepResult(False, None, str(error))
        try:
            proc.wait(_STEP_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(10)
        output = proc.read_output()
        code = proc.returncode
        proc.close()
        return StepResult(True, code, output)

    def run_step(self, step: Step, tokens: dict[str, str], *, confined: bool = True,
                 capabilities=()) -> StepResult:
        return self.run_line(command_line(step, tokens), confined=confined,
                             capabilities=capabilities)

    def run(self, operation: Operation, *, root: str = "source",
            confined: bool = True) -> list[StepResult]:
        tokens = self.tokens(root)
        return [self.run_step(step, tokens, confined=confined) for step in operation.windows]

    def run_script(self, script: str, *, confined: bool = True, root: str = "source",
                   capabilities=()) -> StepResult:
        return self.run_step(Step("ps", script), self.tokens(root), confined=confined,
                             capabilities=capabilities)

    def control_write(self) -> bool:
        """A confined launch built the same way writes to the attempt's own tmp."""
        marker = self.layout.tmp / "control.txt"
        marker.unlink(missing_ok=True)
        self.run_script("[IO.File]::WriteAllText('@TMPD@\\control.txt','ok')")
        return marker.exists() and marker.read_bytes() == b"ok"

    def spawn_suspended(self, argv, *, confined: bool):
        return self.launch(subprocess.list2cmdline(list(argv)), confined=confined, suspended=True)

    def write_inner_script(self, text: str) -> None:
        (self.layout.tmp / "inner.ps1").write_bytes(render(text, self.tokens()).encode("utf-8"))

    def run_nested(self, *, confined: bool) -> StepResult:
        return self.run_script(_NESTED, confined=confined)

    def run_native_move_replace(self, source_file: str, destination_file: str) -> StepResult:
        script = _MOVE_REPLACE.replace("@SRC_FILE@", source_file)
        script = script.replace("@DST_FILE@", destination_file)
        return self.run_script(script)


@dataclass
class Served:
    """A loopback server the parent owns: its address and every path requested of it."""

    url: str = ""
    hits: list[str] = field(default_factory=list)


@contextmanager
def serve_loopback():
    """A tiny HTTP server on 127.0.0.1 that answers ``served-by-parent`` and counts requests."""
    served = Served()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            served.hits.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"served-by-parent")

        def log_message(self, *args):
            return None

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    served.url = "http://127.0.0.1:" + str(server.server_address[1]) + "/"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield served
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def container():
    with ac.Container() as current:
        yield current


def make_box(tmp_path: Path, current: ac.Container, work_rights: str) -> Box:
    """A layout under ``tmp_path`` and the grants for a container the caller owns."""
    layout = make_layout(tmp_path)
    for directory in (layout.tmp, layout.home, layout.vendor_home):
        ac.grant(directory, current.sid, ac.MODIFY)
    ac.grant(layout.work, current.sid, work_rights)
    return Box(layout, current)


@pytest.fixture
def implement_box(tmp_path, container):
    """Tmp, home, vendor home and the work copy writable. The source tree: no entry."""
    return make_box(tmp_path, container, ac.MODIFY)


@pytest.fixture
def review_box(tmp_path, container):
    """As the implement box, but the work copy is read and execute only."""
    return make_box(tmp_path, container, ac.READ_EXECUTE)
