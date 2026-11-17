"""A colleague's own second task keeps its review plan across Studio sessions."""
from copy import deepcopy
from runpy import run_path

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.project_claim import ProjectIdentity
from conductor.command.run_store import RunStore
from conductor.command.task_store import TaskStore
from conductor.ownership import acquire_owner
from tests.test_command_http_api import NOW, PORT, TOKEN, encode, get_headers, ids, post_headers
from tests.test_pilot_project_paths import CREATE, personal_project


PROJECT_ID = "1" * 32


def server(root, mode):
    return CommandApi(RunStore(root), AdapterRegistry([]), session=CommandSession(PORT, TOKEN),
                      budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=ids(),
                      publish_run=lambda _: pytest.fail("unexpected run publication"),
                      identity=ProjectIdentity(PROJECT_ID, None, False, mode, None, None))


@pytest.fixture
def personal(tmp_path_factory):
    with personal_project(False, tmp_path_factory.getbasetemp()) as root:
        run, second = run_path(str(CREATE))["create"](
            root, "First", "Second", [("Read diff", "one file")], "Ada", accepted=True)
        records = RunStore(root).read(run)
        source = dict(task_id=records.config["task"]["id"], run_id=run,
                      artifact_id=records.records[1].value.artifact_id,
                      receipt_id=records.records[2].value.receipt_id)
        with acquire_owner(root):
            yield root, second, dict(version=1, steps=["Read diff"], reviewer="Ada", source=source)


def get(api, task_id):
    return api.handle("GET", f"/command/tasks/{task_id}/review-plan", get_headers())


def save(api, task_id, plan, revision=0, claim=PROJECT_ID):
    body = dict(plan=plan, expected_revision=revision)
    headers = post_headers(body) + ((("X-Conduct-Project", claim),) if claim else ())
    return api.handle("POST", f"/command/tasks/{task_id}/review-plan", headers, encode(body))


def test_persist_reopen_and_compare_and_swap(personal):
    root, second, plan = personal
    before = RunStore(root).read(plan["source"]["run_id"])
    identity = (TaskStore(root).task_path(second) / "task.json").read_bytes()
    writer = server(root, "active")
    assert get(writer, second).payload == {"revision": 0, "plan": None}
    saved = save(writer, second, plan)
    assert (saved.status, saved.payload) == (200, {"revision": 1, "plan": plan})
    assert get(server(root, "view"), second).payload == saved.payload
    assert save(writer, second, plan).payload == saved.payload
    edited = dict(plan, version=2, reviewer="Maya", steps=["Check tests", "Read diff"])
    assert save(writer, second, edited).status == 409
    assert save(writer, second, edited, 1).payload == {"revision": 2, "plan": edited}
    assert get(server(root, "view"), second).payload == {"revision": 2, "plan": edited}
    assert (TaskStore(root).task_path(second) / "task.json").read_bytes() == identity
    assert RunStore(root).read(plan["source"]["run_id"]) == before


def test_wrong_source_or_authority_cannot_write(personal):
    root, second, plan = personal
    active = server(root, "active")
    assert save(server(root, "view"), second, plan).payload["error"]["code"] == "project_not_active"
    assert save(active, second, plan, claim=None).payload["error"]["code"] == "project_mismatch"
    for key in plan["source"]:
        wrong = deepcopy(plan)
        wrong["source"][key] = "other-id"
        assert 400 <= save(active, second, wrong).status < 500
    assert 400 <= save(active, plan["source"]["task_id"], plan).status < 500
    assert 400 <= save(active, second, dict(plan, steps=[])).status < 500
    assert get(active, second).payload == {"revision": 0, "plan": None}
