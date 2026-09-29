"""The desk shell in a real Chromium, against the real server of a one-project `conduct up`.

`/panel/desk.html` is what a hub mounts, so this is the address it boots at: the
production `server.build` over a seeded project with no provider configured and
no agent running -- the single-project server a person gets from `conduct up`,
answering every request itself. Nothing is fed through a seam; whatever is on
screen arrived through a real read of a real route.

What this module holds, each as a measurement and not a reading of source:

- the page boots with no console error and no uncaught exception, and every file
  its module graph fetches answers 200 (the census is spelled out, not derived
  from the server's own allowlist, which would only agree with itself);
- the five regions of spec 5.1 are mounted, childless, and say in `data-state`
  what became of the read that feeds them: the rail and the summary `ready`, the
  three with no read of their own still `empty`;
- a read that is refused, never answered or abandoned at its deadline puts ITS
  region, and the whole shell and its one sentence, in the word it earned
  (`refused` or `failed`): a shell that wrote `ready` whatever came back would
  pass every check above, because the server answers both reads;
- the shell reads exactly `/command/tasks` and `/command/runs` and writes nothing
  -- no other route, no method but GET, nothing in browser storage. The project
  route and its header are lane H's, and are not faked here;
- the page never scrolls sideways, at the desk's width and stacked under 900px.

A fact and its sentence are read in ONE evaluation: two round trips let a read
land between them (the failure `test_studio_rendered.py` had on CI).
"""
from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, Route

from conductor import server
from tests.test_store import good_lane, write_project

#: Every file the desk page's module graph fetches, with the answer each owes:
#: the page, its sheet and boot module, the transport and the refusal vocabulary
#: it translates with, the reader of the address's language (and the element
#: helper that reader draws its controls with), and the catalogue (with its
#: fourteen copy modules) that says a word in the reader's language.
DESK_BOOT_ASSETS = {
    "desk.html": 200, "desk.css": 200, "desk.js": 200, "desk-transport.js": 200,
    "command-projection.js": 200, "studio-i18n.js": 200,
    "studio-preferences.js": 200, "command-view.js": 200, "desk-copy.js": 200,
    "studio-agents-copy.js": 200, "studio-automation-copy.js": 200,
    "studio-feedback-copy.js": 200, "studio-notice-copy.js": 200,
    "studio-participant-copy.js": 200, "studio-run-docs-copy.js": 200,
    "studio-runform-copy.js": 200, "studio-runs-copy.js": 200,
    "studio-runstep-copy.js": 200, "studio-view-copy.js": 200,
    "studio-workflow-copy.js": 200, "studio-workflow-detail-copy.js": 200,
    "desk-wizard-copy.js": 200,
}
#: The regions, the word each stands in once the reads have landed, and why.
REGION_WORDS = (
    ("deskRail", "ready"),     # fed by the tasks read
    ("deskScene", "empty"),    # follows a chosen task: no read of its own yet
    ("deskFeed", "empty"),     # follows a chosen run
    ("deskSummary", "ready"),  # fed by the runs read
    ("deskPult", "empty"),     # follows the gates of a run
)
#: Every word the page carries itself, read in ONE evaluation: the document's language and
#: title, the note and the link in the top bar, the accessible name of each region and the
#: sentence the top bar says once the reads have landed.
PAGE_WORDS = """() => ({
  lang: document.documentElement.lang, title: document.title,
  note: document.querySelector(".desk-note").innerText.trim(),
  link: document.querySelector(".desk-classic").innerText.trim(),
  labels: ["deskRail", "deskScene", "deskFeed", "deskSummary", "deskPult"].map(
    (id) => document.getElementById(id).getAttribute("aria-label")),
  said: document.getElementById("deskStatus").innerText.trim()})"""
#: What the page says in each language the address can choose, spelled out here and not
#: read back from the catalogue the page loads.
PAGE_LANGUAGES = {
    "en": {
        "lang": "en", "title": "December Command — Desk",
        "note": "The desk is being built: its regions are mounted and stay empty until "
                "their modules land.",
        "link": "Classic panel",
        "labels": ["Tasks", "Scene", "Progress", "Summary", "Your console"],
        "said": "Read."},
    "ru": {
        "lang": "ru", "title": "December Command — Стол",
        "note": "Стол в разработке: его области размещены и остаются пустыми, пока не "
                "появятся их модули.",
        "link": "Прежняя панель",
        "labels": ["Задачи", "Сцена", "Ход работы", "Выжимка", "Ваш пульт"],
        "said": "Данные прочитаны."},
}
#: One evaluation for everything a region test asks: word, children and words.
REGION_FACTS = """(ids) => ({
  shell: document.getElementById("deskShell").getAttribute("data-state"),
  said: document.getElementById("deskStatus").innerText.trim(),
  lang: document.documentElement.lang,
  regions: ids.map((id) => {
    const node = document.getElementById(id);
    return {id, word: node.getAttribute("data-state"),
            children: node.childElementCount, text: node.textContent.trim()};
  })})"""
#: The layout facts, again in one evaluation: where each region stands and by how
#: much the page overflows sideways.
LAYOUT_FACTS = """(ids) => ({
  overflow: document.documentElement.scrollWidth - window.innerWidth,
  boxes: Object.fromEntries(ids.map((id) => {
    const box = document.getElementById(id).getBoundingClientRect();
    return [id, {x: box.x, y: box.y, width: box.width, height: box.height}];
  }))})"""
#: The widths the page is measured at, from a small phone to a wide screen, both sides of the
#: 900px break included, and the largest window that stacks.
SWEPT_WIDTHS = (320, 375, 414, 600, 768, 899, 900, 901, 1024, 1280, 1440, 1920)
STACKED_UP_TO = 900
#: A rule that widens one region only in a window under 400px: the overflow a two-width
#: test at 800 and 1280 cannot see.
PLANTED_NARROW_OVERFLOW = "@media (max-width:400px){.desk-feed{min-width:600px}}"
#: The sentences the top bar says for the two phases a bad read earns, spelled
#: out here and not read back from the catalogue the page loads.
SAID_REFUSED = "This read was refused. Nothing below is newer than the refusal."
SAID_FAILED = "This read failed. Nothing below is newer than the failure."
#: A refusal in the server's own vocabulary: a status and a body whose code the
#: page's refusal table knows. A code it did not know would be read as no answer.
REFUSAL_BODY = json.dumps({"error": {"code": "same_origin_denied"}})
#: The shell is settled when its reads are over: `ready`, `refused` (the server
#: said no) or `failed` (nothing was said). A real signal, never a clock.
SETTLED = """() => ["ready", "refused", "failed"].includes(
  document.getElementById("deskShell").getAttribute("data-state"))"""
#: The page's read deadline is 20 s. A window that must reach it is given timers
#: where anything that long fires after three seconds, so a read nobody answers
#: is abandoned by the page's own deadline instead of after a twenty-second wait.
SHORT_DEADLINE = """(() => {
  const real = window.setTimeout.bind(window);
  window.setTimeout = (fn, ms, ...rest) => real(fn, ms >= 10000 ? 3000 : ms, ...rest);
})();"""
#: How each of the two reads is made to answer, and what the desk must then say:
#: (row name, tasks read, runs read, rail, summary, shell and its sentence).
#: `real` passes through to the server; `refused` is a 403 with a known code;
#: `unanswered` aborts the request; `held` is never answered at all.
PHASE_ROWS = (
    ("refused-then-unanswered", "refused", "unanswered", "refused", "failed",
     "failed", SAID_FAILED),
    ("refused-then-real", "refused", "real", "refused", "ready",
     "refused", SAID_REFUSED),
    ("unanswered-then-real", "unanswered", "real", "failed", "ready",
     "failed", SAID_FAILED),
    ("held-until-the-deadline-then-real", "held", "real", "failed", "ready",
     "failed", SAID_FAILED),
)


@dataclass
class Desk:
    """One booted desk window and everything it said and asked, in order."""

    page: Page
    problems: list[str] = field(default_factory=list)
    served: list[tuple[str, int]] = field(default_factory=list)
    asked: list[tuple[str, str, bool]] = field(default_factory=list)


@pytest.fixture(scope="session")
def desk_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The desk at its own address, over a real seeded one-project server."""
    root = write_project(tmp_path_factory.mktemp("desk-shell"),
                         lanes={"claude": good_lane()})
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


@pytest.fixture
def desk(chromium: Browser, desk_url: str) -> Iterator[Desk]:
    """One isolated desk window, booted: the shell has settled its reads."""
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    window = Desk(page)
    page.on("console", lambda message: window.problems.append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: window.problems.append(str(error)))
    page.on("response", lambda response: window.served.append(
        (response.url, response.status)))
    page.on("request", lambda request: window.asked.append(
        (request.method, urlsplit(request.url).path,
         "x-conduct-project" in request.headers)))
    page.goto(desk_url, wait_until="load")
    # A real signal that the reads settled -- the shell's own word -- never a clock.
    page.wait_for_selector('#deskShell[data-state="ready"]')
    try:
        yield window
    finally:
        context.close()


def test_the_desk_boots_from_its_own_address_with_no_error_and_every_file_answering_200(
        desk: Desk) -> None:
    served = {url.rsplit("/", 1)[1]: status for url, status in desk.served
              if "/panel/" in url}
    assert served == DESK_BOOT_ASSETS
    assert desk.problems == []


def test_the_five_regions_are_mounted_childless_and_the_two_that_are_read_stand_ready(
        desk: Desk) -> None:
    facts = desk.page.evaluate(REGION_FACTS, [ident for ident, _ in REGION_WORDS])
    assert [(row["id"], row["word"]) for row in facts["regions"]] == list(REGION_WORDS)
    assert all(row["children"] == 0 and row["text"] == "" for row in facts["regions"])
    assert facts["shell"] == "ready" and facts["said"] == "Read." and facts["lang"] == "en"
    assert desk.problems == []


def _answer(how: str, held: list[Route]) -> Callable[[Route], None]:
    """The handler that makes one routed read answer the way `how` says."""
    def handle(route: Route) -> None:
        if how == "real":
            route.continue_()
        elif how == "refused":
            route.fulfill(status=403, content_type="application/json", body=REFUSAL_BODY)
        elif how == "unanswered":
            route.abort("failed")
        else:
            held.append(route)
    return handle


@pytest.mark.parametrize(
    "tasks,runs,rail,summary,shell,said",
    [pytest.param(*row[1:], id=row[0]) for row in PHASE_ROWS])
def test_a_refused_or_unanswered_read_puts_its_region_and_the_shell_in_the_word_it_earned(
        chromium: Browser, desk_url: str, tasks: str, runs: str,
        rail: str, summary: str, shell: str, said: str) -> None:
    """Every word here is a read the page did not get, and each row names its own.

    The rail is fed by the tasks read and the summary by the runs read; the shell
    says the worst of the two, in the one sentence a person reads. Two reads that
    fail differently tell `refused` from `failed` on the region they feed and
    `failed` from `ready` on the shell, so a page that wrote one word whatever
    came back, or that mixed the two up, is red on some row.
    """
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    uncaught: list[str] = []
    page.on("pageerror", lambda error: uncaught.append(str(error)))
    if "held" in (tasks, runs):
        page.add_init_script(SHORT_DEADLINE)
    held: list[Route] = []
    page.route("**/command/tasks", _answer(tasks, held))
    page.route("**/command/runs", _answer(runs, held))
    try:
        page.goto(desk_url, wait_until="load")
        page.wait_for_function(SETTLED)
        facts = page.evaluate(REGION_FACTS, [ident for ident, _ in REGION_WORDS])
    finally:
        context.close()
    words = [(row["id"], row["word"]) for row in facts["regions"]]
    assert words == [("deskRail", rail), ("deskScene", "empty"), ("deskFeed", "empty"),
                     ("deskSummary", summary), ("deskPult", "empty")]
    assert all(row["children"] == 0 and row["text"] == "" for row in facts["regions"])
    assert (facts["shell"], facts["said"]) == (shell, said)
    assert uncaught == []


@pytest.mark.parametrize("language", list(PAGE_LANGUAGES))
def test_every_word_the_page_carries_is_said_in_the_language_the_address_chooses(
        chromium: Browser, desk_url: str, language: str) -> None:
    """The page's HTML holds no English: what a reader sees arrives from the catalogue.

    `#lang=en` and `#lang=ru` choose the language, and the document, its title, its note,
    its link and the name of every region follow, together with the sentence the top bar
    says. The English row is what the page said before it had a catalogue, so a page that
    kept its literals would pass it and fail the Russian one.
    """
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    problems: list[str] = []
    page.on("console", lambda message: problems.append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))
    try:
        page.goto(f"{desk_url}#lang={language}", wait_until="load")
        page.wait_for_selector('#deskShell[data-state="ready"]')
        words = page.evaluate(PAGE_WORDS)
    finally:
        context.close()
    assert words == PAGE_LANGUAGES[language]
    assert problems == []


def test_the_shell_reads_the_two_routes_that_exist_and_writes_nothing(desk: Desk) -> None:
    command = [(method, path, header) for method, path, header in desk.asked
               if path.startswith("/command/")]
    assert sorted(command) == [("GET", "/command/runs", False),
                               ("GET", "/command/tasks", False)]
    assert {method for method, _path, _header in desk.asked} == {"GET"}
    assert desk.page.evaluate("() => [localStorage.length, sessionStorage.length]") == [0, 0]
    assert desk.problems == []


def _sweep(page: Page) -> dict[int, dict]:
    """The layout facts at each swept width, one evaluation per width."""
    ids = [ident for ident, _ in REGION_WORDS]
    facts = {}
    for width in SWEPT_WIDTHS:
        page.set_viewport_size({"width": width, "height": 900})
        facts[width] = page.evaluate(LAYOUT_FACTS, ids)
    return facts


def test_the_page_does_not_scroll_sideways_at_any_swept_width_and_stacks_up_to_900px(
        desk: Desk) -> None:
    """Twelve widths from a phone to a wide screen, the two sides of the 900px break included.

    The claim is the sweep's, and it is stated as the sweep: at every width in the table the
    page's scroll width is no wider than the window, and the regions stand in the layout that
    width owes them -- three columns above 900px, one stacked reading order at 900px and under.
    """
    for width, facts in _sweep(desk.page).items():
        boxes = facts["boxes"]
        assert facts["overflow"] <= 0, (width, facts["overflow"])
        assert all(box["width"] > 0 for box in boxes.values()), (width, boxes)
        assert boxes["deskScene"]["y"] < boxes["deskFeed"]["y"] < boxes["deskSummary"]["y"], width
        if width <= STACKED_UP_TO:
            assert boxes["deskRail"]["y"] < boxes["deskScene"]["y"] < boxes["deskPult"]["y"], width
        else:
            assert boxes["deskRail"]["x"] < boxes["deskScene"]["x"] < boxes["deskPult"]["x"], width
            assert boxes["deskRail"]["y"] == boxes["deskPult"]["y"] > 0, width
    assert desk.problems == []


def test_the_sweep_sees_an_overflow_that_only_a_narrow_window_shows(
        chromium: Browser, desk_url: str) -> None:
    """The regression for the old two-width test: a region wider than a phone.

    A rule that widens the feed only under 400px leaves 800px and 1280px, the two widths the
    test used to look at, exactly as they were. Sweeping finds it at 320px and 375px and
    nowhere else, so a page that scrolled sideways on a phone can no longer pass.
    """
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()

    def widen(route: Route) -> None:
        real = route.fetch()
        route.fulfill(response=real, body=real.text() + PLANTED_NARROW_OVERFLOW)

    page.route("**/panel/desk.css", widen)
    try:
        page.goto(desk_url, wait_until="load")
        page.wait_for_selector('#deskShell[data-state="ready"]')
        overflowing = {width for width, facts in _sweep(page).items() if facts["overflow"] > 0}
    finally:
        context.close()
    assert overflowing == {320, 375}
    assert not overflowing & {800, 1280}


def test_the_classic_panel_link_is_a_visible_focusable_target_of_44px(desk: Desk) -> None:
    link = desk.page.locator(".desk-classic")
    assert link.get_attribute("href") == "/panel/index.html"
    link.focus()
    assert desk.page.evaluate(
        "() => document.activeElement.classList.contains('desk-classic')")
    assert link.bounding_box()["height"] >= 44
    assert desk.problems == []
