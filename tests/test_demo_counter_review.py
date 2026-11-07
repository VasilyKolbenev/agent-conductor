"""A provider-free run is confined to the frozen, human-only exercise in conduct demo."""
import pytest

from conductor.command import demo_review
from conductor.command.adapters.base import AdapterRegistry
from conductor.command.graph_template import GraphTemplate
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.project_claim import ProjectIdentity
from conductor.command.run_store import RunStore
from conductor.command.template_store import TemplateStore
from tests.test_command_workflow_routes import NOW, PORT, TOKEN, code_of, ids, post


def project(root, *, demo, changed_template=False):
    (root / "conductor").mkdir()
    templates = TemplateStore(root)
    template = demo_review.template()
    if changed_template:
        text = template.as_dict()
        text["nodes"][0]["purpose"] = "A different exercise"
        template = GraphTemplate.from_dict(text)
    templates.save(template)
    store = RunStore(root)
    api = CommandApi(store, AdapterRegistry([]), templates=templates,
                     session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
                     identity=ProjectIdentity(None, None, demo, "active", None, None),
                     clock=lambda: NOW, ids=ids(), publish_run=lambda _: None)
    assert post(api, "/command/tasks", {"task_id": "mine", "title": "Count checks"}).status == 201
    return api, store


def request(**patch):
    return {"run_id": "practice-mine", "cycle_id": "demo-counter-review", "task_id": "mine",
            "workflow_id": "demo-counter-review", "revision": 1, "mode": "confirm",
            "participants": [], "assignments": {}, **patch}


@pytest.mark.parametrize("demo,changed,patch", [
    (False, False, {}), (True, True, {}), (True, False, {"workflow_id": "release-review"}),
    (True, False, {"task_id": None}), (True, False, {"mode": "policy"}),
    (True, False, {"revision": 2}), (True, False, {"assignments": {"role": "vendor"}}),
])
def test_other_empty_teams_are_refused(tmp_path, demo, changed, patch):
    api, store = project(tmp_path, demo=demo, changed_template=changed)
    reply = post(api, "/command/runs", request(**patch))
    assert code_of(reply) == "contract_invalid"
    assert not store.run_path("practice-mine").exists()


def test_double_open_is_one_unanswered_gate_on_the_named_task(tmp_path):
    api, store = project(tmp_path, demo=True)
    assert post(api, "/command/runs", request()).status == 201
    assert post(api, "/command/runs", request()).status == 200
    recovered = store.read("practice-mine")
    assert recovered.config["task"]["id"] == "mine"
    assert [row.kind for row in recovered.records] == ["graph_definition"]
    assert [node.kind for node in recovered.records[0].value.nodes] == ["gate"]
