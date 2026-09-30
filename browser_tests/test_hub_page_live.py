"""The hub's page against the REAL hub, in a real browser, in both languages.

`hub_live.py` builds lane H's own stack (the server with its transport checks and its policy, the
service, the reader, the supervisor and the registry) over a world of fakes that start no process, so
what the page reads is what the hub really answers and what it writes is judged by the hub's own
rules. The fixture bench (`hub_bench.py`) proves the page against the contract; this proves the
contract against the page: the answers are the live ones (`status` of a project that has not run, a
`starting` line after a real `202`, `unlisted_closing` from a real forget, a real `404` for a route
that is not built), and a pass of the hub's loop reaches the page as a frame on the real stream.
Every test runs once in English and once in Russian and ends by asserting that the page raised no
error, broke no policy and asked for nothing outside the hub's entry, its files and its doors.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, expect

from browser_tests.hub_bench import lang, say, watch  # noqa: F401
from browser_tests.hub_live import LiveHub
from browser_tests.test_hub_page_reads import BANNERS, RAIL
from conductor.hub.assets import HUB_ASSETS

A, B, C = (LiveHub.project_id(name) for name in "abc")
DOORS = {"/hub/session", "/hub/projects", "/hub/limits", "/hub/setup", "/hub/events"}
#: What a browser asks of any page by itself and the hub answers with a refusal.
BROWSER_OWN = {"/favicon.ico"}


@dataclass
class LivePage:
    """One page on the real hub, in one language, with what it asked and what it logged."""

    page: Page
    live: LiveHub
    problems: list[str]
    asked: list[tuple[str, str]] = field(default_factory=list)

    def reads(self, path: str) -> int:
        return self.asked.count(("GET", path))

    def writes(self) -> list[str]:
        return [path for method, path in self.asked if method == "POST"]


@pytest.fixture
def live(tmp_path: Path) -> Iterator[LiveHub]:
    """The real hub over the world of fakes: three registered projects and no process."""
    made = LiveHub(tmp_path)
    try:
        yield made
    finally:
        made.close()


@pytest.fixture
def live_page(chromium: Browser, live: LiveHub, lang: str) -> Iterator[LivePage]:
    """The hub's page opened on the real hub, in one language."""
    context = chromium.new_context(viewport={"width": 1300, "height": 1000}, locale=lang)
    try:
        page = context.new_page()
        page.set_default_timeout(8000)
        opened = LivePage(page, live, watch(page))
        page.on("request", lambda one: opened.asked.append(
            (one.method, urlsplit(one.url).path)))
        page.goto(f"{live.origin}/#lang={lang}", wait_until="load")
        yield opened
        assert opened.problems == []
        assert page.evaluate("window.__violations") == []
        allowed = {"/", *HUB_ASSETS, *DOORS, *BROWSER_OWN}
        strays = {path for method, path in opened.asked
                  if method == "GET" and path not in allowed}
        assert strays == set(), "the page asked for something the hub does not list"
    finally:
        context.close()


def ready(one: LivePage) -> None:
    expect(one.page.locator("#hubShell")).to_have_attribute("data-state", "ready")


def press(one: LivePage, key: str) -> None:
    one.page.locator(f'[data-focus="{key}"]').click()


def wait_for(one: LivePage, what: str, condition, seconds: float = 8.0):
    """Poll the page's own rail until `condition(facts)` holds; the facts are returned."""
    facts = None
    for _ in range(int(seconds * 20)):
        facts = one.page.evaluate(RAIL)
        if condition(facts):
            return facts
        one.page.wait_for_timeout(50)
    raise AssertionError(f"timed out waiting for {what}: {facts}")


def wait_reads(one: LivePage, path: str, count: int) -> None:
    """Wait until the page has read `path` at least `count` times: the stream's first frame is
    `projects`, and the page reads again on it, so the second read of the projects is that frame's."""
    for _ in range(160):
        if one.reads(path) >= count:
            return
        one.page.wait_for_timeout(50)
    raise AssertionError(f"{path} was read {one.reads(path)} times, not {count}")


def line_of(facts: dict, project_id: str) -> dict:
    return next(row for row in facts["projects"] if row["id"] == project_id)


def test_the_page_says_what_the_real_hub_says_of_projects_that_never_ran_and_of_its_setup(
        live_page, lang):
    one = live_page
    ready(one)
    facts = one.page.evaluate(RAIL)
    assert [row["name"] for row in facts["projects"]] == ["a", "b", "c"]
    for row in facts["projects"]:
        assert (row["line"], row["actions"], row["working"], row["muted"]) == (
            say(one, "hub.working.stopped"), ["activate"], "stopped", "true"), row
        assert row["note"] == say(one, "hub.rail.no_data")
    assert facts["heading"] == say(one, "hub.rail.heading", count="3")
    assert facts["count"] == say(one, "hub.rail.waiting", count="0")
    banners = one.page.evaluate(BANNERS)
    assert [(name, words[0]) for name, words in banners] == [
        ("profile", say(one, "hub.banner.profile_absent")),
        ("tools", say(one, "hub.banner.tools"))], "the hub's real setup: no profile, nothing pinned"
    wait_reads(one, "/hub/projects", 2)
    assert one.writes() == []


def test_make_active_is_a_real_202_and_the_passes_that_follow_reach_the_page_as_frames(
        live_page):
    one, live = live_page, live_page.live
    child = live.child("a")
    ready(one)
    press(one, f"act:{A}:activate")
    expect(one.page.locator("#hubStatus")).to_have_text(say(one, "hub.notice.accepted"))
    live.tick()
    facts = wait_for(one, "the project to be starting", lambda f: "…" in line_of(f, A)["line"])
    assert line_of(facts, A)["line"] == f"{say(one, 'hub.working.active')} · " + say(
        one, "hub.state.starting_active")
    assert one.writes() == [f"/hub/projects/{A}/activate"]
    assert live.world.spawner.started("a")[0]["mode"] == "active", "the hub started it as active"
    reads = one.reads("/hub/projects")
    live.run_project("a", child.port)
    live.tick()
    facts = wait_for(one, "the project to run", lambda f: line_of(f, A)["muted"] == "false")
    assert line_of(facts, A)["line"] == say(one, "hub.working.active")
    assert line_of(facts, A)["actions"] == ["stop"]
    assert one.reads("/hub/projects") > reads, "a pass of the loop is a frame, and a frame is a read"


def test_a_stuck_project_offers_recover_and_the_real_hub_says_that_route_is_not_built(
        live_page):
    one, live = live_page, live_page.live
    ready(one)
    live.world.gone("b", "stop_uncertain", head="opened")
    live.tick()
    wait_for(one, "the stuck project to show", lambda f: line_of(f, B)["actions"] == ["recover"])
    press(one, f"act:{B}:recover")
    expect(one.page.locator("#hubStatus")).to_have_text(say(one, "hub.notice.not_built"))
    assert one.writes() == [f"/hub/projects/{B}/recover"], "one post, and the hub refused it"


def test_a_project_forgotten_while_it_owes_its_closing_is_named_by_the_page_from_the_hubs_list(
        live_page):
    one, live = live_page, live_page.live
    child = live.child("a")
    ready(one)
    assert live.post(f"/hub/projects/{A}/activate") == 202
    live.tick()
    live.run_project("a", child.port)
    live.tick()
    live.world.gone("a", "serving", head="opened")
    live.tick()
    wait_for(one, "the dead child to be said", lambda f: line_of(f, A)["actions"] == ["recover"])
    press(one, f"menu:{A}")
    press(one, f"act:{A}:forget")
    expect(one.page.locator('#hubBanners [data-banner="unlisted"]')).to_have_count(1)
    facts = one.page.evaluate(RAIL)
    assert [row["id"] for row in facts["projects"]] == [B, C], "the project is off the list"
    owed = live.world.hub_state().closing
    assert [entry.project_id for entry in owed] == [A], "and the hub still holds what it owes"
    title = one.page.evaluate("""() => document.querySelector(
      '#hubBanners [data-banner="unlisted"] span').title""")
    assert title == owed[0].since
    assert one.writes() == [f"/hub/projects/{A}/forget"]


def test_a_registry_the_real_hub_cannot_read_is_the_registry_notice_and_the_failed_status(
        live_page):
    one, live = live_page, live_page.live
    ready(one)
    (live.world.home / "registry.json").write_text("not the registry", encoding="utf-8")
    one.page.reload()
    expect(one.page.locator("#hubShell")).to_have_attribute("data-state", "failed")
    expect(one.page.locator('#hubBanners [data-banner="registry"]')).to_have_text(
        say(one, "hub.banner.registry"))
    assert one.page.evaluate("document.getElementById('hubStatus').textContent") == say(
        one, "hub.status.failed")
