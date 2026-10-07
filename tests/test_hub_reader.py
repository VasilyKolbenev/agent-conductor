"""The reading loop over the running children (spec 4.1.9, 4.5.6, 4.3.4).

The reads themselves are `test_hub_child_client`'s; here the reader is given a child that answers
what a test tells it, on the world of fakes of `tests/_hub_world.py`, and is judged on WHEN it reads
(at once for a new process, a second after a signal, every 30 s), on what a pass causes (a snapshot
only from a complete one, `limits.json` only from the active project, the queue of projects from the
flags read, a frame for the page) and on what it forgets when a child is gone.
"""
from __future__ import annotations

import json
import threading

import pytest

from conductor.hub import child_client, events, reader, snapshots, state, summary
from tests._hub_fake_child import HUB_ORIGIN, run_row, task_row
from tests._hub_stack import A, B, C, Mono
from tests._hub_world import World

F1 = "f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1"
F2 = "f2f2f2f2-f2f2-42f2-82f2-f2f2f2f2f2f2"
PORTS = {"a": 7701, "b": 7702, "c": 7703}


def _cycle(task: str = "task-1", *, failures=(), verdict="live", flag=None, quotas=None,
           queue=None, human: str = "not_required", mode: str = "active") -> child_client.Cycle:
    read = child_client.TaskRead(task_row(task, "Fix"), run_row(f"run-{task}", task,
                                                                  human_state=human), None)
    project = {"project_id": A, "hub_origin": HUB_ORIGIN, "demo": False, "mode": mode}
    return child_client.Cycle(verdict, project, (read,), queue, flag, quotas, tuple(failures))


def _flag(flag_id: str = F1, *, enabled: bool = True, consumed=None, set_at: str = "t") -> dict:
    return {"schema_version": 2, "flag_id": flag_id, "revision": 1, "enabled": enabled,
            "consumed": consumed, "set_at": set_at}


class Fakes:
    """What the reader reads with: a child that answers from a script, and streams as notes."""

    def __init__(self) -> None:
        self.answers: dict[str, child_client.Cycle] = {}
        self.calls: list[dict] = []
        self.streams: list[tuple[int, str]] = []
        self.signals: dict[str, object] = {}
        self.stopped: list[threading.Event] = []

    def read(self, client, *, hub_origin, mode, previous):
        port, project_id = client
        self.calls.append({"port": port, "project": project_id, "origin": hub_origin,
                           "mode": mode, "previous": previous})
        return self.answers.get(project_id) or _cycle()

    def follow(self, port, project_id, on_signal):
        self.streams.append((port, project_id))
        self.signals[project_id] = on_signal
        outer = self

        class Stream:
            def follow(self, stop: threading.Event) -> None:
                outer.stopped.append(stop)
                stop.wait(5)

        return Stream()


class Rig:
    def __init__(self, tmp_path, *, streams: bool = False) -> None:
        self.world = World(tmp_path)
        self.fakes = Fakes()
        self.mono = Mono()
        self.bus = events.EventBus()
        self.box = self.bus.register()
        self.snapshots = snapshots.SnapshotStore(self.world.home, clock=self.mono)
        self.ledger = summary.ObservedLedger()
        self.reader = reader.ChildReader(
            self.world.home, self.world.supervisor, self.world.store, self.snapshots, self.ledger,
            self.bus, hub_origin=HUB_ORIGIN, now=self.world.clock, monotonic=self.mono,
            follow=self.fakes.follow if streams else None, read=self.fakes.read,
            client=lambda port, project_id: (port, project_id))

    def run(self, name: str, *, mode: str = "active", started: str = "windows:1") -> None:
        self.world.alive.add({"a": 101, "b": 202, "c": 303}[name])
        self.world.put_status(name, "serving", mode=mode, port=PORTS[name], started=started)

    def frames(self) -> list[dict]:
        return [json.loads(chunk[len(b"data: "):]) for chunk in self.box.drain()]

    def close(self) -> None:
        self.reader.close()
        self.world.close()


@pytest.fixture
def rig(tmp_path):
    made = Rig(tmp_path)
    yield made
    made.close()


def test_a_child_that_runs_is_read_at_once_with_its_mode_and_the_hubs_origin(rig):
    rig.run("a")
    rig.run("b", mode="view")
    rig.reader.step()
    got = {call["project"]: call for call in rig.fakes.calls}
    assert set(got) == {A, B} and C not in got, "only the running children are read"
    assert (got[A]["port"], got[A]["mode"], got[A]["origin"]) == (7701, "active", HUB_ORIGIN)
    assert got[B]["mode"] == "view"
    assert rig.reader.live(A).cycle.verdict == "live" and rig.reader.live(C) is None


def test_a_running_child_is_not_read_again_before_thirty_seconds_and_is_then(rig):
    rig.run("a")
    rig.reader.step()
    for seconds in (5, 10, 14.9):
        rig.mono.advance(seconds)
        rig.reader.step()
    assert len(rig.fakes.calls) == 1
    rig.mono.advance(0.2)                       # 30.1 s after the read
    rig.reader.step()
    assert len(rig.fakes.calls) == 2


def test_a_signal_makes_the_next_read_a_second_later_and_a_second_signal_does_not_push_it_out(rig):
    rig.run("a")
    rig.reader.step()
    rig.reader.mark(A)
    rig.mono.advance(0.5)
    rig.reader.mark(A)
    rig.reader.step()
    assert len(rig.fakes.calls) == 1, "before the second is up"
    rig.mono.advance(0.5)
    rig.reader.step()
    assert len(rig.fakes.calls) == 2
    rig.mono.advance(0.3)
    rig.reader.step()
    assert len(rig.fakes.calls) == 2, "the signal was spent by that read"


def test_a_new_process_of_a_project_is_read_at_once_and_the_last_pass_is_handed_to_the_read(rig):
    rig.run("a")
    rig.reader.step()
    rig.run("a", started="windows:2")           # the child restarted: a new instance
    rig.reader.step()
    assert len(rig.fakes.calls) == 2
    assert rig.fakes.calls[1]["previous"] == rig.reader.live(A).cycle.memory


def test_a_project_whose_child_is_gone_loses_its_live_data_but_keeps_its_snapshot(rig):
    rig.run("a")
    rig.reader.step()
    assert rig.snapshots.get(A) is not None and rig.reader.live(A) is not None
    rig.frames()
    rig.world.gone("a")
    rig.reader.step()
    assert rig.reader.live(A) is None and rig.snapshots.get(A) is not None
    assert {"kind": "project", "project_id": A} in rig.frames()


def test_every_pass_tells_the_page_with_a_frame_of_the_project_and_only_its_identifier(rig):
    rig.run("a")
    rig.frames()
    rig.reader.step()
    assert rig.frames() == [{"kind": "project", "project_id": A}]


# -- what a pass causes ---------------------------------------------------------------------------


def test_a_snapshot_is_written_from_a_complete_pass_and_from_no_other(rig):
    rig.run("a")
    rig.fakes.answers[A] = _cycle(failures=("quotas",))
    rig.reader.step()
    assert rig.snapshots.get(A) is None, "a pass with a failed read became a snapshot"
    rig.fakes.answers[A] = _cycle(verdict="unreadable", failures=("tasks",))
    rig.mono.advance(31)
    rig.reader.step()
    assert rig.snapshots.get(A) is None
    rig.fakes.answers[A] = _cycle()
    rig.mono.advance(31)
    rig.reader.step()
    got = rig.snapshots.get(A)
    assert got is not None and got.tasks[0]["task"]["task_id"] == "task-1"


def test_limits_json_is_written_only_from_the_quotas_of_the_active_project(rig):
    quotas = {"as_of": "2026-09-30T10:00:00Z", "max_age_seconds": 300, "providers": [],
              "snapshots": []}
    rig.world.store.update(lambda s: state.begin_switch(
        s, A, kind="manual", transition_id="00000000-0000-0000-0000-0000000000aa",
        since="2026-09-30T10:00:00Z", flag=None, previous=None))
    rig.run("a")
    rig.run("b", mode="view")
    rig.fakes.answers[B] = _cycle(quotas={**quotas, "as_of": "2026-09-30T09:00:00Z"})
    rig.reader.step()
    assert rig.snapshots.get_limits() is None, "a view project's quotas are not the limits"
    rig.fakes.answers[A] = _cycle(quotas=quotas)
    rig.mono.advance(31)
    rig.frames()
    rig.reader.step()
    stored = rig.snapshots.get_limits()
    assert stored is not None and stored.project_id == A and stored.quotas["as_of"] == quotas[
        "as_of"]
    assert {"kind": "limits"} in rig.frames()


QUOTAS = {"as_of": "2026-09-30T10:00:00Z", "max_age_seconds": 300, "providers": [], "snapshots": []}


def _b_became_active_over_a_good_limits_file_of_a(rig) -> bytes:
    """A's `limits.json` stands; B was open for viewing and has just been made the active one."""
    assert rig.snapshots.put_limits(A, taken_at="2026-09-30T09:00:00Z", quotas=QUOTAS) == "written"
    rig.world.store.update(lambda s: state.begin_switch(
        s, B, kind="manual", transition_id="00000000-0000-0000-0000-0000000000cc",
        since="2026-09-30T10:00:00Z", flag=None, previous=None))
    rig.run("b", mode="view")                   # its view child serves until it drains
    rig.mono.advance(31)                        # the rule of one write in 5 s no longer holds it
    rig.frames()
    return (rig.world.home / "limits.json").read_bytes()


def test_the_view_child_of_the_project_that_just_became_active_writes_no_limits(rig):
    before = _b_became_active_over_a_good_limits_file_of_a(rig)
    echo = {**QUOTAS, "hub_snapshot": {"project_id": A, "taken_at": "2026-09-30T09:00:00Z"}}
    rig.fakes.answers[B] = _cycle(quotas=echo, mode="view")
    rig.reader.step()
    assert rig.reader.live(B).cycle.verdict == "live", "the view child is read as any child is"
    stored = rig.snapshots.get_limits()
    assert stored is not None, "the echo made limits.json unreadable to every view desk"
    assert stored.project_id == A and (rig.world.home / "limits.json").read_bytes() == before
    assert {"kind": "limits"} not in rig.frames()


def test_the_mode_alone_keeps_a_view_childs_quotas_out_of_limits_json(rig):
    before = _b_became_active_over_a_good_limits_file_of_a(rig)
    rig.fakes.answers[B] = _cycle(quotas={**QUOTAS, "as_of": "2026-09-30T09:59:00Z"}, mode="view")
    rig.reader.step()
    assert (rig.world.home / "limits.json").read_bytes() == before
    rig.run("b", mode="active", started="windows:2")     # drained and started again as the active
    rig.fakes.answers[B] = _cycle(quotas={**QUOTAS, "as_of": "2026-09-30T09:59:00Z"})
    rig.reader.step()
    stored = rig.snapshots.get_limits()
    assert stored is not None and (stored.project_id, stored.quotas["as_of"]) == (
        B, "2026-09-30T09:59:00Z"), "the same project, now running as the active one, is the limits"


def test_a_project_that_read_a_standing_flag_joins_the_queue_and_leaves_it_when_the_flag_is_down(
        rig):
    rig.run("a")
    rig.run("b", mode="view")
    rig.fakes.answers[B] = _cycle(flag=_flag(F1, set_at="2026-09-30T10:02:00Z"))
    rig.fakes.answers[A] = _cycle(flag=_flag(F2, set_at="2026-09-30T10:01:00Z"))
    rig.reader.step()
    assert rig.world.hub_state().queue == (A, B), "the flags are queued in the order they were set"
    rig.fakes.answers[B] = _cycle(flag=_flag(F1, enabled=False))
    rig.mono.advance(31)
    rig.reader.step()
    assert rig.world.hub_state().queue == (A,)
    rig.fakes.answers[A] = _cycle(flag=_flag(F2, consumed={"at": "t", "transition_id": "x",
                                                            "activation_nonce": "n"}))
    rig.mono.advance(31)
    rig.reader.step()
    assert rig.world.hub_state().queue == ()


def test_a_flag_that_was_handed_to_a_transition_does_not_queue_its_project_again(rig):
    rig.world.store.update(lambda s: state.begin_switch(
        s, B, kind="manual", transition_id="00000000-0000-0000-0000-0000000000bb",
        since="2026-09-30T10:00:00Z", flag=state.Flag(F1, 1), previous=None))
    rig.run("b")
    rig.fakes.answers[B] = _cycle(flag=_flag(F1))
    rig.reader.step()
    assert rig.world.hub_state().queue == ()
    rig.fakes.answers[B] = _cycle(flag=_flag(F2))          # a new flag: it queues behind
    rig.mono.advance(31)
    rig.reader.step()
    assert rig.world.hub_state().queue == (B,)


def test_a_flag_that_could_not_be_read_changes_the_queue_neither_way(rig):
    rig.world.store.update(lambda s: state.enqueue(s, B, F1))
    rig.run("b", mode="view")
    rig.fakes.answers[B] = _cycle(flag=None, failures=("auto_continue",))
    rig.reader.step()
    assert rig.world.hub_state().queue == (B,)
    rig.fakes.answers[B] = _cycle(flag=None)               # read, and there is none
    rig.mono.advance(31)
    rig.reader.step()
    assert rig.world.hub_state().queue == ()


def test_a_child_that_is_another_project_writes_nothing_and_shows_its_verdict(rig):
    rig.run("a")
    rig.fakes.answers[A] = child_client.Cycle("identity_mismatch")
    rig.reader.step()
    assert rig.snapshots.get(A) is None and rig.world.hub_state().queue == ()
    assert rig.reader.live(A).cycle.verdict == "identity_mismatch"


def test_a_registry_that_cannot_be_read_stops_the_pass_without_a_crash(rig):
    rig.run("a")
    (rig.world.home / "registry.json").write_text("{not json", encoding="utf-8")
    rig.reader.step()
    assert rig.fakes.calls == []


def test_the_ledger_of_first_seen_moments_is_kept_across_passes_of_one_child(rig):
    rig.run("a")
    detail = {"graph": {"situation": {"checked": [
        {"reason": "confirmation", "count": 1, "sources": ["p1"]}], "gates": []},
        "runtime": None}, "records": []}
    read = child_client.TaskRead(task_row("task-1", "Fix"), run_row("run-1", "task-1",
                                                                    human_state="required"),
                                 None, detail)
    rig.fakes.answers[A] = child_client.Cycle("live", {"project_id": A}, (read,))
    rig.reader.step()
    first = rig.reader.live(A).rows[0]["attention"]["observed_at"]
    rig.world.clock.advance(300)
    rig.mono.advance(31)
    rig.reader.step()
    assert rig.reader.live(A).rows[0]["attention"]["observed_at"] == first


# -- the streams ---------------------------------------------------------------------------


@pytest.fixture
def streaming(tmp_path):
    made = Rig(tmp_path, streams=True)
    yield made
    made.close()


def test_one_stream_is_kept_for_each_running_child_and_replaced_when_the_process_is(streaming):
    rig = streaming
    rig.run("a")
    rig.reader.step()
    rig.reader.step()
    assert rig.fakes.streams == [(7701, A)], "one stream for one process"
    first_stop = rig.fakes.stopped
    rig.run("a", started="windows:2")
    rig.reader.step()
    assert rig.fakes.streams == [(7701, A), (7701, A)]
    deadline = 50
    while not first_stop and deadline:
        threading.Event().wait(0.05)
        deadline -= 1
    assert first_stop and first_stop[0].is_set(), "the old process's stream was not stopped"


def test_a_signal_of_a_stream_is_a_mark_of_its_project(streaming):
    rig = streaming
    rig.run("a")
    rig.reader.step()
    rig.fakes.signals[A]()
    rig.mono.advance(1.1)
    rig.reader.step()
    assert len(rig.fakes.calls) == 2


def test_a_stream_ends_when_its_child_is_gone(streaming):
    rig = streaming
    rig.run("a")
    rig.reader.step()
    threading.Event().wait(0.2)
    rig.world.gone("a")
    rig.reader.step()
    threading.Event().wait(0.2)
    assert all(stop.is_set() for stop in rig.fakes.stopped) and rig.fakes.stopped
