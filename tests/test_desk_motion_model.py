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

What a settled render plays (`planOf`) is decided over that render's own view, not over the view
a moment was seen on: a moment carries the run it was watched on (the task's newest), and it plays
only while it still stands there -- its task in the list, on that run, at the key it brought the
task to. The scene's mark is for the run the scene draws; the plaque is not.
"""
from __future__ import annotations

import copy
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


#: What a plan is made of. The plan is decided over the view of the render that plays it, so a case
#: names the view (`at`: the run the scene draws is on it) and the moments the detector said.
PLAN = PRELUDE + """
const detector = motion.createDetector();
let pending = [];
for (const step of d.steps) pending = [...pending, ...detector.observe(asView(step))];
console.log(JSON.stringify({pending, plan: motion.planOf(pending, asView(d.at))}));
"""
SAID = PRELUDE + """
const detector = motion.createDetector();
console.log(JSON.stringify(d.map((step) => detector.observe(asView(step))
  .map((one) => `${one.kind}:${one.taskId}:${one.runId}`))));
"""
EMPTY_PLAN = {"plaque": None, "scene": None, "entered": []}


def on_scene(one: dict[str, Any], run_id: str | None) -> dict[str, Any]:
    """The view with the scene drawing run `run_id`, or no run at all (`None`)."""
    drawn = {"phase": "empty", "detail": None} if run_id is None else {
        "phase": "ready", "detail": {"run": {"run_id": run_id}}}
    return {**copy.deepcopy(one), "run": drawn}


def planned(steps: list[dict[str, Any]], at: dict[str, Any]) -> dict[str, Any]:
    """The moments a fresh detector says to `steps`, and the plan made of them over the view `at`.
    """
    return run_js(PLAN, MODULES, {"steps": steps, "at": at})


def test_a_moment_carries_the_newest_run_it_was_watched_on():
    """A task that has an older run as well says its NEWEST one (the rail's own rule), whichever
    run the list names first; a task with no run says none."""
    older = {**RUN, "run_id": "run-0", "task_id": "task-a", "created_at": "2026-08-01T10:00:00Z",
             "last_outcome": "succeeded"}
    waiting = view(row("task-a", "waiting_you"))
    waiting["runs"]["list"].insert(0, older)
    said = run_js(SAID, MODULES, [view(row("task-a", "running")), waiting,
                                  view(row("task-a", "waiting_you"), row("task-b", "not_started"))])
    assert said == [[], ["to_you:task-a:run-task-a"], ["entered:task-b:null"]]


def test_the_scene_plays_a_moment_only_on_the_run_it_draws():
    """The plaque names the task and stays; the marks of the scene are for the run on the scene."""
    steps = [view(row("task-a", "running"), chosen="task-a"),
             view(row("task-a", "waiting_you"), chosen="task-a")]
    same = planned(steps, on_scene(steps[-1], "run-task-a"))["plan"]
    other = planned(steps, on_scene(steps[-1], "run-older"))["plan"]
    none = planned(steps, on_scene(steps[-1], None))["plan"]
    assert same["scene"]["kind"] == "to_you"
    assert other["scene"] is None and other["plaque"]["kind"] == "to_you"
    assert none["scene"] is None and none["plaque"]["kind"] == "to_you"


def test_of_two_moments_of_one_task_only_the_one_that_still_stands_is_played():
    """Asked for a decision and then finished before either was shown: the moments wait together,
    and the one the task has left is not played, so the plaque and the scene say `finished`."""
    steps = [view(row("task-a", "running"), chosen="task-a"),
             view(row("task-a", "waiting_you"), chosen="task-a"),
             view(row("task-a", "outcome_succeeded"), chosen="task-a")]
    found = planned(steps, on_scene(steps[-1], "run-task-a"))
    assert [one["kind"] for one in found["pending"]] == ["to_you", "finished"]
    assert found["plan"]["plaque"]["kind"] == "finished"
    assert found["plan"]["scene"]["kind"] == "finished"


def test_a_moment_answered_before_it_is_shown_plays_nothing():
    steps = [view(row("task-a", "running"), chosen="task-a"),
             view(row("task-a", "waiting_you"), chosen="task-a"),
             view(row("task-a", "running"), chosen="task-a")]
    found = planned(steps, on_scene(steps[-1], "run-task-a"))
    assert [one["kind"] for one in found["pending"]] == ["to_you"]
    assert found["plan"] == EMPTY_PLAN


def test_a_task_gone_from_the_list_neither_enters_nor_plays():
    steps = [view(row("task-a", "paused")),
             view(row("task-a", "paused"), row("task-b", "running"))]
    gone = view(row("task-a", "paused"))
    found = planned(steps, on_scene(gone, None))
    assert [one["kind"] for one in found["pending"]] == ["entered", "accepted"]
    assert found["plan"] == EMPTY_PLAN


def test_a_row_that_cannot_be_vouched_for_when_the_plan_is_made_plays_no_moment():
    """The moment was seen on a good reading; by the plan the automation of the task cannot be
    read, so the key its row would say is a guess, and a guess is not a moment that stands."""
    steps = [view(row("task-a", "running"), chosen="task-a"),
             view(row("task-a", "waiting_you"), chosen="task-a")]
    unread = on_scene(steps[-1], "run-task-a")
    unread["automation"]["task-a"] = None
    found = planned(steps, unread)
    assert [one["kind"] for one in found["pending"]] == ["to_you"]
    assert found["plan"] == EMPTY_PLAN


#: Seven tasks in the keys the moments below bring them to: `a` running, `c` finished, `d`
#: waiting for the person and the rest paused. Every moment was watched on its task's own run.
PLAN_ROWS = (row("task-a", "running"), row("task-b", "paused"), row("task-c", "outcome_succeeded"),
             row("task-d", "waiting_you"), row("task-e", "paused"), row("task-f", "paused"),
             row("task-g", "paused"))
MOMENTS = [
    {"kind": "accepted", "taskId": "task-a", "runId": "run-task-a"},
    {"kind": "entered", "taskId": "task-b", "runId": "run-task-b"},
    {"kind": "finished", "taskId": "task-c", "runId": "run-task-c"},
    {"kind": "to_you", "taskId": "task-d", "runId": "run-task-d"},
    {"kind": "entered", "taskId": "task-e", "runId": "run-task-e"},
    {"kind": "entered", "taskId": "task-f", "runId": "run-task-f"},
    {"kind": "entered", "taskId": "task-g", "runId": "run-task-g"}]


def plan(moments: list[dict], chosen: str | None, drawn: str | None = None) -> dict[str, Any]:
    """What `planOf` makes of these moments over the view of seven tasks standing as `PLAN_ROWS`
    say, `chosen` the task the scene was asked for and `drawn` the run it draws."""
    at = on_scene(view(*PLAN_ROWS, chosen=chosen), drawn)
    body = PRELUDE + "console.log(JSON.stringify(motion.planOf(d.moments, asView(d.at))));"
    return run_js(body, MODULES, {"moments": moments, "at": at})


def test_one_plaque_says_the_most_urgent_moment_and_the_scene_plays_the_chosen_tasks_own():
    found = plan(MOMENTS, "task-c", "run-task-c")
    assert found["plaque"] == {"kind": "to_you", "taskId": "task-d", "runId": "run-task-d"}
    assert found["scene"] == {"kind": "finished", "taskId": "task-c", "runId": "run-task-c"}


@pytest.mark.parametrize("kind,task_id", [
    ("accepted", "task-a"), ("finished", "task-c"), ("to_you", "task-d")])
def test_a_moment_does_not_stand_on_another_run_of_its_task_at_the_same_key(kind, task_id):
    """The key a moment brought its task to is not enough: the task stands at that key NOW, but on
    another run than the one the moment was watched on (it started a new run since, which got there
    too). The moment of the old run is not the moment of this one: no plaque, no mark. The same
    moment on the run the task stands on does play (the control, in the same view)."""
    own = f"run-{task_id}"
    stands = plan([{"kind": kind, "taskId": task_id, "runId": own}], task_id, own)
    other = plan([{"kind": kind, "taskId": task_id, "runId": f"{own}-before"}], task_id, own)
    assert stands["plaque"]["kind"] == kind and stands["scene"]["kind"] == kind
    assert other == EMPTY_PLAN
    gone = plan([{"kind": kind, "taskId": task_id, "runId": None}], task_id, own)
    assert gone == EMPTY_PLAN


def test_the_scene_plays_nothing_for_a_task_that_is_not_the_one_it_draws():
    assert plan(MOMENTS, "task-b", "run-task-b")["scene"] is None
    assert plan(MOMENTS, None, "run-task-c")["scene"] is None
    assert plan([], "task-a", "run-task-a") == EMPTY_PLAN


def test_at_most_three_new_tasks_enter_at_once_in_the_order_of_the_list():
    assert plan(MOMENTS, None)["entered"] == ["task-b", "task-e", "task-f"]
