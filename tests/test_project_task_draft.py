"""Only one verified active project's authenticated editor can hold a volatile draft."""
from concurrent.futures import ThreadPoolExecutor
import json

import pytest
from conductor.command.project_claim import ProjectIdentity
from tests.test_command_http_api import TOKEN, api, post_headers

PROJECT = "a" * 32
PATH = "/command/project/task-draft"
TASK = "task-123456789abc"


def installation(tmp_path):
    subject, store, events = api(tmp_path)
    subject._identity = ProjectIdentity(PROJECT, None, False, "active", None, None)
    return subject, store, events


def call(subject, op, *, claim=PROJECT, token=TOKEN, project=PROJECT, **data):
    body = {"op": op, "project": project, **data}
    payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    headers = list(post_headers(body, token=token, length=len(payload)))
    if claim is not None:
        headers.append(("X-Conduct-Project", claim))
    return subject.handle("POST", PATH, headers, payload)


def answers(text="Сверить отчёт 🧭"):
    return dict(title=text, brief=text, hint="", titleEdited=False, guided=True, withoutGit=True,
                includeInstructions=None, items=[], cycleId="dalio-v6", owner={}, instructions={},
                models={"role-checker": {"provider": "codex", "text": "gpt-6.1-sol"}})


def test_editable_draft_is_scoped_without_creating_any_run_task_or_events(tmp_path):
    subject, store, events = installation(tmp_path)
    before = store.read("run-001").records
    assert call(subject, "open", task=TASK, claim=None).status == 409
    assert call(subject, "open", task=TASK, token="not-this-session").status == 403
    opened = call(subject, "open", task=TASK)
    assert opened.status == 201, opened.payload
    key = opened.payload["key"]
    assert len(key) == 32
    assert call(subject, "save", key=key, base=0, answers=answers()).payload == {"revision": 1}
    assert call(subject, "read", key=key).payload == {
        "task": TASK, "revision": 1, "answers": answers()}
    assert call(subject, "read", key=key, project="b"*32).status == 409
    assert call(subject, "save", key=key, base=0, answers=answers("other tab")).status == 409
    assert call(subject, "save", key=key, base=0, answers=answers()).payload == {"revision": 1}
    assert call(subject, "save", key=key, base=1, answers={**answers(), "authorization": {}}).status == 422
    assert call(subject, "discard", key=key, base=0).status == 409
    assert call(subject, "discard", key=key, base=1).status == 200
    assert call(subject, "save", key=key, base=1, answers=answers()).status == 404
    assert call(subject, "read", key=key).status == 404
    assert store.read("run-001").records == before
    assert not list(subject._tasks.tasks()) and events == []


def test_exhaustion_and_expiry_never_allocate_on_read_or_reopen_old_key(tmp_path):
    subject, _, _ = installation(tmp_path)
    tick = [100.]
    subject._task_drafts.clock = lambda: tick[0]
    for index in range(20):
        assert call(subject, "read", key=f"{index:032x}").status == 404
    keys = [call(subject, "open", task=TASK).payload["key"] for _ in range(16)]
    assert len(set(keys)) == 16 and call(subject, "open", task=TASK).status == 409
    assert call(subject, "save", key=keys[0], base=0, answers=answers("Ж"*9000)).status == 422
    tick[0] += 1800
    assert call(subject, "save", key=keys[0], base=0, answers=answers()).status == 404
    assert call(subject, "open", task=TASK).payload["key"] not in keys


def test_two_tabs_cannot_replace_each_others_edit_and_restart_forgets_input(tmp_path):
    subject, _, _ = installation(tmp_path)
    key = call(subject, "open", task=TASK).payload["key"]
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda text: call(subject, "save", key=key, base=0,
                                                  answers=answers(text)).status, ["left", "right"]))
    assert sorted(outcomes) == [200, 409]
    subject._identity = ProjectIdentity(PROJECT, None, False, "view", None, None)
    assert call(subject, "read", key=key).status == 409
    restarted, _, _ = installation(tmp_path / "other")
    assert call(restarted, "read", key=key).status == 404


@pytest.mark.parametrize("extra", [
    {"actor": "private"}, {"preview": {"body": "private"}}, {"owner": {"role": ["private"]}},
    {"models": {"role": {"provider": "codex", "text": "hello", "token": "private"}}},
    {"items": [{"kind": "project_doc", "docId": "d-"+"a"*32, "gitOid": "c"*40, "mode": "copy",
                "edits": [], "content": "private repository text"}]},
])
def test_only_editable_fields_cross_and_refusals_do_not_echo_their_values(tmp_path, extra):
    subject, _, _ = installation(tmp_path)
    key = call(subject, "open", task=TASK).payload["key"]
    refused = call(subject, "save", key=key, base=0, answers={**answers(), **extra})
    assert refused.status == 422 and "private" not in str(refused.payload)
    assert call(subject, "read", key=key).payload["answers"] is None
