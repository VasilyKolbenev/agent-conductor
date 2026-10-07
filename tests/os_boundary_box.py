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
import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests import os_boundary_windows as ac
from tests.os_boundary_layout import Layout, Operation, Step, make_layout, render, snapshot

_STEP_TIMEOUT = 90.0
#: Every launch of a probe script starts without PowerShell's own cmdlet modules. The CI
#: host's container lost them (``Write-Output``, ``New-Object`` and ``Add-Type`` were "not
#: recognized" there, while .NET calls ran), and a probe that quietly needed one passed on a
#: desktop and failed on the runner. Removing them from the launch itself, for the confined
#: run and its control alike, makes such a dependence fail on every host.
WITHOUT_CMDLETS = (
    "$PSModuleAutoLoadingPreference = 'None'; "
    "Remove-Module Microsoft.PowerShell.Utility, Microsoft.PowerShell.Management, "
    "Microsoft.PowerShell.Security, Microsoft.PowerShell.Diagnostics -Force "
    "-ErrorAction SilentlyContinue; "
)
#: ``MoveFileExW(a, b, MOVEFILE_REPLACE_EXISTING)`` called through a P/Invoke method that the
#: script emits into memory itself: ``Add-Type`` is a cmdlet and compiles C# with a helper
#: process, and neither is needed to make one native call.
_MOVE_REPLACE = (
    "$t = [AppDomain]::CurrentDomain.DefineDynamicAssembly("
    "[Reflection.AssemblyName]::new('h'), [Reflection.Emit.AssemblyBuilderAccess]::Run)"
    ".DefineDynamicModule('h').DefineType('N'); "
    "$m = $t.DefinePInvokeMethod('MoveFileExW', 'kernel32.dll', 'Public,Static,PinvokeImpl', "
    "'Standard', [bool], [Type[]]@([string], [string], [int]), 'Winapi', 'Unicode'); "
    "$m.SetImplementationFlags('PreserveSig'); $n = $t.CreateType(); "
    "[Console]::Out.Write('ok=' + $n::MoveFileExW('@SRC_FILE@','@DST_FILE@',1))"
)
_NESTED = (
    "$i = [Diagnostics.ProcessStartInfo]::new(); $i.FileName = '@POWERSHELL@'; "
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


_START_A_SHELL = (
    "try { $i = [Diagnostics.ProcessStartInfo]::new(); $i.FileName = '@POWERSHELL@'; "
    "$i.Arguments = '-NoProfile -NonInteractive -Command exit 0'; $i.UseShellExecute = $false; "
    "[void][Diagnostics.Process]::Start($i).WaitForExit(); [Console]::Out.Write('started') } "
    "catch { [Console]::Out.Write($_.Exception.Message) }"
)


def shell_start_problem(box) -> str:
    """Empty when a confined PowerShell can start a PowerShell of its own, else what it said."""
    result = box.run_script(_START_A_SHELL)
    if result.started and result.output == "started":
        return ""
    return result.output.strip() or f"the shell printed nothing and exited {result.exit_code}"


def require_child_shell(box) -> None:
    """Skip the calling test, naming the fact, when the container cannot start a shell.

    A test about what a confined child's own child may do measures nothing on a host where
    the container cannot start that child; the reason is also a warning so a quiet run shows it.
    """
    problem = shell_start_problem(box)
    if problem:
        reason = ("a PowerShell in this host's container cannot start a PowerShell of its own: "
                  + problem)
        warnings.warn(f"OS-boundary host difference: {reason}", stacklevel=2)
        pytest.skip(reason)


def powershell_line(body: str) -> str:
    """The command line that runs ``body`` in Windows PowerShell exactly as written."""
    return subprocess.list2cmdline([
        str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-Command", body])


def command_line(step: Step, tokens: dict[str, str]) -> str:
    """The raw command line for one step, identical for the confined run and its control."""
    body = render(step.body, tokens)
    if step.tool == "ps":
        return powershell_line(WITHOUT_CMDLETS + body)
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
        script = WITHOUT_CMDLETS + render(text, self.tokens())
        (self.layout.tmp / "inner.ps1").write_bytes(script.encode("utf-8"))

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
