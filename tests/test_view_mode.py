"""A project opened for viewing never starts an agent (spec 4.3.1, 4.3.6, 12.10 day 8).

The guarantee sits on the runner, not on the page: a `ProcessRunner` built with
`spawns_allowed=False` refuses every `run` and `start` before it does anything else, so no
child exists, no ownership loan was claimed (a loan that is retired without proof would poison
the owner), and the refusal is the same `CommandSpecError` every unusable command gets.

This is the first slice of that section. What is here: the runner's refusal (with a control,
so a spy that sees nothing cannot pass), and two witnesses that a server launched with
`Launch(mode="view")` spawns nothing: one through task creation, the reads and the preview,
one through the writes of a cycle and a run (flow, draft, revision, template, run creation).
A calibration plants a child in each road of the second walk and requires the spy to see it,
so a road the walk does not reach turns that case red instead of passing unnoticed.

What that witness does NOT prove, and why its name says what it walks and not what it
guarantees: the mode does not gate spawning yet. `Launch.mode` reaches only the project
identity; the runner built at `command/providers.py` is still spawn-capable whatever the mode,
so the witness is green in `active` too. It says that today's walk starts no child, not that a
view process cannot start one. Also not here: the policy driver and the quota collector are
not gated by the mode, `--mode view` still refuses to start, and the routes that read git or
request a seed are lane L's.

The spec's own name for the witness (4.3.6) is kept for the day-8 version, which must (a) make
the mode reach the runner's construction site and (b) discriminate: assert that the runner the
flow reaches refuses to spawn, or add the control where the same flow does spawn in `active`
(authorize, then the driver). A green test under that name is read as the guarantee holding,
so it is not used before it is true.
"""
from __future__ import annotations

import re
import subprocess
from contextlib import contextmanager
from pathlib import Path
from threading import Thread

import pytest

from conductor import ownership, ownership_transition, server
from conductor.command import http_writes, task_routes
from conductor.command.adapters.process import CommandSpec, CommandSpecError, ProcessRunner
from conductor.command.api_contracts import ApiRefusal
from conductor.command.api_refusals import ERROR_STATUS, _FIXED_MESSAGES
from conductor.command.graph_template import load_template
from conductor.command.project_claim import Launch
from tests._fakeproc import fake_argv
from tests.alpha1_live_extensions import REFUSALS
from tests.test_cockpit_command_api_freeze import EXPECTED_ERRORS
from tests.test_command_http_api import TOKEN
from tests.test_command_run_routes import INSTANCE, ROLE
from tests.test_command_run_socket import pinned
from tests.test_command_workflow_draft import WORKFLOW, a_document
from tests.test_command_workflow_flow import chain, review, step
from tests.test_policy_driver import ask
from tests.test_policy_runtime import NOW, PD, setup
from tests.test_server_command_http import _request
from tests.test_store import good_lane, write_project

REAL_POPEN = subprocess.Popen


class PopenSpy:
    """Counts every child the process starts, and starts it (a control needs a real one)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def __call__(self, *args, **kwargs):
        self.calls.append(tuple(args))
        return REAL_POPEN(*args, **kwargs)


@pytest.fixture
def spy(monkeypatch) -> PopenSpy:
    watcher = PopenSpy()
    monkeypatch.setattr(subprocess, "Popen", watcher)
    return watcher


def _spec() -> CommandSpec:
    return CommandSpec(argv=fake_argv(), cwd="work", timeout_seconds=10)


def _root(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    (root / "work").mkdir()
    return root


# -- the runner ----------------------------------------------------------------------


@pytest.mark.parametrize("door", ["run", "start"])
def test_a_runner_that_may_not_spawn_refuses_before_a_child_exists(tmp_path, spy, door):
    runner = ProcessRunner(_root(tmp_path), spawns_allowed=False)
    with pytest.raises(CommandSpecError, match="may not spawn"):
        getattr(runner, door)(_spec())
    assert spy.calls == [] and runner.active_tokens() == ()


def test_a_runner_that_may_spawn_still_does_through_the_same_spy(tmp_path, spy):
    runner = ProcessRunner(_root(tmp_path))
    assert runner.run(_spec()).status == "completed"
    assert len(spy.calls) == 1


def test_a_refused_spawn_claims_no_ownership_loan_and_leaves_the_owner_whole(tmp_path, spy):
    from tests._drain_harness import DrainProject
    root = DrainProject.build(tmp_path).root
    (root / "work").mkdir()
    owner = ownership.acquire_owner(root)
    try:
        runner = ProcessRunner(root, spawns_allowed=False)
        with pytest.raises(CommandSpecError):
            runner.run(_spec())
        owner.check()            # a loan retired without proof would say recovery_required
    finally:
        owner.release()          # and would refuse to let go while a loan stood
    assert spy.calls == []


# -- the first witness ---------------------------------------------------------------


def test_a_server_launched_for_viewing_spawns_no_child_through_task_creation_reads_and_preview(
        tmp_path, spy):
    """A task, the reads and the preview, walked on a server launched for viewing: no child.

    It holds for `Launch(mode="active")` as well, because the mode does not reach the runner
    yet (see the module docstring). What it pins is the walk: each step below answers as
    written, and the process starts nothing while it does.
    """
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    f = setup(root, two_steps=True, checker=True)
    ownership_transition.activate(root, legacy_writers_stopped=True)
    subject = server.build(root, 0, registry=f.registry, clock=lambda: NOW,
                           ids=f.runtime._ids, token_factory=lambda _: TOKEN,
                           launch=Launch(mode="view"))
    thread = Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    # A registry given by hand has no installed provider configuration to judge.
    subject.command_api._policy.provider_digest = lambda config: PD
    subject.command_api._policy.provider_facts = None
    flow = [
        ("GET", "/command/session", None, 200),
        ("GET", "/command/tasks", None, 200),
        ("POST", "/command/tasks", {"task_id": "task-1", "title": "Look around"}, 201),
        ("GET", "/command/tasks/task-1", None, 200),
        ("GET", "/command/workflows", None, 200),
        ("GET", "/command/runs", None, 200),
        ("GET", "/command/runs/run", None, 200),
        ("GET", "/command/runs/run/controls", None, 200),
        ("GET", "/command/quotas", None, 200),
        ("GET", "/command/runs/run/automation", None, 200),
        ("POST", "/command/runs/run/automation/preview", ask(), 200),
    ]
    try:
        walked = []
        for method, path, body, expected in flow:
            status, payload, _ = _request(subject, method, path, body)
            walked.append((method, path, status))
            assert status == expected, (method, path, status, payload)
    finally:
        subject.shutdown()
        subject.server_close()
        thread.join(10)
    assert len(walked) == len(flow) and not thread.is_alive()
    assert spy.calls == [], f"a child was started: {spy.calls}"


# -- the second witness: the writes of a cycle and a run -----------------------------

FLOW_CYCLE = "cycle-0a1b2c3d"
RUN = "run-view-1"


@contextmanager
def _served(tmp_path):
    """A project on an activated root, with one provider resolved, launched for viewing."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    ownership_transition.activate(root, legacy_writers_stopped=True)
    subject = server.build(root, 0, providers=pinned(tmp_path), clock=lambda: NOW,
                           token_factory=lambda _: TOKEN, launch=Launch(mode="view"))
    thread = Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    try:
        yield subject
    finally:
        subject.shutdown()
        subject.server_close()
        thread.join(10)
        assert not thread.is_alive()


def _send(subject, method, path, body, expected):
    status, payload, _ = _request(subject, method, path, body)
    assert status == expected, (method, path, status, payload)
    return payload


def _walk_cycle_and_run(subject) -> None:
    """A task, two cycles, a template and a run bound to the task, then the reads that show them."""
    _send(subject, "GET", "/command/session", None, 200)
    _send(subject, "POST", "/command/tasks", {"task_id": "task-1", "title": "Look around"}, 201)
    flow_path = f"/command/workflows/{FLOW_CYCLE}/flow"
    flow = chain(review("plan"), step("result", "human"))
    saved = _send(subject, "POST", flow_path, {
        "source": {"flow": flow}, "publish_revision": None, "expected_absent": True}, 201)
    published = _send(subject, "POST", flow_path, {
        "source": {"flow": flow}, "publish_revision": 1,
        "expected_digest": saved["draft_digest"]}, 201)
    assert published["published"] is not None, published
    draft_path = f"/command/workflows/{WORKFLOW}/draft"
    _send(subject, "POST", draft_path, {"document": a_document(), "expected_absent": True}, 201)
    drawn = _send(subject, "GET", f"/command/workflows/{WORKFLOW}", None, 200)
    _send(subject, "POST", f"/command/workflows/{WORKFLOW}/revisions", {
        "revision": 1, "reviewed_digest": drawn["draft"]["digest"]}, 201)
    _send(subject, "POST", "/command/templates", load_template("dalio-v2").as_dict(), 201)
    opened = _send(subject, "POST", "/command/runs", {
        "run_id": RUN, "cycle_id": "default-orbit", "mode": "confirm",
        "participants": [{"instance_id": INSTANCE, "provider_id": "codex", "model": None}],
        "workflow_id": WORKFLOW, "revision": 1, "assignments": {ROLE: INSTANCE},
        "task_id": "task-1"}, 201)
    assert opened["graph"]["run_id"] == RUN, opened
    listed = _send(subject, "GET", "/command/runs", None, 200)
    assert [row["run_id"] for row in listed["runs"]] == [RUN], listed
    _send(subject, "GET", f"/command/runs/{RUN}", None, 200)
    _send(subject, "GET", "/command/tasks/task-1", None, 200)


def test_a_server_launched_for_viewing_spawns_no_child_through_cycle_publication_and_run_creation(
        tmp_path, spy):
    """A cycle through the flow door and through draft and revision, a template, a run: no child.

    Run creation needs a resolved provider, so this walk cannot share the server of the walk
    above (a server takes an adapter registry or provider configuration, never both). The
    provider it resolves owns the spawn-capable runner, so a zero here is not "nothing was
    there to spawn from". Like that walk it holds in `active` too until the mode reaches the
    runner, and the calibration below shows it would see a child in every road it walks.
    """
    with _served(tmp_path) as subject:
        _walk_cycle_and_run(subject)
        resolved = [row.provider_id for row in subject.command_providers if row.available]
    assert resolved == ["codex"]
    assert spy.calls == [], f"a child was started: {spy.calls}"


# -- the calibration: the walk above must be able to say no --------------------------

#: The handler each write of the cycle and run walk goes through, one per POST route.
ROADS = ("create_task", "_write_flow", "_save_draft", "_publish_revision",
         "_publish_template", "_open_run")


@pytest.mark.parametrize("road", ROADS)
def test_the_cycle_and_run_walk_sees_a_spawn_planted_in_each_road_it_walks(
        tmp_path, spy, monkeypatch, road):
    """A witness that cannot say no is a number: plant a child in one road, expect to see it."""
    home = task_routes if road == "create_task" else http_writes
    real, planted = getattr(home, road), []

    def plant(*args, **kwargs):
        planted.append(road)
        subprocess.Popen(fake_argv()).wait()
        return real(*args, **kwargs)

    monkeypatch.setattr(home, road, plant)
    with _served(tmp_path) as subject:
        _walk_cycle_and_run(subject)
    assert planted and len(spy.calls) == len(planted), (road, planted, spy.calls)


# -- the code the view door throws (spec 4.3.1, 11.1) -----------------------------------

CODE = "project_not_active"
SENTENCE = "the project is open for viewing and starts no agent"
REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "src" / "conductor" / "panel"


def test_project_not_active_is_409_with_fixed_words_and_no_detail():
    refusal = ApiRefusal.fixed(CODE)
    assert refusal.status == 409 and refusal.message == SENTENCE
    assert dict(refusal.detail) == {}
    assert refusal.as_dict() == {"error": {"code": CODE, "message": SENTENCE, "detail": {}}}


def test_project_not_active_stands_in_every_place_of_the_command_vocabulary_python_can_read():
    assert ERROR_STATUS[CODE] == 409                       # place 1
    assert _FIXED_MESSAGES[CODE] == SENTENCE               # place 2
    assert EXPECTED_ERRORS[CODE] == (409, "lifecycle")     # place 5
    assert REFUSALS[CODE] == 409                           # place 6


def test_project_not_active_stands_in_the_canon_the_labels_and_both_languages_of_the_notice():
    canon = (REPO / "docs" / "specs" / "2026-08-13-cockpit-command-api.md").read_text(
        encoding="utf-8")
    assert re.search(rf'"code": "{CODE}",\s+"status": 409,\s+"source": "lifecycle"', canon)  # 4
    labels = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    assert re.search(rf"^  {CODE}: ", labels, re.MULTILINE)                                # 7
    notice = (PANEL / "studio-notice-copy.js").read_text(encoding="utf-8")
    found = re.search(rf'"error\.{CODE}": \["([^"]+)", "([^"]+)"\]', notice)               # 8
    assert found and all(found.groups()) and found.group(1) != found.group(2)
