"""The installed Studio's preview, grant and result are one offline application journey."""
import errno
import os
import subprocess
from threading import Thread

import pytest
from playwright.sync_api import expect

from conductor import demo, ownership, ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.seed_record import write_seed
from conductor.command.seed_stage import move_staged, stage_empty
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from tests import _fakeexe
from tests.fake_process_fixtures import registered_fake_processes
from tests.relay_roads import CODEX, Site
from tests.test_patch_do_policy import ACTUAL, PATCH, run_state, work_and_calls
from tests.test_policy_runtime import NOW, PD


def test_the_offline_desk_rejects_a_changed_fixture_before_the_version_probe(tmp_path):
    executable = _fakeexe.build(tmp_path / "fixture", "codex", "_fakecodex")
    assert executable is not None
    executable.write_bytes(b"not an executable")
    if os.name == "nt":
        with pytest.raises(ValueError, match="registered fake changed or disappeared"):
            subprocess.run([str(executable), "--version"], check=False, capture_output=True)
        return
    # POSIX runs the fixture directly. A damaged script must fail at exec, before the probe.
    with pytest.raises(OSError) as refusal:
        subprocess.run([str(executable), "--version"], check=False, capture_output=True)
    assert refusal.value.errno == errno.ENOEXEC


@pytest.mark.parametrize("seeded,gated", [(False, False), (True, False), (True, True)])
def test_review_one_patch_and_see_the_independent_result(chromium, tmp_path, seeded, gated):
    root = demo.materialize(tmp_path / "root")
    ownership_transition.activate(root, legacy_writers_stopped=True)
    site = Site(tmp_path, CODEX, root=root)
    with site.owned():
        item = "work-001" if seeded else "item"
        f = run_state(site.root, site.adapter, item=item, with_gates=gated)
        TaskStore(site.root).create_task(TaskRecord("one", "Исправить счётчик", "one", NOW))
        if seeded:
            seed = stage_empty(root, task_id="one", work_scope="one", work_item_id=item,
                               staged_at=NOW)
            write_seed(root, seed)
            move_staged(root, seed)
        work, calls = work_and_calls(site, PATCH, item=item)
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
        # Wait for the one action within the bound this test just reviewed and granted.
        action_ms = 1000 * preview["terms"]["max_action_seconds"]
        expect(panel.locator("[data-automation-state]")).to_have_attribute(
            "data-automation-state", "waiting" if gated else "complete", timeout=action_ms)
        records = f.store.read("run").records
        assert calls == ["prepare", "apply", "check"]
        assert len([r for r in records if r.kind == "action_request"]) == 1
        assert [r.value.outcome for r in records if r.kind == "action_result"] == ["succeeded"]
        assert [r.value.verifier_instance_id for r in records
                if r.kind == "evidence"] == ["checker"]
        assert (work / "count.py").read_bytes() == ACTUAL
        if seeded:
            (work / "count.py").unlink()
            (work / "unreviewed.py").write_bytes(b"later edit")
            packet = page.request.get(f"{base}/command/runs/run").json()
            assert packet["checked_changes"]["files"] == [
                {"path": "count.py", "state": "added"}, {"path": "test_count.py", "state": "added"}]
        writes = []
        page.on("request", lambda req: writes.append(req.method) if req.method == "POST" else None)
        if gated:
            page.set_viewport_size({"width": 375, "height": 820})
            page.locator('#studioPrimary [data-run-action="decide"]').click()
            decisions = page.locator("#bodyDecisions")
            decisions.locator('[data-focus-key="decision:run/accept"]').click()
            checked = decisions.locator("[data-patch-result]")
            expect(checked).to_contain_text("checker")
            expect(checked.locator("[data-checked-path]")).to_have_count(2)
            expect(checked.locator("[data-checked-path]").last).to_be_in_viewport()
            expect(checked).to_contain_text("count.py")
            expect(checked).not_to_contain_text("unreviewed.py")
            expect(decisions.locator('[data-focus-key="field:actor"]')).to_be_visible()
            decisions.locator('[data-focus-key="decision:run/next"]').click()
            expect(decisions.locator("[data-patch-result]")).to_have_count(0)
            assert not writes
            decisions.locator('[data-focus-key="decision:run/accept"]').click()
            decisions.locator('[data-focus-key="field:actor"]').fill("offline-owner")
            decisions.get_by_role("button", name="Записать решение", exact=True).click()
            expect(decisions.get_by_text("offline-owner", exact=True).first).to_be_visible()
            receipts = [r.value for r in f.store.read("run").records if r.kind == "decision"]
            assert [(r.gate_id, r.action, r.actor) for r in receipts] == [
                ("accept", "approve", "offline-owner")]
            assert writes == ["POST"]
            return
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
            expect(listing).to_contain_text("work/_tasks/one/" + item)
            if seeded:
                expect(listing.locator("[data-checked-path]")).to_have_count(2)
                expect(listing).to_contain_text("test_count.py")
            page.goto(f"{base}/panel/desk.html#task=one&run=run&lang={lang}")
            desk_result = page.locator("[data-deck-run='run'] [data-patch-result]").first
            expect(desk_result).to_contain_text("work/_tasks/one/" + item)
            if seeded:
                expect(desk_result.locator("[data-checked-path]")).to_have_count(2)
            expect(desk_result).to_contain_text("checker")
        if seeded:
            digest = packet["checked_changes"]["digest"].removeprefix("sha256:")
            manifest = ownership.data_root(root) / "accept/run/snapshots" / (digest + ".json")
            original = manifest.read_bytes()
            try:
                manifest.write_bytes(b"[]")
                response = page.request.get(f"{base}/command/runs/run")
                assert response.ok
                assert response.json()["checked_changes"] == {
                    **packet["checked_changes"], "total": None, "files": []}
                page.reload()
                shown = page.locator("[data-deck-run='run'] [data-patch-result]").first
                expect(shown).to_contain_text("The checked file list is unavailable.")
            finally:
                manifest.write_bytes(original)
        else:
            assert "checked_changes" not in page.request.get(f"{base}/command/runs/run").json()
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
        page.goto(f"http://127.0.0.1:{srv.server_port}/panel/studio.html#lang=ru")
        page.locator("#navWorkflow").click()
        page.locator("#workflowToolbar select[name='workflow']").select_option("repair")
        page.locator('[data-node-id="do"]').click()
        selector = page.get_by_label("Как Do изменяет файлы")
        expect(selector).to_have_value("implement")
        selector.select_option("implement-patch-v1")
        page.locator('[data-focus="action:onSaveDraft"]').click()
        expect(page.locator('[data-save="saved"]')).to_be_visible()
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
