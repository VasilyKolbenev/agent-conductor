"""The word of a task's row: a case for each rule of spec 5.2.1, the closed key set, the copy.

`desk-status.js` is pure, so these run the real module under Node: the fields go in as the
routes spell them and the key and its parameters come back. The rules are read top to bottom
and the first that fits decides, so each case is built to reach ONE rule and the ordering
cases put two rules on the same input and say which wins.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.desk_node import PANEL, run_js
from tests.test_desk_time import clock_reads
from tests.test_graph_source import _code

MODULES = {"st": "desk-status.js", "copy": "desk-status-copy.js", "i18n": "studio-i18n.js",
           "words": "studio-runwords.js"}
#: The journal projection lane D1 keeps for both sides (see the fixture's own `about`).
JOURNAL = json.loads((Path(__file__).parent / "fixtures" / "desk" / "journal_index.json")
                     .read_text(encoding="utf-8"))
TASK = {"task_id": "task-a", "title": "A", "unreadable": False}


def a_run(**changes) -> dict:
    """A newest run's row as `GET /command/runs` spells it, at rest."""
    row = {"run_id": "run-1", "unreadable": False, "human_state": "not_required",
           "open_actions": 0, "last_outcome": None, "task_id": "task-a"}
    return {**row, **changes}


def automation(state: str, reason: str = "none") -> dict:
    return {"state": state, "reason_code": reason, "expires_at": None}


def entry(state: str, reason: str | None = None, position: int = 1) -> dict:
    return {"run_id": "run-1", "state": state, "reason_code": reason, "position": position}


def status(key: str, **params: str) -> dict:
    return {"key": key, "params": params}


#: name -> (input, the answer). One or two per rule, then the ordering cases.
CASES = {
    "rule 1: an unreadable task": (
        {"task": {**TASK, "unreadable": True}, "run": a_run()}, status("task_unreadable")),
    "rule 2: no run at all": ({"task": TASK, "run": None}, status("not_started")),
    "rule 3: an unreadable run": (
        {"task": TASK, "run": a_run(unreadable=True)}, status("run_unreadable")),
    "rule 4: a human is required": (
        {"task": TASK, "run": a_run(human_state="required")}, status("waiting_you")),
    "rule 5: a queue record wants confirmation": (
        {"task": TASK, "run": a_run(), "entry": entry("confirmation_required")},
        status("queue_confirmation")),
    "rule 6: a queue record is blocked": (
        {"task": TASK, "run": a_run(), "entry": entry("blocked")}, status("queue_blocked")),
    "rule 7: a queue record is preauthorized, third in line": (
        {"task": TASK, "run": a_run(), "entry": entry("preauthorized", "behind", 3)},
        status("queued", position="3")),
    "rule 7: a preauthorized record of a project that is not active": (
        {"task": TASK, "run": a_run(),
         "entry": entry("preauthorized", "project_not_active", 1)}, status("queued_inactive")),
    "rule 8: the run's state is unknown": (
        {"task": TASK, "run": a_run(human_state="unknown")}, status("state_unknown")),
    "rule 9: an action is open": (
        {"task": TASK, "run": a_run(open_actions=2)}, status("running")),
    "rule 10: a checkpoint of a project that is not active": (
        {"task": TASK, "run": a_run(),
         "automation": automation("restart_required", "project_not_active")},
        status("checkpoint_inactive")),
    "rule 11: a checkpoint that needs an explicit resume": (
        {"task": TASK, "run": a_run(),
         "automation": automation("restart_required", "explicit_resume_required")},
        status("checkpoint")),
    "rule 12: a checkpoint with no owner": (
        {"task": TASK, "run": a_run(),
         "automation": automation("restart_required", "owner_required")},
        status("owner_missing")),
    "rule 13: stalled, and the reason stays a parameter": (
        {"task": TASK, "run": a_run(), "automation": automation("stalled", "seed_blocked")},
        status("stalled", reason_code="seed_blocked")),
    "rule 13: stalled with another reason": (
        {"task": TASK, "run": a_run(), "automation": automation("stalled", "plan_stalled")},
        status("stalled", reason_code="plan_stalled")),
    "rule 14: the grant expired": (
        {"task": TASK, "run": a_run(), "automation": automation("expired", "expired")},
        status("expired")),
    "rule 15: paused": (
        {"task": TASK, "run": a_run(), "automation": automation("paused", "paused")},
        status("paused")),
    "rule 16: revoked": (
        {"task": TASK, "run": a_run(), "automation": automation("revoked", "revoked")},
        status("revoked")),
    "rule 17: automation running": (
        {"task": TASK, "run": a_run(), "automation": automation("running", "action_in_flight")},
        status("running")),
    "rule 17: automation waiting": (
        {"task": TASK, "run": a_run(), "automation": automation("waiting", "plan_waiting")},
        status("running")),
    "rule 17: automation ready": (
        {"task": TASK, "run": a_run(), "automation": automation("ready", "ready")},
        status("running")),
    "rule 18: succeeded": (
        {"task": TASK, "run": a_run(last_outcome="succeeded")}, status("outcome_succeeded")),
    "rule 18: verification failed": (
        {"task": TASK, "run": a_run(last_outcome="verification_failed")},
        status("outcome_verification_failed")),
    "rule 18: failed": (
        {"task": TASK, "run": a_run(last_outcome="failed")}, status("outcome_failed")),
    "rule 18: unknown": (
        {"task": TASK, "run": a_run(last_outcome="unknown")}, status("outcome_unknown")),
    "rule 18: rejected": (
        {"task": TASK, "run": a_run(last_outcome="rejected")}, status("outcome_rejected")),
    "rule 18: cancelled": (
        {"task": TASK, "run": a_run(last_outcome="cancelled")}, status("outcome_cancelled")),
    "rule 19: a plan that ended with no outcome": (
        {"task": TASK, "run": a_run(), "automation": automation("complete", "plan_ended")},
        status("ended")),
    "rule 20: nobody has authorized the run and no record queues it": (
        {"task": TASK, "run": a_run(),
         "automation": automation("unconfigured", "authorization_required")},
        status("not_started")),
    "rule 21: nothing else fits": (
        {"task": TASK, "run": a_run(),
         "automation": automation("restart_required", "some_new_reason")},
        status("no_outcome")),
    # -- ordering: two rules on one input, and which wins ---------------------------
    "a human decision beats a queue record and an outcome": (
        {"task": TASK, "run": a_run(human_state="required", last_outcome="succeeded"),
         "entry": entry("blocked")}, status("waiting_you")),
    "a queue record beats the run's own state": (
        {"task": TASK, "run": a_run(human_state="unknown", open_actions=1),
         "entry": entry("confirmation_required")}, status("queue_confirmation")),
    "an unknown state beats an open action": (
        {"task": TASK, "run": a_run(human_state="unknown", open_actions=1)},
        status("state_unknown")),
    "an open action beats the automation": (
        {"task": TASK, "run": a_run(open_actions=1),
         "automation": automation("paused", "paused")}, status("running")),
    "the automation beats the last outcome": (
        {"task": TASK, "run": a_run(last_outcome="succeeded"),
         "automation": automation("paused", "paused")}, status("paused")),
    "the last outcome beats a plan that ended": (
        {"task": TASK, "run": a_run(last_outcome="failed"),
         "automation": automation("complete", "plan_ended")}, status("outcome_failed")),
    "a queue record stops an unconfigured run reading as not started": (
        {"task": TASK, "run": a_run(),
         "automation": automation("unconfigured", "authorization_required"),
         "entry": entry("preauthorized", "behind", 2)}, status("queued", position="2")),
    # -- automation not read: rules 10-17, 19 and 20 are skipped ---------------------
    "unread automation and no outcome is no result, never not started": (
        {"task": TASK, "run": a_run(), "automation": None}, status("no_outcome")),
    "unread automation still shows the outcome": (
        {"task": TASK, "run": a_run(last_outcome="failed"), "automation": None},
        status("outcome_failed")),
    "unread automation shows an open action": (
        {"task": TASK, "run": a_run(open_actions=1), "automation": None}, status("running")),
    "an outcome this build has no word for reads as unknown, never as no result": (
        {"task": TASK, "run": a_run(last_outcome="brand_new_outcome")},
        status("state_unknown")),
}
#: The keys of spec 5.2.1, written out here by hand: the module's own list is held to it.
SPEC_KEYS = (
    "task_unreadable", "not_started", "run_unreadable", "waiting_you", "queue_confirmation",
    "queue_blocked", "queued", "queued_inactive", "state_unknown", "running",
    "checkpoint_inactive", "checkpoint", "owner_missing", "stalled", "expired", "paused",
    "revoked", "outcome_succeeded", "outcome_verification_failed", "outcome_failed",
    "outcome_unknown", "outcome_rejected", "outcome_cancelled", "ended", "no_outcome")
#: The Russian words spec 5.2.1 gives for its keys, verbatim.
SPEC_RUSSIAN = {
    "task_unreadable": "Запись не читается", "not_started": "Не запущена",
    "run_unreadable": "Запись не читается", "waiting_you": "Ждёт вашего решения",
    "queue_confirmation": "Ждёт вашего подтверждения",
    "queue_blocked": "В очереди · не может начаться",
    "queued": "В очереди · {position}-я",
    "queued_inactive": "В очереди · начнётся после активации",
    "state_unknown": "Состояние неизвестно", "running": "Идёт",
    "checkpoint_inactive": "На контрольной точке · запуск — у активного проекта",
    "checkpoint": "На контрольной точке · нужно продолжить",
    "owner_missing": "Нет владельца проекта", "stalled": "Запуск остановился",
    "expired": "Разрешение истекло", "paused": "На паузе", "revoked": "Разрешение отозвано",
    "outcome_succeeded": "Успешно", "outcome_verification_failed": "Проверка не пройдена",
    "outcome_failed": "Ошибка", "outcome_unknown": "Исход неизвестен",
    "outcome_rejected": "Отклонено", "outcome_cancelled": "Отменено",
    "ended": "Завершён без результата", "no_outcome": "Результата пока нет"}
#: The machine words that never reach the screen (spec 5.2).
RAW_TOKENS = re.compile(r"\b(?:verification_failed|policy|created|ready|empty)\b", re.I)


@pytest.fixture(scope="module")
def answers() -> list[dict]:
    """Every case answered by the real module in one Node run, in table order."""
    return run_js("console.log(JSON.stringify(d.map((input) => st.taskStatus(input))));",
                  MODULES, [case for case, _ in CASES.values()])


@pytest.mark.parametrize("index,name", list(enumerate(CASES)), ids=list(CASES))
def test_each_case_gets_the_key_and_the_parameters_its_rule_gives(answers, index, name):
    assert answers[index] == CASES[name][1]


def test_the_cases_reach_every_key_and_answer_no_key_outside_the_closed_list(answers):
    reached = {answer["key"] for answer in answers}
    assert reached == set(SPEC_KEYS), sorted(set(SPEC_KEYS) ^ reached)


def test_the_module_exports_the_closed_key_list_and_its_functions_and_no_more():
    out = run_js("console.log(JSON.stringify({names: Object.keys(st).sort(), "
                 "keys: st.STATUS_KEYS, frozen: Object.isFrozen(st.STATUS_KEYS)}));", MODULES)
    assert out["names"] == ["STATUS_KEYS", "journalIndex", "taskStatus", "waitingSince"]
    assert out["keys"] == list(SPEC_KEYS) and out["frozen"] is True


def test_task_status_reads_its_input_and_changes_nothing_of_it():
    out = run_js("""
      const deep = (value) => { Object.values(value ?? {}).forEach(
        (item) => typeof item === "object" && deep(item)); return Object.freeze(value); };
      const answers = d.map((input) => st.taskStatus(deep(structuredClone(input))));
      console.log(JSON.stringify(answers.map((answer) => Object.isFrozen(answer))));
    """, MODULES, [case for case, _ in CASES.values()])
    assert all(out)


def test_every_key_has_one_string_in_each_language_and_the_copy_holds_no_other():
    out = run_js("""
      const rows = Object.entries(i18n.MESSAGES).filter(([key]) => key.startsWith("desk_status."));
      console.log(JSON.stringify({rows: rows.map(([key, row]) => [key, row.en, row.ru]),
        whole: i18n.validateMessages(Object.fromEntries(rows)),
        copy: Object.keys(copy.DESK_STATUS_COPY)}));
    """, MODULES)
    keys = [row[0].removeprefix("desk_status.") for row in out["rows"]]
    assert sorted(keys) == sorted(SPEC_KEYS)
    assert out["whole"] is True and sorted(out["copy"]) == sorted(
        f"desk_status.{key}" for key in SPEC_KEYS)
    for _key, english, russian in out["rows"]:
        assert english and russian and english != russian
        assert not RAW_TOKENS.search(english) and not RAW_TOKENS.search(russian)


def test_the_russian_words_are_the_specs_own_and_the_queue_position_is_the_one_parameter():
    out = run_js("""
      console.log(JSON.stringify(Object.fromEntries(d.map(
        (key) => [key, i18n.MESSAGES[`desk_status.${key}`].ru]))));
    """, MODULES, list(SPEC_RUSSIAN))
    assert out == SPEC_RUSSIAN
    said = run_js("""console.log(JSON.stringify(i18n.LOCALES.map(
      (locale) => i18n.message(locale, "desk_status.queued", {position: "4"}))));""", MODULES)
    assert said == ["Queued · #4", "В очереди · 4-я"]


def test_the_status_modules_import_nothing_so_the_hub_can_take_them_whole():
    for name in ("desk-status.js", "desk-status-copy.js"):
        source = (PANEL / name).read_text(encoding="utf-8")
        assert not re.search(r"^import\b|\bimport\s*\(", source, re.M), name


def test_the_status_modules_read_no_clock():
    for name in ("desk-status.js", "desk-status-copy.js"):
        assert clock_reads(_code(PANEL / name)) == [], name


# -- the journal and the time a human step has waited (spec 4.5.6) ---------------------------
CASES_OF_THE_JOURNAL = JOURNAL["cases"]
NAMES_OF_THE_JOURNAL = [case["name"] for case in CASES_OF_THE_JOURNAL]


def _index(records: object) -> list:
    return run_js("console.log(JSON.stringify(st.journalIndex(d)));", MODULES, records)


@pytest.mark.parametrize("case", CASES_OF_THE_JOURNAL, ids=NAMES_OF_THE_JOURNAL)
def test_the_journal_index_of_each_fixture_case_is_the_projection_the_hub_carries(case):
    assert _index(case["records"]) == case["journal"]


def test_the_journal_index_keeps_the_last_256_rows_in_order_with_five_keys_each():
    records = [{"record_type": "action_request",
                "record": {"action_id": f"action-{n}", "node_id": "do",
                           "requested_at": "2026-09-29T09:00:00Z", "secret": "kept out"}}
               for n in range(300)]
    index = _index(records)
    assert [row["action_id"] for row in index] == [f"action-{n}" for n in range(44, 300)]
    assert all(sorted(row) == ["action_id", "instant", "node_id", "proposal_id", "record_type"]
               for row in index)
    assert "kept out" not in json.dumps(index)


def test_the_journal_index_skips_a_row_that_is_not_a_typed_record_and_answers_a_list_always():
    junk = [None, 3, "row", [], {}, {"record_type": 4, "record": {}},
            {"record_type": "decision"}, {"record_type": "decision", "record": None},
            {"record_type": "decision", "record": {"decided_at": "2026-09-29T09:25:00Z"}}]
    assert [row["record_type"] for row in _index(junk)] == ["decision"]
    out = run_js("console.log(JSON.stringify([null, undefined, {}, 'x', 4].map("
                 "(value) => st.journalIndex(value))));", MODULES)
    assert out == [[]] * 5


def test_each_kind_studio_words_an_instant_for_is_dated_by_its_own_field_and_no_other():
    fields = run_js("console.log(JSON.stringify(words.INSTANT_FIELDS));", MODULES)
    assert fields
    stamp = "2026-09-29T09:31:00Z"
    right = [{"record_type": kind, "record": {field: stamp}} for kind, field in fields.items()]
    wrong = [{"record_type": kind, "record": {"unrelated_at": stamp}} for kind in fields]
    assert [row["instant"] for row in _index(right)] == [stamp] * len(fields)
    assert [row["instant"] for row in _index(wrong)] == [None] * len(fields)


def _since(**given: object) -> str | None:
    return run_js("console.log(JSON.stringify(st.waitingSince(d)));", MODULES, given)


CASES_OF_WAITING = [pytest.param(case, item, id=f"{case['name']}: {item['name']}")
                    for case in CASES_OF_THE_JOURNAL for item in case["waiting"]]


@pytest.mark.parametrize("case,item", CASES_OF_WAITING)
def test_waiting_since_finds_the_record_that_opened_the_step_or_says_it_did_not(case, item):
    assert _since(reason=item["reason"], sources=item["sources"], journal=case["journal"],
                  runtime=case["runtime"]) == item["at"]


def test_the_fixture_reaches_all_five_reasons_and_finds_and_misses_for_the_four_that_can():
    reasons = {item["reason"] for case in CASES_OF_THE_JOURNAL for item in case["waiting"]}
    assert {"confirmation", "attempt_bound", "gate_decision", "input_document",
            "reconcile"} <= reasons
    for reason in ("confirmation", "attempt_bound", "gate_decision", "input_document"):
        found = [item["at"] is not None for case in CASES_OF_THE_JOURNAL
                 for item in case["waiting"] if item["reason"] == reason]
        assert True in found and False in found, reason
    assert all(item["at"] is None for case in CASES_OF_THE_JOURNAL
               for item in case["waiting"] if item["reason"] == "reconcile")


def _row(kind: str, instant: str | None, **ids: str) -> dict:
    return {"record_type": kind, "instant": instant, "action_id": None, "node_id": None,
            "proposal_id": None, **ids}


def test_the_last_result_of_a_step_is_the_last_one_in_the_journal_and_not_the_latest_instant():
    journal = [_row("action_request", "2026-09-29T09:00:00Z", action_id="a1", node_id="do"),
               _row("action_result", "2026-09-29T09:30:00Z", action_id="a1"),
               _row("action_request", "2026-09-29T09:01:00Z", action_id="a2", node_id="do"),
               _row("action_result", "2026-09-29T09:10:00Z", action_id="a2")]
    assert _since(reason="attempt_bound", sources=["do"], journal=journal,
                  runtime=[]) == "2026-09-29T09:10:00Z"


def test_instants_are_compared_as_times_so_a_fraction_of_a_second_sorts_after_its_second():
    journal = [_row("action_proposal", "2026-09-29T09:00:00.5Z", proposal_id="p1"),
               _row("action_proposal", "2026-09-29T09:00:00Z", proposal_id="p2")]
    assert _since(reason="confirmation", sources=["p1", "p2"], journal=journal,
                  runtime=[]) == "2026-09-29T09:00:00Z"


def test_a_source_whose_record_has_no_instant_is_not_found_and_the_others_still_are():
    journal = [_row("action_proposal", None, proposal_id="p1"),
               _row("action_proposal", "2026-09-29T09:03:00Z", proposal_id="p2")]
    assert _since(reason="confirmation", sources=["p1", "p2"], journal=journal,
                  runtime=[]) == "2026-09-29T09:03:00Z"
    assert _since(reason="confirmation", sources=["p1"], journal=journal, runtime=[]) is None


def test_a_journal_that_lost_its_first_rows_cannot_date_a_step_that_nothing_opened():
    """The graph record is older than the 256 rows the projection keeps: not found."""
    records = [{"record_type": "graph_definition",
                "record": {"created_at": "2026-09-29T09:00:00Z"}}]
    records += [{"record_type": "action_request",
                 "record": {"action_id": f"a{n}", "node_id": "do",
                            "requested_at": "2026-09-29T09:01:00Z"}} for n in range(300)]
    journal = _index(records)
    assert len(journal) == 256 and journal[0]["record_type"] == "action_request"
    assert _since(reason="input_document", sources=["intake"], journal=journal,
                  runtime=[{"node_id": "intake", "opened_by": []}]) is None


@pytest.mark.parametrize("given", [
    {"reason": "confirmation"}, {"reason": "attempt_bound", "sources": None},
    {"reason": "gate_decision", "sources": ["g"], "journal": None, "runtime": None},
    {"reason": "gate_decision", "sources": ["g"], "journal": [],
     "runtime": [{"node_id": "g", "opened_by": "not a list"}]},
    {"reason": "no_such_reason", "sources": ["x"], "journal": [], "runtime": []},
    {"reason": "confirmation", "sources": [None, 4, {}], "journal": [], "runtime": []}])
def test_waiting_since_answers_null_and_never_throws_for_input_it_cannot_read(given):
    assert _since(**given) is None
