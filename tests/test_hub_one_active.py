"""One active project at a time, and the queue of the others (spec 4.3.2, 4.3.4, 4.3.6).

Spec 4.1.13 item 6 lists these tests, and 4.3.6 gives their names. The first half judges the
model and its store (`HubState`, `HubStateStore`); the second half judges the supervisor on the
world of fakes of `tests/_hub_world.py`. The tests of 4.3.6 that need what the hub reads from
its children (a run waiting for a human, a project that is free) are the ones this slice
cannot carry: there is no child client yet.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conductor.hub import instance, registry, state, supervisor
from tests._hub_world import FakeSpawner, World, id_of, iso

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


# -- a project that left the registry still counts (4.1.7, restart steps 1 and 2) ----------------


def _leave_the_registry(world: World, name: str) -> None:
    registry.remove_project(id_of(name), world.home)


def _register_again(world: World, name: str) -> None:
    registry.add_project(project_id=id_of(name), root=world.roots[name],
                         root_identity=("abc".index(name) + 1, 1), name=name, folder=world.home,
                         now=iso(world.clock.now))


@pytest.mark.parametrize("how", ["activate", "restart"])
def test_no_active_child_starts_while_an_active_process_of_an_unregistered_project_lives(
        world, how):
    world.running("b")                               # an active child that nobody's state names
    _leave_the_registry(world, "b")
    if how == "activate":
        world.supervisor.activate(id_of("a"))
    else:
        _with_a_spawned_transition(world, "a")
        world.supervisor.restart()
    for _ in range(3):
        world.supervisor.tick()
    assert world.spawner.calls == [], "a second active child was started beside a live one"
    world.gone("b")
    world.supervisor.tick()
    (call,) = world.spawner.calls
    assert call["project_id"] == id_of("a") and call["mode"] == "active"


def test_a_switch_away_from_an_active_project_that_left_the_registry_still_closes_it_first(world):
    _activate_and_start(world, "a")
    _leave_the_registry(world, "a")
    world.supervisor.activate(id_of("b"))
    assert world.spawner.children[0].closed, "the old child was not asked to drain"
    (owed,) = world.hub_state().closing
    assert (owed.project_id, owed.pid) == (id_of("a"), 101), "the closing obligation was dropped"
    for _ in range(3):
        world.supervisor.tick()
    assert world.spawner.started("b") == [], "the new child started while the old one lives"
    world.gone("a")                                  # dead and closed, but the hub cannot prove it
    world.supervisor.tick()
    assert world.spawner.started("b") == [], "a closure the hub cannot judge was taken as proven"
    assert world.supervisor.status(id_of("b")).lifecycle.state_code == "active_not_closed"
    _register_again(world, "a")                      # judged again, it is proven closed
    world.supervisor.tick()
    assert len(world.spawner.started("b")) == 1 and world.hub_state().closing == ()


def test_a_waiting_transition_whose_project_left_the_registry_is_not_consumed(world):
    world.supervisor.activate(id_of("a"), flag=FLAG)
    _leave_the_registry(world, "a")
    for _ in range(2):
        world.supervisor.tick()                      # must not raise
    assert world.spawner.calls == []
    assert world.hub_state().transition.spawned_at is None, "the transition was consumed"
    _register_again(world, "a")
    world.supervisor.tick()
    (call,) = world.spawner.calls
    assert call["transition"] == world.hub_state().transition.id
    assert call["auto_continue"] == f"{FLAG.flag_id}@{FLAG.revision}"


# -- a status file that is not the record blocks; a closing entry of an unlisted project is named --


def _corrupt_status(world: World, name: str, *, stem: str | None = None) -> Path:
    folder = world.home / "run"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stem or id_of(name)}.json"
    path.write_text("{this is not the status record", encoding="utf-8")
    return path


@pytest.mark.parametrize("how", ["activate", "restart"])
def test_a_status_file_that_is_not_the_record_blocks_a_new_active_child_and_says_why(world, how):
    broken = _corrupt_status(world, "b")              # a file nobody can read, of a project
    if how == "activate":
        world.supervisor.activate(id_of("a"))
    else:
        _with_a_spawned_transition(world, "a")
        world.supervisor.restart()
    for _ in range(3):
        world.supervisor.tick()
    assert world.spawner.calls == [], "an active child started beside a file that may be a live one"
    waiting, owner = (world.supervisor.status(id_of(name)).lifecycle for name in "ab")
    assert waiting.state_code == "status_unreadable" and owner.state_code == "status_unreadable"
    broken.unlink()                                   # the file is gone: nothing is in the way
    world.supervisor.tick()
    (call,) = world.spawner.calls
    assert call["project_id"] == id_of("a") and call["mode"] == "active"
    assert world.supervisor.status(id_of("a")).lifecycle.state_code is None


def test_a_file_under_run_that_no_child_could_have_written_does_not_block(world):
    _corrupt_status(world, "b", stem="notes")          # a child writes only <project id>.json
    _corrupt_status(world, "b", stem="B" * 32)
    world.supervisor.activate(id_of("a"))
    world.supervisor.tick()
    assert len(world.spawner.started("a")) == 1


def test_a_status_file_that_is_not_the_record_does_not_keep_a_project_from_opening_for_view(world):
    _corrupt_status(world, "b")
    world.supervisor.view(id_of("a"))                  # a view child spawns nothing itself
    (call,) = world.spawner.calls
    assert call["mode"] == "view" and call["project_id"] == id_of("a")


def test_a_stuck_closure_is_named_before_an_unreadable_file(world):
    _activate_and_start(world, "a")
    world.supervisor.activate(id_of("b"))
    world.gone("a", "stop_uncertain", head="opened")
    _corrupt_status(world, "c")
    world.supervisor.tick()
    assert world.supervisor.status(id_of("b")).lifecycle.state_code == "active_not_closed"


def _stop_and_forget(world: World, name: str = "a") -> None:
    """The active project stops (nobody queued), is gone, and the owner takes it off the list."""
    _activate_and_start(world, name)
    world.supervisor.stop(id_of(name))
    world.gone(name)
    _leave_the_registry(world, name)
    world.supervisor.tick()


def test_a_closing_entry_of_a_project_off_the_list_is_named_and_blocks_until_it_is_back(world):
    _stop_and_forget(world)
    (owed,) = world.supervisor.unlisted_closing()
    assert (owed.project_id, owed.action) == (id_of("a"), "relist")
    assert owed.since == world.hub_state().closing[0].since
    world.supervisor.activate(id_of("b"))
    for _ in range(3):
        world.supervisor.tick()
    assert world.spawner.started("b") == [] and len(world.hub_state().closing) == 1
    assert world.supervisor.status(id_of("b")).lifecycle.state_code == "active_not_closed"
    _register_again(world, "a")                        # listed again: the rule can judge it
    world.supervisor.tick()
    assert len(world.spawner.started("b")) == 1
    assert world.supervisor.unlisted_closing() == () and world.hub_state().closing == ()


def test_an_unlisted_entry_whose_head_is_opened_leaves_only_after_it_is_listed_and_recovered(world):
    _activate_and_start(world, "a")
    world.supervisor.activate(id_of("b"))
    world.gone("a", "serving", head="opened")          # the old child died in its work
    _leave_the_registry(world, "a")
    for _ in range(2):
        world.supervisor.tick()
    _register_again(world, "a")
    world.supervisor.tick()
    assert world.spawner.started("b") == [], "an opened head was taken as closed"
    assert world.supervisor.status(id_of("a")).lifecycle.state == "recovery_required"
    assert world.supervisor.unlisted_closing() == (), "listed again, so no longer unlisted"
    world.gone("a", "stopped", head="recovered")       # after "Восстановить"
    world.supervisor.tick()
    assert len(world.spawner.started("b")) == 1 and world.hub_state().closing == ()


def test_forgetting_an_active_project_that_is_not_proven_closed_leaves_its_obligation(world):
    _with_a_spawned_transition(world, "a")
    world.gone("a", "serving", head="opened")
    world.supervisor.forget(id_of("a"))
    current = world.hub_state()
    assert current.active_project_id is None and current.transition is None
    assert [entry.project_id for entry in current.closing] == [id_of("a")]
    assert registry.load(world.home).project(id_of("a")) is None
    assert [owed.project_id for owed in world.supervisor.unlisted_closing()] == [id_of("a")]


def test_forgetting_a_project_proven_closed_leaves_no_obligation_and_clears_queue_and_flags(world):
    world.supervisor.activate(id_of("b"), flag=FLAG)
    world.supervisor.tick()
    world.running("b")
    world.store.update(lambda s: state.enqueue(s, id_of("b"), F2))    # a new flag while active
    assert world.hub_state().handed_flags == {id_of("b"): F1} and world.hub_state().queue == (B,)
    with pytest.raises(supervisor.SupervisorRefused) as running:
        world.supervisor.forget(id_of("b"))
    assert running.value.code == "project_running"
    world.gone("b")                                    # stopped and closed
    world.supervisor.forget(id_of("b"))
    current = world.hub_state()
    assert (current.active_project_id, current.queue, dict(current.handed_flags),
            current.closing) == (None, (), {}, ())
    with pytest.raises(supervisor.SupervisorRefused) as unknown:
        world.supervisor.forget(id_of("b"))
    assert unknown.value.code == "project_not_found"
