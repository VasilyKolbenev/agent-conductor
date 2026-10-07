"""Execute the task boundary: malformed navigation must never become authority."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "conductor" / "panel"


def _js(body: str):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to execute the Studio value modules")
    source = (f"import * as tasks from {json.dumps((PANEL / 'studio-tasks-model.js').as_uri())};\n"
              f"import * as nav from {json.dumps((PANEL / 'studio-taskflow.js').as_uri())};\n"
              f"import {{EMPTY, reduce}} from {json.dumps((PANEL / 'studio-store.js').as_uri())};\n"
              + body)
    result = subprocess.run([node, "--input-type=module", "-e", source],
                            capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _row(**patch):
    return {"schema_version": 1, "task_id": "task-a", "title": "Same name",
            "work_scope": "scope-a", "created_at": "2026-09-21T10:00:00Z",
            "unreadable": False, **patch}


@pytest.mark.parametrize("patch", [
    {"task_id": "a" * 65}, {"work_scope": "a" * 65}, {"title": "bad\nname"},
    {"title": " "}, {"title": "x" * 201}, {"created_at": "yesterday"},
    {"schema_version": 2}, {"unreadable": "false"}, {"foreign": "value"},
])
def test_task_list_refuses_a_malformed_row_whole(patch):
    payload = json.dumps({"tasks": [_row(), _row(**{"task_id": "task-b", **patch})]})
    assert _js(f"console.log(JSON.stringify(tasks.projectTasks({payload}))); ") is None


def test_duplicate_names_remain_separate_but_duplicate_ids_are_refused():
    payload = json.dumps({"tasks": [_row(), _row(task_id="task-b", work_scope="scope-b")]})
    assert _js(f"console.log(JSON.stringify(tasks.projectTasks({payload}).map(r => r.task_id)));") == ["task-a", "task-b"]
    payload = json.dumps({"tasks": [_row(), _row()]})
    assert _js(f"console.log(JSON.stringify(tasks.projectTasks({payload}))); ") is None


def test_missing_unreadable_and_stale_tasks_never_open_a_new_run():
    payload = json.dumps({"tasks": [_row()]})
    body = f"""
    let state = reduce(EMPTY, {{type:'tasks-loaded', payload:{payload}}});
    const answers = [tasks.canOpenTask(state)];
    state = reduce(state, {{type:'task-chosen', taskId:'missing'}});
    answers.push(tasks.canOpenTask(state));
    state = reduce(state, {{type:'task-chosen', taskId:'task-a'}});
    answers.push(tasks.canOpenTask(state));
    state = reduce(state, {{type:'tasks-phase', phase:'failed'}});
    answers.push(tasks.canOpenTask(state));
    console.log(JSON.stringify(answers));
    """
    assert _js(body) == [False, False, True, False]


def test_navigation_accepts_only_identifiers_and_never_creates_authority():
    assert _js("console.log(JSON.stringify(nav.navigation('#task=../bad&run=run-a&screen=runs&token=secret')));") == {
        "taskId": None, "runId": "run-a", "workflowId": None, "screen": "runs"}
    assert _js("console.log(JSON.stringify(nav.navigationHash(EMPTY)));") == "#screen=overview"


def test_new_creation_draft_survives_an_older_accepted_request():
    body = """
    let state = reduce(EMPTY, {type:'task-edit', patch:{taskId:'old', title:'Old'}});
    const generation = state.tasks.draft.generation;
    state = reduce(state, {type:'task-edit', patch:{taskId:'new', title:'New'}});
    state = reduce(state, {type:'task-spent', generation});
    console.log(JSON.stringify(state.tasks.draft));
    """
    assert _js(body) == {"taskId": "new", "title": "New", "generation": 2, "sent": False}


def test_generated_identity_belongs_to_the_draft_until_it_is_spent():
    body = """
    let state = EMPTY;
    const flow = nav.taskFlow({state:() => state,
      dispatch:event => {state = reduce(state,event);}});
    flow.editTask({title:'First'});
    const first = state.tasks.draft.taskId;
    flow.editTask({title:'Edited'});
    state = reduce(state,{type:'tasks-phase',phase:'failed'});
    const kept = state.tasks.draft.taskId;
    state = reduce(state,{type:'task-spent',generation:state.tasks.draft.generation});
    flow.editTask({title:'Next task'});
    console.log(JSON.stringify([tasks.isTaskId(first), first === kept,
      first !== state.tasks.draft.taskId]));
    """
    assert _js(body) == [True, True, True]
