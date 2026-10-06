"""The desk's address in a real Chromium: what a hash selects, how it is written back, and the
state a foreign project's hash puts the desk in.

The same production `server.build` over the seeded one-project directory that
`test_desk_rail_scene.py` uses (its tasks and its runs), so every selection here is a real read
of a real route. What this module holds, each as a measurement of the page:

- a hash that names a task, or a task and a run, opens that run at boot; the address the desk
  then holds is the canonical one (the selection it drew, then `lang`), and junk, repeated keys,
  the old `screen` key, an unknown task, and keys that hang on nothing are dropped from it;
- a `hashchange` selects without reloading the document, reads only what a selection reads and
  sends no header; a hash carrying only the language keeps the selection, says the words in the
  new language and re-reads the drawn run in it; a theme sets the root attribute and its absence
  removes it; a hash that arrives before the lists have landed is applied once they have;
- a press writes the address by `replaceState`: no `hashchange`, no new history entry;
- a run of another task that a hash names is refused by the read and kept out of the address;
- a hash that repeats `project`, or claims a project other than the bound one (or any project when
  none is bound), puts the desk in the terminal state "open for another project": one sentence,
  the regions empty, no request, and nothing applied afterwards.

A fact and its sentence are read in ONE evaluation, as `test_desk_shell.py` does.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, Request, Route

from browser_tests.desk_identity import identified_server
from browser_tests.desk_settled import SETTLED, shell_is
from browser_tests.test_desk_rail_scene import (  # noqa: F401  (seeded_url is a fixture)
    _seed, seeded_url)
from tests.test_store import good_lane, write_project

PROJECT_A, PROJECT_B = "a" * 32, "b" * 32
FOREIGN = {"en": "This desk is open for another project. Reload the page to continue.",
           "ru": "Стол открыт для другого проекта. Перезагрузите страницу, чтобы продолжить."}
#: What the scene says of the run it draws, per language.
SUBJECT = {"en": "{task} · run {run}", "ru": "{task} · запуск {run}"}
FIX, DOCS = "Fix lost text", "Write the docs"
#: The body's background under each theme: the concept's `--space` in the light and dark palettes.
LIGHT_BACKGROUND, DARK_BACKGROUND = "rgb(231, 236, 229)", "rgb(5, 9, 8)"
#: A counter of `hashchange` events and a mark of the document, set before the desk's own
#: script runs: a reload changes the mark, and a press that fired `hashchange` moves the count.
INIT = """(() => {
  window.__marker = Math.random();
  window.__hashchanges = 0;
  window.addEventListener("hashchange", () => { window.__hashchanges += 1; });
})();"""
#: Everything a test asks of the page, in one evaluation.
FACTS = """() => {
  const deck = document.querySelector("#deskScene [data-deck-run]");
  const state = (id) => document.getElementById(id).getAttribute("data-state");
  return {
    hash: location.hash, lang: document.documentElement.lang,
    theme: document.documentElement.getAttribute("data-theme"),
    background: getComputedStyle(document.body).backgroundColor,
    shell: state("deskShell"), scene: state("deskScene"), rail: state("deskRail"),
    summary: state("deskSummary"),
    said: document.getElementById("deskStatus").innerText.trim(),
    run: deck ? deck.dataset.deckRun : null,
    subject: document.querySelector("#deskScene .desk-scene__subject")?.textContent ?? null,
    chosen: [...document.querySelectorAll("#deskRail [data-task-id]")]
      .filter((node) => node.getAttribute("aria-pressed") === "true")
      .map((node) => node.dataset.taskId),
    words: [...document.querySelectorAll("#deskRail .desk-task__state")]
      .map((node) => node.textContent),
    railChildren: document.getElementById("deskRail").childElementCount,
    sceneChildren: document.getElementById("deskScene").childElementCount,
    marker: window.__marker, hashchanges: window.__hashchanges, entries: history.length};
}"""
ON_RUN = """(id) => document.querySelector("#deskScene [data-deck-run]")?.dataset.deckRun === id
  && document.getElementById("deskScene")?.getAttribute("data-state") === "ready" """
AT_HASH = "(hash) => location.hash === hash"
#: Two animation frames: whatever a `hashchange` handler does before its first real wait has been
#: done, and any request it made has been asked. A frame boundary, never a clock.
QUIET = """() => new Promise((done) => requestAnimationFrame(
  () => requestAnimationFrame(done)))"""


@dataclass
class Window:
    """One booted desk window on the seeded project and everything it asked."""

    page: Page
    problems: list[str] = field(default_factory=list)
    asked: list[tuple[str, str, bool]] = field(default_factory=list)
    languages: list[tuple[str, str]] = field(default_factory=list)


def _note(window: Window, request: Request) -> None:
    """Record one request: method, path and whether it carried the project header, and the
    language it asked in."""
    path = urlsplit(request.url).path
    window.asked.append((request.method, path, "x-conduct-project" in request.headers))
    window.languages.append((path, request.headers.get("accept-language", "")))


@pytest.fixture(scope="session")
def identified_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The desk at its own address over the same seeded project, served AS the project
    `PROJECT_A`: its claim read says so and it accepts a request that claims it."""
    root = write_project(tmp_path_factory.mktemp("desk-claim"), lanes={"claude": good_lane()})
    _seed(root)
    with identified_server(root, PROJECT_A) as origin:
        yield f"{origin}/panel/desk.html"


@pytest.fixture
def open_desk(chromium: Browser, seeded_url: str,  # noqa: F811
              identified_url: str) -> Iterator[Callable[..., Window]]:
    """A factory of desk windows at a given fragment, each closed when the test is over. A
    window that names a project in its hash is opened on the server that is that project."""
    opened: list[Window] = []

    def make(fragment: str = "", *, before: Callable[[Page], None] | None = None,
             identified: bool = False) -> Window:
        context = chromium.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        window = Window(page)
        opened.append(window)
        page.on("console", lambda message: window.problems.append(message.text)
                if message.type == "error" else None)
        page.on("pageerror", lambda error: window.problems.append(str(error)))
        page.on("request", lambda request: _note(window, request))
        page.add_init_script(INIT)
        # Attribute reads to navigation only. Live SSE is checked separately;
        # HTTP 204 deliberately ends the stream without background retries.
        page.route("**/events", lambda route: route.fulfill(status=204))
        if before is not None:
            before(page)
        page.goto(f"{identified_url if identified else seeded_url}{fragment}",
                  wait_until="load")
        return window

    yield make
    for window in opened:
        window.page.context.close()


def _go(page: Page, fragment: str) -> None:
    """What the hub does to a mounted desk: replace the address, changing only the fragment."""
    page.evaluate("(hash) => location.replace(location.href.split('#')[0] + hash)", fragment)


def _reads(window: Window) -> list[str]:
    """Every `/command/` route asked, in order."""
    return [path for _method, path, _header in window.asked if path.startswith("/command/")]


def _only_gets_and_no_header(window: Window) -> None:
    assert {method for method, _path, _header in window.asked} == {"GET"}
    assert not any(header for _method, _path, header in window.asked)


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_hash_that_names_a_task_and_a_run_opens_that_run_at_boot(open_desk, language):
    window = open_desk(f"#task=task-fix&run=run-fix-old&lang={language}")
    page = window.page
    page.wait_for_function(ON_RUN, arg="run-fix-old")
    facts = page.evaluate(FACTS)
    assert (facts["chosen"], facts["run"]) == (["task-fix"], "run-fix-old")
    assert facts["subject"] == SUBJECT[language].format(task=FIX, run="run-fix-old")
    assert facts["hash"] == f"#task=task-fix&run=run-fix-old&lang={language}"
    detail = sorted(path for path in _reads(window) if path.startswith("/command/runs/")
                    and not path.endswith("/automation"))
    # The run view also reads its acceptance facts (desk-accept-host.js, the «Принять в проект» block).
    assert detail == ["/command/runs/run-fix-old", "/command/runs/run-fix-old/accept",
                      "/command/runs/run-fix-old/controls"]
    _only_gets_and_no_header(window)
    assert page.evaluate("() => [localStorage.length, sessionStorage.length]") == [0, 0]
    assert window.problems == []


def test_a_hash_that_names_only_a_task_opens_its_newest_run_and_the_address_then_names_it(
        open_desk):
    window = open_desk("#task=task-fix")
    window.page.wait_for_function(ON_RUN, arg="run-fix-new")
    window.page.wait_for_function(AT_HASH, arg="#task=task-fix&run=run-fix-new&lang=en")
    facts = window.page.evaluate(FACTS)
    assert (facts["chosen"], facts["run"], facts["lang"]) == (["task-fix"], "run-fix-new", "en")
    assert window.problems == []


#: (row, the hash the desk is opened with, the address it holds once it has applied it, what it
#: has chosen). Each row hands the router something the grammar must drop.
NORMALISED = (
    ("junk-a-repeated-task-and-a-gate-without-a-run",
     "#screen=runs&task=task-fix&task=task-docs&x=1&gate=g1", "#lang=en", []),
    ("the-old-screen-key-and-junk-around-a-task",
     "#screen=runs&junk=1&task=task-docs&lang=en&token=abc",
     "#task=task-docs&run=run-docs&lang=en", ["task-docs"]),
    ("a-run-with-no-task", "#run=run-fix-new&gate=g1", "#lang=en", []),
    ("an-unknown-task", "#task=no-such-task&run=run-fix-new", "#lang=en", []),
)


@pytest.mark.parametrize("opened,held,chosen", [pytest.param(*row[1:], id=row[0])
                                                for row in NORMALISED])
def test_the_desk_holds_the_canonical_address_and_drops_what_the_grammar_refuses(
        open_desk, opened, held, chosen):
    window = open_desk(opened)
    window.page.wait_for_function(AT_HASH, arg=held)
    facts = window.page.evaluate(FACTS)
    assert facts["chosen"] == chosen
    assert facts["shell"] == "ready" and window.problems == []
    if not chosen:
        assert not [path for path in _reads(window) if path.count("/") > 2
                    and not path.endswith("/automation")]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_hashchange_selects_without_reloading_the_document_and_reads_only(
        open_desk, language):
    window = open_desk(f"#task=task-fix&lang={language}")
    page = window.page
    page.wait_for_function(ON_RUN, arg="run-fix-new")
    before = page.evaluate(FACTS)
    asked, read = len(window.asked), len(_reads(window))
    _go(page, f"#task=task-docs&lang={language}")
    page.wait_for_function(ON_RUN, arg="run-docs")
    after = page.evaluate(FACTS)
    assert after["marker"] == before["marker"] and after["hashchanges"] == 1
    assert after["entries"] == before["entries"]
    assert after["chosen"] == ["task-docs"]
    assert after["subject"] == SUBJECT[language].format(task=DOCS, run="run-docs")
    assert after["hash"] == f"#task=task-docs&run=run-docs&lang={language}"
    assert [path for _m, path, _h in window.asked[asked:] if "/panel/" in path] == []
    assert sorted(_reads(window)[read:]) == [
        "/command/runs/run-docs", "/command/runs/run-docs/accept",
        "/command/runs/run-docs/controls"]
    _only_gets_and_no_header(window)
    assert window.problems == []


def test_a_hashchange_that_changes_only_the_run_opens_that_run_of_the_same_task(open_desk):
    window = open_desk("#task=task-fix")
    window.page.wait_for_function(ON_RUN, arg="run-fix-new")
    _go(window.page, "#task=task-fix&run=run-fix-old&lang=en")
    window.page.wait_for_function(ON_RUN, arg="run-fix-old")
    facts = window.page.evaluate(FACTS)
    assert (facts["chosen"], facts["hash"]) == (
        ["task-fix"], "#task=task-fix&run=run-fix-old&lang=en")
    assert window.problems == []


@pytest.mark.parametrize("start,other", [("en", "ru"), ("ru", "en")])
def test_a_hash_with_only_the_language_keeps_the_selection_and_re_reads_the_run_in_it(
        open_desk, start, other):
    window = open_desk(f"#task=task-fix&lang={start}")
    page = window.page
    page.wait_for_function(ON_RUN, arg="run-fix-new")
    before = page.evaluate(FACTS)
    _go(page, f"#lang={other}")
    page.wait_for_function(
        "(lang) => document.documentElement.lang === lang && document.getElementById("
        "'deskScene')?.getAttribute('data-state') === 'ready'", arg=other)
    after = page.evaluate(FACTS)
    assert (after["chosen"], after["run"]) == (before["chosen"], before["run"])
    assert after["subject"] == SUBJECT[other].format(task=FIX, run="run-fix-new")
    assert after["words"] != before["words"]
    assert after["hash"] == f"#task=task-fix&run=run-fix-new&lang={other}"
    reads = [language for path, language in window.languages
             if path == "/command/runs/run-fix-new"]
    assert [value.split(",")[0].split("-")[0] for value in reads] == [start, other]
    assert window.problems == []


def test_the_theme_of_the_hash_sets_the_root_attribute_and_a_hash_without_one_removes_it(
        open_desk):
    window = open_desk("#theme=light&lang=en")
    page = window.page
    page.wait_for_function(SETTLED)
    first = page.evaluate(FACTS)
    assert (first["theme"], first["background"]) == ("light", LIGHT_BACKGROUND)
    _go(page, "#theme=dark&lang=en")
    page.wait_for_function("() => document.documentElement.dataset.theme === 'dark'")
    second = page.evaluate(FACTS)
    assert (second["theme"], second["background"]) == ("dark", DARK_BACKGROUND)
    _go(page, "#lang=en")
    page.wait_for_function("() => !document.documentElement.hasAttribute('data-theme')")
    assert page.evaluate(FACTS)["hash"] == "#lang=en"
    assert window.problems == []


def test_a_press_writes_the_address_without_a_hashchange_or_a_new_history_entry(open_desk):
    window = open_desk("#lang=en")
    page = window.page
    page.wait_for_function(SETTLED)
    before = page.evaluate(FACTS)
    page.locator('#deskRail [data-task-id="task-docs"]').click()
    page.wait_for_function(ON_RUN, arg="run-docs")
    page.wait_for_function(AT_HASH, arg="#task=task-docs&run=run-docs&lang=en")
    after = page.evaluate(FACTS)
    assert after["hashchanges"] == 0 and after["entries"] == before["entries"]
    assert after["marker"] == before["marker"]
    assert window.problems == []


def test_a_run_of_another_task_that_a_hash_names_is_refused_and_kept_out_of_the_address(
        open_desk):
    window = open_desk("#task=task-docs&run=run-fix-new&lang=en")
    window.page.wait_for_function(shell_is("failed"))
    facts = window.page.evaluate(FACTS)
    assert (facts["chosen"], facts["run"], facts["shell"]) == (["task-docs"], None, "failed")
    assert facts["hash"] == "#task=task-docs&lang=en"
    assert window.problems == []


def test_a_hash_that_arrives_before_the_lists_have_landed_is_applied_when_they_have(open_desk):
    held: list[Route] = []
    window = open_desk("#lang=en", before=lambda page: page.route(
        "**/command/tasks", lambda route: held.append(route)))
    page = window.page
    page.wait_for_function(shell_is("loading"))
    _go(page, "#task=task-docs&lang=en")
    page.evaluate(QUIET)
    assert page.evaluate(FACTS)["chosen"] == [] and len(held) == 1
    held[0].continue_()
    page.wait_for_function(ON_RUN, arg="run-docs")
    assert page.evaluate(FACTS)["chosen"] == ["task-docs"]
    assert window.problems == []


# -- the terminal state: the desk is open for another project ----------------------------------
def _foreign(facts: dict, language: str) -> None:
    words = (facts["shell"], facts["rail"], facts["scene"], facts["summary"])
    assert words == ("refused", "empty", "empty", "empty")
    assert facts["said"] == FOREIGN[language]
    # The scene holds the plate: the sentence and the one button that reloads the page.
    assert (facts["railChildren"], facts["sceneChildren"], facts["chosen"]) == (0, 2, [])
    assert facts["run"] is None and facts["subject"] is None


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_repeated_project_at_boot_puts_the_desk_in_the_foreign_state_and_asks_for_nothing(
        open_desk, language):
    fragment = f"#project={PROJECT_A}&project={PROJECT_A}&task=task-fix&lang={language}"
    window = open_desk(fragment)
    window.page.wait_for_function(shell_is("refused"))
    facts = window.page.evaluate(FACTS)
    _foreign(facts, language)
    assert facts["hash"] == fragment
    assert _reads(window) == []
    assert window.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_different_project_in_a_later_hash_stops_the_desk_and_nothing_after_it_applies(
        open_desk, language):
    window = open_desk(f"#project={PROJECT_A}&task=task-fix&lang={language}", identified=True)
    page = window.page
    page.wait_for_function(ON_RUN, arg="run-fix-new")
    assert page.evaluate(FACTS)["hash"] == (
        f"#project={PROJECT_A}&task=task-fix&run=run-fix-new&lang={language}")
    other = f"#project={PROJECT_B}&task=task-docs&lang={language}"
    _go(page, other)
    page.wait_for_function(shell_is("refused"))
    _foreign(page.evaluate(FACTS), language)
    asked = len(window.asked)
    back = f"#project={PROJECT_A}&task=task-docs&lang={language}"
    _go(page, back)
    page.evaluate(QUIET)
    facts = page.evaluate(FACTS)
    _foreign(facts, language)
    assert facts["hash"] == back and len(window.asked) == asked
    assert window.problems == []


def test_a_hash_that_names_no_project_leaves_the_bound_one_in_the_address(open_desk):
    window = open_desk(f"#project={PROJECT_A}&task=task-fix&lang=en", identified=True)
    window.page.wait_for_function(ON_RUN, arg="run-fix-new")
    _go(window.page, "#task=task-docs&lang=en")
    window.page.wait_for_function(ON_RUN, arg="run-docs")
    facts = window.page.evaluate(FACTS)
    assert facts["hash"] == f"#project={PROJECT_A}&task=task-docs&run=run-docs&lang=en"
    assert facts["shell"] == "ready" and window.problems == []


def test_a_project_claimed_by_a_desk_that_bound_none_is_a_foreign_project(open_desk):
    window = open_desk("#task=task-fix&lang=en")
    window.page.wait_for_function(ON_RUN, arg="run-fix-new")
    _go(window.page, f"#project={PROJECT_A}&task=task-docs&lang=en")
    window.page.wait_for_function(shell_is("refused"))
    _foreign(window.page.evaluate(FACTS), "en")
    assert window.problems == []
