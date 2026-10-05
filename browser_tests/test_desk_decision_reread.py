"""A person partway through a decision keeps the list and the record they chose while the run is
read again, and writes nothing until the answer has landed.

Every full refresh the desk makes reads the chosen run again, and while that read is out the scene
says the run is "stale". The decisions the host holds belong to that same run, so they stay: the
list of gates, the record a person selected in it and what they typed. The card says it is
updating, and no write goes out until the fresh read lands; then the list is taken from it and the
selected record stays if the run still has it. A run or a task that is another subject starts over.
The window of the re-read is made by the test (the scene's controls read is held, the re-read is
started by a press on the run panel's own refresh), never hoped for.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, expect

from browser_tests.desk_hold import Hold, close_context, land_read, read_again
from browser_tests.desk_settled import SETTLED
from browser_tests.test_desk_hash import ON_RUN
from browser_tests.test_desk_rail_scene import seeded_url  # noqa: F401  (a fixture)

UPDATING = {"en": "Updating the run's data…", "ru": "Обновляем данные запуска…"}
FIX, CHECK = "run-fix-new", "run-check"
ADDRESS = "#task=task-fix&run=run-fix-new&panel=run&lang={language}"
#: The two gates of the seeded plan: the one that waits for an answer, and the one after it.
CURRENT, LATER = "gate-confirm-do", "gate-result"
#: A press on a control that says it is unavailable: the host must refuse it on its own account.
FORCE_PRESS = "(node) => { node.disabled = false; node.click(); }"


def _record(run: str, gate: str) -> str:
    return f'#deskRun [data-focus-key="decision:{run}/{gate}"]'


def _open(chromium: Browser, url: str, language: str = "en"):
    """A window on the run with its panel open, once its stream has opened."""
    context = chromium.new_context(viewport={"width": 1400, "height": 1000})
    page = context.new_page()
    page.set_default_timeout(8000)
    posts: list[str] = []
    page.on("request", lambda request: posts.append(urlsplit(request.url).path)
            if request.method == "POST" else None)
    controls = Hold(page, f"**/command/runs/{FIX}/controls")
    page.goto(f"{url}{ADDRESS.format(language=language)}", wait_until="load")
    page.wait_for_function(SETTLED)
    page.wait_for_function(ON_RUN, arg=FIX)
    expect(page.locator("#deskShell")).to_have_attribute("data-connection", "open")
    return context, page, controls, posts


def _read_again(page: Page, controls: Hold) -> None:
    read_again(page, controls, page.locator('#deskRun [data-focus-key="action:refreshRuns"]').click)


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_decision_list_and_the_record_a_person_selected_stay_while_the_run_is_read_again(
        chromium: Browser, seeded_url: str, language: str):  # noqa: F811
    context, page, controls, _posts = _open(chromium, seeded_url, language)
    try:
        for gate in (CURRENT, LATER):
            expect(page.locator(_record(FIX, gate))).to_have_count(1)
        page.locator(_record(FIX, LATER)).click()
        expect(page.locator(_record(FIX, LATER))).to_have_attribute("aria-pressed", "true")
        _read_again(page, controls)
        for gate in (CURRENT, LATER):
            expect(page.locator(_record(FIX, gate))).to_have_count(1)
        expect(page.locator(_record(FIX, LATER))).to_have_attribute("aria-pressed", "true")
        expect(page.locator(_record(FIX, CURRENT))).to_have_attribute("aria-pressed", "false")
        expect(page.locator("#deskPult [data-desk-decision]")).to_contain_text(UPDATING[language])
        land_read(page, controls)
        for gate in (CURRENT, LATER):
            expect(page.locator(_record(FIX, gate))).to_have_count(1)
        expect(page.locator(_record(FIX, LATER))).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#deskPult [data-desk-decision]")).not_to_contain_text(
            UPDATING[language])
    finally:
        close_context(context)


def test_no_decision_is_written_while_the_run_is_read_again_and_the_card_says_it_is_updating(
        chromium: Browser, seeded_url: str):  # noqa: F811
    context, page, controls, posts = _open(chromium, seeded_url)
    try:
        page.locator('[data-focus-key="pult:actor-change"]').click()
        page.locator('[data-focus-key="pult:actor-name"]').fill("desk-owner")
        page.locator('[data-focus-key="pult:actor-save"]').click()
        card = page.locator("#deskPult [data-desk-decision]")
        card.locator('[data-focus-key="choice:approve"]').check()
        submit = card.locator('[data-focus-key="action:submitDecision"]')
        expect(submit).to_be_enabled()
        expect(card).not_to_contain_text(UPDATING["en"])
        _read_again(page, controls)
        expect(card).to_be_visible()
        expect(card).to_contain_text(UPDATING["en"])
        expect(submit).to_be_disabled()
        submit.evaluate(FORCE_PRESS)
        page.evaluate("() => new Promise((done) => requestAnimationFrame(done))")
        assert [path for path in posts if path.endswith("/decisions")] == []
        expect(card.locator('[data-focus-key="choice:approve"]')).to_be_checked()
        land_read(page, controls)
        expect(submit).to_be_enabled()
        expect(card).not_to_contain_text(UPDATING["en"])
        assert [path for path in posts if path.endswith("/decisions")] == []
    finally:
        close_context(context)


def test_another_task_is_another_subject_and_starts_the_record_and_the_list_over(
        chromium: Browser, seeded_url: str):  # noqa: F811
    context, page, controls, _posts = _open(chromium, seeded_url)
    try:
        page.locator(_record(FIX, LATER)).click()
        expect(page.locator(_record(FIX, LATER))).to_have_attribute("aria-pressed", "true")
        page.locator('#deskRail [data-task-id="task-check"]').click()
        page.wait_for_function(ON_RUN, arg=CHECK)
        expect(page.locator(_record(FIX, LATER))).to_have_count(0)
        expect(page.locator(_record(CHECK, CURRENT))).to_have_attribute("aria-pressed", "true")
        expect(page.locator(_record(CHECK, LATER))).to_have_attribute("aria-pressed", "false")
        page.locator('#deskRail [data-task-id="task-fix"]').click()
        page.wait_for_function(ON_RUN, arg=FIX)
        expect(page.locator(_record(FIX, CURRENT))).to_have_attribute("aria-pressed", "true")
        expect(page.locator(_record(FIX, LATER))).to_have_attribute("aria-pressed", "false")
    finally:
        close_context(context)
