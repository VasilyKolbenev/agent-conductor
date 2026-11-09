"""Connect to two real project utilities and reopen the saved exchange in view mode."""
from contextlib import contextmanager
from threading import Thread

from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_studio_rendered import studio_url
from conductor import demo, ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.project_claim import Launch


@contextmanager
def studio(root, mode):
    http = server.build(root, 0, registry=AdapterRegistry([]), launch=Launch(mode=mode))
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}", http.project_identity.project_id
    finally:
        http.shutdown()
        thread.join(5)
        http.server_close()


def attach(panel, name, identifier, mode):
    panel.get_by_role("button", name="Custom utility", exact=True).click()
    panel.get_by_label("Name", exact=True).fill(name)
    panel.get_by_label("Identifier", exact=True).fill(identifier)
    panel.get_by_label("Connection", exact=True).select_option(mode)
    panel.get_by_role("button", name="Connect utility").click()
    expect(panel.get_by_label("Task text")).to_be_visible()
    expect(panel.get_by_role("heading", name=name, exact=True)).to_be_visible()


def test_saved_exchange_is_readable_when_the_same_project_reopens_read_only(chromium, tmp_path):
    root = demo.materialize(tmp_path / "project")
    ownership_transition.activate(root, legacy_writers_stopped=True)
    context = chromium.new_context(viewport={"width": 975, "height": 800})
    page = context.new_page()
    sent, errors = [], []
    page.on("pageerror", lambda err: errors.append(str(err)))

    def request(req):
        if req.url.endswith("/command/project/utilities") and req.method == "POST":
            sent.append((req.post_data_json["op"], req.headers))

    page.on("request", request)
    try:
        with studio(root, "active") as (url, project_id):
            page.goto(url + "/#screen=agents&lang=en")
            opener = page.locator("#utilityAgents")
            opener.click()
            panel = page.get_by_role("dialog")
            panel.get_by_role("button", name="Kimi Code", exact=True).click()
            expect(panel).to_contain_text("conduct providers")
            expect(panel).to_contain_text("Kimi Desktop")
            attach(panel, "My local CLI", "my-cli", "manual")
            panel.get_by_label("Task text").fill("Inspect the counter")
            assert [op for op, _ in sent] == ["attach"]
            panel.get_by_role("button", name="Send task").click()
            expect(panel).to_contain_text("Inspect the counter")
            panel.get_by_label("CLI reply").fill("Counter verified")
            panel.get_by_role("button", name="Save reply").click()
            expect(panel).to_contain_text("Counter verified")
            expect(panel.get_by_label("CLI reply")).to_have_count(0)
            attach(panel, "CLI B", "cli-b", "stdio-v1")
            expect(panel).to_contain_text(f"utility-bridge --server {url} --utility cli-b")
            panel.get_by_label("Task text").fill("Review one file")
            panel.get_by_role("button", name="Send task").click()
            expect(panel).to_contain_text("Awaiting handoff")
            expect(panel.get_by_label("CLI reply")).to_have_count(0)
            expect(panel).not_to_contain_text("Counter verified")
            panel.get_by_role("button", name="Close").click()
            expect(opener).to_be_focused()
            page.goto("about:blank")

        with studio(root, "view") as (url, reopened):
            assert reopened == project_id
            page.goto(url + "/#screen=runs&lang=ru")
            page.locator("#utilityRuns").click()
            panel = page.get_by_role("dialog")
            expect(panel).to_contain_text("только для просмотра")
            panel.get_by_role("button", name="My local CLI", exact=True).click()
            expect(panel).to_contain_text("Counter verified")
            expect(panel.get_by_role("button", name="Отправить задачу")).to_be_disabled()
            assert [op for op, _ in sent] == ["attach", "send", "manual_reply", "attach", "send"]
            assert all(headers.get("x-conduct-csrf") for _, headers in sent)
            assert all(headers.get("x-conduct-project") == project_id for _, headers in sent)
            assert not errors
            page.goto("about:blank")
    finally:
        close_context(context)


def test_unidentified_studio_reads_its_connections_and_never_offers_writes(chromium, studio_url):
    context = chromium.new_context()
    page = context.new_page()
    posted = []
    page.on("request", lambda req: posted.append(req.url) if req.method == "POST" else None)
    try:
        page.goto(studio_url + "#screen=agents&lang=en")
        page.locator("#utilityAgents").click()
        panel = page.get_by_role("dialog")
        expect(panel).to_contain_text("Open an activated project")
        for name in ("Claude Code", "Codex", "Grok Build", "Kimi Code"):
            expect(panel.get_by_role("button", name=name, exact=True)).to_be_visible()
        panel.get_by_role("button", name="Custom utility").click()
        expect(panel.get_by_role("button", name="Connect utility")).to_be_disabled()
        assert not posted
    finally:
        close_context(context)
