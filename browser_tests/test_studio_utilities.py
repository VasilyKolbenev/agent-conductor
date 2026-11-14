"""Connect to two real project utilities and reopen the saved exchange in view mode."""
import re
from contextlib import contextmanager
from threading import Thread

from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_studio_rendered import studio_url
from conductor import demo, ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.project_claim import Launch
from conductor.utility_bridge import LocalStudio, exchange


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
    hint = "Copy the task" if mode == "manual" else "arachnid.utility.v1"
    expect(panel.get_by_label("Connection", exact=True)).to_have_accessible_description(
        re.compile(hint))
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
            panel.get_by_role("button", name="Prepare handoff").click()
            expect(panel).to_contain_text("Inspect the counter")
            panel.get_by_label("Utility reply").fill("Counter verified")
            panel.get_by_role("button", name="Save reply").click()
            expect(panel).to_contain_text("Counter verified")
            manual_reply = panel.get_by_role("heading", name="Reply recorded by the operator")
            expect(manual_reply).to_be_visible()
            expect(panel.get_by_label("Utility reply")).to_have_count(0)
            attach(panel, "CLI B", "cli-b", "stdio-v1")
            expect(panel).to_contain_text(f"utility-bridge --server {url} --utility cli-b")
            panel.get_by_label("Task text").fill("Review one file")
            panel.get_by_role("button", name="Send task").click()
            expect(panel).to_contain_text("Awaiting handoff")
            expect(panel.get_by_label("Utility reply")).to_have_count(0)
            expect(panel).not_to_contain_text("Counter verified")
            bridge_reply = panel.get_by_role("heading", name="Reply received through the bridge")
            expect(bridge_reply).to_have_count(0)
            client = LocalStudio(url)
            held = client.get("/command/project/utilities")["exchanges"]
            entry, = [e for e in held if e["utility_id"] == "cli-b"]
            claim = dict(utility_id="cli-b", exchange_id=entry["exchange_id"], claim_token="a" * 64)
            assert client.post(op="claim", **claim)[0] == 201
            panel.get_by_role("button", name="Refresh exchanges").click()
            expect(panel.get_by_text("Claimed by bridge", exact=True)).to_be_visible()
            expect(bridge_reply).to_have_count(0)
            panel.get_by_role("button", name="Close with unknown outcome").click()
            expect(panel.get_by_text("Outcome unknown", exact=True)).to_be_visible()
            expect(bridge_reply).to_have_count(0)
            panel.get_by_label("Task text").fill("Read another file")
            panel.get_by_role("button", name="Send task").click()
            expect(panel.get_by_text("Awaiting handoff", exact=True)).to_be_visible()
            assert exchange(client, "cli-b", lambda req: "echo: " + req["text"])
            panel.get_by_role("button", name="Refresh exchanges").click()
            expect(bridge_reply).to_be_visible()
            expect(panel).to_contain_text("echo: Read another file")
            limits = "Workflow roles and quota readings require a provider adapter"
            expect(panel).to_contain_text(limits)
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
            expect(panel.get_by_role("heading", name="Ответ записал оператор")).to_be_visible()
            expect(panel.get_by_role("button", name="Подготовить передачу")).to_be_disabled()
            assert [op for op, _ in sent] == [
                "attach", "send", "manual_reply", "attach", "send", "mark_unknown", "send"]
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
        for name in ("Claude Code", "Codex", "Grok Build", "Kimi Code", "DeepSeek Harness"):
            expect(panel.get_by_role("button", name=name, exact=True)).to_be_visible()
        panel.get_by_role("button", name="DeepSeek Harness").click()
        expect(panel.get_by_role("button", name="Connect chat manually")).to_be_disabled()
        panel.get_by_role("button", name="Custom utility").click()
        expect(panel.get_by_role("button", name="Connect utility")).to_be_disabled()
        assert not posted
    finally:
        close_context(context)


def test_deepseek_chat_records_manual_handoff_and_keeps_api_setup_separate(chromium, tmp_path):
    root = demo.materialize(tmp_path / "project")
    ownership_transition.activate(root, legacy_writers_stopped=True)
    with studio(root, "active") as (url, _):
        context = chromium.new_context(locale="ru-RU", viewport={"width": 1360, "height": 880})
        page = context.new_page()
        posts, external = [], []

        def local_only(route):
            request = route.request
            if not request.url.startswith(url + "/"):
                external.append(request.url)
                route.abort()
            else:
                if request.method == "POST":
                    posts.append((request.url.removeprefix(url), request.post_data_json))
                route.continue_()

        context.route("**/*", local_only)
        try:
            page.goto(url + "/#lang=ru")
            page.locator("#attach").click()
            panel = page.get_by_role("dialog")
            panel.get_by_role("button", name="DeepSeek Harness", exact=True).click(timeout=3000)
            expect(panel).to_contain_text("DEEPSEEK_API_KEY")
            expect(panel).to_contain_text("баланс API")
            expect(panel).not_to_contain_text("вход по подписке")
            assert not posts
            panel.get_by_role("button", name="Подключить чат вручную").click()
            expect(panel.get_by_role("heading", name="DeepSeek Chat", exact=True)).to_be_visible()
            link = panel.get_by_role("link", name="Открыть DeepSeek Chat")
            expect(link).to_have_attribute("href", "https://chat.deepseek.com/")
            panel.get_by_label("Текст задачи").fill("Проверить порядок шагов")
            panel.get_by_role("button", name="Подготовить передачу").click()
            expect(panel).to_contain_text("Ожидает передачи")
            panel.get_by_label("Ответ утилиты").fill("Сначала тесты, затем проверка")
            panel.get_by_role("button", name="Записать ответ").click()
            expect(panel.get_by_role("heading", name="Ответ записал оператор")).to_be_visible()
            page.reload()
            page.locator("#attach").click()
            panel.get_by_role("button", name="DeepSeek Harness", exact=True).click()
            panel.get_by_role("button", name="К обменам DeepSeek Chat").click()
            expect(panel).to_contain_text("Сначала тесты, затем проверка")
            assert [cmd["op"] for _, cmd in posts] == ["attach", "send", "manual_reply"]
            assert all(path == "/command/project/utilities" for path, _ in posts)
            assert posts[0][1]["mode"] == "manual"
            assert not external
        finally:
            close_context(context)


def test_deepseek_chat_does_not_relabel_an_existing_bridge(chromium, tmp_path):
    root = demo.materialize(tmp_path / "project")
    ownership_transition.activate(root, legacy_writers_stopped=True)
    with studio(root, "active") as (url, _):
        client = LocalStudio(url)
        bridge = dict(utility_id="deepseek-chat", label="DeepSeek Chat", mode="stdio-v1")
        assert client.post(op="attach", **bridge)[0] == 201
        context = chromium.new_context()
        page = context.new_page()
        try:
            page.goto(url + "/#screen=agents&lang=en")
            page.locator("#utilityAgents").click()
            panel = page.get_by_role("dialog")
            panel.get_by_role("button", name="DeepSeek Harness", exact=True).click()
            expect(panel).to_contain_text("identifier deepseek-chat is in use")
            expect(panel.get_by_role("button", name="Connect chat manually")).to_have_count(0)
            panel.get_by_role("button", name="DeepSeek Chat", exact=True).click()
            expect(panel).to_contain_text("utility-bridge")
            expect(panel.get_by_role("link", name="Open DeepSeek Chat")).to_have_count(0)
            assert client.get("/command/project/utilities")["utilities"] == [bridge]
        finally:
            close_context(context)
