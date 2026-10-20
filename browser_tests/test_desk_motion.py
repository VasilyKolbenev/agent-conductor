"""The desk's transitions in a real Chromium: shown when they are due, never when they are not.

Spec 5.5 (D11) gives four moments -- a task accepted, a task that is now waiting for the person, a
task finished, and the entry of a new task into the list -- and three conditions: they are played
once and for no longer than 1.2 s; nothing is played for a person who prefers reduced motion (the
plaque that says the moment stays); and nothing is played again after a reconnect or a reload.

Each case here starts a real desk on a real project server, waits until its stream is open (the
reading every change is compared with has been taken by then), changes the project, makes the
server send a real stream frame, and reads what the page did. What it did is read from the page's
own instruments (`desk_motion_bench.INSTRUMENT`): every call of `animate`, with the element and
its timing, and every element the motion layer drew. Nothing is waited for by time: a plaque goes
when the page takes it away, and a thing that must NOT happen is judged after one more full
refresh has landed (`Desk.refreshed`), when whatever the page was going to do about the staged
state is done.

The desk is the packaged one and nothing under `/panel/` is substituted: the first case proves the
page ran the bytes of the package, and each case after it is therefore a case of the product. The
chain that hands each render to the motion module (`desk.js`, `desk-scene.js`, `desk-motion.js`)
is read by `tests/test_desk_motion_wiring.py` as text; here it is read as behaviour.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Browser, expect

from browser_tests.desk_hold import Hold, land_read, read_again
from browser_tests.desk_motion_bench import (
    NEW_TASK, PANEL, QUIET, RUN, TASK, TITLE, WORDS, Desk, Served, Staged, serve, window)

FX_MAX_MS = 1200
#: The files of the chain that carries a render from the scene to the layer, as served.
CHAIN = ("desk-scene.js", "desk-motion.js", "desk-motion-model.js")
#: The read of the scene's run that a stale scene waits for (the controls of the task's run).
CONTROLS = f"**/command/runs/{RUN}/controls"
#: What the scene itself is drawn with at a moment of its own, as opposed to a plaque or a halo.
SCENE_MARKS = {"comet", "ring", "spark"}
#: The moments, each with the status it starts from and the one it ends at, the words the plaque
#: says after the title, and the kinds of element the motion layer must have drawn for it.
MOMENTS = {
    "accepted": ("not_started", "running", {"ring"}),
    "to_you": ("running", "waiting_you", {"comet", "ring"}),
    "finished": ("running", "outcome_succeeded", {"ring", "spark"}),
}
LAYER = "#deskMotion [data-fx]:not([data-fx='plaque'])"
#: The middle of the drawn part (`heart`) of every node a selector finds, in window coordinates.
CENTRES = """([selector, heart]) => [...document.querySelectorAll(selector)].map((node) => {
  const box = (node.querySelector(heart) ?? node).getBoundingClientRect();
  return {x: box.left + box.width / 2, y: box.top + box.height / 2}; })"""
#: A counter of what waits for the person, which the console (D1) will draw; planted here.
PLANT_COUNTER = """() => {
  const counter = document.createElement("span");
  counter.setAttribute("data-attention-count", "");
  counter.textContent = "1";
  Object.assign(counter.style, {position: "fixed", left: "300px", top: "6px"});
  document.body.append(counter);
}"""


def near(point: dict, targets: list[dict]) -> bool:
    """Whether `point` stands within 8 px of one of the `targets`, both in window coordinates."""
    return any(abs(point["x"] - one["x"]) < 8 and abs(point["y"] - one["y"]) < 8
               for one in targets)


@pytest.fixture
def served(tmp_path: Path):
    project = serve(tmp_path)
    try:
        yield project
    finally:
        project.stop()


def drawn(desk: Desk) -> set[str]:
    return set(desk.fx()["added"]) - {"plaque"}


def shown_and_gone(desk: Desk, status: str) -> None:
    """The moment has been shown (its plaque is up, and the marks are made in the same step as
    the plaque) and the marks it drew have left the layer. A layer that is still empty because
    nothing has been drawn yet would pass the second wait alone."""
    expect(desk.plaque()).to_have_text(f"{TITLE} · {WORDS['en'][status]}")
    expect(desk.page.locator(LAYER)).to_have_count(0, timeout=5000)


def test_the_desk_loads_the_packaged_scene_and_motion_modules_as_they_are(
        chromium: Browser, served: Served):
    """Nothing stands between the page and the package: the scene, the motion module and its
    model were each answered 200 with the bytes of the file in `src/conductor/panel`. The two
    motion modules are fetched at all only because the scene imports them, so this is the chain
    `desk-scene.js` to `desk-motion.js` read on the page as the product serves it, and the layer
    the module makes on its first render is there."""
    with window(chromium, served, motion=True) as desk:
        for name in CHAIN:
            answer = desk.panel.get(name)
            assert answer is not None, f"{name} was never fetched by the desk"
            assert answer.status == 200, name
            assert answer.body() == (PANEL / name).read_bytes(), f"{name} is not the package's"
        expect(desk.page.locator("#deskMotion")).to_have_count(1)
        assert desk.problems == []


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("moment", list(MOMENTS))
def test_under_reduced_motion_a_moment_shows_its_plaque_and_plays_nothing(
        chromium: Browser, served: Served, moment: str, language: str):
    before, after, _kinds = MOMENTS[moment]
    staged = Staged()
    staged.stand_at(before)
    with window(chromium, served, motion=False, language=language, staged=staged) as desk:
        desk.say(before, language)
        assert desk.fx() == {"calls": [], "added": []}, "something played at the first reading"
        desk.change(after, language)
        expect(desk.plaque()).to_have_text(f"{TITLE} · {WORDS[language][after]}")
        desk.refreshed()
        assert desk.fx()["calls"] == []
        assert drawn(desk) == set()
        expect(desk.plaque()).to_have_count(0, timeout=15000)
        assert desk.problems == []


@pytest.mark.parametrize("moment", list(MOMENTS))
def test_with_motion_allowed_a_moment_plays_inside_the_cap_and_leaves_nothing_behind(
        chromium: Browser, served: Served, moment: str):
    before, after, kinds = MOMENTS[moment]
    staged = Staged()
    staged.stand_at(before)
    with window(chromium, served, motion=True, staged=staged) as desk:
        desk.say(before)
        assert desk.fx() == {"calls": [], "added": []}, "something played at the first reading"
        desk.change(after)
        expect(desk.plaque()).to_have_text(f"{TITLE} · {WORDS['en'][after]}")
        expect(desk.page.locator(LAYER)).to_have_count(0, timeout=5000)
        played = desk.fx()
        assert kinds <= set(played["added"]), played["added"]
        assert played["calls"], "motion was allowed and nothing was played"
        assert all(call["inLayer"] for call in played["calls"])
        late = [call for call in played["calls"] if call["duration"] + call["delay"] > FX_MAX_MS]
        assert late == []
        assert desk.problems == []


def test_with_motion_allowed_the_entry_of_a_new_task_plays_a_halo_and_says_it(
        chromium: Browser, served: Served):
    with window(chromium, served, motion=True) as desk:
        assert desk.fx() == {"calls": [], "added": []}
        desk.staged.tasks.append(NEW_TASK)
        served.publish()
        row = desk.page.locator('#deskRail [data-task-id="task-new"]')
        expect(row).to_be_visible()
        expect(desk.plaque()).to_have_text("Brand new task · Not started")
        expect(desk.page.locator(LAYER)).to_have_count(0, timeout=5000)
        played = desk.fx()
        assert "halo" in played["added"] and played["calls"]
        assert all(call["duration"] + call["delay"] <= FX_MAX_MS for call in played["calls"])


def test_under_reduced_motion_the_entry_of_a_new_task_shows_its_plaque_and_plays_nothing(
        chromium: Browser, served: Served):
    with window(chromium, served, motion=False) as desk:
        desk.staged.tasks.append(NEW_TASK)
        served.publish()
        expect(desk.page.locator('#deskRail [data-task-id="task-new"]')).to_be_visible()
        expect(desk.plaque()).to_have_text("Brand new task · Not started")
        desk.refreshed()
        assert desk.fx()["calls"] == [] and drawn(desk) == set()


def test_the_scene_moment_is_played_where_the_scene_draws_its_gate_and_its_participants(
        chromium: Browser, served: Served):
    """The waves of «к вам» land on the diamond of a gate the scene draws, and the comet starts at
    the orb of a participant: the geometry is the page's own, read from the page."""
    with window(chromium, served, motion=True) as desk:
        desk.change("waiting_you")
        shown_and_gone(desk, "waiting_you")
        played = desk.fx()["calls"]
        gates = desk.page.evaluate(CENTRES, ["#deskScene [data-trassa-gate]",
                                             ".studio-trace__point"])
        orbs = desk.page.evaluate(CENTRES, ["#deskScene [data-trassa-instance]",
                                            ".studio-planet__orb"])
        waves = [call for call in played if call["fx"] == "ring"]
        comets = [call for call in played if call["fx"] == "comet"]
        assert waves and gates and comets and orbs
        for wave in waves:
            assert near(wave, gates), (wave, gates)
        for comet in comets:
            assert near(comet, orbs), (comet, orbs)


def test_a_moment_for_you_also_waves_on_the_counter_of_what_waits_when_the_desk_draws_one(
        chromium: Browser, served: Served):
    with window(chromium, served, motion=True) as desk:
        desk.page.evaluate(PLANT_COUNTER)
        desk.change("waiting_you")
        shown_and_gone(desk, "waiting_you")
        counter = desk.page.evaluate(CENTRES, ["[data-attention-count]", "none"])
        waves = [call for call in desk.fx()["calls"] if call["fx"] == "ring"]
        assert counter and any(near(wave, counter) for wave in waves), (waves, counter)


def test_a_reload_over_a_changed_project_plays_nothing_and_says_nothing(
        chromium: Browser, served: Served):
    with window(chromium, served, motion=True) as desk:
        desk.staged.stand_at("waiting_you")
        desk.page.reload(wait_until="load")
        desk.say("waiting_you")
        expect(desk.page.locator("#deskShell")).to_have_attribute("data-connection", "open")
        desk.refreshed()
        assert desk.fx() == {"calls": [], "added": []}
        expect(desk.plaque()).to_have_count(0)
        desk.change("outcome_succeeded")
        expect(desk.plaque()).to_have_text(f"{TITLE} · Succeeded")
        assert desk.fx()["calls"], "the reloaded page watches the next change"


def test_a_reconnect_over_a_changed_project_plays_nothing_and_the_next_change_still_plays(
        chromium: Browser, served: Served):
    with window(chromium, served, motion=True) as desk:
        shell = desk.page.locator("#deskShell")
        served.stop()
        expect(shell).to_have_attribute("data-connection", "closed", timeout=15000)
        desk.staged.stand_at("waiting_you")
        served.start()
        expect(shell).to_have_attribute("data-connection", "open", timeout=20000)
        desk.say("waiting_you")
        desk.refreshed()
        assert desk.fx() == {"calls": [], "added": []}
        expect(desk.plaque()).to_have_count(0)
        desk.change("outcome_succeeded")
        expect(desk.plaque()).to_have_text(f"{TITLE} · Succeeded")
        assert desk.fx()["calls"], "the reconnected page watches the next change"


def test_a_moment_waiting_on_a_stale_scene_when_the_stream_drops_is_not_shown_after_it(
        chromium: Browser, served: Served):
    """The moment is found while the scene's read is held, so it waits; the stream then drops.
    What the Desk learnt before a drop is a baseline after it, so the late read plays nothing."""
    with window(chromium, served, motion=True) as desk:
        shell = desk.page.locator("#deskShell")
        controls = Hold(desk.page, CONTROLS)
        read_again(desk.page, controls, lambda: desk.change("waiting_you"))
        served.stop()
        expect(shell).to_have_attribute("data-connection", "closed", timeout=15000)
        served.start()
        controls.land()
        expect(shell).to_have_attribute("data-connection", "open", timeout=20000)
        expect(desk.page.locator("#deskScene")).to_have_attribute("data-state", "ready")
        desk.refreshed()
        assert desk.fx() == {"calls": [], "added": []}, "a moment from before the drop played"
        expect(desk.plaque()).to_have_count(0)
        desk.change("outcome_succeeded")
        expect(desk.plaque()).to_have_text(f"{TITLE} · Succeeded")


def test_a_language_change_redraws_every_region_and_plays_nothing(
        chromium: Browser, served: Served):
    with window(chromium, served, motion=True) as desk:
        desk.page.evaluate("() => { location.hash = `#lang=ru&task=task-working`; }")
        desk.say("running", "ru")
        desk.refreshed()
        assert desk.fx() == {"calls": [], "added": []}
        expect(desk.plaque()).to_have_count(0)


def test_the_layer_outlives_a_redraw_of_every_region_and_the_plaque_with_it(
        chromium: Browser, served: Served):
    with window(chromium, served, motion=False) as desk:
        desk.change("waiting_you")
        expect(desk.plaque()).to_be_visible()
        desk.page.evaluate("() => { document.getElementById('deskMotion').marked = 7; }")
        desk.page.locator('#deskRail [data-task-id="task-closed"]').click()
        expect(desk.page.locator('#deskRail [data-task-id="task-closed"]')).to_have_attribute(
            "aria-pressed", "true")
        assert desk.page.evaluate("() => document.getElementById('deskMotion')?.marked") == 7
        expect(desk.plaque()).to_be_visible()


# -- the moment against the scene it lands on: a scene read again, and a scene left ---------------


def test_a_moment_waits_while_the_scene_is_read_again_and_then_plays_once_on_the_fresh_scene(
        chromium: Browser, served: Served):
    """The change is read (the rail says it) while the read of the scene's own run is held: the
    scene stands as stale, a scene about to be replaced, and nothing plays on it. When the read
    lands the moment is shown on the scene that was drawn from it -- its waves stand on the gate
    of THAT scene -- and one more refresh shows nothing again."""
    with window(chromium, served, motion=True) as desk:
        controls = Hold(desk.page, CONTROLS)
        read_again(desk.page, controls, lambda: desk.change("waiting_you"))
        desk.page.evaluate(QUIET)
        assert desk.fx() == {"calls": [], "added": []}, "a moment played on a stale scene"
        expect(desk.plaque()).to_have_count(0)
        land_read(desk.page, controls)
        shown_and_gone(desk, "waiting_you")
        played = desk.fx()
        gates = desk.page.evaluate(CENTRES, ["#deskScene [data-trassa-gate]",
                                             ".studio-trace__point"])
        waves = [call for call in played["calls"] if call["fx"] == "ring"]
        assert waves and gates and all(near(wave, gates) for wave in waves), (waves, gates)
        assert all(call["duration"] + call["delay"] <= FX_MAX_MS for call in played["calls"])
        desk.refreshed()
        assert desk.fx() == played, "the moment was shown more than once"
        assert desk.problems == []


def test_a_moment_of_the_task_left_marks_no_scene_now_drawn_even_when_its_read_lands_late(
        chromium: Browser, served: Served):
    """The moment of the chosen task is waiting for its scene to settle when the person chooses
    another task. The scene now drawn is the other task's: no mark stands on it, then or when the
    held read of the task left lands late (the page drops it) and the desk reads everything again.

    What stays is the plaque, and it says the moment of the task LEFT: the plaque and the halos
    belong to the rail and not to the scene, and `planOf` takes only the scene's mark from the
    task the scene draws. That is the module's rule and is held here as it stands."""
    with window(chromium, served, motion=True) as desk:
        controls = Hold(desk.page, CONTROLS)
        read_again(desk.page, controls, lambda: desk.change("waiting_you"))
        other = desk.page.locator('#deskRail [data-task-id="task-closed"]')
        other.click()
        expect(other).to_have_attribute("aria-pressed", "true")
        expect(desk.page.locator("#deskScene")).to_have_attribute("data-state", "ready")
        expect(desk.plaque()).to_have_text(f"{TITLE} · {WORDS['en']['waiting_you']}")
        desk.page.evaluate(QUIET)
        assert desk.fx()["calls"] == []
        assert set(desk.fx()["added"]) & SCENE_MARKS == set()
        controls.land()
        desk.refreshed()
        assert desk.fx()["calls"] == []
        assert drawn(desk) == set(), "a mark was drawn on the scene of the task now chosen"
        assert desk.problems == []


def test_a_panel_over_the_scene_keeps_the_plaque_and_draws_no_scene_mark(
        chromium: Browser, served: Served):
    """The scene is not on the screen while a panel covers it, so there is nothing to draw a mark
    on; the plaque says the moment all the same."""
    with window(chromium, served, motion=True) as desk:
        desk.page.locator("#deskRunToggle").click()
        expect(desk.page.locator("#deskScene")).to_be_hidden()
        desk.change("waiting_you")
        expect(desk.plaque()).to_have_text(f"{TITLE} · {WORDS['en']['waiting_you']}")
        desk.refreshed()
        assert desk.fx()["calls"] == [] and drawn(desk) == set()
        assert desk.problems == []


# -- what the layer asks of the page, and what it takes from it ---------------------------------


@pytest.mark.parametrize("motion", [True, False], ids=["motion", "reduced"])
def test_the_motion_layer_writes_nothing_and_asks_for_no_module_after_boot(
        chromium: Browser, served: Served, motion: bool):
    """From the moment the stream is open, through a moment of the scene and the entry of a new
    task: only reads, none of them for a file of the panel, all of them for the stream or the
    command API, and never the session that only a write asks for."""
    with window(chromium, served, motion=motion) as desk:
        asked = desk.listen()
        desk.change("waiting_you")
        expect(desk.plaque()).to_have_text(f"{TITLE} · {WORDS['en']['waiting_you']}")
        desk.staged.tasks.append(NEW_TASK)
        served.publish()
        expect(desk.plaque()).to_have_text("Brand new task · Not started")
        if motion:
            expect(desk.page.locator(LAYER)).to_have_count(0, timeout=5000)
        desk.refreshed()
        assert (drawn(desk) != set()) == motion, "the preference did not decide what was drawn"
        paths = [path for _method, path in asked]
        assert "/command/runs" in paths and "/command/tasks" in paths, "nothing was read"
        assert [one for one in asked if one[0] != "GET"] == []
        assert [path for path in paths if path.startswith("/panel/")] == []
        assert [path for path in paths
                if path != "/events" and not path.startswith("/command/")] == []
        assert [path for path in paths if path.startswith("/command/session")] == []
        assert desk.problems == []


#: The point in the middle of the plaque and what is under it, asked of the page: whether a press
#: on any of nine points of the plaque would land on the layer, and what the middle press would
#: hit. A listener on the document takes the next click as the page gets it.
UNDER_THE_PLAQUE = """() => {
  const layer = document.getElementById("deskMotion");
  const note = layer.querySelector("[data-fx='plaque']");
  const box = note.getBoundingClientRect();
  const at = (across, down) => ({x: box.left + box.width * across,
    y: box.top + box.height * down});
  const stands = (point) => document.elementFromPoint(point.x, point.y);
  const controls = "button, a, input, select, textarea, summary, [role='button']";
  const describe = (node) => ({tag: node.tagName, cls: node.getAttribute("class") ?? "",
    control: node.closest(controls) !== null});
  const middle = at(0.5, 0.5);
  const under = document.elementsFromPoint(middle.x, middle.y)
    .find((node) => !layer.contains(node));
  window.__pressed = null;
  document.addEventListener("click", (event) => {
    window.__pressed = {inLayer: layer.contains(event.target), ...describe(event.target)};
  }, {capture: true, once: true});
  return {
    events: {layer: getComputedStyle(layer).pointerEvents,
      plaque: getComputedStyle(note).pointerEvents},
    covered: [0.1, 0.5, 0.9].flatMap((across) => [0.2, 0.5, 0.8].map((down) => {
      const hit = stands(at(across, down));
      return hit === null || layer.contains(hit);
    })),
    under: describe(under), x: middle.x, y: middle.y};
}"""
#: Watch the layer for the next moment's first marks, and answer, in the very callback that sees
#: them, where a press at the middle of each would land. `done` is made once, with every mark the
#: callback was handed (a plaque is not one); a callback that finds none answers an empty list.
MARK_HITS = """() => {
  const layer = document.getElementById("deskMotion");
  window.__hits = new Promise((done) => {
    const watcher = new MutationObserver((records) => {
      watcher.disconnect();
      const added = records.flatMap((record) => [...record.addedNodes]);
      done(added.filter((node) => node.nodeType === 1 && node.dataset.fx !== "plaque")
        .map((mark) => {
          const box = mark.getBoundingClientRect();
          const hit = document.elementFromPoint(box.left + box.width / 2,
                                                box.top + box.height / 2);
          return {fx: mark.dataset.fx, drawn: box.width > 0 && box.height > 0,
            events: getComputedStyle(mark).pointerEvents,
            hit: hit === null ? null : layer.contains(hit)};
        }));
    });
    watcher.observe(layer, {childList: true});
  });
}"""


def test_the_motion_layer_lets_a_press_through_where_it_draws_the_plaque(
        chromium: Browser, served: Served):
    """Under reduced motion the plaque is the one thing the layer draws. Neither the layer nor the
    plaque takes a press: nine points over it find an element of the page and not the layer, and a
    real click in the middle reaches the element under it, which is no control and writes
    nothing."""
    with window(chromium, served, motion=False) as desk:
        desk.change("waiting_you")
        expect(desk.plaque()).to_be_visible()
        facts = desk.page.evaluate(UNDER_THE_PLAQUE)
        assert facts["events"] == {"layer": "none", "plaque": "none"}
        assert facts["covered"] == [False] * 9, "the layer stands where a press would land"
        assert not facts["under"]["control"], f"the middle of the plaque is over {facts['under']}"
        asked = desk.listen()
        desk.page.mouse.click(facts["x"], facts["y"])
        pressed = desk.page.evaluate("() => window.__pressed")
        assert pressed == {"inLayer": False, **facts["under"]}, "the press did not reach the page"
        assert [one for one in asked if one[0] != "GET"] == []
        assert desk.problems == []


def test_the_motion_layer_lets_a_press_through_where_it_draws_each_mark(
        chromium: Browser, served: Served):
    """With motion allowed, the marks of a moment stand over the scene. At the moment the layer
    is first handed them -- in the callback of an observer on the layer, with no wait of any
    length -- the middle of each is over an element of the page and not over the layer."""
    with window(chromium, served, motion=True) as desk:
        desk.page.evaluate(MARK_HITS)
        desk.change("waiting_you")
        marks = desk.page.evaluate("() => window.__hits")
        assert {"comet", "ring"} <= {mark["fx"] for mark in marks}, marks
        assert all(mark["drawn"] and mark["events"] == "none" and mark["hit"] is False
                   for mark in marks), marks
        assert desk.problems == []
