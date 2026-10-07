"""A POST that has headers but no body has not acquired permission to write.

Use the real HTTP door and task store. An Event acknowledges successful header
validation while the client withholds the body; drain starts before that body is
sent. This witnesses admission across drain, not a fresh request after drain.
"""
from __future__ import annotations

import http.client
import json
from datetime import datetime, timedelta, timezone
from queue import Queue
from threading import Event, Thread

import pytest

from conductor import server, server_drain
from conductor.command.adapters import AdapterRegistry
from conductor.command.task_store import TaskStore
from tests.test_store import good_lane, write_project

WAIT = 10
TASK = {"task_id": "held-body-task", "title": "A valid task with its body withheld"}


@pytest.fixture
def serving(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    subject = server.build(root, 0, registry=AdapterRegistry())
    loop = Thread(target=subject.serve_forever, daemon=True)
    loop.start()
    try:
        yield subject
    finally:
        subject.shutdown()
        subject.server_close()
        loop.join(WAIT)
        assert not loop.is_alive(), "the HTTP server did not retire"


def _send_headers_only(subject, monkeypatch):
    """Acknowledge authentic headers without supplying one byte of the task body."""
    headers_checked = Event()
    body_length = subject.command_api.body_length

    def checked_length(target, headers):
        length = body_length(target, headers)
        headers_checked.set()
        return length

    monkeypatch.setattr(subject.command_api, "body_length", checked_length)
    port = subject.server_address[1]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=WAIT)
    try:
        connection.request("GET", "/command/session")
        session = connection.getresponse()
        assert session.status == 200
        token = json.loads(session.read())["csrf_token"]
        encoded = json.dumps(TASK).encode("utf-8")
        connection.putrequest("POST", "/command/tasks")
        connection.putheader("Origin", f"http://127.0.0.1:{port}")
        connection.putheader("X-Conduct-CSRF", token)
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(len(encoded)))
        connection.endheaders()
        assert headers_checked.wait(WAIT), "the POST never passed header validation"
        return connection, encoded
    except BaseException:
        connection.close()
        raise


def _durable_tasks_and_runs(subject):
    root = subject.command_store.project_root
    tasks = TaskStore(root)
    files = {}
    for directory in (tasks.tasks_root, subject.command_store.runs_root):
        if directory.exists():
            for path in directory.rglob("*"):
                if path.is_file():
                    files[path.relative_to(root).as_posix()] = path.read_bytes()
    return tasks.tasks(), files


def _begin_draining(subject):
    """Use the same admission transition as the real drain."""
    subject.draining = True
    assert subject.draining


def test_a_valid_task_post_with_a_held_body_cannot_write_after_drain_begins(
        serving, monkeypatch):
    before = _durable_tasks_and_runs(serving)
    connection, encoded = _send_headers_only(serving, monkeypatch)
    try:
        _begin_draining(serving)
        connection.send(encoded)
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert (response.status, payload.get("error", {}).get("code")) == (
            409, "server_stopping"), payload
        assert _durable_tasks_and_runs(serving) == before
        assert TaskStore(serving.command_store.project_root).standing(TASK["task_id"]) is None
    finally:
        connection.close()


def test_the_same_held_body_creates_its_task_when_drain_has_not_begun(serving, monkeypatch):
    connection, encoded = _send_headers_only(serving, monkeypatch)
    try:
        connection.send(encoded)
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 201, payload
        stored = TaskStore(serving.command_store.project_root).read(TASK["task_id"])
        assert stored.task_id == TASK["task_id"] and stored.title == TASK["title"]
        assert payload["task"] == stored.as_dict()
    finally:
        connection.close()


class _DrainWaitProbe:
    """Pause a second non-idle observation, or report that drain returned early.

    Each first False reaches the real drain unchanged. Its next iteration must
    observe the still-pending resource again; returning early reports "done"
    instead. Events release the second observation after the resource settles.
    No assertion depends on a thread merely not having run yet.
    """

    def __init__(self, subject, monkeypatch):
        self.subject = subject
        self.checkpoints = Queue()
        self.counts = {"posts": 0, "workers": 0}
        self.release = {name: Event() for name in self.counts}
        posts = subject.wait_command_posts
        workers = subject.command_execution.wait_idle
        monkeypatch.setattr(subject, "wait_command_posts",
                            lambda timeout: self.observe("posts", posts))
        monkeypatch.setattr(subject.command_execution, "wait_idle",
                            lambda timeout: self.observe("workers", workers))
        self.thread = Thread(target=self.run, daemon=True)

    def observe(self, resource, wait):
        idle = wait(0)
        if not idle:
            self.counts[resource] += 1
            if self.counts[resource] == 2:
                self.checkpoints.put(resource)
                assert self.release[resource].wait(WAIT), f"{resource} was never released"
                idle = wait(0)
        return idle

    def run(self):
        now = datetime.now(timezone.utc)
        try:
            server_drain._wait_for_idle(
                self.subject, None, now + timedelta(seconds=60), lambda: now)
        except BaseException as error:
            self.checkpoints.put(error)
        else:
            self.checkpoints.put("done")

    def expect(self, checkpoint):
        observed = self.checkpoints.get(timeout=WAIT)
        assert observed == checkpoint, f"expected {checkpoint}, observed {observed!r}"


class _AdmittedTaskPost:
    """Hold the real mutation, then give it a real unfilled worker reservation."""

    def __init__(self, subject, monkeypatch):
        self.subject, self.handle = subject, subject.command_api.handle
        self.admitted, self.finish, self.settled = Event(), Event(), Event()
        self.reservations = []
        monkeypatch.setattr(subject.command_api, "handle", self)

    def __call__(self, method, path, headers, body=b""):
        if method != "POST" or path != "/command/tasks":
            return self.handle(method, path, headers, body)
        self.admitted.set()
        try:
            assert self.finish.wait(WAIT), "the admitted task write was never released"
            response = self.handle(method, path, headers, body)
            # A real slot models an admitted POST's worker handoff; no adapter,
            # provider or subprocess runs because the reservation stays unfilled.
            self.reservations.append(self.subject.command_execution.claim())
            return response
        finally:
            self.settled.set()

    def close(self):
        self.finish.set()
        if self.admitted.is_set():
            assert self.settled.wait(WAIT), "the admitted POST did not settle during cleanup"
        for reservation in self.reservations:
            reservation.release()


def test_drain_waits_for_an_admitted_post_and_then_its_outstanding_execution(
        serving, monkeypatch):
    post = _AdmittedTaskPost(serving, monkeypatch)
    connection, encoded = _send_headers_only(serving, monkeypatch)
    probe = _DrainWaitProbe(serving, monkeypatch)
    try:
        connection.send(encoded)
        assert post.admitted.wait(WAIT), "the complete POST was never admitted"
        _begin_draining(serving)
        probe.thread.start()
        probe.expect("posts")
        assert TaskStore(serving.command_store.project_root).standing(TASK["task_id"]) is None
        post.finish.set()
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 201, payload
        stored = TaskStore(serving.command_store.project_root).read(TASK["task_id"])
        assert stored.title == TASK["title"]
        probe.release["posts"].set()
        probe.expect("workers")
        assert len(post.reservations) == 1
        post.reservations[0].release()
        probe.release["workers"].set()
        probe.expect("done")
    finally:
        for event in probe.release.values():
            event.set()
        post.close()
        connection.close()
        if probe.thread.ident is not None:
            probe.thread.join(WAIT)
