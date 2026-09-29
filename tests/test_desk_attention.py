"""The items of "waiting for you" and what a row's word may also say (spec 4.1.9, 4.5.6, 5.2.1).

`attentionItems` is the one function that turns a project's raw fields into the list a person is
asked to look at, for the hub's column and the desk's console alike. It is pure, so these run the
real module under Node: a project as the hub's summary spells it goes in, and the items come out.
Each case is built to reach ONE row of the spec's table of reasons, and the run that needs a
person is dated from the shared journal fixture, so the "waiting since" of a step is the same
instant here, in `test_desk_status.py` and in the browser test.
"""
from __future__ import annotations

import pytest

from tests.desk_node import run_js
from tests.test_desk_status import CASES, JOURNAL, MODULES, TASK, a_run, automation, entry

PROJECT = "3f9c0d5a" * 4
OBSERVED = "2026-09-29T10:00:00Z"
RUN_OBSERVED = "2026-09-29T09:59:00Z"
#: The journal and runtime of the fixture's first case: a run with every kind of step in it.
CASE = JOURNAL["cases"][0]
#: The table of spec 4.1.9, written out here by hand: the module's own list is held to it.
REASONS = ("gate_decision", "confirmation", "input_document", "reconcile", "attempt_bound",
           "restart_required", "stalled", "expired", "queue_confirmation", "slot_stuck",
           "recovery_required", "login_recovery_required")
GATE = {"node_id": "review", "gate_id": "gate-1"}


def attention(*reasons: tuple, gates: tuple = (GATE,),
              observed: str | None = RUN_OBSERVED) -> dict:
    """The raw projection a hub row carries for a run that needs a person.

    Each reason is `(reason, sources)` or `(reason, sources, count)`; the count is the number of
    sources unless the server says otherwise, as it does for `reconcile` (a count, no sources).
    """
    return {"reasons": [{"reason": reason, "count": count[0] if count else len(sources),
                         "sources": sources} for reason, sources, *count in reasons],
            "gates": list(gates), "runtime": CASE["runtime"], "journal": CASE["journal"],
            "observed_at": observed, "unreadable": False}


def row(task_id: str = "task-a", run_id: str = "run-1", *, human: str = "required",
        grant: dict | None = None, seen: dict | None = None, task_unreadable: bool = False,
        run_unreadable: bool = False) -> dict:
    """One task row of a project summary: the task, its newest run, its automation, its wait."""
    return {"task": {**TASK, "task_id": task_id, "unreadable": task_unreadable},
            "run": a_run(run_id=run_id, task_id=task_id, human_state=human,
                         unreadable=run_unreadable),
            "automation": grant, "attention": seen}


def project(*tasks: dict, **changes: object) -> dict:
    """The fields of one project as `GET /hub/projects` (or the desk) gives them."""
    return {"project_id": PROJECT, "mode": "active", "state": "running", "data": "live",
            "snapshot_at": None, "login_unclosed": False, "observed_at": OBSERVED,
            "tasks": list(tasks), "task_queue": None, **changes}


def item(reason: str, kind: str, at: str | None, *, task: str | None = "task-a",
         run: str | None = "run-1", gate: str | None = None,
         snapshot: str | None = None) -> dict:
    return {"reason": reason, "key": f"attention_{reason}", "project_id": PROJECT,
            "task_id": task, "run_id": run, "gate_id": gate,
            "since": {"kind": kind, "at": at}, "snapshot_at": snapshot}


def items_of(*inputs: object) -> list:
    """`attentionItems` over each input, in one Node run."""
    return run_js("console.log(JSON.stringify(d.map((input) => st.attentionItems(input))));",
                  MODULES, list(inputs))


def items_for(given: object) -> list:
    return items_of(given)[0]


# -- the closed list ---------------------------------------------------------------------
def test_the_reasons_are_the_table_of_the_spec_in_a_frozen_list_and_the_exports_are_six():
    out = run_js("console.log(JSON.stringify({reasons: st.ATTENTION_REASONS, "
                 "frozen: Object.isFrozen(st.ATTENTION_REASONS), names: Object.keys(st).sort()}));",
                 MODULES)
    assert out["reasons"] == list(REASONS) and out["frozen"] is True
    assert out["names"] == sorted(["taskStatus", "attentionItems", "waitingSince",
                                   "journalIndex", "STATUS_KEYS", "ATTENTION_REASONS"])


# -- a run that needs a person -----------------------------------------------------------
FIVE = attention(("gate_decision", ["review"]), ("confirmation", ["proposal-1"]),
                 ("input_document", ["intake"]), ("reconcile", [], 1),
                 ("attempt_bound", ["do"]))


def test_each_of_the_five_human_reasons_makes_one_item_dated_by_the_journal_or_noticed():
    got = items_for(project(row(seen=FIVE)))
    assert got == [
        item("gate_decision", "waiting", "2026-09-29T09:20:00Z", gate="gate-1"),
        item("confirmation", "waiting", "2026-09-29T09:05:00Z"),
        item("input_document", "waiting", "2026-09-29T09:00:00Z"),
        item("reconcile", "observed", RUN_OBSERVED),
        item("attempt_bound", "waiting", "2026-09-29T09:15:00Z")]


def test_a_step_the_journal_cannot_date_is_noticed_at_the_moment_the_reason_was_first_seen():
    seen = attention(("attempt_bound", ["ghost"]), ("confirmation", ["proposal-9"]))
    assert items_for(project(row(seen=seen))) == [
        item("attempt_bound", "observed", RUN_OBSERVED),
        item("confirmation", "observed", RUN_OBSERVED)]


def test_the_noticed_instant_falls_back_from_the_reason_to_the_project_and_then_to_nothing():
    seen = attention(("reconcile", [], 1), observed=None)
    both, project_only, neither = items_of(
        project(row(seen=attention(("reconcile", [], 1)))),
        project(row(seen=seen)),
        project(row(seen=seen), observed_at=None))
    assert both == [item("reconcile", "observed", RUN_OBSERVED)]
    assert project_only == [item("reconcile", "observed", OBSERVED)]
    assert neither == [item("reconcile", "observed", None)]


def test_two_gates_of_one_run_are_one_item_named_by_the_first_gate_that_needs_a_decision():
    review, check = ({"node_id": "review", "gate_id": "gate-1"},
                     {"node_id": "check", "gate_id": "gate-2"})
    both = ("gate_decision", ["check", "review"])
    forward, backward, absent = items_of(
        project(row(seen=attention(both, gates=(review, check)))),
        project(row(seen=attention(both, gates=(check, review)))),
        project(row(seen=attention(("gate_decision", ["elsewhere"])))))
    assert [(x["reason"], x["gate_id"]) for x in forward] == [("gate_decision", "gate-1")]
    assert [(x["reason"], x["gate_id"]) for x in backward] == [("gate_decision", "gate-2")]
    assert [(x["reason"], x["gate_id"]) for x in absent] == [("gate_decision", None)]


def test_only_a_gate_decision_names_a_gate_even_when_another_reason_names_the_gates_step():
    seen = attention(("input_document", ["review"]), ("attempt_bound", ["review"]),
                     ("confirmation", ["proposal-2"]))
    got = items_for(project(row(seen=seen)))
    assert [(x["reason"], x["gate_id"]) for x in got] == [
        ("input_document", None), ("attempt_bound", None), ("confirmation", None)]


def test_a_reason_with_no_count_the_end_of_a_run_and_an_unknown_reason_make_no_item():
    seen = attention(("run_ended", ["terminal-1"]), ("no_such_reason", ["x"]))
    seen["reasons"].append({"reason": "confirmation", "count": 0, "sources": []})
    assert items_for(project(row(seen=seen))) == []


@pytest.mark.parametrize("human,seen", [
    ("required", None), ("required", {**FIVE, "unreadable": True}),
    ("not_required", FIVE), ("unknown", FIVE)])
def test_only_a_run_that_needs_a_person_and_whose_wait_was_read_names_a_reason(human, seen):
    """A row that needs a person but whose reasons were not read still says so in its own word
    (rule 4 of the table); naming a reason for it would be inventing one."""
    assert items_for(project(row(human=human, seen=seen))) == []


def test_an_unreadable_task_or_run_makes_no_item_even_when_it_carries_a_wait_and_a_grant():
    stalled = automation("stalled", "plan_stalled")
    got = items_of(project(row(seen=FIVE, grant=stalled, task_unreadable=True)),
                   project(row(seen=FIVE, grant=stalled, run_unreadable=True)),
                   project({"task": TASK, "run": None, "automation": None, "attention": None}))
    assert got == [[], [], []]


# -- the automation of a run -------------------------------------------------------------
def _granted(state: str, reason: str, **changes: object) -> list:
    return items_for(project(row(human="not_required", grant=automation(state, reason)),
                             **changes))


@pytest.mark.parametrize("reason", ["plan_stalled", "seed_blocked", "action_failed"])
def test_a_stalled_run_is_an_item_whatever_the_reason_including_a_blocked_seed(reason):
    assert _granted("stalled", reason) == [item("stalled", "observed", OBSERVED)]


def test_an_expired_grant_is_an_item_noticed_at_the_project_instant():
    assert _granted("expired", "expired") == [item("expired", "observed", OBSERVED)]


def test_a_checkpoint_that_asks_for_an_explicit_resume_is_an_item_only_in_an_active_project():
    active = _granted("restart_required", "explicit_resume_required")
    assert active == [item("restart_required", "observed", OBSERVED)]
    for mode in ("view", None):
        assert _granted("restart_required", "explicit_resume_required", mode=mode) == [], mode


@pytest.mark.parametrize("state,reason", [
    ("restart_required", "project_not_active"), ("restart_required", "owner_required"),
    ("paused", "paused"), ("revoked", "revoked"), ("running", "action_in_flight"),
    ("waiting", "plan_waiting"), ("ready", "ready"), ("complete", "plan_ended"),
    ("unconfigured", "authorization_required")])
def test_no_other_state_of_a_grant_is_an_item_and_a_view_checkpoint_never_is(state, reason):
    assert _granted(state, reason) == []
    assert _granted(state, reason, mode="view") == []


# -- the queue and the slot --------------------------------------------------------------
def _queue(*entries: dict, slot: dict | None = None) -> dict:
    return {"schema_version": 1, "revision": 3,
            "slot": slot or {"state": "free", "run_id": None, "reason_code": None},
            "entries": list(entries)}


def _entry(run_id: str, task_id: str, state: str, since: str | None, position: int = 1) -> dict:
    return {"run_id": run_id, "task_id": task_id, "title": "T", "position": position,
            "kind": "start", "enqueued_at": "2026-09-29T08:00:00Z", "enqueued_by": "vasya",
            "state": state, "reason_code": None, "state_since": since, "preauthorization": None}


def test_an_entry_that_waits_for_confirmation_is_an_item_dated_by_the_servers_state_since():
    waiting = _entry("run-7", "task-7", "confirmation_required", "2026-09-29T09:40:00Z")
    unknown = _entry("run-8", "task-8", "confirmation_required", None, 2)
    got = items_for(project(task_queue=_queue(waiting, unknown)))
    assert got == [
        item("queue_confirmation", "waiting", "2026-09-29T09:40:00Z", task="task-7", run="run-7"),
        item("queue_confirmation", "observed", OBSERVED, task="task-8", run="run-8")]


def test_an_entry_that_starts_by_itself_or_is_blocked_is_not_an_item():
    entries = (_entry("run-7", "task-7", "preauthorized", "2026-09-29T09:40:00Z"),
               _entry("run-8", "task-8", "blocked", None, 2))
    assert items_for(project(task_queue=_queue(*entries))) == []


def test_a_stuck_slot_is_an_item_always_noticed_and_named_by_the_task_that_holds_it():
    stuck = {"state": "stuck", "run_id": "run-1", "reason_code": "plan_stalled"}
    held, unknown = items_of(
        project(row(human="not_required"), task_queue=_queue(slot=stuck)),
        project(task_queue=_queue(slot={**stuck, "run_id": "run-x"})))
    assert held == [item("slot_stuck", "observed", OBSERVED)]
    assert unknown == [item("slot_stuck", "observed", OBSERVED, task=None, run="run-x")]
    for state in ("free", "busy", "unavailable"):
        slot = {"state": state, "run_id": "run-1" if state == "busy" else None,
                "reason_code": None}
        assert items_for(project(task_queue=_queue(slot=slot))) == [], state


# -- the project itself ------------------------------------------------------------------
def test_a_project_that_needs_a_restart_of_the_os_and_a_login_that_needs_recovery_are_items():
    bare = {"task_id": None, "run_id": None, "gate_id": None}
    recovery, login, neither = items_of(
        project(state="recovery_required"), project(login_unclosed=True), project())
    assert recovery == [{**item("recovery_required", "observed", OBSERVED), **bare}]
    assert login == [{**item("login_recovery_required", "observed", OBSERVED), **bare}]
    assert neither == []


# -- a snapshot, and what the list looks like whole ---------------------------------------
def test_every_item_of_a_snapshot_carries_the_moment_of_the_snapshot_and_a_live_one_carries_none():
    stalled = row(human="not_required", grant=automation("stalled", "plan_stalled"))
    snap, blank, live, other = items_of(
        project(row(seen=FIVE), stalled, data="snapshot", snapshot_at="2026-09-29T08:40:00Z"),
        project(stalled, data="snapshot", snapshot_at=None),
        project(row(seen=FIVE), stalled, snapshot_at="2026-09-29T08:40:00Z"),
        project(stalled, data="none", snapshot_at="2026-09-29T08:40:00Z"))
    assert len(snap) == 6 and {x["snapshot_at"] for x in snap} == {"2026-09-29T08:40:00Z"}
    assert [x["snapshot_at"] for x in blank] == [None]
    assert {x["snapshot_at"] for x in live} == {None}
    assert {x["snapshot_at"] for x in other} == {None}


def test_the_list_runs_human_steps_then_automation_then_queue_then_slot_then_project_facts():
    tasks = (row("task-a", "run-1", seen=attention(("confirmation", ["proposal-1"]))),
             row("task-b", "run-2", human="not_required",
                 grant=automation("expired", "expired")),
             row("task-c", "run-3", human="not_required",
                 grant=automation("stalled", "plan_stalled")))
    queue = _queue(_entry("run-9", "task-9", "confirmation_required", None),
                   slot={"state": "stuck", "run_id": "run-3", "reason_code": "plan_stalled"})
    got = items_for(project(*tasks, task_queue=queue, state="recovery_required",
                            login_unclosed=True))
    assert [(x["reason"], x["run_id"]) for x in got] == [
        ("confirmation", "run-1"), ("expired", "run-2"), ("stalled", "run-3"),
        ("queue_confirmation", "run-9"), ("slot_stuck", "run-3"),
        ("recovery_required", None), ("login_recovery_required", None)]
    assert [x["task_id"] for x in got][:5] == ["task-a", "task-b", "task-c", "task-9", "task-c"]
    assert {x["key"] for x in got} == {f"attention_{x['reason']}" for x in got}
    assert {x["reason"] for x in got} <= set(REASONS)


def test_one_pair_of_run_and_reason_is_one_item_however_often_the_input_says_it():
    twice = attention(("confirmation", ["proposal-1"]), ("confirmation", ["proposal-2"]))
    assert [x["reason"] for x in items_for(project(row(seen=twice)))] == ["confirmation"]


def test_items_are_frozen_and_the_input_is_read_and_never_changed():
    out = run_js("""
      const deep = (value) => { Object.values(value ?? {}).forEach(
        (item) => typeof item === "object" && deep(item)); return Object.freeze(value); };
      const got = st.attentionItems(deep(structuredClone(d)));
      console.log(JSON.stringify({n: got.length, list: Object.isFrozen(got),
        each: got.every((one) => Object.isFrozen(one) && Object.isFrozen(one.since))}));
    """, MODULES, project(row(seen=FIVE), row("task-b", "run-2", human="not_required",
                                              grant=automation("stalled", "plan_stalled"))))
    assert out == {"n": 6, "list": True, "each": True}


@pytest.mark.parametrize("given", [
    None, 3, "project", [], {}, {"tasks": "rows"}, {"tasks": [None, 3, "row", {}]},
    {"tasks": [{"task": TASK, "run": 4, "automation": "x", "attention": 5}]},
    {"task_queue": 4}, {"task_queue": {"slot": None, "entries": "no"}},
    {"task_queue": {"slot": {"state": "stuck"}, "entries": [None, 3, {}]}}])
def test_input_that_is_not_a_project_summary_makes_a_list_and_never_throws(given):
    assert isinstance(items_for(given), list)


# -- a row's word: a wait's reason, a snapshot and the view ------------------------------
def _statuses(*inputs: object) -> list:
    return run_js("console.log(JSON.stringify(d.map((input) => st.taskStatus(input))));",
                  MODULES, list(inputs))


def test_a_run_that_waits_for_a_person_says_the_first_reason_that_was_read_beside_its_word():
    seen = attention(("reconcile", [], 0), ("gate_decision", ["review"]))
    waiting = a_run(human_state="required")
    bare, read, first, none_read, only_end = _statuses(
        {"task": TASK, "run": waiting},
        {"task": TASK, "run": waiting, "attention": FIVE},
        {"task": TASK, "run": waiting, "attention": seen},
        {"task": TASK, "run": waiting, "attention": None},
        {"task": TASK, "run": waiting,
         "attention": attention(("run_ended", ["terminal-1"]))})
    assert bare == {"key": "waiting_you", "params": {}}
    assert read == {"key": "waiting_you", "params": {"reason": "gate_decision"}}
    assert first == {"key": "waiting_you", "params": {"reason": "gate_decision"}}
    assert none_read == {"key": "waiting_you", "params": {}}
    assert only_end == {"key": "waiting_you", "params": {}}


def test_a_read_wait_changes_no_other_word_of_the_table():
    inputs = [{**case, "attention": FIVE} for case, _ in CASES.values()]
    for (case, expected), got in zip(CASES.values(), _statuses(*inputs)):
        if expected["key"] != "waiting_you":
            assert got == expected, case


def test_a_snapshot_adds_its_moment_to_the_params_of_every_word_and_changes_no_key():
    stamp = "2026-09-29T08:40:00Z"
    snapshot = _statuses(*[{**case, "data": "snapshot", "snapshot_at": stamp}
                           for case, _ in CASES.values()])
    unknown = _statuses(*[{**case, "data": "snapshot"} for case, _ in CASES.values()])
    live = _statuses(*[{**case, "data": "live", "snapshot_at": stamp}
                       for case, _ in CASES.values()])
    for (_case, expected), snap, blank, alive in zip(CASES.values(), snapshot, unknown, live):
        assert snap == {"key": expected["key"], "params": {**expected["params"],
                                                            "snapshot_at": stamp}}
        assert blank == {"key": expected["key"], "params": {**expected["params"],
                                                             "snapshot_at": None}}
        assert alive == expected


def test_the_mode_of_the_project_never_changes_the_word_of_a_row():
    for mode in ("active", "view", None):
        got = _statuses(*[{**case, "mode": mode} for case, _ in CASES.values()])
        assert got == [expected for _case, expected in CASES.values()], mode


def test_in_a_view_project_a_granted_run_reads_as_a_checkpoint_of_a_project_that_is_not_active():
    """The automation read of a `view` process says `project_not_active` (spec 4.4.1), which is
    rule 10: the word needs no mode, and the same run is no "waiting for you" item."""
    grant = automation("restart_required", "project_not_active")
    word = _statuses({"task": TASK, "run": a_run(), "automation": grant, "mode": "view"})[0]
    assert word == {"key": "checkpoint_inactive", "params": {}}
    assert items_for(project(row(human="not_required", grant=grant), mode="view")) == []


def test_a_queue_record_of_a_project_that_is_not_active_reads_as_queued_after_activation():
    queued = entry("preauthorized", "project_not_active", 1)
    word = _statuses({"task": TASK, "run": a_run(), "entry": queued, "mode": "view"})[0]
    assert word == {"key": "queued_inactive", "params": {}}
