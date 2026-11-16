"""Connect to two real project utilities and reopen the saved exchange in view mode."""
import json
import os
import re
import subprocess
from contextlib import contextmanager
from threading import Thread

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_studio_rendered import studio_url
from conductor import demo, ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.project_claim import Launch
from conductor.utility_bridge import LocalStudio, exchange
from tests._ps1 import child_text, write_ps1

GUIDE = ("https://github.com/VasilyKolbenev/agent-conductor/blob/"
         "8ab4f0f980db1b0626c56ffc5e2995516d7d35ec/docs/")


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
            expect(panel).to_contain_text("Local adapter tests only")
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
            panel.get_by_role("button", name="Codex", exact=True).click()
            expect(panel).to_contain_text("откройте свой проект в активном режиме")
            expect(panel.locator("code")).to_have_count(0)
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


def check_card_command(panel, kind, tmp_path):
    snippet = panel.locator("code")
    expected = "& $conduct providers --dir $project --subscription " + kind
    expect(snippet).to_have_text(expected)
    if os.name != "nt":
        return
    # Use the exact text from the card, after checking it against the closed command above.
    command = snippet.inner_text()
    assert command == expected
    stub = write_ps1(tmp_path / "учебный conduct.ps1", """
[IO.File]::WriteAllText($env:CARD_ARGS, (ConvertTo-Json -InputObject $args -Compress))
""")
    project = tmp_path / "проект с пробелом"
    project.mkdir(exist_ok=True)
    captured = tmp_path / (kind + ".json")
    wrapper = write_ps1(tmp_path / "card.ps1", """
$ErrorActionPreference = 'Stop'
$conduct = $env:CARD_CLI
$project = $env:CARD_PROJECT
""" + command)
    env = dict(os.environ, CARD_CLI=str(stub), CARD_PROJECT=str(project), CARD_ARGS=str(captured))
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "RemoteSigned",
         "-File", str(wrapper)], cwd=tmp_path, env=env,
        capture_output=True, timeout=15)
    assert result.returncode == 0, child_text(result.stderr)
    assert json.loads(captured.read_text(encoding="utf-8-sig")) == [
        "providers", "--dir", str(project), "--subscription", kind]


@pytest.mark.parametrize(("language", "target"), [
    ("en", "first-run-v1.en.md#where-to-get-the-pinned-builds"),
    ("ru", "first-run-v1.md#где-взять-закреплённые-сборки"),
])
def test_subscription_cards_link_to_the_reviewed_guide(chromium, tmp_path, language, target):
    root = demo.materialize(tmp_path / "project")
    ownership_transition.activate(root, legacy_writers_stopped=True)
    with studio(root, "active") as (url, _):
        context = chromium.new_context()
        try:
            page = context.new_page()
            page.goto(url + "/#lang=" + language)
            page.locator("#attach").click()
            panel = page.get_by_role("dialog")
            for tool, version in (("Codex", "0.164.0"), ("Grok Build", "1.0.13")):
                panel.get_by_role("button", name=tool, exact=True).click()
                label = (f"Install {tool} {version} for Windows" if language == "en"
                         else f"Установить {tool} {version} для Windows")
                expect(panel.get_by_role("link", name=label, exact=True)).to_have_attribute(
                    "href", GUIDE + target)
        finally:
            close_context(context)


def test_subscription_cards_separate_install_login_quota_and_role(chromium, tmp_path):
    root = demo.materialize(tmp_path / "project")
    ownership_transition.activate(root, legacy_writers_stopped=True)
    with studio(root, "active") as (url, _):
        context = chromium.new_context()
        page = context.new_page()
        posted = []
        try:
            page.goto(url + "/#lang=en")
            providers = [
                dict(provider_id="codex", display_name="Codex", availability="executable_absent",
                     implementation="real_experimental", auth="subscription", task_road="refused",
                     controls=[], vendor_sandbox=None),
                dict(provider_id="grok-build", display_name="Grok", availability="available",
                     implementation="real_experimental", auth="subscription",
                     task_road="review_only", controls=["review"], vendor_sandbox=None),
            ]
            at = "2026-11-16T11:00:00Z"
            base = dict(account=None, account_status="unknown", deferred_at=None)
            rows = [
                dict(base, binding_ids=["codex"], source=dict(kind="codex-cli", version="0.164"),
                     state="unavailable", reason="not_authenticated", observed_at=at,
                     freshness="current", windows=[]),
                dict(base, binding_ids=["grok-build"], source=dict(kind="grok-cli", version="1.0"),
                     state="observed", reason=None, observed_at=at, freshness="current",
                     windows=[dict(limit_id="subscription", window_id="weekly", used_percent=17,
                                   remaining_percent=83, resets_at=None, starts_at=None,
                                   duration_minutes=10080, freshness="current")]),
            ]
            page.route("**/command/workflows",
                       lambda route: route.fulfill(json={"providers": providers}))
            cache_providers = [dict(row, task_road="refused") for row in providers]
            page.route("**/command/quotas", lambda route: route.fulfill(json=dict(
                as_of=at, max_age_seconds=300, providers=cache_providers, snapshots=rows)))
            page.on("request", lambda req: posted.append(req.url) if req.method == "POST" else None)
            page.locator("#attach").click()
            panel = page.get_by_role("dialog")
            panel.get_by_role("button", name="Codex", exact=True).click()
            check_card_command(panel, "codex", tmp_path)
            guide = panel.get_by_role("link", name="Install Codex 0.164.0 for Windows")
            expect(guide).to_have_attribute(
                "href", GUIDE + "first-run-v1.en.md#where-to-get-the-pinned-builds")
            expect(panel.get_by_text("Configured CLI file missing", exact=True)).to_be_visible()
            login = panel.get_by_text("Last quota check requires sign-in", exact=True)
            expect(login).to_be_visible()
            expect(panel.get_by_text("No quota reading", exact=True)).to_be_visible()
            expect(panel.get_by_text("No task role available", exact=True)).to_be_visible()
            panel.get_by_role("button", name="Grok Build", exact=True).click()
            expect(panel.get_by_text("Read-only review", exact=True)).to_be_visible()
            expect(panel.get_by_text("Subscription selected", exact=True)).to_be_visible()
            details = panel.locator("details").filter(has_text="Quota details")
            details.locator("summary").click()
            expect(details).to_contain_text("83%")
            expect(details).to_contain_text("grok-cli")
            check_card_command(panel, "grok-build", tmp_path)
            # A cached reading for a different auth mode is not a subscription allowance.
            cache_providers[1]["auth"] = "api_key"
            panel.get_by_role("button", name="Refresh status").click()
            expect(panel.get_by_text("No quota reading", exact=True)).to_be_visible()
            expect(panel.get_by_text("Read-only review", exact=True)).to_be_visible()
            expect(panel.get_by_text("Quota details and source", exact=True)).to_have_count(0)
            panel.get_by_role("button", name="Kimi Code", exact=True).click()
            expect(panel).to_contain_text("Local adapter tests only")
            panel.get_by_role("button", name="Claude Code", exact=True).click()
            expect(panel).to_contain_text("Public subscription setup is on hold")
            expect(panel.locator("code")).to_have_count(0)
            assert not posted
        finally:
            close_context(context)


@pytest.mark.parametrize(("entry", "opener"), [("/#lang=ru", "#attach"),
                          ("/#screen=agents&lang=ru", "#utilityAgents")])
def test_unavailable_provider_read_preserves_manual_setup(chromium, tmp_path, entry, opener):
    root = demo.materialize(tmp_path / "project")
    ownership_transition.activate(root, legacy_writers_stopped=True)
    with studio(root, "active") as (url, _):
        context = chromium.new_context()
        page = context.new_page()
        try:
            page.goto(url + entry)
            page.locator(opener).click()
            page.route("**/command/workflows", lambda route: route.fulfill(status=503))
            page.route("**/command/quotas", lambda route: route.fulfill(status=503))
            panel = page.get_by_role("dialog")
            panel.get_by_role("button", name="Codex", exact=True).click()
            expect(panel).to_contain_text("Нет данных о состоянии харнесса")
            expect(panel).to_contain_text("Кеш квот недоступен")
            expect(panel).not_to_contain_text("Файл CLI найден")
            expect(panel.get_by_role("button", name="Обновить состояние")).to_be_visible()
            panel.get_by_role("button", name="Своя утилита", exact=True).click()
            expect(panel.get_by_role("button", name="Подключить утилиту")).to_be_enabled()
        finally:
            close_context(context)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_custom_connection_invalid_field_is_visible_and_fixable_on_mobile(chromium, tmp_path, lang):
    root = demo.materialize(tmp_path / "project")
    ownership_transition.activate(root, legacy_writers_stopped=True)
    with studio(root, "active") as (url, _):
        context = chromium.new_context(viewport={"width": 375, "height": 740}, locale=lang)
        page = context.new_page()
        sent = []
        def record(req):
            if req.method == "POST":
                sent.append((req.url.removeprefix(url), req.post_data_json["op"]))
        page.on("request", record)
        ru = lang == "ru"
        try:
            page.goto(url + "/#lang=" + lang)
            page.locator("#menu").click()
            page.locator("#attach").click()
            panel = page.get_by_role("dialog")
            panel.get_by_role("button", name="Своя утилита" if ru else "Custom utility").click()
            name = panel.get_by_label("Название" if ru else "Name", exact=True)
            identifier = panel.get_by_label("Идентификатор" if ru else "Identifier", exact=True)
            action = "Подключить утилиту" if ru else "Connect utility"
            add = panel.get_by_role("button", name=action)
            identifier.fill("!?")
            checks = [(name, "Введите название утилиты." if ru else "Enter a utility name."),
                      (identifier, "Начните с" if ru else "Start with"),
                      (identifier, "зарезервирован" if ru else "reserved")]
            for field, expected in checks:
                add.click()
                expect(field).to_be_focused()
                expect(field).to_have_attribute("aria-invalid", "true")
                expect(field).to_have_accessible_description(re.compile(expected))
                note = panel.locator("#" + field.get_attribute("aria-describedby"))
                expect(note).to_be_in_viewport(ratio=1)
                assert note.evaluate("""n => {
                  const r = n.getBoundingClientRect();
                  const d = n.closest('dialog').getBoundingClientRect();
                  return r.top >= d.top && r.bottom <= d.bottom;
                }""")
                assert not sent
                if field is name:
                    name.fill("Чтение кода")
                else:
                    identifier.fill("con" if identifier.input_value() == "!?" else "review-cli")
            expect(name).not_to_have_attribute("aria-invalid", "true")
            expect(identifier).not_to_have_attribute("aria-invalid", "true")
            expect(identifier).to_have_accessible_description("")
            add.dblclick()
            expect(panel.get_by_role("heading", name="Чтение кода", exact=True)).to_be_visible()
            assert sent == [("/command/project/utilities", "attach")]
        finally:
            close_context(context)


def test_catalog_keyboard_focus_survives_selection_and_pending_reads(chromium, tmp_path):
    root = demo.materialize(tmp_path / "project")
    ownership_transition.activate(root, legacy_writers_stopped=True)
    with studio(root, "active") as (url, _):
        context = chromium.new_context(viewport={"width": 375, "height": 740})
        page = context.new_page()
        try:
            page.goto(url + "/#lang=en")
            page.locator("#menu").click()
            page.locator("#attach").click()
            panel = page.get_by_role("dialog")
            custom = panel.get_by_role("button", name="Custom utility", exact=True)
            custom.click()
            expect(panel.get_by_role("button", name="Connect utility")).to_be_enabled()
            reads = []
            page.route("**/command/quotas", lambda route: reads.append(route))
            codex = panel.get_by_role("button", name="Codex", exact=True)
            codex.focus()
            with page.expect_request("**/command/quotas"):
                codex.press("Enter")
            expect(codex).to_be_focused()
            page.wait_for_function("() => !!document.querySelector('#studioUtilities code')")
            assert len(reads) == 1
            reads.pop().fulfill(status=503)
            expect(panel).to_contain_text("Quota cache unavailable")
            expect(codex).to_be_focused()
            with page.expect_request("**/command/quotas"):
                panel.get_by_role("button", name="Refresh status").click()
            custom.click()
            field = panel.get_by_label("Name", exact=True)
            field.fill("Unfinished name")
            with page.expect_response("**/command/quotas"):
                reads.pop().fulfill(status=503)
            expect(field).to_be_focused()
            expect(field).to_have_value("Unfinished name")
        finally:
            close_context(context)
