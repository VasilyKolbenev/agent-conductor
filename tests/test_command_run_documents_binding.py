"""What the documents a run is opened with do to `bind_inputs` (spec 6.2.3, 6.2.5, 7.3).

A cycle reads two documents at its entry and one instruction per dispatch step. The desk
publishes them through the run's own doors (the artifacts route and the materials route), and the
authorization then binds what stands. These tests run that road on the shipped cycles and on one
flow whose two dispatch steps share an instruction, and judge each claim of 6.2.5 against the
relation itself: the documents go in through the routes, and `bind_inputs` reads the journal they
left.

The entry steps are found here by the definition of 7.3 (a step with no review anywhere above it
along the roads), independently of the compiler, so that a shipped file and the compiler are not
each other's witness.
"""
from __future__ import annotations

import pytest

from conductor.command.authorization_inputs import bind_inputs
from conductor.command.authorization_terms import AUTOMATION_CONTRACT
from conductor.command.contract_values import ContractError
from conductor.command.graph_template import (
    TEMPLATE_DIR, GraphTemplate, RunBinding, load_template, materialize)
from conductor.command.workflow_flow import compile_flow
from tests.test_command_http_api import NOW, RUN_ID, api, post
from tests.test_command_workflow_flow import chain, step

DESK = ("desk-standard", "desk-short", "desk-starter-docs")
DALIO = tuple(sorted(path.stem for path in TEMPLATE_DIR.glob("dalio-*.json")))
BRIEF_AND_MATERIALS = ["artifact-brief", "artifact-materials"]
#: The one step each shipped desk cycle enters by, written out so that a cycle that gained or lost
#: an entry step is a change of this table and not of a computed expectation.
ENTRY = {"desk-standard": ["analyst"], "desk-short": ["do"], "desk-starter-docs": ["plan"]}
CONFIG = {"cycle": {"id": RUN_ID}, "workflow": {"id": "workflow-one", "revision": 1},
          "automation_contract": AUTOMATION_CONTRACT,
          "instances": [{"id": "doer", "adapter": "claude-code"},
                        {"id": "checker", "adapter": "codex-cli"}]}


def plan_of(document):
    """The plan of a workflow document on one run, every role bound to a doer or the checker."""
    template = GraphTemplate.from_dict({**document, "template_id": "template-one", "revision": 1})
    binding = RunBinding(assignments={
        role: "checker" if role == "role-checker" else "doer" for role in template.roles})
    return materialize(template, binding, CONFIG, graph_id="graph-one", run_id=RUN_ID,
                       created_at=NOW)


def published(store):
    return tuple(row.value for row in store.read(RUN_ID).records)


def accepts(plan, store):
    try:
        bind_inputs(plan, published(store))
    except ContractError:
        return False
    return True


def publish(subject, ref, content="text\n"):
    body = {"artifact_id": f"doc-{ref}", "artifact_ref": ref, "media_type": "text/markdown",
            "content": content}
    assert post(subject, f"/command/runs/{RUN_ID}/artifacts", body).status == 201


def publish_materials(subject, *items):
    answer = post(subject, f"/command/runs/{RUN_ID}/materials",
                  {"lang": "en", "items": list(items)})
    assert answer.status == 201
    return answer


def entry_nodes(document):
    """The agent steps with no review above them along the roads (spec 7.3), in file order."""
    nodes = {node["node_id"]: node for node in document["nodes"]}
    parents: dict[str, set[str]] = {}
    for edge in document["edges"]:
        parents.setdefault(edge["to_node"], set()).add(edge["from_node"])

    def review_above(node_id, seen=frozenset()):
        return any(nodes[parent].get("capability") == "review"
                   or (parent not in seen and review_above(parent, seen | {parent}))
                   for parent in parents.get(node_id, ()))

    return [node_id for node_id, node in nodes.items()
            if node.get("capability") in {"dispatch", "review"} and not review_above(node_id)]


def inputs_of(node):
    key = "target_artifact_refs" if node["capability"] == "review" else "artifact_refs"
    return node["arguments"][key]


# --- the entry steps of the shipped cycles ----------------------------------------------------


@pytest.mark.parametrize("name", DESK)
def test_entry_nodes_read_brief_and_materials_in_every_bundled_desk_template(name):
    document = load_template(name).as_dict()
    nodes = {node["node_id"]: node for node in document["nodes"]}
    assert entry_nodes(document) == ENTRY[name]
    assert [inputs_of(nodes[node_id]) for node_id in ENTRY[name]] == [BRIEF_AND_MATERIALS]
    later = [node for node_id, node in nodes.items()
             if node.get("capability") and node_id not in ENTRY[name]]
    assert all(not set(BRIEF_AND_MATERIALS) & set(inputs_of(node)) for node in later), (
        "a step below a review reads that review, not the documents the run was opened with")


def test_the_frozen_dalio_revisions_enter_by_the_brief_alone():
    """Why the test above says `desk`: the five Dalio files are published revisions, replayed by
    every run that used them, so they keep the inputs they were published with."""
    assert DALIO == tuple(f"dalio-v{number}" for number in range(1, 6))
    for name in DALIO:
        document = load_template(name).as_dict()
        entries = entry_nodes(document)
        assert entries == ["goal"], name
        nodes = {node["node_id"]: node for node in document["nodes"]}
        assert inputs_of(nodes["goal"]) == ["artifact-brief"], name


# --- the documents that are always published --------------------------------------------------


@pytest.mark.parametrize("name", DESK)
def test_brief_and_materials_are_always_published_so_bind_inputs_never_refuses(tmp_path, name):
    subject, store, _ = api(tmp_path)
    plan = plan_of(load_template(name).as_dict())
    publish(subject, "artifact-brief", "# Task\n")
    for node in plan.nodes:
        if node.capability == "dispatch":
            publish(subject, node.arguments["instruction_ref"], "Do it.\n")
    assert not accepts(plan, store), "without the materials the cycle cannot be bound"
    empty = publish_materials(subject)
    assert "No materials" in empty.payload["content"]
    assert accepts(plan, store)


def test_a_materials_document_with_items_binds_like_the_one_that_says_there_are_none(tmp_path):
    subject, store, _ = api(tmp_path)
    plan = plan_of(load_template("desk-short").as_dict())
    publish(subject, "artifact-brief")
    publish(subject, "instruction-do")
    publish_materials(subject, {"kind": "note", "title": "A note", "content": "Text."})
    assert accepts(plan, store)


# --- one instruction for two dispatch steps ---------------------------------------------------


def shared_instruction_plan():
    flow = chain(step("do", "agent", verifier_role_id="role-checker"),
                 step("polish", "agent", instruction_from="do", verifier_role_id="role-checker"),
                 step("done", "human"))
    return plan_of(compile_flow(flow))


def test_one_instruction_document_binds_two_dispatch_nodes(tmp_path):
    subject, store, _ = api(tmp_path)
    plan = shared_instruction_plan()
    publish(subject, "artifact-brief")
    publish_materials(subject)
    assert not accepts(plan, store), "the shared instruction is still to be published"
    publish(subject, "instruction-do", "Do it, then polish it.\n")
    instructions, _inputs = bind_inputs(plan, published(store))
    assert [row.node_id for row in instructions] == ["do", "polish"]
    assert len({row.artifact_id for row in instructions}) == 1
    assert len({row.content_digest for row in instructions}) == 1
