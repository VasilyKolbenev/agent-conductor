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

from browser_tests.hub_bench import CSP, FakeHub, HubPage, hub, hub_page, lang  # noqa: F401
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
    rail: document.querySelector(".hub-rail__head").textContent,
    status: document.getElementById("hubStatus").textContent,
    pressed: [...document.querySelectorAll(".hub-seg button")].map((b) => [b.dataset.focus,
      b.getAttribute("aria-pressed")])};
}"""


def say(page: HubPage, key: str, **params: str) -> str:
    """A message of the page's own catalogue, in the language the page is in."""
    return page.page.evaluate("""async ([key, params]) => {
      const copy = await import("/hub/hub-copy.js");
      return copy.hubText(document.documentElement.lang, key, params);
    }""", [key, params])


def test_the_page_boots_under_the_hubs_own_policy_and_says_its_frame_in_its_language(
        hub_page, lang):
    page = hub_page
    expect(page.page.locator("#hubActions .hub-blocked").first).to_be_visible()
    facts = page.page.evaluate(FRAME)
    assert facts["lang"] == lang and facts["title"] == say(page, "hub.page_title")
    assert facts["brand"] == "December Command"
    assert facts["labels"] == [say(page, f"hub.{name}.label") for name in (
        "top", "banners", "confirm", "rail", "center", "side")]
    assert facts["path"] == say(page, "hub.path.none")
    assert facts["actions"] == [
        [say(page, "hub.new_task"), True, say(page, "hub.new_task.blocked")],
        [say(page, "hub.add_project"), True, say(page, "hub.add_project.blocked")]]
    assert facts["rail"].startswith(say(page, "hub.rail.heading", count="0"))
    assert facts["status"] == "", "nothing was read, so nothing is said to have been"
    assert dict(facts["pressed"])[f"seg:lang:{lang}"] == "true"


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
    assert set(page.hub.gets) == {"/", *HUB_ASSETS}, "every file of the registry is used, none else"
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
    assert hub.faults == ["the page asked a child's path: /command/runs"]
    hub.faults.clear()


SIDE = """() => ({center: document.querySelector("#hubCenter [data-case]")?.dataset.case ?? null,
  centerText: document.getElementById("hubCenter").textContent,
  queue: [...document.querySelectorAll("#hubSide [data-queue] > *")].map((n) => n.textContent),
  limits: [...document.querySelectorAll("#hubSide [data-limits] > *")].map(
    (n) => n.textContent)})"""


def test_with_nothing_read_the_centre_asks_for_a_project_and_the_side_says_no_queue_and_no_data(
        hub_page):
    page = hub_page
    facts = page.page.evaluate(SIDE)
    assert facts["center"] == "choose"
    assert facts["centerText"] == say(page, "hub.center.choose")
    assert facts["queue"] == [say(page, "hub.queue.heading"), say(page, "hub.queue.none_active"),
                              say(page, "hub.queue.empty")]
    assert facts["limits"] == [say(page, "hub.limits.heading"), say(page, "hub.limits.none")], (
        "no reading is said as no data, and there is no card for an account nobody read")
