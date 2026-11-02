"""The live desk mounts its wizard against a real one-project command server."""
from __future__ import annotations

import threading
from collections.abc import Iterator
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, expect

from conductor import ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.policy_providers import ProviderAuthority
from conductor.command.run_store import RunStore
from tests.test_command_workflow_routes import contracts
from tests.test_policy_runtime import PD
from tests.test_standard_cycle_checker import _StandardAdapter
from tests.test_store import good_lane, write_project


@pytest.fixture
def wizard_url(tmp_path, request) -> Iterator[str]:
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    ownership_transition.activate(root, legacy_writers_stopped=True)
    run_store = RunStore(root)
    registry = AdapterRegistry([
        _StandardAdapter(run_store, adapter_id="claude-code"),
        _StandardAdapter(run_store, adapter_id="codex")])
    httpd = server.build(root, 0, registry=registry)
    declared = contracts()
    httpd.command_api._providers = declared
    # Injected adapters have no operator pins. Keep the same explicit test-only
    # provider digest used by the real-server flow driver bench.
    if getattr(request, "param", False):
        configs = [ProviderConfig("claude-code", "/test/claude", "fake-claude-jsonl-v1"),
                   ProviderConfig("codex", "/test/codex", "fake-codex-jsonl-v1")]
        authority = ProviderAuthority(configs, declared, registry)
        httpd.command_api._policy.provider_digest = authority.digest
        httpd.command_api._policy.provider_facts = authority.facts
    else:
        httpd.command_api._policy.provider_digest = lambda _config: PD
        httpd.command_api._policy.provider_facts = None
    # This fixture substitutes test adapters for the production catalogue.
    # Membership is explicit; availability still comes from the real contracts
    # and task-channel facts only from the registered adapter classes.
    httpd.command_api._offered_provider_ids = frozenset({"claude-code", "codex"})
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}/panel/desk.html"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()


@pytest.mark.parametrize(("lang", "width"), [("ru", 375), ("en", 1100)])
@pytest.mark.parametrize("wizard_url", [True, False], indirect=True, ids=["configured", "no-metadata"])
def test_first_task_reaches_a_reviewed_dalio_without_manual_ids(chromium: Browser, wizard_url, lang, width):
    context = chromium.new_context(viewport={"width": width, "height": 900})
    try:
        page = context.new_page()
        posts, errors, refusals = [], [], []
        page.on("request", lambda req: posts.append(urlsplit(req.url).path) if req.method == "POST" else None)
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on("response", lambda row: refusals.append((urlsplit(row.url).path, row.json()))
                if row.status >= 400 and "/command/" in row.url else None)
        page.goto(f"{wizard_url}#lang={lang}")
        page.locator('[data-focus-key="pult:actor-change"]').click()
        page.locator('[data-focus-key="pult:actor-name"]').fill("owner")
        page.locator('[data-focus-key="pult:actor-save"]').click()
        page.locator("#deskNewTask").click()
        form = page.locator("#deskWizard")
        def forward():
            button = form.locator('[data-focus="wizard:next"]')
            try:
                expect(button).to_be_enabled(timeout=5000)
            except AssertionError as exc:
                raise AssertionError((form.locator("[data-body]").get_attribute("data-body"),
                                      form.locator("[data-wizard-reason]").inner_text(),
                                      form.locator(".desk-wizard__diagnostics").all_inner_texts())) from exc
            button.click()
        expect(form.locator("[data-guide-stage]")).to_have_count(3)
        empty = form.locator('[data-focus="wizard:git:run_without_git"]')
        expect(empty).to_be_visible()
        expect(empty).to_have_attribute("aria-checked", "false")
        expect(form.locator('[data-focus="wizard:git:connect_git"]')).not_to_be_visible()
        goal = "Проверить отчёт 🧭\nСохранить исходные строки."
        form.locator('[data-focus="wizard:brief"]').fill(goal)
        form.locator('[data-guide-details="optional"] summary').click()
        title = form.locator('[data-focus="wizard:title"]')
        expect(title).to_have_value("Проверить отчёт 🧭")
        title.fill("Owner's task")
        form.locator('[data-focus="wizard:mode"]').click()
        expect(form.locator('[data-focus="wizard:brief"]')).to_have_value(goal)
        form.locator('[data-focus="wizard:mode"]').click()
        form.locator('[data-focus="wizard:brief"]').fill(goal + " ✓")
        empty.click()
        expect(empty).to_have_attribute("aria-checked", "true")
        forward()
        expect(form.locator('[data-guide-stage="team"]')).to_have_attribute("aria-current", "step")
        expect(form.locator('h3[data-card-id="dalio-v6"]')).to_be_visible()
        expect(form.locator('[data-guide-role="executor"]')).to_contain_text("claude-code")
        expect(form.locator('[data-guide-role="checker"]')).to_contain_text("codex")
        expect(form.locator('[data-role="role-checker"] select')).not_to_be_visible()
        form.locator('[data-guide-details="assignments"] summary').click()
        expect(form.locator('[data-role="role-checker"] select')).to_be_visible()
        expect(form.locator("[data-role]")).to_have_count(5)
        form.locator('[data-focus="wizard:back"]').click()
        expect(form.locator('[data-focus="wizard:brief"]')).to_have_value(goal + " ✓")
        forward()
        forward()
        expect(form.locator('[data-guide-stage="review"]')).to_have_attribute("aria-current", "step")
        expect(form.locator("[data-body]")).to_contain_text("Owner's task")
        assert not any(path.endswith("/automation/preview") for path in posts)
        form.locator('[data-focus="wizard:prepare:go"]').dblclick()
        try:
            expect(form.locator('[data-focus="wizard:launch:start"]')).to_be_enabled(timeout=5000)
        except AssertionError as exc:
            raise AssertionError((refusals, form.inner_text())) from exc
        assert not any(path.endswith("/automation/authorize") for path in posts)
        assert not any("/command/project/git/" in path for path in posts)
        assert sum(path.endswith("/runs") for path in posts) == 1
        assert sum(path.endswith("/automation/preview") for path in posts) == 1
        expect(form.locator('[data-plan-step="do"]')).to_contain_text("claude-code")
        expect(form.locator('[data-plan-step="do"] [data-checker]')).to_contain_text("codex")
        expect(form.locator('[data-harness="codex"]')).to_be_visible()
        checkpoints = form.locator("[data-owner-gates]")
        expect(checkpoints.locator("li")).to_have_count(2)
        expect(checkpoints.locator("li").first).to_contain_text("Human Gate - Confirm Do")
        expect(checkpoints.locator("li").first).to_contain_text("Design the Plan")
        expect(checkpoints.locator("li").last).to_contain_text("Result Gate")
        expect(checkpoints.locator("li").last).to_contain_text("Do")
        assert errors == []
        assert form.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    finally:
        context.close()


def test_unsubmitted_answers_survive_reload_only_in_their_project(chromium: Browser, wizard_url):
    context = chromium.new_context()
    try:
        page = context.new_page()
        posts = []
        page.on("request", lambda row: posts.append(urlsplit(row.url).path) if row.method == "POST" else None)
        page.goto(wizard_url + "#lang=en")
        page.locator("#deskNewTask").click()
        form = page.locator("#deskWizard")
        brief = form.locator('[data-focus="wizard:brief"]')
        brief.fill("Keep my first draft 🧭")
        form.locator('[data-focus="wizard:git:run_without_git"]').click()
        entry, saved = page.evaluate("""() => {
          const p = history.state?.deskTaskDraft;
          return p ? [p, JSON.parse(sessionStorage.getItem('desk.first-task.v1:'+p.project+':'+p.task))] : [null,null];
        }""")
        assert entry and set(entry) == {"task", "project"}
        assert saved["brief"] == "Keep my first draft 🧭"
        assert {"authorization", "preview", "actor", "run", "token", "reads"}.isdisjoint(saved)
        page.reload()
        expect(brief).to_have_value("Keep my first draft 🧭")
        expect(form.locator('[data-focus="wizard:next"]')).to_be_enabled()
        assert not posts
        form.locator('[data-focus="wizard:next"]').click()
        form.locator('[data-guide-details="choose"] summary').click()
        form.locator('[data-focus="wizard:cycle:choose:desk-short"]').click()
        expect(form.locator('h3[data-card-id="desk-short"]')).to_be_visible()
        expect(form.locator('[data-focus="wizard:next"]')).to_be_enabled()
        count = len(posts)
        page.reload()
        expect(brief).to_have_value("Keep my first draft 🧭")
        assert len(posts) == count
        form.locator('[data-focus="wizard:next"]').click()
        expect(form.locator('h3[data-card-id="desk-short"]')).to_be_visible()
        expect(form.locator('[data-focus="wizard:next"]')).to_be_enabled()
        form.locator('[data-focus="wizard:back"]').click()
        count = len(posts)
        page.evaluate("() => history.replaceState({...history.state,deskTaskDraft:"
                      "{...history.state.deskTaskDraft, project:'0'.repeat(32)}},'')")
        page.reload()
        expect(brief).to_have_value("")
        brief.fill("Discard on close")
        form.locator('[data-focus="wizard:close"]').click()
        page.locator("#deskNewTask").click()
        expect(brief).to_have_value("")
        assert len(posts) == count
    finally:
        context.close()


def test_copied_material_is_reread_and_only_the_owner_edit_is_saved(chromium: Browser, wizard_url):
    context = chromium.new_context()
    try:
        page = context.new_page()
        doc_id, oid = "d-" + "8" * 32, "7" * 40
        raw = "A project document outside the draft cache."
        row = {"doc_id": doc_id, "git_oid": oid, "path": "docs/readme.md", "length": len(raw)}
        page.route("**/command/project/documents", lambda route: route.fulfill(json={"documents": [row]}))
        page.route("**/command/project/documents/" + doc_id,
                   lambda route: route.fulfill(json={"git_oid": oid, "content": raw}))
        page.goto(wizard_url + "#lang=en")
        page.locator("#deskNewTask").click()
        form = page.locator("#deskWizard")
        form.locator('[data-guide-details="optional"] summary').click()
        form.locator('[data-focus="wizard:add:project_doc"]').click()
        form.locator(f'[data-focus="wizard:picker:take:{doc_id}"]').click()
        form.locator('[data-focus="wizard:card:m1:mode:copy"]').click()
        content = form.locator('[data-focus="wizard:card:m1:content"]')
        expect(content).to_have_value(raw)
        content.fill(raw + " Owner's edit.")
        saved = page.evaluate("""() => {const p=history.state.deskTaskDraft;
          return sessionStorage.getItem('desk.first-task.v1:'+p.project+':'+p.task);}""")
        assert "Owner's edit" in saved and raw not in saved
        page.reload()
        form.locator('[data-guide-details="optional"] summary').click()
        expect(content).to_have_value(raw + " Owner's edit.")
    finally:
        context.close()


def test_new_task_uses_real_git_task_seed_and_run_routes(chromium: Browser, wizard_url: str):
    context = chromium.new_context(viewport={"width": 1100, "height": 1300})
    try:
        page = context.new_page()
        page.set_default_timeout(10000)
        asked: list[tuple[str, str]] = []
        responses: list[tuple[int, str]] = []
        preview_answers: list[object] = []
        errors: list[str] = []
        page.on("request", lambda request: asked.append(
            (request.method, urlsplit(request.url).path)))
        page.on("response", lambda response: responses.append(
            (response.status, urlsplit(response.url).path)))
        page.on("response", lambda response: preview_answers.append(response.json())
                if urlsplit(response.url).path.endswith("/automation/preview") else None)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{wizard_url}#lang=en", wait_until="load")
        page.locator('[data-focus-key="pult:actor-change"]').click()
        page.locator('[data-focus-key="pult:actor-name"]').fill("owner")
        page.locator('[data-focus-key="pult:actor-save"]').click()
        new = page.locator("#deskNewTask")
        expect(new).to_be_enabled()
        new.click()
        wizard = page.locator("#deskWizard [data-wizard]")
        expect(wizard).to_have_attribute("data-wizard-current", "task")
        assert ("GET", "/command/project/git") in asked
        page.locator('[data-focus="wizard:mode"]').click()
        page.locator('[data-focus="wizard:title"]').fill("Host path")
        page.locator('[data-focus="wizard:brief"]').fill("Prepare the path.")
        page.locator('[data-focus="wizard:next"]').click()
        expect(wizard).to_have_attribute("data-wizard-current", "materials")
        expect(page.locator('[data-git-state="not_git"]')).to_have_count(1)
        page.locator('[data-focus="wizard:git:run_without_git"]').click()
        page.locator('[data-focus="wizard:next"]').click()
        expect(wizard).to_have_attribute("data-wizard-current", "cycle")
        page.locator('[data-focus="wizard:cycle:choose:desk-short"]').click()
        expect(page.locator('[data-focus="wizard:next"]')).to_be_enabled()
        page.locator('[data-focus="wizard:next"]').click()
        expect(wizard).to_have_attribute("data-wizard-current", "roles")
        for field in page.locator('[data-instruction] textarea').all():
            field.fill("Carry out this step and report its result.")
        ready = page.locator('[data-focus="wizard:next"]')
        try:
            expect(ready).to_be_enabled()
        except AssertionError as error:
            raise AssertionError({
                "reason": page.locator('[data-wizard-reason]').inner_text(),
                "checks": page.locator('.desk-wizard__diagnostics').all_inner_texts(),
                "roles": page.locator('[data-role]').evaluate_all(
                    "nodes => nodes.map(node => [node.dataset.role, node.dataset.by])"),
                "responses": responses,
                "errors": errors,
            }) from error
        page.locator('[data-focus="wizard:next"]').click()
        expect(wizard).to_have_attribute("data-wizard-current", "prepare")
        page.locator('[data-focus="wizard:prepare:go"]').click()
        try:
            expect(page.locator('[data-prepare="review"]')).to_be_visible()
        except AssertionError as error:
            raise AssertionError({"prepare": page.locator('#deskWizard').inner_text(),
                                  "preview_answers": preview_answers,
                                  "responses": [row for row in responses
                                                if row[1].startswith('/command/')]}) from error
        page.locator('[data-focus="wizard:next"]').click()
        expect(wizard).to_have_attribute("data-wizard-current", "run")
        expect(page.locator('[data-focus="wizard:launch:start"]')).to_be_enabled()
        page.locator('[data-focus="wizard:launch:start"]').click()
        expect(page.locator("#deskWizard")).to_be_hidden()
        expect(page.locator("#deskScene")).to_have_attribute("data-state", "ready")
        address = page.evaluate("() => Object.fromEntries(new URLSearchParams("
                                "location.hash.slice(1)))")
        assert address["task"].startswith("task-")
        assert address["run"] == f'{address["task"]}-r1'
        paths = {path for _method, path in asked}
        assert any(path.endswith("/seed") for path in paths)
        assert ("POST", "/command/tasks") in asked
        assert ("POST", "/command/runs") in asked
        assert ("GET", f'/command/runs/{address["run"]}') in asked
        assert errors == []
    finally:
        context.close()
