"""A plan may not land on a run that already answered one of its gates.

The second of the two orderings of one defect, split out of
``tests/test_command_decision_doors.py`` when that module crossed the project's
line cap -- and along a real seam rather than a convenient line. Next door the
DECISION arrives after the plan and `_hold_gate_is_reached` refuses it. Here the
decision arrives FIRST, which is legal and stays legal: a run may be answered
and then given a graph, and every journal written before graphs existed is one
such run. So the refusal moves to the plan.

What that door refuses is narrow on purpose. A receipt naming a gate the
candidate plan does not draw is admitted exactly as it always was -- the store's
own "a decision written before the plan stays legal" rule is held one layer
down by ``tests/test_command_graph_store.py``, and this door had to be written
so as not to take it back. What is refused is only the plan that would ADOPT an
answer already lying in the journal: the gate would be settled the moment the
plan landed, with every step in front of it untouched.

Both plan-writing roads are driven, because a rule held at one of them is a
rule a caller can walk around.
"""
from __future__ import annotations

from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.artifacts import ArtifactDocument
from tests.test_command_decision_doors import (
    DECISIONS,
    a_plan_less_run,
    refusal_of,
)
from tests.test_command_graph_route import graph_body, post_graph
from tests.test_command_http_api import NOW, RUN_ID, decision_body, post
from tests.test_command_run_terminal_doors import journal_bytes, kinds
from tests.test_command_template_routes import (
    FROM_TEMPLATE_PATH,
    TEMPLATES_PATH,
    api as template_api,
    from_template_body,
    template_body,
)


def a_gate_the_plan_carries():
    """A submitted plan whose gate is the one the receipts below answer."""
    body = graph_body()
    body["nodes"] = [
        {**node, "gate_id": "gate-confirm-do"} if node["kind"] == "gate"
        else node for node in body["nodes"]]
    return body


def test_a_plan_may_not_land_on_a_run_that_already_answered_one_of_its_gates(
        tmp_path):
    """The reversed ordering, refused on the road that reverses it.

    The minimal journal: one record, and it is the offending one.
    """
    subject, store, events = a_plan_less_run(tmp_path)
    assert post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-early")).status == 201
    before = journal_bytes(store)
    events.clear()

    refused = post_graph(subject, a_gate_the_plan_carries())

    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert refusal_of(refused)["code"] == "gate_unreached"
    assert kinds(store) == ["decision"]
    assert journal_bytes(store) == before
    assert events == []


def test_the_plan_door_finds_the_answer_wherever_it_lies_in_the_journal(
        tmp_path):
    """The offending receipt is the THIRD record, behind two innocent ones.

    A door written over the first record alone would pass the witness above --
    its journal holds exactly one -- and would then admit the very plan that
    witness exists to refuse. So the run is given a receipt for a gate this
    plan does NOT carry, then a record that is not a decision at all, and only
    then the answer that matters.
    """
    subject, store, events = a_plan_less_run(tmp_path)
    assert post(subject, DECISIONS, decision_body(
        gate_id="release", receipt_id="decision-foreign")).status == 201
    store.append(ArtifactDocument(
        artifact_id="artifact-1", artifact_ref="artifact-brief", run_id=RUN_ID,
        created_at=NOW, media_type="text/markdown", content="# Brief\n"))
    assert post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-early")).status == 201
    assert kinds(store) == ["decision", "artifact", "decision"]
    before = journal_bytes(store)
    events.clear()

    refused = post_graph(subject, a_gate_the_plan_carries())

    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert refusal_of(refused)["code"] == "gate_unreached"
    assert kinds(store) == ["decision", "artifact", "decision"]
    assert journal_bytes(store) == before
    assert events == []


def test_a_plan_carrying_no_such_gate_still_lands_on_the_same_run(tmp_path):
    """The control, and the rule it keeps: a decision before the plan is legal.

    The very run refused above accepts a plan whose gates the receipt does not
    name. `tests/test_command_graph_store.py` holds the same fact one layer
    down, and this door had to be written so as not to take it back.
    """
    subject, store, _events = a_plan_less_run(tmp_path)
    assert post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-early")).status == 201

    landed = post_graph(subject, graph_body())

    assert landed.status == 201
    assert kinds(store) == ["decision", "graph_definition"]


def test_the_template_road_refuses_the_same_pre_answered_plan(tmp_path):
    """Both plan-writing roads, because one refusing is a road round the other.

    `POST /graph` and `POST /graph/from-template` write the same record by
    different rights, and a rule held at one of them is a rule a caller can
    walk around.
    """
    subject, store, events = template_api(tmp_path)
    assert post(subject, TEMPLATES_PATH, template_body()).status == 201
    assert post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-early")).status == 201
    before = journal_bytes(store)
    events.clear()

    refused = post(subject, FROM_TEMPLATE_PATH, from_template_body())

    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert refusal_of(refused)["code"] == "gate_unreached"
    assert kinds(store) == ["decision"]
    assert journal_bytes(store) == before
    assert events == []
