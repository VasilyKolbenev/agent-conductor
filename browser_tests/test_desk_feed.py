"""The desk's feed "Ход работы" on a real one-project server, in Russian and in English.

The production `server.build` over the project of `tests/desk_progress_seed.py`: a run accepted
at its final gate (every kind of record the feed draws), a run with an attempt in flight and a
run whose check did not pass. What this module holds, each as a measurement of the page:

- the feed of the run on the scene is the journal read as facts, in the journal's order, each
  with its author (harness and what it did), in the reader's language;
- every row says its time in the zone of the browser and keeps the exact value in its hint;
- a check that did not pass carries its sentence in its own row; an attempt in flight is the
  live row;
- no machine word reaches the feed, nothing is stored, nothing but GET is sent, and the page
  throws and logs nothing.

A fact and its sentence are read in ONE evaluation.
"""
from __future__ import annotations

import re

import pytest

from browser_tests.desk_progress_bench import RAW_TOKENS, desk_in, progress_url  # noqa: F401
from tests.test_desk_feed_model import READS, _instant

#: One evaluation: the feed as the page draws it.
FEED_FACTS = """() => {
  const feed = document.getElementById("deskFeed");
  const log = feed.querySelector(".desk-feed__log");
  const text = (node, selector) => node.querySelector(selector)?.textContent ?? null;
  return {
    state: feed.getAttribute("data-state"), title: text(feed, ".desk-feed__title"),
    order: text(feed, ".desk-feed__order"), text: feed.innerText,
    rows: [...feed.querySelectorAll(".desk-feed__row")].map((row) => ({
      kind: row.dataset.kind, tone: row.getAttribute("data-tone"),
      who: text(row, ".desk-feed__who"), what: text(row, ".desk-feed__what"),
      reason: text(row, ".desk-feed__reason"), note: text(row, ".desk-feed__note"),
      at: row.querySelector("time") === null ? null : {
        text: row.querySelector("time").textContent,
        datetime: row.querySelector("time").getAttribute("datetime"),
        title: row.querySelector("time").getAttribute("title")},
      current: row.getAttribute("aria-current")}))};
}"""
#: What each language says of the run that was accepted: kind, who, what, reason.
CLOSED = {
    "en": [
        ("document", "Person", "Document “artifact-brief” published", None),
        ("proposed", "claude-code · Performs", "Step “Analyse the brief” proposed", None),
        ("started", "claude-code · Performs", "Started step “Analyse the brief”", None),
        ("document", "claude-code · Performs", "Document “artifact-plan” published", None),
        ("verdict", "claude-code · Verifies", "Check of step “Analyse the brief”: passed", None),
        ("result", "claude-code · Performs",
         "Result of step “Analyse the brief”: Succeeded", None),
        ("decision", "release-owner · Human decision",
         "Decision on “Confirm the plan”: approved", "Reason: Reviewed the plan."),
        ("proposed", "claude-code · Performs", "Step “Do the work” proposed", None),
        ("started", "claude-code · Performs", "Started step “Do the work”", None),
        ("verdict", "codex-cli · Verifies", "Check of step “Do the work”: passed", None),
        ("result", "claude-code · Performs", "Result of step “Do the work”: Succeeded", None),
        ("decision", "release-owner · Human decision",
         "Decision on “Accept the result”: approved", "Reason: Looks right."),
    ],
    "ru": [
        ("document", "Человек", "Опубликован документ «artifact-brief»", None),
        ("proposed", "claude-code · Выполняет", "Предложен шаг «Analyse the brief»", None),
        ("started", "claude-code · Выполняет", "Начат шаг «Analyse the brief»", None),
        ("document", "claude-code · Выполняет", "Опубликован документ «artifact-plan»", None),
        ("verdict", "claude-code · Проверяет",
         "Проверка шага «Analyse the brief»: пройдена", None),
        ("result", "claude-code · Выполняет",
         "Результат шага «Analyse the brief»: Успешно", None),
        ("decision", "release-owner · Решение человека",
         "Решение на точке «Confirm the plan»: одобрено", "Причина: Reviewed the plan."),
        ("proposed", "claude-code · Выполняет", "Предложен шаг «Do the work»", None),
        ("started", "claude-code · Выполняет", "Начат шаг «Do the work»", None),
        ("verdict", "codex-cli · Проверяет", "Проверка шага «Do the work»: пройдена", None),
        ("result", "claude-code · Выполняет", "Результат шага «Do the work»: Успешно", None),
        ("decision", "release-owner · Решение человека",
         "Решение на точке «Accept the result»: одобрено", "Причина: Looks right."),
    ],
}
HEADS = {"en": ("Progress · run run-closed", "newest at the bottom"),
         "ru": ("Ход работы · запуск run-closed", "новые внизу")}
NOTES = {"en": "Process exit 0 proves the process finished, not that the work was verified.",
         "ru": "Код завершения 0 подтверждает окончание процесса, "
               "но не независимую проверку результата."}
#: The short time of the first row, where the page reads in UTC: the day and month in the
#: language's own order, then the clock.
FIRST_TIME = {"en": "08/19 08:03", "ru": "19.08 08:03"}


def _summary(facts: dict) -> list[tuple]:
    return [(row["kind"], row["who"], row["what"], row["reason"]) for row in facts["rows"]]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_feed_says_the_journal_of_the_run_as_its_facts_in_each_language(desk_in, language):
    window = desk_in(language, task="task-closed")
    facts = window.page.evaluate(FEED_FACTS)
    assert facts["state"] == "ready"
    assert (facts["title"], facts["order"]) == HEADS[language]
    assert _summary(facts) == CLOSED[language]
    assert all(row["note"] is None for row in facts["rows"])
    assert window.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_each_row_says_the_local_time_its_record_states_with_the_exact_value_in_its_hint(
        desk_in, language):
    window = desk_in(language, task="task-closed")
    facts = window.page.evaluate(FEED_FACTS)
    wanted = [at for at in (_instant(row["record_type"], row["record"])
                            for row in READS["run-closed"]["records"]) if at is not None]
    assert [row["at"]["datetime"] for row in facts["rows"]] == wanted
    assert [row["at"]["title"] for row in facts["rows"]] == wanted
    assert facts["rows"][0]["at"]["text"] == FIRST_TIME[language]
    said = window.page.evaluate("""async (iso) => {
      const {instantText} = await import("/panel/desk-time.js");
      return iso.map((one) => instantText(document.documentElement.lang, one).short);
    }""", wanted)
    assert [row["at"]["text"] for row in facts["rows"]] == said


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_check_that_did_not_pass_carries_its_sentence_in_its_own_row_and_is_amber(
        desk_in, language):
    window = desk_in(language, task="task-waiting")
    last = window.page.evaluate(FEED_FACTS)["rows"][-1]
    word = {"en": "Verification failed", "ru": "Проверка не пройдена"}[language]
    lead = {"en": "Result of step “Do the work”: ", "ru": "Результат шага «Do the work»: "}
    assert (last["kind"], last["what"], last["note"], last["tone"]) == (
        "result", lead[language] + word, NOTES[language], "amber")
    assert window.problems == []


def test_an_attempt_in_flight_is_the_live_row_and_carries_the_ion_tone(desk_in):
    window = desk_in("en", task="task-working")
    rows = window.page.evaluate(FEED_FACTS)["rows"]
    live = [row for row in rows if row["tone"] == "ion"]
    assert [(row["kind"], row["what"]) for row in live] == [
        ("started", "Started step “Do the work” · in progress")]
    assert rows[-1]["kind"] == "started"


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("task", ["task-closed", "task-working", "task-waiting"])
def test_the_feed_holds_no_machine_word_and_the_page_stores_and_writes_nothing(
        desk_in, language, task):
    window = desk_in(language, task=task)
    facts = window.page.evaluate(FEED_FACTS)
    assert facts["rows"], "the feed drew nothing"
    assert not re.search(RAW_TOKENS, facts["text"], re.I), facts["text"]
    assert {method for method, _path in window.asked} == {"GET"}
    assert window.page.evaluate("() => [localStorage.length, sessionStorage.length]") == [0, 0]
    assert window.problems == []


def test_a_window_with_no_task_chosen_has_an_empty_feed(desk_in):
    window = desk_in("en")
    facts = window.page.evaluate(FEED_FACTS)
    assert (facts["state"], facts["rows"], facts["text"]) == ("empty", [], "")


#: Every word a record can carry that the feed says, in each language: the outcome of a result
#: (the Studio's own words), the verdict of a check and the answer of a person to a gate.
WORDS = {
    "en": {
        "action_result": {"cancelled": "Cancelled", "failed": "Failed", "rejected": "Rejected",
                          "succeeded": "Succeeded", "unknown": "Outcome unknown",
                          "verification_failed": "Verification failed"},
        "evidence": {"verified": "passed", "mismatch": "not passed",
                     "error": "ended in an error", "unavailable": "unavailable"},
        "decision": {"approve": "approved", "reject": "rejected",
                     "request_changes": "sent back for changes",
                     "waive": "set aside without judging the work"}},
    "ru": {
        "action_result": {"cancelled": "Отменено", "failed": "Ошибка", "rejected": "Отклонено",
                          "succeeded": "Успешно", "unknown": "Исход неизвестен",
                          "verification_failed": "Проверка не пройдена"},
        "evidence": {"verified": "пройдена", "mismatch": "не пройдена",
                     "error": "завершилась ошибкой", "unavailable": "недоступна"},
        "decision": {"approve": "одобрено", "reject": "отклонено",
                     "request_changes": "возвращено на доработку",
                     "waive": "пропущено без оценки работы"}},
}
#: The module in the page, handed the real read of a run with one field of one kind of record
#: changed to each word in turn; what it says of the rows of that kind is what comes back.
EVERY_WORD = """async ([language, table]) => {
  const read = await (await fetch("/command/runs/run-closed")).json();
  const {mountFeed} = await import("/panel/desk-feed.js");
  const mount = document.createElement("section");
  document.body.append(mount);
  const field = {action_result: "outcome", evidence: "verification", decision: "action"};
  const kind = {action_result: "result", evidence: "verdict", decision: "decision"};
  const said = {};
  for (const [type, words] of Object.entries(table)) {
    for (const word of Object.keys(words)) {
      const copy = structuredClone(read);
      for (const row of copy.records) if (row.record_type === type) row.record[field[type]] = word;
      mountFeed(mount, {locale: language, foreign: false, run: {detail: copy}});
      said[`${type}:${word}`] = [...mount.querySelectorAll(".desk-feed__row")]
        .filter((row) => row.dataset.kind === kind[type])
        .map((row) => row.querySelector(".desk-feed__what").textContent);
    }
  }
  return said;
}"""


@pytest.mark.parametrize("language", ["en", "ru"])
def test_every_word_a_result_a_check_or_a_person_can_carry_is_said_and_none_as_a_key(
        desk_in, language):
    window = desk_in(language)
    said = window.page.evaluate(EVERY_WORD, [language, WORDS[language]])
    for type_, words in WORDS[language].items():
        for word, spelled in words.items():
            sentences = said[f"{type_}:{word}"]
            assert sentences and all(spelled in one for one in sentences), (type_, word, sentences)
    assert not re.search(r"\b(?:feed|scene|feedback)\.[a-z_]+", str(said)), said
    assert window.problems == []


#: A row the plan cannot place: no step on a proposal, a gate the plan does not have, a check
#: nobody made.
UNPLACED = """async (language) => {
  const read = await (await fetch("/command/runs/run-closed")).json();
  const {mountFeed} = await import("/panel/desk-feed.js");
  for (const row of read.records) {
    const record = row.record;
    if (row.record_type === "action_proposal") delete record.node_id;
    if (row.record_type === "decision") record.gate_id = "gate-elsewhere";
    if (row.record_type === "evidence") {
      record.verified_by = null;
      record.verifier_instance_id = null;
    }
  }
  const mount = document.createElement("section");
  document.body.append(mount);
  mountFeed(mount, {locale: language, foreign: false, run: {detail: read}});
  const rows = [...mount.querySelectorAll(".desk-feed__row")];
  const said = (kind, part) => rows.filter((row) => row.dataset.kind === kind)
    .map((row) => row.querySelector(part).textContent);
  return {proposed: said("proposed", ".desk-feed__what"),
    decision: said("decision", ".desk-feed__what"), verdict: said("verdict", ".desk-feed__who")};
}"""


@pytest.mark.parametrize("language,expected", [
    ("en", {"proposed": ["Step “a step the plan does not name” proposed"] * 2,
            "decision": ["Decision on “a gate the plan does not name”: approved"] * 2,
            "verdict": ["Unknown participant"] * 2}),
    ("ru", {"proposed": ["Предложен шаг «шаг, которого нет в плане»"] * 2,
            "decision": ["Решение на точке «точка, которой нет в плане»: одобрено"] * 2,
            "verdict": ["Неизвестный участник"] * 2})])
def test_a_row_the_plan_cannot_place_says_so_in_words_and_draws_no_blank(
        desk_in, language, expected):
    window = desk_in(language)
    assert window.page.evaluate(UNPLACED, language) == expected
    assert window.problems == []
