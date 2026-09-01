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
- `close_if_terminal`, which needs no new word for this: nothing runnable and
  something still owed is `stalled`, and a journal forged to strip the policy
  makes the recorded ending disagree with its own plan.

The ARRIVAL is what the owner asked for, and it is driven on both roads a
document can reach a run by: an operator publishing one through the real HTTP
boundary, here; and a real review publishing one through a real transport, in
`test_command_artifact_flow`, where a real review already exists to do it.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.contracts import DecisionReceipt
from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphNode,
)
from conductor.command.graph_schedule import schedule
from conductor.command.run_closing import close_if_terminal
from conductor.command.run_store import CorruptRun, RunStore, snapshot_digest
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
    # Nothing runnable and something still owed is the plan's own word for it.
    assert computed.run_state == "stalled"


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


# -- 13. the ending is recorded, and replay recomputes it ---------------------


def test_a_run_waiting_for_a_document_nobody_publishes_records_a_stalled_end(
        tmp_path):
    """`block` needs no new run word: nothing runnable and something still owed
    is `stalled`, which `close_if_terminal` records through the road it had."""
    store = a_store(tmp_path, plan=a_waiting_plan(policy="block",
                                                  run=STORE_RUN))

    terminal = close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                                 ids=lambda kind: f"{kind}-001")

    assert terminal is not None and terminal.state == "stalled"
    assert [row.kind for row in store.read(STORE_RUN).records][-1] == (
        "run_terminal")


def test_the_twin_whose_document_stands_records_no_ending_at_all(tmp_path):
    """The control on the closing road: the step is offered, so the plan is
    open and there is nothing to record."""
    store = a_store(tmp_path, plan=a_waiting_plan(policy="block",
                                                  run=STORE_RUN),
                    published=True)

    assert close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                             ids=lambda kind: f"{kind}-001") is None


def test_a_journal_that_strips_the_policy_from_the_plan_is_corrupt(tmp_path):
    """The verdict is recomputed from the plan's own bytes on replay.

    Softening a recorded ending by editing the plan it was computed from does
    not work: with the word gone the step is runnable, the run is open, and the
    `stalled` terminal standing beside it is a fact its own journal no longer
    supports.
    """
    store = a_store(tmp_path, plan=a_waiting_plan(policy="block",
                                                  run=STORE_RUN))
    close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                      ids=lambda kind: f"{kind}-001")
    path = store.run_path(STORE_RUN) / "records.jsonl"
    forged = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["record_type"] == "graph_definition":
            for node in row["record"]["nodes"]:
                node.pop("missing_artifact_policy", None)
        forged.append(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")))
    path.write_text("\n".join(forged) + "\n", encoding="utf-8", newline="\n")

    with pytest.raises(CorruptRun, match="does not match what this run"):
        RunStore(tmp_path).read(STORE_RUN)
