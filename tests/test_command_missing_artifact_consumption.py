"""What `block` changes about what may run, and what `fail` still does not.

The other half of `test_command_missing_artifact_policy`, split when that module
crossed the line cap and along the seam the two stop-points already drew: that
one is the FIELD -- its vocabulary, its grammar, both contracts' pairing rules,
the shipped bytes it must not move, and the one authority on which argument key
names a step's inputs. This one is what the field is SPENT on.

Three readers spend it and each is witnessed here:

- the SCHEDULE, which will not call a step runnable while a document its plan
  says to wait for does not exist -- and which goes on offering the step when
  the plan says `fail` or says nothing, on the same journal;
- the eligibility HOLD, which refuses such a step for free, and which names the
  document because that is the one of `blocked`'s three meanings a caller
  cannot see in the plan and can actually go and act on;
- `close_if_terminal`, which records NOTHING while a step is merely waiting. A
  document that nobody has published yet is a wait and not an ending: the run
  stays open until it arrives, and a `stalled` terminal forged over such a wait
  is refused on the append road and again on raw replay.

The ARRIVAL is what the owner asked for, and it is driven on both roads a
document can reach a run by: an operator publishing one through the real HTTP
boundary, here; and a real review publishing one through a real transport, in
`test_command_artifact_flow`, where a real review already exists to do it.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.contracts import DecisionReceipt, canonical_json
from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphNode,
)
from conductor.command.graph_schedule import schedule
from conductor.command.run_closing import close_if_terminal
from conductor.command.run_store import (
    CorruptRun,
    RunStore,
    StoreError,
    snapshot_digest,
)
from conductor.command.run_terminal import RunTerminal
from tests.schedule_journal import Journal, row_of
from tests.test_command_missing_artifact_policy import NOW, an_artifact
from tests.test_command_run_store import CONFIG, a_run

#: The store-backed witnesses open a real run, built by the run store's own
#: helpers, so what replays here is what the product replays.
STORE_RUN = "run-001"


# -- 10. the schedule spends it -----------------------------------------------


def a_waiting_plan(*, policy=None, ref="artifact-brief",
                   run: str = "run-001") -> GraphDefinition:
    """One review step with no roads in, needing one document.

    No predecessors, so nothing about the plan's shape can open or close it and
    the only thing that moves this step is whether the document exists. A review
    rather than a dispatch because an effect-capable step must stand behind a
    gate, and a gate would be a second reason for the answer.
    """
    return GraphDefinition(
        graph_id="graph-wait", run_id=run, created_at=NOW,
        nodes=(GraphNode(node_id="check", kind="task", title="Check it",
                         instance_id="claude-dev", capability="review",
                         arguments={"work_item_id": "work-1",
                                    "target_artifact_refs": [ref],
                                    "result_artifact_ref": "artifact-verdict",
                                    "review_profile": "quality"},
                         missing_artifact_policy=policy),),
        edges=())


def test_a_blocking_step_whose_document_is_absent_is_never_offered():
    computed = schedule(a_waiting_plan(policy="block"), ())

    assert computed.state_of("check") == "blocked"
    assert computed.nodes[0].awaiting_artifacts == ("artifact-brief",)
    assert computed.runnable == ()
    # And the run is OPEN, because waiting for a document is not an ending:
    # publishing one is a thing a person can still go and do.
    assert computed.run_state == "open"


def test_the_document_arriving_is_what_makes_the_step_runnable():
    """The owner's requirement, at the seam that decides it."""
    plan = a_waiting_plan(policy="block")

    assert schedule(plan, (an_artifact("artifact-brief"),)).state_of(
        "check") == "runnable"
    # And a document under a DIFFERENT reference does not answer for it: the
    # requirement is the reference the step named, not any artifact at all.
    assert schedule(plan, (an_artifact("artifact-other"),)).state_of(
        "check") == "blocked"


@pytest.mark.parametrize("policy", [None, "fail"])
def test_the_same_journal_without_block_offers_the_step(policy):
    """The discriminating control, and it carries the whole `absent is fail`
    ruling: the journal that leaves a `block` step waiting leaves this one
    runnable, so nothing here blocks a step merely for missing an input."""
    computed = schedule(a_waiting_plan(policy=policy), ())

    assert computed.state_of("check") == "runnable"
    assert computed.nodes[0].awaiting_artifacts == ()
    assert computed.run_state == "open"


def test_the_awaited_documents_are_never_folded_into_the_roads():
    """The three road tuples partition this step's IN-EDGES, and an artifact
    reference is not a predecessor. A window rendering `blocked_by` under
    "Waiting on" beside the ALL-roads rule would otherwise print a step name
    that names no step."""
    row = schedule(a_waiting_plan(policy="block"), ()).nodes[0]

    assert row.awaiting_artifacts == ("artifact-brief",)
    assert row.blocked_by == () and row.opened_by == () and row.closed_by == ()
    assert row.attempts_spent is False


def a_spent_waiting_plan() -> GraphDefinition:
    """The same lone waiting step, allowed exactly one attempt."""
    waiting = a_waiting_plan(policy="block").nodes[0]
    return GraphDefinition(
        graph_id="graph-wait", run_id="run-001", created_at=NOW,
        nodes=(GraphNode.from_dict({**waiting.as_dict(), "attempt_bound": 1}),),
        edges=())


def test_a_waiting_step_that_has_spent_its_bound_is_spent_and_not_waiting():
    """Two of `blocked`'s three meanings at once, and the stronger one wins.

    The document never arrived AND the one attempt this step was allowed is
    gone. Publishing the document now would change nothing, because there is no
    attempt left to spend on it -- so this is not a wait anybody can end, and
    the run is stalled by the spent bound exactly as it would be on a step whose
    plan named no policy at all.
    """
    journal = Journal()
    journal.result(journal.request("check"), "unknown")

    computed = schedule(a_spent_waiting_plan(), journal.rows())

    row = computed.nodes[0]
    assert (row.state, row.attempts_spent) == ("blocked", True)
    assert row.awaiting_artifacts == ("artifact-brief",)
    assert computed.run_state == "stalled"


def test_a_step_no_run_reaches_is_not_described_as_waiting_for_anything():
    """`awaiting_artifacts` answers "why is this not offered", so it is empty
    wherever that is not the question -- naming documents for a step the run
    can never reach would describe work that will not happen."""
    gate = GraphNode(node_id="gate", kind="gate", title="Gate", gate_id="g-1")
    waiting = a_waiting_plan(policy="block").nodes[0]
    plan = GraphDefinition(
        graph_id="graph-wait", run_id="run-001", created_at=NOW,
        nodes=(gate, waiting),
        edges=(GraphEdge(from_node="gate", to_node="check",
                         condition="on_rejected"),))

    computed = schedule(plan, (a_receipt("approve"),))

    assert computed.state_of("check") == "unreachable"
    assert computed.nodes[1].awaiting_artifacts == ()


def a_receipt(action: str) -> DecisionReceipt:
    return DecisionReceipt(
        receipt_id=f"receipt-{action}", run_id="run-001", gate_id="g-1",
        action=action, actor="owner", decided_at=NOW,
        reason="Answered.", scope_refs=("src",),
        config_digest=snapshot_digest(CONFIG))


# -- 11. the refusal a person meets, and the ending that is recorded ----------


class _As:
    """The one fact `_hold_node_is_eligible` reads off a proposal."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id


def a_gated_plan(*, policy) -> GraphDefinition:
    """The same waiting step, behind a gate nobody has answered."""
    return GraphDefinition(
        graph_id="graph-wait", run_id=STORE_RUN, created_at=NOW,
        nodes=(GraphNode(node_id="gate", kind="gate", title="Gate",
                         gate_id="g-1"),
               a_waiting_plan(policy=policy, run=STORE_RUN).nodes[0]),
        edges=(GraphEdge(from_node="gate", to_node="check"),))


def a_store(tmp_path, *, plan, published=False):
    """One real run following one plan, replayed through the real store."""
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=STORE_RUN, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    store.append(plan)
    if published:
        store.append(an_artifact("artifact-brief", run=STORE_RUN))
    return store


def _kinds(store, run_id=STORE_RUN) -> list[str]:
    """The record types this run's journal really holds, read off the bytes."""
    text = (store.run_path(run_id) / "records.jsonl").read_text(
        encoding="utf-8")
    return [json.loads(line)["record_type"]
            for line in text.splitlines() if line]


def _computed(store, run_id=STORE_RUN):
    """This run's schedule, taken over the journal the store really holds."""
    recovered = store.read(run_id)
    graph = next(row.value for row in recovered.records
                 if row.kind == "graph_definition")
    return schedule(graph, tuple(row.value for row in recovered.records))


def test_the_eligibility_refusal_names_the_document_the_run_is_waiting_for(
        tmp_path):
    """`blocked` covers three situations and only one of them is invisible in
    the plan. A caller told the bare word cannot tell "this step's turn has not
    come" from "somebody has to publish a document", and only the second names
    something they can go and do."""
    from conductor.command.authorize_holds import _hold_node_is_eligible
    from conductor.command.runtime_values import AuthorizationError

    store = a_store(tmp_path, plan=a_waiting_plan(policy="block",
                                                  run=STORE_RUN))

    with pytest.raises(AuthorizationError) as refusal:
        _hold_node_is_eligible(_As("check"), store.read(STORE_RUN))

    said = str(refusal.value)
    assert "is blocked" in said, said
    assert "artifact-brief" in said, said
    assert "before it runs" in said, said


def test_the_same_refusal_says_nothing_about_documents_when_none_is_awaited(
        tmp_path):
    """The other direction, and it needs the document to EXIST.

    A step blocked because its turn has not come is not given a sentence about
    documents. Here the document is published and the gate is unanswered, so
    the step is blocked for a reason that is in the plan and a reader can see.
    """
    from conductor.command.authorize_holds import _hold_node_is_eligible
    from conductor.command.runtime_values import AuthorizationError

    store = a_store(tmp_path, plan=a_gated_plan(policy="block"),
                    published=True)

    with pytest.raises(AuthorizationError) as refusal:
        _hold_node_is_eligible(_As("check"), store.read(STORE_RUN))

    said = str(refusal.value)
    assert "is blocked" in said, said
    # The SENTENCE, not one reference inside it: a first draft of this
    # asserted only that `artifact-brief` was absent, and a build whose
    # refusal said "waiting for artifact(s) []" survived it -- an empty
    # list rendered as a sentence is exactly the noise this half exists
    # to refuse.
    assert "waiting for artifact" not in said, said
    assert "artifact-brief" not in said, said


# -- 12. the operator road, end to end through the real boundary --------------


def test_an_operator_publishing_the_document_makes_the_step_runnable(tmp_path):
    """The other arrival road, driven through the API a person really uses.

    The review road is witnessed next door in `test_command_artifact_flow`,
    where a real review publishes through a real transport. This is the road
    the S4 external-input sentence describes: a person seeds the document
    themselves, through `POST /command/runs/<id>/artifacts`, and the step the
    plan was holding back becomes offerable.

    Both halves are read out of the RUN READ rather than out of `schedule`
    directly, so what is asserted is what the window is actually told.
    """
    from tests.test_command_artifacts import body
    from tests.test_command_http_api import api, get_headers, post

    subject, store, _ = api(tmp_path)
    store.append(a_waiting_plan(policy="block", run=STORE_RUN))

    before = _standing(subject, get_headers)
    created = post(subject, f"/command/runs/{STORE_RUN}/artifacts", body())
    after = _standing(subject, get_headers)

    assert created.status == 201
    assert before["state"] == "blocked"
    assert before["awaiting_artifacts"] == ["artifact-brief"]
    assert after["state"] == "runnable"
    assert after["awaiting_artifacts"] == []


def _standing(subject, get_headers) -> dict:
    """The waiting step's row, as the run read answers it."""
    read = subject.handle("GET", f"/command/runs/{STORE_RUN}", get_headers())
    return next(row for row in read.payload["graph"]["schedule"]["nodes"]
                if row["node_id"] == "check")


def _read_schedule(subject, get_headers) -> tuple[int, dict]:
    """The run read's status and the whole schedule the window is handed."""
    read = subject.handle("GET", f"/command/runs/{STORE_RUN}", get_headers())
    return read.status, read.payload["graph"]["schedule"]


def _a_decided_wait(tmp_path):
    """A real run whose one remaining step is waiting for a document.

    The gate in front of it is answered through the real HTTP boundary, which
    is the road that carries `close_if_terminal`: the closing call runs inside
    the decision's own transaction, so whatever it decides is decided here.
    """
    from tests.test_command_http_api import api, decision_body, post

    subject, store, _ = api(tmp_path)
    store.append(a_gated_plan(policy="block"))

    answered = post(subject, f"/command/runs/{STORE_RUN}/decisions",
                    decision_body(gate_id="g-1"))
    return subject, store, answered


def test_deciding_the_gate_in_front_of_a_waiting_step_ends_nothing(tmp_path):
    """The defect this rule closes, at the door a person actually pushes.

    Answering the gate is the last thing anybody can do, and it leaves the
    review waiting for a document nobody has published. Under the withdrawn
    reading that was the END of the run: a `stalled` terminal was minted inside
    the decision's own transaction, and the artifact the plan was waiting for
    could then never be admitted at all -- publishing it bricked the journal.

    The bytes are read rather than the record list, because "no terminal was
    returned" would also be true of one that had been written and lost.
    """
    subject, store, answered = _a_decided_wait(tmp_path)

    assert answered.status == 201
    assert _kinds(store) == ["graph_definition", "decision"]
    raw = (store.run_path(STORE_RUN) / "records.jsonl").read_bytes()
    assert b"run_terminal" not in raw
    assert json.loads(
        raw.decode("utf-8").splitlines()[-1])["record_type"] == "decision"

    computed = _computed(store)
    waiting = row_of(computed, "check")
    assert waiting.state == "blocked"
    assert waiting.awaiting_artifacts == ("artifact-brief",)
    assert waiting.attempts_spent is False and waiting.blocked_by == ()
    assert computed.run_state == "open"
    assert close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                             ids=lambda kind: f"{kind}-001") is None


def test_the_document_arriving_after_the_decision_opens_the_step_and_ends_nothing(
        tmp_path):
    """And the wait really does end, in the order the owner asked for it in.

    Publish AFTER the decision, which is the order that used to be impossible:
    the run had already recorded its ending, so the store refused the document
    and every later read answered `run_corrupt`. Here the artifact is admitted,
    the step it was holding back becomes runnable, and the run is still open.
    """
    from tests.test_command_artifacts import body
    from tests.test_command_http_api import get_headers, post

    subject, store, _answered = _a_decided_wait(tmp_path)

    created = post(subject, f"/command/runs/{STORE_RUN}/artifacts", body())

    assert created.status == 201
    assert _kinds(store) == ["graph_definition", "decision", "artifact"]
    status, computed = _read_schedule(subject, get_headers)
    assert status == 200
    assert _standing(subject, get_headers)["state"] == "runnable"
    assert _standing(subject, get_headers)["awaiting_artifacts"] == []
    assert computed["run_state"] == "open"
    assert RunStore(tmp_path).read(STORE_RUN).warnings == ()


# -- 13. the ending is recorded, and replay recomputes it ---------------------


def test_a_run_waiting_for_a_document_nobody_publishes_records_no_ending(
        tmp_path):
    """`block` needs no new run word, and it needs no ENDING either.

    Nothing is runnable, and there is still something a person can go and do:
    publish the document. `stalled` would say the opposite -- and, being
    durable, would refuse the very artifact that ends the wait.
    """
    store = a_store(tmp_path, plan=a_waiting_plan(policy="block",
                                                  run=STORE_RUN))

    terminal = close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                                 ids=lambda kind: f"{kind}-001")

    assert terminal is None
    assert _kinds(store) == ["graph_definition"]


def test_the_twin_whose_document_stands_records_no_ending_at_all(tmp_path):
    """The control on the closing road: the step is offered, so the plan is
    open and there is nothing to record."""
    store = a_store(tmp_path, plan=a_waiting_plan(policy="block",
                                                  run=STORE_RUN),
                    published=True)

    assert close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                             ids=lambda kind: f"{kind}-001") is None


def a_bounded_waiting_plan(*, behind_the_work: bool) -> GraphDefinition:
    """A gate, the shipped Do node allowed ONE attempt, and the waiting review.

    The review stands BEHIND that work or beside it, and that one difference is
    the whole of what the two witnesses below tell apart: a road that will never
    open is a second reason the step is not offered, and a step waiting only for
    a document has no second reason at all.

    The Do node is taken from the shipped plan verbatim -- instance, capability
    and arguments -- so the request and the result written for it are the ones
    the store's own chain rules accept.
    """
    from tests.alpha3_graph_artifacts import dalio_definition

    doing = next(row for row in dalio_definition(run_id=STORE_RUN).nodes
                 if row.node_id == "do")
    roads = [GraphEdge(from_node="gate", to_node="do")]
    if behind_the_work:
        roads.append(GraphEdge(from_node="do", to_node="check"))
    return GraphDefinition(
        graph_id="graph-wait", run_id=STORE_RUN, created_at=NOW,
        nodes=(GraphNode(node_id="gate", kind="gate", title="Gate",
                         gate_id="g-1"),
               GraphNode.from_dict({**doing.as_dict(), "attempt_bound": 1}),
               a_waiting_plan(policy="block", run=STORE_RUN).nodes[0]),
        edges=tuple(roads))


def a_bounded_store(tmp_path, *, behind_the_work: bool):
    """That plan, its gate answered and its one attempt spent on an `unknown`.

    `unknown` is this product's word for *the journal supports no answer*, so
    the attempt settles nothing -- and with the bound gone the step can never
    settle again, whatever anybody publishes.
    """
    from tests.test_command_graph_projection import (
        a_proposal,
        a_request,
        a_result,
    )

    store = a_store(
        tmp_path, plan=a_bounded_waiting_plan(behind_the_work=behind_the_work))
    store.append(a_receipt("approve"))
    proposal = a_proposal(node_id="do", index=1, run_id=STORE_RUN)
    store.append(proposal)
    request = a_request(proposal, index=1, run_id=STORE_RUN)
    store.append(request)
    store.append(a_result(request, index=1, run_id=STORE_RUN,
                          outcome="unknown", evidence_refs=()))
    return store


def test_a_step_waiting_behind_a_spent_predecessor_still_stalls_the_run(
        tmp_path):
    """The inversion: a document is not the only thing this step is waiting for.

    Its predecessor spent the one attempt the plan allowed it on an answer that
    settles nothing, so the road into this step can never open. Publishing the
    document would not help -- the step is unreachable in every way that
    matters, and the run really has ended.

    Which is why the wait a run stays open for is the one with NO other reason
    behind it. A fix that read `awaiting_artifacts` alone would call this run
    open forever and leave nobody anything to do.
    """
    store = a_bounded_store(tmp_path, behind_the_work=True)

    computed = _computed(store)
    waiting = row_of(computed, "check")

    assert row_of(computed, "do").attempts_spent is True
    assert waiting.state == "blocked"
    assert waiting.awaiting_artifacts == ("artifact-brief",)
    assert waiting.blocked_by == ("do",)
    assert computed.run_state == "stalled"

    terminal = close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                                 ids=lambda kind: f"{kind}-001")

    assert terminal is not None and terminal.state == "stalled"
    assert _kinds(store)[-1] == "run_terminal"


def test_a_document_wait_beside_a_spent_branch_keeps_the_run_open(tmp_path):
    """The same two facts, wired side by side rather than in a line.

    One branch is spent and can never settle; the other is waiting for a
    document and nothing else. A run whose every blocked step had to be waiting
    would end here, and it must not: publishing the document still gives the
    plan somewhere to go.
    """
    store = a_bounded_store(tmp_path, behind_the_work=False)

    computed = _computed(store)

    assert row_of(computed, "do").attempts_spent is True
    assert computed.state_of("do") == "blocked"
    assert row_of(computed, "check").blocked_by == ()
    assert computed.run_state == "open"
    assert close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                             ids=lambda kind: f"{kind}-001") is None

    store.append(an_artifact("artifact-brief", run=STORE_RUN))

    arrived = _computed(store)
    assert arrived.state_of("check") == "runnable"
    assert arrived.run_state == "open"


def test_a_terminal_recorded_over_a_mere_wait_is_refused_on_append_and_replay(
        tmp_path):
    """`close_if_terminal` declining to write one is only half of the rule.

    The record is bytes, and anybody holding them could put one there. So the
    verdict is recomputed where the record is JUDGED -- on the append road and
    again on raw replay -- and a `stalled` terminal standing over a run that is
    merely waiting is a fact its own journal does not support.

    The two partitions are the TRUE ones, so what is refused is the WORD. A
    forgery that also moved a name would be caught by the comparison that was
    already there, and this would prove nothing about the state.
    """
    store = a_store(tmp_path, plan=a_waiting_plan(policy="block",
                                                  run=STORE_RUN))
    forged = RunTerminal(
        terminal_id="terminal-001", run_id=STORE_RUN, graph_id="graph-wait",
        state="stalled", settled_nodes=(), unreachable_nodes=(),
        recorded_at=NOW)

    with pytest.raises(StoreError, match="does not match what this run"):
        store.append(forged)

    assert _kinds(store) == ["graph_definition"]
    path = store.run_path(STORE_RUN) / "records.jsonl"
    path.write_text(
        path.read_text(encoding="utf-8") + canonical_json(
            {"record": forged.as_dict(), "record_type": "run_terminal"}) + "\n",
        encoding="utf-8", newline="\n")

    with pytest.raises(CorruptRun, match="does not match what this run"):
        RunStore(tmp_path).read(STORE_RUN)
