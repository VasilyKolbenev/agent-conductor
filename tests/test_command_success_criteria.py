"""The four clauses, each on a step that really has it.

`success_criteria` states what counts as success for a step by restating rules
this build already enforces. Which clauses apply is a fact about the step, so
each is driven on a step that has it and on one that does not -- a battery that
only ever looked at one shape would pass on a build that dropped a clause it
never reached.

The four, and the layer each is read from:

- the result must be VERIFIED -- ``verify_holds`` refuses a verification that
  proves nothing, before a success receipt is written;
- WHO may answer for it -- the plan's ``verifier_instance_id`` when it names
  one, the doer otherwise, which is ``graph_causality.permitted_verifier``'s
  own rule;
- a review's own OUTPUT must stand and answer its request --
  ``artifacts._artifact_answers_its_request``;
- and the plan may demand the verification NAME something --
  ``graph_causality.demanded_evidence``.

Nothing here is stored and nothing is editable. The reading is served by the
run read and the workflow read, and the window renders it: the tests that hold
THAT are next door in ``test_studio_success_criteria`` and in the browser.
"""
from __future__ import annotations
from tests.human_situation_samples import READ_AT

import pytest

from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.graph_projection import graph_payload
from conductor.command.success_criteria import (
    CHAIN_SOURCE,
    DEMAND_SOURCE,
    PLAN_SOURCE,
    VERIFIED_SOURCE,
    criteria_rows,
    for_plan,
)

NOW = "2026-09-02T10:00:00Z"
REVIEW_ARGS = {"work_item_id": "w-1", "target_artifact_refs": ["artifact-in"],
               "result_artifact_ref": "artifact-verdict",
               "review_profile": "quality"}
DISPATCH_ARGS = {"work_item_id": "w-1", "instruction_ref": "i-1",
                 "profile": "implement", "artifact_refs": [],
                 "output_limit_profile": "normal"}


def texts(rows) -> str:
    return " | ".join(row["text"] for row in rows)


def sources(rows) -> list[str]:
    return [row["source"] for row in rows]


# -- all four clauses, on the step that has all four --------------------------


def test_a_review_with_a_verifier_and_a_digest_demand_states_all_four():
    rows = criteria_rows(
        kind="task", capability="review", verifier="checker", doer="worker",
        required_evidence="digest", arguments=REVIEW_ARGS)

    assert len(rows) == 4, texts(rows)
    said = texts(rows)
    assert "The result must be verified" in said
    assert "Verified by checker, which this plan names as the step's verifier" in said
    assert "artifact-verdict must stand, published by this step's own action" in said
    assert "The verification must name a digest" in said
    assert sources(rows) == [VERIFIED_SOURCE, PLAN_SOURCE, CHAIN_SOURCE,
                             DEMAND_SOURCE]


# -- and each clause absent on the step that does not have it -----------------


def test_a_dispatch_states_no_artifact_clause():
    """Only a review publishes a document; a dispatch's evidence is a digest of
    what it changed. A clause about a result artifact on a dispatch would be a
    promise about a record that never exists."""
    rows = criteria_rows(
        kind="task", capability="dispatch", verifier="checker", doer="worker",
        required_evidence="digest", arguments=DISPATCH_ARGS)

    said = texts(rows)
    assert "must stand, published by" not in said, said
    assert CHAIN_SOURCE not in sources(rows), sources(rows)
    # The other three are all there, so this is an absence and not a silence.
    assert len(rows) == 3, said


def test_a_step_with_no_evidence_demand_states_no_digest_clause():
    rows = criteria_rows(
        kind="task", capability="review", verifier=None, doer="worker",
        required_evidence=None, arguments=REVIEW_ARGS)

    said = texts(rows)
    assert "must name a digest" not in said, said
    assert DEMAND_SOURCE not in sources(rows), sources(rows)
    assert len(rows) == 3, said


def test_a_step_with_no_verifier_names_the_doer_and_says_which_it_is():
    """The two cases must READ differently. A plan naming a separate verifier
    means evidence from the doer is precisely what is refused; a plan naming
    none means the doer answers. One sentence for both would hide the choice a
    person is making."""
    named = criteria_rows(
        kind="task", capability="dispatch", verifier="checker", doer="worker",
        required_evidence=None, arguments=DISPATCH_ARGS)
    absent = criteria_rows(
        kind="task", capability="dispatch", verifier=None, doer="worker",
        required_evidence=None, arguments=DISPATCH_ARGS)

    assert "Verified by checker, which this plan names" in texts(named)
    assert "Verified by worker, the instance that does the work" in texts(absent)
    assert "names no separate verifier" in texts(absent)
    assert "names no separate verifier" not in texts(named)


def test_a_review_that_names_no_result_reference_yet_says_so():
    rows = criteria_rows(
        kind="task", capability="review", verifier=None, doer="worker",
        required_evidence=None, arguments={"work_item_id": "w-1"})

    assert "names no result reference yet" in texts(rows), texts(rows)


@pytest.mark.parametrize("kind,capability", [
    ("gate", None), ("loop", None), ("task", None),
])
def test_a_step_that_carries_nothing_out_has_no_criteria(kind, capability):
    """Nothing is executed for it, so no verification is owed. An empty tuple
    is a reading a screen can show as "none"."""
    assert criteria_rows(
        kind=kind, capability=capability, verifier=None, doer=None,
        required_evidence=None, arguments={}) == ()


# -- the run read really carries them, per step -------------------------------


def a_plan() -> GraphDefinition:
    return GraphDefinition(
        graph_id="g", run_id="run-001", created_at=NOW,
        nodes=(GraphNode(node_id="gate", kind="gate", title="Gate",
                         gate_id="gate-1"),
               GraphNode(node_id="check", kind="task", title="Check",
                         instance_id="worker", capability="review",
                         arguments=REVIEW_ARGS,
                         verifier_instance_id="checker",
                         required_evidence="digest")),
        edges=())


def test_the_reading_is_keyed_by_node_and_covers_every_step():
    rows = for_plan(a_plan().nodes)

    assert set(rows) == {"gate", "check"}
    assert rows["gate"] == []
    assert len(rows["check"]) == 4, rows["check"]


def test_the_run_read_carries_the_statement_for_the_step_it_describes(tmp_path):
    """Driven through the real projection rather than the helper, because what
    a window is served is what matters -- and a build that derived correctly and
    served nothing would pass every test above."""
    from conductor.command.run_store import RunStore, snapshot_digest
    from tests.test_command_run_store import CONFIG, a_run

    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id="run-001", mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    store.append(a_plan())

    served = graph_payload(store.read("run-001"), computed_at=READ_AT)["success_criteria"]

    assert set(served) == {"gate", "check"}
    said = texts(served["check"])
    assert "Verified by checker" in said, said
    assert "artifact-verdict must stand" in said, said
    assert "must name a digest" in said, said
    assert served["gate"] == []
