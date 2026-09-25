"""The Dalio template's own rules, held apart from what every graph must be.

These relations used to live inside ``GraphDefinition``, which made the default
template the only topology the product could express -- Codex composed an
ordinary three-node graph and the contract refused it for missing stages it had
no reason to want. The rules did not go away; they moved to where a caller can
ask for them.

So each test below has a twin in ``test_command_graph_definition``: the base
contract ACCEPTS the graph this module refuses, because refusing it is a
template's opinion and not a contract's law.
"""
from __future__ import annotations

import pytest

from conductor.command.contracts import ContractError
from conductor.command.graph_dalio import (
    DalioTemplateError,
    is_dalio_correction_template,
    is_dalio_template,
    validate_dalio_correction_template,
    validate_dalio_template,
)
from conductor.command.graph_definition import (
    DALIO_STAGES,
    GraphDefinition,
    GraphEdge,
    GraphLoop,
    GraphNode,
)
from tests.alpha3_graph_artifacts import (
    DISPATCH,
    INSTANCE_ID,
    dalio_definition,
    dalio_edges,
    dalio_nodes,
)


def a_task(node_id, title, stage, capability="evidence", **changes):
    body = dict(node_id=node_id, kind="task", title=title, stage=stage,
                instance_id=INSTANCE_ID, capability=capability)
    body.update(changes)
    return GraphNode(**body)


def without(nodes, *node_ids):
    return tuple(node for node in nodes if node.node_id not in node_ids)


def edges_clear_of(*node_ids):
    dropped = set(node_ids)
    return tuple(edge for edge in dalio_edges()
                 if not {edge.from_node, edge.to_node} & dropped)


def test_the_canonical_graph_is_the_template_it_claims_to_be():
    graph = validate_dalio_template(dalio_definition())
    assert graph is dalio_definition() or graph.digest() == dalio_definition().digest()
    assert is_dalio_template(graph) is True


def test_a_template_error_is_a_contract_error_a_caller_can_catch_broadly():
    assert issubclass(DalioTemplateError, ContractError)


@pytest.mark.parametrize("stage", DALIO_STAGES)
def test_every_stage_must_be_present_for_the_template(stage):
    """What goes with the victim, and why.

    Its edges go, or the base contract refuses an edge to a node that is not
    there. The loop goes too, because its `back_to` names Identify and the base
    contract refuses a loop that reopens a node the graph no longer carries.
    Both refusals would prove nothing about stages, so neither is allowed to
    fire: the template's own `_staged` check is what speaks here.
    """
    victim = dalio_definition().stage_node(stage).node_id
    partial = dalio_definition(nodes=without(dalio_nodes(), victim, "retry-loop"),
                               edges=edges_clear_of(victim, "retry-loop"))
    assert is_dalio_template(partial) is False
    with pytest.raises(DalioTemplateError, match="missing stage node"):
        validate_dalio_template(partial)


def test_two_nodes_may_not_claim_one_stage_in_the_template():
    shared = dalio_definition(nodes=dalio_nodes() + (
        a_task("goal-2", "Goal again", "goal"),))
    with pytest.raises(DalioTemplateError, match="more than one node"):
        validate_dalio_template(shared)


def test_the_template_turns_problems_into_progress_through_exactly_one_loop():
    two = dalio_definition(nodes=dalio_nodes() + (
        GraphNode(node_id="loop-2", kind="loop", title="L2",
                  loop=GraphLoop(bound=2, back_to="identify")),))
    with pytest.raises(DalioTemplateError, match="carries 2 loops"):
        validate_dalio_template(two)
    none = dalio_definition(nodes=without(dalio_nodes(), "retry-loop"),
                            edges=edges_clear_of("retry-loop"))
    with pytest.raises(DalioTemplateError, match="carries 0 loops"):
        validate_dalio_template(none)


def test_the_templates_loop_returns_to_identify_and_nowhere_else():
    elsewhere = dalio_definition(nodes=without(dalio_nodes(), "retry-loop") + (
        GraphNode(node_id="retry-loop", kind="loop", title="L",
                  loop=GraphLoop(bound=3, back_to="diagnose")),))
    with pytest.raises(DalioTemplateError, match="where problems are found again"):
        validate_dalio_template(elsewhere)


def test_only_the_do_node_acts_in_the_template():
    acting = dalio_definition(
        nodes=without(dalio_nodes(), "goal") + (
            a_task("goal", "Goal", "goal", capability=DISPATCH),
            GraphNode(node_id="goal-gate", kind="gate", title="Gate before Goal",
                      gate_id="gate-goal")),
        edges=dalio_edges() + (
            GraphEdge(from_node="goal-gate", to_node="goal"),))
    with pytest.raises(DalioTemplateError, match="only the 'do' stage node"):
        validate_dalio_template(acting)


def test_the_base_contract_accepts_every_graph_this_module_refuses():
    """The twin of each refusal above: a template's opinion is not a law.

    Each of these is built through ``GraphDefinition`` without raising, which is
    the whole point of moving the template out: the product builds graphs that
    are not Dalio, and they are no less valid for it.
    """
    victim = dalio_definition().stage_node("diagnose").node_id
    assert dalio_definition(nodes=without(dalio_nodes(), victim),
                            edges=edges_clear_of(victim)).stages()
    assert dalio_definition(nodes=dalio_nodes() + (
        a_task("goal-2", "Goal again", "goal"),)).stages()["goal"] == (
        "goal", "goal-2")
    assert len(dalio_definition(nodes=dalio_nodes() + (
        GraphNode(node_id="loop-2", kind="loop", title="L2",
                  loop=GraphLoop(bound=2, back_to="identify")),)).nodes) == 9


def test_the_template_validates_exactly_a_definition_and_not_a_subclass():
    class _Hostile(GraphDefinition):
        def stages(self):
            return {stage: (stage,) for stage in DALIO_STAGES}

    base = dalio_definition()
    hostile = _Hostile(graph_id=base.graph_id, run_id=base.run_id,
                       created_at=base.created_at, nodes=base.nodes,
                       edges=base.edges)
    with pytest.raises(DalioTemplateError, match="exactly a GraphDefinition"):
        validate_dalio_template(hostile)


# -- revision 5: the corrected template, held to its own check ---------------------------------


def shipped(name):
    """A shipped template materialized onto two instances, as a run would materialize it."""
    from conductor.command.graph_template import RunBinding, load_template, materialize

    template = load_template(name)
    config = {"instances": [{"id": "doer", "adapter": "claude-code"},
                            {"id": "checker", "adapter": "codex-cli"}]}
    return materialize(template, RunBinding(assignments={
        role: "checker" if role == "role-checker" else "doer" for role in template.roles}),
        config, graph_id="graph-shipped", run_id="run-shipped", created_at="2026-09-23T00:00:00Z")


def test_revision_five_is_the_corrected_template_and_revision_four_keeps_the_one_loop_shape():
    five, four = shipped("dalio-v5"), shipped("dalio-v4")
    assert validate_dalio_correction_template(five) is five
    assert is_dalio_template(five) is False, "the one-loop check was widened to admit revision 5"
    assert validate_dalio_template(four) is four
    assert is_dalio_correction_template(four) is False


def _changed(edit):
    """The shipped revision-5 document, edited, then materialized through the same contract."""
    import copy

    from conductor.command.graph_template import GraphTemplate, RunBinding, load_template, materialize

    document = copy.deepcopy(load_template("dalio-v5").as_dict())
    edit(document)
    template = GraphTemplate.from_dict(document)
    config = {"instances": [{"id": "doer", "adapter": "claude-code"},
                            {"id": "checker", "adapter": "codex-cli"}]}
    return materialize(template, RunBinding(assignments={
        role: "checker" if role == "role-checker" else "doer" for role in template.roles}),
        config, graph_id="graph-changed", run_id="run-changed", created_at="2026-09-23T00:00:00Z")


def _edge(document, pair):
    return next(edge for edge in document["edges"] if (edge["from_node"], edge["to_node"]) == pair)


def _node(document, node_id):
    return next(node for node in document["nodes"] if node["node_id"] == node_id)


def _second_road(document, from_node, to_node, condition, existing_condition):
    """Give a step a second, conditional road; its existing road is made conditional too (contract)."""
    for edge in document["edges"]:
        if edge["from_node"] == from_node:
            edge["condition"] = existing_condition
    document["edges"].append({"from_node": from_node, "to_node": to_node, "condition": condition})


def _swap_do_roads(document):
    _edge(document, ("do", "result-gate"))["condition"] = "on_failed"
    _edge(document, ("do", "correct"))["condition"] = "on_succeeded"


SABOTAGES = {
    "correction_allows_no_second_pass": lambda d: _node(d, "correct")["loop"].update(bound=1),
    "correction_home_is_design": lambda d: _node(d, "correct")["loop"].update(back_to="design"),
    "correction_reached_from_design": lambda d: _second_road(d, "design", "correct", "on_failed", "on_succeeded"),
    "outer_loop_reached_by_a_task": lambda d: _second_road(d, "identify", "retry-loop", "on_failed", "on_succeeded"),
    "success_and_failure_roads_swapped": _swap_do_roads,
}


@pytest.mark.parametrize("sabotage", sorted(SABOTAGES))
def test_the_corrected_template_refuses_every_other_shape(sabotage):
    """Each graph below is one the BASE contract accepts; only the corrected template's check refuses it."""
    changed = _changed(SABOTAGES[sabotage])
    with pytest.raises(DalioTemplateError):
        validate_dalio_correction_template(changed)
    assert is_dalio_correction_template(changed) is False
