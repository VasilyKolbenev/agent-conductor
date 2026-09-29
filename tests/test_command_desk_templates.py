"""The three ready cycles the desk offers (spec 7.9): `desk-standard`, `desk-short`,
`desk-starter-docs`, shipped as data in `command/templates/`.

Each file is a flow v1 (spec 7.2) compiled by `workflow_flow.compile_flow`, plus the name of the
file as `template_id` and `revision: 1`. The flows themselves are lane L's fixtures in
`tests/fixtures/flow/`, and the fixtures are the contract: a fixture and the spec that disagree
are reported, not edited. Every fact of 7.9 is therefore held twice -- once as "the file is the
fixture's flow compiled" and once as a claim written by hand from the spec, which the fixture
cannot vouch for itself. What the compiler does to any document, and the freezes over the
shipped bytes, are L's (spec 7.11 item 5); this file only holds the shape of these three.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from conductor.command.authorization_terms import AUTOMATION_CONTRACT
from conductor.command.contracts import canonical_json
from conductor.command.graph_template import TEMPLATE_DIR, load_template
from conductor.command.graph_template_document import GraphTemplate
from conductor.command.workflow_draft import starters
from conductor.command.workflow_flow import compile_flow

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "flow"
DESK = ("desk-standard", "desk-short", "desk-starter-docs")
BRIEF_AND_MATERIALS = ["artifact-brief", "artifact-materials"]
LANGUAGE_SENTENCE = "Answer in the language of the brief."
#: The roles the three cycles share, so that a harness assignment carries from one to the next.
SHARED_ROLES = {"role-analyst", "role-reviewer", "role-designer", "role-doer", "role-checker"}
#: The digest of each file's canonical JSON at revision 1. A published revision is frozen
#: (`templates/README.md`): a change of these bytes is a new revision and a new digest, on the
#: record. `test_command_workflow_routes.py` reads them to hold every shipped file unmoved.
DESK_DIGESTS = {
    "desk-standard": "109b1a448aa05336dc8bc5ff5a71afbbcf86475a085856db97ec4fcaaa641b41",
    "desk-short": "789f6c26ce6d5b1d3a3209dd18f1a44a01e7f20387646f9b406653ea13a1508d",
    "desk-starter-docs": "b5db65bc9826ce7ef34f2d0b00a4eaf8a04578eada4d4d2621cc9058a97bf3e2",
}
#: Harness and vendor words; a template names roles and nothing about a deployment.
DEPLOYMENT_WORDS = ("claude", "codex", "grok", "kimi", "qwen", "deepseek", "anthropic", "openai",
                    "gemini", "dsh", "gpt", "glm")


def shipped(name: str) -> dict:
    return json.loads((TEMPLATE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def fixture_state(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.flow-state.json").read_text(encoding="utf-8"))


def nodes_of(name: str) -> dict[str, dict]:
    return {node["node_id"]: node for node in shipped(name)["nodes"]}


def edges_of(name: str) -> list[tuple[str, str, str | None]]:
    return [(edge["from_node"], edge["to_node"], edge.get("condition"))
            for edge in shipped(name)["edges"]]


def agent_nodes(name: str) -> list[dict]:
    return [node for node in shipped(name)["nodes"] if "capability" in node]


@pytest.mark.parametrize("name", DESK)
def test_each_desk_template_file_is_its_fixture_flow_compiled_under_its_own_name_and_revision_one(
        name):
    flow = fixture_state(name)["flow"]
    expected = {**compile_flow(flow), "template_id": name, "revision": 1}
    assert canonical_json(shipped(name)) == canonical_json(expected)


@pytest.mark.parametrize("name", DESK)
def test_a_desk_template_loads_through_the_contract_and_is_offered_by_its_file_name(name):
    template = load_template(name)
    assert template.template_id == name and template.revision == 1
    assert GraphTemplate.from_dict(shipped(name)).as_dict() == template.as_dict()
    offered = {row["starter_id"]: row for row in starters()}
    assert offered[name]["title"] == template.title == fixture_state(name)["flow"]["title"]
    assert offered[name]["revision"] == 1 and offered[name]["caveats"] == []
    assert offered[name]["document"]["template_id"] == name


@pytest.mark.parametrize("name", DESK)
def test_a_desk_template_keeps_the_digest_its_first_revision_was_shipped_with(name):
    digest = hashlib.sha256(canonical_json(shipped(name)).encode("utf-8")).hexdigest()
    assert digest == DESK_DIGESTS[name], (
        f"{name} moved: a change is revision 2 with a new digest, not an edit of revision 1")


def test_desk_template_files_are_exactly_the_three_the_spec_names():
    found = sorted(path.stem for path in TEMPLATE_DIR.glob("desk-*.json"))
    assert found == sorted(DESK)


def test_desk_standard_is_analyst_then_do_then_the_result_gate_with_three_passes():
    nodes = nodes_of("desk-standard")
    assert list(nodes) == ["analyst", "do", "result", "do-fix"]
    analyst, do = nodes["analyst"], nodes["do"]
    assert (analyst["role_id"], analyst["capability"]) == ("role-analyst", "review")
    assert analyst["arguments"]["review_profile"] == "spec"
    assert analyst["arguments"]["target_artifact_refs"] == BRIEF_AND_MATERIALS
    assert (do["role_id"], do["capability"]) == ("role-doer", "dispatch")
    assert do["verifier_role_id"] == "role-checker"
    assert do["arguments"]["instruction_ref"] == "instruction-do"
    assert do["arguments"]["artifact_refs"] == ["artifact-analyst"]
    assert nodes["result"]["kind"] == "gate" and nodes["result"]["success_requires"] == (
        "human_approval")
    assert nodes["do-fix"]["kind"] == "loop"
    assert nodes["do-fix"]["loop"] == {"bound": 3, "back_to": "do"}
    assert edges_of("desk-standard") == [("analyst", "do", "on_succeeded"),
                                         ("do", "result", "on_succeeded"),
                                         ("do", "do-fix", "on_failed")]


def test_desk_short_is_do_then_the_result_gate_with_two_passes_and_reads_the_brief_directly():
    nodes = nodes_of("desk-short")
    assert list(nodes) == ["do", "result", "do-fix"]
    do = nodes["do"]
    assert (do["role_id"], do["capability"], do["verifier_role_id"]) == (
        "role-doer", "dispatch", "role-checker")
    assert do["arguments"]["instruction_ref"] == "instruction-do"
    assert do["arguments"]["artifact_refs"] == BRIEF_AND_MATERIALS
    assert nodes["do-fix"]["loop"] == {"bound": 2, "back_to": "do"}
    assert edges_of("desk-short") == [("do", "result", "on_succeeded"),
                                      ("do", "do-fix", "on_failed")]


def test_desk_starter_docs_is_a_chain_of_three_reviews_and_no_dispatch():
    nodes = nodes_of("desk-starter-docs")
    assert list(nodes) == ["plan", "ideas", "scheme", "result"]
    roles = {step: (nodes[step]["role_id"], nodes[step]["arguments"]["review_profile"])
             for step in ("plan", "ideas", "scheme")}
    assert roles == {"plan": ("role-analyst", "spec"), "ideas": ("role-reviewer", "quality"),
                     "scheme": ("role-designer", "spec")}
    assert {node["capability"] for node in agent_nodes("desk-starter-docs")} == {"review"}
    assert nodes["plan"]["arguments"]["target_artifact_refs"] == BRIEF_AND_MATERIALS
    assert nodes["ideas"]["arguments"]["target_artifact_refs"] == ["artifact-plan"]
    assert nodes["scheme"]["arguments"]["target_artifact_refs"] == [
        "artifact-plan", "artifact-ideas"]
    assert edges_of("desk-starter-docs") == [("plan", "ideas", "on_succeeded"),
                                             ("ideas", "scheme", "on_succeeded"),
                                             ("scheme", "result", "on_succeeded")]


@pytest.mark.parametrize("name", DESK)
def test_desk_templates_write_every_timeout_and_close_each_purpose_with_the_language_sentence(name):
    for node in agent_nodes(name):
        assert node["timeout_seconds"] == 1800, node["node_id"]
        purpose = node["purpose"]
        assert purpose.isascii() and len(purpose) <= 500, node["node_id"]
        assert purpose.endswith(LANGUAGE_SENTENCE), node["node_id"]


@pytest.mark.parametrize("name", DESK)
def test_desk_templates_share_the_five_roles_and_name_no_harness(name):
    document = shipped(name)
    named = {node["role_id"] for node in document["nodes"] if "role_id" in node}
    named |= {node["verifier_role_id"] for node in document["nodes"] if "verifier_role_id" in node}
    assert named <= SHARED_ROLES
    text = (TEMPLATE_DIR / f"{name}.json").read_text(encoding="utf-8").lower()
    for word in DEPLOYMENT_WORDS:
        assert not re.search(rf"\b{word}\b", text), word


@pytest.mark.parametrize("name", DESK)
def test_desk_templates_run_under_the_bounded_contract_that_allows_a_dispatch_without_a_gate(name):
    assert shipped(name)["execution_contract"] == AUTOMATION_CONTRACT == "bounded-run-v1"
    kinds = {node["kind"] for node in shipped(name)["nodes"]}
    assert "gate" in kinds, "the last word stays with a person (spec 3)"


@pytest.mark.parametrize("name", DESK)
def test_the_fixture_and_the_file_agree_on_how_the_steps_are_titled(name):
    flow = fixture_state(name)["flow"]
    assert all(step["title"] is None for step in flow["steps"]), (
        "step titles are null in a flow (spec 7.9); the desk translates the kind's name")
    assert all(node["title"] for node in shipped(name)["nodes"])
