"""Flow schema v1 (spec 7.2): the closed shapes of the editor's model, form only.

The compiler and the importer join this file on days 3-4 (spec 7.11 item 1). What is held here
is the part every later module leans on: the exact keys of every level, the vocabularies that
must equal the core's own, and that a flow the shape refuses is refused at a named address.
"""
import copy
import json
import re
from collections import OrderedDict
from pathlib import Path

import pytest

from conductor.command import workflow_draft, workflow_flow as flow_schema
from conductor.command.adapters.deep_commands import REVIEW_PROFILES
from conductor.command.contract_values import ContractError
from conductor.command.graph_conditions import EDGE_CONDITIONS
from conductor.command.graph_template_document import TemplateNode
from conductor.command.workflow_flow import FlowShapeError, settled_flow

SPEC_STEP_KEYS = {
    "agent": ["step_id", "type", "title", "purpose", "position", "timeout_seconds", "role_id",
              "capability", "verifier_role_id", "review_profile", "reads", "instruction_from", "ext"],
    "human": ["step_id", "type", "title", "purpose", "position", "timeout_seconds", "ext"],
    "route": ["step_id", "type", "title", "purpose", "position", "timeout_seconds", "ext"],
    "loop": ["step_id", "type", "title", "purpose", "position", "timeout_seconds", "back_to", "bound",
             "ext"]}
SPEC_EXT_FIELDS = {"stage", "arguments", "resources", "attempt_bound", "required_evidence",
                   "failure_policy", "missing_artifact_policy", "gate_id", "success_requires"}
SPEC_WHEN = ["success", "failed", "approved", "rejected", "changes_requested", "waived",
             "bound_reached", "bound_remaining", "always"]


def step(step_id, kind, **own):
    """One canonical step: every key of its type present, the spec's defaults, then the overrides."""
    values = {"step_id": step_id, "type": kind, "title": None, "purpose": None, "position": None,
              "timeout_seconds": None, "ext": {}}
    if kind == "agent":
        values.update(role_id="role-doer", capability="dispatch", verifier_role_id=None,
                      review_profile=None, reads=[], instruction_from=None)
    if kind == "loop":
        values.update(back_to="do", bound=2)
    values.update(own)
    return {key: values[key] for key in SPEC_STEP_KEYS[kind]}


def canonical_flow():
    return {"flow_version": 1, "title": "Standard",
            "steps": [
                step("analyst", "agent", role_id="role-analyst", capability="review", review_profile="spec"),
                step("do", "agent", verifier_role_id="role-checker", timeout_seconds=1800),
                step("result", "human"),
                step("do-fix", "loop", back_to="do", bound=3)],
            "links": [{"from": "analyst", "to": "do", "when": "success"},
                      {"from": "do", "to": "result", "when": "success"},
                      {"from": "do", "to": "do-fix", "when": "failed"}],
            "ext": {}}


def test_every_template_node_field_is_typed_in_flow_or_an_extension_field():
    """Both directions: a field the core adds to a template node cannot be lost by the editor silently."""
    step_fields = {key for keys in flow_schema.STEP_FIELDS.values() for key in keys} - {"ext"}
    assert set(flow_schema.TEMPLATE_FIELD_OF_STEP_FIELD) == step_fields, "every typed field says where it goes"
    typed = set(flow_schema.TEMPLATE_FIELD_OF_STEP_FIELD.values())
    assert typed | flow_schema.EXT_FIELDS == TemplateNode._FIELDS
    assert typed & flow_schema.EXT_FIELDS == {"arguments"}, "only arguments is both computed and overridable"
    assert flow_schema.EXT_FIELDS == SPEC_EXT_FIELDS


def test_flow_when_words_map_onto_exactly_the_graph_conditions_plus_always():
    assert list(flow_schema.LINK_WHEN) == SPEC_WHEN
    conditions = [value for value in flow_schema.LINK_WHEN.values() if value is not None]
    assert set(conditions) == EDGE_CONDITIONS and len(conditions) == len(EDGE_CONDITIONS)
    assert flow_schema.LINK_WHEN["always"] is None and flow_schema.LINK_WHEN["success"] == "on_succeeded"


def test_flow_review_profiles_equal_the_adapter_vocabulary():
    assert set(flow_schema.REVIEW_PROFILES) == set(REVIEW_PROFILES)


def test_flow_size_limits_are_imported_from_the_draft_module_not_rewritten():
    assert flow_schema.MAX_STEPS == workflow_draft.MAX_DRAFT_NODES
    assert flow_schema.MAX_LINKS == workflow_draft.MAX_DRAFT_EDGES
    source = Path(flow_schema.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\b(256|1024)\b", source), "the draft limits are imported, never respelled"


def test_a_canonical_flow_settles_to_an_equal_independent_copy():
    flow = canonical_flow()
    flow["steps"][1]["ext"] = {"arguments": {"files": ["a", "b"]}, "resources": [{"kind": "sandbox"}]}
    flow["steps"][1]["position"] = {"x": 10, "y": -4}
    before = copy.deepcopy(flow)
    settled = settled_flow(flow)
    assert settled == flow and flow == before
    assert settled is not flow and settled["steps"] is not flow["steps"]
    settled["steps"][1]["ext"]["arguments"]["files"].append("c")
    settled["steps"][1]["position"]["x"] = 99
    assert flow == before, "no nested value is shared with the caller's flow"
    assert json.loads(json.dumps(settled)) == settled


def test_a_step_of_each_type_carries_exactly_its_own_keys():
    assert {kind: list(keys) for kind, keys in flow_schema.STEP_FIELDS.items()} == SPEC_STEP_KEYS
    for kind, keys in SPEC_STEP_KEYS.items():
        flow = canonical_flow()
        flow["steps"] = [step("only", kind)]
        flow["links"] = []
        assert list(settled_flow(flow)["steps"][0]) == keys


def test_flow_extension_keys_are_closed_and_the_cycle_may_only_null_its_contract():
    flow = canonical_flow()
    flow["ext"] = {"execution_contract": None}
    flow["steps"][0]["ext"] = {key: None for key in SPEC_EXT_FIELDS}
    assert settled_flow(flow) == flow
    assert flow_schema.FLOW_EXT_FIELDS == {"execution_contract"}


def refused(mutate):
    flow = canonical_flow()
    mutate(flow)
    return flow


def _set(target, key, value):
    def apply(flow):
        node = flow
        for part in target:
            node = node[part]
        node[key] = value
    return apply


def _delete(target, key):
    def apply(flow):
        node = flow
        for part in target:
            node = node[part]
        del node[key]
    return apply


REFUSALS = [
    ("flow alien key", _set([], "extra", 1), "flow.extra"),
    ("flow missing key", _delete([], "links"), "flow.links"),
    ("flow version other", _set([], "flow_version", 2), "flow.flow_version"),
    ("flow version bool", _set([], "flow_version", True), "flow.flow_version"),
    ("flow title number", _set([], "title", 7), "flow.title"),
    ("steps tuple", lambda f: f.update(steps=tuple(f["steps"])), "flow.steps"),
    ("too many steps", lambda f: f.update(steps=[step(f"s{n}", "human") for n in range(257)]), "flow.steps"),
    ("too many links", lambda f: f.update(links=[f["links"][0]] * 1025), "flow.links"),
    ("step dict subclass", lambda f: f["steps"].__setitem__(0, OrderedDict(f["steps"][0])), "flow.steps[0]"),
    ("step type other", _set(["steps", 0], "type", "task"), "flow.steps[0].type"),
    ("step type missing", _delete(["steps", 0], "type"), "flow.steps[0].type"),
    ("step alien key", _set(["steps", 1], "bogus", 1), "flow.steps[1].bogus"),
    ("human step with a role", _set(["steps", 2], "role_id", "role-doer"), "flow.steps[2].role_id"),
    ("agent missing key", _delete(["steps", 1], "verifier_role_id"), "flow.steps[1].verifier_role_id"),
    ("timeout text", _set(["steps", 1], "timeout_seconds", "60"), "flow.steps[1].timeout_seconds"),
    ("timeout bool", _set(["steps", 1], "timeout_seconds", True), "flow.steps[1].timeout_seconds"),
    ("step title number", _set(["steps", 1], "title", 3), "flow.steps[1].title"),
    ("position third axis", _set(["steps", 1], "position", {"x": 1, "y": 2, "z": 3}), "flow.steps[1].position.z"),
    ("position missing axis", _set(["steps", 1], "position", {"x": 1}), "flow.steps[1].position.y"),
    ("position fraction", _set(["steps", 1], "position", {"x": 1.5, "y": 2}), "flow.steps[1].position.x"),
    ("review profile other", _set(["steps", 0], "review_profile", "style"), "flow.steps[0].review_profile"),
    ("nine reads", _set(["steps", 1], "reads", ["analyst"] * 9), "flow.steps[1].reads"),
    ("read not text", _set(["steps", 1], "reads", [4]), "flow.steps[1].reads[0]"),
    ("loop bound text", _set(["steps", 3], "bound", "3"), "flow.steps[3].bound"),
    ("loop without a home", _set(["steps", 3], "back_to", None), "flow.steps[3].back_to"),
    ("step extension alien key", _set(["steps", 1, "ext"], "speed", 1), "flow.steps[1].ext.speed"),
    ("step extension not JSON", _set(["steps", 1, "ext"], "resources", {1, 2}), "flow.steps[1].ext.resources"),
    ("step extension NaN", _set(["steps", 1, "ext"], "arguments", {"n": float("nan")}), "flow.steps[1].ext.arguments"),
    ("step extension number key", _set(["steps", 1, "ext"], "arguments", {1: 2}), "flow.steps[1].ext.arguments"),
    ("flow extension alien key", _set(["ext"], "bogus", None), "flow.ext.bogus"),
    ("flow extension contract named", _set(["ext"], "execution_contract", "bounded-run-v1"),
     "flow.ext.execution_contract"),
    ("link alien key", _set(["links", 0], "why", 1), "flow.links[0].why"),
    ("link missing target", _delete(["links", 0], "to"), "flow.links[0].to"),
    ("link source number", _set(["links", 0], "from", 5), "flow.links[0].from"),
    ("link core spelling", _set(["links", 0], "when", "on_succeeded"), "flow.links[0].when"),
]


@pytest.mark.parametrize("mutate,path", [(mutate, path) for _, mutate, path in REFUSALS],
                         ids=[name for name, _, _ in REFUSALS])
def test_a_flow_the_shape_refuses_names_the_address_of_the_fault(mutate, path):
    flow = refused(mutate)
    before = copy.deepcopy(flow)
    with pytest.raises(FlowShapeError) as caught:
        settled_flow(flow)
    assert caught.value.path == path and isinstance(caught.value, ContractError)
    assert str(caught.value).startswith(path + ": ")
    assert flow == before, "a refusal leaves the caller's flow as it was"


def test_a_flow_that_is_not_a_plain_object_is_refused_at_its_root():
    for value in (None, [], "flow", OrderedDict(canonical_flow())):
        with pytest.raises(FlowShapeError) as caught:
            settled_flow(value)
        assert caught.value.path == "flow"


def test_a_bad_id_or_an_out_of_range_number_still_settles_for_the_rules_to_address():
    flow = canonical_flow()
    flow["steps"][0].update(step_id="not a valid id!", title="x" * 1000 + "\nline", timeout_seconds=-5,
                            position={"x": 10 ** 9, "y": 0}, role_id="", capability="")
    flow["steps"][3].update(bound=0)
    flow["links"][0].update({"from": "", "to": "nowhere"})
    assert settled_flow(flow) == flow
