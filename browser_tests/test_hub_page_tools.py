"""What the hub's page does with the tools it is asked to pin, in a real browser.

`GET /hub/setup` lists, for a tool that is not settled, the candidates the hub found: an id, the
last folder and file, the version the tool said. The page shows each as `display · version` with a
«Закрепить» beside it, and a press posts `{"candidate_id"}` to the route of that tool and nothing
else: the page never sees or sends a path, and the id is nowhere on the screen. A refusal is said in
its own words: a tool that now says another version than the one shown, a git that is too old, and a
pin FILE that is damaged, unreadable or unwritable, which is never said as the tool's version (lane
H's handoff). The fake hub checks each POST as the hub does and records it. Every test runs in both
languages.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from browser_tests.hub_bench import (HubPage, fixture, hub,  # noqa: F401
                                     hub_page, lang, ready, say)

SETUP = fixture("hub_setup.json")
CAND = SETUP["tools"]["git"]["candidates"][0]["candidate_id"]
PIN = "/hub/tools/git/pin"
TOOLS = '#hubBanners [data-banner="tools"]'
FACTS = """() => [...document.querySelectorAll(
  '#hubBanners [data-banner="tools"] .hub-tool')].map((n) => ({tool: n.dataset.tool,
  state: n.dataset.state, text: n.firstElementChild.textContent,
  candidates: [...n.querySelectorAll(".hub-tool__candidate")].map((c) => [
    c.firstElementChild.textContent, c.querySelector("button").dataset.focus,
    c.querySelector("button").textContent]),
  hint: n.querySelector("small")?.textContent ?? null}))"""
PINNED = {"tool": "git", "state": "pinned", "display": "Git\\cmd\\git.exe", "version": "2.45.2"}


def clause(page: HubPage, code: str) -> str:
    return page.page.evaluate("""async (code) => (await import("/hub/hub-copy.js"))
      .codeWords(document.documentElement.lang, code)""", code)


def settled_setup() -> dict[str, object]:
    """The setup after the pin: both tools pinned, nothing on offer."""
    setup = fixture("hub_setup.json")
    setup["tools"]["git"].update(state="pinned", display="Git\\cmd\\git.exe", version="2.45.2",
                                 candidates=[])
    return setup


def wait_reads(page: HubPage, path: str, count: int) -> None:
    for _ in range(80):
        if page.hub.requests(path) >= count:
            return
        page.page.wait_for_timeout(50)
    raise AssertionError(f"{path} was asked {page.hub.requests(path)} times, not {count}")


def test_a_tool_that_is_not_pinned_shows_its_candidate_by_display_and_version_and_the_hint(
        hub_page):
    page = hub_page
    ready(page)
    [row] = page.page.evaluate(FACTS)
    assert row == {"tool": "git", "state": "not_pinned",
                   "text": say(page, "hub.tool.state.not_pinned", tool="git"),
                   "candidates": [["Git\\cmd\\git.exe · 2.45.2", "pin:git:0",
                                   say(page, "hub.act.pin")]],
                   "hint": say(page, "hub.tool.restart_to_find")}
    expect(page.page.locator(TOOLS)).to_contain_text(say(page, "hub.banner.tools"))
    assert "cand-" not in page.page.content(), "the id of a candidate is nowhere on the screen"
    assert page.hub.posts == [], "nothing is sent by showing the offer"


def test_a_press_posts_only_the_candidate_id_to_the_route_of_its_tool_and_reads_the_setup_again(
        hub_page):
    page = hub_page
    ready(page)
    page.hub.post_answers[PIN] = (200, PINNED)
    page.hub.answer("/hub/setup", settled_setup())
    reads = page.hub.requests("/hub/setup")
    page.page.locator('[data-focus="pin:git:0"]').click()
    expect(page.page.locator("#hubStatus")).to_have_text(say(page, "hub.tool.pinned"))
    assert page.hub.posts == [{"path": PIN, "body": {"candidate_id": CAND}}]
    wait_reads(page, "/hub/setup", reads + 1)
    expect(page.page.locator(TOOLS)).to_have_count(0)


REFUSALS = [
    (409, "git_changed", None, "hub.tool.pin_changed"),
    (409, "git_too_old", None, "hub.tool.pin_too_old"),
    (409, "tool_version_unreadable", {"reason": "corrupt"}, "hub.tool.pin_problem.corrupt"),
    (409, "tool_version_unreadable", {"reason": "unreadable"}, "hub.tool.pin_problem.unreadable"),
    (409, "tool_version_unreadable", {"reason": "unwritable"}, "hub.tool.pin_problem.unwritable"),
]


@pytest.mark.parametrize("status,code,detail,key", REFUSALS, ids=[row[3] for row in REFUSALS])
def test_a_refusal_of_a_pin_is_said_in_its_own_words_and_the_setup_is_read_again(
        hub_page, status, code, detail, key):
    page = hub_page
    ready(page)
    page.hub.refuse(PIN, status, code, detail)
    reads = page.hub.requests("/hub/setup")
    page.page.locator('[data-focus="pin:git:0"]').click()
    expect(page.page.locator("#hubStatus")).to_have_text(say(page, key))
    assert page.hub.posts == [{"path": PIN, "body": {"candidate_id": CAND}}]
    wait_reads(page, "/hub/setup", reads + 1)
    if key.startswith("hub.tool.pin_problem."):
        assert clause(page, "tool_version_unreadable") not in page.page.locator(
            "#hubStatus").text_content(), "a pin file is never said as the tool's version"


@pytest.mark.parametrize("status,code", [
    (404, "candidate_not_found"), (409, "tool_version_unreadable"), (422, "contract_invalid")])
def test_any_other_refusal_of_a_pin_is_said_in_the_clause_of_its_code(hub_page, status, code):
    page = hub_page
    ready(page)
    page.hub.refuse(PIN, status, code)
    page.page.locator('[data-focus="pin:git:0"]').click()
    expect(page.page.locator("#hubStatus")).to_have_text(
        say(page, "hub.notice.refused", reason=clause(page, code)))


def test_a_pinned_tool_that_changed_offers_candidates_without_the_hint_for_a_missing_tool(
        hub_page):
    page = hub_page
    setup = fixture("hub_setup.json")
    setup["tools"]["git"].update(state="changed", display="Git\\cmd\\git.exe", version="2.40.0")
    page.hub.answer("/hub/setup", setup)
    page.page.reload()
    ready(page)
    [row] = page.page.evaluate(FACTS)
    assert (row["state"], row["hint"], len(row["candidates"])) == ("changed", None, 1)
    assert row["text"] == say(page, "hub.tool.state.changed", tool="git")


def test_a_settled_tool_shows_nothing_and_a_pin_file_that_cannot_be_read_offers_no_press(
        hub_page):
    page = hub_page
    page.hub.answer("/hub/setup", settled_setup())
    page.page.reload()
    ready(page)
    expect(page.page.locator(TOOLS)).to_have_count(0)
    unreadable = fixture("hub_setup.json")
    unreadable["tools"]["git"].update(state="unreadable", display=None, version=None)
    page.hub.answer("/hub/setup", unreadable)
    page.page.reload()
    ready(page)
    [row] = page.page.evaluate(FACTS)
    assert row["text"] == say(page, "hub.tool.pin_problem.unreadable")
    assert (row["candidates"], row["hint"]) == ([], None)
    assert page.page.locator('[data-focus^="pin:"]').count() == 0
