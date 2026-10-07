"""What the hub's page does when a person presses a project's action, in a real browser.

Every press is one POST to the hub with the session's token, an exact Origin and a JSON body, and is
shown as done only after the hub's answer and a read of what it holds. An action that changes the
active project asks first, in the words of the spec, and posts nothing until it is confirmed; a stop
cannot be unsaid and says so; a refusal is said in the clause of its code and the page reads again;
a queue is reordered by posting the whole new order. The fake hub checks each POST as the hub does
and records it, so what a test reads back is what was really sent. Every test runs in both
languages.
"""
from __future__ import annotations

from playwright.sync_api import expect

from browser_tests.hub_bench import (HubPage, fixture, hub,  # noqa: F401
                                     hub_page, lang, ready, say)

PROJECTS = fixture("hub_projects.json")
WEB, LANDING, BOT = (row["project_id"] for row in PROJECTS["projects"])
CONFIRM = """() => ({
  box: document.querySelector("#hubConfirm .hub-confirm__box") !== null,
  sentences: [...document.querySelectorAll("#hubConfirm .hub-confirm__box p")].map(
    (n) => n.textContent),
  buttons: [...document.querySelectorAll("#hubConfirm button")].map((n) => [n.dataset.focus,
    n.textContent])})"""


def press(page: HubPage, key: str) -> None:
    page.page.locator(f'[data-focus="{key}"]').click()


def wait_posts(page: HubPage, count: int) -> None:
    for _ in range(80):
        if len(page.hub.posts) >= count:
            return
        page.page.wait_for_timeout(50)
    raise AssertionError(f"{len(page.hub.posts)} posts, not {count}")


def wait_read_beyond(page: HubPage, path: str, reads: int, why: str) -> None:
    """Wait until the hub has been asked `path` more than `reads` times.

    The notice is drawn and the read is started in the same task, but the status text reaches the
    test over the browser's channel and the read reaches the fake hub over HTTP: neither is ahead of
    the other, so a count taken right after the notice may still be the old one.
    """
    for _ in range(80):
        if page.hub.requests(path) > reads:
            return
        page.page.wait_for_timeout(50)
    raise AssertionError(f"{why}: {path} was asked {page.hub.requests(path)} times, not more "
                         f"than {reads}")


def test_make_active_asks_first_when_another_project_works_and_posts_nothing_until_confirmed(
        hub_page):
    page = hub_page
    ready(page)
    press(page, f"act:{BOT}:activate")
    facts = page.page.evaluate(CONFIRM)
    assert facts["sentences"] == [say(page, "hub.confirm.switch", name="web-app")]
    assert facts["buttons"] == [["confirm:yes", say(page, "hub.act.activate")],
                                ["confirm:no", say(page, "hub.confirm.cancel")]]
    assert page.hub.posts == [], "nothing is written before the question is answered"
    press(page, "confirm:no")
    expect(page.page.locator("#hubConfirm .hub-confirm__box")).to_have_count(0)
    assert page.hub.posts == []
    press(page, f"act:{BOT}:activate")
    reads = page.hub.requests("/hub/projects")
    press(page, "confirm:yes")
    expect(page.page.locator("#hubStatus")).to_have_text(say(page, "hub.notice.accepted"))
    assert page.hub.posts == [{"path": f"/hub/projects/{BOT}/activate", "body": {}}]
    wait_read_beyond(page, "/hub/projects", reads, "what was done is read, not assumed")
    expect(page.page.locator("#hubConfirm .hub-confirm__box")).to_have_count(0)


def test_stopping_the_active_project_asks_first_names_the_next_one_and_cannot_be_unsaid(hub_page):
    page = hub_page
    ready(page)
    press(page, f"act:{WEB}:stop")
    facts = page.page.evaluate(CONFIRM)
    assert facts["sentences"] == [say(page, "hub.confirm.stop"),
                                  say(page, "hub.confirm.stop_next", name="landing")]
    assert facts["buttons"][0] == ["confirm:yes", say(page, "hub.act.stop")]
    assert page.hub.posts == []
    press(page, "confirm:yes")
    wait_posts(page, 1)
    assert page.hub.posts == [{"path": f"/hub/projects/{WEB}/stop", "body": {}}]


def test_a_project_nobody_works_beside_is_made_active_with_no_question(hub_page):
    page = hub_page
    idle = fixture("hub_projects.json")
    idle["active_project_id"] = None
    idle["projects"][0].update(working="stopped", state="stopped", mode=None, desk_url=None,
                               instance=None, stopped_at="2026-09-29T09:00:00Z")
    page.hub.answer("/hub/projects", idle)
    page.page.reload()
    ready(page)
    press(page, f"act:{BOT}:activate")
    wait_posts(page, 1)
    assert page.hub.posts == [{"path": f"/hub/projects/{BOT}/activate", "body": {}}]
    expect(page.page.locator("#hubConfirm .hub-confirm__box")).to_have_count(0)


def test_a_refusal_is_said_in_the_clause_of_its_code_and_the_page_reads_again(hub_page):
    page = hub_page
    ready(page)
    page.hub.refuse(f"/hub/projects/{WEB}/stop", 409, "project_busy")
    reads = page.hub.requests("/hub/projects")
    press(page, f"act:{WEB}:stop")
    press(page, "confirm:yes")
    clause = page.page.evaluate("""async () => (await import("/hub/hub-copy.js"))
      .codeWords(document.documentElement.lang, "project_busy")""")
    expect(page.page.locator("#hubStatus")).to_have_text(say(page, "hub.notice.refused",
                                                            reason=clause))
    wait_read_beyond(page, "/hub/projects", reads, "a refusal is followed by a read")
    assert page.hub.posts == [{"path": f"/hub/projects/{WEB}/stop", "body": {}}], (
        "one post went out, and once")


def _stuck_project(page: HubPage) -> None:
    """The third project is one whose stop was not confirmed: its main action is «Recover»."""
    stuck = fixture("hub_projects.json")
    stuck["projects"][2].update(state="stop_uncertain", working="stopped")
    page.hub.answer("/hub/projects", stuck)
    page.page.reload()
    ready(page)


def test_an_action_the_hub_does_not_have_in_this_build_is_said_as_that_and_not_as_a_bad_address(
        hub_page):
    page = hub_page
    _stuck_project(page)
    page.hub.refuse(f"/hub/projects/{BOT}/recover", 404, "route_not_found",
                    {"reason": "not in this build"})
    reads = page.hub.requests("/hub/projects")
    press(page, f"act:{BOT}:recover")
    expect(page.page.locator("#hubStatus")).to_have_text(say(page, "hub.notice.not_built"))
    assert page.hub.posts == [{"path": f"/hub/projects/{BOT}/recover", "body": {}}], (
        "one post went out, once, and the hub refused it")
    wait_read_beyond(page, "/hub/projects", reads, "a refusal is followed by a read")


def test_a_route_that_is_not_found_for_any_other_reason_keeps_the_clause_of_its_code(hub_page):
    page = hub_page
    _stuck_project(page)
    page.hub.refuse(f"/hub/projects/{BOT}/recover", 404, "route_not_found",
                    {"reason": "a path nobody has"})
    press(page, f"act:{BOT}:recover")
    clause = page.page.evaluate("""async () => (await import("/hub/hub-copy.js"))
      .codeWords(document.documentElement.lang, "route_not_found")""")
    expect(page.page.locator("#hubStatus")).to_have_text(say(page, "hub.notice.refused",
                                                            reason=clause))


def test_raising_a_queued_project_posts_the_whole_new_order_of_the_queue(hub_page):
    page = hub_page
    two = fixture("hub_projects.json")
    two["project_queue"] = [LANDING, BOT]
    two["projects"][2].update(working="queued", queue_position=2)
    page.hub.answer("/hub/projects", two)
    page.page.reload()
    ready(page)
    facts = page.page.evaluate("""() => [...document.querySelectorAll(".hub-project")].map(
      (n) => [n.dataset.projectId, [...n.querySelectorAll(".hub-project__act")].map(
        (b) => b.dataset.action)])""")
    assert facts[1:] == [[LANDING, ["lower", "clear_flag"]], [BOT, ["raise", "clear_flag"]]]
    press(page, f"act:{BOT}:raise")
    wait_posts(page, 1)
    assert page.hub.posts == [{"path": "/hub/queue/order", "body": {"order": [BOT, LANDING]}}]


def test_a_project_in_view_says_who_is_in_progress_and_offers_to_make_it_active(hub_page):
    page = hub_page
    view = fixture("hub_projects.json")
    view["projects"][2].update(working="view", state="running", mode="view",
                               instance="c" * 32, data="live", resume_run_id="run-9",
                               desk_url="http://127.0.0.1:7702/panel/desk.html")
    page.hub.answer("/hub/projects", view)
    page.page.reload()
    ready(page)
    press(page, f"project:{BOT}")
    bar = page.page.evaluate("""() => ({text: document.querySelector("#hubActions .hub-view")
      ?.firstElementChild.textContent ?? null, button: document.querySelector(
        '#hubActions .hub-view [data-focus="view:activate"]')?.textContent ?? null})""")
    assert bar == {"text": say(page, "hub.view.with_active", name="web-app"),
                   "button": say(page, "hub.act.activate")}, (
        "a run to resume does not turn «Make active» into «Continue» for a project in view")
    press(page, "view:activate")
    assert page.page.evaluate(CONFIRM)["sentences"] == [
        say(page, "hub.confirm.switch", name="web-app")]
    press(page, "confirm:yes")
    wait_posts(page, 1)
    assert page.hub.posts == [{"path": f"/hub/projects/{BOT}/activate", "body": {}}]


def test_a_menu_opens_for_one_project_and_offers_the_actions_that_hold_for_it(hub_page):
    page = hub_page
    ready(page)
    press(page, f"menu:{BOT}")
    items = page.page.evaluate("""() => [...document.querySelectorAll(
      ".hub-project__items button")].map((b) => b.dataset.focus)""")
    assert items == [f"act:{BOT}:view_open", f"act:{BOT}:forget"]
    press(page, f"act:{BOT}:view_open")
    wait_posts(page, 1)
    assert page.hub.posts == [{"path": f"/hub/projects/{BOT}/view", "body": {}}]
    expect(page.page.locator(".hub-project__items")).to_have_count(0)
