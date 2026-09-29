"""The corners of `import_template` (spec 7.3): it is total, and it types what the rules accept.

Two things are held here. Every document a template accepts becomes a flow, so a gate or a loop
that binds a role imports, its binding going to `ext`, and compiling the flow gives the document
back. And what the importer says with a typed field (`reads`, `instruction_from`) is only what
`flow_rules` would accept, so an imported flow is never judged worse than the document it came
from; whatever the typed fields cannot say stays whole in `ext.arguments`.
"""
import json

import pytest

from conductor.command import flow_rules, workflow_flow as flow_schema
from conductor.command.graph_template import TEMPLATE_DIR
from conductor.command.workflow_flow import FlowShapeError, settled_flow
from tests.test_command_flow_routes import WORKFLOW_ID, flow_path
from tests.test_command_workflow_flow import (
    BOUNDED, SANDBOX, STUDIO_CORPUS, accepted, chain, compiled, dispatch_node, edge, gate_node,
    imported, loop_node, review, review_node, same, step, template, without_identity)
from tests.test_command_workflow_routes import api, get, post


def binding(node, role, capability, **more):
    """A gate or a loop that binds a role, the way the core accepts one."""
    return {**node, "role_id": role, "capability": capability, "arguments": {}, **more}


BOUND = {
    "a gate that binds a review role": template(
        [binding(gate_node("g"), "role-analyst", "review")], [], **BOUNDED),
    "a gate that binds a dispatch role and a verifier": template(
        [binding(gate_node("g"), "role-doer", "dispatch", verifier_role_id="role-checker")],
        [], **BOUNDED),
    "a gate that binds a role and carries arguments": template(
        [binding(gate_node("g"), "role-analyst", "review", arguments={"note": 1})], [], **BOUNDED),
    "a gate that binds a role and holds resources": template(
        [binding(gate_node("g"), "role-analyst", "review", resources=SANDBOX)], [], **BOUNDED),
    "a gate that binds a role in a template with no contract": template(
        [binding(gate_node("g"), "role-analyst", "review")], []),
    "a loop that binds a role": template(
        [dispatch_node("do", ["artifact-brief"]),
         binding(loop_node("fix", "do", 2), "role-analyst", "review")],
        [edge("do", "fix", "on_failed")], **BOUNDED),
    "a loop that binds a role and a verifier": template(
        [dispatch_node("do", ["artifact-brief"]),
         binding(loop_node("fix", "do", 2), "role-doer", "dispatch",
                 verifier_role_id="role-checker")],
        [edge("do", "fix", "on_failed")], **BOUNDED),
    "a gate that binds a role beside an ordinary review": template(
        [review_node("goal", ["artifact-brief"]),
         binding(gate_node("g"), "role-designer", "review")],
        [edge("goal", "g", "on_succeeded")], **BOUNDED),
}


@pytest.mark.parametrize("name", sorted(BOUND))
def test_a_gate_or_a_loop_that_binds_a_role_imports_and_compiles_back_to_the_same_document(name):
    document = accepted(BOUND[name])
    flow = imported(document)
    assert settled_flow(flow) == flow
    assert same(compiled(flow), without_identity(document))


def test_the_binding_of_a_gate_lands_in_its_ext_and_no_typed_field_of_the_flow_moves():
    document = accepted(BOUND["a gate that binds a dispatch role and a verifier"])
    only, = imported(document)["steps"]
    assert only["type"] == "human"
    assert only["ext"] == {"role_id": "role-doer", "capability": "dispatch",
                           "verifier_role_id": "role-checker", "arguments": {},
                           "success_requires": None}  # this gate demands nothing of its answer
    assert set(only) == set(flow_schema.STEP_FIELDS["human"])


def test_the_binding_of_a_loop_lands_in_its_ext_beside_its_typed_bound_and_back_to():
    flow = imported(accepted(BOUND["a loop that binds a role"]))
    loop = flow["steps"][1]
    assert (loop["type"], loop["back_to"], loop["bound"]) == ("loop", "do", 2)
    assert loop["ext"] == {"role_id": "role-analyst", "capability": "review", "arguments": {}}


def test_a_gate_that_binds_nothing_gets_no_binding_key_in_its_ext():
    flow = imported(accepted(STUDIO_CORPUS["a gate that demands nothing"]))
    assert flow["steps"][0]["ext"] == {"success_requires": None}


def test_the_two_sets_name_exactly_the_role_keys_a_flow_types_only_on_an_agent():
    assert flow_schema.BOUND_EXT_FIELDS == {"role_id", "capability", "verifier_role_id"}
    assert not flow_schema.BOUND_EXT_FIELDS & flow_schema.EXT_FIELDS
    agent_typed = set(flow_schema.STEP_FIELDS["agent"])
    assert flow_schema.BOUND_EXT_FIELDS <= agent_typed
    assert {kind: sorted(keys) for kind, keys in flow_schema.STEP_EXT_FIELDS.items()} == {
        "agent": sorted(flow_schema.EXT_FIELDS), "route": sorted(flow_schema.EXT_FIELDS),
        "human": sorted(flow_schema.EXT_FIELDS | flow_schema.BOUND_EXT_FIELDS),
        "loop": sorted(flow_schema.EXT_FIELDS | flow_schema.BOUND_EXT_FIELDS)}


@pytest.mark.parametrize("kind", ["agent", "route"])
@pytest.mark.parametrize("key", ["role_id", "capability", "verifier_role_id"])
def test_a_role_key_in_the_ext_of_an_agent_or_a_route_is_refused_by_the_form(kind, key):
    flow = chain(step("only", kind), step("result", "human"))
    flow["steps"][0]["ext"] = {key: "role-x"}
    with pytest.raises(FlowShapeError) as refused:
        settled_flow(flow)
    assert refused.value.path == f"flow.steps[0].ext.{key}"


@pytest.mark.parametrize("kind", ["human", "loop"])
def test_a_role_key_in_the_ext_of_a_gate_or_a_loop_settles(kind):
    flow = chain(step("do", "agent", verifier_role_id="role-checker"), step("result", "human"))
    flow["steps"].append(step("extra", kind))
    flow["steps"][-1]["ext"] = {"role_id": "role-x", "capability": "review",
                                "verifier_role_id": "role-y"}
    assert settled_flow(flow) == flow


def test_a_role_key_alone_in_the_ext_of_a_gate_is_an_ext_invalid_row_at_that_step():
    flow = chain(review("plan"), step("ask", "human"))
    flow["steps"][1]["ext"] = {"role_id": "role-analyst"}
    rows = [row for row in flow_rules.flow_rules(flow) if row["code"] == "ext_invalid"]
    assert rows == [{"code": "ext_invalid", "severity": "error", "at": {"step_id": "ask"},
                     "params": {"field": "role_id"}}]


def test_a_stored_revision_with_a_bound_gate_reads_back_as_a_flow_and_publishes_unchanged(
        tmp_path):
    subject, _store, templates, _events = api(tmp_path)
    document = without_identity(accepted(BOUND["a gate that binds a review role"]))
    stored = post(subject, f"/command/workflows/{WORKFLOW_ID}/revisions",
                  {"revision": 1, "document": document})
    assert stored.status == 201, stored.payload
    read = get(subject, flow_path()).payload
    assert read["flow"] is not None and read["source"] == "published"
    assert read["flow"]["steps"][0]["ext"]["role_id"] == "role-analyst"
    assert read["publishable"] is True
    again = post(subject, flow_path(), {
        "source": {"copy_of": {"workflow_id": WORKFLOW_ID, "revision": 1}},
        "expected_absent": True, "publish_revision": 2})
    assert again.status == 200 and again.payload["published"] == {"revision": 1, "created": False}
    assert list(templates.revisions(WORKFLOW_ID)) == [1]


def test_the_shipped_templates_and_the_studio_corpus_keep_their_ext_free_of_role_keys():
    documents = [accepted(raw) for raw in STUDIO_CORPUS.values()]
    documents += [json.loads(path.read_text(encoding="utf-8"))
                  for path in sorted(TEMPLATE_DIR.glob("*.json"))]
    for document in documents:
        for row in imported(document)["steps"]:
            assert not flow_schema.BOUND_EXT_FIELDS & set(row["ext"])
