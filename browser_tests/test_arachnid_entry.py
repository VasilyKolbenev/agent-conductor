"""Use the package's real root and project API for the operator's first visit."""
from contextlib import contextmanager
from threading import Thread

from playwright.sync_api import expect

from conductor import demo, ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.project_claim import Launch


@contextmanager
def project(folder, *, populated=False, active=False):
    root = demo.materialize(folder)
    if populated:
        demo.populate(root)
    if active:
        ownership_transition.activate(root, legacy_writers_stopped=True)
    mode = "active" if active else "view"
    with server.build(root, 0, registry=AdapterRegistry([]), launch=Launch(mode=mode)) as http:
        thread = Thread(target=http.serve_forever)
        thread.start()
        try:
            yield f"http://127.0.0.1:{http.server_port}"
        finally:
            http.shutdown()
            thread.join(5)


def test_bare_root_uses_saved_runs_and_keeps_hash_navigation_in_the_workspace(chromium, tmp_path):
    with project(tmp_path / "project", populated=True) as url:
        page = chromium.new_page(locale="en-US")
        writes = []
        page.on("request", lambda req: writes.append(req.url) if req.method == "POST" else None)
        try:
            page.goto(url)
            expect(page.locator("#workspace")).to_be_visible()
            sessions = page.locator("#sessions [data-session]")
            expect(sessions.first).to_be_visible()
            name = sessions.first.get_attribute("data-session")
            expect(page.locator("#title")).not_to_be_empty()
            expect(page.locator("#command")).to_be_visible()
            expect(page.locator("#messages")).to_have_attribute(
                "aria-label", "Conversation with Kolos")
            expect(page.locator("#command")).to_have_attribute("placeholder", "Ask Kolos…")
            page.locator("#command").fill("A question for this run")
            page.locator("#new").click()
            expect(page.locator("#command")).to_have_value("")
            expect(page.locator("#orbitHere [data-step]")).to_have_count(0)
            page.go_back()
            expect(page.locator("#sessions [aria-current=true]")).to_have_attribute(
                "data-session", name)
            expect(page.locator("#command")).to_have_value("A question for this run")
            page.locator("#limits").click()
            expect(page.locator("#inspection [data-focus-key=quota-read]")).to_be_visible()
            expect(page.locator("#inspection")).to_contain_text("no providers", ignore_case=True)
            page.locator("#close").click()
            expect(page.locator("#detail")).to_be_hidden()
            page.goto(url + "/#session=absent&lang=en")
            expect(page.locator("#notice")).to_contain_text("not found", ignore_case=True)
            expect(page.locator("#orbitHere [data-step]")).to_have_count(0)
            assert not writes
        finally:
            page.close()


def test_wrong_project_never_displays_another_projects_sessions(chromium, tmp_path):
    with project(tmp_path / "project", populated=True) as url:
        page = chromium.new_page(locale="en-US")
        reads = []
        page.on("request", lambda req: reads.append(req.url))
        try:
            page.goto(url + "/#project=" + "a" * 32)
            expect(page.locator("#notice")).to_contain_text("another project")
            expect(page.locator("#sessions [data-session]")).to_have_count(0)
            assert not any("/command/runs" in req for req in reads)
            page.goto(url + "/#lang=en")
            expect(page.locator("#sessions [data-session]").first).to_be_visible()
        finally:
            page.close()


def test_empty_root_offers_a_conversation_without_inventing_sessions(chromium, tmp_path):
    with project(tmp_path / "empty") as url:
        page = chromium.new_page(locale="ru-RU", viewport={"width": 390, "height": 844})
        try:
            page.goto(url)
            expect(page.locator("#command")).to_be_visible()
            expect(page.locator("#title")).to_have_text("Новая сессия")
            expect(page.locator(".speaker")).to_contain_text("Колос")
            expect(page.locator(".speaker")).to_contain_text("Титан ИИ")
            expect(page.locator("#command")).to_have_attribute("aria-label", "Написать Колосу…")
            expect(page.locator("#sessions [data-session]")).to_have_count(0)
            page.locator("#menu").click()
            page.locator("#attach").click()
            dialog = page.get_by_role("dialog")
            expect(dialog).to_be_visible()
            expect(dialog).to_contain_text("Kimi Code")
            expect(page.locator("#prepareTask")).to_be_hidden()
            assert page.evaluate("document.documentElement.scrollWidth === window.innerWidth")
        finally:
            page.close()


def test_two_local_sessions_keep_separate_drafts_and_history(chromium, tmp_path):
    with project(tmp_path / "project", populated=True) as url:
        page = chromium.new_page(locale="en-US")
        try:
            page.goto(url)
            page.locator("#new").click()
            first = page.url
            page.locator("#command").fill("Check the first counter")
            page.locator("#command").press("Enter")
            expect(page.locator("#title")).to_have_text("Check the first counter")
            page.locator("#command").fill("Keep this draft")
            page.locator("#new").click()
            assert page.url != first
            expect(page.locator("#messages")).to_be_empty()
            expect(page.locator("#command")).to_have_value("")
            page.go_back()
            expect(page.locator("#messages")).to_contain_text("Check the first counter")
            expect(page.locator("#command")).to_have_value("Keep this draft")
            page.locator("#memory").click()
            expect(page.locator("#inspection")).to_contain_text("Check the first counter")
            expect(page.locator("#inspection")).not_to_contain_text("Keep this draft")
        finally:
            page.close()


def test_root_exposes_a_connected_utility_after_an_explicit_registration(chromium, tmp_path):
    with project(tmp_path / "active", active=True) as url:
        page = chromium.new_page(locale="en-US")
        try:
            page.goto(url)
            page.locator("#attach").click()
            dialog = page.get_by_role("dialog")
            dialog.get_by_role("button", name="Custom utility").click()
            inputs = dialog.locator("form input")
            inputs.nth(0).fill("Counter helper")
            inputs.nth(1).fill("counter-helper")
            dialog.locator("form button[type=submit]").click()
            expect(dialog.get_by_role("heading", name="Counter helper")).to_be_visible()
            dialog.get_by_role("button", name="Close", exact=True).click()
            util = page.locator("#externalHarnesses [data-utility=counter-helper]")
            expect(util).to_be_visible()
            util.click()
            expect(dialog.get_by_label("Task text")).to_be_visible()
        finally:
            page.close()


def test_explicit_legacy_screen_preserves_fragment_and_back_navigation(chromium, tmp_path):
    with project(tmp_path / "project") as url:
        page = chromium.new_page(locale="en-US")
        try:
            page.goto(url)
            expect(page.locator("#workspace")).to_be_visible()
            fragment = "#screen=agents&lang=ru&theme=dark"
            page.goto(url + "/?from=link" + fragment)
            expect(page.locator("#screenAgents")).to_be_visible()
            assert page.url == url + "/panel/studio.html" + fragment
            page.go_back()
            expect(page.locator("#workspace")).to_be_visible()
        finally:
            page.close()
