"""What a graph definition IS, and every runtime word it refuses to become.

The canonical Dalio graph is built by ``tests/alpha3_graph_artifacts`` through
the production contract, and the fixture handed to the UI lane is derived from
that build rather than typed by hand -- so the fixture cannot drift from the
contract that produced it. This module re-derives it on every run and pins the
result, then spends the rest of its length on what the contract REFUSES.

Each refusal below is written so the relation it names is the one that fires.
Dropping a stage node also orphans its edges, for instance, and an "edge names
an unknown node" refusal would prove nothing about stages; those cases remove
the edges too, so the stage rule is what speaks.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.adapters.process import DISPATCH_CAPABILITY
from conductor.command.contracts import ContractError, canonical_json
from conductor.command.graph_definition import (
    DALIO_STAGES,
    EFFECT_STAGE,
    EFFECTING_CAPABILITIES,
    FEEDBACK_STAGE,
    MAX_RESOURCES,
    RUNTIME_ONLY_FIELDS,
    GraphDefinition,
    GraphEdge,
    GraphLoop,
    GraphNode,
    GraphResource,
)
from tests.alpha3_graph_artifacts import (
    ARTIFACTS,
    INSTANCE_ID,
    dalio_definition,
    dalio_edges,
    dalio_nodes,
    derive_all,
    load,
)

INSTANCE = INSTANCE_ID
dalio = dalio_definition


def a_task(node_id, title, stage, capability="evidence", **changes):
    body = dict(node_id=node_id, kind="task", title=title, stage=stage,
                instance_id=INSTANCE, capability=capability)
    body.update(changes)
    return GraphNode(**body)


def without(nodes, *node_ids):
    return tuple(node for node in nodes if node.node_id not in node_ids)


def edges_clear_of(*node_ids):
    dropped = set(node_ids)
    return tuple(edge for edge in dalio_edges()
                 if not {edge.from_node, edge.to_node} & dropped)


# -- the canonical graph, and the fixture derived from it ----------------------


def test_the_canonical_dalio_graph_is_accepted_whole():
    graph = dalio()
    assert [node.stage for node in graph.nodes if node.stage] == list(DALIO_STAGES)
    assert graph.stage_node(EFFECT_STAGE).node_id == "do"
    assert graph.stage_node(FEEDBACK_STAGE).node_id == "identify"
    assert sum(node.loop is not None for node in graph.nodes) == 1
    assert [node.node_id for node in graph.nodes if node.effecting] == ["do"]


def test_a_definition_survives_its_own_canonical_json_unchanged():
    graph = dalio()
    recovered = GraphDefinition.from_dict(json.loads(canonical_json(graph)))
    assert recovered.as_dict() == graph.as_dict()
    assert recovered.digest() == graph.digest()


def test_the_digest_moves_with_the_plan_and_not_with_its_spelling():
    graph = dalio()
    reordered = GraphDefinition.from_dict(dict(reversed(list(graph.as_dict().items()))))
    assert reordered.digest() == graph.digest(), "key order is not a plan change"
    louder = dalio(nodes=without(dalio_nodes(), "retry-loop") + (
        GraphNode(node_id="retry-loop", kind="loop", title="Turn problems into progress",
                  loop=GraphLoop(bound=4, back_to="identify")),))
    assert louder.digest() != graph.digest(), "a changed bound is a changed plan"


@pytest.mark.parametrize("name", ARTIFACTS)
def test_a_frozen_artifact_still_equals_what_this_contract_produces(name):
    """Re-derived on every run: drift reds here, not in the UI lane's browser."""
    assert derive_all()[name] == load(name)


def test_the_frozen_document_carries_the_definition_and_its_own_digest():
    document = load("alpha3_dalio_definition")
    assert set(document) == {"_comment", "definition", "definition_digest"}
    recovered = GraphDefinition.from_dict(document["definition"])
    assert recovered.digest() == document["definition_digest"]


def test_the_frozen_document_carries_no_runtime_word_at_any_depth():
    """The split is what the UI lane is handed, so the fixture itself proves it."""
    found: list[str] = []

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in RUNTIME_ONLY_FIELDS:
                    found.append(key)
                if key != "arguments":
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(load("alpha3_dalio_definition")["definition"])
    assert found == [], f"the frozen definition carries runtime word(s) {found!r}"


# -- the two layers do not overlap --------------------------------------------


@pytest.mark.parametrize("word", sorted(RUNTIME_ONLY_FIELDS))
def test_no_runtime_word_can_be_carried_by_a_definition(word):
    """Every word that belongs to a run is refused as a field, at every level."""
    for document, build in (
            ("graph", lambda: dalio(extra={word: "x"})),
            ("node", lambda: GraphNode.from_dict(
                {"node_id": "n", "kind": "task", "title": "T", "stage": "goal",
                 word: "x"})),
            ("edge", lambda: GraphEdge.from_dict(
                {"from_node": "a", "to_node": "b", word: "x"})),
            ("resource", lambda: GraphResource.from_dict(
                {"kind": "model", "name": "m", word: "x"})),
            ("loop", lambda: GraphLoop.from_dict(
                {"bound": 3, "back_to": "identify", word: "x"})),
    ):
        with pytest.raises(ContractError, match="runtime-only field"):
            build()


def test_a_capability_payload_is_not_searched_for_runtime_words():
    """`arguments` is the capability's own closed schema, judged at its own door.

    Two doors judging one value is how they come to disagree, so this one proves
    the payload is canonical JSON and stops. A key that happens to read like a
    runtime word inside a vendor payload is not this contract's business.
    """
    node = a_task("do", "Do", "do", capability=DISPATCH_CAPABILITY,
                  arguments={"status": "whatever the capability means by it"})
    assert node.arguments["status"] == "whatever the capability means by it"


def test_arguments_must_be_canonical_json_data():
    with pytest.raises(ContractError):
        a_task("do", "Do", "do", capability=DISPATCH_CAPABILITY,
               arguments={"payload": {1, 2}})


# -- the effect road ----------------------------------------------------------


def test_only_the_do_stage_node_may_carry_an_effecting_capability():
    with pytest.raises(ContractError, match="only the 'do' stage node"):
        dalio(nodes=without(dalio_nodes(), "goal") + (
            a_task("goal", "Goal", "goal", capability=DISPATCH_CAPABILITY),))


def test_the_contract_and_the_runtime_spell_the_effecting_capability_alike():
    """A contract module may not import an adapter, so a test holds them equal."""
    assert EFFECTING_CAPABILITIES == {DISPATCH_CAPABILITY}


def test_every_road_into_the_effect_node_passes_through_a_gate():
    with pytest.raises(ContractError, match="without a gate"):
        dalio(edges=dalio_edges() + (GraphEdge(from_node="design", to_node="do"),))


def test_an_effect_node_no_road_reaches_is_refused_rather_than_stranded():
    with pytest.raises(ContractError, match="reachable from nowhere"):
        dalio(edges=edges_clear_of("do"))


# -- the shape: one cycle, and it is not an edge -------------------------------


def test_the_edge_set_is_a_dag_and_says_so_when_it_is_not():
    with pytest.raises(ContractError, match="form a cycle"):
        dalio(edges=dalio_edges() + (
            GraphEdge(from_node="retry-loop", to_node="identify"),))


def test_a_loop_returns_to_the_identify_stage_and_nowhere_else():
    with pytest.raises(ContractError, match="feedback relation"):
        dalio(nodes=without(dalio_nodes(), "retry-loop") + (
            GraphNode(node_id="retry-loop", kind="loop", title="L",
                      loop=GraphLoop(bound=3, back_to="diagnose")),))


def test_a_graph_carries_at_most_one_loop():
    with pytest.raises(ContractError, match="at most one loop"):
        dalio(nodes=dalio_nodes() + (
            GraphNode(node_id="loop-2", kind="loop", title="L2",
                      loop=GraphLoop(bound=2, back_to="identify")),))


@pytest.mark.parametrize("bound", [0, 100, -1, True, "3", 3.0])
def test_a_loop_bound_is_a_whole_number_of_passes_within_reach(bound):
    with pytest.raises(ContractError, match="loop bound"):
        GraphLoop(bound=bound, back_to="identify")


def test_an_edge_may_not_name_itself_on_both_ends():
    with pytest.raises(ContractError, match="names itself"):
        GraphEdge(from_node="goal", to_node="goal")


def test_an_edge_may_not_name_a_node_the_graph_does_not_carry():
    with pytest.raises(ContractError, match="unknown node"):
        dalio(edges=dalio_edges() + (GraphEdge(from_node="goal", to_node="ghost"),))


def test_a_graph_may_not_repeat_an_edge():
    with pytest.raises(ContractError, match="repeat a from/to pair"):
        dalio(edges=dalio_edges() + (GraphEdge(from_node="goal", to_node="identify"),))


# -- the five stages ----------------------------------------------------------


@pytest.mark.parametrize("stage", DALIO_STAGES)
def test_every_dalio_stage_must_be_present(stage):
    """The edges of the removed node go with it, so the STAGE rule is what fires."""
    victim = dalio().stage_node(stage).node_id
    with pytest.raises(ContractError, match="missing stage node"):
        dalio(nodes=without(dalio_nodes(), victim), edges=edges_clear_of(victim))


def test_two_nodes_may_not_claim_one_stage():
    with pytest.raises(ContractError, match="one node per stage"):
        dalio(nodes=dalio_nodes() + (a_task("goal-2", "Goal again", "goal"),))


def test_a_gate_or_a_loop_carries_no_stage():
    for kind, extra in (("gate", {"gate_id": "gate-x"}),
                        ("loop", {"loop": GraphLoop(bound=2, back_to="identify")})):
        with pytest.raises(ContractError, match="must not name a stage"):
            GraphNode(node_id="n", kind=kind, title="N", stage="goal", **extra)


def test_a_task_must_name_the_stage_it_belongs_to():
    with pytest.raises(ContractError, match="must name a stage"):
        GraphNode(node_id="n", kind="task", title="N")


# -- bindings and resources ---------------------------------------------------


def test_a_binding_is_whole_or_absent():
    for changes in ({"instance_id": INSTANCE}, {"capability": "evidence"}):
        with pytest.raises(ContractError, match="together or neither"):
            GraphNode(node_id="n", kind="task", title="N", stage="goal", **changes)


def test_arguments_without_a_capability_name_nobody_to_read_them():
    with pytest.raises(ContractError, match="no capability to read them"):
        GraphNode(node_id="n", kind="task", title="N", stage="goal",
                  arguments={"work_item_id": "work-001"})


def test_the_definition_never_names_the_provider_behind_an_instance():
    """The run's frozen config binds instance to adapter; a copy here could drift."""
    document = dalio().as_dict()
    spelled = canonical_json(document)
    assert "instance_id" in spelled
    for absent in ("provider_id", "adapter_id", "vendor", "executable"):
        assert absent not in spelled, f"{absent} is a second spelling of a binding"


@pytest.mark.parametrize("kind", ["gpu", "", "MODEL", None])
def test_a_resource_kind_outside_the_closed_vocabulary_is_refused(kind):
    with pytest.raises(ContractError, match="resource kind"):
        GraphResource(kind=kind, name="a")


def test_a_node_may_not_declare_more_resources_than_the_contract_carries():
    too_many = tuple(GraphResource(kind="tool", name=f"tool-{i}")
                     for i in range(MAX_RESOURCES + 1))
    with pytest.raises(ContractError, match="more than"):
        a_task("do", "Do", "do", resources=too_many)


def test_a_node_may_not_repeat_one_resource():
    twice = (GraphResource(kind="model", name="sonnet"),
             GraphResource(kind="model", name="sonnet"))
    with pytest.raises(ContractError, match="repeats a resource"):
        a_task("do", "Do", "do", resources=twice)


# -- identity and unknown fields ----------------------------------------------


def test_nodes_and_gates_carry_unique_identities():
    with pytest.raises(ContractError, match="repeat a node_id"):
        dalio(nodes=dalio_nodes() + (a_task("goal", "Twin", "identify"),))
    with pytest.raises(ContractError, match="repeat a gate_id"):
        dalio(nodes=dalio_nodes() + (
            GraphNode(node_id="gate-twin", kind="gate", title="Twin",
                      gate_id="gate-result"),))


@pytest.mark.parametrize("level,build", [
    ("node", lambda: GraphNode.from_dict(
        {"node_id": "n", "kind": "task", "title": "T", "stage": "goal", "extra": 1})),
    ("edge", lambda: GraphEdge.from_dict(
        {"from_node": "a", "to_node": "b", "weight": 1})),
    ("resource", lambda: GraphResource.from_dict(
        {"kind": "model", "name": "m", "size": 1})),
    ("loop", lambda: GraphLoop.from_dict(
        {"bound": 2, "back_to": "identify", "mode": "eager"})),
])
def test_an_unsupported_field_is_refused_rather_than_ignored(level, build):
    with pytest.raises(ContractError, match="unsupported field"):
        build()


def test_a_gate_names_its_gate_and_nothing_else_does():
    with pytest.raises(ContractError, match="must name a gate_id"):
        GraphNode(node_id="g", kind="gate", title="G")
    with pytest.raises(ContractError, match="must not name a gate_id"):
        GraphNode(node_id="t", kind="task", title="T", stage="goal",
                  gate_id="gate-x")


def test_only_a_loop_node_carries_a_loop():
    with pytest.raises(ContractError, match="must carry a GraphLoop"):
        GraphNode(node_id="l", kind="loop", title="L")
    with pytest.raises(ContractError, match="must not carry a loop"):
        GraphNode(node_id="t", kind="task", title="T", stage="goal",
                  loop=GraphLoop(bound=2, back_to="identify"))
