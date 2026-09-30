"""The continue-after flag judged against its shape, from the real module under Node.

`desk-flag-model.js` is values in, values out: it judges the record a read of
`/command/project/auto-continue` answers (spec 4.3.4), says which line of spec 5.8 the record
reads as, lists the runs a person may mark from what the desk already holds, and builds the
closed body of a save. The records are D1's fixture `tests/fixtures/desk/flag_reads.json`, in the
shape lane H's hand-off fixes; every malformed body below is made from one of them by a single
change, so what turns it away is that change and nothing else.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from tests.desk_node import run_js

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "desk" / "flag_reads.json")
                      .read_text(encoding="utf-8"))
RECORDS = {name: FIXTURES[name] for name in ("absent", "standing", "removed", "consumed")}
MODULES = {"flag": "desk-flag-model.js"}


def _judge(payloads: list[Any]) -> list[Any]:
    """`projectFlag` of each payload, and whether the answer is frozen all the way down."""
    return run_js("""
      const frozen = (value) => value === null || typeof value !== "object"
        || (Object.isFrozen(value) && Object.values(value).every(frozen));
      console.log(JSON.stringify(d.map((payload) => {
        const found = flag.projectFlag(payload);
        return {flag: found, frozen: found === null ? null : frozen(found)};
      })));
    """, MODULES, payloads)


@pytest.mark.parametrize("name", list(RECORDS))
def test_each_record_of_spec_5_8_is_kept_whole_frozen_and_unchanged(name):
    (answer,) = _judge([RECORDS[name]])
    assert answer == {"flag": RECORDS[name], "frozen": True}


def _without(key: str) -> dict:
    record = copy.deepcopy(RECORDS["standing"])
    del record[key]
    return record


def _with(**changes: Any) -> dict:
    return {**copy.deepcopy(RECORDS["standing"]), **changes}


def _run(**changes: Any) -> dict:
    row = {**RECORDS["standing"]["resume_runs"][0], **changes}
    return _with(resume_runs=[row])


MALFORMED = {
    **{f"missing-{key}": _without(key) for key in RECORDS["standing"]},
    "a-key-too-many": _with(extra=1),
    "schema-version-1": _with(schema_version=1),
    "schema-version-text": _with(schema_version="2"),
    "revision-negative": _with(revision=-1),
    "revision-fraction": _with(revision=1.5),
    "revision-text": _with(revision="3"),
    "enabled-text": _with(enabled="true"),
    "actor-number": _with(actor=7),
    "flag-id-empty": _with(flag_id=""),
    "set-at-number": _with(set_at=7),
    "queue-number": _with(start_task_queue=1),
    "runs-not-a-list": _with(resume_runs={"run-old": 1}),
    "run-row-not-an-object": _with(resume_runs=["run-old"]),
    "run-row-a-key-too-many": _run(extra="x"),
    "run-row-missing-digest": _with(resume_runs=[
        {key: value for key, value in RECORDS["standing"]["resume_runs"][0].items()
         if key != "authorization_digest"}]),
    "run-id-empty": _run(run_id=""),
    "authorization-id-number": _run(authorization_id=1),
    "last-control-number": _run(last_control_id=7),
    "last-control-empty": _run(last_control_id=""),
    "consumed-not-an-object": _with(consumed="yes"),
    "consumed-missing-nonce": _with(enabled=False, consumed={"at": "x", "transition_id": "y"}),
    "consumed-a-key-too-many": _with(enabled=False, consumed={
        **RECORDS["consumed"]["consumed"], "extra": "x"}),
    "consumed-empty-at": _with(enabled=False, consumed={**RECORDS["consumed"]["consumed"],
                                                        "at": ""}),
    "standing-without-an-id": _with(flag_id=None),
    "standing-without-an-actor": _with(actor=None),
    "standing-without-a-time": _with(set_at=None),
    "consumed-and-still-enabled": _with(consumed=RECORDS["consumed"]["consumed"]),
}


@pytest.mark.parametrize("name", list(MALFORMED))
def test_a_body_that_is_not_the_record_of_spec_4_3_4_is_no_flag(name):
    assert _judge([MALFORMED[name]]) == [{"flag": None, "frozen": None}]


def test_what_is_not_an_object_is_no_flag():
    got = _judge([None, [], [RECORDS["standing"]], "flag", 7, True])
    assert got == [{"flag": None, "frozen": None}] * 6


def test_a_flag_reads_as_the_line_of_spec_5_8_its_record_earns():
    got = run_js("""
      console.log(JSON.stringify(d.map((payload) => flag.flagLine(flag.projectFlag(payload)))));
    """, MODULES, [RECORDS[name] for name in ("standing", "consumed", "absent", "removed")])
    assert got == [
        {"kind": "standing", "at": "2026-09-30T14:05:00Z", "actor": "vasya"},
        {"kind": "consumed", "at": "2026-09-30T16:40:00Z", "actor": "vasya"},
        {"kind": "none", "at": None, "actor": None},
        {"kind": "none", "at": None, "actor": None}]


# -- the runs a person may mark ---------------------------------------------------------------

def _task(task_id: str, **more: Any) -> dict:
    return {"task_id": task_id, "title": f"Title of {task_id}", **more}


def _run_row(run_id: str, task_id: str, created: str) -> dict:
    return {"run_id": run_id, "task_id": task_id, "created_at": created}


def _answer(run_id: str, state: str, reason: str) -> dict:
    return {"run_id": run_id, "state": state, "reason_code": reason}


#: (task id, the run of it, created, the automation answer or None): one task per case of the
#: table of spec 5.8 -- and the runs a flag can never continue.
WORLD = (
    ("t-paused", "r-paused", "2026-09-30T08:00:00Z", _answer("r-paused", "paused", "paused")),
    ("t-explicit", "r-explicit", "2026-09-30T09:00:00Z",
     _answer("r-explicit", "restart_required", "explicit_resume_required")),
    ("t-inactive", "r-inactive", "2026-09-30T07:00:00Z",
     _answer("r-inactive", "restart_required", "project_not_active")),
    ("t-expired", "r-expired", "2026-09-30T06:00:00Z", _answer("r-expired", "expired", "expired")),
    ("t-running", "r-running", "2026-09-30T05:00:00Z",
     _answer("r-running", "running", "action_in_flight")),
    ("t-waiting", "r-waiting", "2026-09-30T05:01:00Z",
     _answer("r-waiting", "waiting", "plan_waiting")),
    ("t-revoked", "r-revoked", "2026-09-30T05:02:00Z", _answer("r-revoked", "revoked", "revoked")),
    ("t-complete", "r-complete", "2026-09-30T05:03:00Z",
     _answer("r-complete", "complete", "plan_ended")),
    ("t-owner", "r-owner", "2026-09-30T05:04:00Z",
     _answer("r-owner", "restart_required", "owner_required")),
    ("t-noread", "r-noread", "2026-09-30T05:05:00Z", None),
    ("t-other", "r-other", "2026-09-30T05:06:00Z", _answer("r-not-this-one", "paused", "paused")),
)


def _resumable(world=WORLD, phase="ready", unreadable=("t-unread",), extra=()):
    tasks = [_task(task) for task, *_ in world] + [_task(t, unreadable=True) for t in unreadable]
    runs = [_run_row(run, task, created) for task, run, created, _a in world] + list(extra)
    automation = [[task, answer] for task, _r, _c, answer in world]
    automation += [[t, _answer("r-unread", "paused", "paused")] for t in unreadable]
    return run_js("""
      const automation = new Map(d.automation);
      const rows = flag.resumableRuns({tasks: {phase: "ready", list: d.tasks},
        runs: {phase: d.phase, list: d.runs}, automation});
      console.log(JSON.stringify({rows, frozen: Object.isFrozen(rows)}));
    """, MODULES, {"tasks": tasks, "runs": runs, "automation": automation, "phase": phase})


def test_only_a_paused_or_waiting_for_a_resume_run_is_offered_oldest_first_and_expired_apart():
    got = _resumable()
    assert got["frozen"] is True
    assert [(row["run_id"], row["expired"]) for row in got["rows"]] == [
        ("r-expired", True), ("r-inactive", False), ("r-paused", False), ("r-explicit", False)]
    first = got["rows"][1]
    assert first == {"run_id": "r-inactive", "task_id": "t-inactive",
                     "title": "Title of t-inactive", "created_at": "2026-09-30T07:00:00Z",
                     "expired": False}


def test_two_runs_made_at_the_same_instant_are_listed_by_their_ids():
    world = (("t-b", "r-b", "2026-09-30T08:00:00Z", _answer("r-b", "paused", "paused")),
             ("t-a", "r-a", "2026-09-30T08:00:00Z", _answer("r-a", "paused", "paused")))
    assert [row["run_id"] for row in _resumable(world, unreadable=())["rows"]] == ["r-a", "r-b"]


def test_a_task_the_desk_could_not_read_and_a_runs_list_not_yet_read_offer_nothing():
    assert all(row["run_id"] != "r-unread" for row in _resumable()["rows"])
    assert _resumable(phase="loading")["rows"] == []


def test_an_answer_that_names_a_run_the_list_does_not_hold_offers_nothing():
    world = (("t-x", "r-x", "2026-09-30T08:00:00Z", _answer("r-ghost", "paused", "paused")),)
    assert _resumable(world, unreadable=())["rows"] == []


def _marks(flag: dict, rows: list[dict]) -> list[str]:
    return run_js("""
      const record = flag.projectFlag(d.flag);
      console.log(JSON.stringify(flag.initialMarks(record, d.rows)));
    """, MODULES, {"flag": flag, "rows": rows})


def test_a_standing_flag_opens_with_its_listed_runs_marked_when_they_can_still_continue():
    rows = [{"run_id": "run-old", "expired": False}, {"run_id": "run-new", "expired": True},
            {"run_id": "run-other", "expired": False}]
    assert _marks(RECORDS["standing"], rows) == ["run-old"]


@pytest.mark.parametrize("name", ["absent", "removed", "consumed"])
def test_a_flag_that_is_off_opens_with_nothing_marked(name):
    assert _marks(RECORDS[name], [{"run_id": "run-old", "expired": False}]) == []


def _body(**arguments: Any) -> dict:
    return run_js("""
      const body = flag.flagBody(d);
      console.log(JSON.stringify({body, keys: Object.keys(body), frozen: Object.isFrozen(body)
        && Object.isFrozen(body.resume_runs)}));
    """, MODULES, arguments)


def test_the_body_of_a_save_is_the_four_keys_of_spec_4_3_4_in_the_order_it_gives_them():
    got = _body(enabled=True, actor="vasya", runIds=["run-old", "run-new"], startQueue=True)
    assert got["keys"] == ["enabled", "actor", "resume_runs", "start_task_queue"]
    assert got["body"] == {"enabled": True, "actor": "vasya",
                           "resume_runs": ["run-old", "run-new"], "start_task_queue": True}
    assert got["frozen"] is True


def test_a_queue_start_is_true_only_when_it_is_true():
    assert _body(enabled=True, actor="a", runIds=[], startQueue="yes")["body"][
        "start_task_queue"] is False
    assert _body(enabled=True, actor="a", runIds=[])["body"]["start_task_queue"] is False


def test_a_flag_taken_off_names_no_run_and_no_queue_start_whatever_was_marked():
    got = _body(enabled=False, actor="vasya", runIds=["run-old"], startQueue=True)
    assert got["body"] == {"enabled": False, "actor": "vasya", "resume_runs": [],
                           "start_task_queue": False}
    assert got["keys"] == ["enabled", "actor", "resume_runs", "start_task_queue"]
