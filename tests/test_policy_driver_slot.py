"""The drain gate and the slot snapshot that the drain and the queue are written against.

Real driver, real store, the two-step independent-check run of test_policy_driver. A Gate holds the
doer's execute open, so a step stays in flight for exactly as long as a test needs it to.
"""
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from conductor.command import policy_driver
from conductor.command.contract_values import ContractError
from tests.test_policy_driver import ask, attach_driver, authorize
from tests.test_policy_runtime import setup


class Gate:
    """Keeps the doer's execute open until the test lets it go."""

    def __init__(self, adapter):
        self.entered, self.go = Event(), Event()
        original = adapter.execute

        def execute(prepared):
            self.entered.set()
            assert self.go.wait(8), "the test never opened the gate"
            return original(prepared)
        adapter.execute = execute


@pytest.fixture
def run(tmp_path):
    f = setup(tmp_path, two_steps=True, checker=True)
    gate = Gate(f.adapter)
    driver, execution = attach_driver(f)
    try:
        yield SimpleNamespace(f=f, gate=gate, driver=driver, execution=execution)
    finally:
        gate.go.set()
        driver.stop()
        execution.shutdown()


def journal(f):
    """Every file of the run as bytes: a write of any kind changes this."""
    root = f.store.run_path("run")
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


def records(f, kind):
    return [row.value for row in f.store.read("run").records if row.kind == kind]


def in_flight(run):
    """Grant the run and wait until its first step sits inside the adapter."""
    authorize(run.f)
    assert run.gate.entered.wait(8), "the first step never reached the adapter"


def let_the_step_finish(run):
    run.gate.go.set()
    assert run.execution.wait_idle(8), "the first step never settled"


def test_hold_new_work_stops_the_next_proposal_and_writes_nothing_to_the_journal(run):
    in_flight(run)
    before = journal(run.f)
    run.driver.hold_new_work()
    assert journal(run.f) == before, "holding new work must not touch the run"
    let_the_step_finish(run)
    quiet = journal(run.f)
    for _ in range(3):
        run.driver.wake("run")
        run.driver._tick("run", "grant")
    assert journal(run.f) == quiet
    assert [row.node_id for row in records(run.f, "action_proposal")] == ["do"]


def test_hold_new_work_refuses_a_new_activation(run):
    preview = run.f.policy.preview("run", ask())
    run.driver.hold_activation("run")  # free until the hold is set
    before = journal(run.f)
    run.driver.hold_new_work()
    for run_id in ("other", "run"):
        with pytest.raises(policy_driver.NewWorkHeld) as refused:
            run.driver.hold_activation(run_id)
        assert isinstance(refused.value, ContractError)
    with pytest.raises(policy_driver.NewWorkHeld):
        run.f.policy.authorize("run", {"authorization_id": "grant",
            "preview_digest": preview["preview_digest"], "authorized_by": "owner",
            "terms": preview["terms"], "supersedes": None})
    assert journal(run.f) == before
    assert not run.driver.is_active("run", "grant")


def test_an_action_already_in_flight_still_settles_while_new_work_is_held(run):
    in_flight(run)
    run.driver.hold_new_work()
    let_the_step_finish(run)
    run.driver._tick("run", "grant")
    assert [row.node_id for row in records(run.f, "action_request")] == ["do"]
    assert [row.outcome for row in records(run.f, "action_result")] == ["succeeded"]
    assert run.f.adapter.execute_calls == 1
    assert run.driver._inflight is None
    assert not records(run.f, "run_terminal")


def test_hold_new_work_returns_only_after_a_tick_past_the_gate_has_admitted_its_action(run):
    entered, go = Event(), Event()
    original = run.driver._proposal

    def proposal(*args):
        entered.set()
        assert go.wait(8), "the test never released the tick"
        return original(*args)
    run.driver._proposal = proposal
    seen = {}

    def hold():
        run.driver.hold_new_work()
        seen["returned"] = True
        seen["requests"] = [row.node_id for row in records(run.f, "action_request")]
        seen["inflight"] = run.driver._inflight

    holder = Thread(target=hold)
    try:
        authorize(run.f)
        assert entered.wait(8), "no tick reached its proposal"
        holder.start()
        holder.join(.3)
        assert "returned" not in seen, "hold_new_work returned while a tick was still admitting its action"
    finally:
        go.set()  # never leave the tick parked: the fixture stops the driver next
    holder.join(8)
    assert not holder.is_alive()
    assert seen["requests"] == ["do"] and seen["inflight"] is not None
