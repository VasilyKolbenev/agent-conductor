"""The installed Studio's preview, grant and result are one offline application journey."""
from threading import Thread

from playwright.sync_api import expect

from conductor import demo, ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from tests.relay_roads import CODEX, Site
from tests.test_patch_do_policy import ACTUAL, PATCH, run_state, work_and_calls
from tests.test_policy_runtime import NOW, PD


def test_review_one_patch_and_see_the_independent_result(chromium, tmp_path):
    root = demo.materialize(tmp_path / "root")
    ownership_transition.activate(root, legacy_writers_stopped=True)
    site = Site(tmp_path, CODEX, root=root)
    with site.owned():
        f = run_state(site.root, site.adapter)
        TaskStore(site.root).create_task(TaskRecord("one", "Исправить счётчик", "one", NOW))
        work, calls = work_and_calls(site, PATCH)
    srv = server.build(site.root, 0, registry=AdapterRegistry([site.adapter]))
    # An injected registry has no installed-provider descriptors.
    srv.command_api._policy.provider_digest = lambda _: PD
    srv.command_api._policy.provider_facts = None
    thread = Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    context = chromium.new_context(viewport={"width": 1280, "height": 850})
    try:
        page = context.new_page()
        base = f"http://127.0.0.1:{srv.server_port}"
        page.goto(f"{base}/#screen=runs&task=one&run=run&lang=ru")
        panel = page.locator('[data-automation="run"]')
        expect(panel.locator("[data-automation-state]")).to_have_attribute(
            "data-automation-state", "unconfigured")
        actor = panel.locator('[data-focus="automation:run:actor"]')
        actor.fill("offline-test")
        with page.expect_response(lambda r: r.url.endswith("/automation/preview")) as heard:
            panel.locator('[data-focus="automation:preview"]').click()
        preview = heard.value.json()
        assert heard.value.status == 200, preview
        assert preview["patch_steps"] == ["do"] and preview["terms"]["max_actions"] == 1
        expect(panel.locator("[data-automation-preview]")).to_contain_text(
            "Этим же действием приложение применит его к копии задачи.")
        assert calls == [] and (work / "count.py").read_bytes() != ACTUAL
        with page.expect_response(lambda r: r.url.endswith("/automation/authorize")) as accepted:
            panel.locator('[data-focus="automation:authorize"]').click()
        assert accepted.value.ok
        expect(panel.locator("[data-automation-state]")).to_have_attribute(
            "data-automation-state", "complete", timeout=15000)
        records = f.store.read("run").records
        assert calls == ["prepare", "apply", "check"]
        assert len([r for r in records if r.kind == "action_request"]) == 1
        assert [r.value.outcome for r in records if r.kind == "action_result"] == ["succeeded"]
        assert [r.value.verifier_instance_id for r in records
                if r.kind == "evidence"] == ["checker"]
        assert (work / "count.py").read_bytes() == ACTUAL
        writes = []
        page.on("request", lambda req: writes.append(req.method) if req.method == "POST" else None)
        views = [("ru", 1280, "Открыть результат"), ("en", 375, "Open the result")]
        for lang, width, label in views:
            page.set_viewport_size({"width": width, "height": 850})
            page.goto(f"{base}/#screen=runs&task=one&run=run&lang={lang}")
            opening = page.get_by_role("button", name=label, exact=True)
            opening.focus()
            opening.press("Enter")
            result = page.locator("[data-last-outcome]")
            expect(result).to_be_focused()
            listing = result.locator("[data-patch-result]")
            expect(listing).to_be_in_viewport()
            expect(listing).to_contain_text("checker")
            expect(listing).to_contain_text("work/_tasks/one/item")
            page.goto(f"{base}/panel/desk.html#task=one&run=run&lang={lang}")
            desk_result = page.locator("[data-deck-run='run'] [data-patch-result]").first
            expect(desk_result).to_contain_text("work/_tasks/one/item")
            expect(desk_result).to_contain_text("checker")
        assert not writes
    finally:
        context.close()
        srv.shutdown()
        thread.join(5)
        srv.server_close()


def test_select_patch_in_studio_and_publish_the_new_revision(chromium, tmp_path):
    from conductor.command.template_store import TemplateStore
    from conductor.command.workflow_draft import WorkflowDraft
    from tests.test_command_workflow_draft import a_document

    root = demo.materialize(tmp_path / "editing")
    templates = TemplateStore(root)
    document = a_document(execution_contract="bounded-run-v1")
    document["nodes"][1].update(
        verifier_role_id="role-checker", timeout_seconds=60, attempt_bound=1)
    templates.save_draft(WorkflowDraft(workflow_id="repair", saved_at=NOW, document=document))
    srv = server.build(root, 0, registry=AdapterRegistry([]))
    thread = Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    context = chromium.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{srv.server_port}/#lang=ru")
        page.locator("#navWorkflow").click()
        page.locator("#workflowToolbar select[name='workflow']").select_option("repair")
        page.locator('[data-node-id="do"]').click()
        selector = page.get_by_label("Как Do изменяет файлы")
        expect(selector).to_have_value("implement")
        selector.select_option("implement-patch-v1")
        page.locator('[data-focus="action:onSaveDraft"]').click()
        page.locator('[data-focus="action:onPublish"]').click()
        page.locator('[data-focus="action:onPublishConfirm"]').click()
        expect(page.locator('[data-review="publish"]')).to_have_count(0)
        assert templates.revisions("repair") == (1,)
        published = templates.load("repair", 1)
        do = next(node for node in published.nodes if node.node_id == "do")
        assert dict(do.payload()) == {**document["nodes"][1]["arguments"],
                                      "profile": "implement-patch-v1"}
        assert do.verifier_role_id == "role-checker"
    finally:
        context.close()
        srv.shutdown()
        thread.join(5)
        srv.server_close()
