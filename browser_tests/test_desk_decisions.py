"""The Desk's always-visible gate card writes a task-bound decision on the real server."""
from __future__ import annotations

from playwright.sync_api import Browser, expect

from browser_tests.desk_identity import identified_server
from browser_tests.test_desk_rail_scene import _seed
from conductor.command.run_store import RunStore
from tests.test_store import good_lane, write_project

PROJECT = "a" * 32


def _world(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    _seed(root)
    return root


def test_current_gate_in_pult_records_a_receipt_without_opening_the_run_panel(
        tmp_path, chromium: Browser):
    root = _world(tmp_path)
    with identified_server(root, PROJECT) as origin:
        context = chromium.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(f"{origin}/panel/desk.html#project={PROJECT}&task=task-fix"
                      "&run=run-fix-new&lang=en")
            card = page.locator("#deskPult [data-desk-decision]")
            expect(card).to_be_visible()
            expect(page.locator("#deskRun")).to_be_hidden()
            expect(card).to_contain_text("Human Gate")
            page.locator('[data-focus-key="pult:actor-change"]').click()
            page.locator('[data-focus-key="pult:actor-name"]').fill("desk-owner")
            page.locator('[data-focus-key="pult:actor-save"]').click()
            expect(card).to_contain_text("desk-owner")
            button = card.locator('[data-focus-key="action:submitDecision"]')
            expect(button).to_be_enabled()
            with page.expect_response(lambda response: response.url.endswith("/decisions")) as sent:
                button.click()
            assert sent.value.status == 201, sent.value.json()
            recorded = [row.value for row in RunStore(root).read("run-fix-new").records
                        if row.kind == "decision"]
            assert len(recorded) == 1
            assert recorded[0].gate_id == "gate-confirm-do"
            assert recorded[0].actor == "desk-owner"
            assert errors == []
        finally:
            context.close()


def test_view_gate_is_visible_with_a_disabled_reason(tmp_path, chromium: Browser):
    root = _world(tmp_path)
    with identified_server(root, PROJECT, mode="view") as origin:
        context = chromium.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        writes: list[str] = []
        page.on("request", lambda request: writes.append(request.url)
                if request.method == "POST" else None)
        try:
            page.goto(f"{origin}/panel/desk.html#project={PROJECT}&task=task-fix"
                      "&run=run-fix-new&lang=ru")
            card = page.locator("#deskPult [data-desk-decision]")
            expect(card).to_be_visible()
            expect(card).to_contain_text("Проект открыт для просмотра")
            expect(card.locator('[data-focus-key="action:submitDecision"]')).to_be_disabled()
            assert writes == []
        finally:
            context.close()
