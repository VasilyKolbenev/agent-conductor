"""The reads that establish whether a task was closed, in a real page.

A task is closed when its newest run was accepted at its final gate (spec 5.4), and no list the
desk reads says so: the run itself does. `desk-closing.js` reads a run only when its row says it
could have been accepted -- nothing open, no step asking a person, its last outcome a success --
and only the newest run of a task, through the boot module's own read door. What this module
holds, in the real module and in the real desk:

- only such a run is read, once, and a run that fails the row's test is never read;
- a read that fails, is refused, names another task or another run establishes nothing and
  disturbs no other task;
- a desk that has gone foreign, or whose lists were not read, asks for nothing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from browser_tests.desk_progress_bench import desk_in, progress_url  # noqa: F401

FIXTURE = json.loads((Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "desk"
                      / "feed_reads.json").read_text(encoding="utf-8"))
SEEDED = FIXTURE["seeded"]
#: The module in the page, handed the real lists and reads of the seeded project and a read
#: door that answers from them (or fails for the runs it is told to).
READ_CLOSING = """async ({tasks, runs, reads, fail, stopped, phase}) => {
  const {readClosing} = await import("/panel/desk-closing.js");
  const asked = [];
  const read = async (runId) => {
    asked.push(runId);
    if (fail.includes(runId)) throw new Error("store_error");
    return structuredClone(reads[runId]);
  };
  const found = await readClosing({read, tasks: {phase, list: tasks}, runs: {phase, list: runs},
    stopped: () => stopped});
  return {asked, found: [...found].map(([task, digest]) => [task, digest.run_id, digest.closed])};
}"""


def _closing(page, *, reads=None, fail=(), stopped=False, phase="ready", tasks=None):
    return page.evaluate(READ_CLOSING, {
        "tasks": SEEDED["tasks"]["tasks"] if tasks is None else tasks,
        "runs": SEEDED["runs"]["runs"], "reads": SEEDED["reads"] if reads is None else reads,
        "fail": list(fail), "stopped": stopped, "phase": phase})


def test_only_the_newest_run_that_could_have_been_accepted_is_read_and_it_is_read_once(desk_in):
    window = desk_in("en")
    found = _closing(window.page)
    assert found == {"asked": ["run-closed"], "found": [["task-closed", "run-closed", True]]}
    assert window.problems == []


def test_a_read_that_fails_establishes_nothing_and_throws_nothing(desk_in):
    window = desk_in("en")
    assert _closing(window.page, fail=["run-closed"]) == {"asked": ["run-closed"], "found": []}
    assert window.problems == []


def test_a_read_that_names_another_task_establishes_nothing(desk_in):
    reads = json.loads(json.dumps(SEEDED["reads"]))
    reads["run-closed"]["config"]["task"] = {"id": "task-idle", "work_scope": "task-idle"}
    reads["run-closed"]["task"] = {"id": "task-idle", "work_scope": "task-idle",
                                   "title": "Update the API docs", "unreadable": False}
    window = desk_in("en")
    assert _closing(window.page, reads=reads) == {"asked": ["run-closed"], "found": []}


def test_a_read_the_scene_would_refuse_establishes_nothing(desk_in):
    reads = json.loads(json.dumps(SEEDED["reads"]))
    reads["run-closed"]["not_a_key_of_a_run_read"] = 1
    window = desk_in("en")
    assert _closing(window.page, reads=reads) == {"asked": ["run-closed"], "found": []}


def test_a_read_that_answers_with_another_run_of_the_task_establishes_nothing(desk_in):
    """The body of a different run that says it belongs to the task: the run asked about is
    what a digest must be of, not merely the task."""
    reads = json.loads(json.dumps(SEEDED["reads"]))
    other = reads["run-waiting"]
    other["config"]["task"] = {"id": "task-closed", "work_scope": "task-closed"}
    other["task"] = {"id": "task-closed", "work_scope": "task-closed",
                     "title": "Ship the landing page", "unreadable": False}
    reads["run-closed"] = other
    window = desk_in("en")
    assert _closing(window.page, reads=reads)["found"] == []
    assert window.problems == []


def test_a_desk_that_went_foreign_or_whose_lists_were_not_read_asks_for_nothing(desk_in):
    window = desk_in("en")
    assert _closing(window.page, stopped=True) == {"asked": [], "found": []}
    assert _closing(window.page, phase="failed") == {"asked": [], "found": []}
    assert _closing(window.page, phase="loading") == {"asked": [], "found": []}


def test_a_task_the_list_cannot_read_is_never_asked_about(desk_in):
    lost = {"task_id": "task-closed", "title": None, "unreadable": True, "created_at": None,
            "schema_version": None, "work_scope": None}
    others = [task for task in SEEDED["tasks"]["tasks"] if task["task_id"] != "task-closed"]
    window = desk_in("en")
    assert _closing(window.page, tasks=[lost, *others]) == {"asked": [], "found": []}


@pytest.mark.parametrize("task", [None, "task-closed"])
def test_the_desk_reads_the_run_of_a_finished_task_and_no_other_run_besides_the_one_it_draws(
        desk_in, task):
    """Chosen or not, the closing read is one GET of the finished run; the scene adds its own."""
    window = desk_in("en", task=task)
    reads = [path for method, path in window.asked
             if method == "GET" and path.startswith("/command/runs/")
             and path.count("/") == 3]
    assert sorted(reads) == sorted(["/command/runs/run-closed"] * (1 if task is None else 2))
    assert {method for method, _path in window.asked} == {"GET"}
    assert window.problems == []
