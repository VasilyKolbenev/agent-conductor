"""A plan written in roles, and the one door that turns it into a run's own.

Every claim here is made by building real values through the real contracts.
The template is the SHIPPED data file wherever one will do, because a fixture
written beside the test would only prove that two pieces of this file agree.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from conductor.command.contracts import ContractError

from tests import alpha4_role_artifacts
from conductor.command.graph_dalio import is_dalio_template
from conductor.command.graph_definition import (
    RUNTIME_ONLY_FIELDS,
    GraphDefinition,
    GraphEdge,
)
from conductor.command.graph_template import (
    DEPLOYMENT_ONLY_FIELDS,
    TEMPLATE_DIR,
    GraphTemplate,
    RunBinding,
    TemplateError,
    TemplateNode,
    load_template,
    materialize,
)

NOW = "2026-08-20T10:00:00Z"
#: What this build's available providers offer, as the runtime would hand it in.
SERVED = {
    "claude-code": ("observe", "review", "dispatch"),
    "codex": ("observe", "review", "dispatch"),
    "reviewer-only": ("observe", "review"),
}
#: Two instances of the SAME harness, told apart by configuration alone: the
#: adapter is one word, the instance is another, and a run binds roles to the
#: second. Nothing in a template, a binding or the materializer reads the first.
TWO_OF_ONE = {"instances": [
    {"id": "claude-primary", "adapter": "claude-code"},
    {"id": "claude-secondary", "adapter": "claude-code"},
]}
MIXED = {"instances": [
    {"id": "claude-dev", "adapter": "claude-code"},
    {"id": "codex-review", "adapter": "codex"},
    {"id": "reader", "adapter": "reviewer-only"},
]}
SOLO = {"instances": [{"id": "solo", "adapter": "claude-code"}]}


def dalio() -> GraphTemplate:
    return load_template("dalio-v1")


def spread(template: GraphTemplate) -> RunBinding:
    """Roles across two instances, with the acting role on the one that acts."""
    return RunBinding(assignments={
        "role-thinker": "codex-review", "role-diagnostician": "codex-review",
        "role-designer": "codex-review", "role-implementer": "claude-dev"})


def every_role_to(template: GraphTemplate, instance: str) -> RunBinding:
    return RunBinding(assignments={role: instance for role in template.roles})


def built(template: GraphTemplate, binding: RunBinding, config: dict,
          **changes: str) -> GraphDefinition:
    values = {"graph_id": "graph-run", "run_id": "run-001", "created_at": NOW}
    values.update(changes)
    return materialize(template, binding, config, SERVED, **values)


def test_the_default_cycle_ships_as_data_and_needs_no_code_to_read_it():
    """The file IS the cycle: it goes through the same door any file would."""
    template = dalio()
    assert template.template_id == "template-dalio" and template.revision == 1
    assert [node.node_id for node in template.nodes] == [
        "goal", "identify", "diagnose", "design", "confirm-gate", "do",
        "result-gate", "retry-loop"]
    # Round trip through the contract's own spelling, so what ships is exactly
    # what `from_dict` accepts and `as_dict` produces.
    assert GraphTemplate.from_dict(template.as_dict()) == template


def test_the_shipped_cycle_names_roles_and_no_deployment_anywhere():
    """Not one provider, instance or adapter word survives in the document."""
    document = json.dumps(dalio().as_dict())
    for word in sorted(DEPLOYMENT_ONLY_FIELDS):
        assert f'"{word}"' not in document, word
    assert '"role_id"' in document


def test_a_role_may_carry_several_steps_and_roles_are_distinct():
    """`role-thinker` does two of the five steps; the role set says four."""
    template = dalio()
    assert template.roles == ("role-thinker", "role-diagnostician",
                              "role-designer", "role-implementer")
    thinking = [node.node_id for node in template.nodes
                if node.role_id == "role-thinker"]
    assert thinking == ["goal", "identify"]


def test_one_template_runs_with_two_different_sets_of_assignments():
    """The same work, twice, on different deployments. Same shape, own record."""
    template = dalio()
    across = built(template, spread(template), MIXED, graph_id="graph-a",
                   run_id="run-a")
    alone = built(template, every_role_to(template, "solo"), SOLO,
                  graph_id="graph-b", run_id="run-b")
    assert is_dalio_template(across) and is_dalio_template(alone)
    assert [node.node_id for node in across.nodes] == \
        [node.node_id for node in alone.nodes]
    assert across.edges == alone.edges
    assert sorted({node.instance_id for node in across.nodes
                   if node.instance_id}) == ["claude-dev", "codex-review"]
    assert sorted({node.instance_id for node in alone.nodes
                   if node.instance_id}) == ["solo"]
    # Two runs, two records, and neither can be mistaken for the other.
    assert across.digest() != alone.digest()


def test_one_instance_may_carry_every_role_in_the_cycle():
    """A small deployment is one instance doing all of it, and that is legal."""
    template = dalio()
    definition = built(template, every_role_to(template, "solo"), SOLO)
    assert {node.instance_id for node in definition.nodes
            if node.instance_id} == {"solo"}
    assert is_dalio_template(definition)


def test_two_instances_of_one_harness_are_told_apart_by_configuration():
    """The adapter is shared; the instances are not, and the plan names those."""
    template = dalio()
    binding = RunBinding(assignments={
        "role-thinker": "claude-primary", "role-diagnostician": "claude-primary",
        "role-designer": "claude-secondary", "role-implementer": "claude-secondary"})
    definition = built(template, binding, TWO_OF_ONE)
    assert sorted({node.instance_id for node in definition.nodes
                   if node.instance_id}) == ["claude-primary", "claude-secondary"]
    # And the adapter they share appears nowhere in the durable record.
    assert "claude-code" not in json.dumps(definition.as_dict())


#: One fault per binding, each naming the relation it cuts.
_REFUSED_BINDINGS = (
    ("a role the template does not name",
     {"role-thinker": "solo", "role-diagnostician": "solo", "role-designer": "solo",
      "role-implementer": "solo", "role-nobody": "solo"}, SOLO,
     "does not name"),
    ("a role the template names, left out",
     {"role-thinker": "solo", "role-diagnostician": "solo", "role-designer": "solo"},
     SOLO, "unassigned"),
    ("an instance the frozen configuration does not declare",
     {"role-thinker": "ghost", "role-diagnostician": "ghost",
      "role-designer": "ghost", "role-implementer": "ghost"}, SOLO,
     "frozen configuration does not declare"),
    ("a capability the bound adapter does not serve",
     {"role-thinker": "reader", "role-diagnostician": "reader",
      "role-designer": "reader", "role-implementer": "reader"}, MIXED,
     "does not serve it"),
)


@pytest.mark.parametrize("name,assignments,config,says", _REFUSED_BINDINGS,
                         ids=[row[0] for row in _REFUSED_BINDINGS])
def test_materialization_refuses_before_a_definition_exists(
        name, assignments, config, says):
    """Every one of these is caught with zero durable bytes written.

    A plan that reaches the journal can never be edited, so a plan whose steps
    no adapter can carry out would stand there forever answering
    `service_refused` to every proposal made against it.
    """
    with pytest.raises(TemplateError) as refusal:
        built(dalio(), RunBinding(assignments=assignments), config)
    assert says in str(refusal.value)


def test_an_adapter_no_available_provider_backs_is_refused():
    """`served` is the runtime's answer, and an absent one is not a yes."""
    template = dalio()
    with pytest.raises(TemplateError, match="no available provider"):
        materialize(template, every_role_to(template, "solo"), SOLO,
                    {"codex": ("review", "dispatch")},
                    graph_id="graph-x", run_id="run-x", created_at=NOW)


#: A deployment's word and a run's word, at each level a document has, each
#: with the reason it is refused FOR. Two reasons appear, and the difference
#: is worth keeping visible: the template's own levels are closed, so an
#: unknown key is the whole answer there; the leaf values it reuses from
#: `graph_definition` -- a loop, a resource -- carry that contract's own
#: by-name refusal of a run's words, which is stronger and already tested
#: where it lives.
_FORBIDDEN_DOCUMENTS = (
    ("provider at the top level", {"provider_id": "claude-code"}, {},
     "unsupported field"),
    ("instance on a node", {}, {"instance_id": "claude-dev"},
     "unsupported field"),
    ("adapter on a node", {}, {"adapter": "claude-code"}, "unsupported field"),
    ("a run's phase on a node", {}, {"phase": "idle"}, "unsupported field"),
    ("a run's pass nested in a node's loop", {},
     {"loop": {"bound": 2, "back_to": "goal", "pass": 1}}, "runtime-only field"),
)


@pytest.mark.parametrize("name,top,node,says", _FORBIDDEN_DOCUMENTS,
                         ids=[row[0] for row in _FORBIDDEN_DOCUMENTS])
def test_a_template_refuses_a_deployment_word_and_a_run_word(name, top, node, says):
    """Each is refused, and each says which rule refused it.

    The reason is asserted, not just the exception: a test that accepted any
    `ContractError` would go on passing if the shape opened and something else
    happened to fail nearby.
    """
    document = dalio().as_dict()
    document.update(top)
    document["nodes"][0].update(node)
    with pytest.raises(ContractError, match=says):
        GraphTemplate.from_dict(document)


def test_this_contract_names_no_field_a_deployment_or_a_run_owns():
    """The guard a closed shape cannot be: what happens when a field is ADDED.

    Nothing can smuggle `instance_id` into a template as data. What could
    happen is somebody putting it in `_FIELDS` one day, at which point the
    document would accept it and every refusal above would still pass. This
    reads the contract's own vocabulary instead.
    """
    for owner, fields in (("template", GraphTemplate._FIELDS),
                          ("template node", TemplateNode._FIELDS)):
        deployment = sorted(fields & DEPLOYMENT_ONLY_FIELDS)
        assert not deployment, f"{owner} names deployment field(s) {deployment!r}"
        runtime = sorted(fields & RUNTIME_ONLY_FIELDS)
        assert not runtime, f"{owner} names run field(s) {runtime!r}"
    # And the vocabulary is not empty in the direction that matters: the words
    # a template must never grow a field for are actually listed.
    assert {"instance_id", "provider_id", "adapter"} <= DEPLOYMENT_ONLY_FIELDS


def test_a_step_binds_a_role_and_a_capability_or_neither():
    with pytest.raises(TemplateError, match="capability with no role"):
        TemplateNode(node_id="a", kind="task", title="A", capability="review")
    with pytest.raises(TemplateError, match="role with no capability"):
        TemplateNode(node_id="a", kind="task", title="A", role_id="role-x")


def test_a_template_that_could_not_be_built_is_refused_at_construction():
    """The topology rules stay in the base contract; a template PROVES itself.

    Nothing here re-states what a graph must be. The template materializes
    against placeholders the moment it is constructed, so a shape the product
    could not build never becomes a template at all.
    """
    document = dalio().as_dict()
    document["edges"].append({"from_node": "retry-loop", "to_node": "goal"})
    with pytest.raises(TemplateError, match="does not describe a graph"):
        GraphTemplate.from_dict(document)


def test_editing_a_template_makes_a_revision_and_leaves_past_runs_alone():
    """A correction is a new identity; a record already written does not move."""
    template = dalio()
    followed = built(template, every_role_to(template, "solo"), SOLO)
    before = followed.digest()

    document = template.as_dict()
    document["revision"] = 2
    document["nodes"][0]["title"] = "Goal, restated"
    corrected = GraphTemplate.from_dict(document)
    assert corrected.revision == 2 and corrected != template

    again = materialize(corrected, every_role_to(corrected, "solo"), SOLO,
                        SERVED, graph_id="graph-run", run_id="run-002",
                        created_at=NOW)
    assert again.digest() != before
    # The run that already followed the first revision replays byte for byte:
    # its record was never touched by the edit.
    assert followed.digest() == before
    assert GraphDefinition.from_dict(followed.as_dict()).digest() == before


def test_a_synthetic_eighth_provider_needs_no_orchestration_change():
    """The regression behind the whole slice: identity is data, not a branch.

    Nothing in this test edits production. A provider this build has never
    heard of is named only in the two places a provider is ever named -- the
    frozen configuration's binding and the runtime's `served` answer -- and the
    template, the binding and the materializer carry it without knowing it.
    """
    template = dalio()
    config = {"instances": [{"id": "eighth-node", "adapter": "synthetic-eighth"}]}
    served = dict(SERVED, **{"synthetic-eighth": ("observe", "review", "dispatch")})
    definition = materialize(
        template, every_role_to(template, "eighth-node"), config, served,
        graph_id="graph-eighth", run_id="run-eighth", created_at=NOW)
    assert is_dalio_template(definition)
    assert {node.instance_id for node in definition.nodes
            if node.instance_id} == {"eighth-node"}


def test_a_binding_is_a_total_map_and_says_which_instances_it_uses():
    template = dalio()
    binding = spread(template)
    binding.covers(template)
    assert binding.instances == ("claude-dev", "codex-review")
    assert RunBinding.from_dict(binding.as_dict()) == binding


def test_the_materializer_takes_the_exact_types_and_no_lookalike():
    """A subclass may answer for itself; neither door accepts one."""
    class Sneaky(GraphTemplate):
        pass

    template = dalio()
    with pytest.raises(TemplateError, match="exactly a GraphTemplate"):
        materialize(Sneaky(template_id="t", revision=1, title="T",
                           nodes=template.nodes, edges=template.edges),
                    every_role_to(template, "solo"), SOLO, SERVED,
                    graph_id="g", run_id="r", created_at=NOW)
    with pytest.raises(TemplateError, match="exactly a RunBinding"):
        materialize(template, {"role-thinker": "solo"}, SOLO, SERVED,
                    graph_id="g", run_id="r", created_at=NOW)


def test_edges_and_nodes_are_taken_by_identity_of_type():
    template = dalio()
    with pytest.raises(TemplateError, match="TemplateNode"):
        GraphTemplate(template_id="t", revision=1, title="T",
                      nodes=({"node_id": "a"},), edges=())
    with pytest.raises(TemplateError, match="GraphEdge"):
        GraphTemplate(template_id="t", revision=1, title="T",
                      nodes=template.nodes, edges=({"from_node": "goal"},))
    assert GraphEdge(from_node="goal", to_node="identify") in template.edges


def test_the_shipped_template_reaches_the_wheel_a_user_installs(tmp_path):
    """A user receives the wheel, not this tree -- so assert on the artifact.

    The default cycle is DATA, which is exactly the kind of file a packaging
    change drops silently: the code would still import, `load_template` would
    raise at the first call, and nothing in a source-tree test would have
    noticed.
    """
    wheel_module = pytest.importorskip("hatchling.builders.wheel")
    root = Path(__file__).resolve().parents[1]
    artifacts = list(
        wheel_module.WheelBuilder(str(root)).build(directory=str(tmp_path)))
    assert len(artifacts) == 1
    with zipfile.ZipFile(artifacts[0]) as wheel:
        shipped = {name for name in wheel.namelist()
                   if name.startswith("conductor/command/templates/")}
    packaged = {f"conductor/command/templates/{path.name}"
                for path in TEMPLATE_DIR.iterdir() if path.is_file()}
    assert shipped == packaged
    assert "conductor/command/templates/dalio-v1.json" in shipped


def test_the_frozen_role_artifacts_are_what_production_derives_today():
    """The UI lane's handoff, re-derived and compared on every run.

    A fixture that is only ever read is a claim about a file. These are BUILT
    by the production contracts each time this runs, so production drifting
    away from the shape the Fable lane was handed reds here rather than in a
    browser weeks later.
    """
    derived = alpha4_role_artifacts.derive_all()
    assert sorted(derived) == sorted(alpha4_role_artifacts.ARTIFACTS)
    for name in alpha4_role_artifacts.ARTIFACTS:
        assert derived[name] == alpha4_role_artifacts.load(name), name


def test_the_handed_over_runs_share_one_topology_and_no_record():
    """What the artifacts are FOR: one cycle, two deployments, two records."""
    runs = alpha4_role_artifacts.load("alpha4_materialized_runs")["runs"]
    assert [run["name"] for run in runs] == ["two-instances", "one-instance"]
    shapes = {tuple(node["node_id"] for node in run["definition"]["nodes"])
              for run in runs}
    assert len(shapes) == 1, "the same template produced two different shapes"
    assert len({run["definition_digest"] for run in runs}) == 2
    assert [run["instances"] for run in runs] == [
        ["claude-dev", "codex-review"], ["solo-node"]]


def test_the_handed_over_template_carries_roles_and_no_deployment():
    """What Fable renders and submits: work and roles, and nothing about here."""
    handed = alpha4_role_artifacts.load("alpha4_dalio_template")
    assert handed["roles"] == list(dalio().roles)
    document = json.dumps(handed["template"])
    for word in sorted(DEPLOYMENT_ONLY_FIELDS):
        assert f'"{word}"' not in document, word
    # And the run-side artifact is where a deployment IS named, so the split
    # is visible in the handoff itself rather than only in prose.
    bindings = json.dumps(alpha4_role_artifacts.load("alpha4_run_bindings"))
    assert '"adapter"' in bindings and '"assignments"' in bindings
