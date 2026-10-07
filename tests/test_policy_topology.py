"""Only a new marked workflow can trade per-step gates for bounded authority."""
from dataclasses import replace
import pytest

from conductor.command.contracts import ABSENT, ContractError, RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphNode, GraphEdge
from conductor.command.graph_template import GraphTemplate, TemplateNode, RunBinding, materialize
from conductor.command.run_store import RunStore, StoreError, snapshot_digest
from tests.test_policy_runtime import ARGS, NOW


def steps():
    return tuple(GraphNode(name, "task", name, instance_id="doer", capability="dispatch",
                           arguments=ARGS) for name in ("first", "next"))


def graph():
    return GraphDefinition("g", "run", NOW, nodes=steps(),
        edges=(GraphEdge("first", "next", "on_failed"),), execution_contract="bounded-run-v1")


def test_legacy_topology_still_requires_gates_bounded_has_explicit_marker():
    with pytest.raises(ContractError, match="gate"):
        GraphDefinition("g", "run", NOW, nodes=steps())
    value = graph()
    assert GraphDefinition.from_dict(value.as_dict()) == value
    with pytest.raises(ContractError, match="gate"):
        replace(value, execution_contract=ABSENT)


@pytest.mark.parametrize("marker", [None, "future", False])
def test_unknown_or_null_marker_does_not_relax_topology(marker):
    with pytest.raises(ContractError, match="execution_contract"):
        GraphDefinition.from_dict({**graph().as_dict(), "execution_contract": marker})


@pytest.mark.parametrize("mode,marked", [("confirm", True), ("policy", False)])
def test_direct_graph_append_cannot_opt_an_old_run_into_execution(tmp_path, mode, marked):
    config = {"cycle": {"id": "cycle"}, "instances": [{"id": "doer", "adapter": "claude-code"}],
              "workflow": {"id": "custom", "revision": 1}}
    if marked:
        config["automation_contract"] = "bounded-run-v1"
    store = RunStore(tmp_path)
    store.create_run(RunEnvelope("run", "cycle", NOW, snapshot_digest(config), mode=mode), config)
    before = store.read("run").records
    with pytest.raises(StoreError, match="opt-in"):
        store.append(graph())
    assert store.read("run").records == before


def test_template_round_trip_materialization_requires_frozen_opt_in():
    template = GraphTemplate("custom", 1, "Automatic", nodes=tuple(
        TemplateNode(name, "task", name, role_id="maker", capability="dispatch", arguments=ARGS)
        for name in ("first", "next")), edges=(GraphEdge("first", "next", "on_succeeded"),),
        execution_contract="bounded-run-v1")
    template = GraphTemplate.from_dict(template.as_dict())
    config = {"instances": [{"id": "doer", "adapter": "claude-code"}]}
    bound = RunBinding({"maker": "doer"})
    with pytest.raises(ContractError, match="Policy"):
        materialize(template, bound, config, graph_id="g", run_id="run", created_at=NOW)
    config["automation_contract"] = "bounded-run-v1"
    result = materialize(template, bound, config, graph_id="g", run_id="run", created_at=NOW)
    assert result.execution_contract == "bounded-run-v1"
    assert result.edges == template.edges and [n.node_id for n in result.nodes] == ["first", "next"]
