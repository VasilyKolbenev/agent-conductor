"""When the desk may play a transition, and when it must not (spec 5.5, D11).

`desk-motion-model.js` is pure: it reads the view the boot module draws from and answers which of
the four moments that view shows -- «принята», «к вам», «завершена» and the entry of a new task --
or none. These run the real module under Node. The rule they hold is the one the spec states in
one sentence: the detector never plays a transition again after a reconnect or a reload. It is made
of four facts, each with a case of its own:

- a reading is compared only with the reading before it, and only while the stream is `open`;
  every other connection word ends the comparison, so the first reading after a load, a drop, a
  reconnect or a page restored from the cache is a baseline and says nothing;
- a render in which the lists are not both read (a reload of the lists is out) is not a reading:
  it neither says a moment nor loses the baseline;
- a row whose automation could not be read, or a view whose queue could not, is not a row to
  compare: a read that failed must not look like a task that started or finished;
- a desk that ended in the terminal state keeps nothing.

Language and theme change a render and no reading, so they say nothing either.
"""
from __future__ import annotations

import shutil
from typing import Any

import pytest

from tests.desk_node import run_js

MODULES = {"motion": "desk-motion-model.js"}
#: What every case below starts from: the view as the boot module hands it (a JSON view cannot
#: carry a Map, so the automation goes in as an object and is made a Map here).
PRELUDE = """
const asView = (view) => ({...view, automation: new Map(Object.entries(view.automation))});
const walk = (steps) => {
  const detector = motion.createDetector();
  const said = (found) => found.map((one) => `${one.kind}:${one.taskId}`);
  return steps.map((step) => said(detector.observe(asView(step))));
};
"""
CREATED = "2026-09-01T10:00:00Z"
RUN = {"run_id": "run-a", "task_id": "task-a", "created_at": CREATED, "unreadable": False,
       "human_state": "not_required", "open_actions": 0, "last_outcome": None}
#: The run row and the automation answer that earn each status key the spec names.
STATES: dict[str, tuple[dict[str, Any] | None, dict[str, Any] | None]] = {
    "not_started": (None, None),
    "running": ({"open_actions": 1}, {"state": "running", "reason_code": "none"}),
    "waiting_you": ({"human_state": "required"}, {"state": "waiting", "reason_code": "none"}),
    "outcome_succeeded": ({"last_outcome": "succeeded"},
                          {"state": "complete", "reason_code": "none"}),
    "outcome_failed": ({"last_outcome": "failed"}, {"state": "complete", "reason_code": "none"}),
    "paused": ({}, {"state": "paused", "reason_code": "none"}),
}
EMPTY_QUEUE = {"entries": [], "slot": {"state": "free"}}


def row(task_id: str, state: str, *, title: str | None = None) -> dict[str, Any]:
    """One task of a view, standing at `state`: its task row, its newest run and its automation."""
    changes, automation = STATES[state]
    task = {"task_id": task_id, "title": title or task_id, "unreadable": False}
    run = None if changes is None else {**RUN, "run_id": f"run-{task_id}", "task_id": task_id,
                                        **changes}
    return {"task": task, "run": run, "automation": automation}


def view(*rows: dict[str, Any], connection: str = "open", queue: Any = EMPTY_QUEUE,
         foreign: bool = False, chosen: str | None = None, locale: str = "en",
         phase: str = "ready") -> dict[str, Any]:
    """The view of `render()` for these rows, as JSON."""
    return {"connection": connection, "queue": queue, "foreign": foreign, "taskId": chosen,
            "locale": locale,
            "tasks": {"phase": phase, "list": [one["task"] for one in rows]},
            "runs": {"phase": phase, "list": [one["run"] for one in rows if one["run"]]},
            "automation": {one["task"]["task_id"]: one["automation"] for one in rows
                           if one["run"]}}


def walk(*steps: dict[str, Any]) -> list[list[str]]:
    """What a fresh detector says to each of these views, in order: `kind:task` strings."""
    return run_js(PRELUDE + "console.log(JSON.stringify(walk(d)));", MODULES, list(steps))


@pytest.fixture(autouse=True, scope="module")
def node_is_present() -> None:
    """These tests run the real module: a machine without Node FAILS here instead of skipping."""
    if shutil.which("node") is None:
        pytest.fail("Node is required to run the desk's motion model")


def test_the_fixture_rows_earn_the_status_keys_the_cases_name():
    """The cases below say a status by name; this holds the rows that earn it."""
    body = """
      const keys = d.map((one) => motion.readingOf(asView(one))[0].key);
      console.log(JSON.stringify(keys));"""
    states = list(STATES)
    keys = run_js(PRELUDE + body, MODULES, [view(row("task-a", name)) for name in states])
    assert dict(zip(states, keys)) == {
        "not_started": "not_started", "running": "running", "waiting_you": "waiting_you",
        "outcome_succeeded": "outcome_succeeded", "outcome_failed": "outcome_failed",
        "paused": "paused"}


def test_the_first_reading_is_a_baseline_and_says_no_moment():
    assert walk(view(row("task-a", "running"))) == [[]]


@pytest.mark.parametrize("before,after,moment", [
    ("not_started", "running", "accepted"),
    ("running", "waiting_you", "to_you"),
    ("running", "outcome_succeeded", "finished"),
    ("waiting_you", "outcome_succeeded", "finished"),
    ("paused", "running", None),
    ("waiting_you", "running", None),
    ("running", "outcome_failed", None),
    ("outcome_succeeded", "running", None),
    ("running", "paused", None),
    ("outcome_failed", "waiting_you", "to_you"),
], ids=lambda value: str(value))
def test_a_live_change_of_one_task_says_its_moment_and_only_that_one(before, after, moment):
    said = walk(view(row("task-a", before)), view(row("task-a", after)))
    assert said == [[], [] if moment is None else [f"{moment}:task-a"]]


def test_a_second_reading_of_the_same_state_says_nothing():
    first = view(row("task-a", "running"))
    assert walk(first, first, view(row("task-a", "running"), locale="ru")) == [[], [], []]


def test_a_new_task_enters_and_a_new_task_already_running_is_also_accepted():
    quiet = view(row("task-a", "paused"))
    assert walk(quiet, view(row("task-a", "paused"), row("task-b", "not_started"))) == [
        [], ["entered:task-b"]]
    assert walk(quiet, view(row("task-a", "paused"), row("task-b", "running"))) == [
        [], ["entered:task-b", "accepted:task-b"]]


def test_nothing_is_said_after_a_reconnect_until_a_change_is_watched_in_the_new_life():
    """The stream drops, the page reconnects (`connecting`, then `open`) and the state changed
    meanwhile: the reading that closes the reconnect is a baseline. Only the next change counts."""
    start = view(row("task-a", "not_started"))
    away = view(row("task-a", "waiting_you"), connection="closed")
    reading = view(row("task-a", "waiting_you"), connection="connecting")
    back = view(row("task-a", "waiting_you"))
    after = view(row("task-a", "outcome_succeeded"))
    assert walk(start, away, reading, back, after) == [[], [], [], [], ["finished:task-a"]]


def test_the_refresh_of_a_reconnect_says_nothing_even_if_it_lands_while_the_word_is_open():
    """A change that lands after the drop but before the first `open` render is never compared with
    the reading from before the drop: the drop ended that reading."""
    start = view(row("task-a", "running"))
    dropped = view(row("task-a", "running"), connection="closed")
    landed = view(row("task-a", "waiting_you"))
    assert walk(start, dropped, landed) == [[], [], []]


def test_a_page_loaded_on_a_changed_state_is_a_new_detector_and_says_nothing():
    """A reload is a new page and a new detector: whatever the project holds is the baseline."""
    changed = view(row("task-a", "waiting_you"))
    assert walk(changed) == [[]]
    assert walk(changed, changed) == [[], []]


@pytest.mark.parametrize("word", ["connecting", "closed", "unknown-word"])
def test_only_an_open_stream_is_a_live_reading(word):
    start = view(row("task-a", "not_started"))
    assert walk(start, view(row("task-a", "running"), connection=word)) == [[], []]


def test_a_render_while_the_lists_are_read_again_keeps_the_baseline():
    """The wizard's exit and the run panel read the lists again: while they are out the view has no
    lists, and the change they bring is watched against the reading from before."""
    start = view(row("task-a", "not_started"))
    reading = view(row("task-a", "not_started"), phase="loading")
    landed = view(row("task-a", "running"))
    assert walk(start, reading, landed) == [[], [], ["accepted:task-a"]]


def test_a_read_that_failed_is_not_a_task_that_started_or_finished_and_loses_no_change():
    """The automation of a task whose read failed is `null`: the status it would earn is a guess.
    That reading says nothing and is not the reading the next one is compared with: the change
    that landed meanwhile is said when a reading that can be vouched for shows it."""
    before = view(row("task-a", "waiting_you"))
    unread = view(row("task-a", "running"))
    unread["automation"]["task-a"] = None
    after = view(row("task-a", "outcome_succeeded"))
    assert walk(before, unread) == [[], []]
    assert walk(before, unread, after) == [[], [], ["finished:task-a"]]


def test_a_queue_that_could_not_be_read_makes_no_row_comparable_for_that_reading():
    start = view(row("task-a", "not_started"))
    no_queue = view(row("task-a", "running"), queue=None)
    assert walk(start, no_queue) == [[], []]
    assert walk(start, no_queue, view(row("task-a", "waiting_you"))) == [
        [], [], ["to_you:task-a"]]


def test_a_desk_that_ended_in_the_terminal_state_keeps_nothing():
    start = view(row("task-a", "not_started"))
    ended = view(row("task-a", "not_started"), foreign=True)
    assert walk(start, ended, view(row("task-a", "running"))) == [[], [], []]


def test_a_task_that_goes_away_says_nothing_and_a_task_that_comes_back_enters_again():
    both = view(row("task-a", "paused"), row("task-b", "paused"))
    one = view(row("task-a", "paused"))
    assert walk(both, one, both) == [[], [], ["entered:task-b"]]


def test_several_changes_at_once_are_said_in_the_order_of_the_list():
    before = view(row("task-a", "running"), row("task-b", "running"), row("task-c", "not_started"))
    after = view(row("task-a", "waiting_you"), row("task-b", "outcome_succeeded"),
                 row("task-c", "running"))
    assert walk(before, after)[1] == ["to_you:task-a", "finished:task-b", "accepted:task-c"]


MOMENTS = [
    {"kind": "accepted", "taskId": "task-a"}, {"kind": "entered", "taskId": "task-b"},
    {"kind": "finished", "taskId": "task-c"}, {"kind": "to_you", "taskId": "task-d"},
    {"kind": "entered", "taskId": "task-e"}, {"kind": "entered", "taskId": "task-f"},
    {"kind": "entered", "taskId": "task-g"}]


def plan(moments: list[dict], chosen: str | None) -> dict[str, Any]:
    body = "console.log(JSON.stringify(motion.planOf(d.moments, d.chosen)));"
    return run_js(body, MODULES, {"moments": moments, "chosen": chosen})


def test_one_plaque_says_the_most_urgent_moment_and_the_scene_plays_the_chosen_tasks_own():
    found = plan(MOMENTS, "task-c")
    assert found["plaque"] == {"kind": "to_you", "taskId": "task-d"}
    assert found["scene"] == {"kind": "finished", "taskId": "task-c"}


def test_the_scene_plays_nothing_for_a_task_that_is_not_the_one_it_draws():
    assert plan(MOMENTS, "task-b")["scene"] is None
    assert plan(MOMENTS, None)["scene"] is None
    assert plan([], "task-a") == {"plaque": None, "scene": None, "entered": []}


def test_at_most_three_new_tasks_enter_at_once_in_the_order_of_the_list():
    assert plan(MOMENTS, None)["entered"] == ["task-b", "task-e", "task-f"]
