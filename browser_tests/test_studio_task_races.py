"""Task writes keep their subject when the person types or navigates meanwhile.

POSTs reach the real server before their replies are held. The later browser
state is therefore measured against a durable operation, not an invented 200.
No harness is executed by these task/run creation requests.
"""
from __future__ import annotations

import re

import pytest

from playwright.sync_api import Browser, Page, expect

from browser_tests.run_picker import choose_run
from browser_tests.task_picker import create_task, selected_task, expect_selected_task
from browser_tests.test_studio_layout import (  # noqa: F401
    _model_form, configured_project, project,
)
from browser_tests.test_studio_lifecycle import _Project, _open
from browser_tests.test_studio_tasks import _fill_run, _open_run
from conductor.command.run_store import RunStore
from conductor.command.task_store import TaskStore


def _task_title(page: Page):
    disclosure = page.locator("#studioTasks details").first
    if disclosure.get_attribute("open") is None:
        disclosure.locator("summary").click()
    return page.locator('[data-focus="task-title"]')


def _hold_open(page: Page, project: _Project):
    held = []
    url = project.url + "command/runs"

    def hold(route):
        if route.request.method == "POST":
            response = route.fetch()
            assert response.status == 201, response.json()
            held.append((route, response))
            page.evaluate("() => { window.__raceOpenReachedServer = true; }")
        else:
            route.continue_()

    page.route(url, hold)
    page.locator('[data-focus="action:onOpenRun"]').click()
    page.wait_for_function("() => window.__raceOpenReachedServer === true")
    assert len(held) == 1
    return url, held[0]


def _release_open(page: Page, url: str, held) -> None:
    # The list GET starts in the accepted callback. Waiting for its response
    # proves that callback has run before any assertion about what it cleared.
    with page.expect_response(lambda response: response.request.method == "GET"
                              and response.url == url):
        route, response = held
        route.fulfill(response=response)


def test_enter_creation_clears_visible_text_and_the_next_task_gets_a_new_identity(
        chromium: Browser, project: _Project) -> None:
    page, window = _open(chromium, project, double=True)
    try:
        title = _task_title(page)
        title.fill("Created with Enter")
        with page.expect_response(lambda response: response.request.method == "POST"
                                  and response.url.endswith("/command/tasks")) as created:
            title.press("Enter")
        assert created.value.status == 201, created.value.json()
        first_id = created.value.json()["task"]["task_id"]
        expect_selected_task(page, first_id)
        expect(page.get_by_role("button", name="Create task", exact=True)).to_be_enabled()
        assert TaskStore(project.root).read(first_id).title == "Created with Enter"
        # This input was focused when task-spent rendered. Focus restoration
        # must not put the spent text back over an empty reducer draft.
        expect(title).to_have_value("")
        second_id = create_task(page, "The next task")
        assert second_id != first_id
        assert TaskStore(project.root).read(second_id).title == "The next task"
        assert len(TaskStore(project.root).tasks()) == 2
        assert window.writes("/command/tasks") == 2
        assert window.page_errors == []
    finally:
        page.context.close()


def test_a_created_and_read_back_task_finishes_its_writing_status(
        chromium: Browser, project: _Project) -> None:
    page, window = _open(chromium, project, double=True)
    try:
        task_id = create_task(page, "Read back this task")
        assert TaskStore(project.root).read(task_id).title == "Read back this task"
        expect_selected_task(page, task_id)
        expect(page.locator("#studioStatus")).not_to_contain_text("Writing")
        # A later successful read may not resurrect the stale progress claim.
        with page.expect_response(lambda response: response.request.method == "GET"
                                  and response.url.endswith("/command/tasks")):
            page.get_by_role("button", name="Read tasks again", exact=True).click()
        expect(page.locator("#studioStatus")).not_to_contain_text("Writing")
        assert window.writes("/command/tasks") == 1
        assert window.page_errors == []
    finally:
        page.context.close()


def test_a_late_open_reply_keeps_the_run_chosen_within_the_same_task(
        chromium: Browser, configured_project: _Project) -> None:
    page, window = _open(chromium, configured_project, double=True)
    try:
        _model_form(page, "same-task-navigation")
        task_id = selected_task(page)
        _open_run(page, "run-already-open")
        _open_run(page, "run-other-existing")
        _fill_run(page, "run-late-open")
        url, held = _hold_open(page, configured_project)
        assert RunStore(configured_project.root).read("run-late-open").config["task"]["id"] == task_id
        page.locator("#navRuns").click()
        choose_run(page, "run-already-open")
        expect(page.locator("#bodyRuns .studio-runs__detail")).to_contain_text("run-already-open")
        assert "run=run-already-open" in page.url
        _release_open(page, url, held)
        expect(page).to_have_url(re.compile(r"(?:[&#])run=run-already-open(?:&|$)"))
        expect(page.locator("#bodyRuns .studio-runs__detail")).to_contain_text("run-already-open")
        assert selected_task(page) == task_id
        assert not any(method == "GET" and path.endswith("/runs/run-late-open")
                       for method, path, _ in window.rows)
        assert window.writes("/proposals") == window.writes("/actions") == 0
        assert window.page_errors == []
    finally:
        page.unroute_all(behavior="ignoreErrors")
        page.context.close()


def test_a_late_open_reply_keeps_the_next_opening_draft(
        chromium: Browser, configured_project: _Project) -> None:
    page, window = _open(chromium, configured_project, double=True)
    try:
        _model_form(page, "same-task-draft")
        _fill_run(page, "run-first-opening")
        url, held = _hold_open(page, configured_project)
        page.locator('[data-focus="run-id"]').fill("run-next-opening")
        page.locator('[data-focus="cycle-id"]').fill("cycle-next-opening")
        model = page.locator('[data-focus^="model-"]').first
        model_key = model.get_attribute("data-focus")
        model.fill("next-model")
        # Keep no text input focused: focus restoration must not conceal an
        # opening-cleared event by copying one old DOM value back afterwards.
        page.locator("#navWorkflow").focus()
        _release_open(page, url, held)
        expect(page.locator('[data-focus="run-id"]')).to_have_value("run-next-opening")
        expect(page.locator('[data-focus="cycle-id"]')).to_have_value("cycle-next-opening")
        expect(page.locator(f'[data-focus="{model_key}"]')).to_have_value("next-model")
        # Run creation uses the workflow write channel. A final global notice
        # cannot leave that channel claiming its POST is still in flight.
        save_line = page.locator("#workflowToolbar [data-save]")
        expect(save_line).not_to_have_attribute("data-save", "submitting")
        expect(save_line).not_to_contain_text("Writing")
        assert window.writes("/command/runs") == 1
        assert RunStore(configured_project.root).read("run-first-opening").config["task"]["id"] == selected_task(page)
        assert not RunStore(configured_project.root).run_path("run-next-opening").exists()
        assert window.writes("/proposals") == window.writes("/actions") == 0
        assert window.page_errors == []
    finally:
        page.unroute_all(behavior="ignoreErrors")
        page.context.close()


def test_a_late_task_creation_keeps_the_run_chosen_within_the_original_task(
        chromium: Browser, configured_project: _Project) -> None:
    page, window = _open(chromium, configured_project, double=True)
    held = []
    try:
        _model_form(page, "late-task-navigation")
        task_a = selected_task(page)
        _open_run(page, "run-original-a1")
        _open_run(page, "run-selected-a2")
        page.locator("#navRuns").click()
        choose_run(page, "run-original-a1")
        expect(page.locator("#bodyRuns .studio-runs__detail")).to_contain_text("run-original-a1")
        url = configured_project.url + "command/tasks"

        def hold_task(route):
            if route.request.method == "POST":
                response = route.fetch()
                assert response.status == 201, response.json()
                held.append((route, response))
                page.evaluate("() => { window.__raceTaskReachedServer = true; }")
            else:
                route.continue_()

        page.route(url, hold_task)
        _task_title(page).fill("Created while choosing another run")
        page.get_by_role("button", name="Create task", exact=True).click()
        page.wait_for_function("() => window.__raceTaskReachedServer === true")
        assert len(held) == 1
        task_b = held[0][1].json()["task"]["task_id"]
        assert task_b != task_a
        assert TaskStore(configured_project.root).read(task_b).title == "Created while choosing another run"
        # No title edit and no task selection change: those two guards cannot
        # substitute for the separate intent to inspect a different run.
        choose_run(page, "run-selected-a2")
        expect(page.locator("#bodyRuns .studio-runs__detail")).to_contain_text("run-selected-a2")
        assert selected_task(page) == task_a
        with page.expect_response(lambda response: response.request.method == "GET"
                                  and response.url == url):
            held[0][0].fulfill(response=held[0][1])
        expect_selected_task(page, task_a)
        expect(page).to_have_url(re.compile(r"(?:[&#])run=run-selected-a2(?:&|$)"))
        expect(page.locator("#bodyRuns .studio-runs__detail")).to_contain_text("run-selected-a2")
        assert RunStore(configured_project.root).read("run-selected-a2").config["task"]["id"] == task_a
        assert TaskStore(configured_project.root).read(task_b).title == "Created while choosing another run"
        assert window.writes("/command/tasks") == 2
        assert window.writes("/proposals") == window.writes("/actions") == 0
        assert window.page_errors == []
    finally:
        page.unroute_all(behavior="ignoreErrors")
        page.context.close()


#: Where a person types on the chosen run: a step's proposal and a document's content.
TYPED_FIELDS = {"step": '#bodyRuns [data-step^="propose:"] [name="proposed_by"]',
                "document": '#bodyRuns [data-step="document"] [name="content"]'}


@pytest.mark.parametrize("draft", sorted(TYPED_FIELDS))
def test_a_late_task_creation_leaves_the_run_a_person_is_typing_in_untouched(
        chromium: Browser, configured_project: _Project, draft: str) -> None:
    page, window = _open(chromium, configured_project, double=True)
    held = []
    try:
        _model_form(page, "late-typing")
        task_a = selected_task(page)
        _open_run(page, "run-typing")
        page.locator("#navRuns").click()
        choose_run(page, "run-typing")
        expect(page.locator("#bodyRuns .studio-runs__detail")).to_contain_text("run-typing")
        url = configured_project.url + "command/tasks"

        def hold_task(route):
            if route.request.method == "POST":
                response = route.fetch()
                assert response.status == 201, response.json()
                held.append((route, response))
                page.evaluate("() => { window.__raceTaskReachedServer = true; }")
            else:
                route.continue_()

        page.route(url, hold_task)
        _task_title(page).fill("Created while typing")
        page.get_by_role("button", name="Create task", exact=True).click()
        page.wait_for_function("() => window.__raceTaskReachedServer === true")
        assert len(held) == 1
        # Words typed into a step of the chosen run while the answer is on its way.
        who = page.locator(TYPED_FIELDS[draft]).first
        who.fill("release-owner")
        who.blur()
        with page.expect_response(lambda response: response.request.method == "GET"
                                  and response.url == url):
            held[0][0].fulfill(response=held[0][1])
        expect_selected_task(page, task_a)
        expect(page.locator("#bodyRuns .studio-runs__detail")).to_contain_text("run-typing")
        expect(who).to_have_value("release-owner")
    finally:
        assert window.console_errors == [] and window.page_errors == []
        page.context.close()
