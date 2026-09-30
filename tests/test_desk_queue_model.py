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


def test_the_module_exports_project_queue_and_nothing_else():
    assert run_js("console.log(JSON.stringify(Object.keys(queue)));", MODULES) == ["projectQueue"]


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


def test_the_model_imports_nothing_reads_no_clock_and_touches_no_page():
    source = (PANEL / "desk-queue-model.js").read_text(encoding="utf-8")
    assert not re.search(r"^import\b|\bimport\s*\(", source, re.M)
    code = _code(PANEL / "desk-queue-model.js")
    assert clock_reads(code) == []
    assert not re.search(r"\b(?:document|window|fetch|localStorage|sessionStorage)\b", code)
