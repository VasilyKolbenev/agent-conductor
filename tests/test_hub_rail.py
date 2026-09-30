"""The hub's column of projects, as values: a project's line, its one main action, its tasks
and the list of what waits for you (spec 4.1.10, 4.1.9, 4.3.3, 4.5.4).

`hub-rail.js` holds the pure part of the column: every question the drawing needs answered, and no
markup. A project's line is the hub's own `state` and `working` through the table of 4.1.10 and
never a word of the page's; the task words are `desk-status.js` through `desk-status-copy.js`, so a
task is told as the desk's rail tells it; the list «Ждут вас» is `attentionItems` of the shared
module, with the ids of each item taken from the row the hub gave and never from a word. The tests
run the packaged modules under Node on the contract fixture `tests/fixtures/hub/hub_projects.json`
and on rows built to name each value of the two closed lists. The drawing is proved in the browser
(`browser_tests/test_hub_page.py`).
"""
from __future__ import annotations

import copy
from typing import Any

from tests.desk_wizard_node import fixture, run_js

MODULES = {"rail": "hub-rail.js", "copy": "hub-copy.js", "time": "desk-time.js"}
PAGE = fixture("hub", "hub_projects.json")["response"]
ROW = PAGE["projects"][2]  # a stopped project with no tasks: the plainest row the hub gives
PRELUDE = """
const show = (value) => console.log(JSON.stringify(value));
const page = d.page;
const ctx = (over = {}) => ({locale: "en", projects: page.projects,
  activeId: page.active_project_id, queue: page.project_queue, ...over});
const row = (over) => ({...structuredClone(d.row), ...over});
const when = (iso) => time.instantText("en", iso).short;
const line = (project, over = {}) => rail.projectLine(project, ctx(over));
const ids = (list) => list.map((action) => action.id);
"""


def js(body: str, **extra: Any) -> Any:
    return run_js(PRELUDE + body, {"page": PAGE, "row": ROW, **extra}, modules=MODULES)


def test_each_project_of_the_contract_fixture_says_its_working_state_and_offers_its_actions():
    out = js("""
      const [active, queued, stopped] = page.projects.map((one) => line(one));
      show({active, queued, stopped, stoppedAt: when(page.projects[2].stopped_at)});
    """)
    active, queued, stopped = out["active"], out["queued"], out["stopped"]
    assert (active["text"], active["tone"]) == ("In progress", "ion")
    assert [(a["id"], a["target"], a["confirm"]) for a in active["actions"]] == [
        ("stop", "projectStop", "stop")]
    assert queued["text"] == "Queued · #1" and queued["tone"] is None
    assert [a["id"] for a in queued["actions"]] == ["clear_flag"], (
        "the only project in the queue can be neither raised nor lowered")
    assert stopped["text"] == f"Stopped · since {out['stoppedAt']}"
    assert [(a["id"], a["target"], a["label"]) for a in stopped["actions"]] == [
        ("activate", "projectActivate", "Make active")]
    assert stopped["actions"][0]["confirm"] == "switch", "an active project is working"


def test_a_stopped_project_with_a_run_to_resume_offers_continue_else_make_active():
    out = js("""
      const resume = line(row({resume_run_id: "run-9"}));
      const plain = line(row({resume_run_id: null, stopped_at: null}));
      const idle = line(row({resume_run_id: null}), {activeId: null});
      show({resume: resume.actions.map((a) => a.label), plain: plain.text,
        idle: idle.actions.map((a) => [a.id, a.confirm])});
    """)
    assert out["resume"] == ["Continue"] and out["plain"] == "Stopped"
    assert out["idle"] == [["activate", None]], "nothing is working, so nothing asks first"


#: One row per value of `state` with no word of its own beside the working state, and one per value
#: that has: the line after the working word, the actions by id in order, and the tone.
STATE_TABLE = [
    ("running", "active", "In progress", ["stop"], "ion"),
    ("starting", "active", "In progress · Starting…", [], None),
    ("starting", "view", "View · Opening…", [], None),
    ("stopping", "stopped", "Stopped · Stopping…", [], None),
    ("stop_overdue", "stopped", "Stopped · The stop is taking long: the step has not finished", [],
     "amber"),
    ("stop_uncertain", "stopped", "Stopped · Stop not confirmed · the OS needs a restart",
     ["recover"], "amber"),
    ("failed", "active", "In progress · Did not start: startup error", ["restart"], "amber"),
    ("failed", "view", "View · Did not start: startup error", ["restart"], "amber"),
    ("busy_elsewhere", "stopped", "Stopped · Open in another conduct up", ["recheck"], "amber"),
    ("recovery_required", "stopped", "Stopped · The OS needs a restart", ["recover"], "amber"),
    ("identity_mismatch", "stopped", "Stopped · A different project is in the folder now",
     ["forget"], "amber"),
    ("missing", "stopped", "Stopped · The folder was not found or was replaced", ["forget"],
     "amber"),
    ("running", "view", "View", ["activate", "close_view"], None),
]


def test_every_value_of_state_and_working_has_its_line_and_its_main_action_by_the_rule():
    out = js("""
      show(d.table.map(([state, working]) => {
        const one = row({state, working, stopped_at: null, state_code: "hub_flags_incomplete",
          resume_run_id: null, queue_position: null, drain_deadline: null, mode:
          working === "view" ? "view" : null});
        const said = line(one);
        return [said.text, ids(said.actions), said.tone];
      }));
    """, table=[[s, w] for s, w, *_ in STATE_TABLE])
    for (state, working, text, actions, tone), (said, got, tint) in zip(STATE_TABLE, out):
        assert (said, got, tint) == (text, actions, tone), (state, working)


def test_a_failed_start_says_the_clause_of_its_code_and_repeats_the_same_mode():
    out = js("""
      const active = line(row({state: "failed", working: "active", state_code: "bind_failed"}));
      const view = line(row({state: "failed", working: "view", state_code: "bind_failed"}));
      const queued = line(row({state: "failed", working: "queued", state_code: "bind_failed"}));
      const ru = line(row({state: "failed", working: "active", state_code: "start_timeout"}),
        {locale: "ru"});
      show({active: [active.text, active.actions[0].target], view: view.actions[0].target,
        queued: queued.actions[0].target, ru: ru.text});
    """)
    assert out["active"] == ["In progress · Did not start: the port is taken", "projectActivate"]
    assert out["view"] == "projectView" and out["queued"] == "projectActivate"
    assert out["ru"] == "В работе · Не запустился: не ответил вовремя"


def test_a_project_takes_the_seat_of_one_that_is_still_closing_and_names_it():
    out = js("""
      const closing = row({project_id: "a".repeat(32), name: "old-one", state: "stopping",
        working: "stopped", stopped_at: null, drain_deadline: "2026-09-29T10:05:00Z"});
      const waiting = row({project_id: "b".repeat(32), name: "new-one", state: "stopped",
        working: "active"});
      const here = {projects: [closing, waiting], activeId: waiting.project_id, queue: []};
      const stuck = row({project_id: "c".repeat(32), name: "stuck-one", state: "stop_uncertain",
        working: "stopped"});
      const refused = row({project_id: "d".repeat(32), name: "next-one", state: "stopped",
        working: "stopped", state_code: "active_not_closed"});
      show({waits: line(waiting, here).text, closing: line(closing, here).text,
        notActive: line(refused, {projects: [stuck, refused], activeId: null, queue: []}).text,
        stuckActions: ids(line(stuck, {projects: [stuck, refused], activeId: null,
          queue: []}).actions)});
    """)
    assert out["waits"] == "Will become active after old-one stops"
    assert out["closing"].startswith("Stopped · Stopping, until ")
    assert out["notActive"] == ("Did not become active: stuck-one is not closed · the OS needs "
                                "a restart")
    assert out["stuckActions"] == ["recover"], "the way out stands on the project that blocks"


def test_a_project_in_view_says_its_place_in_the_queue_and_a_queued_one_its_own():
    out = js("""
      const view = line(row({working: "view", state: "running", queue_position: 2}));
      const queued = line(row({working: "queued", queue_position: 3, project_id: "c"}),
        {queue: ["a", "b", "c"]});
      show({view: view.text, queued: [queued.text, ids(queued.actions)]});
    """)
    assert out["view"] == "View · queued #2"
    assert out["queued"] == ["Queued · #3", ["raise", "clear_flag"]], (
        "the last of the queue can only be raised")


def test_a_switch_asks_first_when_an_active_project_is_working_and_a_stop_names_the_next_one():
    out = js("""
      const others = [page.projects[0], page.projects[1], page.projects[2]];
      const stop = line(page.projects[0]).actions[0];
      const again = line(row({state: "failed", working: "active"}), {activeId: "x"}).actions[0];
      const words = (kind, project) => rail.confirmWords(kind, project, ctx());
      show({stop: stop.confirm, again: again.confirm,
        switchWords: words("switch", page.projects[2]),
        stopWords: words("stop", page.projects[0]),
        stopNoQueue: rail.confirmWords("stop", page.projects[0], ctx({queue: []}))});
    """)
    assert out["stop"] == "stop" and out["again"] is None
    assert out["switchWords"] == ["web-app is in progress now: it will stop at a checkpoint — "
                                  "its current step will finish on its own."]
    assert out["stopWords"] == [
        "The current step will finish on its own, no new step will begin. The stop cannot be "
        "cancelled.", "landing will become active next."]
    assert len(out["stopNoQueue"]) == 1


def test_moving_a_project_in_the_queue_is_a_new_order_and_an_impossible_move_is_none():
    out = js("""
      const order = ["a", "b", "c"];
      show({raise: rail.moveInQueue(order, "c", -1), lower: rail.moveInQueue(order, "a", 1),
        top: rail.moveInQueue(order, "a", -1), bottom: rail.moveInQueue(order, "c", 1),
        absent: rail.moveInQueue(order, "z", 1), same: order});
    """)
    assert out == {"raise": ["a", "c", "b"], "lower": ["b", "a", "c"], "top": None,
                   "bottom": None, "absent": None, "same": ["a", "b", "c"]}


def test_the_raise_and_lower_actions_carry_the_whole_new_order_of_the_queue():
    out = js("""
      const one = row({project_id: "b".repeat(32), working: "queued", queue_position: 2});
      const order = ["a".repeat(32), "b".repeat(32), "c".repeat(32)];
      const said = line(one, {queue: order});
      show(said.actions.map((action) => [action.id, action.target, action.order]));
    """)
    a, b, c = "a" * 32, "b" * 32, "c" * 32
    assert out == [["raise", "queueOrder", [b, a, c]], ["lower", "queueOrder", [a, c, b]],
                   ["clear_flag", None, None]]


def test_the_menu_of_a_project_offers_view_close_and_forget_only_where_the_spec_does():
    out = js("""
      const items = (over) => rail.menuItems(row(over)).map((item) => item.id);
      show({stopped: items({state: "stopped", working: "stopped"}),
        running: items({state: "running", working: "active"}),
        view: items({state: "running", working: "view"}),
        failed: items({state: "failed", working: "queued"}),
        stopping: items({state: "stopping", working: "stopped"}),
        uncertain: items({state: "stop_uncertain", working: "stopped"}),
        missing: items({state: "missing", working: "stopped"}),
        activeFailed: items({state: "failed", working: "active"})});
    """)
    assert out == {"stopped": ["view_open", "forget"], "running": [],
                   "view": ["close_view"], "failed": ["view_open", "forget"], "stopping": [],
                   "uncertain": ["forget"], "missing": ["forget"], "activeFailed": ["forget"]}


def test_the_tasks_under_a_project_say_the_shared_words_and_the_snapshot_they_came_from():
    out = js("""
      const [live, snap, none] = page.projects.map((one) => rail.taskRows(one, ctx()));
      const ru = rail.taskRows(page.projects[0], ctx({locale: "ru"}));
      show({live, snap, none, ru: ru.map((task) => task.text),
        at: when(page.projects[1].snapshot_at)});
    """)
    assert [(t["task_id"], t["title"], t["text"], t["tone"]) for t in out["live"]] == [
        ("task-001", "Fix the payment form", "Running", "ion"),
        ("task-002", "Add a dark theme", "Waiting for your decision", "amber")]
    assert [t["snapshot"] for t in out["live"]] == [None, None]
    assert [t["run_id"] for t in out["live"]] == ["run-001", "run-002"]
    [task] = out["snap"]
    assert task["text"] == "At a checkpoint · needs to be continued"
    assert task["snapshot"] == f"snapshot from {out['at']}" and out["none"] == []
    assert out["ru"] == ["Идёт", "Ждёт вашего решения"]


def test_two_tasks_with_one_title_carry_their_id_tails_and_a_task_with_no_run_is_not_started():
    out = js("""
      const one = structuredClone(page.projects[0]);
      one.tasks[0].task.title = one.tasks[1].task.title = "Same";
      one.tasks[1].run = null;
      show(rail.taskRows(one, ctx()).map((task) => [task.title, task.text, task.run_id]));
    """)
    assert out == [["Same · task-001", "Running", "run-001"],
                   ["Same · task-002", "Not started", None]]


def test_what_waits_for_you_is_listed_with_the_ids_of_its_row_and_counted_per_project():
    out = js("""
      const named = structuredClone(page.projects);
      named[0].tasks[1].attention.reasons[0].sources = ["review"];
      const list = rail.attentionList(named, {}, ctx());
      const raw = rail.attentionList(page.projects, {}, ctx());
      show({list, raw: raw.map((one) => one.gate_id), count: rail.waitingCount(list),
        byProject: rail.waitingByProject(list)});
    """)
    [item] = out["list"]
    assert (item["project_id"], item["task_id"], item["run_id"], item["gate_id"]) == (
        PAGE["projects"][0]["project_id"], "task-002", "run-002", "gate-review")
    assert out["raw"] == [None], (
        "the fixture names the source by the gate id where its own gate row has the node id, and "
        "the shared module matches node ids: so the gate is not found, and none is invented")
    assert item["text"].startswith("web-app · Add a dark theme · Gate decision · noticed at ")
    assert item["exact"] == "2026-09-29T10:00:00Z"
    assert out["count"] == 1
    assert out["byProject"] == {PAGE["projects"][0]["project_id"]: 1}


def test_a_reason_the_hub_gave_no_time_for_is_dated_by_when_this_page_first_noticed_it():
    out = js("""
      const stalled = structuredClone(page.projects[0]);
      stalled.tasks[0].automation = {state: "stalled", reason_code: "x", expires_at: null};
      stalled.tasks[1].attention = null;
      stalled.tasks[1].run.human_state = "not_required";
      const first = rail.noticedMap({}, [stalled], "2026-09-29T10:00:00Z");
      const later = rail.noticedMap(first, [stalled], "2026-09-29T10:30:00Z");
      const gone = rail.noticedMap(later, [page.projects[2]], "2026-09-29T11:00:00Z");
      const back = rail.noticedMap(gone, [stalled], "2026-09-29T11:30:00Z");
      const list = rail.attentionList([stalled], later, ctx());
      show({first, later, gone, back, exact: list.map((one) => one.exact),
        texts: list.map((one) => one.text.split(" · ").slice(-2))});
    """)
    key = PAGE["projects"][0]["project_id"]
    assert out["first"] == {key: "2026-09-29T10:00:00Z"}
    assert out["later"] == {key: "2026-09-29T10:00:00Z"}, "the first sight stands"
    assert out["gone"] == {} and out["back"] == {key: "2026-09-29T11:30:00Z"}
    assert out["exact"] == ["2026-09-29T10:00:00Z"]
    assert out["texts"][0][0] == "Run stalled" and out["texts"][0][1].startswith("noticed at ")


def test_a_project_the_hub_has_no_live_data_for_is_muted_and_says_so():
    out = js("""
      const snap = page.projects[1], none = page.projects[2];
      show({snap: rail.mutedNote(snap, ctx()), none: rail.mutedNote(none, ctx()),
        live: rail.mutedNote(page.projects[0], ctx()),
        ru: rail.mutedNote(snap, ctx({locale: "ru"})), at: when(snap.snapshot_at)});
    """)
    assert out["snap"] == f"snapshot from {out['at']}"
    assert out["none"] == "No data yet" and out["live"] is None
    assert out["ru"].startswith("снимок от ")


def test_a_row_the_page_does_not_know_is_read_without_throwing_and_says_nothing_false():
    out = js("""
      const odd = {project_id: 7, name: null, state: "from-the-future", working: "elsewhere",
        tasks: "no"};
      show({line: line(odd), tasks: rail.taskRows(odd, ctx()),
        list: rail.attentionList([odd, null, 4], {}, ctx()), menu: rail.menuItems(odd)});
    """)
    assert out["tasks"] == [] and out["list"] == [] and out["menu"] == []
    assert out["line"]["actions"] == [] and out["line"]["text"] == ""
