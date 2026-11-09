"""The actual Runs screen binds its evidence conversation to the selected journal request."""
from threading import Thread
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from conductor import demo, ownership, ownership_transition, server
from conductor.command.adapters import AdapterRegistry
from conductor.command.contracts import ActionProposal, ActionRequest, RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.project_claim import Launch
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from tests.test_policy_runtime import NOW


@pytest.fixture()
def atlas_url(tmp_path):
    root = demo.materialize(tmp_path / "root")
    ownership_transition.activate(root, legacy_writers_stopped=True)
    with ownership.acquire_owner(root):
        TaskStore(root).create_task(TaskRecord("one", "Repair", "one", NOW))
        for run_id in ("first", "second"):
            create_run(root, run_id)
    http = server.build(root, 0, registry=AdapterRegistry([]), launch=Launch(mode="view"))
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}"
    finally:
        http.shutdown()
        thread.join(5)
        http.server_close()


def create_run(root, run_id):
    store = RunStore(root)
    config = {"cycle": {"id": "repair"},
              "task": {"id": "one", "work_scope": "one"},
              "instances": [{"id": name, "adapter": "codex", "model": "model"}
                            for name in ("maker", "checker")]}
    store.create_run(RunEnvelope(run_id, "repair", NOW, snapshot_digest(config), mode="confirm"),
                     config)
    args = {"work_item_id": "item", "instruction_ref": "brief", "profile": "implement-patch-v1",
            "artifact_refs": [], "output_limit_profile": "normal", "work_scope": "one"}
    node = GraphNode("repair-counter", "task", "Do", instance_id="maker", capability="dispatch",
                     arguments=args, timeout_seconds=30, attempt_bound=2,
                     verifier_instance_id="checker")
    gate = GraphNode("authorize", "gate", "Authorize", gate_id="authorize")
    store.append(GraphDefinition("graph-" + run_id, run_id, NOW, nodes=(gate, node),
                                 edges=(GraphEdge(gate.node_id, node.node_id),)))
    for n in (1, 2):
        action = f"action-{run_id}-{n}"
        proposal = ActionProposal("proposal-" + action, run_id, "attempt-" + action, "maker",
                                  "dispatch", args, ("src",), "tester", NOW, 30, "repair",
                                  snapshot_digest(config), node_id=node.node_id)
        store.append(proposal)
        store.append(ActionRequest(action, run_id, "attempt-" + action, "maker", "dispatch",
                                   args, ("src",), "tester", NOW,
                                   "dispatch-" + proposal.proposal_id,
                                   30, proposal.preview_digest, "confirm", node_id=node.node_id))


def evidence(action, run="first"):
    return {"run_id": run, "node_id": "repair-counter", "action_id": action,
            "attempt_id": "attempt-" + action, "outcome": "succeeded", "files_total": 1,
            "manifest_digest": "sha256:" + "1"*64,
            "verdict": {"status": "verified", "adapter_id": "codex", "instance_id": "checker"},
            "files": [{"path": action + ".py", "state": "modified", "diff_status": "available",
                       "lines": ["@@ -1 +1 @@", "-old", "+new-" + action]}],
            "tests": {"status": "recorded", "source": "external",
                      "summary": {"total": 3, "errors": 0, "failures": 0, "skipped": 1},
                      "cases": [{"name": "test_" + action.replace("-", "_"),
                                 "path": "checks.py", "line": 4,
                                 "assertion": "assert result == 4"},
                                {"name": "test_without_assertion", "path": "checks.py",
                                 "line": 7, "assertion": None}]}}


@pytest.mark.parametrize(("lang", "width"), [("ru", 375), ("en", 1280)])
def test_selects_one_actual_request_and_keeps_the_atlas_conversation(
        chromium, atlas_url, lang, width):
    context = chromium.new_context(viewport={"width": width, "height": 850})
    page = context.new_page()
    writes, errors, held = [], [], []
    page.on("request", lambda req: writes.append(req.url) if req.method == "POST" else None)
    page.on("pageerror", lambda err: errors.append(str(err)))

    def route_detail(route):
        action = urlsplit(route.request.url).path.rsplit("/", 1)[-1]
        if action == "action-first-2":
            held.append(route)
        else:
            route.fulfill(json=evidence(action))

    page.route("**/steps/repair-counter/actions/*", route_detail)
    try:
        page.goto(atlas_url + "/#screen=runs&task=one&run=first&lang=" + lang)
        atlas = page.locator("#studioAtlas")
        step = atlas.locator('[data-atlas-step="repair-counter"]')
        expect(step).to_be_visible()
        step.focus()
        step.press("Enter")
        pick = atlas.locator("[data-atlas-attempt]")
        expect(pick).to_have_value("action-first-2")
        pick.select_option("action-first-1")
        inspector = atlas.locator("[data-atlas-inspector]")
        expect(inspector).to_contain_text("+new-action-first-1")
        if width >= 1200:
            panel_box = inspector.bounding_box()
            chat_box = atlas.locator(".atlas-chat").bounding_box()
            main_box = page.locator("#studioMain").bounding_box()
            assert panel_box["width"] >= 300
            assert panel_box["x"] >= chat_box["x"] + chat_box["width"]
            right_gap = main_box["x"] + main_box["width"] - panel_box["x"] - panel_box["width"]
            assert 0 <= right_gap < 60
        assert held
        held.pop().fulfill(json=evidence("action-first-2"))
        field = atlas.locator("[data-atlas-field]")
        if width == 375:
            atlas.locator("[data-atlas-close]").click()
            expect(step).to_be_focused()
        field.fill("Какой тест подтверждает исправление?" if lang == "ru" else "Which test?")
        field.press("Enter")
        expect(inspector).to_contain_text("assert result == 4")
        inspector.get_by_role("button", name="test_without_assertion").click()
        expect(inspector.locator(".atlas-assert")).to_have_count(0)
        expect(inspector).not_to_contain_text("action-first-2.py")
        expect(atlas.locator("[role=log]")).to_contain_text("action-first-1")
        atlas.locator('[data-atlas-tab="verdict"]').click()
        expect(inspector).to_contain_text("checker")
        if width >= 1200:
            field.focus()
            page.set_viewport_size({"width": 375, "height": 850})
            expect(inspector.get_by_role("heading", name="Do", exact=True)).to_be_focused()
            expect(atlas.locator(".atlas-chat")).to_have_js_property("inert", True)
            page.set_viewport_size({"width": width, "height": 850})
            expect(atlas.locator(".atlas-chat")).to_have_js_property("inert", False)
            expect(pick).to_have_value("action-first-1")
            field.focus()
            expect(field).to_be_focused()
        assert not writes and not errors, (writes, errors)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        close_context(context)


def test_wrong_echo_is_refused_and_drafts_follow_runs(chromium, atlas_url):
    context = chromium.new_context(viewport={"width": 1280, "height": 850})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    wrong = True

    def respond(route):
        action = urlsplit(route.request.url).path.rsplit("/", 1)[-1]
        run = action.split("-")[1]
        row = evidence(action, run)
        if wrong and run == "first":
            row["attempt_id"] = "attempt-from-another-run"
        else:
            row.update(files_total=None, files=[], manifest_digest=None, verdict=None)
            row["tests"] = {"status": "not_recorded", "cases": [], "source": None, "summary": None}
        route.fulfill(json=row)

    def pick_run(run):
        page.locator(".studio-run-picker:not([open]) summary").click()
        page.locator('[data-focus-key="run:' + run + '"]').click()

    try:
        page.route("**/steps/repair-counter/actions/*", respond)
        page.goto(atlas_url + "/#screen=runs&task=one&run=first&lang=en")
        atlas = page.locator("#studioAtlas")
        step = atlas.locator("[data-atlas-step=repair-counter]")
        panel = atlas.locator("[data-atlas-inspector]")
        field = atlas.locator("[data-atlas-field]")
        step.click()
        expect(panel).to_contain_text("could not be confirmed")
        expect(panel).not_to_contain_text("new-action-first")
        wrong = False
        panel.get_by_role("button", name="Refresh evidence").click()
        expect(panel).to_contain_text("no confirmed file snapshot")
        field.fill("first run private draft")
        pick_run("second")
        expect(field).to_have_value("")
        expect(panel).to_be_hidden()
        step.click()
        expect(panel.locator("[data-atlas-attempt]")).to_have_value("action-second-2")
        field.fill("Tests?")
        field.press("Enter")
        expect(atlas.locator("[role=log]")).to_contain_text("No test report")
        expect(panel).to_contain_text("No test definitions")
        panel.locator("[data-atlas-tab=verdict]").click()
        expect(panel).to_contain_text("No independent verdict")
        pick_run("first")
        expect(field).to_have_value("first run private draft")
        expect(panel.locator("[data-atlas-attempt]")).to_have_value("action-first-2")
        expect(atlas.locator("[role=log]")).not_to_contain_text("action-second-2")
        assert not errors
    finally:
        close_context(context)
