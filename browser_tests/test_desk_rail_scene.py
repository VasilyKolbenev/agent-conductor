"""The desk's rail on a real one-project server, in Russian and in English.

The production `server.build` over a seeded project, with no provider configured and no
agent running -- the single-project server a person gets from `conduct up`. The project holds
six tasks with the runs they earned: a task whose newest run stands at a human gate (its
older run never started), a task whose run was only planned, a task with no run at all, two
tasks with the same title, and a task whose run, once its row is made to say it had finished
unverified, is the one case a test cannot seed through the real journal (see below).

What this module holds, each as a measurement of the page and not a reading of source:

- the rail lists every task with the word the rules of spec 5.2.1 give its NEWEST run, in the
  reader's language, and the machine words never reach the screen;
- `verification_failed` is never drawn without its sentence in the same row;
- the desk reads `/command/tasks`, `/command/runs` and the automation of the newest run of each
  task that has one -- no other route, no method but GET, no project header, nothing stored;
- a refused or unanswered list read empties the rail and says so, and an automation read that
  fails changes only the row it belongs to;
- pressing a row marks it and only it, and keeps the keyboard's place across the redraw.

A fact and its sentence are read in ONE evaluation, as `test_desk_shell.py` does.
"""
from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, Route

from conductor import server
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from tests.alpha3_graph_artifacts import dalio_definition
from tests.test_command_graph_projection import settle_to_the_confirm_gate
from tests.test_command_run_store import a_run
from tests.test_store import good_lane, write_project

NOW = "2026-08-19T09:00:00Z"
OLDER, NEWER = "2026-08-19T08:00:00Z", "2026-08-19T10:00:00Z"
#: (task id, title): the tasks the project holds. The two twins share a title.
TASKS = (
    ("task-fix", "Fix lost text"), ("task-docs", "Write the docs"),
    ("task-idle", "Tidy up"), ("task-twin-aaaa1111", "Twin"),
    ("task-twin-bbbb2222", "Twin"), ("task-check", "Check the export"),
)
#: What each task's row says in each language: (title as drawn, the word, its sentence).
NOTE_EN = "Process exit 0 proves the process finished, not that the work was verified."
NOTE_RU = ("Код завершения 0 подтверждает окончание процесса, "
           "но не независимую проверку результата.")
ROWS = {
    "en": {
        "task-fix": ("Fix lost text", "Waiting for your decision", None),
        "task-docs": ("Write the docs", "Not started", None),
        "task-idle": ("Tidy up", "Not started", None),
        "task-twin-aaaa1111": ("Twin · aaaa1111", "Not started", None),
        "task-twin-bbbb2222": ("Twin · bbbb2222", "Not started", None),
        "task-check": ("Check the export", "Waiting for your decision", None),
    },
    "ru": {
        "task-fix": ("Fix lost text", "Ждёт вашего решения", None),
        "task-docs": ("Write the docs", "Не запущена", None),
        "task-idle": ("Tidy up", "Не запущена", None),
        "task-twin-aaaa1111": ("Twin · aaaa1111", "Не запущена", None),
        "task-twin-bbbb2222": ("Twin · bbbb2222", "Не запущена", None),
        "task-check": ("Check the export", "Ждёт вашего решения", None),
    },
}
#: The newest run of each task that has one: the only runs whose automation the desk reads.
NEWEST = {"task-fix": "run-fix-new", "task-docs": "run-docs", "task-check": "run-check"}
#: The words the person's screen must never carry (spec 5.2).
RAW_TOKENS = re.compile(r"\b(?:verification_failed|policy|created|ready|empty)\b", re.I)
#: Everything the rail test asks of the page, in one evaluation.
RAIL_FACTS = """() => ({
  shell: document.getElementById("deskShell").getAttribute("data-state"),
  rail: document.getElementById("deskRail").getAttribute("data-state"),
  summary: document.getElementById("deskSummary").getAttribute("data-state"),
  said: document.getElementById("deskStatus").innerText.trim(),
  text: document.getElementById("deskRail").innerText,
  head: document.querySelector("#deskRail .desk-rail__head")?.textContent ?? null,
  rows: [...document.querySelectorAll("#deskRail [data-task-id]")].map((row) => ({
    id: row.dataset.taskId, pressed: row.getAttribute("aria-pressed"),
    title: row.querySelector(".desk-task__title").textContent,
    word: row.querySelector(".desk-task__state").textContent,
    tone: row.querySelector(".desk-task__state").getAttribute("data-tone"),
    note: row.querySelector(".desk-task__note")?.textContent ?? null,
    height: row.getBoundingClientRect().height}))})"""
SETTLED = """() => ["ready", "refused", "failed"].includes(
  document.getElementById("deskShell").getAttribute("data-state"))"""
REFUSAL_BODY = json.dumps({"error": {"code": "same_origin_denied"}})


def _run(store: RunStore, run_id: str, task_id: str, created: str = NOW) -> str:
    """One run of one task with the Dalio plan frozen into it; its config digest."""
    config = {"cycle": {"id": "default-orbit"}, "task": {"id": task_id, "work_scope": task_id},
              "instances": [{"id": "claude-dev", "adapter": "claude-code"}]}
    digest = snapshot_digest(config)
    store.create_run(a_run(run_id=run_id, mode="confirm", config_digest=digest,
                           created_at=created), config)
    store.append(dalio_definition(run_id=run_id))
    return digest


def _seed(root: Path) -> None:
    tasks = TaskStore(root)
    for task_id, title in TASKS:
        tasks.create_task(TaskRecord(task_id, title, task_id, NOW))
    store = RunStore(root)
    _run(store, "run-fix-old", "task-fix", OLDER)
    digest = _run(store, "run-fix-new", "task-fix", NEWER)
    settle_to_the_confirm_gate(store, run_id="run-fix-new", config_digest=digest)
    _run(store, "run-docs", "task-docs")
    digest = _run(store, "run-check", "task-check")
    settle_to_the_confirm_gate(store, run_id="run-check", config_digest=digest)


@pytest.fixture(scope="session")
def seeded_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The desk at its own address, over a real seeded one-project server."""
    root = write_project(tmp_path_factory.mktemp("desk-rail"), lanes={"claude": good_lane()})
    _seed(root)
    httpd = server.build(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}/panel/desk.html"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "desk server did not stop"


@dataclass
class Window:
    """One booted desk window on the seeded project and everything it asked."""

    page: Page
    problems: list[str] = field(default_factory=list)
    asked: list[tuple[str, str, bool]] = field(default_factory=list)


def _open(browser: Browser, url: str, language: str, *, width: int = 1280) -> Window:
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    window = Window(page)
    page.on("console", lambda message: window.problems.append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: window.problems.append(str(error)))
    page.on("request", lambda request: window.asked.append(
        (request.method, urlsplit(request.url).path, "x-conduct-project" in request.headers)))
    page.goto(f"{url}#lang={language}", wait_until="load")
    page.wait_for_function(SETTLED)
    return window


@pytest.fixture
def desk_in(chromium: Browser, seeded_url: str) -> Iterator:
    """A factory of booted windows, each closed when the test is over."""
    opened: list[Window] = []

    def make(language: str = "en", *, width: int = 1280) -> Window:
        opened.append(_open(chromium, seeded_url, language, width=width))
        return opened[-1]

    yield make
    for window in opened:
        window.page.context.close()


def _rows(facts: dict) -> dict[str, tuple[str, str, str | None]]:
    return {row["id"]: (row["title"], row["word"], row["note"]) for row in facts["rows"]}


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_rail_lists_each_task_with_the_word_its_newest_run_earned(desk_in, language):
    window = desk_in(language)
    facts = window.page.evaluate(RAIL_FACTS)
    assert _rows(facts) == ROWS[language]
    assert (facts["shell"], facts["rail"], facts["summary"]) == ("ready",) * 3
    assert not RAW_TOKENS.search(facts["text"]), facts["text"]
    assert window.problems == []


def test_the_tasks_waiting_for_a_person_carry_the_amber_tone_and_every_row_clears_44px(desk_in):
    facts = desk_in("en").page.evaluate(RAIL_FACTS)
    tones = {row["id"]: row["tone"] for row in facts["rows"]}
    assert tones == {"task-fix": "amber", "task-docs": None, "task-idle": None,
                     "task-twin-aaaa1111": None, "task-twin-bbbb2222": None,
                     "task-check": "amber"}
    assert all(row["height"] >= 44 for row in facts["rows"])


def test_the_desk_reads_the_lists_and_the_newest_run_of_each_task_and_writes_nothing(desk_in):
    window = desk_in("en")
    command = sorted((method, path, header) for method, path, header in window.asked
                     if path.startswith("/command/"))
    assert command == sorted(
        [("GET", "/command/tasks", False), ("GET", "/command/runs", False)]
        + [("GET", f"/command/runs/{run}/automation", False) for run in NEWEST.values()])
    assert {method for method, _path, _header in window.asked} == {"GET"}
    assert window.page.evaluate("() => [localStorage.length, sessionStorage.length]") == [0, 0]
    assert window.problems == []


def _answer(page: Page, pattern: str, how: str) -> None:
    def handle(route: Route) -> None:
        if how == "refused":
            route.fulfill(status=403, content_type="application/json", body=REFUSAL_BODY)
        else:
            route.abort("failed")
    page.route(pattern, handle)


@pytest.mark.parametrize("tasks,runs,word,said", [
    ("refused", "real", "refused", "This read was refused. Nothing below is newer than the "
                                   "refusal."),
    ("real", "unanswered", "failed", "This read failed. Nothing below is newer than the "
                                     "failure."),
    ("refused", "unanswered", "failed", "This read failed. Nothing below is newer than the "
                                        "failure."),
], ids=["tasks-refused", "runs-unanswered", "both-lists-lost"])
def test_a_list_that_is_not_read_empties_the_rail_and_the_shell_says_why(
        chromium: Browser, seeded_url: str, tasks: str, runs: str, word: str, said: str):
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    uncaught: list[str] = []
    page.on("pageerror", lambda error: uncaught.append(str(error)))
    if tasks != "real":
        _answer(page, "**/command/tasks", tasks)
    if runs != "real":
        _answer(page, "**/command/runs", runs)
    try:
        page.goto(f"{seeded_url}#lang=en", wait_until="load")
        page.wait_for_function(SETTLED)
        facts = page.evaluate(RAIL_FACTS)
    finally:
        context.close()
    assert (facts["rail"], facts["shell"], facts["said"]) == (word, word, said)
    assert facts["rows"] == [] and facts["text"].strip() == ""
    assert uncaught == []


def test_an_automation_read_that_fails_changes_only_the_row_it_belongs_to(
        chromium: Browser, seeded_url: str):
    """Rule 20 needs the automation, so a task whose read was lost falls to the last rule."""
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    uncaught: list[str] = []
    page.on("pageerror", lambda error: uncaught.append(str(error)))
    _answer(page, "**/command/runs/run-docs/automation", "refused")
    try:
        page.goto(f"{seeded_url}#lang=en", wait_until="load")
        page.wait_for_function(SETTLED)
        facts = page.evaluate(RAIL_FACTS)
    finally:
        context.close()
    rows = _rows(facts)
    assert rows["task-docs"] == ("Write the docs", "No result yet", None)
    assert {key: value for key, value in rows.items() if key != "task-docs"} == {
        key: value for key, value in ROWS["en"].items() if key != "task-docs"}
    assert (facts["rail"], facts["shell"]) == ("ready", "ready")
    assert uncaught == []


def test_a_finished_but_unverified_run_is_never_drawn_without_its_sentence(
        chromium: Browser, seeded_url: str):
    """The one word a test cannot seed through the journal: the run row is made to say it.

    A run whose result was `verification_failed` and that still needs a human at its result
    gate reads `waiting_you` (rule 4 comes first), and once that gate is answered the run has
    moved on. So the newest run's row is rewritten in flight to the state the rules give this
    word -- nothing waiting, nothing open, `verification_failed` its last outcome -- and the
    page is asked to draw it, in both languages, with its sentence in the same row.
    """
    for language, word, note in (("en", "Verification failed", NOTE_EN),
                                 ("ru", "Проверка не пройдена", NOTE_RU)):
        context = chromium.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        def unverified(route: Route) -> None:
            body = route.fetch().json()
            for row in body["runs"]:
                if row["run_id"] == "run-check":
                    row.update(human_state="not_required", last_outcome="verification_failed")
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

        page.route("**/command/runs", unverified)
        try:
            page.goto(f"{seeded_url}#lang={language}", wait_until="load")
            page.wait_for_function(SETTLED)
            facts = page.evaluate(RAIL_FACTS)
        finally:
            context.close()
        assert _rows(facts)["task-check"] == ("Check the export", word, note)
        assert not RAW_TOKENS.search(facts["text"]), facts["text"]


def test_pressing_a_row_marks_it_alone_and_the_keyboard_keeps_its_place(desk_in):
    window = desk_in("en")
    page = window.page
    row = page.locator('#deskRail [data-task-id="task-docs"]')
    row.focus()
    page.keyboard.press("Enter")
    page.wait_for_function(
        """() => document.querySelector('#deskRail [data-task-id="task-docs"]')
           .getAttribute("aria-pressed") === "true" """)
    facts = page.evaluate(RAIL_FACTS)
    assert [row["id"] for row in facts["rows"] if row["pressed"] == "true"] == ["task-docs"]
    assert page.evaluate("() => document.activeElement.dataset.taskId") == "task-docs"
    assert window.problems == []
