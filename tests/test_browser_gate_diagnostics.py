"""The browser gate's host picture: added to a failure's record, never in its place.

Windows CI run 36258690638 failed a fixture's navigation with Chromium's
``connect failed: 10055`` (ERR_NO_BUFFER_SPACE), and the record could not say
whose resource was short. ``browser_tests/host_snapshot.py`` now appends a
picture of this run's processes and the host's sockets; these checks hold it to
its two promises -- the original failure stays first and whole, and a picture
that cannot be taken says so in its place instead of raising.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from browser_tests import conftest as gate_conftest
from browser_tests import host_snapshot

_URL = "http://127.0.0.1:55731/panel/graph.html"
_ORIGINAL = f"Page.goto: net::ERR_NO_BUFFER_SPACE at {_URL}"

_NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    127.0.0.1:55731        0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:55731        127.0.0.1:61001        ESTABLISHED     4242
  TCP    127.0.0.1:61001        127.0.0.1:55731        ESTABLISHED     5492
  TCP    127.0.0.1:61002        127.0.0.1:55731        TIME_WAIT       0
  TCP    10.0.0.4:49700         20.1.2.3:443           ESTABLISHED     900
  TCP    [::1]:7000             [::]:0                 ПРОСЛУШИВАНИЕ   900
  TCP    [::1]:7001             [::]:0                 IN ASCOLTO      900
  UDP    0.0.0.0:5353           *:*                                    900
"""


class _Report:
    nodeid = "browser_tests/test_graph_rendered.py::test_a_step[light]"
    when = "setup"
    longreprtext = _ORIGINAL


class _Item:
    funcargs = {"graph_url": _URL}


def _record(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv(gate_conftest.ARTIFACTS_ENV, str(tmp_path))
    monkeypatch.setattr(host_snapshot, "_TAKEN", {"failures": 0})
    gate_conftest._write_failure_evidence(_Item(), _Report())
    return next(tmp_path.glob("*.setup.failure.txt")).read_text("utf-8")


def test_a_setup_failure_keeps_its_error_first_and_gains_the_host_picture(
        tmp_path: Path, monkeypatch) -> None:
    text = _record(tmp_path, monkeypatch)
    head, marker, picture = text.partition("host snapshot at the failure, before teardown:\n")
    assert _ORIGINAL in head and marker, text
    facts = json.loads(picture)
    assert facts["loopback_ports"] == [55731]
    assert facts["pytest_pid"] > 0 and facts["time"]
    if sys.platform == "win32":
        assert facts["this_run"][0]["pid"] == facts["pytest_pid"]
        assert {"handles", "threads", "created"} <= set(facts["this_run"][0])
        assert "55731" in facts["tcp"]["ports"] and facts["system"]["handles"] > 0
    else:
        assert "Windows only" in facts["host"]


def test_a_host_picture_that_cannot_be_taken_never_costs_the_failure(
        tmp_path: Path, monkeypatch) -> None:
    def refuse(_ports=()):
        raise RuntimeError("no picture here")

    monkeypatch.setattr(host_snapshot, "snapshot", refuse)
    text = _record(tmp_path, monkeypatch)
    assert text.index(_ORIGINAL) < text.index("host snapshot unavailable: RuntimeError")


def test_the_socket_table_names_the_listener_and_this_runs_states_at_the_port() -> None:
    rows = host_snapshot.parse_netstat(_NETSTAT)
    assert len(rows) == 7, rows
    assert rows[-1]["state"] == "IN ASCOLTO" and rows[-1]["listening"] is True
    summary = host_snapshot.tcp_summary(rows, [55731], [4242, 5492], {4242: "python.exe"})
    port = summary["ports"]["55731"]
    assert port["listeners"] == [4242]
    assert port["by_state"] == {"LISTENING": 1, "ESTABLISHED": 2, "TIME_WAIT": 1}
    assert summary["this_run"] == {"4242": {"LISTENING": 1, "ESTABLISHED": 1},
                                   "5492": {"ESTABLISHED": 1}}
    assert summary["loopback_by_state"]["TIME_WAIT"] == 1
    assert [row["listening"] for row in rows if row["pid"] == 900] == [False, True, True]


#: ``netstat -anoq`` adds the TCP ports a process has bound but not connected: they hold
#: dynamic ports and plain ``-ano`` never shows them (CI run 37482638641's pictures could
#: not count them at its four 10055 connects).
_NETSTAT_BOUND = """
  TCP    127.0.0.1:55731        0.0.0.0:0              LISTENING       4242
  TCP    0.0.0.0:49179          0.0.0.0:0              BOUND           2588
  TCP    0.0.0.0:49180          0.0.0.0:0              BOUND           2588
  TCP    0.0.0.0:49181          0.0.0.0:0              BOUND           900
"""
_NETSH_EN = """
Protocol tcp Dynamic Port Range
---------------------------------
Start Port      : 49152
Number of Ports : 16384
"""
_NETSH_RU = """
Протокол tcp: диапазон динамических портов
---------------------------------
Начальный порт  : 1025
Число портов    : 64511
"""


def test_a_bound_port_is_counted_by_its_owner_and_is_no_listener() -> None:
    rows = host_snapshot.parse_netstat(_NETSTAT_BOUND)
    assert [row["listening"] for row in rows] == [True, False, False, False]
    summary = host_snapshot.tcp_summary(rows, [55731], [4242], {2588: "chrome.exe"})
    assert summary["by_state"]["BOUND"] == 3
    assert summary["bound_by_owner"] == [[2588, "chrome.exe", 2], [900, "?", 1]]
    assert summary["ports"]["55731"]["listeners"] == [4242]


def test_the_socket_table_is_read_with_bound_ports(monkeypatch) -> None:
    seen: list[list[str]] = []

    class _Done:
        stdout = _NETSTAT_BOUND

    def run(argv, **_options):
        seen.append(list(argv))
        return _Done()

    monkeypatch.setattr(host_snapshot.subprocess, "run", run)
    assert len(host_snapshot._netstat()) == 4
    assert seen[0][1:] == ["-anoq"]


def test_the_dynamic_port_range_is_read_in_any_language() -> None:
    assert host_snapshot.parse_dynamic_ports(_NETSH_EN) == {"start": 49152, "count": 16384}
    assert host_snapshot.parse_dynamic_ports(_NETSH_RU) == {"start": 1025, "count": 64511}
    assert host_snapshot.parse_dynamic_ports("no numbers here") is None


def test_a_cascade_of_failures_pays_for_only_the_first_pictures(monkeypatch) -> None:
    taken: list[object] = []
    monkeypatch.setattr(host_snapshot, "_TAKEN", {"failures": 0})
    monkeypatch.setattr(host_snapshot, "snapshot",
                        lambda ports=(): taken.append(ports) or {"ports": list(ports)})
    sections = [host_snapshot.failure_section({"url": _URL}, "", [])
                for _ in range(host_snapshot.FAILURE_PICTURES + 2)]
    assert len(taken) == host_snapshot.FAILURE_PICTURES
    assert all(section.startswith("host snapshot skipped")
               for section in sections[host_snapshot.FAILURE_PICTURES:])


def test_the_reaper_keeps_a_close_that_raised_instead_of_dropping_it(monkeypatch) -> None:
    class Raising:
        def close(self) -> None:
            raise RuntimeError("Target page, context or browser has been closed")

    class Quiet:
        def close(self) -> None:
            return None

    reaped = {"returned": 0, "raised": 0, "errors": []}
    monkeypatch.setattr(gate_conftest, "_REAPED", reaped)
    monkeypatch.setattr(gate_conftest, "_OPEN_CONTEXTS", [Quiet(), Raising()])
    gate_conftest._reap_contexts()
    assert gate_conftest._OPEN_CONTEXTS == []
    assert reaped["returned"] == 1 and reaped["raised"] == 1
    assert "has been closed" in reaped["errors"][0]


def test_a_module_boundary_writes_both_pictures_and_what_the_module_left(
        tmp_path: Path) -> None:
    boundary = host_snapshot.ModuleBoundary(str(tmp_path))
    boundary.finish(contexts_left=2, reaped={"returned": 3, "raised": 0, "errors": []})
    written = json.loads((tmp_path / "host" / f"{Path(__file__).stem}.json")
                         .read_text("utf-8"))
    assert written["contexts_left_at_close"] == 2
    assert written["reaped"]["returned"] == 3
    assert written["start"]["pytest_pid"] == written["end"]["pytest_pid"] > 0
