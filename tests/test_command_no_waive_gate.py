"""A gate that may not be set aside, and the three doors that hold it shut.

`waive` is the one decision that closes a gate WITHOUT judging the work. Every
gate this product has ever drawn accepts it, and that is right for most: a
person who decides the question no longer applies needs a way to say so. What
was missing is the other half -- a gate where setting it aside is exactly what
must not be possible, because the whole reason it exists is that a Human looked.

`success_requires: "human_approval"` says that, on gate nodes only, and it is
held at three doors rather than one:

- the SCREEN stops offering the answer, so nobody is invited to give one;
- the SERVER refuses it before anything is appended, so a client that asks
  anyway is told no and the run's bytes do not move;
- the STORE refuses a journal that carries one, so bytes written around the
  server -- by hand, by an older build, by anything -- are refused when they are
  READ rather than merely when they are written.

The third is what makes this a property of the record rather than a courtesy of
the boundary, and it is why the rule lives beside `_decision_names_a_planned_gate`
in `graph_causality`: both are pure functions of the plan's own bytes among the
PRIOR records, and both stay silent on a run that follows no plan.

Two things it deliberately does NOT do. It never makes a gate easier to pass:
`reject` and `request_changes` stay legal, and there are positive controls on
the very same gate below. And it does not quietly change any plan already
written -- absent means every answer a gate has always had, so all three shipped
starters digest exactly as they did.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from conductor.command.contracts import ContractError, canonical_json
from conductor.command.graph_causality import gate_refuses_waiver
from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphNode,
    _rebuilt_node,
)
from conductor.command.graph_template import (
    RunBinding,
    TemplateError,
    TemplateNode,
    load_template,
    materialize,
)
from conductor.command.graph_template_document import (
    _rebuilt_node as _rebuilt_template_node,
)
from conductor.command.graph_values import (
    GATE_SUCCESS_DEMANDS,
    settled_success_requires,
)
from conductor.command.run_store import RunStore, StoreError, snapshot_digest
from conductor.command.workflow_draft import parse_document, publish_candidate
from tests.test_command_run_store import CONFIG, a_run

NOW = "2026-09-02T10:00:00Z"
RUN_ID = "run-001"
SOLO = {"instances": [{"id": "solo", "adapter": "claude-code"}]}
STARTERS = ("dalio-v1", "dalio-v2", "dalio-v3")
DEMAND = "human_approval"
#: Every answer a gate can carry that is NOT the one this field removes. Each
#: stays legal on a protected gate, and each has a witness saying so.
STILL_LEGAL = ("approve", "reject", "request_changes")


def a_gate(**changes) -> GraphNode:
    values = {"node_id": "gate", "kind": "gate", "title": "Human Gate",
              "gate_id": "gate-1"}
    values.update(changes)
    return GraphNode(**values)


def a_plan(*, demand=DEMAND, waived_road=False) -> GraphDefinition:
    edges = [GraphEdge(from_node="gate", to_node="do",
                       condition="on_approved" if waived_road else None)]
    if waived_road:
        edges.append(GraphEdge(from_node="gate", to_node="skip",
                               condition="on_waived"))
    nodes = [a_gate(success_requires=demand),
             GraphNode(node_id="do", kind="task", title="Do",
                       instance_id="solo", capability="review",
                       arguments={"work_item_id": "w-1",
                                  "target_artifact_refs": ["artifact-brief"],
                                  "result_artifact_ref": "artifact-out",
                                  "review_profile": "quality"})]
    if waived_road:
        nodes.append(GraphNode(node_id="skip", kind="task", title="Skip"))
    return GraphDefinition(graph_id="graph-gate", run_id=RUN_ID,
                           created_at=NOW, nodes=tuple(nodes),
                           edges=tuple(edges))


# -- 1. the vocabulary, and the one direction it may grow ---------------------


def test_the_vocabulary_is_one_word_and_it_only_ever_tightens():
    """Both directions. A word leaving would make every plan naming it
    unreadable; a word arriving must remove an answer, never restore one."""
    assert GATE_SUCCESS_DEMANDS == frozenset({DEMAND})


def test_the_refusal_says_which_direction_this_vocabulary_may_grow():
    """The rule a future word is judged by, said where a person meets it.

    A word that made a gate EASIER to answer would change what an approval
    already recorded under stricter terms had meant -- which is the one thing an
    immutable revision exists to prevent.
    """
    with pytest.raises(ContractError) as refusal:
        settled_success_requires("optional")

    said = str(refusal.value)
    assert "harder to give, never easier" in said, said
    assert "['human_approval']" in said, said


@pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
def test_saying_nothing_and_saying_blank_are_one_answer(value):
    assert settled_success_requires(value) is None


@pytest.mark.parametrize("value", ["waivable", "any", "HUMAN_APPROVAL",
                                   "human approval", "signature"])
def test_a_demand_this_build_has_no_behaviour_for_is_refused(value):
    """Case included, and `signature` deliberately among them: nothing here
    signs anything, and a vocabulary that admitted the word would invite a
    reader to believe otherwise."""
    with pytest.raises(ContractError, match="harder to give"):
        settled_success_requires(value)


@pytest.mark.parametrize("value", [1, True, [], {}, ["human_approval"]])
def test_a_demand_that_is_not_text_is_refused_before_it_is_compared(value):
    with pytest.raises(ContractError, match="is text, or nothing at all"):
        settled_success_requires(value)


# -- 2. only a gate, in each contract's own words -----------------------------


@pytest.mark.parametrize("kind,extra", [
    ("task", {}),
    ("loop", {"loop": {"bound": 2, "back_to": "gate"}}),
])
def test_a_definition_step_that_is_not_a_gate_may_name_no_demand(kind, extra):
    with pytest.raises(ContractError, match="only a gate is answered by a"):
        GraphNode(node_id="n", kind=kind, title="N",
                  success_requires=DEMAND, **extra)


def test_the_definition_refusal_names_the_kind_it_actually_found():
    """A person is told which of the two things to change."""
    with pytest.raises(ContractError) as refusal:
        GraphNode(node_id="n", kind="task", title="N", success_requires=DEMAND)

    assert "is a task and names a gate success requirement" in str(refusal.value)


def test_a_gate_may_name_it():
    assert a_gate(success_requires=DEMAND).success_requires == DEMAND


@pytest.mark.parametrize("kind", ["task", "loop"])
def test_a_template_step_that_is_not_a_gate_may_name_no_demand(kind):
    """The TEMPLATE's own words, and its own half of the fact.

    Both layers refuse this, so a witness matching only what they share would
    pass on a build whose template rule had been deleted -- the green survivor
    the failure-policy slice shipped and had to correct. This asks for the half
    only this layer says, and the next witness asserts the other layer's
    sentence is absent from it.
    """
    extra = {"loop": {"bound": 2, "back_to": "n"}} if kind == "loop" else {}
    with pytest.raises(TemplateError) as refusal:
        TemplateNode(node_id="n", kind=kind, title="N",
                     success_requires=DEMAND, **extra)

    said = str(refusal.value)
    assert f"is a {kind!r}, not a gate" in said, said


def test_the_template_refusal_is_its_own_and_not_the_definitions_leaking():
    with pytest.raises(TemplateError) as refusal:
        TemplateNode(node_id="n", kind="task", title="N",
                     success_requires=DEMAND)

    assert "is a task and names a gate" not in str(refusal.value)


# -- 3. the shipped bytes do not move -----------------------------------------


def test_a_plan_naming_no_demand_writes_no_key_and_moves_no_digest():
    silent = GraphDefinition(graph_id="g", run_id=RUN_ID, created_at=NOW,
                             nodes=(a_gate(),), edges=())
    demanding = GraphDefinition(graph_id="g", run_id=RUN_ID, created_at=NOW,
                                nodes=(a_gate(success_requires=DEMAND),),
                                edges=())

    assert "success_requires" not in silent.nodes[0].as_dict()
    assert demanding.nodes[0].as_dict()["success_requires"] == DEMAND
    assert silent.digest() != demanding.digest()


def test_a_document_writing_an_explicit_null_is_not_the_canonical_spelling():
    written = {**a_gate().as_dict(), "success_requires": None}

    rebuilt = GraphNode.from_dict(written)

    assert rebuilt.success_requires is None
    assert "success_requires" not in rebuilt.as_dict()
    assert TemplateNode.from_dict(
        {"node_id": "g", "kind": "gate", "title": "G", "gate_id": "gate-1",
         "resources": [], "success_requires": None}).success_requires is None


@pytest.mark.parametrize("starter", STARTERS)
def test_a_shipped_starter_demands_nothing_and_digests_as_it_always_did(starter):
    """Asked of the CONTRACT's own rendering rather than the file on disk: the
    file cannot change by adding a field here, but the RENDERER can."""
    from tests.test_alpha6_dalio_revision import (
        REVISION_ONE_DIGEST,
        REVISION_THREE_DIGEST,
        REVISION_TWO_DIGEST,
    )

    pinned = {"dalio-v1": REVISION_ONE_DIGEST, "dalio-v2": REVISION_TWO_DIGEST,
              "dalio-v3": REVISION_THREE_DIGEST}[starter]
    template = load_template(starter)
    assert [node.success_requires for node in template.nodes] == (
        [None] * len(template.nodes))
    rendered = template.as_dict()
    assert all("success_requires" not in node for node in rendered["nodes"])
    assert hashlib.sha256(
        canonical_json(rendered).encode("utf-8")).hexdigest() == pinned, (
        f"{starter} no longer renders the document it was reviewed with")


def test_the_shipped_starters_really_carry_gates_and_this_is_not_vacuous():
    """The control on the measurement above: a starter with no gate would
    satisfy it while proving nothing about gates."""
    gates = [node.node_id for node in load_template("dalio-v3").nodes
             if node.kind == "gate"]

    assert len(gates) >= 2, gates


# -- 4. the road from a drawing to a frozen plan ------------------------------


def a_drawing(gate: dict) -> dict:
    return {"schema_version": 1, "title": "One protected gate",
            "nodes": [gate,
                      {"kind": "task", "node_id": "do", "title": "Do the work",
                       "stage": "do", "role_id": "role-implementer",
                       "capability": "dispatch",
                       "arguments": {"work_item_id": "work-001",
                                     "instruction_ref": "instruction-plan",
                                     "profile": "implement",
                                     "artifact_refs": ["artifact-plan"],
                                     "output_limit_profile": "normal"},
                       "resources": []}],
            "edges": [{"from_node": "confirm-gate", "to_node": "do"}]}


def test_the_demand_survives_the_road_from_a_drawing_to_a_frozen_plan():
    """Draft, publish, materialize -- and into the plan's own BYTES."""
    document = parse_document(a_drawing({
        "kind": "gate", "node_id": "confirm-gate", "title": "Human gate",
        "gate_id": "gate-confirm-do", "resources": [],
        "success_requires": DEMAND}))
    assert document["nodes"][0]["success_requires"] == DEMAND

    template = publish_candidate(document, workflow_id="flow", revision=1)
    assert next(row for row in template.steps()
                if row.node_id == "confirm-gate").success_requires == DEMAND

    plan = materialize(
        template, RunBinding(assignments={"role-implementer": "solo"}),
        SOLO, graph_id="graph-001", run_id=RUN_ID, created_at=NOW)
    frozen = next(row for row in plan.nodes if row.node_id == "confirm-gate")
    assert frozen.success_requires == DEMAND
    assert frozen.as_dict()["success_requires"] == DEMAND


def test_a_draft_naming_a_word_this_build_cannot_store_is_refused_at_the_door():
    with pytest.raises(ContractError, match="harder to give"):
        parse_document(a_drawing({
            "kind": "gate", "node_id": "confirm-gate", "title": "Human gate",
            "gate_id": "gate-confirm-do", "resources": [],
            "success_requires": "optional"}))


def test_the_field_round_trips_through_each_contracts_own_spelling():
    for node in (a_gate(success_requires=DEMAND),
                 TemplateNode(node_id="g", kind="gate", title="G",
                              gate_id="gate-1", success_requires=DEMAND)):
        rebuilt = type(node).from_dict(node.as_dict())
        assert rebuilt.success_requires == DEMAND
        assert rebuilt.as_dict() == node.as_dict()


def test_both_rebuilds_carry_the_demand():
    """A rebuild re-validates every field, so one it forgets is one the store
    silently drops from a plan a run is already following."""
    assert _rebuilt_node(a_gate(success_requires=DEMAND)).success_requires == (
        DEMAND)
    assert _rebuilt_template_node(
        TemplateNode(node_id="g", kind="gate", title="G", gate_id="gate-1",
                     success_requires=DEMAND)).success_requires == DEMAND


# -- 5. the dead road, refused where the workflow is published ----------------


def test_a_waived_road_out_of_a_protected_gate_is_refused():
    """A road nobody could ever travel is a road a reader will believe in.

    The same category as the capability-less rule beside it: that one refuses a
    condition no step could ever produce, and this refuses the one word THIS
    gate can never produce.
    """
    with pytest.raises(ContractError) as refusal:
        a_plan(waived_road=True)

    said = str(refusal.value)
    assert "can therefore never be waived" in said, said
    assert "no run could ever travel" in said, said


def test_the_same_road_is_legal_out_of_a_gate_that_may_be_waived():
    """The discriminating control: the demand is what closes the road, not the
    road's own shape."""
    plan = a_plan(demand=None, waived_road=True)

    assert [edge.condition for edge in plan.edges] == ["on_approved",
                                                       "on_waived"]


def test_the_same_refusal_reaches_a_person_where_the_workflow_is_published():
    """It is the DRAFT road that matters: refusing at publish is the last
    moment somebody can still fix the drawing."""
    document = parse_document({
        "schema_version": 1, "title": "Dead road",
        "nodes": [
            {"kind": "gate", "node_id": "g", "title": "Gate",
             "gate_id": "gate-1", "resources": [], "success_requires": DEMAND},
            {"kind": "task", "node_id": "a", "title": "A", "resources": []},
            {"kind": "task", "node_id": "b", "title": "B", "resources": []}],
        "edges": [{"from_node": "g", "to_node": "a", "condition": "on_approved"},
                  {"from_node": "g", "to_node": "b", "condition": "on_waived"}]})

    from conductor.command.workflow_draft import DraftRefused

    with pytest.raises(DraftRefused) as refusal:
        publish_candidate(document, workflow_id="flow", revision=1)

    # The publish road EXPLAINS rather than re-raising: a well-formed draft that
    # does not yet construct a revision comes back as structured rows, so the
    # reason a person is shown is the diagnostic and not the wrapper sentence.
    rows = refusal.value.diagnostics
    # `template_refused`, because it is the template's own PROBE
    # materialization that meets the dead road first: a `GraphTemplate` proves
    # itself by building one, so a workflow that could not produce a runnable
    # plan is refused before any revision exists to carry it.
    assert [row["code"] for row in rows] == ["template_refused"], rows
    assert "no run could ever travel" in rows[0]["message"], rows
    assert "can therefore never be waived" in rows[0]["message"], rows


# -- 6. the one reading both doors spend --------------------------------------


def a_store(tmp_path, *, demand=DEMAND):
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    store.append(a_plan(demand=demand))
    return store


def test_the_reading_answers_for_the_gate_the_plan_protects(tmp_path):
    recovered = a_store(tmp_path).read(RUN_ID)

    assert gate_refuses_waiver(recovered, "gate-1") is True
    assert gate_refuses_waiver(recovered, "gate-nobody-planned") is False


def test_the_reading_answers_no_for_a_gate_the_plan_leaves_waivable(tmp_path):
    recovered = a_store(tmp_path, demand=None).read(RUN_ID)

    assert gate_refuses_waiver(recovered, "gate-1") is False


def test_a_run_that_follows_no_plan_protects_nothing(tmp_path):
    """A journal written before graphs existed must go on replaying, and there
    is no gate in it to protect."""
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)

    assert gate_refuses_waiver(store.read(RUN_ID), "gate-1") is False


# -- 7. the live door: refused before anything is written ---------------------


def _api_over(tmp_path):
    from tests.test_command_graph_route import an_api_over

    return an_api_over(tmp_path, adapters=[])


def _decision(action, **changes):
    from tests.test_command_http_api import decision_body

    body = {"receipt_id": f"receipt-{action}", "gate_id": "gate-1",
            "action": action, "actor": "release-owner",
            "reason": "Reviewed the durable result."}
    body.update(changes)
    return decision_body(**body)


def _post(subject, body):
    from tests.test_command_http_api import post

    return post(subject, f"/command/runs/{RUN_ID}/decisions", body)


def _journal(store):
    return (store.run_path(RUN_ID) / "records.jsonl").read_bytes()


def test_the_server_refuses_a_waiver_and_the_run_does_not_move(tmp_path):
    """Refused BEFORE the append, so the whole of what the run records about
    the attempt is nothing: the journal bytes are identical either side."""
    from conductor.command.api_contracts import ERROR_STATUS

    store = a_store(tmp_path)
    subject = _api_over(tmp_path)
    before = _journal(store)

    refused = _post(subject, _decision("waive"))

    assert refused.status == ERROR_STATUS["service_refused"]
    error = refused.payload["error"]
    assert error["code"] == "service_refused"
    assert "requires explicit human approval and cannot be waived" in (
        error["message"])
    assert error["detail"]["gate_id"] == "gate-1"
    assert _journal(store) == before


@pytest.mark.parametrize("action", STILL_LEGAL)
def test_every_other_answer_stays_legal_on_the_very_same_gate(
        action, tmp_path):
    """The positive controls, and they carry the ruling: this makes a gate
    harder to PASS, never harder to fail. Driven on the same protected gate, so
    a build that refused every decision would fail here."""
    store = a_store(tmp_path)
    subject = _api_over(tmp_path)

    answered = _post(subject, _decision(action))

    assert answered.status == 201, answered.payload
    assert [row.kind for row in store.read(RUN_ID).records][-1] == "decision"


def test_a_waiver_is_accepted_on_a_gate_the_plan_leaves_waivable(tmp_path):
    """The discriminating control on the live road: the demand is what refuses
    the waiver, not the route refusing waivers generally."""
    store = a_store(tmp_path, demand=None)
    subject = _api_over(tmp_path)

    answered = _post(subject, _decision("waive"))

    assert answered.status == 201, answered.payload
    assert [row.kind for row in store.read(RUN_ID).records][-1] == "decision"


# -- 8. the replay door: bytes written around the server ----------------------


def test_a_forged_journal_carrying_a_waiver_is_refused_when_it_is_read(
        tmp_path):
    """The half that makes this a property of the RECORD.

    The waiver is written while the plan says the gate may be waived, and the
    PLAN is then forged to demand approval -- which is the shape somebody would
    reach for to make a protected gate look waived. The read refuses it.
    """
    store = a_store(tmp_path, demand=None)
    subject = _api_over(tmp_path)
    assert _post(subject, _decision("waive")).status == 201
    path = store.run_path(RUN_ID) / "records.jsonl"
    forged = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["record_type"] == "graph_definition":
            for node in row["record"]["nodes"]:
                if node.get("gate_id") == "gate-1":
                    node["success_requires"] = DEMAND
        forged.append(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")))
    path.write_text("\n".join(forged) + "\n", encoding="utf-8", newline="\n")

    with pytest.raises(StoreError, match="requires explicit human approval"):
        RunStore(tmp_path).read(RUN_ID)


def test_the_untouched_journal_still_replays(tmp_path):
    """The control on the forgery: the same run, unforged, reads cleanly -- so
    the refusal above is about the edit and not about the journal's shape."""
    store = a_store(tmp_path, demand=None)
    subject = _api_over(tmp_path)
    assert _post(subject, _decision("waive")).status == 201

    recovered = RunStore(tmp_path).read(RUN_ID)

    assert recovered.warnings == ()
    assert [row.kind for row in recovered.records] == [
        "graph_definition", "decision"]
