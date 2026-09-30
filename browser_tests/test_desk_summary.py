"""The desk's summary on a real one-project server, in Russian and in English.

The production `server.build` over the project of `tests/desk_progress_seed.py`: one task in each
place -- accepted at its final gate, an attempt in flight, a check that did not pass and waits for
a person, and one nobody started. What this module holds, each as a measurement of the page:

- the bar counts the tasks in four places and says, in words, what "closed" means; the strip has
  one segment for each task; "now" names the run on the scene and what goes on in it;
- a press opens the panel "кто что делал и сделал": each task with the word the rail gives it and
  what the records say of who did, who checked and who accepted; the participants of the run on
  the scene with role, harness, actions, documents and time; a redraw keeps it open;
- the summary appears only when its numbers are known, and a finished run that could not be read
  is not counted closed;
- no machine word, targets of 44 px, nothing stored, nothing but GET, no console error.

A fact and its sentence are read in ONE evaluation.
"""
from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import Route

from browser_tests.desk_progress_bench import RAW_TOKENS, ZONE, desk_in, progress_url  # noqa: F401

#: One evaluation: the summary as the page draws it.
SUMMARY_FACTS = """() => {
  const mount = document.getElementById("deskSummary");
  const bar = mount.querySelector(".desk-sum__bar");
  const panel = mount.querySelector(".desk-sum__panel");
  const text = (node, selector) => node.querySelector(selector)?.textContent ?? null;
  return {
    state: mount.getAttribute("data-state"), children: mount.childElementCount,
    text: mount.innerText,
    bar: bar === null ? null : {expanded: bar.getAttribute("aria-expanded"),
      controls: bar.getAttribute("aria-controls"), height: bar.getBoundingClientRect().height,
      more: text(bar, ".desk-sum__more"), now: text(bar, ".desk-sum__now"),
      chips: [...bar.querySelectorAll(".desk-sum__chip")].map((chip) => ({
        label: text(chip, ".desk-sum__label"), count: text(chip, "b"),
        tone: chip.getAttribute("data-tone"), title: chip.getAttribute("title")})),
      track: [...bar.querySelectorAll(".desk-sum__track i")].map(
        (one) => one.getAttribute("data-tone")),
      trackHidden: bar.querySelector(".desk-sum__track")?.getAttribute("aria-hidden")},
    panel: panel === null ? null : {id: panel.id, hidden: panel.hidden,
      title: text(panel, ".desk-sum__title"),
      how: [...panel.querySelectorAll(".desk-sum__how p")].map((one) => one.textContent),
      tasks: [...panel.querySelectorAll(".desk-sum__task")].map((row) => ({
        title: text(row, ".desk-sum__task-title"), what: text(row, ".desk-sum__task-what"),
        tone: row.getAttribute("data-tone")})),
      peopleHead: text(panel, ".desk-sum__people-head"),
      people: [...panel.querySelectorAll(".desk-sum__person")].map((row) => ({
        name: text(row, ".desk-sum__person-name"), role: text(row, ".desk-sum__person-role"),
        facts: [...row.querySelectorAll(".desk-sum__fact")].map((one) => one.textContent),
        at: row.querySelector("time") === null ? null : {
          text: row.querySelector("time").textContent,
          title: row.querySelector("time").getAttribute("title")}})),
      noRun: text(panel, ".desk-sum__no-run")},
    rail: [...document.querySelectorAll("#deskRail [data-task-id]")].map((row) => [
      row.querySelector(".desk-task__title").textContent,
      row.querySelector(".desk-task__state").textContent]),
  };
}"""
WAIT_BAR = "() => document.querySelector('#deskSummary .desk-sum__bar') !== null"

CHIPS = {
    "en": [("In progress", "1"), ("Waiting for you", "1"), ("Closed", "1"), ("Left", "1")],
    "ru": [("В работе", "1"), ("Ждут вас", "1"), ("Закрыто", "1"), ("Осталось", "1")]}
CLOSED_CAPTION = {"en": "The newest run was accepted at its final gate.",
                  "ru": "Последний запуск принят на финальном гейте."}
#: The strip: one segment for each task in the rail's order (closed, idle, waiting, working).
TRACK = ["done", None, "amber", "ion"]


def _open(desk_in, language, task=None):
    window = desk_in(language, task=task)
    window.page.wait_for_function(WAIT_BAR)
    return window


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_bar_counts_the_tasks_in_four_places_and_says_what_closed_means(desk_in, language):
    window = _open(desk_in, language)
    facts = window.page.evaluate(SUMMARY_FACTS)
    assert facts["state"] == "ready"
    assert [(chip["label"], chip["count"]) for chip in facts["bar"]["chips"]] == CHIPS[language]
    assert [chip["tone"] for chip in facts["bar"]["chips"]] == ["ion", "amber", None, None]
    closed = facts["bar"]["chips"][2]
    assert closed["title"] == CLOSED_CAPTION[language]
    assert facts["bar"]["track"] == TRACK and facts["bar"]["trackHidden"] == "true"
    assert facts["bar"]["now"] is None, "no run is on the scene"
    assert window.problems == []


NOW = {
    ("en", "task-working"): "now in run-working: claude-code · Do the work",
    ("en", "task-waiting"): "now in run-waiting: waiting for your decision: Accept the result",
    ("en", "task-closed"): "now in run-closed: nothing is running and nothing asks you",
    ("ru", "task-working"): "сейчас в run-working: claude-code · Do the work",
    ("ru", "task-waiting"): "сейчас в run-waiting: ждёт вашего решения: Accept the result",
    ("ru", "task-closed"): "сейчас в run-closed: ничего не идёт и ничего не ждёт вас"}


@pytest.mark.parametrize("language,task", list(NOW))
def test_now_names_the_run_on_the_scene_and_what_goes_on_in_it(desk_in, language, task):
    window = _open(desk_in, language, task)
    window.page.wait_for_function(
        "() => document.querySelector('#deskSummary .desk-sum__now') !== null")
    assert window.page.evaluate(SUMMARY_FACTS)["bar"]["now"] == NOW[(language, task)]
    assert window.problems == []


@pytest.mark.parametrize("language,more,less", [
    ("en", "Details ▴", "Collapse ▾"), ("ru", "Подробнее ▴", "Свернуть ▾")])
def test_a_press_opens_the_panel_and_a_press_of_its_close_puts_focus_back_on_the_bar(
        desk_in, language, more, less):
    window = _open(desk_in, language)
    before = window.page.evaluate(SUMMARY_FACTS)
    assert (before["bar"]["expanded"], before["panel"]["hidden"], before["bar"]["more"]) == (
        "false", True, more)
    assert before["bar"]["controls"] == before["panel"]["id"]
    window.page.locator("#deskSummary .desk-sum__bar").click()
    opened = window.page.evaluate(SUMMARY_FACTS)
    assert (opened["bar"]["expanded"], opened["panel"]["hidden"], opened["bar"]["more"]) == (
        "true", False, less)
    window.page.locator("#deskSummary .desk-sum__close").click()
    closed = window.page.evaluate(SUMMARY_FACTS)
    assert (closed["bar"]["expanded"], closed["panel"]["hidden"]) == ("false", True)
    assert window.page.evaluate(
        "() => document.activeElement.classList.contains('desk-sum__bar')")
    assert window.problems == []


TASKS = {
    "en": {
        "title": "Who did what, and what was done",
        "rows": [
            ("Ship the landing page", "Succeeded · Did: claude-code · Checked: claude-code, "
                                      "codex-cli · Accepted: release-owner", "done"),
            ("Update the API docs", "Not started", None),
            ("Import the export", "Waiting for your decision", "amber"),
            ("Fix lost text", "Running", "ion")]},
    "ru": {
        "title": "Кто что делал и сделал",
        "rows": [
            ("Ship the landing page", "Успешно · Сделал: claude-code · Проверил: claude-code, "
                                      "codex-cli · Принял: release-owner", "done"),
            ("Update the API docs", "Не запущена", None),
            ("Import the export", "Ждёт вашего решения", "amber"),
            ("Fix lost text", "Идёт", "ion")]}}


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_panel_lists_each_task_with_its_word_and_what_the_records_say_of_who_did_what(
        desk_in, language):
    window = _open(desk_in, language)
    window.page.locator("#deskSummary .desk-sum__bar").click()
    panel = window.page.evaluate(SUMMARY_FACTS)["panel"]
    assert panel["title"] == TASKS[language]["title"]
    assert [(row["title"], row["what"], row["tone"]) for row in panel["tasks"]] == [
        tuple(row) for row in TASKS[language]["rows"]]
    assert window.problems == []


#: The module in the page, handed a list with two tasks of one title and one it cannot read.
TITLES = """async (language) => {
  const {mountSummary} = await import("/panel/desk-summary.js");
  const mount = document.createElement("section");
  document.body.append(mount);
  const task = (id, title) => ({task_id: id, title, unreadable: title === null,
    created_at: title === null ? null : "2026-08-19T08:00:00Z",
    schema_version: title === null ? null : 1, work_scope: title === null ? null : id});
  const list = [task("task-twin-aaaa1111", "Twin"), task("task-twin-bbbb2222", "Twin"),
    task("task-lost-1234abcd", null), task("task-single", "Single")];
  mountSummary(mount, {locale: language, foreign: false, listed: true, taskId: null,
    tasks: {phase: "ready", list}, runs: {phase: "ready", list: []}, automation: new Map(),
    closing: new Map(), run: {detail: null}});
  return [...mount.querySelectorAll(".desk-sum__task-title")].map((one) => one.textContent);
}"""


@pytest.mark.parametrize("language,lost", [("en", "Unreadable task"), ("ru", "Задача не читается")])
def test_a_repeated_or_unreadable_title_carries_the_tail_of_its_id_as_the_rail_does(
        desk_in, language, lost):
    window = desk_in(language)
    titles = window.page.evaluate(TITLES, language)
    assert titles == ["Twin · aaaa1111", "Twin · bbbb2222", f"{lost} · 1234abcd", "Single"]


def test_the_task_on_the_scene_says_what_its_run_records_before_it_is_finished(desk_in):
    window = _open(desk_in, "en", "task-waiting")
    window.page.locator("#deskSummary .desk-sum__bar").click()
    rows = {row["title"]: row["what"]
            for row in window.page.evaluate(SUMMARY_FACTS)["panel"]["tasks"]}
    assert rows["Import the export"] == (
        "Waiting for your decision · Did: claude-code · Checked: claude-code")
    assert rows["Fix lost text"] == "Running", "a task whose run is not on the scene has no facts"


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_panel_says_the_word_the_rail_says_for_every_task(desk_in, language):
    """Two places name a task's newest run; a drift between them reds here."""
    window = _open(desk_in, language)
    window.page.locator("#deskSummary .desk-sum__bar").click()
    facts = window.page.evaluate(SUMMARY_FACTS)
    words = {title: what for title, what in facts["rail"]}
    for row in facts["panel"]["tasks"]:
        assert row["what"].split(" · ")[0] == words[row["title"]], row


PEOPLE = {
    "en": {"head": "Participants · run run-closed",
           "people": [
               ("claude-dev", "claude-code · Performs", ["Actions: 2", "Documents: artifact-plan"]),
               ("codex-check", "codex-cli · Verifies", ["Checks: 1"])]},
    "ru": {"head": "Участники · запуск run-closed",
           "people": [
               ("claude-dev", "claude-code · Выполняет",
                ["Действий: 2", "Документы: artifact-plan"]),
               ("codex-check", "codex-cli · Проверяет", ["Проверок: 1"])]}}
LAST = {"en": ["08/19 08:51", "08/19 08:48"], "ru": ["19.08 08:51", "19.08 08:48"]}
EXACT = ["2026-08-19T08:51:00Z", "2026-08-19T08:48:00Z"]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_panel_lists_the_participants_of_the_run_with_only_what_the_records_say(
        desk_in, language):
    window = _open(desk_in, language, "task-closed")
    window.page.locator("#deskSummary .desk-sum__bar").click()
    panel = window.page.evaluate(SUMMARY_FACTS)["panel"]
    assert panel["peopleHead"] == PEOPLE[language]["head"]
    assert [(one["name"], one["role"], one["facts"]) for one in panel["people"]] == [
        tuple(row) for row in PEOPLE[language]["people"]]
    assert [one["at"]["text"] for one in panel["people"]] == LAST[language]
    assert [one["at"]["title"] for one in panel["people"]] == EXACT
    assert panel["noRun"] is None


def test_with_no_run_on_the_scene_the_panel_says_so_and_lists_no_participants(desk_in):
    window = _open(desk_in, "en")
    window.page.locator("#deskSummary .desk-sum__bar").click()
    panel = window.page.evaluate(SUMMARY_FACTS)["panel"]
    assert panel["people"] == [] and panel["peopleHead"] is None
    assert panel["noRun"] == "Choose a task to see who works on its run."


def test_an_open_panel_and_its_explanation_survive_a_redraw(desk_in):
    window = _open(desk_in, "en", "task-closed")
    window.page.locator("#deskSummary .desk-sum__bar").click()
    window.page.locator("#deskSummary .desk-sum__how summary").click()
    window.page.evaluate("() => { location.hash = '#lang=en&task=task-closed&theme=dark'; }")
    window.page.wait_for_function(
        "() => document.documentElement.getAttribute('data-theme') === 'dark'")
    facts = window.page.evaluate(SUMMARY_FACTS)
    assert (facts["bar"]["expanded"], facts["panel"]["hidden"]) == ("true", False)
    assert len(facts["panel"]["how"]) == 5
    assert window.page.evaluate(
        "() => document.querySelector('#deskSummary .desk-sum__how').open") is True


HOW = {"en": ["In progress: A run has begun and is not over, and nothing in it asks you: it "
              "goes, or it is paused or parked.",
              "Waiting for you: The task is in your “waiting for you” list: a step, a "
              "confirmation, a resume or a stopped grant.",
              "Closed: The newest run was accepted at its final gate.",
              "Left: Work remains: nothing began yet, the run waits in the queue, or its last "
              "result is not accepted.",
              "Unclear: The records cannot say: a task or run cannot be read, or its state or "
              "outcome is unknown."]}


def test_the_explanation_behind_the_mark_says_each_place_in_words(desk_in):
    window = _open(desk_in, "en")
    window.page.locator("#deskSummary .desk-sum__bar").click()
    assert window.page.evaluate(SUMMARY_FACTS)["panel"]["how"] == HOW["en"]


@pytest.mark.parametrize("task", [None, "task-closed", "task-working", "task-waiting"])
@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_summary_holds_no_machine_word_and_the_page_stores_and_writes_nothing(
        desk_in, language, task):
    window = _open(desk_in, language, task)
    window.page.locator("#deskSummary .desk-sum__bar").click()
    window.page.locator("#deskSummary .desk-sum__how summary").click()
    facts = window.page.evaluate(SUMMARY_FACTS)
    assert not re.search(RAW_TOKENS, facts["text"], re.I), facts["text"]
    assert {method for method, _path in window.asked} == {"GET"}
    assert window.page.evaluate("() => [localStorage.length, sessionStorage.length]") == [0, 0]
    assert window.problems == []


def test_every_control_of_the_summary_clears_44px(desk_in):
    window = _open(desk_in, "en", "task-closed")
    window.page.locator("#deskSummary .desk-sum__bar").click()
    heights = window.page.evaluate("""() => [...document.querySelectorAll(
      "#deskSummary button, #deskSummary summary")].map((node) => [node.className || node.tagName,
      node.getBoundingClientRect().height])""")
    assert len(heights) == 3 and all(height >= 44 for _name, height in heights), heights


# -- a finished run that cannot be read is not counted closed -------------------------------------

def _answer(page, how: str) -> None:
    def handle(route: Route) -> None:
        if how == "refused":
            route.fulfill(status=403, content_type="application/json",
                          body='{"error": {"code": "same_origin_denied"}}')
        else:
            route.abort("failed")
    page.route("**/command/runs/run-closed", handle)


@pytest.mark.parametrize("how", ["refused", "lost"])
def test_a_finished_run_that_cannot_be_read_is_left_and_not_closed(chromium, progress_url, how):
    context = chromium.new_context(viewport={"width": 1280, "height": 900}, timezone_id=ZONE)
    page = context.new_page()
    problems: list[str] = []
    page.on("pageerror", lambda error: problems.append(str(error)))
    _answer(page, how)
    try:
        page.goto(f"{progress_url}#lang=en", wait_until="load")
        page.wait_for_function(WAIT_BAR)
        counts = [(chip["label"], chip["count"])
                  for chip in page.evaluate(SUMMARY_FACTS)["bar"]["chips"]]
    finally:
        context.close()
    assert counts == [("In progress", "1"), ("Waiting for you", "1"), ("Closed", "0"),
                      ("Left", "2")]
    assert problems == []


def test_the_summary_is_drawn_when_its_numbers_are_known_and_not_before(chromium, progress_url):
    context = chromium.new_context(viewport={"width": 1280, "height": 900}, timezone_id=ZONE)
    page = context.new_page()
    held: list[Route] = []
    page.route("**/command/runs/run-closed", lambda route: held.append(route))
    try:
        page.goto(f"{progress_url}#lang=en", wait_until="load")
        page.wait_for_function(
            "() => document.querySelectorAll('#deskRail [data-task-id]').length === 4")
        for _wait in range(200):
            if held:
                break
            page.wait_for_timeout(50)
        assert held, "the closing read of the finished run was never asked"
        waiting = page.evaluate(SUMMARY_FACTS)
        held[0].continue_()
        page.wait_for_function(WAIT_BAR)
        known = page.evaluate(SUMMARY_FACTS)
    finally:
        context.close()
    assert (waiting["children"], waiting["text"]) == (0, "")
    assert known["children"] > 0


#: The widths the shell's own sweep uses at its extremes, and both sides of its 900px break.
WIDTHS = (320, 375, 600, 899, 900, 1280)
OVERFLOW = "() => document.documentElement.scrollWidth - window.innerWidth"


@pytest.mark.parametrize("task", [None, "task-closed"])
def test_the_page_does_not_scroll_sideways_with_the_summary_shut_or_open_at_any_width(
        desk_in, task):
    window = _open(desk_in, "en", task)
    page = window.page
    for opened in (False, True):
        if opened:
            page.locator("#deskSummary .desk-sum__bar").click()
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate(OVERFLOW) <= 0, (opened, width)
    assert window.problems == []


# -- a check that did not pass, and the guard of spec 5.6.8 over the four regions -----------------

NOTE = {"en": "Process exit 0 proves the process finished, not that the work was verified.",
        "ru": "Код завершения 0 подтверждает окончание процесса, "
              "но не независимую проверку результата."}
UNVERIFIED = {"en": "Verification failed", "ru": "Проверка не пройдена"}


def _made_to_say_unverified(route: Route) -> None:
    """The real list, with the waiting run's row saying it finished with a check that failed."""
    body = route.fetch().json()
    for row in body["runs"]:
        if row["run_id"] == "run-waiting":
            row.update(human_state="not_required", last_outcome="verification_failed")
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_check_that_did_not_pass_carries_its_sentence_in_the_same_row_of_the_panel(
        chromium, progress_url, language):
    context = chromium.new_context(viewport={"width": 1280, "height": 900}, timezone_id=ZONE)
    page = context.new_page()
    page.route("**/command/runs", _made_to_say_unverified)
    try:
        page.goto(f"{progress_url}#lang={language}", wait_until="load")
        page.wait_for_function(WAIT_BAR)
        page.locator("#deskSummary .desk-sum__bar").click()
        row = page.evaluate("""() => {
          const item = [...document.querySelectorAll("#deskSummary .desk-sum__task")]
            .find((one) => one.querySelector(".desk-sum__task-title").textContent
              === "Import the export");
          return {what: item.querySelector(".desk-sum__task-what").textContent,
            note: item.querySelector(".desk-sum__task-note")?.textContent ?? null};
        }""")
    finally:
        context.close()
    assert row["note"] == NOTE[language]
    assert row["what"].startswith(UNVERIFIED[language])


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("task", [None, "task-closed", "task-waiting"])
def test_no_region_of_the_desk_carries_a_machine_word_with_every_panel_and_document_open(
        desk_in, language, task):
    """Spec 5.6.8, guard 3: the rail, the feed, the summary and the console."""
    window = _open(desk_in, language, task)
    window.page.locator("#deskSummary .desk-sum__bar").click()
    window.page.evaluate("""() => document
      .querySelectorAll("#deskSummary details, #deskFeed details")
      .forEach((one) => { one.open = true; })""")
    said = window.page.evaluate("""() => Object.fromEntries(
      ["deskRail", "deskFeed", "deskSummary", "deskPult"].map(
        (id) => [id, document.getElementById(id).innerText]))""")
    assert all(text for region, text in said.items() if region != "deskFeed" or task), said
    for region, text in said.items():
        assert not re.search(RAW_TOKENS, text, re.I), (region, text)
    assert window.problems == []


#: The module in the page, handed a finished task whose run was done by two instances of one
#: harness and checked by a third: the panel names a harness once.
SAME_HARNESS = """async (language) => {
  const {mountSummary} = await import("/panel/desk-summary.js");
  const mount = document.createElement("section");
  document.body.append(mount);
  const task = {task_id: "task-one", title: "One", unreadable: false, schema_version: 1,
    created_at: "2026-08-19T08:00:00Z", work_scope: "task-one"};
  const row = {run_id: "run-one", unreadable: false, task_id: "task-one",
    created_at: "2026-08-19T08:00:00Z", human_state: "not_required", open_actions: 0,
    last_outcome: "succeeded"};
  const digest = {run_id: "run-one", closed: true, pass: {pass: 2, bound: 3},
    did: [{instance: "a", harness: "claude-code"}, {instance: "b", harness: "claude-code"}],
    verified: [{instance: "c", harness: "codex-cli"}], accepted: ["owner", "owner-two"]};
  mountSummary(mount, {locale: language, foreign: false, listed: true, taskId: null,
    tasks: {phase: "ready", list: [task]}, runs: {phase: "ready", list: [row]},
    automation: new Map(), closing: new Map([["task-one", digest]]), run: {detail: null}});
  return mount.querySelector(".desk-sum__task-what").textContent;
}"""


@pytest.mark.parametrize("language,said", [
    ("en", "Succeeded · Pass 2 of 3 · Did: claude-code · Checked: codex-cli · "
           "Accepted: owner, owner-two"),
    ("ru", "Успешно · Проход 2 из 3 · Сделал: claude-code · Проверил: codex-cli · "
           "Принял: owner, owner-two")])
def test_a_harness_is_named_once_however_many_instances_of_it_took_part(desk_in, language, said):
    assert desk_in(language).page.evaluate(SAME_HARNESS, language) == said
