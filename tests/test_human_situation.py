"""Present needs, durable ambiguity and historical gates, before application.

These pure witnesses use real contract values and the existing schedule/lap
journal. They do not claim a live process, grant or native HTTP verification.
"""
from dataclasses import replace
import ast
from pathlib import Path

import pytest

from conductor.command.attempts import AttemptEvent, action_request_digest
from conductor.command.contracts import ContractError
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.graph_schedule import schedule
from conductor.command.human_situation import human_situation, CHECKED_REASONS, UNKNOWN_REASONS
from conductor.command.run_terminal import RunTerminal
from tests.schedule_journal import Journal, NOW, RUN_ID, routed_dalio, through_the_body

READ_AT = "2026-09-21T15:00:00.123Z"


def plan(*nodes, edges=()):
    return GraphDefinition(graph_id="human-plan", run_id=RUN_ID, created_at=NOW,
                           nodes=nodes, edges=edges)


def task(name, **changes):
    return GraphNode(node_id=name, title=name, kind="task", instance_id="solo",
                     capability="review", **changes)


def gate(name):
    return GraphNode(node_id=name, title=name, kind="gate", gate_id="gate-" + name)


def view(definition, journal=None, *, mode="confirm", warnings=(), at=READ_AT):
    values = () if journal is None else journal.rows()
    return human_situation(definition, values,
        None if definition is None else schedule(definition, values), run_id=RUN_ID,
        mode=mode, warnings=warnings, computed_at=at)


def checked(reading, reason):
    return next(row for row in reading["checked"] if row["reason"] == reason)


def gate_row(reading, name):
    return next(row for row in reading["gates"] if row["node_id"] == name)


def lease(journal, node):
    action_id = journal.request(node)
    request = journal.values[-1]
    journal.values.append(AttemptEvent(
        event_id="lease-" + action_id, run_id=RUN_ID, action_id=action_id,
        attempt_id=request.attempt_id, instance_id=request.instance_id,
        adapter_id="claude-code", phase="effect_lease", recorded_at=NOW,
        request_digest=action_request_digest(request), recovery_ref="owned", outcome=None,
        exit_code=None, schema_version=2))
    return action_id


def ended(journal, definition):
    computed = schedule(definition, journal.rows())
    assert computed.run_state != "open", "ending witness must really have a terminal plan"
    journal.values.append(RunTerminal(terminal_id="ended", run_id=RUN_ID,
        graph_id=definition.graph_id, state=computed.run_state,
        settled_nodes=computed.settled, unreachable_nodes=computed.unreachable, recorded_at=NOW))


def test_h1_reopened_gate_needs_new_answer_but_current_lap_correction_does_not():
    definition, journal = routed_dalio(), Journal()
    journal.did("goal")
    through_the_body(journal)
    current = gate_row(view(definition, journal), "confirm-gate")
    assert current["answerable"] == "supersede"
    assert current["needs_decision"] is False
    assert current["standing_belongs_to_current_lap"] is True
    standing = current["standing_receipt"]
    journal.decide("gate-result", "request_changes")
    for name in ("identify", "diagnose", "design"):
        journal.did(name)
    reading = view(definition, journal)
    reopened = gate_row(reading, "confirm-gate")
    assert reading["state"] == "required"
    assert reopened["arrived"] and reopened["needs_decision"]
    assert reopened["standing_receipt"] == standing
    assert reopened["standing_belongs_to_current_lap"] is False
    assert reopened["lap"]["required_pass"] == 2
    assert checked(reading, "gate_decision")["sources"] == ["confirm-gate"]


def test_h2_pending_gate_is_not_required_while_a_reached_proposal_is():
    definition, journal = routed_dalio(), Journal()
    pending = view(definition, journal)
    assert pending["state"] == "not_required"
    assert gate_row(pending, "confirm-gate")["why_not"] == "road_not_open"
    journal.did("goal")
    journal.did("identify")
    journal.propose("diagnose")
    reading = view(definition, journal)
    assert reading["state"] == "required"
    assert checked(reading, "confirmation")["sources"] == [journal.values[-1].proposal_id]
    assert checked(reading, "gate_decision")["count"] == 0


def test_h2_documents_only_count_after_the_road_opens_and_never_after_halt():
    document = task("document", arguments={"target_artifact_refs": ["brief"]},
                    missing_artifact_policy="block")
    definition = plan(task("before"), document,
                      edges=(GraphEdge(from_node="before", to_node="document"),))
    journal = Journal()
    assert checked(view(definition, journal), "input_document")["count"] == 0
    journal.did("before")
    assert checked(view(definition, journal), "input_document")["sources"] == ["document"]
    halted = plan(task("before", failure_policy="halt_run"), document, edges=definition.edges)
    stopped = Journal()
    stopped.did("before", "failed")
    assert checked(view(halted, stopped), "input_document")["count"] == 0


def test_h3_closed_road_and_dead_predecessor_are_not_a_gate_wait():
    definition = plan(gate("choice"), gate("branch"), gate("beyond"), edges=(
        GraphEdge(from_node="choice", to_node="branch", condition="on_rejected"),
        GraphEdge(from_node="branch", to_node="beyond")))
    journal = Journal()
    journal.decide("gate-choice", "approve")
    reading = view(definition, journal)
    assert reading["state"] == "not_required"
    for name in ("branch", "beyond"):
        row = gate_row(reading, name)
        assert row["needs_decision"] is False and row["arrived"] is False
        assert row["why_not"] == "branch_closed"


def test_h4_halt_does_not_erase_an_arrived_gate_while_another_attempt_holds_run_open():
    definition = plan(task("fails", failure_policy="halt_run"), task("other"), gate("answer"))
    journal = Journal()
    journal.did("fails", "failed")
    lease(journal, "other")
    computed = schedule(definition, journal.rows())
    assert computed.run_state == "open"
    assert computed.state_of("answer") == "blocked"
    reading = view(definition, journal)
    assert reading["state"] == "required"
    assert gate_row(reading, "answer")["needs_decision"] is True


def test_h4_recorded_terminal_suppresses_gate_and_attempt_bound_needs():
    definition = plan(task("spent", attempt_bound=1), gate("answer"))
    journal = Journal()
    journal.did("spent", "unknown")
    # Gate is reached, so the plan remains open; a real halt makes it terminal.
    definition = replace(definition, nodes=(*definition.nodes, task("fails", failure_policy="halt_run")))
    journal.did("fails", "failed")
    before = view(definition, journal)
    assert checked(before, "gate_decision")["count"] == 1
    assert checked(before, "attempt_bound")["sources"] == ["spent"]
    ended(journal, definition)
    after = view(definition, journal)
    assert after["state"] == "not_required"
    assert all(row["count"] == 0 for row in after["checked"] if row["reason"] != "run_ended")
    assert checked(after, "run_ended")["sources"] == ["ended"]
    assert gate_row(after, "answer")["answerable"] == "none"


@pytest.mark.parametrize("record_ending", [False, True])
def test_h5_contradictory_receipts_remain_unknown_even_when_an_ending_stands(record_ending):
    definition, journal = plan(gate("answer")), Journal()
    journal.decide("gate-answer", "approve")
    if record_ending:
        ended(journal, definition)
    # Pure diagnostic guard: a contradictory historical value is not a write authorization.
    journal.decide("gate-answer", "reject", supersede=False)
    reading = view(definition, journal)
    assert reading["state"] == "unknown"
    assert reading["unknown_because"] == ["contradictory_gate_receipts"]
    assert gate_row(reading, "answer")["standing_receipt"] is None
    assert gate_row(reading, "answer")["needs_decision"] is False


def test_h6_read_instant_is_injected_and_warning_prose_never_reaches_the_value():
    journal = Journal()
    first = view(None, journal, warnings=("private C:/account/secret",))
    later = view(None, journal, warnings=("private C:/account/secret",), at="2099-01-01T00:00:00Z")
    assert first["computed_at"] == READ_AT and later["computed_at"] != READ_AT
    assert {k: v for k, v in first.items() if k != "computed_at"} == {
        k: v for k, v in later.items() if k != "computed_at"}
    assert first["state"] == "unknown" and "private" not in repr(first)
    assert first["unknown_because"] == ["replay_warnings"]
    with pytest.raises(ContractError):
        view(None, at="yesterday")


def test_h7_not_required_always_names_every_checked_reason_and_positive_controls_work():
    definition, journal = routed_dalio(), Journal()
    empty = view(None)
    assert empty["state"] == "not_required"
    assert tuple(row["reason"] for row in empty["checked"]) == CHECKED_REASONS
    assert tuple(row["reason"] for row in empty["unknown_sources"]) == UNKNOWN_REASONS
    journal.did("goal")
    through_the_body(journal)
    assert gate_row(view(definition, journal), "result-gate")["needs_decision"] is True
    journal.decide("gate-result", "approve")
    finished = view(definition, journal)
    assert finished["state"] == "not_required"
    assert len(finished["checked"]) == 6 and finished["unknown_because"] == []


def test_request_only_bytes_are_unknown_on_every_fresh_read_not_a_reconcile_instruction():
    definition, journal = plan(task("do")), Journal()
    action = journal.request("do")
    journal.propose("do")  # runtime phase would now misleadingly say proposed.
    first = view(definition, journal)
    copied = Journal()
    copied.values = [type(value).from_dict(value.as_dict()) for value in journal.values]
    assert view(definition, copied) == first
    assert first["state"] == "unknown"
    assert checked(first, "confirmation")["count"] == 0
    assert checked(first, "reconcile") == {"reason": "reconcile", "count": 0, "sources": []}
    source = next(row for row in first["unknown_sources"] if row["reason"] == "unobserved_request")
    assert source["sources"] == [action] and source["count"] == 1


def test_a_running_request_with_reproposal_does_not_become_confirmation_or_reconcile():
    definition, journal = plan(task("do")), Journal()
    lease(journal, "do")
    journal.propose("do")
    reading = view(definition, journal)
    assert reading["state"] == "not_required"
    assert checked(reading, "confirmation")["count"] == checked(reading, "reconcile")["count"] == 0


@pytest.mark.parametrize("finished", [False, True])
def test_an_unplanned_claimed_attempt_does_not_hide_an_independent_confirmation(finished):
    journal = Journal()
    lease(journal, None)
    request = journal.values[0]
    if finished:
        journal.result(request.action_id)
    journal.propose(None, attempt=request.attempt_id)
    assert checked(view(None, journal), "confirmation")["count"] == 0
    journal.values[-1] = replace(journal.values[-1], instance_id="other-instance", preview_digest="")
    assert checked(view(None, journal), "confirmation")["count"] == 0
    journal.propose(None, attempt="independent-attempt")
    journal.values[-1] = replace(journal.values[-1], instance_id="other-instance", preview_digest="")
    reading = view(None, journal)
    assert reading["state"] == "required"
    assert checked(reading, "confirmation")["sources"] == [journal.values[-1].proposal_id]


def test_closed_and_spent_nodes_do_not_revive_old_confirmation_proposals():
    definition = plan(gate("choice"), task("closed"), task("spent", attempt_bound=1), edges=(
        GraphEdge(from_node="choice", to_node="closed", condition="on_rejected"),))
    journal = Journal()
    journal.propose("closed")
    journal.decide("gate-choice", "approve")
    journal.did("spent", "unknown")
    journal.propose("spent")
    reading = view(definition, journal)
    assert checked(reading, "confirmation")["count"] == 0
    assert checked(reading, "attempt_bound")["sources"] == ["spent"]


@pytest.mark.parametrize("mode,expected", [("confirm", 1), ("propose", 1), ("observe", 0), ("policy", 0)])
def test_unplanned_proposal_has_its_own_confirm_fact_and_mode_is_not_inferred(mode, expected):
    journal = Journal()
    journal.propose(None)
    reading = view(None, journal, mode=mode)
    assert checked(reading, "confirmation")["count"] == expected
    assert reading["gates"] == []


def test_human_situation_does_not_import_runtime_reconcile_store_or_coordinator():
    import conductor.command.human_situation as module
    syntax = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(syntax) if isinstance(node, ast.ImportFrom)}
    assert not imported & {"runtime", "reconcile", "run_store", "coordinator"}
