"""Two same-named tasks through real Studio routes; late replies never switch tasks."""
from __future__ import annotations

import json

from playwright.sync_api import Browser, Page, expect

from browser_tests.run_picker import choose_run, reveal_runs
from browser_tests.task_picker import choose_task, create_task, selected_task, expect_selected_task
from browser_tests.test_studio_layout import (  # noqa: F401
    _model_form, configured_project, project,
)
from browser_tests.test_studio_lifecycle import _Project, _open, _settle
from conductor.command.run_store import RunStore
from conductor.command.task_store import TaskStore

def _fill_run(page: Page, run_id: str) -> None:
    page.locator("#navWorkflow").click()
    fold = page.locator('[data-fold="run"]')
    if fold.get_attribute("open") is None:
        fold.locator("summary").click()
    for role in page.locator('[data-focus^="role-"]').all():
        role.select_option("claude-code")
    page.locator('[data-focus="run-id"]').fill(run_id)
    page.locator('[data-focus="cycle-id"]').fill(f"cycle-{run_id}")
    page.locator('[data-focus="run-mode"]').select_option("confirm")


def _open_run(page: Page, run_id: str) -> None:
    _fill_run(page, run_id)
    with page.expect_response(lambda response: response.request.method == "POST"
                              and response.url.endswith("/command/runs")) as opened:
        page.locator('[data-focus="action:onOpenRun"]').click()
    assert opened.value.status == 201, opened.value.json()


def _pair(page: Page) -> tuple[str, str]:
    _model_form(page, "task-flow")
    task_a = selected_task(page)
    _open_run(page, "run-alpha")
    task_b = create_task(page)
    _open_run(page, "run-beta")
    return task_a, task_b


def test_two_same_named_tasks_freeze_separate_scopes_and_resume_after_reload(
        chromium: Browser, configured_project: _Project, tmp_path) -> None:
    page, window = _open(chromium, configured_project, double=True)
    try:
        task_a, task_b = _pair(page)
        store = RunStore(configured_project.root)
        for run_id, task_id in [("run-alpha", task_a), ("run-beta", task_b)]:
            assert store.read(run_id).config["task"] == {"id": task_id, "work_scope": task_id}
        assert TaskStore(configured_project.root).read(task_a).title == TaskStore(configured_project.root).read(task_b).title
        choose_task(page, task_a)
        page.locator("#navRuns").click()
        choose_run(page, "run-alpha")
        expect(page.locator("#bodyRuns")).to_contain_text("Task work scope")
        assert page.locator('[data-focus-key="run:run-beta"]').count() == 0
        assert f"task={task_a}" in page.url and "run=run-alpha" in page.url
        page.reload(wait_until="load")
        _settle(page)
        expect(page.locator('#bodyRuns .studio-runs__detail')).to_contain_text(task_a)
        assert selected_task(page) == task_a
        assert window.posted("/command/runs")[-1]["task_id"] == task_b
        page.set_viewport_size({"width": 1280, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth <= 1280")
        page.screenshot(path=str(tmp_path / "studio-tasks-1280.png"))
        page.emulate_media(color_scheme="dark")
        page.screenshot(path=str(tmp_path / "studio-tasks-1280-dark.png"))
        assert window.storage() == [0, 0]
        assert window.page_errors == []
    finally:
        page.context.close()


def test_a_new_run_requires_a_readable_selected_task(
        chromium: Browser, configured_project: _Project) -> None:
    page, window = _open(chromium, configured_project, double=True)
    try:
        _model_form(page, "task-flow")
        task_a = selected_task(page)
        choose_task(page, None)
        expect(page.locator('[data-focus="action:onOpenRun"]')).to_be_disabled()
        assert window.writes("/command/runs") == 0
        choose_task(page, task_a)
        expect(page.locator('[data-focus="action:onOpenRun"]')).to_be_enabled()
    finally:
        page.context.close()


def test_a_late_run_read_cannot_restore_the_previous_task_or_its_actions(
        chromium: Browser, configured_project: _Project) -> None:
    page, window = _open(chromium, configured_project, double=True)
    held = []
    try:
        task_a, task_b = _pair(page)
        url = configured_project.url + "command/runs/run-alpha"
        payload = page.request.get(url).json()
        page.route(url, lambda route: held.append(route))
        choose_task(page, task_a)
        page.locator("#navRuns").click()
        choose_run(page, "run-alpha")
        page.wait_for_function("() => document.querySelector('#bodyRuns').innerText.includes('read has not landed')")
        assert held
        choose_task(page, task_b)
        # Choosing a task opens its newest run by itself and redraws the picker;
        # the explicit choice below is made once that has landed.
        expect(page.locator('[data-focus-key="run:run-beta"]')).to_have_attribute("aria-pressed", "true")
        choose_run(page, "run-beta")
        held[0].fulfill(status=200, content_type="application/json", body=json.dumps(payload))
        expect(page.locator('#bodyRuns .studio-runs__detail')).to_contain_text(task_b)
        assert selected_task(page) == task_b
        assert "run-alpha" not in page.locator('#bodyRuns .studio-runs__detail').inner_text()
        assert window.writes("/proposals") == window.writes("/actions") == 0
    finally:
        page.unroute_all(behavior="ignoreErrors")
        page.context.close()


def test_a_mismatched_frozen_task_payload_refuses_the_whole_run(
        chromium: Browser, configured_project: _Project) -> None:
    page, window = _open(chromium, configured_project, double=True)
    try:
        task_a, task_b = _pair(page)
        choose_task(page, task_a)
        url = configured_project.url + "command/runs/run-alpha"
        payload = page.request.get(url).json()
        payload["task"]["work_scope"] = task_b
        page.route(url, lambda route: route.fulfill(status=200,
                   content_type="application/json", body=json.dumps(payload)))
        page.locator("#navRuns").click()
        choose_run(page, "run-alpha")
        expect(page.locator("#screenRuns")).to_have_attribute("data-state", "failed")
        assert page.locator('#bodyRuns [data-step]').count() == 0
        assert window.writes("/proposals") == window.writes("/actions") == 0
    finally:
        page.context.close()


def test_a_late_open_reply_never_selects_its_old_task_or_run(
        chromium: Browser, configured_project: _Project) -> None:
    page, window = _open(chromium, configured_project, double=True)
    held = []
    try:
        _model_form(page, "task-flow")
        task_a = selected_task(page)
        task_b = create_task(page)
        choose_task(page, task_a)
        _fill_run(page, "run-late")
        url = configured_project.url + "command/runs"

        def hold_post(route):
            if route.request.method == "POST":
                held.append((route, route.fetch()))
                page.evaluate("() => { window.__heldOpen = true; }")
            else:
                route.continue_()

        page.route(url, hold_post)
        page.locator('[data-focus="action:onOpenRun"]').click()
        page.wait_for_function("() => window.__heldOpen === true")
        assert held
        choose_task(page, task_b)
        page.locator("#navRuns").click()
        with page.expect_response(lambda response: response.request.method == "GET"
                                  and response.url == url):
            route, response = held[0]
            route.fulfill(response=response)
        assert selected_task(page) == task_b
        assert "run=run-late" not in page.url
        assert not any(method == "GET" and path.endswith("/runs/run-late")
                       for method, path, _ in window.rows)
        assert RunStore(configured_project.root).read("run-late").config["task"]["id"] == task_a
    finally:
        page.unroute_all(behavior="ignoreErrors")
        page.context.close()


def test_old_taskless_runs_remain_readable_but_are_marked_as_history(
        chromium: Browser, project: _Project) -> None:
    page, window = _open(chromium, project, double=True)
    try:
        page.locator("#navRuns").click()
        reveal_runs(page)
        page.locator('.studio-run').first.click()
        expect(page.locator("#bodyRuns")).to_contain_text("No task — historical run")
        assert window.writes("/command/runs") == 0
    finally:
        page.context.close()


def test_a_generated_task_identity_survives_unknown_reply_and_background_reads(
        chromium: Browser, project: _Project) -> None:
    page, window = _open(chromium, project, double=True)
    attempts = []
    try:
        url = project.url + "command/tasks"
        def lose_first_reply(route):
            if route.request.method != "POST":
                route.continue_()
                return
            attempts.append(json.loads(route.request.post_data))
            if len(attempts) == 1:
                assert route.fetch().status == 201
                route.abort("failed")
            else:
                route.continue_()
        page.route(url, lose_first_reply)
        page.locator('[data-focus="task-new"]').click()
        assert page.locator('#studioTasks input').count() == 1
        name = page.locator('[data-focus="task-title"]')
        name.fill("Keep this name")
        page.get_by_role("button", name="Create task", exact=True).click()
        expect(page.locator("#studioStatus")).to_contain_text("Outcome unknown")
        page.evaluate("() => window.__stream.emit(JSON.stringify({kind:'state'}))")
        expect(name).to_have_value("Keep this name")
        with page.expect_response(lambda response: response.request.method == "POST"
                                  and response.url == url) as retry:
            page.get_by_role("button", name="Create task", exact=True).click()
        assert retry.value.status == 200
        assert attempts[0] == attempts[1]
        assert len(TaskStore(project.root).tasks()) == 1
        expect_selected_task(page, attempts[0]["task_id"])
        assert window.page_errors == []
    finally:
        page.context.close()


def test_editing_an_accepted_task_with_a_lost_reply_starts_a_new_identity(
        chromium: Browser, project: _Project) -> None:
    page, window = _open(chromium, project, double=True)
    attempts = []
    try:
        url = project.url + "command/tasks"

        def lose_first(route):
            if route.request.method != "POST":
                route.continue_()
                return
            attempts.append(json.loads(route.request.post_data))
            if len(attempts) == 1:
                assert route.fetch().status == 201
                route.abort("failed")
            else:
                route.continue_()

        page.route(url, lose_first)
        page.locator('[data-focus="task-new"]').click()
        name = page.locator('[data-focus="task-title"]')
        name.fill("First accepted task")
        page.get_by_role("button", name="Create task", exact=True).click()
        expect(page.locator("#studioStatus")).to_contain_text("Outcome unknown")
        first = attempts[0]
        assert TaskStore(project.root).read(first["task_id"]).title == first["title"]
        name.fill("The next edited task")
        with page.expect_response(lambda response: response.request.method == "POST"
                                  and response.url == url) as second:
            page.get_by_role("button", name="Create task", exact=True).click()
        assert second.value.status == 201, second.value.json()
        next_id = second.value.json()["task"]["task_id"]
        assert next_id != first["task_id"]
        expect_selected_task(page, next_id)
        assert TaskStore(project.root).read(next_id).title == "The next edited task"
        assert TaskStore(project.root).read(first["task_id"]).title == first["title"]
        assert len(TaskStore(project.root).tasks()) == 2
        expect(page.locator(f'[data-task-outcome="{first["task_id"]}"]')).to_contain_text(first["title"])
        expect(page.locator("#studioStatus")).not_to_contain_text("Writing")
        assert window.page_errors == []
    finally:
        page.context.close()


def test_a_late_task_reply_keeps_the_next_draft_and_the_current_selection(
        chromium: Browser, project: _Project) -> None:
    page, window = _open(chromium, project, double=True)
    held = []
    try:
        selected = create_task(page, "Keep this selection")
        url = project.url + "command/tasks"

        def hold_first(route):
            if route.request.method == "POST" and not held:
                response = route.fetch()
                assert response.status == 201, response.json()
                held.append((route, response))
                page.evaluate("() => { window.__heldTask = true; }")
            else:
                route.continue_()

        page.route(url, hold_first)
        page.locator('[data-focus="task-new"]').click()
        name = page.locator('[data-focus="task-title"]')
        name.fill("Accepted while editing")
        page.get_by_role("button", name="Create task", exact=True).click()
        page.wait_for_function("() => window.__heldTask === true")
        first_id = held[0][1].json()["task"]["task_id"]
        assert TaskStore(project.root).read(first_id).title == "Accepted while editing"
        name.fill("A separate next draft")
        with page.expect_response(lambda response: response.request.method == "GET"
                                  and response.url == url):
            held[0][0].fulfill(response=held[0][1])
        expect(name).to_have_value("A separate next draft")
        expect_selected_task(page, selected)
        expect(page.locator(f'[data-task-outcome="{first_id}"]')).to_contain_text("Accepted while editing")
        with page.expect_response(lambda response: response.request.method == "POST"
                                  and response.url == url) as next_reply:
            page.get_by_role("button", name="Create task", exact=True).click()
        assert next_reply.value.status == 201, next_reply.value.json()
        next_id = next_reply.value.json()["task"]["task_id"]
        assert next_id != first_id
        expect_selected_task(page, next_id)
        assert TaskStore(project.root).read(next_id).title == "A separate next draft"
        assert TaskStore(project.root).read(first_id).title == "Accepted while editing"
        assert len(TaskStore(project.root).tasks()) == 3
        assert window.page_errors == []
    finally:
        page.unroute_all(behavior="ignoreErrors")
        page.context.close()
