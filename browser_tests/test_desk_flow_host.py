"""The desk's flow host uses its shared transport against the real flow route."""
from __future__ import annotations

import uuid

from playwright.sync_api import Browser, expect

from browser_tests.desk_flow_bench import desk_url  # noqa: F401


def test_flow_host_renders_a_new_cycle_and_saves_an_edit_through_transport(
        chromium: Browser, desk_url: str):  # noqa: F811
    context = chromium.new_context(viewport={"width": 900, "height": 1200})
    try:
        page = context.new_page()
        page.goto(f"{desk_url}/panel/desk.html", wait_until="load")
        page.add_style_tag(url=f"{desk_url}/panel/desk-flow.css")
        nonce = uuid.uuid4().hex
        page.evaluate("""async (nonce) => {
          const {createFlowHost} = await import('/panel/desk-flow-host.js');
          const {createTransport} = await import('/panel/desk-transport.js');
          const mount = document.createElement('div');
          document.body.append(mount);
          const door = createTransport(() => 'en');
          window.flowHost = createFlowHost({mount, door, locale: () => 'en', nonce,
            onForeign: () => { throw new Error('unexpected foreign project'); }});
          window.flowHost.open();
          window.flowHost.dispatch({type: 'new', from: 'empty', title: 'Host witness'});
        }""", nonce)
        expect(page.locator("[data-flow]")).to_have_attribute("data-flow-phase", "ready")
        page.locator('[data-add-kind="analyst"]').click()
        expect(page.locator("[data-flow]")).to_have_attribute("data-flow-save", "saved")
        answer = page.evaluate("""async () => {
          const id = window.flowHost.state().write.workflowId;
          const response = await fetch(`/command/workflows/${encodeURIComponent(id)}/flow`);
          return {id, payload: await response.json()};
        }""")
        assert answer["id"].startswith("cycle-")
        assert answer["payload"]["source"] == "draft"
        assert [step["step_id"] for step in answer["payload"]["flow"]["steps"]] == ["analyst"]
        page.locator('[data-node-id="analyst"]').click()
        expect(page.locator("[data-flow-inspector]")).to_have_attribute("data-selected", "analyst")
        layout = page.evaluate("""() => {
          const canvas = document.querySelector('[data-flow-canvas]');
          const inspector = document.querySelector('[data-flow-inspector]');
          return {node: getComputedStyle(document.querySelector('[data-node-id="analyst"]'))
            .position, overflow: getComputedStyle(canvas).overflowX,
            inspectorRight: inspector.getBoundingClientRect().right,
            inspectorWidth: inspector.scrollWidth, available: inspector.clientWidth};
        }""")
        assert layout["node"] == "absolute" and layout["overflow"] == "auto"
        assert layout["inspectorRight"] <= 900 and layout["inspectorWidth"] <= layout["available"]
        page.evaluate("() => window.flowHost.dispose()")
        expect(page.locator("[data-flow]")).to_have_count(0)
    finally:
        context.close()
