"""A colleague uses prior verification evidence in a new chat, without a provider."""
from pathlib import Path
from runpy import run_path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_studio_atlas import atlas_url, evidence  # noqa: F401
from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.project_claim import Launch
from tests.test_arachnid_review_source import source_rows


def ask(page, message):
    field = page.locator("#command")
    field.fill(message)
    field.press("Enter")


def test_unaccepted_history_cannot_seed_a_review(chromium, atlas_url):
    context = chromium.new_context()
    try:
        page = context.new_page()
        writes = []
        page.on("request", lambda req: writes.append(req.method) if req.method != "GET" else None)
        def saved_task(route):
            data = route.fetch().json()
            previous = next(t for t in data["tasks"] if t["task_id"] == "one")
            data["tasks"].append({**previous, "task_id": "next", "work_scope": "next",
                                  "title": "Сверить итоговый отчёт"})
            route.fulfill(json=data)

        page.route("**/command/tasks", saved_task)
        page.goto(atlas_url + "/#task=next&lang=ru")
        expect(page.locator("#title")).to_have_text("Сверить итоговый отчёт")
        page.get_by_role("button", name="Найди порядок проверки из прошлой задачи").click(
            timeout=5000)
        expect(page.locator("#messages .atlas").last).to_contain_text("Нет принятой попытки")
        expect(page.locator(".review-proposal")).to_have_count(0)
        assert not writes
    finally:
        close_context(context)


def test_chat_edits_a_new_plan_but_keeps_the_cited_attempt(chromium, atlas_url):
    context = chromium.new_context()
    try:
        page = context.new_page()
        writes, errors = [], []
        page.on("request", lambda req: writes.append(req.method) if req.method != "GET" else None)
        page.on("pageerror", lambda err: errors.append(str(err)))
        data = source_rows()
        page.route("**/command/runs/first", lambda route: route.fulfill(json=data["run"]))
        page.route("**/actions/action-first-2", lambda route: route.fulfill(json=data["attempt"]))
        page.goto(atlas_url + "/#new=1&lang=ru")
        page.get_by_role("button", name="Найди порядок проверки из прошлой задачи").click()
        first = page.locator('.review-proposal[data-revision="1"]')
        expect(first.locator(".review-steps li")).to_have_count(4)
        expect(first).to_contain_text("codex · checker")
        ask(page, "Добавь перед тестами проверку пустого списка")
        second = page.locator('.review-proposal[data-revision="2"]')
        expect(second.locator("li").nth(1)).to_have_text("проверку пустого списка")
        ask(page, "Измени шаг 2: проверить пустой список и один успех")
        third = page.locator('.review-proposal[data-revision="3"]')
        expect(third.locator("li").nth(1)).to_have_text("проверить пустой список и один успех")
        same_source = first.locator("a").last.get_attribute("href")
        assert third.locator("a").last.get_attribute("href") == same_source
        expect(first.locator("li")).to_have_count(4)
        ask(page, "Что-нибудь другое")
        expect(page.locator("#messages .atlas").last).to_contain_text("Например")
        expect(page.locator(".review-proposal")).to_have_count(3)
        ask(page, "Проверяющий: Grok")
        fourth = page.locator('.review-proposal[data-revision="4"]')
        expect(fourth).to_contain_text("Предлагаю независимого проверяющего: Grok")
        expect(fourth).to_contain_text("В прошлом запуске проверял codex · checker")
        page.locator("#command").fill("Исправить соседний счётчик.")
        fourth.get_by_role("button", name="Перенести в текст задачи").click()
        assert page.locator("#command").input_value().startswith("Исправить соседний счётчик.")
        assert "проверить пустой список и один успех" in page.locator("#command").input_value()
        assert "attempt-action-first-2" in page.locator("#command").input_value()
        page.locator("#new").click()
        expect(page.locator(".review-proposal")).to_have_count(0)
        assert not writes and not errors
    finally:
        close_context(context)


def test_citation_opens_protocol_of_the_named_attempt_even_when_a_newer_one_exists(
        chromium, atlas_url):
    context = chromium.new_context()
    try:
        page = context.new_page()
        page.route("**/actions/action-first-1",
                   lambda route: route.fulfill(json=evidence("action-first-1")))
        page.goto(atlas_url + "/#session=first&proofNode=repair-counter&proofAction=action-first-1"
                  "&proofAttempt=attempt-action-first-1&lang=en")
        expect(page.locator("#inspection [data-atlas-attempt]")).to_have_value("action-first-1")
        expect(page.locator("#inspection")).to_contain_text("test_action_first_1")
    finally:
        close_context(context)


def test_saved_colleague_task_quotes_and_edits_the_first_tasks_actual_checks(chromium, tmp_path):
    setup = Path(__file__).resolve().parents[1] / "distribution/windows-two-task/first_task.py"
    root = tmp_path / "personal"
    first = "Сверить реестр архивов"
    second = "Сверить реестр вложений"
    steps = [("Сопоставить имена", "Имена трёх архивов совпали"),
             ("Прочитать метки", "Зафиксировано две метки")]
    run_id, task_id = run_path(str(setup))["create"](
        root, first, second, steps, "Ольга", accepted=True)
    http = server.build(root, 0, registry=AdapterRegistry([]), launch=Launch(mode="view"))
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    context = chromium.new_context()
    writes, errors = [], []
    context.on("request", lambda req: writes.append(req.method) if req.method != "GET" else None)
    try:
        base = f"http://127.0.0.1:{http.server_port}"
        page = context.new_page()
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(f"{base}/#task={task_id}&lang=ru")
        expect(page.locator("#title")).to_have_text(second)
        page.get_by_role("button", name="Найди порядок проверки из прошлой задачи").click()
        original = page.locator('.review-proposal[data-revision="1"]')
        expect(original.locator("li")).to_have_text([s[0] for s in steps])
        ask(page, "Измени шаг 2: сверить вложенные теги")
        edited = page.locator('.review-proposal[data-revision="2"]')
        expect(edited.locator("li")).to_have_text([steps[0][0], "сверить вложенные теги"])
        proof = edited.locator('a[href*="reviewEvidence"]')
        href = proof.get_attribute("href")
        q = parse_qs(urlsplit(href).fragment)
        assert q["session"] == [run_id] and len(q["reviewEvidence"]) == 1
        assert original.locator('a[href*="reviewEvidence"]').get_attribute("href") == href
        with context.expect_page() as popup:
            proof.click()
        source = popup.value
        source.on("pageerror", lambda err: errors.append(str(err)))
        panel = source.locator("#inspection")
        expect(panel).to_contain_text(first)
        expect(panel).to_contain_text("Ольга")
        expect(panel.locator("li strong")).to_have_text([s[0] for s in steps])
        expect(panel.locator("li p")).to_have_text([s[1] for s in steps])
        expect(panel).not_to_contain_text("сверить вложенные теги")
        source.goto(base + href.replace(q["reviewEvidence"][0], "unknown-proof"))
        expect(panel).to_contain_text("Указанная запись проверки не найдена")
        expect(panel.locator("li")).to_have_count(0)
        edited.get_by_role("button", name="Перенести в текст задачи").click()
        draft = page.locator("#command").input_value()
        assert draft.startswith(second) and "сверить вложенные теги" in draft
        assert urlsplit(page.url).fragment.startswith(f"task={task_id}&")
        assert not writes and not errors
    finally:
        close_context(context)
        http.shutdown()
        thread.join(5)
        http.server_close()
