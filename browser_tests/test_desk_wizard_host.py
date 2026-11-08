"""The live desk mounts its wizard against a real one-project command server."""
from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import replace
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, expect

from browser_tests.desk_hold import close_context, until
from conductor import ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.codex_cli import CODEX_PROFILE
from conductor.command.adapters.grok_build import GROK_PROFILE
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
    if getattr(request, "param", False) == "pins":
        class CheckedCodex(_StandardAdapter):
            profile = CODEX_PROFILE

        class CheckedGrok(_StandardAdapter):
            profile = GROK_PROFILE

        names = ("claude-code", "codex", "grok-build")
        adapters = [_StandardAdapter(run_store, adapter_id=names[0]), CheckedCodex(run_store, adapter_id=names[1]),
                    CheckedGrok(run_store, adapter_id=names[2])]
    else:
        names = ("claude-code", "codex")
        adapters = [_StandardAdapter(run_store, adapter_id=name) for name in names]
    registry = AdapterRegistry(adapters)
    httpd = server.build(root, 0, registry=registry)
    declared = contracts(reachable=names, known=names)
    # Injected adapters have no operator pins. Keep the same explicit test-only
    # provider digest used by the real-server flow driver bench.
    if getattr(request, "param", False) is True:
        declared = tuple(replace(row, auth="api_key") for row in declared)
        configs = [ProviderConfig("claude-code", "/test/claude", "fake-claude-jsonl-v1"),
                   ProviderConfig("codex", "/test/codex", "fake-codex-jsonl-v1")]
        authority = ProviderAuthority(configs, declared, registry)
        httpd.command_api._policy.provider_digest = authority.digest
        httpd.command_api._policy.provider_facts = authority.facts
    else:
        httpd.command_api._policy.provider_digest = lambda _config: PD
        httpd.command_api._policy.provider_facts = None
    httpd.command_api._providers = declared
    # This fixture substitutes test adapters for the production catalogue.
    # Membership is explicit; availability still comes from the real contracts
    # and task-channel facts only from the registered adapter classes.
    httpd.command_api._offered_provider_ids = frozenset(names)
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
        expect(form.locator('[data-guide-executors]')).to_contain_text("claude-code")
        expect(form.locator('[data-guide-checkers]')).to_contain_text("codex")
        expect(form.locator('[data-guide-time]')).to_contain_text("резерв" if lang == "ru" else "reserve", ignore_case=True)
        expect(form.locator('[data-plan-step="do"]')).not_to_be_visible()
        form.locator('[data-guide-details="terms"] summary').click()
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
        close_context(context)


@pytest.mark.parametrize("wizard_url", ["pins"], indirect=True)
def test_owner_pinned_codex_and_default_grok_reach_the_frozen_grant_card(chromium: Browser, wizard_url):
    page = chromium.new_page()
    try:
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        def open_assignments(form, phase):
            summary = form.locator('[data-guide-details="assignments"] summary')
            try:
                expect(summary).to_be_visible()
            except AssertionError as exc:
                listed = page.request.get(wizard_url.split("/panel/")[0] + "/command/workflows").json()
                raise AssertionError((phase, listed.get("workflows"), errors)) from exc
            summary.click()
        page.goto(wizard_url + "#lang=en")
        page.locator('[data-focus-key="pult:actor-change"]').click()
        page.locator('[data-focus-key="pult:actor-name"]').fill("owner")
        page.locator('[data-focus-key="pult:actor-save"]').click()
        page.locator("#deskNewTask").click()
        form = page.locator("#deskWizard")
        form.locator('[data-focus="wizard:brief"]').fill("Review three files.")
        form.locator('[data-focus="wizard:git:run_without_git"]').click()
        form.locator('[data-focus="wizard:next"]').click()
        open_assignments(form, "fresh")
        checker = form.locator('[data-focus="wizard:role:role-checker"]')
        checker.select_option("codex")
        model = form.locator('[data-focus="wizard:model:role-checker"]')
        expect(model).to_have_value("")
        model.fill("invalid model id")
        expect(form.locator('[data-focus="wizard:next"]')).to_be_disabled()
        model.fill("gpt-6.1-sol")
        checker.select_option("claude-code")
        checker.select_option("codex")
        expect(model).to_have_value("")
        model.fill("gpt-6.1-sol")
        form.locator('[data-focus="wizard:role:role-diagnostician"]').select_option("grok-build")
        expect(form.locator('[data-focus="wizard:model:role-diagnostician"]')).to_have_count(0)
        expect(form.locator('[data-draft="saved"]')).to_be_visible()
        page.reload()
        form.locator('[data-focus="wizard:next"]').click()
        open_assignments(form, "reloaded")
        expect(model).to_have_value("gpt-6.1-sol")
        form.locator('[data-focus="wizard:back"]').click()
        form.locator('[data-focus="wizard:next"]').click()
        form.locator('[data-focus="wizard:next"]').click()
        with page.expect_request(lambda req: req.method == "POST" and req.url.endswith("/command/runs")) as sent:
            form.locator('[data-focus="wizard:prepare:go"]').click()
        body = sent.value.post_data_json
        pins = {p["instance_id"]: (p["provider_id"], p["model"]) for p in body["participants"]}
        assert pins["instance-role-checker"] == ("codex", "gpt-6.1-sol")
        assert pins["instance-role-diagnostician"] == ("grok-build", None)
        expect(form.locator("[data-guide-checkers]")).to_contain_text("gpt-6.1-sol")
        form.locator('[data-focus="wizard:launch:actor"]').fill("owner")
        expect(form.locator('[data-focus="wizard:launch:start"]')).to_be_enabled()
        base = wizard_url.split("/panel/")[0]
        config = page.request.get(f'{base}/command/runs/{body["run_id"]}').json()["config"]
        frozen = {r["id"]: r.get("model") for r in config["instances"]}
        assert frozen["instance-role-checker"] == "gpt-6.1-sol"
        assert frozen["instance-role-diagnostician"] is None
    finally:
        close_context(page.context)


@pytest.mark.parametrize("wizard_url", ["pins"], indirect=True)
def test_saved_cycle_runs_the_selected_revision_and_preserves_the_workflow_draft(
        chromium: Browser, wizard_url, tmp_path):
    from conductor.command.graph_template import load_template
    from conductor.command.template_store import TemplateStore
    from conductor.command.workflow_draft import WorkflowDraft, publish_candidate

    templates = TemplateStore(tmp_path)
    key = "colleague-dalio"
    row = load_template("dalio-v6").as_dict()
    document = {k: v for k, v in row.items() if k not in ("template_id", "revision")}
    document.update(title="Reviewed Dalio", execution_contract="bounded-run-v1")
    templates.save(publish_candidate(document, workflow_id=key, revision=1))
    draft = {**document, "title": "Unfinished change",
             "nodes": [n for n in document["nodes"] if n["node_id"] != "do"]}
    templates.save_draft(WorkflowDraft(key, "2026-11-08T08:00:00Z", draft))
    original = templates.draft_path(key).read_bytes()
    page = chromium.new_page(viewport={"width": 375, "height": 900})
    try:
        page.goto(wizard_url + "#lang=en")
        page.locator("#deskNewTask").click()
        form = page.locator("#deskWizard")
        field = lambda key: form.locator(f'[data-focus="wizard:{key}"]')
        field("brief").fill("Fix the mixed success counter.")
        field("git:run_without_git").click()
        field("next").click()
        form.locator('[data-guide-details="choose"] summary').click()
        field("cycle:choose:" + key).click()
        form.locator('[data-guide-details="assignments"] summary').click()
        expect(field("role:role-implementer")).to_be_visible()
        field("role:role-diagnostician").select_option("grok-build")
        field("role:role-checker").select_option("codex")
        field("instr:do:text").fill("Implement the checked fix.")
        expect(form.locator('[data-draft="saved"]')).to_be_visible()
        assert templates.draft_path(key).read_bytes() == original
        # A different maintainer publishes a later revision while this tab is open.
        templates.save(publish_candidate({**document, "title": "Revised tomorrow"},
                                         workflow_id=key, revision=2))
        page.reload()
        field("next").click()
        expect(form.get_by_text("Selected revision 1", exact=True)).to_be_visible()
        field("next").click()
        with page.expect_request(lambda req: req.method == "POST"
                                 and req.url.endswith("/command/runs")) as sent:
            field("prepare:go").click()
        planned = sent.value.post_data_json
        assert planned["workflow_id"] == key and planned["revision"] == 1
        expect(form.locator('[data-guide-checkers]')).to_contain_text("codex")
        assert templates.revisions(key) == (1, 2)
        assert templates.draft_path(key).read_bytes() == original
    finally:
        close_context(page.context)


def test_unsubmitted_answers_survive_reload_only_in_their_project(chromium: Browser, wizard_url):
    context = chromium.new_context()
    try:
        page = context.new_page()
        posts = []
        page.on("request", lambda row: posts.append(urlsplit(row.url).path) if row.method == "POST"
                and not row.url.endswith("/project/task-draft") else None)
        page.goto(wizard_url + "#lang=en")
        page.locator("#deskNewTask").click()
        form = page.locator("#deskWizard")
        brief = form.locator('[data-focus="wizard:brief"]')
        brief.fill("Keep my first draft 🧭")
        form.locator('[data-focus="wizard:git:run_without_git"]').click()
        expect(form.locator('[data-draft="saved"]')).to_be_visible()
        entry = page.evaluate("history.state.deskTaskDraft")
        assert set(entry) == {"key", "project"} and len(entry["key"]) == 32
        page.reload()
        expect(brief).to_have_value("Keep my first draft 🧭")
        expect(form.locator('[data-focus="wizard:next"]')).to_be_enabled()
        assert not posts
        form.locator('[data-focus="wizard:next"]').click()
        form.locator('[data-guide-details="choose"] summary').click()
        form.locator('[data-focus="wizard:cycle:choose:desk-short"]').click()
        expect(form.locator('h3[data-card-id="desk-short"]')).to_be_visible()
        expect(form.locator('[data-focus="wizard:next"]')).to_be_enabled()
        expect(form.locator('[data-draft="saved"]')).to_be_visible()
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
        close_context(context)


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
        expect(form.locator('[data-draft="saved"]')).to_be_visible()
        assert set(page.evaluate("history.state.deskTaskDraft")) == {"key", "project"}
        page.reload()
        form.locator('[data-guide-details="optional"] summary').click()
        expect(content).to_have_value(raw + " Owner's edit.")
    finally:
        close_context(context)


@pytest.mark.parametrize("committed", [False, True], ids=["before-request", "before-ack"])
def test_unacknowledged_edit_is_marked_and_close_discards_a_late_save(chromium: Browser, wizard_url, committed):
    context = chromium.new_context()
    try:
        page = context.new_page()
        held = []
        def delay(route):
            if route.request.post_data_json["op"] == "save":
                held.append((route, route.fetch() if committed else None))
            else:
                route.continue_()
        page.route("**/command/project/task-draft", delay)
        page.goto(wizard_url + "#lang=en")
        page.locator("#deskNewTask").dblclick()
        form = page.locator("#deskWizard")
        brief = form.locator('[data-focus="wizard:brief"]')
        with page.expect_request(lambda row: row.url.endswith("/project/task-draft")
                                 and row.post_data_json["op"] == "save"):
            brief.fill("still editing")
        expect(form.locator('[data-draft="saving"]')).to_be_visible()
        until(page, "the draft save is held before the request or acknowledgement", lambda: bool(held))
        assert not page.evaluate("window.dispatchEvent(new Event('beforeunload', {cancelable:true}))")
        assert "still editing" not in page.evaluate("JSON.stringify(history.state) + location.href")
        with page.expect_response(lambda row: row.url.endswith("/project/task-draft")
                                  and row.request.post_data_json["op"] == "discard") as discarded:
            form.locator('[data-focus="wizard:close"]').click()
        assert discarded.value.status == 200
        assert page.evaluate("!history.state?.deskTaskDraft")
        with page.expect_response(lambda row: row.url.endswith("/project/task-draft")
                                  and row.request.post_data_json["op"] == "save") as late:
            route, remote = held[0]
            if remote is None:
                route.continue_()
            else:
                route.fulfill(response=remote)
        assert late.value.status == (200 if committed else 404)
        page.locator("#deskNewTask").click()
        expect(brief).to_have_value("")
    finally:
        close_context(context)


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
        close_context(context)
