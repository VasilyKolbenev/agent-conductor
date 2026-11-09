"""A colleague can take a real task from Studio to the Desk wizard without creating work."""
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from conductor import demo, server
from conductor.command.project_claim import Launch


@pytest.mark.parametrize("practice,lang,width", [
    (False, "ru", 375), (False, "en", 1280), (True, "ru", 375), (True, "en", 1280),
])
def test_a_first_visit_offers_the_own_task_wizard(chromium, tmp_path, practice, lang, width):
    root = demo.materialize(tmp_path)
    if practice:
        demo.populate(root)
    http = server.build(root, 0, launch=Launch(demo=practice))
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    context = chromium.new_context(viewport={"width": width, "height": 820})
    try:
        page = context.new_page()
        writes = []
        page.on("request", lambda req: writes.append(req.url) if req.method == "POST" else None)
        page.goto(f"http://127.0.0.1:{http.server_port}/panel/studio.html#lang={lang}")
        expect(page.locator("#screenOverview")).to_have_attribute("data-state", "ready")
        own = page.get_by_role("link", name="Поставить свою задачу" if lang == "ru" else "Start your own task")
        expect(own).to_have_count(1)
        expect(own).to_be_in_viewport()
        if practice:
            expect(page.get_by_role("button", name="Начать упражнение" if lang == "ru"
                                    else "Start the exercise")).to_be_in_viewport()
        else:
            expect(page.locator("#bodyOverview .studio-entry").get_by_role("link")).to_have_count(1)
            expect(page.locator("#studioTasks [data-focus='task-picker']")).to_have_count(0)
            manual = page.locator("#studioTasks details[data-task-create]")
            expect(manual.locator("summary")).to_have_text(
                "Создать запись без запуска" if lang == "ru" else "Create a task record only")
            manual.locator("summary").click()
            expect(manual.locator('input[name="task-title"]')).to_be_visible()
            manual.locator("summary").click()
            expect(page.locator("#bodyOverview")).to_contain_text(
                "Какой результат вам нужен?" if lang == "ru" else "What would you like to get done?")
            expect(page.locator(".studio-overview__blocked")).to_have_count(0)
            assert page.locator(".studio-entry").bounding_box()["y"] < page.locator("#studioTasks").bounding_box()["y"]
        own.focus()
        page.keyboard.press("Enter")
        page.wait_for_url("**/panel/desk.html#*")
        assert urlsplit(page.url).path == "/panel/desk.html"
        assert parse_qs(urlsplit(page.url).fragment)["lang"] == [lang]
        field = page.locator('#deskWizard [data-focus="wizard:brief"]')
        expect(field).to_be_visible()
        field.fill("My counter fix")
        assert writes == []
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        close_context(context)
        http.shutdown()
        thread.join(5)
        http.server_close()


def test_an_unread_task_list_is_not_presented_as_a_first_project(chromium, tmp_path):
    root = demo.materialize(tmp_path)
    http = server.build(root, 0)
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    context = chromium.new_context(viewport={"width": 375, "height": 820})
    try:
        page = context.new_page()
        page.route("**/command/tasks", lambda route: route.fulfill(status=503, json={"error": "offline"}))
        page.goto(f"http://127.0.0.1:{http.server_port}/panel/studio.html#lang=ru")
        expect(page.locator("[data-task-notice]")).to_be_visible()
        expect(page.locator(".studio-entry")).to_have_count(0)
        expect(page.get_by_role("link", name="Поставить свою задачу")).to_be_in_viewport()
    finally:
        close_context(context)
        http.shutdown()
        thread.join(5)
        http.server_close()
