"""`conduct hub [--port N]`: one hub, one loopback port, the hub page and its files (4.1, 4.1.7).

The command runs in this process on a home of its own (`CONDUCT_HOME`) with a stop event standing
in for Ctrl+C, so the hub is a real one: it takes `hub.lock`, binds, serves `hub.html` and the
files of `HUB_ASSETS`, and answers the routes this build has. What it refuses it refuses on ONE
stderr line `conduct hub: refused <code>: <detail>` with nothing on stdout and exit 1: a home
inside a project (before the folder is made), a relative `CONDUCT_HOME`, a port that is taken, a
`hub-state.json` that is not the schema. A second hub prints the first one's address and exits 0.
"""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

from conductor.__main__ import _build_parser, main
from conductor.hub import cli, instance
from tests._hub_stack import request


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    folder = tmp_path / "home"
    monkeypatch.setenv("CONDUCT_HOME", str(folder))
    return folder


class Hub:
    """`hub_command` on a thread, its stdout read for the address it prints."""

    def __init__(self, capsys, port: int = 0) -> None:
        self.stop = threading.Event()
        self.code: list[int] = []
        self.capsys = capsys
        self.out = ""
        self.err = ""
        self.thread = threading.Thread(
            target=lambda: self.code.append(cli.hub_command(port, stop=self.stop)), daemon=True)
        self.thread.start()

    def address(self, seconds: float = 20.0) -> str:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            captured = self.capsys.readouterr()
            self.out += captured.out
            self.err += captured.err
            if self.out.count("\n") >= 1:
                return self.out.splitlines()[0]
            time.sleep(0.05)
        raise AssertionError(f"the hub printed no address; stderr: {self.err!r}")

    @property
    def port(self) -> int:
        return int(self.address().rsplit(":", 1)[1].rstrip("/"))

    def finish(self) -> int:
        self.stop.set()
        self.thread.join(20)
        assert not self.thread.is_alive(), "the hub did not exit"
        return self.code[0]


@pytest.fixture
def hub(home, capsys):
    made = []

    def start(port: int = 0) -> Hub:
        made.append(Hub(capsys, port))
        return made[-1]

    yield start
    for one in made:
        if one.thread.is_alive():
            one.finish()


def test_the_command_is_hub_with_a_port_that_defaults_to_7700():
    args = _build_parser().parse_args(["hub"])
    assert args.command == "hub" and args.port == 7700
    assert _build_parser().parse_args(["hub", "--port", "0"]).port == 0
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["hub", "--host", "0.0.0.0"])


def test_a_hub_prints_its_address_and_serves_the_page_the_files_and_the_routes_it_has(hub, home):
    running = hub()
    address = running.address()
    assert address.startswith("http://127.0.0.1:") and address.endswith("/")
    port = running.port
    page = request(port, "GET", "/")
    assert page.status == 200 and b"<html" in page.body.lower()
    assert request(port, "GET", "/hub/hub.js").status == 200
    assert request(port, "GET", "/hub/session").json()["origin"] == address.rstrip("/")
    projects = request(port, "GET", "/hub/projects").json()
    assert projects["projects"] == [] and projects["active_project_id"] is None
    assert request(port, "GET", "/hub/limits").json()["source"] == "none"
    assert request(port, "GET", "/hub/setup").json()["hub_job"] in ("none", "breakaway",
                                                                    "kill_on_close")
    record = instance.read_hub_json(home)
    assert record is not None and record.port == port and record.url == address
    assert running.finish() == 0
    assert instance.read_hub_json(home) is None, "hub.json was left behind"
    instance.HubInstance.acquire(home).close()                   # hub.lock is free again


def test_a_second_hub_prints_the_first_ones_address_says_so_and_exits_zero(hub, capsys):
    first = hub()
    address = first.address()
    capsys.readouterr()
    assert main(["hub", "--port", "0"]) == 0
    out, err = capsys.readouterr()
    assert out == address + "\n" and err.count("\n") == 1 and "already running" in err
    assert request(first.port, "GET", "/hub/session").status == 200, "the first hub is untouched"


def test_a_home_inside_a_project_is_refused_on_one_line_before_anything_is_made(
        tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    (project / ".conduct").mkdir(parents=True)
    inside = project / "deep" / "home"
    monkeypatch.setenv("CONDUCT_HOME", str(inside))
    assert main(["hub", "--port", "0"]) == 1
    out, err = capsys.readouterr()
    assert out == "" and err.count("\n") == 1 and "Traceback" not in err
    assert err.startswith("conduct hub: refused conduct_home_invalid: ")
    assert not inside.exists() and not (project / "deep").exists(), "the hub made its folder"


def test_a_relative_conduct_home_is_refused_conduct_home_invalid(monkeypatch, capsys):
    monkeypatch.setenv("CONDUCT_HOME", "relative/home")
    assert main(["hub", "--port", "0"]) == 1
    out, err = capsys.readouterr()
    assert out == "" and err.startswith("conduct hub: refused conduct_home_invalid: ")
    assert err.count("\n") == 1


def test_a_port_that_is_taken_is_hub_bind_failed_and_the_lock_is_let_go(home, capsys):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        assert main(["hub", "--port", str(taken.getsockname()[1])]) == 1
    out, err = capsys.readouterr()
    assert out == "" and err.startswith("conduct hub: refused hub_bind_failed: ")
    assert err.count("\n") == 1
    instance.HubInstance.acquire(home).close()


def test_a_hub_state_that_is_not_the_schema_is_refused_and_left_as_the_owner_wrote_it(
        home, capsys):
    home.mkdir(parents=True)
    (home / "hub-state.json").write_text("{not the schema", encoding="utf-8")
    assert main(["hub", "--port", "0"]) == 1
    out, err = capsys.readouterr()
    assert out == "" and err.startswith("conduct hub: refused hub_state_invalid: ")
    assert (home / "hub-state.json").read_text(encoding="utf-8") == "{not the schema"
    instance.HubInstance.acquire(home).close()


def test_the_exit_report_names_each_child_with_its_deadline_or_says_it_is_done():
    from datetime import datetime, timezone
    deadline = datetime(2026, 9, 30, 16, 40, tzinfo=timezone.utc)
    line = cli.exit_report([("web-app", deadline, False), ("landing", None, True)])
    assert line == ("conduct hub: waiting for the children to stop: web-app until 16:40 UTC, "
                    "landing done")
    assert cli.exit_report([("web-app", None, False)]) == \
        "conduct hub: waiting for the children to stop: web-app"
    assert cli.exit_report([]) == "conduct hub: no child to wait for"


def test_the_command_line_itself_serves_and_prints_its_address_in_a_process_of_its_own(tmp_path):
    import os
    import subprocess
    import sys
    source = Path(__file__).resolve().parents[1] / "src"
    env = {**os.environ, "CONDUCT_HOME": str(tmp_path / "home"), "PYTHONPATH": str(source)}
    process = subprocess.Popen([sys.executable, "-m", "conductor", "hub", "--port", "0"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
    try:
        address = process.stdout.readline().strip()
        assert address.startswith("http://127.0.0.1:") and address.endswith("/"), address
        port = int(address.rsplit(":", 1)[1].rstrip("/"))
        assert request(port, "GET", "/hub/session").status == 200
        assert request(port, "GET", "/").status == 200
    finally:
        process.kill()
        process.wait(10)
        for stream in (process.stdout, process.stderr):
            stream.close()


def test_the_exit_of_the_hub_closes_the_pipe_of_every_child_it_started(
        hub, home, tmp_path, monkeypatch, capsys):
    from conductor import ownership_native
    from conductor.hub import registry, spawn
    from tests._hub_world import FakeChild, FakeSpawner

    class Draining(FakeChild):
        def close_stdin(self) -> None:
            super().close_stdin()
            self.code = 0                                 # it drains and leaves at once

    class Spawner(FakeSpawner):
        def start(self, **arguments):
            found = Draining(**arguments)
            self.calls.append(arguments)
            self.children.append(found)
            return found

    spawner = Spawner()
    monkeypatch.setattr(spawn, "Spawner", lambda folder, *, hub_origin: spawner)
    root = tmp_path / "project"
    root.mkdir()
    registry.add_project(project_id="a" * 32, root=str(root), name="web-app", folder=home,
                         root_identity=tuple(ownership_native.identity(str(root))),
                         now="2026-09-30T10:00:00Z")
    running = hub()
    port = running.port
    token = request(port, "GET", "/hub/session").json()["csrf_token"]
    answered = request(port, "POST", f"/hub/projects/{'a' * 32}/activate", body=b"{}", headers={
        "Origin": f"http://127.0.0.1:{port}", "X-Conduct-CSRF": token,
        "Content-Type": "application/json"})
    assert answered.status == 202, answered.body
    deadline = time.monotonic() + 10
    while not spawner.children and time.monotonic() < deadline:
        time.sleep(0.05)
    assert spawner.children and not spawner.children[0].closed
    assert running.finish() == 0
    assert spawner.children[0].closed, "the hub left its child's pipe open"
