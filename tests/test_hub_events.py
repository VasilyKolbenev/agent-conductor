"""The frames of the hub's stream and their mailboxes (spec 4.6.4), and the hub's loop.

A frame is one of six kinds, holds only identifiers of the grammar of 4.6.3 and is written as
canonical JSON after `data: `. A mailbox keeps the frames in the order they came, each once; a
client that falls too far behind is given the three plain frames that make it read everything again
rather than a queue without a bound. The hub's loop ticks its service once a second and survives a
fault of one pass, saying it once.
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from conductor.hub import events, server

A, B = "a" * 32, "b" * 32
OPERATION = "operation-" + "0" * 32


def test_a_frame_is_its_kind_and_exactly_its_own_identifiers():
    assert events.frame("projects") == {"kind": "projects"}
    assert events.frame("project", project_id=A) == {"kind": "project", "project_id": A}
    assert events.frame("operation", operation_id=OPERATION)["operation_id"] == OPERATION
    assert set(events.FRAME_KEYS) == {"projects", "project", "limits", "setup", "operation",
                                      "pick"}
    for kind, ids in (("project", {}), ("projects", {"project_id": A}), ("limits", {"x": A}),
                      ("pick", {"pick_id": A}), ("operation", {"operation_id": "operation-x"}),
                      ("project", {"project_id": 3}), ("nothing", {})):
        with pytest.raises(ValueError):
            events.frame(kind, **ids)


def test_a_frame_is_written_as_canonical_json_after_data():
    assert events.encode({"kind": "project", "project_id": A}) == (
        b'data: {"kind":"project","project_id":"' + A.encode() + b'"}\n\n')


def _kinds(box: events.Mailbox) -> list[dict]:
    return [json.loads(chunk[len(b"data: "):]) for chunk in box.drain()]


def test_a_mailbox_keeps_frames_in_order_and_a_repeated_frame_once():
    box = events.Mailbox()
    for one in ({"kind": "projects"}, {"kind": "project", "project_id": A},
                {"kind": "project", "project_id": B}, {"kind": "projects"},
                {"kind": "project", "project_id": A}, {"kind": "limits"}):
        box.publish(one)
    assert _kinds(box) == [{"kind": "projects"}, {"kind": "project", "project_id": A},
                           {"kind": "project", "project_id": B}, {"kind": "limits"}]
    assert _kinds(box) == [] and not box.wait(0.01)


def test_a_client_that_falls_far_behind_is_told_to_read_everything_and_nothing_more():
    box = events.Mailbox()
    for number in range(events.MAX_PENDING + 5):
        box.publish({"kind": "project", "project_id": f"{number:032x}"})
    got = _kinds(box)
    assert got[:3] == list(events.CATCH_UP)
    assert len(got) < events.MAX_PENDING, "the queue of a slow client is bounded"


def test_the_bus_gives_every_client_its_own_mailbox_and_forgets_one_that_left():
    bus = events.EventBus()
    first, second = bus.register(), bus.register()
    bus.publish("limits")
    bus.publish("project", project_id=A)
    both = [{"kind": "limits"}, {"kind": "project", "project_id": A}]
    assert _kinds(first) == both and _kinds(second) == both
    bus.unregister(second)
    bus.publish("setup")
    assert _kinds(first) == [{"kind": "setup"}] and _kinds(second) == []
    assert bus.clients == 1
    with pytest.raises(ValueError):
        bus.publish("run", run_id="x")


def test_a_wake_lets_a_waiter_go_without_a_frame():
    box = events.Mailbox()
    woken = []
    thread = threading.Thread(target=lambda: woken.append(box.wait(5)))
    thread.start()
    box.wake()
    thread.join(2)
    assert woken == [True] and box.drain() == ()


# -- the loop -------------------------------------------------------------------------------


class Service:
    def __init__(self, faults: int = 0) -> None:
        self.ticks = 0
        self.faults = faults

    def tick(self) -> None:
        self.ticks += 1
        if self.ticks <= self.faults:
            raise RuntimeError("the registry went away")


def test_the_loop_ticks_until_stopped_and_a_fault_of_a_pass_is_said_once_and_does_not_end_it():
    service, said = Service(faults=3), []
    loop = server.HubLoop(service, interval=0.01, report=said.append)
    loop.start()
    deadline = time.monotonic() + 5
    while service.ticks < 6 and time.monotonic() < deadline:
        time.sleep(0.01)
    loop.stop()
    loop.join(2)
    assert service.ticks >= 6 and not loop.is_alive()
    assert said == ["conduct hub: RuntimeError: the registry went away"]
