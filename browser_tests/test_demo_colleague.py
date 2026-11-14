"""One new task reaches its own human receipt using only the installed demo's public doors."""
from __future__ import annotations

import threading
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from conductor import demo, server
from conductor.command.project_claim import Launch
from conductor.command.run_store import RunStore


@pytest.mark.parametrize("lang,width,title,begin,submit", [
    ("ru", 375, "Проверить счётчик 🚀", "Проверить учебный результат", "Записать решение"),
    ("en", 1280, "Check the counter's result", "Review sample result", "Record this decision"),
])
def test_fresh_task_to_its_own_receipt(chromium, tmp_path, lang, width, title, begin, submit):
    root = demo.materialize(tmp_path)
    demo.populate(root)
    httpd = server.build(root, 0, launch=Launch(demo=True))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    context = chromium.new_context(viewport={"width": width, "height": 840})
    try:
        page = context.new_page()
        writes = []
        page.on("request", lambda req: writes.append(urlsplit(req.url).path)
                if req.method == "POST" else None)
        page.goto(f"http://127.0.0.1:{httpd.server_port}/panel/studio.html#lang={lang}")
        expect(page.locator("#screenOverview")).to_have_attribute("data-state", "ready")
        expect(page.locator("[data-demo-intro]")).to_be_visible()
        page.get_by_role("button", name="Начать упражнение" if lang == "ru"
                         else "Start the exercise").click()
        expect(page.locator('[data-focus="task-title"]')).to_be_focused()
        page.locator('[data-focus="task-title"]').fill(title)
        page.locator('[data-focus="task-create"]').click()
        ready = page.get_by_role("button", name=begin, exact=True)
        expect(ready).to_be_enabled()
        expect(page.locator("details[data-task-create] input")).to_be_hidden()
        expect(page.locator("#bodyOverview")).to_contain_text(title)
        expect(page.locator("#bodyOverview")).not_to_contain_text("demo-run-001")
        task_id = parse_qs(urlsplit(page.url).fragment)["task"][0]
        if lang == "en":
            # Both clicks reach the same mounted control before the first reply.
            ready.evaluate("(node) => { node.click(); node.click(); }")
        else:
            ready.click()
        decision = page.locator("#screenDecisions")
        expect(decision).to_be_visible()
        expect(decision).to_contain_text("A ✓ · B ✗ · C ✓")
        expect(decision).to_contain_text("2 / 3")
        if width == 375:
            expect(decision.get_by_text("A ✓ · B ✗ · C ✓", exact=False).last).to_be_in_viewport()
        run_id = parse_qs(urlsplit(page.url).fragment)["run"][0]
        store = RunStore(root)
        before = store.read(run_id)
        assert before.config["task"]["id"] == task_id
        assert tuple(before.config["instances"]) == ()
        assert [r.kind for r in before.records] == ["graph_definition"]
        button = page.get_by_role("button", name=submit, exact=True)
        expect(button).to_be_disabled()
        name = page.locator('[data-focus-key="field:actor"]')
        hint = decision.get_by_text("colleague-demo", exact=False)
        expect(hint).to_be_visible()
        expect(hint).to_contain_text("A–Z")
        name.fill("коллега-демо")
        expect(button).to_be_disabled()
        expect(name).to_have_value("коллега-демо")
        expect(hint).to_be_visible()
        assert not any(path.endswith("/decisions") for path in writes)
        name.fill("colleague-demo")
        expect(button).to_be_enabled()
        with page.expect_response(lambda response: response.url.endswith("/decisions")) as sent:
            button.click()
        assert sent.value.status == 201
        expect(decision.get_by_text("colleague-demo", exact=True)).to_be_visible()
        page.reload()
        # The sole saved answer remains visible without selecting the gate a second time.
        expect(decision.get_by_text("colleague-demo", exact=True)).to_be_visible()
        after = store.read(run_id)
        receipts = [r.value for r in after.records if r.kind == "decision"]
        assert [(r.action, r.actor) for r in receipts] == [("approve", "colleague-demo")]
        assert not any(r.kind.startswith("action_") for r in after.records)
        assert writes.count("/command/tasks") == writes.count("/command/runs") == 1
        assert sum(path.endswith("/decisions") for path in writes) == 1
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        context.close()
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
