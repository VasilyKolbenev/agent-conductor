"""The command deck's real DOM, plus the existing full run-route witnesses.

These small payloads deliberately exercise the renderer boundary, not the HTTP
schema. The neighboring run-journal module supplies the production store/read
road; this module supplies cases such as shared adapters and verifier-only
assignments that its seed does not contain. No vendor is installed or invoked.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from browser_tests.test_studio_rendered import studio, studio_url  # noqa: F401


def _detail() -> dict:
    return {
        "run": {"run_id": "run-one", "mode": "observe"},
        "config": {"instances": [
            {"id": "alpha", "adapter": "sample-harness"},
            {"id": "beta", "adapter": "sample-harness", "model": "chosen"},
            {"id": "standby", "adapter": "another-harness"}]},
        "controls": None, "records": [],
        "graph": {"definition": {"nodes": [
            {"node_id": "analyse", "title": "Find the cause", "kind": "task",
             "instance_id": "alpha", "verifier_instance_id": "beta"},
            {"node_id": "repair", "title": "Fix the cause", "kind": "task",
             "instance_id": "alpha"}], "edges": [
            {"from_node": "analyse", "to_node": "repair", "condition": "on_failed"}]},
            "runtime": {"nodes": [
                {"node_id": "analyse", "phase": "observed",
                 "outcome": "verification_failed", "attempt_ids": []},
                {"node_id": "repair", "phase": "idle", "outcome": None,
                 "attempt_ids": []}]},
            "schedule": {"nodes": [
                {"node_id": "analyse", "state": "settled"},
                {"node_id": "repair", "state": "blocked", "blocked_by": ["check"],
                 "awaiting_artifacts": ["finding-notes"]}]}}}


def _mount(page: Page, detail: dict) -> None:
    page.evaluate("""async detail => {
      const {mountRuns} = await import('/panel/studio-runs.js');
      let mount = document.getElementById('deckTest');
      if (!mount) {
        mount = document.createElement('div'); mount.id = 'deckTest';
        mount.className = 'studio-shell'; document.body.append(mount);
      }
      mountRuns(mount, {runs: {phase: 'ready', list: [],
        selectedId: detail.run.run_id, detail}}, {});
    }""", detail)
    orbit = page.locator('#deckTest [data-run-lens="orbit"]')
    if orbit.count() and orbit.get_attribute("aria-pressed") != "true":
        orbit.evaluate("node => node.click()")  # the lens, without moving focus onto its button


def _inspector(page: Page):
    return page.locator("#deckTest .studio-deck__inspector")


def _tab(page: Page, name: str):
    # These are native disclosures now, not permanent navigation tabs.
    if name == "Task":
        for fold in _inspector(page).locator("details[open]").all():
            fold.locator("summary").click()
        name = "Parameters"
    if name == "Technical details":
        name = "Parameters"
    summary = _inspector(page).get_by_text(name, exact=True)
    if not summary.evaluate("el => el.parentElement.open"):
        summary.click()
    return summary


def test_planets_follow_instance_identity_and_include_verifier_only_duties(studio):
    page, problems = studio
    _mount(page, _detail())
    assert page.locator("#deckTest .studio-deck__fleet .studio-planet").count() == 3
    assert _inspector(page).get_by_role("combobox").locator("option").count() == 2
    page.locator('#deckTest [data-instance="beta"]').click()
    assert _inspector(page).locator(".studio-deck__step").count() == 1
    assert "Review assignment" in _inspector(page).inner_text()
    _tab(page, "Parameters")
    assert "Model: chosen" in _inspector(page).inner_text()
    page.locator('#deckTest [data-instance="standby"]').click()
    assert "No plan step is assigned" in _inspector(page).inner_text()
    assert problems == []


def test_unknowns_and_execution_are_not_rewritten_as_success_or_capacity(studio):
    page, _ = studio
    _mount(page, _detail())
    _tab(page, "Parameters")
    body = _inspector(page).inner_text()
    assert "pinned no model" in body and "controls read has not landed" in body
    assert "reset time are not reported" in body and "0%" not in body
    _tab(page, "Task")
    body = _inspector(page).inner_text()
    assert "Execution phase: observed" in body
    assert "Process exit 0 proves the process finished" in body
    assert "Route: repair · on_failed" in body
    _inspector(page).get_by_role("combobox").select_option("repair")
    body = _inspector(page).inner_text()
    assert "Waiting" in body and "Plan position:" not in body
    assert "Missing documents: finding-notes" in body
    assert "Waiting on: check" in body
    _tab(page, "Technical details")
    assert "Plan position: blocked" in _inspector(page).inner_text()
    detail = _detail()
    detail["graph"]["runtime"] = None
    detail["graph"]["schedule"] = None
    _mount(page, detail)
    assert "Execution phase: not stated" in _inspector(page).inner_text()
    assert "Plan position: not stated" in _inspector(page).inner_text()
    detail["controls"] = {"instances": [{"instance_id": "alpha", "controls": []}]}
    _mount(page, detail)
    _tab(page, "Parameters")
    assert "Capabilities this build can serve: none served by this build" in (
        _inspector(page).inner_text())


def test_keyboard_selection_and_focus_survive_same_run_read_but_not_another_run(studio):
    page, _ = studio
    detail = _detail()
    _mount(page, detail)
    beta = page.locator('#deckTest [data-instance="beta"]')
    beta.focus()
    beta.press("Enter")
    _tab(page, "Parameters")
    beta.focus()
    detail["config"]["instances"][1]["model"] = "changed-by-new-read"
    _mount(page, detail)
    assert beta.get_attribute("aria-pressed") == "true"
    assert beta.evaluate("node => node === document.activeElement")
    assert "changed-by-new-read" in _inspector(page).inner_text()
    detail["run"]["run_id"] = "run-two"
    _mount(page, detail)
    assert page.locator('#deckTest [data-instance="alpha"]').get_attribute(
        "aria-pressed") == "true"
    assert "changed-by-new-read" not in _inspector(page).inner_text()


@pytest.mark.parametrize("width", [390, 1280])
def test_long_instance_ids_remain_inside_the_page_and_selection_is_not_colour_only(
        studio, width):
    page, _ = studio
    page.set_viewport_size({"width": width, "height": 900})
    detail = _detail()
    detail["config"]["instances"][0]["id"] = "a" * 128
    _mount(page, detail)
    box = page.locator("#deckTest")
    measured = box.evaluate("""root => ({
      width: root.clientWidth, scroll: root.scrollWidth,
      selected: root.querySelector('.studio-deck__fleet .studio-planet[aria-pressed="true"]')
        .querySelector('.studio-planet__selection').textContent,
      ring: getComputedStyle(root.querySelector('.studio-deck__fleet [aria-pressed="true"] .studio-planet__orb')).borderStyle
    })""")
    assert measured["scroll"] <= measured["width"]
    assert measured["selected"] == "Selected" and measured["ring"] == "double"


def test_no_participants_and_no_plan_are_visible_not_filled_with_demo_harnesses(studio):
    page, _ = studio
    detail = _detail()
    detail["config"]["instances"] = []
    detail["graph"] = None
    _mount(page, detail)
    assert page.locator("#deckTest .studio-deck__fleet .studio-planet").count() == 0
    assert "binds no participants" in page.locator("#deckTest .studio-deck").inner_text()


def test_default_unconditional_route_is_known_not_missing(studio):
    page, _ = studio
    detail = _detail()
    del detail["graph"]["definition"]["edges"][0]["condition"]
    _mount(page, detail)
    _tab(page, "Technical details")
    assert "Route: repair · unconditional" in _inspector(page).inner_text()


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_command_deck_has_depth_and_adjacent_inspector_without_losing_actions(studio, theme):
    page, problems = studio
    page.emulate_media(color_scheme=theme)
    page.set_viewport_size({"width": 1280, "height": 900})
    _mount(page, _detail())
    fleet = page.locator("#deckTest .studio-deck__fleet")
    panel = _inspector(page)
    geometry = fleet.bounding_box(), panel.bounding_box()
    assert abs(geometry[0]["y"] - geometry[1]["y"]) < 2
    assert abs(geometry[0]["x"] + geometry[0]["width"] - geometry[1]["x"]) < 2
    assert geometry[1]["width"] == 298
    material = page.locator("#deckTest .studio-planet__orb").first.evaluate(
        "el => ({image: getComputedStyle(el).backgroundImage, "
        "shadow: getComputedStyle(el).boxShadow})")
    assert "radial-gradient" in material["image"] and "inset" in material["shadow"]
    about = page.locator("#deckTest .studio-deck__about")
    assert about.get_attribute("open") is None
    about.locator("summary").click()
    assert "selecting one does not start it" in about.inner_text()
    page.locator('#deckTest [data-instance="beta"]').click()
    assert "Review assignment" in panel.inner_text()
    assert problems == []


def test_disclosures_keyboard_and_step_survive_only_the_same_run(studio):
    page, problems = studio
    detail = _detail()
    _mount(page, detail)
    _inspector(page).get_by_role("combobox").select_option("repair")
    assert _inspector(page).get_by_role("tab").count() == 0
    assert _inspector(page).locator("details[open]").count() == 0
    parameters = _inspector(page).get_by_text("Parameters", exact=True)
    parameters.press("Enter")
    history = _inspector(page).get_by_text("History", exact=True)
    history.press("Space")
    _mount(page, detail)
    assert _inspector(page).locator("details[open]").count() == 2
    assert history.evaluate("el => el === document.activeElement")
    assert _inspector(page).get_by_role("combobox").input_value() == "repair"
    assert "No records explicitly name" in _inspector(page).inner_text()
    _tab(page, "Technical details")
    _mount(page, detail)
    assert _inspector(page).locator("details[open]").count() == 2
    page.locator('#deckTest [data-instance="alpha"]').click()
    assert _inspector(page).locator("details[open]").count() == 2
    _inspector(page).get_by_role("combobox").select_option("analyse")
    assert _inspector(page).locator('[data-detail-fold="parameters"]').get_attribute("open") is None
    detail["run"]["run_id"] = "other-run"
    _mount(page, detail)
    assert _inspector(page).locator("details[open]").count() == 0
    assert _inspector(page).get_by_role("combobox").input_value() == "analyse"
    assert problems == []


def test_history_names_only_explicit_participants_and_keeps_failure_explanation(studio):
    page, _ = studio
    detail = _detail()
    detail["records"] = [
        {"record_type": "action_result", "record": {"instance_id": "somebody-else",
         "action_id": "foreign-action", "outcome": "succeeded"}},
        {"record_type": "action_result", "record": {"instance_id": "alpha",
         "action_id": "mine", "outcome": "verification_failed"}},
        {"record_type": "action_result", "record": {"instance_id": "somebody-else",
         "verifier_instance_id": "alpha", "action_id": "checked-by-me", "outcome": "failed"}},
    ]
    _mount(page, detail)
    _tab(page, "History")
    text = _inspector(page).inner_text()
    assert "foreign-action" not in text and "mine" in text and "checked-by-me" in text
    assert "Process exit 0 proves the process finished" in text
    assert _inspector(page).get_by_role("region", name="History").locator("li").evaluate_all(
        "items => items.map(item => item.value)") == [2, 3]


def test_read_only_pane_and_about_remain_keyboard_reachable_after_refresh(studio):
    page, _ = studio
    detail = _detail()
    _mount(page, detail)
    history = _tab(page, "History")
    history.press("Tab")
    pane = _inspector(page).get_by_role("region", name="History")
    assert pane.evaluate("el => el === document.activeElement")
    _mount(page, detail)
    assert pane.evaluate("el => el === document.activeElement")
    about = page.locator("#deckTest .studio-deck__about summary")
    about.focus()
    about.press("Enter")
    _mount(page, detail)
    assert about.evaluate("el => el === document.activeElement")
    assert page.locator("#deckTest .studio-deck__about").get_attribute("open") is not None


def test_run_picker_remembers_closed_state_before_a_run_is_selected(studio):
    page, _ = studio
    _mount(page, _detail())
    def empty_read():
        page.evaluate("""async () => {
          const {mountRuns} = await import('/panel/studio-runs.js');
          mountRuns(document.getElementById('deckTest'), {runs: {
            phase: 'ready', list: [], selectedId: null, detail: null}}, {});
        }""")
    empty_read()
    picker = page.locator("#deckTest .studio-run-picker")
    assert picker.get_attribute("open") is not None
    picker.locator("summary").click()
    empty_read()
    assert picker.get_attribute("open") is None
    assert picker.locator("summary").evaluate("el => el === document.activeElement")


def test_history_read_position_survives_live_read_but_not_new_run(studio):
    page, _ = studio
    detail = _detail()
    detail["records"] = [{"record_type": "action_result", "record": {
        "instance_id": "alpha", "action_id": f"action-{n}", "outcome": "failed"}}
        for n in range(30)]
    _mount(page, detail)
    _tab(page, "History").press("Tab")
    panel = _inspector(page)
    panel.evaluate("el => {el.scrollTop = 280}")
    assert panel.evaluate("el => el.scrollTop") == 280
    _mount(page, detail)
    assert panel.evaluate("el => el.scrollTop") == 280
    detail["run"]["run_id"] = "other-run"
    _mount(page, detail)
    assert panel.evaluate("el => el.scrollTop") == 0


@pytest.mark.parametrize("state,phrase", [("blocked", "Waiting"), ("unreachable", "Route closed")])
def test_compact_status_keeps_a_blocked_step_visible_without_a_reason_array(studio, state, phrase):
    page, _ = studio
    detail = _detail()
    detail["graph"]["runtime"] = None
    detail["graph"]["schedule"] = {"nodes": [{"node_id": "analyse", "state": state}]}
    _mount(page, detail)
    assert _inspector(page).locator("details[open]").count() == 0
    assert phrase in _inspector(page).inner_text()
    detail["graph"]["schedule"] = None
    _mount(page, detail)
    assert "Status unavailable" in _inspector(page).inner_text()


def test_failed_verification_is_visible_before_any_details_are_opened(studio):
    page, _ = studio
    _mount(page, _detail())
    assert _inspector(page).locator("details[open]").count() == 0
    body = _inspector(page).inner_text()
    assert "Verification failed" in body and "Process exit 0 proves the process finished" in body
    assert "Execution phase:" not in body and "Route:" not in body
    page.locator('#deckTest [data-instance="beta"]').click()
    assert "Review assignment · status belongs to the step" in _inspector(page).inner_text()


def test_routes_derive_from_bound_identity_and_refresh_geometry(studio):
    page, problems = studio
    detail = _detail()
    _mount(page, detail)
    route = page.locator('#deckTest .studio-deck__route[data-from="alpha"][data-to="beta"]')
    route.wait_for(state="attached")
    assert page.locator("#deckTest .studio-deck__route").count() == 1
    assert "verification" in route.text_content()
    label = page.locator("#deckTest .studio-deck__route-label")
    assert label.is_visible() and label.get_attribute("data-kind") == "verification"
    assert label.locator("path").count() == 1 and label.locator("text").count() == 0
    before = route.get_attribute("d")
    page.set_viewport_size({"width": 620, "height": 900})
    page.wait_for_function("before => document.querySelector('#deckTest .studio-deck__route').getAttribute('d') !== before", arg=before)
    detail["config"]["instances"] = detail["config"]["instances"][:1]
    _mount(page, detail)
    assert page.locator("#deckTest .studio-deck__route").count() == 0
    _tab(page, "Technical details")
    assert "Route: repair · on_failed" in _inspector(page).inner_text()
    assert problems == []
