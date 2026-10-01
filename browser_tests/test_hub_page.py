"""The hub's page in a real browser, in both languages, on a fake hub over the contract fixtures.

The bench (`hub_bench.py`) serves the page exactly as the hub will: `GET /` answers `hub.html`,
`/hub/<name>` answers the files of the registry and nothing else, every response carries the hub's
own policy (no inline script or style, frames only of a loopback address, no other origin), and
every POST is checked as the hub checks it and recorded. So what a test reads back is what the page
really asked for and really sent. Every test runs once in English and once in Russian: what is
asserted about a word is asserted against the catalogue's own message for that language, never a
literal, so a missing or swapped message fails in the language it is missing in. A test ends by
asserting that the page raised no error, broke no policy and asked no path the hub does not serve.
"""
from __future__ import annotations

import urllib.error
import urllib.request

from playwright.sync_api import expect

from browser_tests.hub_bench import (CSP, FakeHub, HubPage, hub,  # noqa: F401
                                     hub_page, lang, ready, say)
from conductor.hub.assets import HUB_ASSETS

FRAME = """() => {
  const label = (id) => document.getElementById(id).getAttribute("aria-label");
  const actions = [...document.querySelectorAll("#hubActions .hub-blocked")].map((one) => [
    one.querySelector("button").textContent, one.querySelector("button").disabled,
    one.querySelector("small").textContent]);
  return {lang: document.documentElement.lang, title: document.title,
    brand: document.querySelector(".hub-brand").textContent,
    labels: ["hubTop", "hubBanners", "hubConfirm", "hubRail", "hubCenter", "hubSide"].map(label),
    path: document.getElementById("hubPath").textContent, actions,
    add: [...document.querySelectorAll('#hubActions [data-focus="add-project"]')].map(
      (button) => [button.textContent, button.disabled]),
    rail: document.querySelector(".hub-rail__head").textContent,
    status: document.getElementById("hubStatus").textContent,
    pressed: [...document.querySelectorAll(".hub-seg button")].map((b) => [b.dataset.focus,
      b.getAttribute("aria-pressed")])};
}"""


def test_the_page_boots_under_the_hubs_own_policy_and_says_its_frame_in_its_language(
        hub_page, lang):
    page = hub_page
    ready(page)
    facts = page.page.evaluate(FRAME)
    assert facts["lang"] == lang and facts["title"] == say(page, "hub.page_title")
    assert facts["brand"] == "December Command"
    assert facts["labels"] == [say(page, f"hub.{name}.label") for name in (
        "top", "banners", "confirm", "rail", "center", "side")]
    assert facts["path"] == say(page, "hub.path.none")
    assert facts["actions"] == [
        [say(page, "hub.new_task"), True, say(page, "hub.new_task.blocked")]]
    assert facts["add"] == [[say(page, "hub.add_project"), False]]
    assert facts["rail"].startswith(say(page, "hub.rail.heading", count="3"))
    assert facts["status"] == say(page, "hub.status.ready")
    assert dict(facts["pressed"])[f"seg:lang:{lang}"] == "true"


def test_add_project_shows_the_two_terminal_commands_without_sending_a_path(hub_page, lang):
    page = hub_page
    ready(page)
    page.page.locator('[data-focus="add-project"]').click()
    guide = page.page.locator('[data-banner="first-run"]')
    expect(guide).to_be_visible()
    assert guide.locator("code").all_text_contents() == [
        "conduct providers --profile",
        'conduct projects add --dir "<absolute-folder>" --legacy-writers-stopped']
    assert guide.locator("strong").text_content() == say(page, "hub.first.heading")


def test_a_language_and_a_theme_chosen_on_the_page_are_written_to_its_address_and_say_every_word(
        hub_page, lang):
    page = hub_page
    other = "ru" if lang == "en" else "en"
    page.page.locator(f'[data-focus="seg:lang:{other}"]').click()
    expect(page.page.locator("html")).to_have_attribute("lang", other)
    assert page.page.evaluate("location.hash").count(f"lang={other}") == 1
    assert page.page.evaluate("document.title") == say(page, "hub.page_title")
    page.page.locator('[data-focus="seg:theme:dark"]').click()
    expect(page.page.locator("html")).to_have_attribute("data-theme", "dark")
    assert set(page.page.evaluate("location.hash").lstrip("#").split("&")) == {
        f"lang={other}", "theme=dark"}
    page.page.locator('[data-focus="seg:theme:null"]').click()
    expect(page.page.locator("html")).not_to_have_attribute("data-theme", "dark")
    assert "theme" not in page.page.evaluate("location.hash")
    assert page.page.evaluate("document.activeElement.dataset.focus") == "seg:theme:null", (
        "a pass replaces what it draws and the control that had focus is found again")


def test_the_page_asks_only_for_the_entry_and_the_files_of_the_registry(hub_page):
    page = hub_page
    page.page.wait_for_load_state("networkidle")
    doors = {"/hub/session", "/hub/projects", "/hub/limits", "/hub/setup", "/hub/events"}
    assert set(page.hub.gets) == {"/", *HUB_ASSETS, *doors}, (
        "every file of the registry is used; the reads and the stream are the doors; none else")
    assert page.hub.posts == []


def test_the_fake_hub_serves_the_registry_and_the_entry_and_nothing_else_under_its_policy(hub):
    def get(path: str) -> tuple[int, str]:
        try:
            with urllib.request.urlopen(hub.url + path, timeout=5) as answer:
                return answer.status, answer.headers["Content-Security-Policy"]
        except urllib.error.HTTPError as error:
            return error.code, error.headers["Content-Security-Policy"]

    assert get("/") == (200, CSP) and get("/hub/hub.js") == (200, CSP)
    assert get("/hub/hub.html")[0] == 404, "the entry page is not a row of the registry"
    assert get("/hub/desk-flow.js")[0] == 404 and get("/panel/desk.html")[0] == 404
    assert get("/hub/studio-i18n.js")[0] == 404 and get("/command/runs")[0] == 404
    assert hub.faults == [
        "a path the hub does not serve: /hub/hub.html",
        "a path the hub does not serve: /hub/desk-flow.js",
        "a path the hub does not serve: /panel/desk.html",
        "a path the hub does not serve: /hub/studio-i18n.js",
        "the page asked a child's path: /command/runs",
        "a path the hub does not serve: /command/runs"]
    hub.faults.clear()


SIDE = """() => ({center: document.querySelector("#hubStub [data-case]")?.dataset.case ?? null,
  centerText: document.getElementById("hubStub").textContent,
  queue: [...document.querySelectorAll("#hubSide [data-queue] > *")].map((n) => n.textContent),
  limits: [...document.querySelectorAll("#hubSide [data-limits] > *")].map(
    (n) => n.textContent)})"""


def test_with_nothing_read_the_centre_asks_for_a_project_and_the_side_says_no_queue_and_no_data(
        hub, chromium, lang):
    for path in ("/hub/projects", "/hub/limits", "/hub/setup"):
        hub.answer(path, {"error": {"code": "registry_invalid", "message": "", "detail": None}},
                   status=500)
    context = chromium.new_context(viewport={"width": 1300, "height": 1000}, locale=lang)
    try:
        page = context.new_page()
        page.goto(f"{hub.url}/#lang={lang}", wait_until="load")
        opened = HubPage(page, hub, [])
        expect(page.locator("#hubShell")).to_have_attribute("data-state", "failed")
        facts = page.evaluate(SIDE)
        assert facts["center"] == "choose"
        assert facts["centerText"] == say(opened, "hub.center.choose")
        assert facts["queue"] == [say(opened, "hub.queue.heading"),
                                  say(opened, "hub.queue.none_active"),
                                  say(opened, "hub.queue.empty")]
        assert facts["limits"] == [say(opened, "hub.limits.heading"),
                                   say(opened, "hub.limits.none")], (
            "no reading is said as no data, and there is no card for an account nobody read")
        assert page.evaluate("document.getElementById('hubStatus').textContent") == say(
            opened, "hub.status.failed")
    finally:
        context.close()
