"""Real shell preferences preserve drafts and accepted writes in flight."""
from browser_tests.task_picker import selected_task, expect_selected_task

from playwright.sync_api import Browser, expect

from browser_tests.test_studio_layout import (  # noqa: F401
    _model_form, configured_project, project,
)
from browser_tests.test_studio_lifecycle import _Project, _open, _settle
from browser_tests.test_studio_tasks import _open_run
from browser_tests.test_studio_task_races import _task_title
from conductor.command.task_store import TaskStore
from tests.studio_source_messages import message_english, message_russian


def _switch(page, language="ru", theme="dark"):
    page.locator('[data-focus="preference-language"]').select_option(language)
    page.locator('[data-focus="preference-theme"]').select_option(theme)
    expect(page.locator("html")).to_have_attribute("lang", language)
    expect(page.locator("html")).to_have_attribute("data-theme", theme)


def test_five_screen_shell_preferences_preserve_selection_drafts_and_reload(
        chromium: Browser, configured_project: _Project, tmp_path):
    page, window = _open(chromium, configured_project, double=True)
    try:
        _model_form(page, "preference-flow")
        _open_run(page, "preference-run")
        page.locator("#navRuns").click()
        task_id = selected_task(page)
        title = _task_title(page)
        title.fill("Overview <b>Личный черновик</b>")
        before = [row for row in window.rows if row[0] == "POST"]
        _switch(page)
        expect(title).to_have_value("Overview <b>Личный черновик</b>")
        assert selected_task(page) == task_id
        assert "run=preference-run" in page.url and "workflow=preference-flow" in page.url
        for suffix, label in [("Overview", "Обзор"), ("Workflow", "Процесс"),
                              ("Runs", "Запуски"), ("Decisions", "Решения"), ("Agents", "Участники")]:
            tab = page.locator("#nav" + suffix)
            expect(tab).to_have_text(label)
            tab.click()
            expect(page.locator("#screen" + suffix)).to_be_visible()
        assert [row for row in window.rows if row[0] == "POST"] == before
        page.locator("#navRuns").click()
        page.set_viewport_size({"width": 1280, "height": 900})
        page.emulate_media(color_scheme="light")
        assert page.locator("body").evaluate("n=>getComputedStyle(n).backgroundColor") == "rgb(12, 16, 15)"
        assert page.evaluate("document.documentElement.scrollWidth <= 1280")
        page.screenshot(path=str(tmp_path / "studio-shell-ru-dark-1280.png"))
        page.reload(wait_until="load")
        _settle(page)
        expect(page.locator("html")).to_have_attribute("lang", "ru")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        expect_selected_task(page, task_id)
        assert "run=preference-run" in page.url
        _switch(page, "en", "light")
        expect(page.locator("#navRuns")).to_have_text("Runs")
        assert page.locator("body").evaluate("n=>getComputedStyle(n).backgroundColor") == "rgb(238, 241, 237)"
        page.screenshot(path=str(tmp_path / "studio-shell-en-light-1280.png"))
        assert window.page_errors == [] and window.storage() == [0, 0]
    finally:
        page.context.close()


def test_switching_preferences_keeps_an_accepted_pending_task_and_the_next_draft(
        chromium: Browser, project: _Project):
    page, window = _open(chromium, project, double=True)
    held = []
    url = project.url + "command/tasks"

    def hold(route):
        if route.request.method != "POST":
            route.continue_()
            return
        response = route.fetch()
        held.append((route, response))
        page.evaluate("() => { window.__preferenceTaskAccepted = true; }")

    try:
        page.route(url, hold)
        title = _task_title(page)
        title.fill("Accepted task")
        page.locator('[data-focus="task-create"]').click()
        page.wait_for_function("() => window.__preferenceTaskAccepted === true")
        assert held[0][1].status == 201, held[0][1].json()
        title.fill("Следующий черновик")
        # The notice already on screen is the one said again, in the language switched to.
        assert page.locator("#studioStatus").inner_text() == message_english("notice.writing")
        _switch(page)
        expect(page.locator('[data-focus="task-create"]')).to_be_disabled()
        expect(title).to_have_value("Следующий черновик")
        expect(page.locator("#studioStatus")).to_have_text(message_russian("notice.writing"))
        assert window.writes("/command/tasks") == 1
        route, response = held.pop()
        task_id = response.json()["task"]["task_id"]
        route.fulfill(response=response)
        expect(page.locator('[data-focus="task-create"]')).to_be_enabled()
        expect(page.locator("#studioStatus")).to_have_text(
            message_russian("notice.task_created").replace("{title}", "Accepted task"))
        expect(title).to_have_value("Следующий черновик")
        assert TaskStore(project.root).read(task_id).title == "Accepted task"
        assert window.writes("/command/tasks") == 1 and window.page_errors == []
    finally:
        page.unroute_all(behavior="ignoreErrors")
        page.context.close()


def test_russian_browser_defaults_to_russian_without_rewriting_user_data(
        chromium: Browser, project: _Project):
    page, window = _open(chromium, project, double=True, locale="ru-RU")
    try:
        expect(page.locator("html")).to_have_attribute("lang", "ru")
        expect(page.locator("#navOverview")).to_have_text("Обзор")
        expect(page.locator('[data-focus="preference-language"]')).to_have_value("ru")
        assert window.writes("/command/") == 0 and window.page_errors == []
    finally:
        page.context.close()
