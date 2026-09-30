"""The control ids of the continue-after flag are the flag's alone (spec 4.3.4, 4.4.4 step 3).

The control the pump writes for a run the flag lists is named `flag-` and 32 hex digits, and a
control has no field that says the flag wrote it: the name is the mark, and the desk reads
«continued by the flag» from it. A mark says something only while nobody else can make it, so the
two doors through which a human's control id enters (the automation control and the queue's
resume) refuse the shape, and the pump refuses to write it for a queue entry that already holds
it. The flag's own writer passes through none of them: `test_queue_pump_flag.py` holds that.
"""
from __future__ import annotations

import re

import pytest

from conductor.command import queue_flag
from conductor.command.api_contracts import refusal_from_exception
from conductor.command.contract_values import ContractError
from conductor.command.flag_control_id import is_flag_control_id, refuse_flag_control_id
from conductor.command.queue_bodies import parse_write
from conductor.command.queue_store import QueueEntry, ResumePreauth
from tests.queue_fixtures import Holder, NOW, project, resume_body, start_body
from tests.test_command_http_api import post
from tests.test_command_queue_wire import error, wire
from tests.test_queue_pump import controls, paused_grant, q  # noqa: F401  (q is the fixture)

NAME = "flag-0123456789abcdef0123456789abcdef"
REFUSED = "continue-after flag"


def test_the_shape_is_exactly_what_the_pump_names_its_resume_of_a_listed_run():
    name = queue_flag.control_id_of("00000001-1111-4222-8333-444444444444", "run")
    assert re.fullmatch(r"flag-[0-9a-f]{32}", name) and is_flag_control_id(name)
    assert is_flag_control_id(NAME)


@pytest.mark.parametrize("name", [
    "flag-" + "a" * 31, "flag-" + "a" * 33, "flag-" + "A" * 32, "Flag-" + "a" * 32,
    "flag-" + "g" * 32, "xflag-" + "a" * 32, "flag-" + "a" * 32 + "x", "flag-" + "a" * 32 + "\n",
    "flag_" + "a" * 32, "flag-" + "a" * 16 + "-" + "a" * 15, "flag", ""])
def test_a_neighbour_of_the_shape_is_not_the_shape(name):
    assert not is_flag_control_id(name)
    refuse_flag_control_id(name)                           # and the refusal lets it through


@pytest.mark.parametrize("value", [None, 5, b"flag-" + b"a" * 32, ["flag-" + "a" * 32]])
def test_a_value_that_is_not_a_string_is_not_the_shape(value):
    assert not is_flag_control_id(value)


def test_the_refusal_of_the_shape_is_a_contract_error_that_says_whose_name_it_is():
    with pytest.raises(ContractError, match=REFUSED):
        refuse_flag_control_id(NAME)


def prepared(tmp_path, action):
    """A run with a live grant (paused first for a resume) and the control body for `action`."""
    f = project(tmp_path)
    f.policy.driver = Holder()
    granted, _ = f.policy.authorize("run", start_body(f, "run", "grant-1"))
    expected = None
    if action == "resume":
        f.policy.control("run", {"control_id": "pause", "authorization_id": "grant-1",
            "authorization_digest": granted.authorization_digest, "action": "pause",
            "actor": "owner", "expected_control_id": None})
        expected = "pause"

    def body(control_id):
        return {"control_id": control_id, "authorization_id": "grant-1",
                "authorization_digest": granted.authorization_digest, "action": action,
                "actor": "owner", "expected_control_id": expected}
    return f, body


@pytest.mark.parametrize("action", ["resume", "pause", "revoke"])
def test_a_direct_control_named_like_the_flags_is_refused_and_writes_nothing(tmp_path, action):
    f, body = prepared(tmp_path, action)
    before = f.store.read("run").records
    with pytest.raises(ContractError, match=REFUSED):
        f.policy.control("run", body(NAME))
    assert f.store.read("run").records == before
    control, created = f.policy.control("run", body("by-hand"))   # the same body, another name
    assert created and control.control_id == "by-hand"


def test_a_queue_resume_named_like_the_flags_is_refused_as_contract_invalid(q):
    granted = paused_grant(q, "run")
    with pytest.raises(ContractError, match=REFUSED) as refused:
        parse_write({"run_id": "run", "resume": resume_body(granted, NAME, "pause")}, NOW)
    assert refusal_from_exception(refused.value).code == "contract_invalid"
    ask = parse_write({"run_id": "run", "resume": resume_body(granted, "resume-1", "pause")}, NOW)
    assert ask.preauth.control_id == "resume-1"


def test_an_entry_already_on_file_with_the_flags_name_is_dropped_and_writes_no_control(q):
    granted = paused_grant(q, "run")
    pre = ResumePreauth(NAME, granted.authorization_id, granted.authorization_digest, "pause",
                        "vasily", NOW)
    entry = QueueEntry("run", "resume", NOW, "vasily", pre, None)     # came in before the doors
    q.service.commit([entry], [])
    q.service.admitted.add(entry.key)
    assert q.service.start_next() is False
    assert [row.control_id for row in controls(q)] == ["pause"]
    dropped, = q.service.store.read().entries
    assert dropped.preauthorization is None and dropped.dropped.reason_code == "preview_refused"
    assert q.service.store.read_receipt("run", "run_authorization_control", NAME) is None


@pytest.mark.parametrize("door", ["/command/runs/run/automation/control", "/command/queue"])
def test_the_wire_refuses_the_flags_name_at_both_doors_422_contract_invalid_and_writes_nothing(
        tmp_path, door):
    w = wire(tmp_path)
    granted, _ = w.f.policy.authorize("run", start_body(w.f, "run", "grant-1"))
    w.f.policy.control("run", {"control_id": "pause", "authorization_id": "grant-1",
        "authorization_digest": granted.authorization_digest, "action": "pause",
        "actor": "owner", "expected_control_id": None})
    w.events.clear()
    records = w.f.store.read("run").records
    resume = {"control_id": NAME, "authorization_id": "grant-1", "actor": "vasily",
              "authorization_digest": granted.authorization_digest, "expected_control_id": "pause"}
    body = {"run_id": "run", "resume": resume} if door == "/command/queue" else {
        **resume, "action": "resume", "actor": "owner"}
    assert error(post(w.api, door, body)) == (422, "contract_invalid", {})
    assert w.f.store.read("run").records == records and w.events == []
    assert not w.api._queue.store.path.exists()
