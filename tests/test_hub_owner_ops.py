"""The recoveries the hub runs as operations of the one ledger (spec 4.1.8, 4.6.4; ADR-8).

The command is faked at the one seam, `popen`: it writes what a real one would print and, like the
real `conduct ownership recover`, leaves ONE thing behind on success: the ownership head. A
recovery is simulated by changing `world.heads` only; the child's status file is never rewritten.
"""
from __future__ import annotations

import json
import threading

import pytest

from conductor.hub import events, operations, owner_ops, refusals, routes
from tests._hub_world import World, id_of
from tests.test_hub_operations import settled
from tests.test_hub_owner_command import (LEGACY, LOGIN_LEGACY, LOGIN_OTHER, LOGIN_SAME_BOOT,
                                          NOT_PROVEN, OTHER_ENVIRONMENT, REWORDED, SAME_BOOT,
                                          UNMEASURED, Held, fake)

RECOVERED = json.dumps({"phase": "recovered", "generation": 4})
LOGIN_RECOVERED = json.dumps({"state": "recovered", "resource": "sha256:ab"})
KEY, FOLDER = "ab" * 32, r"C:\logins\shared"


@pytest.fixture
def world(tmp_path):
    made = World(tmp_path)
    yield made
    made.close()


def _ops(world, popen):
    ledger = operations.Operations(world.home, events.EventBus(),
                                   start=lambda _p: None, status=lambda _p: ("running", None))
    ops = owner_ops.OwnerOps(world.home, ledger, world.supervisor, popen=popen,
                             policy=lambda: "none", status=lambda _pid: ("running", None))
    return ledger, ops


def _recovering(world, name, **kwargs):
    """A command that leaves the head `recovered` before it returns, as the real one does."""
    inner = fake(**kwargs)

    def launch(argv, **options):
        world.heads[name] = "recovered"
        return inner(argv, **options)
    return launch


def _crash_stop_uncertain(world, name="a"):
    world.supervisor.activate(id_of(name))
    world.supervisor.tick()
    world.running(name)
    world.spawner.children[-1].leave(1)
    world.gone(name, "stop_uncertain", head="opened")


def _recover(world, ops, name="a"):
    return ops.recover(world.supervisor.require_recoverable(id_of(name)))


def test_a_recovery_runs_the_ownership_command_for_the_registered_root_and_nothing_else(world):
    seen = []
    ledger, ops = _ops(world, fake(out=RECOVERED, seen=seen))
    world.gone("a", "stop_uncertain", head="opened")
    row = settled(ledger, _recover(world, ops))
    ((argv, _kwargs),) = seen
    assert argv[3:] == ["ownership", "recover", "--dir", world.roots["a"]]
    assert row["kind"] == "recover" and row["step"] == "recover"
    assert row["project_id"] == id_of("a") and row["source"] is None
    assert (row["state"], row["code"], row["detail"], row["result"]) == (
        "succeeded", None, None, None)
    assert world.roots["a"] not in json.dumps(row)


def test_a_recovery_that_succeeds_lets_the_supervisor_start_the_active_project_by_its_table(world):
    ledger, ops = _ops(world, _recovering(world, "a", out=RECOVERED))
    _crash_stop_uncertain(world)
    assert settled(ledger, _recover(world, ops))["state"] == "succeeded"
    world.supervisor.tick()
    again = world.spawner.calls[-1]
    assert (again["project_id"], again["mode"]) == (id_of("a"), "active")
    assert (again["transition"], again["auto_continue"]) == (None, None)
    assert len(world.spawner.started("a")) == 2


def test_a_recovery_of_a_project_that_is_not_active_starts_nothing(world):
    ledger, ops = _ops(world, _recovering(world, "b", out=RECOVERED))
    world.gone("b", "stop_uncertain", head="opened")
    assert settled(ledger, _recover(world, ops, "b"))["state"] == "succeeded"
    world.supervisor.tick()
    assert world.spawner.calls == []


@pytest.mark.parametrize(("err", "code"), [
    ("recovery_required: restart the OS\n", "recovery_required"),
    ("recovery_refused: nothing\n", "recovery_refused"),
    ("transition_conflict: x\n", "transition_conflict"),
    ("ownership_lost: x\n", "ownership_lost"),
    ("Traceback (most recent call last):\n", "subprocess_failed"),
    ("owner_busy: x\n", "subprocess_failed"),
    ("login_recovery_required: x\n", "subprocess_failed")])
def test_a_refused_recovery_ends_failed_with_a_code_of_its_step_and_starts_nothing(
        world, err, code):
    ledger, ops = _ops(world, fake(err=err, code=1))
    world.gone("a", "serving", head="opened")
    row = settled(ledger, _recover(world, ops))
    assert (row["state"], row["code"]) == ("failed", code) and world.spawner.calls == []
    assert world.roots["a"] not in json.dumps(row)


@pytest.mark.parametrize("out", ["{}", "", "not json", json.dumps({"phase": "closed"}),
                                 RECOVERED + "\n{}\n"])
def test_a_recovery_that_exits_zero_without_the_one_recovered_object_is_subprocess_failed(
        world, out):
    ledger, ops = _ops(world, fake(out=out))
    world.gone("a", "serving", head="opened")
    row = settled(ledger, _recover(world, ops))
    assert (row["state"], row["code"], row["detail"]) == ("failed", "subprocess_failed", None)


@pytest.mark.parametrize(("err", "word"), [
    (SAME_BOOT, "restart_needed"), (LEGACY, "prepare_needed"),
    (OTHER_ENVIRONMENT, "other_environment"), (UNMEASURED, "not_proven"),
    (NOT_PROVEN, "not_proven"), (REWORDED, "not_proven")])
def test_a_recovery_that_needs_a_restart_or_a_preparation_says_which_in_the_row(world, err, word):
    ledger, ops = _ops(world, fake(err=err, code=1))
    world.gone("a", "serving", head="opened")
    row = settled(ledger, _recover(world, ops))
    assert (row["state"], row["code"], row["detail"]) == (
        "failed", "recovery_required", {"reason": word})
    assert world.roots["a"] not in json.dumps(row) and world.spawner.calls == []


def test_a_recovery_that_failed_for_another_code_carries_no_reason(world):
    ledger, ops = _ops(world, fake(err="recovery_refused: nothing\n", code=1))
    world.gone("a", "serving", head="opened")
    row = settled(ledger, _recover(world, ops))
    assert (row["code"], row["detail"]) == ("recovery_refused", None)


@pytest.mark.parametrize("err", [SAME_BOOT, LEGACY, OTHER_ENVIRONMENT, UNMEASURED, REWORDED, ""])
def test_no_command_the_hub_runs_for_a_recovery_carries_a_prepare_flag(world, err):
    seen = []
    ledger, ops = _ops(world, fake(err=err, code=1, seen=seen))
    world.gone("a", "serving", head="opened")
    settled(ledger, _recover(world, ops))
    assert seen and not [arg for argv, _ in seen for arg in argv if "prepare" in arg]


def test_the_route_table_has_no_route_that_prepares():
    assert not [row.path for row in routes.HUB_ROUTES if "prepare" in row.path]


def test_a_second_recovery_of_the_same_project_while_one_runs_is_refused_project_busy(world):
    command = Held(out=RECOVERED)
    ledger, ops = _ops(world, command)
    world.gone("a", "serving", head="opened")
    first = _recover(world, ops)
    assert command.entered.wait(10)
    with pytest.raises(refusals.HubRefusal) as busy:
        ops.require_free(id_of("a"))
    assert busy.value.code == "project_busy"
    with pytest.raises(refusals.HubRefusal) as again:
        _recover(world, ops)
    assert again.value.code == "project_busy"
    command.release.set()
    assert settled(ledger, first)["state"] == "succeeded"
    ops.require_free(id_of("a"))                            # free again once the row ended


def test_a_fault_inside_the_operation_ends_the_row_failed_in_the_closed_vocabulary(world):
    def broken(_argv, **_kwargs):
        raise RuntimeError("the popen seam broke in a way nobody listed")

    ledger, ops = _ops(world, broken)
    world.gone("a", "serving", head="opened")
    row = settled(ledger, _recover(world, ops))
    assert (row["state"], row["code"], row["detail"]) == ("failed", "subprocess_failed", None)
    assert "RuntimeError" not in json.dumps(row)


def test_an_operation_whose_thread_cannot_be_made_does_not_stay_running_and_claim_its_project(
        world, monkeypatch):
    ledger, ops = _ops(world, fake(out=RECOVERED))
    world.gone("a", "serving", head="opened")

    def no_thread(_self):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading.Thread, "start", no_thread)
    row = ledger.get(_recover(world, ops))
    assert (row["state"], row["code"]) == ("failed", "subprocess_failed")
    ops.require_free(id_of("a"))                         # the project is free for another try


def test_a_hub_that_is_closing_starts_no_recovery_and_ends_none_in_flight(world):
    command = Held(out=RECOVERED)
    ledger, ops = _ops(world, command)
    world.gone("a", "serving", head="opened")
    world.gone("b", "serving", head="opened")
    flying = _recover(world, ops)
    assert command.entered.wait(10)
    ops.close()
    with pytest.raises(refusals.HubRefusal) as sealed:
        _recover(world, ops, "b")
    assert sealed.value.code == "project_busy" and len(command.started) == 1
    assert ledger.get(flying)["state"] == "running"              # close did not end the command
    command.release.set()
    assert settled(ledger, flying)["state"] == "succeeded"       # and it finished on its own


def test_a_command_that_reaches_its_launch_after_the_hub_closed_is_not_started(world):
    started = []
    ledger, ops = _ops(world, fake(out=RECOVERED, seen=started))
    world.gone("a", "serving", head="opened")
    project = world.supervisor.require_recoverable(id_of("a"))
    ident = ledger.open_project_row("recover", project.project_id, "recover")
    ops.close()
    ops._recover(ident, project)             # what a thread that lost the race with `close` runs
    row = ledger.get(ident)
    assert started == [] and (row["state"], row["code"]) == ("failed", "subprocess_failed")


def test_a_hub_job_that_would_end_a_command_with_the_hub_fails_the_row_and_starts_none(world):
    started = []
    ledger = operations.Operations(world.home, events.EventBus(),
                                   start=lambda _p: None, status=lambda _p: ("running", None))
    ops = owner_ops.OwnerOps(world.home, ledger, world.supervisor,
                             popen=fake(out=RECOVERED, seen=started),
                             policy=lambda: "kill_on_close", status=lambda _pid: ("running", None))
    world.gone("a", "serving", head="opened")
    row = settled(ledger, _recover(world, ops))
    assert started == [] and (row["state"], row["code"]) == ("failed", "subprocess_failed")


# -- the recovery of a shared login (recover-login) ------------------------------------------------


def test_a_login_recovery_runs_the_command_for_the_folder_it_was_given_and_ends_on_its_object(
        world):
    seen = []
    ledger, ops = _ops(world, fake(out=LOGIN_RECOVERED, seen=seen))
    row = settled(ledger, ops.recover_login(KEY, FOLDER))
    ((argv, _kwargs),) = seen
    assert argv[3:] == ["ownership", "recover-login", "--auth-home", FOLDER]
    assert (row["kind"], row["step"], row["project_id"], row["source"]) == (
        "recover_login", "recover_login", None, None)
    assert (row["state"], row["code"], row["detail"], row["result"]) == (
        "succeeded", None, None, None)
    assert FOLDER not in json.dumps(row)


@pytest.mark.parametrize("out", ["{}", "", "not json", RECOVERED, LOGIN_RECOVERED + "\n{}\n"])
def test_a_login_recovery_that_exits_zero_without_its_one_recovered_object_is_subprocess_failed(
        world, out):
    ledger, ops = _ops(world, fake(out=out))
    row = settled(ledger, ops.recover_login(KEY, FOLDER))
    assert (row["state"], row["code"], row["detail"]) == ("failed", "subprocess_failed", None)


@pytest.mark.parametrize(("err", "code"), [
    ("login_recovery_required: restart the OS\n", "login_recovery_required"),
    ("login_owner_busy: x\n", "login_owner_busy"),
    ("login_ownership_invalid: x\n", "login_ownership_invalid"),
    ("login_context_required: x\n", "login_context_required"),
    ("recovery_refused: x\n", "subprocess_failed"),
    ("recovery_required: restart the OS\n", "subprocess_failed"),
    ("Traceback (most recent call last):\n", "subprocess_failed")])
def test_a_refused_login_recovery_ends_failed_with_a_code_of_its_step(world, err, code):
    ledger, ops = _ops(world, fake(err=err, code=1))
    row = settled(ledger, ops.recover_login(KEY, FOLDER))
    assert (row["state"], row["code"]) == ("failed", code) and FOLDER not in json.dumps(row)


@pytest.mark.parametrize(("err", "word"), [
    (LOGIN_SAME_BOOT, "restart_needed"), (LOGIN_LEGACY, "prepare_needed"),
    (LOGIN_OTHER, "other_environment"),
    ("login_recovery_required: no restart is proven: x\n", "not_proven"),
    ("login_recovery_required: a sentence nobody knows\n", "not_proven")])
def test_a_login_recovery_that_needs_a_restart_or_a_preparation_says_which_in_the_row(
        world, err, word):
    ledger, ops = _ops(world, fake(err=err, code=1))
    row = settled(ledger, ops.recover_login(KEY, FOLDER))
    assert (row["state"], row["code"], row["detail"]) == (
        "failed", "login_recovery_required", {"reason": word})
    assert FOLDER not in json.dumps(row)


@pytest.mark.parametrize("err", [LOGIN_SAME_BOOT, LOGIN_LEGACY, LOGIN_OTHER, ""])
def test_no_command_the_hub_runs_for_a_login_recovery_carries_a_prepare_flag(world, err):
    seen = []
    ledger, ops = _ops(world, fake(err=err, code=1, seen=seen))
    settled(ledger, ops.recover_login(KEY, FOLDER))
    assert seen and not [arg for argv, _ in seen for arg in argv if "prepare" in arg]


def test_a_second_login_recovery_of_the_same_key_while_one_runs_is_the_operation_running(world):
    command = Held(out=LOGIN_RECOVERED)
    ledger, ops = _ops(world, command)
    first = ops.recover_login(KEY, FOLDER)
    assert command.entered.wait(10)
    assert ops.recover_login(KEY, FOLDER) == first and ops.running_login(KEY) == first
    assert len(command.started) == 1
    other = ops.recover_login("cd" * 32, FOLDER + "-2")          # another login is its own
    assert other != first
    command.release.set()
    assert settled(ledger, first)["state"] == "succeeded" and settled(ledger, other)
    assert ops.running_login(KEY) is None
    assert ops.recover_login(KEY, FOLDER) != first               # after it ended: a new one


def test_a_login_recovery_runs_beside_a_project_operation(world):
    ledger, ops = _ops(world, fake(out=LOGIN_RECOVERED))
    ledger.open_project_row("recover", id_of("a"), "recover")     # stays running
    assert settled(ledger, ops.recover_login(KEY, FOLDER))["state"] == "succeeded"
    assert ledger.running_for(id_of("a")) is not None


def test_a_hub_that_is_closing_starts_no_login_recovery_and_hands_back_the_one_that_runs(world):
    command = Held(out=LOGIN_RECOVERED)
    ledger, ops = _ops(world, command)
    flying = ops.recover_login(KEY, FOLDER)
    assert command.entered.wait(10)
    ops.close()
    assert ops.recover_login(KEY, FOLDER) == flying              # an idempotent answer is harmless
    with pytest.raises(refusals.HubRefusal) as sealed:
        ops.recover_login("cd" * 32, FOLDER + "-2")
    assert sealed.value.code == "operation_busy" and len(command.started) == 1
    command.release.set()
    assert settled(ledger, flying)["state"] == "succeeded"


def test_a_fault_inside_a_login_recovery_ends_the_row_failed_in_the_closed_vocabulary(world):
    def broken(_argv, **_kwargs):
        raise RuntimeError("the popen seam broke")

    ledger, ops = _ops(world, broken)
    row = settled(ledger, ops.recover_login(KEY, FOLDER))
    assert (row["state"], row["code"], row["detail"]) == ("failed", "subprocess_failed", None)
