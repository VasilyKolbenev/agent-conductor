"""The map of the five tabs' functions against a booted desk (spec 5.6, 5.6.8 guard 2, browser half).

`tests/desk_function_map.py` says, for each of the 70 functions the five tabs had, whether the desk
draws it, has its module waiting for a mount, has none of it, or retired it; `tests/test_desk_function_map.py`
holds those words to the source. This module holds them to a desk in a real browser, on a real
seeded one-project server: what the map says a booted desk draws IS drawn, in both languages, and
what it says is not built is not there: the desk has exactly the five regions, no tab list, no panel
where an address asks for them. The wizard, cycle editor, run panel, queue and stream are mounted;
the old tabs remain absent. The day another surface is built
a row here reds with it, and is moved by the lane that built it.

A fact and its sentence are read in ONE evaluation.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page

from browser_tests.test_desk_rail_scene import SETTLED, _seed
from conductor import server
from tests.desk_function_map import ROWS
from tests.test_store import good_lane, write_project

#: The five regions of the desk (spec 5.1) and nothing else.
REGIONS = ["rail", "scene", "feed", "summary", "pult"]
#: Old Studio tabs still have no surface; wizard, cycle, run and people do.
ABSENT_SURFACES = '[class*="desk-panel"], [data-panel], [role="tablist"], [role="tab"]'
ASKS = [("#panel=cycle", True, False), ("#new=task", False, True),
        ("#task=task-fix&prepare=1", False, True),
        ("#panel=run", False, False), ("#panel=people", False, False),
        ("#workflow=desk-standard", False, False)]
SHOWN = """(selectors) => Object.fromEntries(selectors.map(
  (selector) => [selector, document.querySelectorAll(selector).length]))"""
FACTS = f"""() => ({{regions: [...document.querySelectorAll("[data-region]")].map(
  (node) => node.dataset.region), absent: document.querySelectorAll('{ABSENT_SURFACES}').length,
  flow: !document.getElementById('deskFlow').hidden,
  people: !document.getElementById('deskPeople').hidden,
  run: !document.getElementById('deskRun').hidden,
  wizard: !document.getElementById('deskWizard').hidden,
  connection: document.getElementById('deskConnection').getAttribute('role'),
  hash: location.hash}})"""


@pytest.fixture(scope="module")
def desk_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The desk at its own address over a real seeded one-project server."""
    root = write_project(tmp_path_factory.mktemp("desk-map"), lanes={"claude": good_lane()})
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


def booted(chromium: Browser, url: str, fragment: str) -> tuple[Page, list[str]]:
    """A desk window at `fragment`, settled, and the paths it asked."""
    context = chromium.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    asked: list[str] = []
    page.on("request", lambda request: asked.append(urlsplit(request.url).path))
    page.route("**/events", lambda route: route.fulfill(status=204))
    page.goto(f"{url}{fragment}", wait_until="load")
    page.wait_for_function(SETTLED)
    page.wait_for_selector('#deskShell[data-connection="closed"]')
    return page, asked


@pytest.mark.parametrize("language", ["en", "ru"])
def test_every_function_the_map_puts_on_the_desk_and_can_point_at_is_drawn_by_a_booted_desk(
        chromium, desk_url, language):
    pointed = {row.name: row.selector for row in ROWS
               if row.state == "on_desk" and row.selector is not None}
    assert len(pointed) >= 7, "the rows that name a place to look at"
    page, _asked = booted(chromium, desk_url, f"#task=task-fix&run=run-fix-new&lang={language}")
    try:
        page.wait_for_function("() => document.querySelector('#deskScene [data-deck-run]') !== null")
        shown = page.evaluate(SHOWN, sorted(set(pointed.values())))
        missing = [name for name, selector in pointed.items() if shown[selector] == 0]
        assert missing == [], f"the map says these are drawn and they are not: {missing}"
        assert page.evaluate(SHOWN, ["#nothing-is-here"]) == {"#nothing-is-here": 0}, (
            "the count sees a place that is not there")
    finally:
        page.context.close()


def test_the_surface_check_sees_a_panel_or_tab_that_would_be_added(
        chromium, desk_url):
    page, _asked = booted(chromium, desk_url, "#lang=en")
    try:
        assert page.evaluate(FACTS)["absent"] == 0
        page.evaluate("""() => { for (const markup of ['<div data-panel="run"></div>',
          '<div role="tablist"></div>', '<div class="desk-panel"></div>']) {
            document.body.insertAdjacentHTML("beforeend", markup); } }""")
        assert page.evaluate(FACTS)["absent"] == 3
    finally:
        page.context.close()


@pytest.mark.parametrize("ask,flow,wizard", ASKS)
def test_the_address_opens_only_the_mounted_surface_it_names(
        chromium, desk_url, ask, flow, wizard):
    page, asked = booted(chromium, desk_url, f"{ask}&lang=en" if "&" in ask or "=" in ask else ask)
    try:
        page.evaluate("() => new Promise((done) => requestAnimationFrame(() => "
                      "requestAnimationFrame(done)))")
        facts = page.evaluate(FACTS)
        assert facts["regions"] == REGIONS, "the five regions of the desk and no sixth"
        assert facts["absent"] == 0, "old tabs remain absent"
        assert (facts["flow"], facts["wizard"]) == (flow, wizard)
        assert facts["people"] == (ask == "#panel=people")
        assert facts["run"] == (ask == "#panel=run")
        assert facts["connection"] == "status"
        assert "/events" in asked, "the booted desk opens its projection stream"
    finally:
        page.context.close()


def test_the_rows_that_are_not_on_the_desk_name_an_owner_and_the_five_regions_are_what_remains():
    off = [row for row in ROWS if row.state != "on_desk"]
    assert len(off) >= 16 and all(row.owner in ("D1", "D2") for row in off)
    assert REGIONS == ["rail", "scene", "feed", "summary", "pult"], Path(__file__).name
