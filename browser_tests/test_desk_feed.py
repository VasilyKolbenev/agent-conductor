"""The desk's feed "Ход работы" on a real one-project server, in Russian and in English.

The production `server.build` over the project of `tests/desk_progress_seed.py`: a run accepted
at its final gate (every kind of record the feed draws), a run with an attempt in flight and a
run whose check did not pass. What this module holds, each as a measurement of the page:

- the feed of the run on the scene is the journal read as facts, in the journal's order, each
  with its author (harness and what it did), in the reader's language;
- every row says its time in the zone of the browser and keeps the exact value in its hint;
- a check that did not pass carries its sentence in its own row; an attempt in flight is the
  live row; a check a step's own adapter made (no verifier is named) is its performer's and says
  the Studio's sentence, and only such a check does;
- no machine word reaches the feed, nothing is stored, nothing but GET is sent, and the page
  throws and logs nothing.

A fact and its sentence are read in ONE evaluation.
"""
from __future__ import annotations

import re

import pytest

from browser_tests.desk_progress_bench import RAW_TOKENS, desk_in, progress_url  # noqa: F401
from tests.test_desk_feed_model import READS, REJECTED, _instant

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
        ("verdict", "claude-code · Performs", "Check of step “Analyse the brief”: passed", None),
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
        ("verdict", "claude-code · Выполняет",
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
#: The Studio's own sentence (`runstep.same_adapter`) for a step whose check was made by its own
#: adapter: the one row of the accepted run that carries it is the check of "Analyse the brief".
SAME = {"en": "Verified by the same participant's adapter over its own post-observation "
              "evidence; no independent checker is named by this step.",
        "ru": "Проверяет адаптер того же участника по собственным данным после исполнения. "
              "Независимый проверяющий для этого шага не назначен."}
OWN_CHECK_ROW = 4
#: The short time of the first row, where the page reads in UTC: the day and month in the
#: language's own order, then the clock.
FIRST_TIME = {"en": "08/19 08:03", "ru": "19.08 08:03"}


def _summary(facts: dict) -> list[tuple]:
    return [(row["kind"], row["who"], row["what"], row["reason"]) for row in facts["rows"]]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_feed_says_the_journal_of_the_run_as_its_facts_in_each_language(desk_in, language):
    # The feed says the state of the scene. A stream that opens makes a full refresh, which
    # stands the scene as `stale` until the run is read again, so the stream is ended.
    window = desk_in(language, task="task-closed", stream=False)
    facts = window.page.evaluate(FEED_FACTS)
    assert facts["state"] == "ready"
    assert (facts["title"], facts["order"]) == HEADS[language]
    assert _summary(facts) == CLOSED[language]
    assert [row["note"] for row in facts["rows"]] == [
        SAME[language] if place == OWN_CHECK_ROW else None for place in range(12)]
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


#: The verdict rows the page drew: who each is by and every sentence it carries; and the Studio's
#: own message the wording of `SAME` is held equal to.
VERDICT_ROWS = """async (language) => {
  const {message} = await import("/panel/studio-i18n.js");
  const rows = [...document.querySelectorAll("#deskFeed .desk-feed__row")]
    .filter((row) => row.dataset.kind === "verdict");
  return {studio: message(language, "runstep.same_adapter"),
    rows: rows.map((row) => [row.querySelector(".desk-feed__who").textContent,
      [...row.querySelectorAll(".desk-feed__note")].map((note) => note.textContent)])};
}"""
VERDICT_WHO = {"en": ["claude-code · Performs", "codex-cli · Verifies"],
               "ru": ["claude-code · Выполняет", "codex-cli · Проверяет"]}


@pytest.mark.parametrize("language", ["en", "ru"])
def test_only_a_check_by_the_steps_own_adapter_names_its_performer_and_says_the_studios_sentence(
        desk_in, language):
    window = desk_in(language, task="task-closed")
    found = window.page.evaluate(VERDICT_ROWS, language)
    assert found["studio"] == SAME[language]
    assert found["rows"] == [[VERDICT_WHO[language][0], [SAME[language]]],
                             [VERDICT_WHO[language][1], []]]
    assert window.problems == []


#: The real run with every check it holds turned into "not passed": the module in the page draws
#: it, and what comes back is every sentence each verdict row carries.
NOT_PASSED = """async (language) => {
  const read = await (await fetch("/command/runs/run-closed")).json();
  const {mountFeed} = await import("/panel/desk-feed.js");
  for (const row of read.records) {
    if (row.record_type === "evidence") row.record.verification = "mismatch";
  }
  const mount = document.createElement("section");
  document.body.append(mount);
  mountFeed(mount, {locale: language, foreign: false, run: {detail: read}});
  return [...mount.querySelectorAll(".desk-feed__row")]
    .filter((row) => row.dataset.kind === "verdict")
    .map((row) => [...row.querySelectorAll(".desk-feed__note")].map((note) => note.textContent));
}"""


@pytest.mark.parametrize("language", ["en", "ru"])
def test_an_own_check_that_did_not_pass_says_both_sentences_and_an_independent_one_only_its_own(
        desk_in, language):
    window = desk_in(language)
    found = window.page.evaluate(NOT_PASSED, language)
    assert found == [[NOTES[language], SAME[language]], [NOTES[language]]]
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
    decision: said("decision", ".desk-feed__what"), verdict: said("verdict", ".desk-feed__who"),
    verdictNotes: rows.filter((row) => row.dataset.kind === "verdict")
      .map((row) => row.querySelectorAll(".desk-feed__note").length)};
}"""


@pytest.mark.parametrize("language,expected", [
    ("en", {"proposed": ["Step “a step the plan does not name” proposed"] * 2,
            "decision": ["Decision on “a gate the plan does not name”: approved"] * 2,
            "verdict": ["Unknown participant"] * 2, "verdictNotes": [0, 0]}),
    ("ru", {"proposed": ["Предложен шаг «шаг, которого нет в плане»"] * 2,
            "decision": ["Решение на точке «точка, которой нет в плане»: одобрено"] * 2,
            "verdict": ["Неизвестный участник"] * 2, "verdictNotes": [0, 0]})])
def test_a_row_the_plan_cannot_place_says_so_in_words_and_draws_no_blank(
        desk_in, language, expected):
    window = desk_in(language)
    assert window.page.evaluate(UNPLACED, language) == expected
    assert window.problems == []


# -- documents in their rows, and the place of the list --------------------------------------

#: One evaluation: the documents of the feed, the list's place and the newest row.
PLACE_FACTS = """() => {
  const log = document.querySelector("#deskFeed .desk-feed__log");
  const rows = [...log.querySelectorAll(".desk-feed__row")];
  const box = log.getBoundingClientRect(), last = rows.at(-1).getBoundingClientRect();
  return {
    top: log.scrollTop, height: log.scrollHeight, client: log.clientHeight,
    atBottom: log.scrollHeight - log.scrollTop - log.clientHeight <= 4,
    current: rows.map((row) => row.getAttribute("aria-current")),
    lastInView: last.bottom <= box.bottom + 1 && last.top >= box.top - 1,
    open: [...log.querySelectorAll("details")].map((node) => node.open),
    summaries: [...log.querySelectorAll("summary")].map((node) => node.textContent),
    texts: [...log.querySelectorAll("details[open] .desk-feed__text")].map((node) => ({
      text: node.textContent, markup: node.children.length, tag: node.tagName})),
    focusable: log.getAttribute("tabindex"), run: log.dataset.run};
}"""
#: The documents of the seeded run: the person's brief and the action's plan.
BRIEF_TEXT = "Ship the landing page by Friday.\nKeep the hero copy short."
PLAN_TEXT = "# Plan\n\n1. Draft the hero copy\n2. Put <b>bold</b> in the footer\n"


@pytest.mark.parametrize("language,label", [("en", "Show the text"), ("ru", "Показать текст")])
def test_a_document_opens_in_its_row_and_its_text_is_text_and_never_markup(
        desk_in, language, label):
    window = desk_in(language, task="task-closed")
    before = window.page.evaluate(PLACE_FACTS)
    assert before["summaries"] == [label, label] and before["open"] == [False, False]
    window.page.locator("#deskFeed summary").nth(1).click()
    after = window.page.evaluate(PLACE_FACTS)
    assert after["open"] == [False, True]
    assert after["texts"] == [{"text": PLAN_TEXT, "markup": 0, "tag": "PRE"}]
    window.page.locator("#deskFeed summary").nth(0).click()
    both = window.page.evaluate(PLACE_FACTS)
    assert [one["text"] for one in both["texts"]] == [BRIEF_TEXT, PLAN_TEXT]
    assert window.problems == []


def test_the_newest_row_is_the_current_one_stands_in_view_and_the_list_can_be_reached_by_key(
        desk_in):
    facts = desk_in("en", task="task-closed").page.evaluate(PLACE_FACTS)
    assert facts["current"] == [None] * 11 + ["true"]
    assert facts["lastInView"] and facts["atBottom"]
    assert facts["height"] > facts["client"], "the list scrolls"
    assert facts["focusable"] == "0"


#: A redraw of the same run: the theme is set by the address, which draws every region again.
REDRAW = """(theme) => {
  location.hash = `#lang=${document.documentElement.lang}&task=task-closed&theme=${theme}`;
}"""
DRAWN = """(theme) => document.documentElement.getAttribute("data-theme") === theme"""


def _redraw(window, theme: str = "dark") -> None:
    window.page.evaluate(REDRAW, theme)
    window.page.wait_for_function(DRAWN, arg=theme)


def test_an_open_document_and_the_place_of_the_list_survive_a_redraw_of_the_same_run(desk_in):
    window = desk_in("en", task="task-closed")
    window.page.locator("#deskFeed summary").nth(1).click()
    window.page.evaluate("""() => { const log = document.querySelector("#deskFeed .desk-feed__log");
      log.scrollTop = 40; }""")
    before = window.page.evaluate(PLACE_FACTS)
    _redraw(window)
    after = window.page.evaluate(PLACE_FACTS)
    assert (after["open"], after["top"], after["run"]) == (
        before["open"], before["top"], "run-closed") == ([False, True], 40, "run-closed")
    assert window.problems == []


def test_a_language_set_by_the_address_keeps_the_open_document_and_says_the_rest_anew(desk_in):
    window = desk_in("en", task="task-closed")
    window.page.locator("#deskFeed summary").nth(1).click()
    window.page.evaluate("() => { location.hash = '#lang=ru&task=task-closed'; }")
    window.page.wait_for_function("() => document.documentElement.lang === 'ru'")
    window.page.wait_for_function(
        "() => document.querySelector('#deskFeed .desk-feed__title')?.textContent.includes('Ход')")
    after = window.page.evaluate(PLACE_FACTS)
    assert after["open"] == [False, True] and after["summaries"] == ["Показать текст"] * 2
    assert window.problems == []


def test_a_reader_who_scrolled_up_is_not_pulled_down_and_one_at_the_bottom_stays_there(desk_in):
    window = desk_in("en", task="task-closed")
    assert window.page.evaluate(PLACE_FACTS)["atBottom"]
    _redraw(window, "dark")
    assert window.page.evaluate(PLACE_FACTS)["atBottom"]
    window.page.evaluate("""() => { document.querySelector("#deskFeed .desk-feed__log")
      .scrollTop = 0; }""")
    _redraw(window, "light")
    stayed = window.page.evaluate(PLACE_FACTS)
    assert stayed["top"] == 0 and not stayed["atBottom"]


def test_another_run_starts_at_the_bottom_even_when_the_last_one_was_left_at_the_top(desk_in):
    window = desk_in("en", task="task-closed")
    window.page.evaluate("""() => { document.querySelector("#deskFeed .desk-feed__log")
      .scrollTop = 0; }""")
    window.page.locator('#deskRail [data-task-id="task-waiting"]').click()
    window.page.wait_for_function(
        "() => document.querySelector('#deskFeed .desk-feed__log')?.dataset.run === 'run-waiting'")
    facts = window.page.evaluate(PLACE_FACTS)
    assert facts["run"] == "run-waiting" and facts["atBottom"] and facts["lastInView"]


#: The module in the page, handed a real read: the rows of one kind, and what opens in them.
ROWS_OF = """async ([language, read, kind, edit]) => {
  const {mountFeed} = await import("/panel/desk-feed.js");
  if (edit === "large") {
    read.records.find((row) => row.record_type === "artifact").record.content = "x".repeat(49153);
  }
  const mount = document.createElement("section");
  document.body.append(mount);
  mountFeed(mount, {locale: language, foreign: false, run: {detail: read}});
  const part = (row, selector) => row.querySelector(selector)?.textContent ?? null;
  return [...mount.querySelectorAll(".desk-feed__row")]
    .filter((row) => row.dataset.kind === kind).map((row) => ({
      who: part(row, ".desk-feed__who"), what: part(row, ".desk-feed__what"),
      summary: part(row, "summary"), note: part(row, ".desk-feed__note"),
      findings: [...row.querySelectorAll(".desk-feed__finding")].map((one) => ({
        kind: part(one, "strong"), summary: part(one, "p"),
        where: part(one, ".desk-feed__where")}))}));
}"""
FINDINGS = {
    "en": {"who": "codex-cli · Verifies", "what": "Findings of the check of step “do”",
           "summary": "Show the text", "kind": "Defect"},
    "ru": {"who": "codex-cli · Проверяет", "what": "Замечания проверки шага «do»",
           "summary": "Показать текст", "kind": "Дефект"}}


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_typed_findings_of_a_checker_are_a_row_with_the_kind_the_words_and_the_place(
        desk_in, language):
    window = desk_in(language)
    (found,) = window.page.evaluate(ROWS_OF, [language, REJECTED, "findings", None])
    said = FINDINGS[language]
    assert (found["who"], found["what"], found["summary"]) == (
        said["who"], said["what"], said["summary"])
    assert found["findings"] == [{"kind": said["kind"], "where": "answer.py:2",
                                  "summary": "answer() must return 1 instead of 2"}]
    assert window.problems == []


@pytest.mark.parametrize("language,words", [
    ("en", "This document is too large to show here."),
    ("ru", "Документ слишком велик, чтобы показать его здесь.")])
def test_a_document_past_the_limit_says_so_in_its_row_and_offers_no_text(
        desk_in, language, words):
    window = desk_in(language)
    first = window.page.evaluate(ROWS_OF, [language, READS["run-closed"], "document", "large"])[0]
    assert (first["note"], first["summary"]) == (words, None)
    assert window.problems == []


#: The module in the page: one run drawn, the list scrolled to its top, another run drawn on the
#: same mount -- as when the address names another run of the task on the scene.
ANOTHER_RUN = """async () => {
  const {mountFeed} = await import("/panel/desk-feed.js");
  const read = async (id) => (await fetch(`/command/runs/${id}`)).json();
  const mount = document.createElement("section");
  document.body.append(mount);
  const view = async (id) => ({locale: "en", foreign: false, run: {detail: await read(id)}});
  mountFeed(mount, await view("run-closed"));
  mount.querySelector(".desk-feed__log").scrollTop = 0;
  mountFeed(mount, await view("run-waiting"));
  const log = mount.querySelector(".desk-feed__log");
  return {run: log.dataset.run, bottom: log.scrollHeight - log.scrollTop - log.clientHeight};
}"""


def test_a_list_that_held_another_run_draws_the_new_one_at_its_bottom(desk_in):
    window = desk_in("en")
    window.page.set_viewport_size({"width": 1280, "height": 900})
    facts = window.page.evaluate(ANOTHER_RUN)
    assert facts["run"] == "run-waiting" and facts["bottom"] <= 4
