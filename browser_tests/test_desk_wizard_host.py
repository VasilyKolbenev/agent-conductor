"""The live desk mounts its wizard against a real one-project command server."""
from __future__ import annotations

import threading
from collections.abc import Iterator
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, expect

from conductor import ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.run_store import RunStore
from tests.test_command_workflow_routes import contracts
from tests.test_policy_runtime import PD
from tests.test_standard_cycle_checker import _StandardAdapter
from tests.test_store import good_lane, write_project


@pytest.fixture
def wizard_url(tmp_path) -> Iterator[str]:
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    ownership_transition.activate(root, legacy_writers_stopped=True)
    run_store = RunStore(root)
    httpd = server.build(root, 0, registry=AdapterRegistry([
        _StandardAdapter(run_store, adapter_id="claude-code"),
        _StandardAdapter(run_store, adapter_id="codex")]))
    httpd.command_api._providers = contracts()
    # Injected adapters have no operator pins. Keep the same explicit test-only
    # provider digest used by the real-server flow driver bench.
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
