"""The supervisor of the hub's children (spec 4.1.4, 4.1.5, 4.1.7, 4.3.6, 4.1.13 item 3).

It begins with the rule the supervisor stands on: a project is proven closed only when its
process is dead by `(pid, process_started)` AND the head of its ownership, read without
writing, is not `opened` (4.1.7); that rule is a function of the state module, asked here on the
real probe and the real head of a real project. Then the supervisor on a world of fakes
(`tests/_hub_world.py`: a clock, a table of live pids, a table of heads, a spawner that starts
nothing and records each start): the switch that drains the old child before it starts the new
one, the rule that nothing starts while a closure is not proven, the restart of the hub, the
transition that is spawned once, the start that times out, the bind that is tried again on port
0, and what `activate`, `view` and `stop` refuse. The real children are in the last part.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import replace
from datetime import timedelta

import pytest

from conductor import (ownership, ownership_native, ownership_records, ownership_transition,
                       process_identity, up_status)
from conductor.hub import instance, registry, spawn, state, supervisor
from tests._drain_harness import (CHILD, LINGER, PROBE, RUN_ID, WAIT, DrainChild, DrainProject,
                                  _kill_tree, wait_until)
from tests._hub_world import World, id_of, iso
from tests.test_store import good_lane, write_project

NOW = "2026-09-30T10:00:00Z"
SLEEPER = [sys.executable, "-c", "import time; time.sleep(120)"]
FLAG = state.Flag("f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1", 3)


@pytest.fixture
def world(tmp_path):
    made = World(tmp_path)
    yield made
    made.close()


def _activated(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    write_project(root, lanes={"claude": good_lane()})
    ownership_transition.activate(root, legacy_writers_stopped=True)
    return root


def test_proven_closed_needs_a_dead_process_and_an_ownership_head_that_is_not_opened(tmp_path):
    root = _activated(tmp_path)
    nonce = ownership_records.state(root)[1]["nonce"]
    child = subprocess.Popen(SLEEPER, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    try:
        recorded = state.ClosingEntry("a" * 32, child.pid,
                                      process_identity.started_of(child.pid), nonce, NOW)
        # A live process, a head that was never opened: not closed, and the word says why.
        assert state.proven_closed(recorded, root) == state.Closure(False, "process_alive")
        child.kill()
        child.wait(timeout=20)
        # Dead, and the head is `active`, never opened: closed.
        assert state.proven_closed(recorded, root) == state.Closure(True, "proven")
        # Dead, and the project's owner opened it and never closed it: not closed.
        owner = ownership.acquire_owner(root)
        try:
            assert state.proven_closed(recorded, root) == state.Closure(False, "head_opened")
        finally:
            owner.release()
        assert state.proven_closed(recorded, root) == state.Closure(True, "proven")
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=20)


# -- the supervisor on a world of fakes ----------------------------------------------------------


def _activate_and_start(world: World, name: str = "a") -> None:
    """Make `name` the active project and let the supervisor start its child; it then serves."""
    world.supervisor.activate(id_of(name))
    world.supervisor.tick()
    assert len(world.spawner.started(name)) == 1
    world.running(name)


def test_activating_a_project_with_nothing_running_starts_its_child_with_the_transition(world):
    world.supervisor.activate(id_of("a"), flag=FLAG)
    assert world.spawner.calls == [], "activate only records the intent; a tick carries it out"
    world.supervisor.tick()
    (call,) = world.spawner.calls
    expected = world.hub_state().transition
    assert call == {"project_id": id_of("a"), "root": world.roots["a"], "port": 7701,
                    "mode": "active", "transition": expected.id,
                    "auto_continue": f"{FLAG.flag_id}@{FLAG.revision}"}
    assert expected.spawned_at == iso(world.clock.now) and world.hub_state().closing == ()


def test_the_start_is_recorded_before_the_child_is_started_so_a_crash_between_cannot_repeat_it(
        world):
    seen_at_the_start = []
    world.spawner.before_start = lambda arguments: seen_at_the_start.append(
        (world.hub_state().transition.spawned_at, world.hub_state().closing))
    world.supervisor.activate(id_of("a"), flag=FLAG)
    world.supervisor.tick()
    assert seen_at_the_start == [(iso(world.clock.now), ())], (
        "the child was started before the state said it was")


def test_a_view_child_never_stands_in_the_way_of_the_active_one(world):
    world.supervisor.view(id_of("b"))
    world.running("b", mode="view")
    world.supervisor.activate(id_of("a"))
    world.supervisor.tick()
    assert [call["mode"] for call in world.spawner.calls] == ["view", "active"]


def test_a_view_child_of_the_project_itself_is_awaited_before_its_active_child_even_unreported(
        world):
    world.supervisor.view(id_of("a"))                # alive, and it has written no status file
    assert not list((world.home / "run").glob("*.json"))
    world.supervisor.activate(id_of("a"))
    world.supervisor.tick()
    assert [call["mode"] for call in world.spawner.calls] == ["view"], "started beside its view"
    world.spawner.children[0].leave(0)
    world.supervisor.tick()
    assert [call["mode"] for call in world.spawner.calls] == ["view", "active"]


# -- the restart of the hub (4.1.7) -------------------------------------------------------------


def _with_a_spawned_transition(world: World, name: str = "a", flag=None) -> None:
    tid = "00000000-0000-0000-0000-0000000000aa"
    world.store.update(lambda s: state.begin_switch(
        s, id_of(name), kind="manual", transition_id=tid, since=NOW, flag=flag, previous=None))
    world.store.update(lambda s: state.settle_closed(s, [], spawned_at=NOW, transition_id=tid))


def test_hub_restart_waits_for_any_live_active_mode_process_before_starting_an_active_child(
        world):
    _with_a_spawned_transition(world)
    world.running("a")
    world.put_status("a", "stopping")                # its own project's child, draining
    world.running("b")                               # and another project's active child
    world.put_status("a", "stopping")
    world.supervisor.restart()
    world.supervisor.tick()
    assert world.spawner.calls == []
    assert world.supervisor.status(id_of("a")).lifecycle.state == "stopping"
    world.gone("a")
    world.supervisor.tick()
    assert world.spawner.calls == [], "another project's active child is still alive"
    world.gone("b")
    world.supervisor.tick()
    (call,) = world.spawner.calls
    assert call["project_id"] == id_of("a") and call["mode"] == "active"


def test_a_restart_starts_the_active_project_with_neither_a_transition_nor_a_flag(world):
    _with_a_spawned_transition(world, flag=FLAG)
    world.gone("a", "serving", head="closed")        # the hub died, the child drained and closed
    world.supervisor.restart()
    (call,) = world.spawner.calls
    assert (call["transition"], call["auto_continue"]) == (None, None)
    assert world.hub_state().handed_flags == {id_of("a"): FLAG.flag_id}


def test_hub_restart_restores_no_view_children(world):
    _with_a_spawned_transition(world, "a")
    world.gone("a")
    world.gone("b", "serving")                       # a view child that drained with the hub
    world.put_status("b", "serving", mode="view")
    world.supervisor.restart()
    world.supervisor.tick()
    assert world.spawner.started("b") == []
    assert [call["project_id"] for call in world.spawner.calls] == [id_of("a")]


def test_a_restart_with_no_active_project_chooses_none(world):
    world.supervisor.restart()
    world.supervisor.tick()
    assert world.spawner.calls == [] and world.hub_state().active_project_id is None


def test_a_child_that_has_not_served_in_thirty_seconds_is_asked_to_drain_and_reads_failed(world):
    world.supervisor.activate(id_of("a"))
    world.supervisor.tick()
    child = world.spawner.children[0]
    world.clock.advance(29)
    world.supervisor.tick()
    assert not child.closed
    world.clock.advance(2)
    world.supervisor.tick()
    assert child.closed
    found = world.supervisor.status(id_of("a")).lifecycle
    assert (found.state, found.state_code) == ("failed", "start_timeout")
    world.supervisor.tick()
    assert len(world.spawner.calls) == 1


def test_a_child_that_serves_in_time_is_never_timed_out(world):
    world.supervisor.activate(id_of("a"))
    world.supervisor.tick()
    world.clock.advance(20)
    world.running("a")
    world.clock.advance(60)
    world.supervisor.tick()
    assert not world.spawner.children[0].closed
    assert world.supervisor.status(id_of("a")).lifecycle.state == "running"


def test_a_child_that_left_without_a_record_is_a_start_that_failed(world):
    world.supervisor.activate(id_of("a"))
    world.supervisor.tick()
    world.spawner.children[0].leave(1)
    found = world.supervisor.status(id_of("a")).lifecycle
    assert (found.state, found.state_code) == ("failed", "start_failed")


def test_a_bind_that_failed_is_tried_once_more_on_port_zero_and_the_registry_keeps_its_port(
        world):
    world.supervisor.activate(id_of("a"), flag=FLAG)
    world.supervisor.tick()
    world.spawner.children[0].leave(1)
    world.put_status("a", "refused", code="bind_failed")
    world.supervisor.tick()
    first, second = world.spawner.calls
    assert first["port"] == 7701 and second["port"] == 0
    assert {k: v for k, v in second.items() if k != "port"} == {
        k: v for k, v in first.items() if k != "port"}, "the retry is the same start"
    world.spawner.children[1].leave(1)
    world.put_status("a", "refused", code="bind_failed")
    world.supervisor.tick()
    assert len(world.spawner.calls) == 2, "a second failed bind is not tried a third time"
    assert world.supervisor.status(id_of("a")).lifecycle.state_code == "bind_failed"
    assert registry.load(world.home).project(id_of("a")).port == 7701


def test_a_stale_refusal_of_an_earlier_child_is_not_taken_for_the_new_ones(world):
    world.put_status("a", "refused", code="bind_failed", at=world.clock.now - timedelta(hours=1))
    world.supervisor.activate(id_of("a"))
    world.supervisor.tick()
    world.spawner.children[0].leave(1)
    world.supervisor.tick()
    assert len(world.spawner.calls) == 1, "the old file is not this child's refusal"


def test_a_registry_port_that_is_the_hubs_own_starts_the_child_on_port_zero_at_once(tmp_path):
    made = World(tmp_path, hub_port=7701)
    try:
        made.supervisor.activate(id_of("a"))
        made.supervisor.tick()
        assert made.spawner.calls[0]["port"] == 0
    finally:
        made.close()


# -- what activate, view and stop refuse --------------------------------------------------------


def _refused(call, *args, **kwargs) -> str:
    with pytest.raises(supervisor.SupervisorRefused) as caught:
        call(*args, **kwargs)
    return caught.value.code


def test_activate_refuses_what_cannot_be_made_active_and_changes_nothing(world):
    assert _refused(world.supervisor.activate, "f" * 32) == "project_not_found"
    _activate_and_start(world, "a")
    before = world.hub_state()
    assert _refused(world.supervisor.activate, id_of("a")) == "already_active"
    world.spawner.refusal = spawn.SpawnRefused("hub_in_kill_on_close_job", "a job")
    assert _refused(world.supervisor.activate, id_of("b")) == "hub_in_kill_on_close_job"
    assert world.hub_state() == before
    world.spawner.refusal = None
    world.supervisor.activate(id_of("b"))
    assert _refused(world.supervisor.activate, id_of("a")) == "active_not_closed"


def test_activating_the_active_project_whose_child_is_gone_starts_it_again_without_a_transition(
        world):
    _activate_and_start(world, "a")
    world.spawner.children[0].leave(1)
    world.gone("a", "serving", head="closed")            # it crashed and left nothing to recover
    before = world.hub_state()
    world.supervisor.activate(id_of("a"))                # "Запустить снова" / "Продолжить"
    world.supervisor.tick()
    assert len(world.spawner.calls) == 2
    again = world.spawner.calls[-1]
    assert (again["mode"], again["transition"], again["auto_continue"]) == ("active", None, None)
    assert world.hub_state() == before, "a restart of the active project is not a new transition"


def test_activating_the_active_project_whose_stop_was_not_confirmed_starts_nothing_until_recovered(
        world):
    _activate_and_start(world, "a")
    world.spawner.children[0].leave(1)
    world.gone("a", "stop_uncertain", head="opened")
    world.supervisor.activate(id_of("a"))
    world.supervisor.tick()
    assert len(world.spawner.calls) == 1, "the table offers to recover it, and starts nothing"
    assert world.supervisor.status(id_of("a")).lifecycle.state == "stop_uncertain"


def test_switching_away_from_a_child_that_has_not_reported_yet_is_refused_and_changes_nothing(
        world):
    world.supervisor.activate(id_of("a"))
    world.supervisor.tick()                  # A's child is started and has written no status yet
    before = world.hub_state()
    assert _refused(world.supervisor.activate, id_of("b")) == "project_busy"
    assert world.hub_state() == before and not world.spawner.children[0].closed
    world.running("a")
    world.supervisor.activate(id_of("b"))    # once it has reported, the switch goes through
    assert [entry.project_id for entry in world.hub_state().closing] == [id_of("a")]
    assert world.spawner.children[0].closed


def test_view_starts_a_view_child_and_refuses_a_project_that_is_running_or_active(world):
    world.supervisor.view(id_of("b"))
    (call,) = world.spawner.calls
    assert (call["mode"], call["transition"], call["auto_continue"]) == ("view", None, None)
    assert _refused(world.supervisor.view, id_of("b")) == "project_running"
    _activate_and_start(world, "a")
    assert _refused(world.supervisor.view, id_of("a")) in ("project_running", "already_active")
    assert _refused(world.supervisor.view, "f" * 32) == "project_not_found"
    world.spawner.refusal = spawn.SpawnRefused("hub_in_kill_on_close_job", "a job")
    assert _refused(world.supervisor.view, id_of("c")) == "hub_in_kill_on_close_job"
    assert len(world.spawner.calls) == 2


def test_stopping_the_active_project_with_nobody_queued_leaves_none_active(world):
    _activate_and_start(world, "a")
    world.supervisor.stop(id_of("a"))
    assert world.hub_state().active_project_id is None
    world.gone("a")
    world.supervisor.tick()
    assert world.hub_state().closing == () and len(world.spawner.calls) == 1


def test_stopping_a_view_child_drains_it_and_changes_no_state(world):
    world.supervisor.view(id_of("b"))
    world.running("b", mode="view")
    before = world.hub_state()
    world.supervisor.stop(id_of("b"))
    assert world.spawner.children[0].closed and world.hub_state() == before


def test_stopping_what_is_not_running_is_project_not_running(world):
    assert _refused(world.supervisor.stop, id_of("b")) == "project_not_running"
    assert _refused(world.supervisor.stop, "f" * 32) == "project_not_found"


# -- the words of a project ------------------------------------------------------------------------


def test_a_project_reads_its_lifecycle_its_working_state_and_its_mode(world):
    _activate_and_start(world, "a")
    world.supervisor.view(id_of("b"))
    world.running("b", mode="view")
    world.store.update(lambda s: state.enqueue(s, id_of("c"), FLAG.flag_id))
    found = {name: world.supervisor.status(id_of(name)) for name in "abc"}
    assert [(found[n].lifecycle.state, found[n].working, found[n].mode) for n in "abc"] == [
        ("running", "active", "active"), ("running", "view", "view"), ("stopped", "queued", None)]


def test_a_project_reports_its_port_a_stable_instance_per_process_and_when_it_stopped(world):
    _activate_and_start(world, "a")
    first = world.supervisor.status(id_of("a"))
    assert first.port == 7701 and first.stopped_at is None
    assert first.instance is not None and len(first.instance) == 32
    assert world.supervisor.status(id_of("a")).instance == first.instance, "it is not re-minted"
    world.put_status("a", "serving", started="windows:2")         # the same pid, a new process
    restarted = world.supervisor.status(id_of("a"))
    assert restarted.instance not in (None, first.instance), "a restart must be a new instance"
    world.gone("a")
    stopped = world.supervisor.status(id_of("a"))
    assert (stopped.port, stopped.instance) == (None, None)
    assert stopped.stopped_at == world.clock.now, "the stop time is the status file's own"
    assert world.supervisor.status(id_of("b")).stopped_at is None


def test_a_registry_that_is_not_the_schema_stops_the_loop_without_a_crash(world):
    _activate_and_start(world, "a")
    (world.home / "registry.json").write_text("{not json", encoding="utf-8")
    world.supervisor.tick()
    assert len(world.spawner.calls) == 1


# -- real children: the real `conduct up` with fake dispatch, started by a real spawner ------------

ORIGIN = "http://127.0.0.1:7700"


class RecordingSpawner(spawn.Spawner):
    """The real spawner, which remembers what it started."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[dict] = []
        self.children: list[spawn.Child] = []

    def start(self, **arguments) -> spawn.Child:
        self.calls.append(arguments)
        child = super().start(**arguments)
        self.children.append(child)
        return child


class RealHub:
    """A hub's parts over the drain harness's project: its home, its registry, its children."""

    def __init__(self, project: DrainProject, *, port: int | None = None,
                 registered: bool = True, hub_port: int = 7700) -> None:
        self.project = project
        if registered:
            registry.add_project(
                project_id=project.project_id, root=str(project.root), name="drain",
                root_identity=ownership_native.identity(project.root), folder=project.home)
            if port is not None:
                registry.mutate(lambda current: registry.Registry(None, tuple(
                    replace(p, port=port) for p in current.projects)), project.home)
        self.instance = instance.HubInstance.acquire(project.home)
        self.store = state.HubStateStore(project.home, self.instance)
        self.spawner = RecordingSpawner(
            project.home, hub_origin=ORIGIN, head=(sys.executable, str(CHILD)),
            environ=project._environment(False, None, None, "none", LINGER, None),
            job_policy=lambda: "none")         # the job of this machine is not what is judged
        self.supervisor = supervisor.Supervisor(project.home, self.store, self.spawner,
                                                hub_port=hub_port)

    def pump(self) -> list[dict]:
        """One tick, and what has been started so far."""
        self.supervisor.tick()
        return self.spawner.calls

    def close(self) -> None:
        self.instance.close()


def _record(project: DrainProject):
    try:
        return up_status.read_status(project.status_file)
    except up_status.StatusInvalid:
        return None


def _state_of(project: DrainProject) -> str | None:
    found = _record(project)
    return None if found is None else found.state


def _talk_to(project: DrainProject, hub: RealHub) -> DrainChild:
    """The harness's helper for the HTTP door of the child the hub last started."""
    port = _record(project).port
    return DrainChild(project, hub.spawner.children[-1].popen, True,
                      project.home / "logs" / f"{project.project_id}.log",
                      lines=[f"http://127.0.0.1:{port}/"])


def _forget_the_markers(project: DrainProject) -> None:
    """The markers of attempt `n` have the same name in every process: clear them between."""
    for marker in (*project.control.glob("entered-*"), *project.control.glob("release-*")):
        marker.unlink()


@pytest.fixture
def real(tmp_path):
    made = DrainProject.build(tmp_path)
    hubs: list[RealHub] = []
    yield made, hubs
    for hub in hubs:
        for child in hub.spawner.children:
            child.close_stdin()
    for marker in made.control.glob("release-*"):
        marker.unlink()
    for number in range(1, 5):
        (made.control / f"release-{number}").write_text("1", encoding="ascii")
    for hub in hubs:
        for child in hub.spawner.children:
            try:
                child.wait(30)
            except subprocess.TimeoutExpired:
                _kill_tree(child.popen)
        hub.close()


def _the_new_hub_waits_and_starts_nothing(second: RealHub, project: DrainProject) -> None:
    """For longer than a probe window: no child is started and the drain is not disturbed."""
    deadline = time.monotonic() + PROBE + 1.0
    while time.monotonic() < deadline:
        second.pump()
        assert second.spawner.calls == [], "a second child was started during the drain"
        assert _state_of(project) == "stopping", "the drain was disturbed"
        time.sleep(0.1)
    assert second.supervisor.status(project.project_id).lifecycle.state == "stopping"


def _a_human_resumes_the_run_and_it_finishes(project: DrainProject, second: RealHub) -> None:
    """The restarted run waits for a person; one `resume` carries it to its end."""
    again = _talk_to(project, second)
    status, automation = again.http("GET", f"/command/runs/{RUN_ID}/automation")
    assert (status, automation["state"], automation["reason_code"]) == (
        200, "restart_required", "explicit_resume_required")
    status, resumed = again.http("POST", f"/command/runs/{RUN_ID}/automation/control", {
        "control_id": "resume-1", "authorization_id": "grant", "action": "resume",
        "authorization_digest": automation["authorization"]["authorization_digest"],
        "actor": "owner", "expected_control_id": None})
    assert status == 201, resumed
    again.wait_attempt(1)
    again.release(1)
    project.wait_run_terminal(again)
    assert project.results() == ["succeeded", "succeeded"]
    assert project.proposal_nodes() == ["do", "next"], "each step was proposed once"


def test_hub_restart_during_a_child_drain_starts_no_second_child_and_meets_no_owner_busy(real):
    project, hubs = real
    first = RealHub(project)
    hubs.append(first)
    first.supervisor.activate(project.project_id)
    first.pump()
    wait_until(lambda: _state_of(project) == "serving", WAIT, "the first child to serve")
    old_pid = _record(project).pid
    child = _talk_to(project, first)
    child.authorize()
    child.wait_attempt(1)                      # an attempt is inside its effect, holding on
    first.spawner.children[0].close_stdin()    # the hub dies: its end of the pipe goes
    first.close()
    wait_until(lambda: _state_of(project) == "stopping", WAIT, "the child to begin draining")
    second = RealHub(project, registered=False)
    hubs.append(second)
    second.supervisor.restart()
    _the_new_hub_waits_and_starts_nothing(second, project)
    child.release(1)                           # the attempt ends, the drain completes
    wait_until(lambda: _state_of(project) == "stopped", WAIT, "the first child to stop")
    assert project.head_phase() == "closed"
    _forget_the_markers(project)
    wait_until(lambda: bool(second.pump()), WAIT, "the new hub to start the child")
    (call,) = second.spawner.calls
    assert (call["mode"], call["transition"], call["auto_continue"]) == ("active", None, None)
    wait_until(lambda: _state_of(project) == "serving" and _record(project).pid != old_pid,
               WAIT, "the second child to serve")
    log = project.home / "logs" / f"{project.project_id}.log"
    assert "owner_busy" not in log.read_text(encoding="utf-8", errors="replace")
    _a_human_resumes_the_run_and_it_finishes(project, second)


def _a_port_of_the_range_held_by_a_socket() -> socket.socket:
    for port in (p for p in range(7701, 7800) if p != 7777):
        holder = socket.socket()
        try:
            holder.bind(("127.0.0.1", port))
            holder.listen(1)
            return holder
        except OSError:
            holder.close()
    pytest.skip("every port of 7701-7799 is in use on this machine")


def test_a_busy_port_falls_back_to_port_zero_once_and_the_registry_keeps_its_port(real):
    project, hubs = real
    holder = _a_port_of_the_range_held_by_a_socket()
    try:
        port = holder.getsockname()[1]
        hub = RealHub(project, port=port)
        hubs.append(hub)
        hub.supervisor.activate(project.project_id)
        hub.pump()
        wait_until(lambda: len(hub.pump()) == 2, WAIT, "the hub to try the port 0")
        first, second = hub.spawner.calls
        assert (first["port"], second["port"]) == (port, 0)
        wait_until(lambda: _state_of(project) == "serving", WAIT, "the child to serve on 0")
        assert _record(project).port not in (0, port)
        assert registry.load(project.home).project(project.project_id).port == port
        assert hub.supervisor.status(project.project_id).lifecycle.state == "running"
    finally:
        holder.close()


def _two_children(tmp_path, popen_of_second=None):
    """Two real children of two projects, each by a spawner of its own; both serving."""
    projects, spawners, children = [], [], []
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        project = DrainProject.build(tmp_path / name)
        options = {} if popen_of_second is None or name == "a" else {"popen": popen_of_second(
            children[0])}
        spawner = spawn.Spawner(
            project.home, hub_origin=ORIGIN, head=(sys.executable, str(CHILD)),
            environ=project._environment(True, None, None, "none", 0.0, None),
            job_policy=lambda: "none", **options)
        child = spawner.start(project_id=project.project_id, root=project.root, port=0,
                              mode="active")
        projects.append(project)
        spawners.append(spawner)
        children.append(child)
        wait_until(lambda project=project: _state_of(project) == "serving", WAIT,
                   f"the child of {name} to serve")
    return projects, children


def _leaking(first: spawn.Child):
    """A `Popen` that lets the next child inherit the write end of another child's stdin."""
    def popen(argv, **options):
        if os.name == "nt":
            import msvcrt
            os.set_handle_inheritable(msvcrt.get_osfhandle(first.popen.stdin.fileno()), True)
        else:
            os.set_inheritable(first.popen.stdin.fileno(), True)
        return subprocess.Popen(argv, **{**options, "close_fds": False})
    return popen


def test_the_instrument_sees_a_pipe_that_leaks_into_a_second_child(tmp_path):
    (a, b), (first, second) = _two_children(tmp_path, popen_of_second=_leaking)
    try:
        first.close_stdin()
        time.sleep(2.0)
        assert _state_of(a) == "serving" and first.poll() is None, (
            "the write end of A's pipe leaked into B, so A must not have seen end of file")
    finally:
        _kill_tree(second.popen)
        first.wait(WAIT)
        _kill_tree(first.popen)


def test_closing_the_pipe_of_one_child_gives_another_child_no_end_of_file(tmp_path):
    (a, b), (first, second) = _two_children(tmp_path)
    try:
        first.close_stdin()
        assert first.wait(WAIT) == 0 and _state_of(a) == "stopped"
        assert second.poll() is None and _state_of(b) == "serving", "B saw the end of A's pipe"
        second.close_stdin()
        assert second.wait(WAIT) == 0 and _state_of(b) == "stopped"
    finally:
        for child in (first, second):
            if child.poll() is None:
                _kill_tree(child.popen)
