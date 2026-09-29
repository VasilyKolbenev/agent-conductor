"""A project opened for viewing never starts an agent (spec 4.3.1, 4.3.6, 12.10 day 8).

The guarantee sits on the runner, not on the page: a `ProcessRunner` built with
`spawns_allowed=False` refuses every `run` and `start` before it does anything else, so no
child exists, no ownership loan was claimed (a loan that is retired without proof would poison
the owner), and the refusal is the same `CommandSpecError` every unusable command gets.

What is here, in file order:

* the runner's refusal, with a control, so a spy that sees nothing cannot pass;
* two walks of a server launched with `Launch(mode="view")` that start no child (task, reads
  and preview on a hand registry; flow, draft, revision, template and run creation on a
  resolved provider), a calibration that plants a child in each road of the second walk and
  requires the spy to see it, and the witness under the spec's name, which runs both walks in
  `view` and in `active` and then asks a real command of every runner the resolver built: in
  `view` each refuses before a child exists, in `active` each starts one. A zero that could
  not have been anything else is not what it reports;
* that the launch mode is what decides it: the resolver's `spawns_allowed` reaches the one
  runner all adapters share;
* no `PolicyDriver` and no quota collector in `view` (and both in `active`), and the quota read
  answered from the hub's limits snapshot with `hub_snapshot`;
* `authorize` and `resume` refused `project_not_active` in `view`. That test is strict xfail:
  the door is lane L's (`command/policy_service.py`), delivered as
  `handoffs/H-to-L-view-door.patch`, and the marker is removed in the commit that applies it;
* the code `project_not_active` in every place of 11.1 python and the text files can be read from.

Not here: the read of git state and the request of a seed named in the spec's text (their
routes are lane L's and do not exist in this build), `test_standalone_up_never_executes_auto_continue`
(the queue pump that executes a flag is lane L's), and the real-process witness, which is
`tests/test_view_child.py`.
"""
from __future__ import annotations

import json
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path
from threading import Thread

import pytest

from conductor import ownership, ownership_transition, server
from conductor.command import http_writes, providers, task_routes
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
from tests.test_policy_driver import ask, assert_two_steps, wait_terminal
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


@contextmanager
def _served_by_hand(tmp_path, mode: str = "view"):
    """An activated project on two fake adapters (no runner is built), launched in `mode`."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    f = setup(root, two_steps=True, checker=True)
    ownership_transition.activate(root, legacy_writers_stopped=True)
    subject = server.build(root, 0, registry=f.registry, clock=lambda: NOW,
                           ids=f.runtime._ids, token_factory=lambda _: TOKEN,
                           launch=Launch(mode=mode))
    thread = Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    # A registry given by hand has no installed provider configuration to judge.
    subject.command_api._policy.provider_digest = lambda config: PD
    subject.command_api._policy.provider_facts = None
    f.policy, f.runtime, f.store = (subject.command_api._policy, subject.command_api.runtime,
                                    subject.command_store)
    f.adapter._store = f.verifier._store = f.store
    try:
        yield subject, f
    finally:
        subject.shutdown()
        subject.server_close()
        thread.join(10)
        assert not thread.is_alive()


READS_AND_PREVIEW = [
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


def _walk_reads_and_preview(tmp_path, mode: str = "view") -> int:
    """A task, the reads and the preview on a server launched in `mode`; how many steps."""
    with _served_by_hand(tmp_path, mode) as (subject, _):
        for method, path, body, expected in READS_AND_PREVIEW:
            status, payload, _ = _request(subject, method, path, body)
            assert status == expected, (method, path, status, payload)
    return len(READS_AND_PREVIEW)


def test_a_server_launched_for_viewing_spawns_no_child_through_task_creation_reads_and_preview(
        tmp_path, spy):
    """A task, the reads and the preview, walked on a server launched for viewing: no child.

    A registry given by hand builds no runner, so this walk cannot tell the two modes apart;
    what it pins is the walk itself. The witness that can tell them apart is the one under the
    spec's name, below.
    """
    assert _walk_reads_and_preview(tmp_path) == 11
    assert spy.calls == [], f"a child was started: {spy.calls}"


# -- the second witness: the writes of a cycle and a run -----------------------------

FLOW_CYCLE = "cycle-0a1b2c3d"
RUN = "run-view-1"


@contextmanager
def _served(tmp_path, mode: str = "view"):
    """A project on an activated root, with one provider resolved, launched in `mode`."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    (root / "work").mkdir()          # a runner refuses a working folder that is the root itself
    ownership_transition.activate(root, legacy_writers_stopped=True)
    subject = server.build(root, 0, providers=pinned(tmp_path), clock=lambda: NOW,
                           token_factory=lambda _: TOKEN, launch=Launch(mode=mode))
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


# -- the mode reaches the runner the providers build (spec 4.3.1) ----------------------


@pytest.fixture
def runners(monkeypatch) -> list[ProcessRunner]:
    """Every runner the provider resolver builds, in order: the class it builds is recorded."""
    made: list[ProcessRunner] = []

    class Recording(ProcessRunner):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            made.append(self)

    monkeypatch.setattr(providers, "ProcessRunner", Recording)
    return made


def _ask_for_a_child(runner: ProcessRunner) -> str:
    """One real command through this runner: what it did, in a word."""
    try:
        return runner.run(_spec()).status
    except CommandSpecError:
        return "refused"


def _prepare_flow(base: Path, mode: str, runners, spy) -> dict:
    """Both prepare roads on servers launched in `mode`, then a child asked of every runner."""
    _walk_reads_and_preview(base / "reads", mode)
    made = len(runners)
    with _served(base / "cycle", mode) as subject:
        _walk_cycle_and_run(subject)
        by_the_walks = len(spy.calls)
        asked = [_ask_for_a_child(runner) for runner in runners[made:]]
    return {"children_by_the_walks": by_the_walks, "asked": asked, "children": len(spy.calls)}


def test_view_mode_process_never_spawns_a_child_through_a_full_prepare_flow(
        tmp_path, spy, runners):
    """View: no child in the prepare flow and every runner refuses one. Active: a runner spawns.

    Both walks (task, reads and preview on a hand registry; flow, draft, revision, template and
    run creation on a resolved provider) run on servers launched in the mode under test. Then a
    real command is asked of every runner the resolver built for that server. In `view` each
    is refused before a child exists and the `Popen` spy stays empty; in `active` the same ask
    starts one real child per runner, which is what makes the empty spy mean something.

    Not walked: the read of git state and the request of a seed, which the spec's text names.
    Their routes are lane L's and do not exist in this build; their own tests are L's
    (`test_view_mode_git_routes_refuse_project_not_active_and_spawn_nothing`, 9.12).
    """
    viewed = _prepare_flow(tmp_path / "view", "view", runners, spy)
    assert viewed["asked"] and set(viewed["asked"]) == {"refused"}, viewed
    assert (viewed["children_by_the_walks"], viewed["children"]) == (0, 0), viewed
    active = _prepare_flow(tmp_path / "active", "active", runners, spy)
    assert active["asked"] == ["completed"] * len(active["asked"]) and active["asked"], active
    assert active["children_by_the_walks"] == 0, active
    assert active["children"] == len(active["asked"]), active


def test_the_provider_resolver_builds_a_runner_that_refuses_when_spawning_is_not_allowed(
        tmp_path, spy, runners):
    root = _root(tmp_path)
    for allowed in (False, True):
        providers.resolve_providers(pinned(tmp_path), root=root, clock=lambda: NOW,
                                    ids=lambda kind: f"{kind}-1", spawns_allowed=allowed)
    refused, permitted = runners
    assert (_ask_for_a_child(refused), _ask_for_a_child(permitted)) == ("refused", "completed")
    assert len(spy.calls) == 1


# -- no driver, no collector, and the limits of the active project (spec 4.3.1, 4.5.4) ---


def test_view_mode_starts_no_policy_driver_and_no_quota_collector(tmp_path):
    """A view server has neither, and closes as cleanly as an active one that has both."""
    seen = {}
    for mode in ("view", "active"):
        with _served(tmp_path / mode, mode) as subject:
            seen[mode] = (subject.policy_driver is not None,
                          subject.quota_collector is not None)
        assert not subject.retirement_uncertain and subject.project_owner is None, mode
    assert seen == {"view": (False, False), "active": (True, True)}


def _limits_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "conduct-home"
    home.mkdir()
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    return home


def _quotas(subject) -> dict:
    return _send(subject, "GET", "/command/quotas", None, 200)


def test_view_mode_quotas_answer_from_the_hub_limits_snapshot_with_its_time(
        tmp_path, monkeypatch):
    home = _limits_home(tmp_path, monkeypatch)
    with _served(tmp_path / "view-before", "view") as subject:
        nothing = _quotas(subject)
    with _served(tmp_path / "active", "active") as subject:
        answer = _quotas(subject)
    stored = {"schema_version": 1, "project_id": "3f9c0a1b2c3d4e5f60718293a4b5c6d7",
              "taken_at": "2026-08-11T11:59:01Z", "quotas": answer}
    (home / "limits.json").write_text(json.dumps(stored), encoding="utf-8")
    with _served(tmp_path / "view-after", "view") as subject:
        shown = _quotas(subject)
    assert nothing["snapshots"] == [] and nothing["hub_snapshot"] is None
    assert [row["provider_id"] for row in nothing["providers"]]        # this project's own rows
    assert shown == {**answer, "hub_snapshot": {
        "project_id": stored["project_id"], "taken_at": "2026-08-11T11:59:01Z"}}
    assert answer["snapshots"], "the stored answer must carry rows for the copy to mean anything"


def test_the_hub_snapshot_key_is_absent_in_active_mode_even_when_a_snapshot_stands(
        tmp_path, monkeypatch):
    home = _limits_home(tmp_path, monkeypatch)
    (home / "limits.json").write_text(json.dumps({
        "schema_version": 1, "project_id": "3f9c0a1b2c3d4e5f60718293a4b5c6d7",
        "taken_at": "2026-08-11T11:59:01Z",
        "quotas": {"as_of": NOW, "max_age_seconds": 300.0, "providers": [], "snapshots": []},
    }), encoding="utf-8")
    with _served(tmp_path / "active", "active") as subject:
        answer = _quotas(subject)
    assert "hub_snapshot" not in answer and answer["providers"]


# -- authorize and resume in view: the door is lane L's (spec 4.3.1, 4.4.1) -------------


def _asked_in(mode: str, tmp_path) -> list:
    """`authorize` and a `resume` control, as the desk would send them, and what each was told."""
    with _served_by_hand(tmp_path, mode) as (subject, f):
        base = "/command/runs/run/automation"
        status, preview, _ = _request(subject, "POST", f"{base}/preview", ask())
        assert status == 200, preview
        granted = _request(subject, "POST", f"{base}/authorize", {
            "authorization_id": "grant", "preview_digest": preview["preview_digest"],
            "authorized_by": "owner", "terms": preview["terms"], "supersedes": None})
        digest = granted[1]["authorization_digest"] if granted[0] == 201 else "sha256:" + "0" * 64
        resumed = _request(subject, "POST", f"{base}/control", {
            "control_id": "resume-1", "authorization_id": "grant", "action": "resume",
            "authorization_digest": digest, "actor": "owner", "expected_control_id": None})
        if mode == "active":
            assert_two_steps(f, wait_terminal(f))
    return [(status, payload.get("error", {}).get("code")) for status, payload, _ in
            (granted, resumed)]


@pytest.mark.xfail(strict=True, reason=(
    "the door that throws the code is lane L's (command/policy_service.py, spec 4.4.1); the two "
    "lines are in handoffs/H-to-L-view-door.patch. When they land this turns XPASS, which strict "
    "reports as a failure: remove this marker then."))
def test_view_mode_refuses_authorize_and_resume_with_project_not_active(tmp_path):
    """In view both writes are refused 409 `project_not_active`; in active neither is.

    The active run is the control: there `authorize` creates the grant (201) and the driver
    runs the two steps, and the resume is judged by the grant's history like any other.
    """
    viewed = _asked_in("view", tmp_path / "view")
    active = _asked_in("active", tmp_path / "active")
    assert viewed == [(409, CODE), (409, CODE)], viewed
    assert active[0] == (201, None) and active[1][1] != CODE, active


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
