"""What the hub believes after `conduct ownership recover` (spec 4.1.8, ADR-8; review ruling D-H1).

A recovery leaves ONE thing behind: the ownership head (`recovered`). The child's status file is
the dead process's last word and is never rewritten by the command, so these tests change
`world.heads` only. `world.gone()` is used for the crash, never for the recovery.
"""
from __future__ import annotations

import pytest

from conductor.hub import lifecycle as words
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
