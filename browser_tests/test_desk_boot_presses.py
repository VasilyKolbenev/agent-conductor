"""A press made while the desk is still booting is never undone by the boot.

The boot reads the address once, at its start, and applies it when its lists have landed. A person
on a slow machine can press a panel's toggle, or the new task button, in between; the boot would
then apply the address it read to a desk that has moved on, and close what the person had just
opened. The reads of the boot are HELD here (the project claim, which is read first, or the tasks
list, which is read after it), which is the window a slow machine makes, and the press is made
inside it: a real press of the mouse, forced, so that it is made whether or not the control looks
available. What the desk allowed is read off the control before the press, and what is judged
after the read lands is that the allowed press stands.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Browser, expect

from browser_tests.desk_hold import Hold, close_context, until
from browser_tests.desk_wizard_bench import desk_url  # noqa: F401  (the fixture)
from browser_tests.test_desk_rail_scene import seeded_url  # noqa: F401  (a fixture)

#: What each toggle of the top bar opens: the word of the address and the region that shows it.
PANELS = {"deskFlowToggle": ("cycle", "#deskFlow"), "deskPeopleToggle": ("people", "#deskPeople"),
          "deskRunToggle": ("run", "#deskRun")}
#: Every control a person can use before the desk has drawn a list.
CONTROLS = [*PANELS, "deskNewTask"]
#: The reads of the boot that a test may hold: the claim comes first, the lists after it.
CLAIM, TASKS = "**/command/project", "**/command/tasks"


def _booting(chromium: Browser, desk_url: str, read: str):  # noqa: F811
    """A window whose boot is waiting for `read`, which is held."""
    context = chromium.new_context(viewport={"width": 1100, "height": 1200})
    page = context.new_page()
    held = Hold(page, read)
    held.hold()
    page.goto(f"{desk_url}/panel/desk.html#lang=en", wait_until="load")
    until(page, f"the boot's read {read} is held", held.reached)
    return context, page, held


def _booted(page) -> None:
    """The boot has applied its address: the stream opens after it, and not before."""
    expect(page.locator("#deskShell")).to_have_attribute("data-connection", "open")


@pytest.mark.parametrize("read", [CLAIM, TASKS], ids=["claim", "tasks"])
@pytest.mark.parametrize("control", list(PANELS))
def test_a_panel_pressed_while_the_boot_reads_is_still_open_when_the_read_lands(
        chromium: Browser, desk_url: str, control: str, read: str):  # noqa: F811
    panel, region = PANELS[control]
    context, page, held = _booting(chromium, desk_url, read)
    try:
        toggle = page.locator(f"#{control}")
        allowed = toggle.is_enabled()
        toggle.click(force=True)
        held.land()
        _booted(page)
        assert toggle.get_attribute("aria-expanded") == str(allowed).lower()
        assert page.locator(region).is_visible() == allowed
        assert (f"panel={panel}" in page.url) == allowed
    finally:
        close_context(context)


def test_the_wizard_opened_while_the_boot_reads_its_lists_is_still_open_when_they_land(
        chromium: Browser, desk_url: str):  # noqa: F811
    context, page, held = _booting(chromium, desk_url, TASKS)
    try:
        opener = page.locator("#deskNewTask")
        allowed = opener.is_enabled()
        opener.click(force=True)
        if allowed:
            expect(page.locator("#deskWizard [data-wizard]")).to_be_visible()
        held.land()
        _booted(page)
        assert page.locator("#deskWizard").is_visible() == allowed
        assert ("new=task" in page.url) == allowed
    finally:
        close_context(context)


def test_a_panel_pressed_while_the_boot_reads_the_run_its_address_names_is_not_replaced_by_it(
        chromium: Browser, seeded_url: str):  # noqa: F811
    """The boot's navigation also waits for the run of the task the address names; the address
    names the people panel, and a press made in that wait is the person's, not the address's."""
    context = chromium.new_context(viewport={"width": 1100, "height": 1200})
    page = context.new_page()
    held = Hold(page, "**/command/runs/run-fix-new")
    held.hold()
    try:
        page.goto(f"{seeded_url}#task=task-fix&panel=people&lang=en", wait_until="load")
        until(page, "the boot's read of the run is held", held.reached)
        toggle = page.locator("#deskFlowToggle")
        allowed = toggle.is_enabled()
        toggle.click(force=True)
        held.land()
        _booted(page)
        assert (toggle.get_attribute("aria-expanded") == "true") == allowed
        assert (page.locator("#deskPeopleToggle").get_attribute("aria-expanded")
                == "true") == (not allowed), "the address's panel opens when no press was made"
        assert ("panel=cycle" in page.url) == allowed and ("panel=people" in page.url) != allowed
    finally:
        close_context(context)


@pytest.mark.parametrize("read", [CLAIM, TASKS], ids=["claim", "tasks"])
def test_every_control_that_opens_something_is_off_while_the_boot_reads_and_on_when_it_is_over(
        chromium: Browser, desk_url: str, read: str):  # noqa: F811
    context, page, held = _booting(chromium, desk_url, read)
    try:
        for control in CONTROLS:
            expect(page.locator(f"#{control}")).to_be_disabled()
        held.land()
        _booted(page)
        for control in CONTROLS:
            expect(page.locator(f"#{control}")).to_be_enabled()
        page.locator("#deskFlowToggle").click()
        expect(page.locator("#deskFlow")).to_be_visible()
        assert "panel=cycle" in page.url
    finally:
        close_context(context)
