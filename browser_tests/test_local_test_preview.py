"""The served permission preview shows the pinned runtime and test order before a grant."""
import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.desk_wizard_bench import bench, desk_url  # noqa: F401
from browser_tests import desk_wizard_queue as queue_door
from browser_tests.test_desk_wizard_launch import STANDARD, to_card
from browser_tests.test_studio_rendered import studio_url  # noqa: F401
from tests.desk_wizard_node import fixture
from conductor.command.adapters import AdapterRegistry
from conductor.command.http_api import CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.policy_view import automation_view
from tests.relay_roads import CODEX, Site
from tests.test_command_http_api import PORT, TOKEN, get_headers, ids
from tests.test_patch_do_policy import run_state
from tests.test_policy_runtime import NOW


def reviewed_payload(root):
    plan = {"runner": "python-unittest-v1", "start": "checks",
            "pattern": "test_counter_*.py", "timeout_seconds": 17,
            "toolchain": {"install": str(root / "harnesses" / "python" / "3.12.14"),
                          "entry": "python.exe", "runtime_digest": "sha256:" + "9" * 64}}
    site = Site(root, CODEX)
    with site.owned():
        f = run_state(site.root, site.adapter, item="work-001", instruction=(
            "Review the counter.\n\nconduct.test-plan.v1\n" + json.dumps(plan)))
        api = CommandApi(f.store, AdapterRegistry([site.adapter]),
            session=CommandSession(PORT, TOKEN), budget=f.policy.budget,
            clock=lambda: NOW, ids=ids(), publish_run=lambda _run: None)
        detail = api.handle("GET", "/command/runs/run", get_headers())
        assert detail.status == 200
        preview = f.policy.preview("run", {"node_limits": [
            {"node_id": "do", "timeout_seconds": 30, "max_attempts": 1}],
            "max_actions": 1, "max_action_seconds": 60, "max_total_task_seconds": 60,
            "duration_seconds": 300})
        return {"read": detail.payload, "initial": automation_view(f.policy, "run"),
                "preview": preview, "plan": plan}


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_permission_preview_discloses_test_runtime_and_order(chromium, studio_url, tmp_path, lang):
    payload = reviewed_payload(tmp_path / "wire")
    payload["lang"] = lang
    context = chromium.new_context(viewport={"width": 375, "height": 850})
    page = context.new_page()
    writes = []
    page.on("request", lambda req: writes.append(req.url) if req.method == "POST" else None)
    try:
        page.goto(studio_url + "#lang=" + lang)
        page.evaluate("""async p => {
          const {mountAutomation} = await import("/panel/studio-automation.js");
          const {projectAutomationPreview} = await import("/panel/studio-automation-model.js");
          const detail = p.read, preview = projectAutomationPreview(p.preview, detail);
          if (!preview) throw new Error("reviewed test preview refused");
          const host = document.createElement("main");
          host.id = "testPreviewWitness"; document.body.prepend(host);
          const state = {locale:p.lang, connection:"open", decisions:{phase:"ready",list:[]},
            runs:{detail, selectedId:"run"}};
          const draft = {...p.preview.terms, custom:true, actor:"local-owner"};
          for (const key of ["max_actions","max_action_seconds",
            "max_total_task_seconds","duration_seconds"]) draft[key] = String(draft[key]);
          const held = {runId:"run", phase:"ready", pending:false, request:null, draft,
            view:{...p.initial, owner_present:true}, preview};
          const actions = Object.fromEntries(["preview","edit","refresh","authorize"]
            .map(key => [key, () => { throw new Error("unexpected action " + key); }]));
          mountAutomation(host, state, held, actions, () => {});
        }""", payload)
        review = page.locator("#testPreviewWitness [data-automation-preview]")
        expect(review).to_be_visible()
        sentence = ("After applying the patch, before the checker: python-unittest-v1, "
                    "checks/test_counter_*.py, up to 17s." if lang == "en" else
                    "После патча, до проверяющего: python-unittest-v1, "
                    "checks/test_counter_*.py, до 17 с.")
        expect(review).to_contain_text(sentence)
        expect(review).to_contain_text("checker-model")
        pin = review.locator("details").filter(has_text=(
            "Pinned test runtime" if lang == "en" else "Закреплённая среда тестов"))
        pin.locator("summary").click()
        expected_pin = json.dumps(payload["plan"]["toolchain"], indent=2, ensure_ascii=False)
        expect(pin.locator("pre")).to_have_text(expected_pin)
        expect(review.locator('[data-focus="automation:authorize"]')).to_be_enabled()
        assert writes == []
        if lang == "en" and os.environ.get("DO_TEST_PROTOCOL_KIT"):
            output = Path(os.environ["DO_TEST_PROTOCOL_KIT"])
            output.mkdir(parents=True, exist_ok=True)
            review.screenshot(path=str(output / "preview-runtime.png"))
    finally:
        close_context(context)


def test_desk_card_discloses_bound_tests_before_launch(bench, monkeypatch):
    preview = json.loads(json.dumps(STANDARD))
    plan = {"runner": "python-unittest-v1", "start": "checks", "pattern": "test_*.py",
            "timeout_seconds": 17, "toolchain": {
                "install": "C:\\trusted\\harnesses\\python\\3.12.14", "entry": "python.exe",
                "runtime_digest": "sha256:" + "9" * 64}}
    preview.update(patch_steps=["do"], test_steps=[{"node_id": "do", "policy": plan,
        "policy_digest": "sha256:" + "8" * 64, "toolpin_digest": "sha256:" + "7" * 64}])
    detail = fixture("wizard", "run_detail.json")
    detail["run"]["config_digest"] = preview["terms"]["config_digest"]
    detail["graph"]["definition_digest"] = preview["terms"]["graph_digest"]
    node = next(row for row in detail["graph"]["definition"]["nodes"] if row["node_id"] == "do")
    node.update(capability="dispatch", arguments={"profile": "implement-patch-v1"})
    binding = preview["terms"]["instruction_bindings"][0]
    detail["records"] = [{"record_type": "artifact", "record": {
        "artifact_id": binding["artifact_id"], "source_action_id": None,
        "content": "Do.\n\nconduct.test-plan.v1\n" + json.dumps(plan)}}]
    monkeypatch.setattr(queue_door, "fixture", lambda *parts:
                        detail if parts[-1] == "run_detail.json" else fixture(*parts))
    to_card(bench, "en", preview=preview)
    step = bench.page.locator('[data-plan-step="do"]')
    expect(step).to_contain_text("After applying the patch, before the checker: python-unittest-v1")
    expect(step).to_contain_text("checks/test_*.py, up to 17s.")
    step.get_by_text("Pinned test runtime", exact=True).click()
    expect(step.locator("pre")).to_have_text(json.dumps(plan["toolchain"], indent=2))
    assert bench.bodies("launch_authorize") == bench.bodies("launch_enqueue") == []
