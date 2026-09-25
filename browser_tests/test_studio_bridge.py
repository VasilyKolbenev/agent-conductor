"""The approved Bridge uses the real frozen run and keeps one inspector."""
from playwright.sync_api import Browser, expect

from browser_tests.test_studio_layout import _model_form, configured_project, project  # noqa: F401
from browser_tests.test_studio_lifecycle import _Project, _open, _settle
from browser_tests.test_studio_tasks import _open_run
from conductor.command.run_store import RunStore


def test_real_run_trace_and_orbit_share_selection_without_writing(
        chromium: Browser, configured_project: _Project, tmp_path):
    page, window = _open(chromium, configured_project, double=True)
    try:
        _model_form(page, "bridge-flow")
        _open_run(page, "bridge-run")
        page.locator("#navRuns").click()
        deck = page.locator('[data-deck-run="bridge-run"]')
        expect(deck.locator(".studio-trace")).to_be_visible()
        frozen = RunStore(configured_project.root).read("bridge-run")
        instances = frozen.config["instances"]
        assert deck.locator("[data-trassa-instance]").count() == len(instances)
        before = [row for row in window.rows if row[0] == "POST"]
        selected = instances[-1]["id"]
        deck.locator(f'[data-trassa-instance="{selected}"]').click()
        expect(deck).to_have_attribute("data-selected-instance", selected)
        deck.locator('[data-run-lens="orbit"]').click()
        expect(deck.locator(f'[data-instance="{selected}"]')).to_have_attribute("aria-pressed", "true")
        expect(deck.locator(".studio-deck__inspector h4")).to_have_text(selected)
        deck.locator('[data-run-lens="trassa"]').click()
        expect(deck.locator(f'[data-trassa-instance="{selected}"]')).to_have_attribute("aria-pressed", "true")
        for width, height in [(1280, 800), (1440, 900), (900, 700)]:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.set_viewport_size({"width": 1280, "height": 900})
        page.locator('[data-focus="preference-theme"]').select_option("dark")
        page.screenshot(path=str(tmp_path / "studio-bridge-dark-1280.png"))
        page.locator('[data-focus="preference-theme"]').select_option("light")
        page.screenshot(path=str(tmp_path / "studio-bridge-light-1280.png"))
        assert [row for row in window.rows if row[0] == "POST"] == before
        assert window.page_errors == []
    finally:
        page.context.close()


def test_task_rail_opens_the_newest_real_run_and_reload_keeps_its_binding(
        chromium: Browser, configured_project: _Project):
    page, window = _open(chromium, configured_project, double=True)
    try:
        _model_form(page, "bridge-latest")
        _open_run(page, "bridge-first")
        _open_run(page, "bridge-second")
        task_id = RunStore(configured_project.root).read("bridge-second").config["task"]["id"]
        page.locator("#navRuns").click()
        page.locator('[data-task-id=""]').click()
        page.locator(f'[data-task-id="{task_id}"]').click()
        expect(page.locator('[data-deck-run="bridge-second"]')).to_be_visible()
        assert "run=bridge-second" in page.url and f"task={task_id}" in page.url
        page.reload(wait_until="load")
        _settle(page)
        expect(page.locator(f'[data-task-id="{task_id}"]')).to_have_attribute("aria-pressed", "true")
        expect(page.locator('[data-deck-run="bridge-second"]')).to_be_visible()
        assert window.page_errors == []
    finally:
        page.context.close()
