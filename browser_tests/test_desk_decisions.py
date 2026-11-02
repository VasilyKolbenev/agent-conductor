"""The Desk's always-visible gate card writes a task-bound decision on the real server."""
from __future__ import annotations

from playwright.sync_api import Browser, expect

from browser_tests.desk_identity import identified_server
from browser_tests.test_desk_rail_scene import NOW, _seed
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.run_store import RunStore, snapshot_digest
from tests.test_command_run_store import a_run
from tests.test_store import good_lane, write_project

PROJECT = "a" * 32


def _world(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    _seed(root)
    return root


def test_current_gate_in_pult_records_a_receipt_without_opening_the_run_panel(
        tmp_path, chromium: Browser):
    root = _world(tmp_path)
    with identified_server(root, PROJECT) as origin:
        context = chromium.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(f"{origin}/panel/desk.html#project={PROJECT}&task=task-fix"
                      "&run=run-fix-new&lang=en")
            card = page.locator("#deskPult [data-desk-decision]")
            expect(card).to_be_visible()
            expect(page.locator("#deskRun")).to_be_hidden()
            expect(card).to_contain_text("Human Gate")
            page.locator('[data-focus-key="pult:actor-change"]').click()
            page.locator('[data-focus-key="pult:actor-name"]').fill("desk-owner")
            page.locator('[data-focus-key="pult:actor-save"]').click()
            expect(card).to_contain_text("desk-owner")
            button = card.locator('[data-focus-key="action:submitDecision"]')
            expect(button).to_be_enabled()
            with page.expect_response(lambda response: response.url.endswith("/decisions")) as sent:
                button.click()
            assert sent.value.status == 201, sent.value.json()
            recorded = [row.value for row in RunStore(root).read("run-fix-new").records
                        if row.kind == "decision"]
            assert len(recorded) == 1
            assert recorded[0].gate_id == "gate-confirm-do"
            assert recorded[0].actor == "desk-owner"
            assert errors == []
        finally:
            context.close()


def _gate_pair(root, run):
    store = RunStore(root)
    config = {"cycle": {"id": "default-orbit"}, "task": {"id": "task-fix", "work_scope": "task-fix"},
              "instances": [{"id": "qa", "adapter": "codex"}]}
    store.create_run(a_run(run_id=run, mode="confirm", config_digest=snapshot_digest(config)), config)
    store.append(GraphDefinition("gates", run, NOW, nodes=(
        GraphNode("confirm", "gate", "Confirm Do", gate_id="gate-confirm-do"),
        GraphNode("result", "gate", "Result Gate", gate_id="gate-result")),
        edges=(GraphEdge("confirm", "result", condition="on_approved"),)))
    return store


def test_pult_offers_the_next_unanswered_gate_and_history_keeps_the_first(tmp_path, chromium: Browser):
    root = _world(tmp_path)
    run = "two-gates"
    store = _gate_pair(root, run)
    with identified_server(root, PROJECT) as origin:
        context = chromium.new_context(viewport={"width": 375, "height": 900})
        page = context.new_page()
        try:
            page.goto(f"{origin}/panel/desk.html#project={PROJECT}&task=task-fix&run={run}&lang=en")
            card = page.locator("#deskPult [data-desk-decision]")
            expect(card.locator("h3").first).to_have_text("Confirm Do")
            page.locator('[data-focus-key="pult:actor-change"]').click()
            page.locator('[data-focus-key="pult:actor-name"]').fill("qa-owner")
            page.locator('[data-focus-key="pult:actor-save"]').click()
            with page.expect_response(lambda row: row.url.endswith("/decisions")) as sent:
                card.locator('[data-focus-key="action:submitDecision"]').click()
            assert sent.value.status == 201
            expect(card.locator("h3").first).to_have_text("Result Gate")
            page.locator("#deskRunToggle").click()
            page.locator(f'[data-focus-key="decision:{run}/gate-confirm-do"]').click()
            expect(page.locator("#deskRun .studio-decisions")).to_contain_text("qa-owner")
            expect(card.locator("h3").first).to_have_text("Result Gate")
            assert [r.value.gate_id for r in store.read(run).records if r.kind == "decision"] == [
                "gate-confirm-do"]
            with page.expect_response(lambda row: row.url.endswith("/decisions")) as sent:
                card.locator('[data-focus-key="action:submitDecision"]').click()
            assert sent.value.status == 201
            assert [r.value.gate_id for r in store.read(run).records if r.kind == "decision"] == [
                "gate-confirm-do", "gate-result"]
        finally:
            context.close()


def test_view_gate_is_visible_with_a_disabled_reason(tmp_path, chromium: Browser):
    root = _world(tmp_path)
    with identified_server(root, PROJECT, mode="view") as origin:
        context = chromium.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        writes: list[str] = []
        page.on("request", lambda request: writes.append(request.url)
                if request.method == "POST" else None)
        try:
            page.goto(f"{origin}/panel/desk.html#project={PROJECT}&task=task-fix"
                      "&run=run-fix-new&lang=ru")
            card = page.locator("#deskPult [data-desk-decision]")
            expect(card).to_be_visible()
            expect(card).to_contain_text("Проект открыт для просмотра")
            expect(card.locator('[data-focus-key="action:submitDecision"]')).to_be_disabled()
            assert writes == []
        finally:
            context.close()


def test_narrow_gate_keeps_keyboard_choices_and_their_text_inside_the_card(tmp_path, chromium: Browser):
    root = _world(tmp_path)
    run = "task-8d5d8cc04a694ee198705517-r1"
    store = _gate_pair(root, run)
    with identified_server(root, PROJECT) as origin:
        context = chromium.new_context(viewport={"width": 375, "height": 900})
        page = context.new_page()
        try:
            page.goto(f"{origin}/panel/desk.html#project={PROJECT}&task=task-fix&run={run}&lang=ru")
            card = page.locator("#deskPult [data-desk-decision]")
            page.locator('[data-focus-key="pult:actor-change"]').click()
            page.locator('[data-focus-key="pult:actor-name"]').fill("qa-fixture-owner")
            page.locator('[data-focus-key="pult:actor-save"]').click()
            with page.expect_response(lambda row: row.url.endswith("/decisions")) as sent:
                card.locator('[data-focus-key="action:submitDecision"]').click()
            assert sent.value.status == 201
            expect(card.locator("h3").first).to_have_text("Result Gate")
            layout = page.evaluate("""() => {
              const card = document.querySelector('#deskPult [data-desk-decision]');
              const edge = Math.min(innerWidth, card.getBoundingClientRect().right);
              const choices = Array.from(card.querySelectorAll('.studio-choice'));
              const clipped = Array.from(card.querySelectorAll('.studio-choice span')).filter(span => {
                const range = document.createRange(); range.selectNodeContents(span);
                return Array.from(range.getClientRects()).some(rect => rect.right > edge + 1);
              }).map(span => span.textContent);
              const crowded = choices.filter(choice => {
                const explanation = choice.querySelector('.studio-choice__m').getBoundingClientRect();
                const outcome = choice.querySelector('.studio-choice__c').getBoundingClientRect();
                return outcome.top < explanation.bottom - 1;
              }).map(choice => choice.querySelector('input').value);
              return [choices.length, clipped, crowded];
            }""")
            assert layout == [4, [], []], "each outcome should fit and follow its explanation"
            first = card.locator('[data-focus-key="choice:approve"]')
            second = card.locator('[data-focus-key="choice:reject"]')
            first.focus()
            page.keyboard.press("ArrowDown")
            expect(second).to_be_checked()
            expect(second).to_be_focused()
            assert [r.value.gate_id for r in store.read(run).records if r.kind == "decision"] == [
                "gate-confirm-do"]
        finally:
            context.close()
