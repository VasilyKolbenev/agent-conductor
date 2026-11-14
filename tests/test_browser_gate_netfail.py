"""The browser gate's passive count of Chromium's ``connect failed: 10055`` (R1.3-E1).

Windows CI met one refused loopback connect in about 1900 contexts and kept nothing from the runs
that passed, so how often the event happens in a test that PASSES was not known. The conftest now
writes down, in `<artifacts>/netfail/<module>.jsonl`, every such line Chromium said in any phase of
any test whatever its outcome, every `requestfailed` that carries `ERR_NO_BUFFER_SPACE` with its
clocks (wall time, time since the page's context opened, time since any context last closed), and
closes the module's file with its totals. It only observes: no verdict, outcome or test changes.

These hold the count to what it promises: one record per real line and none for a line that merely
MENTIONS 10055, every phase and outcome scanned, nothing without the gate's variable, a directory
that cannot be written costs no test, and the clocks read exactly. The two event counts of the
closing line are never added, and a run replaces what an earlier run left in its module's file.
Above all it only observes: a session that heard the line ends with the exit code and the summary
it would have without the count, and the gate's verdict is the same whether a module heard it or
not. The fakes stand in for Playwright's objects and the events are fired by hand; the last tests
run the real hooks in child pytest sessions and the real gate over modules of their own.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from browser_tests import conftest as gate_conftest
from browser_tests import gate

ENV = gate_conftest.ARTIFACTS_ENV
MODULE = "test_studio_runs_fold"
NODE = f"browser_tests/{MODULE}.py::test_a (call)"
#: The line Windows CI run 41 printed, as Playwright's `pw:browser` channel relays Chromium's own.
CHROMIUM = (r"2026-10-20T18:12:57.076Z pw:browser [pid=2688][err] "
            r"[1020/181257.075:ERROR:net\socket\tcp_socket_win.cc:1148] connect failed: 10055")
URL = "http://127.0.0.1:55731/panel/studio-focus.js?v=7#top"
BUFFER = "net::ERR_NO_BUFFER_SPACE"

#: Lines that talk about 10055 and are not the event.
MENTIONS = {
    "a pid of 10055": CHROMIUM.replace("2688", "10055").replace("failed: 10055", "failed: 10061"),
    "another error code": CHROMIUM.replace("failed: 10055", "failed: 10061"),
    "a code that only begins with it": CHROMIUM + "1",
    "the source in a traceback": '    sample = "' + CHROMIUM + '"',
    "a message that quotes it": "E   AssertionError: " + CHROMIUM,
    "the words without the channel": CHROMIUM.split("] ", 1)[1],
    "the channel without the words": "2026-10-20T18:12:57.076Z pw:browser [pid=2688] saw 10055",
    "another socket call": CHROMIUM.replace("connect failed", "bind failed"),
}


class _Emitter:
    """What Playwright's objects offer a listener, and a way to fire what they would hear."""

    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}

    def on(self, event: str, handler) -> None:
        self.listeners.setdefault(event, []).append(handler)

    def fire(self, event: str, *heard: object) -> None:
        for handler in list(self.listeners.get(event, [])):
            handler(*heard)


class _Page(_Emitter):
    def __init__(self, context: "_Context") -> None:
        super().__init__()
        self.context = context
        self.url = "about:blank"


class _Context(_Emitter):
    def __init__(self) -> None:
        super().__init__()
        self.pages: list[_Page] = []

    def new_page(self) -> _Page:
        page = _Page(self)
        self.pages.append(page)
        self.fire("page", page)
        return page

    def close(self) -> None:
        self.fire("close", self)


class _Browser:
    def new_context(self, **_options: object) -> _Context:
        return _Context()


class _Request:
    def __init__(self, failure: object, url: str = URL) -> None:
        self.url = url
        self.failure = failure


class _Outcome:
    def __init__(self, report: pytest.TestReport) -> None:
        self.report = report

    def get_result(self) -> pytest.TestReport:
        return self.report


def _report(stderr: str = "", *, when: str = "call", outcome: str = "passed",
            module: str = MODULE) -> pytest.TestReport:
    sections = [(f"Captured stderr {when}", stderr)] if stderr else []
    return pytest.TestReport(
        f"browser_tests/{module}.py::test_a", (f"browser_tests/{module}.py", 0, "test_a"), {},
        outcome, "boom" if outcome == "failed" else None, when, sections)


def _hear(report: pytest.TestReport) -> None:
    """Drive the conftest's own report hook as pytest does: up to its yield, then the report."""
    hook = gate_conftest.pytest_runtest_makereport(None, None)
    next(hook)
    with pytest.raises(StopIteration):
        hook.send(_Outcome(report))


def _records(artifacts: Path, module: str = MODULE) -> list[dict]:
    path = artifacts / "netfail" / f"{module}.jsonl"
    if not path.exists():
        return []
    return [json.loads(row) for row in path.read_text(encoding="utf-8").splitlines()]


def _in_the_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name the running test as the gate's module would. Pytest sets this variable itself at the
    start of every phase, so it is set in a test's body, never in its fixture."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", NODE)


def _browser(monkeypatch: pytest.MonkeyPatch) -> _Browser:
    """The gate's wrapper over a fake browser, with the module's open-context list its own."""
    _in_the_module(monkeypatch)
    monkeypatch.setattr(gate_conftest, "_OPEN_CONTEXTS", [])
    return gate_conftest._instrumented(_Browser())


def _page(monkeypatch: pytest.MonkeyPatch) -> _Page:
    """A page born the way the gate's wrapper births one: through an instrumented browser."""
    return _browser(monkeypatch).new_context().new_page()


@pytest.fixture
def armed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The gate's world: its variable set, this process's counters emptied."""
    monkeypatch.setenv(ENV, str(tmp_path))
    monkeypatch.setattr(gate_conftest, "_SAID", {})
    monkeypatch.setattr(gate_conftest, "_NETFAIL", {})
    monkeypatch.setattr(gate_conftest, "_NETFAIL_OPENED", set())
    monkeypatch.setitem(gate_conftest._CLOCK, "opened", 0)
    monkeypatch.setitem(gate_conftest._CLOCK, "last_close", None)
    return tmp_path


# -- the stderr line -------------------------------------------------------------------------

def test_a_passed_report_with_the_chromium_line_gives_exactly_one_record(armed: Path) -> None:
    noise = ["2026-10-20T18:12:50.000Z pw:browser [pid=2688] <launched> pid=2688", CHROMIUM,
             "2026-10-20T18:12:58.000Z pw:browser [pid=2688][err] [other.cc:9] something else"]
    report = _report("\n".join(noise) + "\n")
    _hear(report)
    [record] = _records(armed)
    assert (record["node"], record["phase"], record["outcome"]) == (
        report.nodeid, "call", "passed")
    assert record["line"] == CHROMIUM
    assert report.outcome == "passed"


def test_every_line_is_a_record_and_the_text_kept_is_cut_at_300(armed: Path) -> None:
    long = CHROMIUM.replace(r"net\socket", "net\\" + "x" * 400 + "\\socket")
    _hear(_report(f"{CHROMIUM}\r\n{long}\r\n"))
    first, second = _records(armed)
    assert first["line"] == CHROMIUM
    assert len(second["line"]) == 300 and second["line"] == long[:300]


def test_the_phases_a_report_still_carries_are_not_counted_again(armed: Path) -> None:
    """Pytest puts every earlier phase's captured sections on each later report."""
    report = _report(CHROMIUM, when="teardown")
    report.sections[:0] = [("Captured stderr setup", CHROMIUM + "\n" + CHROMIUM),
                           ("Captured stderr call", CHROMIUM),
                           ("Captured stdout teardown", CHROMIUM)]
    assert report.capstderr.count(CHROMIUM) == 4
    _hear(report)
    [record] = _records(armed)
    assert record["phase"] == "teardown"


@pytest.mark.parametrize("when", ["setup", "call", "teardown"])
@pytest.mark.parametrize("outcome", ["passed", "failed", "skipped"])
def test_every_phase_and_every_outcome_is_scanned(
        armed: Path, monkeypatch: pytest.MonkeyPatch, when: str, outcome: str) -> None:
    monkeypatch.setattr(gate_conftest, "_write_failure_evidence", lambda item, report: None)
    report = _report(CHROMIUM, when=when, outcome=outcome)
    _hear(report)
    [record] = _records(armed)
    assert (record["phase"], record["outcome"]) == (when, outcome)
    assert report.outcome == outcome


@pytest.mark.parametrize("line", MENTIONS.values(), ids=MENTIONS.keys())
def test_a_line_that_only_mentions_10055_gives_no_record(armed: Path, line: str) -> None:
    _hear(_report(f"{line}\n"))
    assert _records(armed) == []
    assert not (armed / "netfail").exists()


def test_without_the_gate_variable_no_file_is_created(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gate_conftest, "_NETFAIL", {})
    page = _page(monkeypatch)
    _hear(_report(CHROMIUM))
    page.fire("requestfailed", _Request(BUFFER))
    page.context.close()
    gate_conftest.pytest_sessionfinish(None, 0)
    assert list(tmp_path.iterdir()) == []
    assert gate_conftest._NETFAIL == {}


def test_a_directory_that_cannot_be_written_costs_no_test(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the directory should be", encoding="utf-8")
    monkeypatch.setenv(ENV, str(blocked))
    monkeypatch.setattr(gate_conftest, "_NETFAIL", {})
    monkeypatch.setattr(gate_conftest, "_SAID", {})
    page = _page(monkeypatch)
    for outcome in ("passed", "skipped"):
        report = _report(CHROMIUM, outcome=outcome)
        _hear(report)
        assert report.outcome == outcome and report.sections == [
            ("Captured stderr call", CHROMIUM)]
    page.fire("requestfailed", _Request(BUFFER))
    page.context.close()
    gate_conftest.pytest_sessionfinish(None, 0)
    totals = gate_conftest._NETFAIL[MODULE]
    assert totals["chromium_lines"] == 2 and totals["write_errors"] >= 3
    assert MODULE in capsys.readouterr().err and blocked.read_text("utf-8").startswith("a file")


# -- requestfailed ----------------------------------------------------------------------------

def test_a_refused_buffer_request_is_written_with_its_clocks_to_the_millisecond(
        armed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    browser = _browser(monkeypatch)
    first = browser.new_context()
    first_page = first.new_page()
    now[0] = 100.5
    first_page.fire("requestfailed", _Request(BUFFER))
    now[0] = 101.0
    first.close()
    now[0] = 102.0
    second_page = browser.new_context().new_page()
    now[0] = 102.25
    second_page.fire("requestfailed", _Request(BUFFER))
    one, two = _records(armed)
    assert [row["kind"] for row in (one, two)] == ["requestfailed"] * 2
    assert (one["context_index"], one["ms_since_open"], one["ms_since_last_close"]) == (
        1, 500, None)
    assert (two["context_index"], two["ms_since_open"], two["ms_since_last_close"]) == (
        2, 250, 1250)
    assert one["node"] == two["node"] == NODE
    assert one["path"] == "/panel/studio-focus.js" and one["failure"] == BUFFER
    stamp = datetime.datetime.fromisoformat(one["time"])
    assert stamp.utcoffset() == datetime.timedelta(0)
    assert abs(datetime.datetime.now(datetime.timezone.utc) - stamp).total_seconds() < 60


def test_only_the_path_of_the_url_is_written(armed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = _page(monkeypatch)
    page.fire("requestfailed", _Request(BUFFER, "http://127.0.0.1:55731/panel/a.js?token=s3#frag"))
    text = (armed / "netfail" / f"{MODULE}.jsonl").read_text(encoding="utf-8")
    assert json.loads(text)["path"] == "/panel/a.js"
    assert not any(word in text for word in ("token", "s3", "frag", "?", "#", "127.0.0.1"))


@pytest.mark.parametrize("failure", ["net::ERR_ABORTED", "net::ERR_CONNECTION_REFUSED", "", None])
def test_any_other_failure_is_no_record_and_the_page_still_hears_it(
        armed: Path, monkeypatch: pytest.MonkeyPatch, failure: object) -> None:
    page = _page(monkeypatch)
    page.fire("requestfailed", _Request(failure))
    assert _records(armed) == []
    [said] = gate_conftest._SAID[page]
    assert said.startswith(f"requestfailed {URL} {failure or ''} at=")


def test_one_event_is_one_record_and_one_line_in_the_page_store(
        armed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = _page(monkeypatch)
    page.fire("requestfailed", _Request(BUFFER))
    assert len(_records(armed)) == 1
    assert len(gate_conftest._SAID[page]) == 1


def test_a_page_whose_context_is_unknown_is_still_written_without_its_clocks(
        armed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _in_the_module(monkeypatch)

    class Stray(_Emitter):
        @property
        def context(self) -> object:
            raise RuntimeError("no context for this page")

    stray = Stray()
    gate_conftest._remember(stray)
    stray.fire("requestfailed", _Request(BUFFER))
    [record] = _records(armed)
    assert record["failure"] == BUFFER
    assert record["context_index"] is None and record["ms_since_open"] is None


def test_counting_that_cannot_read_what_it_is_given_raises_nothing(
        armed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Called by hand: a listener that raised would surface in the test's next Playwright call."""
    class Unreadable:
        @property
        def failure(self) -> str:
            raise RuntimeError("no failure here")

    class Unwatchable:
        def on(self, *_heard: object) -> None:
            raise RuntimeError("no listeners today")

    gate_conftest._note_no_buffer_space(_page(monkeypatch), Unreadable())
    gate_conftest._track_context(Unwatchable())
    gate_conftest._note_netfail(None)
    assert _records(armed) == []


# -- the closing line --------------------------------------------------------------------------

def test_the_closing_line_has_the_totals_of_the_module(
        armed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    browser = _browser(monkeypatch)
    first, second = browser.new_context(), browser.new_context()
    page = second.new_page()
    page.fire("requestfailed", _Request(BUFFER))
    page.fire("requestfailed", _Request("net::ERR_ABORTED"))
    first.close()
    _hear(_report(f"{CHROMIUM}\n{CHROMIUM}\n"))
    gate_conftest.pytest_sessionfinish(None, 0)
    *events, closing = _records(armed)
    assert [row["kind"] for row in events] == ["requestfailed", "chromium-line", "chromium-line"]
    assert closing["kind"] == "summary" and closing["module"] == MODULE
    assert (closing["contexts_opened"], closing["contexts_closed"]) == (2, 1)
    assert (closing["requestfailed"], closing["chromium_lines"]) == (1, 2)
    assert closing["write_errors"] == 0 and closing["time"]


def test_a_module_that_heard_nothing_still_closes_its_file(armed: Path) -> None:
    _hear(_report("an ordinary line\n"))
    gate_conftest.pytest_sessionfinish(None, 0)
    [closing] = _records(armed)
    assert closing["kind"] == "summary" and closing["module"] == MODULE
    assert (closing["contexts_opened"], closing["chromium_lines"], closing["requestfailed"],
            closing["write_errors"]) == (0, 0, 0, 0)


def test_one_incident_heard_twice_is_one_in_each_count_and_the_two_are_never_added(
        armed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chromium says its line and the page then sees the request fail: one refused connect.

    The rule "5 per order" counts incidents, so a field that added the two views would read 2 for
    this one. The closing line has the two counts and no sum, under any name: no value is 2.
    """
    page = _page(monkeypatch)
    _hear(_report(CHROMIUM + "\n"))
    page.fire("requestfailed", _Request(BUFFER))
    gate_conftest.pytest_sessionfinish(None, 0)
    *events, closing = _records(armed)
    assert sorted(row["kind"] for row in events) == ["chromium-line", "requestfailed"]
    assert (closing["chromium_lines"], closing["requestfailed"]) == (1, 1)
    assert set(closing) == {"kind", "module", "time", "contexts_opened", "contexts_closed",
                            "chromium_lines", "requestfailed", "write_errors"}
    assert 2 not in closing.values()


# -- a run replaces what an earlier run left ------------------------------------------------------

def _earlier_run(artifacts: Path, module: str = MODULE) -> Path:
    """The file an earlier run left for a module: a stale line and a stale closing line."""
    path = artifacts / "netfail" / f"{module}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"kind": "chromium-line", "node": "STALE", "line": "STALE"}) + "\n"
        + json.dumps({"kind": "summary", "module": module, "chromium_lines": 9}) + "\n",
        encoding="utf-8")
    return path


def test_the_first_line_of_a_session_replaces_the_file_an_earlier_run_left(armed: Path) -> None:
    here, elsewhere = _earlier_run(armed), _earlier_run(armed, "test_some_other_module")
    other = elsewhere.read_bytes()
    _hear(_report(CHROMIUM))
    [record] = _records(armed)
    assert record["line"] == CHROMIUM and "STALE" not in here.read_text(encoding="utf-8")
    assert elsewhere.read_bytes() == other  # another module's file is not this session's to touch


def test_the_lines_of_one_session_after_its_first_are_appended(armed: Path) -> None:
    _earlier_run(armed)
    _hear(_report(f"{CHROMIUM}\n{CHROMIUM}\n"))
    _hear(_report(CHROMIUM, when="teardown"))
    gate_conftest.pytest_sessionfinish(None, 0)
    *lines, closing = _records(armed)
    assert [row["kind"] for row in lines] == ["chromium-line"] * 3
    assert [row["phase"] for row in lines] == ["call", "call", "teardown"]
    assert closing["kind"] == "summary" and closing["chromium_lines"] == 3


def test_a_module_that_heard_nothing_replaces_the_old_file_with_its_closing_line(
        armed: Path) -> None:
    path = _earlier_run(armed)
    _hear(_report("an ordinary line\n"))
    gate_conftest.pytest_sessionfinish(None, 0)
    [closing] = _records(armed)
    assert closing["kind"] == "summary" and closing["chromium_lines"] == 0
    assert "STALE" not in path.read_text(encoding="utf-8")


# -- the real hooks, in child sessions -----------------------------------------------------------

#: A copy of the conftest runs these. Chromium's line goes to stderr in a passing call, in a failing
#: call, in a setup and in a teardown, lines that only mention 10055 go there too, and one test
#: has a refused buffer request fired through the conftest's own wrapper.
INNER = r'''
import sys

LINE = ("2026-10-20T18:12:57.076Z pw:browser [pid=2688][err] "
        "[1020/181257.075:ERROR:net\\socket\\tcp_socket_win.cc:1148] connect failed: 10055")
OTHER = LINE.replace("failed: 10055", "failed: 10061")

import pytest


@pytest.fixture
def loud_setup():
    sys.stderr.write(LINE + "\n")
    yield


@pytest.fixture
def loud_teardown():
    yield
    sys.stderr.write(LINE + "\n")


class Fake:
    def __init__(self):
        self.heard = {}

    def on(self, event, handler):
        self.heard.setdefault(event, []).append(handler)

    def fire(self, event, *args):
        for handler in list(self.heard.get(event, [])):
            handler(*args)

    def close(self):
        self.fire("close", self)


class Browser:
    def new_context(self, **options):
        return Fake()


def test_a_passes_while_chromium_complains():
    sys.stderr.write(LINE + "\n")


def test_b_fails_while_chromium_complains():
    sys.stderr.write(LINE + "\n")
    assert False, "B fails"


def test_c_hears_only_mentions():
    sys.stderr.write(OTHER + "\n")


def test_d_has_a_loud_setup(loud_setup):
    pass


def test_e_has_a_loud_teardown(loud_teardown):
    pass


def test_f_sees_a_refused_buffer_request():
    import conftest

    context = conftest._instrumented(Browser()).new_context()
    page, refused = Fake(), Fake()
    page.context = context
    refused.url = "http://127.0.0.1:55731/panel/a.js?token=s3"
    refused.failure = "net::ERR_NO_BUFFER_SPACE"
    context.fire("page", page)
    page.fire("requestfailed", refused)
'''
#: The same module with its one failing test made to pass, and one with nothing to hear.
GREEN = INNER.replace('    assert False, "B fails"\n', "    pass\n")
QUIET = "def test_nothing_is_said():\n    assert True\n"
assert GREEN != INNER


def _project(root: Path, body: str) -> Path:
    """A project of its own: a copy of the conftest and one test module."""
    project = root / "project"
    project.mkdir()
    (project / "conftest.py").write_text(
        Path(gate_conftest.__file__).read_text(encoding="utf-8"), encoding="utf-8")
    (project / "test_inner.py").write_text(body, encoding="utf-8")
    return project


def _session(project: Path, name: str, *, armed: bool) -> subprocess.CompletedProcess:
    """One child pytest session over the project, with the gate's variable set or not at all."""
    environment = {key: value for key, value in os.environ.items()
                   if key not in (ENV, "PYTEST_ADDOPTS")}
    if armed:
        environment[ENV] = str(project / "artifacts")
    return subprocess.run(
        [sys.executable, "-B", "-m", "pytest", str(project), "-q", "-p", "no:cacheprovider",
         "-o", "addopts=", "--rootdir", str(project), "--basetemp", str(project.parent / name)],
        cwd=project, env=environment, capture_output=True, text=True, timeout=180)


def _verdict(done: subprocess.CompletedProcess) -> tuple:
    """What a session says about its tests, without its clock: exit code, failures, counts."""
    failed = sorted(re.findall(r"^FAILED (\S+)", done.stdout, re.MULTILINE))
    counts = re.sub(r"\s+in [\d.]+s.*$", "", done.stdout.strip().splitlines()[-1])
    return done.returncode, failed, counts


def test_the_real_hooks_count_a_passing_test_a_failing_one_and_every_phase(
        tmp_path: Path) -> None:
    project = _project(tmp_path, INNER)
    done = _session(project, "bt", armed=True)
    output = done.stdout[-2000:] + done.stderr[-1000:]
    assert done.returncode == 1 and "1 failed, 5 passed" in done.stdout, output
    *lines, closing = _records(project / "artifacts", "test_inner")
    chromium = [row for row in lines if row["kind"] == "chromium-line"]
    seen = sorted((row["node"].split("::")[1], row["phase"], row["outcome"]) for row in chromium)
    assert seen == [
        ("test_a_passes_while_chromium_complains", "call", "passed"),
        ("test_b_fails_while_chromium_complains", "call", "failed"),
        ("test_d_has_a_loud_setup", "setup", "passed"),
        ("test_e_has_a_loud_teardown", "teardown", "passed")], output
    assert {row["line"] for row in chromium} == {CHROMIUM}
    [refused] = [row for row in lines if row["kind"] == "requestfailed"]
    assert refused["node"].startswith("test_inner.py::test_f_sees_a_refused_buffer_request")
    assert (refused["path"], refused["failure"], refused["context_index"]) == (
        "/panel/a.js", BUFFER, 1), output
    assert closing["kind"] == "summary" and closing["module"] == "test_inner", output
    assert (closing["chromium_lines"], closing["requestfailed"]) == (4, 1)
    assert (closing["contexts_opened"], closing["contexts_closed"]) == (1, 1)


@pytest.mark.parametrize(("body", "code", "failed", "counts", "events"), [
    (GREEN, 0, [], "6 passed", 5),
    (INNER, 1, ["test_inner.py::test_b_fails_while_chromium_complains"], "1 failed, 5 passed", 5),
    (QUIET, 0, [], "1 passed", 0)],
    ids=["every kind of line, every test passes", "the same, one test fails", "nothing heard"])
def test_a_session_that_heard_the_line_ends_as_it_would_without_the_count(
        tmp_path: Path, body: str, code: int, failed: list, counts: str, events: int) -> None:
    """The count only observes. The same project, run without the gate's variable and with it,
    leaves pytest with the same exit code and the same counts and failures; the armed run did hear
    (its file says so), the bare one wrote nothing."""
    project = _project(tmp_path, body)
    bare = _session(project, "bt-bare", armed=False)
    assert not (project / "artifacts").exists()
    counted = _session(project, "bt-counted", armed=True)
    output = (counted.stdout + counted.stderr)[-2000:]
    assert _verdict(bare) == _verdict(counted) == (code, failed, counts), output
    heard = [row for row in _records(project / "artifacts", "test_inner")
             if row["kind"] != "summary"]
    assert len(heard) == events, output


def test_a_second_session_over_the_same_artifacts_leaves_only_its_own_lines(
        tmp_path: Path) -> None:
    project = _project(tmp_path, INNER)
    first = _session(project, "bt-first", armed=True)
    one = _records(project / "artifacts", "test_inner")
    second = _session(project, "bt-second", armed=True)
    two = _records(project / "artifacts", "test_inner")
    assert first.returncode == second.returncode == 1
    assert len(one) == len(two) == 6 and [row["kind"] for row in two].count("summary") == 1


# -- the real gate, over modules of its own ----------------------------------------------------

LOUD = f"import sys\n\n\ndef test_loud():\n    sys.stderr.write({CHROMIUM!r} + '\\n')\n"
LOUD_RED = LOUD + "    assert False, 'deliberate'\n"
QUIET_GREEN = "def test_green():\n    assert True\n"
QUIET_RED = "def test_red():\n    assert False, 'deliberate'\n"


def _gate(tmp_path: Path, modules: dict[str, str], reverse: bool) -> tuple[int, dict]:
    """The real runner, the real conftest, modules of the test's own: its exit code and report."""
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir()
    shutil.copyfile(gate_conftest.__file__, modules_dir / "conftest.py")
    for name, body in modules.items():
        (modules_dir / name).write_text(body, encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    code = gate.run_gate(modules_dir, artifacts, reverse, True, timeout=170, keep_going=True)
    return code, json.loads((artifacts / "gate.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("reverse", [False, True], ids=["normal order", "reverse order"])
def test_a_module_that_heard_the_line_leaves_the_gate_green_in_either_order(
        tmp_path: Path, reverse: bool) -> None:
    code, report = _gate(
        tmp_path, {"test_a_loud.py": LOUD, "test_b_quiet.py": QUIET_GREEN}, reverse)
    assert (code, report["result"], report["complete"]) == (0, "green", True), report
    assert report["failures"] == [] and report["stopped"] is None
    assert [row["exit_code"] for row in report["records"]] == [0, 0]
    assert {row["pytest_end"] for row in report["records"]} == {"ordinary"}
    assert all(row[name] == 0 for row in report["records"] for name in gate.WAIVER_OUTCOMES)
    artifacts = tmp_path / "artifacts"
    loud = _records(artifacts, "test_a_loud")  # the count was armed and did hear the line
    assert [(row["kind"], row.get("outcome")) for row in loud] == [
        ("chromium-line", "passed"), ("summary", None)]
    [quiet] = _records(artifacts, "test_b_quiet")
    assert quiet["kind"] == "summary" and quiet["chromium_lines"] == 0


def test_a_heard_line_changes_neither_which_modules_are_red_nor_the_gates_exit(
        tmp_path: Path) -> None:
    modules = {"test_a_loud_green.py": LOUD, "test_b_loud_red.py": LOUD_RED,
               "test_c_quiet_red.py": QUIET_RED, "test_d_quiet_green.py": QUIET_GREEN}
    code, report = _gate(tmp_path, modules, False)
    assert (code, report["result"], report["complete"]) == (1, "red", True), report
    assert report["failures"] == ["test_b_loud_red.py", "test_c_quiet_red.py"]
    assert {row["module"]: row["exit_code"] for row in report["records"]} == {
        "test_a_loud_green.py": 0, "test_b_loud_red.py": 1, "test_c_quiet_red.py": 1,
        "test_d_quiet_green.py": 0}
    loud, quiet = (row for row in report["records"]
                   if row["module"] in ("test_b_loud_red.py", "test_c_quiet_red.py"))
    same = ("exit_code", "pytest_end", *gate.WAIVER_OUTCOMES)
    assert {name: loud[name] for name in same} == {name: quiet[name] for name in same}
    heard = _records(tmp_path / "artifacts", "test_b_loud_red")
    assert [(row["kind"], row.get("outcome")) for row in heard] == [
        ("chromium-line", "failed"), ("summary", None)]
