"""Desk step and document controls against the real project command server."""
from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import replace

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from browser_tests.desk_hold import Hold, land_read, read_again
from conductor import server
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from tests.test_command_execution_coordinator import ids, provider_registry
from tests.test_command_run_store import a_run
from tests.test_store import good_lane, write_project
from tests.alpha3_graph_artifacts import dalio_definition


@pytest.fixture
def live_desk(tmp_path) -> Iterator[tuple[str, object, object]]:
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    TaskStore(root).create_task(TaskRecord("task-fix", "Fix lost text", "work-001",
                                           "2026-09-30T12:00:00Z"))
    config = {"cycle": {"id": "default-orbit"},
              "task": {"id": "task-fix", "work_scope": "work-001"},
              "instances": [{"id": "claude-dev", "adapter": "claude-code"}]}
    store = RunStore(root)
    store.create_run(a_run(run_id="run-fix-old", mode="confirm",
                           config_digest=snapshot_digest(config)), config)
    plan = dalio_definition(run_id="run-fix-old")
    store.append(replace(plan, nodes=tuple(replace(node,
        arguments={**node.arguments, "work_scope": "work-001"})
        if node.kind == "task" else node for node in plan.nodes)))
    harness = tmp_path / "harness"
    harness.mkdir()
    mint = ids()
    httpd = server.build(root, 0, registry=provider_registry(harness, mint), ids=mint)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}/panel/desk.html", root, httpd
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()


def _the_control_follows_a_re_read(page: Page, httpd, controls: Hold, control: Locator) -> None:
    """The desk reads the run again (a stream asks for it after the connection opens and after
    every write); held, the scene stands as stale. A write control is off until the read lands
    and on once it has, so the claim that it is on waits for the read. The test makes the window
    itself and does not hope the stream makes it."""
    read_again(page, controls, httpd.clients.publish_state)
    expect(control).to_be_disabled()
    land_read(page, controls)
    expect(control).to_be_enabled()


def test_document_and_manual_step_are_written_for_the_selected_task_run(
        chromium: Browser, live_desk):
    url, root, httpd = live_desk
    context = chromium.new_context(viewport={"width": 1400, "height": 1000})
    page = context.new_page()
    controls = Hold(page, "**/command/runs/run-fix-old/controls")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{url}#task=task-fix&run=run-fix-old&panel=run&lang=en")
    panel = page.locator("#deskRun")
    try:
        expect(panel.locator('[data-subject="run:run-fix-old"]')).to_be_visible()
        page.wait_for_selector('#deskShell[data-connection="open"]')
        form = panel.locator('[data-step="document"]')
        expect(form).to_be_visible()
        ref = "artifact-brief"
        expect(form.locator('[name="artifact_ref"] option[value="artifact-brief"]')).to_have_count(1)
        form.locator('[name="artifact_ref"]').select_option(ref)
        form.locator('[name="content"]').fill("# Desk input\n\nApproved source.")
        form.locator('[name="content"]').press("Tab")
        _the_control_follows_a_re_read(
            page, httpd, controls, form.locator('[data-focus-key="document:publish"]'))
        with page.expect_response(lambda response: response.url.endswith("/artifacts")) as sent:
            form.locator('[data-focus-key="document:publish"]').click()
        assert sent.value.status == 201, sent.value.json()
        page.wait_for_function("() => document.querySelector('#deskRun [data-step=\"document\"] "
                               "[name=\"content\"]')?.value === ''")
        assert any(row.kind == "artifact" and row.value.artifact_ref == ref
                   for row in RunStore(root).read("run-fix-old").records)

        proposal = panel.locator('[data-step^="propose:"]').first
        expect(proposal).to_be_visible()
        proposal.locator('[name="proposed_by"]').click()
        page.keyboard.type("desk-owner")
        page.keyboard.press("Tab")
        proposal.locator('[name="rationale"]').click()
        page.keyboard.type("Proceed from the saved plan.")
        page.keyboard.press("Tab")
        _the_control_follows_a_re_read(
            page, httpd, controls, proposal.locator('button[type="submit"]'))
        with page.expect_response(lambda response: response.url.endswith("/proposals")) as sent:
            proposal.locator('button[type="submit"]').click()
        assert sent.value.status == 201, sent.value.json()
        assert any(row.kind == "action_proposal"
                   for row in RunStore(root).read("run-fix-old").records)
        confirmation = panel.locator('[data-step="confirm:goal"]')
        expect(confirmation).to_be_visible()
        confirmation.locator('[name="confirmed_by"]').click()
        page.keyboard.type("desk-owner")
        page.keyboard.press("Tab")
        _the_control_follows_a_re_read(
            page, httpd, controls, confirmation.locator('button[type="submit"]'))
        with page.expect_response(lambda response: response.url.endswith("/actions")) as sent:
            confirmation.locator('button[type="submit"]').click()
        assert sent.value.status == 201, sent.value.json()
        assert any(row.kind == "action_request"
                   for row in RunStore(root).read("run-fix-old").records)
        expect(panel.locator('[data-subject="run:run-fix-old"]')).to_be_visible()
        assert errors == []
    finally:
        context.close()
