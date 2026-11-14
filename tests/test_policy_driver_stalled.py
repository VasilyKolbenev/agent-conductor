"""A run whose plan ENDS `stalled` leaves the slot as a completed one does, and reads as ended.

A plan ends on one of two words (`run_terminal.TERMINAL_STATES`): `complete`, or `stalled` when
what is still owed is owed for good (a step whose one attempt answered `unknown`, a halt that
stopped a branch which could still run). Either way the run records its ending, and from then on
its journal takes no pause, revoke or resume. The driver freed the slot on `complete` alone, so a
`stalled` run held it forever: the queue stood, another run was refused `slot_busy`, the desk
offered to free the slot by a pause the door refused, and the Studio offered a resume.

Now the tick the ending wakes frees the slot and only then publishes one frame (spec 4.4.4). Until
it does, the run reads ended and its slot busy with `plan_ended`, the row a completed run takes
(spec 4.4.6). Nothing is written: the doors still refuse every control, and the ending stands as
recorded. The last test hands the server's own reads to the desk's modules and the hub's rules.

A real server on the flow bench (`tests/flow_driver_bench.py`). The once-a-second tick is moved
away, so a tick comes only of a wake: the activation, or a record of the attempt (its events
wake the driver as its result does). A tick may therefore begin before the run has ended, and
`HeldTick` holds the first one that finds the ending, not the first one that runs.
"""
from __future__ import annotations

import time
from threading import Event

import pytest

from conductor.command import policy_driver
from conductor.hub import summary
from tests.desk_node import run_js
from tests.test_command_flow_driver import DOER, cycle, slot_of  # noqa: F401 -- a fixture
from tests.test_command_workflow_flow import chain, review, step
from tests.test_server_command_http import _request

FREE = {"state": "free", "run_id": None, "reason_code": None}
DESK = {"queue": "desk-queue-model.js", "status": "desk-status.js", "flag": "desk-flag-model.js"}


@pytest.fixture(autouse=True)
def slow_tick(monkeypatch):
    """Only an explicit wake makes a tick: the once-a-second tick is moved out of the way."""
    monkeypatch.setattr(policy_driver, "TICK_SECONDS", 60)


def once(node):
    """`node`, which may be tried once: an `unknown` answer then leaves it owed for good."""
    return {**node, "ext": {**node["ext"], "attempt_bound": 1}}


def spent():
    """The analyst may answer once and answers `unknown`: the plan ends `stalled` there."""
    return chain(once(review("analyst")), DOER, step("result", "human"))


def halted():
    """`plan` opens two branches; `left` halts the run when it fails, while `right` could run."""
    left = review("left", role_id="role-reviewer")
    left = {**left, "ext": {**left["ext"], "failure_policy": "halt_run"}}
    return {"flow_version": 1, "title": "Halt", "ext": {}, "links": [
        {"from": "plan", "to": "left", "when": "success"},
        {"from": "plan", "to": "right", "when": "success"},
        {"from": "left", "to": "join", "when": "success"},
        {"from": "right", "to": "join", "when": "success"},
        {"from": "join", "to": "result", "when": "success"}],
        "steps": [review("plan"), left, review("right", role_id="role-designer"),
                  step("join", "agent", verifier_role_id="role-checker"),
                  step("result", "human")]}


def frames_of(run):
    """The frames the driver publishes from now on, each with the holder at that moment."""
    policy = run.subject.command_api._policy
    frames, publish = [], policy.notify
    policy.notify = lambda run_id: (frames.append((run_id, run.holder())), publish(run_id))
    return frames


def read(run, path):
    status, payload, _ = _request(run.subject, "GET", path)
    assert status == 200, payload
    return payload


def control(run, action):
    """A person's control of the run's grant, written as the Studio and the desk write it."""
    view = read(run, "/command/runs/run/automation")
    return run.post("/command/runs/run/automation/control", {
        "control_id": f"{action}-1", "authorization_id": "grant", "action": action,
        "authorization_digest": view["authorization"]["authorization_digest"], "actor": "owner",
        "expected_control_id": (view["control"] or {}).get("control_id")})


def journal(run):
    return [(row.kind, row.value.as_dict()) for row in run.store.read("run").records]


class HeldTick:
    """Stands where the seed settler stands and holds the first tick that finds the run ended.

    A tick that begins while the action is still owed waits here for its answer: the ending is
    recorded by the thread that ran the action, so a tick that began before it and read the plan
    after it would free the slot without ever being held. `seen` counts every tick that found
    the ending, held or not; the driver is one thread, so each of them went on to read the plan
    once it was let go.
    """

    def __init__(self, seeds, store):
        self.seeds, self.store = seeds, store
        self.entered, self.go = Event(), Event()
        self.seen = 0

    def rows(self, run_id, kind):
        return [row.value for row in self.store.read(run_id).records if row.kind == kind]

    def owed(self, run_id):
        answered = {row.action_id for row in self.rows(run_id, "action_result")}
        return any(row.action_id not in answered for row in self.rows(run_id, "action_request"))

    def settle(self, run_id):
        deadline = time.monotonic() + 10
        while self.owed(run_id) and time.monotonic() < deadline:
            time.sleep(0.005)
        if self.rows(run_id, "run_terminal"):
            self.seen += 1
            self.entered.set()
            assert self.go.wait(10), "the test never let the tick go"
        return self.seeds.settle(run_id)


def test_a_spent_step_ends_the_plan_stalled_and_its_tick_frees_the_slot_then_one_frame(cycle):
    run = cycle(spent(), outcomes={"analyst": ["unknown"]})
    policy = run.subject.command_api._policy
    held = policy.seeds = HeldTick(policy.seeds, run.store)
    try:
        run.start()
        assert held.entered.wait(15), "the ending never woke the driver"
        frames = frames_of(run)
        assert run.plan_state() == "stalled"
        assert [row.state for row in run.terminal()] == ["stalled"]
        assert run.holder() == "run"
        assert run.automation() == ("complete", "plan_ended")
        assert slot_of(run) == {"state": "busy", "run_id": "run", "reason_code": "plan_ended"}
    finally:  # a failure above must not leave the driver's thread held past the teardown
        held.go.set()
    run.until("the frame after the slot is freed", lambda: frames == [("run", None)])
    assert held.seen == 1, f"{held.seen} ticks found the ending: the one it woke frees the slot"
    assert run.automation() == ("complete", "plan_ended") and slot_of(run) == FREE
    assert run.steps() == ["analyst"]


def test_a_halt_ends_the_plan_stalled_frees_the_slot_and_every_control_is_still_refused(cycle):
    run = cycle(halted(), outcomes={"left": ["failed"]})
    run.start()
    run.until("the slot freed", lambda: run.plan_state() == "stalled" and run.holder() is None)
    assert [row.state for row in run.terminal()] == ["stalled"]
    assert run.steps() == ["plan", "left"], "the halt stopped `right`, which could still run"
    assert run.automation() == ("complete", "plan_ended") and slot_of(run) == FREE
    before = journal(run)
    for action in ("pause", "revoke", "resume"):
        status, body = control(run, action)
        assert status == 422, (action, body)
    assert journal(run) == before, "nothing was written: the ending stands as recorded"
    run.subject.policy_driver.hold_activation("another-run")  # the slot takes the next run


def test_the_desk_and_the_hub_read_an_ended_run_as_over_and_offer_nothing_it_refuses(cycle):
    """The server's own reads, handed to the desk's modules (in node) and to the hub's rules."""
    run = cycle(spent(), outcomes={"analyst": ["unknown"]})
    run.start()
    run.until("the slot freed", lambda: run.plan_state() == "stalled" and run.holder() is None)
    reads = {"queue": read(run, "/command/queue"),
             "automation": read(run, "/command/runs/run/automation"),
             "run": next(row for row in read(run, "/command/runs")["runs"]
                         if row["run_id"] == "run")}
    said = run_js("""
      const task = {task_id: "task", title: "Task"};
      const tasks = [{task, run: d.run, automation: d.automation}];
      const read = queue.projectQueue(d.queue);
      console.log(JSON.stringify({slot: read?.slot ?? null,
        release: queue.releaseOffer(read, {mode: "active", actor: "owner"}),
        waiting: status.attentionItems({project_id: "p", mode: "active", tasks,
          task_queue: d.queue, observed_at: "2026-10-20T00:00:00Z"}).map((one) => one.reason),
        word: status.taskStatus({task, run: d.run, automation: d.automation}).key,
        flag: flag.resumableRuns({tasks: {list: [task]}, runs: {phase: "ready", list: [d.run]},
          automation: new Map([["task", d.automation]])}).length}));
    """, DESK, reads)
    assert said == {"slot": FREE, "release": None, "waiting": [], "word": "outcome_unknown",
                    "flag": 0}
    assert reads["automation"]["state"] not in summary.HOLDING, "the hub reads the project free"
    assert summary._resume_run([{"run": reads["run"], "automation": reads["automation"]}]) is None
