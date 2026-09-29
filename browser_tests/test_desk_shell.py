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
- the shell reads exactly `/command/tasks` and `/command/runs` and writes nothing
  -- no other route, no method but GET, nothing in browser storage. The project
  route and its header are lane H's, and are not faked here;
- the page never scrolls sideways, at the desk's width and stacked under 900px.

A fact and its sentence are read in ONE evaluation: two round trips let a read
land between them (the failure `test_studio_rendered.py` had on CI).
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from tests.test_store import good_lane, write_project

#: Every file the desk page's module graph fetches, with the answer each owes:
#: the page, its sheet and boot module, the transport and the refusal vocabulary
#: it translates with, and the catalogue (with its twelve copy modules) that says
#: a phase in the reader's language.
DESK_BOOT_ASSETS = {
    "desk.html": 200, "desk.css": 200, "desk.js": 200, "desk-transport.js": 200,
    "command-projection.js": 200, "studio-i18n.js": 200,
    "studio-agents-copy.js": 200, "studio-automation-copy.js": 200,
    "studio-feedback-copy.js": 200, "studio-notice-copy.js": 200,
    "studio-participant-copy.js": 200, "studio-run-docs-copy.js": 200,
    "studio-runform-copy.js": 200, "studio-runs-copy.js": 200,
    "studio-runstep-copy.js": 200, "studio-view-copy.js": 200,
    "studio-workflow-copy.js": 200, "studio-workflow-detail-copy.js": 200,
}
#: The regions, the word each stands in once the reads have landed, and why.
REGION_WORDS = (
    ("deskRail", "ready"),     # fed by the tasks read
    ("deskScene", "empty"),    # follows a chosen task: no read of its own yet
    ("deskFeed", "empty"),     # follows a chosen run
    ("deskSummary", "ready"),  # fed by the runs read
    ("deskPult", "empty"),     # follows the gates of a run
)
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


def test_the_five_regions_are_mounted_empty_and_stand_in_the_word_their_read_earned(
        desk: Desk) -> None:
    facts = desk.page.evaluate(REGION_FACTS, [ident for ident, _ in REGION_WORDS])
    assert [(row["id"], row["word"]) for row in facts["regions"]] == list(REGION_WORDS)
    assert all(row["children"] == 0 and row["text"] == "" for row in facts["regions"])
    assert facts["shell"] == "ready" and facts["said"] == "Read." and facts["lang"] == "en"
    assert desk.problems == []


def test_the_shell_reads_the_two_routes_that_exist_and_writes_nothing(desk: Desk) -> None:
    command = [(method, path, header) for method, path, header in desk.asked
               if path.startswith("/command/")]
    assert sorted(command) == [("GET", "/command/runs", False),
                               ("GET", "/command/tasks", False)]
    assert {method for method, _path, _header in desk.asked} == {"GET"}
    assert desk.page.evaluate("() => [localStorage.length, sessionStorage.length]") == [0, 0]
    assert desk.problems == []


def test_the_page_never_scrolls_sideways_and_the_regions_stack_under_900px(
        desk: Desk) -> None:
    ids = [ident for ident, _ in REGION_WORDS]
    wide = desk.page.evaluate(LAYOUT_FACTS, ids)
    boxes = wide["boxes"]
    assert wide["overflow"] <= 0, wide
    # Three columns under the top bar: the rail, the centre, the pult.
    assert boxes["deskRail"]["x"] < boxes["deskScene"]["x"] < boxes["deskPult"]["x"]
    assert boxes["deskRail"]["y"] == boxes["deskPult"]["y"] > 0
    assert boxes["deskScene"]["y"] < boxes["deskFeed"]["y"] < boxes["deskSummary"]["y"]
    desk.page.set_viewport_size({"width": 800, "height": 900})
    narrow = desk.page.evaluate(LAYOUT_FACTS, ids)
    stacked = narrow["boxes"]
    assert narrow["overflow"] <= 0, narrow
    assert stacked["deskRail"]["y"] < stacked["deskScene"]["y"] < stacked["deskPult"]["y"]
    assert all(box["width"] > 0 for box in stacked.values()), stacked
    assert desk.problems == []


def test_the_classic_panel_link_is_a_visible_focusable_target_of_44px(desk: Desk) -> None:
    link = desk.page.locator(".desk-classic")
    assert link.get_attribute("href") == "/panel/index.html"
    link.focus()
    assert desk.page.evaluate(
        "() => document.activeElement.classList.contains('desk-classic')")
    assert link.bounding_box()["height"] >= 44
    assert desk.problems == []
