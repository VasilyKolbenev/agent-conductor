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
from playwright.sync_api import Browser, Locator, Page, expect

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
    # Where a person first looks, the latest run says whether a person is needed: the
    # server's own reading (`human_state`), never a blind count of undecided gates.
    latest = _overview_card(page, "The most recent run").inner_text()
    assert "Human attention" in latest and "You are needed" in latest, latest
    assert "Gates waiting" not in said and "gate(s) waiting" not in said, said
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
    # The list row carries the server's reading of whether a person is needed, and
    # no blind count of undecided gates beside it (MAIN-UI-STUDIO-PORT-SPEC §5.2).
    assert "human attention required" in said, said
    assert "gate(s) waiting" not in said, said
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
    # The screen names itself once, and each gate reads as three things apart -- its title, the
    # run and gate it is, its state -- in the accessible name as well as on the screen.
    expect(page.locator("#screenDecisions h2")).to_have_count(1)
    key = f"{demo_scenario.RUN_ID}/{demo_scenario.WAITING_GATE}"
    gate = page.locator(".studio-decision", has=page.locator(".studio-decision__id", has_text=key))
    assert f" {key} " in gate.evaluate("n => n.textContent"), gate.evaluate("n => n.textContent")
    title = gate.locator(".studio-decision__t").bounding_box()
    ident = gate.locator(".studio-decision__id").bounding_box()
    assert ident["y"] >= title["y"] + title["height"] - 1, (title, ident)
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


# The expected order is a reading order, not a census of the CSS classes that
# happen to implement it. Geometry below must agree with these visible headings.
OVERVIEW_HEADINGS = (
    "The most recent run", "Human attention", "What is blocked",
    "Ready to run?", "What this is",
)


def _overview_card(page: Page, title: str) -> Locator:
    return page.locator("#bodyOverview > section").filter(
        has=page.get_by_role("heading", name=title, exact=True))


def _overview_geometry(page: Page) -> list[dict]:
    page.wait_for_selector('#screenOverview[data-state="ready"]:not([hidden])')
    expect(page.locator("#bodyOverview").get_by_role(
        "button", name="Read this run", exact=True)).to_be_visible()
    # Found and measured in ONE evaluation. Every render replaces these cards and reads still
    # land after the screen says ready; a locator's evaluate_all finds the cards in one round
    # trip and measures them in the next, so a render between the two measured detached nodes.
    return page.evaluate(
        """() => [...document.querySelectorAll('#bodyOverview > section')].map(card => {
          const box = card.getBoundingClientRect();
          const style = getComputedStyle(card);
          return {title: card.querySelector('h3').textContent,
            left: box.left, right: box.right, top: box.top, bottom: box.bottom,
            width: box.width, height: box.height,
            visible: style.display !== 'none' && style.visibility !== 'hidden'
              && box.width > 0 && box.height > 0};
        })""")


def test_overview_shows_latest_run_and_attention_together_on_a_laptop(
        front_door) -> None:
    """The useful first row fits the first screen, without changing its facts."""
    page, problems = front_door
    page.set_viewport_size({"width": 1280, "height": 800})
    cards = _overview_geometry(page)
    assert tuple(card["title"] for card in cards) == OVERVIEW_HEADINGS
    latest, attention, *secondary = cards
    for card in (latest, attention):
        assert card["visible"] and 0 <= card["top"] < card["bottom"] <= 800, card
    assert abs(latest["top"] - attention["top"]) <= 1, cards
    assert latest["right"] < attention["left"], cards
    assert all(card["top"] >= latest["bottom"] for card in secondary), cards
    said = _overview_card(page, "The most recent run").inner_text()
    assert demo_scenario.RUN_ID in said and "last outcome: succeeded" in said
    assert problems == []


def test_overview_keeps_every_card_readable_in_one_narrow_column(
        front_door) -> None:
    """No clipped card or horizontal page scroll hides the secondary facts."""
    page, problems = front_door
    page.set_viewport_size({"width": 500, "height": 800})
    cards = _overview_geometry(page)
    assert tuple(card["title"] for card in cards) == OVERVIEW_HEADINGS
    assert all(card["visible"] for card in cards), cards
    for earlier, later in zip(cards, cards[1:]):
        assert later["top"] >= earlier["bottom"], cards
        assert abs(later["left"] - earlier["left"]) <= 1, cards
        assert abs(later["width"] - earlier["width"]) <= 1, cards
    for title in OVERVIEW_HEADINGS:
        card = _overview_card(page, title)
        card.scroll_into_view_if_needed()
        expect(card.get_by_role("heading", name=title, exact=True)).to_be_visible()
        box = card.bounding_box()
        assert box is not None and box["x"] >= 0, box
        assert box["x"] + box["width"] <= 500, box
    assert page.evaluate(
        "() => Math.max(document.documentElement.scrollWidth, "
        "document.body.scrollWidth) - document.documentElement.clientWidth") == 0
    assert problems == []


# A render queued behind every query that finds the Overview's cards, through the language
# control's own door: choosing the language already chosen changes no fact and redraws every
# mount. A microtask lands after the query holds its nodes and before any later step can run.
_RENDER_AFTER_EVERY_FIND = """() => {
  window.rendersQueued = 0;
  const language = document.querySelector('#studioPreferences select[name="language"]');
  let pending = false;
  for (const kind of [Document, Element]) {
    const find = kind.prototype.querySelectorAll;
    kind.prototype.querySelectorAll = function (selector) {
      const found = find.call(this, selector);
      if (!pending && [...found].some((node) => node.parentElement?.id === "bodyOverview")) {
        pending = true;
        window.rendersQueued += 1;
        queueMicrotask(() => {
          language.dispatchEvent(new Event("change"));
          pending = false;
        });
      }
      return found;
    };
  }
}"""


def test_overview_geometry_is_read_from_the_cards_on_screen_when_a_render_follows_every_find(
        front_door) -> None:
    """Every render replaces the Overview's cards, and reads still land after it says ready.

    Measured at frozen-17 in the reverse gate: a render landed between finding the cards and
    measuring them, and five detached sections came back with their titles and every box zero
    while the screen showed them whole. Here a render follows every query that finds them.
    """
    page, problems = front_door
    page.evaluate(_RENDER_AFTER_EVERY_FIND)
    for width in (1280, 500):
        page.set_viewport_size({"width": width, "height": 800})
        cards = _overview_geometry(page)
        assert tuple(card["title"] for card in cards) == OVERVIEW_HEADINGS
        assert all(card["visible"] for card in cards), cards
    assert page.evaluate("() => window.rendersQueued") >= 2
    assert problems == []


def _assert_overview_keyboard_order(page: Page) -> None:
    expected = ["Read this run", "Open decisions", "Choose a workflow"]
    controls = page.locator("#bodyOverview").get_by_role("button")
    assert controls.all_text_contents() == expected
    controls.first.focus()
    for index, label in enumerate(expected):
        if index:
            page.keyboard.press("Tab")
        assert page.evaluate("() => document.activeElement.textContent") == label


def test_overview_run_link_opens_its_history_and_scopes_attention_to_that_run(
        front_door) -> None:
    """No selection is unknown attention, not proof that nobody is waiting."""
    page, problems = front_door
    _overview_geometry(page)
    attention = _overview_card(page, "Human attention")
    # No run read yet: the need is not established -- never "nobody is needed", never zero.
    expect(attention).to_contain_text("Needs are not established")
    assert "No action is needed" not in attention.inner_text()
    assert "Decisions needed" not in attention.inner_text()
    assert attention.get_by_role("button", name="Open decisions", exact=True).count() == 0
    latest = _overview_card(page, "The most recent run").inner_text()
    assert "You are needed" in latest and "Gates waiting" not in latest, latest
    opener = page.locator("#bodyOverview").get_by_role(
        "button", name="Read this run", exact=True)
    opener.focus()
    page.keyboard.press("Enter")
    page.wait_for_selector("#screenRuns:not([hidden]) ol.studio-timeline")
    detail = page.locator(".studio-runs__detail")
    # The demo run belongs to a named task, so the header names the task, not the run id.
    expect(detail.get_by_role("heading", level=2)).to_have_text(demo_scenario.TASK_TITLE)
    expect(detail.locator("p").filter(has_text="Workflow").first).to_have_text(
        f"Workflow{demo_scenario.WORKFLOW_ID}")
    expect(detail.locator("p").filter(has_text="Revision").first).to_have_text(
        f"Revisionrevision {demo_scenario.REVISION}")
    kinds = page.locator("ol.studio-timeline > li").evaluate_all(
        "rows => rows.map(row => row.querySelector('.studio-row__head "
        ".studio-mono').textContent)")
    assert kinds == ["graph_definition", "decision", "action_proposal",
                     "action_request", "attempt_event", "attempt_event",
                     "evidence", "action_result"]
    page.locator("#navOverview").click()
    # The opened run's verified situation: one decision is needed now (the result gate),
    # and the gate answered on this lap is not counted as a current need.
    expect(attention).to_contain_text("You are needed")
    expect(attention).to_contain_text("Decisions needed: 1")
    assert "Needs are not established" not in attention.inner_text()
    _assert_overview_keyboard_order(page)
    # And the attention is about THIS run: its action opens this run's waiting gate.
    attention.get_by_role("button", name="Open decisions", exact=True).click()
    decisions = page.locator("#screenDecisions")
    expect(decisions).to_contain_text(demo_scenario.WAITING_GATE)
    assert demo_scenario.RUN_ID in decisions.inner_text()
    assert problems == []


def test_the_demo_run_is_named_by_its_task_and_its_header_offers_what_it_needs(front_door) -> None:
    """The run belongs to a named task, so the header names the task, says where the run stands and who
    is needed, and its one main action is that need's own door: the waiting result gate."""
    page, problems = front_door
    page.locator("#navRuns").click()
    rail = page.locator(".studio-task-rail")
    expect(rail).to_contain_text(demo_scenario.SECOND_TASK_TITLE)
    page.locator(f'[data-task-id="{demo_scenario.TASK_ID}"]').click()
    heading = page.locator("#bodyRuns .studio-runs__heading")
    expect(heading.get_by_role("heading", level=2)).to_have_text(demo_scenario.TASK_TITLE)
    situation = heading.locator("[data-run-situation]")
    expect(situation).to_have_attribute("data-run-situation", "required")
    expect(situation).to_have_text("In progress · You are needed · Decisions needed: 1")
    # The cycle under the tasks is this run's own: its process and revision, its crew, its one loop.
    card = page.locator(f'#studioTasks [data-cycle-run="{demo_scenario.RUN_ID}"]')
    expect(card).to_contain_text(f"Release review · revision {demo_scenario.REVISION}")
    expect(card).to_contain_text("Participants: 3 · human gates: 2")
    expect(card.locator("[data-cycle-loop]")).to_have_count(1)
    expect(card.locator("[data-cycle-member]")).to_have_count(len(demo_scenario.PARTICIPANTS))
    main = page.locator('#studioPrimary [data-run-action="decide"]')
    expect(main).to_have_text("Make the decision")
    main.click()
    decisions = page.locator("#screenDecisions")
    expect(decisions).to_contain_text(demo_scenario.WAITING_GATE)
    assert demo_scenario.RUN_ID in decisions.inner_text()
    assert problems == []


# Independent literal pins for Studio's owner-approved command-deck palette,
# not the unchanged classic panel/Graph palette or a value read back from CSS.
@pytest.mark.parametrize("theme,background,ink", [
    ("dark", "rgb(11, 15, 13)", "rgb(239, 244, 233)"),
    ("light", "rgb(230, 236, 230)", "rgb(24, 36, 28)"),
])
def test_demo_decision_choices_keep_native_keyboard_state_and_themed_surfaces(
        front_door, theme, background, ink) -> None:
    """Selection is local; no incomplete answer is submitted by this exercise."""
    page, problems = front_door
    page.emulate_media(color_scheme=theme)
    writes = []
    page.on("request", lambda request: writes.append(request.url)
            if request.method == "POST" and "/decisions" in request.url else None)
    _read_the_demo_run(page)
    page.locator("#navDecisions").click()
    page.locator(f'[data-focus-key="decision:{demo_scenario.RUN_ID}/'
                 f'{demo_scenario.WAITING_GATE}"]').click()
    approve = page.locator('input[type="radio"][value="approve"]')
    reject = page.locator('input[type="radio"][value="reject"]')
    expect(approve).to_be_checked()
    expect(approve).to_be_enabled()
    expect(reject).not_to_be_checked()
    approve.focus()
    approve.press("ArrowRight")
    expect(reject).to_be_checked()
    expect(approve).not_to_be_checked()
    expect(reject).to_be_focused()
    paint = reject.evaluate("""node => {
      const style = getComputedStyle(node), box = node.getBoundingClientRect();
      return {background: style.backgroundColor, color: style.color,
        height: box.height, appearance: style.appearance};
    }""")
    assert paint["background"] == background and paint["color"] == ink, paint
    assert paint["height"] >= 44 and paint["appearance"] != "none", paint
    submit = page.get_by_role("button", name="Record this decision", exact=True)
    expect(submit).to_be_disabled()
    reject.press("Tab")
    expect(page.locator('[data-focus-key="field:actor"]')).to_be_focused()
    page.keyboard.press("Tab")
    expect(page.locator('[data-focus-key="field:reason"]')).to_be_focused()
    page.keyboard.press("Tab")
    expect(submit).not_to_be_focused()
    assert page.locator('input[type="radio"]:checked').input_value() == "reject"
    assert writes == [] and problems == []
