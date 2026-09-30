"""The task-queue read (spec 4.4.6) judged against its shape, from the real `desk-queue-model.js`.

The route is lane L's and is not served yet, so the bodies here are lane D1's own fixtures of the
shape in the spec (`tests/fixtures/desk/queue_read.json`). The model is values in, values out:
a body it can vouch for comes back frozen and cut to the fields the desk reads, and a body it
cannot vouch for is `null`, so the console draws nothing rather than a queue it cannot trust.
The closed lists are written out here by hand from the spec, not read back from the module.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from tests.desk_node import PANEL, run_js
from tests.test_desk_status import ENTRY_REASONS
from tests.test_desk_time import clock_reads
from tests.test_graph_source import _code

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "desk" / "queue_read.json")
                     .read_text(encoding="utf-8"))
CASES = FIXTURE["cases"]
MODULES = {"queue": "desk-queue-model.js"}
#: The reasons a record may give under each state (spec 4.4.6), by hand.
REASONS = {
    "preauthorized": ("behind", "slot_busy", "slot_unavailable", "project_not_active"),
    "confirmation_required": ("terms_changed", "grant_expired", "grant_changed",
                              "preview_refused", "server_restarted"),
    "blocked": ("run_unreadable", "receipt_conflict")}
ENTRY_KEYS = ("run_id", "task_id", "title", "position", "kind", "enqueued_at", "enqueued_by",
              "state", "reason_code", "state_since")
BUSY = CASES[1]["body"]
MANY = CASES[2]["body"]


def _judge(*bodies: object) -> list:
    return run_js("console.log(JSON.stringify(d.map((body) => queue.projectQueue(body))));",
                  MODULES, list(bodies))


def _cut(body: dict) -> dict:
    """What a kept body must come back as: the fields the desk reads, and no others."""
    return {"revision": body["revision"], "slot": body["slot"],
            "entries": [{key: entry[key] for key in ENTRY_KEYS} for entry in body["entries"]]}


#: What the module exports: the judgement of a read and the moves a person makes on one (a
#: module namespace lists its names in alphabetical order).
EXPORTS = ["controlBody", "controlRecorded", "holdsOrder", "holdsRun", "movedOrder",
           "orderBody", "projectHolder", "projectQueue", "releaseOffer", "withdrawBody"]


def test_the_module_exports_the_judgement_and_the_moves_of_a_person_and_nothing_else():
    assert run_js("console.log(JSON.stringify(Object.keys(queue)));", MODULES) == EXPORTS


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_each_fixture_body_is_kept_cut_to_the_fields_the_desk_reads(case):
    assert _judge(case["body"]) == [_cut(case["body"])]


def test_a_kept_queue_is_frozen_all_the_way_down_and_a_field_it_does_not_read_is_left_out():
    body = {**copy.deepcopy(MANY), "future_key": 1}
    body["entries"][0]["future_key"] = {"nested": True}
    out = run_js("""
      const deep = (value) => value === null || typeof value !== "object"
        || (Object.isFrozen(value) && Object.values(value).every(deep));
      const got = queue.projectQueue(d);
      console.log(JSON.stringify({frozen: deep(got), keys: Object.keys(got),
        entry: Object.keys(got.entries[0])}));
    """, MODULES, body)
    assert out == {"frozen": True, "keys": ["revision", "slot", "entries"],
                   "entry": list(ENTRY_KEYS)}


def _with(body: dict, path: tuple, value: object) -> dict:
    edited = copy.deepcopy(body)
    target = edited
    for step in path[:-1]:
        target = target[step]
    if value is _GONE:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return edited


_GONE = object()
FIRST = ("entries", 0)
#: name -> (the body, a broken copy of it). Each break is one fault.
BROKEN = {
    "no schema_version": lambda: _with(MANY, ("schema_version",), _GONE),
    "another schema_version": lambda: _with(MANY, ("schema_version",), 2),
    "no revision": lambda: _with(MANY, ("revision",), _GONE),
    "a negative revision": lambda: _with(MANY, ("revision",), -1),
    "a fractional revision": lambda: _with(MANY, ("revision",), 1.5),
    "a text revision": lambda: _with(MANY, ("revision",), "9"),
    "a boolean revision": lambda: _with(MANY, ("revision",), True),
    "no slot": lambda: _with(MANY, ("slot",), _GONE),
    "a slot that is a list": lambda: _with(MANY, ("slot",), []),
    "a slot state outside the four": lambda: _with(MANY, ("slot", "state"), "idle"),
    "a free slot that names a run": lambda: _with(BUSY, ("slot", "state"), "free"),
    "a busy slot with no run": lambda: _with(BUSY, ("slot", "run_id"), None),
    "a stuck slot with no run": lambda: _with(MANY, ("slot", "run_id"), None),
    "a slot run id that is a number": lambda: _with(BUSY, ("slot", "run_id"), 4),
    "a slot reason that is a number": lambda: _with(BUSY, ("slot", "reason_code"), 4),
    "no entries": lambda: _with(MANY, ("entries",), _GONE),
    "entries that are a text": lambda: _with(MANY, ("entries",), "none"),
    "an entry that is not an object": lambda: _with(MANY, ("entries", 0), "run-docs"),
    "thirty-three entries": lambda: _with(MANY, ("entries",), [
        {**MANY["entries"][0], "run_id": f"run-{n}", "position": n + 1} for n in range(33)]),
    "a run id outside the grammar": lambda: _with(MANY, (*FIRST, "run_id"), "a/b"),
    "an empty run id": lambda: _with(MANY, (*FIRST, "run_id"), ""),
    "a task id that is a number": lambda: _with(MANY, (*FIRST, "task_id"), 3),
    "a title that is a number": lambda: _with(MANY, (*FIRST, "title"), 3),
    "a position of zero": lambda: _with(MANY, (*FIRST, "position"), 0),
    "positions with a gap": lambda: _with(MANY, ("entries", 1, "position"), 3),
    "positions out of order": lambda: _with(MANY, ("entries", 0, "position"), 2),
    "a fractional position": lambda: _with(MANY, (*FIRST, "position"), 1.5),
    "a kind outside the two": lambda: _with(MANY, (*FIRST, "kind"), "restart"),
    "a state outside the three": lambda: _with(MANY, (*FIRST, "state"), "queued"),
    "a reason from another state": lambda: _with(MANY, (*FIRST, "reason_code"), "behind"),
    "a reason outside every list": lambda: _with(MANY, (*FIRST, "reason_code"), "on_fire"),
    "a reason that is a number": lambda: _with(MANY, (*FIRST, "reason_code"), 4),
    "a state_since that is a number": lambda: _with(MANY, (*FIRST, "state_since"), 4),
    "an enqueued_at that is missing": lambda: _with(MANY, (*FIRST, "enqueued_at"), _GONE),
    "an enqueued_by that is a number": lambda: _with(MANY, (*FIRST, "enqueued_by"), 4),
    "two entries of one run": lambda: _with(MANY, ("entries", 1, "run_id"), "run-docs"),
}
NON_OBJECTS = (None, 3, "queue", [], True)


@pytest.mark.parametrize("name", list(BROKEN))
def test_a_body_with_one_fault_is_refused(name):
    assert _judge(BROKEN[name]()) == [None]


def test_a_body_that_is_not_an_object_is_refused():
    assert _judge(*NON_OBJECTS) == [None] * len(NON_OBJECTS)


def test_the_unbroken_bodies_the_faults_are_cut_from_are_kept():
    assert all(kept is not None for kept in _judge(BUSY, MANY))


def test_every_reason_of_the_spec_is_kept_under_its_own_state_and_refused_under_the_others():
    bodies, expected = [], []
    for state, reasons in REASONS.items():
        for code in reasons:
            for other in REASONS:
                edited = _with(MANY, (*FIRST, "state"), other)
                bodies.append(_with(edited, (*FIRST, "reason_code"), code))
                expected.append(other == state)
    assert [kept is not None for kept in _judge(*bodies)] == expected
    assert sorted(code for reasons in REASONS.values() for code in reasons) == sorted(ENTRY_REASONS)


def test_a_reason_may_be_null_under_every_state():
    bodies = [_with(_with(MANY, (*FIRST, "state"), state), (*FIRST, "reason_code"), None)
              for state in REASONS]
    assert all(kept is not None for kept in _judge(*bodies))


def test_a_slot_may_say_any_reason_the_policy_names_and_none():
    bodies = [_with(BUSY, ("slot", "reason_code"), reason)
              for reason in ("action_in_flight", "plan_waiting", "seed_blocked", None)]
    assert all(kept is not None for kept in _judge(*bodies))


# -- the moves of a person on a queue (spec 4.4.5, 4.4.8): order and withdraw ----------------------


def _queue_of(*run_ids: str, revision: int = 7) -> dict:
    """A body of the read with one entry that starts on its own per run, in this order."""
    entries = [{**MANY["entries"][0], "run_id": run_id, "task_id": f"task-{run_id}",
                "title": run_id.upper(), "position": place + 1, "state": "preauthorized",
                "reason_code": "behind"} for place, run_id in enumerate(run_ids)]
    return {**BUSY, "revision": revision, "entries": entries}


def _moves(body: dict, script: str) -> object:
    return run_js(f"const held = queue.projectQueue(d); console.log(JSON.stringify({script}));",
                  MODULES, body)


@pytest.mark.parametrize("run_id, step, expected", [
    ("b", -1, ["b", "a", "c"]), ("b", 1, ["a", "c", "b"]), ("a", 1, ["b", "a", "c"]),
    ("c", -1, ["a", "c", "b"]),
    ("a", -1, None), ("c", 1, None), ("z", 1, None), ("b", 0, None), ("b", 2, None),
    ("b", "1", None), ("b", None, None)])
def test_an_entry_steps_one_place_among_the_visible_entries_and_the_ends_lead_nowhere(
        run_id, step, expected):
    got = _moves(_queue_of("a", "b", "c"), f"queue.movedOrder(held, {json.dumps(run_id)}, "
                                           f"{json.dumps(step)})")
    assert got == expected


def test_a_queue_of_one_entry_has_no_step_at_all():
    assert _moves(_queue_of("a"), 'queue.movedOrder(held, "a", 1)') is None
    assert _moves(_queue_of("a"), 'queue.movedOrder(held, "a", -1)') is None


def test_the_order_body_is_the_revision_that_was_read_and_the_full_list_in_the_new_order():
    got = _moves(_queue_of("a", "b", "c", revision=41), """(() => {
      const body = queue.orderBody(held, "b", 1);
      return {body, keys: Object.keys(body), frozen: Object.isFrozen(body)
        && Object.isFrozen(body.run_ids), none: queue.orderBody(held, "c", 1)};
    })()""")
    assert got == {"body": {"expected_revision": 41, "run_ids": ["a", "c", "b"]},
                   "keys": ["expected_revision", "run_ids"], "frozen": True, "none": None}


def test_a_withdraw_body_is_an_empty_object_and_is_frozen():
    assert _moves(_queue_of("a"), """(() => {
      const body = queue.withdrawBody();
      return {body, frozen: Object.isFrozen(body), same: queue.withdrawBody() === body};
    })()""") == {"body": {}, "frozen": True, "same": False}


def test_what_landed_is_read_from_the_queue_and_never_from_an_answer():
    got = _moves(_queue_of("a", "b", "c"), """({
      order: [queue.holdsOrder(held, ["a", "b", "c"]), queue.holdsOrder(held, ["a", "c", "b"]),
              queue.holdsOrder(held, ["a", "b"]), queue.holdsOrder(held, [])],
      run: [queue.holdsRun(held, "b"), queue.holdsRun(held, "z")],
      not_a_queue: [queue.holdsOrder(null, ["a"]), queue.holdsRun(null, "a")]})""")
    assert got == {"order": [True, False, False, False], "run": [True, False],
                   "not_a_queue": [False, False]}


# -- freeing the slot: the holder's read, the control's body, the offer (spec 4.4.8) --------------

DIGEST = "sha256:" + "a" * 64
HOLDER = {"run_id": "run-x", "state": "expired", "reason_code": "expired",
          "authorization": {"authorization_id": "grant-1", "authorization_digest": DIGEST,
                            "authorized_by": "vasya", "terms": "not read"},
          "control": None, "spent_actions": 1}


#: What the model cuts `HOLDER` to, written out by hand (the tests below read it from the module).
SEEN = {"run_id": "run-x", "state": "expired", "reason_code": "expired",
        "grant": {"authorization_id": "grant-1", "authorization_digest": DIGEST},
        "last_control_id": None}
SEEN_PAUSED = {**SEEN, "last_control_id": "control-7"}
SEEN_NO_GRANT = {**SEEN, "grant": None}


def _holder(run_id: str, **changes: object) -> dict:
    return {**copy.deepcopy(HOLDER), "run_id": run_id, **changes}


def _seen(read: object, run_id: str = "run-x") -> object:
    return run_js("console.log(JSON.stringify(queue.projectHolder(d.read, d.run)));", MODULES,
                  {"read": read, "run": run_id})


def test_a_holder_read_is_cut_to_its_grant_and_its_last_control():
    assert _seen(HOLDER) == {"run_id": "run-x", "state": "expired", "reason_code": "expired",
                             "grant": {"authorization_id": "grant-1",
                                       "authorization_digest": DIGEST},
                             "last_control_id": None}
    paused = _holder("run-x", control={"control_id": "control-7", "action": "pause"})
    assert _seen(paused)["last_control_id"] == "control-7"
    assert _seen(_holder("run-x", authorization=None, control=None))["grant"] is None


@pytest.mark.parametrize("what, read", [
    ("another run's read", _holder("run-y")),
    ("a grant with no digest", _holder("run-x", authorization={"authorization_id": "grant-1"})),
    ("a grant whose digest is not one", _holder(
        "run-x", authorization={"authorization_id": "grant-1", "authorization_digest": "abc"})),
    ("a grant whose id is outside the grammar", _holder(
        "run-x", authorization={"authorization_id": "a/b", "authorization_digest": DIGEST})),
    ("a control that is not an object", _holder("run-x", control="pause")),
    ("a control with no id", _holder("run-x", control={"action": "pause"})),
    ("no control key at all", {key: value for key, value in HOLDER.items() if key != "control"}),
    ("a state that is a number", _holder("run-x", state=3)),
    ("a reason that is missing", {key: value for key, value in HOLDER.items()
                                  if key != "reason_code"}),
    ("a list", []), ("nothing", None), ("a text", "run-x")])
def test_a_holder_read_the_desk_cannot_vouch_for_is_refused(what, read):
    assert _seen(read) is None, what


def _body(holder: object, **ask: object) -> object:
    return run_js("console.log(JSON.stringify(queue.controlBody(d.holder, d.ask)));", MODULES,
                  {"holder": holder, "ask": ask})


def test_the_control_body_carries_the_grant_the_last_control_the_action_and_the_person():
    holder = SEEN_PAUSED
    for action in ("pause", "revoke"):
        assert _body(holder, action=action, actor="vasya", controlId="control-abc") == {
            "control_id": "control-abc", "authorization_id": "grant-1",
            "authorization_digest": DIGEST, "action": action, "actor": "vasya",
            "expected_control_id": "control-7"}
    assert _body(SEEN, action="pause", actor="vasya", controlId="c-1")[
        "expected_control_id"] is None


@pytest.mark.parametrize("what, holder, ask", [
    ("a run with no grant", SEEN_NO_GRANT,
     {"action": "pause", "actor": "vasya", "controlId": "c-1"}),
    ("no holder read", None, {"action": "pause", "actor": "vasya", "controlId": "c-1"}),
    ("a resume, which this door never writes", SEEN,
     {"action": "resume", "actor": "vasya", "controlId": "c-1"}),
    ("an action that is no action", SEEN,
     {"action": "stop", "actor": "vasya", "controlId": "c-1"}),
    ("no person", SEEN, {"action": "pause", "actor": "", "controlId": "c-1"}),
    ("a person that is null", SEEN,
     {"action": "pause", "actor": None, "controlId": "c-1"}),
    ("a control id outside the grammar", SEEN,
     {"action": "pause", "actor": "vasya", "controlId": "a b"})])
def test_a_control_body_is_refused_without_a_grant_a_known_action_a_person_and_an_id(
        what, holder, ask):
    assert _body(holder, **ask) is None, what


def test_a_control_is_recorded_only_when_the_holder_read_names_its_id_as_the_last_control():
    seen = SEEN_PAUSED
    got = run_js("""console.log(JSON.stringify([queue.controlRecorded(d.holder, "control-7"),
      queue.controlRecorded(d.holder, "control-8"), queue.controlRecorded(null, "control-7"),
      queue.controlRecorded(d.none, "control-7"), queue.controlRecorded(d.none, null)]));""",
                 MODULES, {"holder": seen, "none": SEEN})
    assert got == [True, False, False, False, False]


def _slot(state: str, reason: str | None, run_id: str | None = "run-fix-new") -> dict:
    return {**BUSY, "slot": {"state": state, "run_id": run_id, "reason_code": reason}}


@pytest.mark.parametrize("body, mode, actor, expected", [
    (_slot("stuck", "expired"), "active", "vasya",
     {"run_id": "run-fix-new", "reason": "expired", "named": True}),
    (_slot("stuck", "feedback_required"), "active", None,
     {"run_id": "run-fix-new", "reason": "feedback_required", "named": False}),
    (_slot("stuck", "expired"), None, "vasya",
     {"run_id": "run-fix-new", "reason": "expired", "named": True}),
    (_slot("stuck", "expired"), "view", "vasya", None),
    (_slot("busy", "plan_waiting"), "active", "vasya", None),
    (_slot("free", None, None), "active", "vasya", None),
    (_slot("unavailable", "owner_required", None), "active", "vasya", None)])
def test_freeing_the_slot_is_offered_only_for_a_stuck_holder_and_never_in_view(
        body, mode, actor, expected):
    got = run_js("""const held = queue.projectQueue(d.body);
      console.log(JSON.stringify(queue.releaseOffer(held, d.ask)));""", MODULES,
                 {"body": body, "ask": {"mode": mode, "actor": actor}})
    assert got == expected
    assert run_js("console.log(JSON.stringify(queue.releaseOffer(null, d)));", MODULES,
                  {"mode": "active", "actor": "vasya"}) is None


def test_the_model_imports_nothing_reads_no_clock_and_touches_no_page():
    source = (PANEL / "desk-queue-model.js").read_text(encoding="utf-8")
    assert not re.search(r"^import\b|\bimport\s*\(", source, re.M)
    code = _code(PANEL / "desk-queue-model.js")
    assert clock_reads(code) == []
    assert not re.search(r"\b(?:document|window|fetch|localStorage|sessionStorage)\b", code)
