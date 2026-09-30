"""The continue-after flag: its file, its door and the one conditional write (spec 4.3.4).

`<data_root>/auto-continue.json` is what the OWNER of a project decides while looking at the
desk: "when this project is next made active, resume these runs and start the task queue". The
door here is `GET`/`POST /command/project/auto-continue`: a closed body, a server that stamps
`flag_id`, `revision` and `set_at`, and, for every run named, the grant and the last control
the owner was looking at, read from the run journal under the root gate. Nothing here runs the
flag: the queue pump of lane L does, and only through `consume`, which writes the file only if
the flag it was handed is still the one standing.

The route rows, the `CommandApi` attribute and the two branches are lane L's lines
(`H-to-L-auto-continue.patch`), so the handlers are tested directly, over the same stores the
API holds; the patch is walked over a real socket once when it is measured.
"""
from __future__ import annotations

import ast
import json
import re
import threading
from pathlib import Path

import pytest

from conductor.command import auto_continue
from conductor.command.api_refusals import ApiRefusal
from conductor.command.auto_continue import AutoContinueStore
from tests.test_policy_driver import attach_driver, authorize, wait_terminal
from tests.test_policy_runtime import NOW, approve, pause, propose, setup

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
FLAGS = ("6d0f2c1a-3b4e-4f5a-8b9c-0d1e2f3a4b5c", "0e9d8c7b-6a5f-4e3d-8c2b-1a0f9e8d7c6b",
         "5a4b3c2d-1e0f-4a9b-8c7d-6e5f4a3b2c1d")
TRANSITION = "b71e4d09-c2a8-4f35-a6d8-1c0e9f3b5274"
NONCE = "3f9c0a1b2c3d4e5f60718293a4b5c6d7"
LATER = "2026-08-11T13:00:00Z"
CLOSED = {"enabled", "actor", "resume_runs", "start_task_queue"}


def _body(**changes) -> dict:
    return {"enabled": True, "actor": "Вы: Анна", "resume_runs": ["run"],
            "start_task_queue": True, **changes}


class Desk:
    """One project as the door sees it: the run store, the flag file and the clock."""

    def __init__(self, root) -> None:
        self.f = setup(root)
        self.flag = AutoContinueStore(root)
        self._ids = iter(FLAGS)
        self.clock = self.f.policy.clock

    def set(self, body=None, **changes):
        return auto_continue.set_flag(
            self.flag, self.f.store, _body(**changes) if body is None else body, self.clock,
            new_flag_id=lambda: next(self._ids))

    def consume(self, flag_id, revision, **changes):
        arguments = {"expected_flag_id": flag_id, "expected_revision": revision,
                     "transition_id": TRANSITION, "activation_nonce": NONCE, **changes}
        return auto_continue.consume(self.flag, clock=lambda: LATER, **arguments)

    def bytes(self) -> bytes | None:
        return self.flag.path.read_bytes() if self.flag.path.exists() else None


@pytest.fixture
def desk(tmp_path) -> Desk:
    return Desk(tmp_path)


def _refused(call) -> ApiRefusal:
    with pytest.raises(ApiRefusal) as caught:
        call()
    return caught.value


# -- the empty form ------------------------------------------------------------------


def test_no_file_reads_the_form_of_no_flag(desk):
    assert auto_continue.read_flag(desk.flag) == (200, {
        "schema_version": 2, "flag_id": None, "revision": 0, "enabled": False, "actor": None,
        "set_at": None, "resume_runs": [], "start_task_queue": False, "consumed": None})
    assert desk.bytes() is None


# -- the body -------------------------------------------------------------------------


def test_auto_continue_post_needs_an_actor_and_closed_fields_and_the_server_stamps_set_at(desk):
    approve(desk.f)
    refusals = [
        "a list", {}, {k: v for k, v in _body().items() if k != "actor"},
        {**_body(), "set_at": NOW}, {**_body(), "flag_id": FLAGS[0]},
        _body(enabled=1), _body(enabled="true"), _body(start_task_queue=None),
        _body(actor=""), _body(actor="   "), _body(actor=5), _body(actor="a\x00b"),
        _body(resume_runs="run"), _body(resume_runs=["run", "run"]),
        _body(resume_runs=["bad id"]), _body(resume_runs=[7]),
    ]
    for body in refusals:
        refusal = _refused(lambda body=body: desk.set(body))
        assert (refusal.code, refusal.status, dict(refusal.detail)) == ("contract_invalid", 422, {})
    assert desk.bytes() is None
    status, answer = desk.set()
    stored = json.loads(desk.bytes())
    assert status == 200 and answer == stored
    assert answer["set_at"] == NOW == desk.clock()
    assert UUID.fullmatch(answer["flag_id"]) and answer["flag_id"] == FLAGS[0]
    assert (answer["revision"], answer["consumed"], answer["actor"]) == (1, None, "Вы: Анна")
    assert set(stored) == {"schema_version", "flag_id", "revision", "enabled", "actor", "set_at",
                           "resume_runs", "start_task_queue", "consumed"}      # canonical bytes


def test_a_flag_that_is_off_carries_no_runs_and_no_queue_start_and_the_file_is_unchanged(desk):
    approve(desk.f)
    desk.set()
    before = desk.bytes()
    for changes in ({"resume_runs": ["run"]}, {"start_task_queue": True}):
        off = {"enabled": False, "resume_runs": [], "start_task_queue": False, **changes}
        refusal = _refused(lambda off=off: desk.set(**off))
        assert refusal.code == "contract_invalid"
    assert desk.bytes() == before


# -- the binding ----------------------------------------------------------------------


def test_setting_the_flag_binds_each_run_to_its_current_grant_and_last_control(desk):
    grant, _ = approve(desk.f)
    _, first = desk.set()
    assert first["resume_runs"] == [{
        "run_id": "run", "authorization_id": "grant",
        "authorization_digest": grant.authorization_digest, "last_control_id": None}]
    pause(desk.f, grant)
    _, second = desk.set()
    assert second["resume_runs"][0]["last_control_id"] == "pause"
    assert second["resume_runs"][0]["authorization_digest"] == grant.authorization_digest
    assert second["flag_id"] != first["flag_id"] and second["revision"] == 2


def test_a_run_without_a_current_grant_or_with_an_open_action_is_named_and_nothing_is_written(
        desk):
    refusal = _refused(desk.set)                         # no grant at all
    assert (refusal.code, refusal.status, dict(refusal.detail)) == (
        "contract_invalid", 422, {"run_id": "run"})
    assert "run" in refusal.message
    grant, _ = approve(desk.f)
    propose(desk.f)
    desk.f.runtime.authorize_policy("run", "proposal", grant.authorization_id)   # not executed
    refusal = _refused(desk.set)
    assert dict(refusal.detail) == {"run_id": "run"}
    assert desk.bytes() is None


def test_a_grant_that_is_gone_or_a_run_that_does_not_exist_is_named_like_the_others(desk):
    grant, _ = approve(desk.f)
    unknown = _refused(lambda: desk.set(resume_runs=["run", "elsewhere"]))
    assert dict(unknown.detail) == {"run_id": "elsewhere"}
    desk.f.ticks[0] = "2026-08-11T12:05:00Z"             # the grant lasted 300 seconds
    assert dict(_refused(desk.set).detail) == {"run_id": "run"}
    desk.f.ticks[0] = NOW
    desk.f.policy.control("run", {
        "control_id": "revoke", "authorization_id": grant.authorization_id,
        "authorization_digest": grant.authorization_digest, "action": "revoke",
        "actor": "owner", "expected_control_id": None})
    assert dict(_refused(desk.set).detail) == {"run_id": "run"}
    assert desk.bytes() is None


def test_a_run_that_has_ended_cannot_be_carried_on_even_with_its_grant_standing(tmp_path):
    f = setup(tmp_path, two_steps=True, checker=True)
    flag = AutoContinueStore(tmp_path)
    driver, execution = attach_driver(f)
    try:
        authorize(f)
        wait_terminal(f)
        refusal = _refused(lambda: auto_continue.set_flag(
            flag, f.store, _body(), f.policy.clock, new_flag_id=lambda: FLAGS[0]))
        assert dict(refusal.detail) == {"run_id": "run"}
        assert not flag.path.exists()
    finally:
        driver.stop()
        execution.shutdown()


# -- setting, replacing, removing --------------------------------------------------------


def test_every_flag_that_is_on_is_a_new_flag_and_taking_it_down_keeps_its_id(desk):
    approve(desk.f)
    _, first = desk.set()
    _, again = desk.set()
    assert (first["flag_id"], again["flag_id"]) == FLAGS[:2] and again["revision"] == 2
    off = {"enabled": False, "resume_runs": [], "start_task_queue": False}
    _, removed = desk.set(actor="Вы: Борис", **off)
    assert removed["flag_id"] == again["flag_id"] and removed["revision"] == 3
    assert (removed["enabled"], removed["resume_runs"], removed["start_task_queue"],
            removed["actor"], removed["consumed"]) == (False, [], False, "Вы: Борис", None)
    before = desk.bytes()
    assert desk.set(**off)[1] == removed and desk.bytes() == before     # a repeat is not a write


def test_taking_down_what_was_never_set_writes_no_file(desk):
    off = {"enabled": False, "resume_runs": [], "start_task_queue": False}
    status, answer = desk.set(**off)
    assert status == 200 and answer["revision"] == 0 and answer["flag_id"] is None
    assert desk.bytes() is None


def test_the_door_reads_no_driver_no_policy_and_no_mode_so_it_answers_the_same_in_both_modes():
    source = Path(auto_continue.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                for alias in node.names} | {node.module for node in ast.walk(tree)
                                            if isinstance(node, ast.ImportFrom) and node.module}
    forbidden = {"policy_driver", "policy_service", "PolicyDriver", "PolicyService",
                 "project_claim", "ProjectIdentity", "Launch"}
    assert not (imported & forbidden), imported & forbidden
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not ({"mode", "driver", "_policy"} & attributes)


def test_the_door_writes_when_the_run_has_no_driver_as_in_a_view_process(desk):
    approve(desk.f)
    desk.f.policy.driver = None                            # what a view process has
    assert desk.set()[0] == 200 and desk.bytes() is not None


# -- the record is strict --------------------------------------------------------------

GOOD = {
    "schema_version": 2, "flag_id": FLAGS[0], "revision": 1, "enabled": True, "actor": "Вы: Анна",
    "set_at": NOW, "resume_runs": [], "start_task_queue": False, "consumed": None}


def _corrupt(**changes) -> dict:
    return {**GOOD, **changes}


BAD_RECORDS = {
    "another schema": _corrupt(schema_version=1),
    "schema as text": _corrupt(schema_version="2"),
    "a key too many": {**GOOD, "extra": 1},
    "a key missing": {k: v for k, v in GOOD.items() if k != "revision"},
    "a flag id that is not a uuid": _corrupt(flag_id="flag-1"),
    "revision zero": _corrupt(revision=0),
    "revision as bool": _corrupt(revision=True),
    "enabled as int": _corrupt(enabled=1),
    "a time that is not a time": _corrupt(set_at="yesterday"),
    "a run bound without its digest": _corrupt(resume_runs=[{"run_id": "run"}]),
    "runs on a flag that is off and not consumed": _corrupt(
        enabled=False, resume_runs=[{
            "run_id": "run", "authorization_id": "grant",
            "authorization_digest": "sha256:" + "0" * 64, "last_control_id": None}]),
    "a consumed flag that is still on": _corrupt(consumed={
        "at": NOW, "transition_id": TRANSITION, "activation_nonce": NONCE}),
    "a consumption without a nonce": _corrupt(enabled=False, consumed={
        "at": NOW, "transition_id": TRANSITION}),
}


@pytest.mark.parametrize("name", sorted(BAD_RECORDS))
def test_a_file_that_is_not_a_record_of_this_contract_is_corrupt_and_is_never_read_as_a_flag(
        desk, name):
    desk.flag.path.parent.mkdir(parents=True, exist_ok=True)
    desk.flag.path.write_text(json.dumps(BAD_RECORDS[name]), encoding="utf-8")
    with pytest.raises(auto_continue.CorruptFlag):
        auto_continue.read_flag(desk.flag)
    with pytest.raises(auto_continue.CorruptFlag):
        desk.consume(FLAGS[0], 1)


def test_a_good_hand_written_record_is_read_back_as_it_stands(desk):
    desk.flag.path.parent.mkdir(parents=True, exist_ok=True)
    desk.flag.path.write_text(json.dumps(GOOD), encoding="utf-8")
    assert auto_continue.read_flag(desk.flag) == (200, GOOD)


# -- consuming --------------------------------------------------------------------------


def test_consuming_is_a_conditional_write_on_flag_id_and_revision(desk):
    approve(desk.f)
    _, standing = desk.set()
    before = desk.bytes()
    for flag_id, revision in ((FLAGS[1], 1), (FLAGS[0], 2), (FLAGS[0], 0), ("no", 1)):
        assert desk.consume(flag_id, revision) is None
        assert desk.bytes() == before                     # a stranger's flag is not touched
    consumed = desk.consume(standing["flag_id"], standing["revision"])
    assert consumed is not None and desk.bytes() != before
    assert consumed.as_dict() == {**standing, "revision": 2, "enabled": False, "consumed": {
        "at": LATER, "transition_id": TRANSITION, "activation_nonce": NONCE}}
    assert auto_continue.read_flag(desk.flag) == (200, consumed.as_dict())
    assert desk.consume(standing["flag_id"], standing["revision"]) is None
    assert desk.consume(standing["flag_id"], 2) is None   # already consumed, nothing to consume


def test_a_flag_taken_down_or_replaced_after_the_hub_read_it_is_not_consumed_and_survives(desk):
    approve(desk.f)
    _, read_by_the_hub = desk.set()
    off = {"enabled": False, "resume_runs": [], "start_task_queue": False}
    desk.set(**off)                                         # the owner took it down
    assert desk.consume(read_by_the_hub["flag_id"], read_by_the_hub["revision"]) is None
    _, replacement = desk.set()                             # then set a new one
    before = desk.bytes()
    assert desk.consume(read_by_the_hub["flag_id"], read_by_the_hub["revision"]) is None
    assert desk.bytes() == before                           # the new flag is not overwritten
    assert desk.consume(replacement["flag_id"], replacement["revision"]) is not None


def test_a_consumed_flag_keeps_its_runs_and_queue_start_for_the_pump_and_the_queue(desk):
    approve(desk.f)
    _, standing = desk.set()
    consumed = desk.consume(standing["flag_id"], standing["revision"])
    assert [run.run_id for run in consumed.resume_runs] == ["run"]
    assert consumed.start_task_queue is True and consumed.consumed.transition_id == TRANSITION
    _, read = auto_continue.read_flag(desk.flag)
    assert read["enabled"] is False and read["start_task_queue"] is True
    assert read["consumed"] == {"at": LATER, "transition_id": TRANSITION,
                                "activation_nonce": NONCE}


def test_two_consumers_of_one_flag_never_both_win(desk):
    approve(desk.f)
    _, standing = desk.set()
    barrier, wins = threading.Barrier(4), []

    def consume() -> None:
        barrier.wait()
        wins.append(desk.consume(standing["flag_id"], standing["revision"]))

    threads = [threading.Thread(target=consume) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert sorted(win is not None for win in wins) == [False, False, False, True]


@pytest.mark.parametrize("changes", [
    {"transition_id": "not-a-uuid"}, {"activation_nonce": "XYZ"}, {"activation_nonce": ""}])
def test_a_consumption_that_names_no_transition_or_no_nonce_is_refused_and_writes_nothing(
        desk, changes):
    approve(desk.f)
    _, standing = desk.set()
    before = desk.bytes()
    with pytest.raises(Exception) as caught:
        desk.consume(standing["flag_id"], standing["revision"], **changes)
    assert isinstance(caught.value, ValueError) and desk.bytes() == before
