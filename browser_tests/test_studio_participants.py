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


def _inspector(page: Page):
    return page.locator("#deckTest .studio-deck__inspector")


def test_planets_follow_instance_identity_and_include_verifier_only_duties(studio):
    page, problems = studio
    _mount(page, _detail())
    assert page.locator("#deckTest .studio-planet").count() == 3
    assert _inspector(page).locator(".studio-deck__step").count() == 2
    page.locator('#deckTest [data-instance="beta"]').click()
    assert _inspector(page).locator(".studio-deck__step").count() == 1
    assert "Responsibility: verify" in _inspector(page).inner_text()
    assert "Model: chosen" in _inspector(page).inner_text()
    page.locator('#deckTest [data-instance="standby"]').click()
    assert "No plan step is assigned" in _inspector(page).inner_text()
    assert problems == []


def test_unknowns_and_execution_are_not_rewritten_as_success_or_capacity(studio):
    page, _ = studio
    _mount(page, _detail())
    body = _inspector(page).inner_text()
    assert "pinned no model" in body and "controls read has not landed" in body
    assert "Execution phase: observed" in body and "Plan position: blocked" in body
    assert "Process exit 0 proves the process finished" in body
    assert "Missing documents: finding-notes" in body
    assert "Waiting on: check" in body and "Route: repair · on_failed" in body
    assert "reset time are not reported" in body and "0%" not in body
    detail = _detail()
    detail["graph"]["runtime"] = None
    detail["graph"]["schedule"] = None
    _mount(page, detail)
    assert "Execution phase: not stated" in _inspector(page).inner_text()
    assert "Plan position: not stated" in _inspector(page).inner_text()
    detail["controls"] = {"instances": [{"instance_id": "alpha", "controls": []}]}
    _mount(page, detail)
    assert "Capabilities this build can serve: none served by this build" in (
        _inspector(page).inner_text())


def test_keyboard_selection_and_focus_survive_same_run_read_but_not_another_run(studio):
    page, _ = studio
    detail = _detail()
    _mount(page, detail)
    beta = page.locator('#deckTest [data-instance="beta"]')
    beta.focus()
    beta.press("Enter")
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
      selected: root.querySelector('[aria-pressed="true"]')
        .querySelector('.studio-planet__selection').textContent,
      ring: getComputedStyle(root.querySelector('.studio-planet__orb')).borderStyle
    })""")
    assert measured["scroll"] <= measured["width"]
    assert measured["selected"] == "Selected" and measured["ring"] == "double"


def test_no_participants_and_no_plan_are_visible_not_filled_with_demo_harnesses(studio):
    page, _ = studio
    detail = _detail()
    detail["config"]["instances"] = []
    detail["graph"] = None
    _mount(page, detail)
    assert page.locator("#deckTest .studio-planet").count() == 0
    assert "binds no instance" in page.locator("#deckTest .studio-deck").inner_text()


def test_default_unconditional_route_is_known_not_missing(studio):
    page, _ = studio
    detail = _detail()
    del detail["graph"]["definition"]["edges"][0]["condition"]
    _mount(page, detail)
    assert "Route: repair · unconditional" in _inspector(page).inner_text()
