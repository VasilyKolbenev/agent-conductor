"""The real desk and Studio, served for a run whose plan ended `stalled`, offer nothing it refuses.

The run is driven on the flow bench (`tests/flow_driver_bench.py`) through the server's own doors
and bound to a task: its first step may be tried once and answers `unknown`, so the plan ends
`stalled` and the run records the ending. From then on its journal takes no pause, revoke or
resume. The desk showed the run stopped and holding the slot, with "Free the slot" (a pause or a
revoke the door refused), and the Studio "Needs attention before continuing" with Resume and
Revoke. Now the slot is free, the task's row says how its last action ended, and the Studio says
the plan ended and draws no control at all.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, expect

from browser_tests.desk_hold import close_context
from tests.flow_driver_bench import FlowCycle
from tests.test_command_flow_driver import DOER
from tests.test_command_workflow_flow import chain, review, step

TASK = "task-ended"


@pytest.fixture
def ended(tmp_path) -> Iterator[str]:
    """The server's address once the run's plan has ended `stalled` and the ending is recorded."""
    analyst = review("analyst")
    analyst = {**analyst, "ext": {**analyst["ext"], "attempt_bound": 1}}
    run = FlowCycle(tmp_path / "project", chain(analyst, DOER, step("result", "human")),
                    through_doors=True, task=TASK, outcomes={"analyst": ["unknown"]})
    try:
        run.start()
        run.until("the stalled ending",
                  lambda: run.plan_state() == "stalled" and bool(run.terminal()))
        host, port = run.subject.server_address[:2]
        yield f"http://{host}:{port}/"
    finally:
        run.close()


def test_the_desk_shows_the_slot_free_and_offers_nothing_to_free_it(chromium: Browser, ended):
    context = chromium.new_context(viewport={"width": 1400, "height": 1000})
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"{ended}panel/desk.html#task={TASK}&lang=en", wait_until="load")
        expect(page.locator("#deskShell")).to_have_attribute("data-connection", "open")
        expect(page.locator(".desk-queue__now")).to_have_text(
            "Now: nothing is running · the slot is free")
        expect(page.locator(f'[data-task-id="{TASK}"] .desk-task__state')).to_have_text(
            "Outcome unknown")
        expect(page.locator('[data-focus-key="queue:release"]')).to_have_count(0)
        expect(page.locator("[data-pult-slot-hint]")).to_have_count(0)
        assert errors == []
    finally:
        close_context(context)


def test_the_studio_says_the_plan_ended_and_draws_no_control(chromium: Browser, ended):
    context = chromium.new_context(viewport={"width": 1700, "height": 1400}, locale="en-US")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(ended, wait_until="load")
        expect(page.locator("#studioConnection")).to_have_attribute("data-connection", "open")
        page.get_by_role("button", name="Read this run", exact=True).click()
        box = page.locator('[data-automation="run"]')
        state = box.locator("[data-automation-state]")
        expect(state).to_have_attribute("data-automation-state", "complete")
        expect(state.locator("h4")).to_have_text("Plan ended; check the recorded results")
        expect(state).to_contain_text(
            "No further step is eligible. This is not a quality verdict.")
        for key in ("pause", "resume", "revoke", "preview", "authorize"):
            expect(box.locator(f'[data-focus="automation:{key}"]')).to_have_count(0)
        page.locator('[data-focus="preference-language"]').select_option("ru")
        expect(state.locator("h4")).to_have_text(
            "План завершён; проверьте записанные результаты")
        assert errors == []
    finally:
        close_context(context)
