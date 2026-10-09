"""The one AFD trace around the forward Windows gate: started only as reviewed,
stopped while the failing connect is still in the ring, never the verdict.

The gate here is a real child process standing in for the real one. When it
is asked to, it writes a failure record and then waits for the trace to stop
-- the fake netsh's `stop` is what lets it go on -- so a wrapper that only
stopped the trace at the gate's end leaves it waiting, and it answers 99.

No test here may reach the real netsh: every module-level tool call is replaced
by one that fails the test, and each test that needs netsh hands in its fake.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from browser_tests import afd_extract, gate_trace

ROOT = Path(__file__).resolve().parents[1]
GUID = "{E53C6823-7BB8-44BB-90DC-3F86090D48A6}"
NO_SESSION = "There is no trace session currently in progress."
NO_BUFFER_LINE = ("  requestfailed http://127.0.0.1:50123/panel/desk.js "
                  "net::ERR_NO_BUFFER_SPACE at=2026-10-09T10:00:05.000+00:00")
TRACEBACK_LINE = ("E   OSError: [WinError 10055] An operation on a socket could not be "
                  "performed because the system lacked sufficient buffer space")
GATE = """
import pathlib, sys, time
watch, marker, code, mode = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), \\
    int(sys.argv[3]), sys.argv[4]
(marker.parent / "ran").write_text("yes", encoding="utf-8")
if mode in ("record", "note"):
    (watch / "browser_tests_test_x.py_test_y.setup.failure.txt").write_text(
        "page said:\\n" + sys.argv[5] + "\\n", encoding="utf-8")
if mode in ("record", "wait"):
    deadline = time.monotonic() + 30
    while not marker.exists():
        if time.monotonic() > deadline:
            sys.exit(99)
        time.sleep(0.02)
sys.exit(code)
"""


class FakeNetsh:
    """netsh trace as a session that one start opens and one stop closes."""

    def __init__(self, marker: Path, provider: bool = True, help_names: tuple[str, ...] = (),
                 running: str | None = None, start_works: bool = True,
                 config: Path | None = None) -> None:
        self.marker, self.provider, self.start_works = marker, provider, start_works
        self.help_names = help_names or gate_trace.NAMES
        self.running, self.config = running, config
        self.calls: list[tuple[str, ...]] = []
        self.config_at_start: dict[str, object] | None = None

    def __call__(self, *arguments: str, timeout: float = 0) -> tuple[object, str]:
        self.calls.append(arguments)
        if arguments[:2] == ("show", "provider"):
            return (0, f"Name: {arguments[2]}\nProvider Guid: {GUID}") if self.provider \
                else (1, f"'{arguments[2]}' is not a valid or known provider.")
        if arguments[:2] == ("start", "help"):
            return 0, "\n".join(f"\t{name}=x (something)" for name in self.help_names)
        if arguments == ("show", "status"):
            return (0, f"Status: Running\nTrace File: {self.running}") if self.running \
                else (1, NO_SESSION)
        if arguments[0] == "start":
            if self.config is not None:
                self.config_at_start = json.loads(self.config.read_text(encoding="utf-8"))
            if self.start_works:
                self.running = arguments[-1].split("=", 1)[1]
            return (0, "Trace configuration:") if self.start_works else (1, "refused")
        assert arguments == ("stop",), arguments
        self.running = None
        self.marker.write_text("stopped", encoding="utf-8")
        return 0, "Tracing session was successfully stopped."

    def stops(self) -> int:
        return self.calls.count(("stop",))


@pytest.fixture(autouse=True)
def no_real_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(*arguments: object, **options: object) -> tuple[object, str]:
        raise AssertionError(f"a test reached a real tool: {arguments}")

    monkeypatch.setattr(gate_trace, "_netsh", refused)
    monkeypatch.setattr(gate_trace, "_call", refused)


@pytest.fixture
def place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.setattr(gate_trace, "WINDOWS", True)
    monkeypatch.setattr(gate_trace, "POLL_SECONDS", 0.02)
    monkeypatch.setenv("GITHUB_SHA", "f" * 40)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    paths = {name: tmp_path / name for name in ("afd", "record", "watch", "child")}
    for path in paths.values():
        path.mkdir()
    paths["marker"] = paths["child"] / "go-on"
    return paths


def _gate(place: dict[str, Path], code: int, mode: str, line: str = NO_BUFFER_LINE) -> list[str]:
    return [sys.executable, "-c", GATE, str(place["watch"]), str(place["marker"]), str(code),
            mode, line]


def _run(place: dict[str, Path], fake: FakeNetsh, monkeypatch: pytest.MonkeyPatch,
         code: int = 0, mode: str = "none", line: str = NO_BUFFER_LINE) -> int:
    monkeypatch.setattr(gate_trace, "_netsh", fake)
    return gate_trace.run(place["afd"], place["record"], place["watch"],
                          _gate(place, code, mode, line))


def _record(place: dict[str, Path], name: str) -> dict[str, object]:
    return json.loads((place["record"] / name).read_text(encoding="utf-8"))


def test_the_trace_starts_with_exactly_the_reviewed_parameters_and_no_others(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeNetsh(place["marker"], config=place["record"] / gate_trace.CONFIG)
    assert _run(place, fake, monkeypatch) == 0

    started = [call for call in fake.calls if call[0] == "start" and call[1] != "help"]
    assert len(started) == 1
    # Spelled out here, not read from the module: a changed constant reds this.
    assert started[0][:-1] == (
        "start", "provider=Microsoft-Windows-Winsock-AFD", "level=4", "capture=no",
        "report=disabled", "correlation=disabled", "persistent=no", "fileMode=circular",
        "maxSize=64")
    trace_file = Path(started[0][-1].removeprefix("traceFile="))
    assert trace_file.parent == place["afd"].resolve()
    assert re.fullmatch(r"afd-[0-9a-f]{32}\.etl", trace_file.name)
    # The config named the file BEFORE the start, so a cleanup can always find it.
    assert fake.config_at_start is not None
    assert fake.config_at_start["trace_file"] == str(trace_file)
    assert fake.config_at_start["gap"] == {"reason": "starting"}
    config = _record(place, gate_trace.CONFIG)
    assert config["available"] is True and config["sha"] == "f" * 40
    assert config["trace_file"] == str(trace_file) and config["max_seconds"] == 45 * 60
    # The provider and every parameter were asked for before the start.
    assert fake.calls[:3] == [("show", "provider", "Microsoft-Windows-Winsock-AFD"),
                              ("start", "help"), ("show", "status")]
    assert _record(place, gate_trace.STOP)["reason"] == "gate-ended" and fake.stops() == 1


@pytest.mark.parametrize("line", [NO_BUFFER_LINE, TRACEBACK_LINE])
def test_the_first_record_naming_10055_stops_the_trace_while_the_gate_still_runs(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch, line: str) -> None:
    fake = FakeNetsh(place["marker"])
    # 1 is the gate's own red; 99 would mean the stop waited for the gate's end.
    assert _run(place, fake, monkeypatch, code=1, mode="record", line=line) == 1
    stop = _record(place, gate_trace.STOP)
    assert stop["reason"] == "first-no-buffer-space" and stop["stopped"] is True
    assert stop["hit"] == {"record": "browser_tests_test_x.py_test_y.setup.failure.txt",
                           "line": line.strip()}
    assert fake.stops() == 1


@pytest.mark.parametrize("line", [
    "  owner pid 10055 held 10055 handles",
    # An exception line is evidence, but a bare number in it is a PID, not 10055.
    "E   AssertionError: the server (pid 10055) answered 500",
    # A long traceback reprints source: a docstring naming the error is not one.
    "        `net::ERR_NO_BUFFER_SPACE`. Without it a failed import is invisible",
    ">       raise OSError(10055, 'WinError 10055')",
])
def test_a_record_line_that_only_mentions_10055_is_not_a_hit(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch, line: str) -> None:
    fake = FakeNetsh(place["marker"])
    assert _run(place, fake, monkeypatch, code=1, mode="note", line=line) == 1
    assert _record(place, gate_trace.STOP)["reason"] == "gate-ended"


def test_a_start_that_breaks_after_netsh_began_stops_the_session_at_once(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    real_tail = gate_trace._tail
    calls = {"count": 0}

    def tail_that_breaks_once(text: str, lines: int = 20) -> list[str]:
        calls["count"] += 1
        if calls["count"] == 1:  # the first is the start's own, after netsh started
            raise RuntimeError("the start broke")
        return real_tail(text, lines)

    monkeypatch.setattr(gate_trace, "_tail", tail_that_breaks_once)
    fake = FakeNetsh(place["marker"])
    assert _run(place, fake, monkeypatch, code=3, mode="wait") == 3
    assert fake.stops() == 1 and _record(place, gate_trace.STOP)["reason"] == "start-broke"
    assert _record(place, "_start_or_stop-error.json")["error"] == "RuntimeError"


def test_a_trace_dir_outside_the_runner_temp_is_refused(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "elsewhere"))
    fake = FakeNetsh(place["marker"])
    assert _run(place, fake, monkeypatch, code=0) == 0
    assert fake.calls == []
    assert _record(place, gate_trace.CONFIG)["gap"] == {"reason": "trace-dir-outside-runner-temp"}


def test_the_trace_stops_at_its_deadline_while_the_gate_still_runs(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate_trace, "MAX_SECONDS", 0)
    fake = FakeNetsh(place["marker"])
    assert _run(place, fake, monkeypatch, code=0, mode="wait") == 0
    assert _record(place, gate_trace.STOP)["reason"] == "deadline" and fake.stops() == 1


@pytest.mark.parametrize("code", [0, 1, 3])
@pytest.mark.parametrize("provider", [True, False])
def test_the_gate_exit_code_is_the_wrappers_whatever_the_trace_did(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch, code: int,
        provider: bool) -> None:
    fake = FakeNetsh(place["marker"], provider=provider)
    assert _run(place, fake, monkeypatch, code=code) == code


@pytest.mark.parametrize(("fake_settings", "gap"), [
    ({"provider": False}, {"reason": "provider-unknown"}),
    ({"help_names": ("provider", "level", "traceFile", "capture", "report", "correlation",
                     "persistent", "maxSize")},
     {"reason": "parameter-unsupported", "missing": ["fileMode"]}),
    ({"running": r"C:\someone\NetTrace.etl"}, {"reason": "another-session-in-progress"}),
    ({"start_works": False}, {"reason": "start-failed"}),
])
def test_an_unavailable_trace_is_a_written_gap_and_the_gate_still_runs(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
        fake_settings: dict[str, object], gap: dict[str, object]) -> None:
    fake = FakeNetsh(place["marker"], **fake_settings)  # type: ignore[arg-type]
    assert _run(place, fake, monkeypatch, code=1) == 1
    assert (place["child"] / "ran").is_file()
    config = _record(place, gate_trace.CONFIG)
    assert config["available"] is False
    assert {key: config["gap"][key] for key in gap} == gap  # type: ignore[index]
    # Nobody's session was stopped, and a foreign one was never even started over.
    assert fake.stops() == 0 and not (place["record"] / gate_trace.STOP).exists()
    if "running" in fake_settings:
        assert fake.running == r"C:\someone\NetTrace.etl"
        assert not [call for call in fake.calls if call[0] == "start" and call[1] != "help"]


@pytest.mark.parametrize(("windows", "unset", "reason"), [
    (False, None, "not-windows"),
    (True, "GITHUB_ACTIONS", "not-a-ci-runner"),
    (True, "RUNNER_TEMP", "not-a-ci-runner"),
])
def test_off_a_windows_runner_the_wrapper_asks_netsh_nothing_and_runs_the_gate(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch, windows: bool,
        unset: str | None, reason: str) -> None:
    monkeypatch.setattr(gate_trace, "WINDOWS", windows)
    if unset:
        monkeypatch.delenv(unset)
    fake = FakeNetsh(place["marker"])
    assert _run(place, fake, monkeypatch, code=0) == 0
    assert fake.calls == [] and (place["child"] / "ran").is_file()
    assert _record(place, gate_trace.CONFIG)["gap"] == {"reason": reason}


def test_a_session_that_is_not_ours_is_never_stopped(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeNetsh(place["marker"], running=r"C:\someone\NetTrace.etl")
    monkeypatch.setattr(gate_trace, "_netsh", fake)
    mine = place["afd"] / ("afd-" + "0" * 32 + ".etl")
    result = gate_trace.stop_own(mine, place["record"], "cleanup", None)
    assert result["ours_running"] is False and result["status_unknown"] is False
    assert fake.stops() == 0 and fake.running == r"C:\someone\NetTrace.etl"


def test_a_status_that_never_answered_is_unknown_not_foreign(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate_trace, "_netsh", lambda *arguments, **options: ("timed-out", ""))
    mine = place["afd"] / ("afd-" + "0" * 32 + ".etl")
    result = gate_trace.stop_own(mine, place["record"], "cleanup", None)
    assert result["ours_running"] is False and result["status_unknown"] is True


def test_a_watch_that_breaks_still_stops_the_trace_and_the_gate_still_answers(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(watch_dir: Path, seen: dict[str, int]) -> None:
        raise RuntimeError("the watch broke")

    monkeypatch.setattr(gate_trace, "first_no_buffer", broken)
    fake = FakeNetsh(place["marker"])
    assert _run(place, fake, monkeypatch, code=1, mode="wait") == 1
    assert _record(place, gate_trace.STOP)["reason"] == "watch-failed" and fake.stops() == 1
    assert _record(place, "_trace_until_stop-error.json")["error"] == "RuntimeError"


def _collected(place: dict[str, Path]) -> Path:
    trace_file = place["afd"] / ("afd-" + "1" * 32 + ".etl")
    trace_file.write_bytes(b"etl")
    (place["record"] / gate_trace.CONFIG).write_text(json.dumps(
        {"available": True, "trace_file": str(trace_file)}), encoding="utf-8")
    (place["watch"] / "versions.json").write_text('{"chromium": "131.0"}', encoding="utf-8")
    (place["watch"] / "x.setup.failure.txt").write_text(NO_BUFFER_LINE, encoding="utf-8")
    return trace_file


def _extract(place: dict[str, Path]) -> int:
    return gate_trace.main(["--extract", "--record", str(place["record"]),
                            "--watch", str(place["watch"])])


def _writes_xml(argv: list[str], timeout: float, cwd: Path | None = None) -> tuple[object, str]:
    Path(argv[argv.index("-o") + 1]).write_text("<Events></Events>", encoding="utf-8")
    return 0, ""


def test_the_stop_before_the_reversed_order_stops_only_its_own_session_and_decodes_nothing(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    trace_file = _collected(place)
    fake = FakeNetsh(place["marker"], running=str(trace_file))
    monkeypatch.setattr(gate_trace, "_netsh", fake)
    assert gate_trace.main(["--stop", "--record", str(place["record"])]) == 0
    assert fake.stops() == 1
    assert _record(place, gate_trace.BEFORE_REVERSE)["stopped"] is True
    assert not (place["record"] / gate_trace.EXTRACT).exists()
    fake.running = r"C:\someone\NetTrace.etl"
    assert gate_trace.main(["--stop", "--record", str(place["record"])]) == 0
    assert fake.stops() == 1 and fake.running == r"C:\someone\NetTrace.etl"


def test_the_extract_stops_its_own_session_then_decodes_and_selects(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    trace_file = _collected(place)
    fake = FakeNetsh(place["marker"], running=str(trace_file))
    decoded: list[tuple[list[str], Path | None]] = []

    def tracerpt(argv: list[str], timeout: float, cwd: Path | None = None) -> tuple[object, str]:
        fake.calls.append(("tracerpt",))
        decoded.append((argv, cwd))
        Path(argv[argv.index("-o") + 1]).write_text("<Events></Events>", encoding="utf-8")
        return 0, "The command completed successfully."

    monkeypatch.setattr(gate_trace, "_netsh", fake)
    monkeypatch.setattr(gate_trace, "_call", tracerpt)
    assert _extract(place) == 0

    assert fake.stops() == 1 and _record(place, gate_trace.BEFORE_DECODE)["ours_running"] is True
    assert fake.calls.index(("stop",)) < fake.calls.index(("tracerpt",))
    ((argv, cwd),) = decoded
    assert argv[1:] == [str(trace_file), "-o", str(trace_file.with_suffix(".xml")),
                        "-of", "XML", "-y"]
    assert cwd == trace_file.parent
    extract = _record(place, gate_trace.EXTRACT)
    assert extract["decoded"] is True and extract["versions"] == {"chromium": "131.0"}
    assert extract["failures_total"] == 1 and extract["failures"][0]["ports"] == [50123]
    assert extract["before_reverse"] is None and extract["start"] is True


def test_an_extract_whose_selection_breaks_still_answers_0_and_says_why(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    trace_file = _collected(place)
    fake = FakeNetsh(place["marker"], running=str(trace_file))

    def broken(*arguments: object) -> None:
        raise ValueError("the selection broke")

    monkeypatch.setattr(gate_trace, "_netsh", fake)
    monkeypatch.setattr(gate_trace, "_call", _writes_xml)
    monkeypatch.setattr(afd_extract, "extract", broken)
    assert _extract(place) == 0
    assert _record(place, "extract_step-error.json")["error"] == "ValueError"
    assert fake.stops() == 1


OURS = "Status: Running\nTrace File: {file}"
#: netsh's answers in call order (status, then stop and status when the first names ours).
STOP_SCRIPTS = {
    "the status never answers": [("timed-out", "")],
    "the stop said yes and the session stayed": [(0, OURS), (0, "stopped"), (0, OURS)],
    "the stop and the last status never answered": [
        (0, OURS), ("timed-out", ""), ("timed-out", "")],
}


def _scripted(answers: list[tuple[object, str]], trace_file: Path):
    left = list(answers)

    def netsh(*arguments: str, timeout: float = 0) -> tuple[object, str]:
        code, said = left.pop(0) if len(left) > 1 else left[0]
        return code, said.format(file=trace_file)
    return netsh


@pytest.mark.parametrize("script", sorted(STOP_SCRIPTS))
def test_a_session_netsh_does_not_prove_gone_is_never_decoded_live(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    trace_file = _collected(place)
    monkeypatch.setattr(gate_trace, "_netsh", _scripted(STOP_SCRIPTS[script], trace_file))
    assert _extract(place) == 0
    extract = _record(place, gate_trace.EXTRACT)
    assert extract["decoded"] is False
    assert extract["reason"] == "the session may still run; a live file is not decoded"
    assert _record(place, gate_trace.BEFORE_DECODE)["stopped"] is False


def test_an_unanswered_status_after_the_stop_is_not_a_proven_stop(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    mine = place["afd"] / ("afd-" + "2" * 32 + ".etl")
    monkeypatch.setattr(gate_trace, "_netsh", _scripted(
        STOP_SCRIPTS["the stop and the last status never answered"], mine))
    result = gate_trace.stop_own(mine, place["record"], "deadline", None)
    assert result["ours_running"] is True and result["stopped"] is False
    assert result["last_status_unknown"] is True and result["last_status_exit"] == "timed-out"


def test_a_stop_before_the_reversed_order_that_proves_nothing_says_so(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    trace_file = _collected(place)
    monkeypatch.setattr(gate_trace, "_netsh", _scripted(
        STOP_SCRIPTS["the status never answers"], trace_file))
    assert gate_trace.main(["--stop", "--record", str(place["record"])]) == 0
    record = _record(place, gate_trace.BEFORE_REVERSE)
    assert record["stopped"] is False and "may have run while it was still tracing" in str(
        record["limitation"])


class UnconfirmedStart(FakeNetsh):
    """The start goes through, but the status right after it never answers."""

    def __init__(self, marker: Path, clock: dict[str, float] | None = None) -> None:
        super().__init__(marker)
        self.clock, self.just_started = clock, False

    def __call__(self, *arguments: str, timeout: float = 0) -> tuple[object, str]:
        if arguments == ("show", "status") and self.just_started:
            self.just_started = False
            self.calls.append(arguments)
            return "timed-out", ""
        found = super().__call__(*arguments, timeout=timeout)
        if arguments[0] == "start" and arguments[1] != "help":
            self.just_started = True
            if self.clock is not None:
                self.clock["now"] += 600.0  # a slow start
        return found


def test_a_start_netsh_did_not_confirm_is_still_watched_and_stopped_once_proven_ours(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    fake = UnconfirmedStart(place["marker"])
    # 99 would mean nobody watched: the gate waits for the stop the record must cause.
    assert _run(place, fake, monkeypatch, code=1, mode="record") == 1
    config = _record(place, gate_trace.CONFIG)
    assert config["available"] == "unknown" and config["gap"] == {"reason": "start-unconfirmed"}
    stop = _record(place, gate_trace.STOP)
    assert stop["reason"] == "first-no-buffer-space" and stop["stopped"] is True
    starts = [call for call in fake.calls if call[0] == "start" and call[1] != "help"]
    assert len(starts) == 1 and fake.stops() == 1


def test_the_deadline_counts_from_before_the_start(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(gate_trace, "_netsh", UnconfirmedStart(place["marker"], clock))
    session = gate_trace.start(place["afd"], place["record"], clock=lambda: clock["now"])
    assert session is not None and clock["now"] == 700.0
    assert session.deadline == 100.0 + gate_trace.MAX_SECONDS


def test_the_extract_after_no_trace_says_so_and_stops_nothing(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeNetsh(place["marker"], running=r"C:\someone\NetTrace.etl")
    monkeypatch.setattr(gate_trace, "_netsh", fake)
    assert _extract(place) == 0
    assert fake.calls == []
    assert _record(place, gate_trace.EXTRACT) == {
        "decoded": False, "reason": "no trace was collected", "gap": None}


def test_a_decoder_that_writes_nothing_is_a_stated_gap(
        place: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    trace_file = place["afd"] / "afd-x.etl"
    trace_file.write_bytes(b"etl")
    monkeypatch.setattr(gate_trace, "_call",
                        lambda argv, timeout, cwd=None: (1, "Error: no events"))
    found = gate_trace.decode(trace_file, place["watch"])
    assert found["decoded"] is False and found["reason"] == "tracerpt wrote no output"
    assert found["decoder"]["exit"] == 1  # type: ignore[index]


def test_the_module_run_as_a_process_answers_with_the_gates_own_code(tmp_path: Path) -> None:
    # Off a CI runner by construction: the wrapper must refuse to trace here.
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("GITHUB_ACTIONS", "RUNNER_TEMP")}
    environment["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT)])
    done = subprocess.run(
        [sys.executable, "-m", "browser_tests.gate_trace", "--trace-dir", str(tmp_path / "afd"),
         "--record", str(tmp_path / "record"), "--watch", str(tmp_path),
         "--", sys.executable, "-c", "import sys; sys.exit(len(sys.argv) + 2)", "--keep-going"],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=120, check=False)
    # The gate's argv arrived whole, ['-c', '--keep-going'], and its code came back: 2 + 2.
    assert done.returncode == 4, done.stderr
    config = json.loads((tmp_path / "record" / gate_trace.CONFIG).read_text(encoding="utf-8"))
    assert config["gap"]["reason"] in ("not-a-ci-runner", "not-windows")


@pytest.mark.parametrize("argv", [
    ["--record", "r", "--watch", "w", "--", "python", "gate.py"],
    ["--trace-dir", "t", "--record", "r", "--watch", "w"],
    ["--trace-dir", "t", "--record", "r", "--", "python", "gate.py"],
    ["--stop", "--record", "r", "--", "python", "gate.py"],
    ["--extract", "--record", "r", "--watch", "w", "--", "python", "gate.py"],
    ["--extract", "--record", "r"],
    ["--stop", "--extract", "--record", "r", "--watch", "w"],
])
def test_a_run_needs_its_dirs_and_a_gate_and_a_stop_or_extract_runs_none(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as refused:
        gate_trace.main(argv)
    assert refused.value.code == 2
