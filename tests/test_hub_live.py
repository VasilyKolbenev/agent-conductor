"""The whole hub over a REAL child: activate, read, snapshot, stop (spec 4.1.4, 4.1.9, 4.6.3).

The child is the real `conduct up` with fake dispatch (`tests/_drain_child.py`) started by the real
spawner from a project laid down with the repo's own helpers. In front of it is the hub's own stack
(reader, service, loop, HTTP server) on a free port, and the test speaks only HTTP to the hub. It
shows what no fake can: that the identity the child answers is the one the reader expects, that the
reads of the table are answered by a real command surface (the queue and the flag are 404 in this
build and mean `null`), that a complete pass becomes a snapshot on disk, that the stop route drains
the child and the row then reads the snapshot with the time the child stopped.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time

import pytest

from conductor.hub import reader, server, service, snapshots, summary
from tests._drain_harness import WAIT, DrainProject, _kill_tree
from tests._hub_stack import request
from tests.test_hub_supervisor import ORIGIN, RealHub


class Live:
    """A hub's HTTP stack over one real project and its real child."""

    def __init__(self, tmp_path) -> None:
        self.project = DrainProject.build(tmp_path)
        self.hub = RealHub(self.project)
        self.server = server.HubServer(0)
        self.port = self.server.server_port
        folder = self.project.home
        self.snapshots = snapshots.SnapshotStore(folder)
        ledger = summary.ObservedLedger()
        watching = reader.ChildReader(folder, self.hub.supervisor, self.hub.store, self.snapshots,
                                      ledger, self.server.bus, hub_origin=ORIGIN)
        self.service = service.HubService(folder, self.hub.supervisor, self.hub.store,
                                          self.snapshots, watching, ledger, self.server.bus,
                                          job_policy=lambda: "none")
        self.server.attach(self.service)
        self.loop = server.HubLoop(self.service, interval=0.3)
        self.loop.start()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.reader = watching
        self.token = request(self.port, "GET", "/hub/session").json()["csrf_token"]

    def post(self, target: str):
        return request(self.port, "POST", target, body=b"{}", headers={
            "Origin": f"http://127.0.0.1:{self.port}", "X-Conduct-CSRF": self.token,
            "Content-Type": "application/json"})

    def row(self) -> dict:
        return request(self.port, "GET", "/hub/projects").json()["projects"][0]

    def until(self, condition, what: str, seconds: float = WAIT) -> dict:
        deadline = time.monotonic() + seconds
        row = self.row()
        while not condition(row) and time.monotonic() < deadline:
            time.sleep(0.2)
            row = self.row()
        assert condition(row), f"timed out waiting for {what}: {json.dumps(row)[:400]}"
        return row

    def close(self) -> None:
        self.loop.stop()
        self.reader.close()
        for child in self.hub.spawner.children:
            child.close_stdin()
        for number in range(1, 5):
            (self.project.control / f"release-{number}").write_text("1", encoding="ascii")
        for child in self.hub.spawner.children:
            try:
                child.wait(30)
            except subprocess.TimeoutExpired:
                _kill_tree(child.popen)
        self.server.shutdown()
        self.server.server_close()
        self.hub.close()


@pytest.fixture
def live(tmp_path):
    made = Live(tmp_path)
    yield made
    made.close()


def test_a_real_child_is_started_read_snapshotted_and_stopped_through_the_hub(live):
    first = live.row()
    assert (first["state"], first["working"], first["data"]) == ("stopped", "stopped", "none")
    answered = live.post(f"/hub/projects/{first['project_id']}/activate")
    assert answered.status == 202 and answered.json()["working"] == "active"
    row = live.until(lambda r: r["state"] == "running" and r["data"] == "live",
                     "the child to run and be read")
    assert row["mode"] == "active" and row["working"] == "active"
    assert row["instance"] is not None and len(row["instance"]) == 32
    port = int(row["desk_url"].split(":")[2].split("/")[0])
    assert row["desk_url"] == f"http://127.0.0.1:{port}/panel/desk.html" and port != live.port
    assert row["snapshot_at"] is None and row["state_code"] is None
    snap_file = live.project.home / "snapshots" / f"{row['project_id']}.json"
    deadline = time.monotonic() + WAIT
    while not snap_file.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert snap_file.exists(), "a complete pass over a real child wrote no snapshot"
    assert live.snapshots.get(row["project_id"]) is not None
    listed = request(live.port, "GET", "/hub/projects").json()
    assert listed["active_project_id"] == row["project_id"]
    assert request(live.port, "GET", "/hub/limits").json()["source"] in ("live", "none",
                                                                          "snapshot")
    stopped = live.post(f"/hub/projects/{row['project_id']}/stop")
    assert stopped.status == 202 and stopped.json()["state"] == "stopping"
    after = live.until(lambda r: r["state"] == "stopped" and r["data"] == "snapshot",
                       "the child to drain and the row to read its snapshot")
    assert after["snapshot_at"] is not None and after["stopped_at"] is not None
    assert after["desk_url"] is None and after["instance"] is None
    assert request(live.port, "GET", "/hub/projects").json()["active_project_id"] is None
