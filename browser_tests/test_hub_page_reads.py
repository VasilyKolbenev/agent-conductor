"""The hub's page reads the hub and draws what it read, in a real browser, in both languages.

The page asks the hub's three doors for what a person sees (`GET /hub/projects`, `/hub/limits`,
`/hub/setup`, after the session's token) and listens to one stream of frames that carry identifiers
and nothing else. These tests put the contract fixtures behind a fake hub and read back what the
page drew: a project's line and its actions are the hub's own state and working values in the words
of the catalogue; a task is in the shared desk words; a choice is written to the address as
identifiers and interface words only; a banner says what setup says; a frame is an id that makes the
page read again and never a fact. Every test runs once in English and once in Russian, and ends by
asserting that the page raised no error, broke no policy and asked no path the hub does not serve.
"""
from __future__ import annotations

from playwright.sync_api import expect

from browser_tests.hub_bench import (HubPage, fields, fixture, hub,  # noqa: F401
                                     hub_page, lang, ready, say, short)

PROJECTS = fixture("hub_projects.json")
WEB, LANDING, BOT = (row["project_id"] for row in PROJECTS["projects"])
LOGIN = fixture("hub_setup.json")["logins"][0]["login_key"]
RAIL = """() => ({
  heading: document.querySelector(".hub-rail__head span").textContent,
  count: document.querySelector("[data-waiting]").textContent,
  projects: [...document.querySelectorAll(".hub-project")].map((n) => ({id: n.dataset.projectId,
    name: n.querySelector(".hub-project__name").textContent,
    line: n.querySelector(".hub-project__line").textContent, working: n.dataset.working,
    muted: n.dataset.muted, selected: n.dataset.selected,
    badge: n.querySelector("[data-badge]")?.textContent ?? null,
    note: n.querySelector(".hub-project__note")?.textContent ?? null,
    actions: [...n.querySelectorAll(".hub-project__act")].map((b) => b.dataset.action),
    tasks: [...n.querySelectorAll(".hub-task")].map((t) => [t.dataset.taskId,
      t.querySelector(".hub-task__title").textContent,
      t.querySelector(".hub-task__state").textContent])})),
  waiting: [...document.querySelectorAll(".hub-waiting__item")].map((b) => b.textContent),
  status: document.getElementById("hubStatus").textContent,
  shell: document.getElementById("hubShell").dataset.state})"""
CENTER = """() => ({
  center: document.querySelector("#hubCenter [data-case]")?.dataset.case ?? null,
  line: document.querySelector("#hubCenter .hub-stub__line")?.textContent ?? null,
  link: document.querySelector("#hubCenter [data-open-desk]")?.getAttribute("href") ?? null,
  note: document.querySelector("#hubCenter .hub-project__note")?.textContent ?? null,
  actions: [...document.querySelectorAll("#hubCenter .hub-project__act")].map(
    (b) => b.dataset.action),
  path: document.getElementById("hubPath").textContent,
  newTask: [...document.querySelectorAll("#hubActions > *")].slice(0, 1).map((n) => [n.tagName,
    n.getAttribute("href")]),
  side: [...document.querySelectorAll("#hubSide > *")].map((n) => n.dataset.queue === undefined
    ? "limits" : "queue"),
  hash: location.hash})"""
SIDE = """() => ({
  queue: [...document.querySelectorAll("[data-queue] > h2, [data-queue] > p, "
    + "[data-queue] .hub-queue__entry > span")].map((n) => n.textContent),
  caption: document.querySelector(".hub-limits__source").textContent,
  cards: [...document.querySelectorAll(".hub-card")].map((n) => [n.dataset.unverified,
    ...[...n.children].map((c) => c.textContent)])})"""
BANNERS = """() => [...document.querySelectorAll("#hubBanners [data-banner]")].map((n) => [
  n.dataset.banner, [...n.children].map((c) => c.textContent)])"""


def wait_reads(page: HubPage, path: str, count: int) -> None:
    """Wait until the hub has been asked `path` at least `count` times in all."""
    for _ in range(80):
        if page.hub.requests(path) >= count:
            return
        page.page.wait_for_timeout(50)
    raise AssertionError(f"{path} was asked {page.hub.requests(path)} times, not {count}")


def test_the_projects_the_hub_reads_are_drawn_with_the_words_of_their_states(hub_page):
    page = hub_page
    ready(page)
    facts = page.page.evaluate(RAIL)
    assert facts["heading"] == say(page, "hub.rail.heading", count="3")
    assert facts["count"] == say(page, "hub.rail.waiting", count="1")
    web, landing, bot = facts["projects"]
    assert (web["id"], web["name"], web["line"], web["actions"], web["badge"]) == (
        WEB, "web-app", say(page, "hub.working.active"), ["stop"], "◆ 1")
    assert (landing["line"], landing["muted"], landing["actions"]) == (
        say(page, "hub.working.queued", position="1"), "true", ["clear_flag"])
    assert landing["note"] == say(page, "desk_status.snapshot", time=short(
        page, PROJECTS["projects"][1]["snapshot_at"]))
    assert bot["line"] == say(page, "hub.working.stopped_since", time=short(
        page, PROJECTS["projects"][2]["stopped_at"]))
    assert (bot["note"], bot["actions"]) == (say(page, "hub.rail.no_data"), ["activate"])
    at = short(page, "2026-09-29T10:00:00Z")
    assert facts["waiting"] == [say(page, "hub.waiting.row_task", project="web-app",
        task="Add a dark theme", reason=say(page, "desk_status.attention_gate_decision"),
        since=say(page, "desk_status.since_observed", time=at))]
    assert facts["status"] == say(page, "hub.status.ready") and facts["shell"] == "ready"
    wait_reads(page, "/hub/projects", 2)
    assert [page.hub.requests(path) for path in ("/hub/session", "/hub/projects", "/hub/limits",
                                                  "/hub/setup")] == [1, 2, 1, 1], (
        "the stream's first frame says to read again, and that is the second read of the projects")
    assert page.hub.streams_opened == 1


def test_a_project_chosen_opens_into_its_tasks_and_a_running_desk_is_a_link_to_it(hub_page, lang):
    page = hub_page
    ready(page)
    page.page.locator(f'[data-focus="project:{WEB}"]').click()
    expect(page.page.locator(f'.hub-project[data-project-id="{WEB}"]')).to_have_attribute(
        "data-selected", "true")
    facts = page.page.evaluate(RAIL)
    assert facts["projects"][0]["tasks"] == [
        ["task-001", "Fix the payment form", say(page, "desk_status.running")],
        ["task-002", "Add a dark theme", say(page, "desk_status.waiting_you")]]
    assert facts["projects"][1]["selected"] == "false"
    centre = page.page.evaluate(CENTER)
    assert centre["center"] == "running" and centre["path"] == "web-app"
    assert centre["link"].startswith("http://127.0.0.1:7701/panel/desk.html#")
    assert fields(centre["link"].split("#")[1]) == {"project": WEB, "lang": lang}
    assert fields(centre["hash"]) == {"project": WEB, "lang": lang}
    assert centre["side"] == [], "beside a running desk the column is that desk's own"
    assert centre["newTask"][0][0] == "A"
    assert fields(centre["newTask"][0][1].split("#")[1]) == {"project": WEB, "new": "task",
                                                             "lang": lang}


def test_a_task_or_a_waiting_item_chosen_writes_its_ids_to_the_address_and_nothing_else(
        hub_page, lang):
    page = hub_page
    ready(page)
    page.page.locator(f'[data-focus="project:{WEB}"]').click()
    page.page.locator(f'[data-focus="task:{WEB}:task-002"]').click()
    centre = page.page.evaluate(CENTER)
    assert fields(centre["hash"]) == {"project": WEB, "task": "task-002", "run": "run-002",
                                      "lang": lang}
    assert centre["path"] == "web-app › Add a dark theme › run-002"
    assert fields(centre["link"].split("#")[1]) == fields(centre["hash"])
    page.page.locator(f'[data-focus="task:{WEB}:task-001"]').click()
    assert fields(page.page.evaluate("location.hash"))["run"] == "run-001"
    page.page.locator(".hub-waiting__item").click()
    again = fields(page.page.evaluate("location.hash"))
    assert again == {"project": WEB, "task": "task-002", "run": "run-002", "lang": lang}, (
        "the ids come from the row the hub gave; no text and no path is ever written")
    page.page.reload()
    ready(page)
    assert page.page.evaluate(CENTER)["path"] == "web-app › Add a dark theme › run-002", (
        "a reload restores the choice from the address")


def test_a_project_with_no_running_desk_shows_its_stub_the_queue_and_the_limits(hub_page):
    page = hub_page
    ready(page)
    page.page.locator(f'[data-focus="project:{BOT}"]').click()
    centre = page.page.evaluate(CENTER)
    assert centre["center"] == "stub" and centre["link"] is None
    assert centre["line"] == say(page, "hub.working.stopped_since", time=short(
        page, PROJECTS["projects"][2]["stopped_at"]))
    assert centre["actions"] == ["activate"] and centre["side"] == ["queue", "limits"]
    assert centre["newTask"][0][0] == "SPAN", "a desk that does not run cannot take a new task"
    side = page.page.evaluate(SIDE)
    assert side["queue"][:2] == [say(page, "hub.queue.heading"),
                                 say(page, "hub.queue.now", name="web-app")]
    assert side["queue"][2] == say(page, "hub.queue.entry", position="1", name="landing",
                                   time=short(page, "2026-09-29T08:41:00Z"))
    assert side["caption"] == say(page, "hub.limits.live")
    assert side["cards"] == [
        ["false", "openai", say(page, "hub.limits.window", label=say(page, "hub.limits.hours",
            count="5"), value="75", time=short(page, "2026-09-29T12:00:00Z"))],
        ["true", "glm-1", say(page, "hub.limits.unverified"), say(page, "hub.limits.missing")]]


def test_a_language_chosen_after_the_read_says_every_word_of_the_data_again(hub_page, lang):
    page = hub_page
    ready(page)
    other = "ru" if lang == "en" else "en"
    page.page.locator(f'[data-focus="seg:lang:{other}"]').click()
    expect(page.page.locator("html")).to_have_attribute("lang", other)
    facts = page.page.evaluate(RAIL)
    assert facts["projects"][0]["line"] == say(page, "hub.working.active")
    assert facts["heading"] == say(page, "hub.rail.heading", count="3")
    assert facts["status"] == say(page, "hub.status.ready")
    assert facts["projects"][1]["line"] == say(page, "hub.working.queued", position="1")


def test_the_banners_say_what_setup_says_and_a_login_that_is_not_closed_can_be_recovered(
        hub_page):
    page = hub_page
    setup = fixture("hub_setup.json")
    setup.update(profile="absent", hub_job="kill_on_close")
    setup["logins"][0]["state"] = "unclosed"
    setup["projects_home"]["state"] = "invalid"
    page.hub.answer("/hub/setup", setup)
    page.page.reload()
    ready(page)
    banners = page.page.evaluate(BANNERS)
    assert [name for name, _ in banners] == ["profile", "tools", "login", "home", "job",
                                             "unlisted"]
    assert banners[0][1] == [say(page, "hub.banner.profile_absent"),
                             say(page, "hub.banner.profile_how")]
    assert banners[1][1] == [say(page, "hub.banner.tools")]
    assert banners[2][1] == [say(page, "hub.banner.login", harness="claude-code"),
                             say(page, "hub.act.recover_login")]
    assert banners[4][1] == [say(page, "hub.banner.job"), say(page, "hub.banner.job_how")]
    page.page.locator(f'[data-focus="login:{LOGIN}"]').click()
    expect(page.page.locator("#hubStatus")).to_have_text(say(page, "hub.notice.accepted"))
    assert page.hub.posts == [{"path": f"/hub/logins/{LOGIN}/recover", "body": {}}]


UNLISTED = """() => [...document.querySelectorAll('#hubBanners [data-banner="unlisted"]')].map((n) => {
  const control = n.querySelector(".hub-blocked");
  return {text: n.firstElementChild.textContent, title: n.firstElementChild.title,
    label: control.querySelector("button").textContent,
    disabled: control.querySelector("button").disabled,
    why: control.querySelector("small").textContent};
})"""


def test_a_project_taken_off_the_list_that_still_owes_its_closing_is_named_with_its_action_blocked(
        hub_page):
    page = hub_page
    ready(page)
    [fact] = page.page.evaluate(UNLISTED)
    at = short(page, "2026-09-29T08:30:00Z")
    assert fact == {"text": say(page, "hub.unlisted.note", time=at), "title": "2026-09-29T08:30:00Z",
                    "label": say(page, "hub.act.relist"), "disabled": True,
                    "why": say(page, "hub.unlisted.relist_blocked")}
    assert page.hub.posts == [], "the action has no route: it is drawn, never sent"
    clear = fixture("hub_projects.json")
    clear["unlisted_closing"] = []
    page.hub.answer("/hub/projects", clear)
    page.hub.push({"kind": "projects"})
    expect(page.page.locator('#hubBanners [data-banner="unlisted"]')).to_have_count(0)


def test_a_frame_is_an_id_that_makes_the_page_read_again_and_carries_no_fact(hub_page):
    page = hub_page
    ready(page)
    renamed = fixture("hub_projects.json")
    renamed["projects"][0]["name"] = "renamed"
    page.hub.answer("/hub/projects", renamed)
    before = page.hub.requests("/hub/projects")
    page.hub.push({"kind": "project", "project_id": WEB, "name": "sneaky"})
    expect(page.page.locator(".hub-project__name").first).to_have_text("renamed")
    assert "sneaky" not in page.page.inner_text("body")
    for _ in range(5):
        page.hub.push({"kind": "projects"})
    page.page.wait_for_timeout(400)
    assert 2 <= page.hub.requests("/hub/projects") - before <= 4, "a burst is read once or twice"
    for kind in ("limits", "setup"):
        wait_total = page.hub.requests(f"/hub/{kind}") + 1
        page.hub.push({"kind": kind})
        wait_reads(page, f"/hub/{kind}", wait_total)
    reads = page.hub.requests("/hub/projects")
    page.hub.stream.put(b"data: not json\n\n")
    page.hub.push({"kind": "nothing-the-page-knows"})
    page.page.wait_for_timeout(300)
    assert page.hub.requests("/hub/projects") == reads, "a frame of no known kind asks for nothing"


def test_a_read_the_hub_refuses_is_said_and_what_was_read_stays_until_a_read_lands(hub_page):
    page = hub_page
    ready(page)
    page.hub.answer("/hub/projects", {"error": {"code": "registry_invalid", "message": "",
                                               "detail": None}}, status=409)
    page.hub.push({"kind": "projects"})
    expect(page.page.locator('#hubBanners [data-banner="registry"]')).to_have_text(
        say(page, "hub.banner.registry"))
    facts = page.page.evaluate(RAIL)
    assert len(facts["projects"]) == 3 and facts["status"] == say(page, "hub.status.failed")
    assert facts["shell"] == "failed"
    page.hub.answer("/hub/projects", fixture("hub_projects.json"))
    page.hub.push({"kind": "projects"})
    expect(page.page.locator('#hubBanners [data-banner="registry"]')).to_have_count(0)
    ready(page)
    assert [name for name, _ in page.page.evaluate(BANNERS)] == ["tools", "unlisted"], (
        "what setup and the list say stays; only the registry's complaint goes")
