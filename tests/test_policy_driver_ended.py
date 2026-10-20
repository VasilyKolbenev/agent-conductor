"""A run whose plan has ended leaves the slot, whatever stands in front of its next action.

After a run's plan completes the driver deactivates it and publishes one frame (spec 4.4.4), and
a run that has recorded its ending takes no pause and no revoke, so nobody else can free its slot.
Two things the driver asks before it reads the plan used to keep an ended run there forever: the
seed of its task (lost at the result gate, lost between a decision and the tick it wakes, or never
settled before a human closed the plan at its first gate) and an action whose result is `unknown`,
which refuses every proposal and was asked before the plan's own word. Neither holds an ended run;
on an open plan both still hold the next action, and the last two tests say so.

A real server on the flow bench (`tests/flow_driver_bench.py`), the run bound to a task. The
once-a-second tick is moved away, so every tick is one that a decision, a result or the test woke:
the slot is freed by the tick the ending woke, and by nothing that merely waited.

What the settler does with the seed of an ended run is proved apart, on its own bench (`desk` of
`tests/test_seed_driver.py`, a real repository): it answers True and moves nothing, performs no
request and asks git nothing. The run-level tests cannot say that, since the slot is freed whether
or not the settler touched the seed.
"""
from __future__ import annotations

import shutil
from threading import Event

import pytest

from conductor.command import policy_driver, seed_stage
from conductor.command.contract_values import ContractError
from conductor.command.contracts import DecisionReceipt
from conductor.command.product_names import SEED_STAGING_DIR
from conductor.command.run_terminal import RunTerminal
from conductor.command.seed_record import (
    SeedRequest, read_request, read_seed, seed_state, write_request)
from tests.git_repo_helpers import needs_git
from tests.test_command_flow_driver import DOER
from tests.test_command_materials_routes import RUN, TASK, NoGit
from tests.test_command_workflow_flow import chain, review, step
from tests.test_policy_runtime import NOW
from tests.test_seed_driver import (  # noqa: F401 -- `cycle` is a fixture
    BENCH_TASK, ITEM, LINEAR, at_result_gate, cycle, desk, empty_seed, folder_of, settle)
from tests.test_seed_move import gate_held
from tests.test_seed_routes import seed
from tests.test_server_command_http import _request

FREE = {"state": "free", "run_id": None, "reason_code": None}


@pytest.fixture(autouse=True)
def slow_tick(monkeypatch):
    """Only an explicit wake makes a tick: the once-a-second tick is moved out of the way."""
    monkeypatch.setattr(policy_driver, "TICK_SECONDS", 60)


def slot_of(run):
    """The slot the queue door reports, as the desk reads it."""
    status, payload, _ = _request(run.subject, "GET", "/command/queue")
    assert status == 200, payload
    return payload["slot"]


def frames_of(run):
    """The frames the driver publishes from now on, each with the holder at that moment."""
    policy = run.subject.command_api._policy
    frames, publish = [], policy.notify
    policy.notify = lambda run_id: (frames.append((run_id, run.holder())), publish(run_id))
    return frames


def lose_the_seed(run):
    """The task's folder goes away (a person, an editor, git); a tick the test wakes sees it."""
    shutil.rmtree(folder_of(run))
    run.subject.policy_driver.wake("run")
    assert run.until("the seed block", lambda: run.reason() == "seed_blocked") == "seed_blocked"


def freed(run, frames):
    """The ending's own tick freed the slot and then published exactly one frame."""
    run.until("the slot freed", lambda: run.holder() is None and bool(frames))
    assert frames == [("run", None)]
    assert run.automation() == ("complete", "plan_ended") and slot_of(run) == FREE


def gated(*steps):
    """A chain whose roads out of a human step open on its approval."""
    flow = chain(*steps)
    for link, source in zip(flow["links"], steps):
        if source["type"] == "human":
            link["when"] = "approved"
    return flow


class HeldTick:
    """Stands where the seed settler stands and holds the one tick the test woke, before it asks."""

    def __init__(self, seeds):
        self.seeds, self.armed, self.entered, self.go = seeds, Event(), Event(), Event()

    def settle(self, run_id):
        if self.armed.is_set():
            self.armed.clear()
            self.entered.set()
            assert self.go.wait(10), "the test never let the tick go"
        return self.seeds.settle(run_id)


def test_a_seed_lost_at_the_result_gate_does_not_keep_the_rejected_run_in_the_slot(cycle):
    run = cycle(LINEAR)
    assert empty_seed(run)[0] == 201
    run.start()
    at_result_gate(run)
    lose_the_seed(run)
    assert slot_of(run) == {"state": "stuck", "run_id": "run", "reason_code": "seed_blocked"}
    frames = frames_of(run)
    status, body = run.decide("result", "reject-result", action="reject")
    assert status == 201, body
    assert run.plan_state() == "complete" and run.terminal()
    freed(run, frames)


def test_a_seed_lost_between_the_decision_and_the_tick_it_wakes_does_not_keep_the_slot(cycle):
    run = cycle(LINEAR)
    assert empty_seed(run)[0] == 201
    run.start()
    at_result_gate(run)
    policy = run.subject.command_api._policy
    held = policy.seeds = HeldTick(policy.seeds)
    frames = frames_of(run)
    held.armed.set()
    try:
        run.subject.policy_driver.wake("run")
        assert held.entered.wait(15), "the woken tick never reached the settler"
        status, body = run.decide("result", "reject-result", action="reject")
        assert status == 201, body
        shutil.rmtree(folder_of(run))
        assert run.holder() == "run" and frames == []
    finally:  # a failure above must not leave the driver's thread held past the teardown
        held.armed.clear()
        held.go.set()
    freed(run, frames)


def test_a_seed_never_settled_does_not_keep_a_run_its_first_gate_ended(cycle):
    run = cycle(gated(step("approve", "human"), DOER, step("result", "human")))
    root, folder = run.store.project_root, folder_of(run)
    with gate_held(root):
        assert empty_seed(run)[0] == 202
    folder.mkdir(parents=True)
    (folder / "late.txt").write_bytes(b"written by something else")
    run.start()
    assert run.until("the seed block") == "seed_blocked"
    frames = frames_of(run)
    status, body = run.decide("approve", "reject-approve", action="reject")
    assert status == 201, body
    freed(run, frames)
    assert run.steps() == [] and (folder / "late.txt").read_bytes() == b"written by something else"
    # The folder holds a file the move would refuse, so this says only that the seed is still
    # staged; that the settler leaves a staged seed alone is proved on its own, below.
    assert seed_state(root, read_seed(root, BENCH_TASK)) == "staged", "the seed is still staged"


def test_an_unknown_result_does_not_keep_a_run_a_gate_correction_ended(cycle):
    run = cycle(gated(review("plan"), step("approve", "human"), review("analyst"),
                      step("result", "human")), outcomes={"analyst": ["unknown"]})
    run.start()
    run.until("the approval gate", lambda: run.reason() == "waiting")
    assert run.decide("approve", "approve-1")[0] == 201
    reason = run.until("the unknown result", lambda: run.outcomes("analyst") == ["unknown"])
    assert reason == "admission_refused" and run.plan_state() == "open"
    frames = frames_of(run)
    status, body = run.decide("approve", "reject-1", action="reject", supersedes="approve-1")
    assert status == 201, body
    assert run.plan_state() == "complete" and run.terminal()
    freed(run, frames)
    assert run.steps() == ["plan", "analyst"]


def end_the_plan(project):
    """The only gate of the desk's run rejects, the step behind it is never reached, and the
    ending is on the journal as the decision door leaves it: the decision, then `RunTerminal`."""
    digest = project.store.read(RUN).envelope.config_digest
    project.store.append(DecisionReceipt(
        receipt_id="decision-1", run_id=RUN, gate_id="gate-id", action="reject", actor="owner",
        decided_at=NOW, reason="Not this.", scope_refs=("work",), config_digest=digest))
    project.store.append(RunTerminal(
        "ended", RUN, "graph-seed", "complete", ("gate",), ("do",), NOW))


@needs_git
def test_the_settler_of_an_ended_run_answers_true_and_leaves_a_staged_seed_staged(
        tmp_path, monkeypatch):
    """The root's turn is free, so a settler that went on to the seed would move it (it does, on
    an open plan: `test_seed_driver`); for the run that has ended it answers True and does not."""
    monkeypatch.setattr(seed_stage, "MOVE_WAIT_SECONDS", 0.05)
    project = desk(tmp_path)
    with gate_held(project.root):
        assert seed(project).status == 202
    end_the_plan(project)
    record, folder = read_seed(project.root, TASK), project.root / "work" / "_tasks" / TASK / ITEM
    assert seed_state(project.root, record) == "staged"
    assert settle(project) is True
    assert seed_state(project.root, record) == "staged" and not folder.exists()
    assert (project.root / SEED_STAGING_DIR / record.staging).is_dir(), "the staged tree stands"
    assert read_seed(project.root, TASK) == record


@needs_git
def test_the_settler_of_an_ended_run_answers_true_and_performs_no_request_and_asks_git_nothing(
        tmp_path):
    """A view server left a request for a seed from HEAD; an open plan would have it made at this
    moment (`test_seed_driver`). The run has ended: no seed record, no staging, no folder, and the
    reader that fails on any use is never asked. The request stays, as history."""
    project = desk(tmp_path, reader=NoGit())
    write_request(project.root, SeedRequest(TASK, ITEM, True, NOW))
    end_the_plan(project)
    assert settle(project) is True
    assert project.reader.asked == 0
    assert read_seed(project.root, TASK) is None
    assert not (project.root / SEED_STAGING_DIR).exists()
    assert not (project.root / "work" / "_tasks").exists()
    assert read_request(project.root, TASK) is not None


def test_a_seed_lost_on_an_open_plan_still_holds_the_next_dispatch(cycle):
    """The settler is asked on every tick: a folder lost after the first action holds the next."""
    run = cycle(LINEAR)
    assert empty_seed(run)[0] == 201
    real = run.doer.execute

    def execute(prepared):
        if prepared.request.node_id == "analyst":
            shutil.rmtree(folder_of(run))
        return real(prepared)
    run.doer.execute = execute
    run.start()
    assert run.until("the seed block") == "seed_blocked"
    run.subject.policy_driver._tick("run", "grant")
    assert [row.node_id for row in run.records("action_proposal")] == ["analyst"]
    assert run.plan_state() == "open" and not run.terminal()
    assert run.holder() == "run" and run.automation() == ("stalled", "seed_blocked")
    folder_of(run).mkdir(parents=True)
    run.subject.policy_driver.wake("run")
    at_result_gate(run)
    assert run.steps() == ["analyst", "do"], "the folder back, the next tick could"


def test_an_unknown_result_on_an_open_plan_still_refuses_every_proposal(cycle):
    run = cycle(chain(review("analyst"), DOER, step("result", "human")),
                outcomes={"analyst": ["unknown"]})
    run.start()
    reason = run.until("the unknown result", lambda: run.outcomes("analyst") == ["unknown"])
    assert reason == "admission_refused" and run.plan_state() == "open"
    with pytest.raises(ContractError, match="unknown action requires human reconciliation"):
        run.subject.policy_driver._tick("run", "grant")
    assert [row.node_id for row in run.records("action_proposal")] == ["analyst"]
    assert not run.terminal()
    assert run.holder() == "run" and run.automation() == ("stalled", "admission_refused")
