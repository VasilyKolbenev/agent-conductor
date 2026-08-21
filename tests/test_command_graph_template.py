"""A plan written in roles, and the one door that turns it into a run's own.

Every claim here is made by building real values through the real contracts.
The template is the SHIPPED data file wherever one will do, because a fixture
written beside the test would only prove that two pieces of this file agree.
"""
from __future__ import annotations

import json
import traceback
import zipfile
from pathlib import Path

import pytest

from conductor.command.adapters import AdapterRegistry, UnsupportedCapability
from conductor.command.contracts import ContractError, frozen_config_bindings

from tests import alpha4_role_artifacts
from tests.test_command_adapters import FakeAdapter
from conductor.command.graph_dalio import is_dalio_template
from conductor.command.graph_definition import (
    RUNTIME_ONLY_FIELDS,
    GraphDefinition,
    GraphEdge,
    GraphLoop,
    GraphNode,
    GraphResource,
)
from conductor.command.graph_template import (
    DEPLOYMENT_ONLY_FIELDS,
    SCHEMA_VERSION,
    TEMPLATE_DIR,
    GraphTemplate,
    RunBinding,
    TemplateError,
    TemplateNode,
    load_template,
    materialize,
)

NOW = "2026-08-20T10:00:00Z"
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


def _strings(value: object) -> set[str]:
    """Every string anywhere in a JSON document, keys and values alike."""
    if isinstance(value, dict):
        return set(value) | {word for item in value.values()
                             for word in _strings(item)}
    if isinstance(value, list):
        return {word for item in value for word in _strings(item)}
    return {value} if isinstance(value, str) else set()


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
    return materialize(template, binding, config, **values)


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
                        graph_id="graph-run", run_id="run-002", created_at=NOW)
    assert again.digest() != before
    # The run that already followed the first revision replays byte for byte:
    # its record was never touched by the edit.
    assert followed.digest() == before
    assert GraphDefinition.from_dict(followed.as_dict()).digest() == before


def test_a_synthetic_eighth_provider_needs_no_orchestration_change():
    """The regression behind the whole slice: identity is data, not a branch.

    Nothing in this test edits production. A provider this build has never
    heard of is named in the ONE place a template road ever names one -- the
    frozen configuration's binding -- and the template, the binding and the
    materializer carry it without knowing it.
    """
    template = dalio()
    config = {"instances": [{"id": "eighth-node", "adapter": "synthetic-eighth"}]}
    definition = materialize(
        template, every_role_to(template, "eighth-node"), config,
        graph_id="graph-eighth", run_id="run-eighth", created_at=NOW)
    assert is_dalio_template(definition)
    assert {node.instance_id for node in definition.nodes
            if node.instance_id} == {"eighth-node"}


def test_the_shipped_cycle_pins_no_model_on_the_instance_that_runs_it():
    """A resource row names a thing BY NAME, so a model here is a demand.

    A definition materialized onto a Qwen, a GLM or a Grok instance would
    still stand in the journal asking for Sonnet -- a durable record demanding
    something of a product that has never heard of it. Which model runs is the
    business of the configuration behind the assigned instance, not of a cycle
    meant to run in more than one place.
    """
    template = dalio()
    config = {"instances": [{"id": "eighth-node", "adapter": "synthetic-eighth"}]}
    definition = materialize(
        template, every_role_to(template, "eighth-node"), config,
        graph_id="graph-eighth", run_id="run-eighth", created_at=NOW)
    declared = {(row.kind, row.name) for node in definition.nodes
                for row in node.resources}
    # Two-sided on purpose. "No model" must not be satisfiable by carrying no
    # resources at all, which is what the same fix applied in `_build` instead
    # of in the data would do -- and every derived fixture would settle around
    # it without a word.
    assert ("sandbox", "project-root") in declared, sorted(declared)
    assert not [row for row in declared if row[0] == "model"], sorted(declared)

    # And the predicate can still fail, shown rather than asserted: the same
    # walk over a tainted copy of the same document finds the row.
    tainted = template.as_dict()
    step = next(row for row in tainted["nodes"] if row["node_id"] == "do")
    step["resources"].append({"kind": "model", "name": "sonnet"})
    seen = materialize(
        GraphTemplate.from_dict(tainted), every_role_to(template, "eighth-node"),
        config, graph_id="graph-eighth", run_id="run-eighth", created_at=NOW)
    assert "model" in {row.kind for node in seen.nodes for row in node.resources}


def test_a_materialized_plan_invents_no_word_the_template_or_the_run_did_not():
    """Every string in the record traces to the template, the binding or the run.

    Derived rather than a blocklist of vendor words: a hand-typed list of
    products to forbid rots the day an eighth one exists, and says nothing
    about the ninth. This asks the opposite question -- where did each word
    COME from -- so a literal smuggled in from anywhere else is a finding
    whatever it happens to spell.
    """
    template = dalio()
    config = {"instances": [{"id": "eighth-node", "adapter": "synthetic-eighth"}]}
    binding = every_role_to(template, "eighth-node")
    definition = materialize(template, binding, config, graph_id="graph-eighth",
                             run_id="run-eighth", created_at=NOW)
    supplied = _strings(template.as_dict()) | set(binding.bound().values())
    supplied |= {"graph-eighth", "run-eighth", NOW}
    for owner in (GraphDefinition, GraphNode, GraphResource, GraphEdge, GraphLoop):
        supplied |= set(owner._FIELDS)
    invented = sorted(_strings(definition.as_dict()) - supplied)
    assert not invented, invented


def test_the_frozen_configuration_is_read_for_the_adapter_and_for_nothing_else():
    """One fact is taken from a config here, and no other key may change a plan.

    Deleting the `served` parameter is not by itself the end of the second
    authority, and a sabotage run proved it: the same dialect comes back read
    off the instance row -- `controls`, `serves`, whatever it is called --
    permissive whenever the key is absent, so every test written against the
    parameter stays green while the defect is fully intact.

    So the claim is made about the ROW rather than about a parameter, and from
    both sides. Enrich an instance row with anything at all and the plan is the
    same plan; reduce the config to nothing but the binding
    `frozen_config_bindings` returns and it is still the same plan. Whatever a
    row carries beside `id` and `adapter`, this module did not read it.
    """
    template = dalio()
    binding = every_role_to(template, "reader")
    plain = materialize(template, binding, MIXED, graph_id="g", run_id="r",
                        created_at=NOW)

    enriched = {"instances": [
        row if row["id"] != "reader" else dict(
            row, controls=[], capabilities=[], serves=[], model="sonnet")
        for row in MIXED["instances"]]}
    assert materialize(template, binding, enriched, graph_id="g", run_id="r",
                       created_at=NOW).digest() == plain.digest()

    reduced = {"instances": [{"id": name, "adapter": adapter} for name, adapter
                             in sorted(frozen_config_bindings(MIXED).items())]}
    assert materialize(template, binding, reduced, graph_id="g", run_id="r",
                       created_at=NOW).digest() == plain.digest()


def test_a_capability_the_bound_adapter_cannot_do_still_materializes():
    """The verdict MOVED out of this module; it did not change hands here.

    `served` let a caller hand in `{adapter: capabilities}` and refuse on it,
    so a dictionary decided a fact the adapter registry owns -- a capability
    name nobody validated, no argument schema, no family, and a synthetic
    provider that satisfied the whole check with no registry in the room.

    Deleting the parameter is only half of that correction. What proves the
    second authority is GONE is that this module now says yes to a plan it used
    to refuse, and that the one door which may still say no is the registry the
    pair authority already reads.
    """
    template = dalio()
    definition = materialize(template, every_role_to(template, "reader"), MIXED,
                             graph_id="graph-r", run_id="run-r", created_at=NOW)
    assert is_dalio_template(definition)
    doing = next(node for node in definition.nodes if node.capability == "dispatch")
    registry = AdapterRegistry([FakeAdapter(adapter_id="reviewer-only",
                                            capabilities=("observe", "review"))])
    with pytest.raises(UnsupportedCapability):
        registry.validate_arguments("reviewer-only", "dispatch", doing.payload())


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
                    every_role_to(template, "solo"), SOLO,
                    graph_id="g", run_id="r", created_at=NOW)
    with pytest.raises(TemplateError, match="exactly a RunBinding"):
        materialize(template, {"role-thinker": "solo"}, SOLO,
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


# --- what this contract answers for, once somebody edits what it holds ---


class _Hostile:
    """Answers every read with a foreign exception carrying a secret.

    Whatever this raises must never become the contract's answer: a refusal
    that repeats it has read the replacement, which is the act the identity
    check exists to avoid.
    """

    SECRET = "a-secret-no-refusal-may-repeat"

    def __iter__(self):
        raise RuntimeError(self.SECRET)

    def items(self):
        raise RuntimeError(self.SECRET)

    def keys(self):
        raise RuntimeError(self.SECRET)

    def values(self):
        raise RuntimeError(self.SECRET)


def test_a_rendered_template_is_a_copy_and_editing_it_leaves_the_template_alone():
    """A revision is the identity of a plan, so a render must not move one.

    Handing back the contract's own mapping let a caller change what every
    later run materializes from, at the SAME revision -- which is exactly the
    edit a revision exists to make visible.
    """
    template = dalio()
    before = template.as_dict()
    rendered = template.as_dict()
    rendered["nodes"][0]["arguments"]["review_profile"] = "hijacked"
    rendered["nodes"][0]["title"] = "hijacked"
    rendered["title"] = "hijacked"
    assert template.as_dict() == before
    assert template.nodes[0].payload()["review_profile"] == "spec"
    # Two renders are two documents, so one caller's paper is never another's.
    assert template.as_dict()["nodes"] is not template.as_dict()["nodes"]


def test_the_callers_own_arguments_are_taken_once_and_never_read_again():
    """A mapping the caller still holds is a mapping the caller can still edit."""
    caller = {"work_item_id": "work-001", "target_artifact_refs": ["artifact-a"],
              "review_profile": "spec"}
    node = TemplateNode(node_id="n", kind="task", title="T", stage="goal",
                        role_id="role-a", capability="review", arguments=caller)
    caller["review_profile"] = "hijacked"
    assert node.payload()["review_profile"] == "spec"
    with pytest.raises(TypeError):
        node.arguments["review_profile"] = "hijacked"


def test_a_node_whose_arguments_were_replaced_answers_in_its_own_words():
    node = dalio().nodes[0]
    object.__setattr__(node, "arguments", _Hostile())
    for read in (node.payload, node.as_dict):
        with pytest.raises(TemplateError) as refusal:
            read()
        assert "replaced after they were validated" in str(refusal.value)
        assert _Hostile.SECRET not in str(refusal.value)


@pytest.mark.parametrize("field", ["nodes", "edges"])
def test_a_template_whose_nodes_or_edges_were_replaced_answers_in_its_own_words(field):
    """A tuple cannot be edited, which is precisely why it gets replaced whole."""
    template = dalio()
    object.__setattr__(template, field, _Hostile())
    for read in (template.steps, template.as_dict, lambda: template.roles):
        with pytest.raises(TemplateError) as refusal:
            read()
        assert _Hostile.SECRET not in str(refusal.value)


def _plan_of(template: GraphTemplate) -> dict:
    """The plan this template materializes, as data, so two can be compared."""
    return materialize(template, every_role_to(template, "solo"), SOLO,
                       graph_id="g", run_id="r", created_at=NOW).as_dict()


#: One live edit per scalar of every nested value a template holds. The witness
#: catches a tuple swapped WHOLE; none of these swaps a tuple.
_LIVE_EDITS = (
    ("a step's node_id", lambda t: t.nodes[0], "node_id", "hijacked"),
    ("a step's kind", lambda t: t.nodes[0], "kind", "gate"),
    ("a step's title", lambda t: t.nodes[0], "title", "MUTATED WITHOUT REVISION"),
    ("a step's stage", lambda t: t.nodes[0], "stage", "do"),
    ("a step's role_id", lambda t: t.nodes[0], "role_id", "role-nobody"),
    ("a step's capability", lambda t: t.nodes[0], "capability", "dispatch"),
    ("a gate's gate_id", lambda t: t.nodes[4], "gate_id", "gate-hijacked"),
    ("an edge's from_node", lambda t: t.edges[0], "from_node", "diagnose"),
    ("an edge's to_node", lambda t: t.edges[0], "to_node", "diagnose"),
    ("a loop's bound", lambda t: t.nodes[7].loop, "bound", 99),
    ("a loop's back_to", lambda t: t.nodes[7].loop, "back_to", "goal"),
    ("a resource's kind", lambda t: t.nodes[5].resources[0], "kind", "model"),
    ("a resource's name", lambda t: t.nodes[5].resources[0], "name", "sonnet"),
)


@pytest.mark.parametrize("name,reach,field,value", _LIVE_EDITS,
                         ids=[row[0] for row in _LIVE_EDITS])
def test_an_edit_inside_a_template_reaches_neither_the_document_nor_the_plan(
        name, reach, field, value):
    """One template at one revision must never assert two different plans.

    `as_dict` answered from the snapshot while `materialize` walked the live
    objects, so the rendered document said the first step was called `Goal` and
    the definition that same template produced said something else -- both at
    `revision` 1. Every scalar on a `TemplateNode`, a `GraphEdge`, a `GraphLoop`
    and a `GraphResource` was reachable that way, which is why this is a matrix
    rather than a case: the fix is one rebuild from the canonical record, and
    what proves it is that no field is left out of it.
    """
    template = dalio()
    document = template.as_dict()
    plan = _plan_of(template)
    target = reach(template)
    object.__setattr__(target, field, value)
    # Non-vacuity: the probe must really have edited the live value, or this
    # would pass against a template nobody touched.
    assert getattr(target, field) == value, "the probe edited nothing"
    assert template.as_dict() == document
    assert _plan_of(template) == plan
    assert template.revision == 1


def test_a_template_renders_the_fields_it_settled_and_not_a_later_one():
    """The scalars are pinned by the same snapshot the nodes are."""
    template = dalio()
    object.__setattr__(template, "title", "a title nobody reviewed")
    object.__setattr__(template, "revision", 99)
    assert template.as_dict()["title"] == "Dalio five-step cycle"
    assert template.as_dict()["revision"] == 1


def test_a_binding_whose_assignments_were_replaced_answers_in_its_own_words():
    template = dalio()
    binding = every_role_to(template, "solo")
    object.__setattr__(binding, "assignments", _Hostile())
    reads = (binding.bound, binding.as_dict, lambda: binding.instances,
             lambda: binding.covers(template))
    for read in reads:
        with pytest.raises(TemplateError) as refusal:
            read()
        assert _Hostile.SECRET not in str(refusal.value)
    with pytest.raises(TemplateError):
        built(template, binding, SOLO)


def test_a_binding_judges_what_it_was_handed_before_it_reads_one_key():
    """The refusal is this contract's, not whatever the caller passed in.

    A `dict(...)` around the value ran the caller's own `keys` before anything
    had judged it, so a hostile mapping's exception left as the answer -- and a
    `dict` SUBCLASS was quietly turned into a plain one instead of refused,
    though it answers `items` however it likes and this value is copied and
    digested downstream.
    """
    class _Sneaky(dict):
        def items(self):
            raise RuntimeError(_Hostile.SECRET)

    for handed in (_Hostile(), _Sneaky({"role-thinker": "solo"})):
        with pytest.raises(ContractError) as refusal:
            RunBinding(assignments=handed)
        assert "must be a JSON object" in str(refusal.value)
        assert _Hostile.SECRET not in str(refusal.value)


def test_a_binding_holds_its_assignments_closed_against_an_edit_in_place():
    """`covers` reads the role KEYS, so an edited VALUE passed every check."""
    template = dalio()
    binding = every_role_to(template, "solo")
    binding.covers(template)
    with pytest.raises(TypeError):
        binding.assignments["role-thinker"] = "somebody-else"
    assert binding.bound()["role-thinker"] == "solo"


# --- what a closed document accepts, and what it says when it will not ---


@pytest.mark.parametrize("document", [
    {"node_id": "g", "kind": "gate", "title": "G", "gate_id": "gate-x"},
    {"node_id": "a", "kind": "task", "title": "A", "stage": "goal",
     "role_id": "role-a", "capability": "review"},
], ids=["a gate that carries no payload", "an acting step with none yet"])
def test_an_absent_payload_is_a_step_with_none_and_an_explicit_null_is_refused(document):
    """Absent and null are two different documents and get two answers.

    A key that is not there is a step with nothing to hand its capability. A
    key that IS there saying `null` is a document making a statement, and it is
    making it wrongly -- reading both as "empty" told that author nothing.
    """
    assert TemplateNode.from_dict(document).payload() == {}
    with pytest.raises(ContractError, match="must be a JSON object"):
        TemplateNode.from_dict({**document, "arguments": None})


def test_a_document_survives_being_read_and_can_be_read_again():
    """Every field below is taken with `pop`, so the popping must be our own.

    Reading a template emptied the caller's document, and the SECOND read then
    failed claiming a required field was missing -- when the first read is what
    removed it.
    """
    document = dalio().as_dict()
    first = GraphTemplate.from_dict(document)
    second = GraphTemplate.from_dict(document)
    assert first.as_dict() == second.as_dict() == document


def test_this_build_speaks_one_template_schema_and_says_so_to_any_other():
    template = dalio()
    assert template.as_dict()["schema_version"] == SCHEMA_VERSION
    document = template.as_dict()
    for claimed in (SCHEMA_VERSION + 1, SCHEMA_VERSION - 1, 99):
        with pytest.raises(TemplateError, match="schema_version"):
            GraphTemplate.from_dict({**document, "schema_version": claimed})
    # An absent version is this schema, which is what every shipped file is.
    without = {name: value for name, value in document.items()
               if name != "schema_version"}
    assert GraphTemplate.from_dict(without).schema_version == SCHEMA_VERSION


def test_a_missing_template_is_refused_without_naming_the_servers_disk():
    """The refusal owes the caller the name they asked for, and nothing else.

    `OSError` carries the FULL path it failed on, so chaining it printed this
    server's directory layout under any traceback or reporting boundary.
    """
    with pytest.raises(TemplateError) as refusal:
        load_template("no-such-template")
    assert refusal.value.__cause__ is None
    assert refusal.value.__suppress_context__ is True
    printed = "".join(traceback.format_exception(
        type(refusal.value), refusal.value, refusal.value.__traceback__))
    assert str(TEMPLATE_DIR) not in printed
    assert "no-such-template" in str(refusal.value)


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
