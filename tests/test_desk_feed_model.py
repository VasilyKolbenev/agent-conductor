"""The rows of a run's journal, from the real module under Node, over real run reads.

`desk-feed-model.js` is values in, values out: it takes one frozen run read and answers the rows
of the feed of spec 5.3, each a fact of a record -- proposed, started, result, verdict, decision,
document (and the checker's typed findings, which are a document) -- with the participant it
belongs to, the step of the plan, and the instant the record states. The reads are not typed
here: `tests/fixtures/desk/feed_reads.json` is what the production `CommandApi` answered for the
project of `tests/desk_progress_seed.py` and for the independent-check rig, and the first test
derives them again and compares, so a server that changed the shape of a read reds here.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from conductor.command.contract_values import _DECISION_ACTIONS
from tests.desk_feed_reads import derive
from tests.desk_node import PANEL, run_js
from tests.desk_progress_seed import BRIEF, PLAN
from tests.test_panel_cascade import strip_comments

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "desk" / "feed_reads.json")
                     .read_text(encoding="utf-8"))
READS = FIXTURE["seeded"]["reads"]
REJECTED = FIXTURE["rejected"]
MODULES = {"feed": "desk-feed-model.js"}
#: The one line per row the tests compare: kind, who, step title, word.
SUMMARY = """(read) => feed.feedRows(read).map((row) => [row.kind,
  row.who.kind === "participant" ? `${row.who.harness}/${row.who.duty}`
    : (row.who.name ?? "person"),
  row.step?.title ?? null, row.word])"""
CLOSED = [
    ["document", "person", None, None],
    ["proposed", "claude-code/perform", "Analyse the brief", None],
    ["started", "claude-code/perform", "Analyse the brief", None],
    ["document", "claude-code/perform", "Analyse the brief", None],
    ["verdict", "claude-code/perform", "Analyse the brief", "verified"],
    ["result", "claude-code/perform", "Analyse the brief", "succeeded"],
    ["decision", "release-owner", "Confirm the plan", "approve"],
    ["proposed", "claude-code/perform", "Do the work", None],
    ["started", "claude-code/perform", "Do the work", None],
    ["verdict", "codex-cli/verify", "Do the work", "verified"],
    ["result", "claude-code/perform", "Do the work", "succeeded"],
    ["decision", "release-owner", "Accept the result", "approve"],
]
#: The kinds of record the feed draws, and the field each one's instant is read from.
INSTANTS = {"action_proposal": "proposed_at", "action_result": "observed_at",
            "decision": "decided_at", "artifact": "created_at", "evidence": "verified_at",
            "correction_feedback": "recorded_at"}


def rows(read: Any) -> list[dict]:
    """The whole rows of a read, as JSON (frozen-ness is held separately)."""
    return run_js("console.log(JSON.stringify(feed.feedRows(d)));", MODULES, read)


def summary(read: Any) -> list[list]:
    return run_js(f"console.log(JSON.stringify(({SUMMARY})(d)));", MODULES, read)


def edited(name: str, edit) -> dict:
    """A copy of one seeded read with one change made to it."""
    read = copy.deepcopy(READS[name])
    edit(read)
    return read


def test_the_frozen_reads_are_what_the_production_server_answers_today():
    assert derive() == {key: value for key, value in FIXTURE.items() if key != "_comment"} \
        | {"_comment": FIXTURE["_comment"]}


def test_a_run_accepted_at_its_final_gate_reads_as_its_twelve_facts_in_journal_order():
    assert summary(READS["run-closed"]) == CLOSED


def _instant(kind: str, record: dict) -> str | None:
    """The instant the feed is to read off one record, written out the long way."""
    if kind == "attempt_event":
        return record["recorded_at"] if record["phase"] == "effect_lease" else None
    if kind == "evidence":
        return record["verified_at"] or record["observed_at"]
    return record[INSTANTS[kind]] if kind in INSTANTS else None


def test_the_instant_of_each_row_is_the_one_its_record_states_and_the_order_is_the_journals():
    wrappers = READS["run-closed"]["records"]
    wanted = [at for at in (_instant(row["record_type"], row["record"]) for row in wrappers)
              if at is not None]
    assert [row["at"] for row in rows(READS["run-closed"])] == wanted

    def later(read):
        read["records"][1]["record"]["created_at"] = "2030-01-01T00:00:00Z"
    moved = edited("run-closed", later)
    assert rows(moved)[0]["at"] == "2030-01-01T00:00:00Z"
    assert summary(moved) == CLOSED, "a record dated later is not moved down the feed"


def test_a_document_carries_its_reference_and_text_and_a_person_has_no_action_as_author():
    found = rows(READS["run-closed"])
    brief, plan = found[0]["doc"], found[3]["doc"]
    assert (brief["ref"], brief["content"], brief["mediaType"]) == (
        "artifact-brief", BRIEF, "text/markdown")
    assert (plan["ref"], plan["content"], plan["tooLarge"]) == ("artifact-plan", PLAN, False)
    assert found[0]["who"] == {"kind": "person", "name": None}
    assert found[3]["who"]["instance"] == "claude-dev" and found[3]["step"]["node_id"] == "analyse"
    assert all(row["doc"] is None for row in found if row["kind"] != "document")


def test_a_decision_names_its_actor_the_gate_it_answered_and_the_reason_a_person_gave():
    decisions = [row for row in rows(READS["run-closed"]) if row["kind"] == "decision"]
    assert [(row["who"], row["step"], row["word"], row["reason"]) for row in decisions] == [
        ({"kind": "person", "name": "release-owner"},
         {"node_id": "confirm-gate", "title": "Confirm the plan"}, "approve",
         "Reviewed the plan."),
        ({"kind": "person", "name": "release-owner"},
         {"node_id": "result-gate", "title": "Accept the result"}, "approve", "Looks right.")]


def test_an_attempt_with_no_result_is_live_and_one_with_a_result_is_not():
    started = [row for row in rows(READS["run-working"]) if row["kind"] == "started"]
    assert [(row["step"]["node_id"], row["live"]) for row in started] == [
        ("analyse", False), ("do", True)]
    assert [row["live"] for row in rows(READS["run-closed"]) if row["kind"] == "started"] == [
        False, False]


def test_a_check_that_did_not_pass_says_so_on_its_result_row_and_owes_its_sentence():
    last = rows(READS["run-waiting"])[-1]
    assert (last["kind"], last["word"], last["needsNote"]) == (
        "result", "verification_failed", True)
    assert not any(row["needsNote"] for row in rows(READS["run-closed"]))


def test_the_typed_findings_of_a_checker_are_one_row_with_the_checker_as_its_author():
    found = summary(REJECTED)
    assert [row[0] for row in found] == [
        "document", "decision", "proposed", "started", "findings", "result"]
    findings = next(row for row in rows(REJECTED) if row["kind"] == "findings")
    assert findings["who"] == {"kind": "participant", "instance": "checker",
                               "harness": "codex-cli", "model": None, "duty": "verify"}
    assert findings["step"]["node_id"] == "do"
    assert findings["findings"] == [{"kind": "defect", "path": "answer.py", "line": 2,
                                     "summary": "answer() must return 1 instead of 2"}]
    assert found[-1][3] == "verification_failed"


def test_every_row_carries_the_same_keys_and_is_frozen_all_the_way_down():
    out = run_js("""
      const frozen = (value) => value === null || typeof value !== "object"
        || (Object.isFrozen(value) && Object.values(value).every(frozen));
      const made = feed.feedRows(d);
      console.log(JSON.stringify({all: frozen(made), list: Object.isFrozen(made),
        keys: [...new Set(made.map((row) => Object.keys(row).sort().join(",")))],
        unique: new Set(made.map((row) => row.key)).size === made.length}));
    """, MODULES, READS["run-closed"])
    assert out["all"] and out["list"] and out["unique"]
    assert out["keys"] == [
        "at,doc,findings,key,kind,live,needsNote,ownCheck,pass,reason,step,who,word"]


def test_the_closed_list_of_row_kinds_is_the_six_facts_and_the_findings_document():
    out = run_js("console.log(JSON.stringify(feed.FEED_KINDS));", MODULES)
    assert out == ["proposed", "started", "result", "verdict", "decision", "document", "findings"]
    kinds = {row[0] for read in (*READS.values(), REJECTED) for row in summary(read)}
    assert kinds <= set(out)


def test_the_words_of_a_decision_are_the_contracts_own_and_no_other():
    out = run_js("console.log(JSON.stringify(feed.DECISION_WORDS));", MODULES)
    assert sorted(out) == sorted(_DECISION_ACTIONS)


@pytest.mark.parametrize("kind", [
    "run_authorization", "adapter_observation", "run_authorization_control"])
def test_a_record_of_a_kind_the_feed_does_not_draw_adds_no_row(kind):
    """The plan, the requests and the ending are in the read already and make no row
    (`CLOSED`); these three are not in it, so each is put in, with every field that could
    tempt a row out of it."""
    tempting = {"instance_id": "claude-dev", "node_id": "do", "action_id": "action-105",
                "outcome": "succeeded", "actor": "someone", "observed_at": "2026-08-19T09:00:00Z",
                "recorded_at": "2026-08-19T09:00:00Z", "authorized_at": "2026-08-19T09:00:00Z",
                "created_at": "2026-08-19T09:00:00Z", "health": "ready"}

    def insert(read):
        extra = {"record_type": kind, "record": dict(tempting)}
        read["records"] = [extra, *read["records"][:6], extra, *read["records"][6:]]
    assert summary(edited("run-closed", insert)) == CLOSED


def test_the_words_of_a_verification_are_the_verdict_and_an_unchecked_claim_is_no_verdict():
    def verdicts(word):
        def edit(read):
            for row in read["records"]:
                if row["record_type"] == "evidence":
                    row["record"]["verification"] = word
        return [(row["kind"], row["word"], row["needsNote"])
                for row in rows(edited("run-closed", edit)) if row["kind"] == "verdict"]
    assert verdicts("verified") == [("verdict", "verified", False)] * 2
    assert verdicts("mismatch") == [("verdict", "mismatch", True)] * 2
    assert verdicts("error") == [("verdict", "error", False)] * 2
    assert verdicts("unavailable") == [("verdict", "unavailable", False)] * 2
    assert verdicts("unverified") == []


def _verdicts(read: Any) -> list[dict]:
    return [row for row in rows(read) if row["kind"] == "verdict"]


def test_a_check_by_the_steps_own_adapter_is_its_performers_and_one_by_a_checker_is_the_checkers():
    """The records give a step's own check no verifier instance, so no duty of verifying: it is
    the performer's, said so in its row. An evidence that names a checker is that checker's."""
    found = _verdicts(READS["run-closed"])
    assert [(row["who"]["instance"], row["who"]["harness"], row["who"]["duty"], row["ownCheck"])
            for row in found] == [("claude-dev", "claude-code", "perform", True),
                                  ("codex-check", "codex-cli", "verify", False)]
    assert [row["step"]["node_id"] for row in found] == ["analyse", "do"]
    assert {row["ownCheck"] for row in rows(READS["run-closed"]) if row["kind"] != "verdict"} == {
        False}


def test_a_step_the_plan_gave_no_verifier_has_no_row_in_the_duty_of_verifying():
    read = READS["run-closed"]
    nodes = {node["node_id"]: node for node in read["graph"]["definition"]["nodes"]}
    assert [name for name, node in nodes.items()
            if node["kind"] == "task" and "verifier_instance_id" not in node] == ["analyse"]
    duties = {row["step"]["node_id"]: row["who"]["duty"] for row in _verdicts(read)}
    assert duties == {"analyse": "perform", "do": "verify"}


def test_an_own_check_of_an_action_no_request_names_is_its_adapters_and_places_no_step():
    def unrequested(read):
        read["records"] = [row for row in read["records"] if row["record_type"] != "action_request"]
    found = _verdicts(edited("run-closed", unrequested))[0]
    assert found["who"] == {"kind": "participant", "instance": None, "harness": "claude-code",
                            "model": None, "duty": "perform"}
    assert (found["ownCheck"], found["step"]) == (True, None)


def test_a_check_that_names_neither_a_checker_nor_the_adapter_that_made_it_is_nobodys():
    def nameless(read):
        for row in read["records"]:
            if row["record_type"] == "evidence":
                row["record"].pop("verifier_instance_id", None)
                row["record"]["verified_by"] = None
    found = _verdicts(edited("run-closed", nameless))
    assert [(row["who"], row["ownCheck"], row["word"]) for row in found] == [
        ({"kind": "unknown"}, False, "verified")] * 2


def test_a_checker_that_is_null_or_empty_is_none_as_an_absent_one_is_and_the_check_is_the_own():
    for value in (None, ""):
        def emptied(read, value=value):
            first = next(row for row in read["records"] if row["record_type"] == "evidence")
            first["record"]["verifier_instance_id"] = value
        found = _verdicts(edited("run-closed", emptied))
        assert [(row["ownCheck"], row["who"]["duty"]) for row in found] == [
            (True, "perform"), (False, "verify")], repr(value)


def test_a_document_is_shown_up_to_49152_bytes_of_its_text_and_not_a_byte_over():
    def text(content):
        def edit(read):
            [row for row in read["records"] if row["record_type"] == "artifact"][0][
                "record"]["content"] = content
        return rows(edited("run-closed", edit))[0]["doc"]
    assert text("x" * 49152)["tooLarge"] is False and len(text("x" * 49152)["content"]) == 49152
    over = text("x" * 49153)
    assert (over["tooLarge"], over["content"]) == (True, None)
    wide = text("я" * 24577)
    assert (wide["tooLarge"], wide["content"]) == (True, None), "bytes count, not characters"
    assert text("я" * 24576)["tooLarge"] is False


def test_a_loop_pass_is_said_on_a_live_row_only_when_the_run_says_the_pass():
    def looped(pass_number):
        def edit(read):
            read["graph"]["definition"]["nodes"].append({
                "node_id": "again", "kind": "loop", "title": "Again", "resources": [],
                "loop": {"bound": 3, "back_to": "do"}})
            read["graph"]["runtime"]["nodes"].append({
                "node_id": "again", "phase": "idle", "outcome": None, "attempt_ids": [],
                "evidence_refs": [], "observed_at": None, "pass": pass_number})
        return [row["pass"] for row in rows(edited("run-working", edit))
                if row["kind"] == "started"]
    assert looped(2) == [None, {"pass": 2, "bound": 3}]
    assert looped(None) == [None, None]
    assert looped(0) == [None, None], "a loop not yet entered has no pass to say"
    assert {row["pass"] for row in rows(READS["run-working"])} == {None}


def test_an_outcome_this_build_has_no_word_for_is_said_unknown_and_never_passed_on():
    def strange(read):
        [row for row in read["records"] if row["record_type"] == "action_result"][-1][
            "record"]["outcome"] = "exploded"
    found = rows(edited("run-closed", strange))
    assert [(row["word"], row["needsNote"]) for row in found if row["kind"] == "result"] == [
        ("succeeded", False), ("unknown", False)]


def test_a_record_that_cannot_be_read_is_skipped_and_nothing_is_thrown_or_made_up():
    def damage(read):
        read["records"] = [
            {"record_type": "decision", "record": None}, {"record_type": "artifact"},
            {"record_type": "action_result", "record": {"action_id": "x"}},
            {"record_type": "action_proposal", "record": {"node_id": "do"}},
            "not a row", None, 7, *read["records"]]
    assert summary(edited("run-closed", damage)) == CLOSED
    assert run_js("console.log(JSON.stringify(["
                  "feed.feedRows(null), feed.feedRows({}), feed.feedRows({records: 5}), "
                  "feed.feedRows({records: []})]));", MODULES) == [[], [], [], []]


def test_a_participant_the_run_never_froze_is_named_by_its_id_and_has_no_harness():
    def unfreeze(read):
        read["config"]["instances"] = []
    first = rows(edited("run-closed", unfreeze))[1]
    assert first["who"] == {"kind": "participant", "instance": "claude-dev", "harness": None,
                            "model": None, "duty": "perform"}


def test_a_row_reads_no_body_of_an_action_and_no_text_of_an_answer():
    """The feed is an index of protocol facts: never `arguments`, a result's `detail`, or a
    stream. The typed findings and the document's own text are the two bodies it may carry."""
    code = strip_comments((PANEL / "desk-feed-model.js").read_text(encoding="utf-8"))
    for word in (r"\.arguments\b", r"\.detail\b", r"\bstdout\b", r"\bstderr\b",
                 r"\btranscript\b", r"\boutput\b"):
        assert not re.search(word, code), word
