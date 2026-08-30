"""What `conduct demo` actually shows a person, in a real Chromium.

This is the front door. Somebody who has installed this product and typed one
command meets exactly this screen, and for a while what it said was that the
project had no workflow, no run and nothing waiting -- over a directory that
held all three, because the packaged fixture is Protocol v1 and the Studio
reads the command surface.

The server here is the production one over a project built the way `conduct
demo` builds it: `demo.materialize` for the v1 half and `demo.populate` for the
command half. Nothing is seeded by hand, so a story the builder stops writing is
a story this module stops finding.

Every assertion is about RENDERED text. The Python tests beside this one already
prove the durable records are there and replay clean; the open question a
browser answers is whether any of that reaches the screen, and that is a
different question -- three of these facts travel through a payload boundary
that refuses a whole answer when one key moves.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page

from conductor import demo, server
from conductor.command import demo_scenario


@pytest.fixture(scope="session")
def demo_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The demo project, built by both halves, served at its own entry route."""
    root = demo.materialize(tmp_path_factory.mktemp("studio-demo"))
    demo.populate(root)
    httpd = server.build(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}/"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "demo server did not stop"


def _watch(page: Page) -> list[str]:
    problems: list[str] = []
    page.on("console", lambda message: problems.append(
        getattr(message, "text", ""))
        if getattr(message, "type", "") == "error" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))
    return problems


@pytest.fixture
def front_door(chromium: Browser, demo_url: str) -> Iterator[tuple[Page, list[str]]]:
    """The demo's front door, booted and connected, on the Overview screen."""
    context = chromium.new_context(viewport={"width": 1500, "height": 1200})
    page = context.new_page()
    problems = _watch(page)
    page.goto(demo_url, wait_until="load")
    page.wait_for_function(
        "() => document.getElementById('studioPrimary').children.length > 0")
    page.wait_for_selector('#studioConnection[data-connection="open"]')
    try:
        yield page, problems
    finally:
        context.close()


def test_the_demo_front_door_is_not_empty(front_door) -> None:
    """The finding, as a person met it.

    Measured before the repair as an Overview with no run to name at all: the
    "most recent run" section had nothing in it, because the project held no
    runs. The Overview is the first screen and the only one somebody sees
    without clicking, so it is where "populated" has to be true first.
    """
    page, problems = front_door
    overview = page.locator("#screenOverview")

    assert overview.get_attribute("data-state") == "ready", (
        overview.locator("#stateOverview").inner_text())
    said = overview.inner_text()
    assert "web-app" in said, said
    assert demo_scenario.RUN_ID in said, said
    assert "succeeded" in said, said
    # The waiting gate is counted where a person first looks for it.
    assert "Gates waiting" in said, said
    assert problems == []


def test_the_workflow_screen_opens_the_demo_s_published_revision(
        front_door) -> None:
    """A published revision, drawn as the immutable document it is."""
    page, problems = front_door
    page.locator("#navWorkflow").click()
    page.locator("#workflowToolbar select[name='workflow']").select_option(
        demo_scenario.WORKFLOW_ID)
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')

    said = page.locator(".studio-canvas__document").inner_text()
    assert f"revision {demo_scenario.REVISION}" in said, said
    assert page.locator("[data-node-id]").count() >= 5, "the plan drew no steps"
    assert problems == []


def _read_the_demo_run(page: Page) -> None:
    """Open the run whole, which is what a person does to see anything in it."""
    page.locator("#navRuns").click()
    page.wait_for_function(
        "() => document.getElementById('bodyRuns').innerText.includes('"
        + demo_scenario.RUN_ID + "')")
    page.get_by_role("button", name=demo_scenario.RUN_ID).first.click()
    page.wait_for_function(
        "() => document.getElementById('bodyRuns').innerText"
        ".includes('action_result')")


def test_the_runs_screen_lists_the_demo_run_with_its_outcome(
        front_door) -> None:
    """The list, before anything is opened: one run, its outcome, its gate."""
    page, problems = front_door
    page.locator("#navRuns").click()
    page.wait_for_function(
        "() => document.getElementById('bodyRuns').innerText.includes('"
        + demo_scenario.RUN_ID + "')")

    said = page.locator("#bodyRuns").inner_text()
    assert "succeeded" in said, said
    assert "1 gate(s) waiting" in said, said
    # WHICH plan it followed, in the LIST row rather than only after opening it.
    # This test used to assert the outcome and the gate and stop there, which
    # was exactly the shape of the complaint: two runs of two workflows were
    # indistinguishable until you clicked into each. The payload carried both
    # halves the whole time; the row simply did not render them.
    assert (f"{demo_scenario.WORKFLOW_ID} rev {demo_scenario.REVISION}"
            in said), said
    assert problems == []


def test_the_opened_run_names_the_exact_revision_it_followed(
        front_door) -> None:
    """Run identity, on the screen rather than only in the frozen bytes.

    The workflow and the revision are read out of the run's own frozen
    configuration -- the document its `config_digest` is taken over -- so a run
    that showed a plausible workflow instead of its real one would be a
    different defect entirely. This is the demo demonstrating that property.
    """
    page, problems = front_door
    _read_the_demo_run(page)

    said = page.locator("#bodyRuns").inner_text()
    assert demo_scenario.WORKFLOW_ID in said, said
    assert f"revision {demo_scenario.REVISION}" in said, said
    assert problems == []


def test_the_run_draws_its_whole_durable_timeline(front_door) -> None:
    """Every record the run really holds, drawn in append order.

    The five-step progression is what the Runs screen exists to make legible --
    proposal, request, lease, observation, result -- and a demo that showed a
    run with no journal would demonstrate the run list and nothing else.
    """
    page, problems = front_door
    _read_the_demo_run(page)

    said = page.locator("#bodyRuns").inner_text()
    for record in ("action_proposal", "action_request", "attempt_event",
                   "evidence", "action_result"):
        assert record in said, f"{record} is not on screen"
    assert problems == []


def test_the_decisions_screen_shows_the_gate_still_waiting_for_a_person(
        front_door) -> None:
    """One gate answered and one waiting is the pair that explains the concept.

    Waiting is not a durable record -- it is a gate no receipt has answered --
    so this is also the demonstration that the product can SHOW an absence.
    """
    page, problems = front_door
    # The Decisions screen is about ONE run's gates, so it says nothing until a
    # run has been read. That is the product's own order and the demo follows it.
    _read_the_demo_run(page)
    page.locator("#navDecisions").click()
    page.wait_for_function(
        "() => document.getElementById('screenDecisions')"
        ".dataset.state !== 'empty'")

    said = page.locator("#screenDecisions").inner_text()
    assert demo_scenario.WAITING_GATE in said, said
    assert demo_scenario.ANSWERED_GATE in said, said
    # Both gates, each carrying its own state: one a person has answered and
    # one still asking. Shown together, they are what makes the concept legible
    # -- an answered gate alone never shows what is being asked, and a waiting
    # one alone never shows what an answer looks like afterwards.
    assert "gate satisfied" in said, said
    assert "gate idle" in said, said
    assert problems == []


def test_the_demo_front_door_does_not_open_on_five_blockers(front_door) -> None:
    """The mandate's own complaint, measured where a first-time visitor meets it.

    The Overview greeted a new visitor with five blocking rows -- one per
    catalogued provider, each `unconfigured` -- before they had chosen a
    workflow that needed any of them. Nothing was wrong with the machine; it
    was a fresh install being described as five problems.

    What is blocking now is a capability the CHOSEN revision declares that no
    available provider serves, so nothing is blocking until a workflow is
    chosen, and the row names the capability and the steps rather than the
    product. Both halves are asserted: the five rows are gone, and the thing
    that replaced them still appears when it is true.
    """
    page, problems = front_door
    said = page.locator("#screenOverview").inner_text().lower()

    assert "5 blocking" not in said, said
    assert "is unconfigured on this machine" not in said, said

    page.locator("#navWorkflow").click()
    page.locator("#workflowToolbar select[name='workflow']").select_option(
        demo_scenario.WORKFLOW_ID)
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')
    page.locator("#navOverview").click()
    page.wait_for_function(
        "() => document.getElementById('screenOverview').innerText"
        ".toLowerCase().includes('no available provider serves')")

    moved = page.locator("#screenOverview").inner_text().lower()
    assert "no available provider serves dispatch" in moved, moved
    assert "step(s) of this workflow need it" in moved, moved
    # And it is still not one row per provider: the demo configures none, and
    # the roster has five, so a rule that had merely been reworded would show
    # five rows here too.
    assert moved.count("no available provider serves") <= 2, moved
    assert problems == []
