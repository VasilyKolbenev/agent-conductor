"""A profile applied to a project: copy, and for a live child drain first and start again (8.7).

This is the one flow where the hub, on its own authority, drains a child, waits until the process
is gone and its head is a finished phase, runs a command that takes the project's owner, and then
starts the child again, only while everything it was asked under still holds. The test thread
plays the child (it ends it after it sees the drain request) and the owner (it makes the changes
the restart must not override while the copy is held); the operation runs on its own thread. A
wait is a bounded poll on a fact, never a sleep that hopes.
"""
from __future__ import annotations

import dataclasses
import json
import threading
import time

import pytest

from conductor.hub import events, operations, owner_ops, refusals, registry, spawn, state
from tests._hub_world import PIDS, START, World, id_of, iso
from tests.test_hub_operations import PICK, fake_cli, settled
from tests.test_hub_owner_command import Running, fake

F1 = "f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1"
BLANK = {"folder": None, "activated": None, "providers": None, "git": None, "exclude": None,
         "exclude_names": None, "agent_instructions": None, "projects_home_created": None}
COPIED = {**BLANK, "providers": "copied"}


@pytest.fixture
def world(tmp_path):
    made = World(tmp_path)
    yield made
    made.close()


def _until(condition, what: str = "the condition", seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, f"{what} never held"
        time.sleep(0.01)


class Mono:
    """A monotonic clock that moves when told to."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Copy:
    """The fake `conduct providers --from-profile`: what it printed, and what was true as it began.

    With `hold` the command runs on after it started, until `release` is set, so a test can change
    the world while the copy is under way.
    """

    def __init__(self, probe=lambda: None, *, err: str = "", code: int = 0, hold: bool = False):
        self.probe, self.err, self.code = probe, err, code
        self.seen: list[list[str]] = []
        self.facts: list[object] = []
        self.entered = threading.Event()
        self.release = threading.Event() if hold else None

    def __call__(self, argv, **kwargs):
        self.seen.append(list(argv))
        self.facts.append(self.probe())
        process = fake(err=self.err, code=self.code)(argv, **kwargs)
        self.entered.set()
        return process if self.release is None else Running(process, self.release)


def _status_of(world):
    def status(pid):
        found = world.supervisor.status(pid).lifecycle
        return found.state, found.state_code
    return status


def _ops(world, popen, *, status=None, clock=None, poll: float = 0.01):
    ledger = operations.Operations(world.home, events.EventBus(),
                                   start=lambda _p: None, status=lambda _p: ("running", None))
    options = {} if clock is None else {"clock": clock}
    ops = owner_ops.OwnerOps(world.home, ledger, world.supervisor, popen=popen,
                             policy=lambda: "none", status=status or _status_of(world),
                             poll_seconds=poll, **options)
    return ledger, ops


def _steps(ledger, monkeypatch):
    """Every step a row shows, in order (read after each frame the ledger publishes)."""
    seen: list[str] = []
    real = ledger._publish

    def publish(ident):
        step = ledger.get(ident)["step"]
        if not seen or seen[-1] != step:
            seen.append(step)
        real(ident)

    monkeypatch.setattr(ledger, "_publish", publish)
    return seen


def _running_child(world, name: str, mode: str):
    """A child of the hub's own that serves in `mode`; returns it."""
    if mode == "active":
        world.supervisor.activate(id_of(name))
        world.supervisor.tick()
    else:
        world.supervisor.view(id_of(name))
    world.running(name, mode=mode)
    return world.spawner.children[-1]


def _child_ends(world, child, name: str, *, status: str = "stopped", head: str = "closed"):
    """The child leaves as soon as it sees the drain request, as a real one does."""
    _until(lambda: child.closed, "the drain request")
    world.gone(name, status, head=head)


def _probe(world, child, name: str):
    return lambda: {"closed": child.closed, "alive": PIDS[name] in world.alive,
                    "head": world.heads[name]}


def _project(world, name: str):
    return registry.load(world.home).project(id_of(name))


# -- a project with no live child: copy only ---------------------------------------------------


def test_providers_for_a_stopped_project_copies_only_and_never_starts(world, monkeypatch):
    world.gone("a")                                           # stopped, head closed
    before = (world.home / "hub-state.json").read_bytes() if (
        world.home / "hub-state.json").exists() else None
    copy = Copy()
    ledger, ops = _ops(world, copy)
    steps = _steps(ledger, monkeypatch)
    row = settled(ledger, ops.providers(_project(world, "a"), mode=None, restart=False))
    assert copy.seen[0][3:] == ["providers", "--dir", world.roots["a"], "--from-profile"]
    assert steps == ["providers"] and world.spawner.calls == []
    assert (row["kind"], row["state"], row["code"], row["detail"]) == (
        "providers", "succeeded", None, None)
    assert row["result"] == COPIED and row["project_id"] == id_of("a")
    after = (world.home / "hub-state.json").read_bytes() if (
        world.home / "hub-state.json").exists() else None
    assert after == before and world.roots["a"] not in json.dumps(row)


def test_the_blank_result_has_the_keys_of_the_result_of_an_add(tmp_path):
    ledger = operations.Operations(
        tmp_path, events.EventBus(), start=lambda _p: None,
        status=lambda _p: ("running", None), popen=fake_cli())
    row = settled(ledger, ledger.begin(PICK, "Project", True))
    assert set(row["result"]) == set(BLANK)


# -- a live child: drain, copy, start again in the same mode -----------------------------------


@pytest.mark.parametrize(("name", "mode"), [("a", "active"), ("b", "view")])
def test_providers_for_a_running_project_drains_copies_and_starts_in_the_same_mode(
        world, monkeypatch, name, mode):
    child = _running_child(world, name, mode)
    copy = Copy(_probe(world, child, name))
    ledger, ops = _ops(world, copy)
    steps = _steps(ledger, monkeypatch)
    ident = ops.providers(_project(world, name), mode=mode, restart=True)
    _child_ends(world, child, name)
    _until(lambda: ledger.get(ident)["step"] == "start", "the start step")
    if mode == "active":
        world.supervisor.tick()                         # the restart table starts it, not the hub
    assert len(world.spawner.started(name)) == 2
    assert ledger.get(ident)["state"] == "running"      # the child is not serving yet
    world.running(name, mode=mode)
    row = settled(ledger, ident)
    assert steps == ["drain", "providers", "start"]
    assert copy.facts == [{"closed": True, "alive": False, "head": "closed"}]
    again = world.spawner.started(name)[-1]
    assert again["mode"] == mode and (again["transition"], again["auto_continue"]) == (None, None)
    assert (row["state"], row["code"], row["result"]) == ("succeeded", None, COPIED)


def test_the_active_project_stays_active_and_the_queue_is_untouched_by_a_providers_restart(
        world):
    world.store.update(lambda s: state.enqueue(s, id_of("b"), F1))
    child = _running_child(world, "a", "active")
    before = (world.home / "hub-state.json").read_bytes()
    ledger, ops = _ops(world, Copy())
    ident = ops.providers(_project(world, "a"), mode="active", restart=True)
    _child_ends(world, child, "a")
    _until(lambda: ledger.get(ident)["step"] == "start")
    world.supervisor.tick()
    world.running("a")
    assert settled(ledger, ident)["state"] == "succeeded"
    assert (world.home / "hub-state.json").read_bytes() == before
    current = world.hub_state()
    assert (current.active_project_id, current.queue, current.closing) == (
        id_of("a"), (id_of("b"),), ())


def test_a_child_that_was_already_stopping_is_drained_and_copied_but_never_brought_back(world):
    child = _running_child(world, "b", "view")
    ledger, ops = _ops(world, Copy())
    ident = ops.providers(_project(world, "b"), mode="view", restart=False)
    _child_ends(world, child, "b")
    row = settled(ledger, ident)
    world.supervisor.tick()
    assert (row["state"], row["result"]) == ("succeeded", COPIED)
    assert len(world.spawner.started("b")) == 1


def test_providers_restarts_the_project_even_when_the_copy_failed_and_says_so(world):
    child = _running_child(world, "b", "view")
    ledger, ops = _ops(world, Copy(err="owner_busy: x\n", code=1))
    ident = ops.providers(_project(world, "b"), mode="view", restart=True)
    _child_ends(world, child, "b")
    _until(lambda: len(world.spawner.started("b")) == 2, "the restart")
    world.running("b", mode="view")
    row = settled(ledger, ident)
    assert (row["state"], row["code"], row["detail"], row["result"]) == (
        "failed", "owner_busy", None, None)


# -- the restart needs every one of its conditions (D-H3) --------------------------------------


def _outside_process(world, ops, name):
    """A process of the project that the hub did not start appears while the copy runs."""
    world.alive.add(PIDS[name])
    world.put_status(name, "serving")


def _hub_closing(world, ops, name):
    ops.close()


def _another_project_became_active(world, ops, name):
    world.supervisor.activate(id_of("b"))


def _another_is_active_and_gone(world, ops, name):
    """The place went to B, whose child started and has left again: nothing waits, nothing runs."""
    world.supervisor.activate(id_of("b"))
    world.supervisor.tick()
    world.running("b")
    world.gone("b")


def _the_project_became_active(world, ops, name):
    world.supervisor.activate(id_of(name))              # what the queue's hand-over does


def _another_active_process_lives(world, ops, name):
    world.running("c", mode="active")


def _project_unregistered(world, ops, name):
    registry.remove_project(id_of(name), world.home)


def _root_changed(world, ops, name):
    registry.remove_project(id_of(name), world.home)
    registry.add_project(project_id=id_of(name), root=world.roots[name] + "-moved",
                         root_identity=(77, 1), name=name, folder=world.home, now=iso(START))


CONDITIONS = [
    ("a", "active", "drain_not_finished", _outside_process),
    ("a", "active", "hub_closing", _hub_closing),
    ("a", "active", "another_project_became_active", _another_project_became_active),
    ("a", "active", "another_active_process_lives", _another_active_process_lives),
    ("a", "active", "another_project_is_active_and_gone", _another_is_active_and_gone),
    ("a", "active", "project_unregistered", _project_unregistered),
    ("a", "active", "root_changed", _root_changed),
    ("b", "view", "drain_not_finished", _outside_process),
    ("b", "view", "hub_closing", _hub_closing),
    ("b", "view", "project_became_active", _the_project_became_active),
    ("b", "view", "project_unregistered", _project_unregistered),
    ("b", "view", "root_changed", _root_changed)]


@pytest.mark.parametrize("copied", [True, False], ids=["copy-succeeded", "copy-failed"])
@pytest.mark.parametrize(("name", "mode", "condition", "break_it"), CONDITIONS,
                         ids=[f"{row[1]}-{row[2]}" for row in CONDITIONS])
def test_the_restart_after_a_providers_copy_needs_every_one_of_its_conditions(
        world, name, mode, condition, break_it, copied):
    child = _running_child(world, name, mode)
    copy = Copy(err="" if copied else "owner_busy: x\n", code=0 if copied else 1, hold=True)
    ledger, ops = _ops(world, copy)
    ident = ops.providers(_project(world, name), mode=mode, restart=True)
    _child_ends(world, child, name)
    assert copy.entered.wait(10), "the copy never began"
    break_it(world, ops, name)
    copy.release.set()
    row = settled(ledger, ident)
    world.supervisor.tick()
    again = [call for call in world.spawner.started(name) if call["mode"] == mode]
    assert len(again) == 1, f"{condition}: the child was started again"
    assert row["step"] == "providers"
    if copied:
        assert (row["state"], row["code"], row["result"]) == ("succeeded", None, COPIED)
    else:
        assert (row["state"], row["code"], row["result"]) == ("failed", "owner_busy", None)


def test_a_hub_that_exits_while_the_copy_runs_never_revives_the_child_by_any_move(
        world, monkeypatch):
    child = _running_child(world, "a", "active")
    for move in ("activate", "view"):
        monkeypatch.setattr(world.supervisor, move, lambda *a, **k: pytest.fail("a move was made"))
    copy = Copy(hold=True)
    ledger, ops = _ops(world, copy)
    ident = ops.providers(_project(world, "a"), mode="active", restart=True)
    _child_ends(world, child, "a")
    assert copy.entered.wait(10)
    ops.close()
    copy.release.set()
    assert settled(ledger, ident)["state"] == "succeeded"
    assert len(world.spawner.started("a")) == 1


# -- the drain ---------------------------------------------------------------------------------


def test_a_drain_that_ends_stop_uncertain_fails_the_operation_with_that_code_and_copies_nothing(
        world, monkeypatch):
    child = _running_child(world, "b", "view")
    copy = Copy()
    ledger, ops = _ops(world, copy)
    steps = _steps(ledger, monkeypatch)
    ident = ops.providers(_project(world, "b"), mode="view", restart=True)
    _child_ends(world, child, "b", status="stop_uncertain", head="opened")
    row = settled(ledger, ident)
    assert (row["state"], row["code"], row["step"]) == ("failed", "stop_uncertain", "drain")
    assert copy.seen == [] and steps == ["drain"] and len(world.spawner.started("b")) == 1


def test_providers_on_a_live_process_the_hub_did_not_start_goes_to_the_copy_and_fails_owner_busy(
        world, monkeypatch):
    world.running("c", mode="active")                       # no child of the hub's own
    copy = Copy(err="owner_busy: x\n", code=1)
    ledger, ops = _ops(world, copy)
    steps = _steps(ledger, monkeypatch)
    row = settled(ledger, ops.providers(_project(world, "c"), mode="active", restart=True))
    assert (row["state"], row["code"]) == ("failed", "owner_busy")
    assert steps == ["drain", "providers"] and world.spawner.calls == []


def test_a_hub_that_closes_while_a_providers_operation_waits_starts_nothing_and_ends_nothing(
        world):
    child = _running_child(world, "b", "view")
    copy = Copy()
    ledger, ops = _ops(world, copy)
    ident = ops.providers(_project(world, "b"), mode="view", restart=True)
    _until(lambda: child.closed, "the drain request")
    ops.close()                                             # the child has not left yet
    row = settled(ledger, ident)
    assert (row["state"], row["code"]) == ("failed", "subprocess_failed")
    assert copy.seen == [] and len(world.spawner.started("b")) == 1
    assert child.poll() is None                             # the hub ended nothing: it only asked


# -- the start ---------------------------------------------------------------------------------


def test_a_child_that_never_reads_running_ends_the_operation_start_timeout(world):
    child = _running_child(world, "b", "view")
    clock = Mono()
    ledger, ops = _ops(world, Copy(), status=lambda _pid: ("stopped", None), clock=clock)
    ident = ops.providers(_project(world, "b"), mode="view", restart=True)
    _child_ends(world, child, "b")
    _until(lambda: ledger.get(ident)["step"] == "start")

    def time_passes() -> bool:            # the wait reads the clock once and then at each poll
        clock.now += operations.START_WAIT_SECONDS + 1
        return ledger.get(ident)["state"] != "running"

    _until(time_passes, "the end of the start wait")
    row = ledger.get(ident)
    assert (row["state"], row["code"], row["result"]) == ("failed", "start_timeout", COPIED)


@pytest.mark.parametrize(("seen", "code"), [
    (("failed", "bind_failed"), "bind_failed"), (("failed", None), "start_failed"),
    (("recovery_required", None), "start_failed"), (("missing", None), "start_failed"),
    (("failed", "not_a_code_of_the_list"), "subprocess_failed")])
def test_a_child_that_fails_to_start_ends_the_operation_with_a_code_of_the_start_list(
        world, seen, code):
    child = _running_child(world, "b", "view")
    ledger, ops = _ops(world, Copy(), status=lambda _pid: seen)
    ident = ops.providers(_project(world, "b"), mode="view", restart=True)
    _child_ends(world, child, "b")
    row = settled(ledger, ident)
    assert (row["state"], row["code"]) == ("failed", code) and row["result"] == COPIED


def test_a_copy_that_failed_keeps_its_own_code_when_the_start_fails_as_well(world):
    child = _running_child(world, "b", "view")
    ledger, ops = _ops(world, Copy(err="owner_busy: x\n", code=1),
                       status=lambda _pid: ("failed", "bind_failed"))
    ident = ops.providers(_project(world, "b"), mode="view", restart=True)
    _child_ends(world, child, "b")
    row = settled(ledger, ident)
    assert (row["state"], row["code"], row["result"]) == ("failed", "owner_busy", None)
    assert len(world.spawner.started("b")) == 2           # it was started, and it failed there


def test_a_start_the_job_refuses_ends_the_operation_with_that_code_and_keeps_the_copy(world):
    child = _running_child(world, "b", "view")
    copy = Copy(hold=True)
    ledger, ops = _ops(world, copy)
    ident = ops.providers(_project(world, "b"), mode="view", restart=True)
    _child_ends(world, child, "b")
    assert copy.entered.wait(10)
    world.spawner.refusal = spawn.SpawnRefused("hub_in_kill_on_close_job", "a job")
    copy.release.set()
    row = settled(ledger, ident)
    assert (row["state"], row["code"], row["result"]) == (
        "failed", "hub_in_kill_on_close_job", COPIED)
    assert len(world.spawner.started("b")) == 1


# -- what the row says of a copy the command refused ---------------------------------------------


def test_a_project_in_recovery_required_meets_providers_as_subprocess_failed_not_a_new_code(world):
    world.gone("a", "serving", head="opened")               # dead, head left opened
    err = "recovery_required: previous owner did not close the project\n"
    ledger, ops = _ops(world, Copy(err=err, code=1))
    row = settled(ledger, ops.providers(_project(world, "a"), mode=None, restart=False))
    assert (row["state"], row["code"], row["detail"]) == (
        "failed", "subprocess_failed", {"reason": "recovery_required"})
    assert "previous owner" not in json.dumps(row) and world.roots["a"] not in json.dumps(row)
    assert "recovery_required" not in refusals.OPERATION_CODES_BY_STEP["providers"]


@pytest.mark.parametrize(("err", "code"), [
    ("Traceback (most recent call last):\n", "subprocess_failed"), ("", "subprocess_failed"),
    ("owner_busy: x\n", "owner_busy"), ("profile_absent: x\n", "profile_absent"),
    ("profile_invalid: x\n", "profile_invalid"),
    ("noise\nrecovery_required: x\n", "subprocess_failed"),
    ("login_recovery_required: x\n", "subprocess_failed")])
def test_a_providers_failure_without_a_typed_reason_has_a_null_detail(world, err, code):
    world.gone("a")
    ledger, ops = _ops(world, Copy(err=err, code=1))
    row = settled(ledger, ops.providers(_project(world, "a"), mode=None, restart=False))
    assert (row["state"], row["code"], row["detail"]) == ("failed", code, None)


@pytest.mark.parametrize("err", ["owner_busy: x\n", "recovery_required: x\n",
                                 "restart the OS\n", ""])
def test_no_command_the_hub_runs_for_a_profile_carries_a_prepare_flag(world, err):
    world.gone("a")
    copy = Copy(err=err, code=1)
    ledger, ops = _ops(world, copy)
    settled(ledger, ops.providers(_project(world, "a"), mode=None, restart=False))
    assert copy.seen and not [arg for argv in copy.seen for arg in argv if "prepare" in arg]


def test_a_second_operation_on_the_project_while_one_runs_is_refused_project_busy(world):
    world.gone("a")
    copy = Copy(hold=True)
    ledger, ops = _ops(world, copy)
    first = ops.providers(_project(world, "a"), mode=None, restart=False)
    assert copy.entered.wait(10)
    with pytest.raises(refusals.HubRefusal) as busy:
        ops.providers(_project(world, "a"), mode=None, restart=False)
    assert busy.value.code == "project_busy"
    with pytest.raises(refusals.HubRefusal) as other:
        ops.recover(_project(world, "a"))
    assert other.value.code == "project_busy"
    copy.release.set()
    assert settled(ledger, first)["state"] == "succeeded"


def test_a_hub_that_is_closing_starts_no_profile_copy(world):
    world.gone("a")
    copy = Copy()
    ledger, ops = _ops(world, copy)
    ops.close()
    with pytest.raises(refusals.HubRefusal) as sealed:
        ops.providers(_project(world, "a"), mode=None, restart=False)
    assert sealed.value.code == "project_busy" and copy.seen == []
    assert ledger.running_for(id_of("a")) is None


# -- the supervisor's one step: decide and start under its lock --------------------------------


def _lock_is_held_by_another_thread(sup) -> bool:
    got: list[bool] = []
    thread = threading.Thread(target=lambda: got.append(sup._lock.acquire(blocking=False)))
    thread.start()
    thread.join()
    if got[0]:
        sup._lock.release()
    return not got[0]


def _ended(world, name: str, mode: str) -> None:
    """A child of the hub that has been drained and is gone, its head closed."""
    child = _running_child(world, name, mode)
    child.close_stdin()
    world.gone(name, "stopped", head="closed")


def test_restart_in_mode_asks_the_active_project_for_the_restart_table_and_starts_a_view_at_once(
        world):
    _ended(world, "a", "active")
    assert world.supervisor.restart_in_mode(
        id_of("a"), "active", root=world.roots["a"], allowed=lambda: True) is True
    assert len(world.spawner.started("a")) == 1             # by the next tick, not now
    world.supervisor.tick()
    again = world.spawner.started("a")[-1]
    assert (again["mode"], again["transition"], again["auto_continue"]) == ("active", None, None)
    _ended(world, "b", "view")
    assert world.supervisor.restart_in_mode(
        id_of("b"), "view", root=world.roots["b"], allowed=lambda: True) is True
    assert world.spawner.started("b")[-1]["mode"] == "view"


def test_restart_in_mode_does_nothing_for_a_mode_it_does_not_know_or_a_closure_not_proven(world):
    _ended(world, "b", "view")
    assert world.supervisor.restart_in_mode(
        id_of("b"), "stopped", root=world.roots["b"], allowed=lambda: True) is False
    world.heads["b"] = "opened"
    assert world.supervisor.restart_in_mode(
        id_of("b"), "view", root=world.roots["b"], allowed=lambda: True) is False
    assert len(world.spawner.started("b")) == 1


def test_restart_in_mode_does_nothing_on_a_hub_state_nobody_can_read(world):
    _ended(world, "a", "active")
    (world.home / "hub-state.json").write_bytes(b"{not json")
    assert world.supervisor.restart_in_mode(
        id_of("a"), "active", root=world.roots["a"], allowed=lambda: True) is False


def test_restart_in_mode_does_not_ask_an_active_project_that_a_transition_is_about_to_start(
        world):
    world.supervisor.activate(id_of("a"))                   # A is active; its start is waiting
    assert world.supervisor.restart_in_mode(
        id_of("a"), "active", root=world.roots["a"], allowed=lambda: True) is False
    world.supervisor.tick()
    assert len(world.spawner.started("a")) == 1             # started once, by the transition


def test_restart_in_mode_does_not_ask_an_active_project_while_a_closure_is_owed(world):
    _ended(world, "a", "active")
    owed = state.ClosingEntry(id_of("c"), 4812, "windows:1", "1" * 32, "2026-09-30T10:00:00Z")
    world.store.update(lambda current: dataclasses.replace(current, closing=(owed,)))
    assert world.supervisor.restart_in_mode(
        id_of("a"), "active", root=world.roots["a"], allowed=lambda: True) is False


def test_the_decision_and_the_start_are_one_step_under_the_supervisors_lock(world, monkeypatch):
    held: list[tuple[str, bool]] = []
    for name, mode, method in (("a", "active", "_restart_the_active"), ("b", "view", "_launch")):
        _ended(world, name, mode)
        real = getattr(world.supervisor, method)

        def spy(*args, _real=real, _name=method, **kwargs):
            held.append((_name, _lock_is_held_by_another_thread(world.supervisor)))
            return _real(*args, **kwargs)

        monkeypatch.setattr(world.supervisor, method, spy)
        assert world.supervisor.restart_in_mode(
            id_of(name), mode, root=world.roots[name],
            allowed=lambda: held.append(("allowed", _lock_is_held_by_another_thread(
                world.supervisor))) or True) is True
    assert held == [("allowed", True), ("_restart_the_active", True),
                    ("allowed", True), ("_launch", True)]
