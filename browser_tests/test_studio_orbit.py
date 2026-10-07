"""Role navigation on the real renderer, and its existing durable edit road.

The small definition below is a renderer witness, not a runnable workflow.
The last test walks the actual served draft, inspector, save and read-back.
No harness, quota source or runtime binding is fabricated by the orbit.
"""
from __future__ import annotations

import pytest

from browser_tests.test_studio_editing import (  # noqa: F401
    WORKFLOW_ID, _Bench, bench, studio_url,
)
from browser_tests.test_studio_positions import _reopened_from_the_server
from conductor.command.template_store import TemplateStore


def _state():
    return {"workflows": {"selectedId": "one", "draft": {
        "nodes": [
            {"node_id": "build", "kind": "task", "title": "Build it",
             "role_id": "maker", "verifier_role_id": "checker"},
            {"node_id": "repair", "kind": "task", "title": "Repair it",
             "role_id": "maker", "verifier_role_id": "maker"},
            {"node_id": "human", "kind": "gate", "title": "Accept"},
            {"node_id": "unbound", "kind": "task", "title": "Still unassigned",
             "verifier_role_id": "checker"}], "edges": []}},
        "canvas": {"selection": {"kind": None, "id": None}},
        "runs": {"detail": {"config": {"instances": [
            {"id": "maker", "adapter": "FOREIGN-PROVIDER"}]}}}}


def _mount(bench, state):
    bench.page.evaluate("""async state => {
      const {mountCanvas} = await import('/panel/studio-canvas.js');
      let mount = document.getElementById('orbitBench');
      if (!mount) {
        mount = document.createElement('div'); mount.id = 'orbitBench';
        mount.className = 'studio-canvas studio-shell'; document.body.append(mount);
      }
      window.orbitState = state;
      const handlers = {onSelect: selection => {
        window.orbitState.canvas.selection = selection; render();
      }};
      const render = () => mountCanvas(mount, null, window.orbitState, handlers);
      render();
    }""", state)
    return bench.page.locator("#orbitBench")


def test_roles_group_both_duties_and_never_hide_unassigned_steps(bench):
    root = _mount(bench, _state())
    before = list(bench.recorder.rows)
    root.locator('[data-lens="team"]').click()
    assert root.locator("[data-orbit-role]").count() == 3
    assert root.locator("[data-orbit-step]").count() == 2
    assert "perform + verify" in root.locator(".studio-orbit__duties").inner_text()
    root.locator('[data-orbit-role="checker"]').click()
    assert root.locator("[data-orbit-step]").count() == 2
    assert "verify" in root.locator(".studio-orbit__duties").inner_text()
    root.locator('[data-orbit-role=""]').click()
    assert root.locator("[data-orbit-step]").count() == 2
    assert "human decision" in root.locator(".studio-orbit__duties").inner_text()
    assert "FOREIGN-PROVIDER" not in root.inner_text()
    assert "Roles · not live agents" in root.inner_text()
    assert [r for r in bench.recorder.rows if r[0] == "POST"] == [
        r for r in before if r[0] == "POST"]
    assert bench.problems == []


def test_verifier_choice_and_focus_survive_a_step_selection_and_a_read(bench):
    root = _mount(bench, _state())
    root.locator('[data-lens="team"]').press("Enter")
    checker = root.locator('[data-orbit-role="checker"]')
    checker.press("Enter")
    step = root.locator('[data-orbit-step="build"]')
    step.press("Enter")
    assert step.evaluate("el => el === document.activeElement")
    assert checker.get_attribute("aria-pressed") == "true"
    assert step.get_attribute("aria-pressed") == "true"
    state = bench.page.evaluate("() => window.orbitState")
    _mount(bench, state)
    assert checker.get_attribute("aria-pressed") == "true"
    assert step.evaluate("el => el === document.activeElement")
    state["workflows"]["draft"]["nodes"][0]["verifier_role_id"] = "new-reviewer"
    state["workflows"]["draft"]["nodes"][3].pop("verifier_role_id")
    _mount(bench, state)
    assert root.locator('[data-orbit-role="checker"]').count() == 0
    assert root.locator('[data-orbit-role="maker"]').get_attribute("aria-pressed") == "true"


@pytest.mark.parametrize("change", ["workflow", "revision"])
def test_choice_cannot_cross_document_identity(bench, change):
    state = _state()
    root = _mount(bench, state)
    root.locator('[data-lens="team"]').click()
    root.locator('[data-orbit-role="checker"]').click()
    if change == "workflow":
        state["workflows"]["selectedId"] = "two"
    else:
        doc = state["workflows"].pop("draft")
        state["workflows"]["detail"] = {"published": {**doc, "revision": 2}}
    _mount(bench, state)
    assert root.locator('[data-lens="connections"]').get_attribute("aria-pressed") == "true"
    assert not root.locator(".studio-orbit").is_visible()
    root.locator('[data-lens="team"]').click()
    assert root.locator('[data-orbit-role="maker"]').get_attribute("aria-pressed") == "true"


@pytest.mark.parametrize("width,count,length", [
    (390, 3, 120), (1280, 8, 120), (1280, 12, 120), (1280, 8, 0)])
def test_roles_reflow_without_overlap_even_with_long_names(bench, width, count, length):
    bench.page.set_viewport_size({"width": width, "height": 950})
    state = _state()
    state["workflows"]["draft"]["nodes"] = [
        {"node_id": f"n-{i}", "kind": "task", "title": f"Step {i}",
         "role_id": f"role-{i}" + "x" * length} for i in range(count)]
    root = _mount(bench, state)
    root.locator('[data-lens="team"]').click()
    boxes = root.locator("[data-orbit-role]").evaluate_all("""nodes => nodes.map(n => {
      const r = n.getBoundingClientRect(); return {x:r.x,y:r.y,right:r.right,bottom:r.bottom};
    })""")
    for at, a in enumerate(boxes):
        for b in boxes[at + 1:]:
            assert a["right"] <= b["x"] or b["right"] <= a["x"] or (
                a["bottom"] <= b["y"] or b["bottom"] <= a["y"]), (a, b)
    assert root.evaluate("el => el.scrollWidth <= el.clientWidth")


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_orbit_focus_is_visible_and_a_resize_keeps_the_chosen_role(bench, theme):
    page = bench.page
    page.emulate_media(color_scheme=theme, reduced_motion="reduce")
    root = _mount(bench, _state())
    root.locator('[data-lens="team"]').press("Enter")
    chosen = root.locator('[data-orbit-role="checker"]')
    chosen.press("Enter")
    assert chosen.evaluate("el => parseFloat(getComputedStyle(el).outlineWidth)") >= 2
    assert chosen.get_attribute("aria-pressed") == "true"
    assert "Selected" in chosen.inner_text()
    page.set_viewport_size({"width": 390, "height": 900})
    assert chosen.get_attribute("aria-pressed") == "true"
    assert chosen.evaluate("el => el === document.activeElement")
    assert root.evaluate("el => el.scrollWidth <= el.clientWidth")
    assert bench.problems == []


def test_compacting_during_resize_does_not_emit_an_observer_loop_error(bench):
    state = _state()
    state["workflows"]["draft"]["nodes"] = [
        {"node_id": f"n-{i}", "kind": "task", "role_id": f"role-{i}"}
        for i in range(8)]
    root = _mount(bench, state)
    root.locator('[data-lens="team"]').click()
    fleet = root.locator(".studio-orbit__fleet")
    assert "--compact" not in fleet.get_attribute("class")
    bench.page.set_viewport_size({"width": 1280, "height": 900})
    bench.page.wait_for_function("""() => document.querySelector(
        '#orbitBench .studio-orbit__fleet').classList.contains('studio-orbit__fleet--compact')""")
    bench.page.evaluate("() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))")
    assert bench.problems == []


def test_orbit_opens_the_real_inspector_and_its_saved_edit_survives_reload(bench, tmp_path):
    page = bench.page
    page.locator('#workflowNodes [data-lens="team"]').click()
    page.locator('#workflowNodes [data-orbit-step="alpha"]').click()
    title = page.locator('#workflowInspector [data-edit-field="title"]')
    title.fill("A useful task")
    title.press("Tab")
    assert page.locator('#workflowNodes [data-orbit-step="alpha"]').inner_text().startswith(
        "A useful task")
    page.locator('#workflowToolbar [data-focus="action:onSaveDraft"]').click()
    page.wait_for_selector('#workflowToolbar [data-save="saved"]')
    stored = TemplateStore(tmp_path).load_draft(WORKFLOW_ID)
    assert stored.document["nodes"][0]["title"] == "A useful task"
    assert [n["node_id"] for n in stored.document["nodes"]] == ["alpha", "beta", "gamma"]
    _reopened_from_the_server(bench)
    assert "A useful task" in bench.node("alpha").inner_text()
    # Back on the connection canvas, the original keyboard move still acts on
    # the same step; navigation has neither duplicated it nor reordered it.
    bench.node("alpha").click()
    bench.node("alpha").press("Alt+ArrowRight")
    assert bench.node("alpha").evaluate(
        "el => parseFloat(el.style.getPropertyValue('--x'))") > 0
    assert bench.node_ids() == ["alpha", "beta", "gamma"]
    assert bench.problems == []
