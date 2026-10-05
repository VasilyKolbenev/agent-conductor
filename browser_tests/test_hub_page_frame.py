"""The hub's frame in a real browser: the project's desk in an iframe, on real desks, under the hub's
own policy, in both languages (spec 4.5.5).

The hub is the real one (`hub_live.py`: the real server, service and reader over a world of fakes that
start no process) and each running project is a REAL desk server built with this hub as its own, so the
frame policy the desk sends admits this page, the desk's project claim names this hub, and the desk
says where it is by its real `postMessage`. What is asserted is what the browser did, never a reading of
source: one new `<iframe>` with the sandbox of the spec, a desk moved by a replacement of its location
(the document is the same document: a marker set inside it survives), a message believed only from
the frame's window in the one shape, a frame replaced by a NEW element when the project's instance
changes and gone when the project stops, a language change that keeps what a person chose inside the
desk, a desk that cannot take the page away, and a page that says nothing to the desk. A fact and its
sentence are read in ONE evaluation.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Frame, Route, expect
from playwright.sync_api import TimeoutError as WaitTimeout

from browser_tests.desk_identity import identified_server
from browser_tests.hub_bench import (fields, fixture, hub, hub_page, lang,  # noqa: F401
                                     say)
from browser_tests.hub_live import (A, B, C, LivePage, line_of, live,  # noqa: F401
                                    live_page, press, ready, wait_for)
from conductor.hub import state as hub_state
from browser_tests.desk_settled import SETTLED
from browser_tests.test_desk_rail_scene import _seed
from tests.test_store import good_lane, write_project

SANDBOX = ("allow-scripts allow-same-origin allow-forms allow-popups "
           "allow-popups-to-escape-sandbox")
FRAME_FACTS = """() => {
  const frames = [...document.querySelectorAll("#hubDesk iframe")];
  const one = frames[0] ?? null;
  return {count: frames.length, hidden: document.getElementById("hubDesk").hidden,
    sandbox: one?.getAttribute("sandbox") ?? null, title: one?.getAttribute("title") ?? null,
    src: one?.getAttribute("src") ?? null, side: document.getElementById("hubSide").childElementCount,
    stub: document.querySelector("#hubStub [data-case]")?.dataset.case ?? null,
    path: document.getElementById("hubPath").textContent, hash: location.hash};
}"""
#: What the desk drew of the chosen task, asked inside the frame.
DESK_FACTS = """() => ({lang: document.documentElement.lang,
  chosen: [...document.querySelectorAll("#deskRail [data-task-id]")]
    .filter((row) => row.getAttribute("aria-pressed") === "true").map((row) => row.dataset.taskId),
  rows: document.querySelectorAll("#deskRail [data-task-id]").length,
  marker: window.__marker ?? null})"""
#: A valid location message, made inside the frame (what the desk itself says).
SAY = """([kind, project, task, run, extra]) => window.parent.postMessage(
  {kind, project_id: project, task_id: task, run_id: run, ...extra}, "*")"""


def seeded_root(tmp_path: Path, name: str) -> Path:
    """A one-project directory with six tasks and their runs, to be served as a desk."""
    base = tmp_path / "desks" / name
    base.mkdir(parents=True)
    root = write_project(base, lanes={"claude": good_lane()})
    _seed(root)
    return root


def run_project(one: LivePage, name: str, tmp_path: Path, *, mode: str = "active") -> int:
    """The project `name` runs on a real desk: the hub is asked, the loop passes, the desk is read."""
    live_ = one.live
    port = live_.desk(name, seeded_root(tmp_path, name), mode=mode)
    target = f"/hub/projects/{live_.project_id(name)}/{'activate' if mode == 'active' else 'view'}"
    assert live_.post(target) == 202
    live_.tick()
    live_.run_project(name, port, mode=mode)
    live_.tick()
    project = live_.project_id(name)
    wait_for(one, f"{name} to run", lambda f: line_of(f, project)["muted"] == "false")
    return port


@pytest.fixture
def running_a(live_page: LivePage, tmp_path: Path) -> LivePage:
    """The page, with project `a` running on a real desk."""
    ready(live_page)
    live_page.port = run_project(live_page, "a", tmp_path)
    return live_page


def desk_frame(one: LivePage) -> Frame:
    """The desk's window inside the page's one frame, once the desk has drawn."""
    frame = one.page.wait_for_selector("#hubDesk iframe").content_frame()
    frame.wait_for_function(SETTLED)
    return frame


BARE = '<!doctype html><html><body data-bare="1"></body></html>'


def test_the_wait_for_the_desk_goes_on_while_the_frames_document_is_not_the_desk_yet(running_a):
    """A frame is asked before its document has drawn the desk: the wait must go on, not end."""
    one = running_a
    answered: list[str] = []

    def bare_first(route: Route) -> None:
        answered.append(route.request.url)
        if len(answered) == 1:
            route.fulfill(status=200, content_type="text/html", body=BARE)
        else:
            route.continue_()

    one.page.route(re.compile(r"/panel/desk\.html"), bare_first)
    try:
        press(one, f"project:{A}")
        frame = one.page.wait_for_selector("#hubDesk iframe").content_frame()
        frame.wait_for_function('() => document.body?.dataset.bare === "1"')
        with pytest.raises(WaitTimeout):
            frame.wait_for_function(SETTLED, timeout=300)
        frame.evaluate("() => location.reload()")
        assert desk_frame(one).evaluate(DESK_FACTS)["rows"] == 6 and len(answered) == 2
    finally:
        one.page.unroute_all(behavior="ignoreErrors")


def wait_hub(one: LivePage, what: str, script: str, arg=None) -> None:
    try:
        one.page.wait_for_function(script, arg=arg)
    except Exception as error:  # noqa: BLE001 -- say what was waited for, with the page's words
        raise AssertionError(f"timed out waiting for {what}: {one.page.evaluate(FRAME_FACTS)}; "
                             f"the page said {getattr(one, 'problems', None)}") from error


def test_a_running_project_is_mounted_as_one_new_frame_with_the_sandbox_and_the_hash_the_spec_gives(
        running_a, lang):
    one = running_a
    press(one, f"project:{A}")
    frame = desk_frame(one)
    facts = one.page.evaluate(FRAME_FACTS)
    assert (facts["count"], facts["hidden"], facts["sandbox"]) == (1, False, SANDBOX)
    assert facts["title"] == say(one, "hub.frame.title", name="a")
    base, _, hash_text = facts["src"].partition("#")
    assert base == f"http://127.0.0.1:{one.port}/panel/desk.html"
    assert fields(hash_text) == {"project": A, "embed": "hub", "lang": lang}
    assert (facts["side"], facts["stub"]) == (0, None), (
        "beside a running desk the column and the centre are the desk's own")
    desk = frame.evaluate(DESK_FACTS)
    assert desk["lang"] == lang and desk["rows"] == 6, "the desk is bound to its project and drawn"
    assert one.writes() == [], "the page writes nothing to mount a desk"


def test_a_task_chosen_in_the_column_moves_the_desk_and_neither_reloads_it_nor_redraws_the_frame(
        running_a):
    one = running_a
    press(one, f"project:{A}")
    frame = desk_frame(one)
    one.page.evaluate("document.querySelector('#hubDesk iframe').__mine = 'first element'")
    frame.evaluate("window.__marker = 'first document'")
    press(one, f"task:{A}:task-docs")
    frame.wait_for_function("""() => document.querySelector(
      '#deskRail [data-task-id="task-docs"]')?.getAttribute("aria-pressed") === "true" """)
    assert frame.evaluate(DESK_FACTS)["marker"] == "first document", "the same document"
    reads = one.reads("/hub/projects")
    one.live.world.store.update(lambda current: hub_state.enqueue(current, B, FLAG))
    one.live.tick()
    for _ in range(80):
        if one.reads("/hub/projects") > reads:
            break
        one.page.wait_for_timeout(50)
    assert one.reads("/hub/projects") > reads, "the page was redrawn by a read"
    kept = one.page.evaluate("document.querySelector('#hubDesk iframe')?.__mine ?? null")
    assert kept == "first element", "a redraw of the page does not make a new frame"
    assert frame.evaluate(DESK_FACTS)["marker"] == "first document"


def test_the_desks_location_message_sets_the_path_the_highlight_and_the_address_and_nothing_else(
        running_a, lang):
    one = running_a
    press(one, f"project:{A}")
    frame = desk_frame(one)
    reads = (one.reads("/hub/projects"), one.reads("/hub/limits"), one.reads("/hub/setup"))
    frame.locator('#deskRail [data-task-id="task-check"]').click()
    wait_hub(one, "the path to name the task and its run", """() => document.getElementById(
      "hubPath").textContent === "a › Check the export › run-check" """)
    facts = one.page.evaluate(FRAME_FACTS)
    assert fields(facts["hash"]) == {"project": A, "task": "task-check", "run": "run-check",
                                     "lang": lang}
    pressed = one.page.evaluate("""() => document.querySelector(
      '.hub-task[data-task-id="task-check"]').getAttribute("aria-pressed")""")
    assert pressed == "true", "the task is highlighted in the column"
    assert one.writes() == [], "the message causes no write"
    assert (one.reads("/hub/projects"), one.reads("/hub/limits"), one.reads("/hub/setup")) == reads, (
        "and no read of the hub")


def test_a_message_from_anywhere_but_the_frame_in_the_one_shape_changes_nothing(running_a):
    one = running_a
    press(one, f"project:{A}")
    frame = desk_frame(one)
    frame.locator('#deskRail [data-task-id="task-docs"]').click()
    wait_hub(one, "the desk's own location", """() => document.getElementById(
      "hubPath").textContent === "a › Write the docs › run-docs" """)
    one.page.evaluate("""() => {
      window.__addresses = [];
      const original = history.replaceState.bind(history);
      history.replaceState = (...rest) => { original(...rest); window.__addresses.push(location.hash); };
    }""")
    good = ["desk-location", A, "task-check", None, {}]
    forged = [["desk-location", A, "task-check", None, {"token": "x"}],
              ["desk-location", B, "task-check", None, {}],
              ["desk-location", A, "../x", None, {}],
              ["desk-location", A, "task-check", "a run that is a sentence", {}],
              ["desk-write", A, "task-check", None, {}]]
    for message in forged:
        frame.evaluate(SAY, message)
    one.page.evaluate("""(at) => window.postMessage({kind: "desk-location", project_id: at[0],
      task_id: "task-check", run_id: null}, "*")""", [A])
    frame.evaluate(SAY, good)
    wait_hub(one, "the one good message", """() => document.getElementById(
      "hubPath").textContent === "a › Check the export" """)
    addresses = one.page.evaluate("window.__addresses")
    assert len(addresses) == 1 and "task=task-check" in addresses[0], (
        "six forged messages, from the frame and from the page itself, wrote nothing; one good one did")


def test_a_language_chosen_on_the_page_reaches_the_desk_and_keeps_what_was_chosen_inside_it(
        running_a, lang):
    one = running_a
    other = "ru" if lang == "en" else "en"
    press(one, f"project:{A}")
    frame = desk_frame(one)
    press(one, f"task:{A}:task-docs")
    frame.wait_for_function("""() => document.querySelector(
      '#deskRail [data-task-id="task-docs"]')?.getAttribute("aria-pressed") === "true" """)
    frame.evaluate("window.__marker = 'first document'")
    press(one, f"seg:lang:{other}")
    frame.wait_for_function("(want) => document.documentElement.lang === want", arg=other)
    desk = frame.evaluate(DESK_FACTS)
    assert (desk["lang"], desk["chosen"], desk["marker"]) == (other, ["task-docs"], "first document"), (
        "the language moved, the choice inside the desk stayed, and it is the same document")
    assert one.page.evaluate("document.querySelectorAll('#hubDesk iframe').length") == 1
    assert one.page.evaluate("document.querySelector('#hubDesk iframe').getAttribute('title')") == (
        say(one, "hub.frame.title", name="a")), "the frame's name is said in the new language too"


def test_a_changed_instance_replaces_the_frame_with_a_new_element_and_a_stopped_project_removes_it(
        running_a, tmp_path):
    one = running_a
    press(one, f"project:{A}")
    frame = desk_frame(one)
    frame.locator('#deskRail [data-task-id="task-docs"]').click()
    wait_hub(one, "the desk's location", """() => document.getElementById(
      "hubPath").textContent === "a › Write the docs › run-docs" """)
    one.page.evaluate("document.querySelector('#hubDesk iframe').__mine = 'first element'")
    one.live.world.gone("a")
    one.live.tick()
    wait_hub(one, "the frame to go", "() => document.querySelectorAll('#hubDesk iframe').length === 0")
    gone = one.page.evaluate(FRAME_FACTS)
    assert gone["hidden"] is True and gone["stub"] == "stub" and gone["count"] == 0, (
        "a project that is not running has no desk: the stub says what it is doing")
    one.live.run_project("a", one.port)
    one.live.tick()
    wait_hub(one, "a new frame", "() => document.querySelectorAll('#hubDesk iframe').length === 1")
    fresh = one.page.evaluate(FRAME_FACTS)
    assert fresh["hidden"] is False and "task=task-docs" in fresh["src"], (
        "a new desk is opened where the last one said it was")
    assert one.page.evaluate("document.querySelector('#hubDesk iframe').__mine ?? null") is None, (
        "a new element, not the first one with a new address")


def test_choosing_another_running_project_removes_the_old_frame_and_mounts_a_new_one(
        running_a, tmp_path):
    one = running_a
    second = run_project(one, "b", tmp_path, mode="view")
    press(one, f"project:{A}")
    desk_frame(one)
    one.page.evaluate("document.querySelector('#hubDesk iframe').__mine = 'a'")
    press(one, f"project:{B}")
    wait_hub(one, "the frame of b", f"""() => document.querySelector(
      '#hubDesk iframe')?.getAttribute("src")?.includes("project={B}") """)
    facts = one.page.evaluate(FRAME_FACTS)
    assert facts["count"] == 1 and facts["src"].startswith(
        f"http://127.0.0.1:{second}/panel/desk.html#"), "one frame, at the other project's desk"
    assert one.page.evaluate("document.querySelector('#hubDesk iframe').__mine ?? null") is None


def test_the_desk_cannot_take_the_hub_page_away_from_its_frame(running_a):
    one = running_a
    press(one, f"project:{A}")
    frame = desk_frame(one)
    before = one.page.url
    frame.evaluate("""() => { try { window.top.location.href = "about:blank#gone"; } catch (error) {} }""")
    one.page.wait_for_timeout(300)
    assert one.page.url == before, "the sandbox grants no navigation of the top page"
    assert any("allow-top-navigation" in text for text in one.problems), one.problems
    one.problems.clear()


def test_the_hub_says_nothing_to_the_desk_whatever_the_person_does_on_the_page(running_a, lang):
    one = running_a
    other = "ru" if lang == "en" else "en"
    press(one, f"project:{A}")
    frame = desk_frame(one)
    frame.evaluate("""() => { window.__heard = [];
      window.addEventListener("message", (event) => window.__heard.push(String(event.data))); }""")
    press(one, f"task:{A}:task-docs")
    press(one, f"seg:lang:{other}")
    press(one, 'seg:theme:dark')
    frame.wait_for_function("(want) => document.documentElement.lang === want", arg=other)
    frame.evaluate("() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))")
    assert frame.evaluate("window.__heard") == [], (
        "navigation and settings go through the hash alone: no message from the hub")
    expect(one.page.locator("#hubShell")).to_have_attribute("data-state", "ready")


# -- a press that moves the desk: a new task, the flag, a run to continue -----------------------------

FLAG = "f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1"
#: The addresses the desk was moved to, read from the event (the desk may rewrite its own hash at once).
HASHES = """() => { window.__hashes = [];
  window.addEventListener("hashchange", (event) => window.__hashes.push(event.newURL)); }"""


def test_a_new_task_moves_the_shown_desk_to_the_new_task_key_in_the_same_document(running_a):
    one = running_a
    press(one, f"project:{A}")
    frame = desk_frame(one)
    frame.evaluate(HASHES)
    frame.evaluate("window.__marker = 'first document'")
    press(one, "new-task")
    frame.wait_for_function("() => window.__hashes.some((one) => one.includes('new=task'))")
    assert frame.evaluate(DESK_FACTS)["marker"] == "first document", "no reload"
    assert one.writes() == [], "a new task is a move into the desk; the hub writes nothing"
    assert "embed=hub" in frame.evaluate("window.__hashes[0]")


def test_a_new_task_is_blocked_with_its_reason_while_the_chosen_project_has_no_running_desk(
        live_page):
    one = live_page
    ready(one)
    press(one, f"project:{B}")
    facts = one.page.evaluate("""() => { const one = document.querySelector("#hubActions .hub-blocked");
      return [one.querySelector("button").disabled, one.querySelector("small").textContent]; }""")
    assert facts == [True, say(one, "hub.new_task.blocked")]


def test_clear_the_flag_of_a_queued_project_opens_it_for_viewing_then_mounts_its_desk_at_the_flag(
        live_page, tmp_path):
    one, live_ = live_page, live_page.live
    ready(one)
    port = live_.desk("b", seeded_root(tmp_path, "b"), mode="view")
    live_.world.store.update(lambda current: hub_state.enqueue(current, B, FLAG))
    live_.tick()
    wait_for(one, "b to be queued", lambda f: line_of(f, B)["working"] == "queued")
    press(one, f"act:{B}:clear_flag")
    for _ in range(80):
        if one.writes() == [f"/hub/projects/{B}/view"]:
            break
        one.page.wait_for_timeout(50)
    assert one.writes() == [f"/hub/projects/{B}/view"], "the hub opens it for viewing first"
    assert one.page.evaluate("document.querySelectorAll('#hubDesk iframe').length") == 0
    live_.tick()
    live_.run_project("b", port, mode="view")
    live_.tick()
    wait_hub(one, "the desk of b at the flag", f"""() => document.querySelector(
      '#hubDesk iframe')?.getAttribute("src")?.includes("panel=continue") """)
    src = one.page.evaluate("document.querySelector('#hubDesk iframe').getAttribute('src')")
    assert fields(src.partition("#")[2])["project"] == B
    assert fields(one.page.evaluate("location.hash"))["project"] == B


def test_clear_the_flag_of_a_queued_project_whose_view_runs_mounts_its_desk_at_the_flag_with_no_write(
        live_page, tmp_path):
    one, live_ = live_page, live_page.live
    ready(one)
    run_project(one, "b", tmp_path, mode="view")
    live_.world.store.update(lambda current: hub_state.enqueue(current, B, FLAG))
    live_.tick()
    wait_for(one, "b to be viewed", lambda f: line_of(f, B)["working"] == "view")
    press(one, f"project:{C}")
    expect(one.page.locator(f'[data-queue] .hub-queue__entry[data-project-id="{B}"]')).to_have_count(1)
    press(one, f"queue:{B}:clear_flag")
    wait_hub(one, "the desk of b at the flag", """() => document.querySelector(
      '#hubDesk iframe')?.getAttribute("src")?.includes("panel=continue") """)
    assert one.writes() == [], "its desk already runs: nothing is opened and nothing is written"
    assert fields(one.page.evaluate("location.hash"))["project"] == B


def test_continue_activates_the_project_and_mounts_its_new_desk_at_the_run_to_resume(
        live_page, tmp_path, lang):
    from tests._hub_fake_child import automation, run_row, task_row
    one, live_ = live_page, live_page.live
    ready(one)
    resumable = automation("run-9", state="restart_required", reason="explicit_resume_required")
    child = live_.child("b", tasks=[task_row("task-9", "Resume me")],
                        runs=[run_row("run-9", "task-9")], automations={"run-9": resumable})
    assert live_.post(f"/hub/projects/{B}/activate") == 202
    live_.tick()
    live_.run_project("b", child.port)
    live_.tick()
    assert live_.post(f"/hub/projects/{B}/stop") == 202
    live_.world.gone("b")
    live_.tick()
    live_.tick()
    wait_hub(one, "b to offer Continue", f"""(label) => document.querySelector(
      '[data-focus="act:{B}:activate"]')?.textContent === label""", say(one, "hub.act.resume"))
    port = live_.desk("b", seeded_root(tmp_path, "b"))
    press(one, f"act:{B}:activate")
    for _ in range(80):
        if one.writes() == [f"/hub/projects/{B}/activate"]:
            break
        one.page.wait_for_timeout(50)
    assert one.writes() == [f"/hub/projects/{B}/activate"]
    live_.tick()
    live_.run_project("b", port)
    live_.tick()
    wait_hub(one, "the new desk at the run", """() => document.querySelector(
      '#hubDesk iframe')?.getAttribute("src")?.includes("panel=run") """)
    src = one.page.evaluate("document.querySelector('#hubDesk iframe').getAttribute('src')")
    assert fields(src.partition("#")[2]) == {"project": B, "embed": "hub", "task": "task-9",
                                             "run": "run-9", "panel": "run", "lang": lang}


def test_a_message_from_another_window_at_the_desks_own_origin_is_not_the_frames_and_is_ignored(
        running_a):
    one = running_a
    press(one, f"project:{A}")
    frame = desk_frame(one)
    frame.locator('#deskRail [data-task-id="task-docs"]').click()
    wait_hub(one, "the desk's own location", """() => document.getElementById(
      "hubPath").textContent === "a › Write the docs › run-docs" """)
    one.page.evaluate("""(src) => {
      window.__addresses = [];
      const original = history.replaceState.bind(history);
      history.replaceState = (...rest) => { original(...rest); window.__addresses.push(location.hash); };
      const other = document.createElement("iframe");
      other.id = "other";
      other.setAttribute("sandbox", "allow-scripts allow-same-origin");
      other.setAttribute("src", src);
      document.body.append(other);
    }""", f"http://127.0.0.1:{one.port}/panel/desk.html#lang=en")
    other = one.page.wait_for_selector("#other").content_frame()
    other.wait_for_load_state("load")
    other.evaluate(SAY, ["desk-location", A, "task-check", None, {}])
    frame.evaluate(SAY, ["desk-location", A, "task-idle", None, {}])
    wait_hub(one, "the frame's own message", """() => document.getElementById(
      "hubPath").textContent === "a › Tidy up" """)
    addresses = one.page.evaluate("window.__addresses")
    assert len(addresses) == 1 and "task=task-idle" in addresses[0], (
        "the same origin and the exact shape are not enough: the window must be the frame's own")


def test_a_row_that_keeps_its_instance_keeps_the_frame_and_a_new_instance_replaces_the_element(
        hub, hub_page, tmp_path):
    page = hub_page
    rows = fixture("hub_projects.json")
    web = rows["projects"][0]["project_id"]
    with identified_server(seeded_root(tmp_path, "w"), web, hub_origin=hub.url) as origin:
        rows["projects"][0]["desk_url"] = f"{origin}/panel/desk.html"
        hub.answer("/hub/projects", rows)
        page.page.reload()
        page.page.locator(f'[data-focus="project:{web}"]').click()
        page.page.wait_for_selector("#hubDesk iframe")
        page.page.evaluate("document.querySelector('#hubDesk iframe').__mine = 'first element'")
        #: The stream of the page before the reload may still hold a reader of the bench's queue and eat
        #: a frame, so a frame is pushed again until the page has answered it.
        reads = hub.requests("/hub/projects")
        for _ in range(40):
            hub.push({"kind": "project", "project_id": web})
            page.page.wait_for_timeout(100)
            if hub.requests("/hub/projects") > reads:
                break
        assert hub.requests("/hub/projects") > reads
        assert page.page.evaluate("document.querySelector('#hubDesk iframe').__mine") == (
            "first element"), "the same desk in the hub's row: the same frame"
        rows["projects"][0]["instance"] = "e" * 32
        hub.answer("/hub/projects", rows)
        for _ in range(40):
            hub.push({"kind": "project", "project_id": web})
            page.page.wait_for_timeout(100)
            if page.page.evaluate("document.querySelector('#hubDesk iframe')?.__mine") is None:
                break
        wait_hub(page, "a new element for the new instance",
                 "() => document.querySelector('#hubDesk iframe')?.__mine === undefined")
        assert page.page.evaluate("document.querySelectorAll('#hubDesk iframe').length") == 1, (
            "a restarted child is a new instance: a new element, and never two")
