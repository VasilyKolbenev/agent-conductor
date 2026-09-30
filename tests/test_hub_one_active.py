"""One active project at a time, and the queue of the others (spec 4.3.2, 4.3.4, 4.3.6).

Spec 4.1.13 item 6 lists these tests.

The tests of 4.3.6 that the model and its store can already carry. The ones that need a
process to start or a child to stop (`test_hub_never_starts_a_second_active_child...`,
`test_hub_restart_during_a_switch_keeps_at_most_one_active`, and the rest) are in
`test_hub_supervisor.py` and in the files of the later slices, because what they judge is the
supervisor's behaviour and not the state's.
"""
from __future__ import annotations

import pytest

from conductor.hub import instance, state

A, B, C = "a" * 32, "b" * 32, "c" * 32
NONCE = "0123456789abcdef0123456789abcdef"
T1 = "11111111-1111-4111-8111-111111111111"
F1, F2 = "f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1", "f2f2f2f2-f2f2-42f2-82f2-f2f2f2f2f2f2"
NOW = "2026-09-30T10:00:00Z"


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
