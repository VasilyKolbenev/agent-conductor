"""Pin the five frozen ALPHA-1 artifacts the Fable UI lane consumes.

Each document under ``tests/fixtures/alpha1_*.json`` was derived by executing two
real runs through the coordinator path -- never hand-written -- and is re-derived
here on every run. Equality against the frozen bytes is the drift alarm: a
production change that alters a projected field, a durable record order, a
refusal code, a state vocabulary or an SSE frame reds instead of quietly handing
the UI lane a shape the backend no longer produces.

Equality alone would only say "something moved", so each artifact also carries
the relation that gives it meaning -- a projection row withholds every name the
config and contract carry, a state is durable exactly when it adds a record, the
frozen frames are the bytes the production mailbox builds -- and those relations
are asserted against production doors, not against the derivation that wrote the
document.
"""
from __future__ import annotations

import json

import pytest

from conductor import server
from conductor.command.adapters.provider import (
    AVAILABILITY_STATES,
    ProviderConfig,
    ProviderContract,
)
from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.attempts import ATTEMPT_PHASES, OBSERVED_OUTCOMES
from conductor.command.runtime import AttemptState

from tests.alpha1_artifacts import ARTIFACTS, FIXTURES, derive_all, load
from tests.test_command_execution_fanout import WAIT, an_api, confirm, records
from tests.test_command_http_api import RUN_ID


#: The one action a consumer walks: queued before the effect, terminal after it.
STATE_ORDER = ["queued", "leased", "execution_observed", "verifying", "terminal"]
#: What is durable the instant an action is confirmed, before any effect seam.
AT_CONFIRM = ["action_proposal", "action_request"]


@pytest.fixture(scope="module")
def derived(tmp_path_factory):
    """Both real runs, executed once and read by every pin in this module."""
    root = tmp_path_factory.mktemp("alpha1")
    return derive_all(root / "gated", root / "served")


@pytest.mark.parametrize("name", ARTIFACTS)
def test_a_frozen_artifact_still_equals_what_a_real_run_produces(derived, name):
    assert derived[name] == load(name)


def test_the_frozen_artifacts_on_disk_are_exactly_the_five_this_lane_promised():
    assert sorted(path.name for path in FIXTURES.glob("alpha1_*.json")) == sorted(
        f"{name}.json" for name in ARTIFACTS)


# -- artifact 1: the provider availability/controls response shape --


def test_a_projection_row_carries_the_row_fields_and_none_of_the_withheld_names():
    document = load("alpha1_provider_projection")
    row_fields = set(document["row_fields"])
    withheld = set(document["withheld_from_rows"])
    assert withheld and row_fields.isdisjoint(withheld)
    assert [set(row) for row in document["rows"]] == [row_fields] * len(
        document["rows"])
    # Nothing the operator config or the reviewed contract carries is
    # unaccounted for: every such name is either projected or named as withheld.
    carried = set(ProviderConfig._FIELDS) | set(ProviderContract._FIELDS)
    assert carried - row_fields == withheld


def test_the_projected_boolean_agrees_with_the_three_state_availability_beside_it():
    document = load("alpha1_provider_projection")
    assert set(document["availability_vocabulary"]) == set(AVAILABILITY_STATES)
    resolved = document["resolved_availability"]
    assert set(resolved.values()) == set(AVAILABILITY_STATES)
    assert set(resolved) == {row["provider_id"] for row in document["rows"]}
    for row in document["rows"]:
        assert row["available"] is (resolved[row["provider_id"]] == "available")
        assert "availability" not in row


# -- artifact 2: one canonical snapshot per state, honest about durability --


def test_only_a_state_that_adds_a_durable_record_is_marked_durable():
    """Durability is a relation over the journal, never a label on a name."""
    rows = load("alpha1_record_states")["states"]
    assert [row["state"] for row in rows] == STATE_ORDER
    by_state = {row["state"]: row for row in rows}
    queued = by_state["queued"]
    # A queued action is a SECOND action: the queue wrote nothing of its own,
    # so all it has is what its confirmation already recorded.
    assert queued["durable_record_types"] == AT_CONFIRM
    assert queued["durable"] is False
    assert queued["evidence"]["actions_placed_on_the_one_worker"] == 2
    assert len(queued["evidence"]["adapter_execute_arrivals"]) == 1

    seen = list(AT_CONFIRM)
    for name in STATE_ORDER[1:]:
        row = by_state[name]
        assert row["durable_record_types"][:len(seen)] == seen
        added = row["durable_record_types"][len(seen):]
        assert row["durable"] is bool(added)
        seen = row["durable_record_types"]
    assert seen == [
        "action_proposal", "action_request", "attempt_event", "attempt_event",
        "evidence", "action_result"]


def test_every_frozen_record_is_the_record_type_its_snapshot_names():
    rows = load("alpha1_record_states")["states"]
    for row in rows:
        assert [item["record_type"] for item in row["durable_records"]] == (
            row["durable_record_types"])
        for item in row["durable_records"]:
            assert isinstance(item["record"], dict) and item["record"]
    assert {row["state"] for row in rows if not row["durable"]} == {
        "queued", "verifying"}


# -- artifact 3: the refusal and state vocabulary as data --


def test_the_frozen_vocabulary_is_exactly_the_closed_sets_production_holds():
    document = load("alpha1_vocabulary")
    assert document["refusal_codes"] == dict(ERROR_STATUS)
    assert document["attempt_states"] == [state.value for state in AttemptState]
    assert set(document["observed_outcomes"]) == set(OBSERVED_OUTCOMES)
    assert set(document["attempt_event_phases"]) == set(ATTEMPT_PHASES)
    assert set(document["availability_states"]) == set(AVAILABILITY_STATES)
    terminal, pre = set(document["terminal_states"]), set(document["pre_terminal_states"])
    assert terminal.isdisjoint(pre)
    assert terminal | pre == set(document["attempt_states"])
    assert terminal == set(document["receipt_outcomes"]) - {"rejected"}
    assert document["receipt_only_outcomes"] == ["rejected"]


def test_nothing_the_derived_runs_observed_falls_outside_the_frozen_sets():
    document = load("alpha1_vocabulary")
    observed = document["observed_in_the_derived_runs"]
    assert observed["attempt_event_phases"] and observed["refusal_codes"]
    for name, closed in (
            ("attempt_event_phases", "attempt_event_phases"),
            ("observed_outcomes", "observed_outcomes"),
            ("terminal_outcomes", "terminal_states"),
            ("availability_states", "availability_states"),
            ("refusal_codes", "refusal_codes")):
        assert set(observed[name]) <= set(document[closed]), name


def test_a_rejected_report_is_observed_as_rejected_and_recorded_terminal_failed(
        tmp_path):
    """The one vocabulary note that is a claim about the runtime, driven for real."""
    api, store, coordinator, adapters, _tokens, _signals = an_api(tmp_path)
    try:
        adapters[0].outcome = "rejected"
        action_id = confirm(api, instance_id="claude-dev",
                            attempt_id="attempt-001", work_item_id="work-001")
        assert coordinator.wait_idle(WAIT) is True
        observed = [row for row in records(store, "attempt_event")
                    if row.phase == "execution_observed"]
        assert [row.outcome for row in observed] == ["rejected"]
        receipts = records(store, "action_result")
        assert [(row.action_id, row.outcome) for row in receipts] == [
            (action_id, "failed")]
        document = load("alpha1_vocabulary")
        assert "rejected" in document["observed_outcomes"]
        assert "rejected" not in document["attempt_states"]
    finally:
        coordinator.shutdown()


# -- artifact 4: the deterministic backend end-to-end --


def test_the_confirm_was_answered_before_any_terminal_record_existed():
    steps = {row["step"]: row for row in load("alpha1_end_to_end")["steps"]}
    assert list(steps) == [
        "propose", "confirm", "duplicate_confirm", "refused_confirm",
        "authoritative_refresh"]
    confirmed = steps["confirm"]
    assert confirmed["status"] == 201
    assert confirmed["durable_record_types_at_response"] == AT_CONFIRM
    duplicate = steps["duplicate_confirm"]
    assert duplicate["status"] == 200
    assert duplicate["response"]["action_id"] == confirmed["response"]["action_id"]


def test_the_refused_confirm_answers_the_status_its_code_is_registered_with():
    refused = next(row for row in load("alpha1_end_to_end")["steps"]
                   if row["step"] == "refused_confirm")
    code = refused["response"]["error"]["code"]
    assert refused["status"] == ERROR_STATUS[code] >= 400
    assert set(refused["response"]) == {"error"}


def test_the_authoritative_refresh_holds_the_history_the_terminal_snapshot_ends_with():
    refreshed = next(row for row in load("alpha1_end_to_end")["steps"]
                     if row["step"] == "authoritative_refresh")["response"]
    terminal = next(row for row in load("alpha1_record_states")["states"]
                    if row["state"] == "terminal")
    assert refreshed["warnings"] == []
    assert [row["record_type"] for row in refreshed["records"]] == (
        terminal["durable_record_types"])


# -- artifact 5: the identifier-only SSE relation --


def test_a_run_frame_carries_the_run_id_and_nothing_else():
    document = load("alpha1_sse_relation")
    payload = json.loads(document["run_frame"].removeprefix("data: "))
    assert sorted(payload) == document["run_frame_payload_keys"] == ["kind", "run_id"]
    assert payload == {"kind": "run", "run_id": RUN_ID}


def test_the_stream_carried_the_state_frame_and_run_frames_and_no_third_shape():
    document = load("alpha1_sse_relation")
    frames = document["frames_read_in_order"]
    assert frames[0] == document["connect_frame"]
    assert set(frames) == {document["connect_frame"], document["run_frame"]}
    assert frames.count(document["run_frame"]) == len(frames) - 1 >= 1


def test_the_frozen_frames_are_the_bytes_the_production_mailbox_builds():
    document = load("alpha1_sse_relation")
    mailbox = server._Mailbox()
    mailbox.publish_run(RUN_ID)
    assert mailbox.drain() == (document["run_frame"].encode("utf-8"),)
    mailbox.publish_state()
    assert mailbox.drain() == (document["connect_frame"].encode("utf-8"),)
