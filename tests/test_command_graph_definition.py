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
    EFFECTING_CAPABILITIES,
    MAX_RESOURCES,
    RUNTIME_ONLY_FIELDS,
    GraphDefinition,
    GraphEdge,
    GraphLoop,
    GraphNode,
    GraphResource,
)
from tests.graph_loop_corpus import (
    CARRIED as LOOP_CARRIED,
    IDS as LOOP_IDS,
    LOOP_NODE,
    PARAMS as LOOP_PARAMS,
)
from tests.alpha3_graph_artifacts import (
    ARTIFACTS,
    DISPATCH,
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
    assert graph.stages() == {stage: (stage,) for stage in DALIO_STAGES}
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



def test_the_contract_and_the_runtime_spell_the_effecting_capability_alike():
    """A contract module may not import an adapter, so a test holds them equal."""
    assert EFFECTING_CAPABILITIES == {DISPATCH_CAPABILITY}


def test_every_road_into_the_effect_node_passes_through_a_gate():
    with pytest.raises(ContractError, match="without a gate"):
        dalio(edges=dalio_edges() + (GraphEdge(from_node="design", to_node="do"),))


def test_an_effect_node_no_road_reaches_is_refused_rather_than_stranded():
    with pytest.raises(ContractError, match="no road reaches it"):
        dalio(edges=edges_clear_of("do"))


# -- the shape: one cycle, and it is not an edge -------------------------------


def test_the_edge_set_is_a_dag_and_says_so_when_it_is_not():
    with pytest.raises(ContractError, match="form a cycle"):
        dalio(edges=dalio_edges() + (
            GraphEdge(from_node="retry-loop", to_node="identify"),))




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




def test_a_gate_or_a_loop_carries_no_stage():
    for kind, extra in (("gate", {"gate_id": "gate-x"}),
                        ("loop", {"loop": GraphLoop(bound=2, back_to="identify")})):
        with pytest.raises(ContractError, match="must not name a stage"):
            GraphNode(node_id="n", kind=kind, title="N", stage="goal", **extra)



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


# -- the base contract is a graph contract, not the Dalio template -------------


def a_custom_graph(**changes):
    """An ordinary, correct graph that is not Dalio in any way.

    Codex composed one and the contract refused it -- `CUSTOM_GRAPH_REFUSED
    graph is missing stage node(s) [...]` -- because the default template had
    been folded into the base type. The product exists to build different
    multi-harness graphs, so this shape must be as valid as the default one.
    """
    nodes = (
        GraphNode(node_id="collect", kind="task", title="Collect",
                  instance_id=INSTANCE, capability="evidence"),
        GraphNode(node_id="gate", kind="gate", title="Human Gate", gate_id="gate-1"),
        GraphNode(node_id="apply", kind="task", title="Apply",
                  instance_id=INSTANCE, capability=DISPATCH),
    )
    edges = (GraphEdge(from_node="collect", to_node="gate"),
             GraphEdge(from_node="gate", to_node="apply"))
    body = dict(graph_id="g-custom", run_id="run-001",
                created_at="2026-08-19T09:00:00Z", nodes=nodes, edges=edges)
    body.update(changes)
    return GraphDefinition(**body)


def test_a_graph_that_is_not_the_dalio_template_is_still_a_graph():
    graph = a_custom_graph()
    assert graph.stages() == {}, "no node claims a stage, and none has to"
    assert [node.node_id for node in graph.nodes if node.effecting] == ["apply"]


def test_a_task_may_belong_to_no_stage_at_all():
    node = GraphNode(node_id="n", kind="task", title="N")
    assert node.stage is None


def test_several_nodes_may_share_one_stage():
    graph = a_custom_graph(nodes=(
        GraphNode(node_id="collect", kind="task", title="Collect", stage="identify"),
        GraphNode(node_id="also", kind="task", title="Also", stage="identify"),
        GraphNode(node_id="gate", kind="gate", title="G", gate_id="gate-1"),
        GraphNode(node_id="apply", kind="task", title="Apply",
                  instance_id=INSTANCE, capability=DISPATCH)))
    assert graph.stages() == {"identify": ("collect", "also")}
    with pytest.raises(ContractError, match="ask stages"):
        graph.stage_node("identify")


def test_a_graph_may_carry_several_bounded_loops():
    graph = a_custom_graph(nodes=a_custom_graph().nodes + (
        GraphNode(node_id="loop-a", kind="loop", title="A",
                  loop=GraphLoop(bound=2, back_to="collect")),
        GraphNode(node_id="loop-b", kind="loop", title="B",
                  loop=GraphLoop(bound=5, back_to="apply"))))
    assert sum(node.loop is not None for node in graph.nodes) == 2


def test_a_loop_may_only_reopen_a_node_the_graph_carries():
    with pytest.raises(ContractError, match="which this graph does not carry"):
        a_custom_graph(nodes=a_custom_graph().nodes + (
            GraphNode(node_id="loop-a", kind="loop", title="A",
                      loop=GraphLoop(bound=2, back_to="ghost")),))


def test_every_acting_node_is_gated_however_many_there_are():
    """The rule is a property of acting, not of one named node."""
    nodes = a_custom_graph().nodes + (
        GraphNode(node_id="gate-2", kind="gate", title="G2", gate_id="gate-2"),
        GraphNode(node_id="apply-2", kind="task", title="Apply again",
                  instance_id=INSTANCE, capability=DISPATCH))
    gated = a_custom_graph(nodes=nodes, edges=a_custom_graph().edges + (
        GraphEdge(from_node="apply", to_node="gate-2"),
        GraphEdge(from_node="gate-2", to_node="apply-2")))
    assert [node.node_id for node in gated.nodes if node.effecting] == [
        "apply", "apply-2"]
    with pytest.raises(ContractError, match="without a gate"):
        a_custom_graph(nodes=nodes, edges=a_custom_graph().edges + (
            GraphEdge(from_node="apply", to_node="apply-2"),))


# -- the split cannot be walked around ----------------------------------------


@pytest.mark.parametrize("smuggled", [
    {"note": {"pass": 2}},
    {"note": {"deeper": {"status": "succeeded"}}},
    {"note": [{"outcome": "succeeded"}]},
    {"note": [[{"attempt_ids": ["a"]}]]},
])
def test_a_runtime_word_cannot_ride_in_nested_inside_tolerant_extra(smuggled):
    """Codex read `NESTED_RUNTIME_ACCEPTED` and it had reached the digest.

    Checking one level was a promise the walk had to keep.
    """
    with pytest.raises(ContractError, match="runtime-only field"):
        dalio(extra=smuggled)


def test_the_exempt_subtree_is_arguments_and_only_arguments():
    node = a_task("do", "Do", "do", capability=DISPATCH,
                  arguments={"deep": {"status": "vendor's own word"}})
    assert node.arguments["deep"]["status"] == "vendor's own word"
    with pytest.raises(ContractError, match="runtime-only field"):
        GraphNode.from_dict({"node_id": "n", "kind": "task", "title": "T",
                             "resources": [{"kind": "model", "name": "m",
                                            "nested": {"phase": "idle"}}]})


class _HostileNode(GraphNode):
    def as_dict(self):
        out = super().as_dict()
        out["status"] = "succeeded"
        return out


def _hostile_of(base):
    return _HostileNode(
        node_id=base.node_id, kind=base.kind, title=base.title, stage=base.stage,
        instance_id=base.instance_id, capability=base.capability,
        arguments=dict(base.arguments), resources=base.resources,
        gate_id=base.gate_id, loop=base.loop)


def test_a_hostile_node_subclass_cannot_answer_for_itself():
    """Codex read `SUBCLASS_RUNTIME_ACCEPTED succeeded`, and into the digest."""
    hostile = tuple(_hostile_of(n) if n.node_id == "goal" else n
                    for n in dalio_nodes())
    with pytest.raises(ContractError, match="must be exactly GraphNode"):
        dalio(nodes=hostile)


def test_a_hostile_subclass_is_refused_at_every_typed_boundary():
    class _Edge(GraphEdge):
        pass

    class _Resource(GraphResource):
        pass

    class _Loop(GraphLoop):
        pass

    with pytest.raises(ContractError, match="must be exactly GraphEdge"):
        dalio(edges=(_Edge(from_node="goal", to_node="identify"),))
    with pytest.raises(ContractError, match="must be exactly GraphResource"):
        a_task("do", "Do", "do", resources=(_Resource(kind="model", name="m"),))
    with pytest.raises(ContractError, match="must be exactly GraphLoop"):
        GraphNode(node_id="l", kind="loop", title="L",
                  loop=_Loop(bound=2, back_to="identify"))


def test_a_node_edited_after_it_was_validated_is_rebuilt_and_refused():
    """Exact typing stops a subclass; the rebuild stops a later edit."""
    node = a_task("goal", "Goal", "goal")
    object.__setattr__(node, "stage", "not-a-stage")
    with pytest.raises(ContractError, match="stage"):
        dalio(nodes=(node,) + without(dalio_nodes(), "goal"))


@pytest.mark.parametrize("document,message", [
    ({"graph_id": "g", "run_id": "r", "created_at": "2026-08-19T09:00:00Z",
      "nodes": ()}, "graph nodes must be a JSON array"),
    ({"graph_id": "g", "run_id": "r", "created_at": "2026-08-19T09:00:00Z",
      "nodes": [], "edges": ()}, "graph edges must be a JSON array"),
])
def test_a_json_boundary_takes_arrays_and_not_python_tuples(document, message):
    """Codex read `TUPLE_AT_JSON_BOUNDARY_ACCEPTED`. A tuple came from Python."""
    with pytest.raises(ContractError, match=message):
        GraphDefinition.from_dict(document)


def test_node_resources_at_the_json_boundary_are_an_array_too():
    with pytest.raises(ContractError, match="node resources must be a JSON array"):
        GraphNode.from_dict({"node_id": "n", "kind": "task", "title": "T",
                             "resources": ()})


# -- the exemption belongs to a field, not to a name ---------------------------


def test_a_key_merely_named_arguments_is_nobodys_payload_and_is_scanned():
    """Codex: `NESTED_FAKE_ARGUMENTS_ACCEPTED {'arguments': {'status': ...}}`.

    The walk skipped any key spelled `arguments`, wherever it appeared, so a
    runtime word rode into tolerant metadata and into the digest. The exemption
    belongs to the ONE field whose value is a capability's payload, and the code
    that owns that field lifts it out before the walk runs.
    """
    with pytest.raises(ContractError, match="runtime-only field"):
        dalio(extra={"arguments": {"status": "succeeded"}})
    with pytest.raises(ContractError, match="runtime-only field"):
        dalio(extra={"note": {"arguments": {"phase": "idle"}}})


def test_the_real_payload_is_still_the_capabilitys_own_business():
    """The twin of the case above: the FIELD keeps its exemption."""
    node = GraphNode.from_dict({
        "node_id": "do", "kind": "task", "title": "Do", "stage": "do",
        "instance_id": INSTANCE, "capability": DISPATCH,
        "arguments": {"status": "the capability's own word", "deep": {"pass": 2}}})
    assert node.arguments["deep"]["pass"] == 2


# -- a hostile sequence says nothing of its own --------------------------------


class _HostileList(list):
    def __iter__(self):
        raise RuntimeError("APIKEY_SECRET_LIST")


def test_a_hostile_list_subclass_is_refused_before_anything_iterates_it():
    """Codex: `HOSTILE_LIST_ESCAPE RuntimeError APIKEY_SECRET_LIST`.

    `isinstance` let a `list` subclass through the JSON boundary, and its own
    exception -- and whatever the exception carried -- travelled outward as this
    contract's answer.
    """
    document = dalio().as_dict()
    document["nodes"] = _HostileList(document["nodes"])
    with pytest.raises(ContractError, match="graph nodes must be a JSON array") as caught:
        GraphDefinition.from_dict(document)
    assert "APIKEY_SECRET_LIST" not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_a_hostile_iterable_at_the_python_boundary_says_nothing_of_its_own():
    """The constructors take any sequence, so one that raises is the same class."""
    class _Hostile:
        def __iter__(self):
            raise RuntimeError("APIKEY_SECRET_ITER")

    for changes in ({"nodes": _Hostile()}, {"edges": _Hostile()}):
        with pytest.raises(ContractError, match="could not be read as a sequence") as e:
            dalio(**changes)
        assert "APIKEY_SECRET_ITER" not in str(e.value)
    with pytest.raises(ContractError, match="could not be read as a sequence"):
        a_task("do", "Do", "do", resources=_Hostile())


# -- where a loop may send work back to: one corpus, both sides ----------------


def a_looping_graph(back_to):
    """The graph the shared corpus is read against."""
    nodes = (
        GraphNode(node_id="alpha", kind="task", title="Alpha"),
        GraphNode(node_id="beta", kind="task", title="Beta"),
        GraphNode(node_id="gate", kind="gate", title="Gate", gate_id="gate-1"),
        GraphNode(node_id="apply", kind="task", title="Apply",
                  instance_id=INSTANCE, capability=DISPATCH),
        GraphNode(node_id="loop-other", kind="loop", title="Other loop",
                  loop=GraphLoop(bound=2, back_to="alpha")),
        GraphNode(node_id=LOOP_NODE, kind="loop", title="Loop under test",
                  loop=GraphLoop(bound=3, back_to=back_to)),
    )
    return GraphDefinition(
        graph_id="g-loop", run_id="run-001", created_at="2026-08-19T09:00:00Z",
        nodes=nodes, edges=(GraphEdge(from_node="alpha", to_node="beta"),
                            GraphEdge(from_node="beta", to_node="gate"),
                            GraphEdge(from_node="gate", to_node="apply")))


@pytest.mark.parametrize("back_to,accepted", LOOP_PARAMS, ids=LOOP_IDS)
def test_the_backend_answers_the_shared_loop_corpus(back_to, accepted):
    """The Cockpit reads the same rows; a disagreement is a graph nobody can use.

    The self-target row is the one that found this: the backend accepted a loop
    that reopens itself while `graph-store.js` had always called it corrupt, so
    a Human could have composed a plan, watched it persist, and then been shown
    a broken graph.
    """
    if accepted:
        graph = a_looping_graph(back_to)
        loop = [node for node in graph.nodes if node.node_id == LOOP_NODE][0]
        assert loop.loop.back_to == back_to
        return
    with pytest.raises(ContractError):
        a_looping_graph(back_to)


def test_the_corpus_names_the_nodes_the_graph_actually_carries():
    """A corpus whose accepted rows named absent nodes would prove nothing."""
    carried = {node.node_id for node in a_looping_graph("alpha").nodes}
    assert set(LOOP_CARRIED) | {LOOP_NODE} == carried


def test_a_loop_may_still_reopen_any_other_node_including_another_loop():
    graph = a_looping_graph("loop-other")
    assert sum(node.loop is not None for node in graph.nodes) == 2
