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
- the desk reads the project claim first, then `/command/tasks`, `/command/runs`, the project
  queue `/command/queue` and the automation of the newest run of each task that has one -- no
  other route, no method but GET,
  no project header (this server serves no identified project), nothing stored;
- a refused or unanswered list read empties the rail and says so, and an automation read that
  fails changes only the row it belongs to;
- a record the server cannot read is never drawn as "not started": one unreadable run row makes
  every row say so and the scene say the newest run cannot be established, and an unreadable
  task says so on its row and on the scene, with no run and no automation read for it;
- pressing a row marks it and only it, and keeps the keyboard's place across the redraw.

A fact and its sentence are read in ONE evaluation, as `test_desk_shell.py` does.
"""
from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, Route

from conductor import server
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from browser_tests.test_desk_shell import LAYOUT_FACTS, SWEPT_WIDTHS
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


Rewrites = dict[str, Callable[[dict], None]]


def _rewriting(edit: Callable[[dict], None]) -> Callable[[Route], None]:
    """A route handler that answers with the real body, `edit` applied to it in flight."""
    def handle(route: Route) -> None:
        body = route.fetch().json()
        edit(body)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    return handle


def _open(browser: Browser, url: str, language: str, *, width: int = 1280,
          rewrite: Rewrites | None = None) -> Window:
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    window = Window(page)
    page.on("console", lambda message: window.problems.append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: window.problems.append(str(error)))
    page.on("request", lambda request: window.asked.append(
        (request.method, urlsplit(request.url).path, "x-conduct-project" in request.headers)))
    for pattern, edit in (rewrite or {}).items():
        page.route(pattern, _rewriting(edit))
    # These projection cases judge one set of reads and an unconfirmed scene.
    # HTTP 204 deliberately ends EventSource without retry; live updates and
    # reconnect are exercised against real SSE in test_desk_live_stream.py.
    page.route("**/events", lambda route: route.fulfill(status=204))
    page.goto(f"{url}#lang={language}", wait_until="load")
    page.wait_for_function(SETTLED)
    page.wait_for_selector('#deskShell[data-connection="closed"]')
    return window


@pytest.fixture
def desk_in(chromium: Browser, seeded_url: str) -> Iterator:
    """A factory of booted windows, each closed when the test is over."""
    opened: list[Window] = []

    def make(language: str = "en", *, width: int = 1280, rewrite: Rewrites | None = None
             ) -> Window:
        opened.append(_open(chromium, seeded_url, language, width=width, rewrite=rewrite))
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
    asked = [(method, path, header) for method, path, header in window.asked
             if path.startswith("/command/")]
    assert asked[0] == ("GET", "/command/project", False), "the claim is the first read"
    assert sorted(asked) == sorted(
        [("GET", "/command/project", False), ("GET", "/command/tasks", False),
         ("GET", "/command/runs", False), ("GET", "/command/queue", False)]
        + [("GET", f"/command/runs/{run}/automation", False) for run in NEWEST.values()])
    assert {method for method, _path, _header in window.asked} == {"GET"}
    assert window.page.evaluate("() => [localStorage.length, sessionStorage.length]") == [0, 0]
    assert window.problems == []


def _end_the_stream(page: Page) -> None:
    """Answer the projection stream with HTTP 204, as `_open` does: it ends without a retry.

    A live stream that opens refreshes every read the desk made, so a window that holds or
    rewrites a read of its own would meet the desk's refresh as well: a second read of the
    same run taken for the person's, and a rewritten read still in flight when the window
    closes. Live updates and reconnect are judged in test_desk_live_stream.py.
    """
    page.route("**/events", lambda route: route.fulfill(status=204))


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


def _name_another_run(body: dict) -> None:
    body["run_id"] = "run-other"


def test_an_automation_answer_that_names_another_run_is_dropped(desk_in):
    """A body for a run the desk did not ask about is not the automation of the row's run.

    Only `run_id` is rewritten, so the answer is otherwise the real one, which earns the row
    "Not started"; dropped, the row falls to the word an unread automation gives (the same
    fall as a lost read) and no other row changes.
    """
    window = desk_in("en", rewrite={"**/command/runs/run-docs/automation": _name_another_run})
    facts = window.page.evaluate(RAIL_FACTS)
    rows = _rows(facts)
    assert rows["task-docs"] == ("Write the docs", "No result yet", None)
    assert {key: value for key, value in rows.items() if key != "task-docs"} == {
        key: value for key, value in ROWS["en"].items() if key != "task-docs"}
    assert (facts["rail"], facts["shell"]) == ("ready", "ready")
    assert window.problems == []


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
        _end_the_stream(page)
        try:
            page.goto(f"{seeded_url}#lang={language}", wait_until="load")
            page.wait_for_function(SETTLED)
            facts = page.evaluate(RAIL_FACTS)
        finally:
            context.close()
        assert _rows(facts)["task-check"] == ("Check the export", word, note)
        assert not RAW_TOKENS.search(facts["text"]), facts["text"]


# -- a record the server cannot read is never a task that has not started ---------------------
#
# The server lists a record it cannot read with every field but its id null and `unreadable`
# true. The rewrites below make the real answer say that for one run row and for one task, in
# flight, so the page is asked about the shape the server really gives and not about one the
# test invented: the keys are the real row's own.
#: The word every row that cannot be read says, and the name such a task is drawn under.
UNREADABLE_WORD = {"en": "Record cannot be read", "ru": "Запись не читается"}
UNREADABLE_TITLE = {"en": "Unreadable task", "ru": "Задача не читается"}
RUNS_ROUTE, TASKS_ROUTE = "**/command/runs", "**/command/tasks"
#: The task whose record is made unreadable, and the run whose record is.
LOST_TASK, LOST_RUN = "task-fix", "run-docs"


def _make_unreadable(rows: list[dict], key: str, ident: str) -> None:
    for row in rows:
        if row[key] == ident:
            row.update({name: None for name in row if name != key}, unreadable=True)


def _one_run_unreadable(body: dict) -> None:
    _make_unreadable(body["runs"], "run_id", LOST_RUN)


def _one_task_unreadable(body: dict) -> None:
    _make_unreadable(body["tasks"], "task_id", LOST_TASK)


def _reads(window: Window, *, automation: bool) -> list[str]:
    """The run routes the window asked for: every automation read, or every other run read."""
    return sorted(path for _method, path, _header in window.asked
                  if path.startswith("/command/runs/")
                  and path.endswith("/automation") == automation)


@pytest.mark.parametrize("language", ["en", "ru"])
def test_one_unreadable_run_record_makes_every_rail_row_say_the_record_cannot_be_read(
        desk_in, language):
    """A run row that does not read hides whose it is and when it was made, so the newest run
    of NO task can be established: every row says so, and none says it has not started."""
    window = desk_in(language, rewrite={RUNS_ROUTE: _one_run_unreadable})
    facts = window.page.evaluate(RAIL_FACTS)
    assert sorted(row["id"] for row in facts["rows"]) == sorted(task for task, _ in TASKS)
    assert {row["word"] for row in facts["rows"]} == {UNREADABLE_WORD[language]}
    assert (facts["shell"], facts["rail"]) == ("ready", "ready")
    assert not RAW_TOKENS.search(facts["text"]) and "_unreadable" not in facts["text"]
    assert _reads(window, automation=True) == []
    assert window.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_an_unreadable_task_says_the_record_cannot_be_read_and_its_run_is_not_asked_about(
        desk_in, language):
    window = desk_in(language, rewrite={TASKS_ROUTE: _one_task_unreadable})
    facts = window.page.evaluate(RAIL_FACTS)
    rows = _rows(facts)
    assert rows[LOST_TASK] == (f"{UNREADABLE_TITLE[language]} · {LOST_TASK}",
                               UNREADABLE_WORD[language], None)
    assert {key: row for key, row in rows.items() if key != LOST_TASK} == {
        key: row for key, row in ROWS[language].items() if key != LOST_TASK}
    assert (facts["shell"], facts["rail"]) == ("ready", "ready")
    assert not RAW_TOKENS.search(facts["text"]) and "_unreadable" not in facts["text"]
    assert _reads(window, automation=True) == sorted(
        f"/command/runs/{run}/automation" for task, run in NEWEST.items() if task != LOST_TASK)
    assert window.problems == []


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


# -- the scene: the newest run of the chosen task, drawn by the Studio's own modules -------------
#
# The scene mounts `participantDeck`, so what these tests hold is that the desk hands it the
# right run, in the right language, and keeps hold of the answer only while it is the current
# one; the deck's own inner workings are the Studio's and have their own browser modules.
FIX_STEPS = 8
#: What the scene of `task-fix` (its newest run stands at the Confirm gate) says, per language.
#: This fixture refuses its stream with HTTP 204, so the gate is said
#: as `unconfirmed` (the Studio's own word for a decision it cannot vouch for), not as a
#: decision needed.
SCENE_WORDS = {
    "en": {"team": "Run team", "lenses": ["Trace", "Orbit"], "unconfirmed": "Attention unconfirmed",
           "subject": "Fix lost text · run run-fix-new", "none": "This task has no run yet.",
           "choose": "Choose a task to see its newest run.",
           "unknown": "The newest run of this task cannot be established: a run record "
                      "cannot be read.",
           "unreadable": "This task cannot be read, so there is no run to show."},
    "ru": {"team": "Команда запуска", "lenses": ["Трасса", "Орбита"],
           "unconfirmed": "Участие не подтверждено",
           "subject": "Fix lost text · запуск run-fix-new",
           "none": "У этой задачи ещё нет запусков.",
           "choose": "Выберите задачу, чтобы увидеть её новейший запуск.",
           "unknown": "Новейший запуск задачи не установлен: одна из записей запусков "
                      "не читается.",
           "unreadable": "Задача не читается, показывать нечего."},
}
#: Everything the scene tests ask of the page, in one evaluation.
SCENE_FACTS = """() => {
  const deck = document.querySelector("#deskScene [data-deck-run]");
  const trace = document.querySelector("#deskScene .studio-trace");
  const fleet = document.querySelector("#deskScene .studio-deck__fleet");
  const lens = (name) => document.querySelector(`#deskScene [data-run-lens="${name}"]`);
  const lenses = [lens("trassa"), lens("orbit")];
  return {
    shell: document.getElementById("deskShell").getAttribute("data-state"),
    scene: document.getElementById("deskScene").getAttribute("data-state"),
    said: document.getElementById("deskStatus").innerText.trim(),
    text: document.getElementById("deskScene").innerText,
    run: deck ? deck.dataset.deckRun : null, lens: deck ? deck.dataset.deckLens : null,
    team: deck ? deck.querySelector("h3").textContent : null,
    subject: document.querySelector("#deskScene .desk-scene__subject")?.textContent ?? null,
    lenses: lenses.map((node) => node && node.textContent),
    pressed: lenses.map((node) => node && node.getAttribute("aria-pressed")),
    traceShown: Boolean(trace) && !trace.hidden && trace.getBoundingClientRect().height > 0,
    fleetShown: Boolean(fleet) && !fleet.hidden && fleet.getBoundingClientRect().height > 0,
    steps: document.querySelectorAll("#deskScene .studio-trace__step").length,
    gates: [...document.querySelectorAll(
      '#deskScene .studio-trace__step[data-word="needs_decision"]')].map((node) => node.innerText),
    unconfirmed: [...document.querySelectorAll(
      '#deskScene .studio-trace__step[data-word="attention_unconfirmed"]')].map(
      (node) => node.innerText),
    planets: [...document.querySelectorAll(
      "#deskScene [data-trassa-instance], #deskScene [data-instance]")].map(
      (node) => ({id: node.dataset.trassaInstance || node.dataset.instance,
        shown: node.getBoundingClientRect().width > 0})),
    chosen: [...document.querySelectorAll("#deskRail [data-task-id]")]
      .filter((node) => node.getAttribute("aria-pressed") === "true")
      .map((node) => node.dataset.taskId)};
}"""
#: The page hooks `Response.json`, so a test can tell the moment an answer it held back has
#: been read by the page -- a signal, never a clock.
LANDING_HOOK = """(() => {
  window.__landed = [];
  const real = Response.prototype.json;
  Response.prototype.json = function () {
    const path = new URL(this.url).pathname;
    return real.call(this).finally(() => window.__landed.push(path));
  };
})();"""
ALL_REGIONS = ["deskRail", "deskScene", "deskFeed", "deskSummary", "deskPult"]


def _choose(page: Page, task_id: str) -> None:
    page.locator(f'#deskRail [data-task-id="{task_id}"]').click()


def _scene_settled(page: Page, word: str) -> None:
    page.wait_for_function(
        "(word) => document.getElementById('deskScene').getAttribute('data-state') === word",
        arg=word)


@pytest.mark.parametrize("language", ["en", "ru"])
def test_choosing_a_task_mounts_the_trace_for_its_newest_run_and_only_reads(desk_in, language):
    window = desk_in(language)
    words = SCENE_WORDS[language]
    before = window.page.evaluate(SCENE_FACTS)
    assert before["scene"] == "empty" and before["text"].strip() == words["choose"]
    _choose(window.page, "task-fix")
    _scene_settled(window.page, "ready")
    facts = window.page.evaluate(SCENE_FACTS)
    assert (facts["run"], facts["lens"], facts["team"]) == ("run-fix-new", "trassa", words["team"])
    assert (facts["shell"], facts["subject"], facts["chosen"]) == (
        "ready", words["subject"], ["task-fix"])
    assert facts["lenses"] == words["lenses"] and facts["pressed"] == ["true", "false"]
    assert facts["traceShown"] and not facts["fleetShown"] and facts["steps"] == FIX_STEPS
    assert facts["gates"] == []
    assert len(facts["unconfirmed"]) == 1 and words["unconfirmed"] in facts["unconfirmed"][0]
    assert [row["id"] for row in facts["planets"] if row["shown"]] == ["claude-dev"]
    # The run, the controls read for it and -- since the desk mounts the acceptance block of a
    # chosen run, which reads the acceptance facts of that run -- the acceptance read.
    detail = sorted(path for _method, path, _header in window.asked
                    if path.startswith("/command/runs/") and not path.endswith("/automation"))
    assert detail == ["/command/runs/run-fix-new", "/command/runs/run-fix-new/accept",
                      "/command/runs/run-fix-new/controls"]
    assert {method for method, _path, _header in window.asked} == {"GET"}
    assert not any(header for _method, _path, header in window.asked)
    assert window.problems == []


def test_the_orbit_lens_shows_the_participants_of_the_run_and_the_trace_gives_way(desk_in):
    window = desk_in("en")
    _choose(window.page, "task-fix")
    _scene_settled(window.page, "ready")
    window.page.locator('#deskScene [data-run-lens="orbit"]').click()
    facts = window.page.evaluate(SCENE_FACTS)
    assert facts["lens"] == "orbit" and facts["pressed"] == ["false", "true"]
    assert facts["fleetShown"] and not facts["traceShown"]
    assert [row["id"] for row in facts["planets"] if row["shown"]] == ["claude-dev"]
    assert window.problems == []


def test_reading_the_same_run_again_keeps_the_lens_a_person_chose_and_another_run_starts_over(
        desk_in):
    window = desk_in("en")
    page = window.page
    _choose(page, "task-fix")
    _scene_settled(page, "ready")
    page.locator('#deskScene [data-run-lens="orbit"]').click()
    _choose(page, "task-fix")
    _scene_settled(page, "ready")
    assert page.evaluate(SCENE_FACTS)["lens"] == "orbit"
    _choose(page, "task-docs")
    _scene_settled(page, "ready")
    assert page.evaluate(SCENE_FACTS)["lens"] == "trassa"
    assert window.problems == []


def test_a_run_read_again_stays_on_screen_as_stale_until_the_new_answer_lands(
        chromium: Browser, seeded_url: str):
    """The earlier drawing is kept and named for what it is, and the shell says so."""
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    uncaught: list[str] = []
    page.on("pageerror", lambda error: uncaught.append(str(error)))
    held: list[Route] = []
    reads: list[str] = []

    def second_read_held(route: Route) -> None:
        reads.append(route.request.url)
        if len(reads) == 1:
            route.continue_()
        else:
            held.append(route)

    page.route("**/command/runs/run-fix-new", second_read_held)
    _end_the_stream(page)
    try:
        page.goto(f"{seeded_url}#lang=en", wait_until="load")
        page.wait_for_function(SETTLED)
        _choose(page, "task-fix")
        _scene_settled(page, "ready")
        with page.expect_request("**/command/runs/run-fix-new"):
            _choose(page, "task-fix")
        _scene_settled(page, "stale")
        stale = page.evaluate(SCENE_FACTS)
        held[0].continue_()
        _scene_settled(page, "ready")
        ready = page.evaluate(SCENE_FACTS)
    finally:
        page.unroute_all(behavior="ignoreErrors")
        context.close()
    assert (stale["scene"], stale["shell"], stale["run"]) == ("stale", "stale", "run-fix-new")
    assert stale["said"] == "Shown from an earlier read; a newer one has not landed."
    assert (ready["scene"], ready["shell"], ready["said"]) == ("ready", "ready", "Read.")
    assert uncaught == []


def test_a_task_with_no_run_says_so_and_choosing_back_restores_the_scene(desk_in):
    window = desk_in("en")
    page = window.page
    _choose(page, "task-idle")
    empty = page.evaluate(SCENE_FACTS)
    assert (empty["scene"], empty["shell"], empty["run"]) == ("empty", "ready", None)
    assert empty["text"].strip() == SCENE_WORDS["en"]["none"]
    assert empty["chosen"] == ["task-idle"]
    _choose(page, "task-fix")
    _scene_settled(page, "ready")
    assert page.evaluate(SCENE_FACTS)["run"] == "run-fix-new"
    _choose(page, "task-docs")
    _scene_settled(page, "ready")
    assert page.evaluate(SCENE_FACTS)["run"] == "run-docs"
    assert window.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_choosing_a_task_amid_an_unreadable_run_record_says_its_newest_run_cannot_be_established(
        desk_in, language):
    """With one run row unreadable no task's newest run can be told, so the scene says that and
    draws nothing -- not "no run yet", and no run is read for the task chosen."""
    window = desk_in(language, rewrite={RUNS_ROUTE: _one_run_unreadable})
    _choose(window.page, "task-fix")
    facts = window.page.evaluate(SCENE_FACTS)
    assert (facts["scene"], facts["shell"], facts["run"]) == ("empty", "ready", None)
    assert facts["text"].strip() == SCENE_WORDS[language]["unknown"]
    assert facts["chosen"] == ["task-fix"]
    assert _reads(window, automation=False) == [] and _reads(window, automation=True) == []
    assert window.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_choosing_an_unreadable_task_says_there_is_no_run_to_show_and_reads_none(
        desk_in, language):
    window = desk_in(language, rewrite={TASKS_ROUTE: _one_task_unreadable})
    _choose(window.page, LOST_TASK)
    facts = window.page.evaluate(SCENE_FACTS)
    assert (facts["scene"], facts["shell"], facts["run"]) == ("empty", "ready", None)
    assert facts["text"].strip() == SCENE_WORDS[language]["unreadable"]
    assert facts["chosen"] == [LOST_TASK]
    assert _reads(window, automation=False) == []
    assert window.problems == []


def test_a_late_answer_for_a_task_left_behind_never_lands(chromium: Browser, seeded_url: str):
    """The read of `run-fix-new` is held; another task is chosen and drawn; the held one is
    then let go and read by the page -- and the scene stays the other task's."""
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    uncaught: list[str] = []
    page.on("pageerror", lambda error: uncaught.append(str(error)))
    page.add_init_script(LANDING_HOOK)
    held: list[Route] = []
    page.route("**/command/runs/run-fix-new", lambda route: held.append(route))
    _end_the_stream(page)
    try:
        page.goto(f"{seeded_url}#lang=en", wait_until="load")
        page.wait_for_function(SETTLED)
        with page.expect_request("**/command/runs/run-fix-new"):
            _choose(page, "task-fix")
        _scene_settled(page, "loading")
        assert len(held) == 1
        _choose(page, "task-docs")
        _scene_settled(page, "ready")
        held[0].continue_()
        page.wait_for_function("() => window.__landed.includes('/command/runs/run-fix-new')")
        facts = page.evaluate(SCENE_FACTS)
    finally:
        page.unroute_all(behavior="ignoreErrors")
        context.close()
    assert (facts["run"], facts["scene"], facts["chosen"]) == ("run-docs", "ready", ["task-docs"])
    assert facts["subject"] == "Write the docs · run run-docs"
    assert uncaught == []


@pytest.mark.parametrize("how,word,said", [
    ("refused", "refused", "This read was refused. Nothing below is newer than the refusal."),
    ("unanswered", "failed", "This read failed. Nothing below is newer than the failure."),
], ids=["refused", "unanswered"])
def test_a_run_read_that_is_not_answered_leaves_the_scene_empty_in_the_word_it_earned(
        chromium: Browser, seeded_url: str, how: str, word: str, said: str):
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    uncaught: list[str] = []
    page.on("pageerror", lambda error: uncaught.append(str(error)))
    _answer(page, "**/command/runs/run-fix-new", how)
    _end_the_stream(page)
    try:
        page.goto(f"{seeded_url}#lang=en", wait_until="load")
        page.wait_for_function(SETTLED)
        _choose(page, "task-fix")
        _scene_settled(page, word)
        facts = page.evaluate(SCENE_FACTS)
    finally:
        context.close()
    assert (facts["scene"], facts["shell"], facts["said"]) == (word, word, said)
    assert facts["run"] is None and facts["text"].strip() == ""
    assert facts["chosen"] == ["task-fix"]
    assert uncaught == []


def test_a_run_of_another_task_is_never_drawn_as_the_chosen_ones(
        chromium: Browser, seeded_url: str):
    """The run read names the task it belongs to; an answer for another task is refused."""
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    problems: list[str] = []
    page.on("console", lambda message: problems.append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))

    def wrong_task(route: Route) -> None:
        # Rewritten whole and consistently, so the Studio's boundary finds nothing torn and
        # only the desk's own check of whose run this is can refuse it.
        body = route.fetch().json()
        body["config"]["task"] = {"id": "task-docs", "work_scope": "task-docs"}
        body["task"] = {"id": "task-docs", "title": "Write the docs", "unreadable": False,
                        "work_scope": "task-docs"}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route("**/command/runs/run-fix-new", wrong_task)
    _end_the_stream(page)
    try:
        page.goto(f"{seeded_url}#lang=en", wait_until="load")
        page.wait_for_function(SETTLED)
        _choose(page, "task-fix")
        _scene_settled(page, "failed")
        facts = page.evaluate(SCENE_FACTS)
    finally:
        context.close()
    assert facts["run"] is None and facts["shell"] == "failed"
    assert problems == []


def test_the_page_does_not_scroll_sideways_with_a_run_on_the_scene_at_any_swept_width(desk_in):
    window = desk_in("en")
    page = window.page
    _choose(page, "task-fix")
    _scene_settled(page, "ready")
    for lens in ("trassa", "orbit"):
        page.locator(f'#deskScene [data-run-lens="{lens}"]').click()
        for width in SWEPT_WIDTHS:
            page.set_viewport_size({"width": width, "height": 900})
            facts = page.evaluate(LAYOUT_FACTS, ALL_REGIONS)
            assert facts["overflow"] <= 0, (lens, width, facts["overflow"])
    assert window.problems == []
