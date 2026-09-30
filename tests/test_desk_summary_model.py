"""The counters, the tasks and the people of a run, from the real module under Node.

`desk-summary-model.js` is values in, values out. It sorts every task of the project into one of
five places by the word the rail gives it (working, waiting for you, closed, left, unclear), says
of a run whether it was accepted at its final gate, digests a run into who did, checked and
accepted, lists the participants of a run with what the records say they did, and names what is
going on now. The reads are the frozen ones of `tests/fixtures/desk/feed_reads.json`, which the
production server answered for the seeded project (see `tests/test_desk_feed_model.py`).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.desk_node import PANEL, run_js
from tests.test_panel_cascade import strip_comments

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "desk" / "feed_reads.json")
                     .read_text(encoding="utf-8"))
SEEDED = FIXTURE["seeded"]
READS = SEEDED["reads"]
MODULES = {"summary": "desk-summary-model.js", "status": "desk-status.js"}
#: The newest run of each seeded task.
NEWEST = {"task-closed": "run-closed", "task-working": "run-working",
          "task-waiting": "run-waiting"}
#: The seeded project as the boot module holds it, and the digest of every run read.
PRELUDE = """
const seeded = d.seeded;
const automation = new Map(Object.entries(d.newest).map(([task, run]) =>
  [task, seeded.automation[run]]));
const digests = new Map(Object.entries(d.newest).map(([task, run]) =>
  [task, summary.digestOf(seeded.reads[run])]));
const inputs = (closing) => ({tasks: {phase: "ready", list: seeded.tasks.tasks},
  runs: {phase: "ready", list: seeded.runs.runs}, automation, closing});
"""


def js(body: str, **extra: Any) -> Any:
    data = {"seeded": SEEDED, "newest": NEWEST, **extra}
    return run_js(PRELUDE + body, MODULES, data)


def digest(read: dict) -> dict:
    return run_js("console.log(JSON.stringify(summary.digestOf(d)));", MODULES, read)


def edited(name: str, edit) -> dict:
    read = copy.deepcopy(READS[name])
    edit(read)
    return read


def closed_fact(read: dict) -> bool:
    return digest(read)["closed"]


# -- the places, and the word every task has -------------------------------------------------

def test_every_word_a_task_can_have_is_in_exactly_one_place_and_no_other_word_is():
    out = run_js("""
      console.log(JSON.stringify({buckets: Object.keys(summary.BUCKETS).sort(),
        keys: [...status.STATUS_KEYS].sort(),
        places: [...new Set(Object.values(summary.BUCKETS))].sort()}));
    """, MODULES)
    assert out["buckets"] == out["keys"]
    assert out["places"] == ["left", "unclear", "waiting", "working"]


def test_the_places_of_the_words_are_the_ones_the_plan_argues_for():
    out = run_js("console.log(JSON.stringify(summary.BUCKETS));", MODULES)
    by_place: dict[str, list[str]] = {}
    for word, place in out.items():
        by_place.setdefault(place, []).append(word)
    assert {place: sorted(words) for place, words in by_place.items()} == {
        "waiting": ["checkpoint", "expired", "queue_confirmation", "stalled", "waiting_you"],
        "working": ["checkpoint_inactive", "owner_missing", "paused", "revoked", "running"],
        "unclear": ["outcome_unknown", "run_unreadable", "state_unknown", "task_unreadable"],
        "left": sorted(["not_started", "queue_blocked", "queued", "queued_inactive", "ended",
                        "no_outcome", "outcome_succeeded", "outcome_verification_failed",
                        "outcome_failed", "outcome_rejected", "outcome_cancelled"])}


def test_the_seeded_project_is_one_task_in_each_place_and_a_finished_run_is_left_until_closed():
    out = js("""
      const before = summary.summaryOf(inputs(new Map()));
      const after = summary.summaryOf(inputs(digests));
      console.log(JSON.stringify({before: before.counts, after: after.counts,
        rows: after.rows.map((row) => [row.task_id, row.key, row.place, row.run_id])}));
    """)
    assert out["before"] == {"working": 1, "waiting": 1, "closed": 0, "left": 2, "unclear": 0}
    assert out["after"] == {"working": 1, "waiting": 1, "closed": 1, "left": 1, "unclear": 0}
    assert out["rows"] == [
        ["task-closed", "outcome_succeeded", "closed", "run-closed"],
        ["task-idle", "not_started", "left", None],
        ["task-waiting", "waiting_you", "waiting", "run-waiting"],
        ["task-working", "running", "working", "run-working"]]


def test_a_digest_of_another_run_than_the_newest_closes_nothing():
    out = js("""
      const older = {...digests.get("task-closed"), run_id: "run-older"};
      const other = new Map([["task-closed", older]]);
      console.log(JSON.stringify(summary.summaryOf(inputs(other)).counts));
    """)
    assert out["closed"] == 0 and out["left"] == 2


def test_the_places_and_the_rows_add_up_to_the_tasks_and_an_unreadable_task_is_unclear():
    out = js("""
      const tasks = [...seeded.tasks.tasks,
        {task_id: "task-lost", title: null, unreadable: true, created_at: null,
         schema_version: null, work_scope: null}];
      const made = summary.summaryOf({...inputs(digests), tasks: {phase: "ready", list: tasks}});
      console.log(JSON.stringify({counts: made.counts, total: made.total, rows: made.rows.length,
        lost: made.rows.find((row) => row.task_id === "task-lost")}));
    """)
    assert out["total"] == out["rows"] == 5 and sum(out["counts"].values()) == 5
    assert out["counts"]["unclear"] == 1
    assert (out["lost"]["key"], out["lost"]["place"]) == ("task_unreadable", "unclear")


def test_a_run_row_the_list_cannot_read_makes_every_task_unclear_and_not_started():
    out = js("""
      const runs = [...seeded.runs.runs, {run_id: "run-lost", unreadable: true, created_at: null}];
      const made = summary.summaryOf({...inputs(digests), runs: {phase: "ready", list: runs}});
      console.log(JSON.stringify(made.rows.map((row) => [row.task_id, row.key, row.place])));
    """)
    assert {row[2] for row in out} == {"unclear"} and {row[1] for row in out} == {"run_unreadable"}


def test_the_rows_say_the_same_word_as_the_rail_for_the_same_inputs():
    """The rail calls `taskStatus` with the newest run's row and automation: so does this."""
    out = js("""
      const made = summary.summaryOf(inputs(new Map()));
      const newest = (task) => {
        const rows = seeded.runs.runs.filter((one) => one.task_id === task.task_id)
          .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
        return rows[0] ?? null;
      };
      const rail = seeded.tasks.tasks.map((task) => status.taskStatus({task, run: newest(task),
        automation: newest(task) === null ? null : automation.get(task.task_id) ?? null,
        entry: null}).key);
      console.log(JSON.stringify({rail, mine: made.rows.map((row) => row.key)}));
    """)
    assert out["rail"] == out["mine"]


# -- what may be closed, and whether it was ---------------------------------------------------

def test_a_run_accepted_at_its_final_gate_is_closed_and_the_others_of_the_project_are_not():
    assert [digest(READS[name])["closed"] for name in
            ("run-closed", "run-working", "run-waiting")] == [True, False, False]


def _terminal(state: str):
    def edit(read):
        for row in read["records"]:
            if row["record_type"] == "run_terminal":
                row["record"]["state"] = state
    return edit


def _gate(decision: str, lap: bool = True):
    """The result gate's current decision (the plan's runtime) and whether it is this lap's."""
    def edit(read):
        for node in read["graph"]["runtime"]["nodes"]:
            if node["node_id"] == "result-gate":
                node["decision"] = decision
        for gate in read["graph"]["situation"]["gates"]:
            if gate["node_id"] == "result-gate":
                gate["standing_belongs_to_current_lap"] = lap
    return edit


def _no_terminal(read):
    read["records"] = [row for row in read["records"] if row["record_type"] != "run_terminal"]


def _a_road_out(read):
    read["graph"]["definition"]["nodes"].append({
        "node_id": "after", "kind": "task", "title": "After", "resources": []})
    read["graph"]["definition"]["edges"].append({"from_node": "result-gate", "to_node": "after"})


def _no_graph(read):
    read["graph"] = None


@pytest.mark.parametrize("edit", [
    _no_terminal, _terminal("stalled"), _gate("failed"), _gate("waived"),
    _gate("changes_requested"), _gate("idle"), _gate("unknown"), _gate("satisfied", lap=False),
    _a_road_out, _no_graph],
    ids=["no-ending", "ended-stalled", "rejected", "waived", "changes-requested", "unanswered",
         "contradicted", "answer-of-an-earlier-lap", "the-gate-opens-a-road", "no-plan"])
def test_a_run_is_not_closed_unless_it_ended_complete_and_its_final_gate_stands_approved(edit):
    assert closed_fact(edited("run-closed", edit)) is False


def test_a_road_that_opens_only_on_a_change_does_not_stop_a_gate_from_being_the_final_one():
    def routed(read):
        _a_road_out(read)
        read["graph"]["definition"]["edges"][-1]["condition"] = "on_changes_requested"
    assert closed_fact(edited("run-closed", routed)) is True


def test_a_run_may_be_closed_only_when_nothing_is_open_nothing_asks_a_person_and_it_succeeded():
    out = js("""
      const rows = Object.fromEntries(seeded.runs.runs.map((row) => [row.run_id, row]));
      const may = (row) => summary.mayBeClosed(row);
      const closed = rows["run-closed"];
      console.log(JSON.stringify({
        closed: may(closed), working: may(rows["run-working"]), waiting: may(rows["run-waiting"]),
        open: may({...closed, open_actions: 1}), asks: may({...closed, human_state: "required"}),
        unknown: may({...closed, human_state: "unknown"}),
        none: may({...closed, last_outcome: null}),
        failed: may({...closed, last_outcome: "failed"}), lost: may({unreadable: true}),
        nothing: may(null)}));
    """)
    assert out == {"closed": True, "working": False, "waiting": False, "open": False,
                   "asks": False, "unknown": False, "none": False, "failed": False,
                   "lost": False, "nothing": False}


# -- who did, who checked, who accepted, and the people of a run -------------------------------

def test_the_digest_of_the_accepted_run_says_who_did_who_checked_and_who_accepted():
    found = digest(READS["run-closed"])
    assert found["run_id"] == "run-closed" and found["pass"] is None
    assert found["did"] == [{"instance": "claude-dev", "harness": "claude-code"}]
    assert found["verified"] == [{"instance": None, "harness": "claude-code"},
                                 {"instance": "codex-check", "harness": "codex-cli"}]
    assert found["accepted"] == ["release-owner"]


def test_the_digest_of_a_run_no_one_has_accepted_names_no_acceptor_and_says_no_pass():
    found = digest(READS["run-waiting"])
    assert (found["accepted"], found["closed"], found["pass"]) == ([], False, None)
    assert found["did"] == [{"instance": "claude-dev", "harness": "claude-code"}]


def test_the_pass_of_a_bounded_return_is_said_only_when_the_run_states_it():
    def looped(number):
        def edit(read):
            read["graph"]["definition"]["nodes"].append({
                "node_id": "again", "kind": "loop", "title": "Again", "resources": [],
                "loop": {"bound": 3, "back_to": "do"}})
            read["graph"]["runtime"]["nodes"].append({
                "node_id": "again", "phase": "idle", "outcome": None, "attempt_ids": [],
                "evidence_refs": [], "observed_at": None, "pass": number})
        return digest(edited("run-working", edit))["pass"]
    assert looped(2) == {"pass": 2, "bound": 3}
    assert looped(0) is None and looped(None) is None


def test_the_people_of_a_run_are_its_frozen_participants_with_only_what_the_records_say():
    people = run_js("console.log(JSON.stringify(summary.participantsOf(d)));", MODULES,
                    READS["run-closed"])
    doer, checker = people
    assert (doer["instance"], doer["harness"], doer["duty"]) == (
        "claude-dev", "claude-code", "perform")
    assert (doer["actions"], doer["checks"], doer["documents"]) == (2, 0, ["artifact-plan"])
    assert (checker["instance"], checker["harness"], checker["duty"]) == (
        "codex-check", "codex-cli", "verify")
    assert (checker["actions"], checker["checks"], checker["documents"]) == (0, 1, [])
    assert doer["last"] == "2026-08-19T08:51:00Z" and checker["last"] == "2026-08-19T08:48:00Z"


def test_a_participant_who_did_nothing_says_no_time_and_no_count_and_none_is_invented():
    def idle(read):
        read["config"]["instances"].append({"id": "spare", "adapter": "third-cli"})
    people = run_js("console.log(JSON.stringify(summary.participantsOf(d)));", MODULES,
                    edited("run-closed", idle))
    spare = next(one for one in people if one["instance"] == "spare")
    assert (spare["actions"], spare["checks"], spare["documents"], spare["last"],
            spare["duty"]) == (0, 0, [], None, "none")


def test_what_is_going_on_now_is_the_attempt_in_flight_and_the_step_that_asks_a_person():
    def now(name):
        return run_js("console.log(JSON.stringify(summary.nowOf(d)));", MODULES, READS[name])
    assert now("run-working") == {"doing": [{"instance": "claude-dev", "harness": "claude-code",
                                             "step": "Do the work"}], "asking": []}
    assert now("run-waiting") == {"doing": [], "asking": ["Accept the result"]}
    assert now("run-closed") == {"doing": [], "asking": []}


def test_a_value_that_is_not_a_run_read_gives_empty_answers_and_throws_nothing():
    out = run_js("""
      console.log(JSON.stringify([summary.digestOf(null), summary.digestOf({}),
        summary.participantsOf(null), summary.nowOf(undefined), summary.nowOf({}),
        summary.summaryOf({tasks: {list: []}, runs: {phase: "ready", list: []},
          automation: new Map(), closing: new Map()}).counts]));
    """, MODULES)
    assert out == [None, None, [], {"doing": [], "asking": []}, {"doing": [], "asking": []},
                   {"working": 0, "waiting": 0, "closed": 0, "left": 0, "unclear": 0}]


def test_everything_the_model_answers_is_frozen_all_the_way_down():
    out = js("""
      const frozen = (value) => value === null || typeof value !== "object"
        || (Object.isFrozen(value) && Object.values(value).every(frozen));
      const read = seeded.reads["run-closed"];
      console.log(JSON.stringify([frozen(summary.summaryOf(inputs(digests))),
        frozen(summary.digestOf(read)), frozen(summary.participantsOf(read)),
        frozen(summary.nowOf(seeded.reads["run-working"]))]));
    """)
    assert out == [True] * 4


def test_the_model_reads_no_clock_and_no_body_of_an_action():
    code = strip_comments((PANEL / "desk-summary-model.js").read_text(encoding="utf-8"))
    for word in (r"\bDate\.now\b", r"new Date\(\)", r"\bperformance\b", r"\bsetTimeout\b",
                 r"\.arguments\b", r"\.detail\b", r"\bstdout\b", r"\btranscript\b"):
        assert not re.search(word, code), word
