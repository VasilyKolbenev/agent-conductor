"""A task-bound run's saved facts appear in the Desk's read-only detail panel."""
from __future__ import annotations

from playwright.sync_api import Browser, expect

from browser_tests.test_desk_map import booted, desk_url  # noqa: F401


def test_real_run_panel_reads_passport_steps_and_history_then_selects_an_older_run(
        chromium: Browser, desk_url):
    page, asked = booted(chromium, desk_url,
                         "#task=task-fix&run=run-fix-new&panel=run&lang=ru")
    writes = []
    page.on("request", lambda request: writes.append(request.url)
            if request.method != "GET" else None)
    try:
        panel = page.locator("#deskRun")
        expect(panel).to_be_visible()
        expect(panel.locator('[data-subject="run:run-fix-new"]')).to_be_visible()
        expect(panel).to_contain_text("task-fix")
        assert panel.locator(".studio-runs__rows .studio-run").count() == 2
        assert panel.locator(".studio-positions li").count() > 0
        assert panel.locator(".studio-timeline li").count() > 0
        # The read panel now carries the Studio document form for this saved plan.
        assert panel.locator('[data-step="document"]').count() == 1
        assert "/command/runs/run-fix-new" in asked
        panel.locator(".studio-run-picker summary").click()
        panel.locator(".studio-run").filter(has_text="run-fix-old").click()
        expect(panel.locator('[data-subject="run:run-fix-old"]')).to_be_visible()
        assert "run=run-fix-old" in page.url
        assert writes == []
    finally:
        page.context.close()


def test_panel_selection_cannot_land_after_another_task_was_chosen(
        chromium: Browser, desk_url):
    page, _asked = booted(chromium, desk_url,
                          "#task=task-fix&run=run-fix-new&panel=run&lang=en")
    held, errors = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/command/runs/run-fix-old", lambda route: held.append(route))
    try:
        panel = page.locator("#deskRun")
        expect(panel.locator('[data-subject="run:run-fix-new"]')).to_be_visible()
        panel.locator(".studio-run-picker summary").click()
        with page.expect_request("**/command/runs/run-fix-old"):
            panel.locator(".studio-run").filter(has_text="run-fix-old").click()
        page.locator('#deskRail [data-task-id="task-docs"]').click()
        expect(panel.locator('[data-subject="run:run-docs"]')).to_be_visible()
        held[0].continue_()
        page.evaluate("() => new Promise((done) => requestAnimationFrame(() => "
                      "requestAnimationFrame(done)))")
        expect(panel.locator('[data-subject="run:run-docs"]')).to_be_visible()
        assert "task=task-docs" in page.url and "run=run-docs" in page.url
        assert errors == []
    finally:
        page.unroute_all(behavior="ignoreErrors")
        page.context.close()
