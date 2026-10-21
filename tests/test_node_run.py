"""`tests/node_run.py` keeps `subprocess.run`'s verdict and deadline and only adds notes.

The cases that need a hung or a slow process run a real `node` (`shutil.which`, else skipped):
under `.venv` on Windows `sys.executable` is a redirector that starts the real interpreter as
a child, so its CPU, its pipes and its kill are not those of the process the test names. The
shape of the process tables is checked on text, so both operating systems' parsers run
everywhere. Timeouts are 1 s: long enough for Node to be up and waiting, short enough to
repeat.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import types
import warnings

import pytest

from tests import desk_node, desk_wizard_node, node_run

WINDOWS = sys.platform == "win32"
#: A script that never ends and keeps Node in its event loop, doing nothing.
HANG = "setInterval(() => {}, 1000);"
#: A script that ends on its own after half a second.
SLOW = 'setTimeout(() => console.log("ok"), 500);'
#: Node starts a grandchild that keeps Node's stdout and stderr open for 30 s, and says who it
#: is. `detached` matters: on Windows a child that is not detached dies with its parent.
GRANDCHILD = """
import {spawn} from "node:child_process";
import {writeFileSync} from "node:fs";
const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 30000)"],
  {stdio: ["ignore", "inherit", "inherit"], detached: true});
writeFileSync(PID_FILE, String(child.pid));
setInterval(() => {}, 1000);
"""
PROFILE = re.compile(r"cpu user (\d+\.\d{3}) s, kernel (\d+\.\d{3}) s; working set (\d+\.\d) MB "
                     r"\(peak \d+\.\d\); handles (\d+); page faults \d+")


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts as the first Node call of a new process."""
    monkeypatch.setattr(node_run, "_state", {"calls": 0, "last_end": None, "warned": 0})


@pytest.fixture
def node() -> str:
    found = shutil.which("node")
    if found is None:
        pytest.skip("Node is needed to run these cases against a real process")
    return found


def argv_of(node: str) -> list[str]:
    return [node, "--input-type=module"]


def timed_out(node: str, source: str, timeout: float = 1.0) -> subprocess.TimeoutExpired:
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        node_run.run_node(argv_of(node), source, timeout=timeout)
    return caught.value


def notes_of(exc: BaseException) -> str:
    return "\n".join(getattr(exc, "__notes__", []))


def spy_on_popen(monkeypatch: pytest.MonkeyPatch, events: list[str] | None = None,
                 killed: list[str] | None = None,
                 fail: tuple[list[str], BaseException] | None = None) -> list:
    """Every `subprocess.Popen` made from now on; its `asked` holds each `communicate` timeout.

    A start that fails is in the list too, with its `args`. With `events` and `killed` (an argv),
    a `kill()` of the process started with that argv adds "kill" to `events`. With `fail` (an
    argv and an exception), the `communicate` of the process started with that argv raises it.
    """
    made: list = []

    class Spy(subprocess.Popen):
        def __init__(self, *args, **kwargs) -> None:
            self.args = args[0] if args else kwargs["args"]
            self.asked: list[float | None] = []
            made.append(self)
            super().__init__(*args, **kwargs)

        def communicate(self, input=None, timeout=None):  # noqa: A002 - the stdlib's name
            self.asked.append(timeout)
            if fail is not None and self.args == fail[0]:
                raise fail[1]
            return super().communicate(input, timeout)

        def kill(self) -> None:
            if events is not None and self.args == killed:
                events.append("kill")
            super().kill()

    monkeypatch.setattr(subprocess, "Popen", Spy)
    return made


def node_launches(made: list, node: str) -> list[list[str]]:
    """The argv of every start of `node` that `spy_on_popen` saw, in order.

    Whatever the path, a call starts its script once; a timeout adds one `--version` probe.
    """
    return [proc.args for proc in made if proc.args[0] == node]


def record_calls(monkeypatch: pytest.MonkeyPatch, name: str, events: list[str], label: str):
    """Make `node_run.<name>` add `label` to `events` each time it is called."""
    real = getattr(node_run, name)

    def recording(*args):
        events.append(label)
        return real(*args)

    monkeypatch.setattr(node_run, name, recording)


@pytest.mark.parametrize(("source", "code"), [
    pytest.param('console.log(JSON.stringify({word: "\u00e9"}));', 0, id="json_with_an_accent"),
    pytest.param('console.error("bad"); process.exitCode = 3;', 3, id="exit_code_and_stderr"),
    pytest.param("// " + "x" * 9000 + '\nconsole.log("long");', 0, id="script_over_8_kib"),
])
def test_a_call_that_ends_answers_exactly_what_subprocess_run_answers(node, source, code):
    argv = argv_of(node)
    ours = node_run.run_node(argv, source, timeout=30)
    theirs = subprocess.run(argv, input=source, capture_output=True, text=True, encoding="utf-8",
                            timeout=30, check=False)
    assert isinstance(ours, subprocess.CompletedProcess)
    assert (ours.args, ours.returncode, ours.stdout, ours.stderr) == (
        theirs.args, theirs.returncode, theirs.stdout, theirs.stderr)
    assert ours.returncode == code and (ours.stdout or ours.stderr)


def test_a_call_that_cannot_start_raises_what_subprocess_run_raises(tmp_path, monkeypatch):
    made = spy_on_popen(monkeypatch)
    missing = [str(tmp_path / "no-such-node")]
    with pytest.raises(OSError) as ours:
        node_run.run_node(missing, "1", timeout=5)
    assert [proc.args for proc in made] == [missing]  # one attempt, no second one
    with pytest.raises(OSError) as theirs:
        subprocess.run(missing, input="1", capture_output=True, text=True, timeout=5)
    assert type(ours.value) is type(theirs.value) is FileNotFoundError
    assert node_run._state["calls"] == 1 and node_run._state["last_end"] is not None


def test_a_timeout_is_subprocess_runs_own_after_the_same_deadline_and_one_spawn(
        node, monkeypatch):
    made = spy_on_popen(monkeypatch)
    argv = argv_of(node)
    exc = timed_out(node, HANG, timeout=1.0)
    ours = [proc for proc in made if proc.args == argv]
    assert len(ours) == 1
    assert ours[0].asked[0] == 1.0
    assert exc.timeout == 1.0 and exc.cmd == argv
    waited = float(re.search(r"waited (\d+\.\d{3}) s", notes_of(exc))[1])
    # The deadline counts on a coarse clock on Windows: a few ms either way are not a fault.
    assert 0.95 <= waited <= 1.5


def test_the_notes_carry_what_a_red_ci_log_needs(node):
    exc = timed_out(node, r'process.stdout.write("partial-out\n"); '
                          r'process.stderr.write("partial-err\n"); ' + HANG)
    image = re.escape(os.path.basename(node))
    # What the code writes by itself, and what `communicate` documents: the same on any system.
    wanted = [
        r"^node-run: timed out after 1\.0 s; the deadline and the verdict are unchanged, "
        r"no retry$",
        r"^call #1 of this process: the first Node call of it$",
        r"^started \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z UTC at uptime (\d+\.\d{3}|unknown) s; "
        r"spawn took \d+\.\d{3} s; waited \d+\.\d{3} s$",
        r"^stdin: \d+ chars, \d+ bytes; first line: 'process\.stdout\.write\(",
        r"^threads in this Python: \d+$",
        r"^stdout \(12 chars\): 'partial-out\\n'$",
        r"^stderr \(12 chars\): 'partial-err\\n'$",
        # What the system answers is not known on a runner nobody has seen (is there a `ps`, what
        # does it call Node, what does a kill return, is the `node` found the real binary): each
        # such fact must be there, as its value or as `unavailable (<Type>`; no more is asked.
        r"^at the deadline: (alive|poll\(\)|unavailable \()",
        r"^(processes now: \d|process table: unavailable \()",
        r"^after kill: (returncode -?\d+; pipes |unavailable \()",
        rf"^{image} --version after the kill: \S",
    ]
    if WINDOWS:  # the one system whose answers have been read here
        wanted += [
            r"^at the deadline: alive; cpu user \d+\.\d{3} s, kernel \d+\.\d{3} s; working set "
            r"\d+\.\d MB \(peak \d+\.\d\); handles \d+; page faults \d+$",
            r"^background suspects: .+$",
            rf"^processes now: \d+; {image} alive: [1-9]\d* \[.+\]$",
            r"^after kill: returncode 1; pipes closed in \d+\.\d{3} s$",
            rf"^{image} --version after the kill: 'v\d+\.\d+\.\d+' rc 0 in \d+\.\d{{3}} s$",
        ]
    text = notes_of(exc)
    missing = [pattern for pattern in wanted if not re.search(pattern, text, re.M | re.I)]
    assert not missing, f"{missing}\n--- the notes ---\n{text}"
    assert exc.stdout == "partial-out\n" and exc.stderr == "partial-err\n"


@pytest.mark.parametrize("table", ["listed", "no_ps"])
def test_the_posix_branch_gives_whole_notes_whatever_the_system_answers(
        node, monkeypatch, table):
    """The POSIX branch for real on any system: `node_run` is told it runs on Linux, Node is
    the real one, and only `ps` is made up -- a listing that holds Node's pid, or no `ps` at all.
    On Linux and macOS this is the very branch that runs; on Windows it is the only place it
    does. `/proc/uptime` is read for real: a number there, `unknown` here."""
    made = spy_on_popen(monkeypatch)
    monkeypatch.setattr(node_run, "sys", types.SimpleNamespace(platform="linux"))
    image = os.path.basename(node)

    def ps() -> list[list[str]]:
        if table == "no_ps":
            raise FileNotFoundError(2, "No such file or directory", "ps")
        return node_run._parse_ps("    1     0 Ss   00:00:02  9124 systemd\n"
                                  f"{made[0].pid} 4000 Sl   00:00:00 33000 {image}\n")

    monkeypatch.setattr(node_run, "_process_table", ps)
    text = notes_of(timed_out(node, HANG))
    lines = text.splitlines()
    assert "at the deadline: poll() = None" in lines
    assert re.search(r"^started .* at uptime (\d+\.\d{3}|unknown) s; ", text, re.M)
    if table == "listed":
        assert f"processes now: 2; {image} alive: 1 [{made[0].pid} (33000 K)]" in lines
        assert ("the timed-out process (pid ppid stat time rss comm): "
                f"{made[0].pid} 4000 Sl 00:00:00 33000 {image}") in lines
    else:
        assert ("process table: unavailable (FileNotFoundError: [Errno 2] No such file or "
                "directory: 'ps')") in lines
    for fact in (r"after kill: returncode -?\d+; pipes closed in ", r"stdout \(0 chars\): ''",
                 r"stderr \(0 chars\): ''", rf"{re.escape(image)} --version after the kill: "):
        assert re.search(rf"^{fact}", text, re.M), f"{fact}\n--- the notes ---\n{text}"
    assert "diagnostics failed" not in text


def test_the_process_and_the_table_are_read_before_the_kill(node, monkeypatch):
    events: list[str] = []
    spy_on_popen(monkeypatch, events, killed=argv_of(node))
    record_calls(monkeypatch, "_profile", events, "profile")
    record_calls(monkeypatch, "_process_table", events, "table")
    timed_out(node, HANG)
    assert events == ["profile", "table", "kill"]


@pytest.mark.skipif(not WINDOWS, reason="the profile of the process is read from Windows")
def test_the_cpu_at_the_deadline_tells_a_spinning_node_from_a_waiting_one(node):
    spinning = PROFILE.search(notes_of(timed_out(node, "while (true) {}")))
    waiting = PROFILE.search(notes_of(timed_out(node, HANG)))
    assert float(spinning[1]) >= 0.5
    assert float(waiting[1]) + float(waiting[2]) < 0.5
    assert float(waiting[3]) >= 10 and int(waiting[4]) >= 30


def test_a_pipe_another_process_holds_cannot_hold_back_the_failure(node, monkeypatch, tmp_path):
    monkeypatch.setattr(node_run, "DRAIN_AFTER_KILL", 1.0)
    pid_file = tmp_path / "grandchild.pid"
    source = GRANDCHILD.replace("PID_FILE", json.dumps(str(pid_file)))
    began = time.perf_counter()
    try:
        exc = timed_out(node, source, timeout=2.0)
        took = time.perf_counter() - began
    finally:
        try:
            os.kill(int(pid_file.read_text()), signal.SIGTERM)
        except (OSError, ValueError):
            pass  # no grandchild was started, or it is gone already
    # Worst honest case: 2 s deadline, 5 s table, 1 s drain, 5 s probe. The holder lives 30 s.
    assert took < 15
    assert "pipes still open after 1.0 s: another process holds them" in notes_of(exc)


def test_a_fact_that_cannot_be_read_is_named_and_the_timeout_is_still_raised(node, monkeypatch):
    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(node_run, "_process_table", boom)
    text = notes_of(timed_out(node, r'process.stdout.write("kept\n");' + HANG))
    assert "process table: unavailable (RuntimeError: boom)" in text
    assert re.search(r"^stdout \(5 chars\): 'kept\\n'$", text, re.M)


def test_a_diagnostic_block_that_breaks_still_kills_and_keeps_the_timeout(node, monkeypatch):
    made = spy_on_popen(monkeypatch)

    def broken(*args):
        raise RuntimeError("the whole block")

    monkeypatch.setattr(node_run, "_diagnose", broken)
    exc = timed_out(node, HANG)
    assert "node-run: the diagnostics failed: RuntimeError: the whole block" in notes_of(exc)
    ours = [proc for proc in made if proc.args == argv_of(node)]
    # `os.kill(pid, 0)` would end a process on Windows: the spy's own `poll()` is the witness.
    assert len(ours) == 1 and ours[0].poll() is not None


def test_a_failing_drain_is_named_and_the_notes_after_it_still_come(node, monkeypatch):
    def broken(exc, proc):
        raise ValueError("no pipes")

    monkeypatch.setattr(node_run, "_drain", broken)
    text = notes_of(timed_out(node, r'process.stdout.write("kept\n");' + HANG))
    assert "after kill: unavailable (ValueError: no pipes)" in text
    for later in (r"stdout \(\d+ chars\): ", r"stderr \(\d+ chars\): ",
                  rf"{re.escape(os.path.basename(node))} --version after the kill: "):
        assert re.search(rf"^{later}", text, re.M), f"{later}\n--- the notes ---\n{text}"
    assert "diagnostics failed" not in text


@pytest.mark.parametrize("source", [
    pytest.param('console.log("fine");', id="exit_zero"),
    pytest.param('console.error("bad"); process.exitCode = 3;', id="exit_non_zero"),
])
def test_a_call_that_ends_starts_node_exactly_once_each_time(node, monkeypatch, source):
    made = spy_on_popen(monkeypatch)
    argv = argv_of(node)
    first = node_run.run_node(argv, source, timeout=30)
    second = node_run.run_node(argv, source, timeout=30)
    assert (second.returncode, second.stdout, second.stderr) == (
        first.returncode, first.stdout, first.stderr)
    # No retry on a bad exit code, no warm-up before the first call, nothing else started.
    assert node_launches(made, node) == [argv, argv]


def test_a_timeout_starts_the_script_once_and_then_one_version_probe_and_nothing_else(
        node, monkeypatch):
    made = spy_on_popen(monkeypatch)
    timed_out(node, HANG)
    assert node_launches(made, node) == [argv_of(node), [node, "--version"]]


def test_a_call_that_ends_after_the_deadline_but_before_the_kill_is_still_a_timeout(
        node, monkeypatch):
    """A slow `tasklist` on a busy VM: Node ends by itself while the notes are being read."""
    made = spy_on_popen(monkeypatch)
    real = node_run._process_table

    def table_after_the_exit() -> list[list[str]]:
        made[0].wait(timeout=15)  # the script ends 2 s after its start, the deadline is 1 s
        return real()

    monkeypatch.setattr(node_run, "_process_table", table_after_the_exit)
    exc = timed_out(node, 'setTimeout(() => console.log("late"), 2000);', timeout=1.0)
    text = notes_of(exc)
    assert exc.timeout == 1.0 and exc.cmd == argv_of(node)
    assert "no retry" in text and re.search(r"^after kill: returncode 0; pipes ", text, re.M)
    assert exc.stdout == "late\n"  # the call did end, and still the verdict is the deadline's
    assert node_launches(made, node) == [argv_of(node), [node, "--version"]]


@pytest.mark.parametrize("error", [
    pytest.param(BrokenPipeError("the pipe broke"), id="os_error"),
    pytest.param(KeyboardInterrupt(), id="keyboard_interrupt"),
])
def test_an_exception_that_is_not_a_timeout_goes_up_as_it_is_and_the_process_is_killed(
        node, monkeypatch, error):
    argv, events = argv_of(node), []
    made = spy_on_popen(monkeypatch, events, killed=argv, fail=(argv, error))
    with pytest.raises(type(error)) as caught:
        node_run.run_node(argv, 'console.log("quick");', timeout=30)
    assert caught.value is error and not hasattr(error, "__notes__")
    assert node_launches(made, node) == [argv]  # nothing is retried, nothing is probed
    assert events == ["kill"]  # the process is not left behind


HELPERS = {
    "wizard": (desk_wizard_node, lambda body: desk_wizard_node.run_js(body)),
    "desk": (desk_node, lambda body: desk_node.run_js(body, {"m": "desk-copy.js"})),
}


@pytest.mark.parametrize("outcome", ["ok", "bad_exit", "hang"])
@pytest.mark.parametrize("helper", ["wizard", "desk"])
def test_a_desk_helper_starts_the_script_once_whatever_comes_of_it(
        node, monkeypatch, helper, outcome):
    module, call = HELPERS[helper]
    # The real call. Only the hang is cut to a 1 s deadline; a call that ends keeps the helper's
    # own 30 s, so a cold first start on a runner cannot turn `ok` or `bad_exit` into a timeout.
    real = node_run.run_node
    short = outcome == "hang"
    monkeypatch.setattr(module, "run_node", lambda argv, source, *, timeout: real(
        argv, source, timeout=1.0 if short else timeout))
    made = spy_on_popen(monkeypatch)
    probe: list[list[str]] = []  # only a timeout is followed by one `--version`
    if outcome == "ok":
        assert call("console.log(JSON.stringify({ok: 1}));") == {"ok": 1}
    elif outcome == "bad_exit":
        with pytest.raises(AssertionError, match="bad"):
            call('console.error("bad"); process.exitCode = 3;')
    else:
        with pytest.raises(subprocess.TimeoutExpired):
            call(HANG)
        probe = [[node, "--version"]]
    assert node_launches(made, node) == [argv_of(node)] + probe


def test_the_notes_count_the_calls_and_the_pause_before_this_one(node):
    first = notes_of(timed_out(node, HANG))
    assert "call #1 of this process: the first Node call of it" in first
    node_run._state.update(calls=0, last_end=None, warned=0)
    node_run.run_node(argv_of(node), 'console.log("quick");', timeout=30)
    time.sleep(0.3)
    second = notes_of(timed_out(node, HANG))
    pause = re.search(r"call #2 of this process; the previous Node call ended (\d+\.\d{3}) s "
                      r"before this one", second)
    # The sleep is 0.3 s on a clock that may round down a little.
    assert pause and 0.29 <= float(pause[1]) <= 0.9, second


def test_a_slow_call_that_passes_warns_and_answers_the_same(node, monkeypatch):
    monkeypatch.setattr(node_run, "SLOW_CALL", 0.2)
    with pytest.warns(UserWarning, match=r"node-run: a Node call took \d+\.\d s and passed "
                      r"\(call #1 of this process, started \d{4}-.+Z UTC at uptime ") as seen:
        done = node_run.run_node(argv_of(node), SLOW, timeout=30)
    assert (done.returncode, done.stdout, done.stderr) == (0, "ok\n", "")
    assert len(seen) == 1


def test_a_fast_call_makes_no_node_run_warning(node):
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        done = node_run.run_node(argv_of(node), 'console.log("fast");', timeout=30)
    assert done.stdout == "fast\n"
    assert [str(one.message) for one in seen if "node-run" in str(one.message)] == []


def test_the_slow_call_warnings_stop_at_the_cap(node, monkeypatch):
    monkeypatch.setattr(node_run, "SLOW_CALL", 0.2)
    monkeypatch.setattr(node_run, "SLOW_WARNINGS", 2)
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        answers = [node_run.run_node(argv_of(node), SLOW, timeout=30).stdout for _ in range(3)]
    assert answers == ["ok\n"] * 3
    assert len([one for one in seen if "node-run: a Node call took" in str(one.message)]) == 2


def test_both_desk_helpers_call_run_node_with_their_30_second_deadline(monkeypatch):
    seen: list[tuple[list[str], str, float]] = []

    def spy(argv, source, *, timeout):
        seen.append((argv, source, timeout))
        return subprocess.CompletedProcess(argv, 0, '{"ok": 1}', "")

    monkeypatch.setattr(desk_wizard_node, "run_node", spy)
    monkeypatch.setattr(desk_node, "run_node", spy)
    monkeypatch.setattr(shutil, "which", lambda name: "node-stub")
    assert desk_wizard_node.run_js("show(1)") == {"ok": 1}
    assert desk_node.run_js("console.log(1)", {"m": "desk-copy.js"}, {"x": 1}) == {"ok": 1}
    (wizard_argv, wizard_source, wizard_timeout), (desk_argv, desk_source, desk_timeout) = seen
    assert wizard_argv[1:] == desk_argv[1:] == ["--input-type=module"]
    assert wizard_timeout == desk_timeout == 30
    assert wizard_source.startswith('import * as wiz from "file:')
    assert "const d = null;" in wizard_source
    assert desk_source.startswith('import * as m from "file:')
    assert 'const d = {"x": 1};' in desk_source


def test_the_windows_process_table_reads_into_counts_and_digits():
    listing = ('"System Idle Process","0","Services","0","8\u00a0K"\r\n'
               '"node.exe","4100","Console","1","47\u00a0488\u00a0K"\r\n'
               '"MsMpEng.exe","2200","Services","0","641\u00a0452\u00a0K"\r\n'
               '"node.exe","5200","Console","1","40\u00a0008\u00a0K"\r\n'
               "INFO: junk that is not a row\r\n")
    rows = node_run._parse_tasklist(listing)
    assert node_run._windows_table_notes(rows, "NODE.exe") == [
        "processes now: 4; NODE.exe alive: 2 [4100 (47488 K), 5200 (40008 K)]",
        "background suspects: MsMpEng.exe 641452 K"]
    assert node_run._windows_table_notes(rows[:2], "node.exe")[1] == (
        "background suspects: none listed")


def test_the_posix_process_table_reads_into_counts_and_the_timed_out_row():
    listing = ("    1     0 Ss   00:00:02  9124 systemd\n"
               " 4100  4000 Sl   00:00:00 33000 node\n"
               "  200     1 S    00:00:00    12 some name\n"
               "stray line\n")
    rows = node_run._parse_ps(listing)
    assert node_run._posix_table_notes(rows, 4100, "node") == [
        "processes now: 3; node alive: 1 [4100 (33000 K)]",
        "the timed-out process (pid ppid stat time rss comm): 4100 4000 Sl 00:00:00 33000 node"]
    assert node_run._posix_table_notes(rows, 999, "node")[1].endswith(": not listed")


@pytest.mark.skipif(not WINDOWS and not os.path.exists("/proc/uptime"),
                    reason="uptime is read from Windows and Linux only")
def test_the_uptime_is_the_machine_clock_in_seconds():
    assert re.fullmatch(r"\d+\.\d{3}", node_run._uptime())
