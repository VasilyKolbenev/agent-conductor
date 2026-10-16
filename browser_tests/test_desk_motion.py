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
"""
from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Browser, expect

from browser_tests.desk_motion_bench import (
    NEW_TASK, TASK, TITLE, WORDS, Desk, Served, Staged, serve, wiring, window)

FX_MAX_MS = 1200
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


def test_the_page_is_served_the_two_wiring_lines_only_while_the_product_lacks_them():
    """The product's scene carries the lines, or the page is served a scene with exactly those
    two lines more; no other module is ever served an edit here."""
    panel = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
    edited = wiring()
    carried = any("desk-motion.js" in (panel / name).read_text(encoding="utf-8")
                  for name in ("desk.js", "desk-scene.js"))
    if carried:
        assert edited == {}
        return
    assert set(edited) == {"desk-scene.js"}
    product = (panel / "desk-scene.js").read_text(encoding="utf-8")
    served = edited["desk-scene.js"].decode("utf-8")
    assert len(served.splitlines()) == len(product.splitlines()) + 2
    assert served.count("watchMotion") == 2


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
