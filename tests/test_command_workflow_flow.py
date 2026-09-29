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
from conductor.command.graph_template_document import GraphTemplate, TemplateNode
from conductor.command.workflow_flow import FlowShapeError, settled_flow

SPEC_STEP_KEYS = {
    "agent": ["step_id", "type", "title", "purpose", "position", "timeout_seconds", "role_id",
              "capability", "verifier_role_id", "review_profile", "reads", "instruction_from",
              "ext"],
    "human": ["step_id", "type", "title", "purpose", "position", "timeout_seconds", "ext"],
    "route": ["step_id", "type", "title", "purpose", "position", "timeout_seconds", "ext"],
    "loop": ["step_id", "type", "title", "purpose", "position", "timeout_seconds", "back_to",
             "bound", "ext"]}
SPEC_EXT_FIELDS = {"stage", "arguments", "resources", "attempt_bound", "required_evidence",
                   "failure_policy", "missing_artifact_policy", "gate_id", "success_requires"}
SPEC_WHEN = ["success", "failed", "approved", "rejected", "changes_requested", "waived",
             "bound_reached", "bound_remaining", "always"]


def step(step_id, kind, **own):
    """One canonical step: every key of its type, the spec's defaults, then the overrides."""
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
                step("analyst", "agent", role_id="role-analyst", capability="review",
                     review_profile="spec"),
                step("do", "agent", verifier_role_id="role-checker", timeout_seconds=1800),
                step("result", "human"),
                step("do-fix", "loop", back_to="do", bound=3)],
            "links": [{"from": "analyst", "to": "do", "when": "success"},
                      {"from": "do", "to": "result", "when": "success"},
                      {"from": "do", "to": "do-fix", "when": "failed"}],
            "ext": {}}


def test_every_template_node_field_is_typed_in_flow_or_an_extension_field():
    """Both directions: a field the core adds to a template node cannot be lost silently."""
    step_fields = {key for keys in flow_schema.STEP_FIELDS.values() for key in keys} - {"ext"}
    assert set(flow_schema.TEMPLATE_FIELD_OF_STEP_FIELD) == step_fields, (
        "every typed field says where it goes")
    typed = set(flow_schema.TEMPLATE_FIELD_OF_STEP_FIELD.values())
    assert typed | flow_schema.EXT_FIELDS == TemplateNode._FIELDS
    assert typed & flow_schema.EXT_FIELDS == {"arguments"}, (
        "only arguments is both computed and overridable")
    assert flow_schema.EXT_FIELDS == SPEC_EXT_FIELDS


def test_flow_when_words_map_onto_exactly_the_graph_conditions_plus_always():
    assert list(flow_schema.LINK_WHEN) == SPEC_WHEN
    conditions = [value for value in flow_schema.LINK_WHEN.values() if value is not None]
    assert set(conditions) == EDGE_CONDITIONS and len(conditions) == len(EDGE_CONDITIONS)
    assert flow_schema.LINK_WHEN["always"] is None
    assert flow_schema.LINK_WHEN["success"] == "on_succeeded"


def test_flow_review_profiles_equal_the_adapter_vocabulary():
    assert set(flow_schema.REVIEW_PROFILES) == set(REVIEW_PROFILES)


def test_flow_size_limits_are_imported_from_the_draft_module_not_rewritten():
    assert flow_schema.MAX_STEPS == workflow_draft.MAX_DRAFT_NODES
    assert flow_schema.MAX_LINKS == workflow_draft.MAX_DRAFT_EDGES
    source = Path(flow_schema.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\b(256|1024)\b", source), (
        "the draft limits are imported, never respelled")


def test_a_canonical_flow_settles_to_an_equal_independent_copy():
    flow = canonical_flow()
    flow["steps"][1]["ext"] = {"arguments": {"files": ["a", "b"]},
                               "resources": [{"kind": "sandbox"}]}
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
    ("too many steps", lambda f: f.update(steps=[step(f"s{n}", "human") for n in range(257)]),
     "flow.steps"),
    ("too many links", lambda f: f.update(links=[f["links"][0]] * 1025), "flow.links"),
    ("step dict subclass", lambda f: f["steps"].__setitem__(0, OrderedDict(f["steps"][0])),
     "flow.steps[0]"),
    ("step type other", _set(["steps", 0], "type", "task"), "flow.steps[0].type"),
    ("step type missing", _delete(["steps", 0], "type"), "flow.steps[0].type"),
    ("step alien key", _set(["steps", 1], "bogus", 1), "flow.steps[1].bogus"),
    ("human step with a role", _set(["steps", 2], "role_id", "role-doer"), "flow.steps[2].role_id"),
    ("agent missing key", _delete(["steps", 1], "verifier_role_id"),
     "flow.steps[1].verifier_role_id"),
    ("timeout text", _set(["steps", 1], "timeout_seconds", "60"), "flow.steps[1].timeout_seconds"),
    ("timeout bool", _set(["steps", 1], "timeout_seconds", True), "flow.steps[1].timeout_seconds"),
    ("step title number", _set(["steps", 1], "title", 3), "flow.steps[1].title"),
    ("position third axis", _set(["steps", 1], "position", {"x": 1, "y": 2, "z": 3}),
     "flow.steps[1].position.z"),
    ("position missing axis", _set(["steps", 1], "position", {"x": 1}), "flow.steps[1].position.y"),
    ("position fraction", _set(["steps", 1], "position", {"x": 1.5, "y": 2}),
     "flow.steps[1].position.x"),
    ("review profile other", _set(["steps", 0], "review_profile", "style"),
     "flow.steps[0].review_profile"),
    ("nine reads", _set(["steps", 1], "reads", ["analyst"] * 9), "flow.steps[1].reads"),
    ("read not text", _set(["steps", 1], "reads", [4]), "flow.steps[1].reads[0]"),
    ("loop bound text", _set(["steps", 3], "bound", "3"), "flow.steps[3].bound"),
    ("loop without a home", _set(["steps", 3], "back_to", None), "flow.steps[3].back_to"),
    ("step extension alien key", _set(["steps", 1, "ext"], "speed", 1), "flow.steps[1].ext.speed"),
    ("step extension not JSON", _set(["steps", 1, "ext"], "resources", {1, 2}),
     "flow.steps[1].ext.resources"),
    ("step extension NaN", _set(["steps", 1, "ext"], "arguments", {"n": float("nan")}),
     "flow.steps[1].ext.arguments"),
    ("step extension number key", _set(["steps", 1, "ext"], "arguments", {1: 2}),
     "flow.steps[1].ext.arguments"),
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
    flow["steps"][0].update(step_id="not a valid id!", title="x" * 1000 + "\nline",
                            timeout_seconds=-5, position={"x": 10 ** 9, "y": 0}, role_id="",
                            capability="")
    flow["steps"][3].update(bound=0)
    flow["links"][0].update({"from": "", "to": "nowhere"})
    assert settled_flow(flow) == flow


# --- compile_flow (spec 7.3) ----------------------------------------------------------------

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "flow"
CYCLES = ["desk-standard", "desk-short", "desk-starter-docs", "desk-standard-tester", "dalio-v5"]
BRIEF_AND_MATERIALS = ["artifact-brief", "artifact-materials"]


def compiled(flow):
    return flow_schema.compile_flow(flow)


def nodes_of(flow):
    return {row["node_id"]: row for row in compiled(flow)["nodes"]}


def fixture_flow(name):
    path = FIXTURES / f"{name}.flow-state.json"
    return json.loads(path.read_text(encoding="utf-8"))["flow"]


def review(step_id, **own):
    own = {"role_id": "role-analyst", "review_profile": "spec", **own}
    return step(step_id, "agent", capability="review", **own)


def chain(*steps):
    """A flow whose steps follow one another by `success` roads, in the order given."""
    links = [{"from": a["step_id"], "to": b["step_id"], "when": "success"}
             for a, b in zip(steps, steps[1:])]
    return {"flow_version": 1, "title": "Chain", "steps": list(steps), "links": links, "ext": {}}


def test_compile_writes_the_table_of_section_7_3_for_each_step_type():
    document = compiled(canonical_flow())
    assert document["schema_version"] == 1 and document["title"] == "Standard"
    assert document["execution_contract"] == "bounded-run-v1"
    assert "template_id" not in document and "revision" not in document
    nodes = {row["node_id"]: row for row in document["nodes"]}
    assert nodes["analyst"] == {
        "node_id": "analyst", "kind": "task", "title": "Analyst", "role_id": "role-analyst",
        "capability": "review", "resources": [],
        "arguments": {"work_item_id": "work-001", "target_artifact_refs": BRIEF_AND_MATERIALS,
                      "result_artifact_ref": "artifact-analyst", "review_profile": "spec"}}
    assert nodes["do"] == {
        "node_id": "do", "kind": "task", "title": "Doer", "role_id": "role-doer",
        "capability": "dispatch", "timeout_seconds": 1800, "verifier_role_id": "role-checker",
        "resources": [{"kind": "sandbox", "name": "project-root"}],
        "arguments": {"work_item_id": "work-001", "instruction_ref": "instruction-do",
                      "profile": "implement", "artifact_refs": ["artifact-analyst"],
                      "output_limit_profile": "normal"}}
    assert nodes["result"] == {
        "node_id": "result", "kind": "gate", "title": "Decision", "gate_id": "gate-result",
        "success_requires": "human_approval", "resources": []}
    assert nodes["do-fix"] == {
        "node_id": "do-fix", "kind": "loop", "title": "Loop", "resources": [],
        "loop": {"bound": 3, "back_to": "do"}}
    assert document["edges"] == [
        {"from_node": "analyst", "to_node": "do", "condition": "on_succeeded"},
        {"from_node": "do", "to_node": "result", "condition": "on_succeeded"},
        {"from_node": "do", "to_node": "do-fix", "condition": "on_failed"}]


def test_a_route_step_compiles_to_a_task_without_a_role():
    flow = chain(step("wait-here", "route"), step("done", "human"))
    assert nodes_of(flow)["wait-here"] == {
        "node_id": "wait-here", "kind": "task", "title": "Route", "resources": []}


def test_purpose_position_and_timeout_are_carried_when_set_and_left_out_when_not():
    flow = chain(review("plan", purpose="Plan it.", position={"x": 3, "y": -4},
                        timeout_seconds=900), step("done", "human"))
    nodes = nodes_of(flow)
    assert nodes["plan"]["purpose"] == "Plan it."
    assert nodes["plan"]["position"] == {"x": 3, "y": -4}
    assert nodes["plan"]["timeout_seconds"] == 900
    assert not {"purpose", "position", "timeout_seconds"} & set(nodes["done"])


@pytest.mark.parametrize("role,title", [
    ("role-analyst", "Analyst"), ("role-designer", "Designer"),
    ("role-diagnostician", "Diagnostician"), ("role-reviewer", "Reviewer"),
    ("role-doer", "Doer"), ("role-tester", "Tester"), ("role-doer-2", "Doer"),
    ("role-thinker", "thinker"), ("scribe", "scribe")])
def test_an_empty_title_takes_the_english_name_of_the_kind(role, title):
    flow = chain(step("a", "agent", role_id=role), step("done", "human"))
    assert nodes_of(flow)["a"]["title"] == title
    assert nodes_of(flow)["done"]["title"] == "Decision"


def test_a_title_the_author_wrote_is_kept():
    flow = chain(step("a", "agent", title="Read the brief"), step("done", "human", title="Sign"))
    assert [row["title"] for row in compiled(flow)["nodes"]] == ["Read the brief", "Sign"]


def test_entry_steps_read_brief_and_materials_and_others_read_the_nearest_reviews():
    plan, ideas = review("plan"), review("ideas", role_id="role-reviewer")
    scheme = review("scheme", role_id="role-designer", reads=["plan"])
    build, verify = step("build", "agent"), step("verify", "agent", role_id="role-tester")
    flow = chain(plan, ideas, scheme, build, verify, step("done", "human"))
    args = {sid: row["arguments"] for sid, row in nodes_of(flow).items() if "arguments" in row}
    assert args["plan"]["target_artifact_refs"] == BRIEF_AND_MATERIALS
    assert args["ideas"]["target_artifact_refs"] == ["artifact-plan"]
    assert args["scheme"]["target_artifact_refs"] == ["artifact-plan", "artifact-ideas"], (
        "reads join the nearest review, in the order of steps")
    assert args["build"]["artifact_refs"] == ["artifact-scheme"]
    assert args["verify"]["artifact_refs"] == ["artifact-scheme"], (
        "the search goes past a dispatch step to the nearest review above it")


def test_a_dispatch_entry_step_reads_brief_and_materials():
    flow = chain(step("do", "agent"), step("done", "human"))
    assert nodes_of(flow)["do"]["arguments"]["artifact_refs"] == BRIEF_AND_MATERIALS


def test_a_step_below_two_reviews_reads_both_in_the_order_of_steps():
    a, b, join = review("a"), review("b"), step("join", "agent")
    flow = {"flow_version": 1, "title": "Fork", "steps": [a, b, join], "ext": {},
            "links": [{"from": "a", "to": "join", "when": "success"},
                      {"from": "b", "to": "join", "when": "success"}]}
    assert nodes_of(flow)["join"]["arguments"]["artifact_refs"] == ["artifact-a", "artifact-b"]


def test_each_dispatch_step_has_its_own_instruction_unless_it_names_another():
    flow = chain(step("do", "agent"), step("test", "agent", role_id="role-tester"),
                 step("polish", "agent", instruction_from="do"), step("done", "human"))
    refs = {sid: row["arguments"]["instruction_ref"] for sid, row in nodes_of(flow).items()
            if row.get("capability") == "dispatch"}
    assert refs == {"do": "instruction-do", "test": "instruction-test", "polish": "instruction-do"}


def test_an_extension_key_replaces_the_computed_value_whole():
    override = {"work_item_id": "work-009", "instruction_ref": "instruction-plan",
                "profile": "implement", "artifact_refs": ["artifact-brief"]}  # a key fewer
    flow = chain(step("do", "agent", ext={
        "arguments": override, "resources": [], "stage": "do", "attempt_bound": 4,
        "required_evidence": "test_run", "failure_policy": "stop",
        "missing_artifact_policy": "stop"}), step("done", "human", ext={"gate_id": "gate-mine"}))
    nodes = nodes_of(flow)
    assert nodes["do"]["arguments"] == override
    assert nodes["do"]["resources"] == []
    assert {key: nodes["do"][key] for key in (
        "stage", "attempt_bound", "required_evidence", "failure_policy",
        "missing_artifact_policy")} == {
        "stage": "do", "attempt_bound": 4, "required_evidence": "test_run",
        "failure_policy": "stop", "missing_artifact_policy": "stop"}
    assert nodes["done"]["gate_id"] == "gate-mine"
    assert nodes["done"]["success_requires"] == "human_approval"


def test_a_null_success_requires_writes_no_such_field():
    flow = chain(step("do", "agent"), step("done", "human", ext={"success_requires": None}))
    assert "success_requires" not in nodes_of(flow)["done"]


def test_the_cycle_may_drop_its_execution_contract():
    flow = chain(step("done", "human"))
    assert compiled(flow)["execution_contract"] == "bounded-run-v1"
    flow["ext"] = {"execution_contract": None}
    assert "execution_contract" not in compiled(flow)


def test_tester_passes_compile_to_a_loop_home_to_the_nearest_upstream_doer():
    doer = step("do", "agent", verifier_role_id="role-checker")
    tester = step("tester", "agent", role_id="role-tester", verifier_role_id="role-checker")
    flow = chain(doer, tester, step("result", "human"))
    flow["steps"].append(step("tester-fix", "loop", back_to="do", bound=2))
    flow["links"].append({"from": "tester", "to": "tester-fix", "when": "failed"})
    document = compiled(flow)
    loop = next(row for row in document["nodes"] if row["node_id"] == "tester-fix")
    assert loop["loop"] == {"bound": 2, "back_to": "do"}
    assert document["edges"][-1] == {
        "from_node": "tester", "to_node": "tester-fix", "condition": "on_failed"}
    built = GraphTemplate.from_dict({**document, "template_id": "cycle-test", "revision": 1})
    assert [node.node_id for node in built.nodes][-1] == "tester-fix"


def test_compile_keeps_the_order_of_steps_and_links():
    flow = chain(step("z", "agent"), step("a", "agent", role_id="role-tester"), step("m", "human"))
    flow["links"].reverse()
    document = compiled(flow)
    assert [row["node_id"] for row in document["nodes"]] == ["z", "a", "m"]
    assert [(row["from_node"], row["to_node"]) for row in document["edges"]] == [
        ("a", "m"), ("z", "a")]


def test_an_unconditional_link_compiles_to_an_edge_without_a_condition():
    flow = chain(step("a", "agent"), step("b", "human"))
    flow["links"][0]["when"] = "always"
    assert compiled(flow)["edges"] == [{"from_node": "a", "to_node": "b"}]


def test_compile_of_another_capability_takes_its_arguments_from_ext_only():
    flow = chain(step("probe", "agent", capability="evidence"), step("done", "human"))
    assert nodes_of(flow)["probe"]["arguments"] == {}
    assert nodes_of(flow)["probe"]["resources"] == []
    said = {"target_action_id": "action-1", "kinds": ["test_run"]}
    flow["steps"][0]["ext"] = {"arguments": said}
    assert nodes_of(flow)["probe"]["arguments"] == said


def test_compile_does_not_alias_or_mutate_its_input():
    flow = canonical_flow()
    flow["steps"][1]["ext"] = {"arguments": {"files": ["a"]}}
    before = copy.deepcopy(flow)
    document = compiled(flow)
    assert flow == before
    document["nodes"][1]["arguments"]["files"].append("b")
    assert flow == before, "the document shares nothing with the flow it came from"


def test_compile_refuses_what_the_shape_refuses():
    flow = canonical_flow()
    flow["steps"][0]["bogus"] = 1
    with pytest.raises(FlowShapeError):
        compiled(flow)


@pytest.mark.parametrize("cycle", CYCLES)
def test_every_compiled_fixture_cycle_builds_a_template(cycle):
    document = compiled(fixture_flow(cycle))
    built = GraphTemplate.from_dict({**document, "template_id": "cycle-test", "revision": 1})
    assert [node.node_id for node in built.nodes] == [
        row["step_id"] for row in fixture_flow(cycle)["steps"]]
