"""The driver's thread runs the queue pump when its slot is free (spec 4.4.4).

"Where it works": only in a process that has a driver, in the driver's thread, when nothing is
active and nothing is in flight and nothing new is held back; a wake from a queue write or from a
run leaving the slot makes the pass happen at once. The pump itself is the queue's (`queue_pump`,
tested in `test_queue_pump.py`); here it is a recording double so the claims are the driver's own.
After a run's plan completes the driver deactivates it and publishes a frame, because without one
a desk that re-reads the queue on the result frame still sees a busy slot.
"""
from __future__ import annotations

from threading import Event
from types import SimpleNamespace

import pytest

from conductor.command import policy_driver
from tests.test_policy_driver import assert_two_steps, attach_driver, authorize, wait_terminal
from tests.test_policy_driver_slot import Gate, in_flight, let_the_step_finish
from tests.test_policy_runtime import setup


class Pump:
    """Stands where the queue stands: records every pass and can be made to fail."""

    def __init__(self):
        self.passes = 0
        self.fail = False
        self.seen = Event()

    def start_next(self):
        self.passes += 1
        self.seen.set()
        if self.fail:
            raise RuntimeError("a pump pass that fails")
        return False


@pytest.fixture
def slow_tick(monkeypatch):
    """Only an explicit wake makes a pass: the once-a-second tick is moved out of the way."""
    monkeypatch.setattr(policy_driver, "TICK_SECONDS", 60)


def wait_for_pass(pump, after):
    """Block until the pump has been asked more than `after` times."""
    for _ in range(400):
        if pump.passes > after:
            return True
        Event().wait(.02)
    return False


@pytest.fixture
def idle(tmp_path, slow_tick):
    f = setup(tmp_path, two_steps=True, checker=True)
    pump = Pump()
    f.policy.queue = pump
    driver, execution = attach_driver(f)
    try:
        yield SimpleNamespace(f=f, pump=pump, driver=driver, execution=execution)
    finally:
        driver.stop()
        execution.shutdown()


def test_a_wake_makes_the_driver_ask_the_queue_when_nothing_is_active(idle):
    before = idle.pump.passes
    idle.driver.wake_queue()
    assert wait_for_pass(idle.pump, before), "the pump was never asked"


def test_the_driver_does_not_ask_the_queue_while_a_run_is_active(tmp_path, slow_tick):
    f = setup(tmp_path, two_steps=True, checker=True)
    gate = Gate(f.adapter)
    pump = Pump()
    f.policy.queue = pump
    driver, execution = attach_driver(f)
    try:
        in_flight(SimpleNamespace(f=f, gate=gate))
        before = pump.passes
        for _ in range(3):
            driver.wake_queue()
            Event().wait(.15)
        assert pump.passes == before
    finally:
        gate.go.set()
        driver.stop()
        execution.shutdown()


def test_a_run_the_driver_holds_with_no_action_in_flight_still_keeps_the_queue_waiting(idle):
    """The slot is taken by the activation itself: a gate, a stall or a wait hold it too."""
    idle.driver.activate("run", "grant")          # held, and no action ever requested
    Event().wait(.2)                              # the activation's own tick has settled
    before = idle.pump.passes
    assert idle.driver.slot().inflight_run_id is None
    for _ in range(3):
        idle.driver.wake_queue()
        Event().wait(.15)
    assert idle.pump.passes == before


def test_a_paused_runs_action_in_flight_keeps_the_queue_from_being_asked_until_its_result(
        tmp_path, slow_tick):
    f = setup(tmp_path, two_steps=True, checker=True)
    gate = Gate(f.adapter)
    pump = Pump()
    f.policy.queue = pump
    driver, execution = attach_driver(f)
    try:
        grant = authorize(f)
        assert gate.entered.wait(8), "the first step never reached the adapter"
        f.policy.control("run", {"control_id": "pause", "authorization_id": grant.authorization_id,
            "authorization_digest": grant.authorization_digest, "action": "pause",
            "actor": "owner", "expected_control_id": None})
        assert driver.slot().active_run_id is None and driver.slot().inflight_run_id == "run"
        before = pump.passes
        for _ in range(3):
            driver.wake_queue()
            Event().wait(.15)
        assert pump.passes == before, "the queue was asked while an action was in flight"
        let_the_step_finish(SimpleNamespace(f=f, gate=gate, execution=execution))
        driver.wake_queue()
        assert wait_for_pass(pump, before), "the queue was never asked once the result was written"
    finally:
        gate.go.set()
        driver.stop()
        execution.shutdown()


def test_a_pump_that_raises_does_not_stop_the_thread(idle):
    idle.pump.fail = True
    before = idle.pump.passes
    idle.driver.wake_queue()
    assert wait_for_pass(idle.pump, before)
    again = idle.pump.passes
    idle.driver.wake_queue()
    assert wait_for_pass(idle.pump, again), "the thread stopped after a pump failure"
    assert idle.driver._thread.is_alive()


def test_a_driver_that_holds_new_work_asks_the_queue_nothing(idle):
    idle.driver.hold_new_work()
    before = idle.pump.passes
    for _ in range(3):
        idle.driver.wake_queue()
        Event().wait(.15)
    assert idle.pump.passes == before


def test_a_policy_with_no_queue_is_a_driver_that_asks_nothing(tmp_path, slow_tick):
    f = setup(tmp_path, two_steps=True, checker=True)
    assert getattr(f.policy, "queue", None) is None
    driver, execution = attach_driver(f)
    try:
        driver.wake_queue()
        Event().wait(.2)
        assert driver._thread.is_alive()
    finally:
        driver.stop()
        execution.shutdown()


def test_when_a_run_completes_the_driver_deactivates_it_and_then_publishes_one_frame(
        tmp_path, slow_tick):
    f = setup(tmp_path, two_steps=True, checker=True)
    frames = []
    driver, execution = attach_driver(f)
    f.policy.notify = lambda run_id: frames.append((run_id, driver.slot().active_run_id))
    try:
        authorize(f)
        assert_two_steps(f, wait_terminal(f))
        for _ in range(200):
            if frames and frames[-1][1] is None:
                break
            Event().wait(.02)
        assert frames.count(("run", None)) == 1, frames
        assert frames[0] == ("run", "run"), "the authorize frame was published while active"
        assert not driver.is_active("run", "grant")
    finally:
        driver.stop()
        execution.shutdown()
