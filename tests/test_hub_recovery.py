"""What the hub believes after `conduct ownership recover` (spec 4.1.8, ADR-8; review ruling D-H1).

A recovery leaves ONE thing behind: the ownership head (`recovered`). The child's status file is
the dead process's last word and is never rewritten by the command, so these tests change
`world.heads` only. `world.gone()` is used for the crash, never for the recovery.
"""
from __future__ import annotations

import pytest

from conductor.hub import lifecycle as words
from conductor.hub import spawn, supervisor
from tests._hub_world import FakeSpawner, World, id_of


@pytest.fixture
def world(tmp_path):
    made = World(tmp_path)
    yield made
    made.close()


def _crash_stop_uncertain(world, name="a"):
    world.supervisor.activate(id_of(name))
    world.supervisor.tick()
    world.running(name)
    world.spawner.children[-1].leave(1)
    world.gone(name, "stop_uncertain", head="opened")


def _the_recovery_command_ran(world, name="a"):
    world.heads[name] = "recovered"            # the status file is NOT touched


def test_a_stop_uncertain_project_reads_stopped_once_the_recovery_left_its_head_recovered(world):
    _crash_stop_uncertain(world)
    assert world.supervisor.status(id_of("a")).lifecycle.state == "stop_uncertain"
    _the_recovery_command_ran(world)
    assert world.supervisor.status(id_of("a")).lifecycle.state == "stopped"


def test_a_refused_recovery_required_project_reads_stopped_once_its_head_is_recovered(world):
    world.heads["b"] = "opened"
    world.put_status("b", "refused", code="recovery_required")
    assert world.supervisor.status(id_of("b")).lifecycle.state == "recovery_required"
    _the_recovery_command_ran(world, "b")
    assert world.supervisor.status(id_of("b")).lifecycle.state == "stopped"


@pytest.mark.parametrize("head", ["opened", "recovery_prepared", "a_phase_a_later_build_adds"])
def test_a_dead_project_stays_unfinished_for_every_head_that_is_not_a_finished_phase(world, head):
    world.gone("a", "serving", head=head)
    assert world.supervisor.status(id_of("a")).lifecycle.state == "recovery_required"
    world.gone("b", "stop_uncertain", head=head)
    assert world.supervisor.status(id_of("b")).lifecycle.state == "stop_uncertain"


def test_a_head_that_cannot_be_read_never_reads_stopped(world):
    world.gone("a", "serving", head="closed")
    world.unreadable.add("a")
    assert world.supervisor.status(id_of("a")).lifecycle.state == "recovery_required"
    world.gone("b", "stop_uncertain", head="recovered")
    world.unreadable.add("b")
    assert world.supervisor.status(id_of("b")).lifecycle.state == "stop_uncertain"


def test_a_project_with_no_head_at_all_never_reads_stopped(world):
    world.gone("a", "serving", head=None)
    assert world.supervisor.status(id_of("a")).lifecycle.state == "recovery_required"
    world.gone("b", "stop_uncertain", head=None)
    assert world.supervisor.status(id_of("b")).lifecycle.state == "stop_uncertain"


def test_a_head_of_another_activation_never_reads_stopped(world):
    world.gone("a", "serving", head="closed")
    world.nonces["a"] = "f" * 32                       # not the project's own activation
    assert world.supervisor.status(id_of("a")).lifecycle.state == "recovery_required"
    world.gone("b", "stop_uncertain", head="recovered")
    world.nonces["b"] = "f" * 32
    assert world.supervisor.status(id_of("b")).lifecycle.state == "stop_uncertain"


def test_the_supervisor_never_hands_none_to_derive_for_a_dead_record(world, monkeypatch):
    seen = []
    real = words.derive
    monkeypatch.setattr(words, "derive", lambda *a, **k: seen.append(k.get("head_phase", "absent"))
                        or real(*a, **k))
    world.gone("a", "serving", head="closed")
    world.unreadable.add("a")
    world.supervisor.status(id_of("a"))
    assert seen and None not in seen and "absent" not in seen


def test_a_new_hub_after_a_recovery_starts_the_active_project_that_still_says_stop_uncertain(
        world):
    _crash_stop_uncertain(world)
    _the_recovery_command_ran(world)
    spawner = FakeSpawner()
    newer = world.new_supervisor(spawner)
    newer.restart()
    (call,) = spawner.calls
    assert (call["project_id"], call["mode"]) == (id_of("a"), "active")
    assert (call["transition"], call["auto_continue"]) == (None, None)   # it grants nothing


def test_a_new_hub_does_not_start_the_active_project_while_its_head_is_not_a_finished_phase(
        world):
    _crash_stop_uncertain(world)
    for head in ("opened", "recovery_prepared"):
        world.heads["a"] = head
        spawner = FakeSpawner()
        world.new_supervisor(spawner).restart()
        assert spawner.calls == []
    world.heads["a"] = "recovered"
    world.nonces["a"] = "f" * 32                       # a head of another activation
    spawner = FakeSpawner()
    world.new_supervisor(spawner).restart()
    assert spawner.calls == []


# -- the supervisor's moves for a recovery, a drain and the login state (Task 2) ----------------


def _refused(call, *args) -> str:
    with pytest.raises(supervisor.SupervisorRefused) as caught:
        call(*args)
    return caught.value.code


def test_recovery_is_refused_while_a_child_lives_and_when_there_is_nothing_to_recover(world):
    world.running("a")
    assert _refused(world.supervisor.require_recoverable, id_of("a")) == "project_running"
    world.gone("b")                                      # stopped, head closed
    assert _refused(world.supervisor.require_recoverable, id_of("b")) == "recover_not_needed"
    assert _refused(world.supervisor.require_recoverable, "f" * 32) == "project_not_found"


@pytest.mark.parametrize("how", ["stop_uncertain", "died_opened", "stopped_but_head_opened",
                                 "stopped_but_head_prepared", "stopped_but_head_unreadable",
                                 "stopped_but_head_another_activation"])
def test_recovery_is_allowed_for_a_dead_project_whose_head_is_left_open(world, how):
    if how == "stop_uncertain":
        world.gone("a", "stop_uncertain", head="opened")
    elif how == "died_opened":
        world.gone("a", "serving", head="opened")
    elif how == "stopped_but_head_opened":
        world.gone("a", "stopped", head="opened")
    elif how == "stopped_but_head_prepared":
        world.gone("a", "stopped", head="recovery_prepared")
    elif how == "stopped_but_head_unreadable":
        world.gone("a", "stopped", head="closed")
        world.unreadable.add("a")
    else:
        world.gone("a", "stopped", head="closed")
        world.nonces["a"] = "f" * 32
    assert world.supervisor.require_recoverable(id_of("a")).project_id == id_of("a")


def test_a_stop_uncertain_project_whose_process_may_still_live_is_running_not_recoverable(world):
    world.alive.add(101)
    world.put_status("a", "stop_uncertain")
    assert _refused(world.supervisor.require_recoverable, id_of("a")) == "project_running"


def test_after_a_recovery_the_active_project_is_started_again_without_a_transition_or_a_flag(
        world):
    _crash_stop_uncertain(world)
    _the_recovery_command_ran(world)
    world.supervisor.recovered(id_of("a"))
    world.supervisor.tick()
    again = world.spawner.calls[-1]
    assert (again["mode"], again["transition"], again["auto_continue"]) == ("active", None, None)
    assert len(world.spawner.started("a")) == 2


def test_after_a_recovery_a_project_that_is_not_active_is_not_started(world):
    world.gone("b", "stop_uncertain", head="opened")
    _the_recovery_command_ran(world, "b")
    world.supervisor.recovered(id_of("b"))
    world.supervisor.tick()
    assert world.spawner.calls == []


def test_a_recovery_forgets_the_start_failure_that_stood_on_the_project(world):
    def refuse(_arguments):
        raise spawn.SpawnRefused("hub_in_kill_on_close_job", "a job")

    world.spawner.before_start = refuse
    world.supervisor.view(id_of("b"))
    assert world.supervisor.status(id_of("b")).lifecycle.state == "failed"
    world.supervisor.recovered(id_of("b"))
    assert world.supervisor.status(id_of("b")).lifecycle.state == "stopped"


def test_the_recovery_of_the_previous_active_lets_the_waiting_transition_begin(world):
    _crash_stop_uncertain(world)
    world.supervisor.activate(id_of("b"))
    world.supervisor.tick()
    assert world.spawner.started("b") == []          # not proven closed: nothing starts
    _the_recovery_command_ran(world)
    world.supervisor.recovered(id_of("a"))
    world.supervisor.tick()
    (started,) = world.spawner.started("b")
    assert started["mode"] == "active" and started["transition"] is not None
    assert world.hub_state().closing == ()


def test_drain_project_closes_only_the_hubs_own_live_child_and_changes_no_state(world):
    world.supervisor.view(id_of("b"))
    world.running("b", mode="view")
    before = world.hub_state()
    assert world.supervisor.drain_project(id_of("b")) is True
    assert world.spawner.children[0].closed and world.hub_state() == before
    world.running("c")                                   # a live process the hub did not start
    assert world.supervisor.drain_project(id_of("c")) is False
    assert _refused(world.supervisor.drain_project, "f" * 32) == "project_not_found"


def test_closure_of_names_alive_closed_and_uncertain(world):
    world.running("a")
    assert world.supervisor.closure_of(id_of("a")) == "alive"
    world.gone("a", "stopped", head="closed")
    assert world.supervisor.closure_of(id_of("a")) == "closed"
    world.gone("a", "stop_uncertain", head="opened")
    assert world.supervisor.closure_of(id_of("a")) == "uncertain"


@pytest.mark.parametrize("head", ["recovery_prepared", "a_phase_a_later_build_adds"])
def test_closure_of_calls_a_dead_project_uncertain_for_a_head_that_is_not_a_finished_phase(
        world, head):
    world.gone("a", "stopped", head=head)
    assert world.supervisor.closure_of(id_of("a")) == "uncertain"


def test_closure_of_never_calls_an_unreadable_or_foreign_head_closed(world):
    world.gone("a", "stopped", head="closed")
    world.unreadable.add("a")
    assert world.supervisor.closure_of(id_of("a")) == "uncertain"
    world.unreadable.discard("a")
    world.nonces["a"] = "f" * 32
    assert world.supervisor.closure_of(id_of("a")) == "uncertain"


def test_has_live_active_is_true_for_a_live_active_process_or_a_status_file_nobody_can_read(
        world):
    assert world.supervisor.has_live_active() is False
    world.running("b", mode="view")
    assert world.supervisor.has_live_active() is False
    world.running("a", mode="active")
    assert world.supervisor.has_live_active() is True
    world.gone("a")
    assert world.supervisor.has_live_active() is False
    (world.home / "run" / f"{id_of('c')}.json").write_text("{not json", encoding="utf-8")
    assert world.supervisor.has_live_active() is True
