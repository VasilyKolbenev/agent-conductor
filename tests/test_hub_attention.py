"""The raw projection of a run's wait that the hub carries, equal to the desk's (spec 4.5.6).

`attention.journal` is the last 256 typed rows of a run's journal cut to five keys; the desk builds
the same index from its own read of the run (`journalIndex` in `desk-status.js`) and the two are
held equal here by the one shared fixture lane D1 wrote (`tests/fixtures/desk/journal_index.json`:
the spec names `tests/fixtures/journal_index.json`, but D1's file came first and says it was laid
out for this test, so there is one fixture and not two). `INSTANT_FIELDS` is held equal to the two
JS tables.
`attention_of` turns one run read into the `attention` object of `GET /hub/projects`: the reasons
with a count (never `run_ended`), the gates that need a decision (and so `gate_id` only for a
`gate_decision`), the runtime rows, the journal and the moment the hub saw it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conductor.command.graph_schedule import schedule
from conductor.command.human_situation import CHECKED_REASONS, human_situation
from conductor.hub import attention
from tests.desk_node import PANEL, run_js
from tests.schedule_journal import RUN_ID, Journal, routed_dalio, through_the_body
from tests.test_studio_runs import frozen_pairs

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "desk" / "journal_index.json")
                     .read_text(encoding="utf-8"))
CASES = FIXTURE["cases"]
SEEN = "2026-09-30T10:00:00Z"
KEYS = {"record_type", "instant", "action_id", "node_id", "proposal_id"}


def test_the_instant_table_is_the_studios_and_the_desks_kind_by_kind():
    studio = frozen_pairs(PANEL / "studio-runwords.js", "INSTANT_FIELDS")
    desk = frozen_pairs(PANEL / "desk-status.js", "INSTANT_FIELDS")
    assert dict(attention.INSTANT_FIELDS) == studio == desk
    assert len(studio) == 13


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_the_index_of_each_fixture_case_is_the_fixtures_and_the_one_the_desk_builds(case):
    mine = attention.journal_projection(case["records"])
    assert mine == case["journal"]
    assert run_js("console.log(JSON.stringify(st.journalIndex(d)));",
                  {"st": "desk-status.js"}, case["records"]) == mine


def test_the_index_keeps_the_last_256_rows_in_order_with_five_keys_and_no_payload():
    records = [{"record_type": "action_request",
                "record": {"action_id": f"action-{n}", "node_id": "do",
                           "requested_at": "2026-09-30T09:00:00Z", "secret": "kept out"}}
               for n in range(300)]
    index = attention.journal_projection(records)
    assert [row["action_id"] for row in index] == [f"action-{n}" for n in range(44, 300)]
    assert all(set(row) == KEYS for row in index) and "kept out" not in json.dumps(index)
    assert run_js("console.log(JSON.stringify(st.journalIndex(d)));",
                  {"st": "desk-status.js"}, records) == index


def test_a_row_that_is_not_a_typed_record_is_skipped_and_the_answer_is_always_a_list():
    junk = [None, 3, "row", [], {}, {"record_type": 4, "record": {}},
            {"record_type": "decision"}, {"record_type": "decision", "record": None},
            {"record_type": "decision", "record": {"decided_at": "2026-09-30T09:25:00Z"}},
            {"record_type": "decision", "record": {"decided_at": 7, "node_id": ["x"]}}]
    kept = attention.journal_projection(junk)
    assert [(row["record_type"], row["instant"]) for row in kept] == [
        ("decision", "2026-09-30T09:25:00Z"), ("decision", None)]
    for value in (None, {}, "x", 4, (x for x in ())):
        assert attention.journal_projection(value) == []


def test_a_kind_the_build_does_not_know_is_not_stamped_with_an_instant():
    row = {"record_type": "future_kind", "record": {"created_at": "2026-09-30T09:00:00Z"}}
    assert attention.journal_projection([row]) == [
        {"record_type": "future_kind", "instant": None, "action_id": None, "node_id": None,
         "proposal_id": None}]


# -- one run read -> the attention object ------------------------------------------------------


def _reading(definition, journal) -> dict:
    values = journal.rows()
    return human_situation(definition, values, schedule(definition, values), run_id=RUN_ID,
                           mode="confirm", warnings=(), computed_at="2026-09-30T10:00:00.000Z")


def _detail(situation: dict, records=(), nodes=()) -> dict:
    return {"run": {}, "config": {}, "records": list(records), "warnings": [],
            "graph": {"situation": situation, "runtime": {"nodes": list(nodes)}}, "task": None}


def test_a_reached_confirmation_of_a_real_reading_is_one_reason_with_its_proposal_and_no_gate():
    definition, journal = routed_dalio(), Journal()
    journal.did("goal")
    journal.did("identify")
    journal.propose("diagnose")
    proposal = journal.values[-1].proposal_id
    got = attention.attention_of(_detail(_reading(definition, journal)), SEEN)
    assert got == {"reasons": [{"reason": "confirmation", "count": 1, "sources": [proposal]}],
                   "gates": [], "runtime": [], "journal": [], "observed_at": SEEN,
                   "unreadable": False}


def test_a_gate_that_needs_a_decision_is_a_reason_and_its_gate_id_comes_with_its_node():
    definition, journal = routed_dalio(), Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "request_changes")
    for name in ("identify", "diagnose", "design"):
        journal.did(name)
    reading = _reading(definition, journal)
    gate_id = next(row["gate_id"] for row in reading["gates"] if row["node_id"] == "confirm-gate")
    got = attention.attention_of(_detail(reading), SEEN)
    assert got["reasons"] == [{"reason": "gate_decision", "count": 1, "sources": ["confirm-gate"]}]
    assert got["gates"] == [{"node_id": "confirm-gate", "gate_id": gate_id}]
    assert all(set(gate) == {"node_id", "gate_id"} for gate in got["gates"])


def _situation(counts: dict[str, list[str]], gates=()) -> dict:
    return {"state": "required", "computed_at": SEEN, "gates": list(gates),
            "checked": [{"reason": reason, "count": len(counts.get(reason, [])),
                         "sources": counts.get(reason, [])} for reason in CHECKED_REASONS],
            "unknown_because": [], "unknown_sources": []}


def test_the_five_checked_reasons_are_told_apart_reconcile_included_and_run_ended_is_not_one():
    every = {"gate_decision": ["review"], "confirmation": ["proposal-1"],
             "input_document": ["doc"], "reconcile": ["n1", "n2"], "attempt_bound": ["do"],
             "run_ended": ["terminal-1"]}
    gate = {"node_id": "review", "gate_id": "gate-review", "needs_decision": True}
    got = attention.attention_of(_detail(_situation(every, [gate])), SEEN)
    assert [(row["reason"], row["count"]) for row in got["reasons"]] == [
        ("gate_decision", 1), ("confirmation", 1), ("input_document", 1), ("reconcile", 2),
        ("attempt_bound", 1)]
    assert got["gates"] == [{"node_id": "review", "gate_id": "gate-review"}]
    none = attention.attention_of(_detail(_situation({"run_ended": ["t"]})), SEEN)
    assert none["reasons"] == [] and none["gates"] == [] and none["unreadable"] is False


def test_a_gate_that_is_answered_or_not_reached_is_not_listed_among_the_gates():
    gates = [{"node_id": "a", "gate_id": "gate-a", "needs_decision": False},
             {"node_id": "b", "gate_id": "gate-b", "needs_decision": True}]
    got = attention.attention_of(_detail(_situation({"gate_decision": ["b"]}, gates)), SEEN)
    assert got["gates"] == [{"node_id": "b", "gate_id": "gate-b"}]


def test_the_runtime_rows_are_cut_to_the_node_and_what_opened_it_and_the_journal_is_the_index():
    nodes = [{"node_id": "do", "state": "runnable", "opened_by": ["intake"], "blocked_by": [],
              "answerable": None}, {"node_id": "intake", "opened_by": []}]
    records = [{"record_type": "action_proposal",
                "record": {"proposal_id": "p1", "node_id": "do",
                           "proposed_at": "2026-09-30T09:05:00Z", "arguments": {"x": 1}}}]
    situation = _situation({"confirmation": ["p1"]})
    got = attention.attention_of(_detail(situation, records, nodes), SEEN)
    assert got["runtime"] == [{"node_id": "do", "opened_by": ["intake"]},
                              {"node_id": "intake", "opened_by": []}]
    assert got["journal"] == attention.journal_projection(records)
    assert "arguments" not in json.dumps(got)


def test_a_run_without_a_plan_has_no_runtime_rows_and_still_says_what_it_waits_for():
    detail = _detail(_situation({"input_document": ["doc"]}))
    detail["graph"]["runtime"] = None
    got = attention.attention_of(detail, SEEN)
    assert got["runtime"] == [] and [row["reason"] for row in got["reasons"]] == ["input_document"]


@pytest.mark.parametrize("broken", [
    None, {}, {"graph": None}, {"graph": {}}, {"graph": {"situation": {}}},
    {"graph": {"situation": {"checked": "x", "gates": []}}},
    {"graph": {"situation": {"checked": [{"reason": 1, "count": 1, "sources": []}],
                             "gates": []}}},
    {"graph": {"situation": {"checked": [], "gates": [{"node_id": "a"}]}, "runtime": None}},
    "not a dict"])
def test_a_run_read_that_is_not_the_shape_is_said_unreadable_and_carries_no_reason(broken):
    assert attention.attention_of(broken, SEEN) == attention.unreadable(SEEN) == {
        "reasons": [], "gates": [], "runtime": [], "journal": [], "observed_at": SEEN,
        "unreadable": True}
