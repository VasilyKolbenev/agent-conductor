"""`hub-state.json`: who is active, who waits, who is still closing (spec 4.3.2, 4.3.4, 4.1.7).

The model is data and its moves are functions: each returns a new `HubState` and refuses, with
a reason the hub words, the move that would break an invariant. The file is strict to read like
the registry, never rewritten when it is not the schema, and written only by the hub that holds
`hub.lock`, under it. What is judged here, in file order: the bytes and the strict read; the
store and its lock; the moves (`begin_switch`, `settle_closed`, `enqueue`, `dequeue`,
`reorder`, `stop_active`); and the rule that a project is proven closed.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from conductor import ownership_records
from conductor.hub import instance, state
from conductor.ownership_errors import OwnerRefused

A, B, C = "a" * 32, "b" * 32, "c" * 32
NONCE = "0123456789abcdef0123456789abcdef"
T1 = "11111111-1111-4111-8111-111111111111"
T2 = "22222222-2222-4222-8222-222222222222"
F1, F2 = "f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1", "f2f2f2f2-f2f2-42f2-82f2-f2f2f2f2f2f2"
NOW = "2026-09-30T10:00:00Z"
LATER = "2026-09-30T10:05:00Z"


def entry(project_id: str = A, *, pid: int = 4812, started: str | None = "windows:1",
          nonce: str = NONCE, since: str = NOW) -> state.ClosingEntry:
    return state.ClosingEntry(project_id, pid, started, nonce, since)


def document(**changes) -> dict:
    record = {"schema_version": 1, "active_project_id": None, "queue": [], "handed_flags": {},
              "closing": [], "transition": None}
    return {**record, **changes}


def publish(folder: Path, content: object) -> Path:
    path = folder / "hub-state.json"
    path.write_bytes(content if isinstance(content, bytes)
                     else json.dumps(content).encode("utf-8"))
    return path


@pytest.fixture
def hub(tmp_path):
    live = instance.HubInstance.acquire(tmp_path)
    yield live
    live.close()


# -- the bytes and the strict read -----------------------------------------------------------


def test_a_missing_file_is_the_empty_state_and_reading_writes_nothing(tmp_path):
    assert state.load(tmp_path) == state.HubState()
    assert list(tmp_path.iterdir()) == []


def test_the_state_is_canonical_json_with_the_keys_of_the_spec_and_reads_back_whole(
        tmp_path, hub):
    store = state.HubStateStore(tmp_path, hub)
    moved = store.update(lambda s: state.begin_switch(
        state.HubState(queue=(B, C)), B, kind="queue", transition_id=T1, since=NOW,
        flag=state.Flag(F1, 3), previous=None))
    expected = document(active_project_id=B, queue=[C], handed_flags={B: F1}, transition={
        "id": T1, "project_id": B, "kind": "queue", "flag": {"flag_id": F1, "revision": 3},
        "spawned_at": None})
    assert (tmp_path / "hub-state.json").read_bytes() == ownership_records.canonical(expected)
    assert state.load(tmp_path) == moved


BAD_DOCUMENTS = {
    "an unknown key": document(extra=1),
    "a missing key": {k: v for k, v in document().items() if k != "closing"},
    "schema 2": document(schema_version=2),
    "schema true": document(schema_version=True),
    "an active id in capitals": document(active_project_id=A.upper()),
    "an active id that is a number": document(active_project_id=5),
    "a queue that is not a list": document(queue={}),
    "a queue id off the grammar": document(queue=["nope"]),
    "a queue id twice": document(queue=[A, A]),
    "handed flags that are a list": document(handed_flags=[]),
    "a handed flag for a bad project": document(handed_flags={"nope": F1}),
    "a handed flag that is empty": document(handed_flags={A: ""}),
    "closing that is not a list": document(closing={}),
    "a closing entry with another key": document(closing=[{"project_id": A}]),
    "a closing entry with a bad pid": document(closing=[
        {"project_id": A, "pid": 0, "process_started": None, "activation_nonce": NONCE,
         "since": NOW}]),
    "a closing entry with a bad nonce": document(closing=[
        {"project_id": A, "pid": 1, "process_started": None, "activation_nonce": "x",
         "since": NOW}]),
    "a closing entry with a bad time": document(closing=[
        {"project_id": A, "pid": 1, "process_started": None, "activation_nonce": NONCE,
         "since": "soon"}]),
    "a project closing twice": document(closing=[
        {"project_id": A, "pid": 1, "process_started": None, "activation_nonce": NONCE,
         "since": NOW}] * 2),
    "an active project that is also closing": document(active_project_id=A, closing=[
        {"project_id": A, "pid": 1, "process_started": None, "activation_nonce": NONCE,
         "since": NOW}]),
    "a transition for another project": document(active_project_id=A, transition={
        "id": T1, "project_id": B, "kind": "queue", "flag": None, "spawned_at": None}),
    "a transition with no active project": document(transition={
        "id": T1, "project_id": A, "kind": "queue", "flag": None, "spawned_at": None}),
    "a transition of an unknown kind": document(active_project_id=A, transition={
        "id": T1, "project_id": A, "kind": "auto", "flag": None, "spawned_at": None}),
    "a transition id that is not a uuid": document(active_project_id=A, transition={
        "id": "t1", "project_id": A, "kind": "queue", "flag": None, "spawned_at": None}),
    "a transition flag with revision 0": document(active_project_id=A, transition={
        "id": T1, "project_id": A, "kind": "queue", "flag": {"flag_id": F1, "revision": 0},
        "spawned_at": None}),
    "a transition flag with another key": document(active_project_id=A, transition={
        "id": T1, "project_id": A, "kind": "queue", "flag": {"flag_id": F1}, "spawned_at": None}),
    "a transition spawned at no time": document(active_project_id=A, transition={
        "id": T1, "project_id": A, "kind": "queue", "flag": None, "spawned_at": "soon"}),
    "a transition with an extra key": document(active_project_id=A, transition={
        "id": T1, "project_id": A, "kind": "queue", "flag": None, "spawned_at": None, "x": 1}),
    "broken JSON": b"{not json",
    "an array": b"[]",
    "a key twice": b'{"schema_version":1,"schema_version":1}',
    "NaN": b'{"schema_version":NaN}',
    "bytes that are not UTF-8": b'{"schema_version":1,"queue":["\xff"]}',
    "a file over 256 KiB": b" " * (256 * 1024 + 1),
}


@pytest.mark.parametrize("what", sorted(BAD_DOCUMENTS))
def test_a_file_that_is_not_the_schema_is_hub_state_invalid_by_name_and_never_rewritten(
        tmp_path, hub, what):
    path = publish(tmp_path, BAD_DOCUMENTS[what])
    before = path.read_bytes()
    with pytest.raises(state.HubStateError) as caught:
        state.load(tmp_path)
    assert caught.value.code == "hub_state_invalid" and "hub-state.json" in caught.value.detail
    with pytest.raises(state.HubStateError):
        state.HubStateStore(tmp_path, hub).update(lambda s: state.enqueue(s, A, F1))
    assert path.read_bytes() == before, "the owner's file was rewritten"


def test_the_grammar_accepts_a_whole_state_so_the_refusals_above_mean_something(tmp_path):
    publish(tmp_path, document(
        active_project_id=B, queue=[A, C], handed_flags={A: F1, B: F2},
        closing=[{"project_id": C, "pid": 7, "process_started": "windows:5",
                  "activation_nonce": NONCE, "since": NOW}],
        transition={"id": T1, "project_id": B, "kind": "manual", "flag": None,
                    "spawned_at": LATER}))
    loaded = state.load(tmp_path)
    assert loaded.active_project_id == B and loaded.queue == (A, C)
    assert loaded.closing == (entry(C, pid=7, started="windows:5"),)
    assert loaded.transition.spawned_at == LATER and loaded.transition.kind == "manual"


# -- the store and its lock --------------------------------------------------------------------


def test_the_store_writes_only_while_the_hub_holds_its_lock(tmp_path):
    live = instance.HubInstance.acquire(tmp_path)
    store = state.HubStateStore(tmp_path, live)
    store.update(lambda s: state.enqueue(s, A, F1))
    live.close()
    before = (tmp_path / "hub-state.json").read_bytes()
    with pytest.raises(instance.HubLockLost):
        store.update(lambda s: state.enqueue(s, B, F2))
    assert (tmp_path / "hub-state.json").read_bytes() == before


def test_an_update_that_changes_nothing_writes_nothing(tmp_path, hub):
    store = state.HubStateStore(tmp_path, hub)
    store.update(lambda s: state.enqueue(s, A, F1))
    path = tmp_path / "hub-state.json"
    stamp = path.stat().st_mtime_ns
    assert store.update(lambda s: state.enqueue(s, A, F1)).queue == (A,)
    assert path.stat().st_mtime_ns == stamp


def test_a_move_that_would_break_an_invariant_reaches_no_disk(tmp_path, hub):
    store = state.HubStateStore(tmp_path, hub)
    store.update(lambda s: state.enqueue(s, A, F1))
    before = (tmp_path / "hub-state.json").read_bytes()
    broken = state.HubState(active_project_id=A, closing=(entry(A),))
    with pytest.raises(state.HubStateError) as caught:
        store.update(lambda s: broken)
    assert caught.value.code == "hub_state_invalid"
    assert (tmp_path / "hub-state.json").read_bytes() == before


def test_a_folder_that_cannot_be_written_is_hub_state_unwritable(tmp_path):
    live = instance.HubInstance.acquire(tmp_path)
    try:
        (tmp_path / "hub-state.json").mkdir()
        with pytest.raises(state.HubStateError) as caught:
            state.HubStateStore(tmp_path, live).update(lambda s: state.enqueue(s, A, F1))
        assert caught.value.code in ("hub_state_unwritable", "hub_state_invalid")
    finally:
        live.close()


def test_two_threads_updating_one_store_lose_nothing(tmp_path, hub):
    store = state.HubStateStore(tmp_path, hub)
    ids = [f"{number:032x}" for number in range(1, 31)]
    workers = [threading.Thread(target=lambda chunk=ids[i::3]: [
        store.update(lambda s, pid=pid: state.enqueue(s, pid, F1)) for pid in chunk])
        for i in range(3)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(60)
    assert sorted(store.load().queue) == sorted(ids)


def test_an_error_code_outside_the_proposals_cannot_be_built():
    with pytest.raises(ValueError, match="hub_state_gone"):
        state.HubStateError("hub_state_gone", "no")


# -- the moves -------------------------------------------------------------------------------


def test_a_switch_makes_the_new_project_active_takes_it_off_the_queue_and_parks_the_old_one():
    before = state.HubState(active_project_id=A, queue=(B, C), handed_flags={C: F2})
    after = state.begin_switch(before, B, kind="queue", transition_id=T1, since=NOW,
                               flag=state.Flag(F1, 4), previous=entry(A))
    assert after.active_project_id == B and after.queue == (C,)
    assert after.closing == (entry(A),) and after.handed_flags == {B: F1, C: F2}
    assert after.transition == state.Transition(T1, B, "queue", state.Flag(F1, 4), None)
    assert before.active_project_id == A and before.queue == (B, C), "the old state was changed"


def test_a_switch_with_no_flag_hands_none_and_a_manual_one_is_recorded_as_manual():
    after = state.begin_switch(state.HubState(), A, kind="manual", transition_id=T1,
                               since=NOW, flag=None, previous=None)
    assert after.transition == state.Transition(T1, A, "manual", None, None)
    assert dict(after.handed_flags) == {} and after.closing == ()


def test_a_switch_to_the_project_that_is_already_active_is_refused():
    with pytest.raises(state.TransitionRefused) as caught:
        state.begin_switch(state.HubState(active_project_id=A), A, kind="manual",
                           transition_id=T1, since=NOW, flag=None, previous=entry(A))
    assert caught.value.reason == "already_active"


def test_a_switch_to_a_project_that_is_still_closing_is_active_not_closed():
    before = state.HubState(active_project_id=B, closing=(entry(A),))
    with pytest.raises(state.TransitionRefused) as caught:
        state.begin_switch(before, A, kind="manual", transition_id=T1, since=NOW, flag=None,
                           previous=entry(B, pid=9))
    assert caught.value.reason == "active_not_closed"


def test_a_switch_parks_only_the_entry_of_the_project_that_is_active_and_no_other():
    for before, previous in ((state.HubState(active_project_id=A), entry(C)),
                             (state.HubState(), entry(A))):
        with pytest.raises(ValueError, match="previous"):
            state.begin_switch(before, B, kind="manual", transition_id=T1, since=NOW,
                               flag=None, previous=previous)


def test_a_switch_from_an_active_project_with_nothing_left_to_close_parks_nobody():
    after = state.begin_switch(state.HubState(active_project_id=A), B, kind="manual",
                               transition_id=T1, since=NOW, flag=None, previous=None)
    assert after.active_project_id == B and after.closing == ()


def test_a_second_switch_while_the_first_one_still_closes_adds_to_the_closing_list():
    first = state.begin_switch(state.HubState(active_project_id=A), B, kind="manual",
                               transition_id=T1, since=NOW, flag=None, previous=entry(A))
    second = state.begin_switch(first, C, kind="manual", transition_id=T2, since=LATER,
                                flag=None, previous=entry(B, pid=9))
    assert [c.project_id for c in second.closing] == [A, B] and second.active_project_id == C
    assert second.transition.id == T2


def test_settling_the_closed_takes_them_off_the_list_and_stamps_the_spawn_in_one_state():
    parked = state.begin_switch(state.HubState(active_project_id=A), B, kind="queue",
                                transition_id=T1, since=NOW, flag=None, previous=entry(A))
    settled = state.settle_closed(parked, [A], spawned_at=LATER, transition_id=T1)
    assert settled.closing == () and settled.transition.spawned_at == LATER
    assert settled.active_project_id == B


def test_the_spawn_cannot_be_stamped_while_anything_is_still_closing():
    parked = state.begin_switch(state.HubState(active_project_id=A), B, kind="queue",
                                transition_id=T1, since=NOW, flag=None, previous=entry(A))
    with pytest.raises(state.TransitionRefused) as caught:
        state.settle_closed(parked, [], spawned_at=LATER, transition_id=T1)
    assert caught.value.reason == "active_not_closed"


def test_the_spawn_is_stamped_once_and_only_for_the_transition_that_is_pending():
    pending = state.begin_switch(state.HubState(), A, kind="manual", transition_id=T1,
                                 since=NOW, flag=None, previous=None)
    done = state.settle_closed(pending, [], spawned_at=LATER, transition_id=T1)
    with pytest.raises(ValueError, match="transition"):
        state.settle_closed(pending, [], spawned_at=LATER, transition_id=T2)
    with pytest.raises(state.TransitionRefused) as caught:
        state.settle_closed(done, [], spawned_at="2026-09-30T11:00:00Z", transition_id=T1)
    assert caught.value.reason == "already_spawned"
    assert done.transition.spawned_at == LATER


def test_settling_entries_that_are_not_in_the_list_changes_nothing():
    before = state.HubState(closing=(entry(A),))
    assert state.settle_closed(before, [B]) == before


def test_a_project_goes_to_the_end_of_the_queue_when_it_reads_a_flag_not_yet_handed():
    queued = state.enqueue(state.enqueue(state.HubState(), A, F1), B, F2)
    assert queued.queue == (A, B)
    assert state.enqueue(queued, A, F1) is queued, "a project already queued moves nowhere"


def test_a_flag_that_was_handed_to_a_transition_never_queues_the_project_again():
    handed = state.HubState(handed_flags={A: F1})
    assert state.enqueue(handed, A, F1) is handed
    assert state.enqueue(handed, A, F2).queue == (A,)


def test_dequeue_takes_a_project_off_and_an_absent_one_changes_nothing():
    queued = state.HubState(queue=(A, B, C))
    assert state.dequeue(queued, B).queue == (A, C)
    assert state.dequeue(queued, "d" * 32) is queued


def test_a_reorder_that_is_a_permutation_of_the_queue_is_taken_and_keeps_nothing_else():
    before = state.HubState(active_project_id=A, queue=(B, C), handed_flags={B: F1})
    after = state.reorder(before, [C, B])
    assert after.queue == (C, B) and after.active_project_id == A
    assert after.handed_flags == before.handed_flags


@pytest.mark.parametrize("order", [[B], [B, C, A], [B, B], [B, "d" * 32], []],
                         ids=["a project short", "a project over", "a project twice", "a stranger",
                              "nothing"])
def test_a_reorder_that_is_not_a_permutation_is_refused_project_queue_changed(order):
    with pytest.raises(state.TransitionRefused) as caught:
        state.reorder(state.HubState(queue=(B, C)), order)
    assert caught.value.reason == "project_queue_changed"


def test_a_manual_stop_hands_the_place_to_the_next_queued_project_and_not_to_itself():
    before = state.HubState(active_project_id=A, queue=(A, B, C), handed_flags={A: F1})
    after = state.stop_active(before, entry(A), transition_id=T1, since=NOW,
                              next_flag=state.Flag(F2, 2))
    assert after.active_project_id == B and after.queue == (A, C)
    assert after.closing == (entry(A),) and after.transition.kind == "queue"
    assert after.transition.flag == state.Flag(F2, 2) and after.handed_flags[B] == F2


def test_a_manual_stop_with_nobody_else_queued_leaves_no_active_project():
    before = state.HubState(active_project_id=A, queue=(A,), transition=None)
    after = state.stop_active(before, entry(A), transition_id=T1, since=NOW)
    assert after.active_project_id is None and after.transition is None
    assert after.closing == (entry(A),) and after.queue == (A,)


def test_a_stop_needs_the_entry_of_the_project_that_is_active():
    with pytest.raises(ValueError, match="active"):
        state.stop_active(state.HubState(active_project_id=A), entry(B), transition_id=T1,
                          since=NOW)
    with pytest.raises(ValueError, match="active"):
        state.stop_active(state.HubState(), entry(B), transition_id=T1, since=NOW)


# -- proven closed -----------------------------------------------------------------------------


def head(phase: str, nonce: str = NONCE) -> tuple[Path, dict]:
    return Path("/project"), {"phase": phase, "nonce": nonce}


def verdict(*, process: str = "dead", found=None, started: str | None = "windows:1",
            nonce: str = NONCE) -> state.Closure:
    """The verdict on a project whose head reads `found` (a closed head when none is given)."""
    reading = head("closed") if found is None else found

    def seen(root):
        if isinstance(reading, Exception):
            raise reading
        return reading
    return state.proven_closed(
        entry(started=started, nonce=nonce), "/project",
        probe=lambda pid, recorded: process, head_of=seen)


@pytest.mark.parametrize("phase", ["closed", "recovered", "active", "rolled_back"])
def test_a_dead_process_and_a_head_that_is_not_opened_is_proven_closed(phase):
    found = verdict(found=head(phase))
    assert found.closed is True and found.reason == "proven"


def test_a_process_that_is_alive_or_not_proven_dead_is_not_closed_whatever_the_head_says():
    assert verdict(process="alive") == state.Closure(False, "process_alive")
    assert verdict(process="unproven") == state.Closure(False, "process_unproven")


def test_a_head_that_is_opened_is_not_closed_even_when_the_process_is_dead():
    assert verdict(found=head("opened")) == state.Closure(False, "head_opened")


def test_a_head_that_cannot_be_read_says_why_and_is_not_closed():
    refused = verdict(found=OwnerRefused("recovery_required", "interrupted"))
    assert refused == state.Closure(False, "head_recovery_required")
    assert verdict(found=OSError("denied")) == state.Closure(False, "head_unreadable")


def test_a_project_with_no_ownership_head_or_another_activation_is_not_proven_closed():
    assert verdict(found=(Path("/project"), None)) == state.Closure(False, "not_activated")
    assert verdict(found=head("closed", nonce="9" * 32)) == state.Closure(False,
                                                                          "identity_changed")


def test_the_probe_is_asked_about_the_pair_the_entry_recorded():
    asked = []
    state.proven_closed(entry(pid=77, started="windows:5"), "/project",
                        probe=lambda pid, recorded: asked.append((pid, recorded)) or "dead",
                        head_of=lambda root: head("closed"))
    assert asked == [(77, "windows:5")]
