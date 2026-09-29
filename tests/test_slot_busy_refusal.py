"""The refusal `slot_busy` and the doors that say it (spec 4.4.1, 4.4.7, 11.1).

Authorizing a run or resuming one while another run holds the project's slot was
`contract_invalid`, which a desk cannot tell from a fault in the terms and so could only offer to
try the same thing again. It is now `409 slot_busy`, and the detail names the run that holds the
slot. The second half is the rule of 11.1: a new code goes into EVERY place of the vocabulary in
one commit, and this file is the "test of the code" that names each place readable from Python
or from a file.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conductor.command import policy_driver
from conductor.command.api_contracts import (
    ERROR_STATUS, _FIXED_MESSAGES, _REFUSAL_BUILD, ApiRefusal, refusal_from_exception)
from conductor.command.api_refusals import _REVIEWED_FACTS
from conductor.command.contract_values import ContractError
from conductor.command.http_api import CommandApi
from conductor.command.http_transport import CommandSession
from tests.alpha1_live_extensions import REFUSALS
from tests.test_cockpit_command_api_freeze import EXPECTED_ERRORS
from tests.test_command_http_api import PORT, TOKEN, post
from tests.test_policy_driver_slot import run  # noqa: F401 - a fixture
from tests.test_policy_driver_slot import in_flight, journal
from tests.test_policy_runtime import Activation, approve, pause, setup

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "src" / "conductor" / "panel"
CODE = "slot_busy"
HOLDER = "run-holder"


class TakenSlot(Activation):
    """A driver whose slot another run already holds."""

    def __init__(self, holder=HOLDER):
        super().__init__()
        self.holder = holder

    def hold_activation(self, run_id):
        raise policy_driver.SlotBusy(self.holder)


def door(f):
    api = CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
                     budget=f.policy.budget, clock=f.policy.clock, ids=f.runtime._ids,
                     publish_run=lambda run_id: None)
    api._policy = f.policy
    return api


def authorize_body(f):
    preview = f.policy.preview("run", {
        "node_limits": [{"node_id": "do", "timeout_seconds": 30, "max_attempts": 2}],
        "max_actions": 2, "max_action_seconds": 30, "max_total_task_seconds": 60,
        "duration_seconds": 300})
    return {"authorization_id": "second", "preview_digest": preview["preview_digest"],
            "authorized_by": "owner", "terms": preview["terms"], "supersedes": None}


def answer_code(answer):
    return answer.status, answer.payload["error"]["code"], answer.payload["error"]["detail"]


# --- the type, and what raises it -----------------------------------------------------------------


def test_slot_busy_is_a_contract_error_that_carries_the_holder_and_is_not_new_work_held():
    busy = policy_driver.SlotBusy(HOLDER)
    assert isinstance(busy, ContractError) and busy.holder == HOLDER
    assert not isinstance(busy, policy_driver.NewWorkHeld)
    assert not isinstance(policy_driver.NewWorkHeld("x"), policy_driver.SlotBusy)


def test_a_slot_another_run_holds_refuses_activation_and_names_the_holder(run):  # noqa: F811
    in_flight(run)
    before = journal(run.f)
    with pytest.raises(policy_driver.SlotBusy) as refused:
        run.driver.hold_activation("another-run")
    assert refused.value.holder == "run"
    run.driver.hold_activation("run")  # the holder itself is not refused
    assert journal(run.f) == before


def test_a_driver_that_is_not_running_refuses_with_a_plain_contract_error_and_not_slot_busy(
        tmp_path):
    f = setup(tmp_path)
    driver = policy_driver.PolicyDriver(f.policy, f.runtime, None, clock=f.policy.clock,
                                        ids=f.runtime._ids)
    with pytest.raises(ContractError, match="not running") as refused:
        driver.hold_activation("run")
    assert not isinstance(refused.value, policy_driver.SlotBusy)


# --- the doors ------------------------------------------------------------------------------------


def test_authorize_at_a_taken_slot_is_409_slot_busy_naming_the_holder(tmp_path):
    f = setup(tmp_path)
    body = authorize_body(f)
    f.policy.driver = TakenSlot()
    before = f.store.read("run").records
    refused = post(door(f), "/command/runs/run/automation/authorize", body)
    assert answer_code(refused) == (409, CODE, {"run_id": HOLDER})
    assert refused.payload["error"]["message"] == (
        f"another bounded run '{HOLDER}' holds this project's slot")
    assert f.store.read("run").records == before


def test_resume_at_a_taken_slot_is_409_slot_busy_naming_the_holder(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    pause(f, grant)
    f.policy.driver = TakenSlot()
    resume = {"control_id": "resume", "authorization_id": grant.authorization_id,
              "authorization_digest": grant.authorization_digest, "action": "resume",
              "actor": "owner", "expected_control_id": "pause"}
    refused = post(door(f), "/command/runs/run/automation/control", resume)
    assert answer_code(refused) == (409, CODE, {"run_id": HOLDER})


def test_a_holder_that_is_not_a_safe_id_is_refused_as_slot_busy_without_a_detail():
    refusal = refusal_from_exception(policy_driver.SlotBusy("not a safe id!"))
    assert (refusal.status, refusal.code, dict(refusal.detail)) == (409, CODE, {})
    assert refusal.message == _FIXED_MESSAGES[CODE]


@pytest.mark.parametrize("error", [policy_driver.NewWorkHeld("held"), ContractError("other")])
def test_the_other_refusals_of_hold_activation_stay_contract_invalid(error):
    refusal = refusal_from_exception(error)
    assert (refusal.status, refusal.code) == (422, "contract_invalid")


def test_the_reviewed_fact_of_the_code_is_its_holder_and_no_other_shape_passes():
    refusal = ApiRefusal.slot_busy(HOLDER)
    assert dict(refusal.detail) == {"run_id": HOLDER}
    assert refusal.message == f"another bounded run '{HOLDER}' holds this project's slot"
    with pytest.raises(ValueError):
        ApiRefusal.slot_busy("not a safe id!")
    with pytest.raises(ValueError):
        ApiRefusal(_REFUSAL_BUILD, CODE, "some other words", {"run_id": HOLDER})


# --- 11.1: the code stands in every place of the vocabulary ---------------------------------------


def test_slot_busy_stands_in_every_place_of_the_command_vocabulary_that_python_can_read():
    assert ERROR_STATUS[CODE] == 409                    # place 1
    assert _FIXED_MESSAGES[CODE].strip()                # place 2
    assert any(row[0] == CODE and row[1] == ("run_id",)  # place 3: it carries a detail
               for row in _REVIEWED_FACTS)
    assert EXPECTED_ERRORS[CODE] == (409, "concurrency")  # place 5
    assert REFUSALS[CODE] == 409                        # place 6


def test_slot_busy_stands_in_the_canon_the_labels_and_both_languages_of_the_notice():
    canon = (REPO / "docs" / "specs" / "2026-08-13-cockpit-command-api.md").read_text(
        encoding="utf-8")
    assert re.search(rf'"code": "{CODE}",\s+"status": 409,\s+"source": "concurrency"', canon)  # 4
    labels = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    assert re.search(rf"^  {CODE}: ", labels, re.MULTILINE)                              # 7
    notice = (PANEL / "studio-notice-copy.js").read_text(encoding="utf-8")
    found = re.search(rf'"error\.{CODE}": \["([^"]+)", "([^"]+)"\]', notice)              # 8
    assert found and all(found.groups()) and found.group(1) != found.group(2)
