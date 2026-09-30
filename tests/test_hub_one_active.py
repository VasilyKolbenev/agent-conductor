"""One active project at a time, and the queue of the others (spec 4.3.2, 4.3.4, 4.3.6).

Spec 4.1.13 item 6 lists these tests, and 4.3.6 gives their names. The first half judges the
model and its store (`HubState`, `HubStateStore`); the second half judges the supervisor on the
world of fakes of `tests/_hub_world.py`. The tests of 4.3.6 that need what the hub reads from
its children (a run waiting for a human, a project that is free) are the ones this slice
cannot carry: there is no child client yet.
"""
from __future__ import annotations

import pytest

from conductor.hub import instance, state
from tests._hub_world import FakeSpawner, World, id_of

A, B, C = "a" * 32, "b" * 32, "c" * 32
NONCE = "0123456789abcdef0123456789abcdef"
T1 = "11111111-1111-4111-8111-111111111111"
F1, F2 = "f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1", "f2f2f2f2-f2f2-42f2-82f2-f2f2f2f2f2f2"
NOW = "2026-09-30T10:00:00Z"
FLAG = state.Flag(F1, 3)


@pytest.fixture
def world(tmp_path):
    made = World(tmp_path)
    yield made
    made.close()


def parked(project_id: str = A) -> state.ClosingEntry:
    return state.ClosingEntry(project_id, 4812, "windows:1", NONCE, NOW)


@pytest.fixture
def store(tmp_path):
    live = instance.HubInstance.acquire(tmp_path)
    yield state.HubStateStore(tmp_path, live), tmp_path
    live.close()


def test_activation_takes_the_project_off_the_queue_and_the_same_flag_never_requeues_it(store):
    saved, _ = store
    saved.update(lambda s: state.enqueue(state.enqueue(s, B, F1), C, F2))
    assert saved.load().queue == (B, C)
    saved.update(lambda s: state.begin_switch(
        s, B, kind="queue", transition_id=T1, since=NOW, flag=state.Flag(F1, 1), previous=None))
    handed = saved.load()
    assert handed.queue == (C,) and handed.active_project_id == B
    assert handed.handed_flags == {B: F1}
    # The hub reads B's flag again before the child has consumed it: the same flag_id.
    assert saved.update(lambda s: state.enqueue(s, B, F1)).queue == (C,)
    # The owner sets a flag anew while B is active: a new flag_id, and B queues behind C.
    assert saved.update(lambda s: state.enqueue(s, B, F2)).queue == (C, B)


def test_a_flag_handed_to_a_child_that_died_before_consuming_it_is_not_handed_again(store):
    saved, _ = store
    saved.update(lambda s: state.begin_switch(
        s, B, kind="queue", transition_id=T1, since=NOW, flag=state.Flag(F1, 1), previous=None))
    saved.update(lambda s: state.settle_closed(s, [], spawned_at=NOW, transition_id=T1))
    after_the_death = saved.update(lambda s: state.enqueue(s, B, F1))
    assert after_the_death.queue == () and after_the_death.transition.spawned_at == NOW


def test_queue_order_that_is_not_a_permutation_of_the_queue_is_refused_and_writes_nothing(store):
    saved, folder = store
    saved.update(lambda s: state.enqueue(state.enqueue(s, B, F1), C, F2))
    path = folder / "hub-state.json"
    before = path.read_bytes()
    for order in ([B], [B, C, A], [C, C], [B, A]):
        with pytest.raises(state.TransitionRefused) as caught:
            saved.update(lambda s, order=order: state.reorder(s, order))
        assert caught.value.reason == "project_queue_changed"
        assert path.read_bytes() == before
    assert saved.update(lambda s: state.reorder(s, [C, B])).queue == (C, B)


def test_a_manual_stop_of_the_active_hands_the_place_to_the_next_queued_and_not_to_itself(store):
    saved, _ = store
    saved.update(lambda s: state.begin_switch(
        s, A, kind="manual", transition_id=T1, since=NOW, flag=None, previous=None))
    saved.update(lambda s: state.enqueue(state.enqueue(s, A, F1), B, F2))   # A set a new flag
    after = saved.update(lambda s: state.stop_active(
        s, parked(A), transition_id="22222222-2222-4222-8222-222222222222", since=NOW,
        next_flag=state.Flag(F2, 1)))
    assert after.active_project_id == B and [c.project_id for c in after.closing] == [A]
    assert after.queue == (A,), "A's new flag keeps it queued, behind nobody"
    assert saved.load() == after


def test_a_state_that_stops_the_active_and_queues_nobody_else_has_no_active_project(store):
    saved, _ = store
    saved.update(lambda s: state.begin_switch(
        s, A, kind="manual", transition_id=T1, since=NOW, flag=None, previous=None))
    after = saved.update(lambda s: state.stop_active(
        s, parked(A), transition_id="22222222-2222-4222-8222-222222222222", since=NOW))
    assert after.active_project_id is None and after.transition is None
    assert [c.project_id for c in after.closing] == [A]


# -- the tests of 4.3.6 that need the supervisor, on the world of fakes ---------------------


def _activate_and_start(world: World, name: str = "a") -> None:
    """Make `name` the active project and let the supervisor start its child; it then serves."""
    world.supervisor.activate(id_of(name))
    world.supervisor.tick()
    assert len(world.spawner.started(name)) == 1
    world.running(name)


def test_switching_active_project_drains_the_old_one_before_starting_the_new_one(world):
    _activate_and_start(world, "a")
    old = world.spawner.children[0]
    world.supervisor.activate(id_of("b"))
    assert old.closed, "the old child was not asked to drain"
    assert [entry.project_id for entry in world.hub_state().closing] == [id_of("a")]
    world.supervisor.tick()
    world.put_status("a", "stopping")
    world.supervisor.tick()
    assert world.spawner.started("b") == [], "the new child started while the old one drained"
    world.gone("a")                                  # the drain is over and the head is closed
    world.supervisor.tick()
    (started,) = world.spawner.started("b")
    assert started["mode"] == "active" and started["transition"] is not None
    assert world.hub_state().closing == () and world.hub_state().active_project_id == id_of("b")


@pytest.mark.parametrize("how", ["draining", "stop_uncertain", "died_opened"])
def test_hub_never_starts_a_second_active_child_while_the_first_is_not_proven_closed(world, how):
    _activate_and_start(world, "a")
    world.supervisor.activate(id_of("b"))
    if how == "draining":
        world.put_status("a", "stopping")
    elif how == "stop_uncertain":
        world.gone("a", "stop_uncertain", head="opened")
    else:
        world.gone("a", "serving", head="opened")
    for _ in range(3):
        world.supervisor.tick()
    assert world.spawner.started("b") == [], how
    assert [entry.project_id for entry in world.hub_state().closing] == [id_of("a")]
    if how != "draining":
        assert world.supervisor.status(id_of("b")).lifecycle.state_code == "active_not_closed"
    world.gone("a", "stopped", head="recovered")      # the person recovered it (ADR-8)
    world.supervisor.tick()
    assert len(world.spawner.started("b")) == 1 and world.hub_state().closing == ()


def _with_a_spawned_transition(world: World, name: str = "a", flag=None) -> None:
    tid = "00000000-0000-0000-0000-0000000000aa"
    world.store.update(lambda s: state.begin_switch(
        s, id_of(name), kind="manual", transition_id=tid, since=NOW, flag=flag, previous=None))
    world.store.update(lambda s: state.settle_closed(s, [], spawned_at=NOW, transition_id=tid))


def test_hub_restart_during_a_switch_keeps_at_most_one_active(world):
    _with_a_spawned_transition(world, "a")
    tid = "00000000-0000-0000-0000-0000000000bb"
    world.store.update(lambda s: state.begin_switch(
        s, id_of("b"), kind="manual", transition_id=tid, since=NOW, flag=FLAG,
        previous=state.ClosingEntry(id_of("a"), 101, "windows:1", id_of("a"), NOW)))
    world.gone("a", "serving", head="opened")         # the crash left the old child's head open
    spawner = FakeSpawner()
    newer = world.new_supervisor(spawner)
    newer.restart()
    newer.tick()
    assert world.spawner.calls == [] and spawner.calls == []
    assert [entry.project_id for entry in world.hub_state().closing] == [id_of("a")]
    assert newer.status(id_of("a")).lifecycle.state == "recovery_required"
    assert newer.status(id_of("b")).lifecycle.state_code == "active_not_closed"
    world.gone("a", "stopped", head="recovered")      # after "Восстановить"
    newer.tick()
    (call,) = spawner.calls
    assert call["project_id"] == id_of("b") and call["transition"] == tid
    assert call["auto_continue"] == f"{FLAG.flag_id}@{FLAG.revision}"
    assert world.hub_state().closing == ()


def test_a_transition_is_spawned_once_and_a_hub_restart_never_hands_the_flag_again(world):
    world.supervisor.activate(id_of("a"), flag=FLAG)
    world.supervisor.tick()
    (first,) = world.spawner.calls
    assert first["auto_continue"] == f"{FLAG.flag_id}@{FLAG.revision}"
    world.spawner.children[0].leave(1)               # the child died before it consumed the flag
    world.gone("a", "serving", head="closed")
    for _ in range(3):
        world.supervisor.tick()
    assert len(world.spawner.calls) == 1, "a dead child is not started again by the hub's loop"
    newer_spawner = FakeSpawner()
    newer = world.new_supervisor(newer_spawner)
    newer.restart()
    (again,) = newer_spawner.calls
    assert (again["transition"], again["auto_continue"]) == (None, None)
    assert world.hub_state().queue == () and world.hub_state().transition.spawned_at is not None


# -- the start that does not come to serving ------------------------------------------------------


def test_manual_stop_of_the_active_starts_the_next_queued_project_and_not_itself(world):
    _activate_and_start(world, "a")
    world.store.update(lambda s: state.enqueue(s, id_of("a"), F2))    # A's new flag: A queues
    world.store.update(lambda s: state.enqueue(s, id_of("c"), F1))
    world.supervisor.stop(id_of("a"), next_flag=FLAG)
    assert world.spawner.children[0].closed
    assert world.hub_state().active_project_id == id_of("c")
    assert world.hub_state().queue == (id_of("a"),), "A's new flag keeps it queued, behind nobody"
    world.supervisor.tick()
    assert world.spawner.started("c") == [] and len(world.spawner.started("a")) == 1
    world.gone("a")
    world.supervisor.tick()
    (started,) = world.spawner.started("c")
    assert started["auto_continue"] == f"{FLAG.flag_id}@{FLAG.revision}"
    assert len(world.spawner.started("a")) == 1, "the project just stopped was started again"
